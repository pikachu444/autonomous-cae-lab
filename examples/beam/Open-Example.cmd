@echo off
setlocal
rem Open the public editable beam through the existing Pre working-copy launcher.
set "PSModulePath="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\scripts\start_cae_pre.ps1" -Source "%~dp0cantilever-10x20.FCStd" %*
if not errorlevel 1 exit /b 0
set "CAE_EXAMPLE_EXIT_CODE=%ERRORLEVEL%"
echo.
echo The beam example could not be opened. Read the error above.
pause
endlocal & exit /b %CAE_EXAMPLE_EXIT_CODE%
