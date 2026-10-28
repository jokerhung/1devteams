"""Exercise the piped Windows entrypoint offline, with no real installs."""

import os
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="PowerShell bootstrap requires Windows")


def run_bootstrap(tmp_path, target):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("scripts/install/windows.ps1", "backend/uv.lock", "frontend/package-lock.json"):
            bundle.writestr(f"aiTeams-main/{name}", "fixture")
    env = {
        **os.environ,
        "ONEDEVTEAMS_INSTALL_DIR": str(target),
        "BOOTSTRAP_TEST_ARCHIVE": str(archive),
        "BOOTSTRAP_TEST_SCRIPT": str(ROOT / "install.ps1"),
    }
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            """
            $ErrorActionPreference = 'Stop'
            function Invoke-WebRequest {
                param([switch]$UseBasicParsing, $Uri, $OutFile)
                Copy-Item -LiteralPath $env:BOOTSTRAP_TEST_ARCHIVE -Destination $OutFile
            }
            function powershell.exe {
                Write-Output ('INSTALLER_CALLED ' + ($args -join ' '))
                $global:LASTEXITCODE = 0
            }
            Get-Content -LiteralPath $env:BOOTSTRAP_TEST_SCRIPT -Raw | Invoke-Expression
            """,
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_windows_piped_bootstrap_download_extract_and_dispatch(tmp_path):
    target = tmp_path / "new installation with spaces"
    result = run_bootstrap(tmp_path, target)
    assert result.returncode == 0, result.stderr
    assert (target / "backend/uv.lock").read_text() == "fixture"
    assert "INSTALLER_CALLED" in result.stdout
    assert str(target / "scripts/install/windows.ps1") in result.stdout.replace("/", "\\")


def test_windows_bootstrap_refuses_existing_directory(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    result = run_bootstrap(tmp_path, target)
    assert result.returncode != 0
    assert "Destination already exists" in result.stderr
    assert not list(target.iterdir())
