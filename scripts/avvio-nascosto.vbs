' Avvia l'app del Report AI in background, senza finestre (usato all'accesso a Windows).
' Così http://localhost:8787 funziona sempre. Log in data\tmp\app.log.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
sh.Run "cmd /c (if not exist data\tmp mkdir data\tmp) & uv run digest serve --no-browser > data\tmp\app.log 2>&1", 0, False
