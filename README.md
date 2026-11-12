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

## App locale

Doppio click su **`scripts\avvia-app.bat`** (oppure `uv run digest serve`): scarica da GitHub i
report del cloud e apre http://localhost:8787. Per chiuderla chiudi la finestra nera.

- **A sinistra** l'archivio di tutti i report, **al centro** il report del giorno.
- Sotto ogni notizia tre pulsanti:
  - **🎓 Genera lezione**: guida pratica passo passo, con applicazione a un cliente e
    mini-verifica;
  - **💼 Post LinkedIn**: post pronto da incollare, 2 hook alternativi, prompt per l'immagine;
  - **🎬 Script Short**: script da massimo 60 secondi in tabella (tempo, parlato, a schermo).
- Ogni contenuto impiega 1-3 minuti, si apre nel pannello a destra (**Copia** / **Rigenera**), viene
  salvato in `outputs/` e caricato su GitHub in automatico. Una volta creato, il pulsante diventa
  "Apri".
- Per il testo usa Claude Code col tuo abbonamento (modello in `config/topics.yaml` →
  `generators.model`).

- **Immagini del post:** nel pannello del post, "🖼️ Genera 2 immagini" crea 2 varianti con il
  tuo Soul su Higgsfield (~0,24 crediti, 1-2 minuti), dal "Prompt immagine" del post. Le trovi
  in `outputs/linkedin/immagini/` (JPEG) e sono caricate anche su GitHub. Soul, modello e
  formato si cambiano in `config/topics.yaml` → `generators.images`.

Consiglio: crea un collegamento a `scripts\avvia-app.bat` sul desktop o sulla barra delle
applicazioni.

## Pubblicare su LinkedIn

Nel pannello del post: **🚀 Pubblica / Programma** apre una finestra dove puoi ritoccare il testo,
scegliere l'immagine e poi:
- **Pubblica adesso** → esce subito sul tuo profilo (dopo una conferma);
- **Programma** → scegli data e ora: il post va nella coda `outputs/linkedin/coda.json` e lo
  pubblica il cloud ([.github/workflows/publish.yml](.github/workflows/publish.yml), ogni 30 minuti
  tra le 7 e le 23), anche col PC spento. I programmati si vedono (e si annullano) nella colonna a
  sinistra.

Viene pubblicato esattamente il testo confermato nella finestra. Il collegamento dura 60 giorni:
l'app avvisa e si ricollega con un click; il token per il cloud viene copiato da solo nei Secrets
di GitHub. Verifica senza pubblicare nulla:

```bash
uv run digest linkedin-check
```

Per verificare anche dal cloud: GitHub → Actions → "Pubblica post programmati" → Run workflow
con "Solo verifica" spuntato (oppure `gh workflow run publish.yml -f verifica=true`).

Prima volta: crea l'app su LinkedIn Developers (passi in [DOMANDE_APERTE.md](DOMANDE_APERTE.md)).
Servono entrambi i prodotti "Share on LinkedIn" e "Sign In with LinkedIn using OpenID Connect".

## La tua voce

Post e Short seguono [config/voice/federico_voice.md](config/voice/federico_voice.md): una guida di
stile ricavata dai tuoi post LinkedIn (hook, ritmo, frecce, emoji, CTA, cosa non fai mai). Quando
pubblichi nuovi post, aggiornala:

```bash
uv run digest voice
```

Riscarica i tuoi post con Apify (~0,02 $) e riscrive la guida. Con `--reuse` la rigenera senza
riscaricare.

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
