"""Start the installed production build on all three platforms; Ctrl+C stops both services."""

import argparse
import ipaddress
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402


def local_ipv4_addresses():
    """Discover local interface addresses without an external IP lookup service."""
    candidates = set()
    try:
        candidates.update(
            item[4][0]
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
        )
    except OSError:
        pass
    try:
        # UDP connect selects the default route; no packet is sent (no send/recv).
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            candidates.add(probe.getsockname()[0])
    except OSError:
        pass
    addresses = []
    for candidate in candidates:
        try:
            address = ipaddress.IPv4Address(candidate)
            if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
                continue
            # Only advertise addresses actually assigned to this host, not remote DNS results.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((str(address), 0))
            addresses.append(str(address))
        except (OSError, ValueError):
            continue
    return sorted(addresses, key=ipaddress.IPv4Address)


def access_urls(frontend, addresses):
    return [f"http://localhost:{frontend}", *[f"http://{address}:{frontend}" for address in addresses]]


def configure_origins(env, frontend, addresses):
    origins = [value.strip() for value in env.get("CORS_ORIGINS", "").split(",") if value.strip()]
    origins.extend(access_urls(frontend, addresses))
    origins.append(f"http://127.0.0.1:{frontend}")
    # Runtime only: preserve backend/.env and custom domains, never allow wildcard origins.
    env["CORS_ORIGINS"] = ",".join(dict.fromkeys(origins))


def print_access_urls(frontend, addresses):
    urls = access_urls(frontend, addresses)
    print("\n1devTeams is ready.", flush=True)
    print(f"  Localhost: {urls[0]}", flush=True)
    for url in urls[1:]:
        print(f"  Network:   {url}", flush=True)
    if not addresses:
        print("  Network: no usable local IPv4 address detected.", flush=True)
    print("Network access requires a reachable LAN/VPN and an allowed firewall port.", flush=True)
    print("Change the default Owner password before allowing network access.", flush=True)
    print("Keep this terminal open. Ctrl+C stops both services.", flush=True)


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Start, verify readiness and stop")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    args = parser.parse_args()
    runtime = json.loads((ROOT / ".tools/runtime.json").read_text(encoding="utf-8"))
    values = dotenv_values(ROOT / ".env", interpolate=False)
    frontend = int(values.get("FRONTEND_PORT") or 3060)
    backend = int(values.get("BACKEND_PORT") or 8060)
    if frontend == backend or not all(1 <= port <= 65535 for port in (frontend, backend)):
        raise ValueError("Invalid ports in root .env")
    for port in (frontend, backend):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    if not (ROOT / "frontend/.next-build/BUILD_ID").is_file():
        raise ValueError("Production build missing. Rerun the installer.")
    env = os.environ.copy()
    # Honor the installed backend config over unrelated IDE environment variables.
    setting_names = {name.upper() for name in Settings.model_fields}
    for key in list(env):
        if key.upper() in setting_names:
            del env[key]
    env.update(
        {
            key: value
            for key, value in dotenv_values(ROOT / "backend/.env", interpolate=False).items()
            if value is not None
        }
    )
    addresses = local_ipv4_addresses()
    configure_origins(env, frontend, addresses)
    env["BACKEND_URL"] = f"http://127.0.0.1:{backend}"
    env["NEXT_PUBLIC_API_URL"] = env["BACKEND_URL"]
    env["NEXT_DIST_DIR"] = ".next-build"
    env["PATH"] = os.pathsep.join(
        [
            str(Path(runtime["node"]).parent),
            str(Path(runtime["git"]).parent),
            str(ROOT / ".tools/providers/node_modules/.bin"),
            str(ROOT / "node_modules/.bin"),
            env.get("PATH", ""),
        ]
    )
    python = ROOT / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    logs = ROOT / ".dev-logs"
    logs.mkdir(exist_ok=True)
    children, streams = [], []
    try:
        for name, cwd, command in [
            (
                "installed-backend",
                ROOT / "backend",
                [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend)],
            ),
            (
                "installed-frontend",
                ROOT / "frontend",
                [
                    runtime["node"],
                    str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "0.0.0.0",
                    "--port",
                    str(frontend),
                ],
            ),
        ]:
            stream = (logs / f"{name}.log").open("a", encoding="utf-8")
            streams.append(stream)
            children.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=stream,
                    stderr=stream,
                    start_new_session=os.name != "nt",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            )
        deadline = time.monotonic() + 90
        while True:
            if any(child.poll() is not None for child in children):
                raise RuntimeError(f"A service exited. See logs in {logs}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{backend}/api/health", timeout=3) as response:
                    healthy = json.load(response).get("status") == "ok"
                with urllib.request.urlopen(f"http://127.0.0.1:{frontend}/login", timeout=5) as response:
                    healthy = healthy and response.status == 200
                if healthy:
                    break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Services were not ready within 90 seconds. See {logs}")
            time.sleep(0.5)
        print_access_urls(frontend, addresses)
        if args.check:
            return
        if not args.no_open:
            webbrowser.open(f"http://localhost:{frontend}")
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError(f"A service stopped. See {logs}")
    except KeyboardInterrupt:
        print("Stopping 1devTeams...")
    finally:
        for child in reversed(children):
            stop(child)
        for stream in streams:
            stream.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
