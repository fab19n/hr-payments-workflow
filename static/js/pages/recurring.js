"use strict";
/* ---------------- Payments › Recurring (slice 8) ----------------
   View key payees, address #/<CODE>/<YYYY-MM>/payments/recurring; also drawn in Setup's Recurring payments section (Admin ›
   Setup, with the company buttons there). Built to design/canvas/Recurring.dc.html: the head with Excel and Add recurring
   payment, the month not set up yet, the search with its count, Show stopped and Show deleted, the type filter (Setup's
   payment types, with how many of each), the table sorted by any column, 25 rows at a time, Add to <month> on a row, and the
   recurring payment's form (its fields in the board's order, checked before it is sent, with Stop using, Use again, Delete,
   Where used, History). Salary advances stay in the form until HR › Claims and advances (slice 14). */

// What a change to a recurring payment (a save, stop, use again, a salary advance) did to the months already set up.
function savedCard(ch, head = "Saved") {
  if (!ch || !(ch.changes?.length || ch.kept?.length)) return "";
  return `<div class="card rc-result" role="status"><h3>${icon("check")}${esc(head)}. Months already set up:</h3>
    ${(ch.changes || []).map(x => `<div class="note">${esc(x)}</div>`).join("")}
    ${ch.kept?.length ? `<div class="note"><b>Left as they were</b> (paid, linked, changed by hand, or already due; change them by hand if needed): ${ch.kept.map(esc).join("; ")}</div>` : ""}
    <div class="note small">Months not set up yet get these figures when they are set up.</div></div>`;
}

// What the page keeps while it is on one company: the type picked, whether stopped ones show, how many rows show.
const RC = { key: null, type: "all", stopped: true, shown: 25 };
const RC_STEP = 25;
const rcType = p => state.meta.categories[p.category] || p.category;
const rcGlyph = p => p.direction === "in" ? "coins" : p.category === "salary" ? "staff" : ["director", "consultant"].includes(p.category) ? "person" : p.category === "statutory" ? "statutory" : "receipt";

