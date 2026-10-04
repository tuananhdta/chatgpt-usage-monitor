@echo off
setlocal

set "TASK_PREFIX=ChatGPT Usage Monitor"

for %%T in (09:00 10:00 11:00 13:00 14:00 15:00 16:00 17:00) do (
  set "TASK_TIME=%%T"
  setlocal enabledelayedexpansion
  set "TASK_NAME=%TASK_PREFIX% !TASK_TIME::=!"
  schtasks /Delete /F /TN "!TASK_NAME!" >nul 2>nul
  endlocal
)

schtasks /Delete /F /TN "ChatGPT Usage Monitor Slack Listener" >nul 2>nul

echo Removed schedules for %TASK_PREFIX%.
pause
