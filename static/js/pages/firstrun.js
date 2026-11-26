"use strict";
/* ---------------- First run (design/canvas/FirstRun.dc.html) ----------------
   An install with no company yet opens on this welcome page in place of the Overview (core/shell.js render): import a setup file
   (the same file, checks and counts as Setup › Move setup) or add the first company and say where its books are kept, then the
   steps that come next. The page stays after either, with a note of what was done and the steps open, until Open Overview.
   Nothing here is new to the server: the import is POST /api/setup/import (a preview, then the import) and the company is POST
   /api/setup/entities, each audited like every Setup change. Departures from the board, kept for later slices: no Undo on the note
   (Undo is slice 10), no "Runs payroll in this app" tick (slice 15), no name or Sign out in the header (sign-in is slice 16). */
const FR = { name: "", preview: null, file: null, error: "", refused: "", why: "", done: null, note: null, saved: null, alerted: false, addOpen: false, busy: "", tried: false, kind: "", code: "", cname: "", reg: "", addError: "" };

// The page takes the place of the Overview while there is no company, and after one is added or a file imported, until Open Overview.
function firstRunDue() {
  // What was saved and not read again is in the records once something reads them (Setup does): the note is over, the Overview draws.
  if (FR.saved && (state.metaReads || 0) > FR.saved.reads) { FR.saved = null; FR.alerted = false; }
  return state.view === "overview" && !!state.meta && (!(state.meta.entities || []).length || !!FR.done || !!FR.saved);
}
// The shell (menu and top bar) has nothing to offer yet: the page has its own head.
function firstRunShell(on) {
  if (!on && (FR.done || FR.note) && state.view !== "overview") FR.done = FR.note = null;  // another page was opened: the note of what was done is over
  const c = typeof document !== "undefined" ? document.body?.classList : null;
  if (on) c?.add?.("first-run"); else c?.remove?.("first-run");
}

const FR_STEPS = [
  ["bank", "Add a bank account", "Each payment is matched against the company's bank statement. Add the account in Setup.", "Admin › Setup", () => "#/admin/setup/accounts"],
  ["staff", "Add your staff or paste the Excel list", "One person at a time, or paste your Excel staff list: each row is checked and shown before anything is saved. Leave, claims and payroll start from these records.", "HR › Staff", () => menuHref(MENU_BY_PAGE["hr/staff"])],
  ["recurring", "Add recurring payments", "Salaries, rent and other regular payments, so each month starts with them already listed.", "Payments › Recurring", () => menuHref(MENU_BY_PAGE["payments/recurring"])],
  ["calendar", "Set up the month", "Open the first month you want to track. Earlier months stay as they are.", "Payments › Payments register", () => menuHref(MENU_BY_PAGE["payments/register"])],
  ["vault", "Make the first backup", "An encrypted copy of the records, kept in the backup folder.", "Admin › Backup", () => "#/admin/backup"],
];

