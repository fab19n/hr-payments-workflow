"use strict";
/* ---------------- The payment dialog and Add payment (slice 3) ----------------
   A payment opens in a centred dialog over the Payments register (design/canvas/Payment.dc.html, DarkPayment.dc.html for dark):
   its head (type, due date, status words, Pay to), four facts (amount, paid date, bank account, documents), its documents
   (several files per type, a drop on a row adds a file as that type, a drop anywhere else asks which document each file is),
   its links to SQL Account and the bank statement, the details form with the Bank account field, part paid and the estimate
   tick, its history, and the document viewer beside it (in place of it below 860 pixels). A filed month is read only.
   Add a payment opens the New payment dialog (NewPayment.dc.html) over the register.
   Waits for later slices: the Approval marker and the request and approval form boxes (slice 11); a Kept here company's
   posted voucher (stage 2): its payment shows the record reference field, as any payment with no SQL voucher. */

// The file types the server takes (hrp/docstore.py ALLOWED) and its largest upload (MAX_CONTENT_LENGTH).
const PD_TYPES = [".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".ods", ".csv", ".docx", ".doc", ".txt", ".xml", ".eml", ".msg"];
const PD_MAX = 40 * 1024 * 1024;
const pdQ = s => (typeof document.querySelector === "function" ? document.querySelector(s) : null);
const pdExt = name => ((String(name || "").match(/\.[^.]+$/) || [""])[0]).toLowerCase();
const pdSize = b => b == null ? "" : b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
const pdWhen = iso => { if (!iso) return ""; const t = iso.slice(11, 16); return shortDate(iso) + (t ? `, ${t}` : ""); };
const pdSlug = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
// Focus the first of these that is there.
function pdFocus(...sels) {
  for (const s of sels) { const el = s && pdQ(s); if (el && el.focus) { el.focus({ preventScroll: false }); return true; } }
  return false;
}
// What the dialog keeps while one payment is open (a redraw after an upload or a save keeps it): the document on show in the
// viewer and its zoom, the uploads going on, the files waiting for their type, the open menu, the question asked on a row,
// saving, and the server's refusal.
function payUi(id) {
  if (!state.pay || state.pay.id !== id) state.pay = { id, viewer: null, zoom: "100", ups: [], pick: null, menu: null, ask: null, saving: false, refused: null, n: 0 };
  return state.pay;
}
const payOf = id => state.data?.payments?.find(x => x.id === id) || null;
// The company's bank accounts (the meta's company carries them; the month's does not).
const pdAccounts = () => state.meta.entities.find(x => x.id === state.data?.entity?.id)?.accounts || [];
// The document types this payment can take beyond its required ones: those in use, never the ones the app files itself
// (statements, reconciliations, SQL listings), and for a company not kept in SQL no SQL documents.
function pdExtraTypes(p) {
  const noSql = !state.data.entity.uses_sql;
  return Object.keys(state.meta.doc_types).filter(t => !p.required.includes(t) && docActive(t) && !["statement", "recon", "sqlexport"].includes(t) && !(noSql && docFromSql(t)));
}
// The first guess at a file's type, from its name (the dialog asks before anything is filed).
function pdGuess(name, keys) {
  const t = String(name).toLowerCase();
  const g = /payslip/.test(t) ? "payslip" : /approval|\.eml$|\.msg$/.test(t) ? "approval" : /claim/.test(t) ? "claim" : /e-?invoice/.test(t) ? "einvoice"
    : /\bpv|voucher/.test(t) ? "pv" : /\bor\b|receipt/.test(t) ? "or" : /slip|ibg|fpx|transfer|duitnow/.test(t) ? "bank" : /ack|portal/.test(t) ? "portal" : /bill|invoice|inv/.test(t) ? "invoice" : "other";
  return keys.includes(g) ? g : keys.includes("other") ? "other" : keys[0];
}
// What the viewer can show: a PDF or an image; anything else is downloaded (the server serves nothing else inline).
function pdKind(name) {
  const x = pdExt(name);
  return x === ".pdf" ? "pdf" : [".png", ".jpg", ".jpeg"].includes(x) ? "image" : [".eml", ".msg"].includes(x) ? "email"
    : [".xlsx", ".xls", ".ods", ".csv"].includes(x) ? "sheet" : [".docx", ".doc"].includes(x) ? "word" : "other";
}
const PD_CANT = { email: ["Emails can't be shown here", "Download it and open it in your mail program."],
  sheet: ["Spreadsheets can't be shown here", "Download it and open it in Excel or a similar program."],
  word: ["Word documents can't be shown here", "Download it and open it in Word."],
  other: ["This file can't be shown here", "Download it and open it in the program it belongs to."] };

// ---------- the dialog ----------
function openPayment(id, keep = {}) {
  const p = payOf(id);
  if (!p) return closeDrawer(true);
  if (state.openPayment !== id) state.pay = null;
  state.openPayment = id; state.drawerDirty = null; state.np = null;
  const S = payUi(id), d = state.data, e = d.entity, ro = !!d.closed_at, cur = p.currency || "MYR", into = p.direction === "in";
  if (S.viewer && !p.documents.some(x => x.id === S.viewer)) S.viewer = null;
  const typeLabel = state.meta.categories[p.category] || p.category;
  const lines = p.bank_lines || [], hasBank = lines.length > 0;
  const gap = p.bank_total == null || p.amount == null || estimateShort(p) ? 0 : p.amount - p.bank_total;
  const have = p.required.filter(t => p.documents.some(x => x.doc_type === t) || p.evidence[t]).length;
  const done = have === p.required.length;
  // The status words (aria-live, so a change is read out): the server's word for why a payment is not paid yet, else
  // Part paid, Complete or Paid with documents missing.
  const status = statusPill(p) || `<span class="pill grey">${into ? "Not received yet" : "Not paid"}</span>`;
  const flag = p.status !== "planned" && p.flag ? flagPill(p.flag) : "";
  const est = p.amount_is_estimate ? `<span class="pill grey" title="${e.uses_sql ? "Planned figure. The SQL voucher or bank line replaces it." : "Planned figure. The bank line replaces it."}">estimate</span>` : "";
  const hint = p.flag?.hint ? `<div class="pd-hint">${esc(p.flag.hint)}</div>` : "";
  const payTo = p.bank_details || p.payee_ref ? `<div class="pd-payto">Pay to: <span class="mono">${esc([p.bank_details, p.payee_ref].filter(Boolean).join(" "))}</span></div>` : "";
  const acct = pdAccounts().find(a => a.id === p.account_id);
  const amountNote = estimateShort(p) ? `Estimated ${money(p.planned_amount, cur)}` : p.amount_is_estimate ? "Estimate" : gap > 0.01 ? `${money(p.bank_total, cur)} on the bank statement` : into ? "Money in" : "Money out";
  const paidNote = !p.paid_date ? "Not recorded yet" : p.paid_source === "bank" ? (lines.length > 1 ? "From the bank lines" : "From the bank line") : p.paid_source === "sql" ? "From the SQL voucher" : "Entered by hand";
  const acctNote = acct ? (hasBank ? "Its bank line is on this account" : p.paid_date ? (into ? "The account it was paid into" : "The account it was paid from") : (into ? "The account it will be paid into" : "The account it will be paid from")) : "No account chosen";
  const fact = (k, v, note, extra = "") => `<div class="pd-fact"><span class="pd-fact-k">${k}</span><div class="pd-fact-v">${v}</div>${note ? `<span class="pd-fact-n">${esc(note)}</span>` : ""}${extra}</div>`;
  const facts = fact("Amount", esc(money(p.amount, cur)), amountNote)
    + fact(into ? "Received on" : "Paid on", esc(p.paid_date ? fmtDate(p.paid_date) : into ? "Not received yet" : "Not paid yet"), paidNote)
    + fact(into ? "Paid into" : "Paid from", esc(acct ? acct.label : "Not set"), acctNote)
    + fact("Documents", `${have} of ${p.required.length}`, "", `<div class="bar pd-bar ${done ? "ok" : "warn"}" aria-hidden="true"><i style="width:${p.required.length ? Math.round(have / p.required.length * 100) : 100}%"></i></div>`);
  const MN = monthName(d.month);
  const lock = ro ? `<div class="pd-lock" role="note">${icon("lock")}<div><b>${esc(MN)} is filed for ${esc(e.code)}, so this payment is read only</b>
      <div>Filed on ${esc(shortDate(d.closed_at))}. Nothing in a filed month changes. To correct it, reopen ${esc(MN)} on its Monthly checklist, then file it again.</div></div>
      <a class="ghost small" href="${pageAddr("checklist", d)}">Open the Monthly checklist</a></div>` : "";
  const viewing = S.viewer ? p.documents.find(x => x.id === S.viewer) : null;
  const dr = $("#drawer");
  // The dialog is drawn into its own box; the viewer is a box beside it, made once per View and taken away only when it
  // is closed or shows another document. So a redraw (a menu, a save, an upload) never touches the viewer: an iframe
  // taken out of the page and put back loads its file again (another "opened" entry in the audit trail, a PDF back on
  // page 1). Where focus was in the dialog (a field being typed in), it stays.
  const was = document.activeElement, wasId = was && was.id && dr.contains?.(was) ? was.id : null;
  const sel = wasId && typeof was.selectionStart === "number" ? [was.selectionStart, was.selectionEnd] : null;
  let box = dr.querySelector ? dr.querySelector(":scope > #pd-box") : null;
  if (dr.querySelector && !box) { dr.innerHTML = `<div class="pd-main" id="pd-box"></div>`; box = dr.querySelector("#pd-box"); }
  const old = dr.querySelector ? dr.querySelector(":scope > .pd-viewer") : null;
  if (old && (!viewing || old.dataset.doc !== String(viewing.id))) old.remove();
  const kept = !!(viewing && old && old.isConnected);
  const html = `
    <div class="pd-top">
      <div class="pd-head"><span class="plate brand">${icon("receipt")}</span>
        <div class="pd-words"><span class="eyebrow">${esc(e.code)} · ${esc(typeLabel)} · due ${esc(fmtDate(p.due_date))}</span>
          <h2 id="drawerTitle" tabindex="-1">${esc(p.description)}</h2>
          <div class="pd-pills"><span class="pd-status" aria-live="polite">${status}</span>${flag}${est}</div>
          ${hint}${payTo}</div>
        <button type="button" class="ghost small pd-x" id="closeDrawer" aria-label="Close">${icon("close")}</button></div>
      <div class="pd-facts">${facts}</div>
      ${lock}
    </div>
    <div class="pd-body">
      <div class="pd-col">${pdRequired(p, ro)}${pdOthers(p, ro)}${pdLinked(p, ro)}</div>
      <div class="pd-col">${pdForm(p, ro)}<section class="pd-sec pd-hist">${histSection("payments", p.id)}</section></div>
    </div>
    <div class="pd-foot">
      ${ro ? "" : `<button type="button" class="btn danger" id="deletePayment">Remove this payment</button>`}
      <span id="pd-foot" class="pd-foot-note${ro ? " ro" : ""}">${ro ? `Read only: ${esc(MN)} is filed.` : ""}</span>
      <div class="pd-foot-acts"><button type="button" class="ghost" data-pd-close="1">${ro ? "Close" : "Cancel"}</button>
        ${ro ? "" : `<button type="submit" class="btn" id="pd-save" form="payForm">Save details</button>`}</div>
    </div>`;
  if (box) {
    // History stays open across a redraw, with what it loaded (loaded again after a save or upload, which add to it).
    const oh = box.querySelector?.("details[data-hist]");
    if (oh) S.hist = { open: !!oh.open, html: oh.dataset.loaded && !S.histStale ? oh.querySelector(".hist-body")?.innerHTML ?? null : null };
    S.histStale = false;
    box.innerHTML = html;
    const nh = S.hist?.open ? box.querySelector?.("details[data-hist]") : null;
    if (nh) {
      const hb = nh.querySelector(".hist-body");
      if (S.hist.html != null && hb) { hb.innerHTML = S.hist.html; nh.dataset.loaded = "1"; }
      nh.open = true;   // not loaded: the toggle listener (core/listeners.js) loads it
    }
    if (viewing && !kept) dr.insertAdjacentHTML("beforeend", pdViewer(viewing, ro));
  } else dr.innerHTML = `<div class="pd-main">${html}</div>${viewing ? pdViewer(viewing, ro) : ""}`;   // a page with no real DOM (the tests)
  dr.classList?.remove?.("pd-viewing");
  if (viewing) dr.classList?.add?.("pd-viewing");
  showDrawer("dialog");
  state.payLoaded = payFormValues();
  if (!ro) for (const [k, v] of Object.entries(keep)) { const el = $("#" + k); if (el) el[el.type === "checkbox" ? "checked" : "value"] = v; }
  if (wasId && document.activeElement !== was) {
    const el = document.getElementById?.(wasId);
    if (el && dr.contains?.(el)) { el.focus({ preventScroll: true }); if (sel) try { el.setSelectionRange(sel[0], sel[1]); } catch { /* not a text field */ } }
  }
  pdLive();
}

// Draws the open payment again with what was typed in it, keeping the place the list was scrolled to, then focuses the
// first of focus that is there.
function payPaint(...focus) {
  if (!state.openPayment || !dlgDrawerOpen()) return;
  const body = pdQ(".pd-body"), top = body ? body.scrollTop : 0;
  openPayment(state.openPayment, unsavedEdits());
  const nb = pdQ(".pd-body"); if (nb) nb.scrollTop = top;
  if (focus.length) pdFocus(...focus);
}

// The required documents: one row per file of each type, or one saying what is missing, or what SQL or the bank
// statement already shows; then a row to add another. The uploads going on and the files waiting for their type go first.
function pdRequired(p, ro) {
  const S = state.pay, e = state.data.entity;
  const note = ro ? "Read only: the month is filed, so documents can be viewed and downloaded but not added, replaced or removed."
    : `Drop files on a box, or click Upload. A file dropped on a box is added beside the ones already there; files dropped anywhere else ask which document each one is. Replace swaps one and Remove takes one off. A box ticked from ${e.uses_sql ? "SQL or " : ""}the bank statement needs no upload, but can still take a copy.`;
  return `<section class="pd-sec" aria-labelledby="pd-req-h"><div class="pd-sec-h">${icon("upload")}<h3 id="pd-req-h">Required documents</h3>
      ${ro ? "" : `<button type="button" class="ghost small" id="pd-multi" data-pd-multi="1">${icon("upload")}Upload several files</button>`}</div>
    <p class="note">${esc(note)}</p>
    ${S.pick ? pdPickHtml(p) : ""}${S.ups.length ? pdUpsHtml() : ""}
    ${p.required.map(t => pdType(p, t, ro)).join("")}</section>`;
}
function pdOthers(p, ro) {
  const types = [...new Set(p.documents.map(x => x.doc_type).filter(t => !p.required.includes(t)))];
  const extra = pdExtraTypes(p), x = state.pay?.xType;   // the type picked stays picked across a redraw
  const pick = x && extra.includes(x) ? x : ["approval", "other"].find(t => extra.includes(t)) || extra[0];
  return `<section class="pd-sec" aria-labelledby="pd-oth-h"><div class="pd-sec-h">${icon("folder")}<h3 id="pd-oth-h">Other documents</h3></div>
    ${types.map(t => pdType(p, t, ro)).join("") || `<p class="note">No other documents on this payment yet.</p>`}
    ${extra.length && !ro ? `<div class="pd-xup"><label class="field"><span>Document type</span><select id="extraType">${extra.map(t => `<option value="${esc(t)}" ${t === pick ? "selected" : ""}>${esc(state.meta.doc_types[t] || t)}</option>`).join("")}</select></label>
      <button type="button" class="ghost" id="extraUpload">${icon("upload")}Upload another document</button></div>` : ""}</section>`;
}
// One document type: its rows and, once it has a file, the row to add another (a drop on it adds a file as that type).
function pdType(p, t, ro) {
  const docs = p.documents.filter(x => x.doc_type === t), ev = p.evidence[t];
  const rows = docs.length ? docs.map(x => pdRow(p, t, "file", x, ro)).join("") : pdRow(p, t, ev ? "ev" : "need", null, ro);
  const name = t === "other" ? "document" : docLabel(t);
  const add = docs.length && !ro ? `<div class="pd-add" data-slot="${esc(t)}"><button type="button" class="ghost small" id="pd-add-${pdSlug(t)}" data-upload="${esc(t)}">${icon("plus")}Add another ${esc(name)}</button>
      <span class="pd-add-n">or drop files here</span></div>` : "";
  return `<div class="pd-type">${rows}${add}</div>`;
}
function pdNeedNote(t) {
  const e = state.data.entity;
  if (t === "bank") return "Not uploaded. Matching its bank line ticks this too.";
  if (t === "einvoice" && e.uses_sql) return "Not uploaded. A validated e-Invoice in SQL ticks this too.";
  if (e.uses_sql && docFromSql(t)) return "Not uploaded. Linking its SQL voucher ticks this too.";
  return "Not uploaded.";
}
function pdRow(p, t, kind, doc, ro) {
  const S = state.pay, d = state.data, label = state.meta.doc_types[t] || t, ev = p.evidence[t];
  const key = doc ? `doc-${doc.id}` : `ev-${t}`, open = S.menu === key;
  let note, glyph, tone, acts = "", why = "";
  if (kind === "file") {
    const on = S.viewer === doc.id;
    note = `${doc.original_name} · ${pdSize(doc.size)}${doc.size != null ? " · " : ""}uploaded ${pdWhen(doc.uploaded_at)}`; glyph = "check"; tone = "ok";
    acts = `<button type="button" class="ghost small${on ? " on" : ""}" id="pd-vw-${doc.id}" data-pd-view="${doc.id}" aria-pressed="${on}" aria-label="View ${esc(doc.original_name)}">${icon("eye")}View</button>
      <a class="ghost small pd-icon" href="/api/documents/${doc.id}/file?download=1" download aria-label="Download ${esc(doc.original_name)}" title="Download">${icon("download")}</a>`;
  } else if (kind === "need") {
    note = pdNeedNote(t); glyph = "document"; tone = "warn";
    if (p.not_counted[t]) why = `<div class="pd-why">${esc(p.not_counted[t].hint)}</div>`;
    if (!ro) acts = `<button type="button" class="btn small" id="pd-up-${pdSlug(t)}" data-upload="${esc(t)}" aria-label="Upload ${esc(label)}">${icon("upload")}Upload</button>`;
  } else {
    const line = t === "bank";
    note = ev.text; glyph = line ? "bank" : "database"; tone = "ok";
    acts = `<a class="ghost small" href="${pageAddr(line ? "bank" : "sql", d)}">${icon("eye")}${line ? "View line" : "View in SQL"}</a>`;
  }
  const what = doc ? doc.original_name : label;
  const menu = ro || kind === "need" ? "" : `<div class="pd-mw"><button type="button" class="ghost small pd-icon" id="pd-mb-${key}" data-pd-menu="${key}" aria-haspopup="menu" aria-expanded="${open}" aria-label="More actions for ${esc(what)}">${icon("more")}</button>
    ${open ? `<div class="pd-menu" role="menu" aria-label="More actions for ${esc(what)}">${doc
      ? `<button type="button" role="menuitem" tabindex="-1" data-pd-mi="replace" data-pd-doc="${doc.id}">Replace file</button><button type="button" role="menuitem" tabindex="-1" class="bad" data-pd-mi="remove" data-pd-doc="${doc.id}">Remove</button>`
      : `<button type="button" role="menuitem" tabindex="-1" data-pd-mi="copy" data-pd-type="${esc(t)}">Upload a copy anyway</button>`}</div>` : ""}</div>`;
  const A = S.ask && doc && S.ask.doc === doc.id ? S.ask : null;
  const askText = !A ? "" : A.act === "replace" ? `Replace “${doc.original_name}” with “${A.file.name}”? The old file is taken out of the audit pack.`
    : `Remove “${doc.original_name}”? It is taken off here and left out of the audit pack; the file itself is kept on this PC.`;
  const ask = A ? `<div class="pd-ask" role="alertdialog" aria-label="${esc(askText)}"><span>${esc(askText)}</span>
      <button type="button" class="ghost small" id="pd-ask-no" data-pd-ask="no">Cancel</button>
      <button type="button" class="btn small${A.act === "remove" ? " danger-solid" : ""}" data-pd-ask="yes">${A.act === "remove" ? "Remove" : "Replace"}</button></div>` : "";
  return `<div class="pd-doc ${kind}${S.viewer && doc && S.viewer === doc.id ? " viewing" : ""}" data-slot="${esc(t)}">
      <span class="pd-plate ${tone}">${icon(glyph)}</span>
      <div class="pd-doc-t"><b>${esc(label)}</b><div class="pd-doc-n">${esc(note)}</div>${why}</div>
      <div class="pd-doc-a">${acts}${menu}</div></div>${ask}`;
}
// The files dropped or picked together, each with the type it will be filed as (a first guess from its name).
function pdPickHtml(p) {
  const keys = [...p.required, ...pdExtraTypes(p).filter(t => !p.required.includes(t))];
  const n = state.pay.pick.length;
  return `<div class="pd-pick" role="group" aria-labelledby="pd-pick-h"><b id="pd-pick-h">Which document is each file?</b>
    <span class="note">Each file is filed as the type chosen here. The first guess comes from the file name.</span>
    ${state.pay.pick.map((x, i) => `<div class="pd-pick-row">${icon("document")}<span class="pd-pick-name"><b>${esc(x.file.name)}</b> <span class="muted">${esc(pdSize(x.file.size))}</span></span>
      <label class="sr-only" for="pd-pk-${i}">Document type for ${esc(x.file.name)}</label>
      <select id="pd-pk-${i}" data-pd-pk="${i}">${keys.map(k => `<option value="${esc(k)}" ${k === x.type ? "selected" : ""}>${esc(state.meta.doc_types[k] || k)}</option>`).join("")}</select></div>`).join("")}
    <div class="pd-pick-acts"><button type="button" class="ghost small" data-pd-pick="cancel">Cancel</button>
      <button type="button" class="btn small" id="pd-pick-go" data-pd-pick="go">Upload ${n} file${n === 1 ? "" : "s"}</button></div></div>`;
}
// The uploads: each file has its row with a progress bar, then a tick; one not added keeps its row with the reason and
// what to do (Retry, or Dismiss).
function pdUpsHtml() {
  const W = { up: "Uploading", ok: "Added", fail: "Couldn't add" };
  return `<ul class="pd-ups" aria-label="Uploads">${state.pay.ups.map(u => `<li class="pd-up ${u.st}" id="pd-upr-${u.id}">
    <span class="pd-plate ${u.st === "fail" ? "bad" : u.st === "ok" ? "ok" : "brand"}">${icon(u.st === "fail" ? "alert" : u.st === "ok" ? "check" : "upload")}</span>
    <div class="pd-up-t"><div class="pd-up-top"><span><b>${esc(u.file.name)}</b> <span class="muted">as ${esc(docLabel(u.type))}</span></span><span class="pd-up-st" id="pd-ups-${u.id}">${u.st === "up" ? `${u.pct}%` : W[u.st]}</span></div>
      ${u.st !== "fail" ? `<div class="bar pd-upbar" role="progressbar" aria-label="Uploading ${esc(u.file.name)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${u.pct}" id="pd-upb-${u.id}"><i style="width:${u.pct}%"></i></div>` : ""}
      ${u.why ? `<span class="pd-up-why">${esc(u.why)}</span>` : ""}</div>
    ${u.st === "fail" && u.net ? `<button type="button" class="ghost small" data-pd-retry="${u.id}">${icon("refresh")}Retry</button>` : ""}
    ${u.st === "fail" ? `<button type="button" class="ghost small pd-icon" data-pd-dismiss="${u.id}" aria-label="Dismiss ${esc(u.file.name)}">${icon("close")}</button>` : ""}</li>`).join("")}</ul>`;
}
// Linked records: the SQL voucher (for a company kept in SQL Account) and the bank statement lines.
function pdLinked(p, ro) {
  const d = state.data, e = d.entity, cur = p.currency || "MYR", into = p.direction === "in", lines = p.bank_lines || [];
  let sql = "";
  if (e.uses_sql) {
    const v = p.sql_entries || [];
    const rows = v.map(x => `<div class="pd-link-row"><span class="mono">${esc(x.doc_no)}${x.kind === "invoice" ? " (invoice)" : ""} · ${esc(shortDate(x.doc_date))} · ${x.direction && x.direction !== p.direction ? "−" : ""}${esc(money(x.amount, cur))}</span>
      ${ro ? "" : `<button type="button" class="ghost small" data-sql-unlink="${x.id}" aria-label="Unlink ${esc(x.doc_no)}">Unlink</button>`}</div>`).join("");
    const changed = (p.sql_changed || []).map(c => `<div class="pd-changed" role="note">${icon("alert")}<span>${esc(c.doc_no)} changed in SQL ${esc(c.words)}${c.version ? ` (version ${esc(c.version)})` : ""}. Move the link on the SQL import page to follow it.</span></div>`).join("");
    const einv = p.evidence.einvoice && !p.required.includes("einvoice") ? `<div class="note chip have ev">✓ ${esc(p.evidence.einvoice.text)}</div>` : "";
    sql = `<div class="pd-box"><div class="pd-box-h">${icon("database")}<h4>SQL Account</h4>${v.length ? "" : `<a href="${pageAddr("sql", d)}">Find an SQL entry</a>`}</div>
      ${v.length ? rows + changed + einv + (ro ? "" : `<div class="note">Linked by mistake? Unlink puts the voucher back under SQL entries not linked, and the amount and paid date back to what they were.</div>`)
        : `<div class="note">No SQL voucher is linked to this payment.</div>`}</div>`;
  }
  const total = p.bank_total || 0, gap = p.amount == null || estimateShort(p) ? 0 : p.amount - total;
  const bank = `<div class="pd-box"><div class="pd-box-h">${icon("bank")}<h4>Bank statement</h4><a href="${pageAddr("bank", d)}">Bank and reconciliation</a></div>
    ${lines.length ? `<ul class="pd-lines">${lines.map(l => `<li><span>${esc(shortDate(l.txn_date))} · ${esc(l.description.split(" | ").slice(0, 2).join(" "))}</span><span class="num">${(l.amount > 0) === (p.direction === "out") ? "−" : ""}${esc(money(Math.abs(l.amount), cur))}</span></li>`).join("")}</ul>` : ""}
    ${lines.length > 1 || (lines.length && gap > 0.01) ? `<div class="pd-sum"><span>${lines.length > 1 ? `The ${lines.length} lines add up to` : "The line adds up to"}</span><b>${esc(foundOf(p))}</b></div>` : ""}
    ${lines.length && gap < -0.01 ? `<div class="note">The bank lines add up to ${esc(money(total, cur))}, ${esc(money(-gap, cur))} more than the amount.</div>` : ""}
    ${lines.length ? "" : `<div class="note">${into ? "No bank credit matched to this yet." : "Not matched to a bank statement line yet."}</div>`}
    ${estimateShort(p) ? `<div class="note" id="pd-est-note">Estimated at ${esc(money(p.planned_amount, cur))}; the bank lines linked so far add up to ${esc(money(p.bank_total, cur))}. If more was sent, link the rest on the Bank and reconciliation page. If not, confirm the amount above; until then the budget counts the estimate.</div>` : ""}</div>`;
  return `<section class="pd-sec" aria-labelledby="pd-links-h"><div class="pd-sec-h">${icon("link")}<h3 id="pd-links-h">Linked records</h3></div>${sql}${bank}</section>`;
}
// The details: amount, paid date, bank reference, the voucher or record reference, e-Invoice UIN, the Bank account, notes,
// part paid and the estimate tick.
function pdForm(p, ro) {
  const S = state.pay, d = state.data, e = d.entity, off = ro ? " disabled" : "", cur = p.currency || "MYR", into = p.direction === "in";
  const gap = p.bank_total == null || p.amount == null || estimateShort(p) ? 0 : p.amount - p.bank_total;
  // Every account in use, as Add a payment always offered them, in another currency too (a ringgit bill paid from a
  // foreign currency account); the payment keeps its own currency.
  const accts = pickAccounts({ accounts: pdAccounts() }, p.account_id);
  const acctHint = p.paid_date ? (into ? "The account it was paid into." : "The account it was paid from.") : (into ? "The account it will be paid into." : "The account it will be paid from.");
  const acct = accts.length ? `<div class="field"><label for="pf-acct">Bank account</label><select id="pf-acct" aria-describedby="pd-acct-hint pd-move"${off}>
      ${p.account_id ? "" : `<option value="" selected>Not set</option>`}${accts.map(a => acctOption(a, p.account_id)).join("")}</select>
      <span class="note" id="pd-acct-hint">${acctHint}</span></div>`
    : `<div class="field"><span>Bank account</span><div class="pd-noacct">${pdAccounts().length ? `Every bank account of ${esc(e.code)} is stopped. Start one again, or add one,` : `No bank account is set up for ${esc(e.code)}. Add one`} under <a href="${esc(addrOf({ view: "setup", sub: "accounts" }) || "#/")}">Bank accounts in Setup</a></div></div>`;
  const part = gap > 0.01 ? `<div class="pd-part${p.difference_note ? " noted" : ""}" id="pd-part" data-gap="${esc(money(gap, cur))}"><b>Part paid: ${esc(foundOf(p))}</b>
      <p id="pd-part-note">${p.difference_note ? "The difference is noted, so this payment counts as paid." : `${esc(money(gap, cur))} isn't on the bank statement yet. Match the rest on the Bank and reconciliation page, or note why below.`}</p>
      <label class="field"><span>Why the rest isn't on the bank statement</span><input id="pf-diff" value="${esc(p.difference_note || "")}" placeholder="e.g. balance paid next month" aria-describedby="pd-part-note"${off}></label></div>` : "";
  // The tick only where the payment can be changed; what the estimate is short by is said in the Bank statement box.
  const estTick = !ro && (p.amount_is_estimate || estimateShort(p)) ? `<label class="pd-tick"><input type="checkbox" id="pf-confirm"> The amount above is the real figure, not an estimate</label>` : "";
  return `<form class="pd-form" id="payForm" novalidate aria-labelledby="pd-det-h"><div class="pd-sec-h">${icon("edit")}<h3 id="pd-det-h">Details</h3></div>
    <div id="pd-refused-box" tabindex="-1">${S.refused ? refusedNote(S.refused.text, { title: S.refused.title }) : ""}</div>
    <div class="pd-fields">
      <label class="field"><span>Amount (${esc(cur === "MYR" ? "RM" : cur)})</span><input id="pf-amount" type="number" step="0.01" inputmode="decimal" class="num" value="${p.amount ?? ""}"${off}></label>
      <label class="field"><span>${into ? "Received on" : "Paid on"}</span><input id="pf-paid" type="date" value="${p.paid_date || ""}"${off}></label>
      <label class="field"><span>Bank reference</span><input id="pf-bank" value="${esc(p.bank_ref || "")}" placeholder="From the bank slip"${off}></label>
      <label class="field"><span>${e.uses_sql ? (into ? "SQL OR no." : "SQL PV / JV no.") : "Record ref"}</span><input id="pf-sql" value="${esc(p.sql_ref || "")}" placeholder="${e.uses_sql ? "The voucher no. in SQL" : "Your own reference"}"${off}></label>
      <label class="field"><span>e-Invoice UIN</span><input id="pf-einv" value="${esc(p.einvoice_ref || "")}"${off}></label>
      ${acct}
      <div id="pd-move" class="pd-wide"></div>
      <label class="field pd-wide"><span>Notes</span><input id="pf-notes" value="${esc(p.notes || "")}" placeholder="e.g. why it was paid late"${off}></label>
      ${part ? `<div class="pd-wide">${part}</div>` : ""}
      ${estTick ? `<div class="pd-wide">${estTick}</div>` : ""}
    </div></form>`;
}
// The document viewer beside the dialog: a PDF or an image is shown; any other file can't be (the server only downloads it).
function pdViewer(doc, ro) {
  const S = state.pay, kind = pdKind(doc.original_name), z = +S.zoom || 100, src = `/api/documents/${doc.id}/file`;
  const meta = `${state.meta.doc_types[doc.doc_type] || doc.doc_type}${doc.size != null ? " · " + pdSize(doc.size) : ""} · uploaded ${pdWhen(doc.uploaded_at)}`;
  const shows = kind === "pdf" || kind === "image";
  const zoom = shows ? `<label class="pd-zoom">Zoom <select id="pd-v-zoom" data-pd-zoom="1">${["75", "100", "125", "150"].map(v => `<option value="${v}" ${String(z) === v ? "selected" : ""}>${v}%</option>`).join("")}</select></label>` : "";
  const dl = `<a class="ghost small pd-icon" href="${src}?download=1" download aria-label="Download ${esc(doc.original_name)}" title="Download">${icon("download")}</a>`;
  const C = PD_CANT[kind] || PD_CANT.other;
  // Zoom sets the width of what is shown (pdZoomTo), so changing it never fetches the file again.
  const body = kind === "pdf" ? `<iframe class="pd-frame pd-zoomed" title="Preview of ${esc(doc.original_name)}" src="${src}" style="width:${z}%"></iframe>`
    : kind === "image" ? `<div class="pd-img"><img class="pd-zoomed" src="${src}" alt="${esc(doc.original_name)}" style="width:${z}%"></div>`
    : `<div class="pd-cant" role="status">${stPlate("eyeOff", "warn")}<b>${esc(C[0])}</b><p>${esc(C[1])}</p>
        <div class="state-actions"><a class="btn" href="${src}?download=1" download>${icon("download")}Download</a>${ro ? "" : `<button type="button" class="ghost" data-pd-mi="replace" data-pd-doc="${doc.id}">Replace</button>`}</div></div>`;
  return `<section class="pd-viewer" data-doc="${doc.id}" aria-labelledby="pd-v-title"><div class="pd-v-head">${icon("document")}
      <div class="pd-v-words"><h3 id="pd-v-title" tabindex="-1">${esc(doc.original_name)}</h3><span class="muted">${esc(meta)}</span></div>
      ${zoom}${dl}<button type="button" class="ghost small" data-pd-vclose="1">${icon("close")}Close preview</button></div>
    <div class="pd-v-body">${body}</div></section>`;
}

// ---------- what the dialog does ----------
// The form's live parts: Unsaved changes in the footer, the note when the bank account changes, part paid's note.
function pdLive() {
  if (!state.openPayment || !pdQ("#payForm")) return;
  const p = payOf(state.openPayment), ro = !!state.data?.closed_at;
  const foot = pdQ("#pd-foot");
  if (foot && !ro) foot.textContent = Object.keys(unsavedEdits()).length ? "Unsaved changes" : "";
  const box = pdQ("#pd-move"), sel = pdQ("#pf-acct");
  if (box && sel && p) {
    const to = +sel.value || null, from = p.account_id;
    if (to === from) box.innerHTML = "";
    else {
      const A = pdAccounts(), name = id => A.find(a => a.id === id)?.label || "no account";
      const lines = (p.bank_lines || []).length, sql = state.data.entity.uses_sql && (p.sql_entries || []).length ? p.sql_entries.map(x => x.doc_no).join(", ") : "";
      box.innerHTML = `<div class="pd-movenote" role="note">${icon("bank")}<div><b>Moving it from ${esc(name(from))} to ${esc(name(to))}</b>
        <div>${lines ? `Its line is on the ${esc(name(from))} statement, so saving unlinks it there and looks for it on the ${esc(name(to))} statement instead. ` : ""}Both accounts' reconciliations are checked again when you save.${sql ? ` SQL Account still has ${esc(sql)} on ${esc(name(from))}: correct it there too.` : ""}</div></div></div>`;
    }
  }
  const part = pdQ("#pd-part"), diff = pdQ("#pf-diff"), pn = pdQ("#pd-part-note");
  if (part && diff && pn) {
    const noted = !!diff.value.trim();
    part.classList?.toggle?.("noted", noted);
    pn.textContent = noted ? "The difference is noted, so this payment counts as paid." : `${part.dataset.gap} isn't on the bank statement yet. Match the rest on the Bank and reconciliation page, or note why below.`;
  }
}

// The payment dialog's fields the browser couldn't read: [[id, why]].
const PD_FIELD = { "pf-amount": "Amount", "pf-paid": "Paid on" };
function pdBadFields() {
  const off = id => { const v = pdQ("#" + id)?.validity; return !!v && (v.badInput || v.valid === false); };
  return [["pf-amount", "Write the amount as a number, like 1250.00."], ["pf-paid", "Write the date in full, or leave it empty."]].filter(([id]) => off(id));
}
// Save details: only what was changed is sent (so an untouched estimate stays an estimate). While it saves the button says
// Saving… and the fields wait; a refusal is shown in place, above the fields, with what was typed kept.
async function paySave() {
  const id = state.openPayment, p = payOf(id);
  if (!p || state.data.closed_at) return;
  const S = payUi(id);
  if (S.saving) return;
  // A number or date the browser can't read (12e, a date half typed) reads as empty: it is marked, and nothing is sent,
  // so it is never saved as a blank.
  const bad = pdBadFields();
  if (bad.length) {
    for (const [fid, why] of bad) markField(fid, why);
    S.refused = { text: `${bad.length === 1 ? "1 field needs" : `${bad.length} fields need`} a fix: ${bad.map(([fid]) => PD_FIELD[fid]).join(", ")}.` };
    const box = pdQ("#pd-refused-box"); if (box) box.innerHTML = refusedNote(S.refused.text);
    return pdFocus("#" + bad[0][0]);
  }
  const now = payFormValues(), was = state.payLoaded || {}, changed = {};
  for (const k in now) if (now[k] !== was[k]) changed[k] = now[k];
  if (!Object.keys(changed).length) return toast("Nothing has changed.");
  S.saving = true; S.refused = null; pdBusy(true);
  try { await api(`/api/payments/${id}`, { method: "PATCH", json: changed }); }
  catch (e) {
    S.saving = false; S.refused = { text: changeError(e), title: e.unsure ? "It may not have been saved" : "Nothing was saved" }; pdBusy(false);
    const box = pdQ("#pd-refused-box");
    if (box) { box.innerHTML = refusedNote(S.refused.text, { title: S.refused.title }); box.focus?.(); }
    return;
  }
  S.saving = false; S.histStale = true; state.payLoaded = now;
  // Undo puts back fields that nothing else follows from: references, notes, a paid date typed in. A change of amount,
  // estimate or bank account moves bank lines and figures with it, so it is changed back by hand.
  const plain = ["bank_ref", "sql_ref", "einvoice_ref", "notes", "difference_note", ...(p.paid_source === "manual" || !p.paid_date ? ["paid_date"] : [])];
  const back = Object.keys(changed).every(k => plain.includes(k)) ? Object.fromEntries(Object.keys(changed).map(k => [k, was[k] ?? ""])) : null;
  const moved = "account_id" in changed;
  toast(moved ? "Details saved. Both bank accounts' reconciliations are checked again." : "Details saved", false, back ? { undo: async () => {
    await api(`/api/payments/${id}`, { method: "PATCH", json: back });
    toast("Undone. The details are back as they were; the undo is a new entry in the audit trail.");
    if (state.openPayment === id) state.payLoaded = { ...state.payLoaded, ...back };
    await afterSaved(render);
  } } : undefined);
  const form = pdQ("#payForm");
  const ok = await afterSaved(render);
  // A dialog still open that wasn't drawn again (another page overtook the reading back) is not left saying Saving…
  if (state.openPayment === id && pdQ("#payForm") === form) pdBusy(false);
  if (ok) pdFocus("#pd-save", "#drawerTitle");
}
function pdBusy(on) {
  const f = pdQ("#payForm"), b = pdQ("#pd-save");
  if (f?.querySelectorAll) for (const el of f.querySelectorAll("input, select")) { if (on) { el.dataset.pdWas = el.disabled ? "1" : ""; el.disabled = true; } else el.disabled = el.dataset.pdWas === "1"; }
  if (b) {
    b.disabled = on; b.setAttribute?.("aria-busy", on ? "true" : "false");
    b.innerHTML = on ? `<span class="spin" aria-hidden="true"></span>Saving…` : "Save details";
  }
  if (on) pdFocus("#drawerTitle");   // the focus stays in the dialog while the controls wait
}

// Uploads, one file at a time, each with its own row: its progress, then Added; a file the server refuses (or one that
// can't be sent) keeps its row with the reason. The page is drawn again once, after the last.
function pdUpload(items) {
  const S = state.pay;
  if (!S || !items.length) return;
  const add = items.map(x => {
    const u = { id: ++S.n, file: x.file, type: x.type, replaces: x.replaces || null, pct: 0, st: "up", why: "", net: false };
    if (!PD_TYPES.includes(pdExt(x.file.name))) Object.assign(u, { st: "fail", why: `${pdExt(x.file.name) || "This file type"} isn't accepted. Upload a PDF, image, Excel, Word or email file.` });
    else if (x.file.size > PD_MAX) Object.assign(u, { st: "fail", why: `It is ${pdSize(x.file.size)}; a file can be up to 40 MB.` });
    return u;
  });
  S.ups.push(...add); S.pick = null; S.menu = null; S.ask = null;
  payPaint();
  const bad = add.filter(u => u.st === "fail").length;
  if (bad) toast(bad === 1 ? "1 file couldn't be added. Its row says why." : `${bad} files couldn't be added. Their rows say why.`, true);
  return pdSend(add.filter(u => u.st === "up"));
}
async function pdSend(list) {
  const S = state.pay, pid = state.openPayment;
  let added = 0, unsure = false;
  for (const u of list) {
    try { await pdPost(u, pid); u.st = "ok"; u.pct = 100; added++; }
    catch (e) { unsure ||= !!e.unsure; u.st = "fail"; u.net = !!e.net; u.why = e.net ? "The upload stopped before it finished. Check the records folder can be reached, then try again." : changeError(e); }
    if (state.pay === S) payPaint();
  }
  if (!added) {
    if (unsure && state.view === "entity") await render({ unsure });  // it may be there: the page shows what is
    return;
  }
  const okOnes = list.filter(u => u.st === "ok"), one = okOnes[0];
  S.ups = S.ups.filter(u => u.st !== "ok"); S.histStale = true;
  const said = (one.replaces ? `Replaced with ${one.file.name}` : okOnes.length > 1 ? `Added ${okOnes.length} files` : `Added ${one.file.name}`)
    + (state.pay === S ? "" : ` to ${payOf(pid)?.description || "the payment"}`);
  // Closed, or another payment opened, while it uploaded: the page is drawn again only if it is still that payment's
  // register or its dialog (closed and opened again), and the focus stays wherever it is now.
  const same = state.openPayment === pid && dlgDrawerOpen();
  if (state.pay !== S || !same) {
    if (state.view === "entity" && (!state.openPayment || same)) await afterSaved(render);
    return toast(said);
  }
  const ok = await afterSaved(render);
  toast(said);
  // The dialog was closed because the page couldn't be read back: the files not added are named, as their rows went with it.
  const failed = S.ups.filter(u => u.st === "fail");
  if (!ok && !state.openPayment && failed.length) toast(`Not added: ${failed.map(u => `${u.file.name} (${u.why})`).join("; ")}`, true);
  // Focus moves to the documents only if it isn't in a field being typed in.
  if (ok && state.pay === S && state.openPayment === pid && dlgDrawerOpen() && !document.activeElement?.closest?.("#payForm")) pdFocus(one.replaces ? "" : `#pd-add-${pdSlug(one.type)}`, "#pd-multi", "#drawerTitle");
}
// One file, with its progress shown on its row as it goes (XMLHttpRequest reports it; fetch does not).
function pdPost(u, pid) {
  const fd = new FormData();
  fd.append("file", u.file); fd.append("payment_id", pid); fd.append("doc_type", u.type);
  if (u.replaces) fd.append("replaces", u.replaces);
  if (typeof XMLHttpRequest !== "function") return api("/api/upload", { form: fd });
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/upload"); x.setRequestHeader("X-HRP", "1");
    x.upload.onprogress = ev => {
      if (!ev.lengthComputable) return;
      u.pct = Math.min(99, Math.round(ev.loaded / ev.total * 100));
      const b = pdQ(`#pd-upb-${u.id}`), s = pdQ(`#pd-ups-${u.id}`);
      if (b) { b.setAttribute("aria-valuenow", u.pct); if (b.firstElementChild) b.firstElementChild.style.width = u.pct + "%"; }
      if (s) s.textContent = u.pct + "%";
    };
    x.onload = () => {
      let data = null;
      try { data = JSON.parse(x.responseText); } catch { /* not JSON */ }
      const ok = x.status >= 200 && x.status < 300;
      if (ok && data) resolve(data);
      else if (ok) reject(Object.assign(new Error(BAD_REPLY), { unsure: true }));  // as api(): an OK answer that can't be read is an error
      else reject(Object.assign(new Error(data?.error || (x.status === 413 ? `It is ${pdSize(u.file.size)}; a file can be up to 40 MB.` : `Something went wrong (${x.status}).`)),
        { unsure: x.status >= 500 }));
    };
    x.onerror = () => { const e = new Error("network"); e.net = e.unsure = true; reject(e); };
    x.send(fd);
  });
}

