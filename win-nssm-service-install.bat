@echo OFF

net session >nul 2>&1
if '%errorlevel%' NEQ '0' (
    echo Please start this script with admin rights
    pause
    exit /B 1
)

cd "%~dp0"

nssm install "mpv trakt sync daemon" \"%~dp0venv\Scripts\python.exe\" \"%~dp0mpv-trakt-daemon.py\"

nssm set "mpv trakt sync daemon" AppDirectory "%~dp0"
nssm set "mpv trakt sync daemon" AppStdout "%~dp0\log.txt"
nssm set "mpv trakt sync daemon" AppStderr "%~dp0\log.txt"

pause
