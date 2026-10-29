@echo off
setlocal
cd /d "%~dp0"
title Aarohan 2026 event server
if not exist ".venv\Scripts\python.exe" (
  echo Create the virtual environment and install backend\requirements.txt first.
  pause
  exit /b 1
)
if not exist "backend\.env" (
  echo Copy backend\.env.example to backend\.env and set ADMIN_PASSWORD first.
  pause
  exit /b 1
)
echo Registration: http://localhost:5000/
echo Admin: http://localhost:5000/admin-login
echo Keep this window open while the event is running.
cd backend
"..\.venv\Scripts\python.exe" -m waitress --listen=0.0.0.0:5000 --threads=16 app:app
pause