// Escape inside the dialog closes what is on top first: a menu, a question on a row, the files waiting for their type, the
// viewer. True when it closed one of those (the dialog itself stays).
function payEscape() {
  const S = state.pay;
  if (!S || !state.openPayment || !dlgDrawerOpen()) return false;
  if (S.menu) { const k = S.menu; S.menu = null; payPaint(`#pd-mb-${k}`, "#drawerTitle"); return true; }
  if (S.ask) { const k = `doc-${S.ask.doc}`; S.ask = null; payPaint(`#pd-mb-${k}`, "#drawerTitle"); return true; }
  if (S.pick) { S.pick = null; payPaint("#pd-multi", "#drawerTitle"); return true; }
  if (S.viewer) { const v = S.viewer; S.viewer = null; payPaint(`#pd-vw-${v}`, "#drawerTitle"); return true; }
  return false;
}

// The dialog's own buttons (core/events.js sends each click here first). True when the click was one of them.
async function payClick(t, ds) {
  const S = state.pay;
  if (ds.pdClose) { await closeDrawer(); return true; }
  if (ds.npDir) { npDir(ds.npDir); return true; }
  if (!S || !state.openPayment) return false;
  const p = payOf(state.openPayment);
  if (ds.pdView) {
    const id = +ds.pdView;
    S.viewer = S.viewer === id ? null : id; S.menu = null;
    payPaint(S.viewer ? "#pd-v-title" : `#pd-vw-${id}`, "#drawerTitle");
    return true;
  }
  if (ds.pdVclose) { const v = S.viewer; S.viewer = null; payPaint(`#pd-vw-${v}`, "#drawerTitle"); return true; }
  if (ds.pdMenu) { const k = ds.pdMenu; S.menu = S.menu === k ? null : k; S.ask = null; payPaint(S.menu ? `#pd-mb-${k} ~ .pd-menu [role=menuitem]` : `#pd-mb-${k}`); return true; }
  if (ds.pdMi) {
    S.menu = null;
    if (ds.pdMi === "copy") { payPaint(); const files = await pickFile(true); if (files.length) await pdUpload(files.map(file => ({ file, type: ds.pdType }))); return true; }
    const doc = p?.documents.find(x => x.id === +ds.pdDoc);
    if (!doc) return true;
    if (ds.pdMi === "remove") { S.ask = { act: "remove", doc: doc.id }; S.viewer = null; payPaint("#pd-ask-no"); return true; }
    const [file] = await pickFile(false);
    if (!file) { payPaint(`#pd-mb-doc-${doc.id}`, "#drawerTitle"); return true; }
    S.ask = { act: "replace", doc: doc.id, file }; S.viewer = null; payPaint("#pd-ask-no");
    return true;
  }
  if (ds.pdAsk) {
    const A = S.ask; S.ask = null;
    if (!A || ds.pdAsk === "no") { payPaint(A ? `#pd-mb-doc-${A.doc}` : "", "#drawerTitle"); return true; }
    const doc = p?.documents.find(x => x.id === A.doc);
    if (!doc) { payPaint(); return true; }
    if (A.act === "replace") { await pdUpload([{ file: A.file, type: doc.doc_type, replaces: doc.id }]); return true; }
    try { await api(`/api/documents/${doc.id}/remove`, { json: {} }); }
    catch (e) { payPaint(); toast(changeError(e), true); return true; }
    const ok = await afterSaved(render);
    toast(`Removed ${doc.original_name}`);
    if (ok) pdFocus(`#pd-add-${pdSlug(doc.doc_type)}`, `#pd-up-${pdSlug(doc.doc_type)}`, "#drawerTitle");
    return true;
  }
  if (ds.pdMulti) {
    const files = await pickFile(true);
    if (!files.length) return true;
    pdAskTypes(p, files);
    return true;
  }
  if (ds.pdPick) {
    if (ds.pdPick === "cancel") { S.pick = null; payPaint("#pd-multi", "#drawerTitle"); return true; }
    await pdUpload(S.pick || []);
    return true;
  }
  if (ds.pdDismiss) { S.ups = S.ups.filter(u => u.id !== +ds.pdDismiss); payPaint("#pd-multi", "#drawerTitle"); return true; }
  if (ds.pdRetry) {
    const u = S.ups.find(x => x.id === +ds.pdRetry);
    if (u) { Object.assign(u, { st: "up", pct: 0, why: "", net: false }); payPaint(); await pdSend([u]); }
    return true;
  }
  return false;
}
// Files dropped anywhere in the dialog but a document box, or picked with Upload several files: each waits with a first
// guess at its type until Upload.
function pdAskTypes(p, files) {
  const S = state.pay, keys = [...p.required, ...pdExtraTypes(p).filter(t => !p.required.includes(t))];
  S.pick = files.map(file => ({ file, type: pdGuess(file.name, keys) })); S.menu = null; S.ask = null;
  payPaint("#pd-pk-0");
}
// Arrow keys, Home and End in an open menu; Tab closes it; the arrow keys on its button open it.
function pdMenuKey(ev) {
  const S = state.pay, t = ev.target;
  if (!S || !state.openPayment) return;
  if (t.dataset?.pdMenu && (ev.key === "ArrowDown" || ev.key === "ArrowUp")) {
    ev.preventDefault();
    if (S.menu !== t.dataset.pdMenu) { S.menu = t.dataset.pdMenu; payPaint(`#pd-mb-${S.menu} ~ .pd-menu [role=menuitem]`); }
    else pdFocus(`#pd-mb-${S.menu} ~ .pd-menu [role=menuitem]`);
    return;
  }
  if (t.getAttribute?.("role") !== "menuitem" || !t.closest?.(".pd-menu")) return;
  const items = [...t.closest(".pd-menu").querySelectorAll('[role="menuitem"]')], i = items.indexOf(t);
  if (ev.key === "Tab") { const k = S.menu; S.menu = null; ev.preventDefault(); payPaint(`#pd-mb-${k}`); return; }
  const to = ev.key === "ArrowDown" ? (i + 1) % items.length : ev.key === "ArrowUp" ? (i <= 0 ? items.length - 1 : i - 1) : ev.key === "Home" ? 0 : ev.key === "End" ? items.length - 1 : -1;
  if (to < 0) return;
  ev.preventDefault(); items[to].focus();
}

