"use strict";
// Single-page UI. Talks only to this PC's own server (/api/...).

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const money = (n, cur = "MYR") => n == null ? "—" : (cur === "MYR" ? "RM " : cur + " ") + Number(n).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtDate = iso => { if (!iso) return "—"; const [y, m, d] = iso.slice(0, 10).split("-"); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const shortDate = iso => { if (!iso) return "—"; const [, m, d] = iso.slice(0, 10).split("-"); return `${+d} ${MONTHS[+m - 1]}`; };
const monthName = k => { const [y, m] = k.split("-"); return ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][+m - 1] + " " + y; };
const shiftMonth = (k, n) => { let [y, m] = k.split("-").map(Number); m += n; y += Math.floor((m - 1) / 12); m = ((m - 1) % 12 + 12) % 12 + 1; return `${y}-${String(m).padStart(2, "0")}`; };

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "X-HRP": "1" } };
  if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); init.method = opts.method || "POST"; }
  if (opts.form) { init.body = opts.form; init.method = "POST"; }
  const r = await fetch(path, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Something went wrong (${r.status}).`);
  return data;
}

function toast(msg, bad) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast" + (bad ? " bad" : ""); t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => t.hidden = true, bad ? 6000 : 2500);
}
// Money received shows with a green +, so it can't be read as a payment.
const signed = (n, cur, dir) => n == null || dir !== "in" ? money(n, cur) : `<span class="recv">+${money(n, cur)}</span>`;
// A due date's totals: money out, then money received, each currency apart; never added together.
function groupTotals(list) {
  const sums = new Map();
  const ordered = [...list].sort((a, b) => (a.direction === "in") - (b.direction === "in") || (a.currency !== "MYR") - (b.currency !== "MYR"));
  for (const p of ordered) { const k = `${p.direction === "in" ? "in" : "out"} ${p.currency}`; sums.set(k, (sums.get(k) || 0) + (p.amount || 0)); }
  return [...sums].map(([k, n]) => { const [dir, cur] = k.split(" "); return signed(n, cur, dir); }).join("<br>");
}
// A document type's short name, e.g. "Official Receipt" for "Official Receipt (SQL)"
const docLabel = t => (state.meta.doc_types[t] || t).split(" (")[0];
const matchedNote = r => r.bank_lines_matched ? `; ${r.bank_lines_matched} bank lines matched` : "";
const changedInSql = x => x.linked_to ? `<div class="note">Changed in SQL? This number is already linked to ${esc(x.linked_to)} at ${money(x.linked_amount)}.</div>` : "";
// "RM 10,000.00 of 20,000.00": what the linked bank lines add up to, against the payment's amount
const foundOf = p => `${money(p.bank_total, p.currency)} of ${money(p.amount, p.currency).replace(/^\S+ /, "")}`;
// An estimate that took the total of the bank lines linked so far, short of the figure estimated (a transfer not linked yet?)
const estimateShort = p => p.planned_is_estimate && p.planned_amount != null && !p.sql_entries.length && p.bank_total != null
  && p.planned_amount - p.bank_total > 0.01;
const lowerFirst = s => s.charAt(0).toLowerCase() + s.slice(1);
// What a payment's or checklist item's dates mean today, as the server words it (Due today, Waiting for SQL record...)
const flagPill = f => f ? `<span class="pill ${f.tone}"${f.hint ? ` title="${esc(f.hint)}"` : ""}>${esc(f.text)}</span>` : "";
// A required document SQL or the bank statement already shows, e.g. "PV2609-020 (print from SQL)": no upload needed.
const evidenceChip = ev => `<span class="chip have ev" title="${esc(ev.text)}. No upload needed; you can still add a copy.">✓ ${esc(ev.text)}</span>`;
// A required document's chip on a payment row: · missing (with why what SQL has doesn't count, e.g. an e-Invoice taken
// back), ✓ uploaded, or ✓ what already shows it.
function docChip(p, dt) {
  const why = p.not_counted[dt];
  if (p.missing.includes(dt)) return `<span class="chip need"${why ? ` title="${esc(why.hint)}"` : ""}>· ${esc(dt.toUpperCase())}</span>`;
  return p.evidence[dt] && !p.documents.some(x => x.doc_type === dt) ? evidenceChip(p.evidence[dt]) : `<span class="chip have">✓ ${esc(dt.toUpperCase())}</span>`;
}

// Payroll cycle: until the 10th you're still closing last month's cycle. Of today, or of the day given (a date).
function currentCycle(t = new Date()) { const d = new Date(t.getFullYear(), t.getMonth() - (t.getDate() <= 10 ? 1 : 0), 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }

// Today is worked out when it is wanted, never kept: the day the page was last drawn is state.day.
const dayKey = () => { const t = new Date(); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`; };

const state = { meta: null, view: "overview", entity: null, month: currentCycle(), day: dayKey(), data: null, openPayment: null, sqlOpen: {}, sqlPaste: {},
  nextAll: {}, bankOnly: false };
// Sidebar sections; companies are listed between Dashboard and Monthly work.
const VIEWS = [["Monthly work", [["budget", "Budget"], ["bank", "Bank statements"], ["sql", "SQL import"], ["payees", "Recurring"]]],
  ["Filing", [["audit", "Audit pack"], ["settings", "Backup & log"]]]];
const ICON = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  entity: '<path d="M4 21V5l8-3v19M12 9h8v12M8 8h.01M8 12h.01M8 16h.01M16 13h.01M16 17h.01M2 21h20"/>',
  budget: '<path d="M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12M16 14h.01"/>',
  bank: '<path d="M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M2 21h20M12 3l9 5H3z"/>',
  sql: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  payees: '<path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/>',
  audit: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 15l2 2 4-4"/>',
  settings: '<path d="M3 4h18v4H3zM5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/>',
};
const icon = v => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[v]}</svg>`;

function renderNav() {
  const btn = (v, label, on, extra = "") => `<button data-view="${v}"${extra} class="${on ? "on" : ""}">${icon(v)}<span>${label}</span></button>`;
  const items = [`<div class="group">Dashboard</div>`, btn("overview", "Overview", state.view === "overview"), `<div class="group">Companies</div>`];
  for (const e of state.meta.entities)
    items.push(btn("entity", `${esc(e.code)} <small>${esc(e.name.replace(/ (Sdn Bhd|Ltd)$/i, ""))}</small>`, state.view === "entity" && state.entity === e.id, ` data-entity="${e.id}"`));
  for (const [group, views] of VIEWS) {
    items.push(`<div class="group">${group}</div>`);
    for (const [v, l] of views) items.push(btn(v, l, state.view === v));
  }
  $("#nav").innerHTML = items.join("");
  $("#monthLabel").textContent = monthName(state.month) + " payroll";
  const crumb = $("#pageTitle");
  if (!crumb) return;
  const g = VIEWS.find(x => x[1].some(v => v[0] === state.view));
  crumb.textContent = state.view === "overview" ? "Dashboard › Overview"
    : state.view === "entity" ? `Companies › ${state.meta.entities.find(e => e.id === state.entity)?.code || ""}`
    : g ? `${g[0]} › ${g[1].find(v => v[0] === state.view)[1]}` : "";
}

function go(view, entity) {
  if (!closeDrawer()) return;
  state.view = view; state.bankOnly = false; if (entity) state.entity = +entity;
  if (!state.entity) state.entity = state.meta.entities[0].id;
  renderNav(); render();
}

async function render() {
  const main = $("#main");
  if (dayKey() !== state.day) await newDay();
  try {
    if (state.view === "overview") await viewOverview(main);
    else if (state.view === "entity") await viewEntity(main);
    else if (state.view === "budget") await viewBudget(main);
    else if (state.view === "bank") await viewBank(main);
    else if (state.view === "sql") await viewSql(main);
    else if (state.view === "payees") await viewPayees(main);
    else if (state.view === "audit") await viewAudit(main);
    else if (state.view === "settings") await viewSettings(main);
  } catch (e) { main.innerHTML = `<div class="card"><b>Couldn't load this page.</b><div class="note">${esc(e.message)}</div></div>`; }
}

function entityPicker() {
  return `<div class="row noprint">${state.meta.entities.map(e => `<button class="${e.id === state.entity ? "btn" : "ghost"} small" data-pick-entity="${e.id}">${esc(e.name)}</button>`).join("")}</div>`;
}
const ent = () => state.meta.entities.find(e => e.id === state.entity);
// A month is set up (its checklist and recurring payments added) when you ask, or for the current cycle on loading.
// One not set up can still hold payments (from an SQL voucher or a bank line), which are shown below this card.
const notSetUp = (e, month, held) => `<div class="card noprint"><h2>${esc(monthName(month))} isn't set up yet</h2>
  <div class="note">${held ? `It already holds ${held} payment${held > 1 ? "s" : ""}, shown below. ` : ""}Setting it up adds ${esc(e.code)}'s checklist and recurring payments for the month.${e.first_month && month < e.first_month
    ? ` It is before the first month tracked in this app (${esc(monthName(e.first_month))}).` : ""}</div>
  <div class="row"><button class="btn" data-open-month="${e.id}">Set up this month</button></div></div>`;

/* ---------------- Go, and Next up ---------------- */
// Go: opens where something is done, for its company and month whichever are showing: the payment's drawer, a checklist
// item on the month page, the month page with what a count stands for marked, the Bank statements page on an account
// (only the lines to explain, for filter to_explain), or another page: the Budget page as at the day a row counts (as_at)
// when it has one. The page starts at the top; what is brought into view once it is drawn (a marked item, the
// statement) goes after that.
function goTo(g) {
  if (!closeDrawer()) return;
  const tasks = g.task_ids || (g.task_id ? [g.task_id] : null);
  if (g.entity_id) state.entity = g.entity_id;
  if (g.month) state.month = g.month;
  state.view = g.view;
  state.openPayment = g.payment_id || null;
  state.asAt = g.view === "budget" ? g.as_at || null : null;
  state.mark = g.view !== "entity" ? null : g.payment_ids ? { pay: p => g.payment_ids.includes(p.id) }
    : tasks ? { task: t => tasks.includes(t.id) } : g.filter ? markFor(g.filter) : null;
  state.focusBank = g.view === "bank" ? { account: g.account_id || null } : null;
  if (g.view === "bank") state.bankOnly = g.filter === "to_explain";
  window.scrollTo?.(0, 0);
  renderNav(); return render();
}

