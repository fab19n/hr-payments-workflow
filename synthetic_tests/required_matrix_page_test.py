"""The Required documents grid's page (slice 9c), on made-up records: the page script runs in Node on a small tree-shaped stand-in for the
page (no browser), and every request is answered by the real server, so what is saved is checked in the records.

Checks: the grid (document types across, payment types down, the sources, every box a labelled button, names shown as they are written);
clicking boxes, the Changed, not saved yet marks and what saving would do; one Save for every changed type, with its reason, and nothing
else written; a refused save keeping the boxes and the reason, a save with no clear answer, and a saved one that can't be read back;
every way off the page asking Discard your changes?, and the two pickers never carrying boxes over; the page read again keeping them;
one company, its documents from SQL Account greyed while it is Kept here, Follow all companies again; the warnings (later sets replaced,
documents no longer in use, types that need what Other needs, companies with their own set); the earlier sets; the arrow keys; one save
at a time; and the sideways scroll with the type names held.

Run: .venv\\Scripts\\python -m synthetic_tests.required_matrix_page_test
"""
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-required-page-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_files  # noqa: E402
from synthetic_tests.flags import KEEP_GOING  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}]},
    {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed, failed = [], []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:900]}" if detail else ""))
        if not KEEP_GOING:
            sys.exit(1)
        failed.append(name)
        return
    passed.append(name)
    print(f"PASS {name}")


db.init()
client = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


EXA, EXB = [r["id"] for r in q("SELECT id FROM entities ORDER BY id")]
M0 = db.current_cycle()
M1, M2, M3 = db.shift_month(M0, 1), db.shift_month(M0, 2), db.shift_month(M0, 3)
for e in (EXA, EXB):
    for m in (M0, M1):
        call("post", "/api/months/open", json={"entity_id": e, "month": m})
# names with markup in them: the person's own text
ODD_TYPE, ODD_DOC = 'Tap <img src=x onerror=1> "water" & co', 'Memo <b>bold</b> & "q"'
call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_memo", "label": ODD_DOC, "singular": "memo", "plural": "memos"}})
call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_odd", "label": ODD_TYPE, "direction": "out"}})
old_type = call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_old", "label": "Test old kind", "direction": "out"}})
call("post", f"/api/setup/payment_types/{old_type['id']}/stop", json={"reason": "Not used now"})
# two paid utility payments with their invoice and bank receipt but no voucher: unticking the voucher would complete them
for n in (1, 2):
    pid = call("post", "/api/payments", json={"entity_id": EXA, "month": M0, "description": f"Test utility {n}", "category": "utility", "amount": 10})["id"]
    for d in ("invoice", "bank"):
        call("post", "/api/upload", data={"payment_id": str(pid), "doc_type": d, "file": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), f"{d}.pdf")})
    call("patch", f"/api/payments/{pid}", json={"paid_date": f"{M0}-05"})

