@echo off
cd /d "%~dp0"
title RecruitBoss
echo.
echo  RecruitBoss - local AI hiring desk
echo  ----------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo  First run: creating Python environment...
  py -3 -m venv .venv || python -m venv .venv
  if errorlevel 1 (echo  Python 3.10+ is required. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (echo  Package install failed. Check your internet connection. & pause & exit /b 1)
if not exist ".env" copy ".env.example" ".env" >nul
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (echo  NOTE: Ollama is not running. The app still works with rules-only scoring. Start Ollama for AI reading.) else (echo  Ollama is running.)
echo.
echo  Opening http://127.0.0.1:8000  (close this window to stop)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
