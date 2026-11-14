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
// Document types: in use (not stopped), and kept in SQL Account (from_sql). A server without doc_info: all in use, sql_only.
const docInfo = k => state.meta.doc_info?.[k] || null;
const docActive = k => docInfo(k)?.active == null || !!+docInfo(k).active;
const docFromSql = k => docInfo(k) ? !!+docInfo(k).from_sql : (state.meta.sql_only || []).includes(k);
// Payment types: the way the money goes (in or out) and whether they are in use (meta.category_info; a server without it:
// Money received is money in, every other type money out).
const catInfo = k => state.meta.category_info?.[k] || {};
const catDir = k => catInfo(k).direction || (k === "receipt" ? "in" : "out");
const catActive = k => catInfo(k).active == null || !!+catInfo(k).active;
// The type a new payment going this way starts on: money in, Money received; money out, Other, or with setting the type
// General settings gives new recurring payments. Failing those, the first type in use going that way.
function defaultType(dir, setting) {
  const cats = state.meta.categories || {}, ok = k => k && k in cats && catActive(k) && catDir(k) === dir;
  const want = dir === "in" ? ["receipt"] : [setting ? state.meta.settings?.payee_default_category : null, "other"];
  return want.find(ok) || Object.keys(cats).find(ok) || (dir === "in" ? "receipt" : "other");
}
// A one-off payment added by hand starts as a claim (when claims are in use), else as defaultType gives.
const oneOffType = () => catActive("claim") && catDir("claim") === "out" ? "claim" : defaultType("out");
// A payment type picker's options: the types in use going this way (any way without dir), and sel and keep (the record's
// own type) even when stopped, so a record keeps its type until it is changed.
function typeOptions(sel, dir, keep) {
  const cats = state.meta.categories || {};
  const keys = Object.keys(cats).filter(k => k === sel || (catActive(k) || k === keep) && (!dir || catDir(k) === dir));
  if (sel && !keys.includes(sel)) keys.push(sel);
  return keys.map(k => `<option value="${esc(k)}" ${k === sel ? "selected" : ""}>${esc(cats[k] || k)}${catActive(k) ? "" : " (stopped)"}</option>`).join("");
}
// A type picker beside a money in / money out picker: choosing a direction offers only the types going that way (the one
// chosen stays if it goes that way too, else the default); choosing a type sets the direction to the type's. then(): after
// either changes. setting and keep as for defaultType and typeOptions.
function pairTypeDir(catSel, dirSel, { setting = false, keep = null, then = () => {} } = {}) {
  const fill = sel => { catSel.innerHTML = typeOptions(sel, dirSel.value, keep); };
  dirSel.onchange = () => {
    const dir = dirSel.value, cur = catSel.value;
    fill(cur && catDir(cur) === dir ? cur : keep && catDir(keep) === dir ? keep : defaultType(dir, setting)); then();
  };
  catSel.onchange = () => {
    const d = catDir(catSel.value);
    if (d !== dirSel.value) { dirSel.value = d; fill(catSel.value); }
    then();
  };
  return fill;
}
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
// A payment's status in the month table. Money received says Received <date> (with the documents still missing), Part
// received, or while it is not in the server's word for why (Not received yet, Waiting for Nov statement...).
function statusPill(p) {
  if (p.status === "planned") return flagPill(p.flag);
  if (p.direction !== "in") return p.status === "complete" ? `<span class="pill ok">Complete</span>` : p.status === "paid" ? `<span class="pill warn">Paid · ${p.missing.length} doc${p.missing.length > 1 ? "s" : ""} missing</span>` :
    `<span class="pill warn">Part paid · ${foundOf(p)}</span>`;
  const day = p.paid_date ? ` ${shortDate(p.paid_date)}` : "";
  return p.status === "complete" ? `<span class="pill ok">Received${day}</span>` : p.status === "part_paid" ? `<span class="pill warn">Part received · ${foundOf(p)}</span>` :
    `<span class="pill warn">Received${day} · ${p.missing.length} doc${p.missing.length > 1 ? "s" : ""} missing</span>`;
}
// A required document SQL or the bank statement already shows, e.g. "PV2601-020 (print from SQL)": no upload needed.
const evidenceChip = ev => `<span class="chip have ev" title="${esc(ev.text)}. No upload needed; you can still add a copy.">✓ ${esc(ev.text)}</span>`;
// A required document's chip on a payment row: · missing (with why what SQL has doesn't count, e.g. an e-Invoice taken
// back), ✓ uploaded, or ✓ what already shows it.
function docChip(p, dt) {
  const why = p.not_counted[dt];
  if (p.missing.includes(dt)) return `<span class="chip need"${why ? ` title="${esc(why.hint)}"` : ""}>· ${esc(dt.toUpperCase())}</span>`;
  return p.evidence[dt] && !p.documents.some(x => x.doc_type === dt) ? evidenceChip(p.evidence[dt]) : `<span class="chip have">✓ ${esc(dt.toUpperCase())}</span>`;
}

