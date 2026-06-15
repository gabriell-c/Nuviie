# Nuviie — backup diário de banco SQLite e media/
# Uso: .\deploy\windows\backup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Date = Get-Date -Format "yyyy-MM-dd_HHmm"
$Dest = Join-Path $Root "deploy\backups\$Date"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$Db = Join-Path $Root "db.sqlite3"
$Media = Join-Path $Root "media"

if (Test-Path $Db) {
    Copy-Item $Db (Join-Path $Dest "db.sqlite3")
    Write-Host "Backup: db.sqlite3" -ForegroundColor Green
} else {
    Write-Host "Aviso: db.sqlite3 não encontrado" -ForegroundColor Yellow
}

if (Test-Path $Media) {
    Copy-Item $Media (Join-Path $Dest "media") -Recurse
    Write-Host "Backup: media/" -ForegroundColor Green
}

Write-Host "Salvo em: $Dest" -ForegroundColor Cyan
