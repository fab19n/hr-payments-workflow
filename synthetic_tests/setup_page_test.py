"""The Setup pages (slice 9a), on made-up records: the real server's answers drive the page script, run in Node on a small stand-in for
the page (no browser), so the pages' own HTML is what is checked.

Checks: the Setup menu (the groups, glyphs, the Recurring payments link and its note, Matching words left out for a company Kept
here, a group the server adds later shown without a change here); Matching words for a company Kept here (the card for an old
link, the Overview and the toast on switching company); the shared list (head, sentence, toolbar with Show stopped and Show deleted,
row sub lines, Used by, status, the empty states, 25 rows at a time and Show 25 more, the tab strip of two sections, Paste a list);
the Books column and the labels Kept in SQL Account and Kept here; the record dialog (groups, Where used, In use, History, the
printed settings only for a company Kept in SQL Account); Stop using, Use again and Delete asking why, in place; Show deleted and the
Put it back dialog; Open Setup from a print note opening that company's own dialog; Move setup (its Everything sentence, its counts)
and First run (welcome page, Where are the books kept?, its counts the same table as Move setup's, add a company); the 520-pixel rule
for the form.

Run: .venv\\Scripts\\python -m synthetic_tests.setup_page_test
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-setup-page-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_files, app_source  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}],
     "payees": [{"name": "Test Payee", "category": "salary", "amount": 3000, "due_day": 28, "month_offset": 1}]},
    {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed, failed = [], []
from synthetic_tests.flags import KEEP_GOING, keep_going  # noqa: E402  (one place for the flag, so a check of it is about the flag the tests use)


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
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


EXA, EXB = [r["id"] for r in q("SELECT id FROM entities ORDER BY id")]
# more records: a stopped account, 30 customers and suppliers, a statutory account that is stopped, a deleted account, a deleted type
# whose key was taken since
old = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Old savings", "bank": "Example Bank", "number": "000-999", "currency": "MYR"}})
call("post", f"/api/setup/accounts/{old['id']}/stop", json={"reason": "Closed by the bank"})
for n in range(1, 31):
    call("post", "/api/setup/parties", json={"entity_id": EXA, "fields": {"name": f"Test Party {n:02d}", "kind": "supplier", "sql_code": f"400-T{n:03d}"}})
for code, name in (("420-1001", "EPF payable"), ("900-E001", "EPF employer expense")):
    call("post", "/api/setup/gl_accounts", json={"entity_id": EXA, "fields": {"code": code, "name": name}})
st = call("post", "/api/setup/statutory_accounts", json={"entity_id": EXA, "fields": {"kind": "epf", "label": "EPF (KWSP)", "payable_code": "420-1001", "employer_code": "900-E001"}})
call("post", f"/api/setup/statutory_accounts/{st['id']}/stop", json={"reason": "Not used any more"})
temp = call("post", "/api/setup/accounts", json={"entity_id": EXB, "fields": {"label": "Temp stop", "bank": "Example Bank", "currency": "MYR"}})
TEMP_BEFORE = call("get", f"/api/setup/accounts/{temp['id']}")
call("post", f"/api/setup/accounts/{temp['id']}/stop", json={"reason": "Not needed"})
TEMP_AFTER = call("get", f"/api/setup/accounts/{temp['id']}")
spare = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Spare", "bank": "Example Bank", "currency": "MYR"}})
call("delete", f"/api/setup/accounts/{spare['id']}", json={"reason": "Opened by mistake"})
t1 = call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form"}})
call("delete", f"/api/setup/doc_types/{t1['id']}", json={"reason": "Wrong name"})
call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form again"}})

dco = call("post", "/api/setup/entities", json={"fields": {"code": "EXD", "name": "Example Delta Ltd", "uses_sql": False}})
call("delete", f"/api/setup/entities/{dco['id']}", json={"reason": "Added by mistake"})
gsp = call("post", "/api/setup/gl_accounts", json={"entity_id": EXA, "fields": {"code": "999-001", "name": "Spare account"}})
call("delete", f"/api/setup/gl_accounts/{gsp['id']}", json={"reason": "Not needed"})

main = [r for r in call("get", f"/api/setup/accounts?entity={EXA}")["rows"] if r["label"] == "Main"][0]
salary = [r for r in call("get", "/api/setup/payment_types")["rows"] if r["key"] == "salary"][0]
GET = {}


def fx(path):
    GET[path] = call("get", path)
    return GET[path]


for p in ("/api/meta", "/api/setup/types", "/api/setup/entities", f"/api/setup/accounts?entity={EXA}", f"/api/setup/accounts?entity={EXB}",
          f"/api/setup/parties?entity={EXA}", f"/api/setup/gl_accounts?entity={EXA}", f"/api/setup/statutory_accounts?entity={EXA}",
          "/api/setup/payment_types", "/api/setup/doc_types", "/api/setup/guess_words", f"/api/setup/accounts/{main['id']}",
          f"/api/setup/accounts/{old['id']}", f"/api/setup/entities/{EXA}", f"/api/setup/entities/{EXB}", f"/api/setup/entities/{EXA}/print",
          f"/api/setup/entities/{EXA}/sql-names", f"/api/setup/restore?kind=accounts&entity={EXA}", "/api/setup/restore?kind=doc_types",
          f"/api/setup/payment_types/{salary['id']}", "/api/setup/import", "/api/setup/required?entity=", f"/api/setup/required?entity={EXA}", f"/api/setup/required?entity={EXB}",
          f"/api/setup/parties?entity={EXB}", "/api/setup/restore?kind=entities", f"/api/setup/restore?kind=gl_accounts&entity={EXA}",
          f"/api/setup/checklist?entity={EXA}", "/api/setup/reminders", "/api/setup/settings", f"/api/setup/restore?kind=checklist&entity={EXA}", "/api/setup/restore?kind=reminders"):
    fx(p)
GET[f"/api/setup/accounts/{temp['id']}"] = TEMP_BEFORE
restored = GET[f"/api/setup/restore?kind=accounts&entity={EXA}"]["rows"][0]
taken = GET["/api/setup/restore?kind=doc_types"]["rows"][0]
PREVIEW = call("post", f"/api/setup/restore/{restored['row_id']}", json={"preview": True})
POST = {
    f"/api/setup/restore/{restored['row_id']}?preview": {"status": 200, "body": PREVIEW},
    f"/api/setup/restore/{restored['row_id']}": {"status": 200, "body": {"label": "Bank account", "same_id": True, "id": spare["id"], "kind": "accounts"}},
    f"/api/setup/restore/{taken['row_id']}?preview": {"status": 400, "body": {"error": taken["problem"]}},
    f"/api/setup/accounts/{old['id']}/use": {"status": 200, "body": {"record": {}}},
    f"/api/setup/accounts/{main['id']}/stop": {"status": 400, "body": {"error": "This is the company's cash book account. Make another account the cash book first."}},
}
EXD_ROW = GET["/api/setup/restore?kind=entities"]["rows"][0]["row_id"]   # the deleted company: its real Put it back preview names it EXD · Example Delta Ltd
POST[f"/api/setup/restore/{EXD_ROW}?preview"] = {"status": 200, "body": call("post", f"/api/setup/restore/{EXD_ROW}", json={"preview": True})}
check("the fixtures are the real server's: a deleted account to put back, a deleted type whose key was taken, 30 parties",
      restored["name"] == "Spare" and taken.get("problem") and len(GET[f"/api/setup/parties?entity={EXA}"]["rows"]) == 30)

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [fxPath, ...files] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, calls = [], listeners = {};
const makeEl = id => { const set = new Set(); return ({ id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", className: "", dataset: {}, attrs: {}, children: [],
  classList: { add: (...c) => c.forEach(x => set.add(x)), remove: (...c) => c.forEach(x => set.delete(x)), toggle() {}, contains: c => set.has(c) }, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
  removeAttribute(k) { delete this.attrs[k]; }, focus() { document.activeElement = this; }, querySelectorAll: () => [], querySelector: () => null, closest: () => null,
  contains: () => false, after() {}, isConnected: true, addEventListener() {}, removeEventListener() {} }); };
const el = id => els[id] ||= makeEl(id);
const document = { activeElement: null, body: { classList: { add() {}, remove() {} } },
  querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : s === ".setup-nav .sn.on" ? (((els.main || {}).nav || {}).active || null)
    : (m => m ? (sandbox.__tabs || {})[m[1]] || null : null)(/^\[role="tab"\]\[data-setup-kind="([a-z_]+)"\]$/.exec(s)),
  querySelectorAll: () => [], getElementById: id => els[id] || null, addEventListener(t, f) { (listeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  const method = init.method || "GET", body = init.body && typeof init.body === "string" ? JSON.parse(init.body) : null;
  if (method !== "GET") {
    calls.push([method, path, body]);
    const held = postDelays[path]; if (held) await new Promise(r => setTimeout(r, Array.isArray(held) ? held.shift() || 0 : held));   // a change that takes its time
    if ((FX.fail || {})[path]) throw new TypeError("Failed to fetch");
    const hit = FX.post[path + (body && body.preview ? "?preview" : "")] || { status: 200, body: { ok: true } };
    return { ok: hit.status < 400, status: hit.status, json: async () => hit.body };
  }
  if ((FX.fail || {})[path]) throw new TypeError("Failed to fetch");   // the app is not running
  if (onGet) onGet(path);
  const slow = delays[path]; if (slow) await new Promise(r => setTimeout(r, Array.isArray(slow) ? slow.shift() || 0 : slow));
  if (lateFail[path] > 0) { lateFail[path]--; throw new TypeError("Failed to fetch"); }   // it fails once it has taken its time
  if ((FX.bad || {})[path]) return { ok: true, status: 200, json: async () => { throw new SyntaxError("not JSON"); } };   // the app answers, but not with the records
  if ((FX.status || {})[path]) return { ok: false, status: FX.status[path], json: async () => ({ error: "The server could not read the records." }) };   // the app answers with a failure
  const hit = FX.get[path];
  if (hit === undefined) return { ok: false, status: 404, json: async () => ({ error: "no fixture for " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(hit)) };
}
const scrolls = [];   // what the window was scrolled to: a page drawn again must not move it
const win = { matchMedia: () => ({ matches: true }), location: { hash: "#/admin/setup", replace(v) { this.hash = v; } }, scrollX: 0, scrollY: 0,
  scrollTo(...a) { scrolls.push(a); [this.scrollX, this.scrollY] = a; }, addEventListener() {}, print() {} };
let onGet = null;   // called with the path of each read: what the page looks like while it is waiting for the records
const delays = {};  // path -> milliseconds a read of it takes (or a list of them, one for each read in turn)
const lateFail = {};  // path -> how many of its next reads fail (after the delay)
const postDelays = {};  // path -> milliseconds a change sent to it takes (or a list of them, one for each in turn)
const sandbox = { document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {} }, window: win, navigator: {}, __el: el, __calls: calls, __listeners: listeners,
  __btn: { closest: () => ({ after() {} }), getAttribute: () => "false", isConnected: true } };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = {};
const tryit = async (name, fn) => { try { out[name] = await fn(); } catch (e) { out[name] = { error: String(e && e.stack || e).slice(0, 400) }; } };
(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));
  run(`state.meta = ${JSON.stringify(FX.get["/api/meta"])}; state.month = "2026-11"; state.day = dayKey(); state.entity = ${FX.EXA};
    globalThis.__realRender = render; menuNextEnsure = () => {};
    globalThis.__toasts = []; { const was = toastShow; toastShow = (msg, bad, opts) => { __toasts.push({ msg, bad, opts }); return was(msg, bad, opts); }; }
    renderNav = () => {}; render = async () => { __calls.push(["render"]); }; navigate = async place => { __calls.push(["navigate", place]); return true; };
    globalThis.click = async (dataset, extra = {}) => { const b = { dataset, tagName: "BUTTON", id: "", className: "", getAttribute: () => null, ...extra }; b.closest = () => b;
      const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; for (const f of __listeners.click || []) await f(ev); };`);
  const main = el("main"), box = () => el("setupMain");
  // The menu is a new element (scrolled to the top) each time the page is drawn, as in a browser; its item on show records what is done to it.
  // The menu has a frame 400 high at the top of the window; its item on show sits at 700 (Move setup), 420 (Required documents) or 80 in its content,
  // and each scrollTop set records whether the section had been written by then.
  const navOf = html => { const m = /class="sn on" data-setup-kind="([a-z_]+)"/.exec(html);
    if (!/class="setup-nav/.test(html)) return null;
    const kind = m && m[1], at = kind === "move" ? 700 : kind === "required" ? 420 : 80;
    let st = 0;
    const nav = { sets: [], kind, clientHeight: 400, clientTop: 0, getBoundingClientRect: () => ({ top: 100, height: 400 }),
      get scrollTop() { return st; }, set scrollTop(v) { st = v; nav.sets.push([v, smWrites > 0]); }, userScroll(v) { st = v; },
      active: { scrolled: [], scrollIntoView(o) { this.scrolled.push(o); }, focus() { document.activeElement = this; }, getBoundingClientRect: () => ({ top: 100 + at - st, height: 40 }) },
      querySelector(s) { return s === ".sn.on" ? this.active : null; } };
    return nav; };
  // The page is 700 high and 2500 more while its section has something in it, or as tall as main is held at (style.minHeight), in a window 600 high:
  // a short page clamps the window's scroll, as a browser does. Each draw's section place is a new element; the old one is off the page, and counts
  // what is written into it (nothing should be once it is overtaken, or once the page it was drawn into has been replaced).
  let mainHtml = "", smHtml = "", smWrites = 0, mainSets = 0;
  const seenY = [];
  const pageH = () => Math.max(700 + (smHtml.length > 200 ? 2500 : 0), parseInt(main.style._h) || 0);
  const clamp = () => { const max = Math.max(0, pageH() - 600); if (win.scrollY > max) win.scrollY = max; seenY.push(win.scrollY); };
  const newSm = (html, on) => { const sm = makeEl("setupMain"); sm.writes = 0; sm.isConnected = on; let h = html;
    Object.defineProperty(sm, "innerHTML", { get: () => h, set(v) { h = v; sm.writes++; if (els.setupMain === sm && sm.isConnected) { smHtml = v; smWrites++; clamp(); } } }); return sm; };
  main.style = { _h: "", log: [], get minHeight() { return this._h; }, set minHeight(v) { this._h = v; this.log.push(v); clamp(); } };
  main.getBoundingClientRect = () => ({ height: pageH() });
  Object.defineProperty(main, "innerHTML", { get: () => mainHtml, set(v) {
    mainHtml = v; mainSets++; const m = /id="setupMain">([\s\S]*)<\/div><\/div>$/.exec(v);
    if (els.setupMain) els.setupMain.isConnected = false;
    els.setupMain = newSm(m ? m[1] : "", !!m); smHtml = m ? m[1] : ""; smWrites = 0; clamp(); main.nav = navOf(v); } });
  els.setupMain = newSm("", true);
  main.nav = null;
  // The dialog's inputs: what is written into #drawer makes its input, select and textarea elements, with the values the HTML gives (a test types into them,
  // and drawerInputs() reads them). Only while drawerInputsOn: the other scenarios leave the dialog without inputs.
  let drawerInputsOn = false, drawerHtml = "";
  {
    const d = el("drawer"), tags = () => [...drawerHtml.matchAll(/<(?:input|select|textarea)\b[^>]*?\bid="([^"]+)"[^>]*>/g)];
    const un = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
    Object.defineProperty(d, "innerHTML", { configurable: true, get: () => drawerHtml, set(v) { drawerHtml = v;
      if (drawerInputsOn) for (const [tag, id] of tags()) { const e = el(id); e.type = (/\btype="([^"]+)"/.exec(tag) || [])[1] || "text"; e.value = un((/\bvalue="([^"]*)"/.exec(tag) || [])[1] || ""); e.checked = /\bchecked\b/.test(tag); } } });
    d.querySelectorAll = sel => drawerInputsOn && /^input\[id\]/.test(sel) ? [...new Set(tags().map(m => m[1]))].map(id => el(id)) : [];
  }
  main.querySelector = s => s === "#setupMain" ? (els.setupMain && els.setupMain.isConnected ? els.setupMain : null) : s === ".setup-nav" ? main.nav : s === ".setup-grid" ? ((m => m ? { dataset: { at: m[1] } } : null)(/class="setup-grid" data-at="([^"]*)"/.exec(mainHtml))) : null;
  const view = async (kind, entity) => {
    run(`state.entity = ${entity}; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false;`);
    await run(`viewSetup(__el("main"))`); await sleep(20); return { nav: main.innerHTML, page: box().innerHTML };
  };

  // the menu and a list: bank accounts of a company Kept in SQL Account
  out.accounts = await view("accounts", FX.EXA);
  out.groupsSql = run(`setupGroups().map(g => g.label)`);
  out.groupsHere = run(`state.entity = ${FX.EXB}; setupGroups().map(g => g.label)`);
  run(`state.entity = ${FX.EXA}`);
  // a group the server adds later (HR with slice 11) shows with no change here; a section the server does not have is left out
  run(`state.setup.types.groups.push(["HR", ["approvers", "nothere"]]); state.setup.types.kinds.approvers = { label: "Approvers", plural: "approvers", glyph: "approval", bespoke: true };`);
  out.groupsHr = run(`setupGroups().map(g => g.label + ":" + g.kinds.join(","))`);
  out.navHr = run(`setupNavHtml(state.setup.types, "accounts")`);
  run(`state.setup.types.groups.pop(); delete state.setup.types.kinds.approvers;`);

  // Matching words for a company Kept here: the card for an old link, and switching company to it from there
  const here = await view("guess_words", FX.EXB);
  out.hereCard = here.page; out.hereNav = here.nav;
  run(`state.entity = ${FX.EXA}; state.view = "setup"; state.setup.kind = "guess_words"`);
  out.tbPlace = run(`(() => { const r = tbPlace(${FX.EXB}); return { view: r.place.view, gone: r.gone, plural: r.plural }; })()`);
  run(`state.setup.kind = "accounts"`);
  out.tbPlaceOk = run(`(() => { const r = tbPlace(${FX.EXB}); return { view: r.place.view, gone: r.gone }; })()`);
  out.sqlWords = (await view("guess_words", FX.EXA)).page;

  out.entities = (await view("entities", FX.EXA)).page;
  const gl = FX.get[`/api/setup/gl_accounts?entity=${FX.EXA}`];
  FX.get[`/api/setup/gl_accounts?entity=${FX.EXA}`] = { rows: [] };
  out.emptyNone = (await view("gl_accounts", FX.EXA)).page;
  FX.get[`/api/setup/gl_accounts?entity=${FX.EXA}`] = gl;
  out.onlyStopped = (await view("statutory_accounts", FX.EXA)).page;
  const parties = await view("parties", FX.EXA);
  out.parties = parties.page;
  await run(`click({ setupMore: "parties" })`);
  out.partiesMore = run(`__el("setupList").innerHTML`);
  run(`listState("setup-parties").q = "no such party"; LIST_REDRAW["setup-parties"]()`);
  out.noMatch = run(`__el("setupList").innerHTML`);
  run(`listState("setup-parties").q = ""`);
  out.types = (await view("payment_types", FX.EXA)).page;

  // the record dialog
  await run(`openSetup("accounts", ${FX.MAIN})`); await sleep(20);
  out.dlgAccount = el("drawer").innerHTML; out.dlgClass = run(`$("#drawer").classList.contains("st-dlg")`);
  await run(`openSetup("payment_types", ${FX.SALARY})`); await sleep(20);
  out.dlgSystem = el("drawer").innerHTML;
  await run(`openSetup("accounts", ${FX.OLD})`); await sleep(20);
  out.dlgStopped = el("drawer").innerHTML;
  await run(`openSetup("accounts", "new")`); await sleep(20);
  out.dlgNew = el("drawer").innerHTML;
  await run(`state.entity = ${FX.EXA}; openSetup("entities", ${FX.EXA})`); await sleep(60);
  out.dlgSql = el("drawer").innerHTML; out.dlgSqlPrint = el("suPrint").innerHTML; out.dlgSqlNames = el("suNames").innerHTML;
  els.suPrint = undefined; els.suNames = undefined;
  await run(`openSetup("entities", ${FX.EXB})`); await sleep(60);
  out.dlgHere = el("drawer").innerHTML; out.dlgHerePrint = el("suPrint").innerHTML;

  // Stop using, Use again and Delete ask why, in place
  await run(`state.entity = ${FX.EXA}; openSetup("accounts", ${FX.MAIN})`); await sleep(20);
  calls.length = 0;
  await run(`setupAct("stop", __btn)`);
  out.whyShown = { hidden: el("setupWhy").hidden, go: el("su-why-go").textContent, note: el("su-why-note").innerHTML };
  el("su-reason").value = "";
  await run(`whySubmit()`);
  out.whyEmpty = { msg: el("su-why-msg").innerHTML, posts: calls.length };
  el("su-reason").value = "Closing the account.";
  await run(`whySubmit()`);
  out.whyRefused = { msg: el("su-why-msg").innerHTML, post: calls[calls.length - 1] };
  run(`hideWhy()`);
  out.whyHidden = { hidden: el("setupWhy").hidden, reason: el("su-reason").value };
  calls.length = 0;
  await run(`openSetup("accounts", ${FX.OLD})`); await sleep(20);
  await run(`setupAct("use", __btn)`); el("su-reason").value = "Needed again"; await run(`whySubmit()`);
  out.useAgain = calls.filter(x => x[0] === "POST");
  await run(`openSetup("accounts", ${FX.OLD})`); await sleep(20);
  calls.length = 0;
  await run(`setupAct("delete", __btn)`); out.deleteNote = el("su-why-note").innerHTML; out.deleteDanger = el("su-why-go").className;
  el("su-reason").value = "Opened by mistake"; await run(`whySubmit()`);
  out.deleted = { calls: calls.filter(x => x[0] === "DELETE"), toast: el("toast").textContent };

  // Show deleted and Put it back
  await view("accounts", FX.EXA);
  run(`state.setup.deleted = true`); await run(`drawDeleted("accounts")`);
  out.deletedAccounts = el("setupDeleted").innerHTML;
  await run(`drawDeleted("doc_types")`); out.deletedTypes = el("setupDeleted").innerHTML;
  calls.length = 0;
  await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20);
  out.putBack = { body: el("rsBody").innerHTML, eyebrow: el("rs-eyebrow").textContent, acts: el("rsActs").innerHTML };
  await run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`);
  out.putBackEmpty = { err: el("pb-why-err").innerHTML, posts: calls.filter(x => x[0] === "POST" && !(x[2] && x[2].preview)).length };
  el("pb-why").value = "It is the new account after all";
  await run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`);
  out.putBackDone = calls.filter(x => x[0] === "POST" && !(x[2] && x[2].preview));
  calls.length = 0;
  await run(`openRestore(${FX.TAKEN}, "Test form")`); await sleep(20);
  out.putBackRefused = el("rsBody").innerHTML;

  // Required documents for a company Kept here: the payment voucher is required where the rules say so, with no "posted here" choice
  run(`state.setup.kind = "required"; state.setup.reqScope = ${FX.EXB}`);
  await run(`setupRequired(__el("setupMain"))`);
  out.required = el("setupMain").innerHTML;
  run(`state.setup.reqScope = ${FX.EXA}`);
  await run(`setupRequired(__el("setupMain"))`);
  out.requiredSql = el("setupMain").innerHTML;
  run(`state.setup.reqScope = null`);

  // Open Setup from a print note: that company's own dialog
  calls.length = 0;
  run(`state.entity = ${FX.EXA}`);
  await run(`click({ invSetup: "1" })`);
  out.invSetup = calls.filter(x => x[0] === "navigate").map(x => x[1]);

  // Move setup: its Everything sentence, the import it refuses, and its counts; First run's counts are the same table
  FX.get["/api/setup/import"] = { empty: true, holding: [] };
  out.moveEmpty = (await view("move", FX.EXA)).page;
  FX.get["/api/setup/import"] = { empty: false, holding: [["companies", 3], ["bank accounts", 3], ["recurring payment", 1], ["months set up", 2]] };
  out.moveBlocked = (await view("move", FX.EXA)).page;
  const P = { what: "full", made: "2026-11-14T10:00:00", notes: ["Companies added later start with the file's starter checklist.", "The file holds: Bank account numbers, and the companies' registration, tax and employer numbers."],
    counts: [["general settings", 8], ["payment types", 15], ["document types", 18], ["companies", 4], ["printed company names", 0], ["bank accounts", 5], ["statutory account", 1], ["checklist items", 50], ["salary advances", 0]] };
  out.moveCounts = run(`(() => { state.setup.move = { payees: false, from: "", empty: true, holding: [], preview: ${JSON.stringify(P)}, name: "setup-2026-11-14.json", refused: "" }; return movePreviewHtml(); })()`);
  run(`state.view = "overview"; state.meta.entities = []; FR.preview = ${JSON.stringify(P)}; FR.name = "setup-2026-11-14.json"; FR.done = null; FR.addOpen = false;`);
  out.frDue = run(`firstRunDue()`); out.frCounts = run(`frHtml()`);
  out.frRows = run(`moveCounts(${JSON.stringify(P)})`);
  out.moveRefused = run(`moveRefusal("setup-everything.json", "This setup file was made by a newer version of the app.")`);
  // a file chosen: not JSON is said as it is; a file the server won't take carries its sentence and is marked refused
  calls.length = 0;
  sandbox.__bad = { text: async () => "this is not json" }; sandbox.__ok = { text: async () => JSON.stringify({ format: "hrp-setup" }) };
  FX.post["/api/setup/import?preview"] = { status: 400, body: { error: "This setup file was made by a newer version of the app." } };
  out.readBad = await run(`readSetupFile(__bad).then(() => "read", e => ({ message: e.message, refused: !!e.refused }))`);
  out.readRefused = await run(`readSetupFile(__ok).then(() => "read", e => ({ message: e.message, refused: !!e.refused }))`);
  out.readPosts = calls.map(x => [x[1], x[2].preview, Object.keys(x[2])]);
  FX.post["/api/setup/import?preview"] = { status: 200, body: P };
  out.readOk = await run(`readSetupFile(__ok).then(r => ({ counts: r.preview.counts.length, setup: r.setup.format }), e => e.message)`);
  run(`FR.preview = null; FR.file = null; FR.addOpen = true; FR.tried = false;`); out.frAdd = run(`frHtml()`);
  run(`FR.code = "abc"; FR.cname = "Example Gamma Ltd"; FR.kind = ""; FR.tried = false;`);
  calls.length = 0;
  await run(`frAddCompany()`);
  out.frNoKind = { posts: calls.length, tried: run(`FR.tried`), html: run(`frHtml()`) };
  run(`FR.kind = "here"`);
  await run(`frAddCompany()`);
  out.frPost = calls.filter(x => x[1] === "/api/setup/entities");
  out.frDone = run(`FR.done`); out.frDoneHtml = run(`frHtml()`);
  run(`FR.done = null; state.meta.entities = [{ id: 1, code: "EXA", active: 1 }]`); out.frDueAfter = run(`firstRunDue()`);

  FX.fail = {};
  await view("accounts", FX.EXA);   // the page's own copy of the sections (the scenarios before this one left none)
  const meta0 = JSON.parse(JSON.stringify(FX.get["/api/meta"]));
  run(`state.meta = ${JSON.stringify(meta0)}; state.entity = ${FX.EXA}; state.view = "setup"`);

  // 1. the page posts a words box left empty as an empty list: the server takes it as no words
  await tryit("partyPost", async () => {
    await run(`state.entity = ${FX.EXA}; openSetup("parties", "new")`); await sleep(20);
    const spec = run(`state.setup.types.kinds.parties.fields.map(f => f.key)`);
    for (const k of spec) { const e = el("su-" + k); e.value = ""; e.checked = false; }
    el("su-name").value = "Test Party"; el("su-kind").value = "supplier"; el("su-entity_id").value = String(FX.EXA);
    calls.length = 0;
    await run(`setupSave()`);
    return calls.filter(x => x[1] === "/api/setup/parties").map(x => x[2]);
  });

  // 3. a company Kept here that still has printed company names: only the names are listed, with Remove; the last one removed ends the section
  await tryit("hereNames", async () => {
    const path = `/api/setup/entities/${FX.EXB}/sql-names`, was = FX.get[path];
    FX.get[path] = { ready: true, names: [{ id: 7, name: "EXAMPLE SWITCHED LTD (2026)", confirmed_at: "2026-11-01T10:00:00", confirmed_by: "tester" }] };
    els.suPrint = undefined; els.suNames = undefined;
    await run(`state.entity = ${FX.EXA}; openSetup("entities", ${FX.EXB})`); await sleep(60);
    const r = { drawer: el("drawer").innerHTML, names: el("suNames").innerHTML, print: el("suPrint").innerHTML };
    FX.post[`/api/setup/entities/${FX.EXB}/sql-names/7`] = { status: 200, body: { removed: "EXAMPLE SWITCHED LTD (2026)", ready: true, names: [] } };
    sandbox.__nb = { dataset: { confirm: "1", sqlNameRemove: "7", sqlName: "EXAMPLE SWITCHED LTD (2026)" }, textContent: "" };
    calls.length = 0;
    await run(`removeSqlName(__nb)`);
    r.removed = calls.filter(x => x[0] === "DELETE").map(x => x[1]); r.after = el("suNames").innerHTML;
    FX.get[path] = was;
    return r;
  });

  // 4. the stopped note once: a stopped record's dialog, and the dialog drawn again right after Stop using
  await tryit("stopNote", async () => {
    const path = `/api/setup/accounts/${FX.TEMP}`, before = FX.get[path];
    await run(`state.entity = ${FX.EXB}; openSetup("accounts", ${FX.TEMP})`); await sleep(20);
    const r = { open: el("drawer").innerHTML };
    await run(`setupAct("stop", __btn)`);
    FX.get[path] = FX.TEMP_AFTER;
    el("su-reason").value = "Not needed"; await run(`whySubmit()`); await sleep(40);
    r.afterStop = el("drawer").innerHTML;
    FX.get[path] = before; run(`state.entity = ${FX.EXA}`);
    return r;
  });

  // 5 and 6. First run: a file of rules alone is not an install ready to use; a failing network leaves the page usable
  const withCompanies = list => { FX.get["/api/meta"] = { ...meta0, entities: list }; };
  const co = (id, code, active) => ({ id, code, name: "Example " + code, uses_sql: 0, active, accounts: [] });
  const setFile = (what, counts) => run(`state.view = "overview"; FR.file = { format: "hrp-setup" }; FR.preview = ${JSON.stringify({ what, made: "2026-11-14T10:00:00", counts, notes: [] })}; FR.name = "setup.json"; FR.busy = ""; FR.done = null; FR.note = null; FR.why = "";`);
  await tryit("frTemplate", async () => {
    withCompanies([]); setFile("template", [["payment types", 15]]); calls.length = 0;
    await run(`frImport()`); const html = run(`frHtml()`);
    return { done: run(`FR.done`), note: run(`FR.note`), due: run(`firstRunDue()`), html, posts: calls.filter(x => x[1] === "/api/setup/import").length };
  });
  await tryit("frCompanies", async () => {
    const r = {};
    withCompanies([co(1, "EXA", 1), co(2, "EXB", 1), co(3, "EXC", 0)]); setFile("full", [["companies", 3]]); await run(`frImport()`);
    r.some = { done: run(`FR.done`), note: run(`FR.note`), html: run(`frHtml()`) };
    withCompanies([co(1, "EXA", 1), co(2, "EXB", 1)]); setFile("full", [["companies", 2]]); await run(`frImport()`);
    r.none = run(`FR.done`);
    withCompanies([co(1, "EXA", 0)]); setFile("full", [["companies", 1]]); await run(`frImport()`);
    r.one = run(`FR.done`);
    // steps never link to "#/": with no address they are grey
    run(`state.meta.entities = []; FR.done = { title: "x", body: "y" }; FR.note = null`);
    r.noCompany = run(`frHtml()`);
    return r;
  });
  await tryit("frFailImport", async () => {
    withCompanies([]); setFile("full", [["companies", 2]]); run(`FR.why = "A reason I typed"`); FX.fail = { "/api/setup/import": true };
    const threw = await run(`frImport().then(() => "ok", e => e.name)`); FX.fail = {};
    return { threw, busy: run(`FR.busy`), why: run(`FR.why`), kept: run(`!!FR.preview`), html: run(`frHtml()`) };
  });
  await tryit("frFailAdd", async () => {
    run(`FR.preview = null; FR.file = null; FR.addOpen = true; FR.tried = false; FR.code = "ABC"; FR.cname = "Example Co"; FR.reg = ""; FR.kind = "sql"; FR.busy = ""; FR.done = null; FR.note = null`);
    FX.fail = { "/api/setup/entities": true };
    const threw = await run(`frAddCompany().then(() => "ok", e => e.name)`); FX.fail = {};
    const r = { threw, busy: run(`FR.busy`), html: run(`frHtml()`), open: run(`FR.addOpen`) };
    // the company was added but the records could not be read again: the page is usable
    withCompanies([co(1, "EXA", 1)]); FX.fail = { "/api/meta": true };
    run(`FR.busy = ""; FR.code = "ABC"; FR.cname = "Example Co"; FR.kind = "sql"`);
    r.threwMeta = await run(`frAddCompany().then(() => "ok", e => e.name)`); FX.fail = {}; r.busyMeta = run(`FR.busy`);
    return r;
  });
  FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.addOpen = false; FR.done = null; FR.note = null; FR.saved = null; FR.code = ""; FR.cname = ""; FR.kind = ""; FR.tried = false`);

  // slice 9c: First run's import reason is filled in from the file chosen; what is sent is what the box shows
  await tryit("frReason", async () => {
    const r = {}, P = { what: "full", made: "2026-11-14T10:00:00", counts: [["companies", 1]], notes: [] };
    FX.post["/api/setup/import?preview"] = { status: 200, body: P };
    withCompanies([]);
    run(`globalThis.__realPick = pickFile; pickFile = async () => [__file]`);
    const pick = async name => { sandbox.__file = { name, text: async () => JSON.stringify({ format: "hrp-setup" }) }; el("fr-why").value = "";
      run(`state.view = "overview"; FR.busy = ""; FR.done = null; FR.note = null; FR.saved = null; FR.preview = null; FR.file = null`); await run(`frPick()`); };
    const box = () => (/<input id="fr-why"[^>]*? value="([^"]*)"/.exec(run(`frHtml()`)) || [])[1];
    const typeIt = v => { el("fr-why").value = v; for (const f of listeners.input || []) f({ target: el("fr-why") }); };
    const send = async () => { calls.length = 0; await run(`frImport().catch(e => e.name)`); return calls.filter(x => x[1] === "/api/setup/import" && !x[2].preview).map(x => x[2].reason); };
    try {
      await pick("Setup everything 2026-11-14.json"); r.shown = box(); r.sentUntouched = await send();
      await pick("setup.json"); typeIt("Moved from the old PC"); r.editedShown = box(); r.sentEdited = await send();
      r.emptied = [];
      for (const gone of ["", "   "]) {
        await pick("Office setup.json"); typeIt(gone);
        FX.fail = { "/api/setup/import": true };   // the app can't be reached: the box shows what was sent
        const first = await send(); FX.fail = {};
        r.emptied.push({ first, box: box(), again: await send() });
      }
      FX.post["/api/setup/import"] = { status: 400, body: { error: "This setup file was made by a newer version of the app." } };
      await pick("first.json"); typeIt("About the first file"); await send(); delete FX.post["/api/setup/import"];
      await pick("second.json"); r.afterRefusal = box();
      typeIt("About the second file"); await run(`click({ frCancelImport: "1" })`); await pick("third.json"); r.afterCancel = box(); r.sentThird = await send();
      const long = "\u{1F600}".repeat(300) + ".json";
      await pick(long); const shownLong = run(`FR.why`); r.long = { shown: shownLong, sent: await send(), units: shownLong.length,
        whole: !/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(shownLong), max: (/<input id="fr-why"[^>]*maxlength="(\d+)"/.exec((await pick("a.json"), run(`frHtml()`))) || [])[1] };
      await pick(`a"<b>&.json`); r.escaped = run(`frHtml()`);
    } finally { run(`pickFile = __realPick; FR.preview = null; FR.file = null; FR.why = ""; FR.name = ""; FR.refused = ""; FR.error = ""; FR.done = null; FR.note = null`); delete FX.post["/api/setup/import"]; FX.fail = {}; }
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"`);
    return r;
  });

  // 8. the rows shown stay shown across a redraw; they start again with another section or company
  await tryit("moreKept", async () => {
    const count = h => (h.match(/class="st-row/g) || []).length, r = {};   // the page drawn whole, or the list alone once Show more has redrawn it
    await view("parties", FX.EXA); r.first = count(box().innerHTML);
    await run(`click({ setupMore: "parties" })`); r.more = count(run(`__el("setupList").innerHTML`));
    await run(`viewSetup(__el("main"))`); await sleep(20); r.redrawn = count(box().innerHTML);
    await view("accounts", FX.EXA); await view("parties", FX.EXA); r.otherSection = count(box().innerHTML);
    await run(`click({ setupMore: "parties" })`); await view("parties", FX.EXB); await view("parties", FX.EXA); r.otherCompany = count(box().innerHTML);
    return r;
  });

  // 9. an arrow key on a tab strip: the tab now selected has the focus once the page is drawn again
  await tryit("tabKey", async () => {
    const mk = (kind, id) => ({ id, dataset: { setupKind: kind }, tagName: "BUTTON", getAttribute: k => k === "role" ? "tab" : null, closest: () => null, focus() { document.activeElement = this; } });
    const a = mk("payment_types", "tab-a"), b = mk("doc_types", "tab-b"), strip = { querySelectorAll: () => [a, b] };
    a.parentNode = strip; b.parentNode = strip;
    b.click = () => run(`click({ setupKind: "doc_types" }, { getAttribute: k => k === "role" ? "tab" : null })`);
    sandbox.__tabs = { payment_types: a, doc_types: b };
    document.activeElement = a;
    for (const f of listeners.keydown || []) f({ key: "ArrowRight", target: a, preventDefault() {} });
    await sleep(120);
    return { active: document.activeElement && document.activeElement.id, kind: run(`state.setup.kind`) };
  });

  // 10. one change per Enter: a double Enter sends it once, in the reason box and in Put it back
  await tryit("double", async () => {
    const r = {};
    await run(`state.entity = ${FX.EXA}; openSetup("accounts", ${FX.OLD})`); await sleep(20);
    calls.length = 0;
    await run(`setupAct("delete", __btn)`); el("su-reason").value = "Opened by mistake";
    const evs = [];
    for (let i = 0; i < 2; i++) for (const f of listeners.keydown || []) evs.push(f({ key: "Enter", target: el("su-reason"), preventDefault() {} }));
    await Promise.all(evs); await sleep(40);
    r.deletes = calls.filter(x => x[0] === "DELETE").length;
    await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20);
    let clicks = 0; el("pb-go").click = () => { clicks++; };
    for (const f of listeners.keydown || []) f({ key: "Enter", target: el("pb-why"), preventDefault() {} });
    r.enterClicks = clicks;
    el("pb-why").value = "It is the new account"; calls.length = 0;
    await Promise.all([run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`), run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`)]);
    r.restores = calls.filter(x => x[0] === "POST" && !(x[2] && x[2].preview)).length;
    return r;
  });

  // 11. the old address of Recurring payments (a link, not a section) with no company opens the first section
  await tryit("deadLink", async () => {
    run(`state.meta.entities = []; state.entity = null; state.setup.kind = "payees"`);
    await run(`viewSetup(__el("main"))`); await sleep(20);
    const r = { kind: run(`state.setup.kind`), page: box().innerHTML };
    run(`state.meta = ${JSON.stringify(meta0)}; state.entity = ${FX.EXA}`);
    return r;
  });

  // 12. Open Setup > Bank accounts in a company's dialog opens that company's accounts, not the top bar's
  await tryit("bankLink", async () => {
    const path = `/api/setup/entities/${FX.EXA}/print`, was = FX.get[path];
    FX.get[path] = { ...was, missing: ["The bank account Main has no bank address: add it in Setup › Bank accounts."] };
    await run(`state.entity = ${FX.EXB}; openSetup("entities", ${FX.EXA})`); await sleep(60);
    const r = { html: el("suPrint").innerHTML, before: run(`state.entity`) };
    await run(`click({ setupKind: "accounts", setupEntity: "${FX.EXA}" })`); await sleep(20);
    r.entity = run(`state.entity`); r.kind = run(`state.setup.kind`);
    FX.get[path] = was; run(`state.entity = ${FX.EXA}`);
    return r;
  });

  // 13. Required documents for a company Kept here: the documents SQL Account issues are greyed and said
  await tryit("requiredHere", async () => {
    const r = {};
    run(`state.setup.kind = "required"; state.setup.reqScope = ${FX.EXB}`); await run(`setupRequired(__el("setupMain"))`); r.here = el("setupMain").innerHTML;
    run(`state.setup.reqScope = null`); await run(`setupRequired(__el("setupMain"))`); r.all = el("setupMain").innerHTML;
    return r;
  });

  // 15. Move setup: Export says what it is doing; right after an import the card links to the companies it added
  await tryit("moveStates", async () => {
    const r = {};
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    r.empty = (await view("move", FX.EXA)).page;
    r.dayKey = run(`dayKey()`);
    await run(`click({ moveExport: "template" })`); r.toastTemplate = el("toast").textContent;
    run(`state.setup.move.payees = true`); await run(`click({ moveExport: "full" })`); r.toastFull = el("toast").textContent;
    run(`state.setup.move.payees = false`); await run(`click({ moveExport: "full" })`); r.toastFullPlain = el("toast").textContent;
    // an import is made: the next time the page is drawn it says so, and goes when the section is left
    run(`state.setup.move.file = { format: "hrp-setup" }; state.setup.move.preview = {}`); calls.length = 0;
    await run(`moveImport("A reason")`);
    r.flag = run(`state.setup.move.justImported`); r.imported = calls.filter(x => x[1] === "/api/setup/import").map(x => x[2].reason);
    FX.get["/api/setup/import"] = { empty: false, holding: [["companies", 3]] };
    r.blocked = (await view("move", FX.EXA)).page;
    await view("accounts", FX.EXA);
    r.blockedLater = (await view("move", FX.EXA)).page;
    return r;
  });

  // 16. Show deleted: a company as CODE · Name, a chart account with its code, each section by its own words
  await tryit("deletedNames", async () => {
    const r = {};
    run(`state.setup.deleted = true`);
    await run(`drawDeleted("entities")`); r.companies = el("setupDeleted").innerHTML;
    run(`state.entity = ${FX.EXA}`); await run(`drawDeleted("gl_accounts")`); r.chart = el("setupDeleted").innerHTML;
    FX.get["/api/setup/restore?kind=filing_words"] = { kind: "filing_words", table: "filing_words", plural: "SQL filing words", label: "SQL filing word", rows: [] };
    await run(`drawDeleted("filing_words")`); r.filing = el("setupDeleted").innerHTML;
    run(`state.setup.deleted = false`);
    return r;
  });

  // A. the rows Show 25 more showed: not kept past another section (a list or not), nor out of Setup; kept by a save; a changed search starts again
  await tryit("moreAway", async () => {
    const count = h => (h.match(/class="st-row/g) || []).length, r = {};
    const more = async () => { await run(`click({ setupMore: "parties" })`); return count(run(`__el("setupList").innerHTML`)); };
    const type = v => { for (const f of listeners.input || []) f({ target: { dataset: { search: "setup-parties" }, value: v, id: "", closest: () => null } }); return count(run(`__el("setupList").innerHTML`)); };
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    await view("parties", FX.EXA); r.first = count(box().innerHTML); r.more = await more();
    await view("required", FX.EXA); await view("parties", FX.EXA); r.afterRequired = count(box().innerHTML);
    await more(); await view("move", FX.EXA); await view("parties", FX.EXA); r.afterMove = count(box().innerHTML);
    await more();
    await run(`applyPlace({ view: "overview", entity: "all", month: "2026-11", sub: null, id: null, params: {} })`);
    run(`state.view = "setup"`);
    await view("parties", FX.EXA); r.afterLeaving = count(box().innerHTML);
    await more(); await run(`viewSetup(__el("main"))`); await sleep(20); r.saveRedraw = count(box().innerHTML);
    r.searched = type("Test"); r.moreAgain = await more(); r.cleared = type("");
    await more(); await run(`click({ setupClear: "parties" })`); r.clearBtn = count(run(`__el("setupList").innerHTML`));
    await more();   // the menu's Setup item while on Setup, or a record's address on the same section: a fresh page, which clears the search too
    await run(`applyPlace({ view: "setup", entity: ${FX.EXA}, month: null, sub: "parties", id: null, params: {} }, { fresh: true })`);
    await view("parties", FX.EXA); r.freshPage = count(box().innerHTML);
    return r;
  });

  // C. the Setup menu keeps its scroll when the page is drawn again, shows its item on show, and takes the focus after a click on an item
  await tryit("navKeep", async () => {
    const r = {};
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    run(`state.view = "setup"; render = async () => { await viewSetup(__el("main")); }`);   // the page is really drawn again for this
    scrolls.length = 0;
    const seen = () => ({ kind: main.nav.kind, top: main.nav.scrollTop, sets: main.nav.sets, intoView: main.nav.active.scrolled.length, focused: document.activeElement === main.nav.active });
    main.innerHTML = "";                                                                      // a deep address: no menu before it
    await view("move", FX.EXA);
    r.deep = seen();
    main.nav.userScroll(400); document.activeElement = null;                                  // the menu was scrolled by hand, its item is in the frame
    await run(`viewSetup(__el("main"))`); await sleep(20);                                    // a save draws the page again
    r.save = seen();
    await run(`click({ setupKind: "accounts" }, { classList: { contains: c => c === "sn" } })`); await sleep(20);   // a click or Enter on an item above the frame
    r.click = seen();
    r.windowScrolls = scrolls.slice();
    run(`render = async () => { __calls.push(["render"]); }`);
    return r;
  });

  // D. Put it back opened from the audit trail or a History: the heading is the preview's name (CODE · Name), as Show deleted names it
  await tryit("putBackTitle", async () => {
    await run(`openRestore(${FX.RS_EXD}, "Example Delta Ltd")`); await sleep(20);
    return { title: el("drawerTitle").textContent, body: el("rsBody").innerHTML, trailBtn: run(`putBackHtml({ id: ${FX.RS_EXD}, put_back: true, record: "Example Delta Ltd" })`) };
  });

  // E3. Put it back with the app stopped: the click handler waits for it, so the message is said
  await tryit("restoreStopped", async () => {
    await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20);
    el("pb-why").value = "A reason"; el("toast").textContent = "";
    FX.fail = { [`/api/setup/restore/${FX.RESTORE}`]: true };
    const threw = await run(`click({ restoreGo: "${FX.RESTORE}" }, { disabled: false, isConnected: true }).then(() => "ok", e => "threw")`);
    FX.fail = {};
    return { threw, toast: el("toast").textContent };
  });

  // E4. the old address of Recurring payments with a record number, with no company: the first section, and no record of it opened
  await tryit("deadLinkId", async () => {
    run(`globalThis.__opened = []; globalThis.__realOpen = openSetup; openSetup = async (...a) => { __opened.push([a[0], a[1]]); return __realOpen(...a); };
      render = async () => { await viewSetup(__el("main")); }; state.meta.entities = []; state.entity = null; state.setup.kind = "parties";`);
    el("toast").textContent = "";
    await run(`applyPlace({ view: "setup", entity: null, month: null, sub: "payees", id: "5", params: {} })`); await sleep(40);
    const r = { opened: run(`__opened.slice()`), kind: run(`state.setup.kind`), toast: el("toast").textContent };
    run(`state.meta = ${JSON.stringify(meta0)}; state.entity = ${FX.EXA}; __opened.length = 0`);   // a record of a real section still opens
    await run(`applyPlace({ view: "setup", entity: ${FX.EXA}, month: null, sub: "entities", id: "${FX.EXA}", params: {} })`); await sleep(60);
    r.control = run(`__opened.slice()`);
    run(`openSetup = __realOpen; render = async () => { __calls.push(["render"]); }; state.view = "setup"`);
    return r;
  });

  // E5. the link to the companies an import added: the redraw right after an import that added one, once
  await tryit("moveFlag", async () => {
    const r = {}, link = "See the companies it added";
    const imported = async () => { run(`state.setup.move = { ...(state.setup.move || {}), file: { format: "hrp-setup" }, preview: {} }`); await run(`moveImport("A reason")`); return run(`state.setup.move.justImported`); };
    FX.get["/api/setup/import"] = { empty: false, holding: [["companies", 3]] };
    r.flag = await imported(); r.right = (await view("move", FX.EXA)).page; r.next = (await view("move", FX.EXA)).page;
    r.flagAfter = run(`state.setup.move.justImported`);
    await imported(); await run(`applyPlace({ view: "overview", entity: "all", month: "2026-11", sub: null, id: null, params: {} })`); run(`state.view = "setup"`);
    r.flagOut = run(`state.setup.move.justImported`); r.afterOverview = (await view("move", FX.EXA)).page;
    withCompanies([]); r.rulesFlag = await imported(); r.rulesBlocked = (await view("move", FX.EXA)).page;   // a file of rules alone: no company came in
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.entity = ${FX.EXA}; state.setup.types = null`);
    await view("accounts", FX.EXA);
    return r;
  });

  // E2. First run when what was written was saved but the records can't be read again: a note and Try again, which only reads
  await tryit("frSaved", async () => {
    const r = {};
    withCompanies([co(1, "EXA", 1)]); setFile("full", [["companies", 1]]); FX.fail = { "/api/meta": true }; calls.length = 0;
    r.threw = await run(`frImport().then(() => "ok", e => e.name)`);
    r.busy = run(`FR.busy`); r.saved = run(`FR.saved`); r.html = run(`frHtml()`);
    await run(`click({ frReload: "1" })`); r.stillSaved = run(`FR.saved`); r.stillBusy = run(`FR.busy`); r.stillHtml = run(`frHtml()`);
    FX.fail = {}; calls.length = 0;
    await run(`click({ frReload: "1" })`);
    r.after = { done: run(`FR.done`), saved: run(`FR.saved`), posts: calls.filter(x => x[0] === "POST").length, html: run(`frHtml()`) };
    run(`state.meta.entities = []; FR.done = null; FR.note = null; FR.preview = null; FR.file = null; FR.addOpen = true; FR.tried = false; FR.code = "ABC"; FR.cname = "Example Co"; FR.reg = ""; FR.kind = "sql"; FR.busy = ""`);
    withCompanies([co(1, "ABC", 1)]); FX.fail = { "/api/meta": true }; calls.length = 0;
    r.addThrew = await run(`frAddCompany().then(() => "ok", e => e.name)`); r.addHtml = run(`frHtml()`); r.addPosts = calls.filter(x => x[1] === "/api/setup/entities").length;
    FX.fail = {}; calls.length = 0;
    await run(`click({ frReload: "1" })`);
    r.addAfter = { done: run(`FR.done`), saved: run(`FR.saved`), posts: calls.filter(x => x[0] === "POST").length };
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.addOpen = false; FR.done = null; FR.note = null; FR.saved = null; FR.code = ""; FR.cname = ""; FR.kind = ""; state.entity = ${FX.EXA}`);
    await view("accounts", FX.EXA);
    return r;
  });

  // B. markup in a name, a label, a code or a note is shown as it is written, never as HTML
  await tryit("escapes", async () => {
    const r = {}, T = "Delivery <i>Order</i> (SQL)", N = "Tom & <b>Jerry</b> Ltd", C = "E&<B";
    const reqPath = `/api/setup/required?entity=${FX.EXB}`, wasReq = FX.get[reqPath];
    FX.get[reqPath] = { ...wasReq, doc_types: [...wasReq.doc_types, { key: "tst_dosql", label: T, from_sql: 1, active: 1 }] };
    run(`state.meta.entities.forEach(x => { if (x.id === ${FX.EXB}) { x.code = ${JSON.stringify(C)}; x.name = ${JSON.stringify(N)}; } })`);
    run(`state.setup.kind = "required"; state.setup.reqScope = ${FX.EXB}`);
    await run(`setupRequired(__el("setupMain"))`); r.required = el("setupMain").innerHTML;
    run(`state.setup.reqScope = null`); FX.get[reqPath] = wasReq;
    const entPath = `/api/setup/entities/${FX.EXA}`, wasEnt = FX.get[entPath];
    FX.get[entPath] = { ...wasEnt, record: { ...wasEnt.record, name: N }, used_by: [["bank <u>account</u>s", 2]], used_total: 2, notes: ["A note with <i>markup</i> & more"] };
    run(`state.entity = ${FX.EXA}`);
    await run(`openSetup("entities", ${FX.EXA})`); await sleep(60); r.dlg = el("drawer").innerHTML; FX.get[entPath] = wasEnt;
    const namesPath = `/api/setup/entities/${FX.EXB}/sql-names`, wasNames = FX.get[namesPath];
    FX.get[namesPath] = { ready: true, names: [{ id: 7, name: "A & <b>B</b> (2026)", confirmed_at: "2026-11-01T10:00:00", confirmed_by: "t <i>ester</i>" }] };
    els.suPrint = undefined; els.suNames = undefined;
    const hereEnt = `/api/setup/entities/${FX.EXB}`, wasHere = FX.get[hereEnt];
    FX.get[hereEnt] = { ...wasHere, record: { ...wasHere.record, name: N } };
    await run(`openSetup("entities", ${FX.EXB})`); await sleep(60); r.names = el("suNames").innerHTML; r.dlgHere = el("drawer").innerHTML; FX.get[namesPath] = wasNames; FX.get[hereEnt] = wasHere;
    const delPath = "/api/setup/restore?kind=entities", wasDel = FX.get[delPath], row = (id, problem) => ({ row_id: id, name: `${C} · ${N}`, code: "C&<D", at: "2026-11-01T10:00:00", actor: "a&<b>", reason: "why <i>x</i>", entry: 12, table: "entities", key: String(id), problem });
    FX.get[delPath] = { kind: "entities", table: "entities", plural: "companies", label: "company", rows: [row(9, "key <u>taken</u>"), row(10, null)] };
    run(`state.setup.deleted = true`); await run(`drawDeleted("entities")`); r.deleted = el("setupDeleted").innerHTML;
    run(`state.setup.deleted = false`); FX.get[delPath] = wasDel;
    FX.post["/api/setup/restore/9?preview"] = { status: 200, body: { ...FX.PREVIEW, name: `${C} · ${N}`, label: "Company <i>x</i>", table: "entities",
      deleted: { entry: 12, at: "2026-11-01T10:00:00", actor: "a&<b>", reason: "why <i>x</i>", key: "5" }, notes: ["note <b>b</b>"] } };
    await run(`openRestore(9, "Old <i>name</i>")`); await sleep(20);
    r.putBack = { head: el("drawerTitle").textContent, body: el("rsBody").innerHTML, drawer: el("drawer").innerHTML };
    FX.get["/api/meta"] = { ...meta0, entities: [{ id: 1, code: C, name: N, uses_sql: 0, active: 1, accounts: [] }] };
    run(`state.view = "overview"; FR.done = null; FR.note = null; FR.saved = null; FR.busy = ""`);
    await run(`frFinish({ code: ${JSON.stringify(C)}, kept: "Kept here" })`); r.banner = run(`frHtml()`);
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.done = null; FR.note = null; state.entity = ${FX.EXA}`);
    await view("accounts", FX.EXA);
    return r;
  });

  // 5. First run: a second Add company whose records can't be read again says so alone, takes the focus, and its button keeps it
  await tryit("frSavedTwice", async () => {
    const r = {};
    el("fr-saved"); el("fr-reload");   // the alert and its button, to see where the focus goes
    run(`state.view = "overview"; state.meta.entities = []; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.busy = ""; FR.preview = null; FR.file = null;
      FR.addOpen = true; FR.tried = false; FR.code = "ABC"; FR.cname = "Example Co"; FR.reg = ""; FR.kind = "here"`);
    withCompanies([co(1, "ABC", 1)]);
    await run(`frAddCompany()`); r.first = run(`FR.done`);                          // the first company is added and read: Company added
    run(`FR.addOpen = true; FR.code = "DEF"; FR.cname = "Example Two"; FR.kind = "here"; FR.tried = false`);
    withCompanies([co(1, "ABC", 1), co(2, "DEF", 1)]); FX.fail = { "/api/meta": true };
    r.threw = await run(`frAddCompany().then(() => "ok", e => e.name)`);
    r.html = run(`frHtml()`); r.done = run(`FR.done`); r.due = run(`firstRunDue()`); r.focus1 = document.activeElement && document.activeElement.id; r.alerted = run(`FR.alerted`);
    await run(`click({ frReload: "1" })`);
    r.focus2 = document.activeElement && document.activeElement.id; r.html2 = run(`frHtml()`);
    FX.fail = {};
    await run(`click({ frReload: "1" })`);
    r.after = { done: run(`FR.done`), saved: run(`FR.saved`), alerted: run(`FR.alerted`), html: run(`frHtml()`) };
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.addOpen = false; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.code = ""; FR.cname = ""; FR.kind = ""; state.entity = ${FX.EXA}`);
    await view("accounts", FX.EXA);
    return r;
  });

  // 6d. Put it back with the app stopped: the dialog says it couldn't load, with a way to try again, and doesn't stay on Loading
  await tryit("restoreLoadFail", async () => {
    FX.fail = { [`/api/setup/restore/${FX.RESTORE}`]: true };
    const threw = await run(`openRestore(${FX.RESTORE}, "Spare").then(() => "ok", e => "threw")`); FX.fail = {};
    return { threw, body: el("rsBody").innerHTML };
  });

  // 6b. a record's History key and a list's name are escaped where they are written into the page
  await tryit("escapesCore", async () => ({ hist: run(`histSection('a"b', '<x>')`), bar: run(`listBar('setup-a"b', 'cust <i>x</i>')`) }));

  // 1. a section drawn again holds the page's height while it is read: the window isn't moved, nothing old is shown meanwhile, and the hold ends only
  // once the whole section (the Show deleted table too) is written, or the read failed; another section or company starts at the top
  await tryit("holdKeeps", async () => {
    const r = {}, P = `/api/setup/parties?entity=${FX.EXA}`, A = `/api/setup/accounts?entity=${FX.EXA}`, D = `/api/setup/restore?kind=accounts&entity=${FX.EXA}`;
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    await view("parties", FX.EXA);
    const during = [];
    delays[P] = 60; onGet = path => { if (path === P) during.push({ y: win.scrollY, hold: main.style.minHeight, section: smHtml.length }); };
    win.scrollY = 800; seenY.length = 0; scrolls.length = 0;
    await run(`viewSetup(__el("main"))`);   // a save, a stop, a delete, a put back: the same section of the same company
    r.same = { y: win.scrollY, low: Math.min(...seenY), scrolls: scrolls.length, during, hold: main.style.minHeight, written: smHtml.length > 200 };
    onGet = path => { if (path === P) win.scrollY = 1000; };   // the user scrolls while it is read
    win.scrollY = 800; scrolls.length = 0;
    await run(`viewSetup(__el("main"))`);
    r.userScroll = { y: win.scrollY, scrolls: scrolls.length };
    await view("accounts", FX.EXA); run(`state.setup.deleted = true`);   // with Show deleted on: its table is part of the draw
    delays[D] = 60; onGet = path => { if (path === D) r.atDeleted = { hold: main.style.minHeight, listWritten: smHtml.length > 200 }; };
    win.scrollY = 800; scrolls.length = 0;
    await run(`viewSetup(__el("main"))`);
    r.deleted = { y: win.scrollY, scrolls: scrolls.length, hold: main.style.minHeight, table: el("setupDeleted").innerHTML.includes("Deleted bank accounts") };
    run(`state.setup.deleted = false`); onGet = null; delete delays[D];
    FX.fail = { [A]: true };
    r.failed = await run(`viewSetup(__el("main"))`).then(() => "ok", e => e.name); FX.fail = {};   // the read fails: the hold doesn't stay
    r.failedHold = main.style.minHeight;
    delete delays[P];
    await view("parties", FX.EXA);
    win.scrollY = 800; scrolls.length = 0;
    await view("accounts", FX.EXA);   // another section
    r.otherSection = { y: win.scrollY, scrolls: scrolls.slice(), hold: main.style.minHeight };
    win.scrollY = 800; scrolls.length = 0;
    await view("accounts", FX.EXB);   // another company
    r.otherCompany = { y: win.scrollY, scrolls: scrolls.slice(), hold: main.style.minHeight };
    await view("accounts", FX.EXA);
    return r;
  });

  // 1f. a draw that has been overtaken, or whose place is no longer on the page, writes nothing
  await tryit("staleDraw", async () => {
    const r = {}, G = `/api/setup/gl_accounts?entity=${FX.EXA}`, PT = "/api/setup/payment_types";
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    const ask = kind => { run(`state.entity = ${FX.EXA}; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false`); return run(`viewSetup(__el("main"))`); };
    const forget = () => run(`delete LIST_REDRAW["setup-gl_accounts"]; delete state.counts["setup-gl_accounts"]; delete LIST_REDRAW["setup-payment_types"]; delete state.counts["setup-payment_types"]; delete LIST_REDRAW["setup-parties"]; delete state.counts["setup-parties"]`);
    // Chart of accounts is read slowly; Payment types is asked for next, and is quick
    await ask("parties");
    forget(); delays[G] = 120; let boxA = null; onGet = path => { if (path === G) boxA = els.setupMain; };
    const a = ask("gl_accounts"); await sleep(20);
    await ask("payment_types");
    r.quick = { page: smHtml.includes('data-setup-new="payment_types"'), a: smHtml.includes('data-setup-new="gl_accounts"') };
    await a; await sleep(20); onGet = null;
    r.overtaken = { writes: boxA.writes, page: smHtml.includes('data-setup-new="payment_types"'), a: smHtml.includes('data-setup-new="gl_accounts"'),
      redraw: run(`typeof LIST_REDRAW["setup-gl_accounts"]`), count: run(`state.counts["setup-gl_accounts"] ?? null`), hold: main.style.minHeight };
    delete delays[G];
    await ask("gl_accounts"); r.later = { a: smHtml.includes('data-setup-new="gl_accounts"'), pt: smHtml.includes('data-setup-new="payment_types"') };
    // the same section drawn twice, the first read finishing first: it doesn't end the hold of the second
    await ask("payment_types"); forget();
    delays[PT] = [100, 400]; let boxB = null; onGet = path => { if (path === PT && !boxB) boxB = els.setupMain; };
    const one = ask("payment_types"); await sleep(20);
    const two = ask("payment_types");
    await one; await sleep(20);
    r.overlap = { holdWhileSecond: main.style.minHeight, firstWrites: boxB.writes, page: smHtml.length };
    await two; onGet = null; delete delays[PT];
    r.overlapEnd = { hold: main.style.minHeight, page: smHtml.includes('data-setup-new="payment_types"') };
    await view("accounts", FX.EXA);
    return r;
  });

  // 3. First run: what was saved and not read again is over once the records have been read again, whatever they list
  await tryit("frSavedElsewhere", async () => {
    const r = {}, read = () => run(`readMeta().then(m => { state.meta = m; return "ok"; }, e => e.name)`);
    run(`state.view = "overview"; state.meta.entities = []; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.busy = ""; FR.preview = null; FR.file = null;
      FR.addOpen = true; FR.tried = false; FR.code = "ALP"; FR.cname = "Example Alpha"; FR.reg = ""; FR.kind = "here"`);
    withCompanies([co(1, "ALP", 1)]);
    await run(`frAddCompany()`); r.first = run(`FR.done && FR.done.title`);   // ALP is added and read
    // BET is added but the records can't be read again: the alert. A read that fails (Setup's, with the app stopped) doesn't end it
    run(`FR.done = null; FR.note = null; FR.addOpen = true; FR.code = "BET"; FR.cname = "Example Beta"; FR.kind = "here"; FR.tried = false`);
    withCompanies([co(1, "ALP", 1), co(2, "BET", 1)]); FX.fail = { "/api/meta": true };
    r.threw = await run(`frAddCompany().then(() => "ok", e => e.name)`);
    r.due = run(`firstRunDue()`); r.savedAt = run(`FR.saved && FR.saved.reads`); r.reads0 = run(`state.metaReads`);
    r.failedRead = await read(); r.dueAfterFailed = run(`firstRunDue()`); r.savedAfterFailed = run(`!!FR.saved`); r.reads1 = run(`state.metaReads`);
    // BET is deleted in Setup, which reads the records again: they list ALP only, so the count of companies didn't rise, and the note is over
    FX.fail = {}; withCompanies([co(1, "ALP", 1)]);
    r.read = await read(); r.dueAfterRead = run(`firstRunDue()`); r.saved = run(`FR.saved`); r.alerted = run(`FR.alerted`);
    // the first company of all, saved but not read: any successful read ends it
    run(`state.meta.entities = []; FR.done = null; FR.note = null; FR.addOpen = true; FR.code = "GHI"; FR.cname = "Example Three"; FR.kind = "here"; FR.tried = false`);
    withCompanies([co(1, "GHI", 1)]); FX.fail = { "/api/meta": true };
    r.threw2 = await run(`frAddCompany().then(() => "ok", e => e.name)`); r.due2 = run(`firstRunDue()`);
    FX.fail = {}; r.read2 = await read(); r.due2After = run(`firstRunDue()`); r.saved2 = run(`FR.saved`);
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.addOpen = false; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.code = ""; FR.cname = ""; FR.kind = ""; state.entity = ${FX.EXA}`);
    await view("accounts", FX.EXA);
    return r;
  });

  // 4c. Put it back's Try again with the app stopped: one request and one dialog each time, however often it is pressed, and it works once the app is back
  await tryit("restoreRetry", async () => {
    const path = `/api/setup/restore/${FX.RESTORE}`, r = { rounds: [] };
    FX.fail = { [path]: true };
    await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20);
    for (let i = 0; i < 3; i++) {
      calls.length = 0;
      await run(`click({ restore: "${FX.RESTORE}", restoreTitle: "Spare" })`); await sleep(20);
      r.rounds.push({ requests: calls.filter(x => x[1] === path).length, dialogs: (el("drawer").innerHTML.match(/id="restoreBox"/g) || []).length, notes: (el("rsBody").innerHTML.match(/Couldn't load this/g) || []).length });
    }
    FX.fail = {}; calls.length = 0;
    await run(`click({ restore: "${FX.RESTORE}", restoreTitle: "Spare" })`); await sleep(20);
    r.back = { requests: calls.filter(x => x[1] === path).length, dialogs: (el("drawer").innerHTML.match(/id="restoreBox"/g) || []).length, body: el("rsBody").innerHTML };
    return r;
  });
  // 1. render() covers the page with its loading skeleton while a draw reads (a read over 0.3 s): the draw, still the latest, puts its grid back and writes
  await tryit("skeleton", async () => {
    const r = {}, P = `/api/setup/parties?entity=${FX.EXA}`, AB = `/api/setup/accounts?entity=${FX.EXB}`;
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    const real = () => run(`render = __realRender`), stub = () => run(`render = async () => { __calls.push(["render"]); }`);
    const shape = (kind, code) => ({ section: smHtml.includes(`data-setup-new="${kind}"`), company: smHtml.includes(code), grid: /class="setup-grid"/.test(main.innerHTML),
      skeleton: /class="skel"/.test(main.innerHTML), menu: !!main.nav, redraw: run(`typeof LIST_REDRAW["setup-${kind}"]`), hold: main.style.minHeight, loading: main.classList.contains("loading") });
    real();
    try {
      // arriving from another page, the records of the section taking 700 ms
      main.innerHTML = `<div>Overview</div>`; run(`render.last = null; state.view = "setup"; state.entity = ${FX.EXA}; state.setup.kind = "parties"; state.setup.stopped = false; state.setup.deleted = false; delete LIST_REDRAW["setup-parties"]`);
      delays[P] = 700; await run(`render()`); delete delays[P];
      r.arrival = shape("parties", "Customers and suppliers");
      // a company switch, 700 ms
      run(`state.entity = ${FX.EXA}; state.setup.kind = "accounts"`); await run(`render()`);
      run(`state.entity = ${FX.EXB}; delete LIST_REDRAW["setup-accounts"]`); delays[AB] = 700; await run(`render()`); delete delays[AB];
      r.switch = shape("accounts", "Bank accounts · EXB");
      // the very first read of the types, 700 ms, on arriving
      main.innerHTML = `<div>Overview</div>`; run(`render.last = null; state.setup.types = null; state.entity = ${FX.EXA}; state.setup.kind = "parties"; delete LIST_REDRAW["setup-parties"]`);
      delays["/api/setup/types"] = 700; await run(`render()`); delete delays["/api/setup/types"];
      r.types = shape("parties", "Customers and suppliers");
    } finally { stub(); }
    await view("accounts", FX.EXA);
    return r;
  });

  // 2. leaving Setup while a draw reads: the new page has no hold of the page's height at once, a read that hangs changes nothing, and nothing is drawn over it
  await tryit("leaving", async () => {
    const r = {}, P = `/api/setup/parties?entity=${FX.EXA}`;
    await view("parties", FX.EXA);
    delays[P] = 400; const a = run(`viewSetup(__el("main"))`); await sleep(40);   // the same section drawn again: the page is held
    r.held = main.style.minHeight;
    await run(`applyPlace({ view: "overview", entity: "all", month: "2026-11", sub: null, id: null, params: {} })`);   // the menu, or the address, to the Overview
    main.innerHTML = `<div>Overview page</div>`;
    r.at = main.style.minHeight; await sleep(100); r.hung = main.style.minHeight;   // the read hasn't come
    await a; await sleep(20); delete delays[P];
    r.end = { hold: main.style.minHeight, page: main.innerHTML };
    // by render(), for a page that isn't Setup
    run(`state.view = "setup"`); await view("parties", FX.EXA);
    delays[P] = 400; const b = run(`viewSetup(__el("main"))`); await sleep(40);
    run(`ROUTES.zzz = { draw: () => async m => { m.innerHTML = "<div>zzz page</div>"; } }; render = __realRender; state.view = "zzz"`);
    try { await run(`render()`); } finally { run(`render = async () => { __calls.push(["render"]); }; state.view = "setup"`); }
    r.byRender = { hold: main.style.minHeight, page: main.innerHTML };
    await b; await sleep(20); delete delays[P];
    r.byRenderEnd = { hold: main.style.minHeight, page: main.innerHTML };
    await view("accounts", FX.EXA);
    return r;
  });

  // 2b. a failure while the grid is drawn (after the page's height is held): the hold doesn't stay
  await tryit("gridFails", async () => {
    const r = {};
    await view("parties", FX.EXA);
    run(`globalThis.__navHtml = setupNavHtml; setupNavHtml = () => { throw new Error("the menu failed"); }`);
    try { r.threw = await run(`viewSetup(__el("main"))`).then(() => "ok", e => e.message); } finally { run(`setupNavHtml = __navHtml`); }
    r.hold = main.style.minHeight;
    await view("accounts", FX.EXA);
    return r;
  });

  // 3. render(): the page on show is the latest render's; an error comes only for the current render
  await tryit("renderStale", async () => {
    const r = {}, AE = `/api/setup/accounts?entity=${FX.EXA}`;
    run(`render = __realRender; ROUTES.zzz = { draw: () => async m => { await new Promise(res => setTimeout(res, 300)); throw new Error("late failure"); } }`);
    try {
      run(`state.view = "setup"; render.last = null; state.entity = ${FX.EXA}; state.setup.kind = "accounts"; state.setup.stopped = false; state.setup.deleted = false`);
      delays[AE] = 400; const a = run(`render()`); await sleep(30);   // company EXA, slow
      run(`state.entity = ${FX.EXB}`); await run(`render()`);        // company EXB, quick: it is the page on show
      r.mid = run(`render.last`); await a; r.last = run(`render.last`); delete delays[AE];
      run(`state.view = "zzz"`); const z = run(`render()`); await sleep(30);   // a page that fails, after 300 ms
      run(`state.view = "setup"; state.entity = ${FX.EXA}; state.setup.kind = "parties"`); await run(`render()`);   // left for Setup meanwhile
      await z; await sleep(20);
      r.error = { painted: main.innerHTML.includes("late failure"), grid: /setup-grid/.test(main.innerHTML), last: run(`render.last`) };
    } finally { run(`render = async () => { __calls.push(["render"]); }; state.view = "setup"; state.entity = ${FX.EXA}`); delete delays[AE]; }
    await view("accounts", FX.EXA);
    return r;
  });

  // 4. a reply that isn't the records (no companies in it) is a failed read
  await tryit("badMeta", async () => {
    const r = {}, reads0 = run(`state.metaReads || 0`), was = run(`state.meta`);
    FX.bad = { "/api/meta": true };
    r.message = await run(`readMeta().then(() => "ok", e => e.message)`);
    r.reads = run(`state.metaReads || 0`) - reads0; r.sameMeta = run(`state.meta`) === was;
    run(`state.view = "overview"; state.meta.entities = []; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.busy = ""; FR.preview = null; FR.file = null;
      FR.addOpen = true; FR.tried = false; FR.code = "NOP"; FR.cname = "Example Nop"; FR.reg = ""; FR.kind = "here"`);
    r.add = await run(`frAddCompany().then(() => "ok", e => e.name + ": " + e.message)`);
    r.saved = run(`!!FR.saved`); r.html = run(`frHtml()`);
    FX.bad = {};
    FX.get["/api/meta"] = {};   // JSON, but no companies in it: readMeta's own check
    r.empty = await run(`readMeta().then(() => "ok", e => e.message)`);
    r.emptyReads = run(`state.metaReads || 0`) - reads0;
    FX.get["/api/meta"] = meta0; run(`state.meta = ${JSON.stringify(meta0)}; state.view = "setup"; FR.addOpen = false; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.code = ""; FR.cname = ""; FR.kind = ""; state.entity = ${FX.EXA}`);
    await view("accounts", FX.EXA);
    return r;
  });

  // 5. every section that has a read of its own: overtaken by another section, drawn twice (the hold), and an overtaken read that throws
  const SECTIONS = [
    { kind: "checklist", path: `/api/setup/checklist?entity=${FX.EXA}`, state: "chk" }, { kind: "reminders", path: "/api/setup/reminders", state: "rem" },
    { kind: "settings", path: "/api/setup/settings", state: "settings" }, { kind: "move", path: "/api/setup/import", state: "move" },
    { kind: "required", path: "/api/setup/required?entity=", state: "req" }, { kind: "parties", path: `/api/setup/parties?entity=${FX.EXA}`, redraw: "setup-parties" }];
  await tryit("staleSections", async () => {
    const out = {};
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    const ask = kind => { run(`state.entity = ${FX.EXA}; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false; state.setup.reqScope = null`); return run(`viewSetup(__el("main"))`); };
    for (const K of SECTIONS) {
      const r = out[K.kind] = {};
      const forget = () => { if (K.state) run(`state.setup.${K.state} = undefined`); if (K.redraw) run(`delete LIST_REDRAW[${JSON.stringify(K.redraw)}]`); };
      const wrote = () => K.state ? run(`state.setup.${K.state} !== undefined && state.setup.${K.state} !== null`) : run(`typeof LIST_REDRAW[${JSON.stringify(K.redraw)}] !== "undefined"`);
      // overtaken by another section: it writes no state, no markup
      await ask("payment_types"); forget();
      delays[K.path] = 150; let boxK = null; onGet = p => { if (p === K.path && !boxK) boxK = els.setupMain; };
      const a = ask(K.kind); await sleep(20);
      await ask("payment_types");
      await a; await sleep(10); onGet = null; delete delays[K.path];
      r.overtaken = { wrote: wrote(), writes: boxK.writes, page: smHtml.includes('data-setup-new="payment_types"'), hold: main.style.minHeight };
      // the same section drawn twice, the first read finishing first: it writes nothing and leaves the hold of the second alone
      await ask(K.kind); forget();
      delays[K.path] = [100, 400]; let firstBox = null, heldFirst = null; onGet = p => { if (p === K.path && !firstBox) { firstBox = els.setupMain; heldFirst = main.style.minHeight; } };
      const one = ask(K.kind); await sleep(20);
      const two = ask(K.kind);
      await one; await sleep(20);
      r.twice = { holdKept: main.style.minHeight !== "" && main.style.minHeight === heldFirst, wrote: wrote(), writes: firstBox.writes };
      await two; onGet = null; delete delays[K.path];
      r.twiceEnd = { hold: main.style.minHeight, wrote: wrote() };
      // an overtaken read that fails: no error comes out of the draw, and no message
      delays[K.path] = 100; lateFail[K.path] = 1;
      const b = ask(K.kind); await sleep(20);
      const toast0 = el("toast").textContent;
      await ask("payment_types");
      r.threw = await b.then(() => "ok", e => e.name); r.quiet = el("toast").textContent === toast0;
      delete delays[K.path]; delete lateFail[K.path];
      await ask("payment_types");
    }
    return out;
  });

  // 5b. the types read at the start: an overtaken draw writes nothing (its reply isn't kept, its page isn't drawn)
  await tryit("staleTypes", async () => {
    const r = {};
    run(`state.entity = ${FX.EXA}; state.setup.stopped = false; state.setup.deleted = false`);
    run(`state.setup.types = null; state.setup.kind = "parties"`);
    delays["/api/setup/types"] = [200, 10];
    const a = run(`viewSetup(__el("main"))`); await sleep(20);
    run(`state.setup.kind = "payment_types"`); await run(`viewSetup(__el("main"))`);
    const types = run(`state.setup.types`), sets = mainSets;
    await a; await sleep(20); delete delays["/api/setup/types"];
    r.after = { sameTypes: run(`state.setup.types`) === types, mainSets: mainSets - sets, page: smHtml.includes('data-setup-new="payment_types"') };
    await view("accounts", FX.EXA);
    return r;
  });

  // 5c. Show deleted is part of the draw of the checklist and the reminders too: the hold lasts until its table is written
  await tryit("deletedHold", async () => {
    const out = {};
    for (const [kind, D] of [["checklist", `/api/setup/restore?kind=checklist&entity=${FX.EXA}`], ["reminders", "/api/setup/restore?kind=reminders"]]) {
      run(`state.entity = ${FX.EXA}; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false`);
      await run(`viewSetup(__el("main"))`);
      run(`state.setup.deleted = true`); el("setupDeleted").innerHTML = "";
      let at = null; delays[D] = 120; onGet = p => { if (p === D) at = { hold: main.style.minHeight, section: smHtml.length > 200 }; };
      await run(`viewSetup(__el("main"))`);
      out[kind] = { at, hold: main.style.minHeight, table: el("setupDeleted").innerHTML.includes("None deleted") };
      onGet = null; delete delays[D]; run(`state.setup.deleted = false`);
    }
    return out;
  });

  // 7. Show deleted unticked while its table is read: nothing is drawn
  await tryit("untick", async () => {
    const D = `/api/setup/restore?kind=accounts&entity=${FX.EXA}`, r = {};
    await view("accounts", FX.EXA); run(`state.setup.deleted = true`);
    delays[D] = 120; const p = run(`drawDeleted("accounts")`); await sleep(20);
    run(`state.setup.deleted = false`); await run(`drawDeleted("accounts")`);   // the tick is taken off: the box is emptied
    await p; await sleep(10); delete delays[D];
    r.box = el("setupDeleted").innerHTML;
    delays[D] = 120; lateFail[D] = 1; run(`state.setup.deleted = true`); const q = run(`drawDeleted("accounts")`); await sleep(20);   // and a read that fails after the tick was taken off
    run(`state.setup.deleted = false`); await run(`drawDeleted("accounts")`); await q; await sleep(10); delete delays[D]; delete lateFail[D];
    r.afterFail = el("setupDeleted").innerHTML;
    return r;
  });

  // ---------- round 7 ----------
  // L1. the Show deleted read (the last of the draw) takes 900 ms, after the section was written: render()'s loading skeleton leaves the section alone
  await tryit("skeletonDeleted", async () => {
    const out = {}, EXA = FX.EXA;
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    const cases = [
      ["accounts", `/api/setup/accounts?entity=${EXA}`, `/api/setup/restore?kind=accounts&entity=${EXA}`, 'data-setup-new="accounts"', "Deleted bank accounts"],
      ["checklist", `/api/setup/checklist?entity=${EXA}`, `/api/setup/restore?kind=checklist&entity=${EXA}`, 'data-chk-new="1"', "None deleted"],
      ["reminders", "/api/setup/reminders", "/api/setup/restore?kind=reminders", 'data-rem-new="1"', "None deleted"]];
    run(`render = __realRender`);
    try {
      for (const deleted of [true, false]) for (const [kind, sect, rest, marker, table] of cases) {
        main.innerHTML = `<div>Overview</div>`;
        run(`render.last = null; state.view = "setup"; state.entity = ${EXA}; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = ${deleted}`);
        delays[sect] = [50]; delays[rest] = [900];
        const t0 = Date.now();
        await run(`render()`);
        out[`${kind}-${deleted ? "on" : "off"}`] = { section: smHtml.includes(marker), skeleton: /class="skel"/.test(main.innerHTML), grid: /class="setup-grid"/.test(main.innerHTML),
          table: deleted ? el("setupDeleted").innerHTML.includes(table) : true, hold: main.style.minHeight, loading: main.classList.contains("loading"), slow: (Date.now() - t0 > 850) === deleted };
        delete delays[sect]; delete delays[rest];
      }
    } finally { run(`render = async () => { __calls.push(["render"]); }; state.setup.deleted = false`); }
    await view("accounts", FX.EXA);
    return out;
  });

  // L1 (slice 0g). render()'s skeleton never covers a section that has been written, so nothing is drawn a second time: a section that takes 900 ms is read
  // once, and its own failure reaches render() (which paints it, with its Try again)
  await tryit("oneDraw", async () => {
    const out = {}, EXA = FX.EXA, A = `/api/setup/accounts?entity=${EXA}`;
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    const arrive = () => { main.innerHTML = `<div>Overview</div>`; run(`render.last = null; state.view = "setup"; state.entity = ${EXA}; state.setup.kind = "accounts"; state.setup.stopped = false; state.setup.deleted = false`); };
    run(`render = __realRender`);
    let n = 0; const count = () => { n = 0; onGet = p => { if (p === A) n++; }; delays[A] = [900]; };
    try {
      count(); arrive(); await run(`render()`); await sleep(40);
      out.slow = { reads: n, written: smHtml.includes('data-setup-new="accounts"'), skeleton: /class="skel"/.test(main.innerHTML), grid: /class="setup-grid"/.test(main.innerHTML) };
      // the read answers 500: the page says so, with its Try again
      count(); FX.status = { [A]: 500 }; arrive(); await run(`render()`); await sleep(40); FX.status = {};
      out.fails500 = { reads: n, html: main.innerHTML };
      await run(`click({ retry: "1" })`); await sleep(40);
      out.after500 = { grid: /class="setup-grid"/.test(main.innerHTML), error: /Couldn(&#39;|')t load/.test(main.innerHTML) };
      // the read can't reach the app: the page says it isn't running, with its Try again
      count(); lateFail[A] = 1; arrive(); await run(`render()`); await sleep(40); delete lateFail[A];
      out.rejects = { reads: n, html: main.innerHTML };
      await run(`click({ retry: "1" })`); await sleep(40);
      out.afterRejects = { grid: /class="setup-grid"/.test(main.innerHTML), error: /isn(&#39;|')t running/.test(main.innerHTML) };
    } finally { onGet = null; delete delays[A]; FX.status = {}; delete lateFail[A]; run(`render = async () => { __calls.push(["render"]); }`); }
    await view("accounts", EXA);
    return out;
  });

  // L2. a change was saved and what reads after it fails (the records overview, or a reply that isn't the records): the page says it was saved (never
  // that nothing was changed), once, the change was made once, and Try again only reads again: it opens no record and closes no dialog
  const SAVED_MSG = "It was saved, but this page could not reload. Try again.";
  const writesOf = (m, re) => calls.filter(x => x[0] === m && re.test(x[1]) && !(x[2] && x[2].preview)).length;
  const badToast = () => sandbox.__toasts.filter(t => t.bad).pop();
  const allSaid = () => [...sandbox.__toasts.map(t => t.msg), el("su-why-msg").innerHTML, el("pb-why-err").innerHTML, el("rsErr").innerHTML].join(" | ");
  const spyOn = () => run(`globalThis.__spy = []; for (const n of ["openSetup", "openChecklist", "openReminder", "closeDrawer"]) { globalThis["__orig_" + n] = globalThis[n]; globalThis[n] = (...a) => { __spy.push(n); return globalThis["__orig_" + n](...a); }; }`);
  const spyOff = () => run(`for (const n of ["openSetup", "openChecklist", "openReminder", "closeDrawer"]) if (globalThis["__orig_" + n]) { globalThis[n] = globalThis["__orig_" + n]; delete globalThis["__orig_" + n]; }`);
  let uniq = 100;
  await tryit("afterSave", async () => {
    const out = {}, EXA = FX.EXA, EXB = FX.EXB, CH = `/api/setup/checklist?entity=${EXA}`, RM = "/api/setup/reminders";
    const chk = FX.get[CH].items[0] || { id: 901 }, rem = FX.get[RM].rules[0];   // a company with no month set up has no item: the id is only sent
    if (!rem) throw new Error("a fixture has no rule");
    const openRec = async (kind, id, ent) => { run(`state.entity = ${ent}`); await run(`openSetup(${JSON.stringify(kind)}, ${JSON.stringify(id)})`); await sleep(20); };
    const why = (fn, act) => async () => { await run(`${fn}(${JSON.stringify(act)}, __btn)`); el("su-reason").value = "A reason"; await run(`whySubmit()`); };
    const fillAll = () => { for (const f of run(`state.setup.types.kinds[state.setup.drawer.kind].fields`)) { const e = el("su-" + f.key); e.value = "1"; e.checked = true; } };
    const chkPost = () => writesOf("POST", /\/api\/setup\/checklist$/), remPost = () => writesOf("POST", /\/api\/setup\/reminders$/);
    const SAVE = { w: () => writesOf("PATCH", /\/api\/setup\/accounts\/\d+$/), prep: () => openRec("accounts", FX.TEMP, EXB),
      fire: async () => { fillAll(); el("su-label").value = "Renamed account " + (++uniq); await run(`setupSave()`); await sleep(30); } };
    const FLOWS = {
      "delete": { w: () => writesOf("DELETE", /\/api\/setup\/accounts\/\d+$/), prep: () => openRec("accounts", FX.OLD, EXA), fire: why("setupAct", "delete") },
      "stop using": { w: () => writesOf("POST", /\/accounts\/\d+\/stop$/), prep: () => openRec("accounts", FX.TEMP, EXB), fire: why("setupAct", "stop") },
      "use again": { w: () => writesOf("POST", /\/accounts\/\d+\/use$/), prep: () => openRec("accounts", FX.OLD, EXA), fire: why("setupAct", "use") },
      "save": SAVE,
      "save (a reply that isn't the records)": { ...SAVE, bad: true },
      "add": { w: () => writesOf("POST", /\/api\/setup\/accounts$/), prep: () => openRec("accounts", "new", EXA), fire: async () => { fillAll(); await run(`setupSave()`); await sleep(30); } },
      "general settings": { w: () => writesOf("PATCH", /\/api\/setup\/settings$/),
        prep: async () => { await view("settings", EXA); const f = run(`state.setup.settings.fields`).find(x => !["bool", "select"].includes(x.type)); el("gs-" + f.key).value = String(++uniq); },
        fire: async () => { await run(`settingsSave()`); await sleep(30); } },
      "move setup import": { w: () => writesOf("POST", /^\/api\/setup\/import$/),
        prep: async () => { await view("move", EXA); run(`state.setup.move = { ...state.setup.move, file: { format: "hrp-setup" }, preview: {} }`); },
        fire: () => run(`moveImport("A reason")`) },
      "paste a list": { w: () => writesOf("POST", /\/api\/setup\/parties\/paste$/),
        prep: async () => { await view("parties", EXA); await run(`openPaste("parties", { force: true })`); el("ps-text").value = "a\tb"; el("ps-scope").value = "company"; el("ps-kind").value = "supplier";
          run(`state.setup.paste.preview = { counts: { add: 1 }, rows: [] }; state.setup.paste.previewFor = pasteForm()`); },
        fire: () => run(`pasteSave(false)`) },
      "put it back": { w: () => writesOf("POST", /\/api\/setup\/restore\/\d+$/),
        prep: async () => { await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20); el("pb-why").value = "A reason"; },
        fire: () => run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`) },
      // the flows that read the records through reloadMeta, which used to swallow a failed read
      "checklist: add an item": { kind: "checklist", w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: "new", completion: "manual" }`); el("cl-from").value = "2026-11"; el("cl-title").value = "A new item"; }, fire: () => run(`chkSave(false)`) },
      "checklist: stop using": { kind: "checklist", w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: ${chk.id} }`); el("cl-from").value = "2026-11"; }, fire: why("chkAct", "stop") },
      "checklist: delete an item": { kind: "checklist", w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: ${chk.id} }`); }, fire: why("chkAct", "delete") },
      "checklist: copy another company's": { kind: "checklist", w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: "copy" }`); el("cp-from").value = "2"; el("cl-from").value = "2026-11"; }, fire: () => run(`chkCopySave(false)`) },
      "reminders: save": { kind: "reminders", w: remPost, prep: () => { run(`state.setup.remOpen = { id: ${rem.id} }`); el("rm-from").value = "2026-11"; el("rm-title").value = "A title"; el("rm-days").value = "5"; }, fire: () => run(`remSave(false)`) },
      "reminders: delete": { kind: "reminders", w: remPost, prep: () => { run(`state.setup.remOpen = { id: ${rem.id} }`); }, fire: why("remAct", "delete") },
    };
    spyOn(); drawerInputsOn = true;   // the dialog has its inputs: a Save or Add leaves it clean only because what it held was saved
    try {
      for (const [name, F] of Object.entries(FLOWS)) {
        const r = out[name] = {};
        await run(`closeDrawer(true)`); await view(F.kind || "accounts", EXA);
        sandbox.__toasts.length = 0; el("su-why-msg").innerHTML = ""; el("pb-why-err").innerHTML = ""; el("rsErr").innerHTML = "";
        await F.prep(); calls.length = 0;
        const reads0 = run(`state.metaReads || 0`);
        if (F.bad) FX.bad = { "/api/meta": true }; else lateFail["/api/meta"] = 1;
        await Promise.resolve(F.fire()).catch(e => { r.threw = String(e); });
        r.hit = F.bad ? true : lateFail["/api/meta"] === 0; delete lateFail["/api/meta"];
        const bad = badToast();
        r.once = F.w(); r.said = !!bad && bad.msg === SAVED_MSG; r.tryAgain = !!(bad && bad.opts && bad.opts.action && bad.opts.action.label === "Try again");
        r.toasts = sandbox.__toasts.filter(t => t.bad).length;
        r.nothing = /Nothing was changed|Failed to fetch/.test(allSaid()); r.drawer = run(`state.setup.drawer`) === null;
        FX.bad = {}; calls.length = 0; run(`__spy.length = 0`);
        if (r.tryAgain) await bad.opts.action.fn();
        await sleep(30);
        r.again = { writes: F.w(), read: run(`state.metaReads || 0`) - reads0, rendered: calls.some(x => x[0] === "render"), spy: run(`__spy.slice()`), toasts: sandbox.__toasts.filter(t => t.bad).length };
      }
    } finally { spyOff(); drawerInputsOn = false; }
    await run(`closeDrawer(true)`); await view("accounts", EXA); run(`state.entity = ${EXA}`);
    return out;
  });

  // L2. ... and when the page's own read fails after the change was saved (render() paints it): the page says it was saved, in the same words, once (no
  // toast as well), with its own Try again, which draws the page again and sends nothing, and says it again if it fails again
  await tryit("afterSavePage", async () => {
    const out = {}, EXA = FX.EXA;
    const CH = `/api/setup/checklist?entity=${EXA}`, RM = "/api/setup/reminders", RQ = "/api/setup/required?entity=", AC = `/api/setup/accounts?entity=${EXA}`, ST = "/api/setup/settings", EN = "/api/setup/entities";
    const chk = FX.get[CH].items[0] || { id: 901 }, rem = FX.get[RM].rules[0], req = FX.get[RQ].types[0];
    if (!rem || !req) throw new Error("a fixture has no rule or type");
    sandbox.__btnArmed = { ...sandbox.__btn, dataset: { armed: "1" } };   // Tidy up's button, once it has counted what would go
    const go = async kind => { run(`state.entity = ${EXA}; state.view = "setup"; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false; state.setup.reqScope = null`);
      await run(`viewSetup(__el("main"))`); await sleep(20); };
    const why = (fn, act, btn = "__btn") => async () => { await run(`${fn}(${JSON.stringify(act)}, ${btn})`); el("su-reason").value = "A reason"; await run(`whySubmit()`); };
    const chkPost = () => writesOf("POST", /\/api\/setup\/checklist$/), remPost = () => writesOf("POST", /\/api\/setup\/reminders$/);
    const FLOWS = {
      "checklist: add an item": { kind: "checklist", path: CH, w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: "new", completion: "manual" }`); el("cl-from").value = "2026-11"; el("cl-title").value = "A new item"; }, fire: () => run(`chkSave(false)`) },
      "checklist: stop using": { kind: "checklist", path: CH, w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: ${chk.id} }`); el("cl-from").value = "2026-11"; }, fire: why("chkAct", "stop") },
      "checklist: delete an item": { kind: "checklist", path: CH, w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: ${chk.id} }`); }, fire: why("chkAct", "delete") },
      "checklist: copy another company's": { kind: "checklist", path: CH, w: chkPost, prep: () => { run(`state.setup.chkOpen = { id: "copy" }`); el("cp-from").value = "2"; el("cl-from").value = "2026-11"; }, fire: () => run(`chkCopySave(false)`) },
      "reminders: save": { kind: "reminders", path: RM, w: remPost, prep: () => { run(`state.setup.remOpen = { id: ${rem.id} }`); el("rm-from").value = "2026-11"; el("rm-title").value = "A title"; el("rm-days").value = "5"; }, fire: () => run(`remSave(false)`) },
      "reminders: delete": { kind: "reminders", path: RM, w: remPost, prep: () => { run(`state.setup.remOpen = { id: ${rem.id} }`); }, fire: why("remAct", "delete") },
      "required documents: save": { kind: "required", path: RQ, w: () => writesOf("POST", /\/api\/setup\/required$/), prep: () => { run(`state.setup.reqOpen = ${JSON.stringify(req.key)}`); el("rq-from").value = "2026-11"; }, fire: () => run(`reqSave(false)`) },
      "bank account: delete": { kind: "accounts", path: AC, w: () => writesOf("DELETE", /\/api\/setup\/accounts\/\d+$/), prep: async () => { await run(`openSetup("accounts", ${FX.OLD})`); await sleep(20); }, fire: why("setupAct", "delete") },
      "tidy up": { kind: "entities", path: EN, w: () => writesOf("POST", /^\/api\/months\/tidy$/), prep: async () => { await run(`openSetup("entities", ${EXA})`); await sleep(40); }, fire: why("setupAct", "tidy", "__btnArmed") },
      "general settings": { kind: "settings", path: ST, w: () => writesOf("PATCH", /\/api\/setup\/settings$/),
        prep: async () => { const f = run(`state.setup.settings.fields`).find(x => !["bool", "select"].includes(x.type)); el("gs-" + f.key).value = String(++uniq); }, fire: () => run(`settingsSave()`) },
      "move setup import": { kind: "move", path: "/api/setup/types", w: () => writesOf("POST", /^\/api\/setup\/import$/),
        prep: async () => { run(`state.setup.move = { ...state.setup.move, file: { format: "hrp-setup" }, preview: {} }`); }, fire: () => run(`moveImport("A reason")`) },
      "put it back": { kind: "accounts", path: AC, w: () => writesOf("POST", /\/api\/setup\/restore\/\d+$/),
        prep: async () => { await run(`openRestore(${FX.RESTORE}, "Spare")`); await sleep(20); el("pb-why").value = "A reason"; }, fire: () => run(`restoreGo(${FX.RESTORE}, { disabled: false, isConnected: true })`) },
    };
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    run(`render = __realRender`);
    try {
      for (const [name, F] of Object.entries(FLOWS)) {
        const r = out[name] = {};
        await run(`closeDrawer(true)`); await go(F.kind); sandbox.__toasts.length = 0; el("su-why-msg").innerHTML = "";
        await F.prep(); calls.length = 0;
        lateFail[F.path] = 1;
        await Promise.resolve(F.fire()).catch(e => { r.threw = String(e); });
        await sleep(40);
        r.hit = lateFail[F.path] === 0; delete lateFail[F.path];
        const html = main.innerHTML;
        r.once = F.w(); r.page = html.includes(SAVED_MSG); r.nothing = /Nothing was changed|isn(&#39;|')t running/.test(html + " " + allSaid()); r.retry = html.includes('data-retry="saved"');
        r.toasts = sandbox.__toasts.filter(t => t.msg === SAVED_MSG).length;
        calls.length = 0;
        lateFail[F.path] = 1; await run(`click({ retry: "saved" })`); await sleep(40); delete lateFail[F.path];   // its Try again fails again: it says it again
        r.again1 = main.innerHTML.includes(SAVED_MSG) && main.innerHTML.includes('data-retry="saved"');
        await run(`click({ retry: "saved" })`); await sleep(60);
        r.again = { writes: F.w(), page: !main.innerHTML.includes(SAVED_MSG) && /class="setup-grid"/.test(main.innerHTML) };
      }
      // a page that fails with no change saved says what it did before: the app has stopped, or the reason, and that nothing was changed
      await run(`closeDrawer(true)`); await go("accounts");
      lateFail[AC] = 1; await run(`render()`); out.plainStopped = { stopped: /isn(&#39;|')t running/.test(main.innerHTML), saved: main.innerHTML.includes(SAVED_MSG) };
      run(`ROUTES.zzz = { draw: () => async m => { throw new Error("The records could not be read."); } }; state.view = "zzz"`); await run(`render()`);
      out.plainError = { reason: main.innerHTML.includes("The records could not be read."), nothing: main.innerHTML.includes("Nothing was changed."), saved: main.innerHTML.includes(SAVED_MSG) };
    } finally { run(`render = async () => { __calls.push(["render"]); }; state.view = "setup"`); for (const k of Object.keys(lateFail)) delete lateFail[k]; }
    await view("accounts", EXA);
    return out;
  });

  // L2. a dialog with something typed in it is left alone when the reading back fails, and so is another dialog the user opened meanwhile (also when the
  // reading back works); the toast's Try again never reopens a record or closes a dialog, and says it again if it fails again; and a record that was saved
  // whose dialog can't be opened again leaves no dialog that adds it twice
  await tryit("dialogs", async () => {
    const r = {}, EXA = FX.EXA, EXB = FX.EXB, NOT_REOPENED = "It was saved, but its dialog could not be opened again.", REFUSED = "This was saved. Close it and open it again from the list.";
    const openRec = async (kind, id, ent) => { run(`state.entity = ${ent}`); await run(`openSetup(${JSON.stringify(kind)}, ${JSON.stringify(id)})`); await sleep(20); };
    const fillAll = () => { for (const f of run(`state.setup.types.kinds[state.setup.drawer.kind].fields`)) { const e = el("su-" + f.key); e.value = "1"; e.checked = true; } };
    const reset = async () => { await run(`closeDrawer(true)`); await view("accounts", EXA); sandbox.__toasts.length = 0; calls.length = 0; };
    const said = () => (badToast() || {}).msg === SAVED_MSG, open = d => run(`state.setup.drawer`) === d && !el("drawer").hidden;
    const toasted = msg => sandbox.__toasts.some(t => t.msg === msg);
    drawerInputsOn = true; spyOn();
    try {
      // 1. Stop using, with something typed in the dialog that the stop doesn't save: the dialog stays open, with what was typed
      await reset();
      await openRec("accounts", FX.TEMP, EXB); el("su-label").value = "typed before the stop";
      const d0 = run(`state.setup.drawer`);
      await run(`setupAct("stop", __btn)`); el("su-reason").value = "A reason"; lateFail["/api/meta"] = 1; await run(`whySubmit()`); await sleep(30);
      r.dirty = { open: open(d0), typed: el("su-label").value, said: said() };
      run(`__spy.length = 0`); await badToast().opts.action.fn(); await sleep(30);
      r.dirtyRetry = { spy: run(`__spy.slice()`), same: open(d0), typed: el("su-label").value };
      // 2. Save Acme; the re-read is slow and fails; meanwhile the user opens another record (and types in it, or doesn't): that dialog is left as it is, and so
      // after Try again
      for (const [key, typed] of [["other", true], ["otherClean", false]]) {
        await reset();
        await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq);
        delays["/api/meta"] = [250]; lateFail["/api/meta"] = 1;
        const saving = run(`setupSave()`); await sleep(80);                       // the write is done; the re-read is pending
        await run(`openSetup("accounts", ${FX.MAIN})`); await sleep(20);          // the user opens another record
        if (typed) el("su-label").value = "typed in the other record";            // and types in it
        const d1 = run(`state.setup.drawer`), want = el("su-label").value;
        await saving; await sleep(300); delete delays["/api/meta"];
        r[key] = { open: open(d1) && run(`state.setup.drawer`).id === FX.MAIN, kept: el("su-label").value === want, said: said(), once: writesOf("PATCH", /\/api\/setup\/accounts\/\d+$/) };
        run(`__spy.length = 0`); calls.length = 0; await badToast().opts.action.fn(); await sleep(40);
        r[key + "Retry"] = { spy: run(`__spy.slice()`), same: open(d1), kept: el("su-label").value === want, writes: calls.filter(x => x[0] !== "render").length };
      }
      // 3. Save Acme and type in it after the save, while the re-read is pending: the dialog stays open as typed, and Try again leaves it alone
      await reset();
      await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq);
      delays["/api/meta"] = [250]; lateFail["/api/meta"] = 1;
      const d2 = run(`state.setup.drawer`), saving2 = run(`setupSave()`); await sleep(80);
      el("su-label").value = "typed after the save";
      await saving2; await sleep(300); delete delays["/api/meta"];
      r.typedAfter = { open: open(d2), typed: el("su-label").value, said: said(), once: writesOf("PATCH", /\/api\/setup\/accounts\/\d+$/) };
      run(`__spy.length = 0`); calls.length = 0; await badToast().opts.action.fn(); await sleep(40);
      r.typedAfterRetry = { spy: run(`__spy.slice()`), same: open(d2), typed: el("su-label").value, writes: calls.filter(x => x[0] !== "render").length };
      // 4. the re-read WORKS (slowly) after the user opened another record: the saved record's dialog is not opened again over it
      await reset();
      await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq);
      delays["/api/meta"] = [250];
      const saving3 = run(`setupSave()`); await sleep(80);
      await run(`openSetup("accounts", ${FX.MAIN})`); await sleep(20);
      const d3 = run(`state.setup.drawer`), want3 = el("su-label").value; run(`__spy.length = 0`);
      await saving3; await sleep(300); delete delays["/api/meta"];
      r.guard = { spy: run(`__spy.slice()`), same: open(d3) && run(`state.setup.drawer`).id === FX.MAIN, kept: el("su-label").value === want3, once: writesOf("PATCH", /\/api\/setup\/accounts\/\d+$/), rendered: calls.some(x => x[0] === "render"), toasts: sandbox.__toasts.filter(t => t.bad).length };
      // 5. Try again fails again: a second "saved" toast (the first was used up by the click); the third works
      await reset(); await openRec("accounts", FX.OLD, EXA);
      await run(`setupAct("delete", __btn)`); el("su-reason").value = "A reason"; lateFail["/api/meta"] = 1; await run(`whySubmit()`); await sleep(30);
      const savedToasts = () => sandbox.__toasts.filter(t => t.msg === SAVED_MSG);
      r.retry1 = savedToasts().length;
      lateFail["/api/meta"] = 1; await savedToasts()[0].opts.action.fn(); await sleep(30);
      r.retry2 = savedToasts().length;
      calls.length = 0; await savedToasts()[1].opts.action.fn(); await sleep(30);
      r.retry3 = { saved: savedToasts().length, rendered: calls.some(x => x[0] === "render") };
      // 6. the record was added (or saved), what reads after it worked, but its dialog can't be opened again: the dialog is closed if nothing was typed in it
      // since, and one that stays open (typed in after the save) can't add the record again
      const posts = () => writesOf("POST", /\/api\/setup\/accounts$/), patches = () => writesOf("PATCH", /\/api\/setup\/accounts\/\d+$/), recPath = `/api/setup/accounts/${FX.TEMP}`;
      FX.post["/api/setup/accounts"] = { status: 200, body: { id: 777 } };   // its record has no answer: the read of it fails
      try {
        await reset(); await openRec("accounts", "new", EXA); fillAll();
        await run(`setupSave()`); await sleep(40);
        r.addClean = { drawer: run(`state.setup.drawer`) === null, said: toasted(NOT_REOPENED), posts: posts() };
        await run(`setupSave()`); await sleep(20);                            // a second click on Add
        r.addCleanAgain = { posts: posts() };
        await reset(); await openRec("accounts", "new", EXA); fillAll();
        delays["/api/setup/accounts/777"] = [150];
        const d4 = run(`state.setup.drawer`), adding = run(`setupSave()`); await sleep(60);
        el("su-label").value = "typed after the add";
        await adding; await sleep(40); delete delays["/api/setup/accounts/777"];
        r.addTyped = { open: open(d4) && run(`state.setup.drawer`).id === "new", typed: el("su-label").value, said: toasted(NOT_REOPENED), posts: posts() };
        await run(`setupSave()`); await sleep(20);                            // a second click on Add
        r.addTypedAgain = { posts: posts(), refused: toasted(REFUSED), open: open(d4) };
      } finally { delete FX.post["/api/setup/accounts"]; }
      for (const [key, typedAfter] of [["saveClean", false], ["saveTyped", true]]) {
        await reset(); await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq);
        delays[recPath] = [150]; lateFail[recPath] = 1;                        // the read that opens the record's dialog again fails
        const d5 = run(`state.setup.drawer`), saving4 = run(`setupSave()`); await sleep(60);
        if (typedAfter) el("su-label").value = "typed after the save";
        await saving4; await sleep(40); delete delays[recPath]; delete lateFail[recPath];
        r[key] = { drawer: typedAfter ? open(d5) : run(`state.setup.drawer`) === null, said: toasted(NOT_REOPENED), patches: patches(), typed: el("su-label").value };
      }
    } finally { spyOff(); drawerInputsOn = false; delete delays["/api/meta"]; delete lateFail["/api/meta"]; delete FX.post["/api/setup/accounts"]; }
    await run(`closeDrawer(true)`); await view("accounts", EXA); run(`state.entity = ${EXA}`);
    return r;
  });

  // slice 9c, known limits (j), (k) and (l): a half-typed reason counts as typed; the checklist and reminders Add dialogs never add twice; what is
  // typed while a change is sent, a dialog closed or another opened meanwhile, and a second submit
  await tryit("limits", async () => {
    const r = {}, EXA = FX.EXA, EXB = FX.EXB, REFUSED = "This was saved. Close it and open it again from the list.", NOT_REOPENED = "It was saved, but its dialog could not be opened again.";
    const CH = `/api/setup/checklist`, RM = "/api/setup/reminders", AC = "/api/setup/accounts", MAINREC = `/api/setup/accounts/${FX.MAIN}`, TEMPREC = `/api/setup/accounts/${FX.TEMP}`;
    const openRec = async (kind, id, ent) => { run(`state.entity = ${ent}`); await run(`openSetup(${JSON.stringify(kind)}, ${JSON.stringify(id)})`); await sleep(20); };
    const fillAll = () => { for (const f of run(`state.setup.types.kinds[state.setup.drawer.kind].fields`)) { const e = el("su-" + f.key); e.value = "1"; e.checked = true; } };
    const clean = () => { for (const k of Object.keys(delays)) delete delays[k]; for (const k of Object.keys(lateFail)) delete lateFail[k]; for (const k of Object.keys(postDelays)) delete postDelays[k]; FX.fail = {}; };
    const reset = async (kind = "accounts") => { clean(); await run(`closeDrawer(true)`); await view(kind, EXA); sandbox.__toasts.length = 0; calls.length = 0; el("su-refused").innerHTML = ""; };
    const sent = path => calls.filter(x => x[0] !== "render" && x[0] !== "navigate" && x[1] === path && !(x[2] && x[2].preview)).length;
    const toasted = msg => sandbox.__toasts.some(t => t.msg === msg);
    const shownNow = () => !el("drawer").hidden;
    const title = () => (/<h2[^>]*>([^<]*)<\/h2>/.exec(el("drawer").innerHTML) || [])[1] || "";
    const dirty = () => run(`drawerDirty()`);
    const was777 = FX.get["/api/setup/accounts/777"], wasPost = FX.post[AC];
    FX.get["/api/setup/accounts/777"] = JSON.parse(JSON.stringify(FX.get[TEMPREC])); FX.get["/api/setup/accounts/777"].record = { ...FX.get[TEMPREC].record, id: 777, label: "The saved account" };
    FX.post[AC] = { status: 200, body: { id: 777 } };
    drawerInputsOn = true;
    try {
      // (j) a reason half-typed under Stop using, with nothing else typed: a Save whose record can't be opened again, or whose reading back fails, keeps the dialog and the reason
      for (const [key, fail] of [["jReopen", TEMPREC], ["jReread", "/api/meta"]]) {
        await reset(); await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq);
        await run(`setupAct("stop", __btn)`); el("su-reason").value = "Half a reas";
        lateFail[fail] = 1; await run(`setupSave()`); await sleep(60);
        r[key] = { open: shownNow() && run(`state.setup.drawer`) !== null, reason: el("su-reason").value, box: el("setupWhy").hidden, said: toasted(fail === TEMPREC ? NOT_REOPENED : SAVED_MSG), writes: sent(TEMPREC) };
      }
      // ...but the reason of the change itself has left the box once the change is kept: the stale dialog closes, and a reason typed in a box
      // opened while the page is read again counts
      await reset(); await openRec("accounts", FX.TEMP, EXB);
      await run(`setupAct("stop", __btn)`); el("su-reason").value = "A reason"; delays["/api/meta"] = [200]; lateFail["/api/meta"] = 1;
      let stopping = run(`whySubmit()`); await sleep(60);
      r.jGone = { hiddenWhileReading: el("setupWhy").hidden, value: el("su-reason").value };
      await run(`setupAct("delete", __btn)`); el("su-reason").value = "Typed while it was read";
      await stopping; await sleep(40);
      r.jNew = { open: shownNow(), reason: el("su-reason").value, box: el("setupWhy").hidden };

      // (k) the checklist's and the reminders' Add: kept, then the reading back fails with something typed since: the dialog stays and never adds again
      const chkItem = () => run(`(() => { if (!state.setup.chk.items.some(x => x.id === 901)) state.setup.chk.items.push({ id: 901, code: "made", completion: "hand", in_use: 1, used: 0, can_delete: true,
        now: { from_month: "0000-00", title: "Made item", detail: "", due_offset: 0, due_day: 5, docs: [], deadline: 0, in_use: 1 }, history: [] }); })()`);
      const chkAdd = async () => { await reset("checklist"); chkItem(); await run(`openChecklist("new")`); el("cl-completion").value = "hand"; el("cl-title").value = "A new item"; el("cl-day").value = "5"; el("cl-from").value = "2026-11"; };
      const remAdd = async () => { await reset("reminders"); await run(`openReminder("new")`); el("rm-key").value = "made_key"; el("rm-kind").value = "joiner"; el("rm-title").value = "Made reminder"; el("rm-detail").value = "Made detail"; el("rm-days").value = "3"; el("rm-from").value = "2026-11"; };
      const ADDS = { checklist: { open: chkAdd, save: p => `chkSave(${p})`, path: CH, field: "cl-title", answer: { item_id: 901, affected: {}, lines: [] } },
        reminders: { open: remAdd, save: p => `remSave(${p})`, path: RM, field: "rm-title", answer: { id: run(`0`), affected: {}, lines: [] } } };
      const remRule = FX.get[RM].rules[0];
      ADDS.reminders.answer.id = remRule.id;
      for (const [kind, A] of Object.entries(ADDS)) {
        FX.post[A.path] = { status: 200, body: A.answer };
        await A.open(); delays["/api/meta"] = [200]; lateFail["/api/meta"] = 1;
        const adding = run(A.save(false)); await sleep(60);
        el(A.field).value = "typed after the add";
        await adding; await sleep(40);
        const k = r["k_" + kind] = { open: shownNow(), typed: el(A.field).value, posts: sent(A.path) };
        await run(A.save(false)); await sleep(30);
        k.again = { posts: sent(A.path), refused: toasted(REFUSED) };
        calls.length = 0; await run(A.save(true)); k.preview = calls.filter(x => x[1] === A.path && x[2].preview).length;

        // (l3) a second submit while the first is on its way sends nothing; after a refusal, or no answer, it can be sent again
        await A.open(); postDelays[A.path] = 150;
        await Promise.all([run(A.save(false)), run(A.save(false))]); await sleep(30);
        const l3 = r["l3_" + kind] = { posts: sent(A.path) };
        await A.open(); FX.post[A.path] = { status: 400, body: { error: "A made-up refusal." } };
        l3.refused = await run(A.save(false) + `.then(() => "ok", e => e.message)`);
        FX.fail = { [A.path]: true }; l3.lost = await run(A.save(false) + `.then(() => "ok", e => e.name)`); FX.fail = {};
        FX.post[A.path] = { status: 200, body: A.answer }; await run(A.save(false)); await sleep(30);
        l3.retry = sent(A.path);

        // (l1) what is typed while the Add is on its way: with the reading back failing, the dialog stays as typed (and can't add again) ...
        await A.open(); postDelays[A.path] = 150; lateFail["/api/meta"] = 1;
        let going = run(A.save(false)); await sleep(50); el(A.field).value = "typed while it was sent"; await going; await sleep(40);
        r["l1fail_" + kind] = { open: shownNow(), typed: el(A.field).value, dirty: dirty() };
        // ... and with it working, the saved record's dialog opens with what was typed, not saved yet
        await A.open(); postDelays[A.path] = 150;
        going = run(A.save(false)); await sleep(50); el(A.field).value = "typed while it was sent"; await going; await sleep(40);
        r["l1_" + kind] = { title: title(), typed: el(A.field).value, dirty: dirty() };

        // (l2) closed while it is on its way, and another dialog opened: the saved record's dialog doesn't take its place; closed and nothing opened, it stays closed
        await A.open(); postDelays[A.path] = 150;
        going = run(A.save(false)); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", FX.MAIN, EXA); run(`state.setup.kind = "${kind}"`);
        const other = el("drawer").innerHTML; await going; await sleep(40);
        r["l2other_" + kind] = { same: el("drawer").innerHTML === other && run(`state.setup.drawer && state.setup.drawer.id`) === FX.MAIN, dirty: dirty() };
        await A.open(); postDelays[A.path] = 150;
        going = run(A.save(false)); await sleep(40); await run(`closeDrawer(true)`); await going; await sleep(40);
        r["l2closed_" + kind] = { closed: !shownNow() && run(`state.setup.${kind === "checklist" ? "chkOpen" : "remOpen"}`) === null };
        // closed and the same Add opened again: the new dialog isn't taken as saved, and what is typed in it counts
        await A.open(); postDelays[A.path] = 150;
        going = run(A.save(false)); await sleep(40); await run(`closeDrawer(true)`); await run(kind === "checklist" ? `openChecklist("new")` : `openReminder("new")`);
        el(A.field).value = "typed in the new one"; await going; await sleep(40);
        r["l2again_" + kind] = { typed: el(A.field).value, dirty: dirty(), saved: run(`!!state.setup.${kind === "checklist" ? "chkOpen" : "remOpen"}?.saved`) };
        delete FX.post[A.path];
      }
      // the server's answer names no reminder: it is found by its key, and not opened over a dialog opened meanwhile
      FX.post[RM] = { status: 200, body: { affected: {}, lines: [] } };
      await remAdd(); el("rm-key").value = remRule.key; postDelays[RM] = 150;
      let going = run(`remSave(false)`); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", FX.MAIN, EXA); run(`state.setup.kind = "reminders"`);
      let other = el("drawer").innerHTML; await going; await sleep(60);
      r.l2byKey = { same: el("drawer").innerHTML === other };
      await remAdd(); el("rm-key").value = remRule.key; await run(`remSave(false)`); await sleep(60);
      r.byKey = { opened: run(`state.setup.remOpen && state.setup.remOpen.id`) === remRule.id };
      delete FX.post[RM];

      // Delete, or Copy, answered after another dialog was opened: that one isn't closed
      const meanwhile = async (kind, prep, fire, path) => {
        await reset(kind); await prep(); postDelays[path] = 150;
        const going = fire(); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", FX.MAIN, EXA); run(`state.setup.kind = "${kind}"`);
        const other = el("drawer").innerHTML; await going; await sleep(40);
        return shownNow() && el("drawer").innerHTML === other;
      };
      const why = (fn, act) => async () => { await run(`${fn}(${JSON.stringify(act)}, __btn)`); el("su-reason").value = "A reason"; return run(`whySubmit()`); };
      r.l2delete = {
        record: await meanwhile("accounts", () => openRec("accounts", FX.OLD, EXA), why("setupAct", "delete"), `/api/setup/accounts/${FX.OLD}`),
        checklist: await meanwhile("checklist", async () => { chkItem(); await run(`openChecklist(901)`); el("cl-from").value = "2026-11"; }, why("chkAct", "delete"), CH),
        reminder: await meanwhile("reminders", async () => { await run(`openReminder(${remRule.id})`); el("rm-from").value = "2026-11"; }, why("remAct", "delete"), RM),
        copy: await meanwhile("checklist", async () => { run(`state.setup.chkOpen = { id: "copy" }`); el("cp-from").value = "2"; el("cl-from").value = "2026-11"; }, () => run(`chkCopySave(false)`), CH),
        paste: await meanwhile("parties", async () => { await run(`openPaste("parties", { force: true })`); el("ps-text").value = "a\tb"; el("ps-scope").value = "company"; el("ps-kind").value = "supplier";
          run(`state.setup.paste.preview = { counts: { add: 1 }, rows: [] }; state.setup.paste.previewFor = pasteForm()`); }, () => run(`pasteSave(false)`), "/api/setup/parties/paste"),
      };
      // Stop using answered after another record was opened, and its reason box too: neither is touched
      await reset(); await openRec("accounts", FX.TEMP, EXB); await run(`setupAct("stop", __btn)`); el("su-reason").value = "A reason"; postDelays[`/api/setup/accounts/${FX.TEMP}/stop`] = 150;
      let stop2 = run(`whySubmit()`); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", FX.MAIN, EXA); await run(`setupAct("stop", __btn)`); el("su-reason").value = "The other reason";
      other = el("drawer").innerHTML; await stop2; await sleep(40);
      r.l2stop = { same: el("drawer").innerHTML === other && run(`state.setup.drawer.id`) === FX.MAIN, reason: el("su-reason").value, box: el("setupWhy").hidden };
      // Copy twice
      await reset("checklist"); run(`state.setup.chkOpen = { id: "copy" }`); el("cp-from").value = "2"; el("cl-from").value = "2026-11"; postDelays[CH] = 100;
      await Promise.all([run(`chkCopySave(false)`), run(`chkCopySave(false)`)]); r.l3copy = sent(CH);

      // (l) the record dialog. l3: a second submit while the first is on its way
      for (const [key, rec, path, ent] of [["add", "new", AC, EXA], ["save", FX.TEMP, TEMPREC, EXB]]) {
        await reset(); await openRec("accounts", rec, ent); fillAll(); el("su-label").value = "Made account " + (++uniq); postDelays[path] = 150;
        await Promise.all([run(`setupSave()`), run(`setupSave()`)]); await sleep(40);
        const one = r["l3_" + key] = { posts: sent(path) };
        await reset(); await openRec("accounts", rec, ent); fillAll(); el("su-label").value = "Made account " + (++uniq);
        const good = FX.post[path]; FX.post[path] = { status: 400, body: { error: "A made-up refusal." } };
        await run(`setupSave()`); one.refused = el("su-refused").innerHTML;
        FX.fail = { [path]: true }; await run(`setupSave().catch(e => e.name)`); FX.fail = {};
        if (good) FX.post[path] = good; else delete FX.post[path];
        await run(`setupSave()`); await sleep(40); one.retry = sent(path);
      }
      // l1: typed while the Add or the Save is on its way
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150; lateFail["/api/meta"] = 1;
      let saving = run(`setupSave()`); await sleep(50); el("su-label").value = "typed while it was sent"; await saving; await sleep(40);
      r.l1addFail = { open: shownNow() && run(`state.setup.drawer.id`) === "new", typed: el("su-label").value, dirty: dirty(), said: toasted(SAVED_MSG) };
      await run(`setupSave()`); r.l1addFail.again = { posts: sent(AC), refused: toasted(REFUSED) };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150;
      saving = run(`setupSave()`); await sleep(50); el("su-label").value = "typed while it was sent"; await saving; await sleep(60);
      r.l1add = { id: run(`state.setup.drawer.id`), title: title(), typed: el("su-label").value, dirty: dirty(), foot: el("su-foot").textContent };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); delays["/api/setup/accounts/777"] = [150];   // typed while the saved record is read
      saving = run(`setupSave()`); await sleep(60); el("su-label").value = "typed while it was read"; await saving; await sleep(60);
      r.l1read = { id: run(`state.setup.drawer.id`), typed: el("su-label").value, dirty: dirty() };
      await reset(); await openRec("accounts", FX.TEMP, EXB); fillAll(); el("su-label").value = "Renamed account " + (++uniq); postDelays[TEMPREC] = 150;
      saving = run(`setupSave()`); await sleep(50); el("su-notes").value = "typed while it was saved"; await saving; await sleep(60);
      r.l1save = { id: run(`state.setup.drawer.id`) === FX.TEMP, notes: el("su-notes").value, label: el("su-label").value, server: FX.get[TEMPREC].record.label, dirty: dirty() };
      // nothing typed meanwhile: the saved record's dialog is clean
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 100; await run(`setupSave()`); await sleep(60);
      r.l1clean = { id: run(`state.setup.drawer.id`), label: el("su-label").value, dirty: dirty() };
      // what was typed in a field the saved record can't change isn't carried into it
      const PT = "/api/setup/payment_types", PT7 = "/api/setup/payment_types/778";
      FX.get[PT7] = JSON.parse(JSON.stringify(FX.get[`/api/setup/payment_types/${FX.SALARY}`])); FX.get[PT7].record = { ...FX.get[PT7].record, id: 778, key: "made_key", label: "Made type", system: 0 }; FX.get[PT7].locked = { key: "It never changes." };
      FX.post[PT] = { status: 200, body: { id: 778 } };
      await reset("payment_types"); await openRec("payment_types", "new", EXA); fillAll(); postDelays[PT] = 150;
      saving = run(`setupSave()`); await sleep(50); el("su-key").value = "typed_key"; await saving; await sleep(60);
      r.l1locked = { key: el("su-key").value, dirty: dirty() };
      delete FX.post[PT]; delete FX.get[PT7];
      // l2: closed while it is on its way and another opened, or nothing; the same while the saved record is read; a refusal then is said in a message
      for (const [key, status] of [["l2add", 200], ["l2refused", 400]]) {
        await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150;
        FX.post[AC] = status === 200 ? { status, body: { id: 777 } } : { status, body: { error: "A made-up refusal." } };
        saving = run(`setupSave()`); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", FX.MAIN, EXA); el("su-label").value = "typed in the other";
        other = el("drawer").innerHTML; el("su-refused").innerHTML = ""; await saving; await sleep(60);
        r[key] = { same: el("drawer").innerHTML === other && run(`state.setup.drawer.id`) === FX.MAIN, typed: el("su-label").value, dirty: dirty(), inDialog: el("su-refused").innerHTML,
          toasts: sandbox.__toasts.map(t => t.msg), posts: sent(AC) };
      }
      // ...and a server failure then is said as not known
      FX.post[AC] = { status: 500, body: { error: "The server could not save it." } };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150;
      saving = run(`setupSave()`); await sleep(40); await run(`closeDrawer(true)`); await saving; await sleep(40);
      r.l2unsure = sandbox.__toasts.map(t => t.msg);
      FX.post[AC] = { status: 200, body: { id: 777 } };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150;
      saving = run(`setupSave()`); await sleep(40); await run(`closeDrawer(true)`); await saving; await sleep(60);
      r.l2closed = { closed: !shownNow() && run(`state.setup.drawer`) === null };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); delays["/api/setup/accounts/777"] = [150];
      saving = run(`setupSave()`); await sleep(60); await run(`closeDrawer(true)`); await saving; await sleep(60);
      r.l2read = { closed: !shownNow() && run(`state.setup.drawer`) === null };
      await reset(); await openRec("accounts", "new", EXA); fillAll(); postDelays[AC] = 150;
      saving = run(`setupSave()`); await sleep(40); await run(`closeDrawer(true)`); await openRec("accounts", "new", EXA); el("su-label").value = "typed in the new one"; await saving; await sleep(60);
      r.l2new = { id: run(`state.setup.drawer.id`), typed: el("su-label").value, dirty: dirty(), saved: run(`!!state.setup.drawer.saved`) };
    } finally {
      drawerInputsOn = false; clean();
      if (was777 === undefined) delete FX.get["/api/setup/accounts/777"]; else FX.get["/api/setup/accounts/777"] = was777;
      if (wasPost === undefined) delete FX.post[AC]; else FX.post[AC] = wasPost;
      delete FX.post[CH]; delete FX.post[RM];
    }
    await run(`closeDrawer(true)`); await view("accounts", EXA); run(`state.entity = ${EXA}`);
    return r;
  });

  // L2. what says "it was saved" belongs to the page that says it: a later, unrelated failure of the page says what it always said
  await tryit("noLeak", async () => {
    const r = {}, EXA = FX.EXA, AC = `/api/setup/accounts?entity=${EXA}`, P = `/api/setup/parties?entity=${EXA}`;
    const open = async () => { run(`state.entity = ${EXA}`); await run(`openSetup("accounts", ${FX.OLD})`); await sleep(20); };
    const delOld = async () => { await run(`setupAct("delete", __btn)`); el("su-reason").value = "A reason"; await run(`whySubmit()`); await sleep(40); };
    const plain = async fn => { sandbox.__toasts.length = 0; await fn(); const h = main.innerHTML; return { saved: h.includes(SAVED_MSG), says: /isn(&#39;|')t running/.test(h) || /Couldn(&#39;|')t load/.test(h) }; };
    const toRealRender = () => run(`render = __realRender; state.view = "setup"; state.entity = ${EXA}; state.setup.kind = "accounts"; state.setup.deleted = false; render.last = null`);
    try {
      // 1. a saved change whose records read failed (a toast, no page painted), then a page that fails for its own reasons
      await run(`closeDrawer(true)`); await view("accounts", EXA); await open(); lateFail["/api/meta"] = 1; await delOld(); delete lateFail["/api/meta"];
      toRealRender(); lateFail[AC] = 1;
      r.afterToast = await plain(() => run(`render()`));
      // 2. a page that painted "it was saved", then another place whose read fails
      await run(`closeDrawer(true)`); run(`render = async () => { __calls.push(["render"]); }`); await view("accounts", EXA);
      toRealRender(); await open(); lateFail[AC] = 1; await delOld();
      r.pageSaved = main.innerHTML.includes(SAVED_MSG);
      lateFail[P] = 1;
      r.afterPlace = await plain(() => run(`applyPlace({ view: "setup", entity: ${EXA}, month: "2026-11", sub: "parties", id: null, params: {} }, { fresh: true })`));
      // 3. the same, then a section switch (redraw)
      run(`render.last = null`); await go2("accounts"); await open(); lateFail[AC] = 1; await delOld();
      r.pageSaved2 = main.innerHTML.includes(SAVED_MSG);
      run(`state.setup.kind = "parties"`); lateFail[P] = 1;
      r.afterRedraw = await plain(() => run(`redraw()`));
    } finally { run(`render = async () => { __calls.push(["render"]); }; state.view = "setup"`); for (const k of Object.keys(lateFail)) delete lateFail[k]; }
    await run(`closeDrawer(true)`); await view("accounts", EXA);
    return r;
    async function go2(kind) { run(`state.entity = ${EXA}; state.view = "setup"; state.setup.kind = ${JSON.stringify(kind)}; state.setup.stopped = false; state.setup.deleted = false`); await run(`viewSetup(__el("main"))`); await sleep(20); }
  });

  // Round 8. render() leaves a page that was overtaken as it always did (a late draw can paint over a newer page: a known limit, which wants a fix in
  // the shell), but never draws anything again: a slow page A, a fast page B opened meanwhile, A's late paint, and then page C, which stays on show
  await tryit("noRedo", async () => {
    const r = {};
    run(`globalThis.__d = { a: 0, b: 0, c: 0, quick: 0 };
      ROUTES.pageA = { draw: () => async m => { await new Promise(res => setTimeout(res, 300)); __d.a++; m.innerHTML = "<div>A page</div>"; } };
      ROUTES.pageB = { draw: () => async m => { const n = ++__d.b; if (n > 1) await new Promise(res => setTimeout(res, 300)); m.innerHTML = "<div>B page " + n + "</div>"; } };
      ROUTES.pageC = { draw: () => async m => { __d.c++; m.innerHTML = "<div>C page</div>"; } };
      ROUTES.quick = { draw: () => async m => { __d.quick++; m.innerHTML = "<div>quick page</div>"; } };
      render = __realRender; render.last = null; state.view = "pageA"`);
    try {
      const a = run(`render()`); await sleep(40);
      run(`state.view = "pageB"`); await run(`render()`);                  // B is quick
      await sleep(330);                                                      // A's read comes and paints over B
      run(`state.view = "pageC"`); await run(`render()`);                  // C is quick, and is the page on show
      await a; await sleep(400);
      r.timeline = { page: main.innerHTML, view: run(`state.view`), a: run(`__d.a`), b: run(`__d.b`), c: run(`__d.c`) };
      // the normal path: one render, one draw
      run(`__d.quick = 0; render.last = null; state.view = "quick"`); await run(`render()`); await sleep(60);
      r.once = run(`__d.quick`);
    } finally { run(`render = async () => { __calls.push(["render"]); }; state.view = "setup"; delete ROUTES.pageA; delete ROUTES.pageB; delete ROUTES.pageC; delete ROUTES.quick`); }
    await view("accounts", FX.EXA);
    return r;
  });
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""

fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps({"get": GET, "post": POST, "EXA": EXA, "EXB": EXB, "MAIN": main["id"], "OLD": old["id"], "SALARY": salary["id"], "TEMP": temp["id"], "TEMP_AFTER": TEMP_AFTER, "RESTORE": restored["row_id"], "TAKEN": taken["row_id"],
                                "RS_EXD": EXD_ROW, "PREVIEW": PREVIEW}), encoding="utf-8")
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
files = [str(f) for f in app_files() if not str(f).endswith("main.js")]   # the page's own start-up is left out
res = subprocess.run([shutil.which("node"), str(probe), str(fx_path), *files], capture_output=True, text=True, encoding="utf-8", timeout=180)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the Setup pages' script ran on the stand-in page, against the server's own answers", o is not None, res.stderr[-1500:])


def plain(v):
    """The page escapes an apostrophe as &#39;: the checks read the words."""
    if isinstance(v, str):
        return v.replace("&#39;", "'")
    if isinstance(v, list):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    return v


