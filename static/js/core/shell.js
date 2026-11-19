"use strict";
/* ---------------- Search and sort on the flat lists ---------------- */
// LT-BEGIN (pure helpers: no page access, so they can be run on their own in Node)
const LT = {
  // The payments a bank line can be linked to, likeliest first: the app's suggestions by score, then the closest amount
  // to what each still has open. Unless all: only those going the same way as the line and not yet covered by their lines.
  linkList(line, pays, q, all) {
    const amt = Math.abs(line.amount), sugg = new Map((line.suggestions || []).map(s => [s.payment_id, s]));
    const open = p => p.amount == null ? null : Math.round((p.amount - (p.linked || 0)) * 100) / 100;
    const rows = pays.filter(p => all || ((p.direction === "in") === (line.amount > 0) && !(p.linked && p.amount && p.linked >= p.amount - 0.005)))
      .map(p => ({ p, open: open(p), sugg: sugg.get(p.id) || null, exact: open(p) != null && Math.abs(open(p) - amt) < 0.005 }))
      .filter(r => LT.match(`${r.p.description} ${LT.amount(r.p.amount)} ${LT.amount(r.open)} ${r.p.month}`, q));
    const off = r => r.open == null ? Infinity : Math.abs(r.open - amt);
    return rows.sort((a, b) => (b.sugg?.score ?? -1) - (a.sugg?.score ?? -1) || off(a) - off(b));
  },
  // Every word typed must be somewhere in the row's text, in any order, ignoring capitals.
  match(text, q) { const t = String(text ?? "").toLowerCase(); return String(q ?? "").toLowerCase().split(/\s+/).filter(Boolean).every(w => t.includes(w)); },
  // Sorted copy by key(row): type "num" compares as numbers, anything else (text, ISO dates) as lower-case text. Blanks go last either way.
  sort(rows, key, type, dir) {
    const val = r => { const v = key(r); return v == null || v === "" ? null : type === "num" ? Number(v) : String(v).toLowerCase(); };
    return rows.map((r, i) => [r, val(r), i]).sort((a, b) => {
      if (a[1] === null || b[1] === null) return a[1] === b[1] ? a[2] - b[2] : a[1] === null ? 1 : -1;
      const c = type === "num" ? a[1] - b[1] : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0;
      return c ? c * dir : a[2] - b[2];
    }).map(x => x[0]);
  },
  // An amount as it might be typed to find it: 1234.5 and 1,234.50 both match, with or without the sign the table shows (- or the minus sign, +).
  amount(n) { if (n == null || n === "") return ""; const v = Number(n), a = Math.abs(v), p = a.toFixed(2), q = a.toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `${p} ${q}` + (v < 0 ? ` -${p} -${q} −${p} −${q}` : v > 0 ? ` +${p} +${q}` : ""); },
  // An amount typed by a person, as a number, or null when it isn't a well-formed amount: digits with or without
  // thousands commas (1,234.50), at most 2 decimals, a minus or brackets for a negative. "25abc" or "1.2.3" give null.
  typedAmount(s) {
    const m = /^\s*(-|\(\s*)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?(\s*\))?\s*$/.exec(String(s ?? ""));
    if (!m || (m[1] || "").startsWith("(") !== !!m[4]) return null;
    const v = Number(m[2].replace(/,/g, "") + (m[3] || ""));
    return m[1] ? (v === 0 ? 0 : -v) : v;
  },
  // Bar length in pixels for a value on a scale that ends at max.
  bar(v, max, width) { return max > 0 && v > 0 ? Math.max(1, Math.round(v / max * width * 100) / 100) : 0; },
  // The lines of a budget (one currency) as chart rows: the biggest `top` by budget, the rest added up as 'Other lines'.
  chart(lines, top = 12) {
    const rows = lines.filter(x => x.amount != null || x.paid != null).map(x => ({ label: x.description || "(no description)", budget: x.amount || 0, paid: x.paid }));
    const big = LT.sort(rows, r => r.budget, "num", -1), keep = big.slice(0, top), rest = big.slice(top);
    if (rest.length) keep.push({ label: "Other lines", n: rest.length, budget: Math.round(rest.reduce((a, r) => a + r.budget, 0) * 100) / 100,
      paid: rest.some(r => r.paid != null) ? Math.round(rest.reduce((a, r) => a + (r.paid || 0), 0) * 100) / 100 : null });
    return keep;
  },
};
// LT-END

