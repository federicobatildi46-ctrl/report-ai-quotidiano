@echo off
REM Apre l'app del Report AI su http://localhost:8787.
REM Se e' gia' accesa (avvio automatico), apre solo il browser; altrimenti la avvia.
title Report AI
cd /d "%~dp0.."
curl -s -o nul --max-time 2 http://localhost:8787/api/sync && (start "" http://localhost:8787 & exit /b 0)
uv run digest serve
if errorlevel 1 pause
