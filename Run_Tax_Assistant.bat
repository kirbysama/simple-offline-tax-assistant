@echo off
title Tax Assistant - 1099 Aggregator & NY Sales Tax Calculator
echo ===================================================
echo Starting Tax Assistant Web Dashboard...
echo ===================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERROR] Virtual environment not found at .venv
    echo Please make sure the virtual environment is installed.
    pause
    exit /b 1
)

echo Launching Streamlit dashboard in your default browser...
call ".venv\Scripts\streamlit.exe" run app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo Streamlit stopped with an error code: %ERRORLEVEL%
    pause
)
