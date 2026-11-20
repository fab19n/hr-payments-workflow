"use strict";
/* ---------------- Payments › Payments register (slice 2) ----------------
   The company month page of before slice 2 is two pages now: this one, the month's payments (view key entity, address
   #/<CODE>/<YYYY-MM>/payments/register), and the Monthly checklist (pages/checklist.js). Built to design/canvas/PaymentsRegister.dc.html
   (DarkCompany.dc.html for dark): the figures that filter, the tabs (All, Not paid, Needs attention, Not in SQL for a company Kept in
   SQL Account, Complete; the tab is in the address, the search is not), the payments grouped by due date with money out and money in
   added up apart, 25 at a time, the bulk bar, Excel, and a filed month read only (reopened on the Monthly checklist). A link to the
   company's to-dos on the Overview stands where the company's Next up card was (core/next.js todoLinks). */

// The head both pages share: the company and its kind, the month's state, the title, the links under it and the buttons beside it.
function monthState(d) {
  if (d.closed_at) return ["ok", "Filed"];
  if (d.before_first) return ["grey", "Before tracking"];
  if (!d.set_up) return ["grey", "Not set up"];
  const cur = currentCycle();
  return ["", d.month === cur ? "Current" : d.month < cur ? "Still open" : "Set up"];
}
function pageHead(d, { glyph, title, links = "", actions = "" }) {
  const e = d.entity, [tone, word] = monthState(d);
  return `<div class="pg-head"><div class="pg-id"><span class="pg-plate" aria-hidden="true">${icon(glyph)}</span><div class="pg-words">
      <div class="pg-eyebrow"><span class="pg-code">${esc(e.code)}</span><span class="muted">${esc(e.name)}</span>
        <span class="kind-chip${e.uses_sql ? " sql" : ""}">${icon(e.uses_sql ? "database" : "books")}${esc(keptLabel(e))}</span>
        <span class="pill${tone ? " " + tone : ""} state-pill"><span class="dot" aria-hidden="true"></span>${esc(word)}</span></div>
      <h1 id="pg-h1" tabindex="-1">${esc(title)} <span class="pg-month">· ${esc(d.label)}</span></h1>
      <div class="pg-links noprint">${links}</div></div></div>
    ${actions ? `<div class="row noprint pg-actions">${actions}</div>` : ""}</div>`;
}
const pageAddr = (view, d, params) => esc(addrOf({ view, entity: d.entity.id, month: d.month, params: params || {} }) || "#/");

// The tabs: [key, label]. Not in SQL only for a company Kept in SQL Account. A payment is Not paid (no paid date), Complete, or
// else Needs attention (paid with a document missing, or part paid); Not in SQL is the server's word (paid, no SQL voucher linked).
const REG_TABS = [["all", "All"], ["unpaid", "Not paid"], ["attention", "Needs attention"], ["nosql", "Not in SQL"], ["complete", "Complete"]];
const REG_WORD = { all: "payments", unpaid: "not paid", attention: "needing attention", nosql: "not in SQL", complete: "complete" };
const regTabs = d => REG_TABS.filter(([k]) => k !== "nosql" || !!d.entity.uses_sql);
const regKind = p => p.status === "planned" ? "unpaid" : p.status === "complete" ? "complete" : "attention";
const regIn = (p, k) => k === "all" || (k === "nosql" ? !!p.not_in_sql : regKind(p) === k);
const regTab = d => { const t = state.addr?.params?.tab; return regTabs(d).some(([k]) => k === t) ? t : "all"; };
const REG_STEP = 25;
// What the page keeps while it is on one company and month: the search (never in the address), how many rows show, the payments
// picked for the bulk bar, the sort and the bulk bar's date. A page change (applyPlace fresh) or another month starts it again.
function regState() {
  const key = `${state.entity}:${state.month}`;
  if (!state.reg || state.reg.key !== key) state.reg = { key, q: "", shown: REG_STEP, picked: [], sort: null, date: "", err: "" };
  return state.reg;
}
// Search: the name, the type, the amount, the SQL voucher and bank references and the notes.
const regText = p => [p.description, state.meta.categories[p.category] || p.category, LT.amount(p.amount), p.sql_ref, p.bank_ref, p.einvoice_ref, p.notes,
  ...(p.sql_entries || []).map(x => x.doc_no)].join(" ");
