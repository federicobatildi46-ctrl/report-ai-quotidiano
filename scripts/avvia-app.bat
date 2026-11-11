@echo off
REM Avvia l'app del Report AI: scarica i report da GitHub e apre il browser su http://localhost:8787
REM Per chiuderla basta chiudere questa finestra.
title Report AI
cd /d "%~dp0.."
uv run digest serve
if errorlevel 1 pause
