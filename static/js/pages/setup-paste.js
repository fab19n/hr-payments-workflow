"use strict";
/* ---- Paste a list (customers and suppliers, the chart of accounts) ---- */
// How the server split the pasted text into columns.
const PASTE_HOW = { tab: "columns separated by tabs", pipe: "columns separated by |", semicolon: "columns separated by ;", comma: "columns separated by commas",
  fixed: "columns lined up with spaces", sql: "a grid copied from SQL Account", report: "a report printed from SQL Account",
  one: "one column (no separator found)" };
// "12 added, 3 changed, 1 skipped" (a save), or what a preview would do.
function pasteCounts(c = {}, preview) {
  const n = k => +c[k] || 0, out = [];
  if (preview) {
    if (n("add")) out.push(`${n("add")} new`);
    if (n("update")) out.push(`${n("update")} to change`);
    if (n("same")) out.push(`${n("same")} already the same`);
    if (n("error")) out.push(`${plural(n("error"), "problem")} (skipped)`);
    return out.join(", ") || "No rows found.";
  }
  if (n("add")) out.push(`${n("add")} added`);
  if (n("update")) out.push(`${n("update")} changed`);
  if (n("error")) out.push(`${n("error")} skipped`);
  return out.length ? out.join(", ") : "Nothing changed: every row was already the same";
}

