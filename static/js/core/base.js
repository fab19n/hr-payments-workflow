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
  nextAll: {}, bankOnly: false, lists: {}, counts: {}, books: { entity: null, tab: "tb", from: null, to: null, rollup: true, account: null, q: "", months: false, side: "customers", party: null }, recon: { entity: null, account: null, year: null, open: null, panel: null, rv: null },
  trail: { f: {}, entries: [], more: false, labels: null, show: false },
  setup: { kind: null, id: null, types: null, stopped: false, deleted: false, view: {}, closed: {}, drawer: null, reqScope: null, req: null, reqOpen: null, chk: null, chkOpen: null, rem: null, remOpen: null, paste: null } };
// Sidebar sections; companies are listed between Dashboard and Monthly work.
// The Payroll check sits under Monthly work until the redesign moves it to HR.
const VIEWS = [["Monthly work", [["budget", "Budget"], ["payroll", "Payroll check"], ["bank", "Bank statements"], ["sql", "SQL import"], ["payees", "Recurring"]]],
  ["Accounting", [["books", "Books"]]],
  ["Filing", [["audit", "Audit pack"], ["trail", "Audit trail"], ["settings", "Backup"]]],
  ["Setup", [["setup", "Setup"]]]];
const ICON = {
  overview: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  entity: '<path d="M4 21V5l8-3v19M12 9h8v12M8 8h.01M8 12h.01M8 16h.01M16 13h.01M16 17h.01M2 21h20"/>',
  budget: '<path d="M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12M16 14h.01"/>',
  bank: '<path d="M3 10h18M5 10v8M9.5 10v8M14.5 10v8M19 10v8M2 21h20M12 3l9 5H3z"/>',
  sql: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  books: '<path d="M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4zM20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6zM7 8h2M15 8h2M7 12h2M15 12h2"/>',
  payees: '<path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/>',
  payroll: '<path d="M4 3h16v18H4zM4 9h16M4 15h16M10 3v18M14 12l1.5 1.5L18 11"/>',
  audit: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 15l2 2 4-4"/>',
  settings: '<path d="M3 4h18v4H3zM5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/>',
  trail: '<path d="M12 3l8 3v6c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V6zM9 12l2 2 4-4"/>',
  setup: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
};
const icon = v => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[v]}</svg>`;