class Soft(dict):
    """A probe answer that may be missing: a key not there reads as an empty answer, so every check runs (and with HRP_KEEP_GOING is listed)."""
    def __missing__(self, k):
        return Soft()

    def count(self, *a):
        return 0


def soften(v):
    if isinstance(v, dict):
        return Soft({k: soften(x) for k, x in v.items()})
    return [soften(x) for x in v] if isinstance(v, list) else v


o = soften(plain(o))


def has(html, *parts):
    return all(p in html for p in parts)


def n(html, pat):
    return len(re.findall(pat, html))


# ---------- the Setup menu ----------
GROUPS = ["Companies and banks", "People and payments", "Payments and documents", "Monthly work", "Matching words", "General"]
check("the Setup menu has the six groups of the server, in order", o["groupsSql"] == GROUPS, o["groupsSql"])
nav = o["accounts"]["nav"]
check("each section is a button with its glyph, the one on show is aria-current, and the groups are named",
      n(nav, r'<button type="button" class="sn[ "]') >= 15 and n(nav, r'aria-current="page"') == 1 and 'class="sn on" data-setup-kind="accounts" aria-current="page"' in nav
      and all(g in nav for g in GROUPS) and n(nav, r'<svg class="glyph"') >= 16, n(nav, r'<button type="button" class="sn'))
