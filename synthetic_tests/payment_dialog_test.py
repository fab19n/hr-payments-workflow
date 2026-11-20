"""The payment dialog's server checks (slice 3), on made-up records only.

1. Moving a payment to another bank account rechecks the reconciliation of both accounts: its bank line on the old
   account's statement is taken off it (left to explain, its confirmation gone) and that statement's sign-off goes; the
   new account's statement is looked at for its line, and that statement's sign-off goes too. A third account, and a
   save that leaves the account as it was, change nothing. Moved back, its old line is linked again with its paid date.
   An account in another currency is accepted, rechecking both; taking the account off frees only the old
   account's lines and rechecks it. A payment with no account is rechecked in
   the books of the company's one account in its currency; a line already linked on the new account keeps its
   confirmation.
2. The document viewer shows only a PDF or an image inline: any other file is served as a download, even when it is
   asked for inline.
3. The month's payments say when a linked SQL voucher was edited in SQL since (the dialog's note), in the SQL import
   page's words; a payment whose voucher is unchanged says nothing.

Made-up company EXP (kept here, not in SQL) with three ringgit accounts, Alpha, Beta and Gamma, and October 2026
statements on each, all signed off; made-up company EXQ (kept in SQL Account) with two linked vouchers, one of them
fetched again from SQL at another amount.

Run: .venv\\Scripts\\python -m synthetic_tests.payment_dialog_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-payment-dialog-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXP", "name": "Example Payments Sdn Bhd", "accounts": [{"label": "Alpha", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXQ", "name": "Example Vouchers Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-444"}]},
    {"code": "EXR", "name": "Example Rent Sdn Bhd", "accounts": [{"label": "Only", "bank": "Example Bank", "number": "000-666"}]},
]}), encoding="utf-8")


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r


EID = q("SELECT id FROM entities WHERE code = 'EXP'")[0]["id"]
A = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]

con = db.connect()
con.arm("user", "test: a made-up company, accounts, payments and statements")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (EID,))
B = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, 'Beta', 'Example Bank', '000-222', 'MYR')", (EID,)).lastrowid
G = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, 'Gamma', 'Example Bank', '000-333', 'MYR')", (EID,)).lastrowid
NOW = db.now()


def pay(desc, amount, acct, paid=None):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date,
                          paid_source, direction, created_at) VALUES (?, '2026-10', ?, 'other', ?, ?, '2026-10-20', ?, ?, 'out', ?)""",
                       (EID, acct, desc, amount, paid, "bank" if paid else None, NOW)).lastrowid