function frHtml() {
  const done = !!FR.done && !FR.saved, p = FR.preview;   // what was done before is not said beside "saved, but could not reload"
  const brand = `<svg class="mark" viewBox="0 0 36 36" role="img" aria-label="HR Payments" width="32" height="32"><rect width="36" height="36" rx="10" fill="#2450B8"/><rect x="9" y="9" width="18" height="18" rx="4" fill="#5C83E0"/><path d="M13 15h10M13 19h6" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" fill="none"/><circle cx="24" cy="23" r="3" fill="#FFFFFF"/></svg>`;
  const imp = FR.busy === "import";
  const importBody = p ? `<div class="fr-file"><div class="row tight">${icon("document")}<span><b>${esc(FR.name)}</b><span class="note"> ${p.what === "full" ? "Everything" : "A template"}, saved ${esc(fmtDate(p.made))}. Importing it adds or changes:</span></span></div>
      ${moveCountsTable(p)}${(p.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join("")}
      <label class="field"><span>Why are you importing this? <span class="req">Optional</span></span><input id="fr-why" type="text" maxlength="500" autocomplete="off" value="${esc(FR.why)}"></label>
      <div class="row"><button type="button" class="btn" data-fr-import="1"${imp ? ` disabled aria-busy="true"` : ""}>${imp ? `<span class="spin" aria-hidden="true"></span>Importing` : "Import"}</button><button type="button" class="ghost" data-fr-cancel-import="1"${imp ? " disabled" : ""}>Cancel</button></div></div>`
    : `${FR.refused ? moveRefusal(FR.name, FR.refused) : ""}${FR.error ? `<div class="refused" role="alert" id="fr-imp-err">${icon("alert")}<div class="refused-text">${esc(FR.error)}</div></div>` : ""}
      <div class="row"><button type="button" class="ghost" data-fr-pick="1"${FR.error || FR.refused ? ` aria-describedby="fr-imp-err"` : ""}>${FR.error || FR.refused ? "Choose another file…" : "Choose a setup file…"}</button><span class="note">A file saved as setup.json</span></div>`;
  const kindCard = (v, title, body) => `<label class="fr-kind${FR.kind === v ? " on" : ""}" for="fr-kind-${v}"><input id="fr-kind-${v}" type="radio" name="fr-kind" value="${v}" data-fr-kind="${v}"${FR.kind === v ? " checked" : ""}><span><b>${title}</b><span class="note">${body}</span></span></label>`;
  const bad = { code: FR.tried && !FR.code.trim() ? "Type a short name for the company." : "", name: FR.tried && !FR.cname.trim() ? "Type the company name." : "", kind: FR.tried && !FR.kind ? "Choose where the books are kept." : "" };
  const field = (id, label, hint, val, err, extra = "") => `<div class="field"><label for="fr-${id}">${label}</label><input id="fr-${id}" type="text" autocomplete="off" value="${esc(val)}"${err ? ` aria-invalid="true"` : ""} aria-describedby="${[hint ? `fr-${id}-hint` : "", err ? `fr-${id}-err` : ""].filter(Boolean).join(" ")}"${extra}>${hint ? `<span class="note" id="fr-${id}-hint">${hint}</span>` : ""}${err ? `<span class="field-err" id="fr-${id}-err">${icon("alert")}${esc(err)}</span>` : ""}</div>`;
  const add = FR.busy === "add";
  const addBody = !FR.addOpen ? `<div class="row"><button type="button" class="btn" id="fr-add-open" data-fr-add-open="1">${icon("plus")}Add a company</button></div>`
    : `<form id="frForm" novalidate>${FR.addError ? refusedNote(FR.addError, { title: "The company wasn't added" }) : ""}
      ${field("code", "Short name", "Shown in the company switcher, for example ABC.", FR.code, bad.code, " data-upper")}
      ${field("name", "Company name", "", FR.cname, bad.name)}
      ${field("reg", `Registration number <span class="req">Optional</span>`, "", FR.reg, "")}
      <fieldset class="fr-kinds" aria-describedby="${bad.kind ? "fr-kind-err" : ""}"><legend>Where are the books kept?</legend>
        ${kindCard("sql", "Kept in SQL Account", "Payments then need their PV, JV or OR from SQL.")}
        ${kindCard("here", "Kept here", "The books are kept in this app: sales, purchases, journals and period close.")}
        ${bad.kind ? `<span class="field-err" id="fr-kind-err">${icon("alert")}${esc(bad.kind)}</span>` : ""}</fieldset>
      <div class="row"><button type="submit" class="btn"${add ? ` disabled aria-busy="true"` : ""}>${add ? `<span class="spin" aria-hidden="true"></span>Adding` : "Add company"}</button><button type="button" class="ghost" data-fr-add-cancel="1"${add ? " disabled" : ""}>Cancel</button></div></form>`;
  const steps = FR_STEPS.map(([glyph, title, body, where, href], i) => `<li class="fr-step"><span class="plate ${done ? "brand" : "mute"}">${icon(glyph)}</span><span class="fr-step-words"><b>${i + 1}. ${esc(title)}</b><span class="note">${esc(body)}</span></span>${done
    ? (a => a && a !== "#/" ? `<a class="pill" href="${esc(a)}" data-fr-step="${esc(glyph)}">${esc(where)}</a>` : `<span class="pill grey">${esc(where)}</span>`)(href())
    : `<span class="pill grey">After a company is added</span>`}</li>`).join("");
  return `<div class="fr-page"><header class="fr-top">${brand}<span class="fr-brand">HR Payments</span></header>
    <div class="fr-main"><div class="fr-head"><h1 id="fr-title" tabindex="-1">Welcome to HR Payments</h1>
      <p class="note">There is no company here yet. Start in one of two ways. Everything is kept on this PC, and each change is noted in the audit trail.</p></div>
    ${FR.saved ? `<div class="banner bad fr-done" role="alert" id="fr-saved" tabindex="-1">${icon("alert")}<span>It was saved, but this page could not reload. Try again.</span><button type="button" class="btn" id="fr-reload" data-fr-reload="1"${FR.busy === "reload" ? ` disabled aria-busy="true"` : ""}>${FR.busy === "reload" ? `<span class="spin" aria-hidden="true"></span>Reading` : "Try again"}</button></div>` : ""}
    ${!FR.saved && !done && FR.note ? `<div class="banner info fr-done" role="status">${icon("help")}<span><b>${esc(FR.note.title)}</b> ${esc(FR.note.body)}</span></div>` : ""}
    ${done ? `<div class="banner ok fr-done" role="status">${icon("check")}<span><b>${esc(FR.done.title)}</b> ${esc(FR.done.body)}</span><button type="button" class="btn" data-fr-open="1">Open Overview</button></div>` : ""}
    ${FR.saved ? "" : `<div class="fr-cards">
      <section class="card fr-card" aria-labelledby="fr-imp-h"><span class="plate brand">${icon("upload")}</span><h2 id="fr-imp-h">Import a setup file</h2>
        <p class="note">Already use HR Payments somewhere else? Start from its setup file (Move setup). Each row is checked as Setup checks it, and nothing is saved unless every row passes.</p>${importBody}</section>
      <section class="card fr-card" aria-labelledby="fr-add-h"><span class="plate brand">${icon("company")}</span><h2 id="fr-add-h">Add your first company</h2>
        <p class="note">Starting fresh? Add the company you pay from. You can add more companies later in Setup.</p>${addBody}</section>
    </div>`}
    <section class="card fr-next" aria-labelledby="fr-next-h"><div><h2 id="fr-next-h">What comes next</h2>
      <span class="note">${done ? "Do these in any order. Each one opens where it is done." : "These open up once the first company is in. Nothing is lost by doing them in any order."}</span></div>
      <ol class="fr-steps">${steps}</ol></section></div></div>`;
}

