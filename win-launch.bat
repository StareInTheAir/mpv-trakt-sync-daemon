@echo off

if exist "venv\Scripts\pythonw.exe" (
    start venv\Scripts\pythonw.exe "sync_daemon.py"
) else (
    start pythonw.exe "sync_daemon.py"
)
