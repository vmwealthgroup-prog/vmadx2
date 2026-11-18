@echo off
cd /d %~dp0
if not exist venv (
  echo Creating virtual environment...
  python -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo *** Package install failed. Copy the error above and send it. ***
  pause
  exit /b 1
)
if not exist .env (
  copy .env.example .env
  echo.
  echo *** .env created. Fill in your Kotak details in .env, then run this again. ***
)
python app.py
pause
