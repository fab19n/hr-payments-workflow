r"""Slice 5: Accounting › SQL import, built to Sql.dc.html and SqlBooks.dc.html, on made-up records only.

The server part runs the app on a temporary records folder (Flask's test client): a company Kept in SQL Account imports a
pasted listing of made-up vouchers, invoices and a journal; one voucher is linked, one is ignored and marked as deleted
in SQL (its date is in the row), two are a probable correction. A second listing is read (not imported) for the preview,
and a company kept here is there for the "isn't used" card. The page's answers that need SQL's reports or a folder of
exports (what a fetch found, the account lines, the checks against SQL's reports) are made up in the shape the server
sends.

The page part runs the page script in Node against a small stand-in for the page (an element per id), and checks the
boards' states and wording: the three steps; Fetch and its folder (Use another folder, a refused folder, Folder saved, the
fetch that couldn't read the folder); what the fetch found (read, not used with each status's chip and its way on, left
alone, what the labels mean, the files left alone); the preview (Preview: nothing is saved yet, a supplier's invoice named
as one, a voucher with no payment, Columns read, the import note and button following a pick); nothing new (with files
not used, and with none); journal lines (balanced and chosen, or refused); SQL's reports only; paste and file refused in
place; the two tabs and their arrow keys; the file box (a wrong type, too large, two files dropped, dragging, chosen);
the result after Import (entries, account lines, journal lines) and its close; Find an SQL entry; Create payments for all
and Ignore all asking first; Linked folding; Ignored with its "Deleted in SQL" pill; Journals and invoices; the checks'
sections in words; the toasts of Ignore and Create payment; and the card a company kept here gets.

Run: .venv\Scripts\python -m synthetic_tests.sql_page_test
"""
import copy
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-page-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle, app_source  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "sql-downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

ROOT = Path(__file__).resolve().parent.parent
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXQ", "name": "Example Query Sdn Bhd", "accounts": [{"label": "Operating account", "bank": "Example Bank", "number": "000-611"}]},
    {"code": "EXH", "name": "Example Here Ltd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-612"}]},
]}), encoding="utf-8")

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:700])


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


meta = j("get", "/api/meta")
ids = {e["code"]: e["id"] for e in meta["entities"]}
EXQ, EXH = ids["EXQ"], ids["EXH"]
acct = {e["code"]: e["accounts"][0]["id"] for e in meta["entities"]}


def packet(rows):
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % " ".join('%s="%s"' % kv for kv in r.items()) for r in rows) + "</ROWDATA></DATAPACKET>")


def voucher(no, day, desc, amount, way="out"):
    return {"DOCNO": no, "DOCTYPE": no[:2], "DOCDATE": day, "DESCRIPTION": desc, "DOCAMT": f"{amount:.2f}", "CANCELLED": "FALSE",
            "DR": f"{amount:.2f}" if way == "in" else "0.00", "CR": "0.00" if way == "in" else f"{amount:.2f}"}


def document(no, day, desc, amount, code):
    return {"DOCNO": no, "DOCTYPE": no[:2], "DOCDATE": day, "DESCRIPTION": desc, "CODE": code, "DOCAMT": f"{amount:.2f}", "CANCELLED": "FALSE"}


# ---------- the made-up month: a payment, then a listing imported ----------
water = j("post", "/api/payments", json={"entity_id": EXQ, "month": "2026-10", "description": "Example water - test", "category": "utility",
                                         "amount": 84.30, "account_id": acct["EXQ"], "due_date": "2026-10-21"})["id"]
first = [voucher("PV2610-201", "20261021", "EXAMPLE WATER OCTOBER", 84.30), voucher("PV2610-202", "20261020", "EXAMPLE COURIER OCTOBER", 186.50),
         voucher("PV2610-203", "20261022", "EXAMPLE STATIONERY OCTOBER", 95.40), voucher("PV2610-208", "20261023", "EXAMPLE PRINTING OCTOBER", 70.00),
         voucher("OR2610-204", "20261025", "EXAMPLE REVERSAL", 48.00, "in"), voucher("PV2610-205", "20261025", "EXAMPLE BANK CHARGES", 48.00),
         document("PI2610-206", "20261026", "EXAMPLE CLEANER - OCTOBER", 1200.00, "400-X101"),
         {**document("JV2610-207", "20261031", "EXAMPLE ACCRUAL OCTOBER", 300.00, ""), "CODE": ""}]
pre = j("post", "/api/sql/preview", json={"entity_id": EXQ, "text": packet(first)})
res = j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})
check("the made-up listing is imported", res["added"] == len(first), res)
sid = {r["doc_no"]: r["id"] for r in q("SELECT id, doc_no FROM sql_entries WHERE entity_id = ?", (EXQ,))}
link = j("post", f"/api/sql/entries/{sid['PV2610-201']}", json={"payment_id": water})
j("post", f"/api/sql/entries/{sid['PV2610-203']}", json={"status": "ignored"})
with db.connect() as con:  # confirmed as deleted in SQL (the server route needs SQL's journal read; the page reads the row's date)
    con.arm("user", "test: an entry confirmed as deleted in SQL")
    con.execute("UPDATE sql_entries SET deleted_in_sql = '2026-11-18T10:05:00' WHERE id = ?", (sid["PV2610-203"],))
    con.commit()
    con.disarm()
d = j("get", f"/api/sql/entries?entity={EXQ}")
check("the page's data: two vouchers waiting, the probable correction, one linked, one ignored with its date",
      sorted(u["doc_no"] for u in d["unlinked"] if not u["correction"]) == ["PV2610-202", "PV2610-208"]
      and sorted(u["doc_no"] for u in d["unlinked"] if u["correction"]) == ["OR2610-204", "PV2610-205"]
      and [x["doc_no"] for x in d["linked"]] == ["PV2610-201"] and [(x["doc_no"], x["deleted_in_sql"]) for x in d["ignored"]] == [("PV2610-203", "2026-11-18T10:05:00")],
      (d["unlinked"], d["ignored"]))
