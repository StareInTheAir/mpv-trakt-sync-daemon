@echo OFF

net session >nul 2>&1
if '%errorlevel%' NEQ '0' (
    echo Please start this script with admin rights
    pause
    exit /B 1
)

cd "%~dp0"

nssm start "mpv trakt sync daemon"

pause
