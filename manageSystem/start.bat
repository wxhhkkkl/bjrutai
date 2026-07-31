@echo off
title BJRT Admin

echo ========================================
echo   BJRT Distribution - Admin Console
echo ========================================
echo.

if not exist "node_modules" (
    echo [1/3] Installing dependencies...
    npm install
) else (
    echo [1/3] Dependencies already installed
)

if not exist ".env" (
    echo [2/3] Creating .env from template...
    copy .env.example .env >nul
    echo       Default API: http://localhost:8000/api/v1
)

echo [3/3] Starting dev server...
echo.
echo   Admin: http://localhost:5173
echo.
echo ========================================
echo.

npm run dev
