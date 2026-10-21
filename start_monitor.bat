@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 bootstrap.py
    goto :finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python bootstrap.py
    goto :finished
)
echo Python was not found. Install Python 3.10 or newer from https://www.python.org/downloads/windows/
echo Include pip and Tcl/Tk, then open this launcher again.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo The monitor could not start or closed with an error. See the message above.
    pause
    exit /b 1
)
exit /b 0
