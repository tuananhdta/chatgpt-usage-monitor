@echo off
cd /d "%~dp0"
python run_report_once.py --source automation --requested-by "Task Scheduler" >> "%~dp0data\scheduled.log" 2>&1
