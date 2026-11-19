"""The side menu (step 0e): one menu definition, built per company kind, with a number on each area and an address on each item.
Made-up companies only. The page script is run in Node against the same small stand-in for the page as addresses_test (a location,
history and hashchange; the pages themselves are stubbed to record that they were drawn), so core/menu.js and core/router.js really run.

Checks: the menu for a company Kept in SQL Account (SQL import, no Kept here group), one Kept here (the group, no SQL import), the
Overview of All companies (the SQL kind when a company in use is, else the Kept here kind) and no company yet (the same menu, no
numbers); areas, items and order as design/canvas/Sidebar.dc.html; Calendar and reminders and Salary advances are no items; the number on an
area counts the Next up rows of that area for the company on show (red with the alert mark when one is overdue; none when 0; the rows
with no company count for every company; Overview counts all); every item has a route and its address round-trips (Monthly checklist
is the register's alias); the page on show is the one item marked aria-current; items are links with their address and a click opens
the page without the browser following the link (a modified click is left to the browser); groups fold and the one holding the page
stays open; the five Coming soon pages, the four Kept here placeholders and the interim landings (e-Invoices, Customers and suppliers,
Statutory payables) land on the right existing page and tab; a page the company does not use still gets the 0c rule.

Run: .venv\\Scripts\\python -m synthetic_tests.menu_test
"""
import json
import subprocess
import tempfile
from pathlib import Path

from synthetic_tests.appsource import app_bundle

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:600])


tmp = Path(tempfile.mkdtemp(prefix="hrp-menu-test-"))
bundle = app_bundle(tmp / "app.js")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const appPath = process.argv[2];
const wait = ms => new Promise(r => setTimeout(r, ms));