const regFound = d => { const q = regState().q.trim(); return q ? d.payments.filter(p => LT.match(regText(p), q)) : d.payments; };
const REG_RANK = p => p.status === "planned" ? (p.flag?.tone === "bad" ? 0 : 1) : p.status === "complete" ? 3 : 2;
function regRows(d, tab) {
  const R = regState(), rows = regFound(d).filter(p => regIn(p, tab));
  if (!R.sort) return rows.slice().sort((a, b) => a.due_date < b.due_date ? -1 : a.due_date > b.due_date ? 1 : 0);
  const { k, dir } = R.sort, cur = p => p.currency === "MYR" ? "" : p.currency;
  const val = p => k === "amt" ? (p.amount == null ? -Infinity : p.amount) : k === "paid" ? (p.paid_date || "") : REG_RANK(p);
  return rows.slice().sort((a, b) => {
    if (k === "amt" && cur(a) !== cur(b)) return cur(a) < cur(b) ? -1 : 1;   // amounts sort within each currency, ringgit first
    const x = val(a), y = val(b);
    return (x < y ? -1 : x > y ? 1 : 0) * dir;
  });
}

const regNote = (d, tab) => ({
  all: "Grouped by due date. Money out and money in are added up apart, each currency on its own.",
  unpaid: `Not paid: no paid date yet. The status says why, from the bank statement${d.entity.uses_sql ? ", SQL" : ""} and the legal deadline.`,
  attention: "Needs attention: paid, but a required document is missing, or part of the amount isn't on the bank statement.",
  nosql: "Not in SQL: paid, but no SQL voucher is linked yet.",
  complete: `Complete: paid, and every required document is uploaded or shown by ${d.entity.uses_sql ? "SQL or " : ""}the bank line.` }[tab]);
function regEmpty(d, tab, q, elsewhere) {
  if (q) return { glyph: "search", tone: "mute", title: `No payments match “${q}”`, clear: true,
    body: `Search looks at the name, type, amount and voucher no.${elsewhere ? ` ${elsewhere} payment${elsewhere > 1 ? "s" : ""} match${elsewhere > 1 ? "" : "es"} in other tabs.` : ""}` };
  const MN = monthName(d.month).split(" ")[0];
  return { all: { glyph: "payment", tone: "brand", title: "No payments this month yet", body: "Add one by hand, or set up recurring payments so each month fills itself." },
    unpaid: { glyph: "check", tone: "ok", title: "Every payment is paid", body: `Nothing in ${MN} is waiting to go out or come in.` },
    attention: { glyph: "check", tone: "ok", title: "Nothing needs attention", body: "Every paid payment has its documents, and no amount is short on the bank statement." },
    nosql: { glyph: "check", tone: "ok", title: "Every paid payment is in SQL", body: "Each paid payment has its SQL voucher linked." },
    complete: { glyph: "clock", tone: "mute", title: "No payment is complete yet", body: "A payment is complete once it is paid and every required document is there." } }[tab];
}
const listEmpty = x => `<div class="state compact list-empty">${stPlate(x.glyph, x.tone)}<b>${esc(x.title)}</b>${x.body ? `<p>${esc(x.body)}</p>` : ""}${x.clear ? `<div class="state-actions"><button type="button" class="ghost" data-reg-clear="1">Clear search</button></div>` : ""}</div>`;