// Draws the page again, keeping the focus on the same control (or the one named by focus). Only while First run is the page on show: an
// answer that comes after another page was opened paints nothing over it.
function frPaint(focus) {
  const main = $("#main"); if (!main || state.view !== "overview") return;
  const a = document.activeElement, id = focus || (a && a.id) || null;
  main.innerHTML = frHtml();
  if (id) document.getElementById(id)?.focus?.({ preventScroll: true });
}
async function viewFirstRun(main) {
  main.innerHTML = frHtml();
  if (FR.done || FR.note) document.getElementById("fr-title")?.focus?.({ preventScroll: true });
}

// Choose a setup file: it is read and previewed as Move setup does (nothing is saved), and its counts shown.
async function frPick() {
  const [f] = await pickFile(false);
  if (!f) return;
  Object.assign(FR, { name: f.name, preview: null, file: null, error: "", refused: "" });
  try { const r = await readSetupFile(f); Object.assign(FR, { file: r.setup, preview: r.preview }); }
  catch (e) { if (appStopped(e)) throw e; if (e.refused) FR.refused = e.message; else FR.error = e.message; }
  frPaint(FR.preview ? "fr-why" : "fr-imp-h");
}
async function frImport() {
  if (!FR.file || FR.busy) return;
  FR.why = $("#fr-why")?.value || FR.why; FR.busy = "import"; frPaint();
  try {
    try { await api("/api/setup/import", { json: { setup: FR.file, reason: FR.why.trim() || "Started this install from a setup file." } }); }
    catch (e) { if (appStopped(e)) throw e; if (e.unsure) throw new Error(changeError(e)); Object.assign(FR, { busy: "", preview: null, file: null, refused: e.message }); frPaint("fr-imp-h"); return; }
    Object.assign(FR, { file: null, preview: null, name: "", why: "" });
    await frFinish({ imported: true });
  } finally { if (FR.busy) { FR.busy = ""; frPaint(); } }  // a network failure: the page is usable again, with what was typed
}
// A company or a file has been added: the menu and the company switcher read the records again. The install is ready to use only when
// there is a company now: a file of rules alone (a template) leaves the page as it was, with a note that says what is next.
async function frFinish({ imported = false, code = "", kept = "" } = {}) {
  // It is written already: if the records can't be read again, the page says so and offers Try again, which only reads them again
  // (never the form that would write it twice).
  FR.saved = { imported, code, kept, reads: state.metaReads || 0 }; FR.done = FR.note = null;
  try { state.meta = await readMeta(); paintOrg(); }
  catch (e) {
    const again = FR.alerted; FR.alerted = true;
    FR.busy = ""; frPaint(again ? "fr-reload" : "fr-saved");  // the alert takes the focus when it first appears; its button keeps it after
    throw e;
  }
  FR.saved = null; FR.alerted = false;
  const list = state.meta.entities || [], n = list.length, stopped = list.filter(e => !isActive(e)).length;
  Object.assign(FR, { busy: "", addOpen: false, refused: "", error: "" });
  if (!n) FR.done = null, FR.note = { title: "Rules imported.", body: "Now add your first company." };
  else {
    FR.note = null;
    const st = !stopped ? "" : stopped === n ? (n === 1 ? ", and it is stopped" : ", all of them stopped") : `, ${stopped} of them stopped`;
    FR.done = imported ? { title: "Setup imported.", body: `${n} ${n === 1 ? "company" : "companies"} came in${st}. Each change is noted in the audit trail.` }
      : { title: "Company added.", body: `${code} is ready: ${kept}. The next steps are open below.` };
  }
  state.entity = firstEntityId(); state.setup.types = null; state.setup.kind = null;
  renderNav();
  await render();
}
// Try again after a write that was saved: the records are read again, nothing is sent.
async function frReload() {
  if (!FR.saved || FR.busy) return;
  FR.busy = "reload"; frPaint("fr-reload");
  try { await frFinish(FR.saved); }
  finally { if (FR.busy) { FR.busy = ""; frPaint("fr-reload"); } }
}
async function frAddCompany() {
  Object.assign(FR, { tried: true, addError: "" });
  const code = FR.code.trim().toUpperCase(), name = FR.cname.trim();
  if (!code || !name || !FR.kind) { frPaint(!code ? "fr-code" : !name ? "fr-name" : "fr-kind-sql"); return; }
  FR.busy = "add"; frPaint();
  try {
    try {
      const fields = { code, name, uses_sql: FR.kind === "sql" ? 1 : 0 };
      if (FR.reg.trim()) fields.reg_no = FR.reg.trim();
      await api("/api/setup/entities", { json: { fields } });
    } catch (e) { if (appStopped(e)) throw e; if (e.unsure) throw new Error(changeError(e)); Object.assign(FR, { busy: "", addError: e.message }); frPaint("fr-code"); return; }
    const kept = FR.kind === "sql" ? "Kept in SQL Account" : "Kept here";
    Object.assign(FR, { tried: false, kind: "", code: "", cname: "", reg: "" });
    await frFinish({ code, kept });
  } finally { if (FR.busy) { FR.busy = ""; frPaint(); } }  // a network failure: the form is usable again, with what was typed
}
// Cancel on the form: a form with something typed in it asks first, as a dialog does.
async function frAddCancel() {
  if (FR.code.trim() || FR.cname.trim() || FR.reg.trim() || FR.kind) {
    if (!(await ask("What you typed for this company will be lost.", { title: "Discard your changes?", yes: "Discard", no: "Keep editing", danger: true, tone: "warn", glyph: "edit" }))) { document.getElementById("fr-code")?.focus?.(); return; }
  }
  Object.assign(FR, { addOpen: false, tried: false, kind: "", code: "", cname: "", reg: "", addError: "" });
  frPaint("fr-add-open");
}