// ---------- Add a payment: the New payment dialog ----------
const NP_LABEL = { co: "Company", desc: "Description", type: "Type", amt: "Amount", due: "Due date", acct: "Bank account" };
// An amount as typed (1,250.00, RM 1250, or blank): the number, null for blank, NaN when it isn't one.
function npAmount(s) {
  const t = String(s || "").trim().replace(/^(RM|[A-Z]{3})\s*/i, "");
  if (!t) return null;
  if (!/^(\d{1,3}(,\d{3})+|\d*)(\.\d*)?$/.test(t) || !/\d/.test(t)) return NaN;
  return Math.round(parseFloat(t.replace(/,/g, "")) * 100) / 100;
}
// From the Overview (slice 1) the dialog asks which company the payment is for: a payment belongs to one company's month, and its
// bank accounts follow the company chosen. The switcher's company is chosen to start with; with All companies, none is.
const npFromOverview = () => state.view === "overview";
const npEnt = () => npFromOverview() ? state.meta.entities.find(x => x.id === state.np?.co) || null : ent();
const npAcctOptions = e => { const accts = pickAccounts(e), acct = defaultAccount(e);
  return accts.map(a => acctOption(a, acct?.id)).join("") || `<option value="">${e ? "No bank account set up yet" : "Choose a company first"}</option>`; };
