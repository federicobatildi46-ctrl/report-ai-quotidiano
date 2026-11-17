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

Il workflow [.github/workflows/daily.yml](.github/workflows/daily.yml) esegue `digest daily` sui
server di GitHub, gratis, e salva report e memoria nel repo. Se fallisce, GitHub ti manda un'email.

**Perché l'orario non dipende più da GitHub.** L'orologio interno di GitHub (`schedule`) su questo
repo parte con 5-8 ore di ritardo: dal 13 al 16/11/2026 l'avvio delle 04:23 UTC è partito tra le
11:37 e le 12:57, e l'email arrivava dopo le 13. L'avvio "a comando" invece è immediato. Quindi il
workflow viene svegliato da più orologi indipendenti; il primo che arriva fa il report, gli altri
si fermano in pochi secondi perché il report di oggi esiste già:
1. **Routine Claude nel cloud** (06:30 e 07:30 italiane d'inverno): fa un push su un ramo
   `claude/...` con un file in `sveglia/`, e il workflow parte subito. Funziona a PC spento.
   Si gestisce da https://claude.ai/code/routines. *Richiede che Claude abbia accesso al repo
   (GitHub collegato su claude.ai): senza, questa sveglia non esiste.*
2. **L'app sul PC**: ogni 10 minuti, dalle 05:45 italiane, se il report manca lo richiede
   (massimo 4 volte al giorno, a 50 minuti di distanza).
3. **Crono di GitHub della sera prima** (20:23–00:23 UTC): con il ritardo abituale partono tra le
   05 e le 09 italiane; quelli che partono fuori dalla finestra 03:45–20:00 UTC si fermano.
4. I crono del mattino restano, nel caso GitHub torni puntuale.

La raccolta parte sempre dall'ultimo report riuscito (fino a 72 ore): un ritardo non fa perdere
notizie. Se Claude ha finito la quota dell'abbonamento (limite delle 5 ore) il report fallisce
senza toccare la memoria e il tentativo successivo riparte da capo.

Prova nel cloud senza inviare né salvare nulla (il report si scarica dalla pagina dell'esecuzione):

```bash
gh workflow run daily.yml -f prova=true
```

Per rifarlo a mano anche se esiste già: `gh workflow run daily.yml -f forza=true`.

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

Indirizzo fisso: **http://localhost:8787** (mettilo nei segnalibri).

- **Sempre accesa:** all'accesso a Windows parte in silenzio un "guardiano"
  (`scripts\avvio-nascosto.vbs`): ogni 30 secondi controlla l'app e, se è spenta o bloccata, la
  riaccende da solo (in ~10-20 secondi). Ne gira uno solo alla volta. Diario in
  `data\tmp\guardiano.log`. Il collegamento in Esecuzione automatica si attiva una volta sola con:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\avvio-automatico.ps1
```

  (per toglierlo: stesso comando con `-Rimuovi`). Log in `data\tmp\app.log`.
- In alternativa doppio click su **`scripts\avvia-app.bat`**: se l'app è già accesa apre solo il
  browser, altrimenti accende il guardiano e apre il browser appena l'app è pronta.
- Per fermare tutto: chiudi `wscript.exe` e `python.exe` (Report AI) da Gestione attività.

- **A sinistra** gli ultimi 7 report; i più vecchi sono nello **Storico** (chiuso, diviso per mese)
  sotto di loro. Tutti i report restano anche su GitHub, nella cartella `reports/` (~25 MB l'anno).
  **Al centro** il report del giorno. In alto la
  barra delle sezioni (salto rapido, sezione attiva evidenziata) e la ricerca nel testo (tasto `/`).
- Dall'email, "Apri nell'app →" porta alla stessa notizia nell'app
  (indirizzo `http://localhost:8787/#AAAA-MM-GG/id-notizia`).
- Se il report di oggi non è ancora arrivato, o ne arriva uno nuovo mentre l'app è aperta,
  compare un avviso in alto.
- Sotto ogni notizia tre pulsanti:
  - **🎓 Genera lezione**: guida pratica passo passo, con applicazione a un cliente e
    mini-verifica;
  - **💼 Post LinkedIn**: post pronto da incollare, 2 hook alternativi, prompt per l'immagine.
    Dentro il post c'è un blocco breve "quanto ti costa non farlo": il target, 2-3 pain point con
    stime di ore o costi persi, la soluzione con il guadagno stimato e una riga di disclaimer.
    Claude fa 2-4 ricerche online per ancorare le stime a dati veri (fonti nelle Note);
  - **🎬 Script Short**: script da massimo 60 secondi in tabella (tempo, parlato, a schermo).
    Per le notizie di "Da provare" usa il formato strumento: hook wow, cos'è, demo, come
    provarlo, "Commenta PAROLA e ti mando il link", più il messaggio pronto per chi commenta.
- Ogni contenuto impiega 1-3 minuti, si apre nel pannello a destra (**Copia** / **Rigenera**), viene
  salvato in `outputs/` e caricato su GitHub in automatico. Una volta creato, il pulsante diventa
  "Apri".
- Per il testo usa Claude Code col tuo abbonamento (modello in `config/topics.yaml` →
  `generators.model`).

- **Carosello (6 slide + PDF):** nel pannello del post, "🎠 Genera carosello" crea copertina con
  il soggetto del tema, 3 slide di concetti, la slide "quanto ti costa non farlo" (pain point con
  stime, soluzione, guadagno stimato e disclaimer) e la slide finale con CTA e "Segui Federico", nello
  stile dei riferimenti (blu elettrico e grigio carta, titoli Anton, corsivo, pillole, riquadro
  giallo). Higgsfield genera solo l'immagine (~3 crediti), i testi li impagina il codice con font
  veri: niente parole storpiate. Ogni carosello usa una "famiglia" visiva diversa dai precedenti
  (statue, oggetti retrò, mani, astronauti, collage surreali, animali…).
  - **✏️ Modifica slide**: cambi i testi di ogni slide e reimpagina (gratis, stessa immagine);
  - **🖼️ Nuova immagine**: stessi testi, soggetto nuovo (~3 crediti);
  - **🔄 Rigenera tutto**: testi e immagine nuovi.
  File in `outputs/linkedin/caroselli/<notizia>/` (slide JPEG, `carosello.pdf`), anche su GitHub.
- **💬 Chiedi alla lezione:** sotto ogni lezione c'è una chat. Fai domande, chiedi esempi o come
  applicarla a te o a un cliente (descrivilo: settore, dimensioni, obiettivo). Claude conosce la
  lezione, le fonti e i tuoi obiettivi, ricorda gli ultimi scambi e distingue i fatti dai suoi
  suggerimenti. Risposta in 10-30 secondi; la conversazione è salvata con la lezione
  (`outputs/lezioni/<notizia>.chat.json`, anche su GitHub). "Svuota chat" per ricominciare.
- **✏️ Modifica testo** (post): correggi il testo del post e salvi; resta quello per la pubblicazione.

Consiglio: crea un collegamento a `scripts\avvia-app.bat` sul desktop o sulla barra delle
applicazioni.

## Controlli di qualità e fact check

Prima di partire, ogni report passa questi controlli automatici (riassunti in fondo a email e app):
- **Scrittura verificata**: se Claude risponde a metà o con testo segnaposto, la scrittura viene
  rifatta fino a 3 volte; se non riesce, il report NON parte (meglio niente che un report vuoto).
- **Link**: ogni link viene aperto; le notizie con link rotto vengono scartate. LinkedIn, X e
  Product Hunt non si fanno controllare dai robot: restano, segnati come non verificabili.
- **Badge calcolato dal codice**, non da Claude: ✅ se c'è una fonte ufficiale (sito dell'azienda
  o repo GitHub della sua organizzazione, elenco in `config/sources.yaml` → `official_domains`);
  🔁 se parlano almeno 2 autori diversi (video + post dello stesso creator = 1 fonte);
  📦 se l'unica fonte è il progetto stesso; ⚠️ negli altri casi.
- **Repo verificate su GitHub**: stelle, date, licenza e stato "archiviata" vengono letti al
  momento dall'API di GitHub e sostituiscono i numeri riportati da creator e aggregatori (★).

## Da pubblicare oggi: il post e lo Short del giorno

Tra le notizie già verificate, Claude sceglie:
- **💼 il post LinkedIn del giorno** per la tua nicchia (definita in `config/topics.yaml` →
  `audience.linkedin`: liberi professionisti e titolari di attività da 10-20 persone): voto di
  adattamento, a chi parla, il problema, l'angolo, l'hook e due alternative. A parità di interesse
  vince la notizia con fact check più forte; sotto 6/10 non propone niente ("oggi non pubblicare").
- **🎬 lo Short del giorno** per il pubblico degli Shorts (`audience.shorts`).

In email e app c'è il riquadro "Da pubblicare oggi"; dall'app "Genera il post" scrive il post
partendo dall'angolo scelto. Decidi sempre tu: niente viene pubblicato da solo.
Per cambiare criteri: `prompts/picks.md`.

## La sezione "Da provare" (idee per gli Shorts)

Repo, skill e plugin per Claude, connettori MCP e app AI con effetto wow, che chiunque può provare
subito: pensata per gli Shorts di reach, dove il pubblico non è tecnico. Fonti:
- **ricerca web di Claude** ogni mattina (`claude -p` con WebSearch, ~1 minuto, prompt in
  `prompts/web_research.md`): solo cose virali negli ultimi giorni, con link ufficiale ed evidenza;
- **Product Hunt AI**, **Show HN** (≥80 punti) e **GitHub Trending**, quando la repo è adatta a
  tutti. (Reddit è stato tolto: blocca le richieste dai server del cloud.)

Ogni notizia ha "Cosa fa / Come si prova / Costo" e un **🎬 Idea Short**: la prima frase pronta.

## Insegnare al filtro cosa ti serve (👍/👎)

Sotto ogni notizia dell'app: **👍** se ti è servita, **👎** se no (poi, se vuoi, il motivo: Rumore,
Già saputo, Non mi serve, Troppo tecnico). Ricliccare lo stesso voto lo toglie.

