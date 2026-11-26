"""Bank and reconciliation's page (slice 4, pages/bank.js), run in Node on a stand-in page (no browser), on made-up records.

The server's own answers for a made-up company are fed to the page script, which draws: the year table with a locked
month (Locked, Reopen month, the sign-off note, the signed statement to file; no Undo sign-off); a month open for
sign-off (the optional note, Prepared by, Mark reconciled, Not ready); the review of the locked month (the locked
banner, a line linked to 3 payments, the No money moved pair, the "best done on a computer" note) and of the open month;
the Reopen month dialog (a reason is required and nothing is sent without one; with one, the reopen is sent); and the
Explain dialog choosing several payments for one line (a running total, "Link 2 payments", sent as payment_ids).

Run: .venv\\Scripts\\python -m synthetic_tests.bank_rec_page_test
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-bank-rec-page-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXW", "name": "Example Web Page Sdn Bhd", "accounts": [{"label": "Operating", "bank": "Example Bank", "number": "0000-1357"}]},
]}), encoding="utf-8")
failures = []


def check(name, ok, detail=""):
    if not ok:
        failures.append(name)
        print(f"FAIL {name}" + (f"\n     {str(detail)[:600]}" if detail else ""))
    else:
        print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXW'")[0]["id"]
AID = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
NOW = db.now()
con = db.connect()
con.arm("user", "test: a made-up company with an October and a November statement")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (EID,))


def pay(desc, amount, month, paid, direction="out"):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                          direction, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (EID, month, AID, "receipt" if direction == "in" else "other", desc, amount, (paid or month + "-05"), paid,
                        "manual" if paid else None, direction, NOW)).lastrowid


def statement(month, opening, lines):
    sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, ?, ?, ?, ?, 1)",
                      (AID, month, opening, round(opening + sum(x[2] for x in lines), 2), NOW)).lastrowid
    bal, ids = opening, []
    for n, (day, desc, amt, status, note) in enumerate(lines, 1):
        bal = round(bal + amt, 2)
        ids.append(con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, status, note)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (sid, n, day, desc, amt, bal, status, note)).lastrowid)
    return sid, ids


A1, A2, A3 = (pay(f"Test Payee {n} wages", amt, "2026-10", "2026-10-05") for n, amt in (("Alpha", 1000), ("Beta", 1500), ("Gamma", 500)))
pay("Test refund out", 200, "2026-10", "2026-10-12")
pay("Test refund back", 200, "2026-10", "2026-10-12", "in")
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 10000, ?)", (AID, NOW))
S_OCT, (L_BULK, _) = statement("2026-10", 10000, [("2026-10-05", "PAYROLL BULK 3 ITEMS", -3000, "unmatched", None),
                                                  ("2026-10-31", "SERVICE CHARGE", -10, "no_docs", "Bank charge")])
N1 = pay("Test Payee Delta fees", 400, "2026-11", None)
N2 = pay("Test Payee Epsilon fees", 250, "2026-11", None)
S_NOV, (L_NOV,) = statement("2026-11", 6990, [("2026-11-06", "IBG DR BULK 2 ITEMS", -650, "unmatched", None)])
con.commit()
con.close()
j("post", f"/api/statement-lines/{L_BULK}", json={"payment_ids": [A1, A2, A3]})
j("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": S_OCT})
key = j("get", f"/api/recon/month?entity_id={EID}&account_id={AID}&month=2026-10")["pairs"][0]["key"]
j("post", "/api/recon/pair", json={"entity_id": EID, "account_id": AID, "month": "2026-10", "key": key, "reason": "Refund sent and returned the same day"})
j("post", "/api/recon/sign-off", json={"entity_id": EID, "statement_id": S_OCT, "note": "Test free note", "prepared_by": "Test Preparer"})

fx = {"entity": EID, "account": AID, "oct": S_OCT, "nov": S_NOV, "nov_line": L_NOV, "n1": N1, "n2": N2,
      "meta": j("get", "/api/meta"),
      "year": j("get", f"/api/recon/year?entity_id={EID}&account_id={AID}"),
      "month": {m: j("get", f"/api/recon/month?entity_id={EID}&account_id={AID}&month={m}") for m in ("2026-10", "2026-11")},
      "review": {str(s): j("get", f"/api/recon/review?entity_id={EID}&statement_id={s}") for s in (S_OCT, S_NOV)},
      "print": j("post", "/api/recon/print", json={"entity_id": EID, "account_id": AID, "month": "2026-11"})}
(tmp / "fixture.json").write_text(json.dumps(fx), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, posts = [], listeners = {}, sel = {}, stored = {};
let watch = null, busyAtPost = null;
const HELD = [{ doc_no: "PV2609-901", why: "Operating September 2026 is marked reconciled and locked, so it can't change" },
              { doc_no: "PV2609-902", why: "Operating September 2026 is marked reconciled and locked, so it can't change" }];  // the button whose state is noted when its request goes out
const fake = (props = {}) => ({ innerHTML: "", value: "", checked: false, hidden: false, textContent: "", dataset: {}, attrs: {}, isConnected: true,
  disabled: false, classList: { add() {}, remove() {} }, setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; },
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, focus() { document.activeElement = this; }, querySelector: () => null,
  querySelectorAll: () => [], scrollIntoView() {}, contains: () => false, matches: () => false,
  closest(s) { return /button/.test(s) ? this : null; }, ...props });
const el = id => els[id] ||= fake({ id, hidden: id === "drawer" });
const document = { activeElement: null, querySelectorAll: () => [], getElementById: id => els[id] || null,
  querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : sel[s] || null,
  addEventListener(t, f) { (listeners[t] ||= []).push(f); } };
// An event sent through every listener the page script registered, as the browser would.
const fire = async (type, target) => { const ev = { type, target, button: 0, key: "", preventDefault() {}, stopPropagation() {} };
  for (const f of listeners[type] || []) await f(ev); await new Promise(r => setTimeout(r, 20)); };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") {
    posts.push([init.method, path, init.body && typeof init.body === "string" ? JSON.parse(init.body) : null]);
    if (watch) busyAtPost = watch.disabled && watch.attrs["aria-busy"] === "true";
    const body = path === "/api/recon/print" ? fx.print : path === "/api/sql/entries/create-all"
      ? { created: 1, linked: 0, left: 0, corrections: [], bank_lines_matched: 0, held: HELD } : { ok: true };
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(body)) };
  }
  const u = new URL("http://x" + path), p = u.pathname, a = u.searchParams;
  const r = p === "/api/meta" ? fx.meta : p === "/api/recon/year" ? fx.year : p === "/api/recon/month" ? fx.month[a.get("month")]
    : p === "/api/recon/review" ? fx.review[a.get("statement_id")] : undefined;
  if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: "not stubbed: " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
const ctx = vm.createContext({ document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, URL,
  localStorage: { getItem: k => k in stored ? stored[k] : k === "hrp-prepared-by" ? "Test Saved Name" : null, setItem(k, v) { stored[k] = v; } }, window: {} });
const run = code => vm.runInContext(code, ctx);
const out = {};
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  await new Promise(r => setTimeout(r, 60));  // the app's own start (main.js) draws its first page: it is over before the checks draw theirs
  run(`state.meta = ${JSON.stringify(fx.meta)}; state.entity = ${fx.entity}; state.view = "bank"; state.month = "2026-11"; state.day = dayKey();`);
  // every toast the page raises, and whether it offered Undo
  run(`var SEEN = []; toast = (m, bad, o) => { SEEN.push({ m, bad: !!bad, undo: !!(o && o.undo) }); return null; }`);
  const toasts = () => JSON.parse(run("JSON.stringify(SEEN.splice(0))"));
  const year = async open => { run(`state.recon = { entity: ${fx.entity}, account: ${fx.account}, year: null, open: ${JSON.stringify(open)}, panel: null, rv: null, print: null }`);
    await run(`viewBank(document.querySelector("#main"))`); return { main: el("main").innerHTML, list: el("stmtList").innerHTML }; };
  out.oct = await year("2026-10");
  out.nov = await year("2026-11");
  // the Reopen month dialog, from the October panel
  await year("2026-10");
  run(`reopenDialog(${fx.oct})`); out.dlg = el("drawer").innerHTML; out.dlgHidden = el("drawer").hidden;
  const go = el("bk-dlg-go"); go.dataset = { sid: String(fx.oct) }; go.textContent = "Reopen month";
  el("bk-why").value = "   "; posts.length = 0;
  await run(`reopenGo(document.querySelector("#bk-dlg-go"))`);
  out.noReason = { err: el("bk-why-err").textContent, posts: posts.length, invalid: el("bk-why").attrs["aria-invalid"] };
  el("bk-why").value = "Test: the service charge is to be checked";
  await run(`reopenGo(document.querySelector("#bk-dlg-go"))`);
  out.reopenPosts = posts.slice(); out.reopenToasts = toasts();
  // Cancel in the dialog, through the page's own click listener
  run(`reopenDialog(${fx.oct})`); el("bk-why").value = ""; await fire("click", fake({ id: "bk-dlg-cancel" })); out.cancelHidden = el("drawer").hidden;
  // Mark reconciled on November, through the click listener: the note and the name typed go with it, the name is kept
  await year("2026-11"); posts.length = 0; toasts();
  sel[`[data-rc-free="${fx.nov}"]`] = fake({ value: "  Test typed note  " }); sel[`[data-rc-by="${fx.nov}"]`] = fake({ value: "Test Typed Name" });
  const signBtn = fake({ dataset: { rcSign: String(fx.nov) } });
  watch = signBtn; await fire("click", signBtn); out.signBusy = busyAtPost; watch = null;
  out.sign = { posts: posts.filter(p => p[1] === "/api/recon/sign-off"), stored: stored["hrp-prepared-by"], toasts: toasts(), enabled: !signBtn.disabled };
  // Reconciled before tracking, through the click listener (the month's name from the month shown)
  posts.length = 0;
  sel[`[data-rc-before-tick="${fx.nov}"]`] = fake({ checked: true }); sel[`[data-rc-note="${fx.nov}"]`] = fake({ value: "Reconciled in the old books" });
  sel[`[data-rc-by="${fx.nov}"]`] = fake({ value: "Test Before Name" });
  await fire("click", fake({ dataset: { rcBefore: String(fx.nov) } }));
  out.before = { posts: posts.filter(p => p[1] === "/api/recon/before-tracking"), toasts: toasts(), stored: stored["hrp-prepared-by"] };
  // Print, through the click listener: the name typed under Prepared by goes with it; Back leaves the preview
  await year("2026-11"); posts.length = 0; sel[`[data-rc-by="${fx.nov}"]`] = fake({ value: "Test Printing Name" });
  await fire("click", fake({ dataset: { rcPrint: "2026-11" } }));
  out.print = { posts: posts.filter(p => p[1] === "/api/recon/print"), html: el("stmtList").innerHTML, kept: run("!!state.recon.print") };
  await fire("click", fake({ dataset: { rcPrintBack: "1" } })); out.printBack = run("state.recon.print");
  run(`state.recon.print = { month: "2026-11", ...${JSON.stringify(fx.print)} }`);
  await run(`viewBank(document.querySelector("#main"))`); out.printAfterReturn = { kept: run("state.recon.print"), list: el("stmtList").innerHTML };
  // A No money moved pair ticked, through the change listener, with the reason typed
  await run(`openReview(${fx.oct}, false)`); run(`state.recon.rv.d.summary.locked = false; state.recon.rv.d.summary.pairs[0].confirmed_at = null`);
  posts.length = 0; toasts();
  const box = fake({ querySelector: s => s === "[data-pair-why]" ? fake({ value: "Test typed reason" }) : s === '[role="alert"]' ? fake() : null });
  await fire("change", fake({ checked: true, dataset: { pairTick: run("state.recon.rv.d.summary.pairs[0].key") }, closest: s => s === ".bk-pair" ? box : null }));
  out.pair = { posts: posts.filter(p => p[1] === "/api/recon/pair"), toasts: toasts() };
  // the reviews
  await run(`openReview(${fx.oct}, false)`); out.revOct = el("stmtList").innerHTML; out.barOct = { hidden: el("rvBar").hidden };
  await run(`openReview(${fx.nov}, false)`); out.revNov = el("stmtList").innerHTML;
  // Explain: one line, two payments ticked together
  run(`explainLine(${fx.nov_line})`); out.ex = el("drawer").innerHTML;
  const pick = id => run(`document.querySelector("#ex-list").onclick({ target: { closest: () => ({ dataset: { exPay: "${id}" } }) } })`);
  pick(fx.n1); out.run1 = { run: el("ex-run").innerHTML, label: el("ex-link").textContent };
  pick(fx.n2); out.run2 = { run: el("ex-run").innerHTML, label: el("ex-link").textContent, list: el("ex-list").innerHTML };
  posts.length = 0;
  await run(`document.querySelector("#ex-link").onclick()`); await new Promise(r => setTimeout(r, 30));
  out.linkPosts = posts.slice();
  // the SQL page: Link or create all (its toast) and an import's result, each with entries the lock held back
  toasts(); run(`state.entity = ${fx.entity}; state.view = "sql"`);
  try { await run(`sqAsk("all-yes")`); } catch (e) { /* the page drawn again after it needs routes this stand-in lacks */ }
  out.heldToast = toasts().map(x => x.m);
  out.heldImport = run(`sqDone({ records: [1], filename: "listing.xlsx" }, { added: 3, linked: 1, skipped: 0, held: ${JSON.stringify(HELD)} }).text`);
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
node = shutil.which("node")
if not node:
    print("SKIPPED the page checks: Node.js isn't installed")
    sys.exit(0)
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
res = subprocess.run([node, str(probe), app_bundle(tmp / "app.js"), str(tmp / "fixture.json")], capture_output=True, text=True, encoding="utf-8", timeout=120)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the page script ran", o is not None, res.stderr[-1500:])
if o is None:
    sys.exit(1)

oc = o["oct"]["list"]
check("the page is called Bank and reconciliation and says a signed-off month is locked",
      "<h1>Bank and reconciliation</h1>" in o["oct"]["main"] and "A signed-off month is locked; reopening it needs a reason and the sign-off again." in o["oct"]["main"])
check("the year table marks the locked month Locked, beside Reconciled", "Locked</span>" in oc and "Reconciled" in oc)
check("the locked month's panel offers Reopen month, never Undo sign-off",
      f'data-rc-reopen="{S_OCT}"' in oc and "Reopen month" in oc and "data-rc-undo" not in oc and "Undo sign-off" not in oc)
check("...says what the lock means", "its lines, matches and book opening can't change, and nothing can be posted into it. Reopen the month to change anything." in oc)
check("...shows the sign-off note the app wrote, the free note and Prepared by",
      "Sign-off note, as kept" in oc and "No money moved: " in oc and "Explained without documents: " in oc and "Note: Test free note" in oc
      and "Prepared by Test Preparer (declared)" in oc)
check("...offers to print the statement and the month's Excel", 'data-rc-print="2026-10"' in oc and "Print the reconciliation statement" in oc
      and "/api/export/recon.xlsx?" in oc)
check("...and has no Mark reconciled", "Mark reconciled" not in oc)
nv = o["nov"]["list"]
check("an open month asks for the optional note and Prepared by (the name kept on this computer), with Mark reconciled and why not",
      "Note for the sign-off" in nv and "Optional" in nv and 'value="Test Saved Name"' in nv and "Mark reconciled" in nv
      and "Not ready: 1 line to explain" in nv and "The app writes the rest of the note itself at sign-off" in nv)
check("the Reopen month dialog asks for a reason, in the board's words",
      "Reopen October 2026 for Operating?" in o["dlg"] and "Why are you reopening this month?" in o["dlg"] and "Required" in o["dlg"]
      and "The reopen and its reason are kept in the audit trail." in o["dlg"] and not o["dlgHidden"])
check("no reason: refused on the page, nothing sent", o["noReason"]["err"] == "Say why you're reopening this month." and o["noReason"]["posts"] == 0
      and o["noReason"]["invalid"] == "true", o["noReason"])
rp = [p for p in o["reopenPosts"] if p[1] == "/api/recon/reopen"]
check("with a reason, the reopen is sent with it", rp and rp[0][2] == {"entity_id": EID, "statement_id": S_OCT, "reason": "Test: the service charge is to be checked"},
      o["reopenPosts"])
check("the reopen's toast says it needs the sign-off again, with no Undo (signing off again is its own step)",
      o["reopenToasts"] == [{"m": "October 2026 reopened for Operating. It needs the sign-off again.", "bad": False, "undo": False}], o["reopenToasts"])
check("Cancel in the Reopen month dialog closes it (the page's click listener)", o["cancelHidden"] is True)
check("Mark reconciled sends the note and the name typed (trimmed), through the page's click listener",
      o["sign"]["posts"] == [["POST", "/api/recon/sign-off", {"entity_id": EID, "statement_id": S_NOV, "note": "Test typed note", "prepared_by": "Test Typed Name"}]],
      o["sign"]["posts"])
check("...keeps the name on this computer for next time", o["sign"]["stored"] == "Test Typed Name", o["sign"]["stored"])
check("...says the month is locked, with no Undo (a signed-off month is reopened with a reason)",
      o["sign"]["toasts"] == [{"m": "Marked as reconciled. November 2026 is locked for Operating.", "bad": False, "undo": False}], o["sign"]["toasts"])
check("...and the button is off while it runs, then on again", o["signBusy"] is True and o["sign"]["enabled"] is True)
check("Reconciled before tracking sends the tick, the note and Prepared by",
      o["before"]["posts"] == [["POST", "/api/recon/before-tracking", {"entity_id": EID, "statement_id": S_NOV, "checked": True,
                                                                         "note": "Reconciled in the old books", "prepared_by": "Test Before Name"}]], o["before"])
check("...and names the month shown in its toast", o["before"]["toasts"] and o["before"]["toasts"][0]["m"]
      == "Marked as reconciled before tracking. November 2026 is locked.", o["before"]["toasts"])
check("Print sends the name typed under Prepared by and shows the preview with the code and check",
      o["print"]["posts"] and o["print"]["posts"][0][2]["printed_by"] == "Test Printing Name" and o["print"]["kept"]
      and fx["print"]["preview"]["code"] in o["print"]["html"] and f"Check: {fx['print']['preview']['check']}" in o["print"]["html"], o["print"]["posts"])
check("...Back to the year leaves it", o["printBack"] is None)
check("...and coming back to the page shows the month as it stands, not an old preview",
      o["printAfterReturn"]["kept"] is None and "Bank reconciliation statement" not in o["printAfterReturn"]["list"])
check("ticking a No money moved pair sends its key and the reason typed, through the page's change listener",
      o["pair"]["posts"] and o["pair"]["posts"][0][2]["reason"] == "Test typed reason" and o["pair"]["posts"][0][2]["confirmed"] is True
      and o["pair"]["toasts"][0]["m"].startswith("Pair confirmed: "), o["pair"])
ro = o["revOct"]
check("the locked month's review says it is locked, with Reopen month, and has no Apply bar",
      "October 2026 is marked reconciled and locked." in ro and "Its lines can't be linked, explained, confirmed or undone." in ro
      and o["barOct"]["hidden"] is True)
check("...the bulk line shows as linked to 3 payments, with each one's part", "Linked to 3 payments" in ro and "RM 3,000.00 together" in ro
      and "Test Payee Beta wages · 1,500.00" in ro)
check("...its lines carry no Undo", 'data-unlink=' not in ro)
pairs_html = ro[ro.find('<div class="bk-pairs">'):ro.find('<div class="rv-bar')]
check("...the No money moved group shows the pair, net nil and confirmed, its reason read only",
      pairs_html.startswith('<div class="bk-pairs">') and "<h3>No money moved · 1 pair</h3>" in pairs_html
      and '<span class="pill ok">All confirmed</span>' in pairs_html and "Net nil" in pairs_html
      and 'value="Refund sent and returned the same day" readonly' in pairs_html and "Confirmed: no money moved" in pairs_html, pairs_html[:400])
check("...in the board's words", "Book entries that cancel each other out and never touched the bank" in pairs_html
      and "The sign-off waits until every pair is confirmed and nil." in pairs_html)
check("the review shows the 'best done on a computer' note for narrow screens", "Best done on a computer" in ro and "desk-note" in ro)
rn = o["revNov"]
check("the open month's review has the Apply bar's place and More options", 'id="rvBar"' in rn and "More options" in rn and "is marked reconciled and locked" not in rn)
check("the Explain dialog links one payment or several, with the board's words",
      "Link to existing payments" in o["ex"] and "or several paid together under one bank reference" in o["ex"] and 'aria-multiselectable="true"' in o["ex"])
check("one payment ticked: the running total says how far it is from the line", "1 selected" in o["run1"]["run"] and "RM 250.00 short" in o["run1"]["run"]
      and o["run1"]["label"] == "Link 1 payment", o["run1"])
check("two ticked: they add up, and the button says Link 2 payments", "2 selected" in o["run2"]["run"] and "Adds up" in o["run2"]["run"]
      and o["run2"]["label"] == "Link 2 payments" and o["run2"]["list"].count('aria-selected="true"') == 2, o["run2"])
lp = [p for p in o["linkPosts"] if p[1] == f"/api/statement-lines/{L_NOV}"]
check("...and linking sends both payments for the one line", lp and lp[0][2] == {"payment_ids": [N1, N2]}, o["linkPosts"])

check("Link or create all says which entries the lock kept from being linked, and why",
      any(m.endswith("; 0 bank lines matched. 2 entries were not linked: Operating September 2026 is marked reconciled and locked") for m in o["heldToast"]), o["heldToast"])
check("...and so does an import's result", o["heldImport"].endswith(". 2 entries were not linked: Operating September 2026 is marked reconciled and locked."), o["heldImport"])

if failures:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("\nAll Bank and reconciliation page checks passed.")
