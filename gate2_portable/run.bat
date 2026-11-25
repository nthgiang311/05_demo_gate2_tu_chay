@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || (echo Can Python 3.12 hoac 3.13 & pause & exit /b 1)
)
.venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
if not exist .env copy .env.example .env >nul
start "" http://127.0.0.1:8765
.venv\Scripts\python -X utf8 server.py
pause
