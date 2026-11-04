@echo off
rem Starts Responsive Viewer and opens it in your browser.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Responsive Viewer isn't installed yet. Double-click install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py %*
pause