// The drawer: paste the text, Read the list (a preview, nothing saved), check the columns and each row, then Save.
async function openPaste(kind, { force = false } = {}) {
  if (!force && !(await mayLeave())) return;
  const spec = state.setup.types?.kinds?.[kind], e = ent();
  if (!spec) return;
  if (spec.per_entity && !e) return toast("Add a company first.", true);
  state.openPayment = null; state.why = null;
  Object.assign(state.setup, { drawer: null, chkOpen: null, remOpen: null, paste: { kind, preview: null, seq: 0 } });
  const parties = kind === "parties";
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">${esc(spec.label)}${e ? " · " + esc(e.code) : ""}</div><h2>Paste a list</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <form class="form setup-form" id="pasteForm">
      <div class="note" style="grid-column:1/-1">In SQL Account, open Maintain Customer (or Supplier, or Account), click a row, press <b>Ctrl+A</b> then <b>Ctrl+C</b>, and paste below. A text file exported from SQL Account, or a list from Excel, works too: columns separated by tabs, commas, | or spaces.</div>
      <label class="field" style="grid-column:1/-1"><span>The list</span><textarea id="ps-text" rows="8" class="mono" spellcheck="false" autocomplete="off" placeholder="Paste the rows here"></textarea>
        <span class="note">Rows are matched by their code: a new code is added, one already here is updated. Empty cells change nothing, and nothing missing from the list is stopped or deleted.</span></label>
      ${parties ? `<label class="field"><span>For</span><select id="ps-scope"><option value="company">This company${e ? ` (${esc(e.code)})` : ""}</option><option value="all">Every company</option></select></label>
      <label class="field"><span>These are</span><select id="ps-kind"><option value="customer">Customers</option><option value="supplier">Suppliers</option><option value="related">Related companies</option>
        <option value="statutory">Statutory bodies</option><option value="">From a Kind column</option></select></label>` : ""}
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-paste-read="1">Read the list</button></div>
      <div id="ps-preview" class="paste-out" style="grid-column:1/-1"></div>
      <label class="field" style="grid-column:1/-1"><span>Why are you making this change? (optional)</span><input id="ps-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit" id="ps-save" disabled>Save</button><span class="note" id="ps-save-note">Read the list first.</span></div></form>`;
  showDrawer();
  watchDrawer();
  $("#ps-text").focus();
}

// What the paste form says now: the text, who it is for and what they are (a preview is only good for these).
function pasteForm() {
  return { text: $("#ps-text")?.value ?? "", scope: $("#ps-scope")?.value ?? null, kind: $("#ps-kind")?.value ?? null };
}
const pasteSameForm = (a, b) => !!a && !!b && a.text === b.text && a.scope === b.scope && a.kind === b.kind;
// Save is only for a preview of the form as it is now, with no message, that adds or changes at least one row.
function pasteCanSave(P) {
  const p = P?.preview;
  if (!p || p.message || !pasteSameForm(P.previewFor, pasteForm())) return false;
  const c = p.counts || {};
  return (+c.add || 0) + (+c.update || 0) > 0 || (p.rows || []).some(r => r.action === "add" || r.action === "update");
}
// The Save button and the note beside it (also while a column picked by hand is read again).
function paintPasteSave(reading = false) {
  const P = state.setup.paste, p = P?.preview, btn = $("#ps-save"), note = $("#ps-save-note");
  if (!btn || !note) return;
  const ok = !reading && pasteCanSave(P);
  btn.disabled = !ok;
  note.hidden = ok;
  note.textContent = reading ? "Reading the list again…" : !p ? "Read the list first."
    : p.message ? "Choose the right columns above first." : "Nothing to add or change.";
}

// The preview of what Save would do: how the text was read, a column picker per field, the counts, and each row.
function paintPaste() {
  const p = state.setup.paste?.preview, box = $("#ps-preview");
  if (!box) return;
  paintPasteSave();
  if (!p) { box.innerHTML = ""; return; }
  const headers = p.headers || [], rows = p.rows || [], mapping = p.mapping || {};
  const colOpts = sel => `<option value="">(none)</option>` + headers.map((h, i) => `<option value="${i}" ${sel != null && sel !== "" && i === +sel ? "selected" : ""}>${esc(h || "Column " + (i + 1))}</option>`).join("");
  const shown = v => v == null || v === "" ? "—" : Array.isArray(v) ? v.join(", ") : String(v);
  const what = r => {
    const msg = r.message ? `<div class="note">${esc(r.message)}</div>` : "";
    if (r.action === "add") return `<span class="pill ok">New</span>${msg}`;
    if (r.action === "update") return `<span class="pill warn">Changes</span>${(r.changes || []).map(([label, was, now]) =>
      `<div class="note">${esc(label)}: ${esc(shown(was))} → ${esc(shown(now))}</div>`).join("")}${msg}`;
    if (r.action === "same") return `<span class="pill grey">Same</span>${msg}`;
    return `<span class="pill bad">Problem</span>${msg}`;
  };
  const table = list => `<div class="tbl-wrap"><table><thead><tr><th class="num">Row</th><th>Code</th><th>Name</th><th>What happens</th></tr></thead><tbody>
    ${list.map(r => `<tr><td class="num">${esc(r.row ?? "")}</td><td class="mono">${esc(r.code || "—")}</td><td>${esc(r.name || "—")}</td><td>${what(r)}</td></tr>`).join("")}</tbody></table></div>`;
  const same = rows.filter(r => r.action === "same"), others = rows.filter(r => r.action !== "same");
  box.innerHTML = `<div class="card paste-preview"><h3>Preview: nothing is saved yet</h3>
    <div class="note">Read as: ${esc(PASTE_HOW[p.how] || p.how || "columns")}${p.header_row === -1 ? ", with no heading row" : ""}${p.read_note ? `. ${esc(p.read_note)}` : "."} If a column was read wrongly, choose the right one below.</div>
    <div class="form">${(p.fields || []).map(f => `<label class="field"><span>${esc(f.label)}${f.required ? " (needed)" : ""}</span><select data-paste-map="${esc(f.key)}">${colOpts(mapping[f.key])}</select></label>`).join("")}</div>
    ${p.message ? `<div class="note warn"><b>${esc(p.message)}</b></div>` : `<div class="note"><b>${esc(pasteCounts(p.counts, true))}</b></div>`}
    ${others.length ? table(others) : ""}
    ${same.length ? `<details><summary>${esc(plural(same.length, "row"))} already the same</summary>${table(same)}</details>` : ""}</div>`;
}

// Read the list (preview: true) or Save it. The text goes every time; the columns as last read (or as just picked: over).
async function pasteSave(preview, over = {}) {
  const P = state.setup.paste;
  if (!P || !$("#pasteForm")) return;
  const form = pasteForm(), text = form.text;
  if (!text.trim()) { $("#ps-text").focus(); return toast("Paste the list first.", true); }
  if (!preview) {
    if (!P.preview || !pasteSameForm(P.previewFor, form)) return toast("Read the list first, and check what happens to each row.", true);
    if (P.preview.message) return toast(P.preview.message, true);
    if (!pasteCanSave(P)) return toast("Nothing to add or change.", true);
  }
  const base = over.base || P.preview;
  const body = { entity_id: state.entity, text, preview: !!preview, header_row: base?.header_row ?? null, mapping: base?.mapping ?? null, ...over };
  delete body.base;
  if (P.kind === "parties") { body.scope = form.scope; body.kind = form.kind || null; }
  const reason = $("#ps-reason").value.trim();
  if (reason) body.reason = reason;
  if (preview) {
    // Each read is numbered: only the latest counts, and only while the form still says what it was read for.
    const seq = P.seq = (P.seq || 0) + 1;
    const current = () => state.setup.paste === P && P.seq === seq && pasteSameForm(form, pasteForm());
    let r;
    try { r = await api(`/api/setup/${P.kind}/paste`, { json: body }); }
    catch (e) { if (!current()) return; paintPaste(); throw e; }  // nor does a stale read's failure say anything
    if (!current()) return;  // changed (or read again) while it was read: that preview is stale
    P.preview = r; P.previewFor = form; return paintPaste();
  }
  const still = suDialog(() => state.setup.paste), r = await api(`/api/setup/${P.kind}/paste`, { json: body });
  if (r.message) return toast(r.message, true);  // nothing was saved: the drawer stays open
  const kind = P.kind;
  toast(pasteCounts(r.counts));
  if (still()) closeDrawer(true);  // a dialog opened meanwhile is left alone
  return afterSaved(async o => { await afterSetupChange(kind); return render(o); });
}

// General settings: one form; Save sends only what changed.
async function setupSettings(box) {
  const s = await api("/api/setup/settings");
  if (!(box = setupBox(box))) return;
  const fields = s.fields || setupSpec()?.fields || [];
  box.innerHTML = `${setupHead("settings", setupSpec(), { intro: "These apply to every company. Each change is kept in the audit trail." })}
    <div class="card"><form class="form setup-form" id="settingsForm">${fields.map(f => fieldHtml(f, s.values?.[f.key], null, "gs-")).join("")}
      <label class="field" style="grid-column:1/-1"><span>Why are you making this change? (optional)</span><input id="gs-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">Save</button></div></form></div>`;
  state.setup.settings = { fields, loaded: formValues(fields, "gs-") };
}
async function settingsSave() {
  const G = state.setup.settings;
  if (!G) return;
  const now = formValues(G.fields, "gs-"), values = {};
  for (const k in now) if (JSON.stringify(now[k]) !== JSON.stringify(G.loaded[k])) values[k] = now[k];
  if (!Object.keys(values).length) return toast("Nothing has changed.");
  const reason = $("#gs-reason").value.trim(), body = { values };
  if (reason) body.reason = reason;
  const was = currentCycle();
  await api("/api/setup/settings", { method: "PATCH", json: body });
  toast("Saved");
  return afterSaved(async o => {
    state.meta = await readMeta(); paintOrg();
    if ("cycle_rollover_day" in values && currentCycle() !== was) {
      if (state.month === was) state.month = currentCycle();
      await openCycleMonths();
    }
    renderNav();
    return render(o);
  });
}

/* Move setup: this install's setup saved as one file (setup.json) to start another install with, and such a file imported into
   records that hold no company yet (hrp/setupfile.py). The template holds the rules only; everything adds the companies and what
   belongs to them, and the recurring payments only when ticked. Saving one is an ordinary download (the server notes it in the audit
   trail); an import is previewed first and asks why. The counts of a file come from the server's own reading of it (stopped records
   are in the file, deleted ones are gone), and First run (pages/firstrun.js) draws the same counts the same way. */
// A signed-off bank reconciliation month an action moved, said after its toast (it stays signed off).
const reconMoved = r => r.recon_changed?.length ? `. The bank reconciliation of signed-off ${r.recon_changed.map(m => monthName(m.month)).join(", ")} changed: it stays signed off; check it again` : "";
const moveHref = (what, extra) => `/api/setup/export?what=${what}${extra}`;
// What the Export buttons say once clicked (the file is saved by the browser; the server notes it in the audit trail).
const moveExportNote = what => `Setup ${what === "template" ? "template" : "everything"} ${dayKey()}.json is downloading${what === "full" && state.setup.move?.payees ? ", with recurring payments" : ""}. It is noted in the audit trail.`;
// What a setup file adds, as the server counts it (setupfile.load): the lists with something in them, with a capital.
const moveCounts = p => (p.counts || []).filter(([, n]) => +n).map(([w, n]) => [w.charAt(0).toUpperCase() + w.slice(1), +n]);
const moveCountsTable = p => `<div class="tbl-wrap"><table class="st-table st-counts"><thead><tr><th scope="col">What</th><th scope="col" class="num">How many</th></tr></thead><tbody>${moveCounts(p).map(([w, n]) => `<tr><td>${esc(w)}</td><td class="num">${n}</td></tr>`).join("")}</tbody></table></div>`;
// A file the server would not take: its reason, and that nothing was added.
const moveRefusal = (name, why) => `<div class="refused" role="alert" id="mv-refused">${icon("alert")}<div class="refused-text"><b>${esc(name || "That file")} can't be imported.</b><div class="refused-why">${esc(why)} Nothing was added.</div></div></div>`;
// A setup file read and previewed (nothing is saved): {setup, preview}. A file that is not JSON says so; one the server refuses
// carries refused = true, with the server's sentence.
async function readSetupFile(f) {
  let setup;
  try { setup = JSON.parse(await f.text()); } catch { throw new Error("That file can't be read as a setup file. Choose a file saved with Export template or Export everything in Move setup."); }
  try { return { setup, preview: await api("/api/setup/import", { json: { setup, preview: true } }) }; }
  catch (e) { if (appStopped(e)) throw e; e.refused = true; throw e; }
}
async function setupMove(box) {
  const st = await api("/api/setup/import");
  if (!(box = setupBox(box))) return;
  const M = state.setup.move ||= { payees: false, from: "", preview: null, refused: "" };
  M.empty = !!st.empty; M.holding = st.holding || [];
  const said = !!M.justImported; M.justImported = false;  // the link to the companies it added is for the redraw right after an import, once
  const list = state.meta.entities || [];
  box.innerHTML = `${setupHead("move", setupSpec(), { intro: "Save this install's setup as a file, to start another install with it. Each file saved is noted in the audit trail." })}
    <section class="card st-move" aria-labelledby="mv-exp-h"><div class="row tight st-sec-head">${icon("download")}<h2 id="mv-exp-h">Export</h2></div>
      <div class="st-move-grid">
        <div class="st-panel"><div class="row tight"><span class="plate brand">${icon("copy")}</span><h3>Template</h3></div>
          <p class="note">The rules only: payment types, document types and the documents each needs, a starter checklist, the joiner and leaver reminders, the matching words and the general settings. No company, bank account, customer, supplier or person.</p>
          <label class="field"><span>Starter checklist</span><select id="mv-from" aria-describedby="mv-from-hint"><option value="">The one new companies get here</option>${list.map(e => `<option value="${e.id}"${String(e.id) === M.from ? " selected" : ""}>${esc(e.code)} · ${esc(e.name)}'s checklist</option>`).join("")}</select>
            <span class="note" id="mv-from-hint">Companies added in the other install start with it.</span></label>
          <div class="row"><a class="btn" id="mvTemplate" data-move-export="template" href="${esc(moveHref("template", M.from ? `&entity=${M.from}` : ""))}">${icon("download")}Export template</a></div></div>
        <div class="st-panel"><div class="row tight"><span class="plate brand">${icon("archive")}</span><h3>Everything</h3></div>
          <p class="note">The template, plus the companies, their bank accounts with the account numbers, charts of accounts, statutory accounts, customers and suppliers, each company's checklist, what its printed invoices need (address, bank details, logo and signature), and the printed company names confirmed. Keep the file safe.</p>
          <label class="row tight"><input type="checkbox" id="mv-payees"${M.payees ? " checked" : ""} aria-describedby="mv-warn"><span>Include recurring payments (staff names, amounts, bank details)</span></label>
          <div class="note warn" id="mv-warn"${M.payees ? "" : " hidden"}>${icon("lock")} <b>The file then holds personal data</b> (staff names, amounts and bank details). Keep it as safe as a backup and delete it once it has been imported.</div>
          <div class="note" id="mv-never">${icon("eyeOff")} <b>Never in the file:</b> staff records, and the secret behind the keyed check on printed forms. The other install makes its own secret, so a form printed here can't be matched there.</div>
          <div class="row"><a class="btn" id="mvFull" data-move-export="full" href="${esc(moveHref("full", M.payees ? "&payees=1" : ""))}">${icon("download")}Export everything</a></div></div>
      </div></section>
    <section class="card st-move" aria-labelledby="mv-imp-h"><div class="row tight st-sec-head">${icon("upload")}<h2 id="mv-imp-h" tabindex="-1">Import a setup file</h2></div>
      <div id="mvImport">${moveImportHtml(said)}</div></section>`;
}
// The import card: not for an install that holds a company; else Choose a file, what the file adds, and Import.
function moveImportHtml(added = false) {
  const M = state.setup.move;
  if (!M.empty) return `<div class="st-blocked">${icon("lock")}<div><b>Not for this install</b>
    <p class="note">A setup file is imported only into new records, before any company is added. These hold ${esc(andList((M.holding || []).map(([w, n]) => `${n} ${w}`)))}.</p>
    <p class="note">To start another install from this one, export above and import the file there.</p>
    ${added ? `<button type="button" class="ghost small" data-setup-kind="entities">${icon("company")}See the companies it added</button>` : ""}</div></div>`;
  return `<p class="note">For a new install, before any company is added. A template's rules are added to the app's own; everything also adds its companies and what belongs to them. Each row is checked as Setup checks it, and nothing is saved unless every row passes.</p>
    <div id="mvPreview">${movePreviewHtml()}</div>${whyForm()}`;
}
// What the file chosen would add (the server made the import and undid it), with Import and Cancel; or why it can't be imported.
function movePreviewHtml() {
  const M = state.setup.move, p = M?.preview;
  if (!p) return `${M?.refused ? moveRefusal(M.name, M.refused) : ""}<div class="row"><button class="btn" type="button" id="mv-pick" data-move-pick="1">${icon("folder")}${M?.refused ? "Choose another file…" : "Choose a setup file…"}</button></div>`;
  const note = n => `<li>${icon(/^The file holds/.test(n) || /^Left out/.test(n) ? "lock" : "help")}<span>${esc(n)}</span></li>`;
  return `<section class="st-file" aria-labelledby="mv-file-h"><div class="row tight">${icon("document")}<div><h3 id="mv-file-h" tabindex="-1">${esc(M.name)}</h3><span class="note">${p.what === "full" ? "Everything" : "A template"}, saved ${esc(fmtDate(p.made))}. Importing it adds or changes:</span></div></div>
    ${moveCountsTable(p)}<ul class="st-notes-list">${(p.notes || []).map(note).join("")}</ul>
    <div class="row"><button class="btn" type="button" id="mv-import" data-move-go="1">${icon("upload")}Import</button><button class="ghost" type="button" data-move-cancel="1">Cancel</button></div></section>`;
}
const moveRepaint = focus => { const b = $("#mvImport"); if (b) { b.innerHTML = moveImportHtml(); if (focus) document.getElementById(focus)?.focus?.({ preventScroll: true }); } };
async function movePick() {
  const [f] = await pickFile(false);
  if (!f) return;
  const M = state.setup.move;
  Object.assign(M, { name: f.name, preview: null, file: null, refused: "" });
  try { const r = await readSetupFile(f); Object.assign(M, { file: r.setup, preview: r.preview }); }
  catch (e) { if (appStopped(e)) throw e; if (e.refused) M.refused = e.message; else { moveRepaint("mv-pick"); return toast(e.message, true); } }
  moveRepaint(M.preview ? "mv-file-h" : "mv-refused");
}
async function moveImport(reason) {
  const M = state.setup.move;
  if (!M?.file) return;
  try { await api("/api/setup/import", { json: { setup: M.file, reason } }); }
  catch (e) { if (appStopped(e) || e.unsure) throw e; Object.assign(M, { file: null, preview: null, refused: e.message }); moveRepaint("mv-refused"); return; }  // "Nothing was added" only for a refusal
  Object.assign(M, { file: null, preview: null, name: "", refused: "" });
  toast("Setup imported");
  await afterSaved(async o => {
    state.meta = await readMeta(); paintOrg();
    M.justImported = (state.meta.entities || []).length > 0;  // a file of rules alone added no company to see
    state.entity = firstEntityId(); state.setup.types = null;
    renderNav();
    return render(o);
  }, () => document.getElementById("mv-imp-h")?.focus?.({ preventScroll: true }));
}

// The months a set was in force: from from_month until to_month, the month the next set took over (either end open).
function reqRange(h) {
  const from = !h.from_month || h.from_month === "0000-00" ? null : monthName(h.from_month), to = h.to_month ? monthName(shiftMonth(h.to_month, -1)) : null;
  return from && to ? (from === to ? from : `${from} to ${to}`) : from ? `From ${from}` : to ? `Until ${to}` : "From the start";
}

/* Monthly checklist (per company) and joiner and leaver reminders (every company). Each item or reminder has terms: what
   it is from a payroll month on. A change starts from a month you choose: the months before it keep what they had,
   and filed months never change. Every change can be previewed first; the server does it, says what it would do and
   undoes it. */
const ordinal = n => { const v = +n, t = v % 100; return `${v}${t >= 11 && t <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[v % 10] || "th"}`; };
// "Dec 2026"
const monShort = k => /^\d{4}-\d{2}$/.test(k || "") ? `${MONTHS[+k.slice(5) - 1]} ${k.slice(0, 4)}` : "";
// "a, b and c"
const andList = a => a.length < 2 ? a.join("") : `${a.slice(0, -1).join(", ")} and ${a[a.length - 1]}`;
const plural = (n, one, many = one + "s") => `${n} ${+n === 1 ? one : many}`;
// A payments rule as the server keeps it, JSON text or not.
const asRule = v => { if (typeof v !== "string") return v || null; try { return JSON.parse(v); } catch { return null; } };
// "18th of the payroll month", "3rd of the month after"
const dueText = t => t?.due_day ? `${ordinal(t.due_day)} of the ${+t.due_offset ? "month after" : "payroll month"}` : "—";
// "30 days after the start date", "30 days before the last day"
function remDays(days, kind) {
  const d = +days || 0, what = kind === "leaver" ? "the last day" : "the start date";
  return d ? `${plural(Math.abs(d), "day")} ${d < 0 ? "before" : "after"} ${what}` : `On ${what}`;
}
const remSalary = s => s == null || s === "" ? "Any salary" : `Salary over ${money(s)}`;
const builtInPill = r => +r?.system ? `<span class="pill" title="The app relies on it, so it can't be deleted">Built in</span>` : "";
// An item's or reminder's terms, newest first (the one in force now among them).
function terms(x) {
  const hs = [...(x.history || [])];
  if (x.now && !hs.some(h => h.from_month === x.now.from_month)) hs.push(x.now);
  return hs.sort((a, b) => String(b.from_month || "").localeCompare(String(a.from_month || "")));
}
// In use from the latest term on (a stop planned for a later month counts as stopped).
const lastTerm = x => terms(x)[0] || x.now || {};
const termUse = (x, t) => t?.in_use == null ? !!x.in_use : !!+t.in_use;
// The term in force in payroll month m: the one whose months hold it (to_month is the month the next one took over);
// for a month before the first term, the first one after it. No month: the latest.
function termAt(x, m) {
  const hs = terms(x);
  if (!/^\d{4}-\d{2}$/.test(m || "")) return hs[0] || x.now || null;
  const later = hs.filter(h => String(h.from_month || "") > m);
  return hs.find(h => String(h.from_month || "") <= m && (!h.to_month || m < h.to_month)) || later[later.length - 1] || hs[0] || x.now || null;
}
// In use in month m (no month: from the latest term on).
const termOn = (x, m) => termUse(x, m ? termAt(x, m) : lastTerm(x));
// In use or Stopped, from the month the latest term starts when that isn't the first one; Built in. With a month m (the
// earliest not filed): as it is then, and when a later term stops it or puts it back, from when.
function termPills(x, m) {
  const cur = m ? termAt(x, m) : null, on = cur ? termUse(x, cur) : false;
  const next = cur && terms(x).reverse().find(h => String(h.from_month || "") > m && termUse(x, h) !== on);
  if (next) return `<div class="row" style="gap:4px">${on ? `<span class="pill ok">In use</span><span class="pill">Stops from ${esc(monShort(next.from_month))}</span>`
    : `<span class="pill grey">Stopped</span><span class="pill">In use again from ${esc(monShort(next.from_month))}</span>`}${builtInPill(x)}</div>`;
  const t = lastTerm(x), from = String(t.from_month || "") > "0000-00" ? monShort(t.from_month) : "";
  return `<div class="row" style="gap:4px">${termOn(x) ? `<span class="pill ok">In use</span>${from ? `<span class="pill">From ${esc(from)}</span>` : ""}`
    : `<span class="pill grey">Stopped${from ? ` from ${esc(from)}` : ""}</span>`}${builtInPill(x)}</div>`;
}
// The terms, month by month, for the drawer.
function termsHtml(x, line) {
  const hs = terms(x);
  return hs.length ? `<div><h3>By month</h3><ul class="used">${hs.map(h => `<li>${esc(reqRange(h))}: ${h.in_use == null || +h.in_use ? esc(line(h)) : "stopped"}</li>`).join("")}</ul></div>` : "";
}
// The types offered in a picker: those in use, plus any already chosen that were stopped since.
function pickTypes(all, chosen) {
  const list = (all || []).filter(x => isActive(x) || chosen.includes(x.key));
  for (const k of chosen) if (!list.some(x => x.key === k)) list.push({ key: k, label: k, active: 0 });
  return list;
}
const tickBox = (id, x, on, attrs = "") => `<label class="row tight"${attrs}><input type="checkbox" id="${esc(id)}" ${on ? "checked" : ""}>
  <span>${esc(x.label || x.key)}${isActive(x) ? "" : ` <span class="muted">(stopped)</span>`}</span></label>`;
// The keys ticked: those chosen before in their order, then those newly ticked in the picker's order.
function ticked(pre, list, had) {
  const on = k => !!document.getElementById(pre + k)?.checked, keys = list.map(x => x.key);
  return [...had.filter(k => keys.includes(k) && on(k)), ...keys.filter(k => on(k) && !had.includes(k))];
}
const docChips = (keys, name) => keys.length ? `<div class="row" style="gap:4px">${keys.map(k => `<span class="chip">${esc(name(k))}</span>`).join("")}</div>` : `<span class="muted">None</span>`;
const setupDocName = (d, k) => (d?.doc_types || []).find(x => x.key === k)?.label || docLabel(k);
const fromMonth = id => {
  const v = $(id)?.value || "";
  if (!/^\d{4}-\d{2}$/.test(v)) throw new Error("Choose the month the change starts from.");
  return v;
};
// What a change does (or would do) to the months already set up, in words.
function effectText(a = {}, what) {
  const n = +a.tasks || 0, p = +a.payments || 0, miss = +a.now_missing || 0, done = +a.now_complete || 0;
  const out = [n ? `${plural(n, what)} in months already set up ${n === 1 ? "changes" : "change"}` : `No ${what} in months already set up changes`];
  if (p) out.push(`${plural(p, "payment")} affected`);
  if (miss) out.push(`${miss} now ${miss === 1 ? "misses" : "miss"} something`);
  if (done) out.push(`${done} ${done === 1 ? "is" : "are"} now complete`);
  return out.join("; ") + ".";
}
// The server's lines and counts, as a card: a preview (nothing saved yet) or what a save just did.
const effectCard = (r, head, what) => `<div class="card"><h3>${esc(head)}</h3>
  ${(r.lines || []).map(x => `<div class="note">${esc(x)}</div>`).join("") || `<div class="note">Nothing in the months already set up changes.</div>`}
  <div class="note"><b>${esc(effectText(r.affected, what))}</b></div></div>`;
const showPreview = (sel, r, what) => { const el = $(sel); if (el) el.innerHTML = effectCard(r, "Preview: nothing is saved yet", what); };
const reloadMeta = async () => { state.meta = await readMeta(); };  // only after a change that was kept (afterSaved): a read that fails says so

// Shows the parts of a checklist or reminder drawer that depend on what is chosen in it.
function setupPaint() {
  const comp = $("#cl-completion")?.value ?? state.setup.chkOpen?.completion, noDeadline = NO_DEADLINE.includes(comp);
  if ($("#cl-rule")) $("#cl-rule").hidden = comp !== "payments";
  if ($("#cl-deadline-f")) $("#cl-deadline-f").hidden = noDeadline;
  if ($("#cl-submit-f")) $("#cl-submit-f").hidden = noDeadline || !$("#cl-deadline")?.checked;
  // A document may be filed on the item instead only when payments need it.
  let any = false;
  for (const l of document.querySelectorAll("#drawer [data-ro]")) { const on = !!document.getElementById("cl-rd-" + l.dataset.ro)?.checked; l.hidden = !on; any ||= on; }
  if ($("#cl-ro-none")) $("#cl-ro-none").hidden = any;
  const kind = $("#rm-kind")?.value ?? state.setup.remOpen?.kind;
  if ($("#rm-what")) $("#rm-what").textContent = kind === "leaver" ? "the last day" : "the start date";
}

// Items done by the statements, the reconciliation or the audit pack have no deadline (the server keeps 0 for them).
const NO_DEADLINE = ["statements", "statements_balanced", "reconciled", "pack", "books"];
// The inputs of a drawer's term (what a change sends), by id: not the month, the reason or what is fixed once added.
const TERM_SKIP = ["cl-from", "cl-reason", "cl-completion", "rm-from", "rm-reason", "rm-short", "rm-key", "rm-kind"];
function termInputs(pre) {
  const all = drawerInputs(), out = {};
  for (const k in all) if (k.startsWith(pre) && !TERM_SKIP.includes(k)) out[k] = all[k];
  return out;
}
// The term's inputs were changed since they were last filled in.
const termEdited = (pre, filled = {}) => { const now = termInputs(pre); return Object.keys({ ...filled, ...now }).some(k => now[k] !== filled[k]); };
// After the term's inputs were filled in again: what they hold counts as unchanged (only the month was changed).
function termBaseline(pre) {
  const now = termInputs(pre), at = state.drawerAt;
  if (at) { for (const k of Object.keys(at)) if (k.startsWith(pre) && !TERM_SKIP.includes(k)) delete at[k]; Object.assign(at, now); }
  return now;
}
// The month input of a checklist or reminder drawer changed: the term in force then fills the drawer in, unless the
// term was edited already (the edits stay and apply from the new month); Stop using or Use again follows the month.
function termMonth(pre, O, x, fill, acts) {
  const m = $(`#${pre}from`)?.value || "", note = $(`#${pre}from-note`);
  for (const el of document.querySelectorAll("#drawer [data-preview-out]")) el.innerHTML = "";
  if (!x || !/^\d{4}-\d{2}$/.test(m)) return;
  if (termEdited(pre, O.filled)) { if (note) { note.textContent = `Your edits apply from ${monthName(m)}.`; note.hidden = false; } }
  else { O.term = termAt(x, m) || {}; fill(O.term); O.filled = termBaseline(pre); if (note) note.hidden = true; }
  const on = termOn(x, m);
  if (on !== O.on && state.why) hideWhy();  // the reason box was for the other button
  O.on = on; acts(x, on);
  setupPaint();
}

