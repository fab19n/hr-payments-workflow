"use strict";
/* ---------------- Entity month ---------------- */
async function viewEntity(main) {
  const [d, next] = await Promise.all([api(`/api/month?entity=${state.entity}&month=${state.month}`), loadNext(state.entity)]);
  state.data = d;
  const setUp = d.set_up ? "" : notSetUp(d.entity, d.month, d.payments.length);
  if (!d.set_up && !d.payments.length && !d.tasks.length) { main.innerHTML = setUp; return; }
  // A reminder waiting here for its own month to be set up shows, but counts only there.
  const counted = d.tasks.filter(t => !t.waiting), doneT = counted.filter(t => t.done).length;
  const tasks = d.tasks.map(t => {
    // Each document still needed is its own upload button, so the file is filed as that type. Once one is filed, Add
    // another files the next one as the same type (a second approval, say). One SQL already
    // shows needs no upload, but can still take one.
    const filed = new Set(t.documents.map(x => x.doc_type));
    const chips = t.required_docs.map(dt => t.missing.includes(dt)
      ? `<button class="chip need" data-task-upload="${t.id}" data-type="${dt}" title="${esc(t.not_counted[dt]?.hint || "Upload the " + docLabel(dt))}">＋ ${esc(docLabel(dt))}</button>`
      : filed.has(dt) ? `<span class="chip have">✓ ${esc(docLabel(dt))}</span>` : evidenceChip(t.evidence[dt])).join("");
    const more = t.required_docs.filter(dt => !t.missing.includes(dt))
      .map(dt => `<button class="ghost small" data-task-upload="${t.id}" data-type="${dt}">＋ ${filed.has(dt) ? "Add another" : "Upload"} ${esc(docLabel(dt))}</button>`).join("");
    const files = t.documents.map(x => `<span class="chip"><a href="/api/documents/${x.id}/file" target="_blank">📄 ${esc(docLabel(x.doc_type))}: ${esc(x.original_name)}</a>
        <button class="link" data-task-upload="${t.id}" data-type="${x.doc_type}" data-replaces="${x.id}" data-name="${esc(x.original_name)}">Replace</button>
        <button class="link" data-remove-doc="${x.id}" data-name="${esc(x.original_name)}">Remove</button></span>`).join("") +
      t.sql_docs.map(x => `<span class="chip have" title="From SQL">SQL ${esc(x.doc_no)} · ${money(x.amount)}${x.taken_back_by ? ` · e-Invoice cancelled by ${esc(x.taken_back_by)}`
        : x.einvoice_status ? " · e-Invoice " + esc(x.einvoice_status.split(",")[0].toLowerCase()) : ""}</span>`).join("");
    // Done when ticked, or when the records show it (auto; its box can't be unticked then). The server words what they
    // show or still lack; a tick by hand that they don't bear out says so.
    const why = t.why ? `<div class="note ${t.auto ? "ok" : t.done_at ? "warn" : ""}">${t.done_at && !t.auto ? "Ticked by hand. " : ""}${esc(t.why)}</div>` : "";
    const waits = t.waiting ? `<div class="note">Part of the ${monthName(t.waiting)} checklist. Shown here until that month is set up; not counted in this month or its audit pack.</div>` : "";
    return `<div class="task ${t.done ? "done" : ""}" id="task-${t.id}">
      <input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""} ${t.auto && !t.done_at ? `disabled title="${esc(t.why)}"` : ""} aria-label="Done">
      <div><div class="t">${esc(t.title)}</div>${t.detail ? `<div class="d">${esc(t.detail)}</div>` : ""}${why}${waits}
        <div class="docs">${chips}${files}${more}<button class="ghost small" data-task-upload="${t.id}" data-type="other">＋ Other document</button></div></div>
      <div class="num"><span class="muted">${shortDate(t.due_date)}</span><br>${t.flag ? flagPill(t.flag) : t.done ? `<span class="pill ok">Done</span>` : ""}</div>
    </div>`;
  }).join("");

  const groups = {};
  for (const p of d.payments) (groups[p.due_date] ||= []).push(p);
  const payRows = Object.keys(groups).sort().map(dd => {
    const list = groups[dd];
    return `<tr class="group"><td colspan="3">Due ${fmtDate(dd)}</td><td class="num">${groupTotals(list)}</td><td colspan="2"></td></tr>` +
      list.map(p => {
        // Not paid: the server's word for why (Due today, Waiting for SQL record...); paid: a note when paid late.
        const st = statusPill(p);
        const late = p.status !== "planned" && p.flag ? `<div class="note late" title="${esc(p.flag.hint || "")}">${esc(p.flag.text)}</div>` : "";
        // A voucher number shown in its chip (✓ PV2601-020) needs no SQL chip beside it.
        const sqlShown = state.meta.sql_only.some(dt => p.required.includes(dt) && p.evidence[dt] && !p.documents.some(x => x.doc_type === dt));
        const docs = p.required.map(dt => docChip(p, dt)).join(" ") +
          (d.entity.uses_sql && p.paid_date && (p.not_in_sql || !sqlShown) ? ` <span class="chip ${p.not_in_sql ? "need" : "have"}" title="${esc(p.sql_ref || "Not recorded in SQL yet")}">${p.not_in_sql ? "·" : "✓"} SQL</span>` : "");
        return `<tr class="click" id="pay-${p.id}" data-payment="${p.id}">
          <td>${esc(p.description)}${p.amount_is_estimate ? ` <span class="pill grey" title="${d.entity.uses_sql ? "Planned figure. The SQL voucher or bank line replaces it." : "Planned figure. The bank line replaces it."}">estimate</span>` : ""}${p.notes ? `<div class="note">${esc(p.notes)}</div>` : ""}</td>
          <td class="muted">${esc(state.meta.categories[p.category] || p.category)}</td>
          <td>${p.paid_date ? shortDate(p.paid_date) : ""}</td>
          <td class="num">${signed(p.amount, p.currency, p.direction)}${estimateShort(p) ? `<div class="note">Estimated ${money(p.planned_amount, p.currency)}</div>` : ""}</td>
          <td>${docs}</td><td>${st}${late}</td></tr>`;
      }).join("");
  }).join("");

  main.innerHTML = `${setUp}
    <div class="row spread"><div><div class="eyebrow">${esc(d.entity.code)}</div><h1>${esc(d.entity.name)} · ${esc(d.label)}${d.before_first ? ` ${BEFORE_PILL}` : ""}</h1></div>
      <div class="row noprint">${d.set_up && !d.closed_at ? `<button class="ghost" data-close-month="1">Mark month as filed</button>` : ""}
      <button class="btn" id="addPayment">Add a payment</button></div></div>
    ${d.closed_at ? `<div class="banner ok"><b>Filed ${shortDate(d.closed_at)}</b><span>This month is marked as filed, so nothing in it counts as to do on the Overview.</span>
      <button class="ghost small noprint" data-reopen-month="1">Reopen</button></div>` : ""}
    <div id="nextUp">${nextCard(next, d.entity.id)}</div>
    <div class="grid2" style="grid-template-columns:minmax(0,1fr)">
      <div class="card"><div class="row spread"><h2>Payments</h2><span class="note">Click a payment to upload its documents.</span></div>
        <div class="tbl-wrap"><table><thead><tr><th>Payment</th><th>Type</th><th>Paid / received</th><th class="num">Amount</th><th>Documents</th><th>Status</th></tr></thead>
        <tbody>${payRows || `<tr><td colspan="6" class="empty">No payments this month yet.</td></tr>`}</tbody></table></div></div>
      <div class="card"><div class="row spread"><h2>Checklist</h2><span class="muted">${doneT} of ${counted.length} done</span></div><div>${tasks}</div></div>
    </div>`;
  // What was typed in the open payment and not saved yet stays after the refresh (an upload, a checklist tick).
  if (state.openPayment) openPayment(state.openPayment, unsavedEdits());
  // Opened from Before you print, Next up or a count to fix a checklist item or some payments: they are brought into
  // view and marked for a moment.
  const { mark } = state;
  state.mark = null;
  flash([...(mark?.task ? d.tasks.filter(mark.task).map(t => $(`#task-${t.id}`)) : []),
    ...(mark?.pay ? d.payments.filter(mark.pay).map(p => $(`#pay-${p.id}`)) : [])]);
}