check("Recurring payments is a link to its page, with its note and the external mark: it has one home",
      re.search(r'<a class="sn" href="#/EXA/2026-11/payments/recurring" data-setup-link="payees" aria-describedby="sn-note-payees">.*?Opens Payments › Recurring', nav) is not None
      and 'data-setup-kind="payees"' not in nav, nav[:600])
check("Matching words are left out of the menu of a company Kept here, and in the menu of one Kept in SQL Account", o["groupsHere"] == [g for g in GROUPS if g != "Matching words"]
      and "Matching words" in nav and "Matching words" not in o["hereNav"] and 'data-setup-kind="guess_words"' not in o["hereNav"] and 'data-setup-kind="guess_words"' in nav)
check("a group the server adds later (HR, slice 11) shows in the menu with its sections, and one it has no section for is left out",
      "HR:approvers" in o["groupsHr"] and 'data-setup-kind="approvers"' in o["navHr"] and "nothere" not in o["navHr"], o["groupsHr"])
check("the menu is Setup's own: the groups are headings of a labelled group of buttons", n(nav, r'role="group" aria-labelledby="sn-g-\d"') == 6)

# ---------- Matching words for a company Kept here ----------
card = o["hereCard"]
check("an old link to Matching words for a company Kept here shows the card: not used, why, the way to a company that does",
      has(card, "Matching words aren't used for EXB", "Example Beta Ltd is Kept here, so there are no SQL vouchers or documents to match",
          "Go to EXA", 'data-pick-entity="', "This page is left out of EXB's Setup menu. An old link or bookmark opened it.") and "<table" not in card, card[:500])
