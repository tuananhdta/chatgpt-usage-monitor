@echo off
cd /d "%~dp0"
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
  echo ERROR: python.exe was not found in PATH.
  exit /b 2
)

"%PYTHON_EXE%" "%~dp0listener_watchdog.py" >> "%~dp0data\slack_listener.log" 2>&1
exit /b %ERRORLEVEL%