def statement(acct, lines):
    sid = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                         VALUES (?, '2026-10', 5000, ?, ?, 1, ?, 'review')""",
                      (acct, round(5000 + sum(x[2] for x in lines), 2), NOW, NOW)).lastrowid
    bal = 5000
    ids = []
    for n, (day, desc, amt, pid, status, conf) in enumerate(lines, 1):
        bal = round(bal + amt, 2)
        ids.append(con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id,
                                  status, confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (sid, n, day, desc, amt, bal, pid, status, conf)).lastrowid)
    return sid, ids


P = pay("Test Payee A printing", 420.0, A, "2026-10-19")
OTHER = pay("Test Payee B cleaning", 300.0, G, "2026-10-12")
S_A, (L_A,) = statement(A, [("2026-10-19", "IBG DR TEST PAYEE A PRINTING", -420.0, P, "matched", NOW)])
S_B, (L_B,) = statement(B, [("2026-10-21", "IBG DR TEST PAYEE A PRINTING", -420.0, None, "unmatched", None)])
S_G, (L_G,) = statement(G, [("2026-10-12", "IBG DR TEST PAYEE B CLEANING", -300.0, OTHER, "matched", NOW)])
con.commit()
con.close()

signed = lambda sid: bool(q("SELECT reconciled_at FROM statements WHERE id = ?", (sid,))[0]["reconciled_at"])
line = lambda lid: q("SELECT * FROM statement_lines WHERE id = ?", (lid,))[0]

# A save that names the same account changes nothing.
call("patch", f"/api/payments/{P}", json={"account_id": A, "notes": "same account"})
check("a save that keeps the account leaves both reconciliations signed off", signed(S_A) and signed(S_B) and signed(S_G))
check("... and the bank line stays linked and confirmed", line(L_A)["payment_id"] == P and line(L_A)["confirmed_at"])

# Moving it from Alpha to Beta.
call("patch", f"/api/payments/{P}", json={"account_id": B})
check("the payment is on Beta now", q("SELECT account_id FROM payments WHERE id = ?", (P,))[0]["account_id"] == B)
la = line(L_A)
check("its line on Alpha's statement is taken off it and left to explain",
      la["payment_id"] is None and la["status"] == "unmatched" and la["confirmed_at"] is None, la)
check("...not marked as undone by a person, so moving the payment back can find it again", la["undone_payment_id"] is None, la)
check("Alpha's October sign-off goes: its reconciliation is checked again", not signed(S_A))
lb = line(L_B)
check("Beta's statement is looked at: its line is linked to the payment", lb["payment_id"] == P and lb["status"] == "matched", lb)
check("Beta's October sign-off goes too: its reconciliation is checked again", not signed(S_B))
check("the paid date follows Beta's line", q("SELECT paid_date FROM payments WHERE id = ?", (P,))[0]["paid_date"] == "2026-10-21")
check("Gamma, not involved, keeps its sign-off", signed(S_G) and line(L_G)["confirmed_at"])
log = [r["what"] for r in q("SELECT what FROM activity ORDER BY id")]
check("the activity log says both sign-offs were removed",
      any("Alpha October 2026" in a and "sign-off" in a for a in log) and any("Beta October 2026" in a and "sign-off" in a for a in log), log[-6:])

# Moved back from Beta to Alpha: its Alpha line is linked again and the paid date is the line's again.
call("patch", f"/api/payments/{P}", json={"account_id": A})
pa = q("SELECT paid_date, paid_source FROM payments WHERE id = ?", (P,))[0]
check("moved back, its line on Alpha is linked to it again", line(L_A)["payment_id"] == P and line(L_A)["status"] == "matched", line(L_A))
check("...and the paid date is the Alpha line's again", pa == {"paid_date": "2026-10-19", "paid_source": "bank"}, pa)
check("...and its Beta line is left to explain", line(L_B)["payment_id"] is None, line(L_B))

# A payment can be moved to an account in another currency (a ringgit bill
# paid from a foreign currency account), keeping its own currency, and both accounts are checked again.
con = db.connect()
con.arm("user", "test: a made-up dollar account and its October statement")
USD = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, 'Delta', 'Example Bank', '000-555', 'USD')", (EID,)).lastrowid
S_D = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                     VALUES (?, '2026-10', 100, 100, ?, 1, ?, 'review')""", (USD, NOW, NOW)).lastrowid
con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id = ?", (NOW, S_A))
con.commit()
con.close()
call("patch", f"/api/payments/{P}", json={"account_id": USD})
pd_ = q("SELECT account_id, currency FROM payments WHERE id = ?", (P,))[0]
check("a ringgit payment moved to the company's dollar account is accepted, and stays a ringgit payment",
      pd_ == {"account_id": USD, "currency": "MYR"}, pd_)
check("...and both accounts' October reconciliations are checked again", not signed(S_A) and not signed(S_D), (signed(S_A), signed(S_D)))

# A payment taken off its bank account (account 0 or blank): accepted; only its lines on the old account's statements
# are freed (not marked as undone by a person), a line on another account's statement linked to another payment stays,
# and the old account's month is checked again.
con = db.connect()
con.arm("user", "test: a made-up payment to take off its account")
PT = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                    direction, created_at) VALUES (?, '2026-10', ?, 'other', 'Test Payee L courier', 55, '2026-10-14', '2026-10-14', 'bank', 'out', ?)""",
                 (EID, A, NOW)).lastrowid
L_T = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
                     VALUES (?, 9, '2026-10-14', 'TEST PAYEE L COURIER', -55, 4525, ?, 'matched', ?)""", (S_A, PT, NOW)).lastrowid
