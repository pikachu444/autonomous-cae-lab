@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Read the error above; press any key to close.
  pause >nul
  exit /b 1
)
endlocal