// What a count stands for on the month page: the checklist items and payments to mark (a row of Next up names its own,
// task_ids and payment_ids). A word that is none of these is a payment's (not_on_statement, past_legal...).
const MARKS = {
  overdue_tasks: { task: t => t.flag?.code === "overdue" },
  due_today_tasks: { task: t => t.flag?.code === "due_today" },
  part_paid: { pay: p => p.status === "part_paid" },
};
const markFor = key => MARKS[key] || { pay: p => p.flag?.code === key };

// Brings the first of these into view and marks them all for a moment.
function flash(els) {
  els = els.filter(Boolean);
  if (!els.length) return;
  for (const x of els) x.classList.add("focus");
  els[0].scrollIntoView?.({ block: "center" });
  setTimeout(() => els.forEach(x => x.classList.remove("focus")), 3000);
}

// A count pill on the Overview goes to what it counts, for its company and the month on show.
function pillGo(kind, entity) {
  const g = { entity_id: entity, month: state.month };
  if (kind === "paid_missing") return goTo({ ...g, view: "audit" });
  if (kind === "unmatched_lines") return goTo({ ...g, view: "bank", filter: "to_explain" });
  if (kind === "not_in_sql") return goTo({ ...g, view: "sql" });
  return goTo({ ...g, view: "entity", filter: kind });
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dayLabel = iso => { const [y, m, d] = iso.split("-").map(Number); return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]} ${d} ${MONTHS[m - 1]}`; };
// The list is for one company (its id) or both. A list that can't be read says so, and the page still shows.
const loadNext = scope => api(`/api/next${scope ? `?entity_id=${scope}` : ""}`).catch(e => ({ error: e.message }));
const nextScope = () => state.view === "entity" ? state.entity : null;
const DUE_WORD = { overdue: "Overdue", today: "Today", soon: "Due", later: "Due" };
const DUE_TONE = { overdue: "bad", today: "warn", soon: "warn", later: "grey" };
const dueTag = r => r.due ? `<span class="pill ${DUE_TONE[r.state]}">${DUE_WORD[r.state]} ${shortDate(r.due)}</span>` : "";
// The company is named after a sentence that doesn't name it already.
const forCompany = r => r.entity && !new RegExp(`\\b${r.entity}\\b`).test(r.text) ? ` <span class="muted">· ${esc(r.entity)}</span>` : "";

function nextRow(r) {
  return `<div class="next-row"><div>${esc(r.text)}${forCompany(r)}</div><div class="next-due">${dueTag(r)}</div>
    <div class="row next-act">${r.rule === 13 ? `<button class="btn small" data-next-backup="1">Back up now</button>` : ""}
    <button class="ghost small" data-next-go="${esc(r.key)}" aria-label="Go: ${esc(r.text)}">Go</button></div></div>`;
}

// The Next up card: 7 rows (3 on a company's page) and Show all, the older months still open as one muted line. Those
// months are not read for the list, so with any open it says nothing is due in the recent ones, never All caught up.
function nextCard(res, scope) {
  if (res.error) return `<div class="card noprint"><h2>Next up</h2><div class="note">Couldn't work out what to do next: ${esc(res.error)}</div></div>`;
  state.next = new Map(res.items.map(r => [r.key, r]));
  const limit = scope ? 3 : 7, many = !scope && state.meta.entities.length > 1;
  const all = state.nextAll[scope || 0];  // Show all is kept for each list: the Overview's and each company's
  const rows = (all ? res.items : res.items.slice(0, limit)).map(nextRow).join("");
  const more = res.items.length > limit ? `<div><button class="link" data-next-all="1">${all ? "Show fewer" : `Show all ${res.items.length}`}</button></div>` : "";
  const older = res.older_open_months.map(o => `<button class="link" data-older="${o.entity_id} ${o.month}">${esc(o.label)}${many
    ? ` (${esc(state.meta.entities.find(e => e.id === o.entity_id)?.code)})` : ""}</button>`).join(", ");
  return `<div class="card noprint"><h2>Next up <span class="muted">· ${esc(dayLabel(res.today))}</span></h2>
    ${res.items.length ? `<div class="next-list">${rows}</div>${more}`
      : `<div class="banner ok"><b>${older ? "Nothing due in the recent months" : "All caught up"}</b>${res.next_due ? `<span>Next due ${shortDate(res.next_due.due)} · ${esc(res.next_due.text)}</span>` : ""}</div>`}
    ${older ? `<div class="note">Older months still open: ${older}</div>` : ""}</div>`;
}

// Reads the list again and redraws the card alone (after a backup, or when the tab comes back into view). With keepOnError,
// a list that can't be read leaves the card as it was.
async function refreshNext(keepOnError) {
  if (!["overview", "entity"].includes(state.view)) return;
  const scope = nextScope(), res = await loadNext(scope), box = $("#nextUp");
  if (box && scope === nextScope() && !(keepOnError && res.error)) box.innerHTML = nextCard(res, scope);
}

/* ---------------- Overview ---------------- */
async function viewOverview(main) {
  const asAt = state.meta.entities.map(e => [e.id, storedAsAt(e.id, state.month)]).filter(([, d]) => d).map(([id, d]) => `&as_at_${id}=${d}`).join("");
  const [ov, next] = await Promise.all([api(`/api/overview?month=${state.month}${asAt}`), loadNext(null)]);
  const cards = ov.entities.map(x => {
    const budget = (cur, n) => `<div class="stat"><b class="mono">${Math.round(n).toLocaleString("en-MY")}</b><span>budget as at ${shortDate(x.budget_as_at)} (${cur === "MYR" ? "RM" : esc(cur)})</span></div>`;
    if (!x.set_up && !x.payments && !x.tasks) return notSetUp(x.entity, ov.month);
    const pct = x.payments ? Math.round(x.complete / x.payments * 100) : 0;
    // Each count is a button to what it counts (pillGo).
    const flags = [], count = (kind, tone, text) => flags.push(`<button class="pillbtn" data-pill="${kind}" data-entity="${x.entity.id}" title="Show these"><span class="pill ${tone}">${text}</span></button>`);
    if (x.overdue_tasks) count("overdue_tasks", "bad", `${x.overdue_tasks} checklist overdue`);
    if (x.due_today_tasks) count("due_today_tasks", "warn", `${x.due_today_tasks} checklist due today`);
    for (const f of x.payment_flags) count(f.code, f.tone, `${f.n} payment${f.n > 1 ? "s" : ""} ${esc(lowerFirst(f.text))}`);
    if (x.part_paid) count("part_paid", "warn", `${x.part_paid} part paid`);
    if (x.paid_missing) count("paid_missing", "warn", `${x.paid_missing} paid, documents missing`);
    if (x.unmatched_lines) count("unmatched_lines", "warn", `${x.unmatched_lines} bank lines not explained`);
    if (x.not_in_sql) count("not_in_sql", "warn", `${x.not_in_sql} paid, not recorded in SQL`);
    // A month filed is done with: the server counts nothing in it as to do.
    if (!flags.length) flags.push(x.closed_at ? `<span class="pill ok">Filed ${shortDate(x.closed_at)}</span>` : `<span class="pill ok">Nothing overdue</span>`);
    if (x.before_first) flags.push(`<span class="pill grey">Before the first month tracked</span>`);
    if (!x.set_up) flags.push(`<span class="pill grey">Month not set up</span>`);
    return `<div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(x.entity.code)}</div><h2>${esc(x.entity.name)}</h2></div>
      <button class="btn small" data-view="entity" data-entity="${x.entity.id}">Open ${esc(x.entity.code)}</button></div>
      <div class="stats">
        <div class="stat"><b>${x.tasks_done}/${x.tasks}</b><span>checklist done</span></div>
        <div class="stat"><b>${x.complete}/${x.payments}</b><span>payments fully documented</span></div>
        <div class="stat"><b>${x.planned}</b><span>not paid yet</span></div>
        ${budget("MYR", x.budget.MYR || 0)}${Object.entries(x.budget).filter(([cur]) => cur !== "MYR").map(([cur, n]) => budget(cur, n)).join("")}
      </div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="row">${flags.join("")}</div>
    </div>`;
  }).join("");
  main.innerHTML = `
    <div id="nextUp">${nextCard(next, null)}</div>
    <div><div class="eyebrow">Payroll month</div><h1>${esc(ov.label)} cycle</h1>
    <div class="note">Covers inputs from the 15th, payday on the 26th, statutory and bills by the 6th of next month, and closing by the 10th.</div></div>
    <div class="grid2">${cards}</div>
    <div class="card"><h2>How a payment is completed</h2>
      <div class="row"><span class="pill grey">Not paid</span> → <span class="pill warn">Paid, documents missing</span> → <span class="pill ok">Complete</span></div>
      <div class="note">A payment becomes <b>Paid</b> when you enter the paid date or its bank statement line is matched. It becomes <b>Complete</b> when every required document is uploaded, or already shown by a linked SQL voucher, a validated e-Invoice or its bank statement line. Only complete payments are ready to file.</div>
      <div class="note">Past its due date and not paid yet, a payment says why: <b>Not on Oct statement</b> (or the month it fell due in) once that month's bank statement is imported without it; until then <b>Waiting for SQL record</b> while SQL isn't imported up to its due date, or else <b>Waiting for Oct statement</b>. A statutory payment not paid by the 15th of the next month shows <b>Past legal deadline</b>.</div>
      <div class="note">If the bank lines matched add up to less than the amount, it shows <b>Part paid</b> until the rest is matched, or you note why in the payment (e.g. balance paid in October).</div>
    </div>`;
}

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
        const st = p.status === "complete" ? `<span class="pill ok">Complete</span>` : p.status === "paid" ? `<span class="pill warn">Paid · ${p.missing.length} doc${p.missing.length > 1 ? "s" : ""} missing</span>` :
          p.status === "part_paid" ? `<span class="pill warn">Part paid · ${foundOf(p)}</span>` : flagPill(p.flag);
        const late = p.status !== "planned" && p.flag ? `<div class="note late" title="${esc(p.flag.hint || "")}">${esc(p.flag.text)}</div>` : "";
        // A voucher number shown in its chip (✓ PV2609-020) needs no SQL chip beside it.
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
    <div class="row spread"><div><div class="eyebrow">${esc(d.entity.code)}</div><h1>${esc(d.entity.name)} · ${esc(d.label)}</h1></div>
      <div class="row noprint">${d.set_up && !d.closed_at ? `<button class="ghost" data-close-month="1">Mark month as filed</button>` : ""}
      <button class="btn" id="addPayment">Add a payment</button></div></div>
    ${d.closed_at ? `<div class="banner ok"><b>Filed ${shortDate(d.closed_at)}</b><span>This month is marked as filed, so nothing in it counts as to do on the Overview.</span>
      <button class="ghost small noprint" data-reopen-month="1">Reopen</button></div>` : ""}
    <div id="nextUp">${nextCard(next, d.entity.id)}</div>
    <div class="grid2" style="grid-template-columns:minmax(0,1fr)">
      <div class="card"><div class="row spread"><h2>Payments</h2><span class="note">Click a payment to upload its documents.</span></div>
        <div class="tbl-wrap"><table><thead><tr><th>Payment</th><th>Type</th><th>Paid</th><th class="num">Amount</th><th>Documents</th><th>Status</th></tr></thead>
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
const mayLeave = () => !Object.keys(unsavedEdits()).length || confirm("Discard your changes?");

