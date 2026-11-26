"""The page loader (slice 0g: static/js/core/page.js, shell.js render, core/saved.js and every page that uses them), on made-up records
only. The page script is run in Node on a stand-in page; every read goes to the real server (Flask's test client) through a pipe, with the
delay or the failure a case asks for, on a clock of the stand-in's own (so a 1.5 s read costs no time). Changes are never sent to the
server: the stand-in answers them as kept (or as the case says) and counts them.

The stand-in page keeps what a real page keeps for these checks: an element with an id is there only while the markup that holds it is on the
page, and every write replaces the nodes it wrote (so a page that was replaced can no longer be written into, and a write of the same words
is still a new node).

Checks:
 A. No page is left on "Loading": with every read delayed 300 ms, 900 ms and 1.5 s, on arrival from another page, on a company switch and on a
    month change, each page ends as it does with no delay (its own frame filled, no skeleton, no dim), and a page that wrote its own frame
    (Bank, Books, Customers and suppliers, Statutory payables, Setup) is never covered by the skeleton, while one that hasn't still is.
 B. No page paints over a newer page: for every page, and each read it makes, that read is made slow and another page (and, apart, the same
    page of another company) is opened meanwhile; when the slow read comes back, answered or failed, nothing changes: no markup, no state,
    no message, no dialog. The same for the parts of a page asked for twice (Books' tabs, the bank's year and review, the budget, the audit
    trail's filters), for dialogs read before they open, for the SQL page's Fetch, and for a render held up by the day's first month set-up.
 C. A change that was kept, then a page that can't be read back: for every such action, the change is sent once, the page says it was saved
    (never that nothing was changed, nor that the app being stopped means nothing was saved), and Try again only reads, whether it fails
    again or works. What a stale page or dialog still holds can't send it again. With the app stopped (or failing) a change that got no answer
    leaves the page saying so, with the steps to start it, never that nothing was sent; a read-back never takes the place of the same page
    asked for again; a result is never written into a page about to be replaced; and only the change's own dialog is ever closed.
 D. "Nothing was changed" is said only when the server refused the change: a server failure or an answer that can't be read says it isn't
    known; a 200 that isn't JSON is an error (never an empty answer).

HRP_KEEP_GOING=1 lists every check that fails. HRP_TEST_STATIC=<a static folder> runs the checks against that copy of the page script (used
to show that they fail without the fix).

Run: .venv\\Scripts\\python -m synthetic_tests.page_load_test
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-page-load-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests import appsource  # noqa: E402
from synthetic_tests.flags import KEEP_GOING  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

STATIC = Path(os.environ.get("HRP_TEST_STATIC") or appsource.STATIC)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "QFB", "name": "Quillon Fabrication Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-410-2291"}]},
    {"code": "MBS", "name": "Marrowby Studio Sdn Bhd", "accounts": [{"label": "Operating", "bank": "Example Bank", "number": "000-410-7765"}]},
    {"code": "TYD", "name": "Tessellate Yard Sdn Bhd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-410-3348"}]},
]}), encoding="utf-8")

passed, failed = [], []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:1400]}" if detail else ""))
        if not KEEP_GOING:
            sys.exit(1)
        failed.append(name)
        return
    passed.append(name)
    print(f"PASS {name}")


db.init()
client = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


meta = j("get", "/api/meta")
IDS = {e["code"]: e["id"] for e in meta["entities"]}
ACCT = {e["code"]: e["accounts"][0]["id"] for e in meta["entities"]}
QFB, MBS = IDS["QFB"], IDS["MBS"]

# the month the page opens on, and the one before it (the page's own current cycle, worked out the same way: the 10th is the rollover day)
from datetime import date, timedelta  # noqa: E402

today = date.today()
first = today.replace(day=1)
if today.day <= 10:
    first = (first - timedelta(days=1)).replace(day=1)
MONTH = first.strftime("%Y-%m")
BEFORE = (first - timedelta(days=1)).strftime("%Y-%m")
payees = {}
for eid, name, amount in ((QFB, "Nerida Quillam", 3200), (QFB, "Tavish Orrell Rental", 1850), (MBS, "Ottoline Fennick", 2750)):
    payees[name] = j("post", "/api/payees", json={"entity_id": eid, "name": name, "desc_template": name + " - {M}", "category": "other", "direction": "out",
                                                  "amount": amount, "amount_varies": 0, "month_offset": 0, "due_day": 12, "account_id": None})
for eid in (QFB, MBS):
    j("post", "/api/setup/checklist", json={"action": "add", "entity_id": eid, "from_month": BEFORE,
                                            "fields": {"completion": "hand", "title": "File the made-up receipt", "detail": "", "due_offset": 0, "due_day": 20, "docs": []}})
for eid in (QFB, MBS, IDS["TYD"]):
    for m in (BEFORE, MONTH):
        j("post", "/api/months/open", json={"entity_id": eid, "month": m})
    j("post", "/api/budget/setup", json={"entity_id": eid, "month": MONTH})
pays = j("get", f"/api/month?entity={QFB}&month={MONTH}")["payments"]
PAY = pays[0]["id"]
j("post", "/api/upload", data={"file": (io.BytesIO(b"made-up receipt"), "receipt.txt"), "payment_id": str(PAY), "doc_type": "other"}, content_type="multipart/form-data")
DOC = j("get", f"/api/month?entity={QFB}&month={MONTH}")["payments"][0]["documents"][0]["id"]
LINE = j("get", f"/api/budget?entity={QFB}&month={MONTH}")["lines"][0]["id"]
TASK = j("get", f"/api/month?entity={QFB}&month={MONTH}")["tasks"][0]["id"]
PAYEE, PAYEE2 = [p["id"] for p in j("get", f"/api/payees?entity={QFB}&month={MONTH}")][:2]
PAY2 = pays[1]["id"]
TYPES = [r["id"] for r in j("get", "/api/setup/payment_types")["rows"]][:2]
FX = {"QFB": QFB, "MBS": MBS, "TYD": IDS["TYD"], "ACCT": ACCT["QFB"], "MONTH": MONTH, "BEFORE": BEFORE, "PAY": PAY, "DOC": DOC, "LINE": LINE, "TASK": TASK, "PAYEE": PAYEE, "PAYEE2": PAYEE2, "PAY2": PAY2, "TYPES": TYPES,
      "STATIC_IDS": re.findall(r'\bid="([\w-]+)"', (STATIC / "index.html").read_text(encoding="utf-8"))}

# ---------------------------------------------------------------------------------------------------------------------------------------------
PROBE = r"""
const fs = require("fs"), vm = require("vm"), readline = require("readline");
const [fxPath, ...files] = process.argv.slice(2);
const unheard = [];   // a failure nobody heard: a draw or an action whose promise nobody waits for
process.on("unhandledRejection", e => unheard.push(String(e && e.message || e)));
const FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));

/* ---- the pipe to the real server ---- */
const waiting = new Map(); let askN = 0, asking = 0;
readline.createInterface({ input: process.stdin }).on("line", l => { const m = JSON.parse(l); const f = waiting.get(m.id); waiting.delete(m.id); asking--; f(m); });
const server = path => new Promise(res => { const id = ++askN; asking++; waiting.set(id, res); process.stdout.write("@@REQ " + JSON.stringify({ id, path }) + "\n"); });
const answers = new Map();   // the server's answers to reads, kept: nothing here changes the records

/* ---- the clock ---- */
let now = 0, timers = [], timerN = 0;
const vSetTimeout = (fn, ms = 0) => { const id = ++timerN; timers.push({ id, at: now + (+ms || 0), fn }); return id; };
const vClearTimeout = id => { timers = timers.filter(t => t.id !== id); };
const turn = () => new Promise(r => setImmediate(r));
// runs everything due up to `until` (or everything there is)
async function settle(until = Infinity) {
  for (let guard = 0; guard < 100000; guard++) {
    for (let i = 0; i < 4; i++) await turn();
    if (asking) { await new Promise(r => setTimeout(r, 1)); continue; }
    const due = timers.filter(t => t.at <= until && t.at < now + 60000).sort((a, b) => a.at - b.at || a.id - b.id)[0];
    if (!due) { if (until !== Infinity) now = Math.max(now, until); return; }
    timers = timers.filter(t => t !== due); now = Math.max(now, due.at); due.fn();
  }
  throw new Error("the page never settled");
}

/* ---- the stand-in page ---- */
let written = 0;   // every write into the page's content (the menu and the top bar, the shell's own, aside), also into a node no longer on show
const SHELL = new Set(["nav", "orgName", "pageTitle", "tbCompany", "tbUser", "monthLabel", "thisMonth", "prevMonth", "nextMonth"]);
const unesc = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const listeners = {};
class El {
  constructor(id, tag = "div", attrs = {}) {
    this.id = id; this.tagName = tag.toUpperCase(); this.attrs = attrs; this._html = ""; this.kids = []; this.node = null; this.isConnected = true; this.written = 0;
    this.value = attrs.value ?? ""; this.checked = "checked" in attrs; this.hidden = "hidden" in attrs; this.disabled = "disabled" in attrs; this.text = ""; this.className = attrs.class || "";
    this.type = attrs.type || ""; this.style = {}; this.on = {}; this.scrollTop = 0; this.offsetParent = null;
    this.dataset = {}; for (const [k, v] of Object.entries(attrs)) if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = v;
    const set = new Set(); this.classList = { add: (...c) => c.forEach(x => set.add(x)), remove: (...c) => c.forEach(x => set.delete(x)), toggle: (c, on) => { (on ?? !set.has(c)) ? set.add(c) : set.delete(c); }, contains: c => set.has(c) };
  }
  gone() { this.isConnected = false; this.kids.forEach(k => k.gone()); }
  parse(h) {
    const out = [];
    for (const m of h.matchAll(/<([a-zA-Z][\w-]*)((?:\s+[^\s=<>"\/]+(?:="[^"]*")?)*)\s*\/?>/g)) {
      const attrs = {}; for (const a of m[2].matchAll(/([^\s=<>"\/]+)(?:="([^"]*)")?/g)) attrs[a[1]] = unesc(a[2] ?? "");
      if (!attrs.id) continue;
      const el = new El(attrs.id, m[1], attrs), rest = h.slice(m.index + m[0].length);
      if (el.tagName === "SELECT") { const body = rest.slice(0, rest.indexOf("</select>")), opts = [...body.matchAll(/<option value="([^"]*)"([^>]*)>/g)];
        el.value = unesc((opts.find(o => /\bselected\b/.test(o[2])) || opts[0] || [0, ""])[1]); }
      if (el.tagName === "TEXTAREA") el.value = unesc(rest.slice(0, rest.indexOf("</textarea>")));
      out.push(el);
    }
    return out;
  }
  set innerHTML(h) { this.kids.forEach(k => k.gone()); this._html = String(h); this.kids = this.parse(this._html); this.node = this._html ? {} : null; this.written++; this.text = ""; if (!SHELL.has(this.id)) written++; }
  get textContent() { return this.text; }
  set textContent(v) { this.text = String(v); if (this.text && !SHELL.has(this.id)) written++; }
  get innerHTML() { return this._html; }
  get firstChild() { return this.node; }
  set outerHTML(h) { this.innerHTML = h; }
  get outerHTML() { return this._html; }
  insertAdjacentHTML(where, h) { this._html = where === "afterbegin" ? h + this._html : this._html + h; this.kids.push(...this.parse(h)); this.node = {}; this.written++; written++; }
  find(id) { for (const k of this.kids) { if (k.id === id) return k; } for (const k of this.kids) { const f = k.find(id); if (f) return f; } return null; }
  // all that is on the page under here: this markup, then what was written into the elements in it since
  full() { return this._html + this.kids.map(k => k.written || k.text ? `\n[#${k.id}] ${k.text || k.full()}` : k.full()).join(""); }
  setAttribute(k, v) { this.attrs[k] = String(v); } getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; } removeAttribute(k) { delete this.attrs[k]; } hasAttribute(k) { return k in this.attrs; }
  addEventListener(t, f) { (this.on[t] ||= []).push(f); } removeEventListener() {}
  querySelector(s) { const m = /^#([\w-]+)$/.exec(s); return m ? this.find(m[1]) : null; }
  querySelectorAll(s) { return /input\[id\]/.test(s) ? this.kids.flatMap(k => [...(["INPUT", "SELECT", "TEXTAREA"].includes(k.tagName) ? [k] : []), ...k.querySelectorAll(s)]) : []; }
  closest() { return null; } contains() { return false; } focus() {} blur() {} click() {} scrollIntoView() {} after() {} remove() {} appendChild() {} setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, height: 100 }; }
}
const roots = {}; for (const id of FX.STATIC_IDS) roots[id] = new El(id);
roots.drawer.hidden = true;
const byId = id => roots[id] || Object.values(roots).reduce((f, r) => f || r.find(id), null);
const document = { activeElement: null, hidden: false, body: { classList: { add() {}, remove() {}, contains: () => false } },
  querySelector: s => { const m = /^#([\w-]+)$/.exec(s); return m ? byId(m[1]) : null; }, querySelectorAll: () => [], getElementById: byId,
  addEventListener(t, f) { (listeners[t] ||= []).push(f); }, removeEventListener() {} };

/* ---- the network: reads from the server, changes answered here ---- */
const NET = {};
const resetNet = () => Object.assign(NET, { delay: () => 0, fail: () => null, reply: () => undefined, down: false, afterWrite: null, reads: [], writes: [], mark: null });
// the answer an overtaken draw is given carries dates of its own, so what it writes shows even where two pages' records read alike
const marked = body => body && typeof body === "object" && !Array.isArray(body) ? { ...body, ...("from" in body ? { from: "1999-01-01" } : {}), ...("to" in body ? { to: "1999-12-31" } : {}), ...("as_at" in body ? { as_at: "1999-12-31" } : {}) } : body;
resetNet();
const response = (status, body, bad) => ({ ok: status < 400, status, json: async () => { if (bad) throw new SyntaxError("Unexpected token <"); return JSON.parse(JSON.stringify(body)); } });
async function fetch(path, init = {}) {
  const method = init.method || "GET";
  const asked = now;
  const wait = ms => ms ? new Promise(r => vSetTimeout(r, Math.max(0, asked + ms - now))) : null;
  if (method !== "GET" && path !== "/api/sql/preview") {
    NET.writes.push([method, path]);
    const w = NET.reply(path, method) || [200, {}];
    if (NET.afterWrite) NET.down = NET.afterWrite;   // what is read from here on fails
    await wait(NET.delay(path, method));
    if (w === "net") throw new TypeError("Failed to fetch");
    return response(w[0], w[1], w[2] === "bad");
  }
  NET.reads.push(path);   // (/api/sql/preview is a POST that only reads)
  const ms = NET.delay(path, method), stale = NET.mark === path && ms > 0, how = NET.fail(path, method) || NET.down || null, own = NET.reply(path, method);
  if (own === "net") { await wait(ms); throw new TypeError("Failed to fetch"); }
  let hit = own ? { status: own[0], body: own[1], bad: own[2] === "bad" } : method !== "GET" ? { status: 200, body: {} } : answers.get(path);
  if (!hit && !how) { const r = await server(path); hit = { status: r.status, body: r.body }; answers.set(path, hit); }
  await wait(ms);
  if (how === "net") throw new TypeError("Failed to fetch");
  if (how === "500") return response(500, { error: "The server could not read the records." });
  if (how === "bad") return response(200, null, true);
  return response(hit.status, stale ? marked(hit.body) : hit.body, hit.bad);
}

const win = { matchMedia: () => ({ matches: true }), scrollX: 0, scrollY: 0, scrollTo() {}, addEventListener() {}, print() {}, open() {} };
const sandbox = { document, fetch, FormData: class { constructor() { this.a = []; } append(k, v) { this.a.push([k, v]); } }, console: { ...console, error() {} }, setTimeout: vSetTimeout, clearTimeout: vClearTimeout,
  URLSearchParams, CSS: { escape: s => s }, localStorage: { store: {}, getItem(k) { return this.store[k] ?? null; }, setItem(k, v) { this.store[k] = String(v); }, removeItem(k) { delete this.store[k]; } },
  window: win, navigator: {}, __el: byId };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);

/* ---- helpers on the page ---- */
const main = () => roots.main;
const PAGES = ["overview", "entity", "checklist", "budget", "payees", "bank", "sql", "books", "parties", "statutory", "einvoices", "payroll", "audit", "trail", "settings", "staff",
  "setup:entities", "setup:accounts", "setup:parties", "setup:checklist", "setup:reminders", "setup:settings", "setup:move", "setup:required"];
const SHELLS = ["bank", "books", "parties", "statutory"];   // they write their own frame before they read
const view = p => p.split(":")[0];
// goes to a page as the menu does (the setup:<section> pages by their address)
function go(p, company = FX.QFB, month = FX.MONTH) {
  const [v, kind] = p.split(":");
  return run(`navigate({ view: ${JSON.stringify(v)}, entity: ${v === "overview" ? `"all"` : company}, month: ${JSON.stringify(month)}, sub: ${JSON.stringify(kind || null)}, id: null, params: {} }, { fresh: true })`);
}
const toasts = () => run(`__toasts`);
function fresh() {
  resetNet(); timers = [];
  run(`ask = async () => true; __toasts.length = 0; state.sqlPreview = null; state.sq = null; state.pay = null; state.openPayment = null; state.recon = { entity: null, account: null, year: null, open: null, panel: null, rv: null };
    state.books = { entity: null, tab: "tb", from: null, to: null, rollup: true, account: null, q: "", months: false, side: "customers", party: null }; state.mark = null; state.asAt = null; state.focusBank = null;
    state.setup.reqScope = null; state.setup.deleted = false; state.setup.stopped = false; state.trail.f = {}; state.trail.show = false; render.last = undefined; render.asked = undefined; render.company = undefined;
    DLG.asking = 0; closeDrawer(true); state.startFailed = false; localStorage.store = {}`);
  for (const id of ["main", "toast"]) { roots[id].innerHTML = ""; roots[id].classList.remove("loading"); }
}
async function open(p, company, month) { go(p, company, month); await settle(); }
// What the page shows (the menu and the top bar are the shell's own, and carry the to-do numbers)
const shown = () => main().full();
const skeleton = () => /class="skel/.test(main().innerHTML);
const boxOf = p => view(p) === "bank" ? "stmtList" : ["books", "parties", "statutory"].includes(view(p)) ? "booksBody" : view(p) === "setup" ? "setupMain" : null;
const filled = p => { const id = boxOf(p); if (!id) return !skeleton() && !!main().innerHTML; const b = main().find(id); return !!b && !!b.innerHTML && !/^<div class="note">Loading…<\/div>$/.test(b.innerHTML) && !skeleton(); };
// the state the pages keep (what an overtaken draw must not write)
const STATE = `JSON.stringify([state.view, state.entity, state.month, state.data && [state.data.entity?.id, state.data.month, state.data.payments?.length], state.sqData && [state.sqData.unlinked?.length, state.sqData.imports?.length],
  state.payees && state.payees.map(p => p.id), state.eiData && [state.eiData.issued?.length, state.eiData.copy], [state.books.entity, state.books.tab, state.books.from, state.books.to, state.books.tb?.accounts?.length ?? null, (state.books.choices || []).length],
  [state.recon.entity, state.recon.account, state.recon.year, state.recon.data?.account?.id ?? null, state.recon.panel?.account?.id ?? null, state.recon.rv?.sid ?? null, state.recon.print?.month ?? null],
  state.setup.chk && state.setup.chk.code, state.setup.rem && state.setup.rem.rules?.length, state.setup.req && state.setup.req.scope, state.setup.settings && state.setup.settings.fields?.length, state.setup.move && state.setup.move.empty,
  state.setup.types && Object.keys(state.setup.types.kinds).length, Object.keys(state.counts).sort().map(k => [k, state.counts[k]]), state.trail.entries.length, state.trail.upto ?? null, OV.act && OV.act.items?.length,
  Object.entries(OV.data).map(([k, v]) => [k, v.busy ? "busy" : v.err ? "err" : "ok"]).sort(), state.next && [...state.next.keys()].sort(), BUD.key, [...(BUD.visible || [])], state.mark ? "mark" : null, state.payeeSaved, state.openPayment, state.setup.id])`;
const snapshot = () => ({ main: shown(), drawer: roots.drawer.full(), closed: roots.drawer.hidden, toasts: toasts().length, writes: written, state: run(STATE), loading: main().classList.contains("loading") });
// what is run as a click is: its failure becomes a message, as the page's click handler makes it
const clicked = code => run(`__started = eval(${JSON.stringify(code)}); Promise.resolve(__started).catch(e => toast(e.message, true)); void 0`);
const differs = (a, b) => Object.keys(a).filter(k => a[k] !== b[k]).map(k => { let i = 0; const x = String(a[k]), y = String(b[k]); while (i < x.length && x[i] === y[i]) i++; return `${k}: ${JSON.stringify(x.slice(Math.max(0, i - 80), i + 120))} -> ${JSON.stringify(y.slice(Math.max(0, i - 80), i + 120))}`; });

const out = {};
const tryit = async (name, fn) => { try { out[name] = await fn(); } catch (e) { out[name] = { crashed: String(e && e.stack || e).slice(0, 900) }; } };

(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));
  run(`globalThis.__toasts = []; toast = (msg, bad, opts) => { __toasts.push({ msg: String(msg), bad: !!bad, action: opts && opts.action || null, undo: opts && opts.undo || null }); return null; };
    ask = async () => true; pickFile = async () => [{ name: "slip.pdf", size: 10 }];`);
  const meta = (await server("/api/meta")).body;
  run(`state.meta = ${JSON.stringify(meta)}; state.month = ${JSON.stringify(FX.MONTH)}; state.day = dayKey(); state.entity = ${FX.QFB};`);

