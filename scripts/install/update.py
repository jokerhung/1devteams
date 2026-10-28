"""Update an existing installation without replacing its configuration or user data."""

import json
import os
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = "https://github.com/jokerhung/1devteams/archive/refs/heads/main.zip"
SOURCE_DIRS = {"backend", "frontend", "scripts", "docs", ".github"}
SOURCE_FILES = {
    "install.sh",
    "install.ps1",
    "README.md",
    "package.json",
    "package-lock.json",
    ".gitattributes",
    ".gitignore",
    ".env.example",
}
RUNTIME_DIRS = {
    ".git",
    ".tools",
    ".venv",
    "node_modules",
    "data",
    "workspaces",
    "backups",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "test-results",
    "spike_logs",
    "config",
}


def source_file(path):
    """Only application source is eligible; runtime and configuration stay in place."""
    if not path.parts:
        return False
    if path.as_posix() in SOURCE_FILES:
        return True
    if path.parts[0] not in SOURCE_DIRS:
        return False
    for part in path.parts:
        if part in RUNTIME_DIRS or part.startswith((".next", ".dev-logs", ".e2e")):
            return False
        if part.startswith(".env") and part != ".env.example":
            return False
    return not path.name.endswith((".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3"))


def download_source(destination):
    archive = destination / "source.zip"
    with urllib.request.urlopen(ARCHIVE, timeout=120) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    source = destination / "source"
    source.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        roots = {Path(info.filename).parts[0] for info in bundle.infolist()}
        if len(roots) != 1:
            raise ValueError("Expected one archive root")
        for info in bundle.infolist():
            path = Path(info.filename)
            if "\\" in info.orig_filename or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive path")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("Archive symlinks are not supported")
            relative = Path(*path.parts[1:])
            if not info.is_dir() and source_file(relative):
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as content, target.open("wb") as output:
                    shutil.copyfileobj(content, output)
    for name in (
        "scripts/install/install.py",
        "scripts/install/run.py",
        "backend/uv.lock",
        "frontend/package-lock.json",
        "backend/app/main.py",
    ):
        if not (source / name).is_file():
            raise ValueError(f"Downloaded source is missing {name}")
    return source


def processes():
    """Read process identity as well as argv, to avoid acting on a reused PID."""
    if os.name == "nt":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,"
            "CommandLine,CreationDate | ConvertTo-Json -Compress",
        ]
        rows = json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))
        return {
            int(row["ProcessId"]): (
                int(row["ParentProcessId"]),
                row["CommandLine"] or "",
                str(row["CreationDate"]),
            )
            for row in rows
        }
    output = subprocess.check_output(["ps", "-axo", "pid=,ppid=,lstart=,args="], text=True)
    result = {}
    for line in output.splitlines():
        parts = line.split(None, 7)
        if len(parts) == 8 and parts[0].isdigit() and parts[1].isdigit():
            result[int(parts[0])] = (int(parts[1]), parts[7], " ".join(parts[2:7]))
    return result


def owns_command(command):
    value = command.replace("\\", "/")
    root = ROOT.as_posix()
    if os.name == "nt":
        value, root = value.lower(), root.lower()
    # Match complete known script paths, never a port or a generic python/node process.
    paths = [f"{root}/scripts/install/run.py", f"{root}/frontend/node_modules/next/dist/bin/next"]
    if any(re.search(r"(?:^|[\s\"'])" + re.escape(path) + r"(?:$|[\s\"'])", value) for path in paths):
        return True
    python = f"{root}/backend/.venv/" + ("scripts/python.exe" if os.name == "nt" else "bin/python")
    return (value.startswith(python + " ") or value.startswith('"' + python + '" ')) and (
        " -m uvicorn app.main:app " in value
    )


def stop_installed():
    snapshot = processes()
    selected = {pid for pid, (_, command, _) in snapshot.items() if owns_command(command)}
    # Include only descendants of verified application processes (PTYs, workers, etc.).
    while True:
        children = {pid for pid, (parent, _, _) in snapshot.items() if parent in selected}
        if children <= selected:
            break
        selected.update(children)
    selected.discard(os.getpid())
    for pid in sorted(selected, reverse=True):
        if processes().get(pid) != snapshot[pid]:
            continue
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 15
    while selected and time.monotonic() < deadline:
        live = processes()
        selected = {pid for pid in selected if live.get(pid) == snapshot[pid]}
        if selected:
            time.sleep(0.3)
    if selected:
        raise RuntimeError("Application processes did not stop; no source was changed")


