@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || (
    echo ERROR: Cannot enter project directory:
    echo "%SCRIPT_DIR%"
    echo.
    pause
    exit /b 1
)

set "MODE=run"
if /I "%~1"=="--check" set "MODE=check"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo ERROR: Python was not found.
    echo Install Python 3.8+ or enable the Python launcher, then run this file again.
    echo.
    pause
    exit /b 1
)

if /I "%MODE%"=="check" (
    echo Checking RingSentry startup environment...
    %PYTHON_CMD% -c "import gui.app; print('import-ok')"
) else (
    echo Starting RingSentry...
    echo Project: "%CD%"
    echo Python : %PYTHON_CMD%
    echo.
    %PYTHON_CMD% main.py
)

if errorlevel 1 (
    echo.
    echo ERROR: Startup failed.
    echo Check that dependencies are installed:
    echo     pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

exit /b 0