  /* ======== A. no page is left on Loading ======== */
  await tryit("A", async () => {
    const res = {};
    for (const p of PAGES) {
      const other = FX.MBS;
      // how each is done: on arrival from another page, by a company switch, by a month change
      const act = how => how === "arrival" ? go(p) : how === "switch" ? (view(p) === "overview" ? go("overview") : run(`tbPick(${other})`))
        : run(`state.month = ${JSON.stringify(FX.BEFORE)}; state.addr.params = {}; redraw()`);   // as the month's arrows do
      const ready = async how => { fresh(); if (how === "arrival") await open(p === "settings" ? "audit" : "settings"); else await open(p); };
      const base = {};
      const r = res[p] = { filledAtOnce: null, cases: [] };
      for (const how of ["arrival", "switch", "month"]) { await ready(how); act(how); await settle(); base[how] = shown(); if (how === "arrival") r.filledAtOnce = filled(p); }
      for (const ms of [300, 900, 1500]) for (const how of ["arrival", "switch", "month"]) {
        if (how === "switch" && ["trail", "settings"].includes(p)) continue;   // a page of no company
        await ready(how);
        const slow = () => ms + 5;   // "300 ms" is just over the skeleton's 0.3 s, as a read of that length is
        NET.delay = slow;
        act(how);
        await settle(now + 302);
        const mid = { skeleton: skeleton(), frame: boxOf(p) ? !!main().find(boxOf(p)) : null };
        await settle();
        const same = shown() === base[how];
        r.cases.push({ ms, how, same, filled: filled(p), skeleton: skeleton(), loading: main().classList.contains("loading"), mid });
      }
    }
    return res;
  });
  // the skeleton is still shown over the old page while a page that has written nothing is read
  await tryit("Askeleton", async () => {
    const res = {};
    for (const p of ["entity", "audit", "payees"]) { fresh(); await open("settings"); NET.delay = () => 900; go(p); await settle(now + 200); const early = skeleton(); await settle(now + 150); res[p] = { early, late: skeleton() }; await settle(); }
    return res;
  });
  // a page left for another and come back to while the other is still read: no stale frame is left undimmed under it, and it ends whole
  await tryit("Aback", async () => {
    fresh(); await open("entity"); const want = shown();
    NET.delay = () => 900; go("books"); await settle(now + 100);
    const frame = !!main().find("booksView");
    go("entity"); await settle(now + 10);
    const dim = main().classList.contains("loading"); await settle(now + 400);
    const left = !!main().find("booksView"), covered = skeleton();   // 0.4 s on: the page left for isn't left on show under this one's address
    await settle();
    return { frame, dim, left, covered, same: shown() === want, loading: main().classList.contains("loading") };
  });

  /* ======== B. no page paints over a newer page ======== */
  const clickedGo = p => { const done = go(p); Promise.resolve(done).catch(e => run(`toast`)(e.message, true)); };
  // a: the page whose read is slow; then: what is opened meanwhile. Returns, for each read of a, what changed once it came back.
  async function overtake(a, then, how) {
    fresh(); await open("settings"); NET.reads.length = 0; await open(a); const paths = [...new Set(NET.reads)];
    const res = [];
    for (const path of paths) {
      fresh(); await open("settings");
      let used = false;
      const mine = p => !used && p === path && (used = true);
      NET.mark = path;
      NET.delay = p => (mine(p) ? (NET.slowOne = true, 1000) : 0);
      if (how === "fail") { let failed = false; NET.fail = p => !failed && p === path && NET.slowOne ? (failed = true, "500") : null; }
      NET.slowOne = false;
      clickedGo(a); await settle(now + 100);
      if (!used) { res.push({ path, skipped: true }); await settle(); continue; }
      then(); await settle(now + 200);
      const before = snapshot();
      await settle();
      res.push({ path, changed: differs(before, snapshot()) });
    }
    return res;
  }

  for (const p of PAGES.filter(p => p !== "staff")) for (const how of ["answer", "fail"]) {
    await tryit(`B:${p}:other:${how}`, () => overtake(p, () => go(view(p) === "payroll" ? "audit" : "payroll"), how));
  }
  for (const p of ["overview", "entity", "checklist", "budget", "payees", "bank", "sql", "books", "parties", "statutory", "einvoices", "payroll", "audit", "setup:accounts", "setup:checklist"]) {
    await tryit(`B:${p}:company:answer`, () => overtake(p, () => view(p) === "overview" ? run(`navigate({ view: "overview", entity: ${FX.MBS}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`) : go(p, FX.MBS), "answer"));
    await tryit(`B:${p}:company:fail`, () => overtake(p, () => view(p) === "overview" ? run(`navigate({ view: "overview", entity: ${FX.MBS}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`) : go(p, FX.MBS), "fail"));
  }