// The tabs as role=tab buttons (roving tabindex; arrow keys in core/listeners.js), each with its count under the search.
function tabButtons(list, cur, attr, idp, panel, counts) {
  return list.map(([k, label]) => `<button type="button" role="tab" class="segtab" id="${idp}-${k}" ${attr}="${k}" aria-selected="${k === cur}" aria-controls="${panel}" tabindex="${k === cur ? 0 : -1}">${esc(label)} <span class="tab-n">${counts[k]}</span></button>`).join("");
}
function regTabsHtml(d) {
  const found = regFound(d), counts = {};
  for (const [k] of regTabs(d)) counts[k] = found.filter(p => regIn(p, k)).length;
  return tabButtons(regTabs(d), regTab(d), "data-reg-tab", "reg-tab", "regPanel", counts);
}
// The figures over the list: each one is a button that picks its tab. Payments out and money in are counted apart.
function regKpis(d) {
  const tab = regTab(d), out = d.payments.filter(p => p.direction !== "in"), inn = d.payments.filter(p => p.direction === "in");
  const n = (list, k) => list.filter(p => regIn(p, k)).length;
  const tile = (k, glyph, tone, value, label, hint) => `<button type="button" class="kpi ${tone}" data-reg-tab="${k}" aria-pressed="${tab === k}">${icon(glyph)}<span class="kpi-t"><b>${value}</b><span>${label}</span><span class="kpi-hint">${hint}</span></span></button>`;
  return tile("complete", "document", "ok", `${n(out, "complete")} / ${out.length}`, "Payments out fully documented", "Show complete")
    + tile("unpaid", "clock", "warn", n(out, "unpaid"), "Payments out not paid yet", "Show not paid")
    + (d.entity.uses_sql ? tile("nosql", "database", "warn", n(d.payments, "nosql"), "Paid, not in SQL", "Show not in SQL")
      : tile("attention", "alert", "warn", n(out, "attention"), "Payments out needing attention", "Show needs attention"))
    + (inn.length ? `<div class="kpi plain ok">${icon("coins")}<span class="kpi-t"><b>${n(inn, "complete")} / ${inn.length}</b><span>Money in fully documented</span>
        <span class="kpi-hint muted">${n(inn, "unpaid")} not received yet · counted apart from payments out</span></span></div>` : "");
}