// Payroll cycle: until the rollover day (General settings, the 10th unless changed) you're still closing last month's
// cycle. Of today, or of the day given (a date).
function currentCycle(t = new Date()) {
  const r = Number(state.meta?.settings?.cycle_rollover_day ?? 10), roll = r >= 1 && r <= 31 ? r : 10;
  const d = new Date(t.getFullYear(), t.getMonth() - (t.getDate() <= roll ? 1 : 0), 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// Today is worked out when it is wanted, never kept: the day the page was last drawn is state.day.
const dayKey = () => { const t = new Date(); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`; };

// month and day are set in start(), once the settings (the rollover day) are loaded.
const state = { meta: null, view: "overview", entity: null, month: null, day: null, data: null, openPayment: null, sqlOpen: {}, sqlPaste: {},
  nextAll: {}, bankOnly: false, lists: {}, counts: {}, recon: { entity: null, account: null, year: null, open: null, panel: null, rv: null },
  trail: { f: {}, entries: [], more: false, labels: null, show: false },
  setup: { kind: null, id: null, types: null, stopped: false, deleted: false, view: {}, closed: {}, drawer: null, reqScope: null, req: null, reqOpen: null, chk: null, chkOpen: null, rem: null, remOpen: null, paste: null } };
// Sidebar sections; companies are listed between Dashboard and Monthly work.
const VIEWS = [["Monthly work", [["budget", "Budget"], ["bank", "Bank statements"], ["sql", "SQL import"], ["payees", "Recurring"]]],
  ["Filing", [["audit", "Audit pack"], ["trail", "Audit trail"], ["settings", "Backup"]]],
  ["Setup", [["setup", "Setup"]]]];
const ICON = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  entity: '<path d="M4 21V5l8-3v19M12 9h8v12M8 8h.01M8 12h.01M8 16h.01M16 13h.01M16 17h.01M2 21h20"/>',
  budget: '<path d="M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12M16 14h.01"/>',
  bank: '<path d="M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M2 21h20M12 3l9 5H3z"/>',
  sql: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  payees: '<path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/>',
  audit: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 15l2 2 4-4"/>',
  settings: '<path d="M3 4h18v4H3zM5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/>',
  trail: '<path d="M12 3l8 3v6c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V6zM9 12l2 2 4-4"/>',
  setup: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
};
const icon = v => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[v]}</svg>`;

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
    else if (state.view === "bank") await viewBank(main);
    else if (state.view === "sql") await viewSql(main);
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
  part_paid: { pay: p => p.direction !== "in" && p.status === "part_paid" },
  "in-part_paid": { pay: p => p.direction === "in" && p.status === "part_paid" },
};
// A count of money received has in- in front of its word, so it marks the receipts alone.
const markFor = key => MARKS[key] || (key.startsWith("in-") ? { pay: p => p.direction === "in" && p.flag?.code === key.slice(3) }
  : { pay: p => p.direction !== "in" && p.flag?.code === key });

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
    <div class="row next-act">${r.rule === 13 ? `<button class="btn small" data-next-backup="1">Open backup</button>` : ""}
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
    // The bar counts payments out; money received has its own figure beside it.
    const outAll = x.payments - x.receipts.payments, outDone = x.complete - x.receipts.complete;
    const pct = outAll ? Math.round(outDone / outAll * 100) : 0;
    // Each count is a button to what it counts (pillGo).
    const flags = [], count = (kind, tone, text) => flags.push(`<button class="pillbtn" data-pill="${kind}" data-entity="${x.entity.id}" title="Show these"><span class="pill ${tone}">${text}</span></button>`);
    if (x.overdue_tasks) count("overdue_tasks", "bad", `${x.overdue_tasks} checklist overdue`);
    if (x.due_today_tasks) count("due_today_tasks", "warn", `${x.due_today_tasks} checklist due today`);
    for (const f of x.payment_flags) count(f.way === "in" ? `in-${f.code}` : f.code, f.tone, `${f.n} ${f.way === "in" ? "receipt" : "payment"}${f.n > 1 ? "s" : ""} ${esc(lowerFirst(f.text))}`);
    if (x.part_paid) count("part_paid", "warn", `${x.part_paid} part paid`);
    if (x.receipts.part_paid) count("in-part_paid", "warn", `${x.receipts.part_paid} part received`);
    if (x.paid_missing) count("paid_missing", "warn", `${x.paid_missing} paid, documents missing`);
    if (x.receipts.paid_missing) count("paid_missing", "warn", `${x.receipts.paid_missing} received, documents missing`);
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
        <div class="stat"><b>${outDone}/${outAll}</b><span>payments fully documented</span></div>
        ${x.receipts.payments ? `<div class="stat"><b>${x.receipts.complete}/${x.receipts.payments}</b><span>receipts fully documented</span></div>` : ""}
        <div class="stat"><b>${x.planned - x.receipts.planned}</b><span>not paid yet</span></div>
        ${x.receipts.payments ? `<div class="stat"><b>${x.receipts.planned}</b><span>not received yet</span></div>` : ""}
        ${budget("MYR", x.budget.MYR || 0)}${Object.entries(x.budget).filter(([cur]) => cur !== "MYR").map(([cur, n]) => budget(cur, n)).join("")}
      </div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="row">${flags.join("")}</div>
    </div>`;
  }).join("");
  main.innerHTML = `
    <div id="nextUp">${nextCard(next, null)}</div>
    <div><div class="eyebrow">Payroll month</div><h1>${esc(ov.label)} cycle</h1>
    <div class="note">Covers the payroll month's checklist and payments, including the bills and statutory payments paid early in the next month. Each item's due date is set in Setup › Monthly checklist.</div></div>
    <div class="grid2">${cards}</div>
    <div class="card"><h2>How a payment is completed</h2>
      <div class="row"><span class="pill grey">Not paid</span> → <span class="pill warn">Paid, documents missing</span> → <span class="pill ok">Complete</span></div>
      <div class="note">A payment becomes <b>Paid</b> when you enter the paid date or its bank statement line is matched. It becomes <b>Complete</b> when every required document is uploaded, or already shown by a linked SQL voucher, a validated e-Invoice or its bank statement line. Only complete payments are ready to file.</div>
      <div class="note">Past its due date and not paid yet, a payment says why: <b>Not on Oct statement</b> (or the month it fell due in) once that month's bank statement is imported without it; until then <b>Waiting for SQL record</b> while SQL isn't imported up to its due date, or else <b>Waiting for Oct statement</b>. A statutory payment not paid by the 15th of the next month shows <b>Past legal deadline</b>.</div>
      <div class="note">If the bank lines matched add up to less than the amount, it shows <b>Part paid</b> until the rest is matched, or you note why in the payment (e.g. balance paid in October).</div>
      <div class="note">Money received (a tenant's rent, say) is set up on the Recurring page as <b>Money in</b>. It shows <b>Not received yet</b> until it is due, then <b>Waiting for Nov statement</b> or <b>Not on Nov statement</b> in the same way, and <b>Received 14 Nov</b> once a bank credit is matched or you enter the date. It is counted apart from the payments, and is never in the Budget.</div>
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
    <div class="row spread"><div><div class="eyebrow">${esc(d.entity.code)}</div><h1>${esc(d.entity.name)} · ${esc(d.label)}</h1></div>
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
const drawerDirty = () => !$("#drawer").hidden && (Object.keys(unsavedEdits()).length > 0 || !!state.drawerDirty?.() || reasonTyped());
const mayLeave = () => !drawerDirty() || confirm("Discard your changes?");

// False when you choose to keep changes not saved yet; force closes it anyway (the payment was removed).
function closeDrawer(force) {
  if (!force && !mayLeave()) return false;
  $("#drawer").hidden = true; state.openPayment = null; state.drawerDirty = null; state.drawerAt = null; state.why = null;
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
// The year view of one account (a row per month), a month's panel opened in place, and the review of a statement's lines.
// What matches, what is in the books and whether a month can be signed off is worked out by the server (hrp/recon.py);
// nothing here posts anything to SQL Account.
const RC_PILL = { to_import: "grey", to_review: "warn", difference: "bad", reconciled: "ok" };
const rcPill = (status, text) => `<span class="pill ${RC_PILL[status] || "grey"}">${esc(text)}</span>`;
const rcUrl = (what, extra = "") => `/api/recon/${what}?entity_id=${state.entity}${extra}`;
const signedAmt = (n, cur) => `${n < 0 ? "−" : "+"}${money(Math.abs(n), cur).replace(/^\S+ /, "")}`;
const dayCount = n => `${n} day${n === 1 ? "" : "s"}`;
const bankText = (l, cur) => [fmtDate(l.txn_date), l.txn_date, l.description, LT.amount(l.amount), cur, l.payment_desc, l.note, l.status === "no_docs" ? "no documents needed" : l.payment_id ? "" : "not explained"].join(" ");

// The books' side of a month as one cell: the balance, or why there is none.
const bookCell = (b, cur) => b.closing != null ? money(b.closing, cur) : `<span class="muted">${esc(b.note || "—")}</span>`;

// Sign-off controls for a month (s: the month's summary), the same in its panel and at the foot of its review.
function signBlock(s) {
  if (!s.statement) return "";
  const id = s.statement.id;
  if (s.reconciled_at) {
    return `<div class="rc-sign"><span class="pill ok">Reconciled ${fmtDate(s.reconciled_at)}${s.reconciled_how === "before tracking" ? " · before tracking" : ""}</span>
      ${s.reconciled_note ? `<span class="note">${esc(s.reconciled_note)}</span>` : ""}
      <button class="ghost small" data-rc-undo="${id}">Undo sign-off</button></div>`;
  }
  const why = s.why_not.length ? `<div class="note">Not ready: ${esc(s.why_not.join("; "))}.</div>` : "";
  const before = s.before_tracking ? `<div class="rc-before"><div class="note">This month is before tracking began here. If it was reconciled outside this app, say so.</div>
      <label class="field"><span>How it was reconciled${s.book_matches ? " (optional: the books agree with the bank)" : ""}</span><input data-rc-note="${id}" maxlength="200" placeholder="e.g. reconciled in SQL Account in August"></label>
      <label class="row"><input type="checkbox" data-rc-before-tick="${id}"> This month was reconciled before tracking began</label>
      <button class="ghost" data-rc-before="${id}" ${s.can_sign_before_tracking ? "" : "disabled"}>Reconciled before tracking</button>
      ${s.can_sign_before_tracking ? "" : `<div class="note">The statement has to add up first.</div>`}</div>` : "";
  return `<div class="rc-sign"><button class="btn" data-rc-sign="${id}" ${s.can_sign ? "" : "disabled"}>Mark reconciled</button>${why}</div>${before}`;
}

function rcTable(title, rows, cur) {
  if (!rows.length) return "";
  return `<div class="tbl-wrap"><h3>${esc(title)} · ${rows.length}</h3><table><thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Why</th></tr></thead><tbody>
    ${rows.map(x => `<tr><td class="mono">${shortDate(x.date)}</td><td class="line-desc">${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc((x.description || "").replaceAll(" | ", " · "))}</td>
      <td class="num">${signedAmt(x.amount, cur)}</td><td class="note">${esc(x.why)}</td></tr>`).join("")}</tbody></table></div>`;
}

function monthPanel(s) {
  const cur = s.account.currency, st = s.statement, rc = s.reconciliation, c = s.lines;
  if (!st) return `<div class="rc-panel"><div class="note">The ${esc(s.label)} statement for ${esc(s.account.label)} isn't imported yet. Import it above.</div>
    <div class="stats"><div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div></div></div>`;
  const diff = s.difference;
  const parts = !rc ? [] : [
    rc.brought_forward ? `${money(rc.brought_forward, cur)} brought forward from last month (bank opening less book opening)` : "",
    rc.books_out ? `${money(rc.books_out, cur)} paid out in the books, not on the statement` : "",
    rc.books_in ? `${money(-rc.books_in, cur)} received in the books, not on the statement` : "",
    rc.bank_net ? `${money(rc.bank_net, cur)} net on the statement, not in the books` : "",
    rc.differ ? `${money(rc.differ, cur)} from matched amounts that differ` : "",
    rc.other ? `${money(rc.other, cur)} not explained by any of these` : ""].filter(Boolean);
  const gone = s.left_out.journals || s.left_out.invoices, unk = s.left_out.unknown;
  return `<div class="rc-panel">
    <div class="stats">
      <div class="stat"><b>${money(st.money_in, cur)}</b><span>Money in</span></div>
      <div class="stat"><b>${money(st.money_out, cur)}</b><span>Money out</span></div>
      <div class="stat"><b>${money(st.closing, cur)}</b><span>Bank closing</span></div>
      <div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div>
      <div class="stat"><b class="${diff == null ? "" : Math.abs(diff) < 0.005 ? "recv" : "bad-text"}">${diff == null ? "—" : money(diff, cur)}</b><span>Difference (bank less books)</span></div>
    </div>
    <div class="row spread"><div>Lines: <b>${c.matched}</b> matched · <b>${c.confirmed}</b> confirmed · <b>${c.to_explain}</b> to explain
      ${st.adds_up ? "" : `<span class="pill bad">Statement doesn't add up</span>`}</div>
      <div class="row">${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank">Statement PDF</a>` : ""}
      <button class="btn small" data-rc-review="${st.id}">Review lines</button></div></div>
    <h3>Reconciliation statement</h3>
    ${s.book.state !== "ok" ? `<div class="note">${esc(s.book.note)}${s.book.note === "Needs book opening" ? ": type this account's book balance under Book opening below." : ": paste the cash book listing for that month on the SQL import page."}</div>` : ""}
    ${diff != null && Math.abs(diff) >= 0.005 ? `<div class="note">The books are ${money(Math.abs(diff), cur)} ${diff > 0 ? "below" : "above"} the bank.${parts.length ? " That is: " + esc(parts.join("; ")) + "." : ""}</div>` : ""}
    ${rcTable("In the books, not on this statement", s.books_only, cur)}${rcTable("On the statement, not in the books", s.bank_only, cur)}
    ${s.differ.length ? `<div class="tbl-wrap"><h3>Matched, but the amounts differ · ${s.differ.length}</h3><table><thead><tr><th>Payment</th><th class="num">Books</th><th class="num">Statement</th><th class="num">Difference</th></tr></thead><tbody>
      ${s.differ.map(x => `<tr><td>${x.ref ? `<b>${esc(x.ref)}</b> ` : ""}${esc(x.description)}</td><td class="num">${money(x.book, cur)}</td><td class="num">${money(x.bank, cur)}</td><td class="num">${money(x.amount, cur)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    ${!s.books_only.length && !s.bank_only.length && !s.differ.length && s.book.state === "ok" ? `<div class="note">Everything on the statement is in the books, and the other way round.</div>` : ""}
    ${gone ? `<div class="note">Not counted as bank movements: ${s.left_out.journals} journal${s.left_out.journals === 1 ? "" : "s"} and ${s.left_out.invoices} customer invoice${s.left_out.invoices === 1 ? "" : "s"} (customer refunds included) in the SQL listing. Fetch SQL's GL Journal of Transaction to count a journal that moves the bank.</div>` : ""}
    ${unk ? `<div class="note">Not counted: ${unk} cash book entr${unk === 1 ? "y" : "ies"} with no money in or out shown, so the books may differ by that amount.</div>` : ""}
    ${s.uses_sql ? `<div class="note">Paste only the bank's cash book listing for reconciliation: a voucher paid from petty cash or a card would count as a bank movement.</div>` : ""}
    ${signBlock(s)}
    <div class="note">Marking a month reconciled is a record kept in this app. Nothing is posted to SQL Account.</div></div>`;
}

async function viewBank(main) {
  const e = ent(), R = state.recon;
  if (R.entity !== state.entity) Object.assign(R, { entity: state.entity, account: null, year: null, open: null, panel: null, rv: null });
  // Opened from Before you print or Next up: that account is shown, and with lines to explain its review opens.
  const focus = state.focusBank; state.focusBank = null;
  if (focus?.account && e.accounts.some(a => a.id === focus.account)) { if (R.account !== focus.account) R.rv = null; R.account = focus.account; }
  if (!e.accounts.some(a => a.id === R.account)) R.account = defaultAccount(e)?.id;
  if (focus && state.month) R.year = state.month.slice(0, 4);
  const acctOpts = pickAccounts(e, R.account).map(a => acctOption(a, R.account, true)).join("");
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>Bank statements</h1>
      <div class="note">Import each month's Maybank statement PDF. Every line is matched to a payment automatically where the payee and amount agree (split DuitNow transfers are added together). Then review the month: confirm what was matched, explain the rest, and mark the month reconciled once the books agree with the bank.</div>
      <form class="row" id="stmtForm"><label class="field"><span>Account</span><select id="stmtAcct">${acctOpts}</select></label>
      <label class="field"><span>Statement PDF</span><input id="stmtFile" type="file" accept=".pdf"></label>
      <button class="btn" type="submit" style="align-self:end">Import statement</button>
      <button class="ghost" type="button" id="rematch" style="align-self:end">Match again</button></form></div>
    <div id="stmtList"></div>`;
  await drawRecon(focus);
}

async function drawRecon(focus) {
  const R = state.recon, box = $("#stmtList");
  if (!box) return;
  if (R.rv) return reloadReview(false);
  const e = ent();
  const y = await api(rcUrl("year", `&account_id=${R.account}${R.year ? `&year=${R.year}` : ""}`));
  R.year = y.year; R.data = y;
  if (focus) {
    const row = y.rows.find(r => r.month === state.month && r.statement_id);
    if (row && state.bankOnly) return openReview(row.statement_id, false);  // the page is at the top already
    if (row) R.open = row.month;
  }
  R.panel = R.open && y.rows.some(r => r.month === R.open) ? await api(rcUrl("month", `&account_id=${R.account}&month=${R.open}`)) : null;
  const cur = y.account.currency;
  const rowHtml = r => `<tr class="${R.open === r.month ? "focus" : ""}"><td><button class="link" data-rc-open="${r.month}" aria-expanded="${R.open === r.month}">${esc(r.label)}</button></td>
      <td>${rcPill(r.status, r.status_text)}</td>
      <td class="num">${r.bank_closing != null ? money(r.bank_closing, cur) : "—"}</td><td class="num">${bookCell({ closing: r.book_closing, note: r.book_note }, cur)}</td>
      <td>${r.reconciled_at ? fmtDate(r.reconciled_at) + (r.reconciled_how === "before tracking" ? ` <span class="muted">· before tracking</span>` : "") : "—"}</td>
      <td class="noprint">${r.document_id ? `<a href="/api/documents/${r.document_id}/file" target="_blank">PDF</a>` : "—"}</td></tr>
      ${R.open === r.month && R.panel ? `<tr class="panelrow"><td colspan="6">${monthPanel(R.panel)}</td></tr>` : ""}`;
  const openings = y.openings.map(o => `${monthName(o.month)}: ${money(o.amount, cur)}`).join(" · ");
  const firstMonth = y.openings[0]?.month || y.rows.filter(r => r.statement_id).map(r => r.month).sort()[0] || y.rows.map(r => r.month).sort()[0] || "";
  box.innerHTML = `<div class="card">
      <div class="row spread"><div><div class="eyebrow">${esc(e.name)}</div><h2>${esc(y.account.label)} · ${esc(y.year)}</h2></div>
      <div class="row noprint">${pickAccounts(e, R.account).length > 1 ? pickAccounts(e, R.account).map(a => `<button class="${a.id === R.account ? "btn" : "ghost"} small" data-rc-acct="${a.id}">${esc(a.label)}</button>`).join("") : ""}
      ${y.years.length > 1 ? y.years.map(yr => `<button class="${yr === y.year ? "btn" : "ghost"} small" data-rc-year="${yr}">${esc(yr)}</button>`).join("") : ""}</div></div>
      <div class="note">Click a month for its summary. Book closing comes from ${esc(y.source)}.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Month</th><th>Status</th><th class="num">Bank closing</th><th class="num">Book closing</th><th>Reconciled on</th><th class="noprint">Statement</th></tr></thead><tbody>
      ${y.rows.map(rowHtml).join("") || `<tr><td colspan="6" class="empty">No months to show for ${esc(y.year)}.</td></tr>`}</tbody></table></div></div>
    <div class="card noprint"><h2>Book opening</h2>
      <div class="note">The balance ${esc(y.account.label)} had in your books on the first day of its first month here${e.uses_sql ? " (your SQL Account bank balance)" : ""}. Type it once; each later month carries on from the month before. ${openings ? `Set so far: ${esc(openings)}.` : "None set yet, so book closing shows Needs book opening."}</div>
      <form class="row" id="openingForm"><label class="field"><span>Month it applies to</span><input id="openMonth" type="month" required value="${esc(firstMonth)}"></label>
      <label class="field"><span>Book balance (${esc(cur)})</span><input id="openAmount" inputmode="decimal" required placeholder="e.g. 25,367.58"></label>
      <button class="btn" type="submit" style="align-self:end">Save book opening</button></form></div>`;
}

/* ---- the review of one statement ---- */
const RV = () => state.recon.rv;

async function openReview(sid, scroll = true) {
  const d = await api(rcUrl("review", `&statement_id=${sid}`));
  const V = state.recon.rv = { sid, d, sel: {}, choice: {}, keep: {}, checked: false, showMatched: false };
  for (const l of d.lines) if (l.state === "open" && l.suggestions.length) V.choice[l.id] = "p:" + l.suggestions[0].payment_id;
  drawReview();
  if (scroll) $("#stmtList")?.scrollIntoView?.({ block: "start" });  // the review replaces the year view, lower on the page
}

// reset false (the page redrew after a one-line action): the rows chosen, their date ticks, the check tick and the
// descriptions typed stay for lines that are as they were.
async function reloadReview(reset = true) {
  const V = RV(), d = await api(rcUrl("review", `&statement_id=${V.sid}`));
  const typed = [...document.querySelectorAll("[data-rv-desc],[data-rv-cat],[data-rv-note]")].map(el => [el.matches("[data-rv-desc]") ? "desc" : el.matches("[data-rv-cat]") ? "cat" : "note", el.dataset.rvDesc || el.dataset.rvCat || el.dataset.rvNote, el.value]);
  const was = Object.fromEntries(V.d.lines.map(l => [l.id, l.state + ":" + l.payment?.id]));
  if (reset) { V.sel = {}; V.keep = {}; V.checked = false; }
  else for (const l of d.lines) if (was[l.id] !== l.state + ":" + l.payment?.id) { delete V.sel[l.id]; delete V.keep[l.id]; delete V.choice[l.id]; }
  V.d = d;
  for (const l of d.lines) {
    if (l.state !== "open") delete V.choice[l.id];
    else if (!V.choice[l.id] && l.suggestions.length) V.choice[l.id] = "p:" + l.suggestions[0].payment_id;
  }
  drawReview();
  if (!reset) for (const [k, id, v] of typed) { const el = document.querySelector(`[data-rv-${k}="${id}"]`); if (el) el.value = v; }
}

// How far the bank date of a line is from the date the books hold for the payment p: {days, date, kind}, or null.
function rvGap(line, p) {
  if (!p) return null;
  const dates = p.voucher_dates?.length ? p.voucher_dates : p.typed_date ? [p.typed_date] : [];
  if (!dates.length) return null;
  const t = Date.parse(line.txn_date);
  const best = dates.map(x => ({ date: x, days: Math.abs(Math.round((Date.parse(x) - t) / 864e5)) })).sort((a, b) => a.days - b.days)[0];
  return best.days ? { ...best, kind: p.voucher_dates?.length ? "voucher" : "payment" } : null;
}
const rvPay = id => RV().d.payments.find(p => p.id === id);
// The date difference a row must have ticked before it can be applied: {days, date, kind} or null.
function rvNeedsTick(l) {
  const V = RV();
  if (l.state !== "open") return l.gap_days ? { days: l.gap_days, date: l.book_date, kind: l.book_date_kind } : null;
  const ch = V.choice[l.id];
  return ch?.startsWith("p:") ? rvGap(l, rvPay(+ch.slice(2))) : null;
}

function rvPayOption(p, sel, why) {
  return `<option value="p:${p.id}" ${sel === "p:" + p.id ? "selected" : ""}>${esc(p.description)} · ${p.direction === "in" ? "+" : ""}${money(p.amount, p.currency)} (${esc(monthName(p.month))})${why ? " · " + esc(why) : ""}${p.linked ? " · already linked " + money(p.linked, p.currency) : ""}</option>`;
}

function rvMine(l) {
  const V = RV();
  if (l.state !== "open") {
    const v = l.vouchers.map(x => `<span class="chip">${esc(x.doc_no)} · ${shortDate(x.doc_date)}</span>`).join(" ");
    return `<div class="rv-what">${l.payment ? `<b>${esc(l.payment.description)}</b> <span class="muted">${l.payment.direction === "in" ? "+" : ""}${money(l.payment.amount, l.payment.currency)} · ${esc(monthName(l.payment.month))}</span>`
      : `<b>No documents needed</b>${l.note ? ` <span class="muted">${esc(l.note)}</span>` : ""}`}</div>
      <div class="row" style="gap:6px">${v}${l.confirmed_at ? `<span class="pill ok">Confirmed ${shortDate(l.confirmed_at)}</span>` : `<span class="pill warn">Matched, not confirmed</span>`}
      <button class="ghost small" data-unlink="${l.id}">Undo</button></div>`;
  }
  const ch = V.choice[l.id] || "";
  const sugg = l.suggestions.map(x => ({ p: rvPay(x.payment_id), why: x.reason })).filter(x => x.p);
  const used = new Set(sugg.map(x => x.p.id));
  const others = V.d.payments.filter(p => !used.has(p.id) && (p.direction === "in") === (l.amount > 0) && !(p.linked && p.amount && p.linked >= p.amount - 0.005));
  const opts = `<option value="">Choose what this is…</option>
    ${sugg.length ? `<optgroup label="Suggested">${sugg.map(x => rvPayOption(x.p, ch, x.why)).join("")}</optgroup>` : ""}
    ${others.length ? `<optgroup label="Open payments">${others.map(p => rvPayOption(p, ch)).join("")}</optgroup>` : ""}
    <option value="c" ${ch === "c" ? "selected" : ""}>Create a payment for this line</option>
    <option value="n" ${ch === "n" ? "selected" : ""}>No documents needed (bank charge)</option>`;
  // Only the types going the line's way: Money received for money in, Other for money out unless changed.
  const dir = l.amount > 0 ? "in" : "out";
  const extra = ch === "c" ? `<input data-rv-desc="${l.id}" maxlength="120" placeholder="What was this payment for?" aria-label="Description of the payment to create">
      <select data-rv-cat="${l.id}" aria-label="Type of payment">${typeOptions(defaultType(dir), dir)}</select>`
    : ch === "n" ? `<input data-rv-note="${l.id}" maxlength="120" placeholder="Reason, e.g. bank charges" aria-label="Reason no documents are needed">` : "";
  return `<div class="row" style="gap:6px"><span class="pill warn">To explain</span>
    <button class="ghost small" data-explain="${l.id}">More options</button></div>
    <select data-rv-choice="${l.id}" aria-label="What this bank line is">${opts}</select>${extra}`;
}

function rvRow(l) {
  const V = RV(), cur = V.d.summary.account.currency, tick = rvNeedsTick(l);
  const open = l.state === "open", can = !open || !!V.choice[l.id];
  return `<div class="rv-row ${open ? "open" : ""}" id="rv-row-${l.id}">
    <div class="rv-mine">${rvMine(l)}
      <label class="row rv-select"><input type="checkbox" data-rv-sel="${l.id}" ${V.sel[l.id] ? "checked" : ""} ${can ? "" : "disabled"}> Select</label>
      ${tick ? `<label class="row rv-keep"><input type="checkbox" data-rv-keep="${l.id}" ${V.keep[l.id] ? "checked" : ""}><span>Bank date differs by ${dayCount(tick.days)}: keep the ${tick.kind} date (${shortDate(tick.date)})</span></label>` : ""}</div>
    <div class="rv-bank"><div class="row spread"><span class="mono">${fmtDate(l.txn_date)}</span><span class="eyebrow">${l.amount < 0 ? "Money out" : "Money in"}</span></div>
      <div class="num ${l.amount < 0 ? "" : "recv"}"><b>${signedAmt(l.amount, cur)}</b></div>
      <div class="line-desc">${esc(l.description.replaceAll(" | ", " · "))}</div>
      <div class="note">Balance ${money(l.balance, cur)}</div></div></div>`;
}

function rvLists() {
  const V = RV(), d = V.d, cur = d.summary.account.currency;
  const text = l => bankText(l, cur);
  const open = listRows("bank", d.lines.filter(l => l.state === "open"), text), done = listRows("bank", d.lines.filter(l => l.state !== "open"), text);
  setCount("bank", open.length + done.length, d.lines.length);
  const totalMatched = d.lines.filter(l => l.state !== "open").length, unconf = d.lines.filter(l => l.state !== "open" && !l.confirmed_at).length;
  return `${open.map(rvRow).join("") || `<div class="empty">${d.lines.some(l => l.state === "open") ? "No open line matches." : "Nothing left to explain."}</div>`}
    ${totalMatched ? `<div class="row spread rv-mhead"><button class="link" data-rv-toggle="1">${totalMatched} matched · ${V.showMatched ? "Hide" : "Show"}</button>
      <div class="row">${unconf ? `<span class="note">${unconf} not confirmed yet</span>` : `<span class="pill ok">All confirmed</span>`}
      <button class="ghost small" data-rv-confirm-all="1" ${unconf ? "" : "disabled"}>Confirm all matched</button></div></div>
      ${V.showMatched ? (done.map(rvRow).join("") || `<div class="empty">No matched line matches.</div>`) : ""}` : ""}`;
}
const drawRvList = () => { const el = $("#rvList"); if (el) { el.innerHTML = rvLists(); paintCount("bank"); paintBar(); } };
LIST_REDRAW.bank = drawRvList;

// The bar at the foot of the review: what is selected, what is left, the difference once the rows are applied.
function paintBar() {
  const V = RV(); if (!V) return;
  const d = V.d, s = d.summary, cur = s.account.currency;
  const picked = d.lines.filter(l => V.sel[l.id]), open = d.lines.filter(l => l.state === "open");
  const left = open.filter(l => !V.sel[l.id]).length;
  // Creating a payment, or linking one the books don't date in this month, adds it to the books of a company not in SQL.
  let after = s.difference;
  if (after != null && !s.uses_sql) {
    for (const l of picked) {
      const ch = V.choice[l.id];
      if (l.state !== "open") continue;
      const p = ch?.startsWith("p:") ? rvPay(+ch.slice(2)) : null;
      if (ch === "c") after -= l.amount;
      else if (p && !(p.paid_date || "").startsWith(s.month)) after -= (p.direction === "in" ? 1 : -1) * (p.amount ?? Math.abs(l.amount));
    }
  }
  const bar = $("#rvBar"), sum = $("#rvSelected");
  if (sum) sum.innerHTML = `<b>${picked.length}</b><span>Selected · ${money(picked.reduce((a, l) => a + l.amount, 0), cur)}</span>`;
  if (!bar) return;
  bar.innerHTML = `<div><b>${picked.length}</b> selected · <b>${left}</b> still to explain</div>
    <div>Difference after applying: <b class="${after == null ? "" : Math.abs(after) < 0.005 ? "recv" : "bad-text"}">${after == null ? "— (" + esc(s.book.note || "no books") + ")" : money(after, cur)}</b></div>
    <label class="row"><input type="checkbox" id="rvChecked" ${V.checked ? "checked" : ""}> I've checked these rows</label>
    <button class="btn" id="rvApply" ${picked.length ? "" : "disabled"}>Apply selected (${picked.length})</button>
    <div class="note rv-nosql">Applying only links, creates payments or explains lines here. Nothing is posted to SQL Account.</div>`;
}

function drawReview() {
  const V = RV(), box = $("#stmtList");
  if (!box || !V) return;
  const d = V.d, s = d.summary, cur = s.account.currency, st = s.statement;
  const diff = s.difference, open = d.lines.filter(l => l.state === "open").length;
  box.innerHTML = `<div class="card"><div class="row spread"><div><div class="eyebrow">${esc(s.account.label)}</div><h2>${esc(s.label)} statement · review</h2></div>
      <div class="row noprint"><button class="ghost small" data-rv-back="1">← Back to the year</button>${st.document_id ? `<a class="ghost small" href="/api/documents/${st.document_id}/file" target="_blank">Statement PDF</a>` : ""}</div></div>
      <div class="stats">
        <div class="stat"><b>${d.lines.length}</b><span>Bank lines · ${open} to explain</span></div>
        <div class="stat"><b>${bookCell(s.book, cur)}</b><span>Book closing</span></div>
        <div class="stat"><b>${money(st.closing, cur)}</b><span>Bank closing${diff == null ? "" : " · difference " + money(diff, cur)}</span></div>
        <div class="stat" id="rvSelected"></div></div>
      <div class="row spread"><div>${rcPill(s.status, s.status_text)}</div></div>
      ${listBar("bank", "statement lines")}
      <div class="row rv-sortbar noprint"><span class="muted small">Sort by</span><table class="rv-sort"><thead><tr>${sortTh("bank", "date", "Date")}${sortTh("bank", "desc", "Description")}${sortTh("bank", "amount", "Amount", "num")}${sortTh("bank", "by", "Explained by")}</tr></thead></table></div>
      <div class="rv-wrap"><div id="rvList" class="rv-list">${rvLists()}</div>
        <div class="rv-bar noprint" id="rvBar"></div></div>
      ${signBlock(s)}
      <div class="note">Marking a month reconciled is a record kept in this app. Nothing is posted to SQL Account.</div></div>`;
  paintCount("bank"); paintBar();
}

// Applies the rows selected on the review screen (one request: all of them or none).
async function rvApply() {
  const V = RV(), rows = [];
  for (const l of V.d.lines) {
    if (!V.sel[l.id]) continue;
    const r = { line_id: l.id }, ch = V.choice[l.id] || "";
    if (l.state === "open") {
      if (ch === "c") {
        const desc = document.querySelector(`[data-rv-desc="${l.id}"]`)?.value.trim();
        if (!desc) throw new Error(`Give the payment for the line of ${shortDate(l.txn_date)} a description.`);
        r.create_payment = { description: desc, category: document.querySelector(`[data-rv-cat="${l.id}"]`)?.value || defaultType(l.amount > 0 ? "in" : "out") };
      } else if (ch === "n") { r.no_docs = true; r.note = document.querySelector(`[data-rv-note="${l.id}"]`)?.value.trim() || ""; }
      else if (ch.startsWith("p:")) r.payment_id = +ch.slice(2);
      else throw new Error(`Choose what the line of ${shortDate(l.txn_date)} is, or untick it.`);
    }
    if (rvNeedsTick(l)) r.keep_date = !!V.keep[l.id];
    rows.push(r);
  }
  const r = await api("/api/recon/apply", { json: { entity_id: state.entity, statement_id: V.sid, checked: V.checked, rows } });
  toast(`Applied ${rows.length} row${rows.length === 1 ? "" : "s"}: ${r.linked} linked, ${r.created} created, ${r.explained} explained, ${r.confirmed} confirmed.`);
  return reloadReview();
}

// Sign-off actions (from the month panel or the review): ask the server, then draw the screen that was open again.
async function rcAct(path, body, done) {
  await api(`/api/recon/${path}`, { json: { entity_id: state.entity, ...body } });
  toast(done);
  if (state.recon.rv) return reloadReview();
  return drawRecon();
}

// The drawer of the one-line actions (link, create a payment, no documents), kept beside the review's dropdown; the line
// stays to confirm. amount: the line's, signed as on the statement (money in above 0).
function explainLine(lineId) {
  const V = RV(), l = V?.d.lines.find(x => x.id === lineId);
  if (!l) return;
  const cur = V.d.summary.account.currency, amount = l.amount;
  const pick = { id: String(V.choice[l.id] || "").startsWith("p:") ? +V.choice[l.id].slice(2) : null, q: "", all: false };
  // Money in is most likely a receipt, money out a one-off payment; only the types going the line's way are offered.
  const dir = amount > 0 ? "in" : "out";
  state.drawerDirty = null;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><h2>Explain bank line</h2><button class="ghost small" id="closeDrawer">Close</button></div>
      <div class="ex-line"><div class="row spread"><span class="muted">${shortDate(l.txn_date)} · ${amount > 0 ? "Money in" : "Money out"}</span><b class="mono">${money(Math.abs(amount), cur)}</b></div>
        <div>${esc(l.description)}</div><div class="note">Balance ${money(l.balance, cur)}</div></div></div>
    <div class="card"><h3>Link to an existing payment</h3>
      <input id="ex-q" type="search" placeholder="Search by name or amount" autocomplete="off" aria-label="Search payments">
      <div class="note" id="ex-count"></div>
      <div class="ex-list" id="ex-list" role="listbox" aria-label="Payments"></div>
      <label class="row ex-all"><input type="checkbox" id="ex-all"><span>Also show money the other way and payments already covered</span></label>
      <div class="note">One payment can be linked to several lines, e.g. a 25,000 fee sent as 5,000 + 10,000 + 10,000.</div>
      <button class="btn" id="ex-link">Link</button></div>
    <div class="card"><h3>Create a new payment for this line</h3>
      <div class="note">For one-off transactions such as web hosting, flights or receipts.</div>
      <label class="field"><span>Description</span><input id="ex-desc"></label>
      <label class="field"><span>Type</span><select id="ex-cat">${typeOptions(defaultType(dir), dir)}</select></label>
      <button class="btn" id="ex-create">Create payment and link</button></div>
    <div class="card"><h3>No documents needed</h3>
      <label class="field"><span>Reason</span><input id="ex-note" placeholder="e.g. bank charges, own-account transfer"></label>
      <button class="ghost" id="ex-none">Mark as no documents needed</button></div>`;
  $("#drawer").hidden = false;
  const paint = () => {
    const rows = LT.linkList(l, V.d.payments, pick.q, pick.all);
    $("#ex-count").textContent = `${rows.length} payment${rows.length === 1 ? "" : "s"}${pick.q ? " found" : ", likeliest first"}`;
    $("#ex-list").innerHTML = rows.map(r => `<button type="button" class="ex-pay ${r.p.id === pick.id ? "on" : ""}" role="option" aria-selected="${r.p.id === pick.id}" data-ex-pay="${r.p.id}">
        <span class="ex-desc">${esc(r.p.description)}</span><span class="mono ex-amt">${r.p.direction === "in" ? "+" : ""}${money(r.p.amount, r.p.currency)}</span>
        <span class="ex-meta">${esc(monthName(r.p.month))}${r.p.linked ? ` · ${money(r.open, r.p.currency)} still open` : ""}${r.sugg ? ` · <b>Suggested</b>: ${esc(r.sugg.reason)}` : r.exact ? ` · <b>Same amount</b>` : ""}</span></button>`).join("")
      || `<div class="note">No payment matches. Try a shorter search, or create a new payment below.</div>`;
  };
  paint();
  $("#ex-q").oninput = e => { pick.q = e.target.value; paint(); };
  $("#ex-all").onchange = e => { pick.all = e.target.checked; paint(); };
  $("#ex-list").onclick = e => { const b = e.target.closest("[data-ex-pay]"); if (b) { pick.id = +b.dataset.exPay; paint(); } };
  const done = async (body) => { try { await api(`/api/statement-lines/${lineId}`, { json: body }); closeDrawer(); toast("Line explained"); render(); } catch (e) { toast(e.message, true); } };
  $("#ex-link").onclick = () => pick.id ? done({ payment_id: pick.id }) : toast("Choose a payment first.", true);
  $("#ex-create").onclick = () => { if (!$("#ex-desc").value.trim()) return toast("Give the payment a description.", true); done({ create_payment: { description: $("#ex-desc").value.trim(), category: $("#ex-cat").value } }); };
  $("#ex-none").onclick = () => done({ status: "no_docs", note: $("#ex-note").value.trim() });
}

/* ---------------- SQL Account exports ---------------- */
const SQL_FIELD_LABELS = { doc_no: "Doc No", date: "Date", description: "Description", payee: "Payee / name", amount: "Amount", debit: "Debit", credit: "Credit",
  einvoice: "e-Invoice UUID", doc_type: "Doc type", einvoice_status: "e-Invoice status", einvoice_link: "e-Invoice link",
  code: "SQL code", payment_method: "Payment method", cheque_no: "Cheque no.", dockey: "Doc key", currency_code: "Currency" };
// What SQL also says of an entry, under its payee: "Code 400-A001 · Chq 12345 · Method Maybank" (only what it has).
const sqlCodes = x => {
  const bits = [x.code && `Code ${x.code}`, x.cheque_no && `Chq ${x.cheque_no}`, x.payment_method && `Method ${x.payment_method}`].filter(Boolean);
  return bits.length ? `<div class="note">${esc(bits.join(" · "))}</div>` : "";
};
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
const applyLabel = p => !p.records.filter(r => !r.exists).length && p.ledger ? "Keep account lines"
  : `Import ${p.records.filter(r => !r.exists).length} entries (${p.records.filter(r => (r.payment_id || r.task_id) && !r.exists || r.exists && r.kind === "invoice" && r.payment_id).length} linked)${p.ledger ? " and keep account lines" : ""}`;
const GL_KIND = { journal: "GL Journal of Transaction", gl_ledger: "GL Ledger", trial_balance: "Trial Balance" };
const sen = n => n == null ? null : n / 100;

// The pill beside an SQL entry that says what SQL's Journal of Transaction gave for it (d.lines[entry id]); clicking
// it opens the lines under the row. "No lines" only shows when a journal read covered the entry's date and book.
function linesPill(lines, x) {
  const l = lines?.[x.id];
  if (!l) return "";
  if (!l.n) return ` <span class="pill grey">No lines</span>`;
  const [cls, text] = l.state === "gone" ? ["bad", "No longer in SQL"] : !l.balanced ? ["bad", "Lines don't balance"]
    : l.total_ok === false ? ["warn", "Lines ≠ amount"] : l.version > 1 ? ["warn", `Changed in SQL (v${l.version})`]
    : [l.unknown?.length || l.warnings ? "warn" : "ok", plural(l.n, "line")];
  return ` <button type="button" class="pill ${cls} pill-btn" data-sql-lines="${esc(x.doc_no)}" title="Show the account lines">${esc(text)}</button>`;
}

// One version of a document's account lines as a table: the bank's lines marked, a code the chart and the customers
// and suppliers don't know marked "Not in chart".
function ledgerLinesTable(v, banks) {
  const known = l => l.name_from === "chart" || l.name_from === "party" || l.control;
  return `<div class="tbl-wrap"><table class="sql-lines"><thead><tr><th>Account</th><th>Description</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead><tbody>
    ${v.lines.map(l => `<tr class="${banks.includes(l.code) ? "sql-bank-line" : ""}"><td><span class="mono">${esc(l.code)}</span> ${esc(l.name || "")}${known(l) ? "" : ` <span class="pill warn">Not in chart</span>`}${banks.includes(l.code) ? ` <span class="pill grey">Bank</span>` : ""}</td>
      <td>${esc(l.description || "")}</td><td class="num">${l.dr ? money(l.dr) : ""}</td><td class="num">${l.cr ? money(l.cr) : ""}</td></tr>`).join("")}
    <tr class="sql-lines-total"><td colspan="2">Total</td><td class="num">${money(v.totals.dr)}</td><td class="num">${money(v.totals.cr)}</td></tr></tbody></table></div>`;
}

// Where a version came from: the report or paste it was read from, and when.
const ledgerSource = v => {
  const b = v.batch || {}, from = { journal: "SQL's GL Journal of Transaction", grid: "the journal lines pasted", legacy: "the journal lines pasted before" }[b.report] || "SQL";
  return `Version ${v.version}, ${esc(fmtDate(v.doc_date))}, from ${from}${b.file_name ? ` (${esc(b.file_name)})` : ""}${b.read_at ? `, read ${esc(b.read_at.replace("T", " "))}` : ""}`;
};

// The inline row a lines pill opens: the current version's lines, the checks on them, and the earlier versions.
function ledgerDocView(v) {
  const [cur, ...older] = v.versions;
  const state = cur.state === "gone" ? ` <span class="pill bad">No longer in SQL</span>` : cur.state === "superseded" ? ` <span class="pill grey">Replaced</span>` : "";
  return `<div class="sql-doc">
    <div class="row spread"><b>${esc(v.doc_no)}${cur.book_label ? ` <span class="muted">· ${esc(cur.book_label)}</span>` : ""}${state}</b><span class="note">${ledgerSource(cur)}</span></div>
    ${ledgerLinesTable(cur, v.bank_codes || [])}
    ${v.checks.length ? v.checks.map(c => `<div class="note warn-text">${esc(c)}</div>`).join("") : `<div class="note">The lines balance and agree with the listing.</div>`}
    ${older.length ? `<details><summary class="note">Earlier versions (${older.length})</summary>${older.map(o => `<div class="note">${ledgerSource(o)}</div>${ledgerLinesTable(o, v.bank_codes || [])}`).join("")}</details>` : ""}
  </div>`;
}

// The card of what SQL's own reports said when they were last read: the journal's counts, and the ledger's and trial
// balance's differences from the account lines, with the checks that couldn't run and why.
function sqlChecksCard(d) {
  const reads = d.ledger?.reads || {}, orph = d.ledger?.orphans || { no_listing: [], not_in_journal: [] };
  if (!Object.keys(reads).length && !orph.no_listing.length && !orph.not_in_journal.length) return "";
  const head = (kind, b) => `<div class="row spread"><h3>${GL_KIND[kind]}</h3><span class="muted">${esc(b.file_name || "")}${b.period_from ? ` · ${shortDate(b.period_from)} to ${shortDate(b.period_to)}` : b.period_to ? ` · as at ${shortDate(b.period_to)}` : ""} · read ${esc((b.read_at || "").replace("T", " "))}</span></div>`;
  const journal = b => {
    const s = b.summary || {};
    return `${head("journal", b)}<div class="note">${plural(s.docs || 0, "document")} (${s.new || 0} new, ${s.changed || 0} changed, ${s.same || 0} unchanged${s.back ? `, ${s.back} back in SQL` : ""}, ${s.gone || 0} no longer in SQL), ${plural(s.lines || 0, "line")}.</div>
      ${s.note ? `<div class="note">${esc(s.note)}</div>` : ""}
      ${s.reused?.length ? `<div class="note warn-text">Moved by more than 180 days, so the number may have been used again in SQL: ${esc(s.reused.join(", "))}.</div>` : ""}
      ${(s.recon_changed || []).map(m => `<div class="note warn-text">The bank reconciliation of ${esc(monthName(m.month))}, signed off, changed: money in ${money(m.before.in)} → ${money(m.after?.in)}, money out ${money(m.before.out)} → ${money(m.after?.out)}. It stays signed off; check it again.</div>`).join("")}`;
  };
  const report = (kind, b) => {
    const rs = b.results || [], warns = rs.filter(r => r.outcome === "warn");
    return `${head(kind, b)}
      ${warns.length ? `<div class="tbl-wrap"><table><thead><tr><th>Account</th><th>What differs</th><th class="num">SQL's figure</th><th class="num">The lines</th><th class="num">Difference</th></tr></thead><tbody>
        ${warns.map(r => `<tr><td class="mono">${esc(r.subject || "")}</td><td>${esc(r.text)}</td><td class="num">${money(sen(r.expected_sen))}</td><td class="num">${money(sen(r.actual_sen))}</td>
          <td class="num">${r.expected_sen != null && r.actual_sen != null ? money(sen(r.actual_sen - r.expected_sen)) : "—"}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="note"><span class="pill ok">No differences</span></div>`}
      ${rs.filter(r => r.outcome === "ok").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "skipped").map(r => `<div class="note">Not checked: ${esc(r.text)}</div>`).join("")}
      ${rs.filter(r => r.outcome === "info").map(r => `<div class="note">${esc(r.text)}</div>`).join("")}`;
  };
  return `<div class="card"><h2>Checks against SQL's reports</h2>
    <div class="note">The latest of SQL's GL Journal of Transaction, GL Ledger and Trial Balance fetched, checked against the account lines kept. Not checked: profit and loss and retained earnings Period To Date or opening balances against the lines, and anything after the dates the journals read cover.</div>
    ${reads.journal ? journal(reads.journal) : ""}
    ${["gl_ledger", "trial_balance"].filter(k => reads[k]).map(k => report(k, reads[k])).join("")}
    ${orph.no_listing.length ? `<h3>In SQL's journal but no listing fetched · ${orph.no_listing.length}</h3>
      <div class="note">Fetch or paste the listing these are in, so each can be matched to a payment.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Section</th><th></th></tr></thead><tbody>
      ${orph.no_listing.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.book)}</td><td><button type="button" class="ghost small" data-sql-lines="${esc(x.doc_no)}">Lines</button></td></tr>`).join("")}</tbody></table></div>` : ""}
    ${orph.not_in_journal.length ? `<h3>Listing entries missing from SQL's Journal of Transaction · ${orph.not_in_journal.length}</h3>
      <div class="note">Dated inside a journal read, but not in it: deleted or renumbered in SQL. Ignore one that SQL no longer has.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th class="num">Amount</th><th></th></tr></thead><tbody>
      ${orph.not_in_journal.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td class="num">${money(x.amount)}</td><td>${x.can_ignore ? `<button class="ghost small" data-sql-ignore-ids="${x.ids.join(",")}">Ignore</button>` : `<span class="muted">${x.kind === "payment" ? "Unlink it first to ignore it" : ""}</span>`}</td></tr>`).join("")}</tbody></table></div>` : ""}
  </div>`;
}

// The fetch preview's "Account lines" box: what keeping SQL's journal would do to the documents kept, and the journals
// that start counting in the bank reconciliation (a signed-off month named).
function sqlLedgerBox(l) {
  if (!l) return "";
  const t = l.totals, c = l.counting || { journals: [], signed_off: [] };
  return `<div class="sql-fetch"><b>Account lines</b>
    ${l.refused ? `<div class="note warn-text">${esc(l.refused)}</div>` : ""}
    ${t.docs ? `<div>${plural(t.docs, "document")}, ${plural(t.lines, "line")}: <b>${t.new} new</b>, ${t.changed} changed, ${t.same} unchanged${t.back ? `, ${t.back} back in SQL` : ""}, ${t.gone} no longer in SQL.</div>` : ""}
    ${l.files.map(f => `<div class="row spread"><span>${esc(f.name)} <span class="muted">· ${esc(f.title)}, ${esc(f.period)}</span></span><span class="muted">${f.kind === "journal" ? `${plural(f.docs, "document")}, ${plural(f.lines, "line")}` : esc(f.note)}</span></div>
      ${f.kind === "journal" && f.note ? `<div class="note">${esc(f.note)}</div>` : ""}`).join("")}
    ${l.gone.length ? `<div class="note"><b>No longer in SQL</b> (deleted or renumbered there; kept here, marked): ${l.gone.map(x => `${esc(x.doc_no)} (${shortDate(x.doc_date)}${x.payment ? `, linked to ${esc(x.payment)}` : ""}${x.bank_move ? `, moved ${money(Math.abs(x.bank_move))} on the bank` : ""}${x.signed_off ? ` <span class="pill warn">${esc(monthName(x.month))} signed off</span>` : ""})`).join("; ")}.</div>` : ""}
    ${c.journals.length ? `<div class="sql-warn"><b>${plural(c.journals.length, "journal")} will count in the bank reconciliation</b> (lines on ${esc(c.bank_code)}):
      ${c.journals.map(j => `<div class="note">${esc(j.doc_no)}, ${shortDate(j.doc_date)}: ${money(Math.abs(j.amount))} ${j.amount > 0 ? "into" : "out of"} the bank${j.before != null ? ` (counted as ${money(j.before)} until now)` : ""}${j.listed ? "" : ", once its listing is imported"}${j.signed_off ? ` <span class="pill warn">${esc(monthName(j.month))} signed off</span>` : ""}</div>`).join("")}</div>` : ""}
    ${c.signed_off.length ? `<div class="note warn-text">The book figures of ${c.signed_off.map(m => esc(monthName(m))).join(", ")} will change. Nothing is un-signed: check those months again after importing.</div>` : ""}
  </div>`;
}

async function viewSql(main) {
  const e = ent();
  if (!e.uses_sql) {
    main.innerHTML = `${entityPicker()}<div class="card"><h1>SQL import</h1><div class="note">${esc(e.name)} isn't kept in SQL Account, so there's nothing to import.</div></div>`;
    return;
  }
  const d = await api(`/api/sql/entries?entity=${state.entity}`);
  const candOpts = u => `<option value="">Choose a payment…</option>${paymentOptions(d.candidates, u)}`;
  const unlinkBtn = x => `<button class="ghost small" data-sql-unlink="${x.id}">Unlink</button>`;
  const unRow = u => `<tr><td class="mono">${esc(u.doc_no)}</td><td>${shortDate(u.doc_date)}</td><td>${esc(u.description)}${u.payee ? `<div class="note">${esc(u.payee)}</div>` : ""}${sqlCodes(u)}${linesPill(d.lines, u)}
        ${u.direction === "in" ? `<span class="pill">Money in</span>` : ""}${u.einvoice ? ` <span class="pill ok">e-Invoice ${esc(u.einvoice.slice(0, 8))}…</span>` : ""}${changedInSql(u)}</td>
        <td class="num">${money(u.amount)}</td>
        <td><div class="row" style="flex-wrap:nowrap;gap:6px"><select data-sql-link="${u.id}" style="max-width:240px">${candOpts(u)}</select><button class="ghost small" data-sql-link-go="${u.id}">Link</button></div></td>
        <td><div class="row"><button class="ghost small" data-sql-create="${u.id}">Create payment</button><button class="ghost small" data-sql-ignore="${u.id}">Ignore</button></div></td></tr>`;
  const waiting = d.unlinked.filter(u => !u.correction), corrections = d.unlinked.filter(u => u.correction);
  state.sqlCorrections = corrections.map(u => u.id);
  const sqlText = x => [x.doc_no, fmtDate(x.doc_date), x.doc_date, x.description, x.payee, x.code, x.cheque_no, x.payment_method, LT.amount(x.amount), x.direction === "in" ? "money in" : "", x.payment_desc,
    x.payment_month ? monthName(x.payment_month) : "", x.einvoice ? "e-invoice" : ""].join(" ");
  const th = (cols, last) => `<thead><tr>${sortTh("sql", "doc", "Doc No")}${sortTh("sql", "date", "Date")}${sortTh("sql", "desc", "Description")}${sortTh("sql", "amount", "Amount", "num")}${cols}${last}</tr></thead>`;
  const none = (list, text) => `<tr><td colspan="6" class="empty">${list.length ? "No entry matches." : text}</td></tr>`;
  const entries = () => {
    const w = listRows("sql", waiting, sqlText), c = listRows("sql", corrections, sqlText), lk = listRows("sql", d.linked, sqlText), ig = listRows("sql", d.ignored, sqlText);
    setCount("sql", w.length + c.length + lk.length + ig.length, waiting.length + corrections.length + d.linked.length + d.ignored.length);
    return `<div class="card"><h2>SQL entries not linked to a payment</h2>
      <div class="row spread"><div class="note">These are in SQL but not in this tracker. Link each one to a payment, create a payment for it, or ignore it (e.g. a reversal).</div>
      ${waiting.length > 1 ? `<button class="ghost small" id="sqlCreateAll">Create payments for all ${waiting.length}</button>` : ""}</div>
      <div class="tbl-wrap"><table>${th(`<th>Link to</th>`, `<th></th>`)}<tbody>
      ${w.map(unRow).join("") || none(waiting, "Nothing waiting.")}
      </tbody></table></div>
      ${corrections.length ? `<div class="row spread"><div><h3>Probably a correction (no money moved)</h3>
        <div class="note">Reversals and contras made in SQL, or a receipt and a payment for the same amount on the same day. Create payments for all leaves these out. Ignore them, unless money really moved.</div></div>
        <button class="ghost small" id="sqlIgnoreAll">Ignore all ${corrections.length}</button></div>
      <div class="tbl-wrap"><table>${th(`<th>Link to</th>`, `<th></th>`)}<tbody>
      ${c.map(unRow).join("") || none(corrections, "")}</tbody></table></div>` : ""}</div>
    <div class="card"><details data-sql-open="linked" ${state.sqlOpen.linked ? "open" : ""}><summary><h2 style="display:inline">Linked to payments</h2> <span class="muted">· ${d.linked.length}</span></summary>
      <div class="note">Linked to the wrong payment? Unlink it: it goes back to the list above, and the payment's amount and paid date go back to what they were. A payment made from the voucher with Create payment, with nothing added since, is removed.</div>
      <div class="tbl-wrap"><table>${th(sortTh("sql", "pay", "Payment"), `<th></th>`)}<tbody>
      ${lk.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td>${esc(x.payment_desc)} <span class="muted">(${monthName(x.payment_month)})</span></td>
        <td>${unlinkBtn(x)}</td></tr>`).join("") || none(d.linked, "None yet.")}
      </tbody></table></div></details></div>
    ${d.ignored.length ? `<div class="card"><details data-sql-open="ignored" ${state.sqlOpen.ignored ? "open" : ""}><summary><h2 style="display:inline">Ignored</h2> <span class="muted">· ${d.ignored.length}</span></summary>
      <div class="tbl-wrap"><table>${th("", `<th></th>`).replace("<th></th></tr>", "<th></th></tr>")}<tbody>
      ${ig.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${x.direction === "in" ? "+" : ""}${money(x.amount)}</td><td><button class="ghost small" data-sql-unignore="${x.id}">Un-ignore</button></td></tr>`).join("") || none(d.ignored, "")}
      </tbody></table></div></details></div>` : ""}`;
  };
  main.innerHTML = `${entityPicker()}
    <div class="card"><h1>SQL import · ${esc(e.code)}</h1>
      <div class="note">Paste each SQL listing for the month in turn: <b>Cash Book</b>, <b>Receipt Voucher</b>, <b>Payment Voucher</b>, <b>Journal</b> and <b>Customer Invoice</b>. Payments and receipts are matched to this tracker; customer invoices are filed against their checklist item of their own month (the e-Invoices for the fund received and the office rental) and linked to the money in they are for (the tenant's rent), and a payroll journal, if there is one, against Salary PVs in SQL. A document that appears in two listings is only kept once, so overlap is fine.</div>
      <div class="row spread" style="align-items:flex-start;gap:16px"><div><h3>Fetch exported listings (one click)</h3>
          <div class="note">Reads every SQL listing saved in <b>${esc(state.meta.sql_exports_dir)}</b>, whatever the files are called, and shows what is new and what is already imported. In SQL: open the listing, then the arrow beside the print button, <b>Export to Microsoft Excel Workbook</b>, and save it in <b>SQL Drive on SQL Connect › Download</b>. It reads the Cash Book, Payment Voucher, Official Receipt, Journal Voucher, Customer Invoice, Sales Invoice and Customer Payment listings (not their GST layouts). It also reads SQL's <b>GL Journal of Transaction</b> (the account lines of every document), <b>GL Ledger</b> (Local - Ledger - Detail, Level 1) and <b>Trial Balance</b> (This Month vs This Year with Opening): export them for the same dates as the listings, and the lines are kept and checked against SQL's own figures. e-Invoice details still come from copy and paste below.</div>
          <details class="sql-folder"><summary>Use another folder</summary>
            <div class="row" style="align-items:flex-end"><label class="field" style="flex:1"><span>Folder the exports are saved in (leave empty for your Downloads folder)</span><input id="sqlDir" value="${state.meta.sql_exports_default ? "" : esc(state.meta.sql_exports_dir)}" placeholder="${esc(state.meta.sql_exports_dir)}" autocomplete="off"></label>
            <button class="ghost" id="sqlDirSave" type="button">Save folder</button></div></details></div>
        <button class="btn" id="sqlFetch" type="button" style="white-space:nowrap">Fetch from SQL exports</button></div>
      <div class="grid2">
        <form id="sqlPasteForm" style="display:grid;gap:8px"><h3>Copy and paste</h3>
          <div class="note">In SQL, open the Cash Book Listing, click any row, press <b>Ctrl+A</b> then <b>Ctrl+C</b>. Click in the box below and press <b>Ctrl+V</b>.</div>
          <textarea id="sqlPaste" rows="5" placeholder="Paste the SQL rows here" style="font-family:var(--f-mono);font-size:.8rem;border:1px solid var(--line-strong);background:var(--bg);border-radius:6px;padding:6px 8px"></textarea>
          <div class="row"><button class="btn" type="submit">Read pasted rows</button></div></form>
        <form id="sqlForm" style="display:grid;gap:8px;align-content:start"><h3>Or choose an exported file</h3>
          <label class="field"><span>SQL export (.xlsx, .xls, .csv)</span><input id="sqlFile" type="file" accept=".xlsx,.xls,.csv,.ods,.txt"></label>
          <div class="row"><button class="btn" type="submit">Read file</button></div></form>
      </div></div>
    <div id="sqlPreview"></div>
    <div class="card"><h2>Find an SQL entry</h2>${listBar("sql", "SQL entries")}</div>
    <div id="sqlEntries">${entries()}</div>
    <div class="card"><h2>Journals and customer invoices</h2>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>e-Invoice</th><th>Checklist item</th></tr></thead><tbody>
      ${d.documents.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.description)}${x.payee ? `<div class="note">${esc(x.payee)}</div>` : ""}${sqlCodes(x)}${linesPill(d.lines, x)}</td>
        <td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.task_title ? `<span class="pill ok">${esc(x.task_title.split(":")[0])} (${esc(x.task_month)})</span>` : `<span class="muted">—</span>`}
          ${x.kind === "journal" && x.bank_move != null ? `<div class="note">Moves ${money(Math.abs(x.bank_move))} ${x.bank_move > 0 ? "into" : "out of"} the bank, so it counts in the bank reconciliation.</div>` : ""}
          ${x.payment_id ? `<div class="row" style="gap:6px"><span class="note">${x.kind === "journal" ? "Payment" : "Receipt"}: ${esc(x.payment_desc)}</span>${unlinkBtn(x)}</div>`
            : x.kind === "journal" && x.bank_move != null ? `<div class="row" style="flex-wrap:nowrap;gap:6px"><select data-sql-link="${x.id}" style="max-width:240px">${candOpts({ doc_no: x.doc_no, direction: x.bank_move > 0 ? "in" : "out" })}</select><button class="ghost small" data-sql-link-go="${x.id}">Link</button><button class="ghost small" data-sql-create="${x.id}">Create payment</button></div>` : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">Paste the Journal and Customer Invoice listings to see them here.</td></tr>`}
      </tbody></table></div></div>
    ${sqlChecksCard(d)}
    <div class="card"><h2>e-Invoices</h2><div class="note">Every SQL document with an e-Invoice, and whether LHDN has validated it.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead><tbody>
      ${d.einvoices.map(x => `<tr><td class="mono">${esc(x.doc_no)}</td><td>${shortDate(x.doc_date)}</td><td>${esc(x.payee || x.description)}</td><td class="num">${money(x.amount)}</td><td>${einvPill(x)}</td>
        <td>${x.payment_id ? unlinkBtn(x) : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">None imported yet.</td></tr>`}
      </tbody></table></div></div>
    <div class="card"><h2>Imported files</h2>${d.imports.map(i => `<div class="row spread"><span>${esc(i.filename)} <span class="muted">· ${i.entries} entries, ${i.linked} linked${i.lines ? ` · ${plural(i.lines, "line")}` : ""}</span></span><span class="muted">${esc(i.imported_at.replace("T", " "))}</span></div>`).join("") || `<div class="note">None yet.</div>`}</div>`;
  // A listing read but not imported yet stays, with links picked by hand, while you tidy the entries below.
  $("#sqlPaste").value = state.sqlPaste[state.entity] || "";
  paintCount("sql"); LIST_REDRAW.sql = () => { $("#sqlEntries").innerHTML = entries(); paintCount("sql"); };
  if (state.sqlPreview?.entity_id === state.entity) renderSqlPreview(state.sqlPreview);
}

function einvPill(x) {
  if (!x.einvoice && !x.einvoice_status) return `<span class="muted">—</span>`;
  const ok = (x.einvoice_status || "").startsWith("Validated") && !x.taken_back_by;
  const pill = `<span class="pill ${ok ? "ok" : "warn"}">${x.taken_back_by ? `Cancelled by ${esc(x.taken_back_by)}` : esc(x.einvoice_status || "Has UUID")}</span>`;
  return x.einvoice_link ? `${pill} <a href="${esc(x.einvoice_link)}" target="_blank" rel="noopener noreferrer">MyInvois ↗</a>` : pill;
}

// A customer invoice (IV) can be linked to the money-in payment it is for (the tenant's rent): the receipt then shows the
// invoice and its e-Invoice. Offered when the company has money in; the server suggests one by name and amount.
function receiptPick(p, r) {
  if (r.kind !== "invoice" || r.doc_type !== "IV") return "";
  const ins = p.candidates.filter(c => c.direction === "in");
  if (!ins.length) return "";
  return `<div class="row" style="flex-wrap:nowrap;gap:6px"><span class="note">Receipt:</span><select data-sql-row="${r.row}"><option value="">Not linked</option>${paymentOptions(ins, { ...r, direction: "in" }, r.payment_id)}</select></div>`;
}

// What Fetch from SQL exports found in the folder: the listings read with what is new in each, the files it could not
// use and why, and what it left alone.
function sqlFetchReview(f) {
  const n = (k, word) => `${k} ${word}${k === 1 ? "" : "s"}`;
  const read = f.files.filter(x => x.status === "read"), before = f.files.filter(x => x.status === "imported_before"),
    copies = f.files.filter(x => x.status === "copy"), unused = f.files.filter(x => !["read", "imported_before", "copy"].includes(x.status));
  const span = x => x.period?.[0] ? `, ${shortDate(x.period[0])} to ${shortDate(x.period[1])}` : x.period?.[1] ? `, as at ${shortDate(x.period[1])}` : "";
  const listings = read.filter(x => !x.report), reports = read.filter(x => x.report);
  const left = [before.length ? `${n(before.length, "file")} imported before` : "", copies.length ? `${n(copies.length, "copy")}`.replace("copys", "copies") + " of a file read" : "",
    f.other ? (f.other === 1 ? "1 other workbook that isn't an SQL listing or report" : `${f.other} other workbooks that aren't SQL listings or reports`) : ""].filter(Boolean);
  return `<div class="sql-fetch">
    <div>${listings.length ? `<b>${n(listings.length, "listing")} read</b> from ${esc(f.folder)}: ${n(f.entries, "document")}, <b>${f.new} new</b>, ${f.already} already imported.`
      : `No new SQL listing was found in ${esc(f.folder)}.`}${reports.length ? ` <b>${n(reports.length, "report")} of SQL's general ledger read.</b>` : ""}</div>
    ${listings.map(x => `<div class="row spread"><span>${esc(x.name)} <span class="muted">· ${esc(x.title)}${span(x)}</span></span>
      <span class="muted">${x.new} new, ${x.already} already imported${x.repeated ? `, ${x.repeated} also in another file` : ""}</span></div>`).join("")}
    ${reports.map(x => `<div class="row spread"><span>${esc(x.name)} <span class="muted">· ${esc(GL_KIND[x.report] || x.title)}${span(x)}</span></span>
      <span class="muted">${x.report === "journal" ? `${n(x.docs, "document")}, ${n(x.lines, "line")}` : n(x.accounts, "account")}</span></div>`).join("")}
    ${unused.length ? `<div class="sql-unused"><b>${n(unused.length, "file")} not used</b>${unused.map(x => `<div class="note">${esc(x.name)}: ${esc(x.reason)}</div>`).join("")}</div>` : ""}
    ${left.length ? `<div class="note">Left alone: ${left.join("; ")}.</div>` : ""}</div>`;
}

function renderSqlPreview(p) {
  state.sqlPreview = p;
  if (p.nothing_new) {  // a fetch with nothing to import: the review says what was found
    $("#sqlPreview").innerHTML = `<div class="card"><div class="row spread"><h2>Nothing new to import</h2><button class="ghost" id="sqlCancel">Close</button></div>
      ${sqlFetchReview(p.fetch)}</div>`;
    return;
  }
  if (p.journal_lines) {  // the lines of a journal: kept for the bank reconciliation, nothing to match
    const jl = p.journal_lines, fmt = x => Number(x).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    // Lines pasted as plain text carry no document key, so the person says which journal they are from.
    const pick = !jl.text_form ? "" : !jl.balanced ? `<div class="note">${esc(jl.message)}</div>` : `
      <label class="field"><span>Which journal are these lines from?</span><select id="sqlJournalPick"><option value="">Choose a journal</option>${jl.options.map(o =>
        `<option value="${o.id}" ${o.id === jl.chosen ? "selected" : ""}>${esc(o.doc_no)}, ${esc(o.doc_date)}, ${fmt(o.amount)}${o.match ? " (same total)" : ""}</option>`).join("")}</select></label>
      ${jl.message ? `<div class="note">${esc(jl.message)}</div>` : ""}`;
    const ok = !jl.text_form || (jl.balanced && jl.chosen);
    $("#sqlPreview").innerHTML = `<div class="card">
      <div class="row spread"><h2>${esc(p.filename)}</h2><span class="muted">${jl.lines} journal lines found</span></div>
      ${pick}
      ${jl.notes.map(n => `<div class="note">${esc(n.text)}</div>`).join("")}
      <div class="row"><button class="btn" id="sqlApply" ${ok ? "" : "disabled"}>Keep ${jl.lines} journal lines</button><button class="ghost" id="sqlCancel">Cancel</button></div></div>`;
    return;
  }
  const colOpts = sel => `<option value="">(none)</option>` + p.headers.map((h, i) => `<option value="${i}" ${i === sel ? "selected" : ""}>${esc(h || "Column " + (i + 1))}</option>`).join("");
  const kinds = { journal: "Journal", invoice: "Customer invoice" };
  const target = r => r.exists ? `<span class="pill grey">Already imported</span>${receiptPick(p, r)}`
    : r.kind !== "payment" ? (r.task_id ? `<span class="pill ok">Checklist: ${esc(r.task_title)}</span>` : `<span class="pill grey">${kinds[r.kind]}, kept on file</span>`) + receiptPick(p, r)
    : `<select data-sql-row="${r.row}"><option value="">Not linked</option>${paymentOptions(p.candidates, r, r.payment_id)}</select>${r.task_id ? `<div class="note">Also: ${esc(r.task_title)}</div>` : ""}${changedInSql(r)}`;
  const blocked = p.ledger?.refused && !p.records.filter(r => !r.exists).length;
  if (p.ledger && !p.records.length) {  // SQL's reports only: account lines to keep, no entries to match
    $("#sqlPreview").innerHTML = `<div class="card">
      <div class="row spread"><h2>SQL's general-ledger reports</h2><span class="muted">No new listing entries</span></div>
      ${sqlFetchReview(p.fetch)}${sqlLedgerBox(p.ledger)}
      <div class="row"><button class="btn" id="sqlApply" ${blocked ? "disabled" : ""}>${applyLabel(p)}</button><button class="ghost" id="sqlCancel">Cancel</button></div></div>`;
    return;
  }
  $("#sqlPreview").innerHTML = `<div class="card">
    <div class="row spread"><h2>${esc(p.filename)}</h2><span class="muted">${p.records.length} entries found</span></div>
    ${p.fetch ? `${sqlFetchReview(p.fetch)}${sqlLedgerBox(p.ledger)}<div class="note">Check each suggested payment, then import. The new documents are listed first.</div>`
      : `<div class="note">Check the columns were read correctly, then check each suggested payment.</div>
    <div class="form">${p.fields.map(f => `<label class="field"><span>${esc(SQL_FIELD_LABELS[f] ?? f)}</span><select data-sql-map="${f}">${colOpts(p.mapping[f])}</select></label>`).join("")}</div>`}
    <div class="tbl-wrap"><table><thead><tr><th>Doc No</th><th>Date</th><th>Description</th><th class="num">Amount</th><th>Records this payment</th></tr></thead><tbody>
    ${p.records.map(r => `<tr><td class="mono">${esc(r.doc_no)}</td><td>${shortDate(r.date)}</td><td>${esc(r.description)}${r.payee ? `<div class="note">${esc(r.payee)}</div>` : ""}${sqlCodes(r)}
      ${r.einvoice || r.einvoice_status ? `<div>${einvPill(r)}</div>` : ""}</td>
      <td class="num">${r.direction === "in" ? "+" : ""}${money(r.amount)}</td>
      <td>${target(r)}</td></tr>`).join("")}
    </tbody></table></div>
    <div class="row"><button class="btn" id="sqlApply">${applyLabel(p)}</button><button class="ghost" id="sqlCancel">Cancel</button></div></div>`;
}

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
      <div class="row"><button class="btn" id="buildPack">Build audit pack PDF</button>
        <a class="ghost" id="excelReport" href="/api/export/month.xlsx?entity_id=${state.entity}&month=${state.month}">Excel report</a>
        <button class="ghost" id="auditorPack">Auditor package</button></div><div id="packOut" class="note" hidden></div>
      ${built ? `<div class="row"><b>Printed and filed?</b><button class="btn" data-close-month="built">Yes, mark month as filed</button></div>` : ""}</div>
    <div class="card"><h2>Recent packs</h2>${packs.length ? packs.map(packRow).join("") : `<div class="note">None built for ${esc(r.label)} yet.</div>`}</div>`;
}

// A pack built for the month: its file (or that it has gone), when, and Check this pack (by its trail row, or by its
// file for one built before the trail recorded packs).
const packRow = p => `<div class="row spread"><span>${p.url ? `<a href="${esc(p.url)}" target="_blank">${esc(p.name)}</a>` : esc(p.name)}${p.missing ? ` <span class="pill bad">File missing</span>` : ""}${p.via ? ` <span class="muted">· for the ${esc(p.via)}</span>` : ""}</span>
  <span class="row tight"><span class="muted">${esc(p.at.replace("T", " "))}</span><button class="ghost small" type="button" data-pack-check="${esc(p.event ?? "")}" data-pack-file="${esc(p.name)}">Check this pack</button></span></div>`;

/* ---- Check this pack (hrp/packcheck.py) ---- */
const PACK_FILE = { unchanged: ["ok", "File unchanged"], changed: ["bad", "File changed"], missing: ["bad", "File missing"],
  not_recorded: ["warn", "Not recorded in the trail"] };
// A trail entry, opened in place (toggleEntry draws it below the button).
const entryLink = (id, text) => id ? `<div><button class="ghost small" type="button" data-tx="${esc(id)}" aria-expanded="false">${esc(text)}</button><div class="tr-body" hidden></div></div>` : "";

// The drawer: whether the file is the one built, what built it, and what changed since in what it reads (grouped, each
// change with its trail entry), then what the check can't tell.
async function openPackCheck(event, file) {
  if (!closeDrawer()) return;
  $("#drawer").innerHTML = `<div class="ex-head"><div class="row spread"><div><div class="eyebrow">Check this pack</div><h2>${esc(file || "Audit pack")}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <div id="pcBody"><div class="note">Loading…</div></div>`;
  $("#drawer").hidden = false;
  let r;
  try {
    r = await api(event ? `/api/audit-pack/check?event=${encodeURIComponent(event)}`
      : `/api/audit-pack/check?entity=${state.entity}&month=${state.month}&file=${encodeURIComponent(file)}`);
  } catch (e) { if ($("#pcBody")) $("#pcBody").innerHTML = `<div class="note bad-text">${esc(e.message)}</div>`; return; }
  if (!$("#pcBody")) return;
  const p = r.pack, pr = p.printed || {}, [tone, word] = PACK_FILE[r.file.state];
  const cover = pr.trail_entry ? `On its cover: ${pr.generated ? `generated ${esc(pr.generated)}, ` : ""}audit trail entry ${esc(pr.trail_entry)} · check code ${esc(pr.check_code)}${pr.worked_out ? " (worked out from the trail)" : ""}.` : "";
  const prog = p.same_program === true ? "Built by the version of the program running now." : p.same_program === false ? "Built by another version of the program." : "";
  const row = (g, x) => `<div class="tr-hist"><div><span class="mono muted">${esc(fmtWhen(x.at))}</span> · <span class="pill ${SRC_TONE[x.source] ?? "grey"}">${esc(x.source_label || "")}</span> ${esc(x.actor || "")}${x.reason ? ` · Why: ${esc(x.reason)}` : ""}${x.late ? ` <span class="pill warn">Sealed late</span>` : ""}</div>
    ${g.key === "packs" ? `<div class="tr-change"><b>Built ${esc(x.record)}</b></div>` : changeHtml(x)}
    ${entryLink(x.entry, `Entry ${x.entry}${x.headline ? `: ${x.headline}` : ""}`)}</div>`;
  const groups = r.changes.groups.map(g => `<h3>${esc(g.label)} · ${esc(g.count)}</h3>${g.rows.map(x => row(g, x)).join("")}
    ${g.more ? `<div class="note">And ${esc(g.more)} more, not listed here.</div>` : ""}`).join("");
  const docs = r.documents.problems.length
    ? `<h3>Its documents' files now · ${esc(r.documents.problems.length)}</h3>${r.documents.problems.map(d => `<div class="note"><b>${esc(d.name)}</b> on ${esc(d.owner)}: ${esc(d.why)}</div>`).join("")}`
    : r.documents.checked ? `<div class="note">The ${esc(r.documents.checked)} document file${r.documents.checked === 1 ? "" : "s"} it would hold now still match${r.documents.checked === 1 ? "es" : ""} the fingerprint taken at upload.</div>` : "";
  $("#pcBody").innerHTML = `<div class="row"><span class="pill ${tone}">${esc(word)}</span></div>
    <div class="note">${esc(r.file.text)}</div>
    <div class="note">${esc(r.company)} · ${esc(r.label)}. ${r.recorded ? `Built ${esc(fmtWhen(p.at))}${p.actor ? ` by ${esc(p.actor)}` : ""}${p.via ? ` for the ${esc(p.via)}` : ""}.` : `File saved ${esc(fmtWhen(p.at))}.`} ${cover} ${prog}</div>
    ${entryLink(p.entry, `Entry ${p.entry}: the pack built`)}
    <h2>Since it was built</h2><div class="note">${esc(r.changes.summary)}</div>${groups}${docs}
    <h2>What this check can't tell</h2>${r.cannot_tell.map(t => `<div class="note">${esc(t)}</div>`).join("")}`;
}

// Marks the month on show as filed. With anything still open (Before you print, or the pack not built or out of date)
// it asks first, naming it: a month filed outside the app can still be marked. afterBuild: asked from 'Printed and
// filed?' on the Audit page.
async function markFiled(afterBuild) {
  const r = await api(`/api/audit-readiness?entity_id=${state.entity}&month=${state.month}`);
  if (r.still_open.length && !confirm(`Still open in ${r.entity.code} ${r.label}:\n${r.still_open.map(s => "• " + s).join("\n")}\n\n${afterBuild ? "" : "If this month was already filed outside the app, that is fine. "}Mark it as filed anyway?`)) return;
  await api("/api/months/close", { json: { entity_id: state.entity, month: state.month, closed: true } });
  toast(`${r.label} marked as filed`); await render();
  // The password is typed each time, so a backup is offered, not made.
  if (confirm("Make an encrypted backup now?")) { state.view = "settings"; renderNav(); await render(); $("#bkPw")?.focus(); }
}

// A line of Before you print opens the screen that fixes it, for this company and month: the payment's drawer, the
// checklist item on the month page, the Bank statements page on that account, or the SQL page.
function fixIt(where, id) {
  const view = { payment: "entity", task: "entity", account: "bank", sql: "sql" }[where];
  return goTo({ view, payment_id: where === "payment" ? id : null, task_id: where === "task" ? id : null, account_id: where === "account" ? id : null });
}

/* ---------------- Backup ---------------- */
async function viewSettings(main) {
  const log = await api("/api/activity");
  main.innerHTML = `
    <div class="card"><h1>Backup</h1>
      <div class="note">Everything is stored on this PC in <span class="mono">${esc(state.meta.data_dir)}</span>: the database (records.db), uploaded documents and audit packs. Nothing is sent anywhere else.</div>
      <div class="note">Backups are saved in the backups folder on this PC. Encrypted backups are also copied to the backup folder below, if you set one.</div>
      <div class="row"><label class="field" style="flex:1"><span>Backup folder (optional)</span><input id="bkDir" value="${esc(state.meta.backup_dir || "")}" placeholder="C:\\Users\\you\\OneDrive\\HR-Backup" autocomplete="off"></label>
        <button class="ghost" id="saveBackupDir" style="align-self:end">Save folder</button></div>
      <div class="note">If this folder is inside your OneDrive folder, OneDrive uploads it. Only encrypted backups are copied there. Leave it empty to copy nowhere.</div>
      <div class="row"><label class="field"><span>Backup password</span><input type="password" id="bkPw" autocomplete="new-password"></label>
        <label class="field"><span>Type it again</span><input type="password" id="bkPw2" autocomplete="new-password"></label>
        <button class="btn" id="doBackupEnc" style="align-self:end">Make encrypted backup</button></div>
      <div class="note">At least 12 characters. Keep the password safe: without it the backup cannot be opened. Open it with 7-Zip (Windows Explorer cannot open AES zips). Only the contents are protected: file names inside the zip can still be seen.</div>
      <div class="row"><button class="ghost" id="doBackup">Backup on this PC only (not encrypted)</button><button class="ghost" id="doCheck">Check documents haven't changed</button></div>
      <div id="setOut" class="note"></div></div>
    <div class="card"><h2>Activity log</h2><div class="tbl-wrap"><table><tbody>
      ${log.map(a => `<tr><td class="mono muted" style="white-space:nowrap">${esc(a.at.replace("T", " "))}</td><td>${esc(a.what)}</td></tr>`).join("") || `<tr><td class="empty">Nothing yet.</td></tr>`}
    </tbody></table></div></div>`;
}

/* ---------------- Setup ---------------- */
// Companies, bank accounts, recurring payments and general settings, kept in the records and changed here. The sections,
// their fields and list columns come from the server (/api/setup/types). A stopped record stays, for its history.
const setupSpec = () => state.setup.types?.kinds?.[state.setup.kind] || null;
const sectionLabel = spec => spec.single || !spec.plural ? spec.label : spec.plural.charAt(0).toUpperCase() + spec.plural.slice(1);
const NUM_TYPES = ["number", "money", "day"];

async function viewSetup(main) {
  const S = state.setup;
  if (!S.types) S.types = await api("/api/setup/types");
  const T = S.types;
  if (!T.kinds[S.kind]) S.kind = T.groups.flatMap(g => g[1]).find(k => T.kinds[k]) || null;
  renderNav();  // the breadcrumb names the section
  const sections = T.groups.map(([g, kinds]) => {
    const ks = kinds.filter(k => T.kinds[k]);
    return ks.length ? `<div class="setup-group">${esc(g)}</div>${ks.map(k => `<button type="button" data-setup-kind="${esc(k)}"${k === S.kind ? ` class="on" aria-current="page"` : ""}>${esc(sectionLabel(T.kinds[k]))}</button>`).join("")}` : "";
  }).join("");
  main.innerHTML = `<div class="setup-grid"><nav class="setup-nav card noprint" aria-label="Setup sections">${sections}</nav><div class="setup-main" id="setupMain"></div></div>`;
  const box = $("#setupMain"), spec = setupSpec();
  if (!spec) box.innerHTML = `<div class="card"><div class="note">Nothing to set up yet.</div></div>`;
  else if (spec.single) await setupSettings(box);
  else if (S.kind === "payees") await viewPayees(box);
  else if (S.kind === "required") await setupRequired(box);
  else if (S.kind === "checklist") await setupChecklist(box);
  else if (S.kind === "reminders") await setupReminders(box);
  else if (S.kind === "move") await setupMove(box);
  else if (spec.bespoke) box.innerHTML = `<div class="card"><h1>${esc(sectionLabel(spec))}</h1><div class="note">This section isn't ready in this version of the app.</div></div>`;
  else await setupList(box, S.kind);
}

// A field's choices as [value, label] pairs: payment types in use only, unless all (to name a value already saved). The
// payment type a voucher's words give is a money-out one; checklist items are every company's, by code.
function fieldOptions(f, all) {
  if (f.options_from === "categories") {
    const dir = f.direction || (state.setup.kind === "guess_words" ? "out" : null);
    return Object.entries(state.meta.categories).filter(([k]) => all || catActive(k) && (!dir || catDir(k) === dir));
  }
  if (f.options_from === "checklist_codes") return Object.entries(state.meta.checklist_codes || {});
  // Customers and suppliers, by id: in use only, unless all. In a per-company list, that company's and every company's.
  if (f.options_from === "parties") {
    const perEntity = !!state.setup.types?.kinds?.[state.setup.kind]?.per_entity;
    return (state.meta.parties || []).filter(pt => all || isActive(pt) && (!perEntity || pt.entity_id == null || pt.entity_id === state.entity))
      .map(pt => [pt.id, `${pt.name}${pt.sql_code ? ` · ${pt.sql_code}` : ""}${pt.entity_id == null ? "" : ` (${state.meta.entities.find(x => x.id === pt.entity_id)?.code ?? "?"})`}`]);
  }
  return f.options || [];
}
// The companies a "company" field offers, by code: those in use, and the one chosen even if stopped since.
const companyChoices = sel => state.meta.entities.filter(x => isActive(x) || String(x.id) === sel);
// A list kept as a list or as JSON text (documents, words): always a list.
function asList(v) {
  if (Array.isArray(v)) return v;
  if (typeof v !== "string" || !v.trim()) return [];
  try { const j = JSON.parse(v); if (Array.isArray(j)) return j; } catch { /* plain text: a comma list */ }
  return splitWords(v);
}
// Words typed with commas between them, as a list.
const splitWords = s => String(s ?? "").split(",").map(x => x.trim()).filter(Boolean);
// An option's value as the input holds it: none (null) is the empty choice.
const optVal = k => k == null ? "" : String(k);
// A value as it reads in a list: month names, Yes or No, an option's label.
function fieldText(f, v) {
  // A company field's empty value is a choice of its own: every company.
  if (f?.type === "company") return v == null || v === "" ? "Every company" : String(state.meta.entities.find(x => x.id === +v)?.code ?? v);
  if (v == null || v === "") return "";
  if (!f) return String(v);
  if (f.options_from === "parties") return String(partyById(v)?.name ?? v);
  if (f.type === "words") return asList(v).join(", ");
  if (f.type === "month") return /^\d{4}-\d{2}$/.test(v) ? monthName(v) : String(v);
  if (f.type === "date") return fmtDate(v);
  if (f.type === "bool") return +v ? "Yes" : "No";
  if (f.type === "money") return Number(v).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (f.type === "select") return String(fieldOptions(f, true).find(o => optVal(o[0]) === String(v))?.[1] ?? v);
  return String(v);
}

// A record the app's own rules rely on (a payment or document type it came with): it can't be deleted.
const systemPill = r => +r?.system ? ` <span class="pill" title="The app relies on it, so it can't be deleted">Used by the app</span>` : "";

// A list's view (Flat or Tree, for a kind that has a tree), kept in this browser.
function setupView(kind, spec) {
  if (!spec.tree) return "flat";
  if (!state.setup.view[kind]) { let v = null; try { v = localStorage.getItem("hrp-setup-view-" + kind); } catch {} state.setup.view[kind] = v === "tree" ? "tree" : "flat"; }
  return state.setup.view[kind];
}
const TREE_TYPES = [["asset", "Assets"], ["liability", "Liabilities"], ["equity", "Equity"], ["income", "Income"], ["expense", "Expenses"]];

// The chart of accounts as a tree: SQL's groups in the order it prints them, each with the accounts under no other
// account, each account with the ones under it (by code). An account without an SQL group goes under its type. A
// heading or an account with others under it opens and closes (closed: the keys closed, "g:CA" or "a:310-000"). A
// search shows the accounts it finds with the ones they sit under, all open. Returns [rows html, accounts in it].
function setupTree(spec, shown, hit, closed, ncol, rowHtml) {
  const up = v => String(v || "").toUpperCase();
  const byCode = new Map(shown.map(r => [up(r.code), r]));
  const parentOf = r => { const p = up(r.parent_code); return p && p !== up(r.code) && byCode.has(p) ? p : null; };
  const keep = new Set();
  for (const r of shown) {
    if (hit && !hit.has(r.id)) continue;
    for (let x = r, seen = new Set(); x && !seen.has(x.id); x = byCode.get(parentOf(x))) { seen.add(x.id); keep.add(x.id); }
  }
  const kids = new Map();
  const roots = [];
  for (const r of shown.filter(r => keep.has(r.id)).sort((a, b) => String(a.code).localeCompare(String(b.code), undefined, { numeric: true }))) {
    const p = parentOf(r);
    // an account whose parent chain loops back is shown at the top of its group
    let loops = false;
    for (let x = p, seen = new Set([up(r.code)]); x; x = parentOf(byCode.get(x))) { if (seen.has(x)) { loops = true; break; } seen.add(x); }
    if (p && !loops) { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(r); } else roots.push(r);
  }
  const groups = (spec.tree.groups || []).map(([code, name]) => ({ key: code, label: `${name} · ${code}` }))
    .concat(TREE_TYPES.map(([t, label]) => ({ key: "~" + t, label: `${label} · no SQL group` })), [{ key: "~", label: "No type or SQL group" }]);
  const groupOf = r => r.sql_type || "~" + (r.type || "");
  const size = r => 1 + (kids.get(up(r.code)) || []).reduce((n, k) => n + size(k), 0);
  // While searching everything found is shown open, and the arrows are only marks: opening or closing then would
  // change what shows after the search with nothing to see now.
  const searching = !!hit;
  let html = "";
  const walk = (list, depth, parent) => {
    for (const r of list) {
      const ch = kids.get(up(r.code)) || [], key = "a:" + up(r.code), open = searching || !closed.has(key);
      const tg = !ch.length ? `<span class="tree-tg" aria-hidden="true"></span>`
        : searching ? `<span class="tree-tg" aria-hidden="true">▾</span>`
        : `<button type="button" class="tree-tg" data-tree="${esc(key)}" aria-expanded="${open}" title="${open ? "Close" : "Open"} the ${ch.length} account${ch.length === 1 ? "" : "s"} under it"><span aria-hidden="true">${open ? "▾" : "▸"}</span><span class="sr-only">${open ? "Close" : "Open"} ${esc(r.code)}</span></button>`;
      const said = (parent ? `, under ${parent.code}` : "") + (hit && !hit.has(r.id) ? ", shown for an account found under it" : "");
      html += rowHtml(r, `<span class="tree-cell" style="--depth:${depth}">${tg}<button class="link" data-setup-open="${r.id}">${esc(r.code || "(no code)")}</button>${said ? `<span class="sr-only">${esc(said)}</span>` : ""}${ch.length && !open ? ` <span class="muted">+${size(r) - 1}</span>` : ""}</span>`);
      if (ch.length && open) walk(ch, depth + 1, r);
    }
  };
  for (const g of groups) {
    const list = roots.filter(r => groupOf(r) === g.key);
    if (!list.length) continue;
    const key = "g:" + g.key, open = searching || !closed.has(key), count = list.reduce((s, r) => s + size(r), 0);
    const head = searching ? `<span class="tree-head"><span aria-hidden="true">▾</span> ${esc(g.label)}</span>`
      : `<button type="button" class="tree-head" data-tree="${esc(key)}" aria-expanded="${open}"><span aria-hidden="true">${open ? "▾" : "▸"}</span> ${esc(g.label)}</button>`;
    html += `<tr class="tree-group"><th colspan="${ncol}" scope="rowgroup">${head} <span class="muted">${count} account${count === 1 ? "" : "s"}</span></th></tr>`;
    if (open) walk(list, 0, null);
  }
  return [html, keep.size];  // every account in the tree, open or closed
}

// Which tree a list is: a kind kept per company (the chart of accounts) has one for each company.
const treeId = (kind, spec) => spec?.per_entity ? `${kind}:${state.entity}` : kind;

// The keys a tree can close: every group heading and every account with others under it.
function treeKeys(rows) {
  const up = v => String(v || "").toUpperCase(), codes = new Set(rows.map(r => up(r.code)));
  const out = new Set(rows.map(r => "g:" + (r.sql_type || "~" + (r.type || ""))));
  for (const r of rows) if (r.parent_code && codes.has(up(r.parent_code))) out.add("a:" + up(r.parent_code));
  return out;
}

// The list of one kind (companies, or one company's bank accounts), stopped ones shown when asked.
async function setupList(box, kind) {
  const S = state.setup, spec = S.types.kinds[kind], id = "setup-" + kind, e = ent();
  const cols = spec.columns || [], fieldOf = k => (spec.fields || []).find(f => f.key === k);
  const isNum = c => NUM_TYPES.includes(fieldOf(c.key)?.type);
  // Registered before the list's first listState, so a sort chosen earlier is kept.
  SORTS[id] ||= Object.fromEntries([...cols.map(c => [c.key, [isNum(c) ? "num" : "text", r => { const f = fieldOf(c.key);
      return f && ["select", "bool", "words", "company"].includes(f.type) ? fieldText(f, r[c.key]) : r[c.key]; }]]),
    ["used", ["num", r => r.used_total]], ["status", ["text", r => r.status]]]);
  if (spec.per_entity && !e) { box.innerHTML = `<div class="card"><h1>${esc(sectionLabel(spec))}</h1><div class="note">Add a company first.</div></div>`; return; }
  const { rows } = await api(`/api/setup/${kind}${spec.per_entity ? `?entity=${state.entity}` : ""}`);
  const stopped = r => r.status === "stopped", nStopped = rows.filter(stopped).length;
  const text = r => [...cols.map(c => fieldText(fieldOf(c.key), r[c.key])), usedText(r.used_by), stopped(r) ? "stopped" : "in use", +r.system ? "used by the app" : ""].join(" ");
  const cell = (r, c, i) => {
    const v = fieldText(fieldOf(c.key), r[c.key]);
    if (!i) return `<td><button class="link" data-setup-open="${r.id}">${esc(v || "(no name)")}</button></td>`;
    return `<td${isNum(c) ? ` class="num"` : ""}>${v ? esc(v) : "—"}</td>`;
  };
  const view = setupView(kind, spec), closed = S.closed[treeId(kind, spec)] ||= new Set();
  const table = () => view === "tree" ? treeTable() : flatTable();
  // The tree: the same columns, unsorted (accounts by code under their group and parent).
  const treeTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), q = listState(id).q.trim();
    const hit = q ? new Set(shown.filter(r => LT.match(text(r), q)).map(r => r.id)) : null;
    const rowHtml = (r, first) => `<tr class="tree-row${hit && !hit.has(r.id) ? " tree-context" : ""}"><td>${first}</td>${cols.slice(1).map((c, i) => cell(r, c, i + 1)).join("")}
        <td class="num" title="${esc(usedText(r.used_by) || "Not used yet")}">${+r.used_total || 0}</td>
        <td>${stopped(r) ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(r)}</td></tr>`;
    const [body, n] = setupTree(spec, shown, hit, closed, cols.length + 2, rowHtml);
    setCount(id, hit ? hit.size : n, rows.length);
    return `<table class="tree"><thead><tr>${cols.map(c => `<th${isNum(c) ? ` class="num"` : ""}>${esc(c.label)}</th>`).join("")}<th class="num">Used by</th><th>Status</th></tr></thead><tbody>
      ${body || `<tr><td colspan="${cols.length + 2}" class="empty">${!rows.length ? "None yet." : shown.length ? `No ${esc(spec.plural)} match.` : `Only stopped ${esc(spec.plural)}: tick Show stopped to see them.`}</td></tr>`}
      </tbody></table>`;
  };
  const flatTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), list = listRows(id, shown, text);
    setCount(id, list.length, rows.length);
    return `<table><thead><tr>${cols.map(c => sortTh(id, c.key, esc(c.label), isNum(c) ? "num" : "")).join("")}${sortTh(id, "used", "Used by", "num")}${sortTh(id, "status", "Status")}</tr></thead><tbody>
      ${list.map(r => `<tr>${cols.map((c, i) => cell(r, c, i)).join("")}
        <td class="num" title="${esc(usedText(r.used_by) || "Not used yet")}">${+r.used_total || 0}</td>
        <td>${stopped(r) ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(r)}</td></tr>`).join("")
      || `<tr><td colspan="${cols.length + 2}" class="empty">${!rows.length ? "None yet." : shown.length ? `No ${esc(spec.plural)} match.` : `Only stopped ${esc(spec.plural)}: tick Show stopped to see them.`}</td></tr>`}
      </tbody></table>`;
  };
  box.innerHTML = `${spec.per_entity ? entityPicker() : ""}
    <div class="card"><div class="row spread"><h1>${esc(sectionLabel(spec))}${spec.per_entity ? ` · ${esc(e.code)}` : ""}</h1>
        <div class="row">${spec.paste ? `<button class="ghost" data-setup-paste="${esc(kind)}">Paste a list</button>` : ""}<button class="btn" data-setup-new="${esc(kind)}">Add ${esc(lowerFirst(spec.label))}</button></div></div>
      ${spec.help ? `<div class="note">${esc(spec.help)}</div>` : ""}
      <div class="note">Click a row to change it. Something already used can't be deleted: stop using it instead, and its history stays.</div>
      <div class="row">${listBar(id, spec.plural)}<label class="row tight"><input type="checkbox" data-setup-stopped ${S.stopped ? "checked" : ""}> Show stopped (${nStopped})</label>
        ${deletedToggle(kind)}
        ${spec.tree ? `<div class="seg" role="group" aria-label="Show the ${esc(spec.plural)} as">${[["flat", "Flat list"], ["tree", "Tree"]].map(([v, l]) =>
          `<button type="button" data-setup-view="${v}" aria-pressed="${view === v}">${l}</button>`).join("")}</div>` : ""}
        ${view === "tree" ? `<button type="button" class="ghost small" data-tree-all="open">Open all</button><button type="button" class="ghost small" data-tree-all="close">Close all</button>` : ""}</div>
      ${view === "tree" ? `<div class="note" id="treeSearchNote" hidden>While searching, everything found is shown open. Clear the search to open or close the groups.</div>` : ""}
      <div class="tbl-wrap" id="setupList">${table()}</div><div id="setupDeleted"></div></div>`;
  paintCount(id);
  drawDeleted(kind);
  // While a search is on, the tree's Open all / Close all are off and a note says why.
  const treeBar = () => {
    const on = !!listState(id).q.trim();
    document.querySelectorAll("[data-tree-all]").forEach(b => { b.disabled = on; });
    const note = $("#treeSearchNote");
    if (note) note.hidden = !on;
  };
  LIST_REDRAW[id] = () => { if (!$("#setupList")) return; $("#setupList").innerHTML = table(); paintCount(id); if (view === "tree") treeBar(); };
  if (view === "tree") treeBar();
  if (spec.tree) (S.treeKeys ||= {})[treeId(kind, spec)] = treeKeys(rows);  // what Close all closes
}

