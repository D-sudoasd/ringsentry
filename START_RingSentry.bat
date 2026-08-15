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

set "PYTHON_EXE="
set "PYTHON_ARGS="

rem Prefer a project environment, then test every PATH candidate. Testing each
rem resolved file avoids a broken WindowsApps alias hiding a working Python.
call :try_python "%SCRIPT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE call :try_python "%SCRIPT_DIR%venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where py 2^>nul') do (
        if not defined PYTHON_EXE call :try_py "%%~fP"
    )
)

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYTHON_EXE call :try_python "%%~fP"
    )
)

if not defined PYTHON_EXE (
    for /f "delims=" %%P in ('where python3 2^>nul') do (
        if not defined PYTHON_EXE call :try_python "%%~fP"
    )
)

if not defined PYTHON_EXE if defined LocalAppData (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
        if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo ERROR: No working Python 3.8 or newer interpreter was found.
    echo Install Python 3.8+ or create .venv in the project directory, then try again.
    echo.
    pause
    exit /b 1
)

if /I "%MODE%"=="check" (
    echo Checking the RingSentry Python runtime and imports ^(this does not open the GUI^)...
    echo Python : "%PYTHON_EXE%" %PYTHON_ARGS%
    call "%PYTHON_EXE%" %PYTHON_ARGS% -c "import gui.app; print('runtime-import-ok')"
) else (
    echo Starting RingSentry...
    echo Project: "%CD%"
    echo Python : "%PYTHON_EXE%" %PYTHON_ARGS%
    echo.
    call "%PYTHON_EXE%" %PYTHON_ARGS% main.py
)

if errorlevel 1 (
    echo.
    echo ERROR: Startup failed.
    echo Check that dependencies are installed:
    echo     "%PYTHON_EXE%" %PYTHON_ARGS% -m pip install .
    echo.
    pause
    exit /b 1
)

exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 1
call "%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
call "%~1" -c "import gui.app" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS="
exit /b 0

:try_py
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 1
call "%~1" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
call "%~1" -3 -c "import gui.app" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%~1"
set "PYTHON_ARGS=-3"
exit /b 0
