Dim shell
Set shell = CreateObject("Wscript.Shell")

shell.Run "cmd /c venv\Scripts\python.exe mpv-trakt-daemon.py >> log.txt 2>&1", 0, False
