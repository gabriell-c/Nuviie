# Registra tarefas no Agendador do Windows (executar como Administrador)
# - Nuviie Waitress: inicia com o Windows
# - Backup diário: 03:00

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$RunScript = Join-Path $Root "deploy\windows\run-production.ps1"
$BackupScript = Join-Path $Root "deploy\windows\backup.ps1"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Execute este script como Administrador."
}

$ActionRun = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""
$TriggerRun = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Nuviie-Production" -Action $ActionRun -Trigger $TriggerRun `
    -RunLevel Highest -Force | Out-Null
Write-Host "Tarefa Nuviie-Production registrada (início com Windows)" -ForegroundColor Green

$ActionBackup = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BackupScript`""
$TriggerBackup = New-ScheduledTaskTrigger -Daily -At 3am
Register-ScheduledTask -TaskName "Nuviie-Backup" -Action $ActionBackup -Trigger $TriggerBackup `
    -Force | Out-Null
Write-Host "Tarefa Nuviie-Backup registrada (diário 03:00)" -ForegroundColor Green

Write-Host ""
Write-Host "Cloudflare Tunnel: instale cloudflared como serviço separado (ver README)." -ForegroundColor Cyan