check("a company Kept in SQL Account sees the list", has(o["sqlWords"], "Payment type guesses", 'data-setup-new="guess_words"') and "aren't used" not in o["sqlWords"])
check("switching company to one Kept here from Matching words lands on its Overview and says so; from another section it stays",
      o["tbPlace"] == {"view": "overview", "gone": "Matching words", "plural": True} and o["tbPlaceOk"] == {"view": "setup", "gone": None}, (o["tbPlace"], o["tbPlaceOk"]))

# ---------- the shared list ----------
page = o["accounts"]["page"]
check("the head: the group, the section with its company, its sentence, and the Add button with its glyph",
      has(page, '<span class="eyebrow">Companies and banks</span>', "Bank accounts · EXA</h1>", "How each company's bank accounts are named here and in SQL Account.",
          'data-setup-new="accounts"', "Add bank account") and "Paste a list" not in page, page[:700])
check("the toolbar: search, the count, Show stopped with how many, Show deleted, and the sentence about stopping",
      has(page, 'data-search="setup-accounts"', 'data-setup-stopped', "Show stopped (1)", 'data-setup-deleted="accounts"', "Show deleted",
          "Click a row to change it. Something already used can't be deleted: stop using it instead, and its history stays."))
check("a row: its name as a button, its last four digits, the bank, Used by with what uses it, and the status",
      has(page, 'data-setup-open="', ">Main</button>", "···· 4417", "Example Bank", 'class="pill ok">In use') and "Old savings" not in page, page[page.index("<tbody>"):][:900])
