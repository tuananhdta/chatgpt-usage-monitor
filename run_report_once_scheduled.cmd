@echo off
cd /d "%~dp0"
python run_report_once.py >> "%~dp0data\scheduled.log" 2>&1