// A salary row says what the month's latest payroll workbook check found, with a link to HR › Payroll › Workbook check.
function payrollLink(d, p) {
  const c = d.payroll_check;
  if (!c || p.category !== "salary") return "";
  const href = pageAddr("payroll", d), fix = +c.to_fix || 0, chk = +c.to_check || 0;
  const text = fix ? `The payroll check found ${fix} thing${fix > 1 ? "s" : ""} to fix` : `Payroll check: nothing to fix${chk ? `, ${chk} to check` : ""} (${shortDate(c.checked_at)})`;
  return `<div><a class="pc-link ${fix ? "bad" : "ok"}" href="${href}">${icon("payroll")}${esc(text)}</a></div>`;
}
function regRow(d, p, canPick, picked) {
  const late = p.status !== "planned" && p.flag ? `<div class="note late" title="${esc(p.flag.hint || "")}">${esc(p.flag.text)}</div>` : "";
  // A voucher number shown in its chip (✓ PV2601-020) needs no SQL chip beside it.
  const sqlShown = state.meta.sql_only.some(dt => p.required.includes(dt) && p.evidence[dt] && !p.documents.some(x => x.doc_type === dt));
  const docs = p.required.map(dt => docChip(p, dt)).join(" ") +
    (d.entity.uses_sql && p.paid_date && (p.not_in_sql || !sqlShown) ? ` <span class="chip ${p.not_in_sql ? "need" : "have"}" title="${esc(p.sql_ref || "Not recorded in SQL yet")}">${p.not_in_sql ? "·" : "✓"} SQL</span>` : "");
  const est = p.amount_is_estimate ? ` <span class="pill grey" title="${d.entity.uses_sql ? "Planned figure. The SQL voucher or bank line replaces it." : "Planned figure. The bank line replaces it."}">estimate</span>` : "";
  return `<tr class="click${picked ? " picked" : ""}" id="pay-${p.id}" data-payment="${p.id}">
    ${canPick ? `<td class="reg-pick"><input type="checkbox" data-reg-pick="${p.id}" ${picked ? "checked " : ""}aria-label="Select ${esc(p.description)}"></td>` : ""}
    <td><button type="button" class="pname" data-payment="${p.id}" aria-haspopup="dialog">${esc(p.description)}</button>${est}${p.notes ? `<div class="note">${esc(p.notes)}</div>` : ""}${payrollLink(d, p)}</td>
    <td class="muted">${esc(state.meta.categories[p.category] || p.category)}</td>
    <td class="nowrap">${p.paid_date ? shortDate(p.paid_date) : ""}</td>
    <td class="num">${signed(p.amount, p.currency, p.direction)}${estimateShort(p) ? `<div class="note">Estimated ${money(p.planned_amount, p.currency)}</div>` : ""}</td>
    <td>${docs}</td><td>${statusPill(p)}${late}</td></tr>`;
}
function regSortTh(k, label, cls) {
  const s = regState().sort, on = s && s.k === k;
  return `<th${cls ? ` class="${cls}"` : ""} aria-sort="${on ? (s.dir > 0 ? "ascending" : "descending") : "none"}"><button type="button" class="sorth" data-reg-sort="${k}"${k === "amt" ? ` aria-label="Sort by amount, grouped by currency"` : ""}>${label}${icon(on ? (s.dir > 0 ? "arrowUp" : "arrowDown") : "sort")}</button></th>`;
}
// The list: the tab, the search, then due-date groups (their totals count every payment of the group in this tab, not only those
// showing), 25 at a time; a sort gives one list.
function regPanelHtml(d) {
  const R = regState(), tab = regTab(d), ro = !!d.closed_at, canPick = !ro, q = R.q.trim();
  const rows = regRows(d, tab), shown = rows.slice(0, R.shown), picked = new Set(R.picked);
  if (!rows.length) return listEmpty(regEmpty(d, tab, q, q && tab !== "all" ? regFound(d).length : 0));
  const span = canPick ? 4 : 3;
  let body = "";
  if (R.sort) body = shown.map(p => regRow(d, p, canPick, picked.has(p.id))).join("");
  else {
    const groups = {};
    for (const p of rows) (groups[p.due_date] ||= []).push(p);
    const on = new Set(shown.map(p => p.id));
    body = Object.keys(groups).sort().filter(dd => groups[dd].some(p => on.has(p.id))).map(dd =>
      `<tr class="group"><td colspan="${span}">Due ${fmtDate(dd)}</td><td class="num">${groupTotals(groups[dd])}</td><td colspan="2"></td></tr>`
      + groups[dd].filter(p => on.has(p.id)).map(p => regRow(d, p, canPick, picked.has(p.id))).join("")).join("");
  }
  const vis = shown.map(p => p.id), all = vis.length > 0 && vis.every(id => picked.has(id));
  const head = `<tr>${canPick ? `<th class="reg-pick"><input type="checkbox" data-reg-pick-all="1" ${all ? "checked " : ""}aria-label="${all ? "Clear the selection" : `Select all ${vis.length} payments shown`}"></th>` : ""}
    <th>Payment</th><th>Type</th>${regSortTh("paid", "Paid / received")}${regSortTh("amt", "Amount", "num")}<th>Documents</th>${regSortTh("status", "Status")}</tr>`;
  const many = rows.length > REG_STEP ? manyRows({ shown: shown.length, total: rows.length, step: REG_STEP, what: tab === "all" ? "payments" : REG_WORD[tab], attr: "data-reg-more" })
    .replace("</div>", `<span class="note">Excel holds every row.</span></div>`) : "";
  return `<div class="tbl-wrap"><table class="reg-tbl" aria-label="Payments for ${esc(d.label)}, ${REG_WORD[tab]}"><thead>${head}</thead><tbody>${body}</tbody></table></div>${many}${canPick ? regBulkHtml(d) : ""}`;
}
// The bulk bar, for a batch paid together (the statutory payments, say): one paid date, or one bank slip, for every payment picked.
function regBulkHtml(d) {
  const R = regState(), ids = R.picked.filter(id => d.payments.some(p => p.id === id));
  if (!ids.length) return `<div id="regBulk"></div>`;
  return `<div id="regBulk" class="bulk-bar" role="region" aria-label="Selected payments"><b>${ids.length} selected</b>
    <label class="bulk-date">Paid date <input id="regBulkDate" type="date" value="${esc(R.date)}"${R.err ? ` aria-invalid="true" aria-describedby="regBulkErr"` : ""}></label>
    <button type="button" class="btn small" data-reg-bulk="date">Set paid date</button>
    <button type="button" class="ghost small" data-reg-bulk="upload">${icon("upload")}Upload one bank slip to all</button>
    <button type="button" class="ghost small bulk-clear" data-reg-bulk="clear">Clear selection</button>
    ${R.err ? `<p id="regBulkErr" class="bulk-err">${icon("alert")}${esc(R.err)}</p>` : ""}</div>`;
}

