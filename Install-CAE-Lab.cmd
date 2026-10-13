@echo off
setlocal
rem Use the existing private Windows runtime; no native solver is installed.
set "PSModulePath="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1" -ResearchUI
if errorlevel 1 goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-desktop-shortcuts.ps1" %*
if errorlevel 1 goto failed
echo.
echo Setup complete. Open Autonomous CAE Lab in your Start menu.
echo Keep this source folder in place. Moving it requires shortcut reinstallation.
pause
endlocal & exit /b 0
:failed
set "CAE_LAB_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Setup failed. Read the error above. Existing shortcuts and user data are preserved.
pause
endlocal & exit /b %CAE_LAB_EXIT_CODE%
