@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%START_2D_Image_Processor.cmd" %*
exit /b %ERRORLEVEL%
