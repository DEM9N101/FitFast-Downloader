@echo off
setlocal
REM Launch FitFast Downloader using the Camoufox venv (Playwright 1.49).
title FitFast Downloader
set PYEXE=%USERPROFILE%\.camoufox-venv\Scripts\pythonw.exe
if not exist "%PYEXE%" set PYEXE=%USERPROFILE%\.camoufox-venv\Scripts\python.exe
if not exist "%PYEXE%" (
    echo Camoufox venv not found at %USERPROFILE%\.camoufox-venv
    echo See README.md for setup instructions.
    pause
    exit /b 1
)
start "" "%PYEXE%" -m app.main
endlocal
