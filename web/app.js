// App locale del Report AI: archivio, report e generatori (lezione, post, short).
marked.setOptions({ breaks: true });   // un "a capo" nel testo = a capo nella pagina (post LinkedIn)
const KINDS = {
  lezione: { icon: "🎓", gen: "Genera lezione", open: "Apri lezione", label: "Lezione" },
  post: { icon: "💼", gen: "Post LinkedIn", open: "Apri post", label: "Post LinkedIn" },
  short: { icon: "🎬", gen: "Script Short", open: "Apri short", label: "Script Shorts" },
};
const BADGES = { ufficiale: "✅ Ufficiale", confermata: "🔁 Confermata", da_verificare: "⚠️ Da verificare",
  smentita: "❌ Smentita", dal_repo: "📦 Dal README" };
const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
  "settembre", "ottobre", "novembre", "dicembre"];

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { date: null, report: null, drawer: null };

function dataIt(iso, withDay = true) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const s = `${d} ${MESI[m - 1]} ${y}`;
  return withDay ? `${GIORNI[dt.getDay()][0].toUpperCase()}${GIORNI[dt.getDay()].slice(1)} ${s}` : s;
}

async function api(path, opts) {
  const r = await fetch(path, { cache: "no-store", ...opts });   // sempre dati freschi
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// ---------- archivio ----------
async function loadArchive() {
  const list = await api("/api/reports");
  $("#archive").innerHTML = list.map((r) =>
    `<a href="#${r.date}" data-date="${r.date}"><div class="d">${dataIt(r.date, false)}</div>
     <div class="m">${r.stories} notizie · ${r.minutes} min</div></a>`).join("") || '<p class="muted small">Nessun report.</p>';
  return list;
}

function markActive() {
  document.querySelectorAll("#archive a").forEach((a) => a.classList.toggle("active", a.dataset.date === state.date));
}

// ---------- report ----------
async function showReport(date) {
  state.date = date;
  markActive();
  const r = await api(`/api/reports/${date}`);
  state.report = r;
  const s = r.stats;
  const sections = r.sections.map((sec) => renderSection(sec, r.outputs)).join("");
  $("#report").innerHTML = `
    <div class="date">${dataIt(r.date)}</div>
    <h1>${esc(r.title)}</h1>
    <div class="stats">${s.stories} notizie · circa ${r.reading_minutes} minuti · ${s.collected} elementi raccolti, ${s.discarded} scartati come rumore</div>
    ${r.in_breve.length ? `<div class="breve"><div class="eyebrow">In breve</div><ul>${r.in_breve.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    ${sections}`;
}

function renderSection(sec, outputs) {
  const head = `<h2>${esc(sec.title)} <small>· ${sec.items.length}</small></h2>`;
  if (!sec.items.length) return `<section class="sec" style="--sec:var(--${sec.id})">${head}<p class="empty">Nessuna novità rilevante.</p></section>`;
  const groups = new Map();
  sec.items.forEach((it) => { const k = it.subsection || ""; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(it); });
  let body = "";
  for (const [, items] of groups) {
    const label = items[0].subsection_label;
    if (label && groups.size > 1) body += `<div class="eyebrow sub">${esc(label)}</div>`;
    body += items.map((it) => renderItem(it, outputs[it.id] || [])).join("");
  }
  return `<section class="sec" style="--sec:var(--${sec.id})">${head}${body}</section>`;
}

function renderItem(it, done) {
  const points = it.key_points?.length ? `<ul class="points">${it.key_points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
  const sources = it.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(" · ");
  const buttons = Object.entries(KINDS).map(([k, v]) => {
    const has = done.includes(k);
    return `<button data-item="${it.id}" data-kind="${k}" class="${has ? "done" : ""}">${v.icon} ${has ? v.open : v.gen}</button>`;
  }).join("");
  return `<div class="item" id="n-${it.id}">
    <h3><a href="${esc(it.primary_url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
    <div><span class="badge b-${it.badge}">${BADGES[it.badge] || it.badge}</span><span class="note">${esc(it.badge_note)}</span></div>
    <p class="summary">${esc(it.summary)}</p>${points}
    <div class="why"><b>Perché ti serve:</b> ${esc(it.why)}</div>
    ${it.short_hook ? `<div class="why hook"><b>🎬 Idea Short:</b> «${esc(it.short_hook)}»</div>` : ""}
    <div class="sources">Fonti: ${sources}</div>
    <div class="actions">${buttons}${renderVote(it.id)}</div></div>`;
}

// ---------- voti 👍/👎: il filtro impara cosa ti serve ----------
const REASONS = ["Rumore", "Già saputo", "Non mi serve", "Troppo tecnico"];

function renderVote(id) {
  const v = state.report?.feedback?.[id] || {};
  const reasons = v.vote === -1 ? `<span class="reasons">${REASONS.map((r) =>
    `<button class="chip ${v.reason === r ? "on" : ""}" data-reason="${r}" data-vote-item="${id}">${r}</button>`).join("")}</span>` : "";
  return `<span class="vote" data-vote-for="${id}">
    <button class="vote-btn ${v.vote === 1 ? "on" : ""}" data-vote="1" data-vote-item="${id}" title="Mi è servita">👍</button>
    <button class="vote-btn ${v.vote === -1 ? "on" : ""}" data-vote="-1" data-vote-item="${id}" title="Non mi serviva">👎</button>${reasons}</span>`;
}

async function sendVote(id, vote, reason = null) {
  const cur = state.report.feedback[id]?.vote;
  const value = reason ? -1 : (cur === vote ? 0 : vote);   // ri-cliccare lo stesso voto lo toglie
  await api("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date: state.date, item_id: id, vote: value, reason }) });
  if (value === 0) delete state.report.feedback[id];
  else state.report.feedback[id] = { vote: value, reason };
  document.querySelector(`[data-vote-for="${id}"]`).outerHTML = renderVote(id);
}

document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-vote-item]");
  if (!b) return;
  e.stopPropagation();
  if (b.dataset.reason) sendVote(b.dataset.voteItem, -1, b.dataset.reason);
  else sendVote(b.dataset.voteItem, Number(b.dataset.vote));
}, true);

// ---------- generatori ----------
async function onAction(btn, force = false) {
  const item = btn.dataset.item, kind = btn.dataset.kind;
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = `⏳ Sto scrivendo… (1-3 min)`;
  try {
    let res = await api("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: state.date, item_id: item, kind, force }) });
    const jobId = res.job_id;   // la risposta dei controlli successivi non contiene più job_id
    while (res.status === "in corso") {
      await new Promise((r) => setTimeout(r, 2500));
      res = await api(`/api/jobs/${jobId}`);
    }
    if (res.status === "errore") throw new Error(res.error);
    btn.classList.add("done");
    btn.textContent = `${KINDS[kind].icon} ${KINDS[kind].open}`;
    await openOutput(kind, item, res.git);
  } catch (e) {
    btn.textContent = original;
    alert(`Generazione non riuscita: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

async function openOutput(kind, item, gitNote) {
  const out = await api(`/api/outputs/${kind}/${item}`);
  state.drawer = { kind, item, markdown: out.markdown };
  $("#drawer-kind").textContent = KINDS[kind].label;
  $("#drawer-title").textContent = out.meta.notizia || "";
  $("#drawer-info").textContent = `${out.path}${gitNote ? " · " + gitNote : ""}`;
  $("#drawer-copy").textContent = kind === "post" ? "Copia il post" : "Copia tutto";
  $("#drawer-body").innerHTML = DOMPurify.sanitize(marked.parse(out.markdown));
  const isPost = kind === "post";
  $("#drawer-carousel").hidden = !isPost;
  $("#drawer-publish").hidden = !isPost;
  $("#drawer-edit").hidden = !isPost;
  if (isPost) renderCarousel(await api(`/api/carousel/${item}`));
  const isLesson = kind === "lezione";
  $("#lesson-chat").hidden = !isLesson;
  $("#drawer-chat").hidden = !isLesson;
  if (isLesson) await loadChat(item);
  $("#drawer").hidden = false;
  document.querySelector(".drawer-scroll").scrollTop = 0;
}

// ---------- chat sotto la lezione ----------
const SUGGESTIONS = ["Come lo applico a un mio cliente?", "Fammi un esempio pratico passo passo",
  "Quali errori devo evitare?", "Come ne faccio un post o uno Short?", "Spiegamelo più semplice"];

function renderChat(messages, pending = null) {
  const log = $("#chat-log");
  log.innerHTML = messages.map((m) => m.role === "user"
    ? `<div class="msg user">${esc(m.text)}</div>`
    : `<div class="msg assistant">${DOMPurify.sanitize(marked.parse(m.text))}</div>`).join("") +
    (pending ? `<div class="msg user">${esc(pending)}</div><div class="msg assistant thinking">Sto pensando… (10-30 secondi)</div>` : "");
  log.scrollTop = log.scrollHeight;
  $("#chat-suggest").innerHTML = SUGGESTIONS.map((s) => `<button class="chip" data-suggest="${esc(s)}">${esc(s)}</button>`).join("");
  $("#chat-clear").hidden = !messages.length;
}

async function loadChat(item) {
  const { messages } = await api(`/api/chat/${item}`);
  state.chat = messages;
  renderChat(messages);
  $("#chat-panel").hidden = !messages.length;   // se c'è già una conversazione resta aperta
  $("#chat-status").textContent = messages.length ? `${messages.length / 2} domande salvate` : "";
}

function openChat() {
  $("#chat-panel").hidden = false;
  $("#lesson-chat").scrollIntoView({ behavior: "smooth", block: "start" });
  setTimeout(() => $("#chat-text").focus(), 300);
}

async function sendChat(text) {
  const q = (text ?? $("#chat-text").value).trim();
  if (!q || $("#chat-send").disabled) return;
  $("#chat-text").value = "";
  $("#chat-send").disabled = true;
  renderChat(state.chat, q);
  try {
    const res = await api(`/api/chat/${state.drawer.item}`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: q }) });
    state.chat = res.messages;
    renderChat(state.chat);
    $("#chat-status").textContent = `Risposta in ${Math.round(res.secs || 0)} s · salvata con la lezione`;
  } catch (e) {
    renderChat(state.chat);
    $("#chat-text").value = q;
    $("#chat-status").textContent = `Non riuscito: ${e.message}`;
  } finally {
    $("#chat-send").disabled = false;
  }
}

$("#chat-toggle").onclick = () => { $("#chat-panel").hidden ? openChat() : ($("#chat-panel").hidden = true); };
$("#drawer-chat").onclick = openChat;
$("#chat-send").onclick = () => sendChat();
$("#chat-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});
$("#chat-suggest").addEventListener("click", (e) => { const s = e.target.dataset?.suggest; if (s) sendChat(s); });
$("#chat-clear").onclick = async () => {
  if (!confirm("Svuotare la chat di questa lezione?")) return;
  state.chat = (await api(`/api/chat/${state.drawer.item}`, { method: "DELETE" })).messages;
  renderChat(state.chat);
  $("#chat-status").textContent = "";
};

// ---------- carosello ----------
async function pollJob(res, ms = 3000) {
  const jobId = res.job_id;
  while (res.status === "in corso") {
    await new Promise((r) => setTimeout(r, ms));
    res = await api(`/api/jobs/${jobId}`);
  }
  if (res.status === "errore") throw new Error(res.error);
  return res;
}

function renderCarousel(c, note = "") {
  state.carousel = c;
  const has = !!c.exists;
  $("#car-gen").textContent = has ? "🔄 Rigenera tutto" : "🎠 Genera carosello";
  $("#car-gen").title = has ? "Testi e immagine nuovi (~3 crediti)" : "Testi + immagine dal post (~3 crediti, 1-2 minuti)";
  $("#car-img").textContent = "🖼️ Nuova immagine";
  $("#car-edit").hidden = $("#car-img").hidden = $("#car-pdf").hidden = !has;
  if (has) $("#car-pdf").href = c.pdf;
  $("#car-strip").innerHTML = has ? c.slides.map((src, i) =>
    `<a href="${src}" target="_blank" rel="noopener" title="Slide ${i + 1}: apri in grande"><img src="${src}" alt="Slide ${i + 1}" loading="lazy"></a>`).join("") : "";
  $("#car-info").textContent = note || (has
    ? "Clicca una slide per vederla in grande. Il PDF è quello che va su LinkedIn."
    : "Copertina con il soggetto del tema, 3 slide di concetti, il costo del non farlo e la CTA finale, nel tuo stile.");
}

async function carouselJob(btn, url, label) {
  const d = state.drawer; if (!d) return;
  const buttons = ["#car-gen", "#car-edit", "#car-img"].map((s) => $(s));
  buttons.forEach((b) => (b.disabled = true));
  const original = btn.textContent;
  btn.textContent = label;
  try {
    const res = await pollJob(await api(url, { method: "POST" }));
    renderCarousel(await api(`/api/carousel/${d.item}`), res.git ? `Fatto · ${res.git}` : "Fatto");
  } catch (e) {
    btn.textContent = original;
    $("#car-info").textContent = `Non riuscito: ${e.message}`;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

$("#car-gen").onclick = () => {
  const d = state.drawer;
  if (state.carousel?.exists && !confirm("Rigenerare testi e immagine? Le modifiche fatte a mano andranno perse.")) return;
  carouselJob($("#car-gen"), `/api/carousel/${d.item}`, "⏳ Testi e immagine in arrivo… (1-2 min)");
};
$("#car-img").onclick = () => {
  const d = state.drawer;
  carouselJob($("#car-img"), `/api/carousel/${d.item}?nuova_immagine=true`, "⏳ Nuova immagine… (1 min)");
};

function field(label, name, value, multiline = false) {
  const v = esc(value ?? "");
  return `<label>${label}</label>` + (multiline
    ? `<textarea name="${name}" rows="${Math.max(2, (value || "").split("\n").length)}">${v}</textarea>`
    : `<input name="${name}" value="${v}">`);
}

$("#car-edit").onclick = () => {
  const p = state.carousel.plan;
  const s = p.slides.map((sl, i) => `<fieldset><legend>Slide ${i + 2}</legend>
    ${field("Titolo", `s${i}.title`, sl.title)}
    ${field("Righe (una per riga, max 4)", `s${i}.lines`, (sl.lines || []).join("\n"), true)}
    ${field("Frase in giallo", `s${i}.highlight`, sl.highlight)}
    ${field("Pillole (separate da virgola)", `s${i}.tags`, (sl.tags || []).join(", "))}</fieldset>`).join("");
  $("#car-form").innerHTML = `<fieldset><legend>Copertina</legend>
      ${field("Sopratitolo", "cover.kicker", p.cover.kicker)}
      ${field("Titolone (1-2 parole)", "cover.title_big", p.cover.title_big)}
      ${field("Resto del titolo", "cover.title_rest", p.cover.title_rest)}
      ${field("Corsivo", "cover.script_accent", p.cover.script_accent)}
      ${field("Barra di ricerca", "cover.search_bar", p.cover.search_bar)}</fieldset>
    ${s}
    ${p.pain ? `<fieldset><legend>Slide ${p.slides.length + 2} · Quanto ti costa non farlo</legend>
      ${field("Target (sopratitolo)", "pain.kicker", p.pain.kicker)}
      ${field("Titolo", "pain.title", p.pain.title)}
      ${field("Pain point: una riga per punto, «stima | problema» (max 3)", "pain.points",
        (p.pain.points || []).map((x) => `${x.figure} | ${x.text}`).join("\n"), true)}
      ${field("Soluzione", "pain.solution", p.pain.solution)}
      ${field("Guadagno stimato (in giallo)", "pain.gain", p.pain.gain)}
      ${field("Spiegazione del guadagno", "pain.gain_text", p.pain.gain_text)}
      ${field("Disclaimer", "pain.note", p.pain.note)}</fieldset>` : ""}
    <fieldset><legend>Slide finale (CTA)</legend>
      ${field("Titolo", "cta.title", p.cta.title)}
      ${field("Testo", "cta.text", p.cta.text, true)}
      ${field("Parola chiave da commentare", "cta.keyword", p.cta.keyword)}</fieldset>`;
  $("#car-msg").textContent = "Le modifiche ai testi sono gratis: l'immagine resta la stessa.";
  $("#car-msg").className = "small muted";
  $("#car-dialog").showModal();
};

$("#car-save").onclick = async () => {
  const val = (n) => $("#car-form").querySelector(`[name="${n}"]`)?.value.trim() ?? "";
  const p = state.carousel.plan;
  const edited = {
    cover: Object.fromEntries(["kicker", "title_big", "title_rest", "script_accent", "search_bar"].map((k) => [k, val(`cover.${k}`)])),
    slides: p.slides.map((_, i) => ({ title: val(`s${i}.title`), lines: val(`s${i}.lines`).split("\n"),
      highlight: val(`s${i}.highlight`), tags: val(`s${i}.tags`).split(",").map((t) => t.trim()) })),
    cta: { title: val("cta.title"), text: val("cta.text"), keyword: val("cta.keyword") },
  };
  if (p.pain) {
    edited.pain = Object.fromEntries(["kicker", "title", "solution", "gain", "gain_text", "note"].map((k) => [k, val(`pain.${k}`)]));
    edited.pain.points = val("pain.points").split("\n").filter((l) => l.trim()).map((l) => {
      const [figure, ...rest] = l.split("|");
      return rest.length ? { figure: figure.trim(), text: rest.join("|").trim() } : { figure: "", text: figure.trim() };
    });
  }
  $("#car-save").disabled = true;
  $("#car-msg").textContent = "⏳ Reimpagino…";
  try {
    const c = await api(`/api/carousel/${state.drawer.item}`, { method: "PUT",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(edited) });
    renderCarousel(c, "Slide aggiornate · salvate su GitHub");
    $("#car-dialog").close();
  } catch (e) {
    $("#car-msg").textContent = `Non salvato: ${e.message}`; $("#car-msg").className = "small err";
  } finally {
    $("#car-save").disabled = false;
  }
};

// ---------- modifica del testo del post ----------
$("#drawer-edit").onclick = () => {
  const d = state.drawer; if (!d) return;
  $("#post-dlg-title").textContent = $("#drawer-title").textContent;
  $("#post-dlg-text").value = postText(d.markdown);
  $("#post-dlg-count").textContent = `${$("#post-dlg-text").value.length} / 3000 caratteri`;
  $("#post-dialog").showModal();
};
$("#post-dlg-text").addEventListener("input", () => {
  const n = $("#post-dlg-text").value.length;
  $("#post-dlg-count").textContent = `${n} / 3000 caratteri${n > 3000 ? " — troppo lungo per LinkedIn" : ""}`;
});
$("#post-dlg-save").onclick = async () => {
  const d = state.drawer;
  try {
    await api(`/api/outputs/post/${d.item}`, { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: $("#post-dlg-text").value }) });
    $("#post-dialog").close();
    await openOutput("post", d.item, "modificato e salvato su GitHub");
  } catch (e) {
    $("#post-dlg-count").textContent = `Non salvato: ${e.message}`;
  }
};

function postText(md) {
  // solo la sezione "## Post": è il testo da incollare su LinkedIn
  const m = md.match(/##\s*Post\s*\n([\s\S]*?)(?=\n##\s|$)/);
  return (m ? m[1] : md).trim();
}

// ---------- eventi ----------
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".actions button[data-kind]");
  if (!btn || btn.disabled) return;
  if (btn.classList.contains("done")) openOutput(btn.dataset.kind, btn.dataset.item);
  else onAction(btn);
});
$("#drawer-close").onclick = () => { $("#drawer").hidden = true; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#drawer").hidden = true; });
$("#drawer-copy").onclick = async () => {
  const d = state.drawer; if (!d) return;
  await navigator.clipboard.writeText(d.kind === "post" ? postText(d.markdown) : d.markdown);
  $("#drawer-copy").textContent = "Copiato ✓";
};
$("#drawer-regen").onclick = () => {
  const d = state.drawer; if (!d) return;
  const btn = document.querySelector(`.actions button[data-item="${d.item}"][data-kind="${d.kind}"]`);
  $("#drawer").hidden = true;
  if (btn && confirm("Rigenerare? Il testo attuale verrà sostituito.")) onAction(btn, true);
};
$("#sync-btn").onclick = async () => { $("#sync-status").textContent = "Sincronizzazione…"; await api("/api/sync", { method: "POST" }); await init(); };
window.addEventListener("hashchange", () => { const d = location.hash.slice(1); if (d && d !== state.date) showReport(d); });

// ---------- LinkedIn: collegamento, pubblicazione, programmazione ----------
const fmtWhen = (iso) => new Date(iso).toLocaleString("it-IT", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
state.li = { connected: false };

async function loadLinkedIn() {
  const s = await api("/api/linkedin/status");
  state.li = s;
  let html;
  if (!s.configured) html = "Da configurare: Client ID e Secret in <code>.env</code>, poi riavvia l'app.";
  else if (!s.connected) html = `<a href="/linkedin/login">🔗 Collega LinkedIn</a>${s.expires_at ? " (collegamento scaduto)" : ""}`;
  else html = `✅ ${esc(s.name || "Collegato")} · scade tra ${s.days_left} giorni` +
    (s.days_left < 10 ? ` · <a href="/linkedin/login">ricollega</a>` : "") +
    `<br>${s.secrets_synced ? "Programmazione nel cloud attiva" : "⚠️ Token non ancora copiato su GitHub (ricollega)"}`;
  $("#li-status").innerHTML = html;

  const q = await api("/api/coda");
  const upcoming = q.filter((e) => e.status === "programmato");
  const recent = q.filter((e) => e.status !== "programmato" && e.status !== "annullato").slice(0, 3);
  $("#coda").innerHTML = [
    ...upcoming.map((e) => `<div class="q"><div>${esc(e.title.slice(0, 60))}</div>
      <div class="q-when">📅 ${fmtWhen(e.publish_at)} · <button class="link" data-cancel="${e.id}">Annulla</button></div></div>`),
    ...recent.map((e) => `<div class="q"><div>${esc(e.title.slice(0, 60))}</div><div class="q-when">${e.status === "pubblicato"
      ? `✅ ${fmtWhen(e.published_at || e.publish_at)} · <a href="${esc(e.url)}" target="_blank" rel="noopener">apri</a>`
      : `❌ errore: ${esc((e.error || "").slice(0, 80))}`}</div></div>`),
  ].join("") || '<span class="muted">Nessun post programmato.</span>';
}

$("#coda").addEventListener("click", async (e) => {
  const id = e.target.dataset?.cancel; if (!id) return;
  if (!confirm("Annullare questo post programmato? Non verrà pubblicato.")) return;
  await api(`/api/coda/${id}`, { method: "DELETE" });
  await loadLinkedIn();
});

async function openPublish() {
  const d = state.drawer; if (!d) return;
  $("#pub-title").textContent = $("#drawer-title").textContent;
  $("#pub-text").value = postText(d.markdown);
  updateCount();
  // allegato: il carosello (PDF) se c'è, altrimenti eventuali immagini singole o niente
  const car = await api(`/api/carousel/${d.item}`);
  const imgs = (await api(`/api/images/${d.item}`)).images;
  $("#pub-images").innerHTML =
    (car.exists ? `<label class="car-choice"><input type="radio" name="pubimg" value="__carosello__" checked><img src="${car.slides[0]}" alt=""><span>Carosello PDF</span></label>` : "") +
    imgs.map((src) => `<label><input type="radio" name="pubimg" value="${src.split("/").pop()}"><img src="${src}" alt=""></label>`).join("") +
    `<label><input type="radio" name="pubimg" value="" ${car.exists ? "" : "checked"}><span class="noimg">nessuno</span></label>`;
  const t = new Date(); t.setDate(t.getDate() + 1); t.setHours(8, 30, 0, 0);
  $("#pub-at").value = new Date(t.getTime() - t.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const ready = state.li.connected;
  $("#pub-now").disabled = $("#pub-schedule").disabled = !ready;
  setMsg(ready ? "" : "Prima collega LinkedIn (colonna a sinistra).", !ready);
  $("#publish-dialog").showModal();
}

function updateCount() {
  const n = $("#pub-text").value.length;
  $("#pub-count").textContent = `${n} / 3000 caratteri${n > 3000 ? " — troppo lungo per LinkedIn" : ""}`;
}
function setMsg(text, isErr = false) { $("#pub-msg").textContent = text; $("#pub-msg").className = "small " + (isErr ? "err" : "ok"); }
function pubPayload() {
  const choice = document.querySelector('input[name="pubimg"]:checked')?.value || "";
  return { item_id: state.drawer.item, title: $("#pub-title").textContent, text: $("#pub-text").value.trim(),
    carousel: choice === "__carosello__", image: choice && choice !== "__carosello__" ? choice : null };
}

$("#pub-text").addEventListener("input", updateCount);
$("#drawer-publish").onclick = openPublish;

$("#pub-schedule").onclick = async () => {
  const when = new Date($("#pub-at").value);
  if (isNaN(when) || when <= new Date()) return setMsg("Scegli una data e un'ora nel futuro.", true);
  if ($("#pub-text").value.length > 3000) return setMsg("Il testo supera i 3000 caratteri.", true);
  if (!confirm(`Programmare il post per ${fmtWhen(when.toISOString())}?\nVerrà pubblicato in automatico sul tuo profilo LinkedIn.`)) return;
  try {
    const r = await api("/api/coda", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...pubPayload(), publish_at: when.toISOString() }) });
    setMsg(`📅 Programmato per ${fmtWhen(r.publish_at)} · ${r.git}`);
    await loadLinkedIn();
  } catch (e) { setMsg(`Non programmato: ${e.message}`, true); }
};

$("#pub-now").onclick = async () => {
  if ($("#pub-text").value.length > 3000) return setMsg("Il testo supera i 3000 caratteri.", true);
  if (!confirm("Pubblicare ADESSO questo post sul tuo profilo LinkedIn?\nSarà visibile a tutti subito.")) return;
  const btn = $("#pub-now"); btn.disabled = true; setMsg("⏳ Pubblicazione in corso…");
  try {
    let res = await api("/api/linkedin/publish", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pubPayload()) });
    const jobId = res.job_id;
    while (res.status === "in corso") { await new Promise((r) => setTimeout(r, 2000)); res = await api(`/api/jobs/${jobId}`); }
    if (res.status === "errore") throw new Error(res.error);
    $("#pub-msg").innerHTML = `✅ Pubblicato! <a href="${esc(res.url)}" target="_blank" rel="noopener">Apri su LinkedIn</a> · ${esc(res.git)}`;
    $("#pub-msg").className = "small ok";
    await loadLinkedIn();
  } catch (e) { setMsg(`Non pubblicato: ${e.message}`, true); }
  finally { btn.disabled = false; }
};

async function refreshSync() {
  const s = await api("/api/sync");
  $("#sync-status").textContent = s.status === "in corso" ? "Sincronizzazione…"
    : s.status === "ok" ? (s.report_today && s.report_today !== "presente"
      ? `Report di oggi: ${s.report_today}` : "Aggiornato da GitHub") : "GitHub non raggiungibile";
  $("#sync-status").title = s.detail || "";
  return s.status;
}

async function init() {
  if (new URLSearchParams(location.search).get("linkedin") === "ok") {
    history.replaceState(null, "", "/" + location.hash);
    setTimeout(() => alert("LinkedIn collegato ✅"), 300);
  }
  loadLinkedIn().catch(() => { $("#li-status").textContent = "Stato LinkedIn non disponibile"; });
  const list = await loadArchive();
  const wanted = location.hash.slice(1);
  const date = list.find((r) => r.date === wanted) ? wanted : list[0]?.date;
  if (date) await showReport(date); else $("#report").innerHTML = '<p class="muted">Ancora nessun report.</p>';
  // il primo git pull gira in background: quando finisce ricarica l'archivio
  if ((await refreshSync()) === "in corso") {
    const t = setInterval(async () => { if ((await refreshSync()) !== "in corso") { clearInterval(t); await loadArchive(); markActive(); } }, 2000);
  }
}
init();