// One input for a field (FieldSpec from the server). lock: why it can't be changed; pre: the id prefix.
function fieldHtml(f, v, lock, pre) {
  const id = pre + f.key, val = v == null ? "" : String(v);
  const wide = f.wide || f.type === "textarea" ? ` style="grid-column:1/-1"` : "";
  const ro = lock ? " readonly" : "", req = f.required && !lock ? " required" : "";
  const len = f.max && ["text", "textarea", "code", "sqlcode"].includes(f.type) ? ` maxlength="${+f.max}"` : "";
  let input;
  if (f.type === "textarea") input = `<textarea id="${id}" rows="3"${ro}${req}${len}>${esc(val)}</textarea>`;
  // A company, or every company (the empty choice): the companies in use by code, and the one saved even if stopped.
  else if (f.type === "company") input = `<select id="${id}"${lock ? " disabled" : ""}><option value="">Every company</option>${companyChoices(val).map(x =>
    `<option value="${x.id}" ${String(x.id) === val ? "selected" : ""}>${esc(x.code)} · ${esc(x.name)}${isActive(x) ? "" : " (stopped)"}</option>`).join("")}</select>`;
  // A code as SQL Account has it: typed in capitals (data-upper).
  else if (f.type === "sqlcode") input = `<input id="${id}" type="text" class="mono" value="${esc(val)}" spellcheck="false" autocomplete="off" data-upper${ro}${req}${len}>`;
  // Words: typed with commas between them, saved as a list.
  else if (f.type === "words") input = `<input id="${id}" type="text" value="${esc(asList(v).join(", "))}" spellcheck="false" autocomplete="off"${ro}${req}>`;
  else if (f.type === "bool" || f.type === "select") {
    const sel = f.type === "bool" ? (val === "" ? "0" : String(+val ? 1 : 0)) : val;
    let opts = f.type === "bool" ? [[1, "Yes"], [0, "No"]] : fieldOptions(f);
    if (sel !== "" && !opts.some(o => optVal(o[0]) === sel)) {  // a value no longer offered (a type stopped since) stays as it is
      const was = fieldOptions(f, true).find(o => optVal(o[0]) === sel);
      const gone = f.options_from !== "categories" || !catActive(sel);  // a type in use but not offered here isn't stopped
      opts = [...opts, was ? [was[0], gone ? `${was[1]} (stopped)` : was[1]] : [sel, sel]];
    }
    // An optional choice has an empty one, unless the server's choices have it already (No legal deadline, say).
    const blank = f.type === "select" && !f.required && !opts.some(o => optVal(o[0]) === "") ? `<option value="">${f.options_from === "parties" ? "(none)" : "—"}</option>` : "";
    input = `<select id="${id}"${lock ? " disabled" : ""}>${blank}${opts.map(([k, l]) => `<option value="${esc(optVal(k))}" ${optVal(k) === sel ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  } else {
    const type = { number: "number", money: "number", day: "number", month: "month", date: "date" }[f.type] || "text";
    const extra = f.type === "money" ? ` step="0.01"` : f.type === "day" ? ` min="1" max="31" step="1"`
      : f.type === "number" ? ` step="any"${f.max != null ? ` max="${+f.max}"` : ""}` : f.type === "code" ? ` class="mono" spellcheck="false" autocomplete="off"` : "";
    input = `<input id="${id}" type="${type}" value="${esc(val)}"${extra}${ro}${req}${len}>`;
  }
  const hint = f.hint || (f.type === "words" ? "Separate the words with commas." : "");
  return `<label class="field${lock ? " locked" : ""}"${wide}><span>${esc(f.label)}</span>${input}${hint ? `<span class="note">${esc(hint)}</span>` : ""}${lock ? `<span class="note">${esc(lock)}</span>` : ""}</label>`;
}
// What an input holds, as the field's type: numbers, 0 or 1, null for an empty date, month or number, a list of words.
function fieldValue(f, el) {
  const v = el.value;
  if (f.type === "words") return splitWords(v);
  if (f.type === "bool") return +v ? 1 : 0;
  if (NUM_TYPES.includes(f.type)) return v.trim() === "" ? null : Number(v);
  if (f.type === "month" || f.type === "date") return v || null;
  if (f.type === "company") return v === "" ? null : +v;
  if (f.type === "sqlcode") return v.trim().toUpperCase() || null;
  if (f.type === "select") { if (v === "") return null; const o = fieldOptions(f, true).find(x => optVal(x[0]) === v); return o ? o[0] : v; }
  return v.trim();
}
function formValues(fields, pre) {
  const out = {};
  for (const f of fields) { const el = document.getElementById(pre + f.key); if (el) out[f.key] = fieldValue(f, el); }
  return out;
}

// The reason asked before a stop, use again, delete or tidy up: its own form, so Enter in it doesn't save the record.
const whyForm = () => `<form id="setupWhy" class="row setup-why" hidden><label class="field"><span>Why are you making this change?</span><input id="su-reason" maxlength="500" autocomplete="off"></label>
  <button class="btn" type="submit" id="su-why-go"></button><button class="ghost" type="button" data-why-cancel="1">Cancel</button></form>`;
// Shows the reason box under the button clicked; run(reason) does the change once a reason is given.
function askWhy(btn, label, run) {
  const f = $("#setupWhy");
  if (!f) return;
  (btn.closest(".adv-row") || btn.closest(".row") || btn).after(f);
  $("#su-why-go").textContent = label; f.hidden = false; state.why = run; $("#su-reason").focus();
}
function hideWhy() {
  const f = $("#setupWhy");
  if (f) { f.hidden = true; $("#su-reason").value = ""; }
  state.why = null;
}
async function whySubmit() {
  const inp = $("#su-reason"), goBtn = $("#su-why-go"), reason = inp.value.trim();
  if (!reason) { toast("Say why you're making this change.", true); inp.focus(); return; }
  const run = state.why;
  if (!run) return hideWhy();
  goBtn.disabled = true;
  try { await run(reason); hideWhy(); } catch (e) { toast(e.message, true); } finally { if (goBtn.isConnected) goBtn.disabled = false; }
}

// After a company, bank account, payment type, document type, matching words, customer or supplier, or GL account
// change: the page's copy of them is read again (the labels and pickers), and a company stopped or deleted while it was
// showing gives way to the first one in use.
async function afterSetupChange(kind) {
  if (!["entities", "accounts", "payment_types", "doc_types", "guess_words", "hint_words", "filing_words", "parties", "gl_accounts"].includes(kind)) return;
  state.meta = await api("/api/meta");
  const e = ent();
  if (!e || !isActive(e)) state.entity = firstEntityId();
  renderNav();
}

// The drawer of one company or bank account (id "new" to add one). keep: what was typed in it and not saved yet, when
// it is drawn again after a stop or use again; notes: what the server said about the save just made.
async function openSetup(kind, id, { force = false, keep = {}, notes = [] } = {}) {
  if (!force && !mayLeave()) return;
  const spec = state.setup.types?.kinds?.[kind];
  if (!spec) return;
  const isNew = id === "new", e = ent();
  if (spec.per_entity && !e) return toast("Add a company first.", true);
  const fresh = Object.fromEntries((spec.fields || []).filter(f => f.default !== undefined).map(f => [f.key, f.default]));
  // A new record's company field starts on the company being viewed (every company is chosen in it).
  for (const f of spec.fields || []) if (f.type === "company" && fresh[f.key] == null && e) fresh[f.key] = e.id;
  const r = isNew ? { record: fresh, used_by: [], locked: {}, can_delete: false, notes: [] } : await api(`/api/setup/${kind}/${id}`);
  const rec = r.record || {}, locked = r.locked || {}, fields = spec.fields || [];
  const stopped = !isNew && (rec.status === "stopped" || !isActive(rec));
  state.openPayment = null; state.why = null; state.setup.id = id;
  const name = isNew ? `New ${lowerFirst(spec.label)}` : rec[spec.name_field] || "(no name)";
  const allNotes = [...(r.notes || []), ...(notes || []).filter(n => !(r.notes || []).includes(n))];
  const tidy = kind === "entities" && !isNew && rec.first_month;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">${esc(spec.label)}${spec.per_entity ? " · " + esc(e.code) : ""}</div><h2>${esc(name)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : `<div class="row">${stopped ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(rec)}</div>`}</div>
    ${spec.help ? `<div class="note">${esc(spec.help)}</div>` : ""}
    <form class="form setup-form" id="setupForm">${fields.map(f => fieldHtml(f, rec[f.key] ?? null, locked[f.key], "su-")).join("")}
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">${isNew ? `Add ${esc(lowerFirst(spec.label))}` : "Save"}</button></div></form>
    ${allNotes.map(n => `<div class="note">${esc(n)}</div>`).join("")}
    ${isNew ? "" : `<div><h3>Where used</h3>${usedHtml(r.used_by)}</div>
    <div class="row">${stopped ? `<button class="ghost" type="button" data-setup-act="use">Use again</button>` : r.can_stop === false ? "" : `<button class="ghost" type="button" data-setup-act="stop">Stop using</button>`}
      ${r.can_delete && !+rec.system ? `<button class="btn danger small" type="button" data-setup-act="delete">Delete</button>` : ""}
      ${tidy ? `<button class="ghost" type="button" data-setup-act="tidy">Tidy up months before this</button>` : ""}</div>
    ${+rec.system ? `<div class="note">The app's own rules rely on this ${esc(lowerFirst(spec.label))}, so it can't be deleted.</div>` : ""}
    ${tidy ? `<div class="note">Tidy up removes, from the months before the first month tracked, the payments with no paid date, documents, SQL voucher or bank line, and the checklist items not ticked with no documents.</div>` : ""}
    ${whyForm()}
    ${histSection(spec.table, id)}`}`;
  $("#drawer").hidden = false;
  state.setup.drawer = { kind, id, locked, loaded: formValues(fields, "su-") };
  watchDrawer(keep);
}

// Save: a new record is added; one already there sends only the fields changed.
async function setupSave() {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind], now = formValues(spec.fields || [], "su-");
  if (D.id === "new") {
    // Empty fields are left out, but a company field always goes: empty there means every company.
    const isCompany = k => (spec.fields || []).some(f => f.key === k && f.type === "company");
    const body = { fields: Object.fromEntries(Object.entries(now).filter(([k, v]) => v !== null && v !== "" || isCompany(k))) };
    if (spec.per_entity) body.entity_id = state.entity;
    const r = await api(`/api/setup/${D.kind}`, { json: body });
    toast(`${spec.label} added`);
    await afterSetupChange(D.kind); await render();
    return r.id == null ? closeDrawer(true) : openSetup(D.kind, r.id, { force: true });
  }
  const fields = {};
  for (const k in now) if (!(k in D.locked) && JSON.stringify(now[k]) !== JSON.stringify(D.loaded[k])) fields[k] = now[k];
  if (!Object.keys(fields).length) return toast("Nothing has changed.");
  const r = await api(`/api/setup/${D.kind}/${D.id}`, { method: "PATCH", json: { fields } });
  toast("Saved");
  await afterSetupChange(D.kind); await render();
  return openSetup(D.kind, D.id, { force: true, notes: r.notes });
}

// Stop using, Use again and Delete ask why first; Tidy up counts first, then asks.
async function setupAct(act, btn) {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind];
  if (act === "tidy") return tidyMonths(D.id, btn);
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  return askWhy(btn, label, async reason => {
    if (act === "delete") {
      await api(`/api/setup/${D.kind}/${D.id}`, { method: "DELETE", json: { reason } });
      closeDrawer(true); toast(`${spec.label} deleted`);
      await afterSetupChange(D.kind); return render();
    }
    await api(`/api/setup/${D.kind}/${D.id}/${act}`, { json: { reason } });
    toast(act === "stop" ? "Stopped. Its history stays." : "In use again");
    const keep = drawerEdits();
    await afterSetupChange(D.kind); await render();
    return openSetup(D.kind, D.id, { force: true, keep });
  });
}

// Tidy up before a company's first month tracked: the first click counts what would go, the second asks why.
async function tidyMonths(eid, btn) {
  const e = state.meta.entities.find(x => x.id === +eid);
  if (btn.dataset.armed !== "1") {
    const n = await api(`/api/months/tidy?entity=${eid}`), before = n.before ? monthName(n.before) : "the first month tracked";
    if (!n.payments && !n.tasks) return toast(`Nothing to tidy up before ${before}.`);
    btn.dataset.armed = "1"; btn.textContent = `Click again to remove ${n.payments} payments and ${n.tasks} checklist items before ${before}`; return;
  }
  return askWhy(btn, "Remove them", async reason => {
    const r = await api("/api/months/tidy", { json: { entity_id: +eid, reason } });
    toast(`Removed ${r.payments} payments and ${r.tasks} checklist items from ${e?.code || "the company"}`);
    const keep = drawerEdits();
    await render(); return openSetup("entities", eid, { force: true, keep });
  });
}

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
function openPaste(kind, { force = false } = {}) {
  if (!force && !mayLeave()) return;
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
  $("#drawer").hidden = false;
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
    catch (e) { if (current()) paintPaste(); throw e; }
    if (!current()) return;  // changed (or read again) while it was read: that preview is stale
    P.preview = r; P.previewFor = form; return paintPaste();
  }
  const r = await api(`/api/setup/${P.kind}/paste`, { json: body });
  if (r.message) return toast(r.message, true);  // nothing was saved: the drawer stays open
  const kind = P.kind;
  toast(pasteCounts(r.counts));
  closeDrawer(true);
  await afterSetupChange(kind); return render();
}

// General settings: one form; Save sends only what changed.
async function setupSettings(box) {
  const s = await api("/api/setup/settings"), fields = s.fields || setupSpec()?.fields || [];
  box.innerHTML = `<div class="card"><h1>General settings</h1>
    <div class="note">These apply to every company. Each change is kept in the audit trail.</div>
    <form class="form setup-form" id="settingsForm">${fields.map(f => fieldHtml(f, s.values?.[f.key], null, "gs-")).join("")}
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
  state.meta = await api("/api/meta"); paintOrg();
  if ("cycle_rollover_day" in values && currentCycle() !== was) {
    if (state.month === was) state.month = currentCycle();
    await openCycleMonths();
  }
  renderNav();
  toast("Saved"); return render();
}

/* Move setup: this install's setup saved as one file (setup.json) to start another install with, and such a file
   imported into records that hold no company yet (hrp/setupfile.py). The template holds the rules only; everything adds
   the companies and what belongs to them, and the recurring payments only when ticked. Saving one is an ordinary
   download (the server notes it in the audit trail); an import is previewed first and asks why. */
const moveHref = (what, extra) => `/api/setup/export?what=${what}${extra}`;
async function setupMove(box) {
  const st = await api("/api/setup/import"), M = state.setup.move ||= { payees: false, from: "", preview: null };
  const list = state.meta.entities || [];
  box.innerHTML = `<div class="card"><h1>Move setup</h1>
    <div class="note">Save this install's setup as a file, to start another install with it. Each file saved is noted in the audit trail.</div>
    <h3>Template</h3>
    <div class="note">The rules only: payment types, document types and the documents each needs, a starter checklist, the joiner and leaver reminders, the matching words and the general settings. No company, bank account, customer, supplier or person.</div>
    <div class="form setup-form"><label class="field" style="grid-column:1/-1"><span>Starter checklist</span><select id="mv-from"><option value="">The one new companies get here</option>${list.map(e => `<option value="${e.id}"${String(e.id) === M.from ? " selected" : ""}>${esc(e.code)} · ${esc(e.name)}'s checklist</option>`).join("")}</select>
      <span class="note">Companies added in the other install start with it.</span></label></div>
    <div class="row"><a class="btn" id="mvTemplate" href="${esc(moveHref("template", M.from ? `&entity=${M.from}` : ""))}">Export template</a></div>
    <h3>Everything</h3>
    <div class="note">The template, plus the companies, their bank accounts with the account numbers, charts of accounts, customers and suppliers, and each company's checklist. Keep the file safe.</div>
    <label class="row"><input type="checkbox" id="mv-payees"${M.payees ? " checked" : ""}><span>Include recurring payments (staff names, amounts, bank details)</span></label>
    <div class="note warn" id="mv-warn"${M.payees ? "" : " hidden"}>The file then holds personal data. Keep it as safe as a backup and delete it once it has been imported.</div>
    <div class="row"><a class="btn" id="mvFull" href="${esc(moveHref("full", M.payees ? "&payees=1" : ""))}">Export everything</a></div></div>
  <div class="card"><h1>Import a setup file</h1>
    ${st.empty ? `<div class="note">For a new install, before any company is added. A template's rules are added to the app's own; everything also adds its companies and what belongs to them. Each row is checked as Setup checks it, and nothing is saved unless every row passes.</div>
      <div class="row"><button class="btn" type="button" data-move-pick="1">Choose a setup file…</button></div>
      <div id="mvPreview">${movePreviewHtml()}</div>${whyForm()}`
    : `<div class="note">A setup file is imported only into new records, before any company is added. These hold ${esc((st.holding || []).map(([w, n]) => `${n} ${w}`).join(", "))}.</div>`}</div>`;
}
// What the file chosen would add (the server made the import and undid it), with Import and Cancel.
function movePreviewHtml() {
  const M = state.setup.move, p = M?.preview;
  if (!p) return "";
  const rows = (p.counts || []).filter(([, n]) => +n).map(([w, n]) => `<tr><td>${esc(w.charAt(0).toUpperCase() + w.slice(1))}</td><td class="num">${esc(n)}</td></tr>`).join("");
  return `<h3>${esc(M.name)}</h3><div class="note">${p.what === "full" ? "Everything" : "A template"}, saved ${esc(fmtDate(p.made))}. Importing it adds or changes:</div>
    <div class="tbl-wrap"><table><tbody>${rows}</tbody></table></div>${(p.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join("")}
    <div class="row"><button class="btn" type="button" data-move-go="1">Import</button><button class="ghost" type="button" data-move-cancel="1">Cancel</button></div>`;
}
async function movePick() {
  const [f] = await pickFile(false);
  if (!f) return;
  const M = state.setup.move;
  let setup;
  try { setup = JSON.parse(await f.text()); } catch { return toast("That file can't be read as a setup file.", true); }
  M.preview = null; M.file = null;
  const p = await api("/api/setup/import", { json: { setup, preview: true } });
  Object.assign(M, { file: setup, name: f.name, preview: p });
  $("#mvPreview").innerHTML = movePreviewHtml();
}
async function moveImport(reason) {
  const M = state.setup.move;
  if (!M?.file) return;
  await api("/api/setup/import", { json: { setup: M.file, reason } });
  Object.assign(M, { file: null, preview: null, name: "" });
  state.meta = await api("/api/meta"); paintOrg();
  state.entity = firstEntityId(); state.setup.types = null;
  toast("Setup imported"); renderNav(); return render();
}

/* Required documents: the documents each payment type needs before a payment counts as complete, for every company or
   for one company of its own. A change starts from a month after the last one filed: the months before it keep the
   rules they had, and filed months never change. */
const reqDocName = k => (state.setup.req?.doc_types || []).find(x => x.key === k)?.label || docLabel(k);
// Since when the set showing has been in force; a type with no set of its own needs what Other needs.
const reqSince = t => t.follows_other ? "Same as Other" : !t.since || t.since === "0000-00" ? "From the start" : `Since ${monthName(t.since)}`;
// The months a set was in force: from from_month until to_month, the month the next set took over (either end open).
function reqRange(h) {
  const from = !h.from_month || h.from_month === "0000-00" ? null : monthName(h.from_month), to = h.to_month ? monthName(shiftMonth(h.to_month, -1)) : null;
  return from && to ? (from === to ? from : `${from} to ${to}`) : from ? `From ${from}` : to ? `Until ${to}` : "From the start";
}
const reqWho = id => id == null ? "all companies" : state.meta.entities.find(e => e.id === +id)?.code || "one company";
// What a change did to the open payments, in words.
function reqAffected(a = {}) {
  const miss = +a.now_missing || 0, done = +a.now_complete || 0, s = n => n === 1 ? "" : "s", is = n => n === 1 ? "is" : "are";
  if (!miss && !done) return "Saved. No open payment changes status.";
  const m = miss ? `${miss} open payment${s(miss)} now miss${miss === 1 ? "es" : ""} a document` : "";
  const c = !done ? "" : miss ? `${done} ${is(done)} now complete` : `${done} open payment${s(done)} ${is(done)} now complete`;
  return `Saved. ${[m, c].filter(Boolean).join("; ")}.`;
}

async function setupRequired(box) {
  const S = state.setup, live = state.meta.entities.filter(isActive);
  if (S.reqScope != null && !live.some(e => e.id === S.reqScope)) S.reqScope = null;
  const d = S.req = await api(`/api/setup/required?entity=${S.reqScope ?? ""}`);
  const co = S.reqScope != null ? live.find(e => e.id === S.reqScope) : null;
  const scopeBtn = (v, label, on, title = "") => `<button class="${on ? "btn" : "ghost"} small" data-req-scope="${v}"${title ? ` title="${esc(title)}"` : ""}>${esc(label)}</button>`;
  const types = [...d.types.filter(isActive), ...d.types.filter(t => !isActive(t))];
  const chips = t => t.docs?.length ? `<div class="row" style="gap:4px">${t.docs.map(k => `<span class="chip">${esc(reqDocName(k))}</span>`).join("")}</div>` : `<span class="muted">None</span>`;
  const row = t => `<tr${isActive(t) ? "" : ` class="muted"`}>
      <td><b>${esc(t.label || t.key)}</b>${t.direction === "in" ? ` <span class="pill ok">Money in</span>` : ""}${isActive(t) ? "" : ` <span class="pill grey">Stopped</span>`}</td>
      <td>${chips(t)}</td><td>${esc(reqSince(t))}</td>
      ${co ? `<td>${t.own ? `<span class="pill">Its own set</span>` : `<span class="muted">Follows all companies</span>`}</td>` : ""}
      <td><button class="ghost small" data-req-edit="${esc(t.key)}">Edit</button></td></tr>`;
  box.innerHTML = `<div class="card"><h1>Required documents</h1>
    <div class="note">The documents each type of payment needs before it counts as complete. A change starts from a month you choose: the months before it keep the documents they needed, and filed months never change.</div>
    <div class="row noprint">${scopeBtn("all", "All companies", !co)}${live.map(e => scopeBtn(e.id, e.code, co?.id === e.id, e.name)).join("")}</div>
    ${co ? `<div class="note">${esc(co.code)} follows the documents set for all companies, unless it has its own set for a type.</div>` : ""}
    <div class="tbl-wrap"><table><thead><tr><th>Type of payment</th><th>Documents needed</th><th>In force</th>${co ? `<th>For ${esc(co.code)}</th>` : ""}<th></th></tr></thead><tbody>
      ${types.map(row).join("") || `<tr><td colspan="${co ? 5 : 4}" class="empty">No payment types yet.</td></tr>`}
    </tbody></table></div></div>`;
}

// The drawer of one payment type's documents, for the scope showing: the document types in use in pack order, ticked
// when in the set; the month the change starts; its history.
function openRequired(key, { force = false, keep = {} } = {}) {
  if (!force && !mayLeave()) return;
  const S = state.setup, d = S.req, t = d?.types.find(x => x.key === key);
  if (!t) return;
  const co = d.scope != null ? state.meta.entities.find(e => e.id === +d.scope) : null;
  const pack = (d.doc_types || []).filter(isActive), set = t.docs || [];
  const gone = set.filter(k => !pack.some(x => x.key === k));  // stopped since: they can't be listed again
  const box = x => `<label class="row tight"><input type="checkbox" id="rq-doc-${esc(x.key)}" ${set.includes(x.key) ? "checked" : ""}>
      <span>${esc(x.label || x.key)}${+x.from_sql ? ` <span class="muted">(from SQL, only for companies kept in SQL)</span>` : ""}</span></label>`;
  const hist = (t.history || []).map(h => `<li>${esc(reqRange(h))}, ${esc(reqWho(h.entity_id))}: ${h.docs?.length ? h.docs.map(k => esc(reqDocName(k))).join(", ") : "none"}</li>`).join("");
  state.openPayment = null; state.why = null; S.drawer = null; S.reqOpen = key;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Required documents · ${co ? esc(co.code) : "All companies"}</div><h2>${esc(t.label || t.key)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      <div class="row">${isActive(t) ? "" : `<span class="pill grey">Stopped</span>`}${co ? (t.own ? `<span class="pill">Its own set</span>` : `<span class="pill grey">Follows all companies</span>`) : ""}<span class="muted">${esc(reqSince(t))}</span></div></div>
    <form class="form setup-form" id="reqForm">
      <div role="group" aria-label="Documents needed" class="req-docs"><span class="muted">Documents needed</span>
        ${pack.map(box).join("") || `<div class="note">No document types in use.</div>`}</div>
      ${gone.length ? `<div class="note" style="grid-column:1/-1">No longer in use, so left out when you save: ${gone.map(k => esc(reqDocName(k))).join(", ")}.</div>` : ""}
      <label class="field"><span>From which month?</span><input id="rq-from" type="month" value="${esc(d.default_from || "")}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">Months before this keep their current rules. Filed months never change.</span></label>
      <label class="field"><span>Why are you making this change? (optional)</span><input id="rq-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">Save</button>
        ${co && t.own ? `<button class="ghost" type="button" data-req-follow="${esc(key)}">Follow all companies again</button>` : ""}</div></form>
    ${co ? `<div class="note">${t.own ? `Follow all companies again ends ${esc(co.code)}'s own set from the month above.` : `Saving gives ${esc(co.code)} its own set for this type from the month above.`}</div>` : ""}
    ${t.follows_other ? `<div class="note">This type has no documents set of its own, so it needs what Other needs. Saving gives it its own set.</div>` : ""}
    ${isActive(t) ? "" : `<div class="note">This type is stopped. Its payments still need the documents set for it.</div>`}
    <div><h3>History</h3>${hist ? `<ul class="used">${hist}</ul>` : `<div class="note">Nothing recorded yet.</div>`}</div>`;
  $("#drawer").hidden = false;
  watchDrawer(keep);
}

// Save (follow: the company follows all companies again): the ticked documents, in the set's order with those newly
// ticked after them in pack order.
async function reqSave(follow) {
  const S = state.setup, d = S.req, key = S.reqOpen, t = d?.types.find(x => x.key === key);
  if (!t) return;
  const from = $("#rq-from").value;
  if (!/^\d{4}-\d{2}$/.test(from)) throw new Error("Choose the month the change starts from.");
  let docs = null;
  if (!follow) {
    const on = k => !!document.getElementById("rq-doc-" + k)?.checked, pack = (d.doc_types || []).filter(isActive).map(x => x.key), set = t.docs || [];
    docs = [...set.filter(k => pack.includes(k) && on(k)), ...pack.filter(k => on(k) && !set.includes(k))];
  }
  const body = { payment_type: key, entity_id: d.scope ?? null, docs, from_month: from }, reason = $("#rq-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/required", { json: body });
  closeDrawer(true); toast(reqAffected(r.affected));
  return render();
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
const reloadMeta = async () => { state.meta = await api("/api/meta").catch(() => state.meta); };

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
const NO_DEADLINE = ["statements", "statements_balanced", "reconciled", "pack"];
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

/* ---- Monthly checklist ---- */
const chkDocName = k => setupDocName(state.setup.chk, k);
const chkCompletion = k => (state.setup.chk?.completions || []).find(c => c.key === k)?.label || k;

async function setupChecklist(box) {
  const S = state.setup, e = ent();
  if (!e) { box.innerHTML = `<div class="card"><h1>Monthly checklist</h1><div class="note">Add a company first.</div></div>`; return; }
  const d = S.chk = await api(`/api/setup/checklist?entity=${state.entity}`);
  const code = d.code || e.code, items = d.items || [];
  // A company added in Setup starts with the starter checklist: while it is untouched and no month is set up, a copy may replace it.
  const copy = (d.replaceable || !items.some(it => it.in_use || termOn(it))) && (d.others || []).length;
  const row = it => {
    const t = it.now || {}, rule = asRule(t.rule);
    return `<tr${termOn(it, d.default_from) ? "" : ` class="muted"`}><td><button class="link" data-chk-open="${it.id}">${esc(t.title || it.code)}</button></td>
      <td>${esc(dueText(t))}${+t.deadline && !NO_DEADLINE.includes(it.completion) ? `<div class="note">Deadline${t.submit_as ? ` · submitted as ${esc(t.submit_as)}` : ""}</div>` : ""}</td>
      <td>${esc(chkCompletion(it.completion))}${it.completion === "payments" && rule?.name?.[1] ? `<div class="note">${esc(rule.name[1])}</div>` : ""}</td>
      <td>${docChips(asList(t.docs), chkDocName)}</td><td>${termPills(it, d.default_from)}</td></tr>`;
  };
  box.innerHTML = `${entityPicker()}
    <div class="card"><div class="row spread"><h1>Monthly checklist · ${esc(code)}</h1>
      <div class="row">${copy ? `<button class="ghost" data-chk-copy="1">Copy from another company</button>` : ""}<button class="btn" data-chk-new="1">Add item</button></div></div>
      <div class="note">What each month's checklist holds for ${esc(code)}, in order. Click an item to change it. A change starts from a payroll month you choose: the months before it keep the checklist they had, and filed months never change.</div>
      <div class="row">${deletedToggle("checklist")}</div>
      <div class="tbl-wrap"><table><thead><tr><th>Item</th><th>Due</th><th>Done when</th><th>Documents</th><th>Status</th></tr></thead><tbody>
        ${items.map(row).join("") || `<tr><td colspan="5" class="empty">${esc(code)} has no monthly checklist yet. Add an item${copy ? ", or copy another company's checklist" : ""}.</td></tr>`}
      </tbody></table></div><div id="setupDeleted"></div></div>`;
  drawDeleted("checklist");
}

// The payments rule of an item done by its payments: which payments it covers and what each needs.
function ruleHtml(rule) {
  const d = state.setup.chk, cats = asList(rule.categories), rd = asList(rule.docs), ro = asList(rule.on_item), names = asList(rule.name);
  const types = pickTypes(d.payment_types, cats), docs = pickTypes((d.doc_types || []), [...rd, ...ro]);
  const dir = rule.direction || "";
  return `<fieldset class="chk-rule" id="cl-rule"><legend>Which payments, and what each needs</legend>
    <div role="group" aria-label="Payment types covered" class="req-docs"><span class="muted">Payment types covered (none ticked: any type)</span>
      ${types.map(x => tickBox("cl-rt-" + x.key, x, cats.includes(x.key))).join("") || `<div class="note">No payment types in use.</div>`}</div>
    <label class="field"><span>Money</span><select id="cl-rdir"><option value="">Either</option><option value="out" ${dir === "out" ? "selected" : ""}>Money out</option><option value="in" ${dir === "in" ? "selected" : ""}>Money in</option></select></label>
    <label class="field"><span>Words in the description or payee</span><input id="cl-rwords" value="${esc(asList(rule.words).join(", "))}" spellcheck="false" autocomplete="off" placeholder="KWSP, KUMPULAN WANG">
      <span class="note">Whole words, with commas between them. Empty: any payment of the types above.</span></label>
    <div role="group" aria-label="Documents each payment needs" class="req-docs"><span class="muted">Each payment needs (at least one)</span>
      ${docs.map(x => tickBox("cl-rd-" + x.key, x, rd.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}</div>
    <div role="group" aria-label="Documents that may be filed on the item instead" class="req-docs"><span class="muted">Of these, may be filed on this item instead</span>
      ${docs.map(x => tickBox("cl-ro-" + x.key, x, ro.includes(x.key), ` data-ro="${esc(x.key)}"`)).join("")}<div class="note" id="cl-ro-none">Tick a document each payment needs first.</div></div>
    <label class="row tight" style="grid-column:1/-1"><input type="checkbox" id="cl-rpaid" ${rule.paid ? "checked" : ""}><span>A paid payment counts without its documents</span></label>
    <label class="field" style="grid-column:1/-1"><span>With no such payment in the month, it is done once the statements are in, saying</span><input id="cl-rnone" maxlength="200" value="${esc(rule.none || "")}" placeholder="no overseas claims this month">
      <span class="note">Leave it empty when the month always has such a payment.</span></label>
    <label class="field"><span>What one is called</span><input id="cl-rname1" maxlength="80" value="${esc(names[0] || "")}" placeholder="KWSP payment"></label>
    <label class="field"><span>What several are called</span><input id="cl-rname2" maxlength="80" value="${esc(names[1] || "")}" placeholder="KWSP payments"></label>
  </fieldset>`;
}

// The drawer of one checklist item (id "new" to add one). keep: what was typed and not saved, when it is drawn again
// after a stop or use again; saved: what the last save did.
function openChecklist(id, { force = false, keep = {}, saved = null } = {}) {
  if (!force && !mayLeave()) return;
  const S = state.setup, d = S.chk;
  if (!d) return;
  const isNew = id === "new", it = isNew ? null : (d.items || []).find(x => x.id === +id);
  if (!isNew && !it) return closeDrawer(true);
  // The month shown: the one typed before it was drawn again, else the earliest not filed; the term in force then.
  const m0 = /^\d{4}-\d{2}$/.test(keep["cl-from"] || "") ? keep["cl-from"] : d.default_from || "";
  const t = (it && termAt(it, m0)) || { title: "", detail: "", due_offset: 0, due_day: "", docs: [], deadline: 0, submit_as: null, rule: null };
  // Built-in completions have a code of their own: a company has each at most once.
  const offered = (d.completions || []).filter(c => !c.code || !(d.items || []).some(x => x.code === c.code));
  const completion = isNew ? offered[0]?.key || "hand" : it.completion, on = isNew || termOn(it, m0);
  const used = +it?.used || 0, code = d.code || ent()?.code || "";
  state.openPayment = null; state.why = null; S.drawer = null; S.remOpen = null; S.chkOpen = { id: isNew ? "new" : it.id, completion, term: isNew ? null : t, on };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Monthly checklist · ${esc(code)}</div><h2>${isNew ? "Add item" : esc(t.title || it.code)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : termPills(it, d.default_from)}</div>
    ${saved ? effectCard(saved, saved.head || "Saved", "checklist item") : ""}
    <form class="form setup-form" id="chkForm">
      ${isNew ? `<label class="field" style="grid-column:1/-1"><span>Done when</span><select id="cl-completion">${offered.map(c => `<option value="${esc(c.key)}">${esc(c.label)}</option>`).join("")}</select>
          <span class="note">Fixed once the item is added. A company has each of the built-in ones once at most.</span></label>`
        : `<label class="field locked" style="grid-column:1/-1"><span>Done when</span><input value="${esc(chkCompletion(completion))}" readonly tabindex="-1"><span class="note">Fixed once the item is added.</span></label>`}
      <label class="field" style="grid-column:1/-1"><span>Title</span><input id="cl-title" maxlength="200" value="${esc(t.title || "")}" required></label>
      <label class="field" style="grid-column:1/-1"><span>Detail</span><textarea id="cl-detail" rows="3" maxlength="2000">${esc(t.detail || "")}</textarea></label>
      <label class="field"><span>Due in</span><select id="cl-off"><option value="0">The payroll month</option><option value="1" ${+t.due_offset ? "selected" : ""}>The month after</option></select></label>
      <label class="field"><span>Day of the month</span><input id="cl-day" type="number" min="1" max="31" step="1" value="${esc(t.due_day ?? "")}" required><span class="note">A shorter month uses its last day.</span></label>
      <div role="group" aria-label="Documents for this item" class="req-docs" id="cl-docs">${chkDocsHtml(asList(t.docs))}</div>
      <label class="row tight" id="cl-deadline-f" style="grid-column:1/-1"><input type="checkbox" id="cl-deadline" ${+t.deadline ? "checked" : ""}><span>A deadline: Next up shows it from a few days before</span></label>
      <label class="field" id="cl-submit-f" style="grid-column:1/-1"><span>Submitted as (optional)</span><input id="cl-submit" maxlength="30" value="${esc(t.submit_as || "")}" placeholder="KWSP">
        <span class="note">Items due the same day with a name here are one Next up row, e.g. Submit Oct KWSP, PERKESO and e-PCB.</span></label>
      ${isNew || completion === "payments" ? ruleHtml(asRule(t.rule) || {}) : ""}
      <label class="field"><span>From which month?</span><input id="cl-from" type="month" value="${esc(m0)}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">Months before this keep the checklist they had. Filed months never change.${isNew ? "" : " The item shows as it is in this month."}</span><span class="note" id="cl-from-note" hidden></span></label>
      <label class="field"><span>Why are you making this change? (optional)</span><input id="cl-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-chk-preview="1">Preview</button><button class="btn" type="submit">${isNew ? "Add item" : "Save"}</button></div></form>
    <div id="cl-preview" data-preview-out></div>
    ${isNew ? "" : `<div><h3>Where used</h3><div class="note">${used ? `In ${plural(used, "month")} so far.` : "Not in any month yet."}</div></div>
    <div class="row" id="cl-act-row">${chkActRow(it, on)}</div>
    <div class="note" id="cl-act-note">${chkActNote(it, on)}</div>
    ${whyForm()}
    ${termsHtml(it, h => `${h.title}, due the ${dueText(h)}${asList(h.docs).length ? `, ${asList(h.docs).map(chkDocName).join(", ")}` : ""}`)}
    ${histSection("checklist_items", it.id)}`}`;
  $("#drawer").hidden = false;
  if (!isNew) S.chkOpen.filled = termInputs("cl-");  // as filled in, before what was typed is put back
  watchDrawer(keep);
  setupPaint();  // after keep, as what it put back may show or hide parts
}
// The item's documents picker: those in use, plus any chosen that were stopped since.
const chkDocsHtml = docs => `<span class="muted">Documents for this item</span>
  ${pickTypes(state.setup.chk?.doc_types, docs).map(x => tickBox("cl-doc-" + x.key, x, docs.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}`;
// Stop using when the item is in use in the month chosen, else Use again; Delete while never used.
const chkActRow = (it, on) => `${on ? `<button class="ghost" type="button" data-chk-act="stop">Stop using</button>` : `<button class="ghost" type="button" data-chk-act="use">Use again</button>`}
  ${it.can_delete ? `<button class="btn danger small" type="button" data-chk-act="delete">Delete</button>` : ""}`;
const chkActNote = (it, on) => `${on ? "Stopping it leaves it out of the months from the month above on, changes planned for later months included; where something is filed on it or it is ticked, it stays." : "Use again puts it back from the month above, with the wording it had."}
  ${it.can_delete ? "" : +it.system ? " The app relies on it, so it can't be deleted." : " It can't be deleted once it has been used; stop using it instead."}`;
// The term in force in another month, put in the drawer's inputs.
function chkFill(t) {
  $("#cl-title").value = t.title || ""; $("#cl-detail").value = t.detail || "";
  $("#cl-off").value = +t.due_offset ? "1" : "0"; $("#cl-day").value = t.due_day ?? "";
  $("#cl-docs").innerHTML = chkDocsHtml(asList(t.docs));
  $("#cl-deadline").checked = !!+t.deadline; $("#cl-submit").value = t.submit_as || "";
  if ($("#cl-rule")) $("#cl-rule").outerHTML = ruleHtml(asRule(t.rule) || {});
}
function chkMonth() {
  const S = state.setup, O = S.chkOpen;
  if (!O || O.id === "new" || O.id === "copy") return;
  termMonth("cl-", O, (S.chk?.items || []).find(x => x.id === O.id), chkFill, (it, on) => {
    $("#cl-act-row").innerHTML = chkActRow(it, on); $("#cl-act-note").innerHTML = chkActNote(it, on);
  });
}

// The item's fields as typed: all of them (a change sends the whole term); the completion only when adding.
function chkFields(isNew) {
  // The term the inputs were filled in from: its documents and rule keep their order.
  const S = state.setup, d = S.chk, O = S.chkOpen, it = (d.items || []).find(x => x.id === O.id), t = O.term || it?.now || {};
  const comp = $("#cl-completion")?.value ?? O.completion, rule0 = asRule(t.rule) || {}, had = asList(t.docs);
  const day = $("#cl-day").value.trim(), deadline = $("#cl-deadline").checked && !NO_DEADLINE.includes(comp) ? 1 : 0;
  const f = { title: $("#cl-title").value.trim(), detail: $("#cl-detail").value.trim(), due_offset: +$("#cl-off").value, due_day: day === "" ? null : +day,
    docs: ticked("cl-doc-", pickTypes(d.doc_types, had), had), deadline, submit_as: deadline ? $("#cl-submit").value.trim() || null : null, rule: null };
  if (comp === "payments") {
    const rd = asList(rule0.docs), ro = asList(rule0.on_item), list = pickTypes(d.doc_types, [...rd, ...ro]), docs = ticked("cl-rd-", list, rd);
    f.rule = { categories: ticked("cl-rt-", pickTypes(d.payment_types, asList(rule0.categories)), asList(rule0.categories)),
      direction: $("#cl-rdir").value || null, words: splitWords($("#cl-rwords").value), docs,
      on_item: ticked("cl-ro-", list, ro).filter(k => docs.includes(k)), paid: $("#cl-rpaid").checked,
      none: $("#cl-rnone").value.trim() || null, name: [$("#cl-rname1").value.trim(), $("#cl-rname2").value.trim()] };
  }
  if (isNew) f.completion = comp;
  return f;
}

// After a checklist change: the page's copy of the codes is read again, the list drawn again, and the item's drawer
// opened again on what the change did.
async function chkDone(r, id, head, keep = {}) {
  toast(`${head}. ${effectText(r.affected, "checklist item")}`);
  await reloadMeta(); await render();
  if (id != null && (state.setup.chk?.items || []).some(x => x.id === +id)) return openChecklist(+id, { force: true, keep, saved: { ...r, head } });
  closeDrawer(true);
}

// Preview (nothing kept) or Save: adds the item, or changes it from the month chosen.
async function chkSave(preview) {
  const S = state.setup, d = S.chk, O = S.chkOpen;
  if (!d || !O || O.id === "copy") return;
  const isNew = O.id === "new";
  const body = { action: isNew ? "add" : "change", entity_id: d.entity_id ?? state.entity, from_month: fromMonth("#cl-from"), fields: chkFields(isNew), preview: !!preview };
  if (!isNew) body.item_id = O.id;
  const reason = $("#cl-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/checklist", { json: body });
  if (preview) return showPreview("#cl-preview", r, "checklist item");
  // Drawn again on the month the change starts from, so it shows the term just saved.
  return chkDone(r, isNew ? r.item_id : O.id, isNew ? "Item added" : "Saved", { "cl-from": body.from_month });
}

// Stop using, Use again (from the month chosen) and Delete ask why first.
async function chkAct(act, btn) {
  const S = state.setup, d = S.chk, O = S.chkOpen;
  if (!d || !O || O.id === "new" || O.id === "copy") return;
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  if (act !== "delete") fromMonth("#cl-from");
  return askWhy(btn, label, async reason => {
    const body = { action: act, entity_id: d.entity_id ?? state.entity, item_id: O.id, reason };
    if (act !== "delete") body.from_month = fromMonth("#cl-from");
    const r = await api("/api/setup/checklist", { json: body });
    if (act === "delete") { closeDrawer(true); toast("Item deleted"); await reloadMeta(); return render(); }
    const keep = { ...drawerEdits(), "cl-from": body.from_month };
    return chkDone(r, O.id, act === "stop" ? "Stopped" : "In use again", keep);
  });
}

// Copy another company's checklist, for a company with no item in use.
function openChkCopy({ force = false } = {}) {
  if (!force && !mayLeave()) return;
  const S = state.setup, d = S.chk, others = d?.others || [];
  if (!others.length) return;
  const code = d.code || ent()?.code || "";
  state.openPayment = null; state.why = null; S.drawer = null; S.remOpen = null; S.chkOpen = { id: "copy" };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Monthly checklist · ${esc(code)}</div><h2>Copy from another company</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <form class="form setup-form" id="chkCopyForm">
      <label class="field" style="grid-column:1/-1"><span>Copy the checklist of</span><select id="cp-from">${others.map(o => `<option value="${o.id}">${esc(o.code)} · ${esc(o.name)} (${plural(+o.items || 0, "item")})</option>`).join("")}</select>
        <span class="note">Its items in force in the month below are added to ${esc(code)}, with their wording, due dates and documents.${d.replaceable ? ` They replace the starter checklist ${esc(code)} was given.` : ""} You can change them here afterwards.</span></label>
      <label class="field"><span>From which month?</span><input id="cl-from" type="month" value="${esc(d.default_from || "")}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">Months before this keep the checklist they had. Filed months never change.</span></label>
      <label class="field"><span>Why are you making this change? (optional)</span><input id="cl-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-chk-copy-preview="1">Preview</button><button class="btn" type="submit">Copy</button></div></form>
    <div id="cl-preview" data-preview-out></div>`;
  $("#drawer").hidden = false;
  watchDrawer();
}
async function chkCopySave(preview) {
  const d = state.setup.chk;
  if (!d || state.setup.chkOpen?.id !== "copy") return;
  const body = { action: "copy", entity_id: d.entity_id ?? state.entity, from_month: fromMonth("#cl-from"), copy_from: +$("#cp-from").value, preview: !!preview };
  const reason = $("#cl-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/checklist", { json: body });
  if (preview) return showPreview("#cl-preview", r, "checklist item");
  toast(`Checklist copied. ${effectText(r.affected, "checklist item")}`);
  closeDrawer(true); await reloadMeta(); return render();
}

/* ---- Joiner and leaver reminders ---- */
const remDocName = k => setupDocName(state.setup.rem, k);
const REM_HINT = "{name} in the title becomes the person's short name; {date} in the detail becomes the start date or last day. No other braces can be used. The wording doesn't change by itself when you change the days or the salary.";

async function setupReminders(box) {
  const d = state.setup.rem = await api("/api/setup/reminders"), rules = d.rules || [];
  const row = r => {
    const t = r.now || {};
    return `<tr${termOn(r, d.default_from) ? "" : ` class="muted"`}><td><button class="link" data-rem-open="${r.id}">${esc(t.title || r.key)}</button>${r.short_name ? `<div class="note">${esc(r.short_name)}</div>` : ""}</td>
      <td>${r.kind === "leaver" ? "Leaver" : "Joiner"}</td><td>${esc(remDays(t.days, r.kind))}</td><td>${esc(remSalary(t.salary_over))}</td>
      <td>${docChips(asList(t.docs), remDocName)}</td><td>${termPills(r, d.default_from)}</td></tr>`;
  };
  box.innerHTML = `<div class="card"><div class="row spread"><h1>Joiner and leaver reminders</h1><button class="btn" data-rem-new="1">Add reminder</button></div>
    <div class="note">A recurring salary's start date or last day adds these reminders to the checklist, each in the month it falls due, for every company. Click one to change it. A change applies to people starting (or leaving) from a month you choose, and filed months never change.</div>
    <div class="row">${deletedToggle("reminders")}</div>
    <div class="tbl-wrap"><table><thead><tr><th>Reminder</th><th>For</th><th>When</th><th>Salary</th><th>Documents</th><th>Status</th></tr></thead><tbody>
      ${rules.map(row).join("") || `<tr><td colspan="6" class="empty">None yet.</td></tr>`}
    </tbody></table></div><div id="setupDeleted"></div></div>`;
  drawDeleted("reminders");
}

// The drawer of one reminder (id "new" to add one); keep and saved as for a checklist item.
function openReminder(id, { force = false, keep = {}, saved = null } = {}) {
  if (!force && !mayLeave()) return;
  const S = state.setup, d = S.rem;
  if (!d) return;
  const isNew = id === "new", r = isNew ? null : (d.rules || []).find(x => x.id === +id);
  if (!isNew && !r) return closeDrawer(true);
  // The month shown: the one typed before it was drawn again, else the earliest not filed; the term in force then.
  const m0 = /^\d{4}-\d{2}$/.test(keep["rm-from"] || "") ? keep["rm-from"] : d.default_from || "";
  const t = (r && termAt(r, m0)) || { days: "", salary_over: null, title: "", detail: "", docs: [] };
  const kind = isNew ? "joiner" : r.kind, on = isNew || termOn(r, m0), used = +r?.used || 0, days = +t.days || 0;
  state.openPayment = null; state.why = null; S.drawer = null; S.chkOpen = null; S.remOpen = { id: isNew ? "new" : r.id, kind, term: isNew ? null : t, on };
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">Joiner and leaver reminder</div><h2>${isNew ? "Add reminder" : esc(t.title || r.key)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : termPills(r, d.default_from)}</div>
    ${saved ? effectCard(saved, saved.head || "Saved", "reminder") : ""}
    <form class="form setup-form" id="remForm">
      ${isNew ? `<label class="field"><span>Key</span><input id="rm-key" class="mono" maxlength="20" spellcheck="false" autocomplete="off" required placeholder="ecp22">
          <span class="note">Lower-case letters, digits and _, 2 to 20, starting with a letter. Fixed once added.</span></label>
        <label class="field"><span>For</span><select id="rm-kind"><option value="joiner">A joiner (from the start date)</option><option value="leaver">A leaver (from the last day)</option></select>
          <span class="note">Fixed once added.</span></label>`
        : `<label class="field locked"><span>Key</span><input class="mono" value="${esc(r.key)}" readonly tabindex="-1"><span class="note">Fixed once added.</span></label>
        <label class="field locked"><span>For</span><input value="${kind === "leaver" ? "A leaver (from the last day)" : "A joiner (from the start date)"}" readonly tabindex="-1"><span class="note">Fixed once added.</span></label>`}
      <label class="field" style="grid-column:1/-1"><span>Short name</span><input id="rm-short" maxlength="40" value="${esc(r?.short_name || "")}" placeholder="e-CP22">
        <span class="note">Next up names reminders due together by their short names, and the recurring payment drawer lists them.</span></label>
      <label class="field"><span>Number of days</span><input id="rm-days" type="number" min="0" max="366" step="1" value="${t.days === "" || t.days == null ? "" : Math.abs(days)}" required>
        <span class="note">0 is on the day itself.</span></label>
      <label class="field"><span>Before or after <span id="rm-what">${kind === "leaver" ? "the last day" : "the start date"}</span></span><select id="rm-when"><option value="after">After</option><option value="before" ${days < 0 ? "selected" : ""}>Before</option></select></label>
      <label class="field" style="grid-column:1/-1"><span>Only when the monthly salary is over (optional)</span><input id="rm-salary" type="number" step="0.01" min="0" value="${esc(t.salary_over ?? "")}">
        <span class="note">Leave it empty for any salary.</span></label>
      <label class="field" style="grid-column:1/-1"><span>Title</span><input id="rm-title" maxlength="200" value="${esc(t.title || "")}" required placeholder="Submit e-CP22 for {name}"></label>
      <label class="field" style="grid-column:1/-1"><span>Detail</span><textarea id="rm-detail" rows="3" maxlength="2000" required>${esc(t.detail || "")}</textarea>
        <span class="note">${esc(REM_HINT)}</span></label>
      <div role="group" aria-label="Documents for this reminder" class="req-docs" id="rm-docs">${remDocsHtml(asList(t.docs))}</div>
      <label class="field" style="grid-column:1/-1"><span>For people starting (or leaving) from which month?</span><input id="rm-from" type="month" value="${esc(m0)}"${d.first_allowed ? ` min="${esc(d.first_allowed)}"` : ""} required>
        <span class="note">The month of the start date or last day. People starting or leaving before it keep the reminders they had. Filed months never change.${isNew ? "" : " The reminder shows as it is for this month."}</span><span class="note" id="rm-from-note" hidden></span></label>
      <label class="field" style="grid-column:1/-1"><span>Why are you making this change? (optional)</span><input id="rm-reason" maxlength="500" autocomplete="off"></label>
      <div class="row" style="grid-column:1/-1"><button class="ghost" type="button" data-rem-preview="1">Preview</button><button class="btn" type="submit">${isNew ? "Add reminder" : "Save"}</button></div></form>
    <div id="rm-preview" data-preview-out></div>
    ${isNew ? "" : `<div><h3>Where used</h3><div class="note">${used ? `${plural(used, "reminder")} made so far.` : "No reminder made yet."}</div></div>
    <div class="row" id="rm-act-row">${remActRow(r, on)}</div>
    <div class="note" id="rm-act-note">${remActNote(r, on)}</div>
    ${whyForm()}
    ${termsHtml(r, h => `${h.title}, ${lowerFirst(remDays(h.days, kind))}${h.salary_over == null || h.salary_over === "" ? "" : `, ${lowerFirst(remSalary(h.salary_over))}`}`)}
    ${histSection("people_tasks", r.id)}`}`;
  $("#drawer").hidden = false;
  if (!isNew) S.remOpen.filled = termInputs("rm-");  // as filled in, before what was typed is put back
  watchDrawer(keep);
  setupPaint();
}
const remDocsHtml = docs => `<span class="muted">Documents for this reminder</span>
  ${pickTypes(state.setup.rem?.doc_types, docs).map(x => tickBox("rm-doc-" + x.key, x, docs.includes(x.key))).join("") || `<div class="note">No document types in use.</div>`}`;
// Stop using when the reminder is in use for the month chosen, else Use again; Delete while never used.
const remActRow = (r, on) => `${on ? `<button class="ghost" type="button" data-rem-act="stop">Stop using</button>` : `<button class="ghost" type="button" data-rem-act="use">Use again</button>`}
  ${r.can_delete ? `<button class="btn danger small" type="button" data-rem-act="delete">Delete</button>` : ""}`;
const remActNote = (r, on) => `${on ? "Stopping it leaves it out for people starting (or leaving) from the month above on, changes planned for later months included; one ticked or with something filed on it stays." : "Use again puts it back for people starting (or leaving) from the month above, with the wording it had."}
  ${r.can_delete ? "" : +r.system ? " The app relies on it, so it can't be deleted." : " It can't be deleted once it has been used; stop using it instead."}`;
// The term in force for another month, put in the drawer's inputs.
function remFill(t) {
  const days = +t.days || 0;
  $("#rm-days").value = t.days === "" || t.days == null ? "" : Math.abs(days); $("#rm-when").value = days < 0 ? "before" : "after";
  $("#rm-salary").value = t.salary_over ?? ""; $("#rm-title").value = t.title || ""; $("#rm-detail").value = t.detail || "";
  $("#rm-docs").innerHTML = remDocsHtml(asList(t.docs));
}
function remMonth() {
  const S = state.setup, O = S.remOpen;
  if (!O || O.id === "new") return;
  termMonth("rm-", O, (S.rem?.rules || []).find(x => x.id === O.id), remFill, (r, on) => {
    $("#rm-act-row").innerHTML = remActRow(r, on); $("#rm-act-note").innerHTML = remActNote(r, on);
  });
}

function remFields() {
  // The term the inputs were filled in from: its documents keep their order.
  const S = state.setup, d = S.rem, O = S.remOpen, r = (d.rules || []).find(x => x.id === O.id), had = asList((O.term || r?.now)?.docs);
  const n = $("#rm-days").value.trim(), sal = $("#rm-salary").value.trim();
  return { days: n === "" ? null : Math.abs(+n) * ($("#rm-when").value === "before" ? -1 : 1), salary_over: sal === "" ? null : +sal,
    title: $("#rm-title").value.trim(), detail: $("#rm-detail").value.trim(), docs: ticked("rm-doc-", pickTypes(d.doc_types, had), had) };
}

async function remDone(r, id, head, keep = {}) {
  toast(`${head}. ${effectText(r.affected, "reminder")}`);
  await reloadMeta(); await render();
  if (id != null && (state.setup.rem?.rules || []).some(x => x.id === +id)) return openReminder(+id, { force: true, keep, saved: { ...r, head } });
  closeDrawer(true);
}

// Preview (nothing kept) or Save: adds the reminder, or changes it for people starting (or leaving) from the month chosen.
async function remSave(preview) {
  const S = state.setup, d = S.rem, O = S.remOpen;
  if (!d || !O) return;
  const isNew = O.id === "new";
  const body = { action: isNew ? "add" : "change", short_name: $("#rm-short").value.trim() || null, from_month: fromMonth("#rm-from"), fields: remFields(), preview: !!preview };
  if (isNew) {
    body.key = $("#rm-key").value.trim().toLowerCase(); body.kind = $("#rm-kind").value;
    if (!/^[a-z][a-z0-9_]{1,19}$/.test(body.key)) throw new Error("The key needs 2 to 20 lower-case letters, digits or _, starting with a letter.");
  } else body.id = O.id;
  const reason = $("#rm-reason").value.trim();
  if (reason) body.reason = reason;
  const r = await api("/api/setup/reminders", { json: body });
  if (preview) return showPreview("#rm-preview", r, "reminder");
  // Drawn again on the month the change starts from, so it shows the term just saved.
  const keep = { "rm-from": body.from_month };
  if (!isNew) return remDone(r, O.id, "Saved", keep);
  // A new reminder is found by the id the server gives, else by its key.
  const nid = r.id ?? r.item_id;
  await remDone(r, nid, "Reminder added", keep);
  if (nid == null) { const x = (state.setup.rem?.rules || []).find(y => y.key === body.key); if (x) openReminder(x.id, { force: true, keep, saved: { ...r, head: "Reminder added" } }); }
}

async function remAct(act, btn) {
  const S = state.setup, O = S.remOpen;
  if (!S.rem || !O || O.id === "new") return;
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  if (act !== "delete") fromMonth("#rm-from");
  return askWhy(btn, label, async reason => {
    const body = { action: act, id: O.id, reason };
    if (act !== "delete") body.from_month = fromMonth("#rm-from");
    const r = await api("/api/setup/reminders", { json: body });
    if (act === "delete") { closeDrawer(true); toast("Reminder deleted"); await reloadMeta(); return render(); }
    const keep = { ...drawerEdits(), "rm-from": body.from_month };
    return remDone(r, O.id, act === "stop" ? "Stopped" : "In use again", keep);
  });
}

// The reminders a salary's start date and last day add, by their short names, for the recurring payment drawer.
function reminderNote() {
  if (!Array.isArray(state.meta.people_tasks)) return "A salary's start date and last day also add reminders to the checklist, each in the month it falls due (Setup › Joiner and leaver reminders).";
  const live = state.meta.people_tasks.filter(isActive);
  const name = t => String(t.short_name || t.title || t.key || "").replace(/\{name\}/g, "the person").replace(/\{date\}/g, "the date").trim();
  const of = kind => live.filter(t => t.kind === kind).map(name).filter(Boolean);
  const parts = [of("joiner").length ? `${andList(of("joiner"))} for a joiner` : "", of("leaver").length ? `${andList(of("leaver"))} for a leaver` : ""].filter(Boolean);
  return parts.length ? `A salary's start date and last day also add reminders to the checklist, each in the month it falls due: ${parts.join(", ")}. One due in a month not set up yet shows in the latest month set up until then, without counting there.`
    : "No joiner or leaver reminders are in use, so a start date or last day adds none to the checklist.";
}

// The line above the app's name: the organisation's name from General settings, as saved (empty: no line).
function paintOrg() {
  const el = $("#orgName");
  if (!el || !state.meta?.settings) return;
  const n = String(state.meta.settings.organisation_name || "").trim();
  el.textContent = n; el.hidden = !n;
}

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
const histSection = (tbl, key) => `<details class="hist" data-hist="${tbl}:${key}"><summary><h3>History</h3></summary><div class="hist-body"></div></details>`;

async function openHistory(tbl, key, title) {
  if (!closeDrawer()) return;
  $("#drawer").innerHTML = `<div class="row spread"><div><div class="eyebrow">History</div><h2>${esc(title || "Record")}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div><div id="histOnly" class="note">Loading…</div>`;
  $("#drawer").hidden = false;
  try { const h = await api(`/api/audit/record/${encodeURIComponent(tbl)}/${encodeURIComponent(key)}`); if ($("#histOnly")) $("#histOnly").outerHTML = `<div>${historyHtml(h)}</div>`; }
  catch (e) { if ($("#histOnly")) $("#histOnly").textContent = e.message; }
}

/* ---- Put back a deleted Setup record (hrp/restore.py) ---- */
// The "Show deleted" tick of a Setup section (kept for every section, as Show stopped is).
const deletedToggle = kind => `<label class="row tight"><input type="checkbox" data-setup-deleted="${esc(kind)}" ${state.setup.deleted ? "checked" : ""}> Show deleted</label>`;

// Show deleted: the section's records deleted in this app and not put back since, newest first, with when, who and why,
// and Put it back, or why it can't be now.
async function drawDeleted(kind) {
  const box = $("#setupDeleted");
  if (!box) return;
  if (!state.setup.deleted) { box.innerHTML = ""; return; }
  const per = ["accounts", "parties", "gl_accounts", "checklist", "payees"].includes(kind);
  if (per && !state.entity) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="note">Loading…</div>`;
  try {
    const d = await api(`/api/setup/restore?kind=${encodeURIComponent(kind)}${per ? `&entity=${state.entity}` : ""}`);
    if ($("#setupDeleted") !== box) return;  // another page or section was drawn meanwhile
    const row = r => `<tr><td>${esc(r.name)}</td><td>${esc(fmtWhen(r.at))}<div class="note">Entry ${esc(r.entry)}</div></td><td>${esc(r.actor || "")}</td><td>${esc(r.reason || "")}</td>
      <td><div class="row tight">${r.problem ? "" : `<button class="ghost small" type="button" data-restore="${esc(r.row_id)}" data-restore-title="${esc(r.name)}">Put it back</button>`}
        <button class="ghost small" type="button" data-hist-open="${esc(r.table)}:${esc(r.key)}" data-hist-title="${esc(r.name)}">History</button></div>
        ${r.problem ? `<div class="note">${esc(r.problem)}</div>` : ""}</td></tr>`;
    box.innerHTML = `<h2>Deleted ${esc(d.plural)}</h2>
      <div class="note">Deleted in this app and not put back since, newest first. Putting one back asks why; it comes back as it was, with its history.</div>
      <div class="tbl-wrap"><table><thead><tr><th>Name</th><th>Deleted</th><th>By</th><th>Why</th><th></th></tr></thead><tbody>
        ${d.rows.map(row).join("") || `<tr><td colspan="5" class="empty">None deleted.</td></tr>`}</tbody></table></div>`;
  } catch (e) { box.innerHTML = `<div class="note bad-text">${esc(e.message)}</div>`; }
}

// Put it back (from the audit trail, a record's History or Show deleted): a drawer shows what it would do first (a
// preview: nothing is kept), or why it can't be put back; Put it back then asks why.
async function openRestore(rowId, title) {
  if (!closeDrawer()) return;
  $("#drawer").innerHTML = `<div class="ex-head"><div class="row spread"><div><div class="eyebrow">Put back</div><h2>${esc(title || "Deleted record")}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div></div>
    <div id="rsBody"><div class="note">Loading…</div></div>`;
  $("#drawer").hidden = false;
  let p;
  try { p = await api(`/api/setup/restore/${rowId}`, { json: { preview: true } }); }
  catch (e) { if ($("#rsBody")) $("#rsBody").innerHTML = `<div class="note bad-text">${esc(e.message)}</div>`; return; }
  if (!$("#rsBody")) return;
  const del = p.deleted || {}, a = p.affected || {};
  const touches = (p.lines || []).length || +a.tasks || +a.payments;
  $("#rsBody").innerHTML = `<div class="note">${esc(p.label)} deleted ${esc(fmtWhen(del.at))}${del.actor ? ` by ${esc(del.actor)}` : ""}, in entry ${esc(del.entry)}${del.reason ? `. Why: ${esc(del.reason)}` : ""}.</div>
    <div class="note">It comes back as it was when it was deleted, ${p.same_id ? "with the same number" : `as #${esc(p.id)}`}.</div>
    ${(p.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join("")}
    ${touches ? effectCard(p, "Putting it back also changes", p.kind === "checklist" ? "checklist item" : "reminder") : `<div class="note">Nothing in the months already set up changes.</div>`}
    <div class="row"><button class="btn" type="button" data-restore-go="${esc(rowId)}">Put it back</button>
      <button class="ghost" type="button" data-hist-open="${esc(p.table)}:${esc(del.key)}" data-hist-title="${esc(title || p.name)}">History</button></div>
    ${whyForm()}`;
}
function restoreGo(rowId, btn) {
  return askWhy(btn, "Put it back", async reason => {
    const r = await api(`/api/setup/restore/${rowId}`, { json: { reason } });
    closeDrawer(true);
    toast(`${r.label} put back${r.same_id ? "" : ` as #${r.id}`}`);
    if (["checklist", "reminders", "payees"].includes(r.kind)) await reloadMeta(); else await afterSetupChange(r.kind);
    return render();
  });
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

/* ---------------- Events ---------------- */
document.addEventListener("click", async ev => {
  const t = ev.target.closest("button, tr[data-payment], a");
  if (!t) return;
  const ds = t.dataset;
  if (ds.sort) return sortClick(ds.sort, ds.col, t);
  try {
    if (ds.view) return go(ds.view, ds.entity);
    if (ds.histOpen) { const [tbl, key] = ds.histOpen.split(":"); return openHistory(tbl, key, ds.histTitle); }
    if (ds.restore) return await openRestore(+ds.restore, ds.restoreTitle);
    if (ds.restoreGo) return restoreGo(+ds.restoreGo, t);
    if (ds.packFile) return await openPackCheck(ds.packCheck, ds.packFile);
    if (ds.tx) return toggleEntry(+ds.tx, t);
    if (ds.trailMore) return trailMore(t);
    if (t.id === "trailCheck") return trailCheck(t);
    if (t.id === "trailAccept") return trailAccept(t);
    if (ds.pill) return pillGo(ds.pill, +ds.entity);
    if (ds.nextGo) { const r = state.next?.get(ds.nextGo); return r && goTo(r.go); }
    if (ds.older) { const [e, m] = ds.older.split(" "); return goTo({ view: "entity", entity_id: +e, month: m }); }
    if (ds.nextAll) { const k = nextScope() || 0; state.nextAll[k] = !state.nextAll[k]; return refreshNext(); }
    if (ds.savedBalance) return render();
    if (ds.nextBackup) {
      state.view = "settings"; renderNav(); await render(); $("#bkPw")?.focus();  // the password is typed there; a plain backup is not offsite
      return;
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
    if (ds.setupKind) {
      if (!closeDrawer()) return;
      Object.assign(state.setup, { kind: ds.setupKind, id: null }); renderNav(); return render();
    }
    if (ds.setupNew) return await openSetup(ds.setupNew, "new");
    if (ds.setupPaste) return openPaste(ds.setupPaste);
    if (ds.pasteRead) { t.disabled = true; try { return await pasteSave(true); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.setupOpen) return await openSetup(state.setup.kind, +ds.setupOpen);
    if (ds.setupView) {
      const kind = state.setup.kind;
      state.setup.view[kind] = ds.setupView === "tree" ? "tree" : "flat";
      try { localStorage.setItem("hrp-setup-view-" + kind, state.setup.view[kind]); } catch {}
      await render();
      return document.querySelector(`[data-setup-view="${state.setup.view[kind]}"]`)?.focus({ preventScroll: true });
    }
    if (ds.tree || ds.treeAll) {
      // Opening or closing a heading or an account draws just the list again, and keeps the focus on that button.
      const kind = state.setup.kind, id = "setup-" + kind, tid = treeId(kind, state.setup.types?.kinds?.[kind]);
      const closed = state.setup.closed[tid] ||= new Set();
      if (ds.tree) closed.has(ds.tree) ? closed.delete(ds.tree) : closed.add(ds.tree);
      else if (ds.treeAll === "open") closed.clear();
      else (state.setup.treeKeys?.[tid] || []).forEach(k => closed.add(k));
      LIST_REDRAW[id]?.();
      return (ds.tree ? document.querySelector(`[data-tree="${CSS.escape(ds.tree)}"]`) : t)?.focus({ preventScroll: true });
    }
    if (ds.setupAct) return await setupAct(ds.setupAct, t);
    if (ds.whyCancel) return hideWhy();
    if (ds.reqScope) {
      if (!closeDrawer()) return;
      state.setup.reqScope = ds.reqScope === "all" ? null : +ds.reqScope; return render();
    }
    if (ds.reqEdit) return openRequired(ds.reqEdit);
    if (ds.reqFollow) { t.disabled = true; try { return await reqSave(true); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.chkNew) return openChecklist("new");
    if (ds.chkOpen) return openChecklist(+ds.chkOpen);
    if (ds.chkCopy) return openChkCopy();
    if (ds.chkAct) return await chkAct(ds.chkAct, t);
    if (ds.remNew) return openReminder("new");
    if (ds.remOpen) return openReminder(+ds.remOpen);
    if (ds.remAct) return await remAct(ds.remAct, t);
    if (ds.movePick) { t.disabled = true; try { return await movePick(); } finally { if (t.isConnected) t.disabled = false; } }
    if (ds.moveGo) return askWhy(t, "Import it", moveImport);
    if (ds.moveCancel) { Object.assign(state.setup.move, { file: null, preview: null }); hideWhy(); $("#mvPreview").innerHTML = ""; return; }
    if (ds.chkPreview || ds.chkCopyPreview || ds.remPreview) {
      t.disabled = true;
      try { return await (ds.chkPreview ? chkSave(true) : ds.chkCopyPreview ? chkCopySave(true) : remSave(true)); } finally { if (t.isConnected) t.disabled = false; }
    }
    if (ds.payeeAct) return await payeeAct(ds.payeeAct, +ds.payeeId, t);
    if (ds.advAdd) return await advAdd(+ds.advAdd, t);
    if (ds.advSave) return await advSave(+ds.advSave, t);
    if (ds.advDel) return advDelete(+ds.advDel, t);
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
    if (ds.explain) return explainLine(+ds.explain);
    if (ds.rcAcct) { Object.assign(state.recon, { account: +ds.rcAcct, year: null, open: null, rv: null }); return render(); }
    if (ds.rcYear) { Object.assign(state.recon, { year: ds.rcYear, open: null }); return drawRecon(); }
    if (ds.rcOpen) { state.recon.open = state.recon.open === ds.rcOpen ? null : ds.rcOpen; return drawRecon(); }
    if (ds.rcReview) return openReview(+ds.rcReview);
    if (ds.rvBack) { state.recon.rv = null; return drawRecon(); }
    if (ds.rvToggle) { RV().showMatched = !RV().showMatched; return drawRvList(); }
    if (ds.rvConfirmAll) {
      const r = await api("/api/recon/confirm-matched", { json: { entity_id: state.entity, statement_id: RV().sid } });
      toast(`${r.confirmed} line${r.confirmed === 1 ? "" : "s"} confirmed${r.needs_date_tick ? `; ${r.needs_date_tick} with a different date left for you to select and tick` : ""}.`);
      return reloadReview();
    }
    if (t.id === "rvApply") { t.disabled = true; try { return await rvApply(); } finally { t.disabled = false; } }
    if (ds.rcSign) return rcAct("sign-off", { statement_id: +ds.rcSign }, "Marked as reconciled.");
    if (ds.rcUndo) return rcAct("undo-sign-off", { statement_id: +ds.rcUndo }, "Sign-off undone.");
    if (ds.rcBefore) {
      const id = ds.rcBefore, tick = document.querySelector(`[data-rc-before-tick="${id}"]`)?.checked === true;
      return rcAct("before-tracking", { statement_id: +id, checked: tick, note: document.querySelector(`[data-rc-note="${id}"]`)?.value || "" }, "Marked as reconciled before tracking.");
    }
    if (ds.unlink) {
      const r = await api(`/api/statement-lines/${ds.unlink}`, { json: { payment_id: null } });
      toast(r.removed ? `Undone. ${r.removed} was created from the bank statement and had nothing else on it, so it was removed too.` : "Undone. The line is waiting to be explained.");
      return render();
    }
    if (t.id === "sqlApply") {
      const p = state.sqlPreview; t.disabled = true;
      const links = {}; for (const r of p.records) if (r.payment_id && (!r.exists || r.kind === "invoice")) links[r.row] = r.payment_id;
      const res = await api("/api/sql/apply", { json: { token: p.token, header_row: p.header_row, mapping: p.mapping, links, journal_id: p.journal_lines?.chosen } });
      state.sqlPreview = null; delete state.sqlPaste[state.entity];
      if (res.journal_lines) { toast(`Kept ${res.journal_lines} journal lines.`); return render(); }
      const kept = res.ledger?.files || [], docs = kept.filter(f => f.kind === "journal").reduce((a, f) => a + (f.summary?.docs || 0), 0),
        diffs = kept.reduce((a, f) => a + (f.problems || 0), 0);
      const lines = kept.length ? `Kept the account lines of ${plural(docs, "document")} from ${plural(kept.length, "report")} of SQL's${diffs ? `; ${plural(diffs, "difference")} from SQL's reports, listed under Checks against SQL's reports` : ""}${res.ledger.recon_changed?.length ? `; the bank reconciliation of a signed-off month changed` : ""}` : "";
      if (!p.records.length && kept.length) { toast(lines + "."); return render(); }
      toast(`Imported ${res.added} entries; ${res.linked} linked to payments${res.skipped ? `, ${res.skipped} already imported` : ""}${matchedNote(res)}${lines ? `. ${lines}` : ""}.`);
      return render();
    }
    if (ds.sqlLines) {
      const row = t.closest("tr"), next = row?.nextElementSibling;
      if (next?.classList.contains("sql-lines-row") && next.dataset.doc === ds.sqlLines) { next.remove(); return; }
      if (next?.classList.contains("sql-lines-row")) next.remove();
      const v = await api(`/api/ledger/doc?entity=${state.entity}&doc_no=${encodeURIComponent(ds.sqlLines)}`);
      const tr = document.createElement("tr");
      tr.className = "sql-lines-row"; tr.dataset.doc = ds.sqlLines;
      tr.innerHTML = `<td colspan="${row.children.length}">${ledgerDocView(v)}</td>`;
      row.after(tr); return;
    }
    if (t.id === "sqlFetch") {
      t.disabled = true; t.textContent = "Reading the folder…";
      try { renderSqlPreview(await api("/api/sql/preview", { json: { entity_id: state.entity, fetch: true } })); }
      finally { t.disabled = false; t.textContent = "Fetch from SQL exports"; }
      return $("#sqlPreview").scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (t.id === "sqlDirSave") {
      const r = await api("/api/settings/sql-exports-dir", { json: { sql_exports_dir: $("#sqlDir").value } });
      state.meta.sql_exports_dir = r.sql_exports_dir; state.meta.sql_exports_default = r.default;
      toast(r.default ? "Reading your Downloads folder" : "Folder saved"); return render();
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
    if (ds.sqlIgnoreIds) {  // every row of a listing entry, so one listed on several rows leaves the list at once
      const r = await api("/api/sql/entries/ignore", { json: { ids: ds.sqlIgnoreIds.split(",").map(Number) } });
      toast(r.ignored === 1 ? "1 entry ignored; it is listed under Ignored" : `${r.ignored} entries ignored; they are listed under Ignored`); return render();
    }
    if (ds.sqlLinkGo) {
      const v = $(`select[data-sql-link="${ds.sqlLinkGo}"]`).value;
      if (!v) return toast("Choose a payment first.", true);
      const r = await api(`/api/sql/entries/${ds.sqlLinkGo}`, { json: { payment_id: +v } }); toast(`Linked${matchedNote(r)}`); return render();
    }
    if (ds.sqlUnlink) {
      const r = await api(`/api/sql/entries/${ds.sqlUnlink}/unlink`, { json: {} });
      toast(r.kind === "journal" ? `${r.doc_no} unlinked${r.removed ? `, and the payment made from it was removed` : ` from ${r.payment}`}`
        : r.removed ? `${r.doc_no} is back under SQL entries not linked, and the payment made from it was removed`
        : `${r.doc_no} unlinked from ${r.payment}; it's back under SQL entries not linked`); return render();
    }
    if (ds.sqlUnignore) { const r = await api(`/api/sql/entries/${ds.sqlUnignore}/unignore`, { json: {} }); toast(`${r.doc_no} is back under SQL entries not linked`); return render(); }
    if (ds.editPayee) { if (!mayLeave()) return; return await editPayee(ds.editPayee); }
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
    if (t.id === "auditorPack") {
      if (!confirm("The auditor package holds staff pay, bank and ID details. It stays on this PC until you send it. Build it now?")) return;
      t.disabled = true; t.textContent = "Building…"; $("#packOut").hidden = true;
      try {
        const r = await api("/api/auditor-export", { json: { entity_id: state.entity, month: state.month } });
        // The package also built a fresh audit pack: show it in Recent packs and Before you print, then the link.
        await render();
        $("#packOut").innerHTML = `Auditor package built (${r.files} files${r.left_out ? `, ${r.left_out} left out because they changed or are missing` : ""}): <a href="${r.url}">${esc(r.name)}</a>. It also built a fresh audit pack, and it is in the exports folder on this PC.`;
        $("#packOut").hidden = false; return;
      } catch (e) { $("#packOut").textContent = `The package wasn't built: ${e.message}`; }
      t.disabled = false; t.textContent = "Auditor package"; $("#packOut").hidden = false; return;
    }
    if (t.id === "doBackup" || t.id === "doBackupEnc") {
      const enc = t.id === "doBackupEnc", out = $("#setOut");
      let body = {};
      if (enc) {
        const pw = $("#bkPw").value;
        if (pw.length < 12) return toast("The password needs at least 12 characters.", true);
        if (pw !== $("#bkPw2").value) return toast("The two passwords are not the same.", true);
        body = { password: pw };
      }
      t.disabled = true;
      try {
        const r = await api("/api/backup", { json: body });
        out.textContent = r.warning || `Saved ${r.file}${r.copied ? " and copied to " + r.copied : ""}${r.not_copied ? ". " + r.not_copied : ""}`;
      } catch (e) { out.textContent = e.message; }
      finally { body = null; if ($("#bkPw")) { $("#bkPw").value = ""; $("#bkPw2").value = ""; } t.disabled = false; }
      return;
    }
    if (t.id === "saveBackupDir") {
      const r = await api("/api/settings/backup-dir", { json: { backup_dir: $("#bkDir").value } });
      state.meta.backup_dir = r.backup_dir; toast(r.backup_dir ? "Backup folder saved" : "Backup folder cleared"); return;
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
    if (t.dataset.rvSel) { RV().sel[t.dataset.rvSel] = t.checked; return paintBar(); }
    if (t.dataset.rvKeep) { RV().keep[t.dataset.rvKeep] = t.checked; return; }
    // Move setup: the links save what is chosen.
    if (t.id === "mv-from") { state.setup.move.from = t.value; $("#mvTemplate").href = moveHref("template", t.value ? `&entity=${t.value}` : ""); return; }
    if (t.id === "mv-payees") {
      state.setup.move.payees = t.checked; $("#mv-warn").hidden = !t.checked;
      $("#mvFull").href = moveHref("full", t.checked ? "&payees=1" : ""); return;
    }
    if (t.id === "rvChecked") { RV().checked = t.checked; return; }
    if (t.dataset.rvChoice) {
      const V = RV(), id = +t.dataset.rvChoice;
      V.choice[id] = t.value; if (!t.value) delete V.sel[id];
      document.getElementById(`rv-row-${id}`).outerHTML = rvRow(V.d.lines.find(l => l.id === id));
      return paintBar();
    }
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
    if (t.id === "sqlJournalPick") {  // the note is worked out again for the journal chosen
      renderSqlPreview(await api("/api/sql/preview", { json: { token: state.sqlPreview.token, journal_id: t.value || null } }));
    }
    if (t.dataset.sqlMap) {
      // The links picked by hand go along, so reading the columns again keeps them for the rows still there.
      const p = state.sqlPreview; const mapping = { ...p.mapping, [t.dataset.sqlMap]: t.value === "" ? null : +t.value };
      const picks = Object.fromEntries(p.records.filter(r => r.picked).map(r => [r.row, r.payment_id]));
      renderSqlPreview(await api("/api/sql/preview", { json: { token: p.token, header_row: p.header_row, mapping, picks } }));
    }
    if (t.dataset.pasteMap) {
      // A column picked by hand: the list is read again with it (nothing saved).
      // The preview goes (Save with it) until the new read comes back; the pickers stay on screen meanwhile.
      const P = state.setup.paste, p = P?.preview || P?.shown;
      if (!p) return;
      const mapping = { ...(p.mapping || {}), [t.dataset.pasteMap]: t.value === "" ? null : +t.value };
      P.shown = { ...p, mapping }; P.preview = null; paintPasteSave(true);  // a second pick while reading keeps this one
      await pasteSave(true, { base: P.shown, header_row: p.header_row ?? null, mapping });
    }
  } catch (e) { toast(e.message, true); }
});

document.addEventListener("submit", async ev => {
  if (ev.target.id === "setupWhy") { ev.preventDefault(); return whySubmit(); }
  const SETUP_SAVES = { setupForm: setupSave, settingsForm: settingsSave, reqForm: () => reqSave(false), chkForm: () => chkSave(false),
    chkCopyForm: () => chkCopySave(false), remForm: () => remSave(false), pasteForm: () => pasteSave(false) };
  if (SETUP_SAVES[ev.target.id]) {
    ev.preventDefault();
    const btn = ev.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try { await SETUP_SAVES[ev.target.id](); } catch (e) { toast(e.message, true); }
    finally { if (btn.isConnected) btn.disabled = false; }
    return;
  }
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
      Object.assign(state.recon, { rv: null, account: +$("#stmtAcct").value, year: r.month.slice(0, 4), open: r.month });
      render();
    } catch (e) { toast(e.message, true); }
  }
  if (ev.target.id === "openingForm") {
    ev.preventDefault();
    const amount = parseFloat($("#openAmount").value.replace(/,/g, ""));
    if (!$("#openMonth").value || Number.isNaN(amount)) return toast("Choose the month and type the balance as a number.", true);
    try {
      await api("/api/recon/book-opening", { json: { entity_id: state.entity, account_id: state.recon.account, month: $("#openMonth").value, amount } });
      toast("Book opening saved."); drawRecon();
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
  state.openPayment = null; state.drawerDirty = null;
  const e = ent(), acct = defaultAccount(e)?.id;
  $("#drawer").innerHTML = `
    <div class="row spread"><h2>Add a payment</h2><button class="ghost small" id="closeDrawer">Close</button></div>
    <div class="note">For ad hoc payments, claims and receipts in ${monthName(state.month)}.</div>
    <form class="form" id="addForm" style="grid-template-columns:1fr 1fr">
      <label class="field" style="grid-column:1/-1"><span>Description</span><input id="ap-desc" required placeholder="e.g. Oct 2026 Claims - Soon"></label>
      <label class="field"><span>Type</span><select id="ap-cat">${typeOptions(oneOffType(), "out")}</select></label>
      <label class="field"><span>Money</span><select id="ap-dir"><option value="out">Paid out</option><option value="in">Received</option></select></label>
      <label class="field"><span>Amount</span><input id="ap-amt" type="number" step="0.01"></label>
      <label class="field"><span>Due date</span><input id="ap-due" type="date"></label>
      <label class="field" style="grid-column:1/-1"><span>Account</span><select id="ap-acct">${pickAccounts(e).map(a => acctOption(a, acct)).join("")}</select></label>
      <div class="row"><button class="btn" type="submit">Add payment</button></div>
    </form>`;
  $("#drawer").hidden = false;
  pairTypeDir($("#ap-cat"), $("#ap-dir"), { keep: oneOffType() });  // Received offers the types of money received; Paid out, the one-off default again
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
// Escape closes the drawer (asking first if something typed would be lost); in the reason box it closes only that.
document.addEventListener("keydown", ev => {
  if (ev.key !== "Escape") return;
  if (ev.target.closest?.("#setupWhy")) return hideWhy();
  closeDrawer();
});
document.addEventListener("input", ev => {
  const id = ev.target.dataset?.search;
  if (id) { listState(id).q = ev.target.value; LIST_REDRAW[id]?.(); }
});
document.addEventListener("input", ev => { if (ev.target.id === "sqlPaste") state.sqlPaste[state.entity] = ev.target.value; });
document.addEventListener("input", ev => { if (ev.target.id === "trailReason") state.trail.reason = ev.target.value; });  // kept across redraws
// The SQL box holds one listing: pasting replaces what is in it, so a listing left there can't run into the next one.
document.addEventListener("paste", ev => {
  const text = ev.target.id === "sqlPaste" && ev.clipboardData?.getData("text");
  if (!text) return;
  ev.preventDefault(); ev.target.value = text; state.sqlPaste[state.entity] = text;
});
// Keeps the SQL page's lists open across a refresh (after Unlink); toggle doesn't bubble, so it is caught on the way down.
document.addEventListener("toggle", ev => { const k = ev.target.dataset?.sqlOpen; if (k) state.sqlOpen[k] = ev.target.open; }, true);
document.addEventListener("toggle", async ev => {
  const d = ev.target, k = d.dataset?.hist;
  if (!k || !d.open || d.dataset.loaded) return;
  const [tbl, key] = k.split(":"), body = d.querySelector(".hist-body");
  body.innerHTML = `<div class="note">Loading…</div>`;
  try { body.innerHTML = historyHtml(await api(`/api/audit/record/${tbl}/${key}`)); d.dataset.loaded = "1"; }
  catch (e) { body.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}, true);
document.addEventListener("change", ev => {
  const k = ev.target.dataset?.tf;
  if (k) {
    const v = ev.target.value;
    if (ev.target.type === "date" && v && !(v >= "2000-01-01" && v <= "2999-12-31")) return;  // a year still being typed
    state.trail.f[k] = v; return refreshTrailList();
  }
  if (ev.target.id === "trailShow") return trailShow(ev.target.checked);
  if (ev.target.matches?.("[data-setup-stopped]")) { state.setup.stopped = ev.target.checked; return LIST_REDRAW["setup-" + state.setup.kind]?.(); }
  if (ev.target.matches?.("[data-setup-deleted]")) { state.setup.deleted = ev.target.checked; return drawDeleted(ev.target.dataset.setupDeleted); }
  if (ev.target.id === "cl-from" && ev.target.closest?.("#chkForm")) return chkMonth();
  if (ev.target.id === "rm-from" && ev.target.closest?.("#remForm")) return remMonth();
  if (ev.target.closest?.("#chkForm, #remForm")) return setupPaint();
});
// A preview shown is of what was typed then: a change typed after it (other than the reason) takes it away.
document.addEventListener("input", ev => {
  if (!ev.target.closest?.("#chkForm, #chkCopyForm, #remForm") || /-reason$/.test(ev.target.id)) return;
  for (const el of document.querySelectorAll("#drawer [data-preview-out]")) el.innerHTML = "";
});
// Paste a list: a change to the text, who it is for or what they are takes the preview away (and Save with it); a
// column picked in the preview reads it again instead (the change listener).
document.addEventListener("input", ev => {
  if (!["ps-text", "ps-scope", "ps-kind"].includes(ev.target.id) || !state.setup.paste) return;
  Object.assign(state.setup.paste, { preview: null, previewFor: null, shown: null }); paintPaste();
});
// A code as SQL Account has it is typed in capitals; the cursor stays where it was.
document.addEventListener("input", ev => {
  const t = ev.target;
  if (!t.matches?.("input[data-upper]") || t.value === t.value.toUpperCase()) return;
  const a = t.selectionStart, b = t.selectionEnd;
  t.value = t.value.toUpperCase();
  try { t.setSelectionRange(a, b); } catch { /* not a text input */ }
});

// The current cycle and the month before are set up on their own; other months when you ask.
async function openCycleMonths() {
  try {
    for (const e of state.meta.entities.filter(isActive)) for (const m of [shiftMonth(currentCycle(), -1), currentCycle()])
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
  state.month = currentCycle(); state.day = dayKey();  // the rollover day comes with the settings
  state.entity = firstEntityId();
  paintOrg();
  await openCycleMonths();
  renderNav(); render();
})();
