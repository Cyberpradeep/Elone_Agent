@echo off
title Elone Agent — SOP Governance Hub
cd /d "%~dp0backend"

echo ========================================================
echo   Starting Elone Agent - SOP Governance Hub Dashboard
echo ========================================================
echo.

if exist "..\venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Using Python: %PYTHON_EXE%
echo Backend API & Frontend Dashboard: http://127.0.0.1:8000
echo.

start "" http://127.0.0.1:8000
"%PYTHON_EXE%" server.py
pause