- I voti finiscono in `data/feedback.json` e vanno su GitHub da soli (30 secondi dopo l'ultimo click).
- Ogni mattina il caporedattore vede i tuoi ultimi voti come esempi + il punteggio di ogni fonte.
- Ogni 10 voti nuovi Claude li riassume in **[config/preferenze.md](config/preferenze.md)**: regole
  leggibili che puoi correggere a mano (le tue correzioni contano più dei voti). Per rigenerarle
  subito: `uv run digest preferences`.

## Pubblicare su LinkedIn

Nel pannello del post: **🚀 Pubblica / Programma** apre una finestra dove puoi ritoccare il testo,
scegliere l'allegato (il **carosello PDF** è selezionato di default se esiste: su LinkedIn appare
come documento da sfogliare) e poi:
- **Pubblica adesso** → esce subito sul tuo profilo (dopo una conferma);
- **Programma** → scegli data e ora: il post va nella coda `outputs/linkedin/coda.json` e lo
  pubblica, all'orario scelto:
  1. **l'app sul PC**, se è accesa (controlla la coda ogni 30 secondi);
  2. **a PC spento, il cloud**: due routine Claude (ai :00 e ai :30, 06:00-22:30 italiane
     d'inverno) lanciano `scripts/sveglia-pubblica.sh`, che sveglia
     [.github/workflows/publish.yml](.github/workflows/publish.yml) solo se c'è un post in uscita
     entro 45 minuti; il workflow aspetta l'orario + 2 minuti (precedenza al PC) e pubblica.
     Routine: https://claude.ai/code/routines.
  Un post rimasto indietro di oltre 3 ore non esce più ("⏰ non uscito, riprogrammalo"): niente
  pubblicazioni a sorpresa o doppioni. I programmati si vedono (e si annullano) a sinistra.

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
