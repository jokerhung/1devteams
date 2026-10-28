# Windows 10/11, PowerShell 5.1+. Run from an extracted source archive or checkout.
[CmdletBinding()]
param(
    [string]$AdminEmail = 'owner@example.com',
    [string]$Workspace = '',
    [int]$FrontendPort = 3060,
    [int]$BackendPort = 8060,
    [string]$PublicUrl = '',
    [switch]$TrustNativeAgents,
    [switch]$EnableRemoteTerminal,
    [switch]$SkipProviders,
    [switch]$SkipBrowser,
    [switch]$NoStart,
    [switch]$Help
)
$ErrorActionPreference = 'Stop'
if ($Help) {
    Write-Host 'Usage: powershell -ExecutionPolicy Bypass -File scripts/install/windows.ps1 [-AdminEmail email] [-Workspace path] [-PublicUrl http://host:3060] [-TrustNativeAgents] [-EnableRemoteTerminal] [-SkipProviders] [-SkipBrowser] [-NoStart]'
    exit 0
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'backend/uv.lock'))) {
    throw 'Download and extract the complete repository before running this installer.'
}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host 'Installing Windows Package Manager (Microsoft WinGet)...'
        Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
        Install-Module Microsoft.WinGet.Client -Repository PSGallery -Scope CurrentUser -Force
        Import-Module Microsoft.WinGet.Client
        Repair-WinGetPackageManager
        $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH', 'User') + ';' + $env:PATH
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet is unavailable. Reopen PowerShell and rerun.' }
    }
    & winget install --id Git.Git --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Git installation failed.' }
    $env:PATH = [Environment]::GetEnvironmentVariable('PATH', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('PATH', 'User') + ';' + $env:PATH
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is unavailable. Reopen PowerShell and rerun.' }
$uvDir = Join-Path $repoRoot '.tools/uv'
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv -and -not (Test-Path -LiteralPath (Join-Path $uvDir 'uv.exe'))) {
    Write-Host 'Installing uv from astral.sh...'
    $oldInstallDir = $env:UV_INSTALL_DIR
    $oldNoPath = $env:UV_NO_MODIFY_PATH
    try {
        $env:UV_INSTALL_DIR = $uvDir
        $env:UV_NO_MODIFY_PATH = '1'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } finally {
        $env:UV_INSTALL_DIR = $oldInstallDir
        $env:UV_NO_MODIFY_PATH = $oldNoPath
    }
}
$uvPath = if ($uv) { $uv.Source } else { Join-Path $uvDir 'uv.exe' }
$env:PATH = (Split-Path $uvPath -Parent) + ';' + $env:PATH
& $uvPath python install 3.12
if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
$arguments = @('--admin-email', $AdminEmail, '--frontend-port', "$FrontendPort", '--backend-port', "$BackendPort")
if ($Workspace) { $arguments += @('--workspace', $Workspace) }
if ($PublicUrl) { $arguments += @('--public-url', $PublicUrl) }
if ($TrustNativeAgents) { $arguments += '--trust-native-agents' }
if ($EnableRemoteTerminal) { $arguments += '--enable-remote-terminal' }
if ($SkipProviders) { $arguments += '--skip-providers' }
if ($SkipBrowser) { $arguments += '--skip-browser' }
if ($NoStart) { $arguments += '--no-start' }
& $uvPath run --no-project --python 3.12 (Join-Path $PSScriptRoot 'install.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Correct the error above and rerun.' }
