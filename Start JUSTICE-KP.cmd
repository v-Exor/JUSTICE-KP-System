@echo off
setlocal
title Start JUSTICE-KP
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_tailscale_app.ps1"
if errorlevel 1 (
    echo.
    echo JUSTICE-KP could not start. Read the message above.
    pause
    exit /b 1
)
exit /b 0
