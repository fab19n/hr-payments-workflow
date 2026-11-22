"""The top bar (step 0e): breadcrumb, company switcher, month switcher and account menu with the theme control.
Made-up companies only. The page script (and theme.js) run in Node against the same small stand-in for the page as menu_test, so
core/topbar.js, core/menu.js and core/router.js really run; the pages are stubbed to record that they were drawn.

Checks: the breadcrumb and the month label ('October 2026', no 'payroll'); the company switcher lists the companies in use only (a stopped
one is left out) with kind, to-do count and an overdue mark; All companies only on the Overview; the 'No company yet' state with Add your
first company (opens Setup > Companies with the add form); the keys (open, move, wrap, Home, End, letters, Escape, Tab, click away,
focus back on the button); switching company keeps the page where the company uses it (from the server's pages) and otherwise lands on its
Overview with the 'Switched to' toast; the bar follows the address (Back, Forward); the month buttons write the address; the account menu
holds the theme control (role group, aria-pressed per option, data-theme and the same storage key); no search box, no bell.

Run: .venv\Scripts\python -m synthetic_tests.topbar_test
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


tmp = Path(tempfile.mkdtemp(prefix="hrp-topbar-test-"))
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
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (m, c) => c.toUpperCase())] = String(v); }
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
    for (const v of ["Overview", "Entity", "Checklist", "Budget", "Payees", "Bank", "Sql", "Books", "Payroll", "Audit", "Trail", "Settings", "Setup"])
      globalThis["view" + v] = async main => { globalThis.__drawn.push(state.view + ":" + state.entity + ":" + state.month); };
    trailNotice = () => {};
    openSetup = async (kind, id) => { globalThis.__opened.push([kind, id]); state.setup.id = id; syncAddr(); };
    state.meta = { entities: [{ id: 1, code: "AAA", name: "Alpha Test Sdn Bhd", short_name: "Alpha", uses_sql: 1, active: 1, accounts: [] },
      { id: 2, code: "BBB", name: "Beta Test Ltd", short_name: "Beta", uses_sql: 0, active: 1, accounts: [] },
      { id: 3, code: "CCC", name: "Gamma Test Sdn Bhd", short_name: "Gamma", uses_sql: 1, active: 0, accounts: [] }], settings: {}, categories: {}, doc_types: {} };
    state.month = "2026-10"; state.entity = 1; state.day = dayKey();`);
  const drawn = () => run("__drawn").length;
  const layers = () => body.children.filter(c => c.className.includes("dlg-layer"));
  const html = n => slot(n).innerHTML, rowHtml = i => html("company").split('role="menuitemradio"')[i + 1] || "";  // a node keeps no HTML of its own here: the slot's is the one set
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
  { id: 3, code: "CCC", name: "Gamma Test Sdn Bhd", short_name: "Gamma", uses_sql: 1, active: 0, accounts: [], pages: SQLP },
  { id: 4, code: "DDD", name: "Delta Test Sdn Bhd", short_name: "Delta", uses_sql: 1, active: 1, accounts: [], pages: SQLP }];

(async () => {
  const E = mkEnv(""), { run, loc } = E;
  const settle = () => wait(25), visit = async h => { loc.hash = h; await settle(); };
  const toasts = () => E.toasts(), clearToasts = () => { E.toastEl.children = []; run("TOASTS.list = []"); };
  // the page as index.html has it: the top bar's own parts
  const mk = (tag, id) => { const n = new E.Node(tag); n.id = id; E.body.appendChild(n); return n; };
  mk("div", "tbCompany"); mk("div", "tbUser"); mk("button", "prevMonth"); mk("button", "nextMonth"); const thisM = mk("button", "thisMonth"); thisM.hidden = true;
  // theme.js, as the page loads it in <head>; storage that records what it is asked
  const root = { attr: null, setAttribute(k, v) { root.attr = v; }, removeAttribute() { root.attr = null; } };
  E.document.documentElement = root;
  run(`globalThis.__store = { set: [], removed: [] }; globalThis.localStorage = { getItem: () => null, setItem: (k, v) => globalThis.__store.set.push([k, v]), removeItem: k => globalThis.__store.removed.push(k) }`);
  run(fs.readFileSync(process.argv[3], "utf8"));
  run(`state.meta.entities = ${JSON.stringify(ENTS)}`);
  await run("routerBoot()"); await settle();
  const slot = n => E.body.querySelector(n === "user" ? "#tbUser" : "#tbCompany");
  const btn = n => slot(n).querySelector("button[data-tb-toggle]");
  const menu = n => slot(n).querySelector(".tb-menu");
  const rows = () => menu("company") ? menu("company").querySelectorAll(".tm") : [];
  const rowCodes = () => rows().map(r => r.getAttribute("data-ta"));
  const active = () => E.document.activeElement.id || "";
  const key = (el, k, extra) => E.dispatch(el, { type: "keydown", key: k, ...(extra || {}) });
  const click = async el => { E.dispatch(el, { type: "click", button: 0 }); await settle(); };
  const shut = async () => { if (menu("company") || menu("user")) { E.dispatch(E.body.querySelector("button[data-tb-away]"), { type: "click", button: 0 }); await settle(); } };
  const text = el => String(el.textContent).replace(/\s+/g, " ").trim();
  const html = n => slot(n).innerHTML, rowHtml = i => html("company").split('role="menuitemradio"')[i + 1] || "";  // a node keeps no HTML of its own here: the slot's is the one set
  const dec = s => String(s).replace(/&#39;/g, "'");

  // ---- the bar as drawn ----
  await visit("#/AAA/2026-10/payments/register");
  { const crumb = E.body.querySelector("#pageTitle"), spans = crumb.querySelectorAll("span"), parts = spans.map(s => text(s)), last = spans[spans.length - 1];
    ok("the breadcrumb names area, a chevron glyph, then the page (the page is aria-current)", parts.join("|") === "Payments|Payments register" && crumb.querySelectorAll("svg").length === 1 && last.getAttribute("aria-current") === "page" && /crumb-area/.test(crumb.innerHTML), parts); }
  ok("the month reads 'October 2026', without the word payroll", text(E.body.querySelector("#monthLabel")) === "October 2026", text(E.body.querySelector("#monthLabel")));
  { const cur = run("state.month === currentCycle()");
    ok("Current shows only when the month is not the current one", thisM.hidden === cur, `${cur} ${thisM.hidden}`); }
  ok("the company button shows the code and the kind", text(btn("company")) === "AAA·Kept in SQL Account" && btn("company").getAttribute("aria-haspopup") === "menu" && btn("company").getAttribute("aria-expanded") === "false", text(btn("company")));
  ok("its name says what it is and what it does", /^AAA · Kept in SQL Account, Alpha Test Sdn Bhd, change company$/.test(btn("company").getAttribute("aria-label")), btn("company").getAttribute("aria-label"));
  ok("the menu is not drawn while closed", !menu("company") && !E.body.querySelector("button[data-tb-away]"));
  ok("there is no search box and no bell", !/search|bell|notification/i.test(slot("company").innerHTML + slot("user").innerHTML));
  ok("the account button names itself and starts closed", btn("user").getAttribute("aria-label") === "Account menu" && btn("user").getAttribute("aria-haspopup") === "menu" && btn("user").getAttribute("aria-expanded") === "false");

  // ---- the company menu ----
  run(`state.menuNext = { items: ${JSON.stringify([{ area: "payments", entity_id: 1, state: "overdue" }, { area: "hr", entity_id: 1, state: "soon" }, { area: "payments", entity_id: 2, state: "soon" }, { area: "admin", entity_id: null, state: "later" }])}, at: Date.now() + 1e9 }`);
  await click(btn("company"));
  ok("a click opens the menu: aria-expanded true, role menu, a click-away layer", btn("company").getAttribute("aria-expanded") === "true" && menu("company").getAttribute("role") === "menu" && !!E.body.querySelector("button[data-tb-away]"));
  ok("it lists the companies in use only: a stopped company is left out", same(rowCodes(), ["AAA", "BBB", "DDD"]) && !slot("company").innerHTML.includes("CCC"), rowCodes());
  ok("each row shows the code, the company's short name (Setup's, here) and the kind; the full name is in the row's title",
    /Alpha/.test(text(rows()[0])) && !/Sdn Bhd/.test(text(rows()[0])) && /Kept in SQL Account/.test(text(rows()[0])) && /Kept here/.test(text(rows()[1])) && /Delta/.test(text(rows()[2])) && !/Sdn Bhd/.test(text(rows()[2]))
    && /class="tb-name" title="Alpha Test Sdn Bhd">Alpha</.test(rowHtml(0)) && /class="tb-name" title="Delta Test Sdn Bhd">Delta</.test(rowHtml(2)), text(rows()[0]) + " | " + rowHtml(0).slice(0, 400));
  ok("the footnote says stopped companies are not offered", /Stopped companies are not offered\./.test(text(menu("company"))));
  ok("the company on show is checked", rows()[0].getAttribute("aria-checked") === "true" && rows()[1].getAttribute("aria-checked") === "false");
  ok("All companies is not offered away from the Overview", !rowCodes().includes("all companies"));
  ok("the to-do count per company (the row with no company counts for each), overdue in red with the alert mark",
    /tb-badge over"><svg[\s\S]*?<span aria-hidden="true">3<\/span>/.test(rowHtml(0)) && /tb-badge"><span aria-hidden="true">2<\/span>/.test(rowHtml(1)) && /tb-badge"><span aria-hidden="true">1<\/span>/.test(rowHtml(2)), rowHtml(0).slice(-200));
  ok("a row's name is read out with its count", /^AAA, Alpha Test Sdn Bhd, Kept in SQL Account, 3 to do, 1 overdue$/.test(rows()[0].getAttribute("aria-label")), rows()[0].getAttribute("aria-label"));
  ok("opening puts the focus on the company on show", active() === "tb-mi-company-0", active());

  // ---- keys ----
  { const ev = key(E.document.activeElement, "ArrowDown");
    ok("ArrowDown moves to the next item (and the page does not scroll)", active() === "tb-mi-company-1" && ev.defaultPrevented, active()); }
  key(E.document.activeElement, "ArrowDown"); key(E.document.activeElement, "ArrowDown");
  ok("ArrowDown wraps from the last item to the first", active() === "tb-mi-company-0", active());
  key(E.document.activeElement, "ArrowUp");
  ok("ArrowUp wraps from the first item to the last", active() === "tb-mi-company-2", active());
  key(E.document.activeElement, "Home"); const h0 = active(); key(E.document.activeElement, "End");
  ok("Home jumps to the first, End to the last", h0 === "tb-mi-company-0" && active() === "tb-mi-company-2", h0 + " " + active());
  key(E.document.activeElement, "b");
  ok("a letter typed moves to the company that starts with it", active() === "tb-mi-company-1", active());
  { const ev = key(E.document.activeElement, "Escape");
    ok("Escape closes the menu and puts the focus back on the button", ev.defaultPrevented && !menu("company") && active() === "tb-mb-company" && btn("company").getAttribute("aria-expanded") === "false", active()); }
  key(E.document.activeElement, "ArrowDown");
  ok("ArrowDown on the button opens the menu and focuses the company on show", !!menu("company") && active() === "tb-mi-company-0", active());
  key(E.document.activeElement, "Tab");
  ok("Tab closes the menu", !menu("company"));
  key(btn("company"), "ArrowUp");
  ok("ArrowUp on the button opens it on the last item", !!menu("company") && active() === "tb-mi-company-2", active());
  await click(E.body.querySelector("button[data-tb-away]"));
  ok("a click outside closes it", !menu("company") && !E.body.querySelector("button[data-tb-away]"));
  await click(btn("company"));
  ok("Enter or Space (a click on the button) opens it", !!menu("company"));
  await click(btn("company"));
  ok("the same again closes it, with the focus on the button", !menu("company") && active() === "tb-mb-company", active());
  await click(btn("user")); await click(btn("company"));
  ok("opening one menu closes the other", !!menu("company") && !menu("user"));
  await shut();

  // ---- the short name: the one set in Setup, else the name without Sdn Bhd, Bhd, Ltd or Limited; the full name for a screen reader ----
  { const was = run("JSON.stringify(state.meta.entities)");
    const mkE = (id, code, name, short) => ({ id, code, name, short_name: short, uses_sql: 1, active: 1, accounts: [], pages: SQLP });
    const LIST = [mkE(1, "S1", "Example Alpha Sdn Bhd", null), mkE(2, "S2", "Example Beta Sdn. Bhd.", ""), mkE(3, "S3", "Example Gamma Bhd", null), mkE(4, "S4", "Example Delta Ltd", null),
      mkE(5, "S5", "Example Epsilon Limited", null), mkE(6, "S6", "Example Zeta Ltd.", "  Zed "), mkE(7, "S7", "Example <b>Eta</b> Ltd", "<i>Eta</i> & Co"), mkE(8, "S8", "Ltd", null),
      mkE(9, "S9", "Example Theta Sdn Bhd Services", null), mkE(10, "S10", "Example Iota, Ltd", null)];
    run(`state.meta.entities = ${JSON.stringify(LIST)}`);
    await click(btn("company"));
    const shown = LIST.map((_, i) => (/class="tb-name"[^>]*>(.*?)<\/span>/.exec(rowHtml(i)) || [])[1]), all = html("company");
    ok("a row shows the short name set in Setup (trimmed), else the name without Sdn Bhd, Sdn. Bhd., Bhd, Ltd or Limited at its end; the whole name when nothing is left; escaped",
      same(shown, ["Example Alpha", "Example Beta", "Example Gamma", "Example Delta", "Example Epsilon", "Zed", "&lt;i&gt;Eta&lt;/i&gt; &amp; Co", "Ltd", "Example Theta Sdn Bhd Services", "Example Iota"]) && !/<i>|<b>/.test(all), shown);
    ok("the full name is in the row's title when the row shows less, and in what a screen reader hears (escaped)",
      /class="tb-name" title="Example Alpha Sdn Bhd">/.test(rowHtml(0)) && /class="tb-name" title="Example Zeta Ltd\.">/.test(rowHtml(5)) && !/title=/.test((/class="tb-name"[^>]*>/.exec(rowHtml(7)) || [""])[0])
      && all.includes('aria-label="S1, Example Alpha Sdn Bhd, Kept in SQL Account') && all.includes('aria-label="S7, Example &lt;b&gt;Eta&lt;/b&gt; Ltd, Kept in SQL Account') && all.includes('title="Example &lt;b&gt;Eta&lt;/b&gt; Ltd"'), rowHtml(0).slice(0, 300));
    await shut();
    run(`state.meta.entities = ${was}`); }

  // ---- switching company ----
  clearToasts();
  await click(btn("company")); await click(rows()[1]);
  ok("a company that uses the page: the same page, at its address", E.got().view === "entity" && E.got().entity === 2 && loc.hash === "#/BBB/2026-10/payments/register" && toasts().length === 0, loc.hash + " " + toasts());
  ok("the button follows: BBB, Kept here; the menu is closed and the focus is on the button", text(btn("company")) === "BBB·Kept here" && !menu("company") && active() === "tb-mb-company", text(btn("company")) + active());
  await visit("#/BBB/accounting/sales"); clearToasts();
  await click(btn("company")); await click(rows()[0]);
  ok("a company that does not use the page (Sales, for one Kept in SQL Account): its Overview", E.got().view === "overview" && E.got().entity === 1 && loc.hash === "#/AAA/2026-10/overview", loc.hash);
  ok("...with the toast 'Switched to AAA' and why", toasts().length === 1 && /Switched to AAA/.test(toasts()[0]) && /Sales aren't used for AAA \(Kept in SQL Account\)/.test(dec(toasts()[0])), toasts());
  await visit("#/AAA/2026-10/accounting/sql"); clearToasts();
  await click(btn("company")); await click(rows()[1]);
  ok("SQL import to a company Kept here: its Overview and the toast", E.got().view === "overview" && E.got().entity === 2 && /SQL import isn't used for BBB \(Kept here\)/.test(dec(toasts()[0] || "")), loc.hash + toasts());
  await visit("#/AAA/hr/staff"); clearToasts();
  await click(btn("company")); await click(rows()[2]);
  ok("a page every kind has (Staff): kept for another company, from the server's pages", E.got().view === "staff" && E.got().entity === 4 && loc.hash === "#/DDD/hr/staff" && toasts().length === 0, loc.hash);
  await visit("#/AAA/accounting/books?tab=pl&from=2026-01-01&to=2026-03-31"); clearToasts();
  await click(btn("company")); await click(rows()[2]);
  ok("Books keeps its tab for the new company, and leaves the old company's dates behind", E.got().view === "books" && /^#\/DDD\/accounting\/books\?tab=pl$/.test(loc.hash), loc.hash);
  await visit("#/AAA/2026-10/payments/register");
  await click(btn("company")); await click(rows()[0]);
  ok("picking the company already on show only closes the menu", !menu("company") && loc.hash === "#/AAA/2026-10/payments/register");
  await visit("#/AAA/2026-10/payments/register?pay=1"); await click(btn("company")); await click(rows()[1]);
  ok("a filter of the old company is not taken to the new one", loc.hash === "#/BBB/2026-10/payments/register", loc.hash);
  await visit("#/admin/backup");
  await click(btn("company")); await click(rows()[2]);
  ok("on a page with no company in its address (Backup) the choice still changes the company", E.got().view === "settings" && E.got().entity === 4 && text(btn("company")).startsWith("DDD") && loc.hash === "#/admin/backup", E.got().entity + loc.hash);

  // ---- All companies: the Overview only ----
  await visit("#/AAA/2026-10/overview");
  await click(btn("company"));
  ok("on the Overview All companies is the first row, then a rule", rowCodes()[0] === "all companies" && /role="separator"/.test(html("company")) && rows()[0].getAttribute("aria-checked") === "false", rowCodes());
  ok("...its count is every company's rows (4)", /<span aria-hidden="true">4<\/span>/.test(rowHtml(0)), rowHtml(0).slice(-100));
  await click(rows()[0]);
  ok("choosing it opens the Overview of all companies at its address", loc.hash === "#/all/2026-10/overview" && run("state.addr.all") === true, loc.hash);
  ok("the button says All companies, with no kind", text(btn("company")) === "All companies" && /aria-label="All companies, change company"/.test(slot("company").innerHTML), text(btn("company")));
  await click(btn("company"));
  ok("with All on show it is the checked row", rows()[0].getAttribute("aria-checked") === "true" && rows().slice(1).every(r => r.getAttribute("aria-checked") === "false"));
  clearToasts();
  await click(rows()[1]);
  ok("picking a company from All opens that company's Overview, with no toast", loc.hash === "#/AAA/2026-10/overview" && run("state.addr.all") === false && toasts().length === 0, loc.hash);
  await visit("#/BBB/2026-10/payments/budget");
  ok("leaving the Overview, the switcher shows the company again", text(btn("company")).startsWith("BBB"));

  // ---- the bar follows the address ----
  await visit("#/AAA/2026-10/payments/register"); await visit("#/BBB/2026-10/payments/register");
  ok("a new address moves the company control", text(btn("company")).startsWith("BBB"));
  E.back(); await settle();
  ok("Back puts it on the earlier company", text(btn("company")).startsWith("AAA") && loc.hash === "#/AAA/2026-10/payments/register", loc.hash);
  E.forward(); await settle();
  ok("Forward on the later one", text(btn("company")).startsWith("BBB"));

  // ---- the month ----
  await visit("#/AAA/2026-10/payments/register");
  await click(E.body.querySelector("#prevMonth"));
  ok("Previous month writes the address and reads 'September 2026'", loc.hash === "#/AAA/2026-09/payments/register" && text(E.body.querySelector("#monthLabel")) === "September 2026", loc.hash);
  await click(E.body.querySelector("#nextMonth")); await click(E.body.querySelector("#nextMonth"));
  ok("Next month moves on: 'November 2026'", loc.hash === "#/AAA/2026-11/payments/register" && text(E.body.querySelector("#monthLabel")) === "November 2026", loc.hash);
  run(`state.month = shiftMonth(currentCycle(), 2); renderNav()`);
  ok("Current is shown for a month that is not the current one", thisM.hidden === false);
  await click(thisM);
  ok("Current goes back to this month, at its address, and hides itself", run("state.month") === run("currentCycle()") && loc.hash.includes(run("currentCycle()")) && thisM.hidden === true, loc.hash);

  // ---- no company yet ----
  run(`state.meta.entities = []; state.entity = null; state.view = "overview"; state.addr = { all: true, id: null, params: {} }; state.menuNext = null; renderNav()`);
  ok("with no company the button says 'No company yet' and has no kind", text(btn("company")) === "No company yet" && btn("company").getAttribute("aria-label") === "No company yet, open the company menu", text(btn("company")));
  await click(btn("company"));
  ok("the menu holds one item, Add your first company, and no company, header or footnote", same(rowCodes(), ["add"]) && /Add your first company/.test(html("company")) && !/Stopped companies|Next up/.test(html("company")), rowCodes());
  ok("the focus is on it", active() === "tb-mi-company-0");
  run("__opened.length = 0");
  await click(rows()[0]);
  ok("it opens Setup > Companies with the add form open", E.got().view === "setup" && run("state.setup.kind") === "entities" && same(run("__opened"), [["entities", "new"]]) && /^#\/admin\/setup\/entities/.test(loc.hash) && !menu("company"), loc.hash + JSON.stringify(run("__opened")));
  run(`state.meta.entities = ${JSON.stringify(ENTS)}; state.entity = 1`);
  await visit("#/AAA/2026-10/payments/register");

  // ---- the account menu and the theme ----
  await click(btn("user"));
  ok("the account menu opens: role menu, what stays on this PC, the audit trail", !!menu("user") && menu("user").getAttribute("role") === "menu" && /Records stay on this PC/.test(html("user")) && /Audit trail/.test(html("user")));
  ok("it offers no sign-out and no users page (no sign-in yet)", !/Sign out|Users and access/.test(html("user")));
  const grp = () => menu("user").querySelector('[role="group"]'), opts = () => menu("user").querySelectorAll("button[data-theme-set]");
  const pressed = () => opts().map(b => b.getAttribute("aria-pressed"));
  ok("the theme is a group of three buttons, Auto, Light, Dark, each with aria-pressed", !!grp() && same(opts().map(b => b.getAttribute("data-theme-set")), ["auto", "light", "dark"]) && same(opts().map(b => text(b)), ["Auto", "Light", "Dark"]) && opts().every(b => b.hasAttribute("aria-pressed")) && !!grp().getAttribute("aria-labelledby"));
  ok("with no choice stored, Auto is the one pressed", same(pressed(), ["true", "false", "false"]), pressed());
  ok("each option has a glyph: auto, sun, moon", ["auto", "sun", "moon"].every((g, i) => new RegExp(`data-theme-set="${["auto", "light", "dark"][i]}"[^>]*><svg[^>]*><use href="[^"]*#i-${g}"`).test(html("user"))));
  ok("focus starts on the first item", active() === "tb-mi-user-0", active());
  key(E.document.activeElement, "ArrowDown"); key(E.document.activeElement, "ArrowDown");
  ok("ArrowDown goes on to the theme options", active() === "tb-mi-user-2", active());
  await click(opts()[2]);
  ok("Dark: data-theme is set, the choice is stored under hrp-theme, Dark is the one pressed", root.attr === "dark" && same(run("__store.set"), [["hrp-theme", "dark"]]) && same(pressed(), ["false", "false", "true"]) && !!menu("user"), root.attr + JSON.stringify(run("__store.set")));
  await click(opts()[1]);
  ok("Light", root.attr === "light" && run("__store.set").pop()[1] === "light" && same(pressed(), ["false", "true", "false"]), pressed());
  await click(opts()[0]);
  ok("Auto: data-theme is removed and the stored choice is cleared", root.attr === null && run("__store.removed").includes("hrp-theme") && same(pressed(), ["true", "false", "false"]));
  await click(opts()[2]); await shut(); await click(btn("user"));
  ok("opened again, the menu shows the theme in use (Dark)", same(pressed(), ["false", "false", "true"]), pressed());
  key(E.document.activeElement, "Escape");
  ok("Escape closes the account menu with the focus on its button", !menu("user") && active() === "tb-mb-user", active());
  await click(btn("user")); await click(menu("user").querySelector("a[data-tb-go]"));
  ok("the audit trail item opens that page and closes the menu", E.got().view === "trail" && loc.hash === "#/admin/audit-trail" && !menu("user"), loc.hash);

  console.log(JSON.stringify(results));
  process.exit(0);
})().catch(e => { console.log(JSON.stringify([["the probe ran to the end", false, String(e && e.stack || e)]])); process.exit(0); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
out = subprocess.run(["node", str(probe), bundle, str(Path(__file__).resolve().parents[1] / "static" / "theme.js")], capture_output=True, text=True, encoding="utf-8", timeout=180)
try:
    results = json.loads(out.stdout.strip().splitlines()[-1])
except Exception:
    results = [["the probe printed its results", False, (out.stdout + out.stderr)[:800]]]
for name, ok_, detail in results:
    check(name, ok_, detail)

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "topbar_test" in readme)

print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