/* ---------------- Payment drawer ---------------- */
// The drawer's inputs, by the field each one saves.
const PAY_INPUTS = { amount: "pf-amount", paid_date: "pf-paid", bank_ref: "pf-bank", sql_ref: "pf-sql", einvoice_ref: "pf-einv",
  notes: "pf-notes", difference_note: "pf-diff", amount_confirmed: "pf-confirm" };

// What has been typed in the payment drawer and not saved, as {input id: value}.
function unsavedEdits() {
  if (!state.openPayment || $("#drawer").hidden || !$("#payForm")) return {};
  const now = payFormValues(), out = {};
  for (const [k, id] of Object.entries(PAY_INPUTS)) {
    const el = $("#" + id);
    if (el && now[k] !== state.payLoaded[k]) out[id] = el.type === "checkbox" ? el.checked : el.value;
  }
  return out;
}
// Other drawers (Setup, a recurring payment) say what they hold through state.drawerDirty, set by watchDrawer once drawn.
// What their inputs hold, by id; the reason box has a check of its own.
function drawerInputs() {
  const out = {};
  for (const el of $("#drawer").querySelectorAll("input[id], select[id], textarea[id]")) if (el.id !== "su-reason") out[el.id] = el.type === "checkbox" ? el.checked : el.value;
  return out;
}
// The inputs changed since the drawer was drawn, as {input id: value}.
function drawerEdits() {
  const at = state.drawerAt || {}, now = drawerInputs(), out = {};
  for (const k in at) if (k in now && now[k] !== at[k]) out[k] = now[k];
  return out;
}
// Called once a drawer is drawn: what it holds now counts as saved. keep: what was typed before it was drawn again.
function watchDrawer(keep = {}) {
  state.drawerAt = drawerInputs(); state.drawerDirty = () => Object.keys(drawerEdits()).length > 0;
  for (const [k, v] of Object.entries(keep)) { const el = document.getElementById(k); if (el) el[el.type === "checkbox" ? "checked" : "value"] = v; }
}
// A reason typed in the Why box and not used yet.
const reasonTyped = () => !!$("#su-reason")?.value.trim() && !$("#setupWhy").hidden;
const drawerDirty = () => drawerShown() && (Object.keys(unsavedEdits()).length > 0 || !!state.drawerDirty?.() || reasonTyped());
// Asks before edits not saved yet are lost. Resolves true when there are none, or when you choose to discard them. Two asks
// at once (Escape twice) share one dialog.
let leavePending = null;
async function mayLeave() {
  if (!drawerDirty()) return true;
  const name = ($("#drawerTitle")?.textContent || "").trim();
  leavePending ||= ask(name ? `You have unsaved changes on “${name}”. Closing now loses them.` : "You have unsaved changes. Closing now loses them.", {
    title: "Discard your changes?", yes: "Discard", no: "Keep editing", danger: true, tone: "warn", glyph: "edit",
    note: "Escape, a click outside the dialog, Cancel, changing page or month, and opening another payment all ask this first.",
    closing: { glyph: "alert", text: "Discarded changes can't be recovered." } })
    .finally(() => { leavePending = null; });
  return leavePending;
}

