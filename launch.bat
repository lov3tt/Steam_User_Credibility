@echo off
cd /d "%~dp0"
title Steam Player Credibility
color 0B

echo.
echo  ========================================
echo   Steam Player Credibility - Launcher
echo  ========================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Please install Python 3.10+ from https://python.org
    echo.
    pause
    exit /b 1
)

:: Stop any old server still running on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Install / upgrade dependencies silently
echo  Installing dependencies...
python -m pip install -r requirements.txt --quiet --upgrade

:: Launch Flask in background and open browser
echo  Starting server at http://127.0.0.1:5000 ...
echo.

:: Start Flask in a new window so this console stays clean
start "Steam Player Credibility - Server" cmd /k "cd /d "%~dp0" && python app.py"

:: Give the server a moment to start, then open the browser
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000"

echo  Server launched! Browser should open automatically.
echo  Close the server window to stop the app.
echo.
pause