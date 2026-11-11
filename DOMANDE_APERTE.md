# Cose da fare

Le decisioni prese sono in [PIANO_OPERATIVO.md §8](PIANO_OPERATIVO.md). Domande aperte: nessuna.

## Da fare (tu) — ognuna serve a una fase precisa

| Quando | Cosa | Come | Stato |
|--------|------|------|-------|
| Fase 1 | **Token Apify** | In `.env` alla riga `APIFY_TOKEN=` | ✅ fatto e verificato |
| Fase 3 | **Password per le app di Gmail** | Account Google → Sicurezza → Verifica in 2 passaggi attiva → "Password per le app" → in `.env` metti `GMAIL_ADDRESS` (la tua mail), `REPORT_TO` (la stessa) e `GMAIL_APP_PASSWORD` | ⏳ |
| Fase 4 | **Token Claude per il cloud** | Esegui `claude setup-token` in un terminale, poi lo salviamo come Secret del repo GitHub | ⏳ |
| Fase 7 | **Autorizzare Higgsfield** | In Claude Code: `/mcp` → higgsfield → autorizza | ⏳ |
| Fase 7 | **Reference per le immagini** | Mandami le immagini di riferimento quando creiamo le prime | ⏳ |
| Fase 8 | **App LinkedIn Developers** | La creiamo insieme associandola alla tua Pagina aziendale esistente | ⏳ |
