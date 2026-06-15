# Nuviie — servidor de produção (Waitress)
# Escuta apenas em 127.0.0.1 — o Cloudflare Tunnel expõe HTTPS publicamente.
# Uso: .\deploy\windows\run-production.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "Virtualenv não encontrado em $Root\.venv — crie com: python -m venv .venv"
}

Write-Host "==> Nuviie produção (Waitress em 127.0.0.1:8000)" -ForegroundColor Cyan

& $Python manage.py collectstatic --noinput

$Waitress = Join-Path $Root ".venv\Scripts\waitress-serve.exe"
if (-not (Test-Path $Waitress)) {
    Write-Error "waitress-serve não encontrado. Rode: pip install waitress"
}
& $Waitress --listen=127.0.0.1:8000 core.wsgi:application
