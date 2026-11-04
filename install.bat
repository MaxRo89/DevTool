@echo off
rem Responsive Viewer installer for Windows. Double-click this file.
setlocal
cd /d "%~dp0"

echo.
echo ==^> Looking for Python 3.9 or newer
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Error: Python 3.9+ was not found.
  echo   Install it from https://www.python.org/downloads/windows/
  echo   and check "Add python.exe to PATH" during setup.
  echo   Or run: winget install Python.Python.3.12
  echo   Then double-click install.bat again.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo Using %%v

echo.
echo ==^> Creating a private environment in .venv
if exist ".venv\Scripts\python.exe" (
  echo Already exists, reusing it.
) else (
  %PY% -m venv .venv
  if errorlevel 1 (
    echo.
    echo Error: couldn't create the environment.
    pause
    exit /b 1
  )
)

echo.
echo ==^> Installing dependencies (Flask, requests)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 (
  echo.
  echo Error: couldn't install the dependencies. Check your internet connection and try again.
  pause
  exit /b 1
)

echo.
echo Responsive Viewer is installed.
echo To open it later, double-click start.bat
echo.
choice /c YN /m "Open it now"
if errorlevel 2 exit /b 0
".venv\Scripts\python.exe" app.py
pause
