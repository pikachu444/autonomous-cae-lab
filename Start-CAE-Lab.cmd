@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1" %*
set "CAE_LAB_EXIT_CODE=%ERRORLEVEL%"
if not "%CAE_LAB_EXIT_CODE%"=="0" (
  echo.
  echo Startup failed. Read the error above; press any key to close.
  pause >nul
)
endlocal & exit /b %CAE_LAB_EXIT_CODE%
