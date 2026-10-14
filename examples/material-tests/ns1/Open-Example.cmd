@echo off
setlocal
rem Use the existing desktop launcher and a new work folder on every opening.
set "PSModulePath="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\scripts\start_cae_pre.ps1" -Source "%~dp0block-j2.FCStd" %*
if not errorlevel 1 exit /b 0
set "CAE_EXAMPLE_EXIT_CODE=%ERRORLEVEL%"
echo.
echo The example could not be opened. Read the error above.
pause
endlocal & exit /b %CAE_EXAMPLE_EXIT_CODE%
