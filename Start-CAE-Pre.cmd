@echo off
setlocal
rem Windows PowerShell rebuilds its module paths after a PS7/Python parent.
set "PSModulePath="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_cae_pre.ps1" %*
set "CAE_NATIVE_EXIT_CODE=%ERRORLEVEL%"
if not "%CAE_NATIVE_EXIT_CODE%"=="0" (
  echo.
  echo Pre startup failed. Read the error above.
  if "%~1"=="" (
    echo Press any key to close.
    pause >nul
  )
)
endlocal & exit /b %CAE_NATIVE_EXIT_CODE%
