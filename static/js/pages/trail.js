"use strict";
/* ---------------- Audit trail ---------------- */
// Every change to the records, as the server recorded it when it was saved (hrp/audit.py), newest first. An entry opens
// to show what changed field by field; a record's own history shows in its drawer (payments, recurring payments) or from
// its History button (budget lines). The page is drawn once; the filters redraw only the list.
const SRC_TONE = { user: "", auto: "grey", import: "grey", migration: "grey", seed: "grey", system: "grey", outside: "bad" };
const fmtWhen = iso => iso ? `${fmtDate(iso)} ${iso.slice(11, 16)}` : "—";
const trailVal = v => v == null || v === "" ? `<span class="muted">empty</span>` : esc(typeof v === "object" ? JSON.stringify(v) : v);

function trailQuery(extra = {}) {
  const f = { ...state.trail.f, ...extra }, q = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v !== "" && v != null) q.set(k, v);
  if (state.trail.show) q.set("show", "1");
  return q.toString();
}

// One change (a row of the trail): what kind of record, which, and its fields before and after. In a record's own
// history the record is known, so only the fields show.
function changeHtml(ch, own) {
  if (ch.table === "restore") return restoreHtml(ch, null);
  const rows = ch.fields.map(f => ch.op === "update"
    ? `<tr><td>${esc(f.label)}</td><td>${trailVal(f.before)}</td><td>${trailVal(f.after)}</td></tr>`
    : `<tr><td>${esc(f.label)}</td><td colspan="2">${trailVal(ch.op === "delete" ? f.before : f.after)}</td></tr>`).join("");
  const head = ch.op === "update" ? `<tr><th>Field</th><th>Before</th><th>After</th></tr>` : "";
  return `<div class="tr-change">${own ? "" : `<div><b>${esc(ch.op_label)}</b> · ${esc(ch.table_label)} · ${esc(ch.record)}</div>`}
    ${rows ? `<table class="diff">${head}${rows}</table>` : ""}${putBackHtml(ch)}</div>`;
}

// A deleted Setup record (the server marks the deletes it could put back): Put it back, or the entry that put it back.
const putBackHtml = ch => ch.put_back_in ? `<div class="note">Put back in entry ${esc(ch.put_back_in)}.</div>`
  : ch.put_back ? `<div class="row"><button class="ghost small" type="button" data-restore="${esc(ch.id)}" data-restore-title="${esc(ch.record)}">Put it back</button></div>` : "";

