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
