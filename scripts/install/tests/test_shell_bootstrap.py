"""Run the real shell download/extract phase offline, stopping before OS installation."""

import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BASH = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
pytestmark = pytest.mark.skipif(
    not BASH or not Path(BASH).is_file() or (os.name != "nt" and os.geteuid() == 0),
    reason="Requires Bash as a non-root user",
)


def shell_path(path):
    value = path.as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


@pytest.mark.parametrize("archive_root", ["aiTeams-main", "1devteams-main", "renamed-repository-main"])
@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_shell_extract_does_not_depend_on_repository_name(tmp_path, archive_root, system):
    archive = tmp_path / "fixture.tar.gz"
    installer = "linux.sh" if system == "Linux" else "macos.sh"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in (f"scripts/install/{installer}", "backend/uv.lock", "frontend/package-lock.json"):
            info = tarfile.TarInfo(f"{archive_root}/{name}")
            info.size = len(b"fixture")
            bundle.addfile(info, io.BytesIO(b"fixture"))
    target = tmp_path / "installation with spaces"
    # Execute exactly the source acquisition phase; never invoke apt/uv/npm.
    source = (ROOT / "install.sh").read_text(encoding="utf-8").split("# Restore interactive stdin")[0]
    result = subprocess.run(
        [
            BASH,
            "-c",
            'uname() { printf "%s\\n" "$BOOTSTRAP_TEST_SYSTEM"; }\n'
            'curl() { cp "$BOOTSTRAP_TEST_ARCHIVE" "${@: -1}"; }\n' + source,
        ],
        env={
            **os.environ,
            "ONEDEVTEAMS_INSTALL_DIR": shell_path(target),
            "BOOTSTRAP_TEST_ARCHIVE": shell_path(archive),
            "BOOTSTRAP_TEST_SYSTEM": system,
        },
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (target / f"scripts/install/{installer}").read_text() == "fixture"
    assert (target / "backend/uv.lock").read_text() == "fixture"
    assert "Source installed at:" in result.stdout


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
@pytest.mark.parametrize("state", ["installed", "partial", "missing_venv", "startup_failure"])
def test_shell_rerun_starts_existing_app_without_download(tmp_path, system, state):
    target = tmp_path / "existing installation"
    target.mkdir()
    if state != "partial":
        for name in (
            "scripts/install/run.py",
            ".tools/runtime.json",
            "frontend/.next-build/BUILD_ID",
            ".env",
            "backend/.env",
        ):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unchanged fixture")
        if state != "missing_venv":
            python = target / "backend/.venv/bin/python"
            python.parent.mkdir(parents=True)
            python.write_text(
                '#!/bin/sh\nprintf "RUNNER_CWD %s\\n" "$PWD"\nprintf "EXISTING_RUNNER_CALLED %s\\n" "$@"\n'
                + ("exit 7\n" if state == "startup_failure" else "exit 0\n"),
                encoding="utf-8",
            )
            python.chmod(0o700)
    before = {file.relative_to(target): file.read_bytes() for file in target.rglob("*") if file.is_file()}
    result = subprocess.run(
        [
            BASH,
            "-c",
            'uname() { printf "%s\\n" "$BOOTSTRAP_TEST_SYSTEM"; }\n'
            'curl() { printf "UNEXPECTED_DOWNLOAD\\n"; return 99; }\n'
            + (ROOT / "install.sh").read_text(encoding="utf-8"),
        ],
        env={**os.environ, "ONEDEVTEAMS_INSTALL_DIR": shell_path(target), "BOOTSTRAP_TEST_SYSTEM": system},
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert "UNEXPECTED_DOWNLOAD" not in result.stdout
    assert "Downloading" not in result.stdout
    if state in {"installed", "startup_failure"}:
        assert result.returncode == (0 if state == "installed" else 7), result.stderr
        assert "EXISTING_RUNNER_CALLED" in result.stdout
        assert "scripts/install/run.py" in result.stdout
        assert "RUNNER_CWD " + shell_path(target) in result.stdout
    else:
        assert result.returncode != 0
        assert "finish installing" in result.stderr or "repair it" in result.stderr
    assert {
        file.relative_to(target): file.read_bytes() for file in target.rglob("*") if file.is_file()
    } == before