// A record put back (the event hrp/restore.py records): from which entry, and under which number. Its history under
// its other number (it came back with a new one when its own had been given to another record) is a click away; in the
// trail (shownKey null) the link opens the record's history.
function restoreHtml(ch, shownKey) {
  const f = Object.fromEntries((ch.fields || []).map(x => [x.name, x.after]));
  const moved = f.as_key != null && String(f.as_key) !== String(f.key);
  const other = shownKey == null || String(shownKey) !== String(f.as_key) ? f.as_key : f.key;
  const label = shownKey == null ? "Its history" : String(other) === String(f.key) ? "Its history before it was deleted" : "Its history since";
  return `<div class="tr-change"><div><b>Put back</b>${f.record ? ` · ${esc(f.record)}` : ""} · from entry ${esc(f.from_entry)}${moved ? ` · as #${esc(f.as_key)}, as #${esc(f.key)} had been given to another record` : ""}</div>
    ${shownKey == null || moved ? `<div class="row"><button class="ghost small" type="button" data-hist-open="${esc(f.table)}:${esc(other)}" data-hist-title="${esc(f.record || "")}">${label}</button></div>` : ""}</div>`;
}

function entryHead(e) {
  return `<span class="mono muted">${esc(fmtWhen(e.at))}</span>
    <span class="tr-what">${esc(e.headline)}${e.reason ? `<span class="note"> · Why: ${esc(e.reason)}</span>` : ""}</span>
    <span class="tr-who"><span class="pill ${SRC_TONE[e.source] ?? "grey"}">${esc(e.source_label)}</span> ${esc(e.actor)}${e.company ? ` · ${esc(e.company)}` : ""}${e.late ? ` <span class="pill warn" title="Sealed at a later start, after the app stopped unexpectedly">Sealed late</span>` : ""}</span>`;
}
const entryHtml = e => `<div class="tr-row" id="tx-${e.id}"><button type="button" class="tr-head" data-tx="${e.id}" aria-expanded="false">${entryHead(e)}</button><div class="tr-body" hidden></div></div>`;

async function toggleEntry(id, btn) {
  const body = btn.nextElementSibling, open = btn.getAttribute("aria-expanded") === "true";
  btn.setAttribute("aria-expanded", String(!open));
  if (open) { body.hidden = true; return; }
  body.hidden = false; body.innerHTML = `<div class="note">Loading…</div>`;
  try {
    const e = await api(`/api/audit/tx/${id}${state.trail.show ? "?show=1" : ""}`);
    // The activity log's own line is the entry's headline already; it shows here only when nothing else changed.
    const shown = e.changes.some(ch => ch.table !== "activity") ? e.changes.filter(ch => ch.table !== "activity") : e.changes;
    body.innerHTML = `${shown.map(ch => changeHtml(ch)).join("") || `<div class="note">Nothing changed in the records (an event only).</div>`}
      ${e.not_shown ? `<div class="note">And ${e.not_shown} more records as they stood.</div>` : ""}
      <div class="note mono">Entry ${e.id} · ${esc(e.action)}${e.machine ? ` · ${esc(e.machine)}` : ""} · check code ${esc(e.check_code)}</div>`;
  } catch (err) { body.innerHTML = `<div class="note bad-text">${esc(err.message)}</div>`; }
}

function statusHtml(st) {
  const items = [];
  if (st.head_behind) items.push("records.db is older than the last entry recorded beside it. That is expected after restoring a backup; otherwise entries may have been removed.");
  if (st.head_rewritten) items.push("The last entry recorded beside records.db has a different fingerprint inside it: the trail may have been rebuilt.");
  for (const p of st.check?.problems || []) items.push(p);
  const last = st.last_full_check;
  const lastLine = last ? `Last full check: ${last.ok ? "everything checked out" : "problems were found"}.` : "The whole trail hasn't been checked yet.";
  return items.length
    ? `<div class="banner bad"><b>The audit trail needs attention</b>${items.map(i => `<span>${esc(i)}</span>`).join("")}</div>`
    : `<div class="banner ok"><b>${st.entries} entries · check code ${esc(st.check_code || "—")}</b><span>The last ${st.check?.checked ?? 0} entries check out. ${esc(lastLine)}</span></div>`;
}

// The changes made outside the app waiting to be accepted. Accept seals up to the last one listed (upto_id), never more.
function outsideHtml(o) {
  const T = state.trail;
  T.upto = o.upto_id;
  if (!o.total) return "";
  const more = o.total - o.changes.length;
  return `<div class="card" id="trailOutside"><h2>Changes made outside this app · ${o.total}</h2>
    <div class="note">These were saved to records.db by another program (such as DB Browser for SQLite), or found by the check to differ from the trail, not made through this app. Check them, then accept them with the reason they were made. They stay in the trail either way.</div>
    ${o.changes.map(ch => changeHtml(ch)).join("")}
    ${more > 0 ? `<div class="note">${more} more are not listed. Accepting seals only the ${o.changes.length} listed above; the next ones then show here.</div>` : ""}
    <div class="row"><label class="field" style="flex:1"><span>Why were they made?</span><input id="trailReason" maxlength="500" value="${esc(T.reason || "")}" placeholder="e.g. Corrected a payee's name in DB Browser"></label>
      <button class="btn" id="trailAccept" style="align-self:end">Accept ${more > 0 ? `these ${o.changes.length}` : "these changes"}</button></div></div>`;
}

async function viewTrail(main) {
  const T = state.trail;
  const [st, page, outside] = await Promise.all([api("/api/audit/status"), api("/api/audit?" + trailQuery()),
    api("/api/audit/outside" + (T.show ? "?show=1" : ""))]);
  T.entries = page.entries; T.more = page.more; T.labels = page.labels; T.seq = (T.seq || 0) + 1;
  const opt = (v, label, cur) => `<option value="${esc(v)}"${String(cur ?? "") === String(v) ? " selected" : ""}>${esc(label)}</option>`;
  main.innerHTML = `
    <div class="card"><div class="eyebrow">Filing</div><h1>Audit trail</h1>
      <div class="note">Every change to the records is recorded here as it is saved: what changed, before and after, who made it, how and why. Entries can't be changed or removed, and each is sealed to the one before, so a change made afterwards shows up when the trail is checked. "Made by" is the Windows user running the app; there is no sign-in yet.</div>
      ${statusHtml(st)}
      <div class="row"><button class="btn" id="trailCheck">Check the audit trail</button>
        <a class="ghost" id="trailExport" href="/api/audit/export.xlsx?${trailQuery()}">Export to Excel</a>
        <label class="row tight"><input type="checkbox" id="trailShow"${T.show ? " checked" : ""}> Show bank details and account numbers</label></div>
      <div id="trailOut" class="note"></div></div>
    <div id="trailOutsideSlot">${outsideHtml(outside)}</div>
    <div class="card">
      <div class="form trail-filters">
        <label class="field"><span>From</span><input type="date" data-tf="from" value="${esc(T.f.from || "")}"></label>
        <label class="field"><span>To</span><input type="date" data-tf="to" value="${esc(T.f.to || "")}"></label>
        <label class="field"><span>Company</span><select data-tf="entity_id">${opt("", "All")}${state.meta.entities.map(e => opt(e.id, e.code, T.f.entity_id)).join("")}</select></label>
        <label class="field"><span>Record</span><select data-tf="tbl">${opt("", "All")}${Object.entries(T.labels.tables).map(([k, v]) => opt(k, v, T.f.tbl)).join("")}</select></label>
        <label class="field"><span>Made by</span><select data-tf="source">${opt("", "All")}${Object.entries(T.labels.sources).map(([k, v]) => opt(k, v, T.f.source)).join("")}</select></label>
        <label class="field"><span>Search</span><input type="search" data-tf="q" value="${esc(T.f.q || "")}" placeholder="A name, amount, ref or reason"></label>
      </div>
      <div id="trailList" class="tr-list" aria-live="polite">${listHtml(T.entries)}</div>
      <div class="row" id="trailMoreRow"${T.more ? "" : " hidden"}><button class="ghost" data-trail-more="1">Show older</button></div>
    </div>`;
}
const listHtml = list => list.map(entryHtml).join("") || `<div class="empty">No entries match.</div>`;

// A filter changed: the list again from the newest, without redrawing the page (the box being typed in keeps its focus).
async function refreshTrailList() {
  const T = state.trail, seq = T.seq = (T.seq || 0) + 1;
  try {
    const page = await api("/api/audit?" + trailQuery());
    if (seq !== T.seq || !$("#trailList")) return;  // a newer change, or another page, came first
    T.entries = page.entries; T.more = page.more;
    $("#trailList").innerHTML = listHtml(T.entries);
    $("#trailMoreRow").hidden = !T.more;
    $("#trailExport").href = "/api/audit/export.xlsx?" + trailQuery();
  } catch (e) { toast(e.message, true); }
}

async function trailMore(btn) {
  const T = state.trail, seq = T.seq, last = T.entries[T.entries.length - 1];
  if (!last || btn.disabled) return;
  btn.disabled = true;
  try {
    const page = await api("/api/audit?" + trailQuery({ before_id: last.id }));
    if (seq !== T.seq || !$("#trailList")) return;  // the filters changed meanwhile: that list is gone
    T.entries.push(...page.entries); T.more = page.more;
    $("#trailList").insertAdjacentHTML("beforeend", page.entries.map(entryHtml).join(""));
    $("#trailMoreRow").hidden = !T.more;
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; }
}

async function trailCheck(btn) {
  btn.disabled = true; btn.textContent = "Checking…";
  try {
    const r = await api("/api/audit/check", { json: {} });
    const text = r.ok ? `All ${r.checked} entries check out, and all ${r.replay.checked} records match the trail. Check code ${esc(r.check_code)}.`
      : `<b class="bad-text">Problems found.</b> ${[...r.problems, ...r.replay.problems.map(p => `${p.table_label} ${p.record} ${p.problem}.`)].map(esc).join(" ")}${r.replay.more ? ` And ${r.replay.more} more.` : ""}${r.replay.count ? " Records that differ are listed under Changes made outside this app." : ""}`;
    if (!$("#trailOut")) { toast(r.ok ? `Audit trail checked: all ${r.checked} entries check out.` : "The audit trail check found problems. Open the audit trail to see them.", !r.ok); return; }
    if (r.replay.count) { await render(); }  // the differences now wait to be accepted
    $("#trailOut").innerHTML = text;
  } catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = "Check the audit trail"; }
}

async function trailAccept(btn) {
  const reason = $("#trailReason").value.trim();
  if (!reason) { toast("Say why these changes were made.", true); $("#trailReason").focus(); return; }
  btn.disabled = true;
  try {
    const r = await api("/api/audit/accept-outside", { json: { reason, upto_id: state.trail.upto } });
    state.trail.reason = ""; toast(`Accepted ${r.accepted} change${r.accepted === 1 ? "" : "s"}`); render();
  } catch (e) { toast(e.message, true); btn.disabled = false; }
}

// Bank details on or off: the open entries and the outside card again; the list itself doesn't show them.
async function trailShow(on) {
  state.trail.show = on;
  try {
    const o = await api("/api/audit/outside" + (on ? "?show=1" : ""));
    if ($("#trailOutsideSlot")) $("#trailOutsideSlot").innerHTML = outsideHtml(o);
    for (const b of document.querySelectorAll('.tr-head[aria-expanded="true"]')) { b.setAttribute("aria-expanded", "false"); await toggleEntry(+b.dataset.tx, b); }
  } catch (e) { toast(e.message, true); }
}

// A record's history, newest first (in a drawer section, or in a drawer of its own for a budget line).
function historyHtml(h) {
  if (!h.changes.length) return `<div class="note">Nothing recorded yet.</div>`;
  // A row of a related record (a recurring payment's salary advance) says what it is; the record's own rows don't need to.
  // A record put back has a row of its own: from which entry (restoreHtml).
  return h.changes.map(ch => `<div class="tr-hist"><div><span class="mono muted">${esc(fmtWhen(ch.at))}</span> · <b>${esc(ch.table === "restore" ? "Put back" : ch.op_label)}</b>${ch.table !== h.table && ch.table !== "restore" ? ` ${esc(ch.table_label.toLowerCase())}` : ""}
      · <span class="pill ${SRC_TONE[ch.source] ?? "grey"}">${esc(ch.source_label || "")}</span> ${esc(ch.actor || "")}${ch.reason ? ` · Why: ${esc(ch.reason)}` : ""}</div>
    ${ch.op === "baseline" ? `<div class="note">As it stood when the audit trail started.</div>` : ch.table === "restore" ? restoreHtml(ch, h.key) : changeHtml(ch, true)}</div>`).join("");
}
const histSection = (tbl, key) => `<details class="hist" data-hist="${esc(tbl)}:${esc(key)}"><summary><h3>History</h3></summary><div class="hist-body"></div></details>`;

async function openHistory(tbl, key, title) {
  if (!(await closeDrawer())) return;
  $("#drawer").innerHTML = `<div class="row spread"><div><div class="eyebrow">History</div><h2>${esc(title || "Record")}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div><div id="histOnly" class="note">Loading…</div>`;
  showDrawer();
  try { const h = await api(`/api/audit/record/${encodeURIComponent(tbl)}/${encodeURIComponent(key)}`); if ($("#histOnly")) $("#histOnly").outerHTML = `<div>${historyHtml(h)}</div>`; }
  catch (e) { if ($("#histOnly")) $("#histOnly").textContent = e.message; }
}

/* ---- Put back a deleted Setup record (hrp/restore.py) ---- */
// The "Show deleted" tick of a Setup section (kept for every section, as Show stopped is).
const deletedToggle = kind => `<label class="row tight"><input type="checkbox" data-setup-deleted="${esc(kind)}" ${state.setup.deleted ? "checked" : ""}> Show deleted</label>`;

// Show deleted: the section's records deleted in this app and not put back since, newest first, with when, who and why, and Put it
// back, or why it can't be now (design/canvas/Setup.dc.html).
async function drawDeleted(kind) {
  const box = $("#setupDeleted");
  if (!box) return;
  if (!state.setup.deleted) { box.innerHTML = ""; return; }
  const per = ["accounts", "parties", "gl_accounts", "statutory_accounts", "checklist", "payees"].includes(kind);
  if (per && !state.entity) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="note" role="status">Loading…</div>`;
  try {
    const d = await api(`/api/setup/restore?kind=${encodeURIComponent(kind)}${per ? `&entity=${state.entity}` : ""}`);
    if ($("#setupDeleted") !== box) return;  // another page or section was drawn meanwhile
    const own = state.setup.types?.kinds?.[kind], plural = own?.deleted_plural || own?.plural || d.plural;  // the section's own words (Filing words, not SQL filing words)
    const row = r => `<tr><td>${esc(r.name)}${r.code ? `<div class="note st-sub">${esc(r.code)}</div>` : ""}</td><td>${esc(fmtWhen(r.at))}<div class="note st-sub">Entry ${esc(r.entry)}</div></td><td>${esc(r.actor || "")}</td><td>${esc(r.reason || "")}</td>
      <td><div class="row tight">${r.problem ? "" : `<button class="ghost small" type="button" data-restore="${esc(r.row_id)}" data-restore-title="${esc(r.name)}" aria-haspopup="dialog">${icon("undo")}Put it back</button>`}
        <button class="ghost small" type="button" data-hist-open="${esc(r.table)}:${esc(r.key)}" data-hist-title="${esc(r.name)}" aria-haspopup="dialog">${icon("history")}History</button></div>
        ${r.problem ? `<div class="note st-problem">${icon("lock")}<span>Can't be put back: ${esc(r.problem)}</span></div>` : ""}</td></tr>`;
    box.innerHTML = `<section class="card st-deleted ex" id="st-del" aria-labelledby="st-del-h"><div class="row tight">${icon("trash")}<h2 id="st-del-h">Deleted ${esc(plural)}</h2></div>
      <div class="note">Deleted in this app and not put back since, newest first. Putting one back asks why; it comes back as it was, with its history.</div>
      <div class="tbl-wrap"><table class="st-table"><thead><tr><th scope="col">Name</th><th scope="col">Deleted</th><th scope="col">By</th><th scope="col">Why</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead><tbody>
        ${d.rows.map(row).join("") || `<tr><td colspan="5" class="empty">None deleted.</td></tr>`}</tbody></table></div></section>`;
  } catch (e) { box.innerHTML = `<div class="note bad-text">${esc(e.message)}</div>`; }
}