// False when you choose to keep changes not saved yet; force closes it anyway (the payment was removed).
function closeDrawer(force) {
  if (!force && !mayLeave()) return false;
  $("#drawer").hidden = true; state.openPayment = null;
  return true;
}

function openPayment(id, keep = {}) {
  const p = state.data.payments.find(x => x.id === id);
  if (!p) return closeDrawer(true);
  state.openPayment = id;
  const dt = state.meta.doc_types;
  const ofType = t => p.documents.filter(x => x.doc_type === t);
  const required = p.required.map(t => slotHtml(t, ofType(t), p.evidence[t], p.not_counted[t])).join("");
  // A company not kept in SQL has no SQL documents. Approval is the usual extra; where it is required already, Other,
  // so a document added without a look at the list is never filed as a voucher.
  const noSql = state.data.entity.uses_sql ? [] : [...state.meta.sql_only, "sqlexport"];
  const extraTypes = Object.keys(dt).filter(t => !p.required.includes(t) && t !== "statement" && !noSql.includes(t));
  const extraPick = extraTypes.includes("approval") ? "approval" : "other";
  const extras = [...new Set(p.documents.map(x => x.doc_type).filter(t => !p.required.includes(t)))].map(t => slotHtml(t, ofType(t))).join("");
  const lines = p.bank_lines.length ? p.bank_lines.map(l => `<div class="line-desc mono">${shortDate(l.txn_date)} · ${(l.amount > 0) === (p.direction === "out") ? "−" : ""}${money(Math.abs(l.amount), p.currency)} · ${esc(l.description.split(" | ").slice(0, 2).join(" "))}</div>`).join("") : `<div class="note">Not matched to a bank statement line yet.</div>`;
  const gap = p.bank_total == null || p.amount == null ? 0 : p.amount - p.bank_total;
  const short = gap > 0.01 ? `<div style="grid-column:1/-1"><b>Part paid: ${foundOf(p)}</b>
      <div class="note">${p.difference_note ? "The difference is noted, so this payment counts as paid." : `${money(gap, p.currency)} isn't on the bank statement yet. Match the rest on the Bank statements page, or note why below.`}</div></div>
      <label class="field" style="grid-column:1/-1"><span>Why the rest isn't on the bank statement</span><input id="pf-diff" value="${esc(p.difference_note || "")}" placeholder="e.g. balance paid in October"></label>` : "";
  const over = gap < -0.01 ? `<div class="note">The bank lines add up to ${money(p.bank_total, p.currency)}, ${money(-gap, p.currency)} more than the amount.</div>` : "";
  const est = estimateShort(p) ? `<div class="note">Estimated at ${money(p.planned_amount, p.currency)}; the bank lines linked so far add up to ${money(p.bank_total, p.currency)}. If more was sent, link the rest on the Bank statements page. If not, confirm the amount above; until then the budget counts the estimate.</div>` : "";
  const vouchers = p.sql_entries.map(x => `<div class="row spread"><span class="mono">${esc(x.doc_no)} · ${shortDate(x.doc_date)} · ${x.direction && x.direction !== p.direction ? "−" : ""}${money(x.amount, p.currency)}</span>
    <button class="ghost small" data-sql-unlink="${x.id}">Unlink</button></div>`).join("");
  $("#drawer").innerHTML = `
    <div class="row spread"><div><div class="eyebrow">${esc(state.meta.categories[p.category] || p.category)} · due ${fmtDate(p.due_date)}</div><h2>${esc(p.description)}</h2></div>
      <button class="ghost small" id="closeDrawer">Close</button></div>
    ${p.flag ? `<div class="row">${flagPill(p.flag)}${p.flag.hint ? `<span class="note">${esc(p.flag.hint)}</span>` : ""}</div>` : ""}
    ${p.bank_details || p.payee_ref ? `<div class="note">Pay to: <span class="mono">${esc(p.bank_details || "")} ${esc(p.payee_ref || "")}</span></div>` : ""}
    <form class="form" id="payForm">
      <label class="field"><span>Amount (${esc(p.currency)})</span><input id="pf-amount" type="number" step="0.01" value="${p.amount ?? ""}"></label>
      <label class="field"><span>Paid on</span><input id="pf-paid" type="date" value="${p.paid_date || ""}"></label>
      <label class="field"><span>Bank reference</span><input id="pf-bank" value="${esc(p.bank_ref || "")}"></label>
      <label class="field"><span>${state.data.entity.uses_sql ? "SQL PV / JV no." : "Record ref"}</span><input id="pf-sql" value="${esc(p.sql_ref || "")}"></label>
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
      <div class="row"><select id="extraType">${extraTypes.map(t => `<option value="${t}" ${t === extraPick ? "selected" : ""}>${esc(dt[t])}</option>`).join("")}</select>
      <button class="ghost small" id="extraUpload">Upload another document</button></div></div>
    ${state.data.entity.uses_sql ? `<div><h3>SQL Account</h3>${vouchers ? vouchers + `<div class="note">Linked by mistake? Unlink puts the voucher back under SQL entries not linked, and the amount and paid date back to what they were.</div>` : `<div class="note">No SQL voucher linked yet.</div>`}</div>` : ""}
    <div><h3>Bank statement</h3>${lines}${over}${est}</div>
    <div class="row"><button class="btn danger small" id="deletePayment">Remove this payment</button></div>`;
  $("#drawer").hidden = false;
  state.payLoaded = payFormValues();
  for (const [k, v] of Object.entries(keep)) { const el = $("#" + k); if (el) el[el.type === "checkbox" ? "checked" : "value"] = v; }
}

function payFormValues() {
  return { amount: $("#pf-amount").value === "" ? null : +$("#pf-amount").value, paid_date: $("#pf-paid").value,
    bank_ref: $("#pf-bank").value.trim(), sql_ref: $("#pf-sql").value.trim(), einvoice_ref: $("#pf-einv").value.trim(), notes: $("#pf-notes").value.trim(),
    difference_note: $("#pf-diff")?.value.trim(), amount_confirmed: !!$("#pf-confirm")?.checked };
}

// One box per document of the type, then one to add another (several transfer slips for one payment, say). With none
// uploaded, ev (what SQL or the bank statement already shows, e.g. PV2609-020) ticks the box, which can still take a file;
// without it, why says why what SQL has doesn't count (an e-Invoice cancelled by a refund note).
function slotHtml(type, docs, ev, why) {
  const label = esc(state.meta.doc_types[type]);
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
      <div class="row spread"><div><div class="eyebrow">${esc(d.entity.name)}</div><h1>Budget for ${esc(d.label)}</h1></div>
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
      <div class="row spread"><div><div class="eyebrow">${esc(d.entity.name)}</div><h1>Budget for ${esc(d.label)}</h1></div>
      <button class="ghost noprint" id="printPage">Print budget</button></div>
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
      <td class="noprint"><button class="ghost small" data-del="${x.id}" aria-label="Delete line ${i + 1}" title="Delete line">×</button></td></tr>`;
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
    $("#bud-body").innerHTML = `<div class="row noprint">
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
  const remove = (ids, text) => confirm(text) && change(() => api("/api/budget/lines/delete", { json: { ids } }));

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
      return remove([+t.dataset.del], `Delete ${x?.description ? `"${x.description}"` : "this line"} from the budget? The payment itself is not changed.`);
    }
    if (t.id === "bud-delsel") return remove([...sel], `Delete ${sel.size} selected line${sel.size === 1 ? "" : "s"} from the budget? The payments themselves are not changed.`);
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

/* ---------------- Bank statements ---------------- */
// Only lines to explain: the statements with none left are not listed, and the lines explained are left out of the rest.
const toExplain = s => s.lines.filter(l => l.status === "unmatched");
const listedStatements = sts => state.bankOnly ? sts.filter(s => toExplain(s).length) : sts;

