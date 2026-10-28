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
        foreach ($required in @('scripts/install/run.py', '.tools/runtime.json', 'frontend/.next-build/BUILD_ID', '.env', 'backend/.env', 'backend/.venv/Scripts/python.exe')) {
            if (-not (Test-Path -LiteralPath (Join-Path $installTarget $required) -PathType Leaf)) {
                throw "Existing directory is not a complete installation: $installTarget (missing $required). Nothing was overwritten. Run scripts/install/windows.ps1 there to finish installing, or set ONEDEVTEAMS_INSTALL_DIR to a new directory."
            }
        }
        Write-Host "Starting the installed version at: $installTarget"
        Write-Host 'App source and dependencies stay unchanged. Loading the latest startup helper in memory.'
        $startupHelper = @'
import runpy
import sys
import urllib.request
from pathlib import Path

launcher = Path(sys.argv[1]).resolve()
sys.argv = [str(launcher)]
helper_url = 'https://raw.githubusercontent.com/jokerhung/1devteams/main/scripts/install/run.py'
try:
    with urllib.request.urlopen(helper_url, timeout=20) as response:
        source = response.read().decode('utf-8')
except (OSError, UnicodeError) as error:
    print(f'Could not load the latest startup helper ({error}). Using the installed launcher; older versions may not print LAN URLs.', flush=True)
    runpy.run_path(str(launcher), run_name='__main__')
else:
    # Preserve the installed project root without writing over its launcher.
    exec(compile(source, helper_url, 'exec'), {'__name__': '__main__', '__file__': str(launcher)})
'@
        & (Join-Path $installTarget 'backend/.venv/Scripts/python.exe') -c $startupHelper (Join-Path $installTarget 'scripts/install/run.py')
        if ($LASTEXITCODE -ne 0) { throw 'Could not start the installed app. Check the error above; no files were changed.' }
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
