@echo off
chcp 65001 >nul
title D4Bot Build Tool
echo ============================================
echo   D4Bot - Standalone EXE Builder
echo ============================================
echo.
echo This script will produce D4Bot.exe (zero dependencies).
echo You only need to run this ONCE.
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo.
    echo Option A: Install Python from https://python.org (check "Add to PATH")
    echo Option B: Install Miniforge (smaller):
    echo     curl -L https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe -o miniforge.exe
    echo     miniforge.exe /S /D=%USERPROFILE%\miniforge3
    echo     Then re-run this script.
    pause
    exit /b 1
)

echo [1/4] Installing PyInstaller...
pip install pyinstaller -q

echo [2/4] Installing project dependencies...
pip install numpy PyYAML opencv-python pillow pyqt5 pyautogui pynput pydirectinput keyboard pywin32 pytweening -q

echo [3/4] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Building D4Bot.exe (this takes 2-5 minutes)...
echo.
pyinstaller --clean --noconfirm d4_bot.spec

if exist "dist\D4Bot.exe" (
    echo.
    echo ============================================
    echo   SUCCESS! 
    echo   dist\D4Bot.exe is ready.
    echo   Copy it anywhere - no dependencies needed.
    echo ============================================
    explorer dist
) else (
    echo.
    echo [ERROR] Build failed. Check output above.
)
pause