# What SQL's reports would add (the shape /api/sql/entries sends): a lines pill, SQL's documents no listing matches, by section.
d["lines"] = {str(sid["PV2610-202"]): {"n": 2, "balanced": True, "state": "current", "version": 1, "total_ok": True, "unknown": [], "warnings": 0}}
d["ledger"] = {"reads": {}, "orphans": {
    "no_listing": [{"doc_no": "PV2610-299", "doc_date": "2026-10-28", "book": "bank"}, {"doc_no": "JV2610-298", "doc_date": "2026-10-29", "book": "general"}],
    "own_lines": [{"doc_no": "CN2610-297", "doc_date": "2026-10-30"}],
    "not_in_journal": [{"doc_no": "PV2610-202", "doc_date": "2026-10-20", "amount": 186.5, "gone": True, "can_confirm": True, "ids": [sid["PV2610-202"]]}],
    "before_tracking": 0}}

# A second listing read, not imported: the preview of a paste.
second = [document("PI2610-210", "20261027", "EXAMPLE CLEANER - EXTRA", 150.00, "400-X101"), document("SD2610-211", "20261027", "EXAMPLE CLEANER - DEBIT", 20.00, "400-X101"),
          document("IV2610-212", "20261028", "EXAMPLE TENANT - OCTOBER", 900.00, "300-X201"), voucher("PV2610-213", "20261029", "EXAMPLE PARKING OCTOBER", 33.00)]
paste_pre = j("post", "/api/sql/preview", json={"entity_id": EXQ, "text": packet(second)})
pv213 = next(r for r in paste_pre["records"] if r["doc_no"] == "PV2610-213")
check("the paste's preview: the voucher has no payment, the invoices are named by type",
      pv213["payment_id"] is None and {r["doc_no"]: r["label"] for r in paste_pre["records"] if r["kind"] != "payment"}
      == {"PI2610-210": "Supplier invoice", "SD2610-211": "Supplier debit note", "IV2610-212": "Customer invoice"})

# What a fetch found, in the shape sqlfetch.gather sends (made-up files).
review = {"folder": str(FOLDER), "other": 2, "entries": 9, "new": 6, "already": 3, "files": [
    {"name": "PV Listing Example.xlsx", "status": "read", "reason": "", "title": "Payment Voucher Listing", "period": ["2026-10-01", "2026-10-31"], "new": 4, "already": 1, "repeated": 0},
    {"name": "GL Journal Example.xlsx", "status": "read", "reason": "", "report": "journal", "title": "GL Journal of Transaction", "period": ["2026-10-01", "2026-10-31"], "docs": 5, "lines": 11},
    {"name": "Old listing A.xlsx", "status": "imported_before", "reason": "Imported before."},
    {"name": "Old listing B.xlsx", "status": "imported_before", "reason": "Imported before."},
    {"name": "PV Listing Example (1).xlsx", "status": "copy", "reason": "A copy of PV Listing Example.xlsx."},
    {"name": "Other company listing.xlsx", "status": "other_company", "reason": "This Payment Voucher Listing is for EXH (Example Here Ltd), not EXQ."},
    {"name": "Printed name listing.xlsx", "status": "unknown_company", "take_for": "EXQ", "company": "EXAMPLE PRINTED NAME SDN BHD",
     "reason": "This Payment Voucher Listing is from a company not in Setup: \"EXAMPLE PRINTED NAME SDN BHD\" matches no company's name or registration number in Setup, so nothing was taken from it. If it is EXQ's, click Take it for EXQ; otherwise correct the company's name or registration number in Setup › Companies, then fetch again."},
    {"name": "Big journal.xlsx", "status": "too_large", "reason": "too large to read (31.4 MB; at most 25 MB). Export a shorter period."},
    {"name": "Cash book short.xlsx", "status": "unreadable", "reason": "This Cash Book Listing says it has 12 documents, but 11 could be read, so nothing was taken from it. Copy and paste this listing instead."},
    {"name": "Locked listing.xlsx", "status": "unreadable", "reason": "This file couldn't be opened. Close it if it is open in Excel, then fetch again."},
    {"name": "MyInvois other.xlsx", "status": "unknown_company", "reason": "This MyInvois copy has no e-Invoice whose supplier or buyer TIN is EXQ's, so it was left out. Enter the company's TIN in Setup › Companies, then fetch again."}]}
ledger_box = {"totals": {"docs": 5, "lines": 11, "new": 4, "changed": 1, "same": 0, "back": 0, "gone": 0}, "refused": None, "gone": [],
              "files": [{"name": "GL Journal Example.xlsx", "title": "GL Journal of Transaction", "period": "01/10/2026-31/10/2026", "kind": "journal", "docs": 5, "lines": 11, "note": ""}],
              "counting": {"bank_code": "310-1000", "signed_off": [], "journals": [{"doc_no": "JV2610-207", "doc_date": "2026-10-31", "amount": -300.0, "before": None, "listed": True, "signed_off": False, "month": "2026-10"}]}}
found = {**copy.deepcopy(paste_pre), "filename": "SQL exports fetched 20261118-1042.csv", "fetch": review, "ledger": ledger_box}
nothing = {"entity_id": EXQ, "records": [], "nothing_new": True, "fetch": {**review, "files": [f for f in review["files"] if f["status"] not in ("read",)]}}
empty = {"entity_id": EXQ, "records": [], "nothing_new": True, "fetch": {"folder": str(FOLDER), "other": 0, "entries": 0, "new": 0, "already": 0, "files": []}}
reports = {"token": "t-reports", "entity_id": EXQ, "filename": "SQL reports fetched 20261118-1042.csv", "records": [], "header_row": -1, "headers": [], "mapping": {},
           "fields": [], "candidates": [], "fetch": {**review, "files": review["files"][1:2]}, "ledger": ledger_box}
