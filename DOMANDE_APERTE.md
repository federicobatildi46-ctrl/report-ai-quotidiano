# Cose da fare e domande rimaste

Le decisioni prese sono in [PIANO_OPERATIVO.md §8](PIANO_OPERATIVO.md).

## Da fare (tu) — ognuna serve a una fase precisa

| Quando | Cosa | Come |
|--------|------|------|
| Fase 1 | **Token Apify** | Incollalo tu in `.env` alla riga `APIFY_TOKEN=` (non in chat: così non resta nella cronologia) |
| Fase 3 | **Password per le app di Gmail** | Account Google → Sicurezza → Verifica in 2 passaggi attiva → "Password per le app" → incollala in `.env` (`GMAIL_APP_PASSWORD`) |
| Fase 4 | **Token Claude per il cloud** | Esegui `claude setup-token` in un terminale, poi lo salviamo come Secret del repo GitHub |
| Fase 7 | **Autorizzare Higgsfield** | In Claude Code: `/mcp` → higgsfield → autorizza |
| Fase 8 | **Pagina LinkedIn** | Crea una Pagina aziendale gratuita (es. la futura agenzia): serve solo per creare l'app su LinkedIn Developers |

## Domande rimaste

1. **Brand e stile visivo:** hai colori, font o immagini di riferimento per le immagini dei post?
   Se no, li definiamo in Fase 7 partendo dai tuoi post migliori.
2. **Email:** il report arriva allo stesso Gmail da cui parte, o a un altro indirizzo?
