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
- `uv run digest collect [--dry-run] [--hours N] [--only ID ...]` — raccolta in `data/raw/`
- Per sviluppare senza toccare la memoria usa sempre `--dry-run`; `data/raw/sample-72h.json` è
  un campione completo per la Fase 2

- `uv run digest build [--input file] [--model m]` — report in `reports/` (JSON + anteprima .md)

## Report (Fase 2)
- Due chiamate `claude -p` in `src/digest/build.py`: selezione (prompts/triage.md) e scrittura
  (prompts/digest.md). Claude non scrive mai URL: i link vengono dalle fonti raccolte.
- `src/digest/claude.py` chiama claude.exe direttamente (non il .cmd), senza MCP né strumenti,
  con `--json-schema`. Evita vincoli rigidi (minItems/maxItems) nello schema: causano rigenerazioni.
- I badge vengono corretti da `fix_badge`; i domini ufficiali e le etichette brevi delle fonti
  sono in `config/sources.yaml` (`official_domains`, `labels`).

## Cloud (Fase 4)
- `.github/workflows/daily.yml` → `uv run digest daily` alle 06:00 UTC, poi commit di `reports/`
  e `data/seen.json`. Prima di modificare in locale: `git pull` (il bot committa ogni giorno).
- Segreti nel repo, non in chiaro: per aggiornarli `gh secret set NOME` (valore da stdin).
- `data/seen.json` è la memoria ufficiale: vive nel repo e la aggiorna il cloud. In locale usa
  `--dry-run` per non creare divergenze.

## App locale (Fasi 5-6)
- `src/digest/app.py` (FastAPI, solo 127.0.0.1:8787) + `web/` (HTML/CSS/JS, marked + DOMPurify da CDN).
- `src/digest/generate.py`: riscarica le fonti (pagina / trascrizione YouTube / README GitHub;
  LinkedIn non scaricabile), compila `prompts/{lesson,linkedin_post,youtube_short}.md`, salva in
  `outputs/{lezioni,linkedin,shorts}/<item_id>.md` con frontmatter YAML.
- `src/digest/gitsync.py`: pull all'avvio, commit+push di ogni contenuto creato.
- Prova nel browser integrato: `.claude/launch.json` → configurazione `report-app`.
- Nel JS le chiamate usano `cache: "no-store"`: senza, il browser mostrava stati vecchi.

## Aggiungere una fonte
Nuovo tipo → funzione `async def collect_x(ctx: Ctx) -> list[Item]` in `src/digest/collectors/`,
registrata in `collectors/__init__.py`. Usa sempre `ctx.is_new(key)` prima di arricchire
(scaricare pagine) e `is_fresh(data, ctx.since)` per la finestra.

## Layout
- `config/sources.yaml` fonti · `config/topics.yaml` interessi e filtro rumore
- `prompts/` template dei prompt · `src/digest/` codice · `web/` UI
- `reports/`, `outputs/`, `data/seen.json` sono generati ma **versionati** (portabilità tra PC)
- Il report quotidiano gira su GitHub Actions; i generatori (lezione/post/Shorts) girano in locale

## Rete
Su questo PC Avast ispeziona l'HTTPS: Python usa `truststore` (iniettato in
`src/digest/__init__.py`), `uv` usa `system-certs = true` in pyproject.toml.
Per l'email: Avast Mail Shield intercetta smtp.gmail.com:465 con un root "Untrusted" → si usa la
porta 587 + STARTTLS (verifica completa). Non disattivare mai la verifica dei certificati.
