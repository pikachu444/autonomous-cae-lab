@echo off
setlocal
rem Let Windows PowerShell rebuild its module paths after a PS7/Python parent.
set "PSModulePath="
if /I "%~1"=="-Tool" if /I "%~3"=="-DesktopShortcut" if "%~4"=="" goto shortcut
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1" %*
goto finished
:shortcut
rem Only the installer's fixed -Tool NAME -DesktopShortcut form enters here.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-windows.ps1" -Tool "%~2"
:finished
set "CAE_LAB_EXIT_CODE=%ERRORLEVEL%"
if not "%CAE_LAB_EXIT_CODE%"=="0" (
  echo.
  echo Startup failed. Read the error above.
  if "%~1"=="" (
    echo Press any key to close.
    pause >nul
  )
  if /I "%~1"=="-Tool" if /I "%~3"=="-DesktopShortcut" if "%~4"=="" (
    echo Press any key to close.
    pause >nul
  )
)
endlocal & exit /b %CAE_LAB_EXIT_CODE%
