@echo off
setlocal
cd /d "%~dp0"

set "TASK_PREFIX=ChatGPT Usage Monitor"
set "RUN_CMD=%~dp0run_report_once_scheduled.cmd"

for %%T in (09:00 10:00 11:00 13:00 14:00 15:00 16:00 17:00) do (
  set "TASK_TIME=%%T"
  setlocal enabledelayedexpansion
  set "TASK_NAME=%TASK_PREFIX% !TASK_TIME::=!"
  schtasks /Create /F /TN "!TASK_NAME!" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST %%T /TR "\"%RUN_CMD%\""
  endlocal
  if errorlevel 1 exit /b 1
)

echo.
echo Installed weekday schedules for %TASK_PREFIX%.
echo Make sure SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are available to scheduled tasks.
pause