check("Used by says how many and what uses it; a stopped record is left out until Show stopped is ticked",
      re.search(r'<td class="st-used"[^>]*><b>\d+</b><div class="note st-sub">[^<]*payment', page) is not None and "Old savings" not in page and "Show stopped (1)" in page)
ent = o["entities"]
check("a company's list has the Books column: Kept in SQL Account or Kept here, never a code or a yes",
      has(ent, ">Books<", "Kept in SQL Account", "Kept here"), ent[:900])
short_hint = next(f.get("hint", "") for f in call("get", "/api/setup/types")["kinds"]["entities"]["fields"] if f["key"] == "short_name")
check("slice 9c: the company switcher shows full names, so Setup's Companies list has no Switcher line, and the Short name field no longer says the switcher shows it",
      "Switcher:" not in ent and "beside the code" not in short_hint and "full name" in short_hint, (short_hint, ent[:900]))
check("an empty section says None yet, and offers to add one (a name that keeps its capitals: GL account)",
      has(o["emptyNone"], "None yet.", 'data-setup-new="gl_accounts"', "Add GL account"), o["emptyNone"][-700:])
check("a section with only stopped records says so and offers Show stopped",
      has(o["onlyStopped"], "Only stopped statutory accounts: tick Show stopped to see them.", 'data-setup-show-stopped="statutory_accounts"'))
