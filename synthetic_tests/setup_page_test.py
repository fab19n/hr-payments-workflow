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
KEEP_GOING = bool(os.environ.get("HRP_KEEP_GOING"))  # list every check that fails, not only the first (to see what a change fixes)


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
          f"/api/setup/parties?entity={EXB}", "/api/setup/restore?kind=entities", f"/api/setup/restore?kind=gl_accounts&entity={EXA}"):
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
    if ((FX.fail || {})[path]) throw new TypeError("Failed to fetch");
    const hit = FX.post[path + (body && body.preview ? "?preview" : "")] || { status: 200, body: { ok: true } };
    return { ok: hit.status < 400, status: hit.status, json: async () => hit.body };
  }
  if ((FX.fail || {})[path]) throw new TypeError("Failed to fetch");   // the app is not running
  if (onGet) onGet(path);
  const hit = FX.get[path];
  if (hit === undefined) return { ok: false, status: 404, json: async () => ({ error: "no fixture for " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(hit)) };
}
const scrolls = [];   // what the window was scrolled to: a page drawn again must not move it
const win = { matchMedia: () => ({ matches: true }), location: { hash: "#/admin/setup", replace(v) { this.hash = v; } }, scrollX: 0, scrollY: 0,
  scrollTo(...a) { scrolls.push(a); [this.scrollX, this.scrollY] = a; }, addEventListener() {}, print() {} };
