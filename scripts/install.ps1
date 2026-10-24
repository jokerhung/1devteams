[CmdletBinding()]
param([switch]$SkipGlobalAdapters)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
foreach ($tool in @('python', 'node', 'git', 'uv', 'npm')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install prerequisite: $tool" }
}
& python -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ required' }
$nodeVersion = & node --version
if ([int]($nodeVersion.TrimStart('v').Split('.')[0]) -lt 20) { throw 'Node 20+ required' }
Push-Location $repoRoot
try {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Adapter installation failed' }
    if (-not $SkipGlobalAdapters) {
        $packages = (Get-Content package.json -Raw | ConvertFrom-Json).devDependencies
        foreach ($name in @('@agentclientprotocol/claude-agent-acp', '@agentclientprotocol/codex-acp')) {
            & npm install --global "$name@$($packages.$name)"
            if ($LASTEXITCODE -ne 0) { throw "Global adapter installation failed: $name" }
        }
    }
    & uv sync --project backend --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed' }
    if (-not (Test-Path backend/.env)) { throw 'Create backend/.env from backend/.env.example, configure secrets, then rerun.' }
    Push-Location backend
    try {
        & ./.venv/Scripts/python.exe -c 'from app.core.config import Settings; from app.db.session import migrate; migrate(Settings().database_url)'
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    } finally { Pop-Location }
    & npm --prefix frontend ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed' }
    & npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
Write-Host 'Installation complete. Run scripts/start.ps1.'
