:: D4 Bot Launcher - Spiritborn S13
:: Copy entire d4-bot folder to gaming laptop, double-click to run.
@echo off
chcp 65001 >nul
title D4 Spiritborn Bot

echo ========================================
echo   D4 Bot - Spiritborn S13
echo   DarkDBx Framework + Captain Enhance
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.9+ from python.org
    pause
    exit /b 1
)

:: Setup virtual environment (first run only)
if not exist venv (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: Copy config
echo [CONFIG] Loading Spiritborn S13 config...
copy /Y config\config_s13_spiritborn.yml config\config.yml >nul

:: Launch
echo [BOT] Starting...
echo.
echo Controls:
echo   END  = Stop bot
echo   DEL  = Pause/Resume
echo   F10  = Get coordinates
echo   F12  = Save screenshot at cursor
echo.
python src\main.py

pause
