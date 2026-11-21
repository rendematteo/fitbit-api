# run.ps1 - atajos del proyecto FitClub
# Uso:
#   .\run.ps1 auth     # re-autorizar (el token dura 7 dias)
#   .\run.ps1 test     # validar credencial + API
#   .\run.ps1 sync     # bajar datos (sin heart-rate)
#   .\run.ps1 report   # generar los 4 HTML
#   .\run.ps1 all      # sync + report
#   .\run.ps1 sync --since 2026-10-01   # args extra al script

param(
    [Parameter(Position = 0)][string]$Cmd = "help",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    $known = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $known) { return $known }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    throw "No encontre Python. Instala Python 3.12+ (https://www.python.org/downloads/)."
}

$py = Get-Python

function Invoke-Report {
    & $py "scripts\panel.py"
    & $py "scripts\plan_vs_real.py"
    & $py "scripts\reporte_2_dias.py"
    & $py "scripts\make_dashboard.py"
}

switch ($Cmd.ToLower()) {
    "auth"   { & $py "scripts\authorize_google_health.py" @Rest }
    "test"   { & $py "scripts\check_and_download.py" --test @Rest }
    "sync"   { & $py "scripts\check_and_download.py" @Rest }
    "report" { Invoke-Report }
    "all"    { & $py "scripts\check_and_download.py" @Rest; Invoke-Report }
    default {
        Write-Host ""
        Write-Host "FitClub - atajos" -ForegroundColor Cyan
        Write-Host "  .\run auth     # re-autorizar (token dura 7 dias)"
        Write-Host "  .\run test     # validar credencial + API"
        Write-Host "  .\run sync     # bajar datos (sin heart-rate)"
        Write-Host "  .\run report   # generar los 4 HTML"
        Write-Host "  .\run all      # sync + report"
        Write-Host ""
        Write-Host "  Extra: .\run sync --since 2026-10-01" -ForegroundColor DarkGray
        Write-Host ""
    }
}
