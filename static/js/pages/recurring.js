"use strict";
/* ---------------- Recurring payees ---------------- */
// What a change to a recurring payment (a save, stop, use again, a salary advance) did to the months already set up.
function savedCard(ch, head = "Saved") {
  if (!ch || !(ch.changes?.length || ch.kept?.length)) return "";
  return `<div class="card"><h3>${esc(head)}. Months already set up:</h3>
    ${(ch.changes || []).map(x => `<div class="note">${esc(x)}</div>`).join("")}
    ${ch.kept?.length ? `<div class="note"><b>Left as they were</b> (paid, linked, changed by hand, or already due; change them by hand if needed): ${ch.kept.map(esc).join("; ")}</div>` : ""}</div>`;
}

// The Recurring page, or the Recurring payments section of Setup: main is the element it is drawn in.
async function viewPayees(main) {
  const e = ent();
  if (!e) { main.innerHTML = `<div class="card"><h1>Recurring payments</h1><div class="note">Add a company first, under Setup › Companies.</div></div>`; return; }
  const list = await api(`/api/payees?entity=${state.entity}&month=${state.month}`);
  // A month not set up gets the card that sets it up, rather than an Add button per row that would set it all up.
  const m = await api(`/api/month?entity=${state.entity}&month=${state.month}`);
  const cats = state.meta.categories, mon = MONTHS[+state.month.slice(5) - 1];
  // What the last save changed in the months already set up, shown once (a save that couldn't keep its drawer open).
  const ch = state.payeeSaved; state.payeeSaved = null;
  const saved = savedCard(ch);
  // The supplier or customer it is linked to, if any: from the page's list, else as the server names it.
  const partyOf = p => { const pt = partyById(p.party_id); return pt || (p.party_id != null && p.party_name ? { name: p.party_name, sql_code: p.party_code, kind: p.party_kind } : null); };
  const partyNote = p => { const pt = partyOf(p);
    return pt ? `<div class="note">${esc(PARTY_KIND[pt.kind] || "Supplier or customer")}: ${esc(pt.name)}${pt.sql_code ? ` · <span class="mono">${esc(pt.sql_code)}</span>` : ""}</div>` : ""; };
  const payeeRow = p => `<tr><td><b>${esc(p.name)}</b><div class="note">${esc(p.desc_template)}</div>${partyNote(p)}
      ${p.start_date ? `<div class="note">Starts ${fmtDate(p.start_date)}</div>` : ""}${p.end_date ? `<div class="note">Ends ${fmtDate(p.end_date)}</div>` : ""}
      ${p.notes ? `<div class="note">${esc(p.notes)}</div>` : ""}${p.advances.map(a => `<div class="note">Advance: −${money(a.monthly_deduction)} a month, ${a.start_month} to ${a.end_month}</div>`).join("")}</td>
      <td>${p.direction === "in" ? `<span class="pill ok">Money in</span> ` : ""}${esc(cats[p.category] || p.category)}</td><td>${p.month_offset ? "Next month" : "Same month"}, day ${p.due_day}</td>
      <td class="num">${money(p.amount, p.currency)}${p.amount_varies ? `<div class="note">varies</div>` : ""}</td>
      <td class="mono">${esc(p.bank_details || p.reference || "")}</td>
      <td>${p.active ? `<span class="pill ok">Active</span>` : `<span class="pill grey">Stopped</span>`}</td>
      <td><div class="row"><button class="ghost small" data-edit-payee="${p.id}">Edit</button>${p.in_month ? `<span class="pill ok">In ${mon} ✓</span>`
        : !p.employed ? `<span class="muted">Not employed in ${mon}</span>` : m.set_up ? `<button class="ghost small" data-add-month="${p.id}">Add to ${mon}</button>` : ""}</div></td></tr>`;
  const payeeText = p => [p.name, p.desc_template, p.notes, p.start_date, p.end_date, fmtDate(p.start_date), fmtDate(p.end_date), cats[p.category], p.category,
    p.direction === "in" ? "money in" : "", p.bank_details, p.reference, LT.amount(p.amount), p.currency, p.active ? "active" : "stopped",
    partyOf(p)?.name, partyOf(p)?.sql_code, ...p.advances.map(a => `advance ${LT.amount(a.monthly_deduction)}`)].join(" ");
  const payeeTable = () => {
    const rows = listRows("payees", list, payeeText);
    setCount("payees", rows.length, list.length);
    return `<table><thead><tr>${sortTh("payees", "name", "Payee")}${sortTh("payees", "type", "Type")}${sortTh("payees", "when", "Paid / received")}${sortTh("payees", "amount", "Usual amount", "num")}${sortTh("payees", "bank", "Bank / ref")}${sortTh("payees", "status", "Status")}<th></th></tr></thead><tbody>
      ${rows.map(payeeRow).join("") || `<tr><td colspan="7" class="empty">${list.length ? "No recurring payment matches." : "None yet."}</td></tr>`}
      </tbody></table>`;
  };
  main.innerHTML = `${entityPicker()}${saved}${m.set_up ? "" : notSetUp(m.entity, m.month)}
    <div class="card"><div class="row spread"><h1>Recurring payments · ${esc(e.code)}</h1><button class="btn" data-edit-payee="new">Add recurring payment</button></div>
      <div class="note">Each active row is added to a month when the month is set up. Saving a change also updates the payments not due yet in ${esc(monthName(currentCycle()))} and later months already set up, unless they were paid, linked or changed by hand. Payments already due are left as they were: they were most likely paid already.</div>
      <div class="row">${listBar("payees", "recurring payments")}${deletedToggle("payees")}</div>
      <div class="tbl-wrap" id="payeeTable">${payeeTable()}</div><div id="setupDeleted"></div></div>`;
  drawDeleted("payees");
  setCount("payees", list.length, list.length); paintCount("payees");
  LIST_REDRAW.payees = () => { $("#payeeTable").innerHTML = payeeTable(); paintCount("payees"); };
  state.payees = list;
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

// The recurring payment's drawer. Opened again after a change made in it (saved: what the change did to the months
// already set up; keep: what was typed elsewhere in the drawer and not saved yet).
async function editPayee(id, { saved = null, keep = {} } = {}) {
  const e = ent(), def = payeeDefaults();
  const p = id === "new" ? { name: "", category: def.category, desc_template: "", amount: "", amount_varies: 0, month_offset: def.month_offset, due_day: def.due_day,
    active: 1, account_id: defaultAccount(e)?.id, advances: [] } : state.payees?.find(x => x.id === +id);
  if (!e || !p) return closeDrawer(true);
  const usage = id === "new" ? null : await api(`/api/payees/${p.id}/usage`).catch(() => null);
  state.openPayment = null; state.why = null;
  const pdir = p.direction || catDir(p.category), into = pdir === "in";
  const acts = id === "new" ? "" : `<div><h3>Where used</h3>${usage ? usedHtml(usage.used_by) : `<div class="note">Couldn't read where it is used.</div>`}</div>
    <div class="row">${p.active ? `<button class="ghost" type="button" data-payee-act="stop" data-payee-id="${p.id}">Stop using</button>`
      : `<button class="ghost" type="button" data-payee-act="use" data-payee-id="${p.id}">Use again</button>`}
      ${usage?.can_delete ? `<button class="btn danger small" type="button" data-payee-act="delete" data-payee-id="${p.id}">Delete</button>` : ""}</div>
    <div class="note">${p.active ? "Stopping it takes it off the months not due yet and leaves it out of new months; its history stays." : "Stopped: it isn't added to new months. Use again puts it back."}${usage?.can_delete ? "" : " It can't be deleted once it has been used; stop using it instead."}</div>
    ${whyForm()}`;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Recurring payment · ${esc(e.code)}</div><h2>${id === "new" ? "Add recurring payment" : esc(p.name)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${id === "new" ? "" : `<div class="row">${p.active ? `<span class="pill ok">In use</span>` : `<span class="pill grey">Stopped</span>`}</div>`}</div>
    ${savedCard(saved, saved?.head || "Saved")}
    <form class="form" id="payeeForm" style="grid-template-columns:1fr 1fr">
      <label class="field" style="grid-column:1/-1"><span>Payee</span><input id="py-name" value="${esc(p.name)}" required></label>
      <label class="field" style="grid-column:1/-1"><span>Description each month ({M} = payroll month, {M+1} = next month)</span><input id="py-desc" value="${esc(p.desc_template)}" placeholder="Electricity - {M}"></label>
      <label class="field"><span>Money</span><select id="py-dir"><option value="out">Money out (a payment)</option><option value="in" ${into ? "selected" : ""}>Money in (received)</option></select></label>
      <label class="field"><span>Type</span><select id="py-cat">${typeOptions(p.category, pdir, id === "new" ? null : p.category)}</select></label>
      <label class="field" id="py-party-f" style="grid-column:1/-1"${PERSONAL_TYPES.includes(p.category) ? " hidden" : ""}><span id="py-party-lbl">${into ? "Customer (optional)" : "Supplier (optional)"}</span>
        <select id="py-party">${partyOptions(e, pdir, p.party_id ?? null, p.party_id ?? null)}</select><span class="note">SQL entries with its code are matched to this payment first.</span></label>
      <label class="field"><span id="py-acct-lbl">${into ? "Paid into" : "Pay from"}</span><select id="py-acct">${pickAccounts(e, p.account_id).map(a => acctOption(a, p.account_id)).join("")}</select></label>
      <label class="field"><span>Usual amount</span><input id="py-amt" type="number" step="0.01" value="${p.amount ?? ""}"></label>
      <label class="field"><span>Amount changes monthly</span><select id="py-var"><option value="0">No, fixed</option><option value="1" ${p.amount_varies ? "selected" : ""}>Yes, estimate</option></select></label>
      <label class="field"><span id="py-off-lbl">${into ? "Received in" : "Paid in"}</span><select id="py-off"><option value="0">The payroll month</option><option value="1" ${p.month_offset ? "selected" : ""}>The following month</option></select></label>
      <label class="field"><span>Day of month</span><input id="py-day" type="number" min="1" max="31" value="${p.due_day}"></label>
      <label class="field"><span>Bank details</span><input id="py-bank" value="${esc(p.bank_details || "")}"></label>
      <label class="field"><span>Account / ref no.</span><input id="py-ref" value="${esc(p.reference || "")}"></label>
      <label class="field" style="grid-column:1/-1"><span>Words that appear in the bank statement (for automatic matching)</span><input id="py-match" value="${esc(p.match_words || "")}"></label>
      <label class="field"><span>Start date (joiners)</span><input id="py-start" type="date" value="${esc(p.start_date || "")}"></label>
      <label class="field"><span>Last day (leavers)</span><input id="py-end" type="date" value="${esc(p.end_date || "")}"></label>
      <div class="note" style="grid-column:1/-1">Salaries are prorated by calendar days in the joining and leaving months. No payment is created before the start date or after the last day. ${esc(reminderNote())}</div>
      <label class="field" style="grid-column:1/-1"><span>Notes</span><input id="py-notes" value="${esc(p.notes || "")}"></label>
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">${id === "new" ? "Add recurring payment" : "Save"}</button></div>
    </form>
    ${id === "new" || !(["salary", "director"].includes(p.category) || p.advances?.length) ? "" : advancesHtml(p)}
    ${acts}
    ${id === "new" ? "" : histSection("payees", p.id)}`;
  $("#drawer").hidden = false;
  watchDrawer(keep);
  // Money in offers the types of money received, money out the others; a type chosen sets the way the money goes.
  const labels = () => { const into = $("#py-dir").value === "in"; $("#py-acct-lbl").textContent = into ? "Paid into" : "Pay from"; $("#py-off-lbl").textContent = into ? "Received in" : "Paid in"; };
  // The supplier or customer: hidden for a salary or director's fee (paid to a person); its label and choices follow the
  // way the money goes; the one chosen stays when it still fits (want: a value typed before the drawer was drawn again).
  const party = want => {
    const s = $("#py-party"), dir = $("#py-dir").value, v = want !== undefined ? want : s.value;
    $("#py-party-f").hidden = PERSONAL_TYPES.includes($("#py-cat").value);
    $("#py-party-lbl").textContent = dir === "in" ? "Customer (optional)" : "Supplier (optional)";
    s.innerHTML = partyOptions(e, dir, v === "" || v == null ? null : +v, p.party_id ?? null);
  };
  const fill = pairTypeDir($("#py-cat"), $("#py-dir"), { setting: true, keep: id === "new" ? null : p.category, then: () => { labels(); party(); } });
  // A direction typed before the drawer was drawn again needs its own types before the type typed can be chosen, and its
  // own suppliers or customers before the one typed can be chosen.
  if (keep["py-dir"] || keep["py-cat"]) { fill(keep["py-cat"] || $("#py-cat").value); labels(); }
  party("py-party" in keep ? keep["py-party"] : undefined);
  $("#payeeForm").onsubmit = async ev => {
    ev.preventDefault();
    const body = { entity_id: state.entity, name: $("#py-name").value.trim(), desc_template: $("#py-desc").value.trim() || $("#py-name").value.trim() + " - {M}",
      direction: $("#py-dir").value, category: $("#py-cat").value, account_id: +$("#py-acct").value, amount: $("#py-amt").value === "" ? null : +$("#py-amt").value,
      amount_varies: +$("#py-var").value, month_offset: +$("#py-off").value, due_day: +$("#py-day").value || def.due_day,
      bank_details: $("#py-bank").value.trim(), reference: $("#py-ref").value.trim(), match_words: $("#py-match").value.trim(),
      start_date: $("#py-start").value || null, end_date: $("#py-end").value || null, notes: $("#py-notes").value.trim(),
      party_id: $("#py-party-f").hidden || $("#py-party").value === "" ? null : +$("#py-party").value };
    if (id !== "new") body.id = +id;
    const btn = ev.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const r = await api("/api/payees", { json: body });
      const keep = Object.fromEntries(Object.entries(drawerEdits()).filter(([k]) => k.startsWith("adv-")));  // an advance being typed stays
      toast("Saved");
      await render();  // the list, and state.payees with the row as saved
      // The drawer stays open on the saved row. A new one is found by its id if the server gives it, else by its name.
      const same = state.payees?.filter(x => x.name === body.name) || [];
      const nid = id !== "new" ? +id : r.id ?? (same.length ? Math.max(...same.map(x => x.id)) : null);
      if (nid && state.payees?.some(x => x.id === nid)) return await editPayee(nid, { saved: r, keep: id === "new" ? {} : keep });
      state.payeeSaved = r; closeDrawer(true); render();
    } catch (e) { toast(e.message, true); }
    finally { if (btn.isConnected) btn.disabled = false; }
  };
}

