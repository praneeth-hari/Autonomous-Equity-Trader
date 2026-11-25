@echo off
REM Starts the read-only API (port 8000) and the web UI (port 5173). Local only.
cd /d "%~dp0"
start "Paper Trader API" cmd /k "python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000"
cd web
start "Paper Trader Web" cmd /k "npm run dev"