// What each flat list can be sorted by: list -> column -> [type, key of a row]. Rows are the server's plain objects.
const SORTS = {
  payees: { name: ["text", p => p.name], type: ["text", p => state.meta.categories[p.category] || p.category], when: ["num", p => p.month_offset * 32 + p.due_day],
    amount: ["num", p => p.amount], bank: ["text", p => p.bank_details || p.reference], status: ["text", p => p.active ? "Active" : "Stopped"] },
  bank: { date: ["text", l => l.txn_date], desc: ["text", l => l.description], amount: ["num", l => l.amount],
    by: ["text", l => l.payment_id ? l.payment_desc : l.status === "no_docs" ? "No documents needed" : "Not explained"] },
  sql: { doc: ["text", x => x.doc_no], date: ["text", x => x.doc_date], desc: ["text", x => x.description], amount: ["num", x => x.amount],
    pay: ["text", x => x.payment_desc] },
};
const LIST_REDRAW = {};  // list -> function that draws just that list again
function listState(id) {
  let st = state.lists[id];
  if (!st) {
    st = state.lists[id] = { q: "", col: null, dir: 1 };
    try { const [c, d] = (localStorage.getItem("hrp-sort-" + id) || "").split(":"); if (SORTS[id][c]) { st.col = c; st.dir = d === "-1" ? -1 : 1; } } catch {}
  }
  return st;
}
// A list's rows as shown: those the search finds (text(row): all the words of the row), in the sort picked, else in the order given.
function listRows(id, rows, text) {
  const st = listState(id), s = st.col && SORTS[id][st.col];
  const found = st.q.trim() ? rows.filter(r => LT.match(text(r), st.q)) : rows;
  return s ? LT.sort(found, s[1], s[0], st.dir) : found;
}
// A column heading that sorts: a button inside the th, with aria-sort on the th.
function sortTh(id, col, label, cls = "") {
  const st = listState(id), on = st.col === col;
  return `<th${cls ? ` class="${cls}"` : ""} aria-sort="${on ? (st.dir > 0 ? "ascending" : "descending") : "none"}"><button type="button" class="sorth" data-sort="${id}" data-col="${col}">${label}<span class="arrow" aria-hidden="true">${on ? (st.dir > 0 ? "▲" : "▼") : ""}</span></button></th>`;
}
function listBar(id, what) {
  return `<div class="listbar noprint"><input type="search" data-search="${id}" value="${esc(listState(id).q)}" placeholder="Search ${what}" aria-label="Search ${what}"><span class="muted" data-count="${id}" aria-live="polite"></span></div>`;
}
const setCount = (id, n, m) => { state.counts[id] = [n, m]; };
function paintCount(id) {
  const el = document.querySelector(`[data-count="${id}"]`), c = state.counts[id];
  if (el && c) el.textContent = `${c[0]} of ${c[1]} shown`;
}
// A click on a heading: first sorts up, again down, a third time goes back to the list's own order.
function sortClick(id, col, btn) {
  const all = [...document.querySelectorAll(`[data-sort="${id}"][data-col="${col}"]`)], at = Math.max(0, all.indexOf(btn));
  const st = listState(id);
  if (st.col !== col) { st.col = col; st.dir = 1; } else if (st.dir > 0) st.dir = -1; else { st.col = null; st.dir = 1; }
  try { if (st.col) localStorage.setItem("hrp-sort-" + id, `${st.col}:${st.dir}`); else localStorage.removeItem("hrp-sort-" + id); } catch {}
  LIST_REDRAW[id]?.();
  document.querySelectorAll(`[data-sort="${id}"][data-col="${col}"]`)[at]?.focus({ preventScroll: true });  // the header that was clicked, not the first table's
}

