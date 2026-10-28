"""Exercise the piped Windows entrypoint offline, with no real installs."""

import os
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.skipif(os.name != "nt", reason="PowerShell bootstrap requires Windows")


def run_bootstrap(tmp_path, target, archive_root="1devteams-main"):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("scripts/install/windows.ps1", "backend/uv.lock", "frontend/package-lock.json"):
            bundle.writestr(f"{archive_root}/{name}", "fixture")
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
                Write-Output 'SOURCE_DOWNLOAD'
                Copy-Item -LiteralPath $env:BOOTSTRAP_TEST_ARCHIVE -Destination $OutFile
            }
            function powershell.exe {
                Write-Output ('INSTALLER_CALLED ' + ($args -join ' '))
                $global:LASTEXITCODE = 0
            }
            $fakePython = Join-Path $env:ONEDEVTEAMS_INSTALL_DIR 'backend/.venv/Scripts/python.exe'
            Set-Item -LiteralPath ('Function:' + $fakePython) -Value {
                Write-Output ('EXISTING_RUNNER_CALLED ' + ($args -join ' '))
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


@pytest.mark.parametrize("archive_root", ["aiTeams-main", "1devteams-main", "renamed-repository-main"])
def test_windows_piped_bootstrap_download_extract_and_dispatch(tmp_path, archive_root):
    target = tmp_path / "new installation with spaces"
    result = run_bootstrap(tmp_path, target, archive_root)
    assert result.returncode == 0, result.stderr
    assert (target / "backend/uv.lock").read_text() == "fixture"
    assert "INSTALLER_CALLED" in result.stdout
    assert str(target / "scripts/install/windows.ps1") in result.stdout.replace("/", "\\")


def test_windows_bootstrap_refuses_existing_directory(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    result = run_bootstrap(tmp_path, target)
    assert result.returncode != 0
    assert "not a complete installation" in result.stderr
    assert "SOURCE_DOWNLOAD" not in result.stdout
    assert not list(target.iterdir())


def test_windows_bootstrap_starts_installed_version_without_download(tmp_path):
    target = tmp_path / "existing installation"
    files = [
        "scripts/install/run.py",
        ".tools/runtime.json",
        "frontend/.next-build/BUILD_ID",
        ".env",
        "backend/.env",
        "backend/.venv/Scripts/python.exe",
    ]
    for name in files:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unchanged fixture")
    result = run_bootstrap(tmp_path, target)
    assert result.returncode == 0, result.stderr
    assert "EXISTING_RUNNER_CALLED" in result.stdout
    assert "scripts/install/run.py" in result.stdout.replace("\\", "/")
    assert "SOURCE_DOWNLOAD" not in result.stdout
    assert "INSTALLER_CALLED" not in result.stdout
    assert all((target / name).read_text() == "unchanged fixture" for name in files)
