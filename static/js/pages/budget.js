"use strict";
/* ---------------- Budget ---------------- */
// The bank balance and the date it was taken are kept in this browser, per company and month. Payments paid on or
// before that date are already out of the balance, so the budget leaves them out (and so does the Overview).
const asAtKey = (eid, month) => `asat-${eid}-${month}`;
// A real day from the year 2000 on, as the server takes it; the date box can hold others while it is being typed in.
const isDay = v => /^[2-9]\d{3}-\d{2}-\d{2}$/.test(v) && !isNaN(new Date(v)) && new Date(v).toISOString().slice(0, 10) === v;
function storedAsAt(eid, month) {
  try { const v = localStorage.getItem(asAtKey(eid, month)) || ""; return isDay(v) ? v : ""; } catch { return ""; }
}

async function viewBudget(main) {
  const balKey = `bal-${state.entity}-${state.month}`, dateKey = asAtKey(state.entity, state.month);
  const load = asAt => api(`/api/budget?entity=${state.entity}&month=${state.month}${asAt ? "&as_at=" + asAt : ""}`);
  const stored = storedAsAt(state.entity, state.month);
  // From a row of Next up (as_at: today) the page is as at that day, which is what the row totals, not the date of the
  // balance kept in this browser. That balance is for the other date, so it is left out until that date is asked for.
  const here = state.asAt; state.asAt = null;
  let d = await load(here || stored);
  if (d.stored) return viewStoredBudget(main, d, here);
  const held = d.to_pay.length + d.paid.length;
  const setUp = d.set_up ? "" : notSetUp(d.entity, d.month, held);
  if (!d.set_up && !held && !d.previous) { main.innerHTML = entityPicker() + setUp; return; }
  let bal = ""; try { bal = localStorage.getItem(balKey) || ""; } catch {}
  const other = here && stored && stored !== here;
  if (other) bal = "";
  // A balance kept without its date (entered before dates were kept): ask for the date rather than show today's.
  const ask = bal !== "" && !stored;
  // The balance is taken around the budget month: a date typed in from the month before to the month after.
  const after = shiftMonth(state.month, 1), [ay, am] = after.split("-").map(Number);
  const first = `${shiftMonth(state.month, -1)}-01`, last = `${after}-${new Date(Date.UTC(ay, am, 0)).getUTCDate()}`;
  const inRange = v => isDay(v) && v >= first && v <= last;
  main.innerHTML = `${entityPicker()}${setUp}
    <div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(d.entity.name)}</div><h1>Budget for ${esc(d.label)}${beforeTracking(d.entity, d.month) ? ` ${BEFORE_PILL}` : ""}</h1></div>
      <button class="ghost noprint" id="printPage">Print budget</button></div>
      ${cycleNote(d)}
      <div class="note noprint">Not set up yet: this list is worked out from the month's payments and can't be edited. ${d.previous ? `Setting it up copies ${esc(monthName(shiftMonth(d.month, -1)))}'s budget with its amounts.` : "Setting it up makes a line for each payment out, which you can then change, add to and delete."} <button class="btn small" id="bud-setup">Set up budget</button></div>
      <div class="note noprint">Lists this month's payments still to pay after the date of the bank balance. Payments paid on or before that date are already out of the balance, so they are under Already paid and not counted. Change amounts on the ${esc(d.entity.code)} page; "EST" marks amounts not confirmed yet.</div>
      <div class="form" style="max-width:800px">
        <label class="field"><span>Bank balance as at</span><input id="bud-date" type="date" min="${first}" max="${last}" value="${ask ? "" : esc(d.as_at)}"></label>
        <label class="field"><span>Bank balance (RM)</span><input id="bud-bal" type="number" step="0.01" value="${esc(bal)}"></label>
        <div class="field"><span>Total budget (RM)</span><b class="mono" id="bud-total"></b></div>
        <div class="field"><span>Shortfall = fund requisition needed</span><b class="mono" id="bud-short"></b></div>
        <div class="field" id="bud-other" hidden><span>Other currencies (not in the shortfall)</span><b class="mono"></b></div>
        ${ask ? `<div class="note noprint" id="bud-ask" style="grid-column:1/-1">Enter the date this balance was taken. Until then the budget is as at today.</div>` : ""}
        ${other ? `<div class="note noprint" style="grid-column:1/-1">As at today, ${esc(shortDate(d.as_at))}, as Next up counts it. The balance you entered is as at ${esc(shortDate(stored))}: <button class="link" data-saved-balance="1">use that date</button>.</div>` : ""}
      </div>
      <div id="bud-body"></div>
    </div>`;
  $("#bud-setup")?.addEventListener("click", () => setUpBudget(d));
  const upd = () => {
    const s = (d.totals.MYR || 0) - Number($("#bud-bal").value || 0);
    $("#bud-short").textContent = s > 0 ? money(s) : "None (balance covers the budget)";
  };
  const draw = () => {
    const other = Object.entries(d.totals).filter(([cur]) => cur !== "MYR");
    $("#bud-total").textContent = money(d.totals.MYR || 0);
    $("#bud-other").hidden = !other.length;
    $("#bud-other b").textContent = other.map(([cur, n]) => money(n, cur)).join(" · ");
    $("#bud-body").innerHTML = budgetTables(d);
    upd();
  };
  $("#bud-bal").addEventListener("input", () => {
    // The date goes with the balance, so the budget stays as it was printed after later payments go out.
    try { localStorage.setItem(balKey, $("#bud-bal").value); if ($("#bud-date").value) localStorage.setItem(dateKey, d.as_at); } catch {}
    upd();
  });
  $("#bud-date").addEventListener("change", async () => {
    const v = $("#bud-date").value;
    if (!inRange(v)) return;  // still being typed
    try {
      const next = await load(v);
      if ($("#bud-date")?.value !== v) return;
      d = next; draw();
      // Kept only once accepted, so a slip of the keyboard can't stop this page and the Overview from loading later.
      try { localStorage.setItem(dateKey, v); } catch {}
      $("#bud-ask")?.remove();
    } catch (e) { toast(e.message, true); }
  });
  $("#bud-date").addEventListener("blur", () => {
    const v = $("#bud-date").value;
    if (!v || inRange(v) || v === d.as_at) return;
    $("#bud-date").value = $("#bud-ask") ? "" : d.as_at;
    toast(`Enter the date the bank balance was taken, from ${fmtDate(first)} to ${fmtDate(last)}.`, true);
  });
  draw();
}

const cycleNote = d => `<div class="note">Covers the payments for the ${esc(d.label)} payroll month, including the bills and statutory payments paid in early ${esc(monthName(shiftMonth(d.month, 1)).split(" ")[0])}.</div>`;

async function setUpBudget(d) {
  try {
    const r = await api("/api/budget/setup", { json: { entity_id: d.entity.id, month: d.month } });
    toast(`Budget set up with ${r.result} line${r.result === 1 ? "" : "s"}`); await render();
  } catch (e) { toast(e.message, true); }
}

// The stored budget: every figure is a box that saves when you leave it (or press Enter).
async function viewStoredBudget(main, d, here) {
  const eid = d.entity.id, month = d.month, balKey = `bal-${eid}-${month}`, dateKey = asAtKey(eid, month);
  // A balance and date kept in this browser before they were kept with the budget go across once.
  let local = {}; try { local = { balance: localStorage.getItem(balKey) || "", as_at: storedAsAt(eid, month) }; } catch {}
  const move = {};
  if (d.balance == null && local.balance) move.balance = local.balance;
  if (!d.saved_as_at && local.as_at) move.as_at = local.as_at;
  try {
    if (Object.keys(move).length) { await api("/api/budget/header", { json: { entity_id: eid, month, ...move } }); d = await api(`/api/budget?entity=${eid}&month=${month}${here ? "&as_at=" + here : ""}`); }
    localStorage.removeItem(balKey); localStorage.removeItem(dateKey);
  } catch {}
  const sel = new Set();
  const other = !!(here && d.saved_as_at && d.saved_as_at !== here);
  const after = shiftMonth(month, 1), [ay, am] = after.split("-").map(Number);
  const first = `${shiftMonth(month, -1)}-01`, last = `${after}-${new Date(Date.UTC(ay, am, 0)).getUTCDate()}`;
  const inRange = v => isDay(v) && v >= first && v <= last;
  const currencies = [...new Set(["MYR", ...ent().accounts.map(a => a.currency)])];
  main.innerHTML = `${entityPicker()}${d.set_up ? "" : notSetUp(d.entity, month, d.lines.length)}
    <div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(d.entity.name)}</div><h1>Budget for ${esc(d.label)}${beforeTracking(d.entity, month) ? ` ${BEFORE_PILL}` : ""}</h1></div>
      <span class="row noprint"><a class="ghost" href="/api/export/budget.xlsx?entity_id=${eid}&month=${month}&as_at=${esc(d.as_at)}">Excel</a>
      <button class="ghost" id="printPage">Print budget</button></span></div>
      ${cycleNote(d)}
      <div class="note noprint">Change any figure, description or detail here; it saves when you leave the box. The payments themselves are not changed. A payment paid on or before the balance date is already out of the balance, so it is not counted as still to pay.</div>
      <div class="form" style="max-width:800px">
        <label class="field"><span>Bank balance as at</span><input id="bud-date" type="date" min="${first}" max="${last}" value="${esc(d.as_at)}"></label>
        <label class="field"><span>Bank balance (RM)</span><input id="bud-bal" type="number" step="0.01" value="${other ? "" : esc(d.balance ?? "")}"></label>
        <div class="field"><span>Still to pay from the balance (RM)</span><b class="mono" id="bud-total"></b></div>
        <div class="field"><span>Shortfall = fund requisition needed</span><b class="mono" id="bud-short"></b></div>
        <div class="field" id="bud-other" hidden><span>Other currencies (not in the shortfall)</span><b class="mono"></b></div>
        <div class="field" id="bud-in" hidden><span>Already paid (in the balance)</span><b class="mono"></b></div>
        ${other ? `<div class="note noprint" style="grid-column:1/-1">As at today, ${esc(shortDate(d.as_at))}, as Next up counts it. The balance you entered is as at ${esc(shortDate(d.saved_as_at))}: <button class="link" data-saved-balance="1">use that date</button>.</div>` : ""}
      </div>
      <div id="bud-body"></div>
    </div>`;
  const plain = (n, cur) => money(n, cur).replace(/^\S+ /, "");
  const diffPill = (diff, cur) => Math.abs(diff) <= 0.01 ? `<span class="pill ok">Matched</span>`
    : `<span class="pill ${diff < 0 ? "warn" : "bad"}">${diff < 0 ? "Under" : "Over"} by ${money(Math.abs(diff), cur)}</span>`;
  const row = (x, i) => `<tr data-line="${x.id}">
      <td class="noprint"><input type="checkbox" data-sel="${x.id}" aria-label="Select line ${i + 1}"${sel.has(x.id) ? " checked" : ""}></td><td>${i + 1}</td>
      <td class="bl-desc"><input class="cell noprint" data-f="description" value="${esc(x.description)}" aria-label="Description"><span class="printonly">${esc(x.description)}</span>
        <input class="cell sub noprint" data-f="details" value="${esc(x.details)}" placeholder="Bank / details" aria-label="Details"><span class="printonly mono">${esc(x.details)}</span>
        ${x.in_balance ? `<div class="note noprint">Paid ${shortDate(x.paid_date)}, already in the balance</div>` : ""}</td>
      <td class="num"><input class="cell amt noprint" data-f="amount" type="number" step="0.01" min="0" value="${x.amount ?? ""}" aria-label="Budget"><span class="printonly">${x.amount == null ? "" : plain(x.amount, x.currency)}</span></td>
      <td class="num noprint">${x.paid == null ? "—" : plain(x.paid, x.currency)}<div><span class="pill ${x.status.tone}">${esc(x.status.text)}</span></div></td>
      <td class="bl-pay"><select class="cell noprint" data-f="payment_id" aria-label="Payment"><option value="">Not linked</option>${d.payments.filter(p => p.currency === x.currency && (!p.line_id || p.line_id === x.id)).map(p =>
        `<option value="${p.id}"${p.id === x.payment_id ? " selected" : ""}>${esc(p.description)} · ${plain(p.amount, p.currency)}</option>`).join("")}</select>
        <div class="note">${x.due_date ? fmtDate(x.due_date) : ""}</div></td>
      <td class="noprint"><div class="row tight"><button class="ghost small" data-hist-open="budget_lines:${x.id}" data-hist-title="${esc(x.description || `Line ${i + 1}`)}" aria-label="History of line ${i + 1}" title="History">History</button>
        <button class="ghost small" data-del="${x.id}" aria-label="Delete line ${i + 1}" title="Delete line">×</button></div></td></tr>`;
  const table = cur => {
    const list = d.lines.filter(x => x.currency === cur), sums = d.sums[cur] || { budget: 0, paid: 0, diff: 0 };
    return `<table><thead><tr><th class="noprint"></th><th>No.</th><th>Description</th><th class="num">${cur === "MYR" ? "RM" : esc(cur)} budget</th><th class="num noprint">Paid · against budget</th><th>Payment · date</th><th class="noprint"></th></tr></thead><tbody>
      ${list.map(row).join("") || `<tr><td colspan="6" class="muted">No lines.</td></tr>`}
      <tr><td class="noprint"></td><td></td><td><b>TOTAL</b></td><td class="num"><b>${plain(sums.budget, cur)}</b></td>
      <td class="num noprint"><b>${plain(sums.paid, cur)}</b><div>${list.some(x => x.paid != null) ? diffPill(sums.diff, cur) : ""}</div></td><td colspan="2" class="noprint"></td></tr></tbody></table>`;
  };
  const upd = () => {
    const s = (d.totals.MYR || 0) - Number($("#bud-bal").value || 0);
    $("#bud-short").textContent = s > 0 ? money(s) : "None (balance covers the budget)";
  };
  const draw = () => {
    const act = document.activeElement, at = act?.dataset?.f && act.closest?.("tr[data-line]");
    const keep = at ? { line: at.dataset.line, f: act.dataset.f, v: act.value } : null;
    for (const id of [...sel]) if (!d.lines.some(x => x.id === id)) sel.delete(id);
    const shown = currencies.filter(c => c === "MYR" || d.lines.some(x => x.currency === c));
    $("#bud-total").textContent = money(d.totals.MYR || 0);
    const others = Object.entries(d.totals).filter(([cur]) => cur !== "MYR");
    $("#bud-other").hidden = !others.length;
    $("#bud-other b").textContent = others.map(([cur, n]) => money(n, cur)).join(" · ");
    const inb = Object.entries(d.in_balance);
    $("#bud-in").hidden = !inb.length;
    $("#bud-in b").textContent = inb.map(([cur, n]) => money(n, cur)).join(" · ");
    $("#bud-body").innerHTML = `${budgetChart(d)}<div class="row noprint">
        <label><input type="checkbox" id="bud-all"${d.lines.length && sel.size === d.lines.length ? " checked" : ""}> Select all</label>
        <button class="ghost small" id="bud-delsel"${sel.size ? "" : " disabled"}>Delete selected${sel.size ? ` (${sel.size})` : ""}</button>
        ${currencies.map(cur => `<button class="btn small" data-add="${esc(cur)}">Add line${currencies.length > 1 ? ` (${cur === "MYR" ? "RM" : esc(cur)})` : ""}</button>`).join("")}</div>
      ${d.lines.some(x => !x.payment_id) ? `<div class="note noprint">${d.lines.filter(x => !x.payment_id).length} line(s) are not linked to a payment, so they show Not paid yet. Link them in the Payment column or delete the ones you don't need.</div>` : ""}
      <div class="tbl-wrap">${shown.map(table).join("")}</div>
      <h3>Paid but not in the budget</h3>
      ${d.not_in_budget.length ? `<div class="note">This month's payments with no line above, paid or still to pay.</div><div class="tbl-wrap"><table><thead><tr><th>Description</th><th class="num">Amount</th><th>Paid on</th><th class="noprint"></th></tr></thead><tbody>
        ${d.not_in_budget.map(p => `<tr><td>${esc(p.description)}</td><td class="num">${money(p.amount, p.currency)}</td><td>${p.paid_date ? fmtDate(p.paid_date) : `<span class="pill grey">Not paid yet</span>`}</td>
        <td class="noprint"><button class="ghost small" data-add-payment="${p.id}">Add to budget</button></td></tr>`).join("")}</tbody></table></div>`
        : `<div class="note">Every payment for this month is on a line.</div>`}`;
    upd();
    if (keep) {
      const el = $(`tr[data-line="${keep.line}"] [data-f="${keep.f}"]`);
      if (el) { el.focus(); if (el.tagName === "INPUT" && el.type !== "number") el.value = keep.v; }
    }
  };
  const refresh = async () => { d = await api(`/api/budget?entity=${eid}&month=${month}&as_at=${d.as_at}`); draw(); };
  const change = async (call, then) => {
    try { const r = await call(); await refresh(); if (then) then(r); } catch (e) { toast(e.message, true); try { await refresh(); } catch {} }
  };
  const header = body => api("/api/budget/header", { json: { entity_id: eid, month, ...body } });
  const remove = async (ids, title, text) => (await ask(text, { title, yes: "Delete", no: "Cancel", danger: true, tone: "bad", glyph: "trash" })) && change(() => api("/api/budget/lines/delete", { json: { ids } }));

  $("#bud-bal").addEventListener("input", upd);
  $("#bud-bal").addEventListener("change", () => change(() => header({ balance: $("#bud-bal").value, ...(d.saved_as_at ? { as_at: d.saved_as_at } : {}) })));
  $("#bud-date").addEventListener("change", () => {
    const v = $("#bud-date").value;
    if (!inRange(v)) return toast(`Enter the date the bank balance was taken, from ${fmtDate(first)} to ${fmtDate(last)}.`, true);
    change(async () => { await header({ as_at: v }); d.as_at = v; });
  });
  const body = $("#bud-body");
  body.addEventListener("change", e => {
    const t = e.target, tr = t.closest?.("tr[data-line]");
    if (t.id === "bud-all") { sel.clear(); if (t.checked) d.lines.forEach(x => sel.add(x.id)); return draw(); }
    if (t.dataset.sel) { t.checked ? sel.add(+t.dataset.sel) : sel.delete(+t.dataset.sel); return draw(); }
    if (!tr || !t.dataset.f) return;
    const v = t.dataset.f === "payment_id" ? (t.value ? +t.value : null) : t.value;
    change(() => api(`/api/budget/lines/${tr.dataset.line}`, { method: "PATCH", json: { [t.dataset.f]: v } }));
  });
  body.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.classList?.contains("cell")) e.target.blur(); });
  body.addEventListener("click", e => {
    const t = e.target.closest?.("button");
    if (!t) return;
    if (t.dataset.add) return change(() => api("/api/budget/lines", { json: { entity_id: eid, month, currency: t.dataset.add } }),
      r => $(`tr[data-line="${r.result}"] [data-f="description"]`)?.focus());
    if (t.dataset.addPayment) return change(() => api("/api/budget/lines", { json: { entity_id: eid, month, payment_id: +t.dataset.addPayment } }));
    if (t.dataset.del) {
      const x = d.lines.find(l => l.id === +t.dataset.del);
      return remove([+t.dataset.del], `Delete ${x?.description ? `\u201c${x.description}\u201d` : "this line"} from the budget?`, "The payment itself is not changed.");
    }
    if (t.id === "bud-delsel") return remove([...sel], `Delete ${sel.size} selected line${sel.size === 1 ? "" : "s"} from the budget?`, "The payments themselves are not changed.");
  });
  draw();
}

// One table per currency of what is still to pay, then the payments already out of the balance, folded away.
function budgetTables(d) {
  const num = (n, cur) => money(n, cur).replace(/^\S+ /, "");
  const byCur = {};
  for (const p of d.to_pay) (byCur[p.currency] ||= []).push(p);
  // due is what the row is budgeted at (an estimate the bank lines linked so far fall short of until the amount is
  // confirmed; what the lines add up to when a note accepts the difference), so due less to_pay was paid by the date.
  const note = p => {
    const full = p.due;
    if (full != null && full - p.to_pay > 0.005) return p.estimate != null
      ? `<div class="note">${money(full - p.to_pay, p.currency)} of the ${num(full, p.currency)} estimated was paid by ${shortDate(d.as_at)}; the rest is budgeted until you confirm the amount on the ${esc(d.entity.code)} page</div>`
      : `<div class="note">${money(full - p.to_pay, p.currency)} of ${num(full, p.currency)} paid by ${shortDate(d.as_at)}; the rest is budgeted</div>`;
    return p.paid_date > d.as_at ? `<div class="note">Paid ${shortDate(p.paid_date)}, after the balance date</div>` : "";
  };
  const tables = Object.entries(byCur).map(([cur, list]) => `<table><thead><tr><th>No.</th><th>Description</th><th class="num">${cur === "MYR" ? "RM" : esc(cur)}</th><th>Payment on</th></tr></thead><tbody>
      ${list.map((p, i) => `<tr><td>${i + 1}</td><td>${esc(p.description)}${p.amount_is_estimate || p.estimate != null ? " (EST)" : ""}${note(p)}${p.bank_details ? `<div class="note mono">${esc(p.bank_details)}</div>` : ""}</td><td class="num">${num(p.to_pay, cur)}</td><td>${fmtDate(p.due_date)}</td></tr>`).join("")}
      <tr><td></td><td><b>TOTAL</b></td><td class="num"><b>${num(d.totals[cur], cur)}</b></td><td></td></tr></tbody></table>`).join("");
  const paidTotals = {};
  for (const p of d.paid) paidTotals[p.currency] = (paidTotals[p.currency] || 0) + (p.amount || 0);
  const paid = d.paid.length ? `<details class="noprint"><summary><h3 style="display:inline">Already paid (in the balance)</h3>
      <span class="muted">· ${d.paid.length} paid on or before ${shortDate(d.as_at)} · ${Object.entries(paidTotals).map(([cur, n]) => money(n, cur)).join(" · ")}</span></summary>
      <div class="tbl-wrap"><table><thead><tr><th>Description</th><th class="num">Amount</th><th>Paid on</th></tr></thead><tbody>
      ${d.paid.map(p => `<tr><td>${esc(p.description)}</td><td class="num">${money(p.amount, p.currency)}</td><td style="white-space:nowrap">${fmtDate(p.paid_date)}</td></tr>`).join("")}
      </tbody></table></div></details>` : "";
  return `<div class="tbl-wrap">${tables || `<div class="empty">${d.paid.length ? `Nothing left to pay after ${fmtDate(d.as_at)}.` : "No payments planned."}</div>`}</div>${paid}`;
}