// One page: its own fake DOM, and a location, history and hashchange that behave as a browser's do (a hash assignment adds
// an entry and raises hashchange later; replaceState changes the entry and raises nothing; Back and Forward raise it).
function mkEnv(startHash) {
  const seen = [], hist = { e: [startHash], i: 0 }, handlers = [];
  const fire = () => setTimeout(() => handlers.slice().forEach(f => f({ type: "hashchange" })), 0);
  const loc = {
    get hash() { return hist.e[hist.i]; },
    set hash(v) { v = String(v); if (v[0] !== "#") v = "#" + v; if (v === hist.e[hist.i]) return; hist.e.splice(hist.i + 1); hist.e.push(v); hist.i++; seen.push(v); fire(); },
    replace(v) { hist.e[hist.i] = String(v); seen.push(String(v)); },
  };
  const history = { replaceState(s, t, url) { hist.e[hist.i] = String(url); seen.push(String(url)); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tick = () => sleep(5);
const parseSel = sel => sel.split(",").map(s => s.trim()).filter(Boolean);
function matchOne(n, sel) {
  const m = /^([a-z0-9]*)((?:\[[^\]]+\]|\.[\w-]+|#[\w-]+)*)(?::not\((.*)\))?$/.exec(sel);
  if (!m) throw new Error("selector not supported: " + sel);
  if (m[1] && n.tagName !== m[1]) return false;
  for (const [, part] of m[2].matchAll(/(\[[^\]]+\]|\.[\w-]+|#[\w-]+)/g)) {
    if (part[0] === ".") { if (!n.classList.contains(part.slice(1))) return false; }
    else if (part[0] === "#") { if (n.id !== part.slice(1)) return false; }
    else {
      const [, k, v] = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(part);
      if (!n.hasAttribute(k) || (v !== undefined && n.getAttribute(k) !== v)) return false;
    }
  }
  if (m[3] && matchOne(n, m[3])) return false;
  return true;
}
const matches = (n, sel) => parseSel(sel).some(s => matchOne(n, s));
const listeners = new Map();   // target -> [{type, fn, capture}]
const addL = (t, type, fn, o) => { const l = listeners.get(t) || []; l.push({ type, fn, capture: o === true || !!(o && o.capture) }); listeners.set(t, l); };
const delL = (t, type, fn, o) => { const c = o === true || !!(o && o.capture); listeners.set(t, (listeners.get(t) || []).filter(x => !(x.type === type && x.fn === fn && x.capture === c))); };
class Node {
  constructor(tag) { this.tagName = tag; this.attrs = {}; this.children = []; this.parent = null; this.hidden = false; this.inert = false; this._html = ""; this.dataset = {}; }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; } set className(v) { this.attrs.class = v; }
  get classList() {
    const n = this, get = () => n.className.split(/\s+/).filter(Boolean);
    return { add: (...c) => { n.className = [...new Set([...get(), ...c])].join(" "); }, remove: (...c) => { n.className = get().filter(x => !c.includes(x)).join(" "); }, contains: c => get().includes(c) };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5)] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  set tabIndex(v) { this.attrs.tabindex = String(v); }
  appendChild(c) { if (c.parent) c.remove(); c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  get firstElementChild() { return this.children[0] || null; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === body; }
  contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = n => { for (const c of n.children) { if (matches(c, sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get textContent() { return (this.text || "") + this.children.map(c => c.textContent).join(""); }
  get innerHTML() { return this._html; }
  set innerHTML(h) { this._html = h; this.children = []; parseInto(this, h); }
  focus() {
    for (let n = this; n; n = n.parent) if (n.inert) return;
    document.activeElement = this;
  }
  addEventListener(type, fn, o) { addL(this, type, fn, o); }
  removeEventListener(type, fn, o) { delL(this, type, fn, o); }
  click() { dispatch(this, { type: "click" }); }
}
function parseInto(root, html) {
  const stack = [root]; const tok = /<(\/?)([a-zA-Z0-9]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>|([^<]+)/g; let m;
  const VOID = new Set(["use", "input", "br", "img"]);
  while ((m = tok.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) { top.text = (top.text || "") + m[5]; continue; }
    const [, close, tag, attrs, selfClose] = m;
    if (close) { stack.pop(); continue; }
    const n = new Node(tag.toLowerCase());
    for (const [, k, v] of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
      n.setAttribute(k, v === undefined ? "" : v);
      if (k === "hidden") n.hidden = true;
    }
    top.appendChild(n);
    if (!selfClose && !VOID.has(n.tagName)) stack.push(n);
  }
}
function dispatch(target, ev) {
  ev.target = target; ev.defaultPrevented = false; ev.stopped = false;
  ev.preventDefault = () => { ev.defaultPrevented = true; }; ev.stopPropagation = () => { ev.stopped = true; };
  const path = []; for (let n = target; n; n = n.parent) path.push(n);
  if (path[path.length - 1] === body) path.push(document);
  const call = (t, capture) => { for (const l of [...(listeners.get(t) || [])]) if (l.type === ev.type && (t === target || l.capture === capture)) { ev.currentTarget = t; l.fn(ev); } };
  for (const t of [...path].reverse()) { if (ev.stopped) return ev; if (t !== target) call(t, true); }   // capture, outermost first
  for (const t of path) { if (ev.stopped) return ev; call(t, false); }                                  // the target (all its listeners once), then bubbling
  return ev;
}
const body = new Node("body");
const side = new Node("aside"); side.className = "side";
const content = new Node("div"); content.className = "content";
const drawer = new Node("aside"); drawer.id = "drawer"; drawer.className = "drawer"; drawer.hidden = true;
const toastEl = new Node("div"); toastEl.id = "toast"; toastEl.hidden = true;
for (const n of [side, content, drawer, toastEl]) body.appendChild(n);
let calm = true;
const document = {
  body, activeElement: body,
  querySelector: sel => body.querySelector(sel), querySelectorAll: sel => body.querySelectorAll(sel),
  createElement: tag => new Node(tag),
  addEventListener(type, fn, o) { addL(document, type, fn, o); }, removeEventListener(type, fn, o) { delL(document, type, fn, o); },
};
  Object.defineProperty(Node.prototype, "textContent", { configurable: true,   // the page sets the month label's text
    get() { return (this.text || "") + this.children.map(c => c.textContent).join(""); }, set(v) { this.text = String(v); this.children = []; } });
  const fetch = () => new Promise(() => {});   // the page's first request never answers: nothing else runs
  const scrolls = [];
  const window = { open() {}, print() {}, matchMedia: () => ({ matches: true }), scrollTo() { scrolls.push(1); }, location: loc, history,
    addEventListener(t, f) { if (t === "hashchange") handlers.push(f); } };
  const ctx = vm.createContext({ document, fetch, console, setTimeout, clearTimeout, FormData: class {}, URLSearchParams,
    localStorage: { getItem: () => null, setItem() {} }, window });
  const run = code => vm.runInContext(code, ctx);
  vm.runInContext(fs.readFileSync(appPath, "utf8"), ctx);
  for (const [id, tag] of [["nav", "nav"], ["monthLabel", "span"], ["pageTitle", "span"], ["main", "main"]]) { const n = new Node(tag); n.id = id; body.appendChild(n); }
  run(`globalThis.__drawn = []; globalThis.__opened = [];
    for (const v of ["Overview", "Entity", "Budget", "Payees", "Bank", "Sql", "Books", "Payroll", "Audit", "Trail", "Settings", "Setup"])
      globalThis["view" + v] = async main => { globalThis.__drawn.push(state.view + ":" + state.entity + ":" + state.month); };
    trailNotice = () => {};
    openSetup = async (kind, id) => { globalThis.__opened.push([kind, id]); state.setup.id = id; syncAddr(); };
    state.meta = { entities: [{ id: 1, code: "AAA", name: "Alpha Test Sdn Bhd", short_name: "Alpha", uses_sql: 1, active: 1, accounts: [] },
      { id: 2, code: "BBB", name: "Beta Test Ltd", short_name: "Beta", uses_sql: 0, active: 1, accounts: [] },
      { id: 3, code: "CCC", name: "Gamma Test Sdn Bhd", short_name: "Gamma", uses_sql: 1, active: 0, accounts: [] }], settings: {}, categories: {}, doc_types: {} };
    state.month = "2026-10"; state.entity = 1; state.day = dayKey();`);
  const drawn = () => run("__drawn").length;
  const layers = () => body.children.filter(c => c.className.includes("dlg-layer"));
  const dec = s => String(s).replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  const toasts = () => toastEl.children.map(c => dec(c.textContent));
  const got = () => ({ view: run("state.view"), entity: run("state.entity"), month: run("state.month"), hash: loc.hash });
  return { run, loc, hist, history, back: () => { if (hist.i > 0) { hist.i--; fire(); } }, forward: () => { if (hist.i < hist.e.length - 1) { hist.i++; fire(); } },
    drawn, layers, toasts, got, drawer, body, toastEl, Node, dispatch, document, seen, handlers };
}


const results = [];
const ok = (name, v, detail) => results.push([name, !!v, detail === undefined ? "" : String(detail)]);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const SQLP = ["overview", "hr/staff", "hr/leave", "hr/claims", "hr/payroll", "payments/approvals", "payments/to-pay", "payments/register", "payments/checklist", "payments/budget", "payments/recurring",
  "accounting/bank", "accounting/sql", "accounting/einvoices", "accounting/books", "accounting/parties", "accounting/statutory", "admin/setup", "admin/audit-pack", "admin/audit-trail", "admin/backup"];
const HEREP = SQLP.filter(p => p !== "accounting/sql");
HEREP.splice(HEREP.indexOf("accounting/statutory") + 1, 0, "accounting/sales", "accounting/purchases", "accounting/journals", "accounting/period-close");
const ENTS = [{ id: 1, code: "AAA", name: "Alpha Test Sdn Bhd", short_name: "Alpha", uses_sql: 1, active: 1, accounts: [], pages: SQLP },
  { id: 2, code: "BBB", name: "Beta Test Ltd", short_name: "Beta", uses_sql: 0, active: 1, accounts: [], pages: HEREP },
  { id: 3, code: "CCC", name: "Gamma Test Sdn Bhd", short_name: "Gamma", uses_sql: 1, active: 0, accounts: [], pages: SQLP }];

(async () => {
  const E = mkEnv(""), { run, loc } = E;
  const settle = () => wait(25), visit = async h => { loc.hash = h; await settle(); };
  const toasts = () => E.toasts(), clearToasts = () => { E.toastEl.children = []; run("TOASTS.list = []"); };
  run(`state.meta.entities = ${JSON.stringify(ENTS)}`);
  await run("routerBoot()"); await settle();
  const nav = () => E.body.querySelector("#nav"), main = () => E.body.querySelector("#main");
  const keys = () => nav().querySelectorAll("a[data-menu]").map(a => a.getAttribute("data-menu"));
  const heads = () => nav().querySelectorAll("button[data-menu-fold]").map(b => b.getAttribute("data-menu-fold"));
  const showOn = async (hash, rows) => { run(`state.menuNext = { items: ${JSON.stringify(rows || [])}, at: Date.now() + 1e9 }`); await visit(hash); run("renderNav()"); };
  const badge = key => { const m = new RegExp(`data-menu-fold="${key}"[\\s\\S]*?</button>`).exec(nav().innerHTML); const b = m && /<span class="nbadge( over)?">(?:<svg[\s\S]*?<\/svg>)?<span aria-hidden="true">(\d+)<\/span><span class="sr-only">([^<]*)<\/span>/.exec(m[0]); return b ? { n: +b[2], over: !!b[1], sr: b[3] } : null; };
  const ovBadge = () => { const m = /data-menu="overview"[^>]*>[\s\S]*?<\/a>/.exec(nav().innerHTML); const b = m && /<span aria-hidden="true">(\d+)<\/span>/.exec(m[0]); return b ? +b[1] : null; };
  const labelsIn = sel => nav().querySelectorAll(sel).map(a => a.querySelectorAll("span")[0].textContent);

  // ---- the menu per company kind ----
  await showOn("#/AAA/2026-10/payments/register");
  ok("a company Kept in SQL Account: the five areas, their items in the design's order, SQL import and no Kept here group", same(keys(), SQLP) && same(heads(), ["hr", "payments", "accounting", "admin"]) && !nav().innerHTML.includes("nav-sub"), keys());
  ok("items are links with an address, not buttons", nav().querySelectorAll("a[data-menu]").every(a => /^#\//.test(a.getAttribute("href"))) && !nav().querySelectorAll("button[data-menu]").length);
  ok("every item has one glyph and its label", nav().querySelectorAll("a[data-menu]").every(a => a.querySelectorAll("svg").length === 1 && a.querySelectorAll("span").length >= 1));
  ok("the area headings are the design's words", same(labelsIn("button[data-menu-fold]"), ["HR", "Payments", "Accounting", "Admin"]));
  const labels = labelsIn("a[data-menu]");
  ok("labels as drawn, and no Calendar and reminders, Salary advances or Users and access", ["Claims and advances", "Payments register", "Monthly checklist", "Bank and reconciliation", "Customers and suppliers", "Statutory payables", "e-Invoices", "SQL import"].every(l => labels.includes(l))
    && !labels.some(l => /Calendar|Salary advances|Users and access/.test(l)), labels);

  await showOn("#/BBB/2026-10/payments/register");
  ok("a company Kept here: no SQL import, and the Kept here group of four after Statutory payables", same(keys(), HEREP) && !keys().includes("accounting/sql") && /nav-sub-label[^>]*>Kept here</.test(nav().innerHTML), keys());
  ok("the Kept here items are Sales, Purchases, Journals, Period close", same(nav().querySelector(".nav-sub").querySelectorAll("a[data-menu]").map(a => a.querySelectorAll("span")[0].textContent), ["Sales", "Purchases", "Journals", "Period close"]));

  await showOn("#/all/2026-10/overview");
  ok("the Overview of All companies: the SQL kind (a company in use is kept in SQL Account)", same(keys(), SQLP) && run("state.addr.all") === true, keys());
  run(`state.meta.entities = ${JSON.stringify(ENTS.map(e => e.id === 1 ? { ...e, active: 0 } : e))}; renderNav()`);
  ok("...the Kept here kind when every company in use is kept here", same(keys(), HEREP), keys());
  run(`state.meta.entities = ${JSON.stringify(ENTS)}`);
  await visit("#/BBB/2026-10/overview");
  ok("the Overview of one company follows that company's kind", same(keys(), HEREP) && run("state.addr.all") === false);

  run(`state.meta.entities = []; state.entity = null; state.view = "overview"; state.addr = { all: true, id: null, params: {} }; state.menuNext = null; renderNav()`);
  ok("no company yet: the same menu as for All companies, drawn without error, no numbers, no address for a company page", same(keys(), SQLP) && !nav().innerHTML.includes("nbadge") && ["hr/staff", "payments/register", "accounting/books"].every(p => nav().querySelectorAll("a[data-menu]").find(a => a.getAttribute("data-menu") === p).getAttribute("href") === "#/"), keys().length);
  { const a = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "payments/register");
    const ev = E.dispatch(a, { type: "click", button: 0 }); await settle();
    ok("no company yet: a click on a company page goes where its address (#/) points, the Overview, and does not draw a page for company null", ev.defaultPrevented && E.got().view === "overview" && run("state.entity") === null, JSON.stringify([ev.defaultPrevented, E.got().view, run("state.view"), run("state.entity"), run("menuHref(MENU_BY_PAGE[\"payments/register\"])"), loc.hash]));
    run(`state.meta.entities = ${JSON.stringify(ENTS)}; state.entity = 1`); }

  run(`state.meta.entities = ${JSON.stringify(ENTS.map(e => ({ ...e, pages: undefined })))}; state.addr.all = false; state.view = "entity"; state.entity = 2; renderNav()`);
  ok("a server that gives no pages: the menu follows the company's kind", same(keys(), HEREP), keys());
  run(`state.meta.entities = ${JSON.stringify(ENTS)}; state.entity = 1`);

  // ---- the numbers on the items, and on a folded area ----
  const ROWS = [{ area: "hr", page: "hr/payroll", entity_id: 1, state: "soon" }, { area: "payments", page: "payments/checklist", entity_id: 1, state: "overdue" }, { area: "payments", page: "payments/register", entity_id: 1, state: "later" },
    { area: "payments", page: "payments/register", entity_id: 2, state: "soon" }, { area: "accounting", page: "accounting/bank", entity_id: 2, state: "today" }, { area: "admin", page: "admin/backup", entity_id: null, state: "later" },
    { area: "hr", page: "hr/payroll", entity_id: 2, state: "overdue" }];
  const itemBadge = page => { const m = new RegExp(`data-menu="${page}"[^>]*>[\\s\\S]*?</a>`).exec(nav().innerHTML); const b = m && /<span class="nbadge( over)?">(?:<svg[\s\S]*?<\/svg>)?<span aria-hidden="true">(\d+)<\/span><span class="sr-only">([^<]*)<\/span>/.exec(m[0]); return b ? { n: +b[2], over: !!b[1], sr: b[3] } : null; };
  const pageBadges = () => ["hr/payroll", "payments/checklist", "payments/register", "accounting/bank", "admin/backup"].map(p => itemBadge(p)?.n ?? null);
  run(`state.menuFold = {}`);
  await showOn("#/AAA/2026-10/payments/register", ROWS);
  ok("AAA: a number on each item the rows name (Payroll 1, Monthly checklist 1 red, Payments register 1, Backup 1: the row with no company counts), none on Bank", same(pageBadges(), [1, 1, 1, null, 1]) && itemBadge("payments/checklist").over && !itemBadge("hr/payroll").over && /1 to do, 1 overdue/.test(itemBadge("payments/checklist").sr), JSON.stringify(pageBadges()));
  ok("...and none on an open area's heading (the number is not counted twice)", ["hr", "payments", "accounting", "admin"].every(k => badge(k) === null));
  ok("Overview carries the total for the company (4)", ovBadge() === 4, ovBadge());
  ok("a red number carries the alert glyph, a blue one does not", /nbadge over"><svg/.test(nav().innerHTML) && !/nbadge"><svg/.test(nav().innerHTML));
  run(`state.menuFold = {hr: true, payments: true, accounting: true}; renderNav()`);
  ok("a folded area shows its own number on the heading (HR 1, Accounting none), and its items are hidden", same(badge("hr"), { n: 1, over: false, sr: ", 1 to do" }) && badge("accounting") === null, JSON.stringify(badge("hr")));
  ok("...the area that holds the page on show stays open, so its heading shows none", badge("payments") === null && !/data-menu-fold="payments"[^>]*aria-expanded="false"/.test(nav().innerHTML));
  run(`state.menuFold = {}`);
  await showOn("#/BBB/2026-10/payments/register", ROWS);
  ok("BBB: Payroll 1 (red), Payments register 1, Bank 1, Backup 1; Overview 4", same(pageBadges(), [1, null, 1, 1, 1]) && itemBadge("hr/payroll").over && ovBadge() === 4, JSON.stringify(pageBadges()));
  await showOn("#/all/2026-10/overview", ROWS);
  ok("All companies: every row (Payroll 2, Checklist 1, Register 2, Bank 1, Backup 1; Overview 7)", same(pageBadges(), [2, 1, 2, 1, 1]) && ovBadge() === 7, JSON.stringify(pageBadges()) + ovBadge());
  run(`state.menuFold = {hr: true, admin: true}; renderNav()`);
  ok("All companies, HR and Admin folded: headings carry HR 2 (red) and Admin 1", badge("hr")?.n === 2 && badge("hr").over && badge("admin")?.n === 1, JSON.stringify([badge("hr"), badge("admin")]));
  run(`state.menuFold = {}`);
  await showOn("#/AAA/2026-10/payments/register", [{ area: "hr", entity_id: 1, state: "soon" }]);
  ok("a row with an area but no page still counts on a folded area and on Overview, not on an item", pageBadges().every(x => x === null) && ovBadge() === 1);
  await showOn("#/AAA/2026-10/payments/register", []);
  ok("with no rows there is no number anywhere", !nav().innerHTML.includes("nbadge"));
  await showOn("#/AAA/2026-10/payments/register", [{ area: "nowhere", entity_id: 1, state: "soon" }, { area: "overview", entity_id: 1, state: "soon" }]);
  ok("a row of an area the menu doesn't have counts nowhere", !nav().innerHTML.includes("nbadge"));
  await showOn("#/AAA/2026-10/payments/register", ROWS);
  ok("a number is read out in words (to do, overdue)", /<span class="sr-only">, 1 to do, 1 overdue<\/span>/.test(nav().innerHTML));

  // ---- every item has a route and its address round-trips ----
  const ALLP = run("MENU_ALL.map(i => i.page)");
  ok("the menu holds 25 items: the 21 of a SQL company and the 4 Kept here", ALLP.length === 25 && same(ALLP.filter(p => !["accounting/sales", "accounting/purchases", "accounting/journals", "accounting/period-close"].includes(p)), SQLP));
  for (const page of ALLP) {
    run(`state.view = "overview"; state.addr.all = true`);
    const r = run(`(() => { const i = MENU_BY_PAGE[${JSON.stringify(page)}], h = menuHref(i), q = parseAddr(h); return { view: i.view, routed: !!ROUTES[i.view], h, q: q && { view: q.view, entity: q.entity }, again: q && addrOf(q), alias: i.alias || null }; })()`);
    ok(`${page} has a route (${r.view}) and an address (${r.h}) that reads back to that page`, r.routed && r.q && r.q.view === r.view && (r.alias ? r.h.includes("/" + r.alias) : r.again === r.h), JSON.stringify(r));
  }
  ok("an item for a page one kind uses goes to a company that uses it, from All companies (SQL import to AAA, Sales to BBB)", run(`menuHref(MENU_BY_PAGE["accounting/sql"])`).startsWith("#/AAA/") && run(`menuHref(MENU_BY_PAGE["accounting/sales"])`).startsWith("#/BBB/"));

  // ---- the page on show is the item marked ----
  const VIEWS = [["overview", "#/all/2026-10/overview", "overview"], ["entity", "#/AAA/2026-10/payments/register", "payments/register"], ["budget", "#/AAA/2026-10/payments/budget", "payments/budget"],
    ["payees", "#/AAA/2026-10/payments/recurring", "payments/recurring"], ["bank", "#/AAA/2026-10/accounting/bank", "accounting/bank"], ["sql", "#/AAA/2026-10/accounting/sql", "accounting/sql"],
    ["books", "#/AAA/accounting/books?tab=pl", "accounting/books"], ["payroll", "#/AAA/2026-10/hr/payroll/workbook", "hr/payroll"], ["audit", "#/AAA/2026-10/admin/audit-pack", "admin/audit-pack"],
    ["trail", "#/admin/audit-trail", "admin/audit-trail"], ["settings", "#/admin/backup", "admin/backup"], ["setup", "#/admin/setup", "admin/setup"], ["staff", "#/AAA/hr/staff", "hr/staff"],
    ["leave", "#/AAA/hr/leave", "hr/leave"], ["claims", "#/AAA/hr/claims", "hr/claims"], ["approvals", "#/AAA/payments/approvals", "payments/approvals"], ["topay", "#/AAA/payments/to-pay", "payments/to-pay"],
    ["einvoices", "#/AAA/2026-10/accounting/einvoices", "accounting/einvoices"], ["parties", "#/AAA/2026-10/accounting/parties", "accounting/parties"], ["statutory", "#/AAA/2026-10/accounting/statutory", "accounting/statutory"],
    ["sales", "#/BBB/accounting/sales", "accounting/sales"], ["purchases", "#/BBB/accounting/purchases", "accounting/purchases"], ["journals", "#/BBB/accounting/journals", "accounting/journals"], ["close", "#/BBB/accounting/period-close", "accounting/period-close"]];
  for (const [view, hash, page] of VIEWS) {
    await showOn(hash);
    const cur = nav().querySelectorAll("a[aria-current]");
    ok(`on ${view} (${hash}) the one item marked aria-current="page" is ${page}`, E.got().view === view && cur.length === 1 && cur[0].getAttribute("data-menu") === page && cur[0].getAttribute("aria-current") === "page" && cur[0].className.includes("on"), E.got().view + " " + cur.map(c => c.getAttribute("data-menu")));
  }
  await showOn("#/AAA/2026-10/accounting/parties");
  await run(`state.books.tab = "tb"; syncAddr()`);
  ok("moving to another Books tab from Customers and suppliers lights Books", nav().querySelectorAll("a[aria-current]")[0]?.getAttribute("data-menu") === "accounting/books" && E.got().view === "books");
  await showOn("#/AAA/2026-10/accounting/parties");
  { const bk = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "accounting/books");
    E.dispatch(bk, { type: "click", button: 0 }); await settle();
    ok("the Books item opens Books on the Trial balance, not on the tab Customers and suppliers left behind, and lights Books", E.got().view === "books" && run("state.books.tab") === "tb" && loc.hash.includes("accounting/books?tab=tb") && nav().querySelectorAll("a[aria-current]")[0]?.getAttribute("data-menu") === "accounting/books", loc.hash + run("state.books.tab")); }
  await showOn("#/AAA/2026-10/accounting/statutory");
  { const bk = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "accounting/books");
    E.dispatch(bk, { type: "click", button: 0 }); await settle();
    ok("...and the same from Statutory payables", E.got().view === "books" && run("state.books.tab") === "tb", run("state.books.tab")); }
  // ---- the focus stays on the item when the menu is drawn again ----
  await showOn("#/AAA/2026-10/payments/budget");
  { const link = () => nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "payments/recurring");
    link().focus();
    run("renderNav()");
    ok("the same menu is not written again, so the focused item stays focused", E.document.activeElement === link() && E.document.activeElement.getAttribute("data-menu") === "payments/recurring");
    run(`state.menuNext = { items: [{ area: "payments", page: "payments/recurring", entity_id: 1, state: "soon" }], at: Date.now() + 1e9 }; renderNav()`);
    ok("...and when the numbers arrive and the menu is written again, the focus goes back to the item that had it", nav().innerHTML.includes("nbadge") && E.document.activeElement === link() && E.document.activeElement.getAttribute("data-menu") === "payments/recurring", String(E.document.activeElement && E.document.activeElement.tagName)); }
  await showOn("#/AAA/2026-10/payments/register");
  ok("the heading above the page names area and page", run("menuCrumb()") === "Payments › Payments register");
  await run("go('overview')"); await settle();
  ok("...Overview has no area in front", run("menuCrumb()") === "Overview");
  await run("go('parties', 1)"); await settle();
  ok("...and an interim landing is named as the menu names it", run("menuCrumb()") === "Accounting › Customers and suppliers");

  // ---- clicking a menu link ----
  await showOn("#/AAA/2026-10/payments/budget");
  { const a = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "hr/staff");
    const ev = E.dispatch(a, { type: "click", button: 0 }); await settle();
    ok("a click on an item opens its page, writes its address, and the browser does not follow the link itself", ev.defaultPrevented && E.got().view === "staff" && loc.hash === "#/AAA/hr/staff", loc.hash);
    const b = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "payments/budget");
    const ev2 = E.dispatch(b, { type: "click", button: 0, ctrlKey: true }); await settle();
    ok("a click with Ctrl (a new tab) is left to the browser: no default prevented, nothing opened here", !ev2.defaultPrevented && E.got().view === "staff", loc.hash);
    const ev3 = E.dispatch(b, { type: "click", button: 1 }); await settle();
    ok("so is a middle click", !ev3.defaultPrevented && E.got().view === "staff"); }
  { const c = nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === "payments/checklist");
    E.dispatch(c, { type: "click", button: 0 }); await settle();
    ok("Monthly checklist opens today's register page", E.got().view === "entity" && loc.hash === "#/AAA/2026-10/payments/register", loc.hash); }

  // ---- folding ----
  const fold = async key => { const b = new E.Node("button"); b.setAttribute("data-menu-fold", key); b.dataset.menuFold = key; E.body.appendChild(b); E.dispatch(b, { type: "click", button: 0 }); await settle(); b.remove(); };
  await showOn("#/AAA/2026-10/accounting/bank");
  const expanded = key => { const m = new RegExp(`data-menu-fold="${key}" aria-expanded="(true|false)"`).exec(nav().innerHTML); return m && m[1]; };
  ok("every group starts open", ["hr", "payments", "accounting", "admin"].every(k => expanded(k) === "true"));
  await fold("hr");
  ok("a click on a heading folds the group (aria-expanded false, its items hidden)", expanded("hr") === "false" && /nav-list" hidden/.test(nav().innerHTML));
  await fold("hr");
  ok("a second click opens it again", expanded("hr") === "true" && !/nav-list" hidden/.test(nav().innerHTML));
  await fold("accounting");
  ok("the group that holds the page on show stays open", expanded("accounting") === "true");
  await fold("accounting");

  // ---- the pages that are not built yet ----
  for (const [view, ent, title] of [["staff", 1, "Staff"], ["leave", 1, "Leave"], ["claims", 1, "Claims and advances"], ["approvals", 1, "Approvals"], ["topay", 1, "To pay"]]) {
    await run(`go("${view}", ${ent})`); await settle();
    const h = main().innerHTML;
    ok(`${title}: a Coming soon page with a sentence about what it will do and a way back, no date`, h.includes(`${title} is coming soon`) && /<p>[^<]{20,}<\/p>/.test(h) && h.includes('data-view="overview"') && !/\d{4}|Q[1-4]|next (week|month)/.test(h.replace(/<svg[\s\S]*?<\/svg>/g, "")), h.slice(0, 200));
  }
  ok("one reusable function draws them all", run("typeof comingSoon") === "function" && run(`(() => { const m = { innerHTML: "" }; comingSoon(m, { title: "X", glyph: "inbox", body: "It will do a thing." }); return m.innerHTML; })()`).includes("X is coming soon"));

  // ---- the Kept here placeholders ----
  for (const [view, title, a, b] of [["sales", "Sales", "Customer invoices", "Receipts (OR series)"], ["purchases", "Purchases", "Supplier invoices (PI series)", "Knock-off"], ["journals", "Journals", "Journal vouchers (JV)", "Reversals"], ["close", "Period close", "Month locks", "Numbering gap check"]]) {
    await run(`go("${view}", 2)`); await settle();
    const h = main().innerHTML;
    ok(`${title} for a company kept here: heading, the not-built-yet note, what will be here, how it connects, the rules`, h.includes(`<h1 id="khTitle"`) && h.includes(`${title} is not built yet`) && h.includes(a) && h.includes(b) && h.includes("How it connects") && h.includes("Rules every document here follows") && h.includes("BBB · Kept here"), h.slice(0, 200));
    const links = [...h.matchAll(/<a href="([^"]+)" data-menu="([^"]+)"/g)];
    ok(`...its links are the menu's addresses`, links.length >= 2 && links.every(m => run(`parseAddr(${JSON.stringify(m[1].replace(/&#39;/g, "'"))})`)), h.slice(0, 100));
  }
  ok("nothing on a placeholder can be entered: no form field or save button", !/<(input|select|textarea)|type="submit"|class="btn"/.test(main().innerHTML));

  // ---- the interim landings ----
  await showOn("#/AAA/2026-10/payments/register"); run("__drawn.length = 0");
  { const click = async page => { E.dispatch(nav().querySelectorAll("a[data-menu]").find(x => x.getAttribute("data-menu") === page), { type: "click", button: 0 }); await settle(); };
    await click("accounting/einvoices");
    ok("the e-Invoices item opens today's SQL import page (its MyInvois part), at its own address", run("__drawn").includes("einvoices:1:2026-10") && loc.hash === "#/AAA/2026-10/accounting/einvoices", loc.hash);
    await click("accounting/parties");
    ok("the Customers and suppliers item opens Books on its parties tab", run("state.books.tab") === "parties" && run("__drawn").pop() === "parties:1:2026-10" && loc.hash === "#/AAA/2026-10/accounting/parties", loc.hash);
    await click("accounting/statutory");
    ok("the Statutory payables item opens Books on its statutory tab", run("state.books.tab") === "statutory" && run("__drawn").pop() === "statutory:1:2026-10" && loc.hash === "#/AAA/2026-10/accounting/statutory", loc.hash);
    await click("accounting/books");
    ok("the Books item opens Books, and its address is the Books one", run("state.view") === "books" && /^#\/AAA\/accounting\/books/.test(loc.hash), loc.hash); }

  // ---- a page the company does not use keeps the 0c rule ----
  await showOn("#/AAA/2026-10/payments/register"); clearToasts();
  await visit("#/BBB/2026-10/accounting/sql");
  ok("SQL import for a company kept here: the Overview and the existing toast", E.got().view === "overview" && toasts().length === 1 && /SQL import isn't used for BBB \(Kept here\)/.test(toasts()[0]), toasts());
  await showOn("#/BBB/2026-10/payments/register"); clearToasts();
  await visit("#/AAA/accounting/sales");
  ok("Sales for a company Kept in SQL Account: the Overview and the toast", E.got().view === "overview" && /Sales aren't used for AAA \(Kept in SQL Account\)/.test(toasts()[0] || ""), toasts());
  await showOn("#/AAA/2026-10/payments/register");
  await run("go('sales', 1)"); await settle();
  ok("...and through go() the card that says so", /Sales aren't used for AAA/.test(main().innerHTML.replace(/&#39;/g, "'")), main().innerHTML.slice(0, 160));

  console.log(JSON.stringify(results));
  process.exit(0);
})().catch(e => { console.log(JSON.stringify([["the probe ran to the end", false, String(e && e.stack || e)]])); process.exit(0); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
out = subprocess.run(["node", str(probe), bundle], capture_output=True, text=True, encoding="utf-8", timeout=180)
try:
    results = json.loads(out.stdout.strip().splitlines()[-1])
except Exception:
    results = [["the probe printed its results", False, (out.stdout + out.stderr)[:800]]]
for name, ok_, detail in results:
    check(name, ok_, detail)

css = Path(__file__).resolve().parents[1].joinpath("static", "app.css").read_text(encoding="utf-8")
narrow = css[css.index("@media (max-width: 860px)"):]
check("a group folded on a wide screen is still shown on a narrow one (beats the global [hidden] rule)",
      ".nav-list[hidden] { display: contents !important; }" in narrow and "[hidden] { display: none !important; }" in css)

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "menu_test" in readme)

print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