// The Recurring page, or the Recurring payments section of Setup: main is the element it is drawn in.
async function viewPayees(main) { return pageDraw("main", page => payeesDraw(page, main)); }
async function payeesDraw(page, main) {
  const e = ent(), inSetup = state.view === "setup";
  if (!e) { main.innerHTML = emptyState({ glyph: "recurring", title: "Recurring payments", body: "Add a company first, under Setup › Companies." }); return; }
  if (RC.key !== e.id) Object.assign(RC, { key: e.id, type: "all", stopped: true, shown: RC_STEP });
  const list = await page.read(api(`/api/payees?entity=${state.entity}&month=${state.month}`));
  // A month not set up gets the card that sets it up, rather than an Add button per row that would set it all up.
  const m = await page.read(api(`/api/month?entity=${state.entity}&month=${state.month}`));
  const mon = MONTHS[+state.month.slice(5) - 1];
  // What the last save changed in the months already set up, shown once (a save that couldn't keep its drawer open).
  const ch = state.payeeSaved; state.payeeSaved = null;
  // The supplier or customer it is linked to, if any: from the page's list, else as the server names it.
  const partyOf = p => { const pt = partyById(p.party_id); return pt || (p.party_id != null && p.party_name ? { name: p.party_name, sql_code: p.party_code, kind: p.party_kind } : null); };
  const partyNote = p => { const pt = partyOf(p);
    return pt ? `<div class="note">${esc(PARTY_KIND[pt.kind] || "Supplier or customer")}: ${esc(pt.name)}${pt.sql_code ? ` · <span class="mono">${esc(pt.sql_code)}</span>` : ""}</div>` : ""; };
  const monthCell = p => p.in_month ? `<span class="rc-in">${icon("check")}In ${mon} ✓</span>`
    : !p.employed ? `<span class="muted small">Not employed in ${mon}</span>`
    : m.set_up ? `<button type="button" class="ghost small" data-add-month="${p.id}">Add to ${mon}</button>` : "";  // a stopped one too: its last payment
  const payeeRow = p => `<tr class="${p.active ? "" : "rc-stopped"}"><td><div class="rc-name"><span class="rc-glyph" aria-hidden="true">${icon(rcGlyph(p))}</span><div>
      <button type="button" class="pname" data-edit-payee="${p.id}">${esc(p.name)}</button><div class="note">${esc(p.desc_template)}</div>${partyNote(p)}
      ${p.start_date ? `<div class="note">Starts ${fmtDate(p.start_date)}</div>` : ""}${p.end_date ? `<div class="note">Ends ${fmtDate(p.end_date)}</div>` : ""}
      ${p.notes ? `<div class="note">${esc(p.notes)}</div>` : ""}${p.advances.map(a => `<div class="note">Advance: −${money(a.monthly_deduction)} a month, ${a.start_month} to ${a.end_month}</div>`).join("")}</div></div></td>
      <td>${p.direction === "in" ? `<span class="pill ok">Money in</span> ` : ""}${esc(rcType(p))}</td><td>${p.month_offset ? "Next month" : "Same month"}, day ${p.due_day}</td>
      <td class="num${p.direction === "in" ? " rc-inflow" : ""}">${p.amount == null ? "—" : (p.direction === "in" ? "+" : "") + money(p.amount, p.currency)}${p.amount_varies ? `<div class="note">varies</div>` : ""}</td>
      <td class="mono">${esc(p.bank_details || p.reference || "")}</td>
      <td><div class="rc-status">${p.active ? `<span class="pill ok">Active</span>` : `<span class="pill grey">Stopped</span>`}${monthCell(p)}</div></td></tr>`;
  const payeeText = p => [p.name, p.desc_template, p.notes, p.start_date, p.end_date, fmtDate(p.start_date), fmtDate(p.end_date), rcType(p), p.category,
    p.direction === "in" ? "money in" : "", p.bank_details, p.reference, p.match_words, LT.amount(p.amount), p.currency, p.active ? "active" : "stopped",
    partyOf(p)?.name, partyOf(p)?.sql_code, ...p.advances.map(a => `advance ${LT.amount(a.monthly_deduction)}`)].join(" ");
  // The type filter: Setup's payment types the company's recurring payments use, in Setup's order, with how many of each.
  const typeKeys = Object.keys(state.meta.categories).filter(k => list.some(p => p.category === k) || k === RC.type);
  for (const p of list) if (!typeKeys.includes(p.category)) typeKeys.push(p.category);
  const chips = () => [["all", "All", list.length], ...typeKeys.map(k => [k, state.meta.categories[k] || k, list.filter(p => p.category === k).length])]
    .map(([k, label, n]) => `<button type="button" class="rc-chip" data-rc-type="${esc(k)}" aria-pressed="${RC.type === k}">${esc(label)} <span class="tab-n">${n}</span></button>`).join("");
  const payeeTable = () => {
    const pool = list.filter(p => (RC.stopped || p.active) && (RC.type === "all" || p.category === RC.type));
    const rows = listRows("payees", pool, payeeText);
    setCount("payees", rows.length, list.length);
    const q = listState("payees").q.trim();
    const empty = !list.length ? emptyState({ glyph: "recurring", title: "No recurring payments yet", body: "Add the payments that repeat every month, such as rent and salaries. Setting up a month then adds them for you.",
        action: { label: "Add a recurring payment", attr: "data-edit-payee", value: "new", glyph: "plus" } })
      : !rows.length ? emptyState({ compact: true, title: "No recurring payment matches", body: `Nothing matches${q ? ` “${q}”` : ""}${RC.type !== "all" ? ` in ${state.meta.categories[RC.type] || RC.type}` : ""}${RC.stopped ? "" : ", with stopped ones hidden"}. Try fewer words.`,
        action: { label: "Clear the search and filter", attr: "data-rc-clear", value: "1" } }) : "";
    if (empty) return `<div class="list-empty">${empty}</div>`;
    return `<div class="tbl-wrap" role="region" aria-label="Recurring payments, scrolls" tabindex="0"><table class="rc-tbl"><thead><tr>${sortTh("payees", "name", "Payee")}${sortTh("payees", "type", "Type")}${sortTh("payees", "when", "Paid / received")}${sortTh("payees", "amount", "Usual amount", "num")}${sortTh("payees", "bank", "Bank / ref")}${sortTh("payees", "status", "Status")}</tr></thead><tbody>
      ${slice(rows, RC.shown).map(payeeRow).join("")}</tbody></table></div>${manyRows({ shown: Math.min(RC.shown, rows.length), total: rows.length > RC_STEP ? rows.length : 0, what: "recurring payments", attr: "data-rc-more" })}`;
  };
  const eyebrow = inSetup ? "Admin › Setup · People and payments" : "Payments · sets up each payroll month";
  main.innerHTML = `<div id="rc" class="rc">${inSetup ? entityPicker() : ""}
    <div class="pg-head"><div class="pg-words"><span class="eyebrow">${esc(eyebrow)}</span><h1 id="pg-h1" tabindex="-1">Recurring payments${inSetup ? ` · ${esc(e.code)}` : ""}</h1>
      <p class="rc-lede">Each active row is added to a month when the month is set up. Saving a change also updates payments not due yet that you haven't changed by hand, in ${esc(monthName(currentCycle()))} and later months already set up. Payments already due are left as they were: they were most likely paid already.</p></div>
      <div class="row noprint pg-actions"><a class="ghost" id="rc-excel" href="/api/export/recurring.xlsx?entity_id=${e.id}" download>${icon("download")}Excel</a>
        <button type="button" class="btn" id="rc-add" data-edit-payee="new">${icon("plus")}Add recurring payment</button></div></div>
    ${savedCard(ch)}${m.set_up ? "" : notSetUp(m.entity, m.month)}
    <section class="card rc-card" aria-label="Recurring payments">
      <div class="rc-top">${listBar("payees", "recurring payments")}
        <label class="rc-check"><input type="checkbox" id="rc-stopped"${RC.stopped ? " checked" : ""}> Show stopped</label>${deletedToggle("payees")}</div>
      <div class="rc-chips" role="group" aria-label="Filter by type" id="rcChips">${chips()}</div>
      <div id="payeeTable">${payeeTable()}</div>
    </section><div id="setupDeleted" class="card rc-deleted"></div></div>`;
  drawDeleted("payees");
  paintCount("payees");
  RC.redraw = () => { const t = $("#payeeTable"), c = $("#rcChips"); if (t) t.innerHTML = payeeTable(); if (c) c.innerHTML = chips(); paintCount("payees"); };
  LIST_REDRAW.payees = () => { RC.shown = RC_STEP; RC.redraw(); };
  state.payees = list;
}
// The list's own controls (core/events.js and core/listeners.js call these): a type picked, Show stopped, Show more, Clear.
function rcPick(what, value) {
  if (what === "type") { RC.type = value; RC.shown = RC_STEP; RC.redraw?.(); return document.querySelector?.(`[data-rc-type="${CSS.escape(value)}"]`)?.focus({ preventScroll: true }); }
  if (what === "stopped") { RC.stopped = !!value; RC.shown = RC_STEP; return RC.redraw?.(); }
  if (what === "more") { RC.shown += RC_STEP; return RC.redraw?.(); }
  if (what === "clear") {
    Object.assign(RC, { type: "all", stopped: true, shown: RC_STEP }); listState("payees").q = "";
    const q = document.querySelector?.('[data-search="payees"]'); if (q) q.value = "";
    const s = $("#rc-stopped"); if (s) s.checked = true;
    RC.redraw?.(); return q?.focus?.();
  }
}