def data_paths():
    # Release native Python DLLs before uv sync on Windows; return no credentials.
    code = textwrap.dedent("""\
        import json, sys
        from pathlib import Path
        root = Path(sys.argv[1])
        sys.path.insert(0, str(root / "backend"))
        from dotenv import dotenv_values
        from sqlalchemy.engine import make_url
        from app.core.config import Settings
        class InstalledSettings(Settings):
            @classmethod
            def settings_customise_sources(cls, settings_cls, **kwargs):
                return (kwargs["init_settings"],)
        values = {k.lower(): v for k, v in dotenv_values(root / "backend/.env", interpolate=False).items()
                  if v is not None}
        settings = InstalledSettings(**values)
        url = make_url(settings.database_url)
        if url.get_backend_name() != "sqlite" or not url.database or settings.checkpoint_postgres_url:
            sys.exit("Automatic updates require SQLite. Back up PostgreSQL and update manually.")
        def absolute(path):
            path = Path(path)
            return str(path.resolve() if path.is_absolute() else (root / "backend" / path).resolve())
        paths = [absolute(url.database), absolute(settings.checkpoint_db), absolute(settings.data_dir)]
        print(json.dumps(paths))
    """)
    paths = json.loads(subprocess.check_output([sys.executable, "-c", code, str(ROOT)], text=True, cwd=ROOT))
    return [Path(path) for path in paths[:2]], Path(paths[2])


def backup_data(folder, databases, data_dir):
    folder.mkdir(parents=True, mode=0o700)
    manifest = {}
    for index, source in enumerate(databases):
        if source.is_file():
            target = folder / f"database-{index}.db"
            with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
                with sqlite3.connect(target) as copy:
                    original.backup(copy)
                    if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Database backup failed integrity check")
            manifest[target.name] = str(source)
    if data_dir.is_dir():
        shutil.copytree(data_dir, folder / "data", symlinks=True)
        manifest["data"] = str(data_dir)
    configuration = [Path("backend/config")]
    for directory in (ROOT, ROOT / "backend", ROOT / "frontend"):
        configuration.extend(
            path.relative_to(ROOT)
            for path in directory.glob(".env*")
            if path.name != ".env.example" and path.is_file()
        )
    for relative in configuration:
        source = ROOT / relative
        if source.is_dir():
            shutil.copytree(source, folder / "configuration" / relative, symlinks=True)
        elif source.is_file():
            target = folder / "configuration" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (folder / "restore-paths.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def recover_ports():
    """Older source installs need no root .env; recover only its two port settings."""
    if (ROOT / ".env").is_file():
        # preflight_ports reads/validates that existing file; never rewrite it.
        return 3060, 8060
    code = textwrap.dedent("""\
        import json, sys
        from pathlib import Path
        from dotenv import dotenv_values
        root = Path(sys.argv[1])
        allowed = {"FRONTEND_PORT", "BACKEND_PORT", "BACKEND_URL", "NEXT_PUBLIC_API_URL", "CORS_ORIGINS"}
        result = {}
        for name in ("backend/.env", "frontend/.env", "frontend/.env.production",
                     "frontend/.env.local", "frontend/.env.production.local"):
            path = root / name
            if path.is_file():
                result.update({k: v for k, v in dotenv_values(path, interpolate=False).items()
                               if k in allowed and v})
        print(json.dumps(result))
    """)
    values = json.loads(subprocess.check_output([sys.executable, "-c", code, str(ROOT)], text=True, cwd=ROOT))
    state_file = ROOT / ".tools/install-state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.is_file() else {}

    def local_ports(urls):
        ports = set()
        for value in urls:
            url = urlsplit(value.strip())
            if url.scheme in {"http", "https"} and url.hostname in {"localhost", "127.0.0.1", "::1"}:
                ports.add(url.port or (443 if url.scheme == "https" else 80))
        return ports

    def choose(name, candidates, default):
        explicit = state.get(name.lower()) or values.get(name.upper())
        if explicit:
            return int(explicit)
        if len(candidates) > 1:
            raise ValueError(f"Conflicting {name} settings. Set FRONTEND_PORT/BACKEND_PORT in root .env.")
        return next(iter(candidates), default)

    frontend = choose("FRONTEND_PORT", local_ports(values.get("CORS_ORIGINS", "").split(",")), 3060)
    backend = choose(
        "BACKEND_PORT",
        local_ports([values.get("BACKEND_URL", "") or values.get("NEXT_PUBLIC_API_URL", "")]),
        8060,
    )
    if frontend == backend or not all(1 <= port <= 65535 for port in (frontend, backend)):
        raise ValueError("Recovered ports are invalid; configure root .env explicitly")
    return frontend, backend


def write_missing_root_env(frontend, backend):
    path = ROOT / ".env"
    if path.exists():
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"FRONTEND_PORT={frontend}\nBACKEND_PORT={backend}\n")
    print(
        f"Created missing root .env: frontend {frontend}, backend {backend}. Backend secrets unchanged.",
        flush=True,
    )