L_TB = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status)
                      VALUES (?, 9, '2026-10-15', 'TEST PAYEE L COURIER FEE', -5, 4995, ?, 'matched')""", (S_B, PT)).lastrowid
con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id IN (?, ?)", (NOW, S_A, S_G))
con.commit()
con.close()
call("patch", f"/api/payments/{PT}", json={"account_id": 0})
check("a payment can be taken off its bank account (account 0)", q("SELECT account_id FROM payments WHERE id = ?", (PT,))[0]["account_id"] is None)
lt = line(L_T)
check("...its line on the old account's statement is freed, not marked as undone by a person",
      lt["payment_id"] is None and lt["status"] == "unmatched" and lt["undone_payment_id"] is None, lt)
check("...a line on another account's statement, linked to another payment, is untouched",
      line(L_G)["payment_id"] == OTHER and line(L_G)["confirmed_at"] and signed(S_G), (line(L_G), signed(S_G)))
check("...and the old account's month is checked again", not signed(S_A))
check("...its line on a statement of an account it isn't on stays linked: only the old account's lines are freed",
      line(L_TB)["payment_id"] == PT, line(L_TB))
call("patch", f"/api/payments/{P}", json={"account_id": ""})
check("a blank account takes it off too", q("SELECT account_id FROM payments WHERE id = ?", (P,))[0]["account_id"] is None)

# The old account is checked again on its own: a payment with no bank line (its paid date typed in) moved from Alpha to
# Beta frees no line, yet Alpha's month loses its sign-off (its books no longer count the payment).
con = db.connect()
con.arm("user", "test: a made-up payment paid by hand")
PM = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                    direction, created_at) VALUES (?, '2026-10', ?, 'other', 'Test Payee J fees', 75, '2026-10-12', '2026-10-12', 'manual', 'out', ?)""",
                 (EID, A, NOW)).lastrowid
con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id = ?", (NOW, S_A))
con.commit()
con.close()
call("patch", f"/api/payments/{PM}", json={"account_id": B})
check("a payment with no bank line moved off Alpha: Alpha's month is checked again on its own", not signed(S_A))

# EXR: a payment with no account counts in the books of the company's one ringgit account, Only (the books' rule: a
# company with exactly one account in that currency). Put on Only, Only's month is checked again; a line already linked
# on Only keeps its confirmation (only lines the move links are changed). Once the company has a second ringgit account,
# no book counts a payment with no account, so moving one has nothing to check again on the old side.
RID = q("SELECT id FROM entities WHERE code = 'EXR'")[0]["id"]
ONLY = q("SELECT id FROM accounts WHERE entity_id = ?", (RID,))[0]["id"]
con = db.connect()
con.arm("user", "test: made-up payments with no account")


def no_acct_pay(desc, paid):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                          direction, created_at) VALUES (?, '2026-10', NULL, 'other', ?, 900, ?, ?, 'manual', 'out', ?)""",
                       (RID, desc, paid, paid, NOW)).lastrowid


PN = no_acct_pay("Test Payee E rent", "2026-10-08")
S_ONLY = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                        VALUES (?, '2026-10', 1000, 1000, ?, 1, ?, 'review')""", (ONLY, NOW, NOW)).lastrowid
S_NOV = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                       VALUES (?, '2026-11', 2000, 1100, ?, 1, ?, 'review')""", (ONLY, NOW, NOW)).lastrowid
L_NOV = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
                       VALUES (?, 1, '2026-11-02', 'TEST PAYEE E RENT', -900, 1100, ?, 'matched', ?)""", (S_NOV, PN, NOW)).lastrowid
con.commit()
con.close()
call("patch", f"/api/payments/{PN}", json={"account_id": ONLY})
check("a payment with no account put on the company's one account: that account's month is checked again", not signed(S_ONLY))
check("a line already linked on the new account keeps its confirmation and its statement's sign-off",
      line(L_NOV)["confirmed_at"] and signed(S_NOV), (line(L_NOV), signed(S_NOV)))
con = db.connect()
con.arm("user", "test: a second made-up ringgit account")
SECOND = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, 'Second', 'Example Bank', '000-777', 'MYR')", (RID,)).lastrowid
con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id = ?", (NOW, S_ONLY))
PN2 = no_acct_pay("Test Payee F rates", "2026-10-09")
con.commit()
con.close()
call("patch", f"/api/payments/{PN2}", json={"account_id": SECOND})
check("with two ringgit accounts no book counted a payment with no account: moving one leaves Only's sign-off", signed(S_ONLY))

