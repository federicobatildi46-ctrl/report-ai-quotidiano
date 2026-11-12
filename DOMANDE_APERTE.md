# Cose da fare

Le decisioni prese sono in [PIANO_OPERATIVO.md §8](PIANO_OPERATIVO.md). Domande aperte: nessuna.

## Da fare (tu) — ognuna serve a una fase precisa

| Quando | Cosa | Come | Stato |
|--------|------|------|-------|
| Fase 1 | **Token Apify** | In `.env` alla riga `APIFY_TOKEN=` | ✅ fatto e verificato |
| Fase 3 | **Password per le app di Gmail** | Account Google → Sicurezza → Verifica in 2 passaggi attiva → "Password per le app" → in `.env` metti `GMAIL_ADDRESS` (la tua mail), `REPORT_TO` (la stessa) e `GMAIL_APP_PASSWORD` | ✅ fatto, invio provato |
| Fase 4 | **Token Claude per il cloud** | Esegui `claude setup-token` in un terminale, poi lo salviamo come Secret del repo GitHub | ✅ fatto, caricato nei Secrets |
| Fase 7 | **Higgsfield** | CLI già installato e autenticato, Soul "Federico Finale" | ✅ fatto |
| Fase 7 | **Reference per le immagini** | Facoltativo: mandami immagini di stile se vuoi un look preciso | ⏳ quando vuoi |
| Fase 8 | **App LinkedIn Developers** | La creiamo insieme associandola alla tua Pagina aziendale esistente | ⏳ |
