@echo off
chcp 65001 >nul
title D4 Bot - Auto Calibration
echo ============================================
echo   D4 Bot - 自动坐标校准
echo ============================================
echo.
echo 使用前请确保:
echo 1. 暗黑4 正在运行（窗口全屏 1920x1080）
echo 2. 角色站在主城（不要在菜单/加载界面）
echo 3. HUD 可见（血条、技能栏、小地图都在）
echo.

cd /d "%~dp0"
python -c "import sys; sys.path.insert(0,'src'); from bot.calibrate import run_calibration; run_calibration()"

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   校准成功！
    echo   坐标已保存到 config/calibration.yaml
    echo ============================================
) else (
    echo.
    echo ============================================
    echo   校准失败！请确保:
    echo   - D4 在游戏中（不在菜单/加载）
    echo   - 分辨率为 1920x1080 窗口全屏
    echo   - 再试一次
    echo ============================================
)
pause
