@echo off
title BJRT Backend API

echo ========================================
echo   BJRT Distribution - Backend API
echo ========================================
echo.

if not exist "venv\Scripts\activate" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
)

echo [2/4] Activating venv...
call venv\Scripts\activate

echo [3/4] Installing dependencies...
pip install -r requirements.txt -q

if not exist ".env" (
    echo.
    echo [!] .env not found. Copy .env.example to .env and edit it.
    echo     copy .env.example .env
    echo.
    pause
    exit /b 1
)

echo [4/4] Starting server...
echo.
echo   API Docs : http://localhost:8000/docs
echo   Health   : http://localhost:8000/api/v1/health
echo.
echo ========================================
echo.

uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