// Resolves false when you choose to keep changes not saved yet; force closes it anyway (the payment was removed). With
// nothing to ask it closes at once, before the first await.
async function closeDrawer(force) {
  if (!force && drawerDirty() && !(await mayLeave())) return false;
  hideDrawer(); state.openPayment = null; state.drawerDirty = null; state.drawerAt = null; state.why = null;
  Object.assign(state.setup, { drawer: null, chkOpen: null, remOpen: null, paste: null });
  return true;
}

function openPayment(id, keep = {}) {
  const p = state.data.payments.find(x => x.id === id);
  if (!p) return closeDrawer(true);
  state.openPayment = id; state.drawerDirty = null;
  const dt = state.meta.doc_types;
  const ofType = t => p.documents.filter(x => x.doc_type === t);
  const required = p.required.map(t => slotHtml(t, ofType(t), p.evidence[t], p.not_counted[t])).join("");
  // The document types in use, but not the ones the app files itself (statements, reconciliations, SQL listings), and for
  // a company not kept in SQL no SQL documents. Approval is the usual extra; where it is required already, Other, so a
  // document added without a look at the list is never filed as a voucher.
  const noSql = !state.data.entity.uses_sql;
  const extraTypes = Object.keys(dt).filter(t => !p.required.includes(t) && docActive(t) && !["statement", "recon", "sqlexport"].includes(t) && !(noSql && docFromSql(t)));
  const extraPick = ["approval", "other"].find(t => extraTypes.includes(t)) || extraTypes[0];
  const extras = [...new Set(p.documents.map(x => x.doc_type).filter(t => !p.required.includes(t)))].map(t => slotHtml(t, ofType(t))).join("");
  const lines = p.bank_lines.length ? p.bank_lines.map(l => `<div class="line-desc mono">${shortDate(l.txn_date)} · ${(l.amount > 0) === (p.direction === "out") ? "−" : ""}${money(Math.abs(l.amount), p.currency)} · ${esc(l.description.split(" | ").slice(0, 2).join(" "))}</div>`).join("") : `<div class="note">${p.direction === "in" ? "No bank credit matched to this yet." : "Not matched to a bank statement line yet."}</div>`;
  const gap = p.bank_total == null || p.amount == null ? 0 : p.amount - p.bank_total;
  const short = gap > 0.01 ? `<div style="grid-column:1/-1"><b>Part paid: ${foundOf(p)}</b>
      <div class="note">${p.difference_note ? "The difference is noted, so this payment counts as paid." : `${money(gap, p.currency)} isn't on the bank statement yet. Match the rest on the Bank statements page, or note why below.`}</div></div>
      <label class="field" style="grid-column:1/-1"><span>Why the rest isn't on the bank statement</span><input id="pf-diff" value="${esc(p.difference_note || "")}" placeholder="e.g. balance paid in October"></label>` : "";
  const over = gap < -0.01 ? `<div class="note">The bank lines add up to ${money(p.bank_total, p.currency)}, ${money(-gap, p.currency)} more than the amount.</div>` : "";
  const est = estimateShort(p) ? `<div class="note">Estimated at ${money(p.planned_amount, p.currency)}; the bank lines linked so far add up to ${money(p.bank_total, p.currency)}. If more was sent, link the rest on the Bank statements page. If not, confirm the amount above; until then the budget counts the estimate.</div>` : "";
  const vouchers = p.sql_entries.map(x => `<div class="row spread"><span class="mono">${esc(x.doc_no)}${x.kind === "invoice" ? " (invoice)" : ""} · ${shortDate(x.doc_date)} · ${x.direction && x.direction !== p.direction ? "−" : ""}${money(x.amount, p.currency)}</span>
    <button class="ghost small" data-sql-unlink="${x.id}">Unlink</button></div>`).join("");
  $("#drawer").innerHTML = `
    <div class="row spread"><div><div class="eyebrow">${esc(state.meta.categories[p.category] || p.category)} · due ${fmtDate(p.due_date)}</div><h2>${esc(p.description)}</h2></div>
      <button class="ghost small" id="closeDrawer">Close</button></div>
    ${p.flag ? `<div class="row">${flagPill(p.flag)}${p.flag.hint ? `<span class="note">${esc(p.flag.hint)}</span>` : ""}</div>` : ""}
    ${p.bank_details || p.payee_ref ? `<div class="note">Pay to: <span class="mono">${esc(p.bank_details || "")} ${esc(p.payee_ref || "")}</span></div>` : ""}
    <form class="form" id="payForm">
      <label class="field"><span>Amount (${esc(p.currency)})</span><input id="pf-amount" type="number" step="0.01" value="${p.amount ?? ""}"></label>
      <label class="field"><span>${p.direction === "in" ? "Received on" : "Paid on"}</span><input id="pf-paid" type="date" value="${p.paid_date || ""}"></label>
      <label class="field"><span>Bank reference</span><input id="pf-bank" value="${esc(p.bank_ref || "")}"></label>
      <label class="field"><span>${state.data.entity.uses_sql ? (p.direction === "in" ? "SQL OR no." : "SQL PV / JV no.") : "Record ref"}</span><input id="pf-sql" value="${esc(p.sql_ref || "")}"></label>
      <label class="field"><span>e-Invoice UIN</span><input id="pf-einv" value="${esc(p.einvoice_ref || "")}"></label>
      <label class="field" style="grid-column:1/-1"><span>Notes</span><input id="pf-notes" value="${esc(p.notes || "")}"></label>
      ${short}
      ${p.amount_is_estimate || estimateShort(p) ? `<label class="row" style="grid-column:1/-1;gap:6px;font-size:.85rem"><input type="checkbox" id="pf-confirm" style="accent-color:var(--accent)"> The amount above is the real figure, not an estimate</label>` : ""}
      <div class="row"><button class="btn" type="submit">Save details</button></div>
    </form>
    <div><h3>Required documents</h3><div class="note">Drop files on a box, or click Upload. A file dropped on a box is added beside the ones already there; Replace swaps one and Remove takes one off. A box ticked from SQL or the bank statement needs no upload, but can still take a copy.</div></div>
    <div style="display:grid;gap:8px">${required}</div>
    <div><h3>Other documents</h3></div>
    <div style="display:grid;gap:8px">${extras}
      ${extraTypes.length ? `<div class="row"><select id="extraType">${extraTypes.map(t => `<option value="${esc(t)}" ${t === extraPick ? "selected" : ""}>${esc(dt[t] || t)}</option>`).join("")}</select>
      <button class="ghost small" id="extraUpload">Upload another document</button></div>` : ""}</div>
    ${state.data.entity.uses_sql ? `<div><h3>SQL Account</h3>${vouchers ? vouchers + (p.evidence.einvoice && !p.required.includes("einvoice") ? `<div class="note chip have ev">✓ ${esc(p.evidence.einvoice.text)}</div>` : "") + `<div class="note">Linked by mistake? Unlink puts the voucher back under SQL entries not linked, and the amount and paid date back to what they were.</div>` : `<div class="note">No SQL voucher linked yet.</div>`}</div>` : ""}
    <div><h3>Bank statement</h3>${lines}${over}${est}</div>
    ${histSection("payments", p.id)}
    <div class="row"><button class="btn danger small" id="deletePayment">Remove this payment</button></div>`;
  showDrawer();
  state.payLoaded = payFormValues();
  for (const [k, v] of Object.entries(keep)) { const el = $("#" + k); if (el) el[el.type === "checkbox" ? "checked" : "value"] = v; }
}

