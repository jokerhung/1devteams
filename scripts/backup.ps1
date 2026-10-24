[CmdletBinding()]
param([string]$Output = '', [switch]$RegisterDaily)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not $Output) { $Output = Join-Path $repoRoot 'backups' }
$Output = [System.IO.Path]::GetFullPath($Output)
if ($RegisterDaily) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Output `"$Output`""
    $trigger = New-ScheduledTaskTrigger -Daily -At '02:00'
    Register-ScheduledTask -TaskName 'aiTeams SQLite Backup' -Action $action -Trigger $trigger -Description 'Daily SQLite and checkpoint backup for aiTeams' -Force | Out-Null
    Write-Host 'Registered daily backup at 02:00 for the current Windows account.'
    return
}
Push-Location (Join-Path $repoRoot 'backend')
try {
    & ./.venv/Scripts/python.exe scripts/backup.py --output $Output
    if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
} finally { Pop-Location }
