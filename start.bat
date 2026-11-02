@echo off
rem Double-click to start VendorGate on Windows. Needs Python 3.9+ (python.org installer).
rem First run installs packages into backend\.venv (internet needed); later runs work offline.
rem Extra options are passed through, e.g.  start.bat --port 8010   or   start.bat --no-browser
setlocal EnableExtensions
cd /d "%~dp0"
title VendorGate - vendor onboarding
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%~dp0run.py" goto not_extracted

set "PY="
for %%C in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=%%~C"
  )
)
if not defined PY goto no_python

%PY% "%~dp0run.py" %*
if errorlevel 1 goto failed
exit /b 0

:no_python
echo.
echo Python 3.9 or newer was not found.
echo  1. Install it from https://www.python.org/downloads/windows/
echo     (tick "Add python.exe to PATH" on the first installer screen).
echo  2. Close this window and double-click start.bat again.
echo.
pause
exit /b 1

:not_extracted
echo.
echo Please extract the zip first (right-click the zip, choose "Extract All"),
echo then double-click start.bat inside the extracted folder.
echo.
pause
exit /b 1

:failed
echo.
echo VendorGate stopped with an error. Read the message above, fix it, and run start.bat again.
echo.
if not defined VG_NO_PAUSE pause
exit /b 1