// A number from the settings, or d when it isn't one.
const numOr = (v, d) => v == null || v === "" || Number.isNaN(+v) ? d : +v;
// The defaults of a new recurring payment, from General settings.
function payeeDefaults() {
  const S = state.meta.settings || {};
  return { category: defaultType("out", true), month_offset: numOr(S.payee_default_month_offset, 1) ? 1 : 0,
    due_day: Math.min(31, Math.max(1, numOr(S.payee_default_due_day, 6))) };
}
// "12 payments, 3 budget lines", from the server's [label, count] pairs.
const usedText = u => (u || []).filter(x => +x[1]).map(([l, n]) => `${n} ${l}`).join(", ");
const usedHtml = u => usedText(u) ? `<ul class="used">${u.filter(x => +x[1]).map(([l, n]) => `<li>${esc(n)} ${esc(l)}</li>`).join("")}</ul>`
  : `<div class="note">Not used anywhere yet.</div>`;

// The form's own checks, before anything is sent (Recurring.dc.html "errors"): {field id: message}.
function payeeErrors() {
  const out = {}, amt = $("#py-amt").value.trim(), day = $("#py-day").value.trim(), start = $("#py-start").value, end = $("#py-end").value;
  if (!$("#py-name").value.trim()) out["py-name"] = "Enter a name.";
  if (amt.startsWith("-")) out["py-amt"] = "Usual amount: give the amount without a minus sign; choose Money in or Money out for its direction.";
  else if (amt && !/^\d+(\.\d{1,2})?$/.test(amt.replace(/,/g, ""))) out["py-amt"] = "Usual amount: give a number, or leave it empty if it changes every month.";
  if (!day) out["py-day"] = "Enter the day of the month.";
  else if (!/^\d+$/.test(day) || +day < 1 || +day > 31) out["py-day"] = "The day of the month is a whole number from 1 to 31.";
  if (start && end && end < start) out["py-end"] = "The last day can't be before the start date.";
  return out;
}

