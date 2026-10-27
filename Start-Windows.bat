@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up the app, this takes a minute or two...
  %PY% -m venv .venv || (echo. & echo Python not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
)
echo Opening the Day Trader Panel in your browser. To quit, close this window.
".venv\Scripts\python.exe" -m streamlit run app.py --browser.gatherUsageStats false
pause