// Budget against paid, one pair of bars per line (RM lines only), drawn as SVG that takes its colours from the page's tokens.
function budgetChart(d) {
  const rows = LT.chart(d.lines.filter(x => x.currency === "MYR")), sums = d.sums.MYR;
  if (!rows.length || !sums) return "";
  const plain = n => money(n, "MYR"), W = 640, X0 = 190, BW = 290, RH = 36, TOP = 54;
  const max = Math.max(...rows.map(r => Math.max(r.budget, r.paid || 0)), sums.budget > 0 ? 0 : 1);
  const cut = (s, n) => s.length > n ? s.slice(0, n - 1) + "…" : s;
  const H = TOP + rows.length * RH + 6, diff = Math.round((sums.paid - sums.budget) * 100) / 100;
  const total = `Total: budget ${plain(sums.budget)}, paid ${plain(sums.paid)}` + (Math.abs(diff) <= 0.01 ? "" : diff < 0 ? `, ${plain(-diff)} under` : `, ${plain(diff)} over`);
  const label = `Budget against paid, RM lines. ${total}. ${rows.length} bar pairs, biggest budget first.`;
  const bars = rows.map((r, i) => {
    const y = TOP + i * RH, over = r.paid != null && r.paid - r.budget > 0.005, bw = LT.bar(r.budget, max, BW), pw = LT.bar(r.paid || 0, max, BW);
    const name = r.n ? `${r.label} (${r.n})` : r.label;
    return `<g><title>${esc(name)}: budget ${plain(r.budget)}, ${r.paid == null ? "not paid yet" : "paid " + plain(r.paid)}</title>
      <text class="lbl" x="${X0 - 8}" y="${y + 17}" text-anchor="end">${esc(cut(name, 25))}</text>
      <rect class="bg" x="${X0}" y="${y + 2}" width="${bw}" height="12"/><text class="val" x="${X0 + bw + 6}" y="${y + 12}">${plain(r.budget)}</text>
      <rect class="${over ? "pd over" : "pd"}" x="${X0}" y="${y + 17}" width="${pw}" height="12"/>
      <text class="val${over ? " over" : ""}" x="${X0 + pw + 6}" y="${y + 27}">${r.paid == null ? "not paid yet" : plain(r.paid) + (over ? " (over)" : "")}</text></g>`;
  }).join("");
  const more = d.lines.some(x => x.currency !== "MYR") ? " Lines in other currencies are in the table only." : "";
  return `<div class="card-in noprint"><div class="tbl-wrap"><svg class="bchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}" xmlns="http://www.w3.org/2000/svg">
    <title>${esc(label)}</title>
    <text class="tot" x="0" y="16">${esc(total)}</text>
    <rect class="bg" x="0" y="30" width="14" height="10"/><text class="lbl" x="20" y="39">Budget</text>
    <rect class="pd" x="80" y="30" width="14" height="10"/><text class="lbl" x="100" y="39">Paid</text>
    <rect class="pd over" x="150" y="30" width="14" height="10"/><text class="lbl" x="170" y="39">Paid, over budget</text>
    ${bars}</svg></div>${more ? `<div class="note">${more.trim()}</div>` : ""}</div>`;
}

function renderNav() {
  const btn = (v, label, on, extra = "") => `<button data-view="${v}"${extra} class="${on ? "on" : ""}">${icon(v)}<span>${label}</span></button>`;
  const items = [`<div class="group">Dashboard</div>`, btn("overview", "Overview", state.view === "overview"), `<div class="group">Companies</div>`];
  // Stopped companies stay in the records (history needs them) but not in the sidebar.
  for (const e of state.meta.entities.filter(isActive))
    items.push(btn("entity", `${esc(e.code)} <small>${esc(e.short_name || e.name.replace(/ (Sdn Bhd|Ltd)$/i, ""))}</small>`, state.view === "entity" && state.entity === e.id, ` data-entity="${e.id}"`));
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
    : state.view === "setup" ? `Setup${setupSpec() ? " › " + sectionLabel(setupSpec()) : ""}`
    : g ? `${g[0]} › ${g[1].find(v => v[0] === state.view)[1]}` : "";
}

function go(view, entity) {
  if (!closeDrawer()) return;
  state.view = view; state.bankOnly = false; state.recon.rv = null; for (const k in state.lists) state.lists[k].q = ""; if (entity) state.entity = +entity;
  if (!state.entity) state.entity = firstEntityId();
  if (view === "setup") state.setup.id = null;  // the section stays, so Setup opens where it was left
  state.payeeSaved = null;
  renderNav(); render();
}

