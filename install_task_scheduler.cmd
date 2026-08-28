@echo off
setlocal
cd /d "%~dp0"

set "TASK_PREFIX=ChatGPT Usage Monitor"
set "RUN_CMD=%~dp0run_report_once_scheduled.cmd"

for %%T in (09:00 10:00 11:00 13:00 14:00 15:00 16:00 17:00) do (
  schtasks /Create /F /TN "%TASK_PREFIX% %%T" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST %%T /TR "\"%RUN_CMD%\""
  if errorlevel 1 exit /b 1
)

echo.
echo Installed weekday schedules for %TASK_PREFIX%.
echo Make sure SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are available to scheduled tasks.
pause
