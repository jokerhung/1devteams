"""Updater checks use temporary installations and never touch running services."""

import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "installer_update", Path(__file__).resolve().parents[1] / "update.py"
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def archive(monkeypatch, extra=None):
    buffer = io.BytesIO()
    files = {
        name: "new source"
        for name in (
            "scripts/install/install.py",
            "scripts/install/run.py",
            "backend/uv.lock",
            "frontend/package-lock.json",
            "backend/app/main.py",
        )
    }
    files.update(extra or {})
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, value in files.items():
            info = zipfile.ZipInfo("placeholder")
            info.filename = "renamed-main/" + name
            bundle.writestr(info, value)
    content = buffer.getvalue()
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(content))


def test_update_replaces_source_preserves_config_data_and_backs_up(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    (root / ".tools").mkdir()
    monkeypatch.setattr(updater, "ROOT", root)
    originals = {
        ".env": "CUSTOM_PORTS",
        "backend/.env": "CUSTOM_SECRETS",
        "frontend/.env.local": "CUSTOM_FRONTEND",
        "backend/config/models_catalog.yaml": "CUSTOM_MODEL",
        "backend/data/aiteams.db": "USER_DATA",
        "workspaces/customer/file.py": "USER_CODE",
        "backend/.venv/keep": "VENV",
        "frontend/node_modules/keep": "DEPS",
    }
    for name, content in {**originals, "backend/app/main.py": "old source"}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    archive(monkeypatch, {name: "SHOULD_NOT_OVERWRITE" for name in originals})
    stage = tmp_path / "stage"
    stage.mkdir()
    source = updater.download_source(stage)
    backup = root / "backups/recovery"
    backup.mkdir(parents=True)
    updater.apply_source(source, backup, [root / "backend/data"])
    assert (root / "backend/app/main.py").read_text() == "new source"
    assert (backup / "source/backend/app/main.py").read_text() == "old source"
    for name, content in originals.items():
        assert (root / name).read_text() == content
    # A later release removes a known source file, while custom files remain.
    custom = root / "backend/app/custom.py"
    custom.write_text("local addition")
    (source / "backend/app/main.py").unlink()
    updater.apply_source(source, backup, [root / "backend/data"])
    assert not (root / "backend/app/main.py").exists()
    assert custom.read_text() == "local addition"


def test_sqlite_backup_includes_wal_and_keeps_database_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    monkeypatch.setattr(updater, "ROOT", root)
    db = root / "custom.db"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE customer (name TEXT)")
        connection.execute("INSERT INTO customer VALUES ('retained')")
        connection.commit()
        backup = root / "backups/recovery"
        updater.backup_data(backup, [db], root / "absent-data")
        assert connection.execute("SELECT name FROM customer").fetchone() == ("retained",)
        with sqlite3.connect(backup / "database-0.db") as copy:
            assert copy.execute("SELECT name FROM customer").fetchone() == ("retained",)
        assert json.loads((backup / "restore-paths.json").read_text())["database-0.db"] == str(db)


def test_settings_resolve_external_data_and_ignore_ambient_env(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    config_dir = root / "backend/app/core"
    config_dir.mkdir(parents=True)
    original = Path(__file__).resolve().parents[3] / "backend/app/core/config.py"
    (config_dir / "config.py").write_bytes(original.read_bytes())
    (config_dir / "__init__.py").touch()
    (config_dir.parent / "__init__.py").touch()
    external = tmp_path / "external"
    (root / "backend/.env").write_text(
        "JWT_SECRET=test-only\nDATABASE_URL=sqlite+aiosqlite:///"
        + (external / "customer.db").as_posix()
        + "\nCHECKPOINT_DB=./local-checkpoint.db\nDATA_DIR="
        + external.as_posix()
        + "\n"
    )
    monkeypatch.setattr(updater, "ROOT", root)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unrelated/database")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "unrelated"))
    databases, data_dir = updater.data_paths()
    assert databases == [external / "customer.db", root / "backend/local-checkpoint.db"]
    assert data_dir == external


@pytest.mark.parametrize("bad", ["../escape.py", "backend/../../escape.py", "backend\\evil.py"])
def test_rejects_unsafe_archive(tmp_path, monkeypatch, bad):
    archive(monkeypatch, {bad: "bad"})
    with pytest.raises(ValueError, match="Unsafe"):
        updater.download_source(tmp_path)


def test_refuses_configured_data_inside_source_before_any_write(tmp_path, monkeypatch):
    root, source, backup = (tmp_path / name for name in ("installed", "source", "backup"))
    root.mkdir()
    (root / ".tools").mkdir()
    monkeypatch.setattr(updater, "ROOT", root)
    (source / "backend/app").mkdir(parents=True)
    (source / "backend/app/customer.py").write_text("new source")
    with pytest.raises(ValueError, match="Configured data overlaps"):
        updater.apply_source(source, backup, [root / "backend/app"])
    assert not (root / "backend").exists()


def test_process_ownership_ignores_other_installations_and_tailscale(tmp_path, monkeypatch):
    root = tmp_path / "installation with spaces"
    monkeypatch.setattr(updater, "ROOT", root)
    assert updater.owns_command(f'python "{root}/scripts/install/run.py"')
    assert updater.owns_command(f"node {root}/frontend/node_modules/next/dist/bin/next start --port 3060")
    python = root / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert updater.owns_command(f'"{python}" -m uvicorn app.main:app --port 8060')
    assert not updater.owns_command("tailscaled --port 3060")
    assert not updater.owns_command("python -m uvicorn other:app --port 8060")
    assert not updater.owns_command(f'python "{root}-other/scripts/install/run.py"')


def test_stop_only_verified_processes_and_descendants(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    snapshot = {
        100: (1, f'python "{tmp_path}/scripts/install/run.py"', "original"),
        101: (100, "child worker", "original"),
        102: (1, "tailscaled", "original"),
    }
    live = dict(snapshot)
    monkeypatch.setattr(updater, "processes", lambda: live.copy())
    calls = []

    def killed(pid):
        calls.append(pid)
        live.pop(pid, None)

    if os.name == "nt":
        monkeypatch.setattr(updater.subprocess, "run", lambda args, **kw: killed(int(args[2])))
    else:
        monkeypatch.setattr(updater.os, "kill", lambda pid, sig: killed(pid))
    updater.stop_installed()
    assert set(calls) == {100, 101}
    assert 102 in live


@pytest.mark.parametrize("failure", ["download", "build", None])
def test_update_sequence_and_failure_preserves_data(tmp_path, monkeypatch, failure):
    root = tmp_path / "installed"
    (root / ".tools").mkdir(parents=True)
    (root / "scripts/install").mkdir(parents=True)
    (root / "scripts/install/install.py").write_text("def preflight_ports(*args): pass\n")
    db = root / "database.db"
    db.write_text("user data")
    monkeypatch.setattr(updater, "ROOT", root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(updater, "data_paths", lambda: ([db], root / "data"))
    steps = []

    def download(path):
        steps.append("download")
        if failure == "download":
            raise OSError("offline")
        return path

    monkeypatch.setattr(updater, "download_source", download)
    monkeypatch.setattr(updater, "stop_installed", lambda: steps.append("stop"))
    monkeypatch.setattr(updater, "backup_data", lambda *a: steps.append("backup"))
    monkeypatch.setattr(updater, "apply_source", lambda *a: steps.append("source"))
    monkeypatch.setattr(updater.shutil, "which", lambda *a, **kw: "uv")

    def run(args, **kwargs):
        if "--update" in args:
            steps.append("build")
            assert "--no-start" in args
            if failure == "build":
                raise subprocess.CalledProcessError(1, args)
        else:
            steps.append("start")

    monkeypatch.setattr(updater.subprocess, "run", run)
    if failure:
        with pytest.raises((OSError, subprocess.SubprocessError)):
            updater.main()
    else:
        updater.main()
    assert db.read_text() == "user data"
    assert not (root / ".tools/update.lock").exists()
    expected = ["download"] if failure == "download" else ["download", "stop", "backup", "source", "build"]
    assert steps == expected + (["start"] if not failure else [])