# A line freed by a move, on a statement signed off before tracking: that sign-off stays (its books are not reviewed here).
con = db.connect()
con.arm("user", "test: a made-up month signed off before tracking")
PBT = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                     direction, created_at) VALUES (?, '2026-09', ?, 'other', 'Test Payee G repairs', 150, '2026-09-10', '2026-09-10', 'bank', 'out', ?)""",
                  (EID, G, NOW)).lastrowid
S_GSEP = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how, reconciled_note)
                        VALUES (?, '2026-09', 5150, 5000, ?, 1, ?, 'before tracking', 'reconciled before this app')""", (G, NOW, NOW)).lastrowid
L_GSEP = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
                        VALUES (?, 1, '2026-09-10', 'TEST PAYEE G REPAIRS', -150, 5000, ?, 'matched', ?)""", (S_GSEP, PBT, NOW)).lastrowid
con.commit()
con.close()
call("patch", f"/api/payments/{PBT}", json={"account_id": B})
check("a line freed by a move on a month signed off before tracking: the line goes, the sign-off stays",
      line(L_GSEP)["payment_id"] is None and signed(S_GSEP), (line(L_GSEP), signed(S_GSEP)))

# The document viewer: a PDF and an image inline; anything else only as a download.
FILES = {"bill.pdf": b"%PDF-1.4\n% made-up test file\n", "slip.png": b"\x89PNG\r\n\x1a\n made-up", "listing.xml": b"<?xml version='1.0'?><x>made-up</x>",
         "notes.txt": b"made-up notes", "sheet.csv": b"a,b\n1,2\n"}
ids = {}
for name, data in FILES.items():
    r = call("post", "/api/upload", data={"payment_id": str(P), "doc_type": "other", "file": (__import__("io").BytesIO(data), name)},
             content_type="multipart/form-data")
    ids[name] = r.get_json()["id"]


def disp(name, extra=""):
    r = call("get", f"/api/documents/{ids[name]}/file{extra}")
    return r.headers.get("Content-Disposition", ""), r.headers.get("Content-Type", ""), r.headers.get("X-Content-Type-Options", "")


d, t, _ = disp("bill.pdf")
check("a PDF is shown inline, as a PDF", d.startswith("inline") and t.startswith("application/pdf"), (d, t))
d, t, _ = disp("slip.png")
check("an image is shown inline, as an image", d.startswith("inline") and t.startswith("image/png"), (d, t))
csp = call("get", f"/api/documents/{ids['bill.pdf']}/file").headers.get("Content-Security-Policy", "")
check("the viewer may show it beside the dialog: the app's own page may frame a document, and nothing else",
      "frame-ancestors 'self'" in csp and "frame-ancestors 'none'" in call("get", "/").headers.get("Content-Security-Policy", ""), csp)
d, _, _ = disp("bill.pdf", "?download=1")
check("a PDF asked for as a download is a download", d.startswith("attachment"), d)
for name in ("listing.xml", "notes.txt", "sheet.csv"):
    d, t, n = disp(name)
    check(f"{name} is refused inline: it is only a download", d.startswith("attachment") and n == "nosniff", (d, t, n))

# A linked voucher edited in SQL: its newer entry, fetched in a later listing, waits on the SQL import page.
QID = q("SELECT id FROM entities WHERE code = 'EXQ'")[0]["id"]
QA = q("SELECT id FROM accounts WHERE entity_id = ?", (QID,))[0]["id"]
con = db.connect()
con.arm("user", "test: made-up SQL listings")
con.execute("UPDATE entities SET uses_sql = 1, first_month = '2026-09' WHERE id = ?", (QID,))
P_EDIT = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, direction, created_at)
                        VALUES (?, '2026-10', ?, 'other', 'Test Payee C toner', 500, '2026-10-15', 'out', ?)""", (QID, QA, NOW)).lastrowid