function bankBlocks(sts) {
  const blocks = listedStatements(sts).map(s => {
    const un = toExplain(s).length;
    return `<div class="card" id="stmt-${s.id}">
      <div class="row spread"><div><div class="eyebrow">${esc(s.account_label)}</div><h2>${monthName(s.month)} statement</h2></div>
      <div class="row">${s.check_ok ? `<span class="pill ok">Balances add up</span>` : `<span class="pill bad">Closing balance differs</span>`}
      ${un ? `<span class="pill warn">${un} lines to explain</span>` : `<span class="pill ok">All lines explained</span>`}
      <a class="ghost small" href="/api/documents/${s.document_id}/file" target="_blank">View PDF</a></div></div>
      <div class="note">Opening ${money(s.opening, s.currency)} · Closing ${money(s.closing, s.currency)} · Debits ${money(s.total_debits, s.currency)} · Credits ${money(s.total_credits, s.currency)}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Explained by</th><th></th></tr></thead><tbody>
      ${(state.bankOnly ? toExplain(s) : s.lines).map(l => `<tr><td class="mono">${shortDate(l.txn_date)}</td><td class="line-desc">${esc(l.description.replaceAll(" | ", " · "))}</td>
        <td class="num ${l.amount < 0 ? "" : "muted"}">${l.amount < 0 ? "−" : "+"}${money(Math.abs(l.amount), s.currency).replace(/^\S+ /, "")}</td>
        <td>${l.payment_id ? `<span class="pill ok">${esc(l.payment_desc)}</span>` : l.status === "no_docs" ? `<span class="pill grey">No documents needed${l.note ? ": " + esc(l.note) : ""}</span>` : `<span class="pill warn">Not explained</span>`}</td>
        <td class="noprint">${l.payment_id || l.status === "no_docs" ? `<button class="ghost small" data-unlink="${l.id}">Undo</button>` : `<button class="ghost small" data-explain="${l.id}" data-account="${s.account_id}" data-month="${s.month}" data-amount="${l.amount}">Explain</button>`}</td></tr>`).join("")}
      </tbody></table></div></div>`;
  }).join("");
  return blocks || `<div class="card empty">${sts.length ? "Every line on the statements is explained." : `No statements imported for ${esc(ent().name)} yet.`}</div>`;
}

async function viewBank(main) {
  const e = ent();
  const sts = await api(`/api/statements?entity=${state.entity}`);
  state.statements = sts;
  // Opened from Before you print or Next up: that account is chosen for the import, and its statement for the month shown.
  const focus = state.focusBank; state.focusBank = null;
  const acctOpts = e.accounts.map(a => `<option value="${a.id}" ${a.id === focus?.account ? "selected" : ""}>${esc(a.label)}${a.number ? " · " + esc(a.number) : ""}</option>`).join("");
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>Bank statements</h1>
      <div class="note">Import each month's Maybank statement PDF. Every line is then matched to a payment automatically where the payee and amount agree (split DuitNow transfers are added together). Explain the rest: link it to a payment, create a payment for it, or mark it as needing no documents (bank charges). A line you undo, or one whose payment you remove, is left for you to explain: Match again leaves it alone.</div>
      <form class="row" id="stmtForm"><label class="field"><span>Account</span><select id="stmtAcct">${acctOpts}</select></label>
      <label class="field"><span>Statement PDF</span><input id="stmtFile" type="file" accept=".pdf"></label>
      <button class="btn" type="submit" style="align-self:end">Import statement</button>
      ${sts.length ? `<button class="ghost" type="button" id="rematch" style="align-self:end">Match again</button>` : ""}</form>
      ${sts.length ? `<label class="row"><input type="checkbox" id="bankOnly" ${state.bankOnly ? "checked" : ""}> Only lines to explain</label>` : ""}</div>
    <div id="stmtList">${bankBlocks(sts)}</div>`;
  const shown = focus && listedStatements(sts).find(s => s.month === state.month && (!focus.account || s.account_id === focus.account));
  if (shown) $(`#stmt-${shown.id}`)?.scrollIntoView?.({ block: "start" });
}

// amount: the line's, signed as on the statement (money in above 0).
async function explainLine(lineId, accountId, month, amount) {
  const pays = await api(`/api/open-payments?account=${accountId}&month=${month}`);
  const opts = pays.map(p => `<option value="${p.id}">${esc(p.description)} · ${p.direction === "in" ? "+" : ""}${money(p.amount, p.currency)} (${p.month})</option>`).join("");
  // Money in is most likely a receipt, money out a one-off payment.
  const cat = amount > 0 ? "receipt" : "other";
  $("#drawer").innerHTML = `
    <div class="row spread"><h2>Explain bank line</h2><button class="ghost small" id="closeDrawer">Close</button></div>
    <div class="card"><h3>Link to an existing payment</h3>
      <select id="ex-pay"><option value="">${pays.length ? "Choose a payment…" : "No payments for this account"}</option>${opts}</select>
      <div class="note">One payment can be linked to several lines, e.g. a 22,000 fee sent as 2,000 + 10,000 + 10,000.</div>
      <button class="btn" id="ex-link">Link</button></div>
    <div class="card"><h3>Create a new payment for this line</h3>
      <div class="note">For one-off transactions such as web hosting, flights or receipts.</div>
      <label class="field"><span>Description</span><input id="ex-desc"></label>
      <label class="field"><span>Type</span><select id="ex-cat">${Object.entries(state.meta.categories).map(([k, v]) => `<option value="${k}" ${k === cat ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <button class="btn" id="ex-create">Create payment and link</button></div>
    <div class="card"><h3>No documents needed</h3>
      <label class="field"><span>Reason</span><input id="ex-note" placeholder="e.g. bank charges, own-account transfer"></label>
      <button class="ghost" id="ex-none">Mark as no documents needed</button></div>`;
  $("#drawer").hidden = false;
  const done = async (body) => { try { await api(`/api/statement-lines/${lineId}`, { json: body }); closeDrawer(); toast("Line explained"); render(); } catch (e) { toast(e.message, true); } };
  $("#ex-link").onclick = () => $("#ex-pay").value ? done({ payment_id: +$("#ex-pay").value }) : toast("Choose a payment first.", true);
  $("#ex-create").onclick = () => { if (!$("#ex-desc").value.trim()) return toast("Give the payment a description.", true); done({ create_payment: { description: $("#ex-desc").value.trim(), category: $("#ex-cat").value } }); };
  $("#ex-none").onclick = () => done({ status: "no_docs", note: $("#ex-note").value.trim() });
}

/* ---------------- SQL Account exports ---------------- */
const SQL_FIELD_LABELS = { doc_no: "Doc No", date: "Date", description: "Description", payee: "Payee / name", amount: "Amount", debit: "Debit", credit: "Credit",
  einvoice: "e-Invoice UUID", doc_type: "Doc type", einvoice_status: "e-Invoice status", einvoice_link: "e-Invoice link" };
// The voucher numbers in a payment's SQL ref box, as the server reads them (sqlimport.refs_of).
const sqlRefs = t => (t || "").toUpperCase().split(/[,;\s]+/).filter(Boolean);

// The payments an SQL entry (x) can be linked to: those going the same way first (money out for a PV, money in for a
// receipt), and among them those that already have another voucher last and labelled, so adding a second one is a
// deliberate choice. The other way follows on its own, for a refund. sel: the payment chosen.
function paymentOptions(cands, x, sel) {
  const has = p => sqlRefs(p.sql_ref).filter(n => n !== x.doc_no.toUpperCase());
  const opts = list => [...list.filter(p => !has(p).length), ...list.filter(p => has(p).length)]
    .map(p => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.description)} · ${money(p.amount)}${has(p).length ? ` (already has ${esc(has(p).join(", "))})` : ""}</option>`).join("");
  const same = cands.filter(p => !x.direction || p.direction === x.direction), other = cands.filter(p => x.direction && p.direction !== x.direction);
  return opts(same) + (other.length
    ? `<optgroup label="${x.direction === "in" ? "Payments out (if this refunds one)" : "Money in (if this pays one back)"}">${opts(other)}</optgroup>` : "");
}
// The Import button's text: the entries not imported yet, and how many of them are linked.
const applyLabel = p => `Import ${p.records.filter(r => !r.exists).length} entries (${p.records.filter(r => (r.payment_id || r.task_id) && !r.exists).length} linked)`;