function npCompany(id) {
  const N = state.np;
  if (!N) return;
  N.co = id ? +id : null;
  const e = npEnt(), sel = $("#ap-acct");
  if (sel) { sel.innerHTML = npAcctOptions(e); sel.disabled = !pickAccounts(e).length; }
  const eb = pdQ("#np-eyebrow"); if (eb) eb.textContent = `From the Overview${e ? ` · ${e.code}` : ""} · ${monthName(state.month)}`;
  N.acct0 = String($("#ap-acct")?.value || "");
}
async function addPaymentDrawer() {
  if (!(await mayLeave())) return;
  state.openPayment = null; state.pay = null; state.drawerDirty = null;
  const fromOv = npFromOverview(), co = fromOv ? (state.addr.all ? null : state.entity) : state.entity;
  state.np = { dir: "out", tried: false, refused: null, saving: false, co };
  const e = npEnt(), acct = defaultAccount(e), accts = pickAccounts(e);
  const today = dayKey(), cur = acct?.currency || "MYR";
  const live = (state.meta.entities || []).filter(isActive);
  const coField = fromOv ? `<div class="field"><label for="ap-co">Company <span class="req">Required</span></label>
        <select id="ap-co" aria-required="true" aria-describedby="np-co-hint"><option value="" disabled${co ? "" : " selected"}>Choose a company</option>${live.map(x =>
          `<option value="${x.id}"${x.id === co ? " selected" : ""}>${esc(x.code)} · ${esc(keptLabel(x))}</option>`).join("")}</select>
        <span class="note" id="np-co-hint">A payment belongs to one company's month. Its bank accounts follow.</span></div>` : "";
  $("#drawer").innerHTML = `<form class="np" id="addForm" novalidate aria-describedby="np-sub">
    <div class="pd-head"><span class="plate brand">${icon("payment")}</span>
      <div class="pd-words"><span class="eyebrow" id="np-eyebrow">${fromOv ? `From the Overview${e ? ` · ${esc(e.code)}` : ""}` : esc(e.code)} · ${esc(monthName(state.month))}</span>
        <h2 id="drawerTitle" tabindex="-1">New payment</h2>
        <span id="np-sub" class="pd-sub">For one-off bills and money in, not coming from a request.</span></div>
      <button type="button" class="ghost small pd-x" id="closeDrawer" aria-label="Close">${icon("close")}</button></div>
    <div class="np-body">
      <div id="np-refused" tabindex="-1"></div><div id="np-summary"></div>
      ${coField}
      <div class="field"><label for="ap-desc">Description <span class="req">Required</span></label>
        <input id="ap-desc" autocomplete="off" aria-required="true" placeholder="What it is, and who it is to or from"></div>
      <div class="field"><span id="np-dir-l">Money</span>
        <div class="seg np-dir" role="group" aria-labelledby="np-dir-l" aria-describedby="np-dir-hint">
          <button type="button" id="np-dir-out" data-np-dir="out" aria-pressed="true">${icon("arrow")}Paid out</button>
          <button type="button" id="np-dir-in" data-np-dir="in" aria-pressed="false">${icon("coins")}Received</button></div>
        <span class="note" id="np-dir-hint">Type lists the payment types for money paid out.</span></div>
      <div class="field"><label for="ap-cat">Type <span class="req">Required</span></label>
        <select id="ap-cat" aria-required="true" aria-describedby="np-type-hint">${typeOptions(npDefault("out"), "out")}</select>
        <span class="note" id="np-type-hint">The types in use, in the order Setup › Payment types lists them.</span></div>
      <div class="field"><label for="ap-amt">Amount (<span id="np-cur">${esc(cur === "MYR" ? "RM" : cur)}</span>)</label>
        <input id="ap-amt" inputmode="decimal" class="num" autocomplete="off" placeholder="0.00" aria-describedby="np-amt-hint">
        <span class="note" id="np-amt-hint">Leave blank if you don't know it yet.</span></div>
      <div class="field"><label for="ap-due">Due date</label><input id="ap-due" type="date" aria-describedby="np-due-hint">
        <span class="note" id="np-due-hint">Blank means today, ${esc(shortDate(today))}.</span></div>
      <div class="field"><label for="ap-acct">Bank account</label>
        <select id="ap-acct" aria-describedby="np-acct-hint"${accts.length ? "" : " disabled"}>${npAcctOptions(e)}</select>
        <span class="note" id="np-acct-hint"></span></div>
    </div>
    <div class="pd-foot"><span id="np-foot" class="pd-foot-note"></span>
      <div class="pd-foot-acts"><button type="button" class="ghost" id="np-cancel" data-pd-close="1">Cancel</button>
        <button type="submit" class="btn" id="np-submit" aria-describedby="np-foot">${icon("plus")}Add payment</button></div></div>
  </form>`;
  showDrawer("new");
  watchDrawer();
  // Unsaved means something typed or chosen by hand: Paid out / Received alone (which sets the type to that way's
  // default) is not, so it never asks "Discard this payment?".
  // The account is compared with what its picker started on (a company whose only account is stopped starts on none).
  // From the Overview a company chosen by hand is unsaved too; its accounts then start on that company's usual one.
  state.np.acct0 = String($("#ap-acct")?.value || "");
  state.drawerDirty = () => !!state.np && (!!$("#ap-desc")?.value.trim() || !!$("#ap-amt")?.value.trim() || !!$("#ap-due")?.value
    || ($("#ap-cat")?.value || "") !== npDefault(state.np.dir) || String($("#ap-acct")?.value || "") !== state.np.acct0 || (fromOv && state.np.co !== co));
  npFoot();
}
// The type a new payment starts on, as the drawer before had it: a one-off going out starts as a claim when claims are in
// use (oneOffType), money in as Money received (defaultType).
const npDefault = dir => dir === "in" ? defaultType("in") : oneOffType();
const npAcct = () => { const v = +($("#ap-acct")?.value || 0); return (npEnt()?.accounts || []).find(a => a.id === v) || null; };
// What is wrong with the form now: {field: message}.
function npErrors() {
  const out = {}, cat = $("#ap-cat")?.value;
  if (npFromOverview() && !npEnt()) out.co = "Choose a company.";
  if (!$("#ap-desc")?.value.trim()) out.desc = "Give the payment a description.";
  if (!cat || !catActive(cat) || catDir(cat) !== state.np.dir) out.type = "Choose one of the payment types in use.";
  if (Number.isNaN(npAmount($("#ap-amt")?.value))) out.amt = "Write the amount as a number, like 1250.00.";
  const due = $("#ap-due")?.validity;
  if (due && (due.badInput || due.valid === false)) out.due = "Write the due date in full, or leave it empty.";
  return out;
}
// The footer's note and the hints that follow what is chosen; once Add was tried, the fields that need a fix are marked.
function npFoot() {
  const N = state.np;
  if (!N || !pdQ("#addForm")) return;
  const errs = npErrors(), bad = Object.keys(errs), a = npAcct(), cur = a?.currency || "MYR", e = npEnt();
  const curEl = pdQ("#np-cur"); if (curEl) curEl.textContent = cur === "MYR" ? "RM" : cur;
  const ah = pdQ("#np-acct-hint");
  if (ah) ah.textContent = !e ? "The accounts show once a company is chosen." : !(e.accounts || []).some(isActive) ? `${e.code} has no bank account yet, so the payment is added without one.` : N.dir === "in" ? "The account the money comes into." : "The account the money goes out from.";
  const foot = pdQ("#np-foot");
  if (foot) foot.textContent = N.saving ? `Adding the payment to ${e ? `${e.code}'s ` : ""}${monthName(state.month)}…`
    : N.refused ? N.unsure ? "It isn't known whether it was added: check the month's payments before adding it again." : "Nothing was added. Fix what the message says, then add it again."
    : !bad.length ? "It is added as not paid yet." : N.tried ? "Fix the fields above, then add it." : `Still needed: ${bad.map(k => k === "amt" ? "A valid amount" : NP_LABEL[k]).join(", ")}.`;
  const sub = pdQ("#np-submit"); if (sub) sub.setAttribute?.("aria-disabled", bad.length ? "true" : "false");
  if (!N.tried) return;
  const ids = { co: "ap-co", desc: "ap-desc", type: "ap-cat", amt: "ap-amt", due: "ap-due" };
  for (const [k, id] of Object.entries(ids)) {
    const el = pdQ("#" + id), had = el?.getAttribute?.("aria-invalid") === "true";
    if (k === "co" && !npFromOverview()) continue;
    if (errs[k] && !had) markField(id, errs[k]); else if (!errs[k] && had) { markField(id, ""); }
    if (!errs[k] && el) el.setAttribute?.("aria-describedby", { co: "np-co-hint", desc: "", type: "np-type-hint", amt: "np-amt-hint", due: "np-due-hint" }[k]);
  }
  const sum = pdQ("#np-summary");
  if (sum) sum.innerHTML = bad.length && !N.refused ? `<div class="refused" role="alert">${icon("alert")}<span><b>${bad.length === 1 ? "1 field needs a fix." : `${bad.length} fields need a fix.`}</b> ${esc(bad.map(k => NP_LABEL[k]).join(", "))}.</span></div>` : "";
}
// Paid out or Received: Type then lists the types going that way (the one chosen stays if it goes that way too).
function npDir(dir) {
  const N = state.np;
  if (!N || N.saving || !["in", "out"].includes(dir) || N.dir === dir) return;
  N.dir = dir; N.refused = null;
  const sel = $("#ap-cat"), keep = sel && catDir(sel.value) === dir ? sel.value : npDefault(dir);
  if (sel) sel.innerHTML = typeOptions(keep, dir);
  for (const k of ["out", "in"]) pdQ(`#np-dir-${k}`)?.setAttribute?.("aria-pressed", k === dir ? "true" : "false");
  const h = pdQ("#np-dir-hint"); if (h) h.textContent = dir === "in" ? "Type lists the payment types for money received." : "Type lists the payment types for money paid out.";
  const r = pdQ("#np-refused"); if (r) r.innerHTML = "";
  npFoot();
}
async function npSave() {
  const N = state.np;
  if (!N || N.saving) return;
  N.tried = true; N.refused = null;
  const r0 = pdQ("#np-refused"); if (r0) r0.innerHTML = "";
  const errs = npErrors();
  npFoot();
  const first = ["co", "desc", "type", "amt", "due"].find(k => errs[k]);
  if (first) return pdFocus("#" + { co: "ap-co", desc: "ap-desc", type: "ap-cat", amt: "ap-amt", due: "ap-due" }[first]);
  const a = npAcct(), desc = $("#ap-desc").value.trim(), e = npEnt();
  const body = { entity_id: e.id, month: state.month, description: desc, category: $("#ap-cat").value, direction: N.dir,
    amount: npAmount($("#ap-amt").value), due_date: $("#ap-due").value || null, account_id: a ? a.id : null };
  N.saving = true; npBusy(true); npFoot();
  let r;
  try { r = await api("/api/payments", { json: body }); }
  catch (e) {
    N.saving = false; N.refused = changeError(e); N.unsure = !!e.unsure; npBusy(false); npFoot();
    const box = pdQ("#np-refused");
    if (box) { box.innerHTML = refusedNote(N.refused, { title: e.unsure ? "It may not have been added" : "Nothing was saved" }); box.focus?.(); }
    return;
  }
  const id = r.id;
  await closeDrawer(true);
  state.mark = { pay: x => x.id === id };
  toast(npFromOverview() ? `Payment added to ${e.code}'s ${monthName(state.month)}` : "Payment added", false, { undo: async () => {
    await api(`/api/payments/${id}`, { method: "DELETE", json: {} });
    toast("Undone. The payment is taken off again; the undo is a new entry in the audit trail.");
    await afterSaved(render);
  } });
  const ok = await afterSaved(render);
  const now = document.activeElement;
  if (ok && (!now || now === document.body || now === $("#main"))) pdFocus("#addPayment");   // back on the button that opened it, drawn again
}
function npBusy(on) {
  const f = pdQ("#addForm"), b = pdQ("#np-submit");
  if (f?.querySelectorAll) for (const el of f.querySelectorAll("input, select, button:not([type=submit])")) { if (on) { el.dataset.pdWas = el.disabled ? "1" : ""; el.disabled = true; } else el.disabled = el.dataset.pdWas === "1"; }
  if (b) { b.disabled = on; b.setAttribute?.("aria-busy", on ? "true" : "false"); b.innerHTML = on ? `<span class="spin" aria-hidden="true"></span>Adding…` : `${icon("plus")}Add payment`; }
  if (on) pdFocus("#drawerTitle");
}

