@echo off
setlocal
title Start JUSTICE-KP Local
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_local_app.ps1"
if errorlevel 1 (
    echo.
    echo JUSTICE-KP local startup stopped. Read the message above.
    pause
    exit /b 1
)
exit /b 0
