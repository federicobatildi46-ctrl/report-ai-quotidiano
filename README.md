# Report AI quotidiano

Un report personale che ogni mattina raccoglie, filtra, verifica e riassume le notizie AI che
contano per me — Claude, Higgsfield, ElevenLabs, i creator che seguo e le novità GitHub per la mia
futura agenzia — me lo manda su Gmail e me lo fa leggere in un'app locale, da cui posso
trasformare ogni notizia in una lezione, un post LinkedIn o uno script Shorts.

- Il report si genera **nel cloud con GitHub Actions** (gratis, anche col PC spento).
- I contenuti (lezioni, post, Shorts) si generano **sul PC** dall'app locale.
- Tutto vive in questo repo privato: cambiando PC basta clonarlo.

Il piano completo è in [PIANO_OPERATIVO.md](PIANO_OPERATIVO.md).

## Requisiti

| Strumento | A cosa serve |
|-----------|--------------|
| Python 3.12+ e `uv` | raccolta, report, app locale |
| Claude Code CLI (`claude`) | scrittura, filtro e fact check, con l'abbonamento Claude |
| `yt-dlp` e `ffmpeg` | sottotitoli e frame dei video YouTube |
| `gh` (GitHub CLI) | repo, segreti del cloud, API GitHub |
| Skill `/watch` | analisi dei video quando i sottotitoli non bastano |

## Installazione (anche su un PC nuovo)

```bash
gh repo clone federicobatildi46-ctrl/report-ai-quotidiano
```

```bash
cd report-ai-quotidiano
```

```bash
uv sync
```

```bash
cp .env.example .env
```

Poi compila `.env` seguendo i commenti nel file. `.env` non va mai su GitHub.

> Nota: su questo PC l'antivirus ispeziona l'HTTPS. Il progetto usa già i certificati di
> Windows (`truststore` in Python, `system-certs` per `uv`), quindi non serve fare nulla.

## Comandi

```bash
uv run digest check-sources
```

Verifica che tutte le fonti in `config/sources.yaml` rispondano.

```bash
uv run digest collect
```

Raccoglie le novità delle ultime 26 ore da tutte le fonti in `data/raw/items-AAAA-MM-GG.json`
e aggiorna la memoria `data/seen.json`, così domani non torna niente di già visto.
Opzioni utili:
- `--dry-run`: prova senza aggiornare la memoria
- `--hours 72`: allarga la finestra
- `--only yt-nicksaraev gh-search`: solo alcune fonti (id da `sources.yaml`)

Alla prima esecuzione ogni fonte viene "fotografata": entra solo ciò che ha una data recente, e
dal giorno dopo ogni elemento nuovo è una novità.

```bash
uv run digest build
```

Claude (col tuo abbonamento, via `claude -p`) prende l'ultima raccolta e in due passaggi:
1. **seleziona** cosa conta e raggruppa le fonti che parlano della stessa cosa;
2. **scrive** titolo, riassunto, "perché ti serve" e badge di fact check.

Poi il codice testa ogni link e corregge i badge incoerenti. Risultato: `reports/AAAA-MM-GG.json`
più un'anteprima leggibile `reports/AAAA-MM-GG.md`. Durata ~1,5 minuti.
Opzioni: `--input file.json` (un'altra raccolta), `--model opus` (un altro modello).

`build` crea anche `reports/AAAA-MM-GG.html`: lo apri con doppio click, ed è la stessa pagina
che arriva per email.

```bash
uv run digest send
```

Invia l'ultimo report a Gmail, da te a te. Servono `GMAIL_ADDRESS` e `GMAIL_APP_PASSWORD` in
`.env`. Opzioni: `--report reports/AAAA-MM-GG.json`, `--to altro@indirizzo`.
`uv run digest render` rigenera solo l'HTML, utile se cambi la grafica in `src/digest/render.py`.

```bash
uv run digest daily
```

Il giro completo: raccolta → report → email. La memoria `data/seen.json` si aggiorna solo se
tutto riesce. `--no-send` salta l'email.

## Nel cloud (GitHub Actions)

Il workflow [.github/workflows/daily.yml](.github/workflows/daily.yml) esegue `digest daily` ogni
giorno alle **06:00 UTC** (7:00 in inverno, 8:00 in estate) sui server di GitHub, gratis, e
salva report e memoria nel repo. Se fallisce, GitHub ti manda un'email.

- **Lanciarlo a mano:** su GitHub → Actions → "Report AI quotidiano" → Run workflow, oppure:

```bash
gh workflow run daily.yml
```

- **Segreti** (GitHub → Settings → Secrets → Actions): `CLAUDE_CODE_OAUTH_TOKEN` (da
  `claude setup-token`), `APIFY_TOKEN`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `REPORT_TO`.
  Per aggiornarne uno:

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

- **Sul PC:** prima di lavorare in locale fai `git pull` per avere gli ultimi report.

Comandi delle fasi successive (non ancora implementati):

| Comando | Fase | Cosa fa |
|---------|------|---------|
| `uv run digest serve` | 5 | app locale su http://localhost:8787 |

## Struttura

```
config/          cosa seguire e come filtrare (sources.yaml, topics.yaml, voice/)
prompts/         i prompt di Claude: report, lezione, post, short, immagine
src/digest/      il codice (collectors, pipeline, server)
web/             l'app locale
scripts/         utilità
.github/         workflow del cloud (Fase 4)
reports/         un report al giorno (JSON + HTML)
outputs/         lezioni, post e script generati
data/            seen.json (cosa è già uscito) · raw/ e tmp/ restano solo in locale
```

## Personalizzare

- **Aggiungere/togliere una fonte:** `config/sources.yaml`
- **Cambiare cosa è rumore e cosa no:** `config/topics.yaml`
- **Cambiare il tono dei post:** `config/voice/federico_voice.md` (generato in Fase 7)
- **Cambiare come scrive Claude:** i file in `prompts/`
