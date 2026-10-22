param([switch]$SmokeTest)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$nextPath = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run: uv sync --project backend --python 3.12' }
if (-not (Test-Path -LiteralPath $nextPath)) { throw 'Run: npm --prefix frontend ci' }
if (-not (Test-Path -LiteralPath (Join-Path $backendRoot '.env')) -and -not $env:JWT_SECRET) {
    throw 'Create backend/.env from backend/.env.example and set JWT_SECRET.'
}
foreach ($port in @(8000, 3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop that service or run the apps separately."
    }
}
$processes = @()
try {
    $processes += Start-Process -FilePath $pythonPath -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru
    $processes += Start-Process -FilePath (Get-Command node).Source -ArgumentList "`"$nextPath`"", 'dev', '--hostname', 'localhost', '--port', '3000' -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru
    Write-Host 'Backend: http://localhost:8000 | Frontend: http://localhost:3000'
    if ($SmokeTest) {
        $deadline = (Get-Date).AddSeconds(90)
        do {
            foreach ($process in $processes) { if ($process.HasExited) { throw 'A dev service exited before readiness.' } }
            try {
                $health = Invoke-RestMethod 'http://localhost:8000/api/health' -TimeoutSec 3
                $page = Invoke-WebRequest 'http://localhost:3000' -UseBasicParsing -TimeoutSec 5
                if ($health.status -eq 'ok' -and $page.StatusCode -eq 200) {
                    Write-Host "Smoke test passed. Claude=$($health.acp.claude); Codex=$($health.acp.codex)"
                    return
                }
            } catch { Start-Sleep -Milliseconds 500 }
        } while ((Get-Date) -lt $deadline)
        throw 'Dev services did not become ready within 90 seconds.'
    }
    Write-Host 'Press Ctrl+C to stop both services.'
    while ($true) {
        foreach ($process in $processes) { if ($process.HasExited) { throw "Dev service exited ($($process.ExitCode))." } }
        Start-Sleep -Milliseconds 500
    }
} finally {
    foreach ($process in $processes) {
        if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F | Out-Null }
    }
}