// The recurring payment's drawer. Opened again after a change made in it (saved: what the change did to the months
// already set up; keep: what was typed elsewhere in the drawer and not saved yet).
async function editPayee(id, opts) { return dialogDraw(dlg => payeeDialog(dlg, id, opts)); }
async function payeeDialog(dlg, id, { saved = null, keep = {} } = {}) {
  const e = ent(), def = payeeDefaults();
  const p = id === "new" ? { name: "", category: def.category, desc_template: "", amount: "", amount_varies: 0, month_offset: def.month_offset, due_day: def.due_day,
    active: 1, account_id: defaultAccount(e)?.id, advances: [] } : state.payees?.find(x => x.id === +id);
  if (!e || !p) return closeDrawer(true);
  const usage = id === "new" ? null : await dlg.read(api(`/api/payees/${p.id}/usage`).catch(() => null));
  state.openPayment = null; state.why = null;
  const pdir = p.direction || catDir(p.category), into = pdir === "in", personal = PERSONAL_TYPES.includes(p.category);
  const req = `<span class="req">Required</span>`;
  const acts = id === "new" ? "" : `<section class="rc-used" aria-labelledby="rc-used-h"><h3 id="rc-used-h">Where used</h3>${usage ? usedHtml(usage.used_by) : `<div class="note">Couldn't read where it is used.</div>`}
    <div class="note">${p.active ? "Stopping it takes it off the months not due yet and leaves it out of new months; its history stays." : "Stopped: it isn't added to new months. Use again puts it back."}${usage?.can_delete ? "" : " It can't be deleted once it has been used; stop using it instead."}</div>
    <div class="row">${p.active ? `<button class="ghost danger-text" type="button" data-payee-act="stop" data-payee-id="${p.id}">Stop using</button>`
      : `<button class="ghost" type="button" data-payee-act="use" data-payee-id="${p.id}">Use again</button>`}
      ${usage?.can_delete ? `<button class="btn danger small" type="button" data-payee-act="delete" data-payee-id="${p.id}">Delete</button>` : ""}</div>
    ${whyForm()}</section>`;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div class="rc-dhead"><span class="rc-plate" aria-hidden="true">${icon(id === "new" ? "plus" : rcGlyph({ ...p, direction: pdir }))}</span><div>
        <div class="eyebrow">${id === "new" ? `Recurring payment · ${esc(e.code)}` : `${esc(rcType(p))}${into ? " · money in" : ""} · ${esc(e.code)}`}</div>
        <h2 id="drawerTitle" tabindex="-1">${id === "new" ? "Add recurring payment" : esc(p.name)}</h2></div></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${id === "new" ? "" : `<div class="row">${p.active ? `<span class="pill ok">In use</span>` : `<span class="pill grey">Stopped</span>`}</div>`}</div>
    ${savedCard(saved, saved?.head || "Saved")}
    <form class="form rc-form" id="payeeForm" novalidate>
      <label class="field"><span>Money</span><select id="py-dir"><option value="out">Money out (a payment)</option><option value="in" ${into ? "selected" : ""}>Money in (received)</option></select></label>
      <label class="field"><span>Type</span><select id="py-cat" aria-describedby="py-cat-hint">${typeOptions(p.category, pdir, id === "new" ? null : p.category)}</select>
        <span class="note" id="py-cat-hint"${personal ? "" : " hidden"}>Salaries and director fees are paid to a person, so there is no supplier to choose.</span></label>
      <label class="field span"><span>Payee ${req}</span><input id="py-name" value="${esc(p.name)}" required autocomplete="off"></label>
      <label class="field span"><span>Description each month ({M} = payroll month, {M+1} = next month)</span><input id="py-desc" value="${esc(p.desc_template)}" placeholder="Electricity - {M}" autocomplete="off"></label>
      <label class="field span" id="py-party-f"${personal ? " hidden" : ""}><span id="py-party-lbl">${into ? "Customer (optional)" : "Supplier (optional)"}</span>
        <select id="py-party">${partyOptions(e, pdir, p.party_id ?? null, p.party_id ?? null)}</select><span class="note">SQL entries with its code are matched to this payment first.</span></label>
      <label class="field"><span id="py-acct-lbl">${into ? "Paid into" : "Pay from"}</span><select id="py-acct">${pickAccounts(e, p.account_id).map(a => acctOption(a, p.account_id)).join("") || `<option value="">No bank account set up yet</option>`}</select></label>
      <label class="field"><span>Usual amount</span><input id="py-amt" inputmode="decimal" class="num" autocomplete="off" value="${p.amount ?? ""}" aria-describedby="py-amt-hint"><span class="note" id="py-amt-hint">Leave it empty if it changes every month.</span></label>
      <label class="field"><span>Amount changes monthly</span><select id="py-var"><option value="0">No, fixed</option><option value="1" ${p.amount_varies ? "selected" : ""}>Yes, estimate</option></select></label>
      <label class="field"><span id="py-off-lbl">${into ? "Received in" : "Paid in"}</span><select id="py-off"><option value="0">The payroll month</option><option value="1" ${p.month_offset ? "selected" : ""}>The following month</option></select></label>
      <label class="field"><span>Day of month ${req}</span><input id="py-day" inputmode="numeric" autocomplete="off" value="${p.due_day}" aria-describedby="py-day-hint"><span class="note" id="py-day-hint">A month with fewer days uses its last day.</span></label>
      <label class="field"><span>Bank details</span><input id="py-bank" value="${esc(p.bank_details || "")}" autocomplete="off"></label>
      <label class="field"><span>Account / ref no.</span><input id="py-ref" value="${esc(p.reference || "")}" autocomplete="off"></label>
      <label class="field span"><span>Words that appear in the bank statement (for automatic matching)</span><input id="py-match" value="${esc(p.match_words || "")}" autocomplete="off"></label>
      <label class="field"><span>Start date (joiners)</span><input id="py-start" type="date" value="${esc(p.start_date || "")}"></label>
      <label class="field"><span>Last day (leavers)</span><input id="py-end" type="date" value="${esc(p.end_date || "")}"></label>
      <div class="note span">Salaries are prorated by calendar days in the joining and leaving months. No payment is created before the start date or after the last day. ${esc(reminderNote())}</div>
      <label class="field span"><span>Notes</span><input id="py-notes" value="${esc(p.notes || "")}" autocomplete="off"></label>
      <div class="row span rc-save"><button class="btn" type="submit" id="py-save">${id === "new" ? "Add recurring payment" : "Save changes"}</button></div>
    </form>
    ${id === "new" || !(["salary", "director"].includes(p.category) || p.advances?.length) ? "" : advancesHtml(p)}
    ${acts}
    ${id === "new" ? "" : histSection("payees", p.id)}`;
  showDrawer();
  watchDrawer(keep);
  // Money in offers the types of money received, money out the others; a type chosen sets the way the money goes.
  const labels = () => { const into = $("#py-dir").value === "in"; $("#py-acct-lbl").textContent = into ? "Paid into" : "Pay from"; $("#py-off-lbl").textContent = into ? "Received in" : "Paid in"; };
  // The supplier or customer: hidden for a salary or director's fee (paid to a person); its label and choices follow the
  // way the money goes; the one chosen stays when it still fits (want: a value typed before the drawer was drawn again).
  const party = want => {
    const s = $("#py-party"), dir = $("#py-dir").value, v = want !== undefined ? want : s.value, personal = PERSONAL_TYPES.includes($("#py-cat").value);
    $("#py-party-f").hidden = personal; $("#py-cat-hint").hidden = !personal;
    $("#py-party-lbl").textContent = dir === "in" ? "Customer (optional)" : "Supplier (optional)";
    s.innerHTML = partyOptions(e, dir, v === "" || v == null ? null : +v, p.party_id ?? null);
  };
  const fill = pairTypeDir($("#py-cat"), $("#py-dir"), { setting: true, keep: id === "new" ? null : p.category, then: () => { labels(); party(); } });
  // A direction typed before the drawer was drawn again needs its own types before the type typed can be chosen, and its
  // own suppliers or customers before the one typed can be chosen.
  if (keep["py-dir"] || keep["py-cat"]) { fill(keep["py-cat"] || $("#py-cat").value); labels(); }
  party("py-party" in keep ? keep["py-party"] : undefined);
  let added = false;  // this Add form's payment is in: it can't be added a second time from here
  $("#payeeForm").onsubmit = async ev => {
    ev.preventDefault();
    if (added) return toast("This was saved. Close it and open it again from the list.", true);
    // The form's own checks first: each field marked in red with what to change, the first one focused, nothing sent.
    const bad = payeeErrors();
    for (const f of ["py-name", "py-amt", "py-day", "py-end"]) markField(f, bad[f] || "");
    const first = ["py-name", "py-amt", "py-day", "py-end"].find(f => bad[f]);
    if (first) { toast("Not saved. Check the fields marked in red.", true); return document.getElementById(first)?.focus(); }
    const amt = $("#py-amt").value.replace(/,/g, "").trim();
    const body = { entity_id: state.entity, name: $("#py-name").value.trim(), desc_template: $("#py-desc").value.trim() || $("#py-name").value.trim() + " - {M}",
      direction: $("#py-dir").value, category: $("#py-cat").value, account_id: +$("#py-acct").value || null, amount: amt === "" ? null : +amt,
      amount_varies: +$("#py-var").value, month_offset: +$("#py-off").value, due_day: +$("#py-day").value || def.due_day,
      bank_details: $("#py-bank").value.trim(), reference: $("#py-ref").value.trim(), match_words: $("#py-match").value.trim(),
      start_date: $("#py-start").value || null, end_date: $("#py-end").value || null, notes: $("#py-notes").value.trim(),
      party_id: $("#py-party-f").hidden || $("#py-party").value === "" ? null : +$("#py-party").value };
    if (id !== "new") body.id = +id;
    const btn = ev.target.querySelector("button[type=submit]");
    btn.disabled = true; btn.setAttribute?.("aria-busy", "true");
    try {
      let r;
      try { r = await api("/api/payees", { json: body }); } catch (e) { return toast(changeError(e), true); }
      added = id === "new";
      const keep = Object.fromEntries(Object.entries(drawerEdits()).filter(([k]) => k.startsWith("adv-")));  // an advance being typed stays
      toast(id === "new" ? `${body.name} added` : "Saved");
      // The list is read again (and state.payees with the row as saved), and the drawer stays open on that row. A new one is found by its
      // id if the server gives it, else by its name.
      await afterSaved(render, () => {
        const same = state.payees?.filter(x => x.name === body.name) || [];
        const nid = id !== "new" ? +id : r.id ?? (same.length ? Math.max(...same.map(x => x.id)) : null);
        if (nid && state.payees?.some(x => x.id === nid)) return editPayee(nid, { saved: r, keep: id === "new" ? {} : keep });
        state.payeeSaved = r; closeDrawer(true); return afterSaved(render);
      }, { dialogSaved: k => k.startsWith("py-") });
    } finally { if (btn.isConnected) { btn.disabled = false; btn.removeAttribute?.("aria-busy"); } }
  };
}

