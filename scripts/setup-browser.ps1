param()
$ErrorActionPreference = 'Stop'
$backendRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'backend'
& uv sync --project $backendRoot --python 3.12 --frozen
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency setup failed.' }
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
& $pythonPath -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium setup failed.' }
Write-Host 'Browser Worker is ready. Enable Browser Worker in the agent settings.'
