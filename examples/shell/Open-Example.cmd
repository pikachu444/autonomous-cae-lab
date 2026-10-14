@echo off
setlocal
rem Reuse the Pre launcher: the public plate is opened in a new working folder.
set "PSModulePath="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\start_cae_pre.ps1" -Source "%~dp0plate-s8.FCStd" %*
if not errorlevel 1 exit /b 0
set "CAE_EXAMPLE_EXIT_CODE=%ERRORLEVEL%"
echo.
echo The shell example could not be opened. Read the error above.
pause
endlocal & exit /b %CAE_EXAMPLE_EXIT_CODE%
