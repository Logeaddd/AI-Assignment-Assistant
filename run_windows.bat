@echo off
setlocal
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Please copy the error above and send it to the developer.
  pause
)
