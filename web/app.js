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
  $("#drawer-images").hidden = kind !== "post";
  $("#drawer-publish").hidden = kind !== "post";
  if (kind === "post") renderImages((await api(`/api/images/${item}`)).images);
  $("#drawer").hidden = false;
  document.querySelector(".drawer-scroll").scrollTop = 0;
}

function renderImages(list, note = "") {
  $("#images-grid").innerHTML = list.map((src) =>
    `<a href="${src}" target="_blank" rel="noopener" download title="Apri / scarica"><img src="${src}" alt="Immagine del post" loading="lazy"></a>`).join("");
  $("#images-btn").textContent = list.length ? "🖼️ Altre 2 varianti" : "🖼️ Genera 2 immagini";
  $("#images-info").textContent = note || (list.length
    ? "Clicca un'immagine per aprirla a piena risoluzione e scaricarla."
    : "Usa il \"Prompt immagine\" del post e il tuo Soul su Higgsfield · ~0,24 crediti · 1-2 minuti.");
}

$("#images-btn").onclick = async () => {
  const d = state.drawer; if (!d) return;
  const btn = $("#images-btn");
  btn.disabled = true; btn.textContent = "⏳ Higgsfield al lavoro… (1-2 min)";
  try {
    let res = await api(`/api/images/${d.item}`, { method: "POST" });
    const jobId = res.job_id;
    while (res.status === "in corso") {
      await new Promise((r) => setTimeout(r, 3000));
      res = await api(`/api/jobs/${jobId}`);
    }
    if (res.status === "errore") throw new Error(res.error);
    renderImages(res.images, res.git ? `Fatto · ${res.git}` : "");
  } catch (e) {
    renderImages((await api(`/api/images/${d.item}`)).images, `Non riuscito: ${e.message}`);
  } finally {
    btn.disabled = false;
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
  const imgs = (await api(`/api/images/${d.item}`)).images;
  $("#pub-images").innerHTML =
    `<label><input type="radio" name="pubimg" value="" ${imgs.length ? "" : "checked"}><span class="noimg">nessuna</span></label>` +
    imgs.map((src, i) => `<label><input type="radio" name="pubimg" value="${src.split("/").pop()}" ${i === 0 ? "checked" : ""}><img src="${src}" alt=""></label>`).join("");
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
  return { item_id: state.drawer.item, title: $("#pub-title").textContent, text: $("#pub-text").value.trim(),
    image: document.querySelector('input[name="pubimg"]:checked')?.value || null };
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
    : s.status === "ok" ? "Aggiornato da GitHub" : "GitHub non raggiungibile";
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
