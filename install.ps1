# One-line entrypoint: irm https://raw.githubusercontent.com/jokerhung/1devteams/main/install.ps1 | iex
# The scoped block also works through Invoke-Expression, where PSScriptRoot is unavailable.
& {
    $ErrorActionPreference = 'Stop'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $installTarget = if ($env:ONEDEVTEAMS_INSTALL_DIR) {
        [IO.Path]::GetFullPath($env:ONEDEVTEAMS_INSTALL_DIR)
    } else {
        Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) '1devTeams'
    }
    if (Test-Path -LiteralPath $installTarget) {
        foreach ($required in @('scripts/install/run.py', 'scripts/install/install.py')) {
            if (-not (Test-Path -LiteralPath (Join-Path $installTarget $required) -PathType Leaf)) {
                throw "Existing directory is not a complete installation: $installTarget (missing $required). Nothing was overwritten. Run scripts/install/windows.ps1 there to finish installing, or set ONEDEVTEAMS_INSTALL_DIR to a new directory."
            }
        }
        $backendEnv = Join-Path $installTarget 'backend/.env'
        $backendPython = Join-Path $installTarget 'backend/.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $backendEnv -PathType Leaf) -or
            -not (Test-Path -LiteralPath $backendPython -PathType Leaf)) {
            $osInstaller = Join-Path $installTarget 'scripts/install/windows.ps1'
            if (-not (Test-Path -LiteralPath $osInstaller -PathType Leaf)) { throw 'OS installer missing. Restore scripts/install/windows.ps1 to repair it.' }
            if (-not (Test-Path -LiteralPath $backendEnv -PathType Leaf)) {
                $oldDatabase = @(foreach ($directory in @($installTarget, (Join-Path $installTarget 'backend'))) {
                    Get-ChildItem -LiteralPath $directory -Force |
                        Where-Object { $_.Name -match '\.(db|sqlite).*' }
                })
                $dataDir = Join-Path $installTarget 'backend/data'
                $oldData = @(if (Test-Path -LiteralPath $dataDir) { Get-ChildItem -LiteralPath $dataDir -Force })
                if ($oldDatabase.Count -gt 0 -or $oldData.Count -gt 0) {
                    throw 'backend/.env is missing, but existing database/data was found. Restore the original backend/.env (especially APP_SECRET_KEY and JWT_SECRET) from backup, then rerun this command. No files were changed.'
                }
            }
            Write-Host "Resuming the incomplete installation at: $installTarget"
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $osInstaller -NoStart
            if ($LASTEXITCODE -ne 0) { throw 'Repair failed. Check the installer output above.' }
            if (-not (Test-Path -LiteralPath $backendEnv -PathType Leaf) -or
                -not (Test-Path -LiteralPath $backendPython -PathType Leaf)) {
                throw 'Repair did not create backend configuration/venv. Check the installer output above.'
            }
        }
        Write-Host "Updating the installed version at: $installTarget"
        Write-Host 'Configuration and user data will be preserved; a recovery backup is created before updating.'
        $startupHelper = @'
import sys
import time
import urllib.request
from pathlib import Path

launcher = Path(sys.argv[1]).resolve().with_name('update.py')
sys.argv = [str(launcher)]
helper_url = f'https://raw.githubusercontent.com/jokerhung/1devteams/main/scripts/install/update.py?t={time.time_ns()}'
try:
    with urllib.request.urlopen(helper_url, timeout=20) as response:
        source = response.read().decode('utf-8')
except (OSError, UnicodeError) as error:
    sys.exit(f'Could not load the updater ({error}). No files were changed; the running server was left alone.')
else:
    # Preserve the installed project root without writing over its launcher.
    exec(compile(source, helper_url, 'exec'), {'__name__': '__main__', '__file__': str(launcher)})
'@
        & (Join-Path $installTarget 'backend/.venv/Scripts/python.exe') -c $startupHelper (Join-Path $installTarget 'scripts/install/run.py')
        if ($LASTEXITCODE -ne 0) { throw 'Update/start failed. Check the error and recovery backup path above.' }
        return
    }
    $downloadRoot = Join-Path ([IO.Path]::GetTempPath()) ('1devteams-install-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    try {
        $archive = Join-Path $downloadRoot 'source.zip'
        Write-Host 'Downloading 1devTeams source from github.com/jokerhung/1devteams (main)...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/jokerhung/1devteams/archive/refs/heads/main.zip' -OutFile $archive
        $extracted = Join-Path $downloadRoot 'source'
        Expand-Archive -LiteralPath $archive -DestinationPath $extracted
        # Discover the archive root instead of depending on the repository name.
        $sourceDirectories = @(Get-ChildItem -LiteralPath $extracted -Directory)
        if ($sourceDirectories.Count -ne 1) { throw 'Expected exactly one source directory in the downloaded archive.' }
        $source = $sourceDirectories[0].FullName
        foreach ($required in @('scripts/install/windows.ps1', 'backend/uv.lock', 'frontend/package-lock.json')) {
            if (-not (Test-Path -LiteralPath (Join-Path $source $required) -PathType Leaf)) {
                throw "Downloaded archive is missing $required. Publish the complete installer to main first."
            }
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $installTarget -Parent) | Out-Null
        # No -Force: never replace an existing installation or its secrets.
        if (Test-Path -LiteralPath $installTarget) { throw 'Destination was created during download; stopping.' }
        Move-Item -LiteralPath $source -Destination $installTarget
    } finally {
        # Only remove this invocation's GUID-named temporary download directory.
        $resolvedTemp = [IO.Path]::GetFullPath($downloadRoot)
        $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if ($resolvedTemp.StartsWith($tempParent, [StringComparison]::OrdinalIgnoreCase) -and
            (Split-Path $resolvedTemp -Leaf) -match '^1devteams-install-[a-f0-9]{32}$') {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
    Write-Host "Source installed at: $installTarget"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $installTarget 'scripts/install/windows.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Installation failed. Source was kept at $installTarget; fix the error and rerun scripts/install/windows.ps1 there." }
}