async function viewEntity(main) {
  const [d, next] = await Promise.all([api(`/api/month?entity=${state.entity}&month=${state.month}`), loadNext(state.entity)]);
  state.data = d;
  // A tab this company doesn't have (Not in SQL on a company kept here) is dropped, so the address written after the draw is clean.
  if (state.addr?.params?.tab && regTab(d) !== state.addr.params.tab) { const { tab: _, ...rest } = state.addr.params; state.addr.params = rest; }
  const R = regState(), e = d.entity, ro = !!d.closed_at, tab = regTab(d);
  if (state.mark) R.shown = Math.max(R.shown, d.payments.length);   // a link marks payments: every row shows, so none it names is left on a later page
  const counted = d.tasks.filter(t => !t.waiting), doneT = counted.filter(t => t.done).length;
  const links = `<div id="todoBox" class="pg-todo">${todoLinks(next)}</div><a class="pg-link" href="${pageAddr("checklist", d)}">${icon("checklist")}${counted.length ? `Monthly checklist: ${doneT} of ${counted.length} done` : "Monthly checklist"}</a>`;
  const actions = (d.set_up || d.before_first || d.payments.length ? `<a class="ghost" id="regExcel" href="/api/export/month.xlsx?entity_id=${e.id}&month=${d.month}" download>${icon("sheet")}Excel</a>` : "")
    + (ro ? "" : `<button class="btn" id="addPayment">${icon("plus")}Add a payment</button>`);
  const head = pageHead(d, { glyph: "payment", title: "Payments register", links, actions });
  const filed = ro ? `<div class="banner ok filed" role="status">${icon("verified")}<div><b>${esc(d.label)} was filed on ${shortDate(d.closed_at)}</b>
      <span>This month is marked as filed, so nothing in it counts as to do on the Overview. Payments and their documents are read-only until the month is reopened on the Monthly checklist.</span></div>
      <a class="ghost small noprint" href="${pageAddr("checklist", d)}">Reopen on the Monthly checklist</a></div>` : "";
  const setUp = d.set_up ? "" : notSetUp(e, d.month, d.payments.length);
  if (!d.set_up && !d.payments.length) { main.innerHTML = head + setUp; return; }
  const q = R.q;
  main.innerHTML = `${head}${filed}${setUp}
    <div class="kpis noprint" role="group" aria-label="Figures for this month. Each one filters the payments" id="regKpis">${regKpis(d)}</div>
    <section class="card reg-card" aria-labelledby="reg-h">
      <div class="reg-top"><div class="reg-title">${icon("payment")}<h2 id="reg-h">Payments</h2><span class="muted">· ${d.payments.length}</span><span class="note">Click a payment to open it.</span></div>
        <div class="reg-tools noprint"><div role="tablist" class="segtabs" id="regTabs" aria-label="Filter payments">${regTabsHtml(d)}</div>
          <div class="search-box">${icon("search")}<label class="sr-only" for="regQ">Search payments by name, type, amount or voucher no.</label>
            <input id="regQ" type="search" value="${esc(q)}" placeholder="Search payments" autocomplete="off" aria-describedby="regQSay"></div>
          <span id="regQSay" class="sr-only" role="status"></span></div></div>
      <p class="reg-note" id="regNote">${esc(regNote(d, tab))}</p>
      <div id="regPanel" role="tabpanel" tabindex="0" aria-labelledby="reg-tab-${tab}">${regPanelHtml(d)}</div>
    </section>`;
  // What was typed in the open payment and not saved yet stays after the refresh (an upload, a save).
  if (state.openPayment) openPayment(state.openPayment, unsavedEdits());
  // Opened from Before you print, Next up or a count to fix some payments: they are brought into view and marked for a moment.
  const { mark } = state;
  state.mark = null;
  flash(mark?.pay ? d.payments.filter(mark.pay).map(p => $(`#pay-${p.id}`)) : []);
}