// The page's own controls (it has no shell around it, so the page-wide handlers don't know them).
document.addEventListener("click", async ev => {
  const t = ev.target?.closest?.("[data-fr-pick], [data-fr-import], [data-fr-cancel-import], [data-fr-add-open], [data-fr-add-cancel], [data-fr-open], [data-fr-kind], [data-fr-reload]");
  if (!t || !$("#fr-title")) return;
  const d = t.dataset;
  try {
    if ("frPick" in d) { t.disabled = true; try { await frPick(); } finally { if (t.isConnected) t.disabled = false; } }
    else if ("frImport" in d) await frImport();
    else if ("frCancelImport" in d) { Object.assign(FR, { preview: null, file: null, name: "", why: "", error: "", refused: "" }); frPaint("fr-imp-h"); }
    else if ("frAddOpen" in d) { FR.addOpen = true; FR.tried = false; frPaint("fr-code"); }
    else if ("frAddCancel" in d) await frAddCancel();
    else if ("frReload" in d) await frReload();
    else if ("frOpen" in d) { FR.done = null; await go("overview"); }
    else if ("frKind" in d) { FR.kind = d.frKind; frPaint(`fr-kind-${d.frKind}`); }
  } catch (e) { toast(e.message, true); }
});
document.addEventListener("input", ev => {
  const t = ev.target;
  if (!t || !$("#fr-title")) return;
  if (t.id === "fr-code") FR.code = t.value.toUpperCase(); else if (t.id === "fr-name") FR.cname = t.value; else if (t.id === "fr-reg") FR.reg = t.value; else if (t.id === "fr-why") FR.why = t.value;
});
document.addEventListener("submit", async ev => {
  if (ev.target.id !== "frForm") return;
  ev.preventDefault();
  try { await frAddCompany(); } catch (e) { toast(e.message, true); }
});
