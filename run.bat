@echo off
title WeTalk Auto Bot Launcher
echo =======================================================
echo          WeTalk Auto Check-in and Video Helper
echo =======================================================
echo.
echo Detecting python environment...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b
)
echo [OK] Python detected.
echo Launching bot.py...
python -u bot.py
pause
