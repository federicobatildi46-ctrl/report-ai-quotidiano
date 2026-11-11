# Piano Operativo — Report automatico notizie e aggiornamenti AI

> Obiettivo: ogni mattina trovo **un solo report** (nell'email e nell'app locale), chiaro e
> verificato, con le notizie che contano davvero per me. Niente home di YouTube, niente feed di
> LinkedIn, niente algoritmo. Da ogni notizia posso, con un click, **imparare** (lezione),
> **creare** (post LinkedIn + immagine) o **registrare** (script Shorts).

**Per chi è:** solo per me. Sto studiando per diventare creator AI e poi aprire la mia agenzia AI
per imprenditori e professionisti (siti e SEO, social e personal brand, video e caroselli, ads,
agenti AI anche vocali, automazioni). Il report serve a **formarmi** e a **produrre contenuti**.

Stato: **Fase 0 completata** · decisioni prese l'11/11/2026 (§8) · prossimo passo: Fase 1.

---

## 1. Principi guida

1. **Costo zero come default.** Il report gira gratis su GitHub Actions; l'"intelligenza" è
   Claude Code (`claude -p`) con il mio abbonamento Pro, non l'API a consumo.
   Costi possibili, opzionali e sotto controllo: Apify (solo LinkedIn: una piccola parte dei
   19 $/mese del piano Starter che ho già) e crediti Higgsfield per le immagini.
2. **Fonti ufficiali prima di tutto.** Feed RSS/Atom e API pubbliche; scraping HTML solo dove non
   esiste un feed; Apify solo dove non c'è alternativa (LinkedIn).
3. **Meno ma meglio.** Massimo **15 minuti di lettura**. Se un giorno non succede niente di
   rilevante, la sezione dice "Nessuna novità rilevante" e basta.
4. **Fact check con livelli espliciti.** Ogni notizia porta un badge di affidabilità (vedi §5).
5. **Decido io cosa esce.** Niente si pubblica su LinkedIn senza il mio click.
6. **Tutto su GitHub.** Codice, configurazione, report, lezioni e bozze vivono nel repo privato:
   se cambio PC faccio `git clone` e ho tutto.

---

## 2. Struttura del report

**Titolo:** Report automatico notizie e aggiornamenti AI — *data*

| # | Sezione | Contenuto |
|---|---------|-----------|
| 1 | **Universo Claude** | Claude Code · Cowork · Chat (app claude.ai) · Claude Design · Ecosistema a 360° (modelli, API, Agent SDK, azienda, status) |
| 2 | **Higgsfield** | Nuove funzioni, modelli, come si applicano |
| 3 | **ElevenLabs** | Prodotto, changelog API, voci e agenti vocali, casi d'uso |
| 4 | **Dai creator che seguo** | Beggiato · Coco · Belli Contarini · Saraev — video lunghi **e Shorts** + post LinkedIn. Riassunto del *contenuto*, non del titolo |
| 5 | **GitHub: repo e skill per la mia agenzia** | Divise per area: siti e SEO · design web · social e contenuti · video editing e caroselli · agenti AI e vocali · automazioni e routine cloud |