check("a search that finds nothing says so and offers to clear it", has(o["noMatch"], "No customers and suppliers match.", 'data-setup-clear="parties"'))
check("a long list shows 25 rows, says how many, and Show 25 more is only the rest",
      n(o["parties"], r'class="st-row') == 25 and has(o["parties"], "Showing 25 of 30 customers and suppliers", 'data-setup-more="parties"', "Show 5 more"))
check("Show more adds the rest and the button goes", n(o["partiesMore"], r'class="st-row') == 30 and "Show 5 more" not in o["partiesMore"] and "data-setup-more" not in o["partiesMore"])
check("Paste a list is beside Add on the sections that have it", has(o["parties"], 'data-setup-paste="parties"', "Paste a list"))
check("two sections share a tab strip with their counts: customers and suppliers with the chart, payment types with document types",
      has(o["parties"], 'role="tablist"', 'data-setup-kind="gl_accounts"', 'aria-selected="false"') and has(o["types"], 'role="tab"', "Payment types", "Document types")
      and re.search(r'Document types <span class="tab-n">\d+</span>', o["types"]) is not None)
check("the types are listed by name, with their key, money and legal deadline", has(o["types"], ">Name<", ">Key<", ">Money<", ">Legal deadline<") and "Used by the app" in o["types"])

# ---------- the record dialog ----------
dlg = o["dlgAccount"]
check("the dialog is Setup's centred one, and its fields are in the board's groups",
      o["dlgClass"] is True and all(f'<legend>{g}</legend>' in dlg for g in ("The account", "SQL Account", "Printed on invoices", "Notes")), dlg[:300])
check("a field needed says Required, the hints are linked to their field, a tick is a checkbox",
      has(dlg, 'Name<span class="req">Required</span>', 'id="su-label-hint"', 'aria-describedby="su-label-err su-label-hint"', 'id="su-label-err"', 'type="checkbox"', "Cash book account"),
      [p for p in ('Name<span class="req">Required</span>', 'id="su-label-hint"', 'aria-describedby="su-label-err su-label-hint"') if p not in dlg])
check("a field that can't change says so, with why: a payment type's key; and one the app relies on says it can't be deleted",
      has(o["dlgSystem"], 'class="req lock"', "Can't be changed", 'class="note lock-why"', 'id="su-key-lock"', "readonly", "Used by the app", "can't be deleted") and 'data-setup-act="delete"' not in o["dlgSystem"],
      o["dlgSystem"][o["dlgSystem"].index('id="su-key"') - 200:][:700])
check("Where used, In use (Stop using, with a note) and History are in the dialog", has(dlg, "<h3", "Where used", ">In use<", 'data-setup-act="stop"', "Stop using", "History", 'data-hist="accounts:'))
check("an unused record says so, and may be deleted; a stopped one offers Use again, not Stop using",
      has(o["dlgStopped"], 'data-setup-act="use"', "Use again", "Stopped</span>") and 'data-setup-act="stop"' not in o["dlgStopped"] and "Not used anywhere yet" in o["dlgStopped"]
      and 'data-setup-act="delete"' in o["dlgStopped"])
check("a new record's dialog has no Where used or In use, and says what Save does",
      has(o["dlgNew"], "New bank account", "Add bank account", "Nothing is kept until you add it.") and "Where used" not in o["dlgNew"] and "In use</h3>" not in o["dlgNew"])
check("the company's dialog: Kept in SQL Account is a tick with the words of both answers",
      has(o["dlgSql"], 'id="su-uses_sql"', "Kept in SQL Account", "Off: Kept here, with no SQL import."))
check("Printed invoices and Printed company names are in the dialog of a company Kept in SQL Account, each with its link",
      'id="suPrint"' in o["dlgSql"] and 'id="suNames"' in o["dlgSql"] and has(o["dlgSqlPrint"], "Printed invoices", 'data-menu="accounting/einvoices"', "Accounting › e-Invoices")
      and has(o["dlgSqlNames"], "Printed company names", 'data-menu="accounting/sql"', "Accounting › SQL import"), o["dlgSqlPrint"][:400])
check("...and left out of the dialog of a company Kept here", 'id="suPrint"' not in o["dlgHere"] and 'id="suNames"' not in o["dlgHere"] and o["dlgHerePrint"] == ""
      and "Printed invoices" not in o["dlgHere"] and "Printed company names" not in o["dlgHere"] and "Where used" in o["dlgHere"])

# ---------- Stop using, Use again and Delete ----------
check("Stop using opens the reason box under the button with the section's note and the button's own words",
      o["whyShown"]["hidden"] is False and o["whyShown"]["go"] == "Stop using it" and "Stopped: hidden from the account lists" in o["whyShown"]["note"])
check("no reason: nothing is sent, and the box says to give one", o["whyEmpty"]["posts"] == 0 and "Say why you're making this change." in o["whyEmpty"]["msg"])
check("a refusal comes back under the reason box, with the server's sentence and that nothing was changed",
      has(o["whyRefused"]["msg"], "cash book account", "Nothing was changed.") and o["whyRefused"]["post"][1].endswith("/stop") and o["whyRefused"]["post"][2] == {"reason": "Closing the account."}, o["whyRefused"])
check("Cancel closes the box and empties the reason", o["whyHidden"] == {"hidden": True, "reason": ""})
check("Use again sends its reason", [(x[1].endswith("/use"), x[2]) for x in o["useAgain"]] == [(True, {"reason": "Needed again"})], o["useAgain"])
check("Delete shows its note, a red button, sends its reason, closes the dialog and says so",
      "It goes from the list. Show deleted keeps it for you" in o["deleteNote"] and "danger" in o["deleteDanger"]
      and [(x[0], x[2]) for x in o["deleted"]["calls"]] == [("DELETE", {"reason": "Opened by mistake"})] and o["deleted"]["toast"] == "Bank account deleted", o["deleted"])

# ---------- Show deleted and Put it back ----------
d = o["deletedAccounts"]
check("Show deleted lists what was deleted: name, when with its entry, by whom, why, and Put it back and History",
      has(d, "Deleted bank accounts", "Putting one back asks why", ">Spare<", "Entry ", "Opened by mistake", f'data-restore="{restored["row_id"]}"', "Put it back", 'data-hist-open="'))
check("one that can't be put back says why, without a Put it back button", has(o["deletedTypes"], "Can't be put back: ") and "data-restore=" not in o["deletedTypes"]
      and taken["problem"] in o["deletedTypes"], o["deletedTypes"][-600:])
pb = o["putBack"]
check("the Put it back dialog says what was deleted and that it comes back as it was, then asks why",
      has(pb["body"], "Bank account deleted", "Opened by mistake", "It comes back as it was when it was deleted, with the same number.", "Nothing in the months already set up changes.",
          'id="pb-why"', "Required") and "Put back" in pb["eyebrow"] and "Put it back" in pb["acts"], pb)
