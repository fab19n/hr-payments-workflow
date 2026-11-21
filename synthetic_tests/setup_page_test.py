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

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:900]}" if detail else ""))
        sys.exit(1)
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
spare = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Spare", "bank": "Example Bank", "currency": "MYR"}})
call("delete", f"/api/setup/accounts/{spare['id']}", json={"reason": "Opened by mistake"})
t1 = call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form"}})
call("delete", f"/api/setup/doc_types/{t1['id']}", json={"reason": "Wrong name"})
call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form again"}})

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
          f"/api/setup/payment_types/{salary['id']}", "/api/setup/import", "/api/setup/required?entity=", f"/api/setup/required?entity={EXA}", f"/api/setup/required?entity={EXB}"):
    fx(p)
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
const document = { activeElement: null, body: { classList: { add() {}, remove() {} } }, querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null,
  querySelectorAll: () => [], getElementById: id => els[id] || null, addEventListener(t, f) { (listeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  const method = init.method || "GET", body = init.body && typeof init.body === "string" ? JSON.parse(init.body) : null;
  if (method !== "GET") {
    calls.push([method, path, body]);
    const hit = FX.post[path + (body && body.preview ? "?preview" : "")] || { status: 200, body: { ok: true } };
    return { ok: hit.status < 400, status: hit.status, json: async () => hit.body };
  }
  const hit = FX.get[path];
  if (hit === undefined) return { ok: false, status: 404, json: async () => ({ error: "no fixture for " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(hit)) };
}
const win = { matchMedia: () => ({ matches: true }), location: { hash: "#/admin/setup", replace(v) { this.hash = v; } }, scrollTo() {}, addEventListener() {}, print() {} };
const sandbox = { document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {} }, window: win, navigator: {}, __el: el, __calls: calls, __listeners: listeners,
  __btn: { closest: () => ({ after() {} }), getAttribute: () => "false", isConnected: true } };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = {};
(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));
  run(`state.meta = ${JSON.stringify(FX.get["/api/meta"])}; state.month = "2026-11"; state.day = dayKey(); state.entity = ${FX.EXA};
    renderNav = () => {}; render = async () => { __calls.push(["render"]); }; navigate = async place => { __calls.push(["navigate", place]); return true; };
    globalThis.click = async (dataset, extra = {}) => { const b = { dataset, tagName: "BUTTON", id: "", className: "", getAttribute: () => null, ...extra }; b.closest = () => b;
      const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; for (const f of __listeners.click || []) await f(ev); };`);
  const main = el("main"), box = () => el("setupMain");
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
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""

fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps({"get": GET, "post": POST, "EXA": EXA, "EXB": EXB, "MAIN": main["id"], "OLD": old["id"], "SALARY": salary["id"], "RESTORE": restored["row_id"], "TAKEN": taken["row_id"]}), encoding="utf-8")
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


o = plain(o)


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
check("Required documents for a company Kept here says the payment voucher is required where the rules say so, and has no posted-here choice",
      has(o["required"], "EXB is Kept here: the payment voucher is required where the rules above say so.") and "posted here" not in o["required"].lower()
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

# ---------- the layout keeps today's narrow rules ----------
css = (Path(__file__).resolve().parents[1] / "static" / "app.css").read_text(encoding="utf-8")
check("the form keeps Setup's 520-pixel rule: two columns, one under 520 pixels, in the new dialog too",
      "@media (max-width: 520px) { .setup-form { grid-template-columns: minmax(0, 1fr); } }" in css and ".setup-form { grid-template-columns: 1fr 1fr; }" in css
      and n(o["dlgAccount"], r'<div class="form setup-form">') >= 4 and not re.search(r'style="[^"]*(?<![-\w])width', o["dlgAccount"]), n(o["dlgAccount"], r'class="form setup-form"'))
check("the dialog fills the screen at phone width, as the other dialogs do, and the list scrolls inside its own frame",
      ".drawer.pay-dlg, .drawer.pay-dlg.pd-viewing, .drawer.pay-dlg.np-dlg, .drawer.pay-dlg.np-dlg.st-dlg { width: 100vw;" in css and "min(680px, calc(100vw - 48px))" in css and 'class="tbl-wrap" id="setupList"' in page)
src = app_source()
check("the page's heading scripts are in the page list, in order: First run after the Overview", src.index("function viewFirstRun") > src.index("async function viewOverview"))

print(f"\n{len(passed)} checks passed")
