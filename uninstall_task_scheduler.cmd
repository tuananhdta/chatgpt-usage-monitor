@echo off
setlocal

set "TASK_PREFIX=ChatGPT Usage Monitor"

for %%T in (09:00 10:00 11:00 13:00 14:00 15:00 16:00 17:00) do (
  schtasks /Delete /F /TN "%TASK_PREFIX% %%T" >nul 2>nul
)

echo Removed schedules for %TASK_PREFIX%.
pause
