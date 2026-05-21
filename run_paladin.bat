:: D4 Bot Launcher - Paladin S13 审判爆炸流
@echo off
chcp 65001 >nul
title D4 Paladin Bot

echo =========================================
echo   D4 Paladin - S13 Judgment Explosion
echo   审判连锁爆炸流 - T120 以下通吃
echo =========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.9+ required
    pause
    exit /b 1
)

if not exist venv (
    echo [SETUP] Creating venv...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo [CONFIG] Paladin S13 Judgment Explosion
copy /Y config\config_s13_paladin.yml config\config.yml >nul

echo.
echo [IMPORTANT] Before first run:
echo   1. Set skills: 圣光箭/祝福之盾/天堂之矛/圣光光环/天罚/审判者誓言
echo   2. Open toolbox (will appear on screen)
echo   3. Press F12 over each skill icon to capture
echo   4. Replace assets/skills/paladin/*.png with captures
echo.
echo [BOT] Starting...
echo END=Stop  DEL=Pause  F10=Coords  F12=Capture icon
echo.
python src\main.py
pause
