@echo off
title P-Value Simulator - Web GUI
echo ============================================
echo   Marine P-Value Simulator - Web Interface
echo ============================================
echo.
echo Starting server... (browser will open automatically)
echo Close this window to stop the server.
echo.
python -m streamlit run "%~dp0pvalue\app.py" --server.port 8501
pause
