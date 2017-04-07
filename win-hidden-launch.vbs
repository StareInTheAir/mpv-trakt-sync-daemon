Dim shell
Set shell = CreateObject("WScript.Shell")

Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")

If (fso.FileExists("venv\Scripts\pythonw.exe")) Then
    shell.Run "venv\Scripts\pythonw.exe mpv-trakt-daemon.py"
Else
    shell.Run "pythonw.exe mpv-trakt-daemon.py"
End If
