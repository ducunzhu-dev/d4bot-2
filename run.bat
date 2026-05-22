@echo off
chcp 65001 >nul
title D4Bot - Unified Launcher
color 0A

echo.
echo ============================================
echo    D4Bot - Diablo 4 Automation Assistant
echo    暗黑破坏神4 智能辅助
echo ============================================
echo.
echo Supports: Barbarian / Druid / Spiritborn
echo           Necromancer / Sorceress / Rogue / Paladin
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.9+ required. Install from python.org
    echo   勾选 "Add to PATH" 后重新运行
    pause
    exit /b 1
)

:: Setup virtual environment (first run only)
if not exist venv (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [SETUP] Installing dependencies...
    pip install -r requirements.txt -q
) else (
    call venv\Scripts\activate.bat
)

echo.
echo [INFO] Starting D4Bot Control Panel...
echo        在面板中选择职业和模式即可开始
echo.
echo Controls:
echo   END  = Stop bot
echo   DEL  = Pause/Resume
echo   F12  = Capture skill icon (in Toolbox)
echo   F10  = Get cursor coords (in Toolbox)
echo.

python src\main.py

pause
