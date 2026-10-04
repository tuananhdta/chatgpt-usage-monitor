@echo off
setlocal
cd /d "%~dp0"

 powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_slack_listener_task.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: Could not create the listener task.
  echo Run this file as Administrator once if Windows reports Access is denied.
  pause
  exit /b 1
)

echo.
echo Make sure .env contains the Socket Mode token and allowlist values.
pause