let onGet = null;   // called with the path of each read: what the page looks like while it is waiting for the records
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
    renderNav = () => {}; render = async () => { __calls.push(["render"]); }; navigate = async place => { __calls.push(["navigate", place]); return true; };
    globalThis.click = async (dataset, extra = {}) => { const b = { dataset, tagName: "BUTTON", id: "", className: "", getAttribute: () => null, ...extra }; b.closest = () => b;
      const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; for (const f of __listeners.click || []) await f(ev); };`);
  const main = el("main"), box = () => el("setupMain");
  // the menu is a new element (scrolled to the top) each time the page is drawn, as in a browser; its item on show records what is done to it
  // The menu has a frame 400 high at the top of the window; its item on show sits at 700 (Move setup), 420 (Required documents) or 80 in its content.
  // Each time the grid is drawn the section's own place is empty until the section is drawn, and each scrollTop set records whether it was.
  const navOf = html => { const m = /class="sn on" data-setup-kind="([a-z_]+)"/.exec(html);
    if (!/class="setup-nav/.test(html)) return null;
    const kind = m && m[1], at = kind === "move" ? 700 : kind === "required" ? 420 : 80;
    let st = 0;
    const nav = { sets: [], kind, clientHeight: 400, clientTop: 0, getBoundingClientRect: () => ({ top: 100, height: 400 }),
      get scrollTop() { return st; }, set scrollTop(v) { st = v; nav.sets.push([v, smWrites > 0]); }, userScroll(v) { st = v; },
      active: { scrolled: [], scrollIntoView(o) { this.scrolled.push(o); }, focus() { document.activeElement = this; }, getBoundingClientRect: () => ({ top: 100 + at - st, height: 40 }) },
      querySelector(s) { return s === ".sn.on" ? this.active : null; } };
    return nav; };
  // The page is 700 high and 2500 more while its section has something in it, in a window 600 high: a short page clamps the window's scroll, as a browser does.
  // The section's own place keeps what the grid was drawn with (the old section, for a redraw) and counts the times the section is written.
  let mainHtml = "", smHtml = "", smWrites = 0;
  const seenY = [];
  const clamp = () => { const max = Math.max(0, 700 + (smHtml.length > 200 ? 2500 : 0) - 600); if (win.scrollY > max) win.scrollY = max; seenY.push(win.scrollY); };
  Object.defineProperty(el("setupMain"), "innerHTML", { get: () => smHtml, set(v) { smHtml = v; smWrites++; clamp(); } });
  Object.defineProperty(main, "innerHTML", { get: () => mainHtml, set(v) {
    mainHtml = v; const m = /id="setupMain">([\s\S]*)<\/div><\/div>$/.exec(v); smHtml = m ? m[1] : ""; smWrites = 0; clamp(); main.nav = navOf(v); } });
  main.nav = null; main.querySelector = s => s === ".setup-nav" ? main.nav : null;
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
    r.windowScrolls = scrolls.length;
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

  // 2. a section drawn again keeps what it showed in place until the new one is read, writes the new one once, and the window keeps its place
  await tryit("redrawKeeps", async () => {
    const r = {}, during = [];
    FX.get["/api/setup/import"] = { empty: true, holding: [] };
    await view("parties", FX.EXA);
    onGet = path => { if (/\/api\/setup\/parties\?entity=/.test(path)) during.push({ kept: smHtml.length > 200, y: win.scrollY }); };
    win.scrollY = 800; seenY.length = 0; scrolls.length = 0;
    await run(`viewSetup(__el("main"))`); await sleep(20);   // a save, a stop, a delete, a put back: the same section of the same company
    r.same = { y: win.scrollY, low: Math.min(...seenY), scrolls: scrolls.length, during, writes: smWrites };
    onGet = path => { if (/\/api\/setup\/parties\?entity=/.test(path)) win.scrollY = 77; };   // something moved the window while the records were read
    win.scrollY = 800; scrolls.length = 0;
    await run(`viewSetup(__el("main"))`); await sleep(20);
    r.moved = { y: win.scrollY, scrolls: scrolls.slice() };
    onGet = null; win.scrollY = 800; scrolls.length = 0;
    await view("accounts", FX.EXA);    // another section starts empty, at the top, and is not put back
    r.otherSection = { y: win.scrollY, scrolls: scrolls.length };
    win.scrollY = 800; scrolls.length = 0;
    await view("accounts", FX.EXB);    // so does another company
    r.otherCompany = { y: win.scrollY, scrolls: scrolls.length };
    await view("accounts", FX.EXA);
    return r;
  });

  // 3. First run: what was saved and not read again is over once something else read the records, and they list the company
  await tryit("frSavedElsewhere", async () => {
    const r = {};
    run(`state.view = "overview"; state.meta.entities = []; FR.done = null; FR.note = null; FR.saved = null; FR.alerted = false; FR.busy = ""; FR.preview = null; FR.file = null;
      FR.addOpen = true; FR.tried = false; FR.code = "GHI"; FR.cname = "Example Three"; FR.reg = ""; FR.kind = "here"`);
    withCompanies([co(1, "GHI", 1)]); FX.fail = { "/api/meta": true };
    r.threw = await run(`frAddCompany().then(() => "ok", e => e.name)`); FX.fail = {};
    r.dueWhileSaved = run(`firstRunDue()`); r.savedKnown = run(`FR.saved && FR.saved.known`);
    run(`state.meta = ${JSON.stringify({ ...meta0, entities: [co(1, "GHI", 1)] })}`);   // Setup read the records again
    r.dueAfter = run(`firstRunDue()`); r.saved = run(`FR.saved`); r.alerted = run(`FR.alerted`);
    // a second company saved but not read: the records still list the first, so it is still saved; they list both once they are read again
    run(`FR.done = null; FR.note = null; FR.addOpen = true; FR.code = "JKL"; FR.cname = "Example Four"; FR.kind = "here"; FR.tried = false`);
    withCompanies([co(1, "GHI", 1), co(2, "JKL", 1)]); FX.fail = { "/api/meta": true };
    r.threw2 = await run(`frAddCompany().then(() => "ok", e => e.name)`); FX.fail = {};
    r.due2 = run(`firstRunDue()`); r.saved2 = run(`!!FR.saved`);
    run(`state.meta = ${JSON.stringify({ ...meta0, entities: [co(1, "GHI", 1), co(2, "JKL", 1)] })}`);
    r.due2After = run(`firstRunDue()`); r.saved2After = run(`FR.saved`);
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
      has(ent, ">Books<", "Kept in SQL Account", "Kept here", "Switcher: ") or has(ent, ">Books<", "Kept in SQL Account", "Kept here"), ent[:900])
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
      and nk["click"] == {"kind": "accounts", "top": 80, "sets": [[400, False], [80, True]], "intoView": 0, "focused": True} and nk["windowScrolls"] == 0, nk)
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
      sv["threw"] == "TypeError" and sv["busy"] == "" and {k: v for k, v in sv["saved"].items() if k != "known"} == {"imported": True, "code": "", "kept": ""} and has(sv["html"], SAVED, 'data-fr-reload="1"')
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

# ---------- round 4 ----------
rk = o["redrawKeeps"]
check("a section drawn again (a save, a stop, a delete, a put back) keeps what it showed in place until the new one is read, writes the new one once, and the window never moves",
      rk["same"]["y"] == 800 and rk["same"]["low"] == 800 and rk["same"]["scrolls"] == 0 and rk["same"]["during"] == [{"kept": True, "y": 800}] and rk["same"]["writes"] == 1, rk["same"])
check("...if anything moved the window meanwhile it goes back where it was, with one scroll; another section or company starts at the top, empty, and is not put back",
      rk["moved"] == {"y": 800, "scrolls": [[0, 800]]} and rk["otherSection"] == {"y": 100, "scrolls": 0} and rk["otherCompany"] == {"y": 100, "scrolls": 0}, rk)
se = o["frSavedElsewhere"]
check("First run's saved-but-not-read note is over once Setup (or anything) has read the records and they list the company: the Overview draws, and the alert is gone",
      se["threw"] == "TypeError" and se["dueWhileSaved"] is True and se["savedKnown"] == 0 and se["dueAfter"] is False and se["saved"] is None and se["alerted"] is False, se)
check("...a second company saved but not read keeps it until the records list one more than they did, and then it is over too",
      se["threw2"] == "TypeError" and se["due2"] is True and se["saved2"] is True and se["due2After"] is False and se["saved2After"] is None, se)
rr = o["restoreRetry"]
check("Put it back's Try again with the app stopped makes one request and shows one dialog each time it is pressed, and works once the app is back",
      all(x == {"requests": 1, "dialogs": 1, "notes": 1} for x in rr["rounds"]) and len(rr["rounds"]) == 3
      and rr["back"]["requests"] == 1 and rr["back"]["dialogs"] == 1 and "It comes back as it was" in rr["back"]["body"] and "Couldn't load" not in rr["back"]["body"], rr)

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