jl_opts = [{"id": sid["JV2610-207"], "doc_no": "JV2610-207", "doc_date": "2026-10-31", "amount": 300.0, "match": True}]
jl_ok = {"token": "t-jl", "entity_id": EXQ, "filename": "SQL listing pasted 20261118-1050.txt", "records": [], "journal_lines": {
    "text_form": True, "balanced": True, "lines": 4, "options": jl_opts, "chosen": sid["JV2610-207"], "message": "Only JV2610-207 has a total of 300.00, so it is chosen.",
    "notes": [{"text": "Journal lines for JV2610-207: none of the 4 lines is on the bank account, so it moves no money. The lines are kept."}]}}
jl_bad = {"token": "t-jl2", "entity_id": EXQ, "filename": "SQL listing pasted 20261118-1051.txt", "records": [], "journal_lines": {
    "text_form": True, "balanced": False, "lines": 3, "options": [], "chosen": None, "notes": [],
    "message": "These lines don't balance: debits add up to 310.00 and credits to 300.00. They can't be kept."}}
SUM = "This Cash Book Listing says it has 12 documents, but 11 could be read, so nothing was taken from it. Copy and paste this listing instead."
fixture = {"exq": EXQ, "exh": EXH, "water": water, "row213": pv213["row"], "id202": sid["PV2610-202"], "id208": sid["PV2610-208"],
           "routes": {"/api/meta": j("get", "/api/meta"), f"/api/sql/entries?entity={EXQ}": d},
           "found": found, "paste": paste_pre, "nothing": nothing, "empty": empty, "reports": reports, "jl_ok": jl_ok, "jl_bad": jl_bad, "sum": SUM,
           "res_import": {"added": 4, "linked": 1, "skipped": 0, "bank_lines_matched": 1, "changed_linked": 1, "replaced": []},
           "res_reports": {"added": 0, "linked": 0, "skipped": 0, "ledger": {"files": [{"kind": "journal", "summary": {"docs": 5}, "problems": 0}, {"kind": "trial_balance", "problems": 2}]}},
           "res_lines": {"journal_lines": 4},
           "create_all": {"created": 2, "linked": 0, "left": 0, "corrections": ["OR2610-204", "PV2610-205"], "bank_lines_matched": 0}}
fx = tmp / "fixture.json"
fx.write_text(json.dumps(fixture), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, posts = [], docListeners = {}, replies = {}, refuse = {};
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, listeners: {}, files: [],
  classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} }, addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
  querySelectorAll() { return []; }, querySelector() { return null; }, setAttribute(k, v) { this["@" + k] = v; }, removeAttribute(k) { delete this["@" + k]; },
  focus() { focused = id; }, remove() {}, scrollIntoView() {} };
let focused = null;
const document = { querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, querySelectorAll: () => [], getElementById: () => null,
  addEventListener(t, f, capture) { (docListeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") {
    posts.push([init.method, path, init.body && typeof init.body === "string" ? JSON.parse(init.body) : "(form)"]);
    if (refuse[path]) { const m = refuse[path]; delete refuse[path]; return { ok: false, status: 400, json: async () => ({ error: m }) }; }
    const r = replies[path] !== undefined ? replies[path] : { ok: true, bank_lines_matched: 0 };
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
  }
  let r = fx.routes[path];
  if (r === undefined && path.startsWith("/api/audit/status")) r = { ok: true };
  if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: "not stubbed: " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
const ctx = vm.createContext({ document, fetch, FormData: class { append() {} }, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, window: { print() {} } });
const run = code => vm.runInContext(code, ctx);
const pause = () => new Promise(r => setTimeout(r, 30));
const target = (dataset = {}, id = "", more = {}) => ({ id, dataset, closest() { return this; }, getAttribute(k) { return this["@" + k] ?? null; }, setAttribute(k, v) { this["@" + k] = v; },
  removeAttribute(k) { delete this["@" + k]; }, classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } }, querySelector() { return null; }, querySelectorAll() { return []; }, ...more });