check("Put it back with no reason sends nothing and says to give one", o["putBackEmpty"]["posts"] == 0 and "Say why you're making this change." in o["putBackEmpty"]["err"])
check("with a reason it is sent", [(x[1], x[2]) for x in o["putBackDone"]] == [(f"/api/setup/restore/{restored['row_id']}", {"reason": "It is the new account after all"})], o["putBackDone"])
check("a record that can't be put back shows the reason in the dialog, nothing to press", has(o["putBackRefused"], "This can't be put back.") and "tst_form" in o["putBackRefused"], o["putBackRefused"][:500])

# ---------- Required documents: no "posted here" choice yet ----------
check("Required documents for a company Kept here says what it is not asked for, and has no posted-here choice",
      has(o["required"], "EXB is Kept here:", "are issued by SQL Account, so they are not asked for while EXB is Kept here.") and "posted here" not in o["required"].lower()
      and has(o["requiredSql"], "EXA is Kept in SQL Account: its payment vouchers are issued by SQL Account and read in on the SQL import page.") and "posted here" not in o["requiredSql"].lower())

# ---------- Open Setup from a print note ----------
check("Open Setup from a print note opens that company's own dialog (its address #/admin/setup/entities/<id>), not the list",
      o["invSetup"] == [{"view": "setup", "entity": EXA, "month": "2026-11", "sub": "entities", "id": str(EXA), "params": {}}], o["invSetup"])

# ---------- Move setup and First run ----------
mv = o["moveEmpty"]
check("the Everything sentence names the statutory accounts, what the printed invoices need, and the printed company names",
      has(mv, "statutory accounts", "what its printed invoices need (address, bank details, logo and signature)", "printed company names confirmed") and "Not for this install" not in mv)
check("Move setup says what this install holds when it refuses another import",
      has(o["moveBlocked"], "Not for this install", "These hold 3 companies, 3 bank accounts, 1 recurring payment and 2 months set up."))
table = lambda html: re.search(r'<table class="st-table st-counts">.*?</table>', html, re.S).group(0)
check("Move setup's counts are the file's, the lists with something in them, a stopped record counted",
      o["frRows"] == [["General settings", 8], ["Payment types", 15], ["Document types", 18], ["Companies", 4], ["Bank accounts", 5], ["Statutory account", 1], ["Checklist items", 50]]
      and "Printed company names" not in table(o["moveCounts"]) and "Salary advances" not in table(o["moveCounts"]) and ">4<" in table(o["moveCounts"]))
check("First run draws the same counts, the same table, as Move setup", table(o["frCounts"]) == table(o["moveCounts"]), (table(o["frCounts"]), table(o["moveCounts"])))
check("a setup file the server won't take is said as it is, with the file's name and that nothing was added",
      has(o["moveRefused"], "setup-everything.json can't be imported.", "made by a newer version of the app.", "Nothing was added."))
fr = o["frCounts"]
check("First run: the welcome page for an install with no company, its two ways in, and what comes next",
      o["frDue"] is True and has(fr, "Welcome to HR Payments", "There is no company here yet.", "Import a setup file", "Add your first company", "What comes next", "After a company is added")
      and fr.count('class="fr-step"') == 5)
check("First run asks where the books are kept, as two choices, Kept in SQL Account and Kept here, and a form's own checks",
      has(o["frAdd"], "Where are the books kept?", 'id="fr-kind-sql"', "Kept in SQL Account", "Payments then need their PV, JV or OR from SQL.", 'id="fr-kind-here"', "Kept here",
          "The books are kept in this app: sales, purchases, journals and period close.", "Registration number", 'Add company</button>'))
check("a company can't be added until it says where its books are kept: nothing is sent, and the choice is asked for",
      o["frNoKind"]["posts"] == 0 and o["frNoKind"]["tried"] is True and "Choose where the books are kept." in o["frNoKind"]["html"])
check("added, it sends the code in capitals, the name and Kept here as 0, and says what was done with the steps open",
      [(x[1], x[2]) for x in o["frPost"]] == [("/api/setup/entities", {"fields": {"code": "ABC", "name": "Example Gamma Ltd", "uses_sql": 0}})]
      and o["frDone"] == {"title": "Company added.", "body": "ABC is ready: Kept here. The next steps are open below."}
      and has(o["frDoneHtml"], "Company added.", "Open Overview", 'href="#/admin/setup/accounts"', "Admin › Backup") and "After a company is added" not in o["frDoneHtml"])
check("First run is for an install with no company: with one it is not due", o["frDueAfter"] is False)

check("a file that isn't JSON is told so, before the server is asked; one the server won't take is marked refused, with its sentence; one it takes gives the preview",
      o["readBad"]["refused"] is False and "can't be read as a setup file" in o["readBad"]["message"]
      and o["readRefused"] == {"message": "This setup file was made by a newer version of the app.", "refused": True}
      and o["readPosts"][0] == ["/api/setup/import", True, ["setup", "preview"]] and len(o["readPosts"]) == 1 and o["readOk"] == {"counts": 9, "setup": "hrp-setup"},
      (o["readBad"], o["readRefused"], o["readPosts"], o["readOk"]))

# ---------- review fixes ----------
pp = o["partyPost"]
check("Add customer or supplier: the page posts the words box left empty as an empty list (the server takes that as no words)",
      len(pp) == 1 and pp[0]["fields"].get("match_words") == [] and pp[0]["fields"].get("name") == "Test Party" and pp[0]["entity_id"] == EXA, pp)
hn = o["hereNames"]
check("a company Kept here that still has printed company names lists them with Remove, says what they still do (no other company can take them), and draws nothing else of the print settings",
      has(hn["drawer"], 'id="suNames"') and 'id="suPrint"' not in hn["drawer"] and "Printed invoices" not in hn["drawer"]
      and has(hn["names"], "Printed company names", "EXAMPLE SWITCHED LTD (2026)", 'data-sql-name-remove="7"',
              "These names were confirmed while this company was Kept in SQL Account. While they stay, no other company can take them; remove any you don't want.")
      and "not used while" not in hn["names"] and "Take it for" not in hn["names"], hn["names"][:600])
check("...and removing the last of them ends the section", hn["removed"] == [f"/api/setup/entities/{EXB}/sql-names/7"] and hn["after"] == "", (hn["removed"], hn["after"]))
SN = "Stopped: hidden from the account lists"
check("the stopped note is said once in a stopped record's dialog, and once in the dialog drawn again right after Stop using",
      o["dlgStopped"].count(SN) == 1 and o["stopNote"]["open"].count(SN) == 0 and o["stopNote"]["afterStop"].count(SN) == 1,
      (o["dlgStopped"].count(SN), o["stopNote"]["open"].count(SN), o["stopNote"]["afterStop"].count(SN)))
ft = o["frTemplate"]
check("First run after a file of rules alone (no company): the page stays, says rules came in and what is next, has no Open Overview, and the steps stay grey",
      ft["done"] is None and ft["note"] == {"title": "Rules imported.", "body": "Now add your first company."} and ft["due"] is True and ft["posts"] == 1
      and has(ft["html"], "Rules imported.", "Now add your first company.", 'class="banner info') and "Open Overview" not in ft["html"] and 'href="#/"' not in ft["html"]
      and n(ft["html"], "After a company is added") == 5 and "setup was imported" not in ft["html"].lower() and "Setup imported" not in ft["html"], ft)
fc = o["frCompanies"]
check("after a file that adds companies the note says how many came in, and mentions stopped ones only when there are some",
      fc["some"]["done"]["body"] == "3 companies came in, 1 of them stopped. Each change is noted in the audit trail." and fc["some"]["note"] is None
      and fc["none"]["body"] == "2 companies came in. Each change is noted in the audit trail."
      and fc["one"]["body"] == "1 company came in, and it is stopped. Each change is noted in the audit trail." and fc["some"]["done"]["title"] == "Setup imported.", fc)
check("the steps of First run are links with an address of their own, never #/: with none they are grey, not a dead link",
      has(fc["some"]["html"], "Open Overview", 'href="#/EXA/hr/staff"', 'href="#/admin/setup/accounts"', 'href="#/admin/backup"') and 'href="#/"' not in fc["some"]["html"]
      and 'href="#/"' not in fc["noCompany"] and n(fc["noCompany"], "data-fr-step") == 2, (n(fc["noCompany"], "data-fr-step"), re.findall(r'href="[^"]*"', fc["noCompany"])))
ff = o["frFailImport"]
check("a network failure during Import leaves First run usable: nothing is busy, the file and what was typed stay, and Import can be pressed again",
      ff["threw"] == "TypeError" and ff["busy"] == "" and ff["why"] == "A reason I typed" and ff["kept"] is True and "aria-busy" not in ff["html"] and "Importing</button>" not in ff["html"]
      and 'data-fr-import="1" disabled' not in ff["html"] and 'data-fr-import="1"' in ff["html"], ff)
fa = o["frFailAdd"]
check("...and the same during Add company: the form stays open with its text, and Add company can be pressed again",
      fa["threw"] == "TypeError" and fa["busy"] == "" and fa["open"] is True and has(fa["html"], 'value="ABC"', 'value="Example Co"', "Add company</button>")
      and "aria-busy" not in fa["html"] and "Adding" not in fa["html"], fa)
check("...and when the records can't be read again once the company was added", fa["threwMeta"] == "TypeError" and fa["busyMeta"] == "", (fa["threwMeta"], fa["busyMeta"]))
css = (Path(__file__).resolve().parents[1] / "static" / "app.css").read_text(encoding="utf-8")
check("the Setup menu is sticky but never taller than the window: it scrolls in its own frame, and under 860 pixels it is plain content with no height limit",
      re.search(r"\.setup-nav \{[^}]*position: sticky;[^}]*max-height: calc\(100vh - 92px\);[^}]*overflow-y: auto;", css) is not None
      and re.search(r"\.setup-nav \{ position: static;[^}]*max-height: none;[^}]*overflow: visible;", css) is not None)
mk = o["moreKept"]
check("the rows already shown stay shown when the list is drawn again (a save, a stop), and start again with another section or another company",
      mk["first"] == 25 and mk["more"] == 30 and mk["redrawn"] == 30 and mk["otherSection"] == 25 and mk["otherCompany"] == 25, mk)
check("an arrow key on a tab strip picks the next tab and the focus is on it once the page is drawn again", o["tabKey"] == {"active": "tab-b", "kind": "doc_types"}, o["tabKey"])
check("Enter twice at once in the reason box makes the change once; Enter in the Put it back reason presses Put it back; two of those at once put it back once",
      o["double"]["deletes"] == 1 and o["double"]["enterClicks"] == 1 and o["double"]["restores"] == 1, o["double"])
dl = o["deadLink"]
check("the old address of Recurring payments with no company opens the first section, not a page that says it isn't ready",
      dl["kind"] == "entities" and "isn't ready" not in dl["page"] and "Companies" in dl["page"] and "Add company" in dl["page"], (dl["kind"], dl["page"][:200]))
bl = o["bankLink"]
check("Open Setup > Bank accounts in a company's dialog opens the accounts of that company, not of the company in the top bar",
      has(bl["html"], f'data-setup-kind="accounts" data-setup-entity="{EXA}"') and bl["before"] == EXB and bl["entity"] == EXA and bl["kind"] == "accounts", bl)
rq = o["requiredHere"]
check("Required documents for a company Kept here greys the documents SQL Account issues and says so; the others stay; every company's table shows none greyed",
      has(rq["here"], "Payment Voucher, Journal Voucher and Official Receipt are issued by SQL Account, so they are not asked for while EXB is Kept here. Where a type lists them below they are greyed.")
      and n(rq["here"], r'class="chip off"') >= 3 and 'class="chip">' in rq["here"] and "where the rules above say so" not in rq["here"]
      and 'class="chip off"' not in rq["all"], (n(rq["here"], r'class="chip off"'), re.findall(r"EXB is Kept here:[^<]*", rq["here"])))
ms = o["moveStates"]
check("Move setup's Export buttons are downloads that say so: the file's name, that it is noted in the audit trail, and recurring payments when ticked",
      has(ms["empty"], 'data-move-export="template"', 'data-move-export="full"')
      and ms["toastTemplate"] == f"Setup template {ms['dayKey']}.json is downloading. It is noted in the audit trail."
      and ms["toastFull"] == f"Setup everything {ms['dayKey']}.json is downloading, with recurring payments. It is noted in the audit trail."
      and ms["toastFullPlain"] == f"Setup everything {ms['dayKey']}.json is downloading. It is noted in the audit trail.", ms)
check("right after an import Move setup's card says why another can't be made and links to the companies it added; the link goes once the section is left",
      ms["flag"] is True and ms["imported"] == ["A reason"] and has(ms["blocked"], "Not for this install", "See the companies it added", 'data-setup-kind="entities"')
      and "See the companies it added" not in ms["blockedLater"] and "Not for this install" in ms["blockedLater"], (ms["flag"], ms["imported"]))
dn = o["deletedNames"]
check("Show deleted names a company as CODE · Name, in the list and on its Put it back button, under the heading Deleted companies",
      has(dn["companies"], "Deleted companies", "EXD · Example Delta Ltd", 'data-restore-title="EXD · Example Delta Ltd"'), dn["companies"][:500])
check("...a chart account by its name with its code under it, under Deleted accounts; and Filing words is Filing words, as the menu says",
      has(dn["chart"], "Deleted accounts", "Spare account", ">999-001<") and "Deleted filing words" in dn["filing"] and "SQL filing words" not in dn["filing"], (dn["chart"][:300], dn["filing"][:200]))

# ---------- round 2 ----------
ma = o["moreAway"]
check("the rows Show 25 more showed are not kept past another section: after Required documents or Move setup (no lists), or after leaving Setup, a list starts at 25 again",
      ma["first"] == 25 and ma["more"] == 30 and ma["afterRequired"] == 25 and ma["afterMove"] == 25 and ma["afterLeaving"] == 25, ma)
check("...a save that draws the page again keeps them; a changed search, clearing it by hand and Clear the search each start at 25 again",
      ma["saveRedraw"] == 30 and ma["searched"] == 25 and ma["moreAgain"] == 30 and ma["cleared"] == 25 and ma["clearBtn"] == 25, ma)
check("...and a fresh page (the menu's Setup item while on Setup, a record's address on the same section) starts at 25 rows as it clears the search", ma["freshPage"] == 25, ma)
nk = o["navKeep"]
check("the Setup menu gets the scroll it had at once, as it is drawn (not when the section has been read), and is scrolled to its item once the section is drawn, only itself (never scrollIntoView, never the window)",
      nk["deep"] == {"kind": "move", "top": 340, "sets": [[0, False], [340, True]], "intoView": 0, "focused": False}
      and nk["save"] == {"kind": "move", "top": 400, "sets": [[400, False]], "intoView": 0, "focused": False}
      and nk["click"] == {"kind": "accounts", "top": 80, "sets": [[400, False], [80, True]], "intoView": 0, "focused": True} and nk["windowScrolls"] == [[0, 0]], nk)
check("a click (or Enter) on a menu item puts the focus on the new item on show; a page drawn again that no menu item asked for leaves the focus alone",
      nk["click"]["kind"] == "accounts" and nk["click"]["focused"] is True and nk["save"]["focused"] is False, nk)
pt = o["putBackTitle"]
check("Put it back opened from the audit trail or a History heads the dialog CODE · Name, as Show deleted does, and its History button too; the trail's own button still names the record as it does",
      pt["title"] == "EXD · Example Delta Ltd" and has(pt["body"], 'data-hist-title="EXD · Example Delta Ltd"') and 'data-restore-title="Example Delta Ltd"' in pt["trailBtn"], (pt["title"], pt["body"][-260:], pt["trailBtn"]))
rs = o["restoreStopped"]
check("Put it back with the app stopped says so: the click handler waits for it, so the message is not lost as an unhandled rejection", rs["threw"] == "ok" and "Failed to fetch" in rs["toast"], rs)
di = o["deadLinkId"]
check("the old address of Recurring payments with a record number and no company opens the first section and no record (no 404 message); a record of a real section still opens",
      di["opened"] == [] and di["kind"] == "entities" and di["toast"] == "" and di["control"] == [["entities", EXA]], di)
mf = o["moveFlag"]
LINK = "See the companies it added"
check("the link to the companies an import added is for the page drawn right after it, once: not on the next draw, nor after the Overview and back, nor after a file of rules alone",
      mf["flag"] is True and has(mf["right"], LINK, "Not for this install") and LINK not in mf["next"] and mf["flagAfter"] is False
      and mf["flagOut"] is False and LINK not in mf["afterOverview"] and mf["rulesFlag"] is False and LINK not in mf["rulesBlocked"] and "Not for this install" in mf["rulesBlocked"], mf)
sv = o["frSaved"]
SAVED = "It was saved, but this page could not reload. Try again."
check("First run when Import was saved but the records can't be read again: it says so with Try again, and no form is left that would write it twice",
      sv["threw"] == "TypeError" and sv["busy"] == "" and {k: v for k, v in sv["saved"].items() if k != "reads"} == {"imported": True, "code": "", "kept": ""} and has(sv["html"], SAVED, 'data-fr-reload="1"')
      and "fr-cards" not in sv["html"] and 'data-fr-import' not in sv["html"] and 'id="fr-add-open"' not in sv["html"] and "aria-busy" not in sv["html"], sv["html"][:700])
check("...Try again only reads: it fails again with a note still there, and once it works the page goes on with nothing sent",
      sv["stillSaved"] is not None and sv["stillBusy"] == "" and SAVED in sv["stillHtml"]
      and sv["after"]["saved"] is None and sv["after"]["posts"] == 0 and sv["after"]["done"]["title"] == "Setup imported." and SAVED not in sv["after"]["html"] and "Open Overview" in sv["after"]["html"], sv)
check("...and the same after Add company: it was written once, Try again reads and gives Company added, and a retype of the code is never asked for",
      sv["addThrew"] == "TypeError" and has(sv["addHtml"], SAVED) and sv["addPosts"] == 1 and sv["addAfter"]["posts"] == 0 and sv["addAfter"]["saved"] is None
      and sv["addAfter"]["done"] == {"title": "Company added.", "body": "ABC is ready: Kept in SQL Account. The next steps are open below."}, sv["addAfter"])
es = o["escapes"]
check("markup in a document type's label and in a company's code and name is shown as written in the Required documents note (the sentence, the chips and the table)",
      has(es["required"], "Payment Voucher, Journal Voucher, Official Receipt and Delivery &lt;i&gt;Order&lt;/i&gt; are issued by SQL Account, so they are not asked for while E&amp;&lt;B is Kept here.", "E&amp;&lt;B")
      and not any(x in es["required"] for x in ("<i>Order</i>", "<b>Jerry", "E&<B")), es["required"][:900])
check("...and in the company's dialog: its name, Where used and the notes",
      has(es["dlg"], "Tom &amp; &lt;b&gt;Jerry&lt;/b&gt; Ltd", "bank &lt;u&gt;account&lt;/u&gt;s", "A note with &lt;i&gt;markup&lt;/i&gt; &amp; more")
      and not any(x in es["dlg"] for x in ("<u>", "<b>Jerry", "<i>markup")), es["dlg"][:500])
check("...and in the printed company names of a company Kept here, and in the heading of its dialog",
      has(es["names"], "A &amp; &lt;b&gt;B&lt;/b&gt; (2026)", "t &lt;i&gt;ester&lt;/i&gt;") and "<b>B</b>" not in es["names"] and "<i>ester" not in es["names"]
      and "Tom &amp; &lt;b&gt;Jerry&lt;/b&gt; Ltd" in es["dlgHere"] and "<b>Jerry" not in es["dlgHere"], es["names"][:400])
check("...and in Show deleted (the name, the code under it, who, why, why it can't be put back, and the Put it back button's title)",
      has(es["deleted"], "E&amp;&lt;B · Tom &amp; &lt;b&gt;Jerry&lt;/b&gt; Ltd", "C&amp;&lt;D", "a&amp;&lt;b&gt;", "why &lt;i&gt;x&lt;/i&gt;", "key &lt;u&gt;taken&lt;/u&gt;",
          'data-restore-title="E&amp;&lt;B · Tom &amp; &lt;b&gt;Jerry&lt;/b&gt; Ltd"') and not any(x in es["deleted"] for x in ("<i>x</i>", "<u>taken", "<b>Jerry", "E&<B")), es["deleted"][:500])
check("...and in the Put it back dialog (its heading is text, its body and the title it was opened with are escaped)",
      es["putBack"]["head"] == "E&<B · Tom & <b>Jerry</b> Ltd" and has(es["putBack"]["body"], "why &lt;i&gt;x&lt;/i&gt;", "a&amp;&lt;b&gt;", "note &lt;b&gt;b&lt;/b&gt;")
      and not any(x in es["putBack"]["body"] for x in ("<i>x</i>", "<b>b</b>")) and "Old &lt;i&gt;name&lt;/i&gt;" in es["putBack"]["drawer"] and "<i>name</i>" not in es["putBack"]["drawer"], es["putBack"]["body"][:400])
check("...and in First run's note after a company is added",
      "E&amp;&lt;B is ready: Kept here." in es["banner"] and "E&<B" not in es["banner"], es["banner"][:300])
check("Required documents for a company Kept in SQL Account greys nothing and has no Kept here note: it is not asked for fewer documents",
      'class="chip off"' not in o["requiredSql"] and "is Kept here" not in o["requiredSql"] and "not asked for" not in o["requiredSql"] and 'class="chip">' in o["requiredSql"], o["requiredSql"][:300])

# ---------- round 3 ----------
s2 = o["frSavedTwice"]
check("a second Add company whose records can't be read again says so alone: the earlier Company added note and Open Overview are gone while it stands, the page stays First run, and the alert takes the focus",
      s2["first"]["title"] == "Company added." and has(s2["html"], SAVED, 'id="fr-reload"', 'id="fr-saved"') and "Company added." not in s2["html"] and "Open Overview" not in s2["html"]
      and s2["done"] is None and s2["due"] is True and s2["focus1"] == "fr-saved" and s2["alerted"] is True, s2)
check("...its Try again keeps the focus when the records can't be read again, and when they can the note says what was added and the alert goes",
      s2["focus2"] == "fr-reload" and SAVED in s2["html2"] and s2["after"]["done"] == {"title": "Company added.", "body": "DEF is ready: Kept here. The next steps are open below."}
      and s2["after"]["saved"] is None and s2["after"]["alerted"] is False and SAVED not in s2["after"]["html"] and "Open Overview" in s2["after"]["html"], s2)
rl = o["restoreLoadFail"]
check("Put it back with the app stopped says it couldn't load, with a Try again that opens it again, instead of Loading for ever",
      rl["threw"] == "ok" and "Couldn't load this. Try again." in rl["body"] and f'data-restore="{restored["row_id"]}"' in rl["body"], rl)
ec = o["escapesCore"]
check("a record's History key and a list's name are escaped where they are written into the page",
      'data-hist="a&quot;b:&lt;x&gt;"' in ec["hist"] and "<x>" not in ec["hist"]
      and has(ec["bar"], 'data-search="setup-a&quot;b"', 'placeholder="Search cust &lt;i&gt;x&lt;/i&gt;"', 'aria-label="Search cust &lt;i&gt;x&lt;/i&gt;"', 'data-count="setup-a&quot;b"') and "<i>x</i>" not in ec["bar"], ec)

# ---------- round 5 ----------
def flag_in_new_process(value):
    env = {k: v for k, v in os.environ.items() if k != "HRP_KEEP_GOING"}
    if value is not None:
        env["HRP_KEEP_GOING"] = value
    return subprocess.run([sys.executable, "-c", "from synthetic_tests.flags import KEEP_GOING; print(KEEP_GOING)"], cwd=str(Path(__file__).resolve().parents[1]),
                          env=env, capture_output=True, text=True).stdout.strip()


from synthetic_tests import flags  # noqa: E402
check("HRP_KEEP_GOING turns keep-going on only for a value other than empty or 0, read in a new process from the module both tests import (the variable they use)",
      flags.KEEP_GOING is KEEP_GOING and [flag_in_new_process(v) for v in ("1", "yes", "0", "", None)] == ["True", "True", "False", "False", "False"])
