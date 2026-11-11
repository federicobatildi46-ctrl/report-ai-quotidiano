# CLAUDE.md — istruzioni per Claude in questo progetto

Progetto: report AI quotidiano locale (vedi PIANO_OPERATIVO.md per obiettivi, architettura e fasi).

## Regole
- Lingua: tutto ciò che l'utente legge (report, UI, prompt di output) è in **italiano**.
- Costo zero come default: preferire RSS/API pubbliche → scraping HTML → Apify (solo LinkedIn).
  Mai introdurre API a pagamento senza chiederlo.
- La parte di scrittura usa `claude -p` (abbonamento), non l'API Anthropic.
- Ogni notizia nel report deve avere: link testato (HTTP 200) e badge di fact check
  (ufficiale / confermata / da verificare / smentita).
- Niente si pubblica su LinkedIn senza conferma esplicita dell'utente nella UI.
- Segreti solo in `.env` (mai nel codice o nei config versionati).

## Comandi
- `uv sync` — installa dipendenze
- `uv run digest check-sources` — verifica le fonti

## Layout
- `config/sources.yaml` fonti · `config/topics.yaml` interessi e filtro rumore
- `prompts/` template dei prompt · `src/digest/` codice · `web/` UI
- `reports/`, `outputs/`, `data/seen.json` sono generati ma **versionati** (portabilità tra PC)
- Il report quotidiano gira su GitHub Actions; i generatori (lezione/post/Shorts) girano in locale

## Rete
Su questo PC l'antivirus ispeziona l'HTTPS: Python usa `truststore` (iniettato in
`src/digest/__init__.py`), `uv` usa `system-certs = true` in pyproject.toml.