const fire = async (type, ev) => { for (const f of docListeners[type] || []) await f({ preventDefault() {}, stopPropagation() {}, ...ev }); await pause(); await pause(); };
const click = (dataset, id, more) => fire("click", { target: target(dataset, id, more) });
const out = {};
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  await pause();
  const show = async (entity, keep) => {
    run(`state.view = "sql"; state.entity = ${entity}; render.company = ${entity}; state.month = "2026-10"; state.day = dayKey(); state.addr = { all: false, id: null, params: {} };` + (keep ? "" : " state.sqlPreview = null; state.sq = null;"));
    await run("render()"); await pause(); return el("main").innerHTML; };
  out.page = await show(fx.exq);
  out.fetchBtn0 = el("sqlFetch").innerHTML;
  // Find an SQL entry
  await fire("input", { target: target({ search: "sql" }, "", { value: "PV2610-208" }) });
  out.found = el("sqlEntries").innerHTML; out.count = el("sq-count").textContent;
  await fire("input", { target: target({ search: "sql" }, "", { value: "" }) });
  out.count0 = el("sq-count").textContent;
  // Sorting the lists by a column heading (the shared sortTh / sortClick), then back to the list's own order
  await click({ sort: "sql", col: "amount" }); out.sortUp = el("sqlEntries").innerHTML;
  await click({ sort: "sql", col: "amount" }); await click({ sort: "sql", col: "amount" }); out.sortOff = el("sqlEntries").innerHTML;
  // Linked folds open; Create payments for all and Ignore all ask first
  await click({ sqFold: "linked" }); out.linkedOpen = el("sqlEntries").innerHTML;
  await click({}, "sqlCreateAll"); out.askAll = el("sqlEntries").innerHTML; out.askFocus = focused;
  await click({ sqAsk: "all-no" }); out.askAllNo = el("sqlEntries").innerHTML;
  await click({}, "sqlIgnoreAll"); out.askIgn = el("sqlEntries").innerHTML;
  await click({ sqAsk: "ign-no" });
  replies["/api/sql/entries/create-all"] = fx.create_all;
  await click({}, "sqlCreateAll"); posts.length = 0; await click({ sqAsk: "all-yes" });
  out.createAll = { posts: posts.map(p => p[1]), toast: el("toast").textContent };
  // Yes pressed twice while the answer is on its way: sent once
  await click({}, "sqlCreateAll"); posts.length = 0;
  await Promise.all([click({ sqAsk: "all-yes" }), click({ sqAsk: "all-yes" })]);
  out.twice = posts.filter(p => p[1] === "/api/sql/entries/create-all").length;
  // Refused: the question goes, the list is read again
  await click({}, "sqlCreateAll"); refuse["/api/sql/entries/create-all"] = "Refused for the test";
  await click({ sqAsk: "all-yes" }); out.refusedAsk = el("sqlEntries").innerHTML; out.refusedToast = el("toast").textContent;
  // Undo of Create payment: what the server did, said truly
  replies[`/api/sql/entries/${fx.id202}/unlink`] = { ok: true, removed: false, doc_no: "PV2610-202" };
  await run(`sqUndo({ id: ${fx.id202}, doc: "PV2610-202", made: true })()`); await pause(); out.undoKept = el("toast").textContent;
  replies[`/api/sql/entries/${fx.id202}/unlink`] = { ok: true, removed: true, doc_no: "PV2610-202" };
  await run(`sqUndo({ id: ${fx.id202}, doc: "PV2610-202", made: true })()`); await pause(); out.undoGone = el("toast").textContent;
  // A question left armed doesn't come back when the page is opened again from another page
  await click({}, "sqlCreateAll"); run('render.last = "overview:0"'); out.backAsk = await show(fx.exq, true);
  // Ignore and Create payment say what they did
  await click({ sqlIgnore: String(fx.id208) }); out.ignoreToast = el("toast").textContent;
  await click({ sqlCreate: String(fx.id202) }); out.createToast = el("toast").textContent;
  // A payment picked to link: Link can be pressed
  await fire("change", { target: target({ sqlLink: String(fx.id202) }, "", { value: String(fx.water) }) });
  out.sel = run("JSON.stringify(state.sq.sel)");
  // The folder: Use another folder, a refused folder, Folder saved, Escape
  await click({ sqFolder: "1" }); out.folderOpen = el("sq-fetch").innerHTML; out.folderFocus = focused;
  el("sqlDir").value = "Q:\\Nowhere";
  refuse["/api/settings/sql-exports-dir"] = "That folder can't be found. Check the path, or leave it empty to use your Downloads folder.";
  await click({}, "sqlDirSave"); out.folderBad = el("sq-fetch").innerHTML;
  replies["/api/settings/sql-exports-dir"] = { sql_exports_dir: "D:\\Example exports", default: false };
  el("sqlDir").value = "D:\\Example exports";
  await click({}, "sqlDirSave"); out.folderSaved = el("sq-fetch").innerHTML; out.folderSavedFocus = focused;
  await click({ sqFolder: "1" }); await fire("keydown", { key: "Escape", target: target({}, "sqlDir") }); out.folderEsc = el("sq-fetch").innerHTML;
  // A fetch that couldn't read the folder
  refuse["/api/sql/preview"] = "The folder D:\\Example exports can't be found. Choose the folder your SQL exports are saved in.";
  await click({}, "sqlFetch"); out.fetchErr = el("sq-fetch").innerHTML;
  // What the fetch found, and the preview under it
  replies["/api/sql/preview"] = fx.found;
  await click({ sqFolder: "1" }); el("sqlDir").value = "Q:\\Typed but not saved";  // the folder box left open
  await click({}, "sqlFetch"); out.found_ = el("sqlPreview").innerHTML; out.fetchBtn = el("sqlFetch").innerHTML; out.arriveFocus = focused;
  out.fetchCard = el("sq-fetch").innerHTML;
  out.steps = el("sq-steps").innerHTML;
  await click({ sqLegend: "1" }); out.legend = el("sqlPreview").innerHTML;
  await click({ sqLeft: "1" }); out.left = el("sqlPreview").innerHTML;
  const take = target({ sqlTake: "EXAMPLE PRINTED NAME SDN BHD" }); await fire("click", { target: take }); out.take = take.textContent;
  // Nothing new, journal lines, SQL's reports only
  run(`renderSqlPreview(${JSON.stringify(fx.nothing)})`); out.nothing = el("sqlPreview").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.empty)})`); out.empty = el("sqlPreview").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.jl_ok)})`); out.jlOk = el("sqlPreview").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.jl_bad)})`); out.jlBad = el("sqlPreview").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.reports)})`); out.reports = el("sqlPreview").innerHTML;
  await click({}, "sqlCancel"); out.cancelled = el("sqlPreview").innerHTML;
  // Paste: empty, refused, read
  el("sqlPaste").value = "";
  await fire("submit", { target: { id: "sqlPasteForm" } }); out.pasteEmpty = el("sql-paste").innerHTML;
  await fire("paste", { target: target({}, "sqlPaste"), clipboardData: { getData: () => "PV2610-301\t01/10/2026\tEXAMPLE\t1.00" } });
  out.pasteErrAfterPaste = run("state.sq.pasteErr");
  el("sqlPaste").value = "UUID\tSupplier TIN\n";
  refuse["/api/sql/preview"] = "This is a copy of SQL's MyInvois Transaction screen: paste it into Excel, save it in the exports folder and use Fetch from SQL exports.";
  await fire("submit", { target: { id: "sqlPasteForm" } }); out.pasteBad = el("sql-paste").innerHTML;
  el("sqlPaste").value = "rows";
  replies["/api/sql/preview"] = fx.paste;
  await fire("submit", { target: { id: "sqlPasteForm" } }); out.paste = el("sqlPreview").innerHTML;
  await click({ sqCols: "1" }); out.cols = el("sqlPreview").innerHTML;
  out.note0 = el("sq-inote").textContent;
  await fire("change", { target: target({ sqlRow: String(fx.row213) }, "", { value: String(fx.water) }) });
  out.note1 = el("sq-inote").textContent; out.apply1 = el("sq-apply-t").textContent;
  // A read that fails keeps the preview shown and the payment picked in it; while reading, the skeleton sits over it
  run('state.sq.reading = "fetch"; sqPaint("result")'); out.readingOver = el("sqlPreview").innerHTML; run('state.sq.reading = null; sqPaint("result")');
  refuse["/api/sql/preview"] = "The folder Q:\\Gone can't be found. Choose the folder your SQL exports are saved in.";
  await click({}, "sqlFetch"); out.keptAfterFetch = el("sqlPreview").innerHTML;
  out.pickAfterFetch = run(`state.sqlPreview && state.sqlPreview.records.find(r => r.row === ${fx.row213}).payment_id`);
  el("sqlPaste").value = "rows again"; refuse["/api/sql/preview"] = "The pasted rows couldn't be read. Clear the box, copy the listing in SQL again and paste it.";
  await fire("submit", { target: { id: "sqlPasteForm" } }); out.keptAfterPaste = el("sqlPreview").innerHTML; out.pasteErrAfter = el("sql-paste").innerHTML;
  out.pickAfterPaste = run(`state.sqlPreview && state.sqlPreview.records.find(r => r.row === ${fx.row213}).payment_id`);
  // The file tab, the arrow keys, the file box
  await click({ sqTab: "file" }); out.fileTab = el("sql-paste").innerHTML;
  await fire("keydown", { key: "ArrowLeft", target: target({ sqTab: "file" }) }); out.modeAfterKey = run("state.sq.mode");
  await click({ sqTab: "file" });
  await fire("change", { target: target({}, "sqlFile", { files: [{ name: "statement-example.pdf", size: 1000 }] }) }); out.wrongType = el("sq-ferr").innerHTML;
  await fire("change", { target: target({}, "sqlFile", { files: [{ name: "big-example.xlsx", size: 30 * 1024 * 1024 }] }) }); out.tooBig = el("sq-ferr").innerHTML;
  await fire("drop", { target: target(), dataTransfer: { types: ["Files"], files: [{ name: "a.xlsx", size: 10 }, { name: "b.xlsx", size: 10 }] } }); out.two = el("sq-ferr").innerHTML;
  await fire("dragover", { target: target(), dataTransfer: { types: ["Files"] } }); out.drag = run("state.sq.drag");
  await fire("drop", { target: target(), dataTransfer: { types: ["Files"], files: [{ name: "listing-example.xlsx", size: 2000 }] } });
  out.chosen = el("sql-file-hint").textContent; out.dragAfter = run("state.sq.drag");
  refuse["/api/sql/preview"] = fx.sum;
  await fire("submit", { target: { id: "sqlForm" } }); out.fileBad = el("sql-paste").innerHTML;
  // Import: the result in place of the preview
  run(`renderSqlPreview(${JSON.stringify(fx.paste)})`);
  replies["/api/sql/apply"] = fx.res_import;
  await click({}, "sqlApply"); out.done = el("main").innerHTML; out.doneFocus = focused;
  await click({ sqDoneClose: "1" }); out.doneClosed = el("sqlPreview").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.reports)})`); replies["/api/sql/apply"] = fx.res_reports;
  await click({}, "sqlApply"); out.doneReports = el("main").innerHTML;
  run(`renderSqlPreview(${JSON.stringify(fx.jl_ok)})`); replies["/api/sql/apply"] = fx.res_lines;
  await click({}, "sqlApply"); out.doneLines = el("main").innerHTML;
  // The result of an import doesn't come back when the page is opened again from another page
  run('render.last = "overview:0"'); out.afterNav = await show(fx.exq, true);
  // A company kept here at this address
  out.here = await show(fx.exh);
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
node = shutil.which("node")
if not node:
    print("SKIPPED the page checks: Node.js isn't installed")
    o = None
else:
    run_ = subprocess.run([node, str(probe), app_bundle(tmp / "app.js"), str(fx)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    o = json.loads(run_.stdout) if run_.returncode == 0 and run_.stdout.strip() else None
    check("the page script ran", o is not None, run_.stderr[-1500:])

if o:
    P = o["page"]
    check("the head: the company and its kind, SQL import, and the board's lede",
          "EXQ · Kept in SQL Account" in P and ">SQL import</h1>" in P and "Payments and receipts are matched to the payments in HR Payments" in P)
    check("the three steps, the third waiting: Fetch them here", all(s in P for s in ("Sign in to SQL Account", "Export each listing", "Fetch them here"))
          and '<li class="now">' in P)
    check("Fetch: one click, the cobalt button, the folder it reads and Use another folder (closed)",
          "Fetch exported listings (one click)" in P and re.search(r'class="btn sq-fetch-b" id="sqlFetch"[^>]*>.*?Fetch from SQL exports</button>', P) is not None
          and "sql-downloads</span>" in P and 'data-sq-folder="1" aria-expanded="false"' in P and "Nothing in the folder is moved or changed" in P)
    check("...and which listings it reads, the supplier's ones too", "<b>Supplier Invoice</b> and <b>Supplier Payment</b> listings" in P)
    check("Or bring in one listing yourself: two tabs, Copy and paste chosen, the paste box and Read pasted rows",
          'role="tablist"' in P and 'id="sql-tab-paste" data-sq-tab="paste" aria-selected="true"' in P and 'aria-selected="false" aria-controls="sql-panel" tabindex="-1">' in P
          and 'id="sqlPaste"' in P and "Read pasted rows" in P)
    check("Find an SQL entry: the box and the count of entries", 'placeholder="Find an SQL entry: doc no., description, amount or payment"' in P and o["count0"] == "6 SQL entries", o["count0"])
    check("...searching narrows every list and says how many show", "PV2610-208" in o["found"] and "PV2610-202" not in o["found"] and o["count"] == "Showing 1 of 6 SQL entries", o["count"])
    check("the shared list bar is back (its search, its label, its count), worded as the board has it",
          'data-search="sql"' in P and 'aria-label="Search SQL entries"' in P and 'id="sq-count" data-count="sql"' in P)
    check("...and the lists sort by their column headings: up, then back to the list's own order",
          'data-sort="sql" data-col="doc"' in P and 'data-sort="sql" data-col="amount"' in P
          and o["sortUp"].index("PV2610-208") < o["sortUp"].index("PV2610-202") and o["sortOff"].index("PV2610-202") < o["sortOff"].index("PV2610-208"))
    check("Create payments for all: Yes pressed twice while it is on its way sends it once", o["twice"] == 1, o["twice"])
    check("...refused: it says why, and the question goes (the list is read again, never left armed)",
          o["refusedToast"] == "Refused for the test" and "Create 2 payments?" not in o["refusedAsk"], (o["refusedToast"], "Create 2 payments?" in o["refusedAsk"]))
    check("Undo of Create payment says what the server did: the payment stays when something is on it, or was removed",
          o["undoKept"] == "Undone. PV2610-202 is not linked; the payment made from it stays, because something is on it now (a matched bank line or a document)."
          and o["undoGone"] == "Undone. PV2610-202 is not linked, and the payment made from it was removed.", (o["undoKept"], o["undoGone"]))
    check("a question left armed doesn't come back when the page is opened again", "Create 2 payments?" not in o["backAsk"] and 'id="sqlCreateAll"' in o["backAsk"])
    check("while reading, the skeleton sits over the preview shown, dimmed", "Reading the folder…" in o["readingOver"] and 'class="sq-dim" inert' in o["readingOver"] and "PV2610-213" in o["readingOver"])
    check("a fetch that fails keeps the preview and the payment picked in it", "PV2610-213" in o["keptAfterFetch"] and o["pickAfterFetch"] == water, o["pickAfterFetch"])
    check("...and so does a paste that fails, its reason under the box",
          "PV2610-213" in o["keptAfterPaste"] and o["pickAfterPaste"] == water and "The pasted rows couldn&#39;t be read." in o["pasteErrAfter"])
    check("an import's result doesn't come back when the page is opened again from another page", "Imported 4 entries" not in o["afterNav"] and "Kept 4 journal lines" not in o["afterNav"]
          and '<li class="now">' in o["afterNav"])
    check("SQL entries not linked: the count, the note, and Create payments for all",
          "SQL entries not linked to a payment" in P and '<span class="sq-count">· 2</span>' in P and "These are in SQL but not in HR Payments." in P
          and 'id="sqlCreateAll">Create payments for all 2</button>' in P)
    check("...each row: Link to (Link waits for a payment), Create payment, Ignore, each named for its voucher",
          'aria-label="Payment to link PV2610-208 to"' in P and re.search(r'aria-label="Link PV2610-208" disabled>Link</button>', P) is not None
          and 'aria-label="Create payment for PV2610-208">Create payment</button>' in P and 'aria-label="Ignore PV2610-208">Ignore</button>' in P)
    check("...a payment picked: Link can be pressed", json.loads(o["sel"]).get(str(fixture["id202"])) == str(water), o["sel"])
    check("Probably a correction: its note and Ignore all", "Probably a correction (no money moved)" in P and 'id="sqlIgnoreAll">Ignore all 2</button>' in P)
    check("Create payments for all asks first, in place, and moves the focus to its answer; Cancel takes it away",
          "Create 2 payments?" in o["askAll"] and "Probable corrections are left out." in o["askAll"] and 'data-sq-ask="all-yes">Create 2 payments</button>' in o["askAll"]
          and o["askFocus"] == "sq-all-yes" and "Create 2 payments?" not in o["askAllNo"])
    check("...Ignore all asks the same way", "Ignore 2 probable corrections?" in o["askIgn"] and "They move to Ignored, below." in o["askIgn"])
    check("...and the answer creates them and says so", o["createAll"]["posts"] == ["/api/sql/entries/create-all"]
          and o["createAll"]["toast"].startswith("Created 2 payments from SQL; 2 left out as probably corrections"), o["createAll"])
    check("Ignore and Create payment say what they did, with the voucher's number",
          o["ignoreToast"] == "Ignored PV2610-208. It is kept under Ignored, below." and o["createToast"] == "Created a payment from PV2610-202 and linked it.",
          (o["ignoreToast"], o["createToast"]))
    check("Linked to payments folds: closed until opened, then its note and Unlink",
          'data-sq-fold="linked" aria-expanded="false"' in P and "Linked to the wrong payment?" not in P
          and "Linked to the wrong payment?" in o["linkedOpen"] and 'aria-label="Unlink PV2610-201">Unlink</button>' in o["linkedOpen"])
    check("Ignored is open, and the one confirmed as deleted in SQL says so, with its date (the fix of section 4.1)",
          'data-sq-fold="ignored" aria-expanded="true"' in P and re.search(r'class="pill grey sq-del">.*?Deleted in SQL 18 Nov</span>', P) is not None
          and 'aria-label="Un-ignore PV2610-203">Un-ignore</button>' in P)
    check("the account lines pill: its count, a button that says it opens", re.search(r'class="pill ok pill-btn" data-sql-lines="PV2610-202" aria-expanded="false"[^>]*>2 lines', P) is not None)
    check("Journals and invoices: its note, the supplier's invoice named as one, the checklist column",
          "Journals, customer invoices and supplier invoices, kept on file against their checklist item." in P
          and re.search(r"EXAMPLE CLEANER - OCTOBER<div class=\"note small\">Supplier invoice", P) is not None and "<th>Checklist item</th>" in P)
    check("the checks against SQL's reports name each section in words, never the raw key (the fix of section 4.1)",
          "<td>the Bank Journal</td>" in P and "<td>the General Journal</td>" in P and "<td>bank</td>" not in P and "<td>general</td>" not in P)
    check("...the listing entry missing from SQL's journal: Deleted in SQL, named for its voucher; the folded list of documents no listing reads",
          'aria-label="Deleted in SQL: PV2610-202">Deleted in SQL</button>' in P and 'data-sq-fold="own" aria-expanded="false"' in P and "No listing this app reads yet · 1" in P)
    check("...and the wide tables carry the 'best done on a computer' note", "Best done on a computer" in P)
    check("the e-Invoices card is still on this page until it has its own (slice 6)", 'id="sqlEinvoices"' in P)
    check("Imported files: each with its counts", "Imported files" in P and "8 entries, 0 linked" in P)
    check("Use another folder opens the box with its help, and the focus goes to it",
          'id="sqlDir"' in o["folderOpen"] and "Save folder" in o["folderOpen"] and "The full path, starting with the drive letter." in o["folderOpen"] and o["folderFocus"] == "sqlDir")
    check("...a folder that can't be found is refused in place, the box keeps what was typed",
          "That folder can&#39;t be found." in o["folderBad"] and 'aria-invalid="true"' in o["folderBad"] and 'value="Q:\\Nowhere"' in o["folderBad"], o["folderBad"][-900:])
    check("...a folder saved says so beside the folder, and the focus goes back to Use another folder",
          "Folder saved" in o["folderSaved"] and "D:\\Example exports" in o["folderSaved"] and 'id="sqlDir"' not in o["folderSaved"] and o["folderSavedFocus"] == "sq-folder-btn")
    check("...Escape in the box closes it", 'id="sqlDir"' not in o["folderEsc"])
    check("a fetch that couldn't read the folder says so in place, with the ways on",
          "The fetch couldn't read the folder" in o["fetchErr"] and "Nothing was imported." in o["fetchErr"] and 'data-sq-folder-fix="1"' in o["fetchErr"]
          and "Paste a listing instead" in o["fetchErr"] and 'role="alert"' in o["fetchErr"])
    F = o["found_"]
    check("What the fetch found: the listings read, the documents, new and already imported",
          "What the fetch found" in F and "<b>1 listing read</b> from" in F and "9 documents" in F and "<b>6 new</b>" in F and "3 already imported" in F
          and "<b>1 report of SQL's general ledger read.</b>" in F and "Payment Voucher Listing, 1 Oct to 31 Oct" in F and ">Read</span>" in F)
    check("...the files not used, each with its status's chip and why",
          "6 files not used" in F and "Each says why. Nothing was taken from them." in F
          and all(w in F for w in (">Another company</span>", ">Company not in Setup</span>", ">Too large</span>", ">Couldn&#39;t be read</span>"))
          and "Too large to read (31.4 MB; at most 25 MB)." in F, re.findall(r"\d+ files? not used", F))
    check("...and the way on each one has: Take it for, Paste this listing instead, Fetch again, Open Setup › Companies",
          'data-sql-take="EXAMPLE PRINTED NAME SDN BHD"' in F and ">Take it for EXQ</button>" in F and 'data-sq-paste-instead="1">Paste this listing instead</button>' in F
          and 'data-sq-refetch="1">Fetch again</button>' in F and 'data-inv-setup="1">Open Setup › Companies</button>' in F)
    check("...what was left alone, What the labels mean and Show files",
          "Left alone: 2 files imported before; 1 copy of a file read; 2 other workbooks that aren't SQL listings or reports." in F
          and 'data-sq-legend="1" aria-expanded="false"' in F and "Show files" in F)
    check("...the legend says what each label means", 'id="sq-legend"' in o["legend"] and "This exact file was imported earlier, so it is left alone." in o["legend"])
    check("...Show files lists the files left alone, a copy naming the file it copies", "Old listing A.xlsx" in o["left"] and "· a copy of PV Listing Example.xlsx" in o["left"] and "Hide files" in o["left"])
    check("...Take it for asks once more before it takes the printed name", o["take"] == 'Click again: "EXAMPLE PRINTED NAME SDN BHD" is EXQ', o["take"])
    check("the preview: its title in words, Preview: nothing is saved yet, the account lines it would keep",
          "SQL exports fetched 18 Nov 2026, 10:42" in F and "Preview: nothing is saved yet" in F and "Account lines" in F and "4 new</b>" in F
          and "1 journal will count in the bank reconciliation" in F)
    check("...after a fetch the Fetch button is the secondary one, Fetch again; the result takes the focus",
          "Fetch again" in o["fetchBtn"] and o["arriveFocus"] == "sqlPreview")
    check("a fetch closes the folder box left open, and Use another folder says it is closed",
          'id="sqlDir"' not in o["fetchCard"] and 'data-sq-folder="1" aria-expanded="false"' in o["fetchCard"] and "Typed but not saved" not in o["fetchCard"])
    S = o["paste"]
    check("a pasted listing's preview: its title in words, the entries found, Check the columns",
          re.search(r"SQL listing pasted \d{1,2} \w{3} \d{4}, \d\d:\d\d", S) is not None and "4 entries found" in S and "Check the columns were read correctly" in S)
    check("...a supplier's documents are named as such, a customer's as a customer invoice (the fix of section 4.1)",
          "Supplier invoice, kept on file" in S and "Supplier debit note, kept on file" in S and "Customer invoice, kept on file" in S)
    check("...a voucher with no payment says it will wait, and the import note counts it",
          "No payment yet. It will wait under entries not linked." in S and 'aria-label="Payment that PV2610-213 records"' in S
          and "1 new document has no payment yet. Import anyway: it waits under SQL entries not linked to a payment." in S)
    check("...a payment picked: the note and the Import button follow", o["note1"] == "Every new voucher is linked to a payment." and o["apply1"] == "Import 4 entries (1 linked)", (o["note1"], o["apply1"]))
    check("...Columns read is folded until opened, then the columns can be picked",
          'data-sq-cols="1" aria-expanded="false"' in S and "data-sql-map" not in S and "data-sql-map" in o["cols"] and "Changing a column reads the rows again; payments you picked stay." in S)
    check("nothing new, with files not used: why, and the ways on",
          "Nothing new to import" in o["nothing"] and "6 files were not used: see why below. Nothing was changed." in o["nothing"]
          and "Paste a listing instead" in o["nothing"] and 'data-sq-folder-fix="1">Use another folder</button>' in o["nothing"] and 'id="sqlCancel">Close</button>' in o["nothing"])
    check("nothing new, with no file at all: export and save it, then fetch again",
          "In SQL Account, export the listing and save it in SQL Drive, in the Download folder, then fetch again." in o["empty"])
    check("journal lines pasted as text: which journal, the note, Keep",
          "These are a journal's lines, pasted as text." in o["jlOk"] and "Which journal are these lines from?" in o["jlOk"] and "Keep 4 journal lines" in o["jlOk"]
          and re.search(r'id="sqlApply" >', o["jlOk"]) is not None)
    check("...lines that don't balance are refused in place, and Keep can't be pressed",
          'role="alert"' in o["jlBad"] and "These lines don&#39;t balance" in o["jlBad"] and re.search(r'id="sqlApply" disabled>', o["jlBad"]) is not None)
    check("SQL's reports only: no listing entries, Keep account lines, nothing matched",
          "SQL&#39;s general-ledger reports" in o["reports"] and "No new listing entries" in o["reports"] and "Keep account lines" in o["reports"]
          and "Nothing is matched to payments: SQL&#39;s account lines are kept and checked against its reports." in o["reports"])
    check("Cancel takes the preview away", o["cancelled"] == "")
    check("an empty paste is refused under the box, not in a toast", "Paste the rows copied from SQL first." in o["pasteEmpty"] and 'aria-invalid="true"' in o["pasteEmpty"])
    check("...and a paste into the box takes the error away (a paste sets the box itself, with no input event)", o["pasteErrAfterPaste"] == "", o["pasteErrAfterPaste"])
    check("...and the server's refusal too", "This is a copy of SQL&#39;s MyInvois Transaction screen" in o["pasteBad"] and 'role="alert"' in o["pasteBad"])
    check("the file tab: the box to choose or drop a file", 'id="sql-drop"' in o["fileTab"] and "<b>Choose an SQL export</b> or drop it here" in o["fileTab"]
          and ".xlsx, .xls, .csv, .ods or .txt, exported from SQL Account" in o["fileTab"] and 'aria-selected="true" aria-controls="sql-panel" tabindex="0">' in o["fileTab"])
    check("...the arrow keys move between the two tabs", o["modeAfterKey"] == "paste", o["modeAfterKey"])
    check("...a file that isn't an export is refused in place", "statement-example.pdf: Export the SQL report as Excel (.xlsx or .xls), CSV or ODS." in o["wrongType"])
    check("...one too large is refused", "This file is too large to read (30.0 MB; at most 25 MB). Export a shorter period from SQL Account." in o["tooBig"])
    check("...two files dropped at once are refused", "Drop one file at a time." in o["two"])
    check("...a file dragged over the box shows it will take it; one dropped is chosen", o["drag"] is True and o["dragAfter"] is False and o["chosen"] == "Chosen: listing-example.xlsx")
    check("...a listing the server can't add up is refused under the box, with Paste this listing instead",
          fixture["sum"].replace("'", "&#39;") in o["fileBad"] and "Paste this listing instead</button>" in o["fileBad"])
    D = o["done"]
    check("Import: the result in place of the preview, its sentence complete, the ways on",
          "Imported 4 entries" in D and "1 linked to payments; 1 bank lines matched. 1 linked voucher was changed in SQL: see Changed in SQL." in D
          and 'data-sq-jump="sql-unlinked-h">See entries not linked' in D and 'data-sq-jump="sb-changed-h">See Changed in SQL</button>' in D
          and 'aria-label="Close this message"' in D and o["doneFocus"] == "sqlPreview")
    check("...the third step says Imported, the new entries are marked, the import is Just now",
          '<li class="done">' in D and "<b>Imported</b>" in D and ">Just imported</span>" in D and "Just now" in D)
    check("...closing it takes it away", o["doneClosed"] == "")
    check("keeping SQL's reports: the account lines kept, the sentence finished (no more \"of SQL's.\")",
          "Kept the account lines</b>" in o["doneReports"] and "Kept the account lines of 5 documents from 2 reports of SQL&#39;s general ledger; 2 differences from SQL&#39;s reports, listed under Checks against SQL&#39;s reports." in o["doneReports"]
          and "See Checks against SQL's reports" in o["doneReports"])
    check("keeping journal lines: how many, and the journal they are kept with", "Kept 4 journal lines" in o["doneLines"] and "They are kept with JV2610-207." in o["doneLines"]
          and "See the journal" in o["doneLines"])
    check("a company kept here at the SQL import address: the card says why, with a way to a company kept in SQL",
          "SQL import isn&#39;t used for EXH" in o["here"] and "Example Here Ltd is kept here, so there is nothing to import from SQL Account." in o["here"]
          and "Go to EXQ" in o["here"], o["here"][:600])

# ---------- the source ----------
sql_js = (ROOT / "static" / "js" / "pages" / "sql.js").read_text(encoding="utf-8")
js = app_source()
check("no company code is written into the SQL page", not re.search(r'"(AISB|AIL|AIP|AI)"', sql_js))
check("no bank's name is written into it", not [b for b in ("Maybank", "CIMB", "Public Bank", "RHB", "Hong Leong", "AmBank", "UOB", "OCBC", "HSBC") if b in sql_js.replace("Method Maybank", "")])
check("the old raw section key and the unfinished import sentence are gone",
      "<td>${esc(x.book)}</td>" not in js and 'report")} of SQL\'s${diffs' not in js)
check("the checks keep their stale trial balance note", 'kind === "trial_balance" && b.stale && warns.length' in js)
check("the SQL page uses the shared list helpers", 'sortTh("sql"' in sql_js and 'listBar("sql"' in sql_js)
check("the toggle listener of the old <details> lists is gone (nothing draws data-sql-open)", "sqlOpen[k] = ev.target.open" not in js and "data-sql-open" not in js)

shutil.rmtree(tmp, ignore_errors=True)
if failures:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    raise SystemExit(1)
print("\nsql_page_test: all passed")