function payFormValues() {
  return { amount: $("#pf-amount").value === "" ? null : +$("#pf-amount").value, paid_date: $("#pf-paid").value,
    bank_ref: $("#pf-bank").value.trim(), sql_ref: $("#pf-sql").value.trim(), einvoice_ref: $("#pf-einv").value.trim(), notes: $("#pf-notes").value.trim(),
    difference_note: $("#pf-diff")?.value.trim(), amount_confirmed: !!$("#pf-confirm")?.checked };
}

// One box per document of the type, then one to add another (several transfer slips for one payment, say). With none
// uploaded, ev (what SQL or the bank statement already shows, e.g. PV2601-020) ticks the box, which can still take a file;
// without it, why says why what SQL has doesn't count (an e-Invoice cancelled by a refund note).
function slotHtml(type, docs, ev, why) {
  const label = esc(state.meta.doc_types[type] || type);
  if (!docs.length) return `<div class="slot ${ev ? "have" : "need"}" data-slot="${type}"><div class="lbl"><b>${label}</b><div class="file"${ev ? ` title="${esc(ev.text)}"` : ""}>${ev ? `✓ ${esc(ev.text)}` : "Not uploaded"}</div>${!ev && why ? `<div class="note">${esc(why.hint)}</div>` : ""}</div><button class="ghost small" data-upload="${type}">Upload</button></div>`;
  return docs.map(d => `<div class="slot have" data-slot="${type}"><div class="lbl"><b>${label}</b><div class="file">${esc(d.original_name)} · ${fmtDate(d.uploaded_at)}</div></div>
    <a class="ghost small" href="/api/documents/${d.id}/file" target="_blank">View</a><button class="ghost small" data-upload="${type}" data-replaces="${d.id}" data-name="${esc(d.original_name)}">Replace</button>
    <button class="ghost small" data-remove-doc="${d.id}" data-name="${esc(d.original_name)}">Remove</button></div>`).join("")
    + `<div class="slot add" data-slot="${type}"><button class="ghost small" data-upload="${type}">+ Add another ${type === "other" ? "document" : esc(docLabel(type))}</button></div>`;
}

// The files picked, [] when cancelled; one only when replacing.
function pickFile(many = true) {
  return new Promise(res => {
    const i = $("#filePick"); i.value = ""; i.multiple = many;
    i.onchange = () => res([...i.files]); i.oncancel = () => res([]); i.click();
  });
}

// Each file is stored as its own document of the type; with replaces, the one file takes that document's place (the
// old one is kept in its history). A file refused (a .zip, say) doesn't stop the rest, and the error names each one
// not added. The page is refreshed once afterwards.
async function uploadFiles(files, fields) {
  if (!files.length) return;
  const refused = [];
  for (const f of files) {
    const fd = new FormData(); fd.append("file", f);
    for (const [k, v] of Object.entries(fields)) if (v != null) fd.append(k, v);
    try { await api("/api/upload", { form: fd }); } catch (e) { refused.push(`${f.name} wasn't added: ${e.message}`); }
  }
  const n = files.length - refused.length;
  if (n) await render();
  if (refused.length) throw new Error((n ? `Added ${n} of ${files.length} files. ` : "") + refused.join(" "));
  toast(fields.replaces ? `Replaced with ${files[0].name}` : n > 1 ? `Added ${n} files` : `Added ${files[0].name}`);
}