P_SAME = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, direction, created_at)
                        VALUES (?, '2026-10', ?, 'other', 'Test Payee D paper', 80, '2026-10-16', 'out', ?)""", (QID, QA, NOW)).lastrowid
imports = [con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, 0, 0)",
                       (QID, f"listing{n}.xlsx", NOW)).lastrowid for n in (1, 2)]
for imp, no, amt, pid, status in [(imports[0], "PV2610-901", 500, P_EDIT, "linked"), (imports[0], "PV2610-902", 80, P_SAME, "linked"),
                                  (imports[1], "PV2610-901", 520, None, "unlinked")]:
    con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
                   payment_id, status) VALUES (?, ?, ?, '2026-10-15', 'Test payee', 'Test payee', ?, 'out', 'PV', 'payment', ?, ?)""",
                (imp, QID, no, amt, pid, status))
con.commit()
con.close()
pays = {p["id"]: p for p in call("get", f"/api/month?entity={QID}&month=2026-10").get_json()["payments"]}
ch = pays[P_EDIT].get("sql_changed")
check("a payment whose linked voucher was edited in SQL says so, in the SQL import page's words",
      ch and ch[0]["doc_no"] == "PV2610-901" and ch[0]["words"] == "from 500.00 to 520.00", ch)
check("...and one whose voucher is unchanged says nothing", pays[P_SAME].get("sql_changed") == [], pays[P_SAME].get("sql_changed"))
check("a company kept here has the list too, empty", all(p["sql_changed"] == [] for p in
                                                         call("get", f"/api/month?entity={EID}&month=2026-10").get_json()["payments"]))

# ---------- the dialogs' page script, in Node on a stand-in page (no browser) ----------
# A number or date the browser can't read is never sent as a blank; an edit clears a refusal shown in the payment dialog
# and in New payment; an untouched New payment, for a company whose only account is stopped, asks nothing on Cancel.
import shutil  # noqa: E402
import subprocess  # noqa: E402
from synthetic_tests.appsource import app_files  # noqa: E402

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const src = process.argv.slice(2).map(f => fs.readFileSync(f, "utf8")).join("\n");
const els = {}, posts = [], listeners = {};
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, type: "text",
  classList: { add() {}, remove() {} }, attrs: {}, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
  removeAttribute(k) { delete this.attrs[k]; }, focus() { document.activeElement = this; }, querySelectorAll: () => [],
  closest(s) { return (s === "#payForm" && this.form === "pay") || (s === "#addForm" && this.form === "add") ? {} : null; } };