// An edit in the payment dialog's form: a refusal was about what was typed then, so it goes (a redraw no longer shows it),
// and so does the mark on the field edited.
function pdEdited(t) {
  if (state.pay?.refused) { state.pay.refused = null; const box = pdQ("#pd-refused-box"); if (box) box.innerHTML = ""; }
  if (t?.id && t.getAttribute?.("aria-invalid") === "true") markField(t.id, "");
  pdLive();
}
// An edit in New payment: the server's refusal goes, so the fields' own marks and summary show again.
function npEdited() {
  if (state.np?.refused) { state.np.refused = null; const box = pdQ("#np-refused"); if (box) box.innerHTML = ""; }
  npFoot();
}

// ---------- the dialog's listeners ----------
if (document.addEventListener) {
  // A click anywhere but an open menu closes it (taken off in place, so what was clicked stays where it is).
  document.addEventListener("click", ev => {
    const S = state.pay;
    if (!S?.menu || ev.target?.closest?.(".pd-mw")) return;
    const k = S.menu; S.menu = null;
    pdQ(".pd-menu")?.remove?.();
    pdQ(`#pd-mb-${k}`)?.setAttribute?.("aria-expanded", "false");
  });
  document.addEventListener("keydown", pdMenuKey);
  document.addEventListener("input", ev => {
    if (ev.target.closest?.("#payForm")) pdEdited(ev.target);
    if (ev.target.closest?.("#addForm")) npEdited();
  });
  document.addEventListener("change", ev => {
    const t = ev.target;
    if (t.dataset?.pdPk != null && state.pay?.pick) { const x = state.pay.pick[+t.dataset.pdPk]; if (x) x.type = t.value; return; }
    if (t.id === "extraType" && state.pay) { state.pay.xType = t.value; return; }
    if (t.dataset?.pdZoom && state.pay) {   // in place: the file on show is not fetched again
      state.pay.zoom = ["75", "100", "125", "150"].includes(t.value) ? t.value : "100";
      const z = pdQ(".pd-viewer .pd-zoomed"); if (z) z.style.width = state.pay.zoom + "%";
      return;
    }
    if (t.closest?.("#payForm")) pdEdited(t);
    if (t.id === "ap-co") npCompany(t.value);
    if (t.closest?.("#addForm")) npEdited();
  });
}