**Ogni notizia contiene:**
- Titolo + riassunto breve (3–5 righe) + "Perché ti serve" (1 riga, legata all'agenzia o ai contenuti)
- Badge fact check + link verificato (controllato HTTP 200 al momento della generazione)
- Pulsanti nell'app: **🎓 Genera lezione** · **💼 Post LinkedIn** · **🎬 Script Shorts**

---

## 3. Architettura: cloud per il report, PC per creare

Il PC alle 9 è spento, quindi il report si genera **nel cloud, gratis, con GitHub Actions**.

```
 ┌──────────────── GitHub (repo privato) ─────────────────┐
 │ codice · config · prompt · report · lezioni · stato     │
 │                                                         │
 │  GitHub Actions — ogni giorno ~07:30 (ora italiana)     │
 │   1. RACCOLTA: RSS/Atom, HTML, YouTube, GitHub, Apify   │
 │   2. DEDUPLICA con data/seen.json (già visto?)          │
 │   3. CERVELLO: claude -p con token abbonamento Pro      │
 │      filtra rumore → classifica → riassume → fact check │
 │   4. VERIFICA LINK (HTTP 200)                           │
 │   5. COMMIT reports/AAAA-MM-GG.json + .html             │
 │   6. EMAIL a Gmail con il report                        │
 └───────────────────────────┬─────────────────────────────┘
                             │ git pull (automatico all'avvio dell'app)
                             ▼
 ┌──────────────── PC — app locale (localhost:8787) ───────┐
 │ report del giorno · archivio · lezioni salvate          │
 │ 🎓 Lezione → claude -p → outputs/lezioni/ (+ in app)    │
 │ 💼 Post → claude -p + Higgsfield (Soul) → Copia         │
 │         → poi Pubblica / Programma (Fase 7)             │
 │ 🎬 Shorts → claude -p → outputs/shorts/                 │
 │ tutto quello che creo → commit + push su GitHub         │
 └─────────────────────────────────────────────────────────┘
```

**Perché GitHub Actions e non Hostinger:**

| | GitHub Actions | Hostinger VPS | Routine cloud di Claude Code |
|---|---|---|---|
| Costo | **0 €** (2.000 min/mese gratis nei repo privati; il report ne usa ~300) | ~5–10 €/mese | 0 € (abbonamento) |
| Manutenzione | nessuna | server da aggiornare e proteggere | nessuna |
| Codice e dati | già nel repo | da sincronizzare | clona il repo |
| Affidabilità orario | buona (possibile ritardo di qualche minuto → partiamo alle 7:30) | ottima | buona |
| Limiti | — | — | numero di esecuzioni al giorno legato al piano |

Scelta: **GitHub Actions**. Le routine cloud di Claude restano un'alternativa se un domani
servisse.

**Stack:** Python + `uv` · FastAPI (app locale) · JSON nel repo per lo stato (Git lo gestisce
bene, a differenza di SQLite) · HTML/JS semplice per la UI · `claude -p` (modello Sonnet per il
report quotidiano, per non consumare i limiti del Pro) · `yt-dlp` per i sottotitoli · skill
`/watch` per i video dove i sottotitoli non bastano.

---

## 4. Fonti (verificate l'11/11/2026: 24/24 raggiungibili)

Dettaglio completo e modificabile in [config/sources.yaml](config/sources.yaml).

| Area | Fonte | Metodo |
|------|-------|--------|
| Claude Code | release GitHub + CHANGELOG.md | Atom / raw |
| Claude (tutto) | anthropic.com/news, anthropic.com/engineering, claude.com/blog | HTML (non c'è un RSS ufficiale) |
| Claude app/API | release notes (support.claude.com, docs.claude.com) | HTML |
| Claude ecosistema | anthropics/skills, Agent SDK, status.claude.com | Atom / RSS |
| Higgsfield | higgsfield.ai/blog + sitemap | HTML / sitemap |
| ElevenLabs | blog RSS + changelog API | RSS / HTML |
| YouTube | 4 canali, feed RSS ufficiale + sottotitoli | RSS + yt-dlp |
| LinkedIn | Belli Contarini, Saraev (+ i miei post per lo stile) | Apify |
| GitHub | API search per area agenzia + Trending + Hacker News + Simon Willison | API / HTML / RSS |

---

## 5. Fact check: come funziona

| Badge | Significato |
|-------|-------------|
| ✅ **Ufficiale** | Fonte primaria (blog/changelog/repo dell'azienda) |
| 🔁 **Confermata** | Riportata da ≥2 fonti indipendenti |
| ⚠️ **Da verificare** | Una sola fonte non ufficiale (es. un creator) — il report lo dice chiaro |
| ❌ **Smentita** | Contraddetta da una fonte ufficiale (mostrata solo se utile a capire) |

In più tutti i link vengono testati prima di entrare nel report: con un link rotto la notizia
viene scartata o segnalata.

---

## 6. Roadmap a fasi

| Fase | Contenuto | Risultato verificabile |
|------|-----------|------------------------|
| **0. Setup** ✅ | Struttura, config, ambiente `uv`, fonti verificate, repo GitHub | `uv run digest check-sources` → 24/24 |
| **1. Raccolta** | Collector RSS/Atom, HTML, YouTube (+ Shorts, sottotitoli), GitHub, LinkedIn via Apify | `uv run digest collect` salva gli item delle ultime 26 h |
| **2. Cervello** | Prompt di filtro/riassunto/fact check, output JSON strutturato | `uv run digest build` → `reports/AAAA-MM-GG.json` |
| **3. Report + email** | Rendering HTML del report + invio a Gmail | Ricevo l'email con il report di prova |
| **4. Cloud** | Workflow GitHub Actions alle 7:30, segreti nel repo, commit automatico dei report | Report nell'email ogni mattina con il PC spento |
| **5. App locale** | Server locale, report, archivio, `git pull` all'avvio | Apro `localhost:8787` e leggo |
| **6. Generatori** | Lezione (in app + file) · Post LinkedIn · Script Shorts (italiano, max 60 s) | Click → contenuto salvato e pushato |
| **7. Voce e immagine** | Guida di stile dai miei post (Apify) + immagini col mio Soul (Higgsfield) | Post che suonano come me + immagine con me |
| **8. LinkedIn** | Copia → poi **Pubblica** e **Programma** via API ufficiale (con conferma) | Post pubblicato/programmato dall'app |
| **9. Affinamento** | 👍/👎 su ogni notizia → il filtro impara cosa è rumore per me | Report sempre più mirato |

Ogni fase si chiude solo quando il suo risultato è stato provato davvero.

---

## 7. Rischi noti

- **YouTube può bloccare i server di GitHub** quando si scaricano i sottotitoli ("conferma di non
  essere un bot"). Piano B: un attore Apify per le trascrizioni (pochi centesimi) oppure riassunto
  da titolo + descrizione, marcato come tale.
- **LinkedIn non ha API di lettura gratuite** → Apify, a basso volume e solo post pubblici
  (lo scraping è contro i termini di LinkedIn: rischio basso ma esiste).
- **Pubblicare su LinkedIn via API** richiede un'app su LinkedIn Developers, che va associata a una
  **Pagina aziendale**: uso quella che ho già (creata per un progetto precedente). L'API
  pubblica sul mio profilo personale. La programmazione la gestiamo noi: coda nel repo + GitHub
  Actions che pubblica all'ora scelta.
- **Limiti del piano Pro:** il report usa Sonnet e un tetto di item per contenere il consumo;
  i generatori on-demand consumano di più (soprattutto la lezione).
- **Higgsfield è a crediti** e il connettore va autorizzato in Claude Code (`/mcp`).

---

## 8. Decisioni prese (11/11/2026)

| Tema | Decisione |
|------|-----------|
| Uso | Solo personale |
| Obiettivo | Formazione da creator → agenzia AI per imprenditori e professionisti |
| Esecuzione | Cloud, GitHub Actions (il PC alle 9 è spento) |
| Consegna | Email Gmail inviata a me stesso (stesso indirizzo mittente e destinatario) + app locale |
| Piano Claude | Pro |
| Lunghezza | Massimo 15 minuti di lettura |
| Creator | Video lunghi e Shorts |
| Fonti GitHub | GitHub API + Trending + Hacker News + Simon Willison |
| Apify | Token in `.env`, verificato (piano Starter, 19 $/mese) |
| Lezione | Dentro l'app **e** salvata come file |
| Immagini | Higgsfield con il mio Soul già creato. Stile visivo definito in Fase 7 partendo dalle reference che mando io |
| LinkedIn | Pubblicazione sul profilo personale; app developer associata alla Pagina aziendale che ho già. Si parte con "Copia", poi "Pubblica" e "Programma" |
| Shorts | Italiano, massimo 60 secondi |
| Portabilità | Tutto su GitHub, repo privato |

Rimane da fare insieme: vedi [DOMANDE_APERTE.md](DOMANDE_APERTE.md).
