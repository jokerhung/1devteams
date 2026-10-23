[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
if ($Setup) {
    & uv sync --project $backendRoot --python 3.12 --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency setup failed.' }
    & npm --prefix $frontendRoot ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency setup failed.' }
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run: uv sync --project backend --python 3.12' }
if (-not (Test-Path -LiteralPath $nextPath)) { throw 'Run: npm --prefix frontend ci' }
$nodePath = (Get-Command node -ErrorAction Stop).Source
& $pythonPath -c 'import sys; assert sys.prefix != sys.base_prefix, "Backend Python must use a virtual environment"; import uvicorn'
if ($LASTEXITCODE -ne 0) { throw 'Backend virtual environment is invalid. Run this script with -Setup.' }
$configJson = & $pythonPath -c @'
import json, os, sys
from pathlib import Path
from dotenv import dotenv_values
root = Path(sys.argv[1])
values = dotenv_values(root / '.env') | os.environ
ports = {}
for name, default in [('FRONTEND_PORT', '3060'), ('BACKEND_PORT', '8060')]:
    value = int(values.get(name, default))
    if not 1 <= value <= 65535:
        raise ValueError(f'{name} must be between 1 and 65535')
    ports[name] = value
if ports['FRONTEND_PORT'] == ports['BACKEND_PORT']:
    raise ValueError('Frontend and backend ports must differ')
backend = dotenv_values(root / 'backend' / '.env')
ports['cors'] = os.environ.get('CORS_ORIGINS', backend.get('CORS_ORIGINS') or '')
print(json.dumps(ports))
'@ $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'Invalid port configuration in .env.' }
$config = $configJson | ConvertFrom-Json
$backendPort = [string]$config.BACKEND_PORT
$frontendPort = [string]$config.FRONTEND_PORT
$backendUrl = "http://localhost:$backendPort"
$frontendUrl = "http://localhost:$frontendPort"
if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env')) -and -not $env:JWT_SECRET) {
    throw 'Create backend/.env from backend/.env.example and set JWT_SECRET.'
}
foreach ($port in @($backendPort, $frontendPort)) {
    $ownerIds = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($ownerId in $ownerIds) {
        if ($ownerId -le 4 -or $ownerId -eq $PID) {
            throw "Cannot stop protected process $ownerId using port $port."
        }
        Write-Host "Stopping process $ownerId using port $port..."
        # Stop the process tree so Next.js/uvicorn children do not retain the port.
        & taskkill.exe /PID $ownerId /T /F | Out-Host
        if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $ownerId -ErrorAction SilentlyContinue)) {
            throw "Could not stop process $ownerId using port $port. Check process permissions."
        }
    }
    $portDeadline = (Get-Date).AddSeconds(10)
    while (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        if ((Get-Date) -ge $portDeadline) {
            throw "Port $port is still in use after stopping its previous process."
        }
        Start-Sleep -Milliseconds 200
    }
}
$processes = @()
$logRoot = Join-Path $repoRoot '.dev-logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$previousApiUrl = $env:NEXT_PUBLIC_API_URL
$previousCors = $env:CORS_ORIGINS
try {
    $env:NEXT_PUBLIC_API_URL = $backendUrl
    $env:CORS_ORIGINS = (@($config.cors -split ',') + @($frontendUrl) | Where-Object { $_ } | Select-Object -Unique) -join ','
    $processes += Start-Process -FilePath $pythonPath -ArgumentList '-u', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', $backendPort -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'backend.stdout.log') -RedirectStandardError (Join-Path $logRoot 'backend.stderr.log') -PassThru
    $processes += Start-Process -FilePath $nodePath -ArgumentList "`"$nextPath`"", 'dev', '--turbopack', '--hostname', 'localhost', '--port', $frontendPort -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'frontend.stdout.log') -RedirectStandardError (Join-Path $logRoot 'frontend.stderr.log') -PassThru
    Write-Host "Backend: $backendUrl | Frontend: $frontendUrl"
    Write-Host "Backend Python: $pythonPath"
    Write-Host "Logs: $logRoot"
    if ($SmokeTest) {
        $deadline = (Get-Date).AddSeconds(90)
        do {
            foreach ($process in $processes) { if ($process.HasExited) { throw "A dev service exited before readiness. See $logRoot" } }
            try {
                $healthResponse = Invoke-WebRequest "$backendUrl/api/health" -Headers @{ Origin = $frontendUrl } -UseBasicParsing -TimeoutSec 3
                $health = $healthResponse.Content | ConvertFrom-Json
                $page = Invoke-WebRequest $frontendUrl -UseBasicParsing -TimeoutSec 5
                if ($health.status -eq 'ok' -and $page.StatusCode -eq 200 -and $healthResponse.Headers['Access-Control-Allow-Origin'] -eq $frontendUrl) {
                    Write-Host "Smoke test passed. Claude=$($health.acp.claude); Codex=$($health.acp.codex)"
                    return
                }
            } catch { Start-Sleep -Milliseconds 500 }
        } while ((Get-Date) -lt $deadline)
        throw 'Dev services did not become ready within 90 seconds.'
    }
    Write-Host 'Press Ctrl+C to stop both services.'
    while ($true) {
        foreach ($process in $processes) { if ($process.HasExited) { throw "Dev service exited ($($process.ExitCode)). See $logRoot" } }
        Start-Sleep -Milliseconds 500
    }
} finally {
    $env:NEXT_PUBLIC_API_URL = $previousApiUrl
    $env:CORS_ORIGINS = $previousCors
    foreach ($process in $processes) {
        if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
}