async function viewSql(main) {
  const e = ent();
  if (!e.uses_sql) {
    main.innerHTML = `${entityPicker()}<div class="card"><h1>SQL import</h1><div class="note">${esc(e.name)} isn't kept in SQL Account, so there's nothing to import.</div></div>`;
    return;
  }
  const d = await api(`/api/sql/entries?entity=${state.entity}`);
  const candOpts = u => `<option value="">Choose a payment…</option>${paymentOptions(d.candidates, u)}`;
  const unlinkBtn = x => `<button class="ghost small" data-sql-unlink="${x.id}">Unlink</button>`;
  const unRow = u => `<tr><td class="mono">${esc(u.doc_no)}</td><td>${shortDate(u.doc_date)}</td><td>${esc(u.description)}${u.payee ? `<div class="note">${esc(u.payee)}</div>` : ""}
        ${u.direction === "in" ? `<span class="pill">Money in</span>` : ""}${u.einvoice ? ` <span class="pill ok">e-Invoice ${esc(u.einvoice.slice(0, 8))}…</span>` : ""}${changedInSql(u)}</td>
        <td class="num">${money(u.amount)}</td>
        <td><div class="row" style="flex-wrap:nowrap;gap:6px"><select data-sql-link="${u.id}" style="max-width:240px">${candOpts(u)}</select><button class="ghost small" data-sql-link-go="${u.id}">Link</button></div></td>
        <td><div class="row"><button class="ghost small" data-sql-create="${u.id}">Create payment</button><button class="ghost small" data-sql-ignore="${u.id}">Ignore</button></div></td></tr>`;
  const waiting = d.unlinked.filter(u => !u.correction), corrections = d.unlinked.filter(u => u.correction);
  state.sqlCorrections = corrections.map(u => u.id);
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>SQL import · ${esc(e.code)}</h1>
      <div class="note">Paste each SQL listing for the month in turn: <b>Cash Book</b>, <b>Receipt Voucher</b>, <b>Payment Voucher</b>, <b>Journal</b> and <b>Customer Invoice</b>. Payments and receipts are matched to this tracker; customer invoices are filed against their checklist item (the e-Invoices for the fund received and the office rental), and a payroll journal, if there is one, against Salary PVs in SQL. A document that appears in two listings is only kept once, so overlap is fine.</div>
      <div class="grid2">
        <form id="sqlPasteForm" style="display:grid;gap:8px"><h3>Copy and paste (easiest)</h3>
          <div class="note">In SQL, open the Cash Book Listing, click any row, press <b>Ctrl+A</b> then <b>Ctrl+C</b>. Click in the box below and press <b>Ctrl+V</b>.</div>
          <textarea id="sqlPaste" rows="5" placeholder="Paste the SQL rows here" style="font-family:var(--f-mono);font-size:.8rem;border:1px solid var(--line);background:var(--bg);border-radius:6px;padding:6px 8px"></textarea>
          <div class="row"><button class="btn" type="submit">Read pasted rows</button></div></form>
        <form id="sqlForm" style="display:grid;gap:8px;align-content:start"><h3>Or choose an exported file</h3>
          <label class="field"><span>SQL export (.xlsx, .xls, .csv)</span><input id="sqlFile" type="file" accept=".xlsx,.xls,.csv,.ods,.txt"></label>
          <div class="row"><button class="btn" type="submit">Read file</button></div></form>
      </div></div>
    <div id="sqlPreview"></div>
    <div class="card"><h2>SQL entries not linked to a payment</h2>
      <div class="row spread"><div class="note">These are in SQL but not in this tracker. Link each one to a payment, create a payment for it, or ignore it (e.g. a reversal).</div>
      ${waiting.length > 1 ? `<button class="ghost small" id="sqlCreateAll">Create payments for all ${waiting.length}</button>` : ""}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Link to</th><th></th></tr></thead><tbody>
      ${waiting.map(unRow).join("") || `<tr><td colspan="6" class="empty">Nothing waiting.</td></tr>`}
      </tbody></table></div>
      ${corrections.length ? `<div class="row spread"><div><h3>Probably a correction (no money moved)</h3>
        <div class="note">Reversals and contras made in SQL, or a receipt and a payment for the same amount on the same day. Create payments for all leaves these out. Ignore them, unless money really moved.</div></div>
        <button class="ghost small" id="sqlIgnoreAll">Ignore all ${corrections.length}</button></div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Link to</th><th></th></tr></thead><tbody>
      ${corrections.map(unRow).join("")}</tbody></table></div>` : ""}</div>
    <div class="card"><details data-sql-open="linked" ${state.sqlOpen.linked ? "open" : ""}><summary><h2 style="display:inline">Linked to payments</h2> <span class="muted">· ${d.linked.length}</span></summary>
      <div class="note">Linked to the wrong payment? Unlink it: it goes back to the list above, and the payment's amount and paid date go back to what they were. A payment made from the voucher with Create payment, with nothing added since, is removed.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Payment</th><th></th></tr></thead><tbody>
      ${d.linked.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td>${esc(x.payment_desc)} <span class="muted">(${monthName(x.payment_month)})</span></td>
        <td>${unlinkBtn(x)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">None yet.</td></tr>`}
      </tbody></table></div></details></div>
    ${d.ignored.length ? `<div class="card"><details data-sql-open="ignored" ${state.sqlOpen.ignored ? "open" : ""}><summary><h2 style="display:inline">Ignored</h2> <span class="muted">· ${d.ignored.length}</span></summary>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th></th></tr></thead><tbody>
      ${d.ignored.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td><button class="ghost small" data-sql-unignore="${x.id}">Un-ignore</button></td></tr>`).join("")}
      </tbody></table></div></details></div>` : ""}
    <div class="card"><h2>Journals and customer invoices</h2>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>e-Invoice</th><th>Checklist item</th></tr></thead><tbody>
      ${d.documents.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}</td>
        <td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.task_title ? `<span class="pill ok">${esc(x.task_title.split(":")[0])} (${esc(x.task_month)})</span>` : `<span class="muted">—</span>`}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Paste the Journal and Customer Invoice listings to see them here.</td></tr>`}
      </tbody></table></div></div>
    <div class="card"><h2>e-Invoices</h2><div class="note">Every SQL document with an e-Invoice, and whether LHDN has validated it.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead><tbody>
      ${d.einvoices.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.payee || x.description)}</td><td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.payment_id ? unlinkBtn(x) : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">None imported yet.</td></tr>`}
      </tbody></table></div></div>
    <div class="card"><h2>Imported files</h2>${d.imports.map(i => `<div class="row spread"><span>${esc(i.filename)} <span class="muted">· ${i.entries} entries, ${i.linked} linked</span></span><span class="muted">${esc(i.imported_at.replace("T", " "))}</span></div>`).join("") || `<div class="note">None yet.</div>`}</div>`;
  // A listing read but not imported yet stays, with links picked by hand, while you tidy the entries below.
  $("#sqlPaste").value = state.sqlPaste[state.entity] || "";
  if (state.sqlPreview?.entity_id === state.entity) renderSqlPreview(state.sqlPreview);
}

function einvPill(x) {
  if (!x.einvoice && !x.einvoice_status) return `<span class="muted">—</span>`;
  const ok = (x.einvoice_status || "").startsWith("Validated") && !x.taken_back_by;
  const pill = `<span class="pill ${ok ? "ok" : "warn"}">${x.taken_back_by ? `Cancelled by ${esc(x.taken_back_by)}` : esc(x.einvoice_status || "Has UUID")}</span>`;
  return x.einvoice_link ? `${pill} <a href="${esc(x.einvoice_link)}" target="_blank" rel="noopener noreferrer">MyInvois ↗</a>` : pill;
}

function renderSqlPreview(p) {
  state.sqlPreview = p;
  const colOpts = sel => `<option value="">(none)</option>` + p.headers.map((h, i) => `<option value="${i}" ${i === sel ? "selected" : ""}>${esc(h || "Column " + (i + 1))}</option>`).join("");
  const kinds = { journal: "Journal", invoice: "Customer invoice" };
  const target = r => r.exists ? `<span class="pill grey">Already imported</span>`
    : r.kind !== "payment" ? (r.task_id ? `<span class="pill ok">Checklist: ${esc(r.task_title)}</span>` : `<span class="pill grey">${kinds[r.kind]}, kept on file</span>`)
    : `<select data-sql-row="${r.row}"><option value="">Not linked</option>${paymentOptions(p.candidates, r, r.payment_id)}</select>${r.task_id ? `<div class="note">Also: ${esc(r.task_title)}</div>` : ""}${changedInSql(r)}`;
  $("#sqlPreview").innerHTML = `<div class="card">
    <div class="row spread"><h2>${esc(p.filename)}</h2><span class="muted">${p.records.length} entries found</span></div>
    <div class="note">Check the columns were read correctly, then check each suggested payment.</div>
    <div class="form">${p.fields.map(f => `<label class="field"><span>${SQL_FIELD_LABELS[f]}</span><select data-sql-map="${f}">${colOpts(p.mapping[f])}</select></label>`).join("")}</div>
    <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Records this payment</th></tr></thead><tbody>
    ${p.records.map(r => `<tr><td class="mono">${esc(r.doc_no)}</td><td>${shortDate(r.date)}</td><td>${esc(r.description)}${r.payee ? `<div class="note">${esc(r.payee)}</div>` : ""}
      ${r.einvoice || r.einvoice_status ? `<div>${einvPill(r)}</div>` : ""}</td>
      <td class="num">${r.direction === "in" ? "+" : ""}${money(r.amount)}</td>
      <td>${target(r)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="row"><button class="btn" id="sqlApply">${applyLabel(p)}</button><button class="ghost" id="sqlCancel">Cancel</button></div></div>`;
}

/* ---------------- Recurring payees ---------------- */
async function viewPayees(main) {
  const e = ent();
  const list = await api(`/api/payees?entity=${state.entity}&month=${state.month}`);
  // A month not set up gets the card that sets it up, rather than an Add button per row that would set it all up.
  const m = await api(`/api/month?entity=${state.entity}&month=${state.month}`);
  const cats = state.meta.categories, mon = MONTHS[+state.month.slice(5) - 1];
  // What the last save changed in the months already set up, shown once.
  const ch = state.payeeSaved; state.payeeSaved = null;
  const saved = ch && (ch.changes.length || ch.kept.length) ? `<div class="card"><h3>Saved. Months already set up:</h3>
    ${ch.changes.map(x => `<div class="note">${esc(x)}</div>`).join("")}
    ${ch.kept.length ? `<div class="note"><b>Left as they were</b> (paid, linked, changed by hand, or already due; change them by hand if needed): ${ch.kept.map(esc).join("; ")}</div>` : ""}</div>` : "";
  main.innerHTML = `${entityPicker()}${saved}${m.set_up ? "" : notSetUp(m.entity, m.month)}
    <div class="card"><div class="row spread"><h1>Recurring payments · ${esc(e.code)}</h1><button class="btn" data-edit-payee="new">Add recurring payment</button></div>
      <div class="note">Each active row is added to a month when the month is set up. Saving a change also updates the payments not due yet in ${esc(monthName(currentCycle()))} and later months already set up, unless they were paid, linked or changed by hand. Payments already due are left as they were: they were most likely paid already.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Payee</th><th>Type</th><th>Paid</th><th class="num">Usual amount</th><th>Bank / ref</th><th>Status</th><th></th></tr></thead><tbody>
      ${list.map(p => `<tr><td><b>${esc(p.name)}</b><div class="note">${esc(p.desc_template)}</div>
        ${p.start_date ? `<div class="note">Starts ${fmtDate(p.start_date)}</div>` : ""}${p.end_date ? `<div class="note">Ends ${fmtDate(p.end_date)}</div>` : ""}
        ${p.notes ? `<div class="note">${esc(p.notes)}</div>` : ""}${p.advances.map(a => `<div class="note">Advance: −${money(a.monthly_deduction)} a month, ${a.start_month} to ${a.end_month}</div>`).join("")}</td>
        <td>${esc(cats[p.category] || p.category)}</td><td>${p.month_offset ? "Next month" : "Same month"}, day ${p.due_day}</td>
        <td class="num">${money(p.amount, p.currency)}${p.amount_varies ? `<div class="note">varies</div>` : ""}</td>
        <td class="mono">${esc(p.bank_details || p.reference || "")}</td>
        <td>${p.active ? `<span class="pill ok">Active</span>` : `<span class="pill grey">Stopped</span>`}</td>
        <td><div class="row"><button class="ghost small" data-edit-payee="${p.id}">Edit</button>${p.in_month ? `<span class="pill ok">In ${mon} ✓</span>`
          : !p.employed ? `<span class="muted">Not employed in ${mon}</span>` : m.set_up ? `<button class="ghost small" data-add-month="${p.id}">Add to ${mon}</button>` : ""}</div></td></tr>`).join("")}
      </tbody></table></div></div>`;
  state.payees = list;
}

function editPayee(id) {
  const p = id === "new" ? { name: "", category: "utility", desc_template: "", amount: "", amount_varies: 0, month_offset: 1, due_day: 6, active: 1, account_id: ent().accounts[0]?.id } : state.payees.find(x => x.id === +id);
  const cats = state.meta.categories;
  $("#drawer").innerHTML = `
    <div class="row spread"><h2>${id === "new" ? "Add recurring payment" : "Edit " + esc(p.name)}</h2><button class="ghost small" id="closeDrawer">Close</button></div>
    <form class="form" id="payeeForm" style="grid-template-columns:1fr 1fr">
      <label class="field" style="grid-column:1/-1"><span>Payee</span><input id="py-name" value="${esc(p.name)}" required></label>
      <label class="field" style="grid-column:1/-1"><span>Description each month ({M} = payroll month, {M+1} = next month)</span><input id="py-desc" value="${esc(p.desc_template)}" placeholder="TNB - {M}"></label>
      <label class="field"><span>Type</span><select id="py-cat">${Object.entries(cats).map(([k, v]) => `<option value="${k}" ${k === p.category ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label class="field"><span>Pay from</span><select id="py-acct">${ent().accounts.map(a => `<option value="${a.id}" ${a.id === p.account_id ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</select></label>
      <label class="field"><span>Usual amount</span><input id="py-amt" type="number" step="0.01" value="${p.amount ?? ""}"></label>
      <label class="field"><span>Amount changes monthly</span><select id="py-var"><option value="0">No, fixed</option><option value="1" ${p.amount_varies ? "selected" : ""}>Yes, estimate</option></select></label>
      <label class="field"><span>Paid in</span><select id="py-off"><option value="0">The payroll month</option><option value="1" ${p.month_offset ? "selected" : ""}>The following month</option></select></label>
      <label class="field"><span>Day of month</span><input id="py-day" type="number" min="1" max="31" value="${p.due_day}"></label>
      <label class="field"><span>Bank details</span><input id="py-bank" value="${esc(p.bank_details || "")}"></label>
      <label class="field"><span>Account / ref no.</span><input id="py-ref" value="${esc(p.reference || "")}"></label>
      <label class="field" style="grid-column:1/-1"><span>Words that appear in the bank statement (for automatic matching)</span><input id="py-match" value="${esc(p.match_words || "")}"></label>
      <label class="field"><span>Start date (joiners)</span><input id="py-start" type="date" value="${esc(p.start_date || "")}"></label>
      <label class="field"><span>Last day (leavers)</span><input id="py-end" type="date" value="${esc(p.end_date || "")}"></label>
      <div class="note" style="grid-column:1/-1">Salaries are prorated by calendar days in the joining and leaving months. No payment is created before the start date or after the last day. A salary's start date and last day also add reminders to the checklist, each in the month it falls due: e-CP22, PERKESO and KWSP registration and stamping the appointment letter for a joiner, CP22A for a leaver. One due in a month not set up yet shows in the latest month set up until then, without counting there.</div>
      <label class="field" style="grid-column:1/-1"><span>Notes</span><input id="py-notes" value="${esc(p.notes || "")}"></label>
      <label class="field"><span>Status</span><select id="py-active"><option value="1">Active</option><option value="0" ${p.active ? "" : "selected"}>Stopped</option></select></label>
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">Save</button></div>
    </form>`;
  $("#drawer").hidden = false;
  $("#payeeForm").onsubmit = async ev => {
    ev.preventDefault();
    const body = { entity_id: state.entity, name: $("#py-name").value.trim(), desc_template: $("#py-desc").value.trim() || $("#py-name").value.trim() + " - {M}",
      category: $("#py-cat").value, account_id: +$("#py-acct").value, amount: $("#py-amt").value === "" ? null : +$("#py-amt").value,
      amount_varies: +$("#py-var").value, month_offset: +$("#py-off").value, due_day: +$("#py-day").value || 6,
      bank_details: $("#py-bank").value.trim(), reference: $("#py-ref").value.trim(), match_words: $("#py-match").value.trim(), active: +$("#py-active").value,
      start_date: $("#py-start").value || null, end_date: $("#py-end").value || null, notes: $("#py-notes").value.trim() };
    if (id !== "new") body.id = +id;
    try { state.payeeSaved = await api("/api/payees", { json: body }); closeDrawer(); toast("Saved"); render(); } catch (e) { toast(e.message, true); }
  };
}

/* ---------------- Audit pack ---------------- */
// Before you print: what the month still needs, as the server works it out, under these headings. Each line is a button
// to the screen that fixes it.
const READY_HEADS = { statement: "Bank statements", lines: "Bank statements", payment: "Payments not complete",
  task: "Checklist documents missing", task_open: "Checklist items not done", not_in_sql: "Paid, not recorded in SQL",
  unprintable: "Files that won't print" };

async function viewAudit(main) {
  const r = await api(`/api/audit-readiness?entity_id=${state.entity}&month=${state.month}`);
  const setUp = r.set_up ? "" : notSetUp(r.entity, r.month, r.payments);
  if (!r.set_up && !r.payments) { main.innerHTML = entityPicker() + setUp; return; }
  const packs = await api(`/api/audit-packs?entity=${state.entity}&month=${state.month}`);
  let head = "";
  const open = r.items.map(x => `${READY_HEADS[x.kind] !== head ? `<h3>${esc(head = READY_HEADS[x.kind])}</h3>` : ""}
    <button class="fix" data-fix="${x.fix}" data-id="${x.id ?? ""}"><b>${esc(x.title)}</b><span>${esc(x.detail)}</span></button>`).join("");
  const pack = !r.pack ? "" : r.pack.changed ? `<div class="row"><span class="pill warn">${esc(r.pack_open)}</span><span class="note">Build it again before you print.</span></div>`
    : `<div class="note">The pack built ${esc(r.pack.when)} is up to date.</div>`;
  // With a pack built and up to date, it asks whether it was printed and filed (a month set up can be marked).
  const built = r.pack && !r.pack.changed && r.set_up && !r.closed_at;
  // What the pack doesn't hold: the SQL vouchers that stand for an upload are printed from SQL.
  const fromSql = r.to_print ? `<div class="note">Not in the PDF: print ${esc(r.to_print)} from SQL.</div>` : "";
  main.innerHTML = `${entityPicker()}${setUp}
    <div class="card"><div class="row spread"><h1>Audit pack · ${esc(r.entity.code)} · ${esc(r.label)}</h1>${r.closed_at ? `<span class="pill ok">Filed ${shortDate(r.closed_at)}</span>` : ""}</div>
      <div class="note">One PDF with an index page, then every payment's documents in filing order (PV, approval, invoice, bank receipt, e-Invoice), then checklist documents and the bank statement. Print it once and file it.</div>
      <h2>Before you print</h2>
      ${r.ready ? `<div class="row"><span class="pill ok">Ready to print</span><span class="note">Every bank statement is imported and explained, every payment and checklist item is done with its documents, and every file will print.</span></div>`
        : `<div class="row">${r.summary.map(s => `<span class="pill warn">${esc(s)}</span>`).join("")}</div>
          <div class="note">Click a line to fix it. You can still build the pack: what is missing is listed on its index page.</div><div class="fixes">${open}</div>`}
      ${fromSql}${pack}
      <div class="row"><button class="btn" id="buildPack">Build audit pack PDF</button></div><div id="packOut" class="note" hidden></div>
      ${built ? `<div class="row"><b>Printed and filed?</b><button class="btn" data-close-month="built">Yes, mark month as filed</button></div>` : ""}</div>
    <div class="card"><h2>Recent packs</h2>${packs.length ? packs.map(p => `<div class="row spread"><a href="${p.url}" target="_blank">${esc(p.name)}</a><span class="muted">${esc(p.at.replace("T", " "))}</span></div>`).join("") : `<div class="note">None built for ${esc(r.label)} yet.</div>`}</div>`;
}

// Marks the month on show as filed. With anything still open (Before you print, or the pack not built or out of date)
// it asks first, naming it: a month filed outside the app can still be marked. afterBuild: asked from 'Printed and
// filed?' on the Audit page.
async function markFiled(afterBuild) {
  const r = await api(`/api/audit-readiness?entity_id=${state.entity}&month=${state.month}`);
  if (r.still_open.length && !confirm(`Still open in ${r.entity.code} ${r.label}:\n${r.still_open.map(s => "• " + s).join("\n")}\n\n${afterBuild ? "" : "If this month was already filed outside the app, that is fine. "}Mark it as filed anyway?`)) return;
  await api("/api/months/close", { json: { entity_id: state.entity, month: state.month, closed: true } });
  toast(`${r.label} marked as filed`); return render();
}

// A line of Before you print opens the screen that fixes it, for this company and month: the payment's drawer, the
// checklist item on the month page, the Bank statements page on that account, or the SQL page.
function fixIt(where, id) {
  const view = { payment: "entity", task: "entity", account: "bank", sql: "sql" }[where];
  return goTo({ view, payment_id: where === "payment" ? id : null, task_id: where === "task" ? id : null, account_id: where === "account" ? id : null });
}

/* ---------------- Backup & log ---------------- */
async function viewSettings(main) {
  const log = await api("/api/activity");
  main.innerHTML = `
    <div class="card"><h1>Backup &amp; records</h1>
      <div class="note">Everything is stored on this PC in <span class="mono">${esc(state.meta.data_dir)}</span>: the database (records.db), uploaded documents and audit packs. Nothing is sent anywhere else.</div>
      <div class="note">${state.meta.backup_dir ? `Backups are also copied to <span class="mono">${esc(state.meta.backup_dir)}</span>.` : `Backups are saved in the backups folder on this PC. To also copy them to an external drive, set <span class="mono">backup_dir</span> in settings.json.`}</div>
      <div class="row"><button class="btn" id="doBackup">Back up now</button><button class="ghost" id="doCheck">Check documents haven't changed</button></div>
      <div id="setOut" class="note"></div></div>
    <div class="card"><h2>First month tracked in this app</h2>
      <div class="note">Months before it are never set up on their own, and nothing in them counts as overdue or past due. Leave it empty for no limit. Tidy up removes, from the months before it, the payments with no paid date, documents, SQL voucher or bank line, and the checklist items not ticked with no documents.</div>
      ${state.meta.entities.map(e => `<div class="row"><label class="field"><span>${esc(e.name)}</span><input type="month" id="first-${e.id}" value="${esc(e.first_month || "")}"></label>
        <button class="ghost small" data-first-month="${e.id}" style="align-self:end">Save</button>
        ${e.first_month ? `<button class="ghost small" data-tidy="${e.id}" style="align-self:end">Tidy up months before this</button>` : ""}</div>`).join("")}</div>
    <div class="card"><h2>Activity log</h2><div class="tbl-wrap"><table><tbody>
      ${log.map(a => `<tr><td class="mono muted" style="white-space:nowrap">${esc(a.at.replace("T", " "))}</td><td>${esc(a.what)}</td></tr>`).join("") || `<tr><td class="empty">Nothing yet.</td></tr>`}
    </tbody></table></div></div>`;
}

/* ---------------- Events ---------------- */
document.addEventListener("click", async ev => {
  const t = ev.target.closest("button, tr[data-payment], a");
  if (!t) return;
  const ds = t.dataset;
  try {
    if (ds.view) return go(ds.view, ds.entity);
    if (ds.pill) return pillGo(ds.pill, +ds.entity);
    if (ds.nextGo) { const r = state.next?.get(ds.nextGo); return r && goTo(r.go); }
    if (ds.older) { const [e, m] = ds.older.split(" "); return goTo({ view: "entity", entity_id: +e, month: m }); }
    if (ds.nextAll) { const k = nextScope() || 0; state.nextAll[k] = !state.nextAll[k]; return refreshNext(); }
    if (ds.savedBalance) return render();
    if (ds.nextBackup) {
      t.disabled = true;
      try { const r = await api("/api/backup", { json: {} }); toast(r.warning || "Backup saved", !!r.warning); } finally { t.disabled = false; }
      return refreshNext();
    }
    if (ds.pickEntity) { if (!closeDrawer()) return; state.entity = +ds.pickEntity; return render(); }
    if (ds.fix) return fixIt(ds.fix, +ds.id);
    if (ds.closeMonth) return await markFiled(ds.closeMonth === "built");
    if (ds.reopenMonth) {
      const r = await api("/api/months/close", { json: { entity_id: state.entity, month: state.month, closed: false } });
      toast(`${monthName(state.month)} reopened.${r.pack_ticked ? " Its audit pack item stays ticked; untick it if the pack needs doing again." : ""}`); return render();
    }
    if (ds.openMonth) {
      await api("/api/months/open", { json: { entity_id: +ds.openMonth, month: state.month } });
      toast(`${monthName(state.month)} is set up`); return render();
    }
    if (t.id === "prevMonth" || t.id === "nextMonth" || t.id === "thisMonth") {
      if (!closeDrawer()) return;
      state.month = t.id === "thisMonth" ? currentCycle() : shiftMonth(state.month, t.id === "prevMonth" ? -1 : 1);
      renderNav(); return render();
    }
    if (t.id === "closeDrawer") return closeDrawer();
    if (t.id === "printPage") return window.print();
    if (ds.payment) {
      // Clicking the open payment again keeps what was typed in it.
      const same = +ds.payment === state.openPayment && !$("#drawer").hidden;
      if (!same && !mayLeave()) return;
      return openPayment(+ds.payment, same ? unsavedEdits() : {});
    }
    // A payment's document box (data-upload: its type) or a checklist item's (data-task-upload, with data-type).
    if (ds.upload || ds.taskUpload) {
      const files = await pickFile(!ds.replaces); if (!files.length) return;
      if (ds.replaces && !confirm(`Replace "${ds.name}" with "${files[0].name}"? The old file is taken out of the audit pack.`)) return;
      const owner = ds.taskUpload ? { task_id: +ds.taskUpload } : { payment_id: state.openPayment };
      // awaited, so a file refused reaches the message below
      return await uploadFiles(files, { ...owner, doc_type: ds.upload || ds.type, replaces: ds.replaces });
    }
    if (t.id === "extraUpload") {
      const files = await pickFile(); if (!files.length) return;
      return await uploadFiles(files, { payment_id: state.openPayment, doc_type: $("#extraType").value });
    }
    if (ds.removeDoc) {
      if (!confirm(`Remove "${ds.name}"? It is taken off here and left out of the audit pack; the file itself is kept on this PC.`)) return;
      await api(`/api/documents/${ds.removeDoc}/remove`, { json: {} }); toast(`Removed ${ds.name}`); return render();
    }
    if (t.id === "deletePayment") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to remove"; return; }
      let r;
      try { r = await api(`/api/payments/${state.openPayment}`, { method: "DELETE", json: {} }); }
      catch (e) { t.dataset.confirm = ""; t.textContent = "Remove this payment"; throw e; }
      closeDrawer(true); toast(`Payment removed${r.unlinked.length ? `; ${r.unlinked.join(", ")} back under SQL entries not linked` : ""}${r.lines
        ? `; ${r.lines} bank line${r.lines > 1 ? "s" : ""} back under lines to explain` : ""}`); return render();
    }
    if (t.id === "addPayment") return addPaymentDrawer();
    if (ds.explain) return explainLine(+ds.explain, +ds.account, ds.month, +ds.amount);
    if (ds.unlink) {
      const r = await api(`/api/statement-lines/${ds.unlink}`, { json: { payment_id: null } });
      toast(r.removed ? `Undone. ${r.removed} was created from the bank statement and had nothing else on it, so it was removed too.` : "Undone. The line is waiting to be explained.");
      return render();
    }
    if (t.id === "sqlApply") {
      const p = state.sqlPreview; t.disabled = true;
      const links = {}; for (const r of p.records) if (r.payment_id && !r.exists) links[r.row] = r.payment_id;
      const res = await api("/api/sql/apply", { json: { token: p.token, header_row: p.header_row, mapping: p.mapping, links } });
      state.sqlPreview = null; delete state.sqlPaste[state.entity];
      toast(`Imported ${res.added} entries; ${res.linked} linked to payments${res.skipped ? `, ${res.skipped} already imported` : ""}${matchedNote(res)}.`);
      return render();
    }
    if (t.id === "sqlCancel") { state.sqlPreview = null; delete state.sqlPaste[state.entity]; $("#sqlPreview").innerHTML = ""; $("#sqlPaste").value = ""; return; }
    if (t.id === "sqlCreateAll") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to create them all"; return; }
      const r = await api("/api/sql/entries/create-all", { json: { entity_id: state.entity } });
      toast(`Created ${r.created} payments from SQL${r.linked ? `; ${r.linked} linked to existing payments with the same SQL number` : ""}${r.left ? `; ${r.left} left for you to check (number already linked, changed in SQL?)` : ""}${r.corrections.length ? `; ${r.corrections.length} left out as probably corrections (no money moved)` : ""}; ${r.bank_lines_matched} bank lines matched`); return render();
    }
    if (t.id === "sqlIgnoreAll") {
      if (t.dataset.confirm !== "1") { t.dataset.confirm = "1"; t.textContent = "Click again to ignore them all"; return; }
      const r = await api("/api/sql/entries/ignore", { json: { ids: state.sqlCorrections } });
      toast(r.ignored === 1 ? "1 entry ignored; it is listed under Ignored" : `${r.ignored} entries ignored; they are listed under Ignored`); return render();
    }
    if (t.id === "rematch") {
      const r = await api("/api/statements/rematch", { json: { entity_id: state.entity } });
      toast(`${r.matched} more bank lines matched; ${r.no_docs} marked as bank charges or own transfers`); return render();
    }
    if (ds.sqlCreate) { const r = await api(`/api/sql/entries/${ds.sqlCreate}`, { json: { create_payment: {} } }); toast(`Payment created${matchedNote(r)}`); return render(); }
    if (ds.sqlIgnore) { await api(`/api/sql/entries/${ds.sqlIgnore}`, { json: { status: "ignored" } }); return render(); }
    if (ds.sqlLinkGo) {
      const v = $(`select[data-sql-link="${ds.sqlLinkGo}"]`).value;
      if (!v) return toast("Choose a payment first.", true);
      const r = await api(`/api/sql/entries/${ds.sqlLinkGo}`, { json: { payment_id: +v } }); toast(`Linked${matchedNote(r)}`); return render();
    }
    if (ds.sqlUnlink) {
      const r = await api(`/api/sql/entries/${ds.sqlUnlink}/unlink`, { json: {} });
      toast(r.removed ? `${r.doc_no} is back under SQL entries not linked, and the payment made from it was removed`
        : `${r.doc_no} unlinked from ${r.payment}; it's back under SQL entries not linked`); return render();
    }
    if (ds.sqlUnignore) { const r = await api(`/api/sql/entries/${ds.sqlUnignore}/unignore`, { json: {} }); toast(`${r.doc_no} is back under SQL entries not linked`); return render(); }
    if (ds.editPayee) return editPayee(ds.editPayee);
    if (ds.addMonth) {
      const r = await api(`/api/payees/${ds.addMonth}/add-to-month`, { json: { month: state.month } });
      toast(r.opened ? `${monthName(state.month)} is set up: its checklist and recurring payments were added` : `Added to ${monthName(state.month)}`);
      return render();
    }
    if (t.id === "buildPack") {
      t.disabled = true; t.textContent = "Building…"; $("#packOut").hidden = true;
      let r;
      try { r = await api("/api/audit-pack", { json: { entity_id: state.entity, month: state.month } }); }
      catch (e) {
        // The button works again, and the reason (which document) stays under it after the message goes.
        t.disabled = false; t.textContent = "Build audit pack PDF";
        $("#packOut").textContent = `The pack wasn't built: ${e.message}`; $("#packOut").hidden = false; throw e;
      }
      window.open(r.url, "_blank"); return render();
    }
    if (t.id === "doBackup") {
      t.disabled = true; const r = await api("/api/backup", { json: {} });
      $("#setOut").textContent = r.warning || `Saved ${r.file}${r.copied ? " and copied to " + r.copied : ""}`; t.disabled = false; return;
    }
    if (ds.firstMonth) {
      await api(`/api/entities/${ds.firstMonth}/first-month`, { json: { month: $(`#first-${ds.firstMonth}`).value } });
      state.meta = await api("/api/meta"); toast("Saved"); return render();
    }
    if (ds.tidy) {
      const e = state.meta.entities.find(x => x.id === +ds.tidy);
      if (t.dataset.confirm !== "1") {
        const n = await api(`/api/months/tidy?entity=${e.id}`);
        if (!n.payments && !n.tasks) return toast(`Nothing to tidy up before ${monthName(n.before)}.`);
        t.dataset.confirm = "1"; t.textContent = `Click again to remove ${n.payments} payments and ${n.tasks} checklist items before ${monthName(n.before)}`; return;
      }
      const r = await api("/api/months/tidy", { json: { entity_id: e.id } });
      toast(`Removed ${r.payments} payments and ${r.tasks} checklist items from ${e.code}`); return render();
    }
    if (t.id === "doCheck") {
      const r = await api("/api/integrity");
      $("#setOut").textContent = r.problems.length ? `${r.problems.length} of ${r.checked} documents are missing or changed: ${r.problems.map(p => p.stored_path).join(", ")}` : `All ${r.checked} documents match their upload fingerprints.`;
    }
  } catch (e) { toast(e.message, true); }
});

document.addEventListener("change", async ev => {
  const t = ev.target;
  try {
    // Only the statements are drawn again, so the account and file chosen for an import stay.
    if (t.id === "bankOnly") { state.bankOnly = t.checked; $("#stmtList").innerHTML = bankBlocks(state.statements); return; }
    if (t.dataset.task) {
      // A tick by hand while something is still missing asks first, naming it.
      const task = state.data.tasks.find(x => x.id === +t.dataset.task);
      if (t.checked && task?.lacking.length && !confirm(`${task.lacking.join(". ")}.\n\nTick anyway?`)) { t.checked = false; return; }
      await api(`/api/tasks/${t.dataset.task}`, { json: { done: t.checked } }); render();
    }
    if (t.dataset.sqlRow) {
      const r = state.sqlPreview.records.find(x => x.row === +t.dataset.sqlRow); r.payment_id = t.value ? +t.value : null; r.picked = true;
      $("#sqlApply").textContent = applyLabel(state.sqlPreview);
    }
    if (t.dataset.sqlMap) {
      // The links picked by hand go along, so reading the columns again keeps them for the rows still there.
      const p = state.sqlPreview; const mapping = { ...p.mapping, [t.dataset.sqlMap]: t.value === "" ? null : +t.value };
      const picks = Object.fromEntries(p.records.filter(r => r.picked).map(r => [r.row, r.payment_id]));
      renderSqlPreview(await api("/api/sql/preview", { json: { token: p.token, header_row: p.header_row, mapping, picks } }));
    }
  } catch (e) { toast(e.message, true); }
});

document.addEventListener("submit", async ev => {
  if (ev.target.id === "payForm") {
    ev.preventDefault();
    try {
      // Only what was changed, so an untouched estimate stays an estimate
      const now = payFormValues(), changed = {};
      for (const k in now) if (now[k] !== state.payLoaded[k]) changed[k] = now[k];
      if (!Object.keys(changed).length) return toast("Nothing has changed.");
      await api(`/api/payments/${state.openPayment}`, { method: "PATCH", json: changed });
      state.payLoaded = now;  // saved, so the refresh shows what the records now hold
      toast("Saved"); render();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "stmtForm") {
    ev.preventDefault();
    const f = $("#stmtFile").files[0];
    if (!f) return toast("Choose the statement PDF first.", true);
    const fd = new FormData(); fd.append("file", f); fd.append("account_id", $("#stmtAcct").value);
    try {
      const r = await api("/api/statements", { form: fd });
      toast(`Imported ${r.lines} lines for ${monthName(r.month)}; ${r.matched} matched, ${r.no_docs} bank charges or own transfers.`);
      render();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "sqlForm") {
    ev.preventDefault();
    const f = $("#sqlFile").files[0];
    if (!f) return toast("Choose the SQL export file first.", true);
    const fd = new FormData(); fd.append("file", f); fd.append("entity_id", state.entity);
    try { renderSqlPreview(await api("/api/sql/preview", { form: fd })); } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "sqlPasteForm") {
    ev.preventDefault();
    const text = $("#sqlPaste").value;
    if (!text.trim()) return toast("Paste the rows copied from SQL first.", true);
    try { renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, text } })); } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "addForm") {
    ev.preventDefault();
    try {
      await api("/api/payments", { json: { entity_id: state.entity, month: state.month, description: $("#ap-desc").value.trim(), category: $("#ap-cat").value,
        amount: $("#ap-amt").value === "" ? null : +$("#ap-amt").value, account_id: +$("#ap-acct").value, due_date: $("#ap-due").value, direction: $("#ap-dir").value } });
      closeDrawer(); toast("Payment added"); render();
    } catch (e) { toast(e.message, true); }
  }
});