// Draws the tabs, the figures, the note and the list again (a tab, the search, a sort, Show more, a pick), not the whole page, so the
// search box keeps the focus.
function regPaint() {
  const d = state.data;
  if (!d || state.view !== "entity" || !d.payments) return;
  const set = (id, html) => { const el = $("#" + id); if (el) el.innerHTML = html; };
  const tab = regTab(d), R = regState();
  set("regTabs", regTabsHtml(d)); set("regKpis", regKpis(d)); set("regPanel", regPanelHtml(d));
  const note = $("#regNote"); if (note) note.textContent = regNote(d, tab);
  const panel = $("#regPanel"); if (panel?.setAttribute) panel.setAttribute("aria-labelledby", `reg-tab-${tab}`);
  const n = regRows(d, tab).length, say = $("#regQSay");
  if (say) say.textContent = R.q.trim() ? `${n} payment${n === 1 ? "" : "s"} match${n === 1 ? "es" : ""}` : "";
}
// A tab (or a figure): written in the address in place of the one before, the marks a link brought are used up.
function regPick(k, focus) {
  const d = state.data;
  if (!d || state.view !== "entity") return;
  const p = { ...(state.addr.params || {}) };
  delete p.mark; delete p.pay;
  if (k === "all") delete p.tab; else p.tab = k;
  state.addr.params = p;
  const R = regState();
  R.shown = REG_STEP; R.picked = []; R.err = "";   // the bulk bar only ever acts on payments listed: a new tab starts a new selection
  syncAddr(); regPaint();
  if (focus) $(`#reg-tab-${regTab(d)}`)?.focus?.();
}
function regSearch(value) {
  const R = regState(), q = String(value ?? "");
  if (q !== R.q) { R.picked = []; R.err = ""; }   // as for a tab: a new search starts a new selection
  R.q = q; R.shown = REG_STEP; regPaint();
}
function regSortClick(k) {
  const R = regState(), s = R.sort, first = k === "amt" ? -1 : 1;
  R.sort = !s || s.k !== k ? { k, dir: first } : s.dir === first ? { k, dir: -first } : null;
  regPaint();
  $(`[data-reg-sort="${k}"]`)?.focus?.();
}
function regMore() {
  const d = state.data, R = regState(), rows = regRows(d, regTab(d)), first = rows[R.shown];
  R.shown += REG_STEP; regPaint();
  if (first) $(`#pay-${first.id} .pname`)?.focus?.();   // the first new row, so Tab goes on from where the list grew
}
function regPickOne(id, on) {
  const R = regState(), set = new Set(R.picked);
  if (on) set.add(id); else set.delete(id);
  R.picked = [...set]; R.err = ""; regPaint();
  $(`[data-reg-pick="${id}"]`)?.focus?.();
}
function regPickAll(on) {
  const d = state.data, R = regState(), vis = regRows(d, regTab(d)).slice(0, R.shown).map(p => p.id);
  R.picked = on ? vis : []; R.err = ""; regPaint();
  $("[data-reg-pick-all]")?.focus?.();
}
// The bulk bar's buttons. Set paid date saves the date on each payment picked that has none yet: one paid already (by hand, or from
// its bank line or SQL voucher) keeps its date, and the toast says how many were left as they were. Upload one bank slip files the
// same file on each (as its bank slip when it asks for one, else as Other, or the first document type in use when Other is stopped).
// A payment the server refuses stays picked, and the message names it; the page is drawn again either way.
async function regBulk(what) {
  const d = state.data, R = regState(), ids = R.picked.filter(id => d.payments.some(p => p.id === id));
  if (what === "clear") { R.picked = []; R.err = ""; regPaint(); return $("#regQ")?.focus?.(); }
  if (!ids.length || d.closed_at) return;
  const pays = ids.map(id => d.payments.find(p => p.id === id)), plural = n => `${n} payment${n === 1 ? "" : "s"}`;
  if (what === "date") {
    const day = $("#regBulkDate")?.value || "";
    R.date = day;
    if (!day) { R.err = "Choose the paid date first."; regPaint(); return $("#regBulkDate")?.focus?.(); }
    const todo = pays.filter(p => !p.paid_date), skipped = pays.length - todo.length, refused = [];
    for (const p of todo) {
      try { await api(`/api/payments/${p.id}`, { method: "PATCH", json: { paid_date: day } }); } catch (e) { refused.push({ p, why: e.message }); }
    }
    R.picked = refused.map(x => x.p.id); R.err = "";
    const kept = skipped ? `; ${plural(skipped)} already paid kept ${skipped === 1 ? "its" : "their"} own date` : "";
    await render();
    if (refused.length) toast(`Paid date ${shortDate(day)} set on ${todo.length - refused.length} of ${todo.length}${kept}; not set on: ${refused.map(x => `${x.p.description} (${x.why})`).join("; ")}`, true);
    else toast(todo.length ? `Paid date ${shortDate(day)} set on ${plural(todo.length)}${kept}` : `Nothing changed: the ${plural(skipped)} picked ${skipped === 1 ? "is" : "are"} paid already and keep${skipped === 1 ? "s its" : " their"} own date`);
    return;
  }
  if (what === "upload") {
    const [file] = await pickFile(false);
    if (!file) return;
    const usable = Object.keys(state.meta.doc_types).filter(t => docActive(t) && !["statement", "recon", "sqlexport"].includes(t) && !docFromSql(t));
    const fallback = usable.includes("other") ? "other" : usable[0] || "other";
    const refused = [];
    for (const p of pays) {
      const fd = new FormData();
      fd.append("file", file); fd.append("payment_id", p.id); fd.append("doc_type", p.required.includes("bank") && docActive("bank") ? "bank" : fallback);
      try { await api("/api/upload", { form: fd }); } catch (e) { refused.push({ p, why: e.message }); }
    }
    R.picked = refused.map(x => x.p.id);
    const n = pays.length - refused.length;
    await render();
    if (refused.length) toast(`${file.name} added to ${n} of ${pays.length}; not added to: ${refused.map(x => `${x.p.description} (${x.why})`).join("; ")}`, true);
    else toast(`Added ${file.name} to ${plural(n)}`);
  }
}

