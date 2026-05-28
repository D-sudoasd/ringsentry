@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%START_RingSentry.cmd" %*
exit /b %ERRORLEVEL%