  // B2. the parts of one page asked for twice, and dialogs: slow first, quick second; the slow one changes nothing when it comes
  async function race(prepare, first, slowPath, second, how) {
    fresh(); await prepare(); await settle();
    let used = false;
    NET.delay = p => !used && p.startsWith(slowPath) ? (used = true, NET.mark = p, 1000) : 0;
    if (how === "fail") { let f = false; NET.fail = p => !f && used && p.startsWith(slowPath) ? (f = true, "500") : null; }
    clicked(first); await settle(now + 100);
    const asked = used;
    clicked(second); await settle(now + 200);
    const before = snapshot();
    await settle();
    const after = snapshot();
    delete before.loading;   // the dim ends when the page's own draw does, overtaken in its part or not
    return { asked, changed: differs(before, after), loading: after.loading };
  }
  const RV = { summary: { statement: { id: 7, closing: 10, document_id: null }, account: { id: 1, label: "Main", currency: "MYR" }, label: "Sample month", month: FX.MONTH, status: "to_review", status_text: "To review", locked: false, why_not: [], book: { state: "ok", closing: 0 }, difference: 0, pairs: [], uses_sql: true, source: "sql", reopens: [] }, lines: [], payments: [] };
  const rvReply = p => p.startsWith("/api/recon/review") ? [200, RV] : undefined;
  const PARTS = {
    "books: a tab clicked while another's report is read": [() => open("books"), `state.books.tab = "pl"; drawBooks()`, "/api/books/profit-and-loss", `state.books.tab = "bs"; drawBooks()`],
    "books: a tab clicked while the page's first report is read": [() => open("settings"), `navigate({ view: "books", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`, "/api/books/trial-balance", `state.books.tab = "bs"; drawBooks()`],
    "bank: a review opened while the year is read": [() => open("bank"), `drawRecon()`, "/api/recon/year", `NET_RV(); openReview(7, false)`],
    "bank: the year asked for while a review is read": [() => open("bank"), `NET_RV(); openReview(7, false)`, "/api/recon/review", `drawRecon()`],
    "budget: another page while the budget is read again": [() => open("budget"), `__el("bud-date").value = "${FX.MONTH}-02"; __el("bud").on.change[0]({ target: { id: "bud-date", closest: () => null, dataset: {} } })`, "/api/budget?", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "Overview: a card tried again, then another page": [() => open("overview"), `ovRetry("due")`, "/api/overview/due", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "Overview: Next up read again, then another page": [() => open("overview"), `refreshNext()`, "/api/next", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "register: Next up's link read again, then the checklist of another company": [() => open("entity"), `refreshNext()`, "/api/next", `navigate({ view: "checklist", entity: ${FX.MBS}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "Overview: the audit trail's notice read, then another page": [() => open("settings"), `NET_NOTICE(); navigate({ view: "overview", entity: "all", month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`, "/api/audit/status?quick=1", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "audit trail: older entries asked for, then another page": [() => open("trail"), `state.trail.entries.length || (state.trail.entries = [{ id: 99 }]); trailMore({ disabled: false })`, "/api/audit?", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "audit trail: a filter's list read, then another page": [() => open("trail"), `refreshTrailList()`, "/api/audit?", `navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "Show deleted read, then another page": [() => open("payees"), `state.setup.deleted = true; drawDeleted("payees")`, "/api/setup/restore", `state.setup.deleted = false; navigate({ view: "audit", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`],
    "a record's History opened, then another record's": [() => open("budget"), `openHistory("budget_lines", ${FX.LINE}, "First")`, `/api/audit/record/budget_lines/${FX.LINE}`, `openHistory("payments", ${FX.PAY}, "Second")`],
    "a record's History closed while it is read": [() => open("budget"), `openHistory("budget_lines", ${FX.LINE}, "First")`, "/api/audit/record", `closeDrawer(true)`],
    "a Setup record asked for, then another record": [() => open("setup:accounts"), `openSetup("accounts", ${FX.ACCT})`, `/api/setup/accounts/${FX.ACCT}`, `openSetup("accounts", "new")`],
    "a Setup record asked for, then another page": [() => open("setup:accounts"), `openSetup("accounts", ${FX.ACCT})`, `/api/setup/accounts/${FX.ACCT}`, `go("audit")`],
    "a recurring payment asked for, then another page": [() => open("payees"), `editPayee(${FX.PAYEE})`, "/api/payees/", `go("audit")`],
    "a recurring payment asked for, then the Add one": [() => open("payees"), `editPayee(${FX.PAYEE})`, "/api/payees/", `editPayee("new")`],
    "Check this pack opened, then closed": [() => open("audit"), `openPackCheck("", "pack.pdf")`, "/api/audit-pack/check", `closeDrawer(true)`],
    "Put it back asked for, then another record's History": [() => open("trail"), `NET_RESTORE(); openRestore(5, "A record")`, "/api/setup/restore/5", `openHistory("budget_lines", ${FX.LINE}, "Other")`],
    "a Setup address with a record, then another page while the section is read": [() => open("settings"), `navigate({ view: "setup", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: "accounts", id: ${FX.ACCT}, params: {} }, { fresh: true })`, "/api/setup/accounts?", `go("audit")`],
    "a Setup address with a record, then the same section without one while it is read": [() => open("settings"), `navigate({ view: "setup", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: "accounts", id: ${FX.ACCT}, params: {} }, { fresh: true })`, "/api/setup/accounts?", `navigate({ view: "setup", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: "accounts", id: null, params: {} }, { fresh: true })`],
    "e-Invoices' print checks read, then another page": [() => open("settings"), `NET_EI(); navigate({ view: "einvoices", entity: ${FX.QFB}, month: ${JSON.stringify(FX.MONTH)}, sub: null, id: null, params: {} }, { fresh: true })`, "/api/invoices/", `go("audit")`],
  };
  run(`globalThis.NET_RV = () => {}; globalThis.NET_NOTICE = () => {}; globalThis.NET_EI = () => {}; globalThis.NET_RESTORE = () => {}`);
  for (const [name, [prepare, first, slowPath, second]] of Object.entries(PARTS)) for (const how of ["answer", "fail"]) {
    await tryit(`P:${name}:${how}`, async () => {
      sandbox.__rv = () => { NET.reply = rvReply; };
      run(`globalThis.NET_RV = () => __rv(); globalThis.NET_NOTICE = () => __notice(); globalThis.NET_EI = () => __ei(); globalThis.NET_RESTORE = () => __restore()`);
      sandbox.__restore = () => { NET.reply = p => p === "/api/setup/restore/5" ? [200, { label: "Bank account", name: "Spare", table: "accounts", kind: "accounts", id: 2, same_id: true, notes: [], lines: [], affected: {},
        deleted: { at: "2026-11-02T10:00:00", actor: "Made-up user", entry: 4, key: 2, reason: "Made up" } }] : undefined; };
      sandbox.__notice = () => { NET.reply = p => p.startsWith("/api/audit/status") ? [200, { outside: 2 }] : undefined; };
      sandbox.__ei = () => { NET.reply = p => p.startsWith("/api/einvoices") ? [200, { copy: false, sources: [], counts: {}, other: [], unmatched: [], print: { missing: [], fonts: [], too_long: [], counts: {} }, received: [], self_billed: [],
        issued: [{ id: 5, doc_no: "IV-1", date: FX.MONTH + "-02", description: "Sample", amount: 1, party: {}, print_kind: "invoice", what: "invoice" }] }]
        : p.startsWith("/api/invoices/") ? [200, { notes: ["No logo"] }] : undefined; };
      return race(prepare, first, slowPath, second, how);
    });
  }

  // a payroll check chip left on the old page, clicked while the next page is read
  await tryit("chip", async () => {
    fresh(); await open("payroll"); const m = main(); NET.delay = p => p.startsWith("/api/audit-readiness") ? 600 : p.startsWith("/api/payroll-check") ? 1000 : 0;
    const chips = [{ dataset: { pcShow: "1" } }]; m.querySelectorAll = s => s === "[data-pc-show]" ? chips : [];
    go("settings"); await settle(); fresh();
    m.querySelectorAll = s => s === "[data-pc-show]" ? chips : [];
    await open("payroll"); NET.delay = p => p.startsWith("/api/audit-readiness") ? 600 : p.startsWith("/api/payroll-check") ? 1000 : 0;
    go("audit"); await settle(now + 100);
    if (chips[0].onclick) chips[0].onclick();
    await settle(now + 700); const before = snapshot(); await settle(); m.querySelectorAll = () => [];
    return { bound: !!chips[0].onclick, changed: differs(before, snapshot()), audit: /Audit pack/.test(shown()) };
  });

  // ... also while the same page of another company is read
  await tryit("chipCompany", async () => {
    fresh(); const m = main(), chips = [{ dataset: { pcShow: "1" } }]; m.querySelectorAll = s => s === "[data-pc-show]" ? chips : [];
    await open("payroll"); const first = chips[0].onclick;
    NET.delay = p => p.startsWith("/api/payroll-check") && !p.includes("check=") ? 600 : p.includes("check=") ? 1000 : 0;
    NET.reply = p => p.includes("check=") ? [404, { error: "No such check." }] : undefined;
    go("payroll", FX.MBS); await settle(now + 100); if (first) first(); await settle(); m.querySelectorAll = () => [];
    return { bound: !!first, mbs: /Payroll check · MBS/.test(shown()), toasts: toasts().length, loading: m.classList.contains("loading") };
  });
  // a Setup preview that answers after another record's dialog was opened is not written into it
  for (const [kind, openIt, other, save] of [["checklist", `openChecklist("new")`, `openChecklist(state.setup.chk.items[0].id)`, `chkSave(true)`], ["reminders", `openReminder("new")`, `openReminder(state.setup.rem.rules[0].id)`, `remSave(true)`]]) {
    await tryit(`preview:${kind}`, async () => {
      fresh(); await open("setup:" + kind); run(openIt); await settle();
      NET.reply = (p, m) => m !== "GET" ? [200, { affected: {}, lines: [] }] : undefined; NET.delay = (p, m) => m !== "GET" ? 900 : 0;
      if (kind === "reminders") byId("rm-key").value = "made_up";
      if (byId(kind === "checklist" ? "cl-from" : "rm-from")) byId(kind === "checklist" ? "cl-from" : "rm-from").value = FX.MONTH;
      run(`${save}.catch(e => toast(e.message, true))`); await settle(now + 100);
      run(other); await settle(now + 50); const before = snapshot(); await settle();
      return { sent: NET.writes.length, changed: differs(before, snapshot()) };
    });
  }

  // a render held up while the day's first month set-up runs: a page asked for after it stays
  await tryit("newDay", async () => {
    fresh(); await open("settings");
    run(`state.day = "2000-01-01"`);
    let first = true;
    NET.reply = (p, m) => m !== "GET" ? [200, {}] : undefined;
    NET.delay = (p, m) => p === "/api/months/open" && first ? (first = false, 1000) : 0;
    go("entity"); await settle(now + 100);
    run(`state.day = dayKey()`);                 // the months are set up meanwhile; the next page doesn't wait
    go("audit"); await settle(now + 200);
    const before = snapshot(), reads = NET.reads.length; await settle();
    return { held: !first, changed: differs(before, snapshot()), read: NET.reads.slice(reads).filter(p => !p.startsWith("/api/next")), audit: /Audit pack/.test(shown()) };
  });
  // a page the company doesn't use, opened while a slow page is read: its card stays
  await tryit("unused", async () => {
    fresh(); await open("settings"); NET.delay = p => p.startsWith("/api/audit-readiness") ? 900 : 0;
    go("audit", FX.TYD); await settle(now + 100); go("sql", FX.TYD); await settle(now + 100);
    const before = snapshot(); await settle();
    return { changed: differs(before, snapshot()), card: /used for TYD/.test(shown()) };
  });

  // the SQL page's Fetch: its answer after another company's SQL page, or after another page, paints nothing there
  const PREVIEW = e => ({ entity_id: e, filename: "SQL exports fetched 20261105-1000.xlsx", fetch: { files: [], folder: "x" }, records: [], mapping: {}, headers: [], fields: [] });
  for (const how of ["answer", "fail"]) for (const where of ["company", "page"]) await tryit(`fetch:${where}:${how}`, async () => {
    fresh(); await open("sql");
    NET.reply = (p, m) => m === "POST" && p === "/api/sql/preview" ? (how === "fail" ? [500, { error: "The folder could not be read." }] : [200, PREVIEW(FX.QFB)]) : undefined;
    NET.delay = (p, m) => m === "POST" ? 1000 : 0;
    run(`sqlFetch().catch(e => toast(e.message, true))`); await settle(now + 100);
    if (where === "company") go("sql", FX.MBS); else go("audit");
    await settle(now + 200);
    const before = snapshot(); await settle();
    const r = { changed: differs(before, snapshot()) };
    // back on QFB's SQL page: nothing is left reading, and the preview read for it is there when no other SQL page was opened meanwhile
    NET.delay = () => 0; await open("sql");
    r.reading = run(`sqState().reading`); r.preview = run(`state.sqlPreview ? state.sqlPreview.entity_id : null`);
    return r;
  });

  /* ======== C. a change kept, then a page that can't be read back ======== */
  const SAVED = "It was saved, but this page could not reload. Try again.";
  const NEVER = /Nothing was changed|Nothing was kept|wasn't built|wasn&#39;t built|Nothing you typed since then was sent or saved|Nothing was added|Nothing was saved|wasn't checked/;
  const said = () => [shown(), roots.drawer.hidden ? "" : roots.drawer.full(), ...toasts().map(t => t.msg)].join("\n");
  const savedCount = () => toasts().filter(t => t.msg === SAVED).length;
  const onPage = () => shown().includes("It was saved, but this page could not reload.");
  const click = async dataset => { const b = { dataset, tagName: "BUTTON", id: dataset.id || "", className: "", disabled: false, innerHTML: "", textContent: "", isConnected: true,
      getAttribute: () => null, setAttribute() {}, removeAttribute() {}, classList: { contains: () => false, add() {}, remove() {} } };
    b.closest = s => /button/.test(s) ? b : null; const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; for (const f of listeners.click || []) f(ev); return b; };
  const fire = (type, target) => { for (const f of listeners[type] || []) f({ type, target, preventDefault() {}, stopPropagation() {} }); };
  sandbox.__click = click;
  const el = id => byId(id);
  const set = (id, v) => { const e = el(id); if (!e) throw new Error("no #" + id); e.value = v; return e; };
  const W = (match, body, status = 200) => { NET.reply = (p, m) => m !== "GET" && match.test(p) ? [status, body] : NET.extra ? NET.extra(p, m) : undefined; };
  const R = { review: () => { NET.extra = p => p.startsWith("/api/recon/review") ? [200, RV] : undefined; } };
  const openRV = async () => { await open("bank"); NET.reply = rvReply; run(`openReview(7, false)`); await settle(); NET.reply = () => undefined; };
  const panel = `state.recon.panel = { statement: { id: 7 }, account: { id: ${FX.ACCT}, label: "Main", currency: "MYR" }, label: "Sample month", locked_at: "2026-10-01", month: ${JSON.stringify(FX.MONTH)} }`;
  const openDialog = async () => { await open("entity"); run(`openPayment(${FX.PAY})`); await settle(); };
  const bud = (type, target) => { const b = el("bud"); if (!b) throw new Error("no budget"); b.on[type][0]({ type, target: { closest: () => null, dataset: {}, classList: { contains: () => false }, ...target }, preventDefault() {} }); };
  const sqPreview = e => `state.sqlPreview = { entity_id: ${e}, token: "t", filename: "listing.xlsx", records: [{ row: 1 }], mapping: {}, header_row: 0 }`;
  const why = async () => { await settle(); const r = el("su-reason"); if (!r) throw new Error("no reason box"); r.value = "A made-up reason"; el("setupWhy").hidden = false; run(`whySubmit()`); };
  const payeeForm = () => { const f = el("payeeForm"); const btn = { disabled: false, isConnected: true, setAttribute() {}, removeAttribute() {} }; return () => f.onsubmit({ preventDefault() {}, target: { querySelector: () => btn } }); };
  const advRow = (k, v) => { for (const [f, x] of Object.entries(v)) set(`adv-${k}-${f}`, x); };
  const btn = () => ({ disabled: false, isConnected: true, getAttribute: () => null, setAttribute() {}, removeAttribute() {}, closest: () => null, after() {} });
  sandbox.__btn = btn();

  // name -> { page: how the page is opened; write: the change's route; reply; act: what is done; n: how many changes it sends }
  const FLOWS = {
    "payment dialog: Save details": { prep: openDialog, route: /\/api\/payments\/\d+$/, reply: {}, act: () => { set("pf-notes", "A made-up note"); run(`paySave()`); }, dialog: "closed" },
    "payment dialog: Save details, then Undo": { prep: openDialog, route: /\/api\/payments\/\d+$/, reply: {}, first: () => { set("pf-notes", "A made-up note"); run(`paySave()`); }, act: undo => undo() },
    "payment dialog: an SQL voucher unlinked": { prep: openDialog, route: /\/api\/sql\/entries\/41\/unlink$/, reply: { doc_no: "PV-1", payment: "x" }, act: () => click({ sqlUnlink: "41" }), dialog: "closed" },
    "payment dialog: a document uploaded": { prep: openDialog, route: /\/api\/upload$/, reply: { id: 1 }, act: () => run(`pdUpload([{ file: { name: "bill.pdf", size: 10 }, type: "invoice" }])`), dialog: "closed" },
    "payment dialog: a document removed": { prep: openDialog, route: /\/api\/documents\/\d+\/remove$/, reply: {}, act: () => { run(`state.pay.ask = { act: "remove", doc: ${FX.DOC} }`); click({ pdAsk: "yes" }); }, dialog: "closed" },
    "New payment: Add": { prep: async () => { await open("entity"); run(`addPaymentDrawer()`); await settle(); }, route: /\/api\/payments$/, reply: { id: 999 }, act: () => { set("ap-desc", "A made-up bill"); run(`npSave()`); } },
    "New payment: Add, then Undo": { prep: async () => { await open("entity"); run(`addPaymentDrawer()`); await settle(); }, route: /\/api\/payments\/999$/, reply: {}, first: () => { NET.reply = (p, m) => m !== "GET" ? [200, { id: 999 }] : undefined; set("ap-desc", "A made-up bill"); run(`npSave()`); }, act: undo => undo() },
    "New payment on the Overview: Add": { prep: async () => { await open("overview"); run(`addPaymentDrawer()`); await settle(); }, route: /\/api\/payments$/, reply: { id: 999 }, act: () => { run(`state.np.co = ${FX.QFB}`); set("ap-co", String(FX.QFB)); set("ap-desc", "A made-up bill"); run(`npSave()`); }, overview: true },
    "register: Set paid date on the picked": { prep: () => open("entity"), route: /\/api\/payments\/\d+$/, reply: {}, act: () => { run(`regState().picked = [${FX.PAY}]; regPaint()`); const d = el("regBulkDate"); if (d) d.value = FX.MONTH + "-05"; else { run(`regState().date = ""`); throw new Error("no bulk date box"); } run(`regBulk("date")`); } },
    "register: one bank slip to the picked": { prep: () => open("entity"), route: /\/api\/upload$/, reply: {}, act: () => { run(`regState().picked = [${FX.PAY}]; regPaint(); regBulk("upload")`); } },
    "checklist: a document uploaded on an item": { prep: () => open("checklist"), route: /\/api\/upload$/, reply: {}, act: () => click({ taskUpload: String(FX.TASK), type: "other", upload: "other" }) },
    "checklist: an item ticked": { prep: () => open("checklist"), route: /\/api\/tasks\/\d+$/, reply: {}, act: () => { run(`state.data.tasks.find(x => x.id === ${FX.TASK}).lacking = []`); fire("change", { dataset: { task: String(FX.TASK) }, checked: true, id: "", closest: () => null, matches: () => false }); } },
    "checklist: month reopened": { prep: () => open("checklist"), route: /\/api\/months\/close$/, reply: { pack_ticked: false }, act: () => click({ reopenMonth: "1" }) },
    "register: month set up": { prep: () => open("entity"), route: /\/api\/months\/open$/, reply: {}, act: () => click({ openMonth: String(FX.QFB) }) },
    "checklist: a document removed": { prep: () => open("checklist"), route: /\/api\/documents\/\d+\/remove$/, reply: {}, act: () => click({ removeDoc: String(FX.DOC), name: "a file" }) },
    "payment dialog: Remove this payment": { prep: openDialog, route: /\/api\/payments\/\d+$/, reply: { unlinked: [], before_tracking: [], lines: 0 }, act: () => { const b = el("deletePayment"); run(`state.openPayment`); click({ id: "deletePayment", confirm: "1" }); } },
    "audit pack: Mark month as filed": { prep: async () => { await open("audit"); run(`ask = async (m, o) => !/backup/i.test(o.title)`); /* filed; "Not now" to the backup */ }, route: /\/api\/months\/close$/, reply: {}, act: () => click({ closeMonth: "1" }) },
    "audit pack: Build": { prep: () => open("audit"), route: /\/api\/audit-pack$/, reply: { url: "/api/audit-pack/file?x=1" }, act: () => click({ id: "buildPack" }) },
    "audit pack: Auditor package": { prep: () => open("audit"), route: /\/api\/auditor-export$/, reply: { url: "/api/auditor-export/file?x=1", files: 3, left_out: 0, name: "package.zip" }, act: () => click({ id: "auditorPack" }), keeps: "package.zip" },
    "audit trail: Accept changes made outside": { prep: () => open("trail"), route: /\/api\/audit\/accept-outside$/, reply: { accepted: 1 }, act: () => { const r = el("trailReason") || (roots.main.insertAdjacentHTML("beforeend", `<input id="trailReason">`), el("trailReason")); r.value = "A made-up reason"; click({ id: "trailAccept" }); } },
    "audit trail: Check, with differences": { prep: () => open("trail"), route: /\/api\/audit\/check$/, reply: { ok: false, checked: 3, check_code: "x", problems: [], replay: { checked: 1, problems: [], count: 1, more: 0 } }, act: () => click({ id: "trailCheck" }), keeps: "found problems" },
    "bank: Reopen month": { prep: async () => { await open("bank"); run(panel); run(`reopenDialog(7)`); await settle(); }, route: /\/api\/recon\/reopen$/, reply: {}, act: () => { set("bk-why", "A made-up reason"); sandbox.__go = { dataset: { sid: "7" }, setAttribute() {}, removeAttribute() {}, disabled: false, textContent: "" }; run(`reopenGo(__go)`); } },
    "bank: Mark reconciled": { prep: async () => { await open("bank"); }, route: /\/api\/recon\/sign-off$/, reply: {}, act: () => run(`rcSign(7, "", "").catch(e => toast(e.message, true))`) },
    "bank: the signed statement uploaded": { prep: () => open("bank"), route: /\/api\/upload$/, reply: {}, act: () => run(`rcSignedUpload(${FX.TASK}, "QFB-1").catch(e => toast(e.message, true))`) },
    "bank: confirm sign-off again": { prep: () => open("bank"), route: /\/api\/recon\/confirm-book$/, reply: {}, act: () => click({ rcReconfirm: "7" }) },
    "bank review: Confirm all matched": { prep: openRV, route: /\/api\/recon\/confirm-matched$/, reply: { confirmed: 1, needs_date_tick: 0 }, act: () => click({ rvConfirmAll: "1" }) },
    "bank review: Apply selected": { prep: async () => { await openRV(); run(`state.recon.rv.d.lines = [{ id: 31, state: "explained", txn_date: ${JSON.stringify(FX.MONTH + "-03")}, amount: -5, balance: 1, description: "Sample line", suggestions: [], vouchers: [], payment: null, group: null }]; state.recon.rv.sel = { 31: true }`); }, route: /\/api\/recon\/apply$/, reply: { linked: 0, created: 0, explained: 0, confirmed: 1 }, act: () => run(`rvApply().catch(e => toast(e.message, true))`),
      after: () => ({ sel: run(`Object.keys(state.recon.rv?.sel || {}).length`) }), want: { sel: 0 } },
    "bank review: a pair ticked": { prep: async () => { await openRV(); run(`state.recon.rv.d.summary.pairs = [{ key: "k1", nil: true, reason: "reversal", docs: [], confirmed_at: null }]`); }, route: /\/api\/recon\/pair$/, reply: {}, act: () => run(`pairTick({ checked: true, dataset: { pairTick: "k1" }, closest: () => null }).catch(e => toast(e.message, true))`) },
    "bank review: a pair's Undo": { prep: async () => { await openRV(); run(`state.recon.rv.d.summary.pairs = [{ key: "k1", nil: true, reason: "reversal", docs: [], confirmed_at: null }]`); }, route: /\/api\/recon\/pair$/, reply: {}, first: () => { NET.extra = rvReply; run(`pairTick({ checked: true, dataset: { pairTick: "k1" }, closest: () => null })`); }, act: undo => undo() },
    "bank review: Undo a line": { prep: openRV, route: /\/api\/statement-lines\/31$/, reply: {}, act: () => click({ unlink: "31" }) },
    "bank: Match again": { prep: () => open("bank"), route: /\/api\/statements\/rematch$/, reply: { matched: 0, no_docs: 0 }, act: () => click({ id: "rematch" }) },
    "bank: Explain a line": { prep: async () => { await openRV(); run(`state.recon.rv.d.lines = [{ id: 31, state: "open", txn_date: ${JSON.stringify(FX.MONTH + "-03")}, amount: -5, balance: 1, description: "Sample line", suggestions: [], vouchers: [] }]; explainLine(31)`); await settle(); }, route: /\/api\/statement-lines\/31$/, reply: {}, act: () => el("ex-none").onclick() },
    "bank: Explain a line, then Undo": { prep: async () => { await openRV(); run(`state.recon.rv.d.lines = [{ id: 31, state: "open", txn_date: ${JSON.stringify(FX.MONTH + "-03")}, amount: -5, balance: 1, description: "Sample line", suggestions: [], vouchers: [] }]; explainLine(31)`); await settle(); }, route: /\/api\/statement-lines\/31$/, reply: {}, first: () => el("ex-none").onclick(), act: undo => undo() },
    "bank: before tracking": { prep: () => open("bank"), route: /\/api\/recon\/before-tracking$/, reply: {}, act: () => run(`rcAct("before-tracking", { statement_id: 7 }, "Marked.").catch(e => toast(e.message, true))`) },
    "bank: statement imported": { prep: () => open("bank"), route: /\/api\/statements$/, reply: { lines: 3, month: FX.MONTH, matched: 1, no_docs: 0 }, act: () => { el("stmtFile").files = [{ name: "s.pdf" }]; fire("submit", { id: "stmtForm", querySelector: () => null }); } },
    "bank: book opening saved": { prep: () => open("bank"), route: /\/api\/recon\/book-opening$/, reply: {}, act: () => { set("openMonth", FX.MONTH); set("openAmount", "10.00"); fire("submit", { id: "openingForm", querySelector: () => null }); } },
    "SQL page: Import": { prep: async () => { await open("sql"); run(sqPreview(FX.QFB)); }, route: /\/api\/sql\/apply$/, reply: { added: 2, linked: 1, skipped: 0 }, act: () => { sandbox.__go = btn(); run(`sqlApply(__go).catch(e => toast(e.message, true))`); }, after: () => ({ done: run(`state.sq?.done?.title || null`) }), want: { done: "Imported 2 entries" }, keeps: "Imported 2 entries" },
    "SQL page: Create payments for all": { prep: () => open("sql"), route: /\/api\/sql\/entries\/create-all$/, reply: { created: 1, linked: 0, left: 0, corrections: [], bank_lines_matched: 0 }, act: () => run(`sqAsk("all-yes").catch(e => toast(e.message, true))`) },
    "SQL page: Ignore all": { prep: () => open("sql"), route: /\/api\/sql\/entries\/ignore$/, reply: { ignored: 1 }, act: () => run(`state.sqlCorrections = [1]; sqAsk("ign-yes").catch(e => toast(e.message, true))`) },
    "SQL page: Link": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41$/, reply: {}, act: () => { const s = document.querySelector; document.querySelector = q => q === 'select[data-sql-link="41"]' ? { value: String(FX.PAY) } : s(q); run(`sqlEntryLink(41).catch(e => toast(e.message, true))`); document.querySelector = s; } },
    "SQL page: Create payment": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41$/, reply: {}, act: () => click({ sqlCreate: "41" }) },
    "SQL page: Ignore": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41$/, reply: {}, act: () => click({ sqlIgnore: "41" }) },
    "SQL page: Ignore, then Undo": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41\/unignore$/, reply: {}, first: () => click({ sqlIgnore: "41" }), act: undo => undo() },
    "SQL page: Link, then Undo": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41\/unlink$/, reply: { removed: false }, first: () => { const s = document.querySelector; document.querySelector = q => q === 'select[data-sql-link="41"]' ? { value: String(FX.PAY) } : s(q); run(`sqlEntryLink(41)`); document.querySelector = s; }, act: undo => undo() },
    "SQL page: take another name for the company": { prep: () => open("sql"), route: /\/api\/sql\/take-company$/, reply: {}, act: () => click({ sqlTake: "Quillon Fab", confirm: "1" }) },
    "SQL page: a moved link followed": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41\/move-link$/, reply: { doc_no: "PV-1", payment: "x" }, act: () => click({ sqlMove: "41", sqlMoveTo: "5" }) },
    "SQL page: rows ignored": { prep: () => open("sql"), route: /\/api\/sql\/entries\/ignore$/, reply: { ignored: 2 }, act: () => click({ sqlIgnoreIds: "1,2" }) },
    "SQL page: Deleted in SQL": { prep: () => open("sql"), route: /\/api\/sql\/entries\/deleted$/, reply: { doc_nos: ["PV-1"] }, act: () => click({ sqlDeletedIds: "1" }) },
    "SQL page: Unlink": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41\/unlink$/, reply: { doc_no: "PV-1", payment: "x" }, act: () => click({ sqlUnlink: "41" }) },
    "SQL page: Un-ignore": { prep: () => open("sql"), route: /\/api\/sql\/entries\/41\/unignore$/, reply: { doc_no: "PV-1" }, act: () => click({ sqlUnignore: "41" }) },
    "e-Invoices: Unlink": { prep: () => open("einvoices"), route: /\/api\/sql\/entries\/41\/unlink$/, reply: { doc_no: "IV-1", payment: "x" }, act: () => click({ sqlUnlink: "41" }) },
    "Books: Use these statutory accounts": { prep: () => open("statutory"), route: /\/api\/statutory\/use-suggested$/, reply: { added: 1 }, act: () => { sandbox.__go = btn(); run(`statutoryUse(__go)`); } },
    "Recurring: add to the month": { prep: () => open("payees"), route: /\/api\/payees\/\d+\/add-to-month$/, reply: { opened: false }, act: () => click({ addMonth: String(FX.PAYEE) }) },
    "Recurring: add a payment": { prep: async () => { await open("payees"); run(`editPayee("new")`); await settle(); }, route: /\/api\/payees$/, reply: { id: 500 }, act: () => { set("py-name", "A made-up payee"); set("py-day", "5"); sandbox.__submit = payeeForm(); run(`__submit()`); }, dialog: "closed" },
    "Recurring: save a payment": { prep: async () => { await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); }, route: /\/api\/payees$/, reply: {}, act: () => { set("py-notes", "A made-up note"); sandbox.__submit = payeeForm(); run(`__submit()`); }, dialog: "closed" },
    "Recurring: delete": { prep: async () => { await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("delete", ${FX.PAYEE}, __btn)`); }, route: /\/api\/payees\/\d+$/, reply: {}, act: why, dialog: "closed" },
    "Recurring: stop using": { prep: async () => { await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("stop", ${FX.PAYEE}, __btn)`); }, route: /\/api\/payees\/\d+\/stop$/, reply: {}, act: why, dialog: "closed" },
    "Recurring: add an advance": { prep: async () => { await open("payees"); run(`state.payees.find(p => p.id === ${FX.PAYEE}).category = "salary"; editPayee(${FX.PAYEE})`); await settle(); }, route: /\/api\/payees\/\d+\/advances$/, reply: {}, act: () => { advRow("new", { amt: "100", from: FX.MONTH, to: FX.MONTH, note: "" }); sandbox.__go = btn(); run(`advAdd(${FX.PAYEE}, __go).catch(e => toast(e.message, true))`); }, dialog: "closed" },
    "Recurring: save an advance": { prep: async () => { await open("payees"); run(`{ const p = state.payees.find(p => p.id === ${FX.PAYEE}); p.category = "salary"; p.advances = [{ id: 8, monthly_deduction: 10, start_month: ${JSON.stringify(FX.MONTH)}, end_month: ${JSON.stringify(FX.MONTH)}, note: "" }]; } editPayee(${FX.PAYEE})`); await settle(); }, route: /\/api\/advances\/8$/, reply: {}, act: () => { set("adv-8-amt", "20"); sandbox.__go = btn(); run(`advSave(8, __go).catch(e => toast(e.message, true))`); }, dialog: "closed" },
    "Recurring: remove an advance": { prep: async () => { await open("payees"); run(`{ const p = state.payees.find(p => p.id === ${FX.PAYEE}); p.category = "salary"; p.advances = [{ id: 8, monthly_deduction: 10, start_month: ${JSON.stringify(FX.MONTH)}, end_month: ${JSON.stringify(FX.MONTH)}, note: "" }]; } editPayee(${FX.PAYEE})`); await settle(); run(`advDelete(8, __btn)`); }, route: /\/api\/advances\/8$/, reply: {}, act: why, dialog: "closed" },
    "Budget: the balance": { prep: () => open("budget"), route: /\/api\/budget\/header$/, reply: {}, act: () => { set("bud-bal", "1,000.00"); bud("change", { id: "bud-bal" }); }, partOnly: true },
    "Budget: the balance's date": { prep: () => open("budget"), route: /\/api\/budget\/header$/, reply: {}, act: () => { set("bud-date", FX.MONTH + "-02"); bud("change", { id: "bud-date" }); }, partOnly: true },
    "Budget: a line changed": { prep: () => open("budget"), route: /\/api\/budget\/lines\/\d+$/, reply: {}, act: () => bud("change", { id: "x", value: "A made-up line", dataset: { f: "description" }, closest: s => s === "tr[data-line]" ? { dataset: { line: String(FX.LINE) } } : null }), partOnly: true },
    "Budget: add a line": { prep: () => open("budget"), route: /\/api\/budget\/lines$/, reply: { result: 77 }, act: () => bud("click", { closest: () => ({ dataset: { add: "MYR" } }) }), partOnly: true },
    "Budget: add a payment to it": { prep: () => open("budget"), route: /\/api\/budget\/lines$/, reply: {}, act: () => bud("click", { closest: () => ({ dataset: { addPayment: String(FX.PAY) } }) }), partOnly: true, keeps: "Added to the budget" },
    "Budget: delete a line": { prep: () => open("budget"), route: /\/api\/budget\/lines\/delete$/, reply: {}, act: () => bud("click", { closest: () => ({ dataset: { del: String(FX.LINE) } }) }), partOnly: true },
    "Budget: set up": { prep: () => open("budget"), route: /\/api\/budget\/setup$/, reply: { result: 2 }, act: () => run(`setUpBudget({ entity: { id: ${FX.QFB} }, month: ${JSON.stringify(FX.MONTH)} })`) },
    "Budget: the browser's old balance carried over": { prep: async () => { await open("settings"); NET.extra = p => p.startsWith("/api/budget?") ? [200, JSON.parse(JSON.stringify({ ...answers.get(`/api/budget?entity=${FX.QFB}&month=${FX.MONTH}`)?.body, balance: null, saved_as_at: null }))] : undefined; run(`localStorage.setItem("bal-${FX.QFB}-${FX.MONTH}", "500")`); }, route: /\/api\/budget\/header$/, reply: {}, act: () => go("budget") },
    "Payroll: a workbook checked": { prep: () => open("payroll"), route: /\/api\/payroll-check$/, reply: { chosen: { report: { headline: "Nothing to fix" } } }, act: () => { el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); }, partOnly: true },
  };
  /* ---- B3. dialogs ---- */
  // two dialogs asked for, each read first, the first answered first (the real server answers one request at a time): the one asked for last
  // is the one shown
  for (const how of ["answer", "fail"]) await tryit(`lastAsked:${how}`, async () => {
    const res = {};
    for (const [k, page, a, b, slowA, slowB, shows] of [
      ["recurring", "payees", `editPayee(${FX.PAYEE})`, `editPayee(${FX.PAYEE2})`, `/api/payees/${FX.PAYEE}/usage`, `/api/payees/${FX.PAYEE2}/usage`, () => run(`$("#py-name")?.value ?? null`)],
      ["setup", "setup:payment_types", `openSetup("payment_types", ${FX.TYPES[0]})`, `openSetup("payment_types", ${FX.TYPES[1]})`, `/api/setup/payment_types/${FX.TYPES[0]}`, `/api/setup/payment_types/${FX.TYPES[1]}`, () => run(`state.setup.drawer?.id ?? null`)]]) {
      fresh(); await open(page);
      NET.delay = p => p === slowA ? 500 : p === slowB ? 1000 : 0;
      if (how === "fail") NET.fail = p => p === slowA ? "500" : null;
      clicked(a); await settle(now + 50); clicked(b); await settle();
      res[k] = { open: !roots.drawer.hidden, shows: shows(), toasts: toasts().length };
    }
    res.want = { recurring: run(`state.payees?.find(p => p.id === ${FX.PAYEE2})?.name ?? null`) };
    await open("payees"); res.want.recurring = run(`state.payees.find(p => p.id === ${FX.PAYEE2}).name`); res.want.setup = FX.TYPES[1];
    return res;
  });

  // a change answered after its dialog was closed and another one opened: the other one is left alone
  const slowWrite = (reply, status = 200) => { NET.reply = (p, m) => m !== "GET" ? [status, reply] : undefined; NET.delay = (p, m) => m !== "GET" ? 900 : 0; };
  const swap = async openOther => { await settle(now + 100); run(`closeDrawer(true)`); run(openOther); await settle(now + 100); };
  const msgs = () => toasts().map(t => t.msg);
  // the payment dialog's Save: refused, kept, and kept with a page that can't be read back
  for (const [k, status, reply, down] of [["saveRefused", 409, { error: "The month is filed." }], ["saveKept", 200, {}], ["saveNotRead", 200, {}, "500"]]) await tryit(`otherDialog:${k}`, async () => {
    fresh(); await open("entity"); run(`openPayment(${FX.PAY})`); await settle();
    slowWrite(reply, status); if (down) NET.afterWrite = down;
    set("pf-notes", "first dialog"); run(`paySave()`);
    await settle(now + 100); run(`closeDrawer(true)`); run(`openPayment(${FX.PAY2})`); set("pf-notes", "typed in the second");
    await settle();
    return { open: run(`state.openPayment`) === FX.PAY2 && !roots.drawer.hidden, notes: el("pf-notes")?.value ?? null, unsaved: run(`Object.keys(unsavedEdits()).join()`),
      refused: el("pd-refused-box")?.innerHTML || "", msgs: msgs() };
  });
  // New payment: refused, and kept
  for (const [k, status, reply] of [["addRefused", 409, { error: "The month is filed." }], ["addKept", 200, { id: 999 }]]) await tryit(`otherDialog:${k}`, async () => {
    fresh(); await open("entity"); run(`addPaymentDrawer()`); await settle();
    slowWrite(reply, status); set("ap-desc", "A made-up bill"); run(`npSave()`); await swap(`addPaymentDrawer()`); set("ap-desc", "A second made-up bill"); await settle();
    return { open: !roots.drawer.hidden && run(`!!state.np`), desc: el("ap-desc")?.value ?? null, refused: el("np-refused")?.innerHTML || "", msgs: msgs() };
  });
  // an upload answered after its dialog was closed and New payment opened, the page then not read back: New payment stays
  await tryit("otherDialog:upload", async () => {
    fresh(); await open("entity"); run(`openPayment(${FX.PAY})`); await settle();
    slowWrite({ id: 1 }); NET.afterWrite = "500"; run(`pdUpload([{ file: { name: "bill.pdf", size: 10 }, type: "invoice" }])`); await settle(now + 100);
    run(`closeDrawer(true)`); run(`addPaymentDrawer()`); await settle();
    return { open: !roots.drawer.hidden && run(`!!state.np`), writes: NET.writes.length, said: msgs().includes("It was saved, but this page could not reload. Try again.") };
  });
  await tryit("otherDialog:removed", async () => {
    fresh(); await open("entity"); run(`openPayment(${FX.PAY})`); await settle();
    slowWrite({ unlinked: [], before_tracking: [], lines: 0 }); click({ id: "deletePayment", confirm: "1" }); await swap(`openPayment(${FX.PAY2})`); await settle();
    return { open: run(`state.openPayment`) === FX.PAY2 && !roots.drawer.hidden };
  });
  await tryit("otherDialog:recurringSaved", async () => {
    fresh(); await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle();
    slowWrite({}); set("py-notes", "first dialog"); sandbox.__submit = payeeForm(); run(`__submit()`); await swap(`editPayee(${FX.PAYEE2})`); set("py-notes", "typed in the second"); await settle();
    return { open: !roots.drawer.hidden, name: el("py-name")?.value ?? null, notes: el("py-notes")?.value ?? null, want: run(`state.payees.find(p => p.id === ${FX.PAYEE2}).name`) };
  });
  await tryit("otherDialog:recurringDeleted", async () => {
    fresh(); await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("delete", ${FX.PAYEE}, __btn)`);
    slowWrite({}); await why(); await swap(`editPayee(${FX.PAYEE2})`); await settle();
    return { open: !roots.drawer.hidden, name: el("py-name")?.value ?? null, want: run(`state.payees.find(p => p.id === ${FX.PAYEE2}).name`) };
  });
  // a stop refused after its dialog was closed: said in a message, not under the next dialog's reason box
  await tryit("otherDialog:stopRefused", async () => {
    fresh(); await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("stop", ${FX.PAYEE}, __btn)`);
    slowWrite({ error: "It is in use." }, 409); await why(); await swap(`editPayee(${FX.PAYEE2})`);
    run(`payeeAct("stop", ${FX.PAYEE2}, __btn)`); set("su-reason", "typed for the second"); await settle();
    return { box: el("su-why-msg")?.innerHTML || "", reason: el("su-reason")?.value ?? null, said: msgs().includes("It is in use.") };
  });
  await tryit("otherDialog:reopened", async () => {
    fresh(); await open("bank"); run(panel); run(`reopenDialog(7)`); await settle();
    slowWrite({}); set("bk-why", "A made-up reason"); sandbox.__go = { dataset: { sid: "7" }, setAttribute() {}, removeAttribute() {}, disabled: false, textContent: "" }; run(`reopenGo(__go)`);
    await swap(`openHistory("budget_lines", ${FX.LINE}, "Opened since")`); await settle();
    return { open: !roots.drawer.hidden, other: /Opened since/.test(roots.drawer.full()) };
  });
  await tryit("otherDialog:putBack", async () => {
    fresh(); await open("trail");
    const preview = { label: "Bank account", name: "Spare", table: "accounts", kind: "accounts", id: 2, same_id: true, notes: [], lines: [], affected: {},
      deleted: { at: "2026-11-02T10:00:00", actor: "Made-up user", entry: 4, key: 2, reason: "Made up" } };
    NET.reply = (p, m) => p === "/api/setup/restore/5" ? [200, preview] : undefined;
    run(`openRestore(5, "A record")`); await settle(); set("pb-why", "A made-up reason");
    slowWrite({ label: "Bank account", kind: "accounts", id: 2, same_id: true }); sandbox.__go = btn(); run(`restoreGo(5, __go)`);
    await swap(`openHistory("budget_lines", ${FX.LINE}, "Opened since")`); await settle();
    return { open: !roots.drawer.hidden, other: /Opened since/.test(roots.drawer.full()) };
  });
  // Mark as filed: the month's readiness read after another page was opened asks nothing there and files nothing
  await tryit("filedElsewhere", async () => {
    fresh(); await open("audit"); NET.delay = p => p.startsWith("/api/audit-readiness") ? 900 : 0; NET.writes.length = 0;
    run(`globalThis.__asked = 0; ask = async () => { __asked++; return true; }`);
    click({ closeMonth: "1" }); await settle(now + 100); NET.delay = () => 0; go("settings"); await settle();
    const res = { asked: run(`__asked`), writes: NET.writes.length };
    run(`ask = async () => true`);
    return res;
  });
  // Add company from the switcher: Setup read after another page was opened gets no add form over it
  await tryit("addCompanyElsewhere", async () => {
    fresh(); await open("settings"); let used = false; NET.delay = p => !used && p.startsWith("/api/setup/entities") ? (used = true, 900) : 0;
    run(`tbAddCompany()`); await settle(now + 100); const asked = used; go("audit"); await settle();
    return { asked, dialog: !roots.drawer.hidden, audit: /Audit pack/.test(shown()) };
  });
  // every page that reads anything is among the pages these checks go through: a new one has to be added to PAGES
  await tryit("routes", async () => {
    const res = { all: run(`Object.keys(ROUTES)`), missed: [] };
    for (const v of res.all) {
      if (PAGES.some(p => view(p) === v)) continue;
      fresh(); await open("settings"); NET.reads.length = 0; await open(v);
      const own = NET.reads.filter(p => !p.startsWith("/api/next"));
      if (own.length) res.missed.push([v, own]);
    }
    return res;
  });

  // what the page keeps of the budget before the flows: read once, so the carry-over case has an answer to alter
  fresh(); await open("budget");

  for (const [name, F] of Object.entries(FLOWS)) for (const how of ["500", "net"]) {
    if (how === "net" && !["payment dialog: Save details", "New payment: Add", "checklist: month reopened", "bank: Mark reconciled", "Budget: a line changed", "SQL page: Import", "Recurring: save a payment", "audit pack: Build"].includes(name)) continue;
    await tryit(`C:${name}:${how}`, async () => {
      fresh(); NET.extra = null;
      await F.prep(); await settle();
      NET.reply = (p, m) => m !== "GET" && F.route.test(p) ? [200, F.reply] : NET.extra ? NET.extra(p, m) : undefined;
      let undo = null;
      if (F.first) { const keep = NET.reply; F.first(); await settle(); NET.reply = keep; undo = toasts().find(t => t.undo)?.undo; if (!undo) throw new Error("no Undo was offered"); }
      toasts().length = 0; NET.writes.length = 0; NET.reads.length = 0; NET.afterWrite = how;
      F.act(undo); await settle();
      const writes = () => NET.writes.filter(w => F.route.test(w[1])).length, others = () => NET.writes.filter(w => !F.route.test(w[1]) && !(F.extraWrites && F.extraWrites.test(w[1]))).map(w => w.join(" "));
      const r = { writes: writes(), others: others(), readsFailed: NET.reads.length, saved: said().includes(SAVED) || onPage(), never: (said().match(NEVER) || [null])[0],
        savedToasts: savedCount(), onPage: onPage(), cards: (shown().match(/<(p|div class="note")>It was saved, but this page could not reload\./g) || []).length,
        dialog: roots.drawer.hidden ? "closed" : "open", drawer: roots.drawer.hidden ? "" : roots.drawer.full().slice(0, 300), said: said().slice(0, 600), kept: F.keeps ? said().includes(F.keeps) : null,
        after: F.after ? F.after() : null };
      // Try again while the reads still fail: it only reads
      const tryAgain = () => { const t = toasts().filter(x => x.msg === SAVED && x.action).pop();
        if (onPage() && !F.partOnly) { click({ retry: "saved" }); return "page"; } if (t) { t.action.fn(); return "toast"; } if (onPage()) { click({ retry: "saved" }); return "page"; } return null; };
      const n0 = NET.reads.length; r.tried = tryAgain(); await settle();
      r.again = { writes: writes(), others: others(), reads: NET.reads.length - n0, saved: said().includes(SAVED) || onPage(), never: (said().match(NEVER) || [null])[0] };
      // and once the records can be read again
      NET.afterWrite = null; NET.down = false; NET.extra = null;
      NET.reply = (p, m) => p === "/api/sql/preview" ? [200, PREVIEW(FX.QFB)] : m !== "GET" && F.route.test(p) ? [200, F.reply] : /\/api\/recon\/review/.test(p) ? [200, RV] : undefined;
      const n1 = NET.reads.length, s1 = savedCount(); r.triedOk = tryAgain(); await settle();
      r.ok = { writes: writes(), others: others(), reads: NET.reads.length - n1, newSaved: savedCount() - s1, onPage: onPage(), kept: F.keeps ? said().includes(F.keeps) : null, after: F.after ? F.after() : null };
      return r;
    });
  }

  // after another page is opened, a part's Try again draws the page on show, never that part over it
  await tryit("tryAgainElsewhere", async () => {
    fresh(); await open("payroll"); NET.reply = (p, m) => m !== "GET" ? [200, { chosen: null }] : undefined; NET.afterWrite = "500";
    el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); await settle();
    const t = toasts().filter(x => x.msg === SAVED && x.action).pop();
    NET.afterWrite = null; NET.down = false; await open("audit"); NET.reads.length = 0; const writes = NET.writes.length;
    t?.action.fn(); await settle();
    return { had: !!t, audit: /Audit pack/.test(shown()), payroll: /Payroll check ·/.test(shown()), sent: NET.writes.length - writes };
  });
  // a part's change answered while the same page of another company is being read, and then a read that fails: that page is not left with
  // nothing (its own draw is not overtaken by the part)
  await tryit("otherCompanyPart", async () => {
    const res = {};
    for (const [k, page, route, reply, act] of [
      ["payroll", "payroll", /\/api\/payroll-check$/, { chosen: null }, () => { el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); }],
      ["bank", "bank", /\/api\/recon\/sign-off$/, {}, () => run(`rcSign(7, "", "").catch(e => toast(e.message, true))`)]]) {
      fresh(); await open(page);
      NET.reply = (p, m) => m !== "GET" && route.test(p) ? [200, reply] : undefined; NET.delay = (p, m) => m !== "GET" ? 500 : 1000;
      NET.afterWrite = "500";   // read after the change is answered: fails. The other company's page, asked for before that, reads fine
      act(); await settle(now + 100); NET.down = false; go(page, FX.MBS); await settle(now + 100); NET.down = "500"; await settle();
      res[k] = { company: run(`state.entity`) === FX.MBS, filled: filled(page) || onPage(), loading: main().classList.contains("loading"), saved: said().includes(SAVED) || onPage() };
    }
    return res;
  });
  // a change answered after the user left: the page now shown is left alone, and the result is said in a message
  await tryit("lateWrite", async () => {
    const res = {};
    fresh(); await open("payroll"); NET.reply = (p, m) => m !== "GET" ? [400, { error: "Not a payroll workbook." }] : undefined; NET.delay = (p, m) => m !== "GET" ? 900 : 0;
    el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); await settle(now + 100); NET.delay = () => 0; go("audit"); await settle(now + 100); const b = shown(); await settle();
    res.refused = { same: shown() === b, toast: toasts().some(t => /payroll\.xlsx wasn't checked/.test(t.msg)) };
    fresh(); await open("payroll"); NET.reply = (p, m) => m !== "GET" ? [200, { chosen: { report: { headline: "Nothing to fix" } } }] : undefined; NET.delay = (p, m) => m !== "GET" ? 900 : 0;
    el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); await settle(now + 100); NET.delay = () => 0; go("audit"); await settle();
    res.kept = { audit: /Audit pack/.test(shown()), payroll: /Payroll check ·/.test(shown()), toast: toasts().some(t => t.msg === "Nothing to fix") };
    return res;
  });
  // a recurring Add whose list can't be read back, with something typed in the dialog meanwhile: it stays, and can't add the payment again
  await tryit("addTwice", async () => {
    fresh(); await open("payees"); run(`editPayee("new")`); await settle();
    NET.reply = (p, m) => m !== "GET" ? [200, { id: 500 }] : undefined; NET.afterWrite = "500"; NET.delay = (p, m) => m === "GET" ? 500 : 0;
    set("py-name", "A made-up payee"); set("py-day", "5"); const submit = payeeForm(); sandbox.__submit = submit; run(`__submit()`); await settle(now + 100);
    const n = el("py-notes"); if (n) n.value = "typed while the list is read"; await settle();
    const open1 = !roots.drawer.hidden, said = toasts().filter(t => t.msg === SAVED && t.action).length; run(`__submit()`); await settle();
    return { open: open1, writes: NET.writes.length, toast: toasts().some(t => /This was saved/.test(t.msg)), said };
  });
  // an advance added whose list can't be read back, with other typing in the dialog: the new advance's boxes are empty, so Add can't send it again
  await tryit("advanceTwice", async () => {
    fresh(); await open("payees"); run(`state.payees.find(p => p.id === ${FX.PAYEE}).category = "salary"; editPayee(${FX.PAYEE})`); await settle();
    NET.reply = (p, m) => m !== "GET" ? [200, {}] : undefined; NET.afterWrite = "500";
    set("py-notes", "typed and not saved"); advRow("new", { amt: "100", from: FX.MONTH, to: FX.MONTH, note: "" }); sandbox.__go = btn(); run(`advAdd(${FX.PAYEE}, __go)`); await settle();
    const r = { open: !roots.drawer.hidden, amt: el("adv-new-amt")?.value ?? null, notes: el("py-notes")?.value ?? null };
    sandbox.__go = btn(); run(`advAdd(${FX.PAYEE}, __go)`); await settle(); r.writes = NET.writes.length;
    return r;
  });
  // the payment dialog's Save, kept but not read back, leaves no dialog saying Saving…
  await tryit("savingStuck", async () => {
    fresh(); await openDialog(); NET.reply = (p, m) => m !== "GET" ? [200, {}] : undefined; NET.afterWrite = "500";
    set("pf-notes", "A made-up note"); run(`paySave()`); await settle();
    return { hidden: roots.drawer.hidden, open: run(`state.openPayment`), saving: run(`!!state.pay?.saving`) };
  });

  // a file added while something is typed in the payment dialog: the dialog stays with what was typed, and the words are said where they show
  await tryit("typedUpload", async () => {
    fresh(); await openDialog(); NET.reply = (p, m) => m !== "GET" ? [200, { id: 1 }] : undefined; NET.afterWrite = "500";
    set("pf-notes", "typed and not saved"); run(`pdUpload([{ file: { name: "bill.pdf", size: 10 }, type: "invoice" }])`); await settle();
    return { open: !roots.drawer.hidden, notes: el("pf-notes")?.value ?? null, said: toasts().filter(t => t.msg === SAVED && t.action).length, writes: NET.writes.length };
  });
  // "it was saved" belongs to the reading back of that change alone: a report read later on the same page and failing says only that
  await tryit("savedOnce", async () => {
    fresh(); await open("books"); run(`render({ saved: true })`); await settle();
    NET.fail = p => p.startsWith("/api/books") ? "500" : null; run(`state.books.tab = "bs"; drawBooks()`); await settle();
    const books = shown();
    fresh(); await open("einvoices"); run(`render({ saved: true })`); await settle();
    NET.fail = p => p.startsWith("/api/einvoices") ? "500" : null; go("einvoices", FX.MBS); await settle();
    return { books: books.includes("It was saved"), reason: books.includes("The server could not read the records."), einvoices: shown().includes("It was saved") };
  });
  // the upload that shows its progress (XMLHttpRequest) reads its answer as api() does
  await tryit("xhr", async () => {
    let answer = null;
    sandbox.XMLHttpRequest = class { constructor() { this.upload = {}; } open() {} setRequestHeader() {}
      send() { setImmediate(() => { if (answer === "net") return this.onerror(); [this.status, this.responseText] = answer; this.onload(); }); } };
    const res = {};
    for (const [k, a] of Object.entries({ ok: [200, '{"id": 3}'], html: [200, "<html></html>"], empty: [200, ""], refused: [400, '{"error": "Not accepted."}'], failed: [500, "oops"], net: "net" })) {
      answer = a; fresh(); const p = run(`pdPost({ id: 1, file: { name: "a.pdf", size: 1 }, type: "other" }, 1).then(d => ({ ok: d }), e => ({ message: e.message, unsure: !!e.unsure }))`); await settle(); res[k] = await p;
    }
    delete sandbox.XMLHttpRequest;
    return res;
  });

  /* ---- a change that got no answer, with the app stopped (or the server failing): the page says what to do, and never that nothing was
     changed, sent or saved, nor on Try again ---- */
  const visible = () => shown().replace(/<[^>]*>/g, " ").replace(/&#39;/g, "'");   // what is read (Copy details keeps the cause in an attribute)
  const UNANSWERED = {
    "the register's bulk Set paid date": [() => open("entity"), () => { run(`regState().picked = [${FX.PAY}]; regPaint()`); set("regBulkDate", FX.MONTH + "-05"); run(`regBulk("date")`); }],
    "the register's one bank slip": [() => open("entity"), () => run(`regState().picked = [${FX.PAY}]; regPaint(); regBulk("upload")`)],
    "a checklist item's upload": [() => open("checklist"), () => click({ taskUpload: String(FX.TASK), type: "other", upload: "other" })],
    "the payment dialog's upload": [openDialog, () => run(`pdUpload([{ file: { name: "bill.pdf", size: 10 }, type: "invoice" }])`)],
  };
  for (const [name, [prep, act]] of Object.entries(UNANSWERED)) for (const how of ["net", "500"]) await tryit(`unanswered:${name}:${how}`, async () => {
    fresh(); await prep(); await settle(); toasts().length = 0;
    NET.reply = (p, m) => m !== "GET" ? (how === "net" ? "net" : [500, { error: "The server could not save it." }]) : undefined; NET.afterWrite = how;
    act(); await settle();
    const first = visible(), told = toasts().map(t => t.msg).join("\n"), button = /data-retry="(\w+)"/.exec(shown());
    const reads = NET.reads.length;
    if (button) click({ retry: button[1] });
    await settle();
    return { first, said: told, pressed: !!button && NET.reads.length > reads, again: visible() };
  });

  /* ---- a read-back never takes the place of the same page asked for again while it was out ---- */
  const AGAIN = {
    payroll: { route: /\/api\/payroll-check$/, reply: { chosen: null }, act: () => { el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); } },
    bank: { route: /\/api\/recon\/sign-off$/, reply: {}, act: () => run(`rcSign(7, "", "").catch(e => toast(e.message, true))`) },
  };
  const outcome = page => ({ filled: filled(page) || onPage(), loading: main().classList.contains("loading"), saved: said().includes(SAVED) || onPage() });
  for (const [page, A] of Object.entries(AGAIN)) for (const how of ["menu", "away and back"]) await tryit(`samePage:${page}:${how}`, async () => {
    fresh(); await open(page);
    NET.reply = (p, m) => m !== "GET" && A.route.test(p) ? [200, A.reply] : undefined; NET.delay = (p, m) => m !== "GET" ? 500 : 1000;
    NET.afterWrite = "500";   // read after the change is answered: fails. The page asked for again before that reads fine
    A.act(); await settle(now + 100); NET.down = false;
    if (how === "away and back") { go("audit"); await settle(now + 10); }
    go(page); await settle(now + 100); NET.down = "500"; await settle();
    return outcome(page);
  });
  // ... nor when the change is sent from the old content, still on show while the page is asked for again
  await tryit("samePage:payroll:old form", async () => {
    fresh(); await open("payroll"); NET.delay = (p, m) => m !== "GET" ? 500 : 1000;
    go("audit"); await settle(now + 10); go("payroll"); await settle(now + 10);
    NET.reply = (p, m) => m !== "GET" ? [200, { chosen: null }] : undefined; NET.afterWrite = "500";
    AGAIN.payroll.act(); await settle();
    return outcome("payroll");
  });
  // ... and a check's chip left on it is not followed then
  await tryit("samePage:payroll:old chip", async () => {
    fresh(); const m = main(), chips = [{ dataset: { pcShow: "1" } }]; m.querySelectorAll = s => s === "[data-pc-show]" ? chips : [];
    await open("payroll"); const old = chips[0].onclick;
    NET.delay = p => p.startsWith("/api/payroll-check") ? 1000 : p.startsWith("/api/audit-readiness") ? 600 : 0;
    NET.fail = p => p.includes("check=") ? "500" : null;
    go("audit"); await settle(now + 10); go("payroll"); await settle(now + 10);
    if (old) old(); await settle(); m.querySelectorAll = () => [];
    return { bound: !!old, filled: filled("payroll"), loading: main().classList.contains("loading"), toasts: toasts().length, read: NET.reads.some(p => p.includes("check=")) };
  });

  /* ---- a result is never lost into a page about to be replaced by a reading of it asked for since ---- */
  const lostCase = async (name, page, reply, act, { write = 0, read = 0, then = () => go(page), status = 200 } = {}) => tryit(`result:${name}`, async () => {
    fresh(); await open(page);
    NET.reply = (p, m) => m !== "GET" ? [status, reply] : undefined; NET.delay = (p, m) => m !== "GET" ? write : read;
    toasts().length = 0; act(); await settle(now + 100); then(); await settle();
    return { said: said() };
  });
  const AUDITOR = { url: "/api/auditor-export/file?x=1", files: 3, left_out: 0, name: "package.zip" };
  await lostCase("the auditor package's link, the page asked for again while it is read back", "audit", AUDITOR, () => click({ id: "auditorPack" }), { read: 800 });
  await lostCase("the auditor package refused, the page asked for again while it is built", "audit", { error: "A made-up reason it can't be built." }, () => click({ id: "auditorPack" }), { write: 500, read: 1000, status: 400 });
  const CHECKED = n => ({ ok: !n, checked: 3, check_code: "x", problems: [], replay: { checked: 1, problems: [], count: n, more: 0 } });
  await lostCase("the audit trail check's result, the page asked for again while it is read back", "trail", CHECKED(1), () => click({ id: "trailCheck" }), { read: 800 });
  await lostCase("the audit trail check's result, the page asked for again while it checks", "trail", CHECKED(0), () => click({ id: "trailCheck" }), { write: 500, read: 1000 });
  await lostCase("a payroll workbook refused, the page asked for again while it is checked", "payroll", { error: "Not a payroll workbook." }, () => AGAIN.payroll.act(), { write: 500, read: 1000, status: 400 });
  await lostCase("a backup made, another page opened meanwhile", "settings", { file: "made-up-backup.zip" }, () => click({ id: "doBackup" }), { write: 900, then: () => go("audit") });
  await tryit("result:an SQL import, the page left while it is read back", async () => {
    fresh(); await open("sql"); run(sqPreview(FX.QFB)); NET.reply = (p, m) => m !== "GET" ? [200, { added: 2, linked: 1, skipped: 0 }] : undefined; NET.delay = (p, m) => m === "GET" && p.startsWith("/api/sql/") ? 800 : 0;
    toasts().length = 0; sandbox.__go = btn(); run(`sqlApply(__go)`); await settle(now + 100); go("audit"); await settle();
    return { said: said() };
  });
  await tryit("result:a backup made, still on its page", async () => {
    fresh(); await open("settings"); NET.reply = (p, m) => m !== "GET" ? [200, { file: "made-up-backup.zip" }] : undefined; toasts().length = 0;
    click({ id: "doBackup" }); await settle();
    return { written: el("setOut")?.textContent || "", toasts: toasts().length };
  });
  await tryit("result:a pair's refusal, its review left meanwhile", async () => {
    fresh(); await openRV(); run(`state.recon.rv.d.summary.pairs = [{ key: "k1", nil: true, reason: "reversal", docs: [], confirmed_at: null }]`);
    NET.reply = (p, m) => m !== "GET" ? [409, { error: "The month is locked." }] : undefined; NET.delay = (p, m) => m !== "GET" ? 900 : 0; toasts().length = 0;
    const err = { textContent: "", isConnected: true }; sandbox.__box = { checked: true, dataset: { pairTick: "k1" }, closest: () => ({ querySelector: s => /alert/.test(s) ? err : null }) };
    run(`pairTick(__box)`); await settle(now + 100); err.isConnected = false; go("audit"); await settle();
    return { said: said() };
  });

  /* ---- only the change's own dialog is closed when the page can't be read back: one opened since, with or without typing, stays ---- */
  const readsFail = () => { NET.down = "500"; };   // from now on (the newer dialog has been read)
  const newer = async (name, prep, send, openOther, check, reply = {}) => tryit(`newer:${name}`, async () => {
    fresh(); NET.extra = null; await prep(); await settle(); slowWrite(reply); toasts().length = 0; NET.writes.length = 0; send(); await settle(now + 100);
    run(`closeDrawer(true)`); run(openOther); await settle(now + 100); readsFail(); await settle();
    return { ...check(), saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });
  const other = () => ({ open: !roots.drawer.hidden, other: /Opened since/.test(roots.drawer.full()) });
  const second = () => ({ open: !roots.drawer.hidden && run(`state.openPayment`) === FX.PAY2 });
  const SINCE = `openHistory("budget_lines", ${FX.LINE}, "Opened since")`;
  const sendNew = () => { set("ap-desc", "A made-up bill"); run(`npSave()`); };
  const newPayment = async () => { await open("entity"); run(`addPaymentDrawer()`); };
  await newer("a new payment, then another payment", newPayment, sendNew, `openPayment(${FX.PAY2})`, second, { id: 999 });
  await newer("a new payment, then a second New payment", newPayment, sendNew, `addPaymentDrawer()`, () => ({ open: !roots.drawer.hidden && run(`!!state.np`) }), { id: 999 });
  await newer("a payment removed", openDialog, () => click({ id: "deletePayment", confirm: "1" }), `openPayment(${FX.PAY2})`, second, { unlinked: [], before_tracking: [], lines: 0 });
  await newer("a recurring payment deleted", async () => { await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("delete", ${FX.PAYEE}, __btn)`); },
    () => { el("su-reason").value = "A made-up reason"; el("setupWhy").hidden = false; run(`whySubmit()`); }, SINCE, other);
  await newer("a bank month reopened", async () => { await open("bank"); run(panel); run(`reopenDialog(7)`); },
    () => { set("bk-why", "A made-up reason"); sandbox.__go = { dataset: { sid: "7" }, setAttribute() {}, removeAttribute() {}, disabled: false, textContent: "" }; run(`reopenGo(__go)`); }, SINCE, other);
  await tryit("newer:a record put back", async () => {
    fresh(); await open("trail");
    NET.reply = (p, m) => p === "/api/setup/restore/5" ? [200, { label: "Bank account", name: "Spare", table: "accounts", kind: "accounts", id: 2, same_id: true, notes: [], lines: [], affected: {},
      deleted: { at: "2026-11-02T10:00:00", actor: "Made-up user", entry: 4, key: 2, reason: "Made up" } }] : undefined;
    run(`openRestore(5, "A record")`); await settle(); set("pb-why", "A made-up reason");
    slowWrite({ label: "Bank account", kind: "accounts", id: 2, same_id: true }); sandbox.__go = btn(); toasts().length = 0; NET.writes.length = 0; run(`restoreGo(5, __go)`); await settle(now + 100);
    run(`closeDrawer(true)`); run(SINCE); await settle(now + 100); readsFail(); await settle();
    return { ...other(), saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });
  // an Undo in a message is a change with no dialog of its own: the payment opened since stays
  await tryit("newer:Undo of Save details with another payment open", async () => {
    fresh(); await openDialog(); NET.reply = (p, m) => m !== "GET" ? [200, {}] : undefined; set("pf-notes", "A made-up note"); run(`paySave()`); await settle();
    const undo = toasts().find(t => t.undo)?.undo; run(`closeDrawer(true)`); run(`openPayment(${FX.PAY2})`); await settle();
    toasts().length = 0; NET.writes.length = 0; NET.afterWrite = "500"; undo(); await settle();
    return { ...second(), saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });
  // a change made on the page, then a dialog opened over it with something typed that no unsaved check watches (Explain a line)
  await tryit("newer:Confirm all matched, then Explain a line with text typed", async () => {
    fresh(); await openRV(); run(`state.recon.rv.d.lines = [{ id: 31, state: "open", txn_date: ${JSON.stringify(FX.MONTH + "-03")}, amount: -5, balance: 1, description: "Sample line", suggestions: [], vouchers: [] }]`);
    slowWrite({ confirmed: 1, needs_date_tick: 0 }); toasts().length = 0; NET.writes.length = 0; click({ rvConfirmAll: "1" }); await settle(now + 100);
    run(`explainLine(31)`); set("ex-desc", "typed while Confirm all was saving"); readsFail(); await settle();
    return { open: !roots.drawer.hidden, typed: el("ex-desc")?.value ?? null, saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });
  // Unlink is on the SQL page too: sent from there it has no dialog, so one shown while it is sent (here without any other being closed) stays
  await tryit("newer:Unlink on the SQL page, then a dialog shown over it", async () => {
    fresh(); await open("sql"); slowWrite({ doc_no: "PV-1", payment: "x" }); toasts().length = 0; NET.writes.length = 0; click({ sqlUnlink: "41" }); await settle(now + 100);
    run(`$("#drawer").innerHTML = "<h2>Shown since</h2>"; showDrawer()`); readsFail(); await settle();
    return { open: !roots.drawer.hidden, saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });
  // the payment dialog's own upload, with another file waiting for its type (or picked to replace one) by then: the dialog stays with it
  for (const [k, waits, still] of [["waiting for their type", `pdAskTypes(payOf(${FX.PAY}), [{ name: "later.pdf", size: 10 }])`, `state.pay?.pick?.length ?? 0`],
    ["picked to replace one", `state.pay.ask = { act: "replace", doc: ${FX.DOC}, file: { name: "later.pdf", size: 10 } }`, `state.pay?.ask?.file ? 1 : 0`]]) await tryit(`newer:files ${k}`, async () => {
    fresh(); await openDialog(); slowWrite({ id: 1 }); NET.afterWrite = "500"; toasts().length = 0; NET.writes.length = 0;
    run(`pdUpload([{ file: { name: "bill.pdf", size: 10 }, type: "invoice" }])`); await settle(now + 100); run(waits); await settle();
    return { open: !roots.drawer.hidden, kept: run(still), saved: said().includes(SAVED) || onPage(), writes: NET.writes.length };
  });

  // SQL Take it for: the Fetch after it refused gives the server's reason, not "could not reload"
  await tryit("takeRefused", async () => {
    fresh(); await open("sql"); toasts().length = 0; NET.writes.length = 0;
    NET.reply = (p, m) => p === "/api/sql/preview" ? [400, { error: "The SQL exports folder wasn't found." }] : m !== "GET" ? [200, {}] : undefined;
    click({ sqlTake: "Quillon Fab", confirm: "1" }); await settle();
    return { said: toasts().map(t => t.msg), card: run(`sqState().fetchErr`), shown: visible().includes("The SQL exports folder wasn't found."), writes: NET.writes.length };
  });

  /* ======== D. "nothing was changed" only when the server refused ======== */
  const REPLIES = { refused: [409, { error: "The month is filed." }], failed: [500, { error: "The server could not save it." }], unread: [200, null, "bad"] };
  await tryit("api", async () => {
    const res = {};
    for (const [k, rep] of Object.entries({ ...REPLIES, html: [403, null, "bad"], broken: "net" })) for (const method of ["GET", "POST"]) {
      fresh(); NET.reply = () => rep === "net" ? undefined : rep; if (rep === "net") NET.fail = () => "net"; if (rep === "net" && method === "POST") NET.reply = () => "net";
      res[`${k}:${method}`] = await (async () => { const p = run(`api("/api/x", ${method === "GET" ? "{}" : "{ json: {} }"}).then(d => ({ ok: d }), e => ({ message: e.message, unsure: !!e.unsure, network: !!e.network }))`); await settle(); return p; })();
    }
    return res;
  });
  for (const [k, rep] of Object.entries(REPLIES)) {
    await tryit(`D:reason:${k}`, async () => {
      fresh(); await open("payees"); run(`editPayee(${FX.PAYEE})`); await settle(); run(`payeeAct("stop", ${FX.PAYEE}, __btn)`); NET.reply = (p, m) => m !== "GET" ? rep : undefined; await why(); await settle();
      return { text: el("su-why-msg").innerHTML };
    });
    await tryit(`D:payment:${k}`, async () => {
      fresh(); await openDialog(); NET.reply = (p, m) => m !== "GET" ? rep : undefined; set("pf-notes", "A made-up note"); run(`paySave()`); await settle();
      return { text: el("pd-refused-box")?.innerHTML || "" };
    });
    await tryit(`D:newPayment:${k}`, async () => {
      fresh(); await open("entity"); run(`addPaymentDrawer()`); await settle(); NET.reply = (p, m) => m !== "GET" ? rep : undefined; set("ap-desc", "A made-up bill"); run(`npSave()`); await settle();
      return { text: (el("np-refused")?.innerHTML || "") + (el("np-foot")?.textContent || "") };
    });
    await tryit(`D:payroll:${k}`, async () => {
      fresh(); await open("payroll"); NET.reply = (p, m) => m !== "GET" ? rep : undefined; el("pcFile").files = [{ name: "payroll.xlsx" }]; el("pcForm").onsubmit({ preventDefault() {} }); await settle();
      return { text: el("pcRefused")?.innerHTML || "" };
    });
    await tryit(`D:pack:${k}`, async () => {
      fresh(); await open("audit"); NET.reply = (p, m) => m !== "GET" ? rep : undefined; click({ id: "buildPack" }); await settle();
      return { text: (el("packOut")?.textContent || "") + toasts().map(t => t.msg).join(" ") };
    });
    await tryit(`D:bulk:${k}`, async () => {
      fresh(); await open("entity"); NET.reply = (p, m) => m !== "GET" ? rep : undefined; NET.afterWrite = "500"; run(`regState().picked = [${FX.PAY}]; regPaint()`); set("regBulkDate", FX.MONTH + "-05"); run(`regBulk("date")`); await settle();
      return { text: said() };
    });
  }

  await settle(); await turn();
  out.unheard = unheard;
  process.stdout.write("@@OUT " + JSON.stringify(out) + "\n");
  process.exit(0);
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps(FX), encoding="utf-8")
names = re.findall(r'<script src="/static/(js/[^"]+)"></script>', (STATIC / "index.html").read_text(encoding="utf-8"))
files = [str(STATIC / n) for n in names if not n.endswith("main.js")]

proc = subprocess.Popen([shutil.which("node"), str(probe), str(fx_path), *files], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
errors = []
reader = threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)
reader.start()
watchdog = threading.Timer(480, proc.kill)
watchdog.start()
o = None
try:
    for line in proc.stdout:
        if line.startswith("@@REQ "):
            req = json.loads(line[6:])
            r = client.get(BASE + req["path"], headers=H)
            proc.stdin.write(json.dumps({"id": req["id"], "status": r.status_code, "body": r.get_json(silent=True) or {}}) + "\n")
            proc.stdin.flush()
        elif line.startswith("@@OUT "):
            o = json.loads(line[6:])
    proc.wait(timeout=30)
finally:
    watchdog.cancel()
    if proc.poll() is None:
        proc.kill()
reader.join(timeout=5)
check("the page's script ran on the stand-in page, reading the real server's answers", o is not None, "".join(errors)[-1500:])


def ran(name):
    r = o.get(name)
    if not isinstance(r, (dict, list)) or (isinstance(r, dict) and "crashed" in r):
        check(f"{name}: the case ran", False, r)
        return None
    return r


# ---------- A ----------
a = ran("A")
if a is not None:
    for p, r in a.items():
        bad = [c for c in r["cases"] if not (c["same"] and c["filled"] and not c["skeleton"] and not c["loading"])]
        check(f"A: {p}: with every read delayed 300 ms, 900 ms and 1.5 s, on arrival, a company switch and a month change, the page ends as with no delay (never left on Loading)",
              r["filledAtOnce"] and len(r["cases"]) >= 6 and not bad, bad[:3] or r)
        if p in ("bank", "books", "parties", "statutory") or p.startswith("setup:"):
            covered = [c for c in r["cases"] if c["mid"]["frame"] is True and c["mid"]["skeleton"]]
            # the page's own frame is there 0.3 s in: Setup's comes once the section list is read, which is kept after the first time
            lost = [c for c in r["cases"] if not (c["mid"]["frame"] and not c["mid"]["skeleton"])]
            check(f"A: {p}: the frame it wrote is still on show once the skeleton is due, never covered by it", not covered and not lost, (covered or lost)[:3])
sk = ran("Askeleton")
if sk is not None:
    check("A: a page that has written nothing still gets the skeleton after 0.3 s (not before)", all(v == {"early": False, "late": True} for v in sk.values()), sk)
back = ran("Aback")
if back is not None:
    check("A: back to a page while the one left for is still read: it is dimmed, the frame of the page left gives way to the skeleton, and it ends whole",
          back == {"frame": True, "dim": True, "left": False, "covered": True, "same": True, "loading": False}, back)


# ---------- B ----------
def untouched(name, r):
    asked = [x for x in r if not x.get("skipped")]
    wrong = [x for x in asked if x["changed"]]
    check(name, bool(asked) and not wrong, wrong[:2] or r)


for key, r in o.items():
    if not key.startswith("B:"):
        continue
    _, page, *rest = key.split(":") if not key.startswith("B:setup:") else ["B", ":".join(key.split(":")[1:3]), *key.split(":")[3:]]
    where, how = rest
    r = ran(key)
    if r is not None:
        untouched(f"B: {page}: each of its reads, slow and {'failing' if how == 'fail' else 'answered'}, coming back after {'the same page of another company' if where == 'company' else 'another page'} was opened, changes nothing there", r)
for key in [k for k in o if k.startswith("P:")]:
    name = key[2:]
    r = ran(key)
    if r is not None:
        part, how = name.rsplit(":", 1)
        check(f"B: {part} ({'the slow read fails' if how == 'fail' else 'the slow read answers'}): the one asked for first changes nothing when it comes", r["asked"] and not r["changed"], r["changed"] or r)
r = ran("chip")
if r is not None:
    check("B: a payroll check chip clicked on the old page while the next page is read doesn't draw the payroll check over it", r["bound"] and r["audit"] and not r["changed"], r)
r = ran("chipCompany")
if r is not None:
    check("B: nor does one clicked while the same page of another company is read: that company's payroll check is drawn", r == {"bound": True, "mbs": True, "toasts": 0, "loading": False}, r)
for kind in ("checklist", "reminders"):
    r = ran(f"preview:{kind}")
    if r is not None:
        check(f"B: a {kind} preview that answers after another record's dialog was opened writes nothing into it", r == {"sent": 1, "changed": []}, r)
r = ran("newDay")
if r is not None:
    check("B: a page held up while the day's first month set-up runs draws nothing over the page asked for after it, and reads nothing", r == {"held": True, "changed": [], "read": [], "audit": True}, r)
r = ran("unused")
if r is not None:
    check("B: the card of a page the company doesn't use stays when the slow page before it comes back", r == {"changed": [], "card": True}, r)
for where in ("company", "page"):
    for how in ("answer", "fail"):
        r = ran(f"fetch:{where}:{how}")
        if r is not None:
            kept = None if where == "company" or how == "fail" else QFB
            check(f"B: SQL Fetch {'failing' if how == 'fail' else 'answered'} after {'another company' + chr(39) + 's SQL page' if where == 'company' else 'another page'} was opened paints nothing there, leaves nothing reading"
                  + ("" if kept is None else ", and its preview is there when you come back"), r["changed"] == [] and r["reading"] is None and (kept is None or r["preview"] == kept), r)

# ---------- B: dialogs ----------
for how in ("answer", "fail"):
    r = ran(f"lastAsked:{how}")
    if r is not None:
        check(f"B: two dialogs asked for, both read first, the first {'answering' if how == 'answer' else 'failing'} before the second: the one asked for last is shown, and nothing is said of the first",
              all(r[k] == {"open": True, "shows": r["want"][k], "toasts": 0} for k in ("recurring", "setup")), r)
r = ran("otherDialog:saveRefused")
if r is not None:
    check("B: a payment's Save refused after its dialog was closed and another payment opened writes nothing into that one, and is said in a message with the payment's name",
          r["open"] and r["notes"] == "typed in the second" and r["unsaved"] == "pf-notes" and not r["refused"].strip() and any(m.endswith(": The month is filed.") for m in r["msgs"]), r)
for k, what in (("saveKept", "kept"), ("saveNotRead", "kept, then not read back,")):
    r = ran(f"otherDialog:{k}")
    if r is not None:
        check(f"B: a payment's Save {what} after another payment was opened leaves that one open with what is typed in it, still counted as unsaved against its own figures",
              r["open"] and r["notes"] == "typed in the second" and r["unsaved"] == "pf-notes" and (k == "saveKept" or "It was saved, but this page could not reload. Try again." in r["msgs"]), r)
r = ran("otherDialog:addRefused")
if r is not None:
    check("B: a new payment refused after its dialog was closed and another opened writes nothing into that one, and is said in a message",
          r["open"] and r["desc"] == "A second made-up bill" and not r["refused"].strip() and "A made-up bill: The month is filed." in r["msgs"], r)
r = ran("otherDialog:addKept")
if r is not None:
    check("B: a new payment added after another New payment was opened doesn't close it: what is typed there stays", r["open"] and r["desc"] == "A second made-up bill", r)
r = ran("otherDialog:upload")
if r is not None:
    check("B: a file's upload answered after New payment was opened, with the page then not read back, leaves New payment open, and says the file was saved", r == {"open": True, "writes": 1, "said": True}, r)
r = ran("otherDialog:removed")
if r is not None:
    check("B: a payment removed after another payment was opened doesn't close that one", r["open"], r)
r = ran("otherDialog:recurringSaved")
if r is not None:
    check("B: a recurring payment saved after another one's dialog was opened leaves that dialog, and what is typed in it, alone (the saved one is not opened over it)",
          r["open"] and r["name"] == r["want"] and r["notes"] == "typed in the second", r)
r = ran("otherDialog:recurringDeleted")
if r is not None:
    check("B: a recurring payment deleted after another one's dialog was opened doesn't close that one", r["open"] and r["name"] == r["want"], r)
r = ran("otherDialog:stopRefused")
if r is not None:
    check("B: a stop refused after its dialog was closed is said in a message: the next dialog's reason box keeps its reason and gets no message",
          r == {"box": "", "reason": "typed for the second", "said": True}, r)
for k, what in (("reopened", "a bank month reopened"), ("putBack", "a record put back")):
    r = ran(f"otherDialog:{k}")
    if r is not None:
        check(f"B: {what} after another dialog was opened doesn't close it", r == {"open": True, "other": True}, r)
r = ran("filedElsewhere")
if r is not None:
    check("B: Mark as filed, left for another page while the month is looked at, asks nothing over that page and files nothing", r == {"asked": 0, "writes": 0}, r)
r = ran("addCompanyElsewhere")
if r is not None:
    check("B: Add company, left for another page while Setup is read, opens no form over that page", r == {"asked": True, "dialog": False, "audit": True}, r)
r = ran("routes")
if r is not None:
    check("B: every page in the table of pages that reads anything is one these checks go through (a new page has to be added to PAGES)", len(r["all"]) > 15 and r["missed"] == [], r["missed"] or r)

# ---------- C ----------
flows = [k for k in o if k.startswith("C:")]
check("C: every action that changes something and then reads back was tried", len({k.rsplit(":", 1)[0] for k in flows}) >= 64, len(flows))
for key in flows:
    name, how = key[2:].rsplit(":", 1)
    r = ran(key)
    if r is None:
        continue
    what = f"C: {name}, then {'the app stops' if how == 'net' else 'the re-read fails'}"
    part_ok = r["tried"] is not None
    good = (r["writes"] == 1 and not r["others"] and r["readsFailed"] > 0 and r["saved"] and r["never"] is None and r["savedToasts"] <= 1 and r["cards"] <= 1)
    check(f"{what}: it is sent once and said to be saved, once, never that nothing was changed", good, r)
    if r["kept"] is not None:
        check(f"{what}: what the action found or said is still said", r["kept"] is True, r["said"])
    check(f"{what}: Try again only reads again, whether it fails again or works (nothing is sent again)",
          part_ok and r["again"]["writes"] == 1 and not r["again"]["others"] and r["again"]["reads"] > 0 and r["again"]["saved"] and r["again"]["never"] is None
          and r["triedOk"] is not None and r["ok"]["writes"] == 1 and not r["ok"]["others"] and r["ok"]["reads"] > 0 and r["ok"]["newSaved"] == 0 and not r["ok"]["onPage"], r)
for name, want in (("bank review: Apply selected", {"sel": 0}), ("SQL page: Import", {"done": "Imported 2 entries"})):
    r = ran(f"C:{name}:500")
    if r is not None:
        if "sel" in want:
            check(f"C: {name}: after the failed re-read nothing stays ticked, so Apply can't send it again", r["after"] == want, r["after"])
        else:
            check(f"C: {name}: the import's result is on the page once Try again has read it (it is not lost with the failed reading)", r["triedOk"] is not None and r["after"] == want and r["ok"]["after"] == want, [r["triedOk"], r["after"], r["ok"]["after"]])
for name in ("payment dialog: Save details", "payment dialog: an SQL voucher unlinked", "payment dialog: a document uploaded", "payment dialog: a document removed", "Recurring: add a payment", "Recurring: save a payment", "Recurring: delete",
             "Recurring: stop using", "Recurring: add an advance", "Recurring: save an advance", "Recurring: remove an advance"):
    r = ran(f"C:{name}:500")
    if r is not None:
        check(f"C: {name}: with nothing else typed, the dialog is closed when the page can't be read back (its words are on the page, not behind a stale dialog)", r["dialog"] == "closed", r["drawer"])
r = ran("tryAgainElsewhere")
if r is not None:
    check("C: a part's Try again pressed after another page was opened reads that page again, and never draws the part over it", r == {"had": True, "audit": True, "payroll": False, "sent": 0}, r)
r = ran("otherCompanyPart")
if r is not None:
    check("C: a part's change answered while the same page of another company is read, with its re-read failing: that page is not left blank or on Loading, and it says the change was saved",
          all(x == {"company": True, "filled": True, "loading": False, "saved": True} for x in r.values()), r)
r = ran("lateWrite")
if r is not None:
    check("C: a change answered after another page was opened leaves that page alone: a refusal and a kept result are said in a message",
          r["refused"] == {"same": True, "toast": True} and r["kept"] == {"audit": True, "payroll": False, "toast": True}, r)
r = ran("addTwice")
if r is not None:
    check("C: a recurring payment's Add left open (typed in while the list was read) refuses a second Add", r == {"open": True, "writes": 1, "toast": True, "said": 1}, r)
r = ran("advanceTwice")
if r is not None:
    check("C: an advance added with the dialog left open (other typing kept) leaves its boxes empty, so Add can't send it again",
          r == {"open": True, "amt": "", "notes": "typed and not saved", "writes": 1}, r)
r = ran("savingStuck")
if r is not None:
    check("C: the payment dialog's Save, kept but not read back, leaves no dialog saying Saving…", r == {"hidden": True, "open": None, "saving": False}, r)

r = ran("savedOnce")
if r is not None:
    check("C: \"it was saved\" is said only of the reading back of that change: a report that fails later says its own reason", r == {"books": False, "reason": True, "einvoices": False}, r)
r = ran("typedUpload")
if r is not None:
    check("C: a file added while something is typed in the payment dialog: the dialog stays with what was typed, and a message says it was saved (the page's words are behind the dialog)",
          r == {"open": True, "notes": "typed and not saved", "said": 1, "writes": 1}, r)

# ---------- C: changes with no answer, the same page asked for again, results and dialogs ----------
NOTHING_SAID = re.compile(r"Nothing was changed|Nothing was kept|Nothing you typed since then was sent or saved|Nothing was added|Nothing was saved")
unanswered = [k for k in o if k.startswith("unanswered:")]
check("C: every bulk action and upload that got no answer was tried", len(unanswered) == 8, unanswered)
for key in unanswered:
    _, name, how = key.split(":")
    r = ran(key)
    if r is None:
        continue
    texts = [r["first"], r["again"]]
    never = [m.group(0) for m in (NOTHING_SAID.search(t) for t in texts + [r["said"]]) if m]
    if how == "net":
        ok = (r["pressed"] and not never and "Failed to fetch" not in r["first"] + r["again"] + r["said"] and (name.startswith("the payment dialog") or "The connection to HR Payments broke." in r["said"])
              and all("HR Payments isn't running" in t and "Start HR Payments.bat" in t and "isn't known whether your last change was saved" in t for t in texts))
        check(f"C: {name} with the app stopped: the page says it isn't running, with the steps to start it, and that it isn't known whether the change was saved (also after Try again), never in the browser's own words", ok, r)
    else:
        check(f"C: {name} with the server failing: neither the page nor its Try again says that nothing was changed", r["pressed"] and not never and all("Couldn't load this page" in t for t in texts), r)
for key in [k for k in o if k.startswith("samePage:") and not k.endswith("old chip")]:
    _, page, how = key.split(":")
    r = ran(key)
    if r is not None:
        check(f"C: {page}: a change answered while that page is asked for again ({how}), its re-read failing, leaves it neither blank nor on Loading, and says the change was saved",
              r == {"filled": True, "loading": False, "saved": True}, r)
r = ran("samePage:payroll:old chip")
if r is not None:
    check("B: a payroll check chip left on show while the same page is asked for again isn't followed, so it can't take that page's draw",
          r == {"bound": True, "filled": True, "loading": False, "toasts": 0, "read": False}, r)
for name, words in (("the auditor package's link, the page asked for again while it is read back", "package.zip"), ("the auditor package refused, the page asked for again while it is built", "A made-up reason it can't be built."),
                    ("the audit trail check's result, the page asked for again while it is read back", "found problems"), ("the audit trail check's result, the page asked for again while it checks", "3 entries check out"),
                    ("a payroll workbook refused, the page asked for again while it is checked", "Not a payroll workbook."), ("a backup made, another page opened meanwhile", "made-up-backup.zip"),
                    ("a pair's refusal, its review left meanwhile", "The month is locked."), ("an SQL import, the page left while it is read back", "Imported 2 entries")):
    r = ran(f"result:{name}")
    if r is not None:
        check(f"C: {name}: it is still said", words in r["said"].replace("&#39;", "'"), r["said"][-900:])
r = ran("result:a backup made, still on its page")
if r is not None:
    check("C: a backup made while its page stays is written under the buttons, with no message", r == {"written": "Saved made-up-backup.zip", "toasts": 0}, r)
newer = [k for k in o if k.startswith("newer:") and not k.startswith("newer:files ")]
check("C: every case of a dialog opened since was tried", len(newer) == 9, newer)
for key in newer:
    r = ran(key)
    if r is None:
        continue
    kept = {k: v for k, v in r.items() if k not in ("saved", "writes")}
    want = {"open": True, "typed": "typed while Confirm all was saving"} if "Explain" in key else {k: True for k in kept}
    check(f"C: {key[6:]}, then the page not read back: the dialog opened since stays (with what is typed in it), and the change is said to be saved, sent once",
          bool(kept) and kept == want and r["saved"] and r["writes"] == 1, r)
for k in ("waiting for their type", "picked to replace one"):
    r = ran(f"newer:files {k}")
    if r is not None:
        check(f"C: the payment dialog's upload, not read back, with a file {k} by then: the dialog stays, and the file with it", r == {"open": True, "kept": 1, "saved": True, "writes": 1}, r)
r = ran("takeRefused")
if r is not None:
    check("C: SQL Take it for, with the Fetch after it refused: the server's reason is said, with that the name was kept (never that the page could not reload), and is in the Fetch card",
          r["said"] and r["said"][-1] == "The name was kept, but the exports weren't fetched: The SQL exports folder wasn't found." and "It was saved, but this page could not reload. Try again." not in r["said"]
          and r["card"] == "The SQL exports folder wasn't found." and r["shown"] and r["writes"] == 1, r)

# ---------- D ----------
r = ran("xhr")
if r is not None:
    unread = {"message": "HR Payments gave an answer this page can't read.", "unsure": True}
    check("D: the payment dialog's upload (with its progress bar) takes a 200 that isn't JSON, or is empty, for an error, never for a file added; a refusal is sure, a server failure and a broken connection aren't",
          r == {"ok": {"ok": {"id": 3}}, "html": unread, "empty": unread, "refused": {"message": "Not accepted.", "unsure": False}, "failed": {"message": "Something went wrong (500).", "unsure": True}, "net": {"message": "network", "unsure": True}}, r)
api = ran("api")
if api is not None:
    for method, write in (("GET", False), ("POST", True)):
        check(f"D: api() {method}: a 200 that isn't JSON is an error, never an empty answer" + (", and it isn't known whether the change was made" if write else ""),
              api[f"unread:{method}"] == {"message": "HR Payments gave an answer this page can't read.", "unsure": write, "network": False}, api[f"unread:{method}"])
        check(f"D: api() {method}: a refusal (409, or a 403 page) is sure; a server failure" + (" isn't" if write else " of a read changes nothing"),
              api[f"refused:{method}"] == {"message": "The month is filed.", "unsure": False, "network": False} and api[f"html:{method}"] == {"message": "Something went wrong (403).", "unsure": False, "network": False}
              and api[f"failed:{method}"] == {"message": "The server could not save it.", "unsure": write, "network": False}, [api[f"{k}:{method}"] for k in ("refused", "html", "failed")])
        check(f"D: api() {method}: the app not reached is marked a network failure" + (", and it isn't known whether the change was made" if write else ""),
              api[f"broken:{method}"] == {"message": "Failed to fetch", "unsure": write, "network": True}, api[f"broken:{method}"])
NOTHING = {"reason": "Nothing was changed.", "payment": "Nothing was saved", "newPayment": "Nothing was added", "payroll": "Nothing was kept", "pack": "The pack wasn't built", "bulk": "not set on"}
UNKNOWN = ("isn't known", "isn&#39;t known")
for place, words in NOTHING.items():
    label = {"reason": "the reason box (stop using)", "payment": "the payment dialog's Save", "newPayment": "New payment", "payroll": "the payroll check", "pack": "building the audit pack", "bulk": "the register's bulk Set paid date"}[place]
    for kind in ("refused", "failed", "unread"):
        r = ran(f"D:{place}:{kind}")
        if r is None:
            continue
        text = r["text"].replace("&#39;", "'")
        if kind == "refused":
            check(f"D: {label}: a refusal says so ({words!r}), with the server's reason", words in text and "The month is filed." in text and "isn't known" not in text, text[:700])
        else:
            check(f"D: {label}: a {'server failure' if kind == 'failed' else '200 that cannot be read'} never says {words!r}; it says it isn't known", words not in text and "isn't known" in text, text[:700])

check("no read or change in any case above failed without somebody waiting for it", o.get("unheard") == [], o.get("unheard"))

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