/* ---------------- Drawers and the payment dialog ---------------- */
// The payment dialog's inputs, by the field each one saves.
const PAY_INPUTS = { amount: "pf-amount", paid_date: "pf-paid", bank_ref: "pf-bank", sql_ref: "pf-sql", einvoice_ref: "pf-einv",
  notes: "pf-notes", difference_note: "pf-diff", amount_confirmed: "pf-confirm", account_id: "pf-acct" };

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
  // A new payment not added yet (NewPayment.dc.html): nothing of it is kept.
  if (state.np && !state.openPayment) leavePending ||= ask("What you typed is not kept.", { title: "Discard this payment?", yes: "Discard",
    no: "Keep editing", danger: true, tone: "warn", glyph: "edit" }).finally(() => { leavePending = null; });
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
  hideDrawer(); state.openPayment = null; state.pay = null; state.np = null; state.drawerDirty = null; state.drawerAt = null; state.why = null;
  Object.assign(state.setup, { drawer: null, chkOpen: null, remOpen: null, paste: null });
  if (state.addr.id || state.setup.id != null) { state.addr.id = null; state.setup.id = null; syncAddr(); }  // a closed drawer is not in the address
  return true;
}

// The payment dialog (openPayment) and Add a payment are drawn by pages/payment.js.
function payFormValues() {
  const acct = $("#pf-acct");
  return { amount: $("#pf-amount").value === "" ? null : +$("#pf-amount").value, paid_date: $("#pf-paid").value,
    bank_ref: $("#pf-bank").value.trim(), sql_ref: $("#pf-sql").value.trim(), einvoice_ref: $("#pf-einv").value.trim(), notes: $("#pf-notes").value.trim(),
    difference_note: $("#pf-diff")?.value.trim(), amount_confirmed: !!$("#pf-confirm")?.checked,
    ...(acct && acct.tagName === "SELECT" ? { account_id: acct.value === "" ? null : +acct.value } : {}) };
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