// A recurring payment's salary advances (recovered by a monthly deduction), each saved or removed on its own, and a row
// to add one. They stay here until HR › Claims and advances (slice 14).
function advancesHtml(p) {
  const row = (a, k) => `<div class="adv-row" id="adv-${k}">
      <label class="field"><span>Monthly deduction</span><input id="adv-${k}-amt" type="number" step="0.01" min="0" value="${a.monthly_deduction ?? ""}"></label>
      <label class="field"><span>First month</span><input id="adv-${k}-from" type="month" value="${esc(a.start_month || "")}"></label>
      <label class="field"><span>Last month</span><input id="adv-${k}-to" type="month" value="${esc(a.end_month || "")}"></label>
      <label class="field adv-note"><span>Note</span><input id="adv-${k}-note" maxlength="200" value="${esc(a.note || "")}"></label>
      <div class="row adv-act">${k === "new" ? `<button class="ghost small" type="button" data-adv-add="${p.id}">Add advance</button>`
        : `<button class="ghost small" type="button" data-adv-save="${a.id}">Save</button><button class="btn danger small" type="button" data-adv-del="${a.id}">Remove</button>`}</div></div>`;
  return `<section class="adv" aria-labelledby="adv-h"><h3 id="adv-h">${icon("advance")}Salary advances</h3>
    <div class="note">An advance is recovered by taking the monthly deduction off this payment from its first month to its last.</div>
    ${(p.advances || []).map(a => row(a, a.id)).join("") || `<div class="note">None.</div>`}
    <div class="eyebrow">Add an advance</div>${row({}, "new")}</section>`;
}
const advBody = k => {
  const amt = $(`#adv-${k}-amt`).value;
  return { monthly_deduction: amt === "" ? null : +amt, start_month: $(`#adv-${k}-from`).value || null, end_month: $(`#adv-${k}-to`).value || null,
    note: $(`#adv-${k}-note`).value.trim() };
};
// After a change made in the recurring payment's drawer: the list is drawn again, then the drawer, showing what the change
// did and keeping what was typed elsewhere in it (drop: the inputs whose values were just saved).
async function payeeChanged(pid, r, head, drop = "") {
  const keep = drawerEdits();
  if (drop) for (const k in keep) if (k.startsWith(drop)) delete keep[k];
  return afterSaved(render, () => editPayee(pid, { saved: r && { ...r, head }, keep }), { dialogSaved: drop ? k => k.startsWith(drop) : false });
}
async function payeeAct(act, pid, btn) {
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  return askWhy(btn, label, async reason => {
    if (act === "delete") {
      await api(`/api/payees/${pid}`, { method: "DELETE", json: { reason } });
      closeDrawer(true); toast("Recurring payment deleted"); return afterSaved(render);
    }
    const r = await api(`/api/payees/${pid}/${act}`, { json: { reason } });
    toast(act === "stop" ? "Stopped. Its history stays." : "In use again");
    return payeeChanged(pid, r, act === "stop" ? "Stopped" : "In use again");
  });
}
async function advAdd(pid, btn) {
  const body = advBody("new");
  if (body.monthly_deduction == null || !body.start_month || !body.end_month) return toast("Type the monthly deduction and choose its first and last month.", true);
  btn.disabled = true;
  try {
    const r = await api(`/api/payees/${pid}/advances`, { json: body }).catch(e => { throw changeThrown(e); });
    // added: the row it was typed in is emptied, so a drawer left open can't add it a second time
    for (const k of ["amt", "from", "to", "note"]) { const el = $(`#adv-new-${k}`); if (el) el.value = ""; }
    toast("Advance added"); return await payeeChanged(pid, r, "Advance added", "adv-new-");
  }
  finally { if (btn.isConnected) btn.disabled = false; }
}
async function advSave(aid, btn) {
  const pid = state.payees?.find(p => (p.advances || []).some(a => a.id === aid))?.id;
  btn.disabled = true;
  try { const r = await api(`/api/advances/${aid}`, { method: "PATCH", json: advBody(aid) }).catch(e => { throw changeThrown(e); }); toast("Advance saved"); return await payeeChanged(pid, r, "Advance saved", `adv-${aid}-`); }
  finally { if (btn.isConnected) btn.disabled = false; }
}
function advDelete(aid, btn) {
  const pid = state.payees?.find(p => (p.advances || []).some(a => a.id === aid))?.id;
  return askWhy(btn, "Remove it", async reason => {
    const r = await api(`/api/advances/${aid}`, { method: "DELETE", json: { reason } });
    toast("Advance removed"); return payeeChanged(pid, r, "Advance removed", `adv-${aid}-`);
  });
}
