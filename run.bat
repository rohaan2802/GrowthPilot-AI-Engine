@echo off
title GrowthPilot - AI Sales & Outbound Engine
color 0A

cd /d "%~dp0"

echo ====================================================================
echo        GrowthPilot - AI Sales & Outbound Engine (Group 904)
echo               FAST School of Computing, Islamabad
echo ====================================================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment .venv not found in %~dp0!
    echo Creating virtual environment and installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [INFO] Created .env from .env.example
    )
)

python run.py
pause