PROBE = r"""
const fs = require("fs"), vm = require("vm"), readline = require("readline");
const [fxPath, ...files] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const unheard = [];
process.on("unhandledRejection", e => unheard.push(String(e && e.stack || e).slice(0, 300)));

/* ---- the pipe to the real server ---- */
const waiting = new Map(); let askN = 0;
readline.createInterface({ input: process.stdin }).on("line", l => { const m = JSON.parse(l); const f = waiting.get(m.id); waiting.delete(m.id); f(m); });
const server = (method, path, body) => new Promise(res => { const id = ++askN; waiting.set(id, res); process.stdout.write("@@REQ " + JSON.stringify({ id, method, path, body }) + "\n"); });
// NET.delay(method, path, body): ms before the answer; NET.fail(...): "net" (never reaches the server), "lost" (done, the answer lost)
const NET = { delay: () => 0, fail: () => null, sent: [] };
async function fetch(path, init = {}) {
  const method = init.method || "GET", body = init.body ? JSON.parse(init.body) : null;
  NET.sent.push([method, path, body]);
  const how = NET.fail(method, path, body), ms = NET.delay(method, path, body);
  const wait = ms ? sleep(ms) : null;
  if (how === "net") { await wait; throw new TypeError("Failed to fetch"); }
  const r = await server(method, path, body);
  await wait;
  if (how === "lost") throw new TypeError("Failed to fetch");
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
}

/* ---- the stand-in page: a tree built from the markup written into it ---- */
const unesc = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
function matchOne(n, sel) {
  const m = /^([a-z0-9]*)((?:\[[^\]]+\]|\.[\w-]+|#[\w-]+)*)(?::not\(([^)]*)\))?$/.exec(sel);
  if (!m) return false;
  if (m[1] && n.tagName.toLowerCase() !== m[1]) return false;
  for (const [, part] of m[2].matchAll(/(\[[^\]]+\]|\.[\w-]+|#[\w-]+)/g)) {
    if (part[0] === ".") { if (!n.classList.contains(part.slice(1))) return false; }
    else if (part[0] === "#") { if (n.id !== part.slice(1)) return false; }
    else { const x = /^\[([\w-]+)(?:="?([^"\]]*)"?)?\]$/.exec(part); if (!x || !n.hasAttribute(x[1]) || (x[2] !== undefined && n.getAttribute(x[1]) !== x[2])) return false; }
  }
  return !(m[3] && matchOne(n, m[3]));
}
function matches(n, sel) {
  return sel.split(",").some(s => {
    const parts = s.trim().split(/\s+/);
    if (!matchOne(n, parts[parts.length - 1])) return false;
    let at = n.parent;
    for (let i = parts.length - 2; i >= 0; i--) { while (at && !matchOne(at, parts[i])) at = at.parent; if (!at) return false; at = at.parent; }
    return true;
  });
}
const listeners = new Map();
const addL = (t, type, fn, o) => { const l = listeners.get(t) || []; l.push({ type, fn, capture: o === true || !!(o && o.capture) }); listeners.set(t, l); };
class Node {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.attrs = {}; this.children = []; this.parent = null; this._html = ""; this.text = ""; this.dataset = {}; this.style = {}; this.hidden = false; this.inert = false; this.scrollTop = 0; this.value = ""; this.checked = false; this.disabled = false; this.readOnly = false; }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; } set className(v) { this.attrs.class = v; }
  get type() { return this.attrs.type || ""; }
  get classList() {
    const n = this, get = () => n.className.split(/\s+/).filter(Boolean);
    return { add: (...c) => { n.className = [...new Set([...get(), ...c])].join(" "); }, remove: (...c) => { n.className = get().filter(x => !c.includes(x)).join(" "); },
      contains: c => get().includes(c), toggle: (c, on) => { const want = on ?? !get().includes(c); want ? n.classList.add(c) : n.classList.remove(c); } };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { if (c.parent) c.remove(); c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  get firstChild() { return this.children[0] || (this.text ? this : null); }
  get firstElementChild() { return this.children[0] || null; }
  get parentNode() { return this.parent; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === body; }
  contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = n => { for (const c of n.children) { if (matches(c, sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get textContent() { return unesc(this.text) + this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.children.forEach(c => { c.parent = null; }); this.children = []; this.text = String(v).replace(/&/g, "&amp;"); this._html = this.text; }
  get innerHTML() { return this._html; }
  set innerHTML(h) { this._html = String(h); this.children.forEach(c => { c.parent = null; }); this.children = []; this.text = ""; parseInto(this, this._html); }
  insertAdjacentHTML(where, h) { parseInto(this, h); this._html += h; }
  getBoundingClientRect() { return { top: 0, height: 600 }; }
  focus() { for (let n = this; n; n = n.parent) if (n.inert) return; focused = this; }
  blur() {} scrollIntoView() {} setSelectionRange() {} after() {}
  addEventListener(type, fn, o) { addL(this, type, fn, o); } removeEventListener() {}
  click() { dispatch(this, { type: "click" }); }
}
function parseInto(root, html) {
  const stack = [root], tok = /<(\/?)([a-zA-Z0-9]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>|([^<]+)/g;
  const VOID = new Set(["use", "input", "br", "img"]), made = [];
  let m;
  while ((m = tok.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) { top.text += m[5]; continue; }
    const [, close, tag, attrs, selfClose] = m;
    if (close) { if (stack.length > 1) stack.pop(); continue; }
    const n = new Node(tag);
    for (const [, k, v] of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) { n.setAttribute(k, v === undefined ? "" : unesc(v)); if (k === "value") n.value = unesc(v); if (k === "checked") n.checked = true; if (k === "hidden") n.hidden = true; }
    top.appendChild(n); made.push(n);
    if (!selfClose && !VOID.has(tag.toLowerCase())) stack.push(n);
  }
  for (const s of made.filter(n => n.tagName === "SELECT")) { const o = s.querySelectorAll("option"); s.value = (o.find(x => x.hasAttribute("selected")) || o[0])?.value || ""; }
}
const body = new Node("body");
let focused = null;
const document = {
  body, hidden: false,
  get activeElement() { return focused && focused.isConnected ? focused : body; }, set activeElement(v) { focused = v; },
  querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s),
  getElementById: id => body.querySelector("#" + id), createElement: null,
  addEventListener(t, f, o) { addL(document, t, f, o); }, removeEventListener() {},
};
function dispatch(target, ev) {
  ev.target = target; ev.defaultPrevented = false; let stopped = false;
  ev.preventDefault = () => { ev.defaultPrevented = true; }; ev.stopPropagation = () => { stopped = true; };
  const path = []; for (let n = target; n; n = n.parent) path.push(n);
  path.push(document);
  const results = [];
  const run = (t, capture) => { for (const l of [...(listeners.get(t) || [])]) if (l.type === ev.type && l.capture === capture) results.push(l.fn(ev)); };
  for (const t of [...path].reverse()) { if (stopped) break; run(t, true); }
  for (const t of path) { if (stopped) break; run(t, false); }
  ev.done = Promise.all(results);
  return ev;
}
for (const [id, tag] of [["nav", "nav"], ["pageTitle", "div"], ["monthLabel", "span"], ["main", "main"], ["drawer", "aside"], ["toast", "div"]]) { const n = new Node(tag); n.id = id; body.appendChild(n); }
body.querySelector("#drawer").hidden = true;
// the top bar's month arrows, as static/index.html has them
for (const id of ["prevMonth", "nextMonth", "thisMonth"]) { const b = new Node("button"); b.id = id; body.appendChild(b); }

const entries = [];  // the window's history: what Back would go to
const location = { hash: "" };
const history = { state: null, replaceState(s, t, url) { this.state = s; location.hash = url; }, go(n) { entries.push(["go", n]); } };
const win = { matchMedia: () => ({ matches: true }), scrollX: 0, scrollY: 0, scrollTo() {}, addEventListener(t, f) { entries.push(["listen", t]); }, print() {}, open() {}, location, history };
const sandbox = { document, fetch, FormData: class {}, console: { ...console, error() {} }, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, window: win, navigator: {} };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);

const $ = s => body.querySelector(s);
const out = {};
const tryit = async (name, fn) => { try { out[name] = await fn(); } catch (e) { out[name] = { error: String(e && e.stack || e).slice(0, 700) }; } };
// nothing on its way, and the preview's wait over
const idle = async (ms = 380) => { await sleep(ms); for (let i = 0; i < 300; i++) { if (!waiting.size) { await sleep(25); if (!waiting.size) return; } else await sleep(20); } throw new Error("never idle"); };
const M = FX.months;
const box = (type, doc) => $("#rq-body")?.querySelector(`[data-rq-type="${type}"][data-rq-doc="${doc}"]`) || null;
const pressed = (type, doc) => box(type, doc)?.getAttribute("aria-pressed");
const info = (type, doc) => { const b = box(type, doc); return b && { pressed: b.getAttribute("aria-pressed"), changed: b.classList.contains("changed"), dot: !!b.querySelector(".rq-dot"),
  label: b.getAttribute("aria-label"), off: b.getAttribute("aria-disabled") === "true", title: b.getAttribute("title"), tag: b.tagName, type: b.getAttribute("type"), id: b.id, cls: b.className }; };
const changedBoxes = () => $("#rq-body") ? $("#rq-body").querySelectorAll("[data-rq-doc].changed").map(b => b.dataset.rqType + "." + b.dataset.rqDoc) : null;
const rowOf = type => $("#rq-body").querySelector(`[data-rq-type="${type}"][data-rq-doc]`).closest("tr");
const status = () => $("#rq-impact")?.textContent || "";
const strips = kind => ($("#rq-impact")?.querySelectorAll(".rq-strip." + kind) || []).map(x => x.textContent);
const warnings = () => ($("#rq-impact")?.querySelectorAll("li") || []).map(x => x.textContent);
const draft = () => JSON.parse(run(`JSON.stringify(state.setup.reqDraft)`));
const toasts = () => run(`__toasts.map(t => t.msg)`);
const asks = () => run(`JSON.parse(JSON.stringify(__asks))`);
const posts = () => NET.sent.filter(x => x[0] === "POST" && x[1] === "/api/setup/required" && !x[2].preview).map(x => x[2]);
const previews = () => NET.sent.filter(x => x[0] === "POST" && x[1] === "/api/setup/required" && x[2].preview).map(x => x[2]);
const reads = () => NET.sent.filter(x => x[0] === "GET" && x[1].startsWith("/api/setup/required")).map(x => x[1]);
const click = async el => { if (el.tagName === "BUTTON") el.focus(); const ev = dispatch(el, { type: "click", button: 0 }); await sleep(0); return ev; };
const tick = async (type, doc) => { await click(box(type, doc)); };
const key = async (el, k, extra = {}) => { const ev = dispatch(el, { type: "keydown", key: k, ...extra }); await sleep(0); return ev; };
const pick = async (id, value) => { const el = $("#" + id); el.value = value; el.focus(); dispatch(el, { type: "change" }); await sleep(0); };
const typeReason = async text => { const el = $("#rq-reason"); el.value = text; dispatch(el, { type: "input" }); await sleep(0); };
const submit = () => dispatch($("#reqForm"), { type: "submit" });
const answer = (...a) => run(`__answers.push(...${JSON.stringify(a)})`);
const server_view = async (entity = null, month = M[0]) => (await server("GET", `/api/setup/required?entity=${entity ?? ""}&month=${month}`, null)).body;
const held = async (type, entity = null, month = M[0]) => (await server_view(entity, month)).types.find(t => t.key === type).at;
const single = async (payment_type, docs, entity_id = null, from_month = M[0]) => (await server("POST", "/api/setup/required", { payment_type, docs, entity_id, from_month })).status;
const quiet = () => { NET.delay = () => 0; NET.fail = () => null; };
const calm = () => { quiet(); run(`__toasts.length = 0; __asks.length = 0; __answers.length = 0;`); NET.sent.length = 0; };
// the grid on show, as the menu opens it, with nothing waiting
async function open() {
  quiet(); run(`rqLeft(); state.setup.reqScope = null;`);
  await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: ${JSON.stringify(M[0])}, sub: "required", id: null, params: {} }, { fresh: true })`);
  await idle(60); calm(); focused = null;
}
const here = () => ({ view: run(`state.view`), kind: run(`state.setup.kind`), grid: !!$("#rq-body") });

(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));
  const meta = (await server("GET", "/api/meta", null)).body;
  run(`state.meta = ${JSON.stringify(meta)}; state.month = ${JSON.stringify(M[0])}; state.day = dayKey(); state.entity = ${FX.EXA}; menuNextEnsure = () => {};
    globalThis.__toasts = []; { const was = toastShow; toastShow = (msg, bad, opts) => { __toasts.push({ msg: String(msg), bad: !!bad, opts }); return was(msg, bad, opts); }; }
    globalThis.__asks = []; globalThis.__answers = []; ask = (message, o) => { __asks.push({ message, title: o?.title, yes: o?.yes, no: o?.no }); const a = __answers.shift(); return Promise.resolve(a ?? false); };
    for (const v of ["viewOverview"]) globalThis[v] = async main => { main.innerHTML = "<div id='ov'>Overview page</div>"; }; trailNotice = () => {};`);

  /* ======== the grid ======== */
  await tryit("drawn", async () => {
    await open();
    const heads = $("#setupMain").querySelectorAll("thead th").map(t => t.textContent);
    const docHeads = $("#setupMain").querySelectorAll("th.rq-doc").map(t => ({ title: t.getAttribute("title"), text: t.textContent, src: t.querySelectorAll(".rq-src").map(x => x.textContent) }));
    const rowNames = $("#rq-body").querySelectorAll("th.rq-type").map(t => t.querySelector(".rq-name").textContent);
    const boxes = $("#rq-body").querySelectorAll("[data-rq-doc]");
    const view = await server_view();
    const mismatch = [];
    for (const b of boxes) { const t = view.types.find(x => x.key === b.dataset.rqType); if ((b.getAttribute("aria-pressed") === "true") !== t.at.docs.includes(b.dataset.rqDoc)) mismatch.push(b.dataset.rqType + "." + b.dataset.rqDoc); }
    const scope = $("#rq-scope"), month = $("#rq-month");
    return { heads, docHeads, rowNames, boxes: boxes.length, ids: new Set(boxes.map(b => b.id)).size, mismatch,
      labelled: boxes.every(b => b.tagName === "BUTTON" && b.getAttribute("type") === "button" && !!b.getAttribute("aria-label") && !b.hasAttribute("tabindex")),
      activeDocs: view.doc_types.filter(d => d.active).map(d => d.label), activeTypes: view.types.filter(t => t.active).map(t => t.label), stoppedTypes: view.types.filter(t => !t.active).map(t => t.label),
      utility: [info("utility", "invoice"), info("utility", "tst_memo")], approval: [info("salary", "approval") || info("other", "approval"), info("claim", "approval")],
      rowHeads: $("#rq-body").querySelectorAll("th.rq-type").every(t => t.getAttribute("scope") === "row"),
      scope: scope.querySelectorAll("option").map(o => o.textContent), scopeValue: scope.value, month: month.value, months: month.querySelectorAll("option").map(o => [o.value, o.textContent, o.hasAttribute("disabled")]),
      save: $("#rq-save").textContent, discard: $("#rq-discard").disabled, reason: [$("#rq-reason").value, $("#rq-reason").getAttribute("maxlength")], note: $("#rq-month-note").textContent,
      live: $("#rq-impact").getAttribute("role"), status: status(), html: $("#setupMain").innerHTML, since: rowOf("utility").querySelector(".rq-since").textContent,
      follower: rowOf("tst_odd").querySelector(".rq-since").textContent, count: rowOf("utility").querySelector(".rq-n").textContent, reads: reads().length };
  });

  /* ======== clicking boxes ======== */
  await tryit("clicks", async () => {
    const r = {};
    await open();
    const before = info("utility", "pv");
    await tick("utility", "pv"); r.at0 = { box: info("utility", "pv"), status: status(), discard: $("#rq-discard").disabled, focus: document.activeElement.id, count: rowOf("utility").querySelector(".rq-n").textContent, changed: changedBoxes() };
    await idle();
    r.previewed = { status: status(), sent: previews(), posts: posts().length };
    await tick("utility", "pv"); await idle();
    r.back = { box: info("utility", "pv"), status: status(), discard: $("#rq-discard").disabled, draft: draft(), changed: changedBoxes(), previews: previews().length };
    await tick("utility", "pv"); await tick("utility", "tst_memo"); await tick("salary", "invoice"); await idle();
    r.three = { status: status(), changed: changedBoxes().sort(), previews: previews().slice(-1)[0], count: previews().length };
    await click($("#rq-discard")); await idle();
    r.discarded = { changed: changedBoxes(), draft: draft(), status: status(), asks: asks().length, posts: posts().length, focus: document.activeElement.id, box: info("utility", "pv").pressed };
    // a preview answered after the boxes changed again says nothing of the older boxes
    calm();
    let n = 0; NET.delay = (m, p, b) => b && b.preview ? (++n === 1 ? 700 : 0) : 0;
    await tick("utility", "pv"); await sleep(340); await tick("utility", "invoice"); await sleep(10);
    r.working = status();
    await idle(800); r.late = { status: status(), n }; quiet();
    // ... also one that comes while the newer boxes' preview is still waiting to be asked
    await click($("#rq-discard")); await idle(); calm();
    NET.delay = (m, p, b) => b && b.preview && b.changes[0].payment_type === "utility" && b.changes.length === 1 ? 450 : 0;
    await tick("utility", "pv"); await sleep(600); await tick("salary", "invoice"); await sleep(220);
    r.betweenLate = status(); await idle(); r.betweenEnd = status(); quiet();
    return { before, ...r };
  });

  /* ======== one save for every changed type ======== */
  await tryit("save", async () => {
    const r = {};
    await open();
    r.setsBefore = FX.none;
    await tick("utility", "pv"); await tick("claim", "bank"); await tick("claim", "bank"); await tick("rental", "tst_memo");
    await typeReason("  Finance asked  "); await idle(); calm();
    const ev = submit(); await ev.done; await idle();
    r.sent = posts(); r.result = strips("ok"); r.changed = changedBoxes(); r.draft = draft(); r.toasts = toasts(); r.reason = $("#rq-reason").value;
    r.pv = info("utility", "pv"); r.month = $("#rq-month").value; r.saveText = $("#rq-save").textContent; r.discard = $("#rq-discard").disabled; r.msgs = strips("msg"); r.prevented = ev.defaultPrevented;
    await click($("#rq-impact").querySelector("[data-rq-dismiss]")); r.dismissed = strips("ok").length;
    NET.sent.length = 0; await submit().done; await idle(); r.nothing = { msgs: strips("msg"), posts: posts().length };
    return r;
  });

  /* ======== a refused save keeps the boxes and the reason ======== */
  await tryit("refused", async () => {
    const r = {};
    await open();
    await tick("claim", "tst_memo"); await typeReason("Memo for claims"); await idle();
    // someone else adds the e-Invoice to staff claims first
    const was = (await held("claim")).docs;
    r.other = await single("claim", [...was, "einvoice"]);
    calm(); await submit().done; await idle();
    r.after = { posts: posts().length, reads: reads().length, msgs: strips("msg"), changed: changedBoxes(), memo: info("claim", "tst_memo").pressed, einvoice: info("claim", "einvoice").pressed,
      reason: $("#rq-reason").value, draft: draft(), server: (await held("claim")).docs, toasts: toasts(), discard: $("#rq-discard").disabled, busy: $("#rq-save").getAttribute("aria-busy"), off: info("claim", "bank").off };
    // saving again keeps the other change and adds only what was ticked
    calm(); await submit().done; await idle();
    r.again = { posts: posts(), server: (await held("claim")).docs, changed: changedBoxes(), msgs: strips("msg"), result: strips("ok") };
    r.was = was;
    // the records refuse it for another reason: a document stopped while it was ticked
    await open();
    await tick("transfer", "tst_memo"); await typeReason("Keep this"); await idle();
    const memo = (await server("GET", "/api/setup/doc_types", null)).body.rows.find(x => x.key === "tst_memo");
    return r;
  });

  /* ======== a saved change that can't be read back, and a save with no clear answer ======== */
  await tryit("kept", async () => {
    const r = {};
    await open();
    await tick("rental", "approval"); await typeReason("Lease changed"); await idle(); calm();
    NET.fail = (m, p) => m === "GET" && p.startsWith("/api/setup/required") ? "net" : null;
    await submit().done; await idle();
    r.failed = { posts: posts().length, page: $("#main").innerHTML, draft: draft(), saving: run(`state.setup.reqSaving`), toasts: toasts() };
    quiet(); NET.sent.length = 0;
    await click($("#main").querySelector("[data-retry]")); await idle();
    r.retried = { posts: posts().length, grid: !!$("#rq-body"), changed: changedBoxes(), draft: draft(), asks: asks().length };
    // leaving after it asks nothing
    await run(`navigate({ view: "overview", entity: "all", month: ${JSON.stringify(M[0])}, sub: null, id: null, params: {} }, { fresh: true })`); await idle(60);
    r.left = { asks: asks().length, view: run(`state.view`) };
    // the server saves it and the answer is lost
    await open();
    await tick("rental", "approval"); await typeReason("Back again"); await idle(); calm();
    NET.fail = (m, p, b) => m === "POST" && !b.preview ? "lost" : null;
    await submit().done; await idle();
    r.lost = { msgs: strips("msg"), changed: changedBoxes(), reason: $("#rq-reason").value, all: $("#main").textContent, toasts: toasts(), posts: posts().length };
    // it never reaches the server: the boxes and the reason stay, and nothing says it was or wasn't saved
    await open();
    await tick("rental", "tst_memo"); await typeReason("Try later"); await idle(); calm();
    NET.fail = (m, p, b) => m === "POST" && !b.preview ? "net" : null;
    await submit().done; await idle();
    r.never = { msgs: strips("msg"), changed: changedBoxes(), reason: $("#rq-reason").value, all: $("#main").textContent, reads: reads().length };
    // the app has stopped: the stopped page, and the boxes are there again once it runs
    NET.fail = () => "net"; calm(); NET.fail = () => "net";
    await submit().done; await idle();
    r.stopped = { page: $("#main").innerHTML, toasts: toasts(), draft: draft() };
    quiet();
    await click($("#main").querySelector("[data-retry]")); await idle();
    r.running = { changed: changedBoxes(), reason: $("#rq-reason").value };
    return r;
  });

  /* ======== every way off the page asks first ======== */
  await tryit("leaving", async () => {
    const r = {};
    const ways = {
      sidebar: () => run(`click_({ menu: "overview" })`),
      topbarCompany: () => run(`tbPick(${JSON.stringify(String(FX.EXB))})`),
      allCompanies: () => run(`tbPick("all")`),
      addCompany: () => run(`tbAddCompany()`),
      accountMenu: () => run(`click_({ tbGo: "admin/audit-trail" })`),
      pageButton: () => run(`click_({ view: "overview" })`),
      go: () => run(`go("settings")`),
      nextUp: () => run(`goTo({ view: "bank", entity_id: ${FX.EXA} })`),
      record: () => run(`goSetupRecord("entities", ${FX.EXA})`),
      section: () => click($("#main").querySelector('[data-setup-kind="payment_types"]')),
      sameSection: () => click($("#main").querySelector('[data-setup-kind="required"]')),
      setupLink: () => click($("#main").querySelector("[data-setup-link]")),
      pageCompany: () => run(`click_({ pickEntity: ${JSON.stringify(String(FX.EXB))} })`),
      prevMonth: () => click($("#prevMonth")),
      nextMonth: () => click($("#nextMonth")),
      thisMonth: () => click($("#thisMonth")),
      back: async () => { location.hash = `#/EXA/${M[0]}/payments/register`; await run(`onHashChange()`); },
      badAddress: async () => { location.hash = "#/nothing/here"; await run(`onHashChange()`); },
    };
    run(`globalThis.click_ = async dataset => { const b = { dataset, tagName: "BUTTON", id: "", className: "", getAttribute: () => null, classList: { contains: () => false } }; b.closest = () => b;
      const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; await __clickAll(ev); };`);
    sandbox.__clickAll = async ev => { for (const l of [...(listeners.get(document) || [])]) if (l.type === "click" && !l.capture) await l.fn(ev); };
    for (const [name, way] of Object.entries(ways)) {
      await open();
      await tick("utility", "tst_memo"); await typeReason("Half typed"); await idle();
      const at = location.hash, month = run(`state.month`), entity = run(`state.entity`);
      calm(); answer(false);
      await way(); await idle(60);
      const kept = { asks: asks(), here: here(), changed: changedBoxes(), reason: $("#rq-reason")?.value, draft: draft(), hash: location.hash === at, month: run(`state.month`) === month, entity: run(`state.entity`) === entity,
        kind: run(`state.setup.kind`), reads: reads().length, hashNow: location.hash };
      calm(); answer(true);
      await way(); await idle(60);
      await run(`closeDrawer(true)`);
      const gone = { asks: asks().length, draft: draft(), changed: changedBoxes(), here: here() };
      await open();
      r[name] = { kept, gone, back: { changed: changedBoxes(), reason: $("#rq-reason").value, asks: asks().length } };
    }
    // with nothing changed, nothing asks; a reason typed alone is something to lose; Escape leaves the page as it is
    await open(); await click($("#prevMonth")); await idle(60); r.clean = { asks: asks().length, month: run(`state.month`) };
    run(`state.month = ${JSON.stringify(M[0])}`);
    await open(); await typeReason("Only a reason"); calm(); answer(false); await run(`go("settings")`); await idle(60);
    r.reasonOnly = { asks: asks(), here: here(), reason: $("#rq-reason")?.value, discard: $("#rq-discard").disabled };
    await typeReason(""); calm(); await run(`go("settings")`); await idle(60); r.reasonCleared = { asks: asks().length, view: run(`state.view`) };
    await open(); await tick("utility", "tst_memo"); await idle(); calm(); box("utility", "tst_memo").focus();
    await key(box("utility", "tst_memo"), "Escape"); await idle(60); r.escape = { asks: asks().length, changed: changedBoxes(), here: here() };
    // two ways at once: one question
    await open(); await tick("utility", "tst_memo"); await idle(); calm();
    let say; sandbox.__held = new Promise(res => { say = res; }); run(`__answers.push(__held)`);
    const a = run(`go("settings")`), b = run(`go("overview")`); await sleep(30); r.twoAsks = asks().length; say(false); await a; await b; await idle(60); r.twoKept = { changed: changedBoxes(), view: run(`state.view`) };
    r.unload = entries.filter(x => x[0] === "listen" && /unload/.test(x[1])).length;
    return r;
  });

  /* ======== For and the month never carry boxes over ======== */
  await tryit("pickers", async () => {
    const r = {};
    for (const [id, value] of [["rq-scope", String(FX.EXB)], ["rq-month", M[1]]]) {
      await open(); await tick("utility", "tst_memo"); await typeReason("Mine"); await idle();
      const was = $("#" + id).value;
      calm(); answer(false); await pick(id, value); await idle(60);
      const kept = { asks: asks(), value: $("#" + id).value, was, changed: changedBoxes(), reason: $("#rq-reason").value, reads: reads(), draft: draft() };
      calm(); answer(true); await pick(id, value); await idle(60);
      r[id] = { kept, gone: { asks: asks().length, value: $("#" + id).value, changed: changedBoxes(), reason: $("#rq-reason").value, reads: reads(), draft: draft(), save: $("#rq-save").textContent, focus: document.activeElement.id } };
    }
    // what the grid said (here, why a box can't be changed) isn't said over the other company's grid
    await open(); await pick("rq-scope", String(FX.EXB)); await idle(60); await tick("utility", "pv"); const saidBefore = strips("msg").length;
    await pick("rq-scope", "all"); await idle(60); r.said = { before: saidBefore, after: strips("msg") };
    // with nothing changed they just draw the other grid, and the month picked stays with another company
    await open(); await pick("rq-month", M[2]); await idle(60); await pick("rq-scope", String(FX.EXB)); await idle(60);
    r.clean = { asks: asks().length, month: $("#rq-month").value, scope: $("#rq-scope").value, reads: reads() };
    await tick("utility", "tst_memo"); await idle(); calm(); await submit().done; await idle();
    r.savedFrom = posts().map(p => [p.entity_id, p.from_month]);
    await run(`navigate({ view: "overview", entity: "all", month: ${JSON.stringify(M[0])}, sub: null, id: null, params: {} }, { fresh: true })`); await idle(60); NET.sent.length = 0;
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: ${JSON.stringify(M[0])}, sub: "required", id: null, params: {} }, { fresh: true })`); await idle(60);
    r.comeBack = { month: $("#rq-month").value, scope: $("#rq-scope").value };
    await single("utility", null, FX.EXB, M[2]);
    return r;
  });

  /* ======== the page read again keeps what isn't saved; boxes aren't clicked while it is read ======== */
  await tryit("reread", async () => {
    const r = {};
    await open(); await tick("utility", "tst_memo"); await typeReason("Still here"); await idle(); calm();
    await run(`render()`); await idle();
    r.same = { changed: changedBoxes(), reason: $("#rq-reason").value, msgs: strips("msg"), asks: asks().length, status: status(), previews: previews().length };
    NET.delay = (m, p) => m === "GET" && p.startsWith("/api/setup/required") ? 400 : 0;
    const drawing = run(`render()`); await sleep(60);
    const during = { grid: !!$("#rq-body") };
    // a click or a Save arriving late, while the page is read (Setup has cleared the grid): it changes nothing and sends nothing
    await run(`rqToggle("utility", "invoice")`); await run(`rqFollow("utility", true)`); await run(`rqSave()`);
    during.draft = draft();
    during.posts = posts().length;
    await drawing; await idle(); quiet();
    r.during = { ...during, changed: changedBoxes(), reason: $("#rq-reason").value };
    // another change under a ticked row is said when the page is read again; the boxes not ticked here follow the records
    r.base = (await held("utility")).docs;
    r.other = await single("utility", ["invoice", "pv", "bank"], null, M[0]);
    await run(`render()`); await idle();
    r.moved = { msgs: strips("msg"), changed: changedBoxes(), pv: info("utility", "pv").pressed, sent: JSON.parse(run(`JSON.stringify(rqBody(state.setup.req, state.setup.reqDraft))`)).changes[0].docs };
    // ... and when the records already hold the ticked box, it is no longer a change
    await single("utility", ["invoice", "pv", "bank", "tst_memo"], null, M[0]);
    await run(`render()`); await idle();
    r.already = { changed: changedBoxes(), draft: draft(), reason: $("#rq-reason").value };
    await single("utility", ["invoice", "pv", "bank"], null, M[0]);
    // read again but it fails: the boxes are kept, and Try again shows them
    await open(); await tick("utility", "tst_memo"); await idle(); calm();
    NET.fail = (m, p) => m === "GET" && p.startsWith("/api/setup/required") ? "net" : null;
    await run(`render()`); await idle(); quiet();
    const page = $("#main").innerHTML;
    calm(); answer(false); await run(`go("settings")`); await idle(60);
    const asked = asks().length;
    await run(`render()`); await idle();
    r.failedRead = { stopped: /isn(&#39;|')t running/.test(page), asked, changed: changedBoxes() };
    return r;
  });

  /* ======== one company ======== */
  await tryit("company", async () => {
    const r = {};
    await open(); await pick("rq-scope", String(FX.EXB)); await idle(60);
    r.kept = { note: $("#setupMain").querySelector(".rq-scope-note").textContent, month: $("#rq-month-note").textContent, head: $("#setupMain").querySelectorAll("thead th").pop().textContent,
      pv: info("utility", "pv"), invoice: info("utility", "invoice"), naHeads: $("#setupMain").querySelectorAll("th.na").map(t => t.getAttribute("title")),
      for: rowOf("utility").querySelector(".rq-for").textContent, follow: !!rowOf("utility").querySelector("[data-rq-follow]"), html: $("#setupMain").innerHTML };
    calm(); await tick("utility", "pv"); await idle();
    r.greyed = { msgs: strips("msg"), pv: info("utility", "pv"), draft: draft(), previews: previews().length };
    // its own set: a change, saved for this company only; the greyed box stays as it was
    await tick("utility", "approval"); await idle();
    r.fresh = { warnings: warnings(), status: status() };
    const everyBefore = (await held("utility")).docs;
    calm(); await submit().done; await idle();
    r.own = { sent: posts(), for: rowOf("utility").querySelector(".rq-for").textContent, every: [(await held("utility")).docs, everyBefore], mine: await held("utility", FX.EXB), since: rowOf("utility").querySelector(".rq-since").textContent };
    // Follow all companies again: pending, its boxes locked, undone by Keep its own set
    const follow = rowOf("utility").querySelector("[data-rq-follow]");
    r.button = { text: follow.textContent, label: follow.getAttribute("aria-label"), id: follow.id };
    calm(); await click(follow); await idle();
    r.pending = { for: rowOf("utility").querySelector(".rq-for").textContent, since: rowOf("utility").querySelector(".rq-since").textContent, approval: info("utility", "approval"), changed: changedBoxes(), status: status(), focus: document.activeElement.id,
      previews: previews().slice(-1)[0] };
    await tick("utility", "invoice"); await idle(); r.locked = { msgs: strips("msg"), invoice: info("utility", "invoice"), draft: draft() };
    await click(rowOf("utility").querySelector("[data-rq-follow]")); await idle();
    r.undone = { draft: draft(), approval: info("utility", "approval"), for: rowOf("utility").querySelector(".rq-for").textContent, focus: document.activeElement.id };
    await tick("utility", "invoice"); await click(rowOf("utility").querySelector("[data-rq-follow]")); await idle();
    r.replaced = { draft: draft(), invoice: info("utility", "invoice").pressed };
    await tick("claim", "tst_memo"); await typeReason("As everyone"); await idle(); calm();
    await submit().done; await idle();
    r.followed = { sent: posts(), for: rowOf("utility").querySelector(".rq-for").textContent, mine: await held("utility", FX.EXB), follow: !!rowOf("utility").querySelector("[data-rq-follow]") };
    // every company: the company with its own set is marked, and a change says it doesn't reach it
    await pick("rq-scope", "all"); await idle(60);
    r.marked = { claim: rowOf("claim").querySelector(".rq-for").textContent, utility: rowOf("utility").querySelector(".rq-for").textContent };
    await tick("claim", "approval"); await idle(); r.reach = warnings();
    // a company that SQL Account keeps greys nothing
    await open(); await pick("rq-scope", String(FX.EXA)); await idle(60);
    r.sql = { note: $("#setupMain").querySelector(".rq-scope-note").textContent, off: $("#rq-body").querySelectorAll("[data-rq-doc][aria-disabled]").length, na: $("#setupMain").querySelectorAll(".na").length };
    // a company no longer in use: its boxes are dropped, said, and never saved for every company
    await open(); await pick("rq-scope", String(FX.EXB)); await idle(60); await tick("claim", "approval"); await idle(); calm();
    await server("POST", `/api/setup/entities/${FX.EXB}/stop`, { reason: "Closed" });
    const m2 = (await server("GET", "/api/meta", null)).body; run(`state.meta = ${JSON.stringify(m2)}`);
    await run(`render()`); await idle();
    r.gone = { scope: $("#rq-scope").value, msgs: strips("msg"), changed: changedBoxes(), draft: draft() };
    await submit().done; await idle(); r.gonePosts = posts().length;
    await server("POST", `/api/setup/entities/${FX.EXB}/use`, { reason: "Open again" });
    const m3 = (await server("GET", "/api/meta", null)).body; run(`state.meta = ${JSON.stringify(m3)}`);
    return r;
  });

  /* ======== what a save would do besides the boxes changed ======== */
  await tryit("warnings", async () => {
    const r = {};
    await single("consultant", ["invoice", "bank"], null, M[2]);
    await open(); await tick("consultant", "tst_memo"); await idle();
    r.later = { warnings: warnings(), since: rowOf("consultant").querySelector(".rq-since").textContent, pressed: pressed("consultant", "approval") };
    calm(); await submit().done; await idle();
    r.laterSets = (await server_view(null, M[2])).types.find(t => t.key === "consultant").at;
    await open(); await tick("other", "tst_memo"); await idle();
    r.other = { warnings: warnings(), followers: (await server_view()).types.filter(t => t.at.follows_other).map(t => t.label) };
    await tick("tst_odd", "approval"); await idle();
    r.otherAndFollower = warnings();
    calm(); await submit().done; await idle();
    r.otherSaved = { sent: posts()[0].changes.map(c => [c.payment_type, c.docs]), odd: (await held("tst_odd")).docs, other: (await held("other")).docs, oldKind: (await held("tst_old")) };
    // a company: it was to follow all companies again later, and all companies are to change later
    await single("director", ["bank"], FX.EXB, M[0]); await single("director", null, FX.EXB, M[2]); await single("receipt", ["bank"], null, M[3]);
    await open(); await pick("rq-scope", String(FX.EXB)); await idle(60);
    r.backNote = rowOf("director").querySelector(".rq-since").textContent;
    await tick("director", "tst_memo"); await idle(); r.back = warnings();
    await click($("#rq-discard")); await idle(); await tick("receipt", "tst_memo"); await idle(); r.theirs = warnings();
    await click($("#rq-discard")); await idle(); await pick("rq-scope", "all"); await idle(60); await tick("receipt", "tst_memo"); await idle(); r.theirsAll = warnings();
    run(`rqDrop()`);
    return r;
  });

  /* ======== a document no longer in use that a set still asks for ======== */
  await tryit("stoppedDoc", async () => {
    const r = {};
    // a set from a filed month's rules can keep a document stopped since: made here by putting it straight in the view
    await open();
    const real = JSON.parse(run(`JSON.stringify(state.setup.req)`));
    const memo = real.doc_types.find(d => d.key === "tst_memo");
    NET.reply = null;
    const doctored = JSON.parse(JSON.stringify(real));
    doctored.doc_types.find(d => d.key === "tst_memo").active = 0;
    const row = doctored.types.find(t => t.key === "rental");
    row.at.docs = ["invoice", "tst_memo", "bank"];
    run(`state.setup.req = ${JSON.stringify(doctored)}; document.querySelector("#setupMain").innerHTML = rqPageHtml(state.setup.req);`);
    r.col = { box: info("rental", "tst_memo"), other: info("claim", "tst_memo"), head: $("#setupMain").querySelectorAll("th.rq-doc").map(t => [t.getAttribute("title"), t.textContent]).find(x => x[0] === memo.label) };
    await tick("rental", "tst_memo"); r.locked = { msgs: strips("msg"), draft: draft() };
    await tick("rental", "approval"); await sleep(20);
    r.changed = { warnings: warnings(), docs: JSON.parse(run(`JSON.stringify(rqBody(state.setup.req, state.setup.reqDraft))`)).changes[0].docs };
    run(`rqDrop()`);
    return r;
  });

  /* ======== earlier sets, and the arrow keys ======== */
  await tryit("more", async () => {
    const r = {};
    await open();
    const h = () => rowOf("utility").querySelector("[data-rq-hist]");
    r.closed = { expanded: h().getAttribute("aria-expanded"), label: h().getAttribute("aria-label"), rows: $("#rq-body").querySelectorAll("tr.rq-hist").length };
    await click(h()); r.open = { expanded: h().getAttribute("aria-expanded"), text: $("#rq-body").querySelector("tr.rq-hist").textContent, focus: document.activeElement.id === h().id, asks: asks().length, draft: draft() };
    await click(rowOf("transfer").querySelector("[data-rq-hist]")); r.start = $("#rq-body").querySelectorAll("tr.rq-hist").map(x => x.textContent).find(x => x.includes("Inter-company"));
    await click(rowOf("tst_odd").querySelector("[data-rq-hist]")); await click(h()); r.shut = $("#rq-body").querySelectorAll("tr.rq-hist").length;
    await open();
    const first = $("#rq-body").querySelector("[data-rq-doc]"); first.focus();
    const at = () => document.activeElement.id;
    const moves = [];
    for (const k of ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "End", "ArrowRight", "Home", "ArrowLeft", "ArrowUp"]) { const ev = await key(document.activeElement, k); moves.push([k, at(), ev.defaultPrevented]); }
    const alt = await key(document.activeElement, "ArrowLeft", { altKey: true });
    r.keys = { first: first.id, moves, alt: alt.defaultPrevented, cols: $("#rq-body").querySelectorAll('[data-rq-r="0"]').length };
    return r;
  });

  /* ======== while it saves ======== */
  await tryit("saving", async () => {
    const r = {};
    await open(); await tick("rental", "tst_memo"); await typeReason("Slow one"); await idle(); calm();
    NET.delay = (m, p, b) => m === "POST" && !b.preview ? 500 : 0;
    const one = submit(); await sleep(40);
    r.during = { save: $("#rq-save").textContent, busy: $("#rq-save").getAttribute("aria-busy"), disabled: [$("#rq-save").disabled, $("#rq-discard").disabled, $("#rq-scope").disabled, $("#rq-month").disabled, $("#rq-reason").readOnly],
      off: $("#rq-body").querySelectorAll("[data-rq-doc]").every(b => b.getAttribute("aria-disabled") === "true"), status: status() };
    await tick("rental", "approval"); await submit().done; await run(`rqDiscard()`);
    r.blocked = { posts: posts().length, changed: changedBoxes() };
    await one.done; await idle();
    r.done = { posts: posts().length, changed: changedBoxes(), result: strips("ok"), off: info("rental", "bank").off };
    // leaving while it is on its way asks in its own words; staying keeps the page
    await tick("rental", "tst_memo"); await idle(); calm();
    NET.delay = (m, p, b) => m === "POST" && !b.preview ? 500 : 0;
    const two = submit(); await sleep(40); answer(false); await run(`go("settings")`);
    r.stay = { asks: asks(), view: run(`state.view`), grid: !!$("#rq-body") };
    calm(); NET.delay = (m, p, b) => 0; await two.done; await idle(700);
    // left, and it is saved: only a message, and the page on show isn't read again
    await tick("rental", "tst_memo"); await idle(); calm();
    NET.delay = (m, p, b) => m === "POST" && !b.preview ? 500 : 0;
    const three = submit(); await sleep(40); answer(true); await run(`navigate({ view: "overview", entity: "all", month: ${JSON.stringify(M[0])}, sub: null, id: null, params: {} }, { fresh: true })`); await sleep(40);
    NET.sent.length = 0; await three.done; await idle();
    r.away = { view: run(`state.view`), main: $("#main").innerHTML, toasts: toasts(), reads: NET.sent.filter(x => x[0] === "GET").length, saving: run(`state.setup.reqSaving`), draft: draft() };
    // left, and it is refused: a message says it wasn't saved
    await open(); await tick("rental", "tst_memo"); await idle(); calm();
    await single("rental", ["bank"], null, M[0]);
    NET.delay = (m, p, b) => m === "POST" && !b.preview ? 400 : 0;
    const four = submit(); await sleep(40); answer(true); await run(`go("overview")`); await sleep(20); await four.done; await idle();
    r.awayRefused = { toasts: toasts(), main: $("#main").innerHTML };
    // come back while it is still saving: the grid waits for it, then is read again
    await open(); await tick("rental", "tst_memo"); await idle(); calm();
    NET.delay = (m, p, b) => m === "POST" && !b.preview ? 600 : 0;
    const five = submit(); await sleep(40); answer(true); await run(`go("overview")`); await sleep(20);
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: ${JSON.stringify(M[0])}, sub: "required", id: null, params: {} }, { fresh: true })`);
    const mid = { off: info("rental", "bank").off, save: $("#rq-save").textContent };
    await five.done; await idle();
    r.back = { mid, memo: info("rental", "tst_memo"), off: info("rental", "bank").off, save: $("#rq-save").textContent, result: strips("ok") };
    return r;
  });

  /* ======== a month filed while the boxes wait ======== */
  await tryit("filed", async () => {
    const r = {};
    await open(); await tick("rental", "approval"); await typeReason("Late change"); await idle(); calm();
    await server("POST", "/api/months/close", { entity_id: FX.EXA, month: M[0], closed: true });
    await submit().done; await idle();
    r.refused = { posts: posts().length, msgs: strips("msg"), changed: changedBoxes(), reason: $("#rq-reason").value, month: $("#rq-month").value, note: $("#rq-month-note").textContent,
      option: $("#rq-month").querySelectorAll("option").filter(o => o.value === M[0]).map(o => o.textContent) };
    calm(); await submit().done; await idle(); r.again = { posts: posts().length, msgs: strips("msg"), previews: previews().length, changed: changedBoxes() };
    answer(true); await pick("rq-month", M[1]); await idle(60);
    r.moved = { month: $("#rq-month").value, changed: changedBoxes(), months: $("#rq-month").querySelectorAll("option").map(o => [o.value, o.textContent, o.hasAttribute("disabled")]).slice(0, 3), note: $("#rq-month-note").textContent };
    // a month picked for one company that another has filed: For that company shows the month offered, and says why
    await open(); await pick("rq-scope", String(FX.EXB)); await idle(60); await pick("rq-month", M[0]); await idle(60);
    const picked = $("#rq-month").value;
    calm(); await pick("rq-scope", String(FX.EXA)); await idle(60);
    r.fallback = { picked, month: $("#rq-month").value, msgs: strips("msg"), reads: reads() };
    return r;
  });

  out.unheard = unheard;
  process.stdout.write("@@OUT " + JSON.stringify(out) + "\n");
  process.exit(0);
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps({"EXA": EXA, "EXB": EXB, "months": [M0, M1, M2, M3], "none": None}), encoding="utf-8")
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
files = [str(f) for f in app_files() if not str(f).endswith("main.js")]
proc = subprocess.Popen([shutil.which("node"), str(probe), str(fx_path), *files], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
errors = []
reader = threading.Thread(target=lambda: errors.append(proc.stderr.read()), daemon=True)
reader.start()
watchdog = threading.Timer(420, proc.kill)
watchdog.start()
o = None
try:
    for line in proc.stdout:
        if line.startswith("@@REQ "):
            req = json.loads(line[6:])
            kw = {"headers": H}
            if req["body"] is not None:
                kw["json"] = req["body"]
            res = client.open(BASE + req["path"], method=req["method"], **kw)
            proc.stdin.write(json.dumps({"id": req["id"], "status": res.status_code, "body": res.get_json(silent=True) or {}}) + "\n")
            proc.stdin.flush()
        elif line.startswith("@@OUT "):
            o = json.loads(line[6:])
    proc.wait(timeout=30)
finally:
    watchdog.cancel()
    if proc.poll() is None:
        proc.kill()
reader.join(timeout=5)
check("the page script ran on the stand-in page, against the real server", o is not None, "".join(errors)[-1500:])
if os.environ.get("HRP_PAGE_OUT"):
    Path(os.environ["HRP_PAGE_OUT"]).write_text(json.dumps(o, indent=1), encoding="utf-8")
for k, v in (o or {}).items():
    if isinstance(v, dict) and v.get("error"):
        print(f"     {k}: {v['error']}")


class Soft(dict):
    """A probe answer that may be missing: a key not there reads as an empty answer, so every check runs (and with HRP_KEEP_GOING is listed)."""
    def __missing__(self, k):
        return Soft()


def soften(v):
    if isinstance(v, dict):
        return Soft({k: soften(x) for k, x in v.items()})
    return [soften(x) for x in v] if isinstance(v, list) else v


def has(text, *parts):
    return isinstance(text, str) and all(p in text for p in parts)


def holds(name, fn, detail=None):
    """A check whose answer may be missing or of another shape on broken code: that is its failure, never a crash of the test."""
    try:
        ok = bool(fn())
    except Exception as x:  # noqa: BLE001
        ok, detail = False, f"{type(x).__name__}: {x}"
    check(name, ok, detail)


o = soften(o)
MONTH = db.month_label

# ---------- the grid ----------
d = o["drawn"]
LABEL = {t["key"]: t["label"] for t in call("get", "/api/setup/required")["types"]}
holds("document types go across, in pack order, then In force and who has their own set; payment types go down, the stopped one last",
      lambda: [h["title"] for h in d["docHeads"]] == d["activeDocs"] and d["heads"][0] == "Payment type" and d["heads"][-2:] == ["In force", "Companies"]
      and d["rowNames"] == d["activeTypes"] + d["stoppedTypes"] and d["stoppedTypes"] == ["Test old kind"] and d["rowHeads"] is True, d["heads"])
holds("every box is ticked as the records have it for the month, and is a button of its own, reached by Tab, with an id and a label",
      lambda: d["mismatch"] == [] and d["boxes"] == d["ids"] == len(d["activeDocs"]) * len(d["rowNames"]) and d["labelled"] is True, (d["boxes"], d["mismatch"]))
holds("a box's label names the type, the document and its state; an approval ticked says it comes from an approved form",
      lambda: d["utility"][0]["label"] == f"{LABEL['utility']}: Invoice / bill, required" and d["utility"][0]["pressed"] == "true"
      and d["utility"][1]["label"] == f"{LABEL['utility']}: {ODD_DOC}, not needed" and d["utility"][1]["pressed"] == "false"
      and d["approval"][1]["label"].endswith("required, from an approved form") and d["approval"][0]["label"].endswith("not needed"), (d["utility"], d["approval"]))
holds("the columns say their sources: from SQL on SQL Account's documents, from form on the approval; there is no posted-here box",
      lambda: [h["src"] for h in d["docHeads"][:5]] == [["from SQL"]] * 3 + [["from form"], []] and "posted here" not in d["html"].lower()
      and has(d["html"], "An approved form fills this box once Approvals is built. Until then the form is uploaded by hand.", "Changed, not saved yet", "This document is issued by SQL Account."), d["docHeads"][:5])
holds("For lists every company and each company in use; the month starts at the one a change is offered from, with the months around it",
      lambda: d["scope"] == ["Every company", "EXA only", "EXB only"] and d["scopeValue"] == "all" and d["month"] == M0 and [M0, MONTH(M0), False] in d["months"]
      and d["months"][0][0] == db.shift_month(M0, -24) and d["months"][-1][0] == db.shift_month(M0, 12) and all(not x[2] for x in d["months"]), d["months"][:3])
holds("Save names the month; Discard has nothing to do; the reason is optional and takes 500 characters; the month's note and the status line are there",
      lambda: d["save"] == f"Save from {MONTH(M0)}" and d["discard"] is True and d["reason"] == ["", "500"] and d["note"] == f"Applies from {MONTH(M0)}. It never reaches a filed month."
      and d["live"] == "status" and d["status"] == "", (d["save"], d["note"]))
holds("each row says since when its set is in force and how many documents it asks for; a type with none says it is as Other",
      lambda: has(d["since"], "From the start", "Earlier sets") and has(d["follower"], "Same as Other") and d["count"] == "3 documents", (d["since"], d["follower"]))
holds("names with markup are shown as they are written, in cells, headings, labels and titles, never as HTML",
      lambda: ODD_TYPE in d["rowNames"] and any(h["title"] == ODD_DOC and h["text"] == ODD_DOC for h in d["docHeads"]) and "<img" not in d["html"] and "<b>bold" not in d["html"]
      and "&lt;img src=x onerror=1&gt; &quot;water&quot; &amp; co" in d["html"] and "&lt;b&gt;bold&lt;/b&gt;" in d["html"], d["rowNames"])

# ---------- clicking boxes ----------
c = o["clicks"]
holds("a click changes the box, marks it Changed, not saved yet (a dot, its title and its label), counts it, and keeps the focus on it",
      lambda: c["before"]["pressed"] == "true" and c["at0"]["box"]["pressed"] == "false" and c["at0"]["box"]["changed"] and c["at0"]["box"]["dot"] and c["at0"]["box"]["title"] == "Changed, not saved yet"
      and c["at0"]["box"]["label"].endswith("not needed, changed, not saved yet") and has(c["at0"]["status"], "1 unsaved change") and c["at0"]["discard"] is False
      and c["at0"]["focus"] == c["before"]["id"] and c["at0"]["count"] == "2 documents" and c["at0"]["changed"] == ["utility.pv"], c["at0"])
holds("what saving would do to open payments is asked of the server as a preview, which saves nothing",
      lambda: has(c["previewed"]["status"], "2 open payments will be complete.") and len(c["previewed"]["sent"]) == 1 and c["previewed"]["posts"] == 0
      and c["previewed"]["sent"][0]["preview"] is True and [x["payment_type"] for x in c["previewed"]["sent"][0]["changes"]] == ["utility"], c["previewed"])
holds("a box clicked back is no change: no mark, nothing kept, nothing more asked",
      lambda: c["back"]["box"]["changed"] is False and c["back"]["box"]["pressed"] == "true" and c["back"]["status"] == "" and c["back"]["discard"] is True and c["back"]["draft"] is None
      and c["back"]["changed"] == [] and c["back"]["previews"] == 1, c["back"])
holds("boxes of several types are counted together, each type in the preview with its documents in its own order, new ones after, in pack order",
      lambda: has(c["three"]["status"], "3 unsaved changes") and c["three"]["changed"] == ["salary.invoice", "utility.pv", "utility.tst_memo"]
      and {x["payment_type"]: x["docs"] for x in c["three"]["previews"]["changes"]} == {"salary": ["pv", "payslip", "bank", "invoice"], "utility": ["invoice", "bank", "tst_memo"]}, c["three"])
holds("Discard puts every box back with nothing asked or sent, and leaves the focus on Save",
      lambda: c["discarded"]["changed"] == [] and c["discarded"]["draft"] is None and c["discarded"]["status"] == "" and c["discarded"]["asks"] == 0 and c["discarded"]["posts"] == 0
      and c["discarded"]["focus"] == "rq-save" and c["discarded"]["box"] == "true", c["discarded"])
holds("a preview answered after the boxes changed again is not shown for them",
      lambda: has(c["working"], "Working out what changes for open payments") and c["late"]["n"] == 2 and has(c["late"]["status"], "2 unsaved changes", "2 open payments will be complete."), (c["working"], c["late"]))
holds("...nor one that comes before the newer boxes have been asked about",
      lambda: has(c["betweenLate"], "2 unsaved changes", "Working out what changes for open payments") and "will" not in c["betweenLate"] and "Working out" not in c["betweenEnd"], (c["betweenLate"], c["betweenEnd"]))

# ---------- one save ----------
s = o["save"]
holds("Save sends every changed type in one request with the reason and what the page showed; a type ticked and unticked is not sent",
      lambda: len(s["sent"]) == 1 and s["sent"][0]["reason"] == "Finance asked" and s["sent"][0]["entity_id"] is None and s["sent"][0]["from_month"] == M0
      and [(x["payment_type"], x["docs"]) for x in s["sent"][0]["changes"]] == [("utility", ["invoice", "bank"]), ("rental", ["invoice", "pv", "bank", "tst_memo"])]
      and all(x["was"]["docs"] == ["invoice", "pv", "bank"] for x in s["sent"][0]["changes"]) and s["prevented"] is True, s["sent"])
holds("once saved: what it did is said (with Dismiss and a message), the grid is read again with nothing marked, and the reason box is empty",
      lambda: s["result"] == ["Saved. 2 open payments are now complete.Dismiss"] and s["toasts"] == [f"Saved from {MONTH(M0)}"] and s["changed"] == [] and s["draft"] is None and s["reason"] == ""
      and s["pv"]["pressed"] == "false" and s["month"] == M0 and s["discard"] is True and s["msgs"] == [] and s["dismissed"] == 0, s)
holds("Save with nothing changed sends nothing and says so", lambda: s["nothing"] == {"msgs": ["Nothing changes: these are the documents already required from that month."], "posts": 0}, s["nothing"])
tx = q("SELECT * FROM audit_tx WHERE reason = 'Finance asked'")
holds("in the records the grid's save is one entry of the audit trail with its reason and a line for each type",
      lambda: len(tx) == 1 and tx[0]["summary"].count("Required documents: ") == 2 and "Utility / telco" in tx[0]["summary"] and "Rental" in tx[0]["summary"], tx)

# ---------- refused ----------
r = o["refused"]
holds("a save refused because the records moved keeps the boxes and the reason, says nothing was saved, and reads the grid again",
      lambda: r["other"] == 200 and r["after"]["posts"] == 1 and r["after"]["reads"] == 1 and r["after"]["msgs"][0] == f"What is required from {MONTH(M0)} for Staff claim changed after this page read it. Nothing was saved."
      and r["after"]["changed"] == ["claim.tst_memo"] and r["after"]["memo"] == "true" and r["after"]["reason"] == "Memo for claims" and r["after"]["server"] == r["was"] + ["einvoice"]
      and r["after"]["discard"] is False and r["after"]["busy"] is None and r["after"]["off"] is False, r["after"])
holds("...the other change is on show, and the row is named to be checked",
      lambda: r["after"]["einvoice"] == "true" and f"What is required from {MONTH(M0)} for Staff claim changed since you ticked it. Check its row before you save." in r["after"]["msgs"], r["after"])
holds("...saving again adds only what was ticked, and keeps what the other change added",
      lambda: len(r["again"]["posts"]) == 1 and r["again"]["posts"][0]["reason"] == "Memo for claims" and r["again"]["server"] == r["was"] + ["einvoice", "tst_memo"]
      and r["again"]["changed"] == [] and r["again"]["msgs"] == [] and len(r["again"]["result"]) == 1, r["again"])

# ---------- kept but not read back, and no clear answer ----------
k = o["kept"]
holds("a saved change that can't be read back says it was saved, once, with nothing kept as unsaved",
      lambda: k["failed"]["posts"] == 1 and has(k["failed"]["page"], "It was saved, but this page could not reload. Try again.", 'data-retry="saved"') and "Nothing was changed" not in k["failed"]["page"]
      and k["failed"]["draft"] is None and k["failed"]["saving"] is False and k["failed"]["toasts"] == [f"Saved from {MONTH(M0)}"], k["failed"])
holds("...its Try again only reads, and leaving after it asks nothing",
      lambda: k["retried"] == {"posts": 0, "grid": True, "changed": [], "draft": None, "asks": 0} and k["left"] == {"asks": 0, "view": "overview"}, (k["retried"], k["left"]))
holds("a save whose answer is lost says it isn't known whether it was saved, never that nothing was, and shows what the records hold",
      lambda: k["lost"]["posts"] == 1 and k["lost"]["msgs"] == ["The connection to HR Payments broke. It isn't known whether it was saved: check before doing it again."]
      and k["lost"]["changed"] == [] and k["lost"]["reason"] == "Back again" and "Nothing was saved" not in k["lost"]["all"] and "Nothing was changed" not in k["lost"]["all"], k["lost"])
holds("one that never reaches the server keeps the boxes and the reason, and says the same",
      lambda: k["never"]["changed"] == ["rental.tst_memo"] and k["never"]["reason"] == "Try later" and "isn't known whether it was saved" in k["never"]["msgs"][0] and k["never"]["reads"] == 1
      and "Nothing was saved" not in k["never"]["all"], k["never"])
holds("with the app stopped the stopped page and a message say it isn't known, and the boxes are there again once it runs",
      lambda: re.search(r"isn(&#39;|')t running", k["stopped"]["page"]) and "Nothing was changed" not in k["stopped"]["page"] and any("isn't known whether it was saved" in t for t in k["stopped"]["toasts"])
      and k["stopped"]["draft"]["reason"] == "Try later" and k["running"] == {"changed": ["rental.tst_memo"], "reason": "Try later"}, (k["stopped"]["toasts"], k["running"]))

# ---------- leaving ----------
WAYS = {"sidebar": "the side menu", "topbarCompany": "the company switcher (another company)", "allCompanies": "the company switcher (All companies)", "addCompany": "Add company in the switcher",
        "accountMenu": "the account menu's Audit trail", "pageButton": "a page button", "go": "go()", "nextUp": "a Next up row", "record": "a link to a Setup record",
        "section": "another Setup section", "sameSection": "the same section's menu item", "setupLink": "Setup's link to Recurring payments", "pageCompany": "a page's own company button",
        "prevMonth": "the month before arrow", "nextMonth": "the month after arrow", "thisMonth": "This month", "back": "Back, or an address typed", "badAddress": "an address that isn't one of the app's"}
lv = o["leaving"]
for way, words in WAYS.items():
    w = lv[way]
    holds(f"leaving by {words} asks Discard your changes?, and Keep editing stays, with the boxes, the reason, the address, the month and the company as they were",
          lambda: [(a["title"], a["yes"], a["no"]) for a in w["kept"]["asks"]] == [("Discard your changes?", "Discard changes", "Keep editing")]
          and w["kept"]["asks"][0]["message"] == "1 unsaved change on Required documents will be lost." and w["kept"]["here"] == {"view": "setup", "kind": "required", "grid": True}
          and w["kept"]["changed"] == ["utility.tst_memo"] and w["kept"]["reason"] == "Half typed" and w["kept"]["hash"] and w["kept"]["month"] and w["kept"]["entity"]
          and w["kept"]["reads"] == 0 and w["kept"]["kind"] == "required", w["kept"])
    holds(f"...Discard changes goes where {words} goes, and nothing comes back with the grid",
          lambda: w["gone"]["asks"] == 1 and w["gone"]["draft"] is None and not w["gone"]["changed"] and w["back"] == {"changed": [], "reason": "", "asks": 0}, (w["gone"], w["back"]))
holds("with nothing changed nothing asks; a reason typed alone is something to lose, and emptied again it isn't",
      lambda: lv["clean"] == {"asks": 0, "month": db.shift_month(M0, -1)} and [a["message"] for a in lv["reasonOnly"]["asks"]] == ["The reason typed on Required documents will be lost."]
      and lv["reasonOnly"]["here"]["grid"] is True and lv["reasonOnly"]["reason"] == "Only a reason" and lv["reasonOnly"]["discard"] is False
      and lv["reasonCleared"] == {"asks": 0, "view": "settings"}, (lv["clean"], lv["reasonOnly"], lv["reasonCleared"]))
holds("Escape on the grid leaves it as it is, and two ways at once ask once",
      lambda: lv["escape"]["asks"] == 0 and lv["escape"]["changed"] == ["utility.tst_memo"] and lv["twoAsks"] == 1 and lv["twoKept"] == {"changed": ["utility.tst_memo"], "view": "setup"}, (lv["escape"], lv["twoKept"]))
holds("as before, nothing in the app stands in the way of closing or reloading the tab", lambda: lv["unload"] == 0, lv["unload"])

# ---------- For and the month ----------
p = o["pickers"]
for pid, words, value, url in (("rq-scope", "For", str(EXB), f"/api/setup/required?entity={EXB}"), ("rq-month", "the month", M1, f"/api/setup/required?entity=&month={M1}")):
    x = p[pid]
    holds(f"changing {words} with a box not saved asks first, and Keep editing puts it back, reading nothing",
          lambda: [a["title"] for a in x["kept"]["asks"]] == ["Discard your changes?"] and x["kept"]["value"] == x["kept"]["was"] and x["kept"]["changed"] == ["utility.tst_memo"]
          and x["kept"]["reason"] == "Mine" and x["kept"]["reads"] == [], x["kept"])
    holds(f"...Discard changes shows the grid picked with no box or reason carried over, the focus back on {words}",
          lambda: x["gone"]["asks"] == 1 and x["gone"]["value"] == value and x["gone"]["changed"] == [] and x["gone"]["reason"] == "" and x["gone"]["draft"] is None
          and x["gone"]["reads"] == [url] and x["gone"]["focus"] == pid, x["gone"])
holds("what the grid said for one company is gone from the next one's", lambda: p["said"] == {"before": 1, "after": []}, p["said"])
holds("with nothing changed the pickers just draw; the month picked stays for another company, and Save is from it",
      lambda: p["clean"]["asks"] == 0 and p["clean"]["month"] == M2 and p["clean"]["scope"] == str(EXB) and p["savedFrom"] == [[EXB, M2]], (p["clean"], p["savedFrom"]))
holds("Setup opened again shows For as it was left and the month a change is offered from", lambda: p["comeBack"] == {"month": M0, "scope": str(EXB)}, p["comeBack"])

# ---------- read again ----------
rr = o["reread"]
holds("the grid read again (the page drawn again) keeps the boxes and the reason, asks nothing and works out their effect again",
      lambda: rr["same"]["changed"] == ["utility.tst_memo"] and rr["same"]["reason"] == "Still here" and rr["same"]["msgs"] == [] and rr["same"]["asks"] == 0 and rr["same"]["previews"] == 1
      and has(rr["same"]["status"], "1 unsaved change", "2 open payments will miss a document."), rr["same"])
holds("while it is being read, a click, a follow or a Save arriving late changes and sends nothing",
      lambda: rr["during"]["posts"] == 0 and rr["during"]["draft"]["edits"] == {"utility": {"tst_memo": True}} and rr["during"]["draft"]["follows"] == {}
      and rr["during"]["changed"] == ["utility.tst_memo"] and rr["during"]["reason"] == "Still here", rr["during"])
holds("when the records moved under a ticked row, the boxes not ticked here follow them, the row is named, and what would be sent keeps the other change",
      lambda: rr["other"] == 200 and rr["moved"]["pv"] == "true" and rr["moved"]["changed"] == ["utility.tst_memo"] and rr["moved"]["sent"] == ["invoice", "pv", "bank", "tst_memo"]
      and rr["moved"]["msgs"] == [f"What is required from {MONTH(M0)} for Utility / telco changed since you ticked it. Check its row before you save."], rr["moved"])
holds("a ticked box the records now hold is no longer a change", lambda: rr["already"]["changed"] == [] and rr["already"]["draft"]["edits"] == {} and rr["already"]["reason"] == "Still here", rr["already"])
holds("a grid that can't be read again keeps the boxes: leaving still asks, and once read they are back",
      lambda: rr["failedRead"] == {"stopped": True, "asked": 1, "changed": ["utility.tst_memo"]}, rr["failedRead"])

# ---------- one company ----------
co = o["company"]
holds("a company Kept here: SQL Account's documents are greyed in the grid and said why, in the note, each box's label and title; the others are as ever",
      lambda: co["kept"]["note"].startswith("EXB is Kept here: Payment Voucher, Journal Voucher and Official Receipt are issued by SQL Account, so they are not asked for while EXB is Kept here.")
      and co["kept"]["pv"]["off"] is True and has(co["kept"]["pv"]["cls"], "off") and co["kept"]["pv"]["label"].endswith("required, issued by SQL Account, so not asked for while EXB is Kept here")
      and co["kept"]["invoice"]["off"] is False and len(co["kept"]["naHeads"]) == 3 and "posted here" not in co["kept"]["html"].lower(), co["kept"])
holds("...its last column says it follows all companies, with nothing to follow again yet; the month's note says what that means",
      lambda: co["kept"]["head"] == "For EXB" and co["kept"]["for"] == "Follows all companies" and co["kept"]["follow"] is False
      and co["kept"]["month"].endswith("EXB follows the documents set for all companies, unless it has its own set for a type."), co["kept"])
holds("a greyed box says why when clicked and stays as it is: nothing is kept as a change",
      lambda: co["greyed"]["pv"]["pressed"] == "true" and co["greyed"]["draft"] is None and co["greyed"]["previews"] == 0
      and co["greyed"]["msgs"] == ["Payment Voucher is issued by SQL Account, so it isn't asked for while EXB is Kept here. Its box stays as it is."], co["greyed"])
holds("a change for a company says it gives the company its own set; it is saved for that company alone, the greyed box kept in it",
      lambda: co["fresh"]["warnings"] == [f"Saving gives EXB its own set for Utility / telco from {MONTH(M0)}."] and len(co["own"]["sent"]) == 1 and co["own"]["sent"][0]["entity_id"] == EXB
      and co["own"]["sent"][0]["changes"][0]["docs"] == ["invoice", "pv", "bank", "approval"] and co["own"]["every"][0] == co["own"]["every"][1]
      and co["own"]["mine"]["own"] is True and co["own"]["for"] == "Its own setFollow all companies again" and co["own"]["since"].startswith(f"Since {MONTH(M0)}"), co["own"])
holds("Follow all companies again waits for Save: the row shows what all companies need, changed boxes marked, and its boxes are locked",
      lambda: co["button"]["text"] == "Follow all companies again" and co["button"]["label"] == "Follow all companies again for Utility / telco"
      and co["pending"]["for"] == "Will follow all companiesKeep its own set" and co["pending"]["since"].startswith("Follows all companies") and co["pending"]["changed"] == ["utility.approval"]
      and co["pending"]["approval"]["off"] is True and has(co["pending"]["status"], "1 unsaved change") and co["pending"]["focus"] == co["button"]["id"]
      and co["pending"]["previews"]["changes"][0]["docs"] is None, co["pending"])
holds("...a click on a locked box says why; Keep its own set takes it back; ticking first and then following drops the ticks",
      lambda: co["locked"]["msgs"] == ["Utility / telco will follow all companies again when you save. Press Keep its own set to change its boxes."] and co["locked"]["draft"]["edits"] == {}
      and co["undone"]["draft"] is None and co["undone"]["approval"]["pressed"] == "true" and co["undone"]["for"] == "Its own setFollow all companies again" and co["undone"]["focus"] == co["button"]["id"]
      and co["replaced"]["draft"]["edits"] == {} and co["replaced"]["draft"]["follows"] == {"utility": True} and co["replaced"]["invoice"] == "true", (co["locked"], co["undone"], co["replaced"]))
holds("...saved with another change in the same request: the follow sent as no documents, and the company follows all companies again",
      lambda: len(co["followed"]["sent"]) == 1 and [(x["payment_type"], x["docs"] is None) for x in co["followed"]["sent"][0]["changes"]] == [("utility", True), ("claim", False)]
      and co["followed"]["for"] == "Follows all companies" and co["followed"]["mine"]["own"] is False and co["followed"]["follow"] is False, co["followed"])
holds("for every company, a type a company has its own set for is marked, and a change to it says it doesn't reach that company",
      lambda: co["marked"] == {"claim": "EXB has its own set", "utility": ""} and co["reach"] == ["EXB has its own set for Staff claim, so this change doesn't reach it."], (co["marked"], co["reach"]))
holds("a company kept in SQL Account greys nothing",
      lambda: co["sql"] == {"note": "EXA is Kept in SQL Account: its payment vouchers are issued by SQL Account and read in on the SQL import page.", "off": 0, "na": 0}, co["sql"])
holds("a company gone out of use takes its boxes with it, and says so: they are never saved for every company",
      lambda: co["gone"]["scope"] == "all" and co["gone"]["changed"] == [] and co["gone"]["draft"] is None and co["gonePosts"] == 0
      and co["gone"]["msgs"] == [f"The boxes that weren't saved were for EXB from {MONTH(M0)}, which can't be shown now, so they were dropped."], co["gone"])

# ---------- warnings ----------
wn = o["warnings"]
holds("a type with a later set says that saving from an earlier month replaces it too, and so it does",
      lambda: wn["later"]["warnings"] == [f"Saving from {MONTH(M0)} also replaces the later set of Consultant fee (from {MONTH(M2)})."] and has(wn["later"]["since"], f"Changes from {MONTH(M2)}")
      and "tst_memo" in wn["laterSets"]["docs"] and wn["laterSets"]["later"] == [], (wn["later"], wn["laterSets"]))
holds("a change to Other names the types that need what Other needs; one of them changed too gets what its own row says",
      lambda: wn["other"]["warnings"] == [f"{ODD_TYPE} and Test old kind have no set of their own and need what Other needs, so this changes them too."]
      and wn["otherAndFollower"] == ["Test old kind has no set of its own and needs what Other needs, so this changes it too."]
      and wn["otherSaved"]["odd"] == ["invoice", "pv", "bank", "approval"] and wn["otherSaved"]["other"] == ["invoice", "pv", "bank", "tst_memo"]
      and wn["otherSaved"]["oldKind"]["follows_other"] is True and wn["otherSaved"]["oldKind"]["docs"] == wn["otherSaved"]["other"], (wn["other"], wn["otherAndFollower"], wn["otherSaved"]))
holds("a company that was to follow all companies again says when, on its row and before Save, which would do away with it",
      lambda: has(wn["backNote"], f"Changes from {MONTH(M2)}")
      and f"EXB was to follow all companies again for Director allowance from {MONTH(M2)}. Saving from {MONTH(M0)} does away with that: its own set carries on." in wn["back"], (wn["backNote"], wn["back"]))
holds("a company's new set says it also stands where all companies have another set later; for every company there is no such line",
      lambda: f"All companies have another set for Money received from {MONTH(M3)}. EXB keeps its own set then too." in wn["theirs"]
      and f"Saving gives EXB its own set for Money received from {MONTH(M0)}." in wn["theirs"] and not any("keeps its own set" in x for x in wn["theirsAll"]), (wn["theirs"], wn["theirsAll"]))
sd = o["stoppedDoc"]
holds("a document no longer in use that a set asks for keeps its column, marked Not in use, its boxes locked",
      lambda: sd["col"]["box"]["pressed"] == "true" and sd["col"]["box"]["off"] is True and sd["col"]["box"]["label"].endswith("required, no longer in use") and sd["col"]["head"][1].endswith("Not in use")
      and sd["locked"]["draft"] is None and "no longer in use" in sd["locked"]["msgs"][0], sd["col"])
holds("...and a changed row says it is left out of the new set, and leaves it out",
      lambda: sd["changed"]["warnings"] == [f"{ODD_DOC} is no longer in use, so it is left out of the new set of Rental."] and sd["changed"]["docs"] == ["invoice", "bank", "approval"], sd["changed"])

# ---------- earlier sets and keys ----------
mo = o["more"]
holds("Earlier sets opens a type's dated sets, with who they are for and the one in force, and closes them; opening them is not a change",
      lambda: mo["closed"] == {"expanded": "false", "label": "Earlier sets for Utility / telco", "rows": 0} and mo["open"]["expanded"] == "true" and mo["open"]["focus"] and mo["open"]["draft"] is None
      and has(mo["open"]["text"], "Earlier sets for Utility / telco", f"From {MONTH(M0)}, all companies: ", f"(in force in {MONTH(M0)})", f"Until {MONTH(db.shift_month(M0, -1))}, all companies: ")
      and mo["open"]["text"].count("(in force in") == 1 and has(mo["start"], "No earlier sets: this set has been in force from the start.", "From the start, all companies: ") and mo["shut"] == 2, mo["open"])
ks = mo["keys"]
holds("the arrow keys move from box to box and stop at the edges, Home and End go to the row's ends; Alt with an arrow is left to the browser",
      lambda: [m[1] for m in ks["moves"]] == ["rq-c-0-1", "rq-c-1-1", "rq-c-1-0", "rq-c-0-0", f"rq-c-0-{ks['cols'] - 1}", f"rq-c-0-{ks['cols'] - 1}", "rq-c-0-0", "rq-c-0-0", "rq-c-0-0"]
      and all(m[2] for m in ks["moves"]) and ks["alt"] is False, ks)

# ---------- while it saves ----------
sv = o["saving"]
holds("while a save is on its way: Saving…, the pickers, buttons, reason and boxes are off, and nothing more is changed or sent",
      lambda: sv["during"]["save"] == "Saving…" and sv["during"]["busy"] == "true" and sv["during"]["disabled"] == [True] * 5 and sv["during"]["off"] and has(sv["during"]["status"], "Saving…")
      and sv["blocked"] == {"posts": 1, "changed": ["rental.tst_memo"]} and sv["done"]["posts"] == 1 and sv["done"]["changed"] == [] and sv["done"]["off"] is False, (sv["during"], sv["blocked"]))
holds("leaving while it saves says it is being saved, and Stay here stays",
      lambda: [(a["title"], a["yes"], a["no"]) for a in sv["stay"]["asks"]] == [("Leave while saving?", "Leave", "Stay here")] and sv["stay"]["view"] == "setup" and sv["stay"]["grid"], sv["stay"])
holds("left and then saved: a message says so with what it did, and the page on show is neither read again nor drawn over",
      lambda: sv["away"]["view"] == "overview" and "Overview page" in sv["away"]["main"] and sv["away"]["toasts"] == [f"Required documents saved from {MONTH(M0)}. No open payment changes status."]
      and sv["away"]["reads"] == 0 and sv["away"]["saving"] is False and sv["away"]["draft"] is None, sv["away"])
holds("left and then refused: a message says it wasn't saved",
      lambda: sv["awayRefused"]["toasts"] == [f"Required documents wasn't saved: What is required from {MONTH(M0)} for Rental changed after this page read it."] and "Overview page" in sv["awayRefused"]["main"], sv["awayRefused"])
holds("opened again while it saves: the grid waits for it, then shows what was saved and says so",
      lambda: sv["back"]["mid"] == {"off": True, "save": "Saving…"} and sv["back"]["memo"]["pressed"] == "true" and sv["back"]["memo"]["changed"] is False and sv["back"]["off"] is False
      and sv["back"]["save"] == f"Save from {MONTH(M0)}" and sv["back"]["result"] == ["Saved. No open payment changes status.Dismiss"], sv["back"])

# ---------- a month filed while boxes wait ----------
fl = o["filed"]
holds("a month filed while the boxes wait: the save is refused with the server's words, the boxes and reason stay, and the month is shown as filed",
      lambda: fl["refused"]["posts"] == 1 and fl["refused"]["msgs"][0] == f"{MONTH(M0)} is filed, and filed months never change. Choose {MONTH(M1)} or later. Nothing was saved."
      and fl["refused"]["changed"] == ["rental.approval"] and fl["refused"]["reason"] == "Late change" and fl["refused"]["month"] == M0 and fl["refused"]["option"] == [f"{MONTH(M0)} (filed)"]
      and fl["refused"]["note"] == f"{MONTH(M0)} is filed, and filed months never change. Choose {MONTH(M1)} or later.", fl["refused"])
holds("...Save from it sends nothing; another month is picked through Discard your changes?, and the filed one can't be picked",
      lambda: fl["again"]["posts"] == 0 and fl["again"]["previews"] == 0 and fl["again"]["changed"] == ["rental.approval"] and "is filed" in fl["again"]["msgs"][0]
      and fl["moved"]["month"] == M1 and fl["moved"]["changed"] == [] and fl["moved"]["months"][0] == [M0, f"{MONTH(M0)} (filed)", True] and fl["moved"]["months"][1] == [M1, MONTH(M1), False], (fl["again"], fl["moved"]))
holds("a month picked that the company chosen next has filed gives way to the month offered, and says so",
      lambda: fl["fallback"] == {"picked": M0, "month": M1, "msgs": [f"{MONTH(M0)} can't be picked now that a month is filed, so the grid shows {MONTH(M1)}."],
                                 "reads": [f"/api/setup/required?entity={EXA}&month={M0}", f"/api/setup/required?entity={EXA}"]}, fl["fallback"])
holds("nothing was thrown that no one heard", lambda: o["unheard"] == [], o["unheard"])

# ---------- narrow screens ----------
css = (Path(__file__).resolve().parents[1] / "static" / "app.css").read_text(encoding="utf-8")
narrow = css[css.find("/* Setup › Required documents ("):]
holds("the grid scrolls sideways in its own frame with the payment types held in place, narrower under 700 pixels, never widening the page",
      lambda: re.search(r"\.rq-wrap \{[^}]*overflow-x: auto", narrow) and re.search(r"\.rq-table \.rq-type \{[^}]*position: sticky; left: 0;[^}]*background: var\(--surface\)", narrow)
      and re.search(r"@media \(max-width: 700px\) \{[^@]*\.rq-table \.rq-type \{ width: 128px", narrow) and re.search(r"\.rq \{[^}]*grid-template-columns: minmax\(0, 1fr\)", narrow))

shutil.rmtree(tmp, ignore_errors=True)

if failed:
    print(f"\n{len(failed)} FAILED, {len(passed)} passed")
    sys.exit(1)
print(f"\nrequired_matrix_page_test: all {len(passed)} checks passed")
