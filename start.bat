@echo off

echo ========================================
echo   BJRT Distribution System
echo ========================================
echo.
echo   [1] Backend API     (backend)
echo   [2] Admin Console   (admin)
echo   [3] Start Both
echo   [0] Exit
echo.
set /p choice="Select: "

if "%choice%"=="1" (
    cd /d "%~dp0backend"
    call start.bat
) else if "%choice%"=="2" (
    cd /d "%~dp0admin"
    call start.bat
) else if "%choice%"=="3" (
    echo Starting Backend API...
    start "BJRT-Backend" cmd /c "cd /d %~dp0backend && start.bat"
    timeout /t 3 >nul
    echo Starting Admin Console...
    start "BJRT-Admin" cmd /c "cd /d %~dp0admin && start.bat"
    echo.
    echo Both services launched in separate windows
) else (
    exit /b 0
)

pause