const document = { activeElement: null, querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, getElementById: id => null,
  addEventListener(t, f) { (listeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") posts.push([init.method, path, init.body]);
  return { ok: true, status: 200, json: async () => ({ ok: true }) };
}
const ctx = vm.createContext({ document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams,
  localStorage: { getItem: () => null, setItem() {} }, window: {} });
const run = code => vm.runInContext(code, ctx);
const fire = (type, id) => { for (const f of listeners[type] || []) f({ type, target: el(id) }); };
const out = {};
(async () => {
  run(src);
  run(`state.meta = { entities: [{ id: 1, code: "TST", name: "Test Co", uses_sql: 0, accounts: [{ id: 9, label: "Old", currency: "MYR", active: 0 }] }],
    categories: { claim: "Staff claim", other: "Other payment", receipt: "Money received" }, category_info: {}, settings: {}, doc_types: {}, doc_info: {} };
    state.entity = 1; state.month = "2026-10"; state.day = dayKey();
    state.data = { entity: { id: 1, code: "TST", uses_sql: 0 }, month: "2026-10", closed_at: null,
      payments: [{ id: 5, description: "Test Payee H", amount: 10, currency: "MYR", direction: "out", documents: [], required: [], evidence: {} }] };
    state.openPayment = 5; payUi(5);`);
  for (const id of ["pf-amount", "pf-paid", "pf-bank", "pf-sql", "pf-einv", "pf-notes"]) el(id).form = "pay";
  for (const id of ["ap-desc", "ap-amt", "ap-due", "ap-cat", "ap-acct"]) el(id).form = "add";
  el("pf-amount").value = "10";
  run("state.payLoaded = payFormValues()");
  // 12e typed in the amount: the browser reads it as empty
  el("pf-amount").value = ""; el("pf-amount").validity = { badInput: true, valid: false };
  await run("paySave()");
  out.bad_posts = posts.length; out.bad_box = el("pd-refused-box").innerHTML;
  // an edit clears the refusal shown
  run(`state.pay.refused = { text: "Refused for the test" }`); el("pd-refused-box").innerHTML = "banner";
  fire("input", "pf-notes");
  out.pay_refused = run("state.pay.refused"); out.pay_box = el("pd-refused-box").innerHTML;
  // New payment, for a company whose only account is stopped: untouched, it is not unsaved
  run("state.openPayment = null; state.pay = null");
  await run("addPaymentDrawer()");
  el("ap-cat").value = run("npDefault('out')");   // what the type picker starts on (the stand-in page doesn't read its options)
  out.np_dirty = run("state.drawerDirty()");
  // a refusal from the server in New payment: an edit clears it
  run(`state.np.refused = "Refused for the test"`); el("np-refused").innerHTML = "banner";
  el("ap-desc").value = "Test"; fire("input", "ap-desc");
  out.np_refused = run("state.np.refused"); out.np_box = el("np-refused").innerHTML;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
files = [str(f) for f in app_files() if not str(f).endswith("main.js")]   # the page's own start-up is left out
res = subprocess.run([shutil.which("node"), str(probe), *files], capture_output=True, text=True, encoding="utf-8", timeout=120)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the dialogs' page script ran on the stand-in page", o is not None, res.stderr[-800:])
check("an amount the browser can't read is never sent as a blank: nothing is saved, and the dialog says which field",
      o["bad_posts"] == 0 and "Amount" in o["bad_box"], o)
check("an edit in the payment dialog takes its refusal away", o["pay_refused"] is None and o["pay_box"] == "", o)
check("New payment for a company whose only account is stopped: untouched, it has no unsaved changes", o["np_dirty"] is False, o)
check("an edit in New payment takes the server's refusal away", o["np_refused"] is None and o["np_box"] == "", o)

# The payment dialog's redraws, on a stand-in page that behaves as a browser does where it matters: drawing the dialog's
# box again replaces its fields (focus goes to the page), and the viewer is a node of its own beside the box.
# A: once a PDF is on show, redraws (a menu opened and closed, the redraw a save makes) neither make its viewer again
# nor take it out of the page (an iframe taken out and put back loads its file again). E: a field being typed in keeps
# the focus and the caret. D: an upload that finishes after the dialog was closed and opened again on the same payment
# draws it again.
PROBE2 = r"""
const fs = require("fs"), vm = require("vm");
const src = process.argv.slice(2).map(f => fs.readFileSync(f, "utf8")).join("\n");
const made = { viewers: 0, removed: 0 }, els = {};
const mk = id => ({ id, value: "", checked: false, hidden: false, dataset: {}, attrs: {}, type: "text", innerHTML: "", textContent: "", isConnected: true,
  classList: { add() {}, remove() {} }, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
  removeAttribute(k) { delete this.attrs[k]; }, focus() { document.activeElement = this; }, setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b; },
  querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, closest() { return null; } });
const body = mk("body");
const el = id => els[id] ||= mk(id);
let box = null, viewer = null;
const drawer = el("drawer"); drawer.hidden = true;
const newBox = () => { const b = mk("pd-box"); let h = "";
  Object.defineProperty(b, "innerHTML", { get: () => h, set(v) {   // the browser makes the fields again: focus goes to the page
    h = v; document.activeElement = body;
    for (const k of Object.keys(els)) if (/^pf-/.test(k)) { const o = els[k]; els[k] = mk(k); els[k].value = o.value; }
  } }); return b; };
Object.defineProperty(drawer, "innerHTML", { get: () => "", set(v) { box = /id="pd-box"/.test(v) ? newBox() : null; if (viewer) { viewer.isConnected = false; viewer = null; } } });
drawer.contains = x => !!x && x !== body;
drawer.querySelector = s => s === ":scope > #pd-box" || s === "#pd-box" ? box : s === ":scope > .pd-viewer" ? viewer
  : /^\.pd-viewer\[data-doc="(\d+)"\]$/.test(s) ? (viewer && viewer.dataset.doc === s.match(/"(\d+)"/)[1] ? viewer : null) : null;
const mkViewer = doc => ({ dataset: { doc }, isConnected: true, remove() { made.removed++; this.isConnected = false; if (viewer === this) viewer = null; } });
drawer.insertAdjacentHTML = (pos, html) => { const m = html.match(/class="pd-viewer" data-doc="(\d+)"/); if (m) { made.viewers++; viewer = mkViewer(m[1]); } };
drawer.appendChild = x => { viewer = x; x.isConnected = true; return x; };
const document = { activeElement: body, body, querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, getElementById: id => els[id] || null,
  addEventListener() {} };
let releaseUpload = null;
async function fetch(path, init = {}) {
  if (path === "/api/upload") await new Promise(r => { releaseUpload = r; });
  return { ok: true, status: 200, json: async () => ({ ok: true, id: 1 }) };
}
const ctx = vm.createContext({ document, fetch, FormData: class { append() {} }, console, setTimeout, clearTimeout, URLSearchParams,
  localStorage: { getItem: () => null, setItem() {} }, window: {} });
const run = code => vm.runInContext(code, ctx);
const out = {};
(async () => {
  run(src);
  run(`state.meta = { entities: [{ id: 1, code: "TST", name: "Test Co", uses_sql: 0, accounts: [] }], categories: { other: "Other payment" },
      category_info: {}, settings: {}, doc_types: { other: "Other" }, doc_info: {} };
    state.entity = 1; state.month = "2026-10"; state.day = dayKey(); state.view = "entity";
    state.data = { entity: { id: 1, code: "TST", uses_sql: 0 }, month: "2026-10", label: "October 2026", closed_at: null,
      payments: [{ id: 5, description: "Test Payee K", amount: 10, currency: "MYR", direction: "out", category: "other", due_date: "2026-10-20",
        status: "planned", flag: null, missing: [], required: [], evidence: {}, not_counted: {}, bank_lines: [], sql_entries: [], sql_changed: [],
        documents: [{ id: 7, doc_type: "other", original_name: "Bill.pdf", size: 900, uploaded_at: "2026-10-02T09:00:00" }] }] };
    globalThis.__renders = 0; render = async () => { globalThis.__renders++; };`);
  run("openPayment(5); state.pay.viewer = 7; payPaint()");
  out.first = made.viewers;
  run(`state.pay.menu = "doc-7"; payPaint(); state.pay.menu = null; payPaint(); openPayment(5, unsavedEdits())`);   // a menu, then the redraw a save makes
  out.viewers = made.viewers; out.removed = made.removed;
  // E: typing in Notes, caret at 2, then a redraw
  const n = els["pf-notes"]; n.value = "abcd"; n.focus(); n.setSelectionRange(2, 2);
  run("payPaint()");
  out.focus = document.activeElement.id; out.caret = document.activeElement.selectionStart; out.fresh = document.activeElement !== n;
  // D: an upload going on while the dialog is closed and opened again on the same payment
  run(`state.pay.viewer = null; payPaint();
    globalThis.__u = { id: 99, file: { name: "Slip.pdf", size: 10 }, type: "other", st: "up", pct: 0, why: "" }; state.pay.ups.push(__u);
    globalThis.__p = pdSend([__u])`);
  await new Promise(r => setTimeout(r, 20));
  await run("closeDrawer(true)");
  run("openPayment(5)");
  const before = run("__renders");
  releaseUpload(); await run("__p");
  out.d_renders = run("__renders") - before;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe2 = tmp / "probe2.js"
probe2.write_text(PROBE2, encoding="utf-8")
res = subprocess.run([shutil.which("node"), str(probe2), *files], capture_output=True, text=True, encoding="utf-8", timeout=120)
o2 = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the redraw probe ran on the stand-in page", o2 is not None, res.stderr[-800:])
check("a PDF on show: redraws neither make its viewer again nor take it out of the page (its file is fetched once)",
      o2["first"] == 1 and o2["viewers"] == 1 and o2["removed"] == 0, o2)
check("a field being typed in keeps the focus and the caret across a redraw",
      o2["focus"] == "pf-notes" and o2["caret"] == 2 and o2["fresh"], o2)
check("an upload finishing after the dialog was closed and opened again on the same payment draws it again", o2["d_renders"] == 1, o2)

print("\nAll payment dialog checks passed.")
