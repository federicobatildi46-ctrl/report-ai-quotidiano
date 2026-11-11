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

Comandi delle fasi successive (non ancora implementati):

| Comando | Fase | Cosa fa |
|---------|------|---------|
| `uv run digest collect` | 1 | scarica le novità delle ultime 26 ore da tutte le fonti |
| `uv run digest build` | 2 | Claude filtra, riassume e verifica → `reports/AAAA-MM-GG.json` |
| `uv run digest send` | 3 | crea l'HTML del report e lo invia a Gmail |
| `uv run digest daily` | 4 | collect + build + send: è quello che gira nel cloud ogni mattina |
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
