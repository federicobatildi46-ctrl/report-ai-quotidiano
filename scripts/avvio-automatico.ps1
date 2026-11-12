# Attiva (o disattiva) l'avvio automatico dell'app all'accesso a Windows.
#   Attiva:     powershell -ExecutionPolicy Bypass -File scripts\avvio-automatico.ps1
#   Disattiva:  powershell -ExecutionPolicy Bypass -File scripts\avvio-automatico.ps1 -Rimuovi
# Crea solo un collegamento nella cartella "Esecuzione automatica" del tuo utente.
param([switch]$Rimuovi)

$startup = [Environment]::GetFolderPath('Startup')
$link = Join-Path $startup 'Report AI.lnk'

if ($Rimuovi) {
    if (Test-Path $link) { Remove-Item $link -Confirm:$false; Write-Output "Avvio automatico disattivato." }
    else { Write-Output "L'avvio automatico non era attivo." }
    exit 0
}

$vbs = Join-Path $PSScriptRoot 'avvio-nascosto.vbs'
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
$s.Arguments = '"' + $vbs + '"'
$s.WorkingDirectory = Split-Path $PSScriptRoot -Parent
$s.Description = 'Report AI: app locale su http://localhost:8787'
$s.Save()
Write-Output "Avvio automatico attivo: $link"
