"use strict";
/* ---------------- Addresses ----------------
   Every page has an address, so Back, Forward and Refresh keep your place and a link lands on a filter:
     #/<company code | all>/<YYYY-MM>/<area>/<page>[/<id>][?<filters>]   a page of one month
     #/<company code>/<area>/<page>[/<id>][?<filters>]                    a page with no month
     #/<area>/<page>[/<kind>[/<id>]]                                      a page with no company
   Only the company code, the month, the page's words, a record number and the filter keys below ever go in an address:
   never a name, an amount or anything personal. ROUTES is the one table of pages (state.view is the page's key in it);
   addrOf(place) writes a place as an address and parseAddr(hash) reads one back (null when it is not one of ours).
   A place is { view, entity (id, "all" or null), month, sub, id, params }: sub and id are the Setup section and record, or the
   payment to open on the register; params are the filters (mark, pay, task, as_at, filter, account, tab, from, to).
   navigate(place) writes the address and applies the place; applyPlace(place) sets the state and draws; go() and goTo() call
   navigate. Known departure from the design: Setup is #/admin/setup[/<kind>[/<id>]] with today's server kind names; the design's
   #/<CODE>/admin/setup/<group>/<page> (companies, hr/approvers) comes with the Setup HR group. Where the page has no real location or history (the test stand-ins) a place is applied with no address. */

// The areas of the menu (core/menu.js draws it): the first word of an address after the company and month.
const AREAS = ["payments", "accounting", "hr", "admin"];
const DATE_RE = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/, MONTH_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const IDS_RE = /^\d{1,9}(,\d{1,9}){0,199}$/;
// The tabs a page's address may name (All, the first tab, is left out of the address): the Payments register's and the Monthly
// checklist's (slice 2); any other page with a tab filter is Books or its Customers and suppliers part.
const PAGE_TABS = { entity: ["unpaid", "attention", "nosql", "complete"], checklist: ["open", "done", "missing"], einvoices: ["received", "self-billed"] };
const BOOKS_TABS = ["tb", "gl", "pl", "bs", "customers", "suppliers", "statutory"];
// The filters an address may carry, and what each may hold (for the page given). Nothing else is read from or written to an address.
const PARAM_RULES = {
  mark: v => /^[a-z0-9][a-z0-9_-]{0,40}$/.test(v), pay: v => IDS_RE.test(v), task: v => IDS_RE.test(v),
  as_at: v => DATE_RE.test(v), filter: v => v === "to_explain", account: v => /^\d{1,9}$/.test(v),
  tab: (v, view) => (PAGE_TABS[view] || BOOKS_TABS).includes(v), from: v => DATE_RE.test(v), to: v => DATE_RE.test(v),
};
// view (the page's key in state.view) -> its address. company: "any" (a code or all), "one" (a code) or "none"; month: the
// page is one month's. The draw function is looked up when it is wanted: the page scripts come after this one.
const ROUTES = {
  overview: { area: null, page: "overview", company: "any", month: true, params: [], draw: () => viewOverview },
  entity: { area: "payments", page: "register", company: "one", month: true, params: ["mark", "pay", "tab"], draw: () => viewEntity },
  budget: { area: "payments", page: "budget", company: "one", month: true, params: ["as_at"], draw: () => viewBudget },
  payees: { area: "payments", page: "recurring", company: "one", month: true, params: [], draw: () => viewPayees },
  bank: { area: "accounting", page: "bank", company: "one", month: true, params: ["filter", "account"], draw: () => viewBank },
  sql: { area: "accounting", page: "sql", company: "one", month: true, params: [], draw: () => viewSql },
  books: { area: "accounting", page: "books", company: "one", month: false, params: ["tab", "from", "to"], draw: () => viewBooks },
  payroll: { area: "hr", page: "payroll/workbook", company: "one", month: true, params: [], draw: () => viewPayroll },
  audit: { area: "admin", page: "audit-pack", company: "one", month: true, params: [], draw: () => viewAudit },
  trail: { area: "admin", page: "audit-trail", company: "none", month: false, params: [], draw: () => viewTrail },
  settings: { area: "admin", page: "backup", company: "none", month: false, params: [], draw: () => viewSettings },
  setup: { area: "admin", page: "setup", company: "none", month: false, params: [], draw: () => viewSetup },
  // The pages the menu adds (step 0e). Staff, Leave, Claims and advances, Approvals and To pay are not built yet (Coming soon);
  // Customers and suppliers and Statutory payables land on today's Books tabs until slice 7 (their address stays their own: applyPlace
  // puts the tab in the state, and placeFromState gives the Books address when the tab moves on); Sales, Purchases, Journals and
  // Period close are the Kept here placeholders. pages/placeholders.js draws them. e-Invoices is its own page (slice 6, pages/einvoices.js).
  staff: { area: "hr", page: "staff", company: "one", month: false, params: [], draw: () => viewStaff },
  leave: { area: "hr", page: "leave", company: "one", month: false, params: [], draw: () => viewLeave },
  claims: { area: "hr", page: "claims", company: "one", month: false, params: [], draw: () => viewClaims },
  approvals: { area: "payments", page: "approvals", company: "one", month: false, params: [], draw: () => viewApprovals },
  topay: { area: "payments", page: "to-pay", company: "one", month: false, params: [], draw: () => viewToPay },
  einvoices: { area: "accounting", page: "einvoices", company: "one", month: true, params: ["tab"], draw: () => viewEinvoices },
  parties: { area: "accounting", page: "parties", company: "one", month: true, params: ["tab"], draw: () => viewBooks },
  statutory: { area: "accounting", page: "statutory", company: "one", month: true, params: ["from", "to"], draw: () => viewBooks },
  sales: { area: "accounting", page: "sales", company: "one", month: false, params: [], draw: () => viewSales },
  purchases: { area: "accounting", page: "purchases", company: "one", month: false, params: [], draw: () => viewPurchases },
  journals: { area: "accounting", page: "journals", company: "one", month: false, params: [], draw: () => viewJournals },
  close: { area: "accounting", page: "period-close", company: "one", month: false, params: [], draw: () => viewPeriodClose },
  // Slice 2: the Monthly checklist, split from the company month page (the register keeps the key entity). pages/checklist.js draws it.
  checklist: { area: "payments", page: "checklist", company: "one", month: true, params: ["mark", "task", "tab"], draw: () => viewChecklist },
};
const ROUTER = { at: null, busy: 0, i: 0 };  // at: the address last written or applied; busy: our own change is going on, so a hashchange or a sync is not a new place; i: the number of the history entry on show
const placeLoc = () => typeof window !== "undefined" && window.location && typeof window.location.hash === "string" ? window.location : null;
const ROUTE_WORDS = r => [...(r.area ? [r.area] : []), ...r.page.split("/")];
const homePlace = () => ({ view: "overview", entity: "all", month: state.month, sub: null, id: null, params: {} });
const entCode = id => state.meta?.entities.find(e => e.id === +id)?.code || null;
const entByCode = code => state.meta?.entities.find(e => String(e.code).toLowerCase() === String(code).toLowerCase()) || null;
const booksTab = B => B.tab === "ledger" ? "gl" : B.tab === "parties" ? (B.side === "suppliers" ? "suppliers" : "customers") : B.tab;

