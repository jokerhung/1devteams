[CmdletBinding()]
param([switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'
$pythonPath = Join-Path $backendRoot '.venv/Scripts/python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules/next/dist/bin/next'
$configJson = & $pythonPath -c @'
import json, os, sys
from pathlib import Path
from dotenv import dotenv_values
values = dotenv_values(Path(sys.argv[1]) / '.env') | os.environ
ports = {key: int(values.get(key, default)) for key, default in [('FRONTEND_PORT',3060),('BACKEND_PORT',8060)]}
assert all(1 <= port <= 65535 for port in ports.values())
assert ports['FRONTEND_PORT'] != ports['BACKEND_PORT']
print(json.dumps(ports))
'@ $repoRoot
if ($LASTEXITCODE -ne 0) { throw 'Invalid configuration or missing virtual environment. Run install.ps1.' }
$config = $configJson | ConvertFrom-Json
$logRoot = Join-Path $repoRoot '.dev-logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$processes = @()
$oldApiUrl = $env:NEXT_PUBLIC_API_URL
$oldBackendUrl = $env:BACKEND_URL
$oldCors = $env:CORS_ORIGINS
try {
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$($config.BACKEND_PORT)"
    $env:BACKEND_URL = $env:NEXT_PUBLIC_API_URL
    $env:CORS_ORIGINS = "http://localhost:$($config.FRONTEND_PORT),http://127.0.0.1:$($config.FRONTEND_PORT)"
    $processes += Start-Process $pythonPath -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', $config.BACKEND_PORT -WorkingDirectory $backendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'production-backend.log') -RedirectStandardError (Join-Path $logRoot 'production-backend.error.log') -PassThru
    # Listen on LAN IPv4 as well as loopback. Tailscale Serve targets 127.0.0.1.
    $processes += Start-Process (Get-Command node).Source -ArgumentList "`"$nextPath`"", 'start', '--hostname', '0.0.0.0', '--port', $config.FRONTEND_PORT -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'production-frontend.log') -RedirectStandardError (Join-Path $logRoot 'production-frontend.error.log') -PassThru
    Write-Host "Frontend: http://localhost:$($config.FRONTEND_PORT) | Backend: http://127.0.0.1:$($config.BACKEND_PORT)"
    $deadline = (Get-Date).AddSeconds(90)
    while ($true) {
        foreach ($process in $processes) {
            if ($process.HasExited) { throw 'A service exited. See .dev-logs/production-*.' }
        }
        if ($SmokeTest) {
            try {
                $health = Invoke-RestMethod "$env:BACKEND_URL/api/health" -TimeoutSec 3
                $page = Invoke-WebRequest "http://127.0.0.1:$($config.FRONTEND_PORT)/login" -UseBasicParsing -TimeoutSec 3
                $proxy = Invoke-RestMethod "http://127.0.0.1:$($config.FRONTEND_PORT)/api/backend/health" -TimeoutSec 3
                if ($health.status -eq 'ok' -and $page.StatusCode -eq 200 -and $proxy.status -eq 'ok') {
                    Write-Host 'Production startup smoke test passed.'
                    return
                }
            } catch { }
            if ((Get-Date) -ge $deadline) { throw 'Startup readiness timeout' }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
    $env:NEXT_PUBLIC_API_URL = $oldApiUrl
    $env:BACKEND_URL = $oldBackendUrl
    $env:CORS_ORIGINS = $oldCors
}