// A recurring payment's salary advances (recovered by a monthly deduction), each saved or removed on its own, and a row
// to add one.
function advancesHtml(p) {
  const row = (a, k) => `<div class="adv-row" id="adv-${k}">
      <label class="field"><span>Monthly deduction</span><input id="adv-${k}-amt" type="number" step="0.01" min="0" value="${a.monthly_deduction ?? ""}"></label>
      <label class="field"><span>First month</span><input id="adv-${k}-from" type="month" value="${esc(a.start_month || "")}"></label>
      <label class="field"><span>Last month</span><input id="adv-${k}-to" type="month" value="${esc(a.end_month || "")}"></label>
      <label class="field adv-note"><span>Note</span><input id="adv-${k}-note" maxlength="200" value="${esc(a.note || "")}"></label>
      <div class="row adv-act">${k === "new" ? `<button class="ghost small" type="button" data-adv-add="${p.id}">Add advance</button>`
        : `<button class="ghost small" type="button" data-adv-save="${a.id}">Save</button><button class="btn danger small" type="button" data-adv-del="${a.id}">Remove</button>`}</div></div>`;
  return `<div class="adv"><h3>Salary advances</h3>
    <div class="note">An advance is recovered by taking the monthly deduction off this payment from its first month to its last.</div>
    ${(p.advances || []).map(a => row(a, a.id)).join("") || `<div class="note">None.</div>`}
    <div class="eyebrow">Add an advance</div>${row({}, "new")}</div>`;
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
  await render();
  return editPayee(pid, { saved: r && { ...r, head }, keep });
}
async function payeeAct(act, pid, btn) {
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  return askWhy(btn, label, async reason => {
    if (act === "delete") {
      await api(`/api/payees/${pid}`, { method: "DELETE", json: { reason } });
      closeDrawer(true); toast("Recurring payment deleted"); return render();
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
  try { const r = await api(`/api/payees/${pid}/advances`, { json: body }); toast("Advance added"); return await payeeChanged(pid, r, "Advance added", "adv-new-"); }
  finally { if (btn.isConnected) btn.disabled = false; }
}
async function advSave(aid, btn) {
  const pid = state.payees?.find(p => (p.advances || []).some(a => a.id === aid))?.id;
  btn.disabled = true;
  try { const r = await api(`/api/advances/${aid}`, { method: "PATCH", json: advBody(aid) }); toast("Advance saved"); return await payeeChanged(pid, r, "Advance saved", `adv-${aid}-`); }
  finally { if (btn.isConnected) btn.disabled = false; }
}
function advDelete(aid, btn) {
  const pid = state.payees?.find(p => (p.advances || []).some(a => a.id === aid))?.id;
  return askWhy(btn, "Remove it", async reason => {
    const r = await api(`/api/advances/${aid}`, { method: "DELETE", json: { reason } });
    toast("Advance removed"); return payeeChanged(pid, r, "Advance removed", `adv-${aid}-`);
  });
}

