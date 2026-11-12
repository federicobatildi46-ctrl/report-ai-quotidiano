' Guardiano dell'app del Report AI: parte all'accesso a Windows, senza finestre.
' Ogni 30 secondi controlla http://localhost:8787: se l'app non risponde la (ri)avvia.
' Cosi' il segnalibro funziona sempre, anche se l'app si blocca o si chiude.
' Log dell'app in data\tmp\app.log (le righe del guardiano in data\tmp\guardiano.log).
Option Explicit
Dim fso, sh, root, tmp, url, mutexFile, lock
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
sh.CurrentDirectory = root
tmp = root & "\data\tmp"
If Not fso.FolderExists(tmp) Then fso.CreateFolder tmp
url = "http://127.0.0.1:8787/api/sync"

' Un solo guardiano alla volta: il file resta aperto finche' questo guardiano vive.
mutexFile = tmp & "\guardiano.lock"
On Error Resume Next
Set lock = fso.OpenTextFile(mutexFile, 2, True)
If Err.Number <> 0 Then WScript.Quit 0   ' c'e' gia' un guardiano attivo
On Error GoTo 0

Function AppRisponde()
    Dim http
    AppRisponde = False
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 2000, 2000, 3000, 5000
    http.Open "GET", url, False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 Then AppRisponde = True
    End If
    On Error GoTo 0
End Function

Sub Annota(testo)
    Dim f
    On Error Resume Next
    Set f = fso.OpenTextFile(tmp & "\guardiano.log", 8, True)
    f.WriteLine Now & "  " & testo
    f.Close
    On Error GoTo 0
End Sub

Dim attese
Annota "guardiano avviato"
Do
    If Not AppRisponde() Then
        Annota "app spenta: la avvio"
        ' PYTHONUNBUFFERED: cosi' il log si scrive subito (utile se qualcosa va storto)
        sh.Run "cmd /c set PYTHONUNBUFFERED=1&& uv run digest serve --no-browser >> data\tmp\app.log 2>&1", 0, False
        ' tempo per partire (uv sync + git pull all'avvio) prima del prossimo controllo
        attese = 0
        Do While attese < 24 And Not AppRisponde()
            WScript.Sleep 5000
            attese = attese + 1
        Loop
        If AppRisponde() Then Annota "app pronta" Else Annota "app non partita: riprovo"
    End If
    WScript.Sleep 30000
Loop
