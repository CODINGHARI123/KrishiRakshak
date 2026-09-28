@echo off
REM Start KrishiRakshak and open it in Chrome.
cd /d "%~dp0"
start "" chrome "http://localhost:5000" 2>nul || start "" "http://localhost:5000"
python app.py