hk = o["holdKeeps"]
check("a section drawn again (a save, a stop, a delete, a put back) holds the page's height while it is read: the window stays at 800 throughout, nothing old is shown meanwhile, the hold ends once it is written, and no scroll is made",
      hk["same"]["y"] == 800 and hk["same"]["low"] == 800 and hk["same"]["scrolls"] == 0 and hk["same"]["during"] == [{"y": 800, "hold": "3200px", "section": 0}]
      and hk["same"]["hold"] == "" and hk["same"]["written"] is True, hk["same"])
check("...a scroll by the user during the read is respected (the page does not jump back), and with Show deleted on the hold lasts until its table is written",
      hk["userScroll"] == {"y": 1000, "scrolls": 0} and hk["atDeleted"] == {"hold": "3200px", "listWritten": True} and hk["deleted"] == {"y": 800, "scrolls": 0, "hold": "", "table": True}, hk)
check("...a read that fails doesn't leave the hold, and another section or company starts at the top (the one scroll), with no hold",
      hk["failed"] == "TypeError" and hk["failedHold"] == "" and hk["otherSection"] == {"y": 0, "scrolls": [[0, 0]], "hold": ""} and hk["otherCompany"] == {"y": 0, "scrolls": [[0, 0]], "hold": ""}, hk)
sd = o["staleDraw"]
check("a draw that another section overtook writes nothing (no markup, no list to redraw, no count): Chart of accounts read slowly and Payment types asked for next, the page ends on Payment types, and Chart of accounts drawn later is Chart of accounts",
      sd["quick"] == {"page": True, "a": False} and sd["overtaken"] == {"writes": 0, "page": True, "a": False, "redraw": "undefined", "count": None, "hold": ""}
      and sd["later"] == {"a": True, "pt": False}, sd)
check("...and an overtaken draw doesn't end the hold of the one that overtook it: the same section drawn twice holds until the second is written",
      sd["overlap"] == {"holdWhileSecond": "3200px", "firstWrites": 0, "page": 0} and sd["overlapEnd"] == {"hold": "", "page": True}, sd)
se = o["frSavedElsewhere"]
check("First run's saved-but-not-read note is over once the records have been read again, whatever they list: a company added but not read, then deleted in Setup, leaves the Overview drawn, not the alert",
      se["first"] == "Company added." and se["threw"] == "TypeError" and se["due"] is True and se["dueAfterFailed"] is True and se["savedAfterFailed"] is True and se["reads1"] == se["reads0"]
      and se["read"] == "ok" and se["dueAfterRead"] is False and se["saved"] is None and se["alerted"] is False, se)
check("...a read that fails doesn't end it, the first company of all is ended by any successful read, and the count of reads is what counts",
      se["failedRead"] == "TypeError" and se["threw2"] == "TypeError" and se["due2"] is True and se["read2"] == "ok" and se["due2After"] is False and se["saved2"] is None, se)
# ---------- round 6 ----------
sk = o["skeleton"]
good = lambda kind, code: {"section": True, "company": True, "grid": True, "skeleton": False, "menu": True, "redraw": "function", "hold": "", "loading": False}
check("a draw still reading when render()'s loading skeleton is due (a read over 0.3 s: arriving from another page, a company switch, the first read of the types) writes the section into its own frame, with its menu and its list to redraw, and no skeleton is left over it",
      sk["arrival"] == good("parties", "") and sk["switch"] == good("accounts", "") and sk["types"] == good("parties", ""), sk)
lv = o["leaving"]
check("leaving Setup while a draw reads leaves the new page no hold of the page's height at once, and a read that hangs (or comes later) changes nothing and draws nothing over the new page",
      lv["held"] != "" and lv["at"] == "" and lv["hung"] == "" and lv["end"] == {"hold": "", "page": "<div>Overview page</div>"}, lv)
check("...also when the new page is drawn by render() (a page that isn't Setup)", lv["byRender"] == {"hold": "", "page": "<div>zzz page</div>"} and lv["byRenderEnd"] == {"hold": "", "page": "<div>zzz page</div>"}, lv)
gf = o["gridFails"]
check("a failure while the grid is drawn, after the page's height was held, leaves no hold", gf["threw"] == "the menu failed" and gf["hold"] == "", gf)
rs = o["renderStale"]
check("render() says the page on show is the latest one's: a draw that was overtaken and finishes late doesn't set the last page drawn (company EXA after EXB)",
      rs["mid"] == f"setup:{EXB}" and rs["last"] == f"setup:{EXB}", rs)
check("...and an error that comes after the page was left is not painted over the page now shown, nor does it say which page was last", rs["error"] == {"painted": False, "grid": True, "last": f"setup:{EXA}"}, rs)
bm = o["badMeta"]
check("a reply that isn't the records (a 200 that isn't JSON, or that holds no companies) is a failed read: it is not counted, state.meta is not replaced, and First run, after a write, shows the alert instead of failing in firstEntityId",
      "this page can't read" in bm["message"] and "couldn't be read" in bm["empty"] and bm["emptyReads"] == 0 and bm["reads"] == 0 and bm["sameMeta"] is True and bm["add"].startswith("Error: HR Payments gave an answer this page can't read")
      and bm["saved"] is True and SAVED in bm["html"], bm)
for kind, st in o["staleSections"].items():
    check(f"{kind}: a draw that another section overtook writes no state, no markup and no list to redraw",
          st["overtaken"] == {"wrote": False, "writes": 0, "page": True, "hold": ""}, st["overtaken"])
    check(f"{kind}: drawn twice, the first read finishing first writes nothing and leaves the hold of the second alone, which ends it when it is written; an overtaken read that fails raises nothing and says nothing",
          st["twice"] == {"holdKept": True, "wrote": False, "writes": 0} and st["twiceEnd"] == {"hold": "", "wrote": True} and st["threw"] == "ok" and st["quiet"] is True, st)
check("the types read at the start: a draw that was overtaken leaves what the newer draw drew (it doesn't keep its own reply or draw its page)",
      o["staleTypes"]["after"] == {"sameTypes": True, "mainSets": 0, "page": True}, o["staleTypes"])
dh = o["deletedHold"]
check("the checklist and the reminders hold the page's height until their Show deleted table is written, as the lists do",
      all(dh[k]["at"] == {"hold": "3200px", "section": True} and dh[k]["hold"] == "" and dh[k]["table"] is True for k in ("checklist", "reminders")), dh)
un = o["untick"]
check("Show deleted unticked while its table is read draws nothing: the box stays empty, also when that read fails", un["box"] == "" and un["afterFail"] == "", un)

ga = re.search(r'<input id="su-gl_code"[^>]*>', o["dlgAccount"])
check("a bank account's GL code input has what the code fields have: monospace, no spell check, no autocomplete, typed in capitals",
      ga is not None and all(x in ga.group(0) for x in ('class="mono"', 'spellcheck="false"', 'autocomplete="off"', "data-upper")), ga.group(0) if ga else None)

rr = o["restoreRetry"]
check("Put it back's Try again with the app stopped makes one request and shows one dialog each time it is pressed, and works once the app is back",
      all(x == {"requests": 1, "dialogs": 1, "notes": 1} for x in rr["rounds"]) and len(rr["rounds"]) == 3
      and rr["back"]["requests"] == 1 and rr["back"]["dialogs"] == 1 and "It comes back as it was" in rr["back"]["body"] and "Couldn't load" not in rr["back"]["body"], rr)

# ---------- round 7 and 8 ----------
sd = o["skeletonDeleted"]
okcase = {"skeleton": False, "grid": True, "hold": "", "loading": False, "section": True, "table": True, "slow": True}
check("L1: a section already written when render()'s loading skeleton is due (the Show deleted read, 900 ms, comes last) is left as it is, for the list, the checklist and the reminders, with Show deleted on and off: the section, its table, no skeleton, no hold",
      all(sd[k] == okcase for k in ("accounts-on", "checklist-on", "reminders-on", "accounts-off", "checklist-off", "reminders-off")), sd)
sw = o["oneDraw"]
check("L1: a section that takes 900 ms is read once and written into the frame it wrote: no skeleton covers it and nothing draws it a second time",
      sw["slow"] == {"reads": 1, "written": True, "skeleton": False, "grid": True}, sw["slow"])
check("L1: a failure of that read (it answers 500 after 900 ms) reaches render(): the page says so, with its Try again, after one read, and Try again draws the section",
      sw["fails500"]["reads"] == 1 and "The server could not read the records." in sw["fails500"]["html"] and 'data-retry="1"' in sw["fails500"]["html"] and "Couldn't load this page" in sw["fails500"]["html"]
      and sw["after500"] == {"grid": True, "error": False}, sw["fails500"]["html"][-300:])
check("...and so does one that can't reach the app: the page says it isn't running, with its Try again, after one read, and Try again draws the section",
      sw["rejects"]["reads"] == 1 and "isn't running" in sw["rejects"]["html"] and 'data-retry="1"' in sw["rejects"]["html"] and sw["afterRejects"] == {"grid": True, "error": False}, sw["rejects"]["html"][-300:])
AFTER_SAVE = ["delete", "stop using", "use again", "save", "save (a reply that isn't the records)", "add", "general settings", "move setup import", "paste a list", "put it back",
              "checklist: add an item", "checklist: stop using", "checklist: delete an item", "checklist: copy another company's", "reminders: save", "reminders: delete"]
check("L2: every flow that changes something is tried with the records overview failing: record save, add, stop using, use again, delete, put it back, general settings, Move setup import, Paste a list, a reply that isn't the records, and the checklist and reminders (which swallowed a failed read)",
      sorted(o["afterSave"].keys()) == sorted(AFTER_SAVE), list(o["afterSave"].keys()))
for name, f in o["afterSave"].items():
    check(f"L2: {name}: the change is made once and, when the records can't be read again after it, it says it was saved, once (not that nothing was changed), with a Try again; Try again reads again, sends nothing, opens no record and closes no dialog",
          f["hit"] is True and f["once"] == 1 and f["said"] is True and f["tryAgain"] is True and f["toasts"] == 1 and f["nothing"] is False and f["drawer"] is True
          and f["again"]["writes"] == 0 and f["again"]["read"] == 1 and f["again"]["rendered"] is True and f["again"]["spy"] == [] and f["again"]["toasts"] == 1, f)
AFTER_PAGE = ["checklist: add an item", "checklist: stop using", "checklist: delete an item", "checklist: copy another company's", "reminders: save", "reminders: delete", "required documents: save",
              "bank account: delete", "tidy up", "general settings", "move setup import", "put it back", "plainStopped", "plainError"]
check("L2: every flow that draws the page after a change is tried with the page's own read failing: checklist (add, stop using, delete, copy), reminders (save, delete), required documents, a bank account's delete, Tidy up, general settings, Move setup import and Put it back",
      sorted(o["afterSavePage"].keys()) == sorted(AFTER_PAGE), list(o["afterSavePage"].keys()))
for name, f in o["afterSavePage"].items():
    if name.startswith("plain"):
        continue
    check(f"L2: {name}: when the page's own read fails after the change was saved, the page says it was saved, once (no toast as well), with its Try again (the change made once, never 'nothing was changed' or 'isn't running'); Try again says it again if it fails again, and draws the page and sends nothing when it works",
          f["hit"] is True and f["once"] == 1 and f["page"] is True and f["nothing"] is False and f["retry"] is True and f["toasts"] == 0 and f["again1"] is True
          and f["again"]["writes"] == 0 and f["again"]["page"] is True, f)
check("L2: a page that fails with nothing saved says what it said before: the app has stopped (or the reason, and that nothing was changed), never that it was saved",
      o["afterSavePage"]["plainStopped"] == {"stopped": True, "saved": False} and o["afterSavePage"]["plainError"] == {"reason": True, "nothing": True, "saved": False}, o["afterSavePage"]["plainStopped"])
dl = o["dialogs"]
TYPED = "typed after the save"
check("L2: a dialog with something typed in it that the change didn't save is left open when the reading back fails, with what was typed and the saved note, and Try again leaves it alone (no record opened, no dialog closed)",
      dl["dirty"] == {"open": True, "typed": "typed before the stop", "said": True} and dl["dirtyRetry"] == {"spy": [], "same": True, "typed": "typed before the stop"}, dl)
check("L2: another record's dialog that the user opened while the re-read was pending is not replaced or closed, by the failure or by Try again, whether they typed in it or not, and the change was made once",
      dl["other"] == {"open": True, "kept": True, "said": True, "once": 1} and dl["otherRetry"] == {"spy": [], "same": True, "kept": True, "writes": 0}
      and dl["otherClean"] == {"open": True, "kept": True, "said": True, "once": 1} and dl["otherCleanRetry"] == {"spy": [], "same": True, "kept": True, "writes": 0}, dl)
check("L2: something typed in a saved record's dialog after the save, while the re-read is pending, stays: the dialog is left open as typed when the reading back fails, and Try again leaves it alone",
      dl["typedAfter"] == {"open": True, "typed": TYPED, "said": True, "once": 1} and dl["typedAfterRetry"] == {"spy": [], "same": True, "typed": TYPED, "writes": 0}, dl)
check("L2: when the re-read works after the user opened another record, the saved record's dialog is not opened again over it: no record opened or dialog closed, the other dialog as it was",
      dl["guard"] == {"spy": [], "same": True, "kept": True, "once": 1, "rendered": True, "toasts": 0}, dl["guard"])
check("L2: a Try again that fails again says it again (a second 'saved' toast), and the next one that works draws the page",
      dl["retry1"] == 1 and dl["retry2"] == 2 and dl["retry3"] == {"saved": 2, "rendered": True}, [dl["retry1"], dl["retry2"], dl["retry3"]])
check("L2: an Add whose record was saved but whose dialog can't be opened again (its read fails) closes the dialog, and a second click on Add makes no second record",
      dl["addClean"] == {"drawer": True, "said": True, "posts": 1} and dl["addCleanAgain"] == {"posts": 1}, [dl["addClean"], dl["addCleanAgain"]])
check("...and one with something typed in it after the save stays open, as typed, but refuses to add the record again: a second click on Add makes no second record and says so",
      dl["addTyped"] == {"open": True, "typed": "typed after the add", "said": True, "posts": 1} and dl["addTypedAgain"] == {"posts": 1, "refused": True, "open": True}, [dl["addTyped"], dl["addTypedAgain"]])
check("L2: a Save whose record's dialog can't be opened again closes the dialog when nothing was typed in it since, and leaves it open as typed when something was; the change was made once",
      dl["saveClean"]["drawer"] is True and dl["saveClean"]["said"] is True and dl["saveClean"]["patches"] == 1 and dl["saveClean"]["typed"].startswith("Renamed account ")
      and dl["saveTyped"] == {"drawer": True, "said": True, "patches": 1, "typed": TYPED}, [dl["saveClean"], dl["saveTyped"]])
nl = o["noLeak"]
check("L2: 'it was saved' belongs to the page that says it: after a saved change whose read failed (a toast), a page that fails for its own reasons says what it always said",
      nl["afterToast"] == {"saved": False, "says": True}, nl)
check("...and so does the next place after a page that said it was saved (applyPlace), and a section switch (redraw)",
      nl["pageSaved"] is True and nl["afterPlace"] == {"saved": False, "says": True} and nl["pageSaved2"] is True and nl["afterRedraw"] == {"saved": False, "says": True}, nl)
nr = o["noRedo"]
check("round 8: render() leaves a page that was overtaken as it always did and draws nothing again: slow A, quick B, A's late paint, then C stays on show, and B was drawn once (a redo of B would land over C)",
      nr["timeline"] == {"page": "<div>C page</div>", "view": "pageC", "a": 1, "b": 1, "c": 1}, nr["timeline"])
check("...and a normal render draws once", nr["once"] == 1, nr)

# ---------- slice 9c: the Setup known limits (j), (k) and (l) ----------
lm = o["limits"]
if lm.get("error"):
    print("     limits:", lm["error"])
HALF = "Half a reas"
check("(j) a reason half-typed under Stop using keeps the dialog, with the reason, when a Save's record can't be opened again, and when the reading back fails",
      lm["jReopen"] == {"open": True, "reason": HALF, "box": False, "said": True, "writes": 1} and lm["jReread"] == {"open": True, "reason": HALF, "box": False, "said": True, "writes": 1}, (lm["jReopen"], lm["jReread"]))
check("(j) the reason a change was made with leaves the box once it is kept, and one typed in a box opened while the page is read again keeps the dialog",
      lm["jGone"] == {"hiddenWhileReading": True, "value": ""} and lm["jNew"] == {"open": True, "reason": "Typed while it was read", "box": False}, (lm["jGone"], lm["jNew"]))
for kind in ("checklist", "reminders"):
    k = lm["k_" + kind]
    check(f"(k) the {kind} Add that was kept stays open with what was typed since, and never adds again from it, though Preview still works",
          k["open"] is True and k["typed"] == "typed after the add" and k["posts"] == 1 and k["again"] == {"posts": 1, "refused": True} and k["preview"] == 1, k)
    x = lm["l3_" + kind]
    check(f"(l) a second submit of the {kind} Add while it is on its way sends nothing; after a refusal or no answer it can be sent again",
          x["posts"] == 1 and x["refused"] == "A made-up refusal." and x["lost"] == "TypeError" and x["retry"] == 3, x)
    check(f"(l) what is typed in the {kind} Add while it is on its way stays, with the dialog, when the reading back fails",
          lm["l1fail_" + kind] == {"open": True, "typed": "typed while it was sent", "dirty": True}, lm["l1fail_" + kind])
    v = lm["l1_" + kind]
    check(f"(l) ...and goes into the saved record's dialog, not saved yet, when it works", v["typed"] == "typed while it was sent" and v["dirty"] is True and v["title"] not in ("", "Add item", "Add reminder"), v)
    check(f"(l) the {kind} Add closed while it is on its way: a dialog opened since isn't replaced; with none opened, it stays closed",
          lm["l2other_" + kind] == {"same": True, "dirty": False} and lm["l2closed_" + kind] == {"closed": True}, (lm["l2other_" + kind], lm["l2closed_" + kind]))
    check(f"(l) ...and the same Add opened again meanwhile isn't taken as saved: what is typed in it counts",
          lm["l2again_" + kind] == {"typed": "typed in the new one", "dirty": True, "saved": False}, lm["l2again_" + kind])
check("(l) a new reminder the server's answer doesn't number is found by its key and opened, but never over a dialog opened since",
      lm["byKey"] == {"opened": True} and lm["l2byKey"] == {"same": True}, (lm["byKey"], lm["l2byKey"]))
check("(l) a Delete (record, checklist item, reminder), a checklist Copy or a Paste a list answered after another dialog was opened doesn't close it",
      lm["l2delete"] == {"record": True, "checklist": True, "reminder": True, "copy": True, "paste": True}, lm["l2delete"])
check("(l) a Stop using answered after another record was opened leaves that dialog and its reason box as they are",
      lm["l2stop"] == {"same": True, "reason": "The other reason", "box": False}, lm["l2stop"])
check("(l) a second Copy while the first is on its way sends nothing", lm["l3copy"] == 1, lm["l3copy"])
for key in ("add", "save"):
    x = lm["l3_" + key]
    check(f"(l) a second submit of the record dialog's {key} while it is on its way sends nothing; after a refusal or no answer it can be sent again",
          x["posts"] == 1 and "A made-up refusal." in x["refused"] and x["retry"] == 3, x)
v = lm["l1addFail"]
check("(l) what is typed while a record is added stays in the open dialog when the reading back fails, as not saved, and it never adds again",
      v == {"open": True, "typed": "typed while it was sent", "dirty": True, "said": True, "again": {"posts": 1, "refused": True}}, v)
check("(l) ...and goes into the saved record's dialog, said as Unsaved changes, when it works",
      lm["l1add"] == {"id": 777, "title": "The saved account", "typed": "typed while it was sent", "dirty": True, "foot": "Unsaved changes"}, lm["l1add"])
check("(l) what is typed while the saved record is read isn't lost either", lm["l1read"] == {"id": 777, "typed": "typed while it was read", "dirty": True}, lm["l1read"])
v = lm["l1save"]
check("(l) the same for a Save: what was typed while it was on its way stays, the other fields show what the server has",
      v["id"] is True and v["notes"] == "typed while it was saved" and v["label"] == v["server"] and v["dirty"] is True, v)
check("(l) with nothing typed meanwhile the saved record's dialog is clean", lm["l1clean"] == {"id": 777, "label": "The saved account", "dirty": False}, lm["l1clean"])
check("(l) what was typed in a field the saved record can't change isn't carried into its dialog", lm["l1locked"] == {"key": "made_key", "dirty": False}, lm["l1locked"])
v = lm["l2add"]
check("(l) the record Add closed while on its way, another record opened: it isn't replaced or rebaselined, and what is typed in it counts",
      v["same"] is True and v["typed"] == "typed in the other" and v["dirty"] is True and v["posts"] == 1, v)
v = lm["l2refused"]
check("(l) a refusal answered after that is said in a message, never in the other record's dialog",
      v["same"] is True and v["inDialog"] == "" and v["toasts"] == ["Bank account wasn't saved: A made-up refusal."], v)
check("...and a server failure then says it isn't known whether it was saved",
      lm["l2unsure"] == ["Bank account: The server could not save it. It isn't known whether it was saved: check before doing it again."], lm["l2unsure"])
check("(l) closed while it is on its way, or while the saved record is read, and nothing else opened: it stays closed",
      lm["l2closed"] == {"closed": True} and lm["l2read"] == {"closed": True}, (lm["l2closed"], lm["l2read"]))
check("(l) a new Add opened meanwhile isn't taken as saved: what is typed in it counts", lm["l2new"] == {"id": "new", "typed": "typed in the new one", "dirty": True, "saved": False}, lm["l2new"])

# ---------- slice 9c: First run's import reason ----------
fr = o["frReason"]
said = "Started this install from Setup everything 2026-11-14.json."
check("First run fills the reason box from the file chosen, and an untouched box is sent as it shows",
      fr["shown"] == said and fr["sentUntouched"] == [said], fr)
check("...a reason typed over it is sent instead", fr["editedShown"] == "Moved from the old PC" and fr["sentEdited"] == ["Moved from the old PC"], fr)
office = "Started this install from Office setup.json."
check("...and an emptied box (or only spaces) gets the same sentence back, shown in the box, and sent",
      fr["emptied"] == [{"first": [office], "box": office, "again": [office]}] * 2, fr["emptied"])
check("each file chosen has its own sentence: after a refused one, and after Cancel, nothing typed or said for an earlier file stays",
      fr["afterRefusal"] == "Started this install from second.json." and fr["afterCancel"] == "Started this install from third.json." and fr["sentThird"] == ["Started this install from third.json."], fr)
lg = fr["long"]
check("a very long file name is cut, whole characters only, so the sentence fits the reason's 500 and is sent as shown",
      lg["units"] <= 500 and lg["units"] >= 498 and lg["whole"] is True and lg["shown"].startswith("Started this install from \U0001F600") and lg["shown"].endswith("\u2026.") and lg["sent"] == [lg["shown"]] and lg["max"] == "500", lg)
check("the file name is shown as it is written, never as HTML", 'value="Started this install from a&quot;&lt;b&gt;&amp;.json."' in fr["escaped"] and "<b>&.json" not in fr["escaped"], fr["escaped"][:600])

# ---------- the layout keeps today's narrow rules ----------
check("the form keeps Setup's 520-pixel rule: two columns, one under 520 pixels, in the new dialog too",
      "@media (max-width: 520px) { .setup-form { grid-template-columns: minmax(0, 1fr); } }" in css and ".setup-form { grid-template-columns: 1fr 1fr; }" in css
      and n(o["dlgAccount"], r'<div class="form setup-form">') >= 4 and not re.search(r'style="[^"]*(?<![-\w])width', o["dlgAccount"]), n(o["dlgAccount"], r'class="form setup-form"'))
check("the dialog fills the screen at phone width, as the other dialogs do, and the list scrolls inside its own frame",
      ".drawer.pay-dlg, .drawer.pay-dlg.pd-viewing, .drawer.pay-dlg.np-dlg, .drawer.pay-dlg.np-dlg.st-dlg { width: 100vw;" in css and "min(680px, calc(100vw - 48px))" in css and 'class="tbl-wrap" id="setupList"' in page)
src = app_source()
check("the page's heading scripts are in the page list, in order: First run after the Overview", src.index("function viewFirstRun") > src.index("async function viewOverview"))

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
