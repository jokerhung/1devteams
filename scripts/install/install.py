"""Shared installer, executed by uv's Python 3.12. No third-party imports here."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args, *, cwd=ROOT, env=None):
    print("Running: " + " ".join(map(str, args)), flush=True)
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def node_major(node):
    try:
        return int(
            subprocess.check_output([str(node), "--version"], text=True).strip().lstrip("v").split(".")[0]
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def node_archive(system, machine, checksums):
    os_name = {"Windows": "win", "Linux": "linux", "Darwin": "darwin"}[system]
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine.lower()
    )
    if not architecture:
        raise ValueError(f"Unsupported architecture: {machine}; use x64 or ARM64")
    extension = "zip" if system == "Windows" else "tar.gz"
    pattern = rf"node-v22\.\d+\.\d+-{os_name}-{architecture}\.{re.escape(extension)}"
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(pattern, parts[1]) and re.fullmatch(r"[a-f0-9]{64}", parts[0]):
            return parts[1], parts[0]
    raise ValueError(f"Official Node.js archive not found for {system}/{machine}")


def ensure_node():
    local = ROOT / ".tools" / "node"
    suffix = "node.exe" if os.name == "nt" else "bin/node"
    candidates = list(local.glob(f"node-*/{suffix}"))
    existing = shutil.which("node")
    if existing:
        candidates.append(Path(existing))
    for candidate in candidates:
        if node_major(candidate) >= 22:
            return candidate.resolve()
    base = "https://nodejs.org/dist/latest-v22.x/"
    with urllib.request.urlopen(base + "SHASUMS256.txt", timeout=60) as response:
        filename, expected = node_archive(
            platform.system(), platform.machine(), response.read().decode("ascii")
        )
    local.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="1devteams-node-") as temp:
        archive = Path(temp) / filename
        print(f"Downloading {filename} from nodejs.org...", flush=True)
        with urllib.request.urlopen(base + filename, timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        with archive.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Node.js checksum mismatch; archive was not installed")
        if filename.endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.namelist():
                    if not (local / member).resolve().is_relative_to(local.resolve()):
                        raise ValueError("Unsafe archive path")
                bundle.extractall(local)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(local, filter="data")
    stem = filename.removesuffix(".zip").removesuffix(".tar.gz")
    node = local / stem / suffix
    if node_major(node) != 22:
        raise ValueError("Downloaded Node.js could not start on this OS")
    return node


def npm_command(node):
    # Invoke npm's JS entrypoint directly, avoiding Windows .cmd quoting problems.
    candidates = [
        node.parent / "node_modules/npm/bin/npm-cli.js",
        node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js",
    ]
    system_npm = shutil.which("npm")
    if system_npm and Path(system_npm).resolve().name == "npm-cli.js":
        candidates.append(Path(system_npm).resolve())
    for candidate in candidates:
        if candidate.is_file():
            return [node, candidate]
    raise ValueError("npm is missing from the Node.js installation")


def preflight_ports(root, frontend, backend):
    """Read only the numeric port settings before touching installed dependencies."""
    ports = {"FRONTEND_PORT": frontend, "BACKEND_PORT": backend}
    path = root / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"\s*(?:export\s+)?(FRONTEND_PORT|BACKEND_PORT)\s*=(.*)", line)
            if match:
                value = re.fullmatch(r"\s*(['\"]?)(\d+)\1\s*(?:#.*)?", match[2])
                if not value:
                    raise ValueError(f"{match[1]} in root .env must be a numeric port")
                ports[match[1]] = int(value[2])
    if len(set(ports.values())) != 2 or not all(1 <= port <= 65535 for port in ports.values()):
        raise ValueError("Frontend/backend ports must be different and between 1 and 65535")
    for port in ports.values():
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as error:
                raise ValueError(f"Port {port} is in use. Stop the application before installing.") from error


def main():
    parser = argparse.ArgumentParser(
        description="Install 1devTeams dependencies, configuration and starter data"
    )
    parser.add_argument("--admin-email", default="owner@example.com")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--frontend-port", type=int, default=3060)
    parser.add_argument("--backend-port", type=int, default=8060)
    parser.add_argument("--public-url", default="")
    parser.add_argument("--trust-native-agents", action="store_true")
    parser.add_argument("--enable-remote-terminal", action="store_true")
    parser.add_argument("--skip-providers", action="store_true")
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    if (
        not all(1 <= p <= 65535 for p in [args.frontend_port, args.backend_port])
        or args.frontend_port == args.backend_port
    ):
        parser.error("Frontend/backend ports must be different and between 1 and 65535")
    uv, git = shutil.which("uv"), shutil.which("git")
    if not uv or not git:
        parser.error("Run the OS-specific installer first to install Git and uv")
    preflight_ports(ROOT, args.frontend_port, args.backend_port)
    node = ensure_node()
    npm = npm_command(node)
    env = os.environ.copy()
    # Always isolate backend dependencies here, even when the invoking shell
    # has UV_PROJECT_ENVIRONMENT pointing at another project or a system prefix.
    env["UV_PROJECT_ENVIRONMENT"] = str(ROOT / "backend/.venv")
    provider_bin = ROOT / ".tools/providers/node_modules/.bin"
    env["PATH"] = os.pathsep.join(
        [str(node.parent), str(provider_bin), str(Path(git).parent), env.get("PATH", "")]
    )
    run([uv, "sync", "--project", ROOT / "backend", "--python", "3.12", "--frozen"], env=env)
    python = ROOT / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([python, ROOT / "scripts/install/initialize.py", *sys.argv[1:]], env=env)
    state = json.loads((ROOT / ".tools/install-state.json").read_text())
    env["BACKEND_URL"] = f"http://127.0.0.1:{state['backend_port']}"
    env["NEXT_PUBLIC_API_URL"] = env["BACKEND_URL"]
    env["NEXT_DIST_DIR"] = ".next-build"
    run([*npm, "ci"], env=env)
    if not args.skip_providers:
        run(
            [
                *npm,
                "install",
                "--prefix",
                ROOT / ".tools/providers",
                "--no-audit",
                "--no-fund",
                "@anthropic-ai/claude-code",
                "@openai/codex",
            ],
            env=env,
        )
    run([*npm, "ci"], cwd=ROOT / "frontend", env=env)
    if not args.skip_browser:
        browser_args = [python, "-m", "playwright", "install"]
        if sys.platform.startswith("linux"):
            browser_args.append("--with-deps")
        run([*browser_args, "chromium"], env=env)
    run([*npm, "run", "build"], cwd=ROOT / "frontend", env=env)
    (ROOT / ".tools/runtime.json").write_text(
        json.dumps({"node": str(node), "git": git}, indent=2), encoding="utf-8"
    )
    print("\nInstallation complete. Agents, teams and templates are ready.")
    print(f"Start: {python} {ROOT / 'scripts/install/run.py'}")
    print("Open Settings > Adapters to log in to Claude/Codex. No provider credentials were created.")
    if not args.trust_native_agents:
        print(
            "Native agents require TRUSTED_NATIVE_ACP=true in backend/.env "
            "after reviewing their OS-level permissions."
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Installation stopped: {error}", file=sys.stderr)
        sys.exit(1)