// Only the filters this page has, and only valid ones; in the table's order.
function cleanParams(view, raw) {
  const out = {};
  for (const k of ROUTES[view]?.params || []) { const v = raw?.[k]; if (v != null && v !== "" && PARAM_RULES[k](String(v), view)) out[k] = String(v); }
  return out;
}

// A place as an address (a string starting #/), or null for a page that is not in ROUTES.
function addrOf(place) {
  const R = ROUTES[place?.view];
  if (!R) return null;
  const seg = [];
  if (R.company !== "none") {
    const id = place.entity === "all" || place.entity == null ? (R.company === "any" ? "all" : state.entity ?? firstEntityId()) : place.entity;
    const code = id === "all" ? "all" : entCode(id);
    if (!code) return null;
    seg.push(encodeURIComponent(code));
  }
  if (R.month) seg.push(MONTH_RE.test(place.month || "") ? place.month : state.month);
  seg.push(...ROUTE_WORDS(R));
  if (place.view === "entity" && /^\d+$/.test(String(place.id ?? ""))) seg.push(String(place.id));
  if (place.view === "setup" && /^[a-z][a-z0-9_]*$/.test(place.sub || "")) { seg.push(place.sub); if (/^\d+$/.test(String(place.id ?? ""))) seg.push(String(place.id)); }
  const q = Object.entries(cleanParams(place.view, place.params)).map(([k, v]) => `${k}=${v}`).join("&");
  return "#/" + seg.join("/") + (q ? "?" + q : "");
}

