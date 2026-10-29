@echo off
setlocal
cd /d "%~dp0"
title AI Think Hack Create - laptop fallback
set "AAROHAN_ENV_FILE=%~dp0backend\.env.event"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Install backend\requirements.txt first.
  pause
  exit /b 1
)
if not exist "%AAROHAN_ENV_FILE%" (
  echo Create backend\.env.event from backend\event-fallback.example and fill in the private settings.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backend\check_event_fallback.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo Team URL: http://localhost:5000/
echo Find this laptop's Wi-Fi IPv4 address with ipconfig, then share http://HOST-IP:5000/
echo Admin URL: http://HOST-IP:5000/admin-login
echo Keep this window and the laptop awake. All clients must use this same fallback URL.
cd backend
"..\.venv\Scripts\python.exe" -m waitress --listen=0.0.0.0:5000 --threads=16 app:app
pause
