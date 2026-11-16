# Le scelte del giorno

Qui sotto ci sono le notizie del mio report AI di oggi, già selezionate, scritte e verificate
(ognuna ha il suo livello di fact check). Scegli:

1. **`linkedin`** — la notizia migliore da trasformare in un **post LinkedIn** per la mia nicchia.
2. **`short`** — la notizia migliore per uno **YouTube Short** di reach.

## Chi sono
{{PROFILE}}

## La mia nicchia su LinkedIn (per `linkedin`)
{{AUDIENCE_LINKEDIN}}

Come scegliere il post:
- Deve parlare a un problema concreto di questa nicchia: ore perse, costi, clienti che scappano,
  lavoro ripetitivo, dipendenza da strumenti costosi. La notizia è il gancio, il problema è il post.
- Deve essere **condivisibile**: un titolare la inoltra al socio o la salva perché ci si riconosce.
- Vale di più una notizia che mostra un risultato misurabile (numeri, tempi, casi reali) o una
  novità che un piccolo studio/azienda può adottare con un sistema su misura.
- **Affidabilità**: a parità di interesse vince la notizia con fact check più forte (UFFICIALE >
  CONFERMATA > DAL PROGETTO > DA VERIFICARE). Mai una notizia SMENTITA. Se scegli una notizia
  DA VERIFICARE o DAL PROGETTO, scrivi in `caveat` cosa va controllato prima di pubblicare
  (altrimenti lascia `caveat` vuoto).
- Scarta per LinkedIn: incidenti e disservizi, release tecniche per sviluppatori, sconti e promo,
  notizie utili solo a me che studio.

Campi di `linkedin`:
- `item_id`: l'id della notizia scelta.
- `score`: da 1 a 10, quanto è adatta alla nicchia. Sii severo: se oggi nessuna notizia merita
  almeno {{MIN_SCORE}}, dai il voto vero (anche 3) e io oggi non pubblico.
- `target`: a chi parla esattamente il post, in max 12 parole (es. "titolari di studi con 10-20
  persone che rispondono a mano a clienti e fornitori").
- `pain`: il problema caldo del target a cui agganciare la notizia, 1 frase.
- `angle`: l'angolo del post in 1-2 frasi scorrevoli, max 40 parole, senza frecce: dal problema,
  alla notizia, a cosa può fare un sistema su misura. Niente promesse che la notizia non sostiene.
- `hook`: le prime 2 righe del post, max 25 parole, nel tono diretto di chi parla a un imprenditore.
- `why`: perché è la migliore di oggi per la nicchia, max 30 parole.
- `caveat`: vedi sopra.
- `alternatives`: fino a 2 altre notizie valide, con `reason` di max 15 parole.

## Il pubblico degli Shorts (per `short`)
{{AUDIENCE_SHORTS}}

Come scegliere lo Short: effetto "wow" immediato, si capisce in 3 secondi, chi guarda può provarlo
subito (meglio se gratis) e viene voglia di commentare per avere il link. Di solito sta nella
sezione "Da provare", ma può essere qualunque notizia.
Campi di `short`: `item_id`, `score` (1-10, severo come sopra), `hook` (la prima frase dello
Short, max 12 parole), `why` (max 25 parole).

## Notizie di oggi
{{ITEMS}}
