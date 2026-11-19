"""Addresses (step 0d): every page has an address, so Back, Forward and Refresh keep your place and a card link lands on a filter.
Made-up companies only. The page script is run in Node against a small stand-in for the page that also has a location, a history
and hashchange (a hash assignment adds an entry and raises hashchange later; replaceState changes the entry and raises nothing),
so core/router.js really runs; the pages themselves are stubbed to record that they were drawn.

Checks: the one table of pages holds every old page key; go(view, entity) writes its final address
(#/CODE/YYYY-MM/area/page, #/CODE/area/page, #/area/page) and parseAddr(addrOf(place)) round-trips; a hashchange to each address
applies that place, once; Back and Forward; refresh (booting with an address) lands on the page, month and filter; an unknown
company, a bad month, an unknown page, all on a page that is one company's, and a page the company does not use land on the
Overview with the toast; Keep editing on an unsaved drawer puts the previous address back without a new entry or a redraw; our own
writes are not applied twice; every Next up go shape maps to an address and back; the month, company and Setup buttons write the
address; with no location the place is applied and nothing is written; no address holds anything but a company code, a month, route
words, record numbers and the known filter keys.

Run: .venv\\Scripts\\python -m synthetic_tests.addresses_test
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


tmp = Path(tempfile.mkdtemp(prefix="hrp-addresses-test-"))
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

(async () => {
  const E = mkEnv(""), { run, loc } = E;
  const settle = () => wait(25);
  const toasts = () => E.toasts(), clearToasts = () => { E.toastEl.children = []; run("TOASTS.list = []"); };
  const visit = async h => { loc.hash = h; await settle(); };
  await run("routerBoot()"); await settle();

  // ---- the table ----
  ok("ROUTES has the twelve old page keys", same(run("Object.keys(ROUTES)"), ["overview", "entity", "budget", "payees", "bank", "sql", "books", "payroll", "audit", "trail", "settings", "setup"]), run("Object.keys(ROUTES)"));
  ok("with no address the Overview opens and its address is written in place of the empty one", loc.hash === "#/all/2026-10/overview" && E.hist.e.length === 1 && E.got().view === "overview" && E.drawn() === 1, JSON.stringify(E.got()));
  ok("the hashchange listener is on", E.handlers.length === 1);

  // ---- go(view, entity) writes its address, and the address reads back ----
  const GO = [["overview", null, "#/all/2026-10/overview"], ["entity", 2, "#/BBB/2026-10/payments/register"], ["budget", 1, "#/AAA/2026-10/payments/budget"],
    ["payees", 1, "#/AAA/2026-10/payments/recurring"], ["bank", 1, "#/AAA/2026-10/accounting/bank"], ["sql", 1, "#/AAA/2026-10/accounting/sql"],
    ["books", 1, "#/AAA/accounting/books?tab=tb"], ["payroll", 1, "#/AAA/2026-10/hr/payroll/workbook"], ["audit", 1, "#/AAA/2026-10/admin/audit-pack"],
    ["trail", null, "#/admin/audit-trail"], ["settings", null, "#/admin/backup"], ["setup", null, "#/admin/setup"]];
  for (const [view, ent, want] of GO) {
    const n0 = E.hist.e.length, d0 = E.drawn();
    const r = await run(`go("${view}", ${ent})`); await settle();
    const g = E.got(), back = run(`parseAddr(${JSON.stringify(g.hash)})`);
    ok(`go("${view}") writes ${want}`, g.hash === want && g.view === view && r === true, g.hash);
    ok(`go("${view}"): one new history entry, drawn once (our own write is not applied twice)`, (E.hist.e.length === n0 + 1 || (view === "overview" && n0 === 1 && E.hist.e.length === 1)) && E.drawn() === d0 + 1, `${E.hist.e.length - n0} entries, ${E.drawn() - d0} draws`);
    ok(`go("${view}"): the address reads back to the same page, company and month`, back && back.view === view && same(run(`addrOf(parseAddr(${JSON.stringify(g.hash)}))`), g.hash)
       && back.month === (["books", "trail", "settings", "setup"].includes(view) ? null : "2026-10") && (view === "overview" ? back.entity === "all" : ["trail", "settings", "setup"].includes(view) ? back.entity === null : back.entity === g.entity), JSON.stringify(back));
  }
  await run(`state.setup.kind = "entities"; go("setup")`); await settle();
  ok("Setup keeps its section in the address", loc.hash === "#/admin/setup/entities", loc.hash);
  await run(`go("overview")`); await settle();
  const n1 = E.hist.e.length, d1 = E.drawn(); await run(`go("overview")`); await settle();
  ok("the same page again writes no new history entry but draws again", E.hist.e.length === n1 && E.drawn() === d1 + 1 && loc.hash === "#/all/2026-10/overview");

  // ---- a hashchange to each address applies that place ----
  const ADDRS = [
    ["#/AAA/2026-09/payments/register", s => s.view === "entity" && s.entity === 1 && s.month === "2026-09"],
    ["#/BBB/2026-08/payments/register/77", s => s.view === "entity" && s.entity === 2 && s.month === "2026-08" && s.open === 77],
    ["#/AAA/2026-10/payments/register?mark=past_legal", s => s.view === "entity" && s.markPay],
    ["#/AAA/2026-10/payments/register?pay=21,22", s => s.view === "entity" && s.markIds === "21,22"],
    ["#/AAA/2026-10/payments/register?task=11", s => s.view === "entity" && s.markTask],
    ["#/AAA/2026-10/payments/budget?as_at=2026-10-05", s => s.view === "budget" && s.asAt === "2026-10-05"],
    ["#/AAA/2026-10/payments/recurring", s => s.view === "payees"],
    ["#/AAA/2026-10/accounting/bank?filter=to_explain&account=5", s => s.view === "bank" && s.bankOnly && s.focus === 5],
    ["#/BBB/2026-10/accounting/bank", s => s.view === "bank" && s.entity === 2 && !s.bankOnly],
    ["#/AAA/2026-10/accounting/sql", s => s.view === "sql"],
    ["#/AAA/accounting/books?tab=gl&from=2026-01-01&to=2026-03-31", s => s.view === "books" && s.tab === "ledger" && s.from === "2026-01-01" && s.to === "2026-03-31"],
    ["#/AAA/accounting/books?tab=suppliers", s => s.view === "books" && s.tab === "parties" && s.side === "suppliers" && !s.from],
    ["#/AAA/accounting/books?tab=statutory", s => s.view === "books" && s.tab === "statutory"],
    ["#/AAA/2026-10/hr/payroll/workbook", s => s.view === "payroll"],
    ["#/AAA/2026-10/admin/audit-pack", s => s.view === "audit"],
    ["#/admin/audit-trail", s => s.view === "trail"],
    ["#/admin/backup", s => s.view === "settings"],
    ["#/admin/setup/guess_words", s => s.view === "setup" && s.kind === "guess_words" && s.setupId == null],
    ["#/admin/setup/entities/2", s => s.view === "setup" && s.kind === "entities" && s.opened === "entities:2"],
    ["#/BBB/2026-10/overview", s => s.view === "overview" && s.entity === 2 && s.all === false],
    ["#/all/2026-07/overview", s => s.view === "overview" && s.month === "2026-07" && s.all === true],
  ];
  const snap = () => run(`({ view: state.view, entity: state.entity, month: state.month, open: state.openPayment, markPay: !!state.mark?.pay, markTask: !!state.mark?.task,
    markIds: state.mark?.pay ? [1, 2, 21, 22, 23].filter(i => state.mark.pay({ id: i })).join(",") : "", asAt: state.asAt, bankOnly: state.bankOnly, focus: state.focusBank?.account ?? null,
    tab: state.books.tab, side: state.books.side, from: state.books.from, to: state.books.to, kind: state.setup.kind, setupId: state.setup.id, all: state.addr.all,
    opened: (__opened[__opened.length - 1] || []).join(":") })`);
  for (const [a, test] of ADDRS) {
    run("__opened.length = 0");
    const n0 = E.hist.e.length, d0 = E.drawn();
    await visit(a);
    const s = snap();
    ok(`a hashchange to ${a} applies it, once, and leaves the address as typed`, test(s) && E.drawn() === d0 + 1 && loc.hash === a && E.hist.e.length === n0 + 1, JSON.stringify(s) + " " + loc.hash);
  }
  await visit("#/AAA/2026-10/payments/checklist");
  ok("the checklist address opens the register and is tidied in place", loc.hash === "#/AAA/2026-10/payments/register" && E.got().view === "entity" && E.hist.e.length === E.hist.i + 1, loc.hash);
  await visit("#/aaa/2026-10/payments/budget");
  ok("a company code is found whatever its capitals, and written as the company has it", loc.hash === "#/AAA/2026-10/payments/budget" && E.got().entity === 1, loc.hash);
  await visit("#/CCC/2026-10/payments/budget");
  ok("a stopped company's address still opens", E.got().entity === 3 && E.got().view === "budget");

  // ---- Back and Forward ----
  await visit("#/AAA/2026-10/payments/register"); await visit("#/AAA/2026-10/accounting/bank?account=5"); await visit("#/BBB/2026-09/overview");
  let d0 = E.drawn();
  E.back(); await settle();
  ok("Back returns to the page before, with its filter", loc.hash === "#/AAA/2026-10/accounting/bank?account=5" && E.got().view === "bank" && E.got().entity === 1 && run("state.addr.params.account") === "5" && E.drawn() === d0 + 1, loc.hash);
  E.back(); await settle();
  ok("Back again, month and company kept", E.got().view === "entity" && E.got().month === "2026-10" && E.got().entity === 1);
  E.forward(); await settle(); E.forward(); await settle();
  ok("Forward goes on", E.got().view === "overview" && E.got().entity === 2 && loc.hash === "#/BBB/2026-09/overview" && E.got().month === "2026-09", JSON.stringify(E.got()));

  // ---- bad addresses land on the Overview with the toast ----
  const BAD = ["#/ZZZ/2026-10/payments/register", "#/AAA/2026-13/payments/register", "#/AAA/2026-10/nowhere/page", "#/AAA/2026-10/payments/nope", "#/all/2026-10/payments/register",
    "#/AAA/payments/register", "#/AAA/2026-10/payments/register/abc", "#/AAA/2026-10/payments/register/1/2", "#/foo", "#/AAA/2026-10/accounting/books", "#/AAA/admin/setup",
    "#/admin/nothing", "#/AAA/2026-10/overview/more", "#/all/2026-10/admin/audit-pack", "#/%E0%A4%A/2026-10/overview", "#abc"];
  for (const a of BAD) {
    await visit("#/AAA/2026-10/payments/budget");
    clearToasts();
    const before = 0, n0 = E.hist.e.length;
    await visit(a);
    const g = E.got(), t = toasts();
    ok(`bad address ${a}: the Overview, the toast, the address put right in place`, g.view === "overview" && t.length === before + 1 && t[t.length - 1] === "That address isn't used here. Showing the Overview."
       && loc.hash === "#/all/" + g.month + "/overview" && E.hist.e.length === n0 + 1, JSON.stringify(g) + " " + t.slice(-1));
  }
  await visit("#/AAA/2026-10/payments/budget");
  { clearToasts(); const before = 0; await visit("#/BBB/2026-10/accounting/sql"); const t = toasts();
    ok("a page the company doesn't use: the Overview and the existing toast", E.got().view === "overview" && t.length === before + 1 && /SQL import isn't used for BBB/.test(t[t.length - 1]) && loc.hash === "#/all/2026-10/overview", t.slice(-1)); }
  await visit("#/CCC/2026-10/accounting/sql");
  ok("a stopped company that does use the page opens it", E.got().view === "sql");
  await visit("#/");
  ok("an empty address (#/) is the Overview with no toast", E.got().view === "overview" && loc.hash === "#/all/2026-10/overview", loc.hash);
  await run(`go("entity", 1)`); await settle();
  await run(`go("sql", 2)`); await settle();
  ok("go() to a page the company doesn't use keeps the 0c rule: the company's own page, and the address says so", E.got().view === "entity" && E.got().entity === 2 && loc.hash === "#/BBB/2026-10/payments/register", JSON.stringify(E.got()));

  // ---- the buttons ----
  await run(`go("budget", 1)`); await settle();
  const btn = attrs => { const b = new E.Node("button"); for (const [k, v] of Object.entries(attrs)) { b.setAttribute(k, v); if (k.startsWith("data-")) b.dataset[k.slice(5).replace(/-(\w)/g, (m, c) => c.toUpperCase())] = v; } E.body.appendChild(b); return b; };
  const click = async b => { E.dispatch(b, { type: "click" }); await settle(); b.remove(); };
  let n0 = E.hist.e.length;
  await click(btn({ id: "prevMonth" }));
  ok("the previous month button writes the month and adds a history entry", loc.hash === "#/AAA/2026-09/payments/budget" && E.hist.e.length === n0 + 1 && E.got().month === "2026-09", loc.hash);
  await click(btn({ id: "nextMonth" })); await click(btn({ id: "nextMonth" }));
  ok("the next month button too", loc.hash === "#/AAA/2026-11/payments/budget", loc.hash);
  await click(btn({ id: "thisMonth" }));
  ok("this month writes the current cycle's month", loc.hash === `#/AAA/${run("currentCycle()")}/payments/budget`, loc.hash);
  E.back(); await settle();
  ok("Back after a month change returns to the month before", E.got().month === "2026-10" && loc.hash === "#/AAA/2026-10/payments/budget", loc.hash);
  await click(btn({ "data-pick-entity": "2" }));
  ok("picking a company writes its code", loc.hash.startsWith("#/BBB/") && E.got().entity === 2, loc.hash);
  await run(`go("setup")`); await click(btn({ "data-setup-kind": "guess_words" }));
  ok("a Setup section button writes the section", loc.hash === "#/admin/setup/guess_words", loc.hash);
  await run(`openSetup("guess_words", 4)`); await settle();
  ok("opening a Setup record puts its number in the address, in place", loc.hash === "#/admin/setup/guess_words/4", loc.hash);
  await run(`closeDrawer(true)`); await settle();
  ok("closing the drawer takes it out again", loc.hash === "#/admin/setup/guess_words" && run("state.setup.id") === null, loc.hash);
  await run(`go("books", 1)`); await run(`state.books.entity = 2; state.books.tab = "pl"; state.books.from = "2026-01-01"; syncAddr()`);
  ok("a Books tab change is written in place (dates belong to the company they were set for)", loc.hash === "#/AAA/accounting/books?tab=pl", loc.hash);
  await run(`state.books.entity = 1; state.books.from = "2026-01-01"; state.books.to = "2026-02-28"; state.books.tab = "parties"; state.books.side = "suppliers"; syncAddr()`);
  ok("Books dates and the suppliers side are written", loc.hash === "#/AAA/accounting/books?tab=suppliers&from=2026-01-01&to=2026-02-28", loc.hash);
  await run(`go("bank", 1)`); await run(`state.addr.params.account = "9"; syncAddr()`);
  ok("a bank account pick is written", loc.hash === "#/AAA/2026-10/accounting/bank?account=9", loc.hash);

  // ---- the Discard check ----
  const openDirty = () => { E.drawer.innerHTML = `<div class="row"><h2>Edit a thing</h2><button id="closeDrawer">Close</button></div><input id="f1">`; run("showDrawer()"); run("state.drawerDirty = () => true"); };
  const answer = async which => { await wait(30); const L = E.layers()[0]; if (!L) return false; L.querySelector(`[data-ask="${which}"]`).click(); await wait(30); return true; };
  await run(`go("budget", 1)`); await settle();
  const prev = loc.hash; openDirty();
  n0 = E.hist.e.length; d0 = E.drawn();
  const pr = run(`go("bank", 1)`); await wait(30);
  ok("go() on an unsaved drawer asks first, and writes nothing yet", E.layers().length === 1 && loc.hash === prev && E.hist.e.length === n0, E.layers().length);
  await answer("no");
  ok("Keep editing: go() resolves false, same address, no entry, no redraw, drawer still open", (await pr) === false && loc.hash === prev && E.hist.e.length === n0 && E.drawn() === d0 && !E.drawer.hidden && E.got().view === "budget");
  const nextHash = "#/AAA/2026-10/payments/register";
  loc.hash = nextHash; await wait(30);
  ok("a pasted address on an unsaved drawer asks too", E.layers().length === 1 && E.layers()[0].textContent.includes("Discard your changes?"));
  const len1 = E.hist.e.length;
  await answer("no"); await settle();
  ok("Keep editing: the previous address is put back in place of the new one, no new entry, no redraw", loc.hash === prev && E.hist.e.length === len1 && E.hist.e[E.hist.i] === prev && E.drawn() === d0 && E.got().view === "budget" && !E.drawer.hidden, loc.hash);
  E.back(); await wait(30); await answer("no"); await settle();
  ok("Back with an unsaved drawer: kept editing puts the address back and stays", E.got().view === "budget" && loc.hash === prev && E.drawn() === d0 && !E.drawer.hidden, loc.hash);
  loc.hash = nextHash; await wait(30); await answer("yes"); await settle();
  ok("Discard: the place is applied and the drawer closed", E.got().view === "entity" && loc.hash === nextHash && E.drawer.hidden && E.drawn() === d0 + 1, loc.hash);
  openDirty(); n0 = E.hist.e.length;
  const pr2 = run(`go("sql", 1)`); await answer("yes");
  ok("Discard on go(): applies and writes", (await pr2) === true && loc.hash === "#/AAA/2026-10/accounting/sql" && E.hist.e.length === n0 + 1, loc.hash);

  // ---- Next up's go shapes ----
  const GOS = [
    [{ view: "entity", task_id: 11 }, "#/AAA/2026-10/payments/register?task=11"],
    [{ view: "entity", task_id: 11, task_ids: [11, 12] }, "#/AAA/2026-10/payments/register?task=11,12"],
    [{ view: "entity", payment_id: 21 }, "#/AAA/2026-10/payments/register/21"],
    [{ view: "entity", payment_ids: [21, 22] }, "#/AAA/2026-10/payments/register?pay=21,22"],
    [{ view: "entity", filter: "past_legal" }, "#/AAA/2026-10/payments/register?mark=past_legal"],
    [{ view: "entity", filter: "in-part_paid" }, "#/AAA/2026-10/payments/register?mark=in-part_paid"],
    [{ view: "entity", filter: "overdue_tasks" }, "#/AAA/2026-10/payments/register?mark=overdue_tasks"],
    [{ view: "entity" }, "#/AAA/2026-10/payments/register"],
    [{ view: "bank" }, "#/AAA/2026-10/accounting/bank"],
    [{ view: "bank", account_id: 5 }, "#/AAA/2026-10/accounting/bank?account=5"],
    [{ view: "bank", account_id: 5, filter: "to_explain" }, "#/AAA/2026-10/accounting/bank?filter=to_explain&account=5"],
    [{ view: "budget", as_at: "2026-10-05" }, "#/AAA/2026-10/payments/budget?as_at=2026-10-05"],
    [{ view: "sql" }, "#/AAA/2026-10/accounting/sql"],
    [{ view: "audit" }, "#/AAA/2026-10/admin/audit-pack"],
    [{ view: "books", tab: "statutory", from: "2026-09-01", to: "2026-10-05" }, "#/AAA/accounting/books?tab=statutory&from=2026-09-01&to=2026-10-05"],
    [{ view: "payroll" }, "#/AAA/2026-10/hr/payroll/workbook"],
    [{ view: "settings", entity_id: null, month: null }, "#/admin/backup"],
  ];
  for (const [g0, want] of GOS) {
    const g = { entity_id: 1, month: "2026-10", ...g0 }, p = run(`linkPlace(${JSON.stringify(g)})`), a = run(`addrOf(linkPlace(${JSON.stringify(g)}))`), q = run(`parseAddr(${JSON.stringify(a)})`);
    ok(`Next up go ${JSON.stringify(g0)} is ${want}`, a === want, a);
    ok(`...and ${a} reads back to the same place`, q && q.view === g.view && same(q.params, run(`cleanParams(${JSON.stringify(g.view)}, ${JSON.stringify(p.params)})`)) && String(q.id ?? "") === String(p.id ?? "")
       && (["settings", "trail", "setup"].includes(g.view) ? q.entity === null : q.entity === 1) && (["settings", "books"].includes(g.view) ? q.month === null : q.month === "2026-10"), JSON.stringify(q));
    await visit("#/BBB/2026-03/overview");
    await run(`goTo(${JSON.stringify(g)})`); await settle();
    const s = snap();
    ok(`goTo(${JSON.stringify(g0)}) lands there and writes it`, loc.hash === want && s.view === g.view && (g.view === "settings" || s.entity === 1) && (["settings", "books"].includes(g.view) || s.month === "2026-10")
       && (g0.payment_id ? s.open === 21 : s.open == null) && (g0.payment_ids ? s.markIds === "21,22" : g0.filter === "overdue_tasks" ? s.markTask && !s.markPay : g0.filter && g.view === "entity" ? s.markPay : g0.task_id ? s.markTask : true)
       && (g.view === "bank" ? s.bankOnly === (g0.filter === "to_explain") && s.focus === (g0.account_id || null) : true)
       && (g.view === "budget" ? s.asAt === g0.as_at : true) && (g.view === "books" ? s.tab === "statutory" && s.from === g0.from && s.to === g0.to : true), JSON.stringify(s) + loc.hash);
  }
  for (const [kind, want] of [["paid_missing", "#/AAA/2026-10/admin/audit-pack"], ["unmatched_lines", "#/AAA/2026-10/accounting/bank?filter=to_explain"], ["not_in_sql", "#/AAA/2026-10/accounting/sql"],
    ["part_paid", "#/AAA/2026-10/payments/register?mark=part_paid"], ["overdue_tasks", "#/AAA/2026-10/payments/register?mark=overdue_tasks"], ["not_on_statement", "#/AAA/2026-10/payments/register?mark=not_on_statement"]]) {
    await run(`state.month = "2026-10"; pillGo(${JSON.stringify(kind)}, 1)`); await settle();
    ok(`the Overview count ${kind} goes to ${want}`, loc.hash === want, loc.hash);
  }

  // ---- refresh: booting with an address ----
  const BOOTS = [["#/AAA/2026-09/payments/register?mark=past_legal", s => s.view === "entity" && s.month === "2026-09" && s.entity === 1 && s.markPay],
    ["#/BBB/2026-07/accounting/bank?filter=to_explain&account=5", s => s.view === "bank" && s.entity === 2 && s.month === "2026-07" && s.bankOnly && s.focus === 5],
    ["#/AAA/accounting/books?tab=statutory&from=2026-01-01&to=2026-02-01", s => s.view === "books" && s.tab === "statutory" && s.from === "2026-01-01"],
    ["#/admin/setup/entities/2", s => s.view === "setup" && s.opened === "entities:2"], ["#/admin/audit-trail", s => s.view === "trail"],
    ["#/all/2026-06/overview", s => s.view === "overview" && s.month === "2026-06" && s.all]];
  for (const [a, test] of BOOTS) {
    const F = mkEnv(a), r = F.run;
    await r("routerBoot()"); await wait(25);
    const s = r(`({ view: state.view, entity: state.entity, month: state.month, markPay: !!state.mark?.pay, bankOnly: state.bankOnly, focus: state.focusBank?.account ?? null, tab: state.books.tab, from: state.books.from,
      opened: (__opened[__opened.length - 1] || []).join(":"), all: state.addr.all })`);
    ok(`refresh on ${a} lands on the page, month and filter`, test(s) && F.loc.hash === a && F.hist.e.length === 1 && F.drawn() === 1, JSON.stringify(s) + F.loc.hash);
    E.seen.push(...F.seen);
  }
  for (const a of ["#/ZZZ/2026-10/overview", "#/AAA/2026-10/payments/nope", "#/BBB/2026-10/accounting/sql", "#/all/2026-10/payments/budget"]) {
    const F = mkEnv(a); await F.run("routerBoot()"); await wait(25);
    const t = F.toasts();
    ok(`refresh on the bad address ${a}: the Overview, the toast, the address put right`, F.got().view === "overview" && t.length === 1 && /isn't used/.test(t[0]) && F.loc.hash === "#/all/2026-10/overview" && F.hist.e.length === 1, JSON.stringify(F.got()) + t);
  }

  // ---- no real location: the page still works (the test stand-ins) ----
  { const F = mkEnv(""); F.run("window.location = undefined; window.history = undefined"); await F.run("routerBoot()"); await wait(15);
    await F.run(`go("budget", 2)`); await wait(15);
    ok("without a location or history, go() applies the place and writes nothing", F.got().view === "budget" && F.got().entity === 2 && F.hist.e.length === 1 && F.hist.e[0] === "", JSON.stringify(F.got()));
    await F.run(`goTo({ view: "entity", entity_id: 1, month: "2026-08", payment_id: 5 })`);
    ok("and goTo() too", F.run("state.view") === "entity" && F.run("state.openPayment") === 5 && F.run("state.month") === "2026-08"); }

  // ---- what an address may hold ----
  const all = [...new Set([...E.seen])].filter(a => a !== "" && a !== "#/" && !BAD.includes(a));
  const key = "(mark|pay|task|as_at|filter|account|tab|from|to)", val = "[a-z0-9_,-]+";
  const okAddr = a => new RegExp(`^#/[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*(\\?${key}=${val}(&${key}=${val})*)?$`).test(a);
  const badOnes = all.filter(a => !okAddr(a));
  ok(`every address written (${all.length} different) holds only a company code, a month, route words, numbers and the known filter keys`, all.length > 40 && !badOnes.length, badOnes.slice(0, 5));
  ok("none carries a name, an amount or a person", !all.some(a => /alpha|beta|gamma|sdn|ltd/i.test(a)));
  ok("addrOf drops a filter key it doesn't know and a value that isn't well formed", run(`addrOf({ view: "bank", entity: 1, month: "2026-10", params: { account: "5", name: "x", filter: "Bob Tan", tab: "tb" } })`) === "#/AAA/2026-10/accounting/bank?account=5");

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

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "addresses_test" in readme)

print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