function addPaymentDrawer() {
  if (!mayLeave()) return;
  state.openPayment = null;
  const e = ent();
  $("#drawer").innerHTML = `
    <div class="row spread"><h2>Add a payment</h2><button class="ghost small" id="closeDrawer">Close</button></div>
    <div class="note">For ad hoc payments, claims and receipts in ${monthName(state.month)}.</div>
    <form class="form" id="addForm" style="grid-template-columns:1fr 1fr">
      <label class="field" style="grid-column:1/-1"><span>Description</span><input id="ap-desc" required placeholder="e.g. Oct 2026 Claims - Soon"></label>
      <label class="field"><span>Type</span><select id="ap-cat">${Object.entries(state.meta.categories).map(([k, v]) => `<option value="${k}" ${k === "claim" ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
      <label class="field"><span>Money</span><select id="ap-dir"><option value="out">Paid out</option><option value="in">Received</option></select></label>
      <label class="field"><span>Amount</span><input id="ap-amt" type="number" step="0.01"></label>
      <label class="field"><span>Due date</span><input id="ap-due" type="date"></label>
      <label class="field" style="grid-column:1/-1"><span>Account</span><select id="ap-acct">${e.accounts.map(a => `<option value="${a.id}">${esc(a.label)}</option>`).join("")}</select></label>
      <div class="row"><button class="btn" type="submit">Add payment</button></div>
    </form>`;
  $("#drawer").hidden = false;
}

// Drag-and-drop files onto a document box in the payment drawer: each file is added, never replacing one. Files dropped
// anywhere else would make the browser leave the app to show them, so that is stopped; a file box (on the Bank
// statements and SQL import pages) still takes its file.
const dragsFiles = ev => ev.dataTransfer?.types?.includes("Files") && !ev.target.closest?.("input[type=file]");
document.addEventListener("dragover", ev => { if (!dragsFiles(ev)) return; ev.preventDefault(); ev.target.closest?.("[data-slot]")?.classList.add("drag"); });
document.addEventListener("dragleave", ev => ev.target.closest?.("[data-slot]")?.classList.remove("drag"));
// Where a file dropped in the wrong place can go, on the page showing.
function dropHint() {
  if (state.openPayment && !$("#drawer").hidden) return "Drop the file onto one of the document boxes.";
  if (state.view === "bank") return "Drop the statement PDF on the Choose file button under Statement PDF.";
  if (state.view === "sql") return "Drop the SQL export on the Choose file button under SQL export.";
  if (state.view === "entity") return "Open the payment and drop the file on a document box, or use the + buttons on the checklist.";
  return "Open a payment on the company's page and drop the file on a document box.";
}
document.addEventListener("drop", async ev => {
  if (!dragsFiles(ev)) return;
  ev.preventDefault();
  const s = ev.target.closest?.("[data-slot]");
  if (!s || !state.openPayment) return toast(dropHint());
  s.classList.remove("drag");
  try { await uploadFiles([...ev.dataTransfer.files], { payment_id: state.openPayment, doc_type: s.dataset.slot }); } catch (e) { toast(e.message, true); }
});
document.addEventListener("keydown", ev => { if (ev.key === "Escape") closeDrawer(); });
document.addEventListener("input", ev => { if (ev.target.id === "sqlPaste") state.sqlPaste[state.entity] = ev.target.value; });
// The SQL box holds one listing: pasting replaces what is in it, so a listing left there can't run into the next one.
document.addEventListener("paste", ev => {
  const text = ev.target.id === "sqlPaste" && ev.clipboardData?.getData("text");
  if (!text) return;
  ev.preventDefault(); ev.target.value = text; state.sqlPaste[state.entity] = text;
});
// Keeps the SQL page's lists open across a refresh (after Unlink); toggle doesn't bubble, so it is caught on the way down.
document.addEventListener("toggle", ev => { const k = ev.target.dataset?.sqlOpen; if (k) state.sqlOpen[k] = ev.target.open; }, true);

// The current cycle and the month before are set up on their own; other months when you ask.
async function openCycleMonths() {
  try {
    for (const e of state.meta.entities) for (const m of [shiftMonth(currentCycle(), -1), currentCycle()])
      await api("/api/months/open", { json: { entity_id: e.id, month: m, auto: true } });
    return true;
  } catch (e) { toast(e.message, true); return false; }
}

// A day after the one the page last set up the cycle's months on, whichever way it is drawn again (a click, or the tab
// coming back): the new cycle's months are set up, and a page still on the cycle it was drawn in moves to the new one,
// unless a payment is open. state.day moves on only once the months are set up, so a failure is tried again.
async function newDay() {
  const [y, m, d] = state.day.split("-").map(Number);
  if (state.month === currentCycle(new Date(y, m - 1, d)) && !state.openPayment) state.month = currentCycle();
  if (await openCycleMonths()) state.day = dayKey();
  renderNav();
}

// A tab left open overnight: when it comes back into view on another day the page is drawn again (what fell due is
// flagged, and render sets up the new cycle); on the same day only the Next up list is read again.
document.addEventListener("visibilitychange", async () => {
  if (document.hidden || !state.meta) return;
  try {
    if (dayKey() === state.day) return await refreshNext(true);
    await render();
  } catch (e) { toast(e.message, true); }
});

(async function start() {
  state.meta = await api("/api/meta");
  state.entity = state.meta.entities[0]?.id;
  await openCycleMonths();
  renderNav(); render();
})();
