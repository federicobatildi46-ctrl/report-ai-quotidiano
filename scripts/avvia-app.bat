@echo off
REM Apre l'app del Report AI su http://localhost:8787.
REM Se e' spenta accende il guardiano (che la avvia e la tiene accesa), poi apre il browser.
title Report AI
cd /d "%~dp0.."
curl -s -o nul --max-time 2 http://127.0.0.1:8787/api/sync && (start "" http://localhost:8787 & exit /b 0)
echo Avvio dell'app in corso (al massimo un minuto)...
start "" wscript.exe "%~dp0avvio-nascosto.vbs"
for /l %%i in (1,1,30) do (
  timeout /t 2 /nobreak >nul
  curl -s -o nul --max-time 2 http://127.0.0.1:8787/api/sync && (start "" http://localhost:8787 & exit /b 0)
)
echo L'app non risponde: guarda data\tmp\app.log
pause
