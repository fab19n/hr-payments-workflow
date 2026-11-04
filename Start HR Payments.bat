@echo off
rem Starts the HR Payments app on this PC only and opens it in your browser.
cd /d "%~dp0"
start "" http://127.0.0.1:8626
".venv\Scripts\python.exe" -m hrp.app
pause
