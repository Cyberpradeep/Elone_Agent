# Elone Agent — SOP Governance Hub PowerShell Launcher
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Starting Elone Agent - SOP Governance Hub Dashboard" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$pythonExe = "python"
if (Test-Path "$scriptDir\..\venv\Scripts\python.exe") {
    $pythonExe = "$scriptDir\..\venv\Scripts\python.exe"
}

Write-Host "Using Python: $pythonExe" -ForegroundColor Yellow
Write-Host "Launching Browser at http://127.0.0.1:8000" -ForegroundColor Green

Start-Process "http://127.0.0.1:8000"
& $pythonExe "$scriptDir\server.py"