// An address as a place, or null when it is not one: another shape, an unknown company, a bad month, an unknown page, a page
// given a company or month it does not have, or all on a page that is one company's.
function parseAddr(hash) {
  if (!state.meta) return null;
  let s = String(hash ?? "");
  if (s[0] === "#") s = s.slice(1);
  const qi = s.indexOf("?"), path = qi < 0 ? s : s.slice(0, qi), query = qi < 0 ? "" : s.slice(qi + 1);
  if (path[0] !== "/") return null;
  let segs = path.slice(1).split("/");
  if (segs[segs.length - 1] === "") segs.pop();
  try { segs = segs.map(decodeURIComponent); } catch { return null; }
  if (!segs.length || segs.some(x => !x || /[\/?#\s]/.test(x))) return null;
  let co = null, month = null;
  if (!(segs[0] === "admin" && ["audit-trail", "backup", "setup"].includes(segs[1]))) {
    co = segs.shift();
    if (MONTH_RE.test(segs[0] || "")) month = segs.shift();
  }
  let view = null, extra = [];
  for (const [v, R] of Object.entries(ROUTES)) {
    for (const page of [R.page, ...(R.alias || [])]) {
      const words = [...(R.area ? [R.area] : []), ...page.split("/")];
      if (words.every((w, i) => segs[i] === w)) { view = v; extra = segs.slice(words.length); break; }
    }
    if (view) break;
  }
  const R = ROUTES[view];
  if (!R || !!month !== R.month || (R.company === "none") !== (co == null)) return null;
  let entity = null, sub = null, id = null;
  if (R.company !== "none") {
    if (co.toLowerCase() === "all") { if (R.company !== "any") return null; entity = "all"; }
    else { const e = entByCode(co); if (!e) return null; entity = e.id; }
  }
  if (view === "entity") { if (extra.length > 1 || (extra.length && !/^\d{1,9}$/.test(extra[0]))) return null; id = extra[0] || null; }
  else if (view === "setup") {
    if (extra.length > 2 || (extra[0] && !/^[a-z][a-z0-9_]*$/.test(extra[0])) || (extra[1] && !/^\d{1,9}$/.test(extra[1]))) return null;
    sub = extra[0] || null; id = extra[1] || null;
  } else if (extra.length) return null;
  const raw = {};
  for (const part of query.split("&")) {
    if (!part) continue;
    const eq = part.indexOf("=");
    try { raw[decodeURIComponent(eq < 0 ? part : part.slice(0, eq))] = eq < 0 ? "" : decodeURIComponent(part.slice(eq + 1)); } catch { /* a malformed pair is left out */ }
  }
  // A register address of before slice 2 that names checklist items (?task=, the checklist was part of that page) opens them on
  // the Monthly checklist, marked.
  if (view === "entity" && !id && raw.task != null && PARAM_RULES.task(String(raw.task))) { view = "checklist"; delete raw.pay; }
  return { view, entity, month, sub, id, params: cleanParams(view, raw) };
}

// The place the state is in now: what addrOf needs to write the address of the page on show. Books and Setup keep their
// own state (the tab, dates, section and record), so those are read live; the other filters are what the place asked for.
function placeFromState() {
  // Customers and suppliers and Statutory payables are Books tabs for now: once the tab moves on, the page is Books.
  if ((state.view === "parties" || state.view === "statutory") && state.books.tab !== state.view) state.view = "books";
  const v = state.view, R = ROUTES[v] || ROUTES.overview, p = { view: R === ROUTES[v] ? v : "overview", entity: null, month: null, sub: null, id: null, params: {} };
  if (R.company !== "none") p.entity = v === "overview" && state.addr.all ? "all" : state.entity;
  if (R.month) p.month = state.month;
  if (v === "entity") { p.id = state.addr.id; p.params = state.addr.params; }
  else if (v === "books") { const B = state.books, same = B.entity === state.entity; p.params = { tab: booksTab(B), from: same ? B.from : null, to: same ? B.to : null }; }
  else if (v === "parties") p.params = state.books.side === "suppliers" ? { tab: "suppliers" } : {};
  else if (v === "statutory") { const B = state.books, same = B.entity === state.entity; p.params = { from: same ? B.from : null, to: same ? B.to : null }; }
  else if (v === "setup") { p.sub = state.setup.kind; p.id = state.setup.id; }
  else p.params = state.addr.params;
  return p;
}
const currentAddr = () => addrOf(placeFromState());

// Writes an address: a new history entry, or (replace) in place of the current one. The same address writes nothing.
function writeAddr(addr, replace) {
  const L = placeLoc();
  if (!L || !addr) return;
  if (L.hash === addr) { ROUTER.at = addr; return; }
  ROUTER.at = addr;  // set first: the hashchange our own write raises is then not a new place
  const H = window.history && window.history.replaceState ? window.history : null;
  if (replace) { if (H) H.replaceState({ i: ROUTER.i }, "", addr); else if (L.replace) L.replace(addr); }
  else { L.hash = addr; ROUTER.i++; if (H) H.replaceState({ i: ROUTER.i }, "", addr); }  // every entry of ours is numbered, so Keep editing can step back to it
}
const entryNo = () => { const s = window.history && window.history.state; return s && typeof s.i === "number" ? s.i : null; };
// The address follows the state when a page changes something an address holds (a tab, a section, an account, the month).
function syncAddr(replace = true) { if (!ROUTER.busy) { writeAddr(currentAddr(), replace); if (state.meta) renderNav(); } }  // the menu lights the page the tab or section moved to
// After a page was drawn: the address says what is really on show (a page the company does not use, a month moved on).
function settleAddr() { const a = currentAddr(); if (a && placeLoc() && placeLoc().hash !== a) writeAddr(a, true); }

// Sets the state from a place and draws it. opts: write (put the address in the history first), replace (in place of the
// current entry), fresh (a page change: searches and the review start again, as go() always did), link (arrived by a link or
// address: the page starts at the top and a bank page takes its focus), fromAddress (also: a page this company doesn't use
// gives the Overview and the toast), bad (the address was not one of ours: the Overview and the toast).
async function applyPlace(place, opts = {}) {
  ROUTER.busy++;
  try {
    let e = place.entity && place.entity !== "all" ? state.meta.entities.find(x => x.id === +place.entity) : null;
    if (opts.bad) { toast("That address isn't used here. Showing the Overview."); place = homePlace(); }
    else if (opts.fromAddress) {
      const gone = e && unusedPage(place.view, e);
      if (gone) { switchedNote(gone, e, PAGE_RULES[place.view]?.plural); place = { ...homePlace(), month: place.month || state.month }; }
    }
    const v = place.view, R = ROUTES[v], p = cleanParams(v, place.params), B = state.books;
    state.view = v;
    if (place.entity && place.entity !== "all") state.entity = +place.entity;
    if (!state.entity) state.entity = firstEntityId();
    if (R.month && MONTH_RE.test(place.month || "")) state.month = place.month;
    if (opts.fresh) { state.recon.rv = null; for (const k in state.lists) state.lists[k].q = ""; state.payeeSaved = null; state.reg = null; state.cl = null; }
    state.addr = { all: place.entity === "all", id: v === "entity" && place.id ? String(place.id) : null, params: p };
    state.openPayment = state.addr.id ? +state.addr.id : null;
    state.mark = v !== "entity" && v !== "checklist" ? null : p.pay ? { pay: x => p.pay.split(",").map(Number).includes(x.id) }
      : p.task ? { task: t => p.task.split(",").map(Number).includes(t.id) } : p.mark ? markFor(p.mark) : null;
    state.asAt = v === "budget" ? p.as_at || null : null;
    state.bankOnly = v === "bank" && p.filter === "to_explain";
    if (opts.link) state.focusBank = v === "bank" ? { account: +p.account || null } : null;
    if (v === "books" && p.tab) {  // the Statutory tab on its month to today, Next up's rows, or the tab an address names
      if (B.entity !== state.entity) Object.assign(B, { entity: state.entity, from: null, to: null, account: null, q: "", party: null });
      B.tab = p.tab === "gl" ? "ledger" : p.tab === "customers" || p.tab === "suppliers" ? "parties" : p.tab;
      if (B.tab === "parties") B.side = p.tab;
      if (p.from || p.to || opts.fromAddress) { B.from = p.from || null; B.to = p.to || null; }
    }
    else if (v === "books" && (B.tab === "parties" || B.tab === "statutory")) B.tab = "tb";  // Books itself (the menu's item) opens on the Trial balance, not on the tab Customers and suppliers or Statutory payables set
    if (v === "parties" || v === "statutory") {  // today's Books page on that tab
      if (B.entity !== state.entity) Object.assign(B, { entity: state.entity, from: null, to: null, account: null, q: "", party: null });
      B.tab = v;
      if (v === "parties") B.side = p.tab === "suppliers" ? "suppliers" : "customers"; else { B.from = p.from || null; B.to = p.to || null; }
    }
    if (v === "setup") { if (place.sub) state.setup.kind = place.sub; state.setup.id = null; }
    if (opts.write) writeAddr(currentAddr(), opts.replace);
    if (opts.link) window.scrollTo?.(0, 0);
    renderNav();
    await render();
    if (v === "setup" && place.id && state.view === "setup" && state.setup.kind) {  // the record the address names opens in its drawer
      try { await openSetup(state.setup.kind, +place.id, { force: true }); } catch (err) { toast(err.message, true); }
    }
    settleAddr();
  } finally { ROUTER.busy--; }
}

// Asks to leave an unsaved drawer (the Discard dialog), then writes the address and applies the place. false: you kept editing.
async function navigate(place, opts = {}) {
  ROUTER.busy++;
  try {
    if (!(await closeDrawer())) return false;
    await applyPlace(place, { write: true, ...opts });
    return true;
  } finally { ROUTER.busy--; }
}
// Draws the page again after a change of month, company or section that has been put into the state already: the address
// follows (a new history entry unless replace).
async function redraw(opts = {}) {
  ROUTER.busy++;
  try { writeAddr(currentAddr(), opts.replace); renderNav(); await render(); settleAddr(); } finally { ROUTER.busy--; }
}

// Back, Forward, a pasted or refreshed address, a link. Our own writes were set in ROUTER.at first, so they are skipped.
async function onHashChange() {
  const L = placeLoc();
  if (!L || !state.meta || L.hash === ROUTER.at) return;
  const h = L.hash, home = !h || h === "#" || h === "#/", place = home ? homePlace() : parseAddr(h), was = ROUTER.at, wasI = ROUTER.i, cur = entryNo();
  ROUTER.busy++;
  try {
    if (!(await closeDrawer())) {  // Keep editing: step back to the entry you were on (a typed address, which has no number, is replaced); nothing is drawn
      if (was) {
        ROUTER.at = was;
        if (cur != null && cur !== wasI && window.history && window.history.go) window.history.go(wasI - cur);
        else if (window.history && window.history.replaceState) window.history.replaceState({ i: wasI }, "", was);
        else if (L.replace) L.replace(was);
      }
      return;
    }
    ROUTER.at = h;
    if (cur != null) ROUTER.i = cur; else { ROUTER.i++; if (window.history && window.history.replaceState) window.history.replaceState({ i: ROUTER.i }, "", h); }
    await applyPlace(place || homePlace(), { link: true, fresh: true, fromAddress: true, bad: !place && !home, write: home, replace: true });
  } finally { ROUTER.busy--; }
}

// The first draw: the address in the bar is the place; with none it is the Overview, and the address is written.
async function routerBoot() {
  const L = placeLoc();
  if (window.addEventListener) window.addEventListener("hashchange", onHashChange);
  const h = L ? L.hash : "", home = !h || h === "#" || h === "#/", place = home ? null : parseAddr(h);
  if (h && !home) ROUTER.at = h;
  if (entryNo() != null) ROUTER.i = entryNo();
  await applyPlace(place || homePlace(), { link: !!place, fresh: true, fromAddress: !!place, bad: !!h && !home && !place, write: !place, replace: true });
  if (L && L.hash && entryNo() == null && window.history && window.history.replaceState) window.history.replaceState({ i: ROUTER.i }, "", L.hash);
}

// What go(view, entity) and goTo(g) ask for, as places.
function goPlace(view, entity) {
  const R = ROUTES[view];
  if (!R) return null;
  const id = entity ? +entity : view === "overview" ? "all" : state.entity ?? firstEntityId();
  return { view, entity: id, month: state.month, sub: view === "setup" ? state.setup.kind : null, id: null, params: {} };
}
// Next up rows and the Overview's counts say view "entity" (the company month page of before slice 2): one about checklist items
// (task_id, task_ids, or a count of them such as overdue_tasks) lands on the Monthly checklist, the rest on the Payments register.
function linkPlace(g) {
  let view = g.view;
  const tasks = g.task_ids || (g.task_id ? [g.task_id] : null), params = {};
  if (view === "entity" && (tasks || (g.filter && MARKS[g.filter]?.task))) view = "checklist";
  if (!ROUTES[view]) return null;
  if (view === "entity") { if (g.payment_ids) params.pay = g.payment_ids.join(","); else if (g.filter) params.mark = g.filter; if (g.tab) params.tab = g.tab; }
  if (view === "checklist") { if (tasks) params.task = tasks.join(","); else if (g.filter) params.mark = g.filter; if (g.tab) params.tab = g.tab; }
  if (view === "budget" && g.as_at) params.as_at = g.as_at;
  if (view === "bank") { if (g.account_id) params.account = String(g.account_id); if (g.filter === "to_explain") params.filter = "to_explain"; }
  if (view === "books") { if (g.tab) params.tab = g.tab; if (g.from) params.from = g.from; if (g.to) params.to = g.to; }
  return { view, entity: g.entity_id || (view === "overview" ? "all" : state.entity ?? firstEntityId()), month: view === "books" ? null : g.month || state.month,
    sub: null, id: view === "entity" && g.payment_id ? g.payment_id : null, params };
}