// Put it back (from the audit trail, a record's History or Show deleted): a dialog shows what it would do first (a preview: nothing is
// kept), or why it can't be put back; Put it back then needs a reason, asked in the dialog.
async function openRestore(rowId, title) {
  if (!(await closeDrawer())) return;
  $("#drawer").innerHTML = `<div class="np st-form" id="restoreBox"><div class="pd-head"><span class="plate brand">${icon("undo")}</span>
      <div class="pd-words"><span class="eyebrow" id="rs-eyebrow">Put back</span><h2 id="drawerTitle" tabindex="-1">${esc(title || "Deleted record")}</h2><span class="pd-sub" id="rs-sub"></span></div>
      <button type="button" class="ghost small pd-x" id="closeDrawer" aria-label="Close">${icon("close")}</button></div>
    <div class="np-body st-body" id="rsBody"><div class="note" role="status">Loading…</div></div>
    <div class="pd-foot"><span class="pd-foot-note ro" id="rs-foot"></span><div class="pd-foot-acts" id="rsActs"><button type="button" class="ghost" data-su-close="1">Close</button></div></div></div>`;
  showDrawer("setup");
  watchDrawer();
  let p;
  try { p = await api(`/api/setup/restore/${rowId}`, { json: { preview: true } }); }
  catch (e) {
    if ($("#rsBody")) $("#rsBody").innerHTML = appStopped(e)
      ? `<div class="note bad-text" role="alert">Couldn't load this. Try again.</div><div class="row"><button type="button" class="ghost small" data-restore="${esc(rowId)}" data-restore-title="${esc(title || "")}">${icon("refresh")}Try again</button></div>`
      : refusedNote(`${e.message} Nothing was changed.`, { title: "This can't be put back." });
    return;
  }
  if (!$("#rsBody")) return;
  const del = p.deleted || {}, a = p.affected || {};
  const touches = (p.lines || []).length || +a.tasks || +a.payments;
  $("#rs-eyebrow").textContent = `Put back · ${p.label}`;
  if (p.name && $("#drawerTitle")) $("#drawerTitle").textContent = p.name;  // as Show deleted names it (a company by its code), whichever way this was opened
  $("#rs-sub").textContent = `Deleted ${fmtWhen(del.at)}${del.actor ? ` by ${del.actor}` : ""}, in entry ${del.entry}.`;
  $("#rsBody").innerHTML = `<div id="rsErr"></div><div class="st-pb"><div>${esc(p.label)} deleted ${esc(fmtWhen(del.at))}${del.actor ? ` by ${esc(del.actor)}` : ""}, in entry ${esc(del.entry)}${del.reason ? `. Why: ${esc(del.reason)}` : ""}.</div>
      <div class="row tight st-back">${icon("undo")}<span>It comes back as it was when it was deleted, ${p.same_id ? "with the same number." : `as #${esc(p.id)}.`}</span></div>
      ${(p.notes || []).map(n => `<div class="row tight st-back">${icon("help")}<span>${esc(n)}</span></div>`).join("")}</div>
    ${touches ? effectCard(p, "Putting it back also changes", p.kind === "checklist" ? "checklist item" : "reminder") : `<div class="note">Nothing in the months already set up changes.</div>`}
    <label class="field"><span>Why are you putting it back? <span class="req">Required</span></span><input id="pb-why" maxlength="500" autocomplete="off" aria-required="true" aria-describedby="pb-why-err" placeholder="Kept in the audit trail with the change">
      <span class="field-err" id="pb-why-err" role="alert"></span></label>
    <div class="row"><button class="ghost small" type="button" data-hist-open="${esc(p.table)}:${esc(del.key)}" data-hist-title="${esc(p.name || title)}">${icon("history")}History</button></div>`;
  $("#rsActs").innerHTML = `<button type="button" class="ghost" data-su-close="1">Cancel</button><button type="button" class="btn" id="pb-go" data-restore-go="${esc(rowId)}">${icon("undo")}Put it back</button>`;
  watchDrawer();
  document.getElementById("pb-why")?.focus?.({ preventScroll: true });
}
async function restoreGo(rowId, btn) {
  if (restoreGo.busy) return;  // Enter pressed twice: it is put back once
  const inp = $("#pb-why"), err = $("#pb-why-err"), reason = (inp?.value || "").trim();
  if (!reason) {
    if (err) err.innerHTML = `${icon("alert")}Say why you're making this change.`;
    if (inp) { inp.setAttribute("aria-invalid", "true"); inp.focus(); }
    return;
  }
  if (err) err.innerHTML = ""; if (inp?.removeAttribute) inp.removeAttribute("aria-invalid");
  btn.disabled = true; restoreGo.busy = true;
  let r;
  try { r = await api(`/api/setup/restore/${rowId}`, { json: { reason } }); }
  catch (e) { if (btn.isConnected) btn.disabled = false; if (appStopped(e)) throw e; if ($("#rsErr")) $("#rsErr").innerHTML = refusedNote(`${e.message} Nothing was changed.`, { title: "This can't be put back." }); return; }
  finally { restoreGo.busy = false; }
  closeDrawer(true);
  toast(`${r.label} put back${r.same_id ? "" : ` as #${r.id}`}`);
  if (["checklist", "reminders", "payees"].includes(r.kind)) await reloadMeta(); else await afterSetupChange(r.kind);
  return render();
}

// The Overview says when the trail needs attention (changes made outside the app, a records.db behind or rebuilt).
async function trailNotice() {
  try {
    const st = await api("/api/audit/status?quick=1");
    if (!(st.outside || st.head_behind || st.head_rewritten) || state.view !== "overview" || $("#trailNotice")) return;
    $("#main").insertAdjacentHTML("afterbegin", `<div class="banner bad noprint" id="trailNotice"><b>The audit trail needs attention</b>
      <span>${st.outside ? `${st.outside} change(s) were made to the records outside this app.` : "records.db doesn't match the last entry recorded beside it."}</span>
      <button class="ghost small" data-view="trail">Open the audit trail</button></div>`);
  } catch { /* the notice is a convenience; the page works without it */ }
}

