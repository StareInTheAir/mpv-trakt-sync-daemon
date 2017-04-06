@echo off

if exist "venv\Scripts\pythonw.exe" (
    start venv\Scripts\pythonw.exe "mpv-trakt-daemon.py"
) else (
    start pythonw.exe "mpv-trakt-daemon.py"
)
