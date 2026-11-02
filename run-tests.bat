@echo off
rem Runs the backend test suite (27 end-to-end tests) on Windows.
setlocal EnableExtensions
cd /d "%~dp0"
set "VG_NO_PAUSE=1"
call "%~dp0start.bat" --test
echo.
pause
