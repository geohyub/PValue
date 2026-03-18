@echo off
title P-Value Simulator - Desktop GUI
echo ============================================
echo   Marine P-Value Simulator - Desktop GUI
echo ============================================
echo.
echo Starting desktop application...
echo.
python -m pvalue.desktop
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. Make sure PyQt6 is installed:
    echo   pip install PyQt6
    echo.
    pause
)