async function render() {
  const main = $("#main");
  if (dayKey() !== state.day) await newDay();
  try {
    if (state.view === "overview") await viewOverview(main);
    else if (state.view === "entity") await viewEntity(main);
    else if (state.view === "budget") await viewBudget(main);
    else if (state.view === "payroll") await viewPayroll(main);
    else if (state.view === "bank") await viewBank(main);
    else if (state.view === "sql") await viewSql(main);
    else if (state.view === "books") await viewBooks(main);
    else if (state.view === "payees") await viewPayees(main);
    else if (state.view === "audit") await viewAudit(main);
    else if (state.view === "settings") await viewSettings(main);
    else if (state.view === "trail") await viewTrail(main);
    else if (state.view === "setup") await viewSetup(main);
    if (state.view === "overview") trailNotice();
  } catch (e) { main.innerHTML = `<div class="card"><b>Couldn't load this page.</b><div class="note">${esc(e.message)}</div></div>`; }
}

function entityPicker() {
  return `<div class="row noprint">${state.meta.entities.filter(e => isActive(e) || e.id === state.entity).map(e => `<button class="${e.id === state.entity ? "btn" : "ghost"} small" data-pick-entity="${e.id}">${esc(e.name)}</button>`).join("")}</div>`;
}
const ent = () => state.meta.entities.find(e => e.id === state.entity);
// A company or bank account is in use unless it was stopped (active 0); one from before Setup has no flag and is in use.
const isActive = x => x.active == null || !!+x.active;
const firstEntityId = () => (state.meta.entities.find(isActive) || state.meta.entities[0])?.id ?? null;
// The accounts to choose from: those in use, and the one already chosen even if it was stopped since.
const pickAccounts = (e, keep) => (e?.accounts || []).filter(a => isActive(a) || a.id === keep);
// A company's usual account: its cash book, else its first account in use.
const defaultAccount = e => { const live = (e?.accounts || []).filter(isActive); return live.find(a => +a.cash_book) || live[0] || e?.accounts?.[0] || null; };
const acctOption = (a, sel, number) => `<option value="${a.id}" ${a.id === sel ? "selected" : ""}>${esc(a.label)}${number && a.number ? " · " + esc(a.number) : ""}${isActive(a) ? "" : " (stopped)"}</option>`;
// Customers and suppliers (state.meta.parties; none on a server without them). A party of entity_id null is every company's.
const PARTY_KIND = { customer: "Customer", supplier: "Supplier", related: "Related company", statutory: "Statutory body" };
const partyById = id => id == null || id === "" ? null : (state.meta.parties || []).find(x => x.id === +id) || null;
// Money out may go to a supplier, money in come from a customer; a related company or a statutory body either way.
const partyFits = (pt, dir) => pt.kind === "related" || pt.kind === "statutory" || pt.kind === (dir === "in" ? "customer" : "supplier");
// A recurring payment of these types is paid to a person, never to a supplier or customer.
const PERSONAL_TYPES = ["salary", "director"];
// The parties a company's recurring payment going this way can be linked to: its own and every company's, in use, of a
// kind that fits; and the one already linked (linked) even when stopped. sel: the one chosen.
function partyOptions(e, dir, sel, linked) {
  const list = (state.meta.parties || []).filter(pt => (pt.entity_id == null || pt.entity_id === e?.id) && partyFits(pt, dir) && (isActive(pt) || pt.id === linked));
  return `<option value="">None</option>` + list.map(pt => `<option value="${pt.id}" ${pt.id === sel ? "selected" : ""}>${esc(pt.name)}${pt.sql_code ? " · " + esc(pt.sql_code) : ""}${isActive(pt) ? "" : " (stopped)"}</option>`).join("");
}
// A month is set up (its checklist and recurring payments added) when you ask, or for the current cycle on loading.
// One not set up can still hold payments (from an SQL voucher or a bank line), which are shown below this card.
// A month before the company's first month tracked (none when it has no first month): its pill is grey, never red,
// overdue or green, as nothing in it is tracked here.
const beforeTracking = (e, month) => !!(e?.first_month && month < e.first_month);
const BEFORE_PILL = `<span class="pill grey">Before tracking</span>`;
const notSetUp = (e, month, held) => `<div class="card noprint"><h2>${esc(monthName(month))} isn't set up yet${beforeTracking(e, month) ? ` ${BEFORE_PILL}` : ""}</h2>
  <div class="note">${held ? `It already holds ${held} payment${held > 1 ? "s" : ""}, shown below. ` : ""}Setting it up adds ${esc(e.code)}'s checklist and recurring payments for the month.${e.first_month && month < e.first_month
    ? ` It is before the first month tracked in this app (${esc(monthName(e.first_month))}).` : ""}</div>
  <div class="row"><button class="btn" data-open-month="${e.id}">Set up this month</button></div></div>`;