def apply_source(source, backup, protected):
    files = [path for path in source.rglob("*") if path.is_file()]
    manifest = ROOT / ".tools/source-manifest.json"
    current = {file.relative_to(source).as_posix() for file in files}
    previous = set(json.loads(manifest.read_text(encoding="utf-8"))) if manifest.is_file() else set()
    obsolete = []
    for name in previous - current:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not source_file(relative):
            raise ValueError("Unsafe installed source manifest")
        obsolete.append(ROOT / relative)
    for target in [*(ROOT / file.relative_to(source) for file in files), *obsolete]:
        # Refuse links and configured data paths even if they overlap a source directory.
        if any(parent.is_symlink() for parent in [target, *target.parents]):
            raise ValueError(f"Refusing to overwrite a symlink: {target}")
        if any(target.resolve() == path or target.resolve().is_relative_to(path) for path in protected):
            raise ValueError(f"Configured data overlaps application source: {target}")
    for target in obsolete:
        if target.is_file():
            saved = backup / "source" / target.relative_to(ROOT)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            target.unlink()
    for file in files:
        relative = file.relative_to(source)
        target = ROOT / relative
        if target.exists():
            saved = backup / "source" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    if manifest.is_file():
        shutil.copy2(manifest, backup / "source-manifest.json")
    manifest.write_text(json.dumps(sorted(current), indent=2), encoding="utf-8")


def main():
    os.chdir(ROOT)
    # Old/unfinished installations may not have reached the final runtime.json step.
    (ROOT / ".tools").mkdir(exist_ok=True)
    lock = ROOT / ".tools/update.lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RuntimeError(
            f"Another update is active. If interrupted, check processes then remove {lock}"
        ) from error
    backup = None
    try:
        databases, data_dir = data_paths()
        if not databases[0].is_file():
            raise ValueError("Configured database is missing; refusing to create an empty replacement")
        if ROOT.is_relative_to(data_dir):
            raise ValueError("DATA_DIR must not contain the installation root (backup would recurse)")
        frontend, backend = recover_ports()
        with tempfile.TemporaryDirectory(prefix="1devteams-update-") as temp:
            print("Downloading latest 1devTeams source (main)...", flush=True)
            source = download_source(Path(temp))
            stop_installed()
            # Do not touch source if another application still owns either configured port.
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "installed_installer", ROOT / "scripts/install/install.py"
            )
            installer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installer)
            installer.preflight_ports(ROOT, frontend, backend)
            backup = ROOT / "backups" / ("update-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
            print(f"Saving recovery backup: {backup}", flush=True)
            backup_data(backup, databases, data_dir)
            apply_source(source, backup, [*databases, data_dir])
            write_missing_root_env(frontend, backend)
        env = os.environ.copy()
        env["PATH"] = str(ROOT / ".tools/uv") + os.pathsep + env.get("PATH", "")
        uv = shutil.which("uv", path=env["PATH"])
        if not uv:
            raise ValueError("uv is missing; repair the OS installation first")
        subprocess.run(
            [
                uv,
                "run",
                "--no-project",
                "--python",
                "3.12",
                str(ROOT / "scripts/install/install.py"),
                "--update",
                "--no-start",
                "--skip-providers",
                "--skip-browser",
            ],
            env=env,
            check=True,
            cwd=ROOT,
        )
    except BaseException:
        if backup:
            print(
                f"Update incomplete; configuration/data retained. Recovery backup: {backup}. "
                "Resolve the error and rerun the same install command.",
                file=sys.stderr,
            )
        raise
    finally:
        lock.rmdir()
    python = ROOT / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    print("Update complete. Starting server...", flush=True)
    subprocess.run([str(python), str(ROOT / "scripts/install/run.py")], check=True, cwd=ROOT)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Update failed: {error}", file=sys.stderr)
        sys.exit(1)
