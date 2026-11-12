"""Phase 4 equivalence proof, on made-up records only: payment types, document types and required documents move from
the constants in hrp/rules.py into tables (update 20), and every status, flag, checklist result, Next up row, Before you
print list and report must come out exactly as before.

How: the records are built at update 19 (the readers still use the values from rules.py), snapshot S0 is taken (and S0
again, to prove the snapshot itself is deterministic), then the remaining updates run and snapshot S1 is taken. S0 must
equal S1, and the rows of the main tables must be unchanged by the update. With --golden, S0 and S1 are also compared
with a snapshot written by the code from before Phase 4 (--write-golden, run on an export of that code).

The file runs on the old code and the new code alike: it uses only routes and functions that exist before Phase 4,
never imports hrp.masters by name, and raw (armed) SQL only where no route exists (statements and their lines, SQL
listing rows, a payment with an unknown type, a document with an unknown type, two legacy checklist documents).

Fixed clock: every hrp module's `date` is a date whose today() is 4 Nov 2026 (the payroll month being worked on is
October), and every hrp module's `now` (db.now and the copy docstore imports) gives 2026-11-04T09:00:00. The fixed
`now` goes beyond masking: the audit pack item compares upload times with the pack file's time on disk, and the times a
month was filed or a statement reconciled are printed in sentences ("Done: month marked as filed 4 Nov", "Reconciled on
4 Nov 2026"); with a fixed clock and pack files dated by os.utime those come out the same on any day. datetime.now()
elsewhere (pack file names, the "Generated" line, the audit trail) stays real and is masked.

Allowances for keys the new code may add (documented, as the brief allows): each response is reduced to the keys it had
before Phase 4 (OLD_* below), so a key added by the new code (such as /api/meta's category_info or doc_info) is not
compared; /api/meta's added keys are listed, and any of them named like "inactive" must be empty.

Run (from the program folder):
    .venv\\Scripts\\python -m synthetic_tests.masters_equivalence_test [--write-golden PATH] [--golden PATH]
"""
import argparse
import datetime as _dt
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-masters-equiv-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

import hrp  # noqa: E402
import hrp.app as appmod  # noqa: E402
from hrp import auditpack, config, db, docstore, nextup, reports  # noqa: E402
from hrp.app import app  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

ARGS = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ARGS.add_argument("--write-golden", metavar="PATH", help="write snapshot S0 as JSON to PATH")
ARGS.add_argument("--golden", metavar="PATH", help="also compare S0 and S1 with the golden snapshot in PATH")
OPTS = ARGS.parse_args()

print(f"hrp imported from {hrp.__file__}")
print(f"records folder: {tmp}")

# ---------- the fixed clock ----------
REAL_DATE, REAL_NOW = _dt.date, db.now
TODAY = (2026, 11, 4)
FIXED_NOW = "2026-11-04T09:00:00"


class D(_dt.date):
    @classmethod
    def today(cls):
        return cls(*TODAY)


def fake_now():
    return FIXED_NOW


def patch_clock():
    """Every hrp module's date (from datetime import date) and now (db.now, or a copy of it) gives the fixed day and
    time. Run again after each init, for a module the new code imports late."""
    for name, mod in list(sys.modules.items()):
        if mod is None or not (name == "hrp" or name.startswith("hrp.")):
            continue
        if getattr(mod, "date", None) is REAL_DATE:
            mod.date = D
        if getattr(mod, "now", None) is REAL_NOW:
            mod.now = fake_now


def at(y, mo, d, h, mi):
    """A time on disk (for os.utime), local, as latest_pack reads it back."""
    return _dt.datetime(y, mo, d, h, mi).timestamp()


passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


# ---------- the records: three made-up companies ----------
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd",
     "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"},
                  {"label": "FCA", "bank": "Example Bank", "number": "000-333", "currency": "USD"}],
     "payees": [
         {"name": "Staff One (Ali)", "category": "salary", "amount": 3500, "due_day": 28, "start_date": "2026-10-06",
          "desc_template": "Salary Ali - {M}"},
         {"name": "Staff Two (Siti)", "category": "salary", "amount": 2800, "due_day": 28, "end_date": "2027-01-31",
          "desc_template": "Salary Siti - {M}"},
         {"name": "Director One", "category": "director", "amount": 2000, "due_day": 28, "desc_template": "Director allowance - {M}"},
         {"name": "KWSP contribution", "category": "statutory", "amount": 1200, "due_day": 6, "month_offset": 1,
          "desc_template": "KWSP - {M}"},
         {"name": "PERKESO SOCSO EIS", "category": "statutory", "amount": 300, "due_day": 6, "month_offset": 1,
          "desc_template": "PERKESO SOCSO EIS - {M}"},
         {"name": "LHDN PCB", "category": "statutory", "amount": 400, "due_day": 6, "month_offset": 1,
          "desc_template": "LHDN PCB - {M}"},
         {"name": "CLAUDE subscription claim", "category": "claim_overseas", "amount": 95, "due_day": 25,
          "start_date": "2026-10-01"},
         {"name": "TNB electricity", "category": "utility", "amount": 250, "due_day": 6, "month_offset": 1},
         {"name": "Office rental", "category": "rental", "amount": 3000, "due_day": 1, "month_offset": 1},
         {"name": "Raman Consulting", "category": "consultant", "amount": 5000, "due_day": 26},
     ]},
    {"code": "AI", "name": "Example International Ltd", "uses_sql": False,
     "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "XCO", "name": "Example Other Sdn Bhd", "accounts": [{"label": "Ops", "bank": "Example Bank", "number": "000-444"}]},
]}), encoding="utf-8")
AISB, AI, XCO = 1, 2, 3
MAIN, FCA, CURRENT, OPS = 1, 2, 3, 4
MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11"]

patch_clock()
full = db.MIGRATIONS[:]
check("the code has at least the 19 updates of Phase 3", len(full) >= 19, len(full))
db.MIGRATIONS[:] = full[:19]
db.init()
patch_clock()
with sqlite3.connect(config.DB_PATH) as _r:
    check("the records are at update 19 while they are built", _r.execute("PRAGMA user_version").fetchone()[0] == 19)
check("today is fixed at 4 Nov 2026 (payroll month October)", db.current_cycle() == "2026-10" and db.now() == FIXED_NOW)

client = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:400])
    return r


def j(method, path, expect=200, **kw):
    return call(method, path, expect, **kw).get_json()


def raw(why, fn):
    """A change no route makes, armed so the trail attributes it."""
    con = db.connect()
    try:
        if hasattr(con, "arm"):
            con.arm("user", f"test: {why}")
        out = fn(con)
        con.commit()
        return out
    finally:
        con.close()


def one(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        row = r.execute(sql, args).fetchone()
    assert row, (sql, args)
    return row[0]


def pay(eid, month, desc):
    return one("SELECT id FROM payments WHERE entity_id = ? AND month = ? AND description LIKE ? ORDER BY id", (eid, month, desc + "%"))


def task(eid, month, code):
    return one("SELECT id FROM tasks WHERE entity_id = ? AND month = ? AND code = ?", (eid, month, code))


def pdf(title):
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.add_metadata({"/Title": title})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def upload(doc_type, name, payment_id=None, task_id=None, data=None, replaces=None):
    form = {"doc_type": doc_type, "file": (io.BytesIO(pdf(name) if data is None else data), name)}
    if payment_id:
        form["payment_id"] = str(payment_id)
    if task_id:
        form["task_id"] = str(task_id)
    if replaces:
        form["replaces"] = str(replaces)
    return j("post", "/api/upload", data=form, content_type="multipart/form-data")["id"]


# 1. Money received from Agrinexus International, a recurring receipt (money in: only the route sets the direction).
j("post", "/api/payees", json={"entity_id": AISB, "name": "Fund from AGRINEXUS INTERNATIONAL", "category": "receipt",
                               "amount": 50000, "due_day": 24, "month_offset": 0, "account_id": MAIN})

# 2. Months: AISB August (filed at the end) to November (opened ahead); AI August to October, tracked from September.
for eid, months in ((AISB, MONTHS), (AI, MONTHS[:3]), (XCO, ["2026-10"])):
    for m in months:
        j("post", "/api/months/open", json={"entity_id": eid, "month": m})
j("post", f"/api/entities/{AI}/first-month", json={"month": "2026-09"})

# 3. Payments added by hand.
for eid, month, acct, cat, desc, amount, due, way in (
        (AISB, "2026-10", MAIN, "other", "Printer lease October", 1000, "2026-10-15", "out"),
        (AISB, "2026-10", MAIN, "other", "Courier charges October", 500, "2026-10-16", "out"),
        (AISB, "2026-10", MAIN, "other", "Stationery due today", 150, "2026-11-04", "out"),
        (AISB, "2026-10", MAIN, "transfer", "Transfer to AI October", 10000, "2026-10-20", "out"),
        (AISB, "2026-10", MAIN, "claim", "Staff claim Ahmad October", 230, "2026-10-22", "out"),
        (AISB, "2026-10", MAIN, "claim_overseas", "GOOGLE Workspace claim October", 60, "2026-10-27", "out"),
        (AISB, "2026-10", MAIN, "receipt", "Second fund from AGRINEXUS INTERNATIONAL", 20000, "2026-10-30", "in"),
        (AI, "2026-08", CURRENT, "other", "Old bill August", 100, "2026-08-20", "out"),
        (AI, "2026-09", CURRENT, "consultant", "Consultant Lim September", 3000, "2026-09-15", "out"),
        (AI, "2026-09", CURRENT, "receipt", "Customer receipt September", 8000, "2026-09-20", "in"),
        (AI, "2026-10", CURRENT, "consultant", "Consultant Lim October", 3000, "2026-10-20", "out"),
        (AI, "2026-10", CURRENT, "receipt", "Customer receipt October", 8000, "2026-10-25", "in"),
        (XCO, "2026-10", OPS, "other", "Misc expense October", 50, "2026-10-10", "out")):
    j("post", "/api/payments", json={"entity_id": eid, "month": month, "account_id": acct, "category": cat, "description": desc,
                                     "amount": amount, "due_date": due, "direction": way})
# A payment type no longer known (from an older version): the readers fall back to 'other' and show the code itself.
raw("payment with an unknown type", lambda con: con.execute(
    """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
       paid_source, direction, created_at) VALUES (1, '2026-10', 1, 'bonus', 'Bonus payout October', 777, 'MYR',
       '2026-10-27', '2026-10-27', 'manual', 'out', ?)""", (FIXED_NOW,)))

# 4. Bank statements and their lines (no route builds them without a real bank PDF).
STATEMENTS = [  # (account, month, opening, closing or None to add up, check_ok, [(date, description, amount)])
    (MAIN, "2026-09", 100000, None, 1, [("2026-09-24", "IBG CREDIT AGRINEXUS INTERNATIONAL", 50000),
                                        ("2026-09-26", "IBG RAMAN CONSULTING", -5000),
                                        ("2026-09-28", "IBG STAFF TWO SALARY", -2800),
                                        ("2026-09-28", "IBG DIRECTOR FEE", -2000)]),
    (FCA, "2026-09", 5000, None, 1, []),
    (MAIN, "2026-10", 140200, None, 1, [("2026-10-15", "PRINTER LEASE PART", -600),
                                        ("2026-10-16", "COURIER SVC", -450),
                                        ("2026-10-20", "KWSP CONTRIBUTION SEP", -1200),
                                        ("2026-10-20", "IBG TRANSFER TO AI", -10000),
                                        ("2026-10-24", "IBG CREDIT AGRINEXUS INTERNATIONAL", 50000),
                                        ("2026-10-28", "IBG ALI SALARY", -2935.48),
                                        ("2026-10-28", "IBG SITI SALARY", -2800),
                                        ("2026-10-29", "INWARD TRANSFER UNKNOWN", 1500),
                                        ("2026-10-30", "SERVICE CHARGE", -12)]),
    (FCA, "2026-10", 5000, 4900, 0, [("2026-10-25", "CLAUDE.AI SUBSCRIPTION", -22.5)]),
    (CURRENT, "2026-08", 21000, None, 1, [("2026-08-28", "OLD BILL PAYMENT", -100)]),
    (CURRENT, "2026-09", 20000, None, 1, [("2026-09-15", "IBG LIM CONSULTANT", -3000), ("2026-09-20", "CUSTOMER RECEIPT", 8000)]),
]


def add_statements(con):
    ids = {}
    for acct, month, opening, closing, ok, lines in STATEMENTS:
        bal, rows = opening, []
        for d, desc, amt in lines:
            bal = round(bal + amt, 2)
            rows.append((d, desc, amt, bal))
        close = bal if closing is None else closing
        debits = round(-sum(a for _, _, a in lines if a < 0), 2)
        credits = round(sum(a for _, _, a in lines if a > 0), 2)
        sid = con.execute("""INSERT INTO statements (account_id, month, statement_date, opening, closing, total_debits, total_credits,
                             imported_at, check_ok) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (acct, month, f"{month}-30", opening, close, debits, credits, FIXED_NOW, ok)).lastrowid
        for n, (d, desc, amt, b) in enumerate(rows, 1):
            con.execute("INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance) VALUES (?, ?, ?, ?, ?, ?)",
                        (sid, n, d, desc, amt, b))
        if (acct, month) != (FCA, "2026-10"):  # one statement kept without its PDF
            ent = con.execute("SELECT e.* FROM entities e JOIN accounts a ON a.entity_id = e.id WHERE a.id = ?", (acct,)).fetchone()
            did = docstore.store(con, entity=ent, month=month, folder="_Bank statements", doc_type="statement",
                                 filename=f"statement {acct} {month}.pdf", data=pdf(f"statement {acct} {month}"), statement_id=sid)
            con.execute("UPDATE statements SET document_id = ? WHERE id = ?", (did, sid))
        ids[acct, month] = sid
    return ids


SID = raw("bank statements", add_statements)


def line(acct, month, n):
    return one("SELECT id FROM statement_lines WHERE statement_id = ? AND line_no = ?", (SID[acct, month], n))


# 5. Bank lines linked to their payments (the route sets the paid dates and takes the lines' totals).
for acct, month, n, eid, pmonth, desc in (
        (MAIN, "2026-09", 1, AISB, "2026-09", "Fund from AGRINEXUS"), (MAIN, "2026-09", 2, AISB, "2026-09", "Raman Consulting"),
        (MAIN, "2026-09", 3, AISB, "2026-09", "Salary Siti"), (MAIN, "2026-09", 4, AISB, "2026-09", "Director allowance"),
        (MAIN, "2026-10", 1, AISB, "2026-10", "Printer lease"), (MAIN, "2026-10", 2, AISB, "2026-10", "Courier charges"),
        (MAIN, "2026-10", 3, AISB, "2026-09", "KWSP"), (MAIN, "2026-10", 4, AISB, "2026-10", "Transfer to AI"),
        (MAIN, "2026-10", 5, AISB, "2026-10", "Fund from AGRINEXUS"), (MAIN, "2026-10", 6, AISB, "2026-10", "Salary Ali"),
        (MAIN, "2026-10", 7, AISB, "2026-10", "Salary Siti"),
        (FCA, "2026-10", 1, AISB, "2026-10", "CLAUDE subscription claim"),  # a USD line on a ringgit payment
        (CURRENT, "2026-09", 1, AI, "2026-09", "Consultant Lim"), (CURRENT, "2026-09", 2, AI, "2026-09", "Customer receipt")):
    j("post", f"/api/statement-lines/{line(acct, month, n)}", json={"payment_id": pay(eid, pmonth, desc)})
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Courier charges')}", json={"difference_note": "Discount given by the courier"})

# 6. An SQL listing (raw rows: the listing parser needs a real SQL Account export), its vouchers then linked by the route.
SQL = [  # doc no, date, description, amount, direction, doc type, kind, e-Invoice UIN, e-Invoice status, item (month, code)
    ("PV2609-001", "2026-09-28", "SALARY SITI SEP 2026", 2800, "out", "PV", "payment", None, None, None),
    ("PV2609-002", "2026-09-28", "DIRECTOR FEE SEP 2026", 2000, "out", "PV", "payment", None, None, None),
    ("PV2609-003", "2026-09-26", "RAMAN CONSULTING SEP 2026", 5000, "out", "PV", "payment", None, None, None),
    ("OR2609-001", "2026-09-24", "FUND FROM AGRINEXUS INTERNATIONAL SEP 2026", 50000, "in", "OR", "payment", None, None, None),
    ("PV2610-001", "2026-10-20", "KWSP SEP 2026", 1200, "out", "PV", "payment", None, None, None),
    ("PV2610-002", "2026-10-06", "LHDN PCB SEP 2026", 400, "out", "PV", "payment", None, None, None),
    ("PV2610-003", "2026-10-28", "SALARY ALI OCT 2026", 2935.48, "out", "PV", "payment", None, None, None),
    ("PV2610-004", "2026-10-28", "SALARY SITI OCT 2026", 2800, "out", "PV", "payment", None, None, None),
    ("PV2610-005", "2026-10-27", "GOOGLE WORKSPACE CLAIM", 60, "out", "PV", "payment", "UIN-SB-005", "Validated", None),
    ("PV2610-010", "2026-10-25", "CLAUDE SUBSCRIPTION CLAIM", 95, "out", "PV", "payment", "UIN-SB-010", "Validated", None),
    ("OR2610-001", "2026-10-24", "FUND FROM AGRINEXUS INTERNATIONAL OCT 2026", 50000, "in", "OR", "payment", None, None, None),
    ("OR2610-002", "2026-10-30", "SELF-BILLED REFUND FOR DUPLICATED SELF-BILLED E-INVOICE (PV2610-005)", 60, "in", "OR", "payment",
     "UIN-REF-002", "Validated", None),
    ("JV2610-001", "2026-10-31", "PAYROLL ACCRUAL OCTOBER 26", 7735.48, None, "JV", "journal", None, None, ("2026-10", "payroll-jv")),
    ("IV2610-001", "2026-10-24", "MONTHLY OPERATING EXPENSES OCTOBER 26", 50000, "in", "IV", "invoice", "UIN-IV-001", "Validated",
     ("2026-10", "fund-received")),
    ("IV2610-002", "2026-11-03", "RENTAL CHARGE FOR OCTOBER 26", 1500, "in", "IV", "invoice", "UIN-IV-002", "Validated",
     ("2026-10", "einv-rental")),
]


def add_sql(con):
    imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (1, 'PV listing.xlsx', ?, ?, 0)",
                      (FIXED_NOW, len(SQL))).lastrowid
    ids = {}
    for no, d, desc, amt, way, typ, kind, uin, st, item in SQL:
        tid = con.execute("SELECT id FROM tasks WHERE entity_id = 1 AND month = ? AND code = ?", item).fetchone()[0] if item else None
        ids[no] = con.execute(
            """INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, einvoice, doc_type,
               kind, einvoice_status, task_id, status) VALUES (?, 1, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (imp, no, d, desc, amt, way, uin, typ, kind, st, tid, "unlinked" if kind == "payment" else kind)).lastrowid
    return ids


SQLID = raw("SQL listing rows", add_sql)
for no, month, desc in (("PV2609-001", "2026-09", "Salary Siti"), ("PV2609-002", "2026-09", "Director allowance"),
                        ("PV2609-003", "2026-09", "Raman Consulting"), ("OR2609-001", "2026-09", "Fund from AGRINEXUS"),
                        ("PV2610-001", "2026-09", "KWSP"), ("PV2610-002", "2026-09", "LHDN PCB"),
                        ("PV2610-003", "2026-10", "Salary Ali"), ("PV2610-004", "2026-10", "Salary Siti"),
                        ("PV2610-005", "2026-10", "GOOGLE Workspace"), ("PV2610-010", "2026-10", "CLAUDE subscription"),
                        ("OR2610-001", "2026-10", "Fund from AGRINEXUS")):  # OR2610-002 stays unlinked (Next up rule 7)
    j("post", f"/api/sql/entries/{SQLID[no]}", json={"payment_id": pay(AISB, month, desc)})

# 7. Paid dates typed in.
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Director allowance')}", json={"paid_date": "2026-10-28"})
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Staff claim Ahmad')}", json={"paid_date": "2026-10-22"})

# 8. Documents (small PDFs; one text file that won't print; one removed, one replaced; one of an unknown type).
old_slip = upload("payslip", "payslip Siti Sep v1.pdf", payment_id=pay(AISB, "2026-09", "Salary Siti"))
upload("payslip", "payslip Siti Sep v2.pdf", payment_id=pay(AISB, "2026-09", "Salary Siti"), replaces=old_slip)
upload("payslip", "payslip director Sep.pdf", payment_id=pay(AISB, "2026-09", "Director allowance"))
upload("invoice", "invoice Raman Sep.pdf", payment_id=pay(AISB, "2026-09", "Raman Consulting"))
upload("invoice", "invoice Lim Sep.pdf", payment_id=pay(AI, "2026-09", "Consultant Lim"))
upload("payslip", "payslip Ali Oct.pdf", payment_id=pay(AISB, "2026-10", "Salary Ali"))
for t in ("pv", "payslip", "bank"):
    upload(t, f"director Oct {t}.pdf", payment_id=pay(AISB, "2026-10", "Director allowance"))
upload("portal", "perkeso acknowledgement Oct.pdf", payment_id=pay(AISB, "2026-10", "PERKESO"))
upload("portal", "kwsp acknowledgement Oct.pdf", task_id=task(AISB, "2026-10", "kwsp"))
upload("claim", "claude claim form.pdf", payment_id=pay(AISB, "2026-10", "CLAUDE subscription"))
upload("approval", "claude claim approval.pdf", payment_id=pay(AISB, "2026-10", "CLAUDE subscription"))
upload("claim", "google claim form.pdf", payment_id=pay(AISB, "2026-10", "GOOGLE Workspace"))
upload("claim", "ahmad claim form.pdf", payment_id=pay(AISB, "2026-10", "Staff claim Ahmad"))
upload("approval", "transfer approval.pdf", payment_id=pay(AISB, "2026-10", "Transfer to AI"))
upload("approval", "budget approval Oct.pdf", task_id=task(AISB, "2026-10", "budget"))
upload("payroll", "payroll summary Oct.pdf", task_id=task(AISB, "2026-10", "payroll-calc"))
upload("invoice", "AI invoices Oct.pdf", task_id=task(AI, "2026-10", "invoices"))
gone = upload("bank", "raman bank slip wrong.pdf", payment_id=pay(AISB, "2026-10", "Raman Consulting"))
j("post", f"/api/documents/{gone}/remove", json={})
upload("other", "raman notes.txt", payment_id=pay(AISB, "2026-10", "Raman Consulting"), data=b"Notes, not a PDF.\n")


def unknown_doc(con):
    ent = con.execute("SELECT * FROM entities WHERE id = 1").fetchone()
    pid = con.execute("SELECT id FROM payments WHERE entity_id = 1 AND month = '2026-10' AND description LIKE 'Raman%'").fetchone()[0]
    docstore.store(con, entity=ent, month="2026-10", folder="misc", doc_type="misc", filename="raman misc.pdf",
                   data=pdf("raman misc"), payment_id=pid)


raw("document with an unknown type", unknown_doc)
# Checklist items set up by an older version: the statement item asking for a document of its own (done by the
# statements, still missing it), and the bank reconciliation item still asking for a reconciliation document (left out).
raw("legacy checklist documents", lambda con: (
    con.execute("UPDATE tasks SET required_docs = '[\"statement\"]' WHERE entity_id = 1 AND month = '2026-09' AND code = 'statement'"),
    con.execute("UPDATE tasks SET required_docs = '[\"recon\"]' WHERE entity_id = 1 AND month = '2026-10' AND code = 'recon'")))

# 9. Ticked by hand.
for eid, month, code in ((AISB, "2026-10", "inputs"), (AISB, "2026-10", "einv-rental"), (AI, "2026-10", "budget")):
    j("post", f"/api/tasks/{task(eid, month, code)}", json={"done": True})

# 10. A stored budget for October (Next up rule 5 reads its lines).
j("post", "/api/budget/setup", json={"entity_id": AISB, "month": "2026-10"})

# 11. September reconciled: book openings, every line confirmed, signed off (both AISB accounts).
j("post", "/api/recon/book-opening", json={"entity_id": AISB, "account_id": MAIN, "month": "2026-09", "amount": 100000})
j("post", "/api/recon/book-opening", json={"entity_id": AISB, "account_id": FCA, "month": "2026-09", "amount": 5000})
j("post", "/api/recon/confirm-matched", json={"entity_id": AISB, "statement_id": SID[MAIN, "2026-09"]})
for acct in (MAIN, FCA):
    j("post", "/api/recon/sign-off", json={"entity_id": AISB, "statement_id": SID[acct, "2026-09"]})

# 12. Audit packs: September built after its documents (unchanged), October built before more were added (changed).
for month, when in (("2026-09", at(2026, 11, 4, 10, 0)), ("2026-10", at(2026, 11, 4, 8, 0))):
    j("post", "/api/audit-pack", json={"entity_id": AISB, "month": month})
    built = db.packs_of({"code": "AISB"}, month)
    check(f"one audit pack built for AISB {month}", len(built) == 1, built)
    os.utime(built[0], (when, when))
upload("bank", "printer lease slip.pdf", payment_id=pay(AISB, "2026-10", "Printer lease"))

# 13. August marked as filed (after every month is set up, so the reminders sit in October and November).
j("post", "/api/months/close", json={"entity_id": AISB, "month": "2026-08", "closed": True})


# ---------- the snapshot ----------
DROP = {"stored_path", "data_dir", "url"}
KEEP_AT = {"as_at", "budget_as_at", "saved_as_at"}  # dates, not times: compared as they are
MASKS = [(re.compile(r"\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}"), "<time>"),
         (re.compile(r"Audit pack .* \(\d{8}-\d{4,6}\)\.pdf"), "<pack name>"),
         (re.compile(r"Audit trail entry \d+ . check code \S+"), "<trail>")]
OLD_META = {"entities", "doc_types", "categories", "required", "sql_only", "data_dir", "backup_dir", "settings"}
TASK_KEYS = ("id", "code", "title", "month", "due_date", "required_docs", "evidence", "done", "auto", "why", "missing", "lacking",
             "shown", "waiting", "not_counted", "flag", "documents", "sql_docs", "done_at")
PAY_KEYS = ("id", "description", "category", "direction", "currency", "amount", "due_date", "paid_date", "status", "missing", "required",
            "evidence", "not_counted", "flag", "bank_total", "not_in_sql", "documents", "sql_entries", "bank_lines")
OVERVIEW_KEYS = ("set_up", "before_first", "closed_at", "payments", "planned", "receipts", "complete", "tasks", "tasks_done", "budget",
                 "budget_as_at", "paid_missing", "part_paid", "payment_flags", "overdue_tasks", "due_today_tasks", "not_in_sql",
                 "unmatched_lines")
ROW_KEYS = ("key", "rule", "entity_id", "entity", "month", "text", "due", "state", "priority", "amount", "currency", "go")
READY_KEYS = ("set_up", "payments", "closed_at", "items", "summary", "ready", "pack", "pack_open", "still_open", "to_print")
NEXT_DATES = ["2026-10-28", "2026-11-04", "2026-11-13", "2026-11-16", "2026-12-08"]
GUESS_WORDS = ["CLAUDE.AI subscription", "Google Workspace", "ANTHROPIC", "Staff claim", "SALARY OCT", "Stamp duty", "CP204 instalment",
               "KWSP Oct", "PERKESO", "LHDN PCB", "HASIL", "SOCSO", "Office RENTAL", "TNB bill", "UNIFI", "TM TECHNOLOGY", "Printer toner",
               "", None]
ACCOUNTS = [(AISB, MAIN), (AISB, FCA), (AI, CURRENT), (XCO, OPS)]


def clean(x):
    """Times dropped to whether they are set (a fixed clock gives them anyway), paths and links dropped, masks applied."""
    if isinstance(x, dict):
        return {k: (bool(v) if k.endswith("_at") and k not in KEEP_AT else clean(v)) for k, v in x.items() if k not in DROP}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, str):
        for rx, sub in MASKS:
            x = rx.sub(sub, x)
        return x
    if isinstance(x, _dt.date):
        return x.isoformat()
    return x


def pick(d, keys):
    return {k: d.get(k) for k in keys}


def docs(ds):
    return sorted(({"id": d["id"], "doc_type": d["doc_type"], "label": d.get("label"), "original_name": d["original_name"]}
                   for d in ds), key=lambda d: d["id"])


def sheet_values(ws):
    out = []
    for row in ws.iter_rows(values_only=True):
        if row and row[0] == "Generated":
            row = (row[0], "<generated>") + tuple(row[2:])
        out.append([v.isoformat() if isinstance(v, _dt.date) else v for v in row])
    return out


def snapshot():
    auditpack._PRINTS.clear()
    s = {}
    m = j("get", "/api/meta")
    extra = sorted(set(m) - OLD_META)
    s["meta"] = {"categories": list(m["categories"].items()), "doc_types": list(m["doc_types"].items()),
                 "required": list(m["required"].items()), "sql_only": m["sql_only"],
                 "inactive": {k: m[k] for k in extra if "inactive" in k.lower() and m[k]},
                 "entities": [(e["id"], e["code"], e["uses_sql"], e["first_month"], [a["id"] for a in e["accounts"]]) for e in m["entities"]]}
    s["meta_new_keys"] = extra  # listed, not compared (see the docstring)

    s["month"] = {}
    for eid in (AISB, AI, XCO):
        for month in MONTHS:
            v = j("get", f"/api/month?entity={eid}&month={month}")
            tasks = []
            for t in v["tasks"]:
                t = pick(t, TASK_KEYS)
                t["documents"] = docs(t["documents"] or [])
                t["sql_docs"] = [pick(x, ("doc_no", "doc_type", "amount", "einvoice", "einvoice_status", "taken_back_by")) for x in t["sql_docs"] or []]
                tasks.append(t)
            pays = []
            for p in v["payments"]:
                p = pick(p, PAY_KEYS)
                p["documents"] = docs(p["documents"] or [])
                p["sql_entries"] = [pick(x, ("doc_no", "doc_date", "amount", "direction", "kind")) for x in p["sql_entries"] or []]
                p["bank_lines"] = [pick(x, ("id", "txn_date", "amount")) for x in p["bank_lines"] or []]
                pays.append(p)
            s["month"][f"{eid}:{month}"] = {"set_up": v["set_up"], "before_first": v["before_first"], "closed_at": v["closed_at"],
                                            "tasks": tasks, "payments": pays}

    s["overview"] = {}
    for month in MONTHS:
        v = j("get", f"/api/overview?month={month}")
        s["overview"][month] = [{"code": e["entity"]["code"], **pick(e, OVERVIEW_KEYS)} for e in v["entities"]]

    nx = j("get", "/api/next")
    s["next_route"] = {"today": nx["today"], "items": [pick(r, ROW_KEYS) for r in nx["items"]], "older": nx["older_open_months"],
                       "next_due": nx["next_due"]}
    s["nextup"] = {}
    con = db.connect()
    try:
        con.execute("PRAGMA query_only = ON")
        for d in NEXT_DATES:
            day = D.fromisoformat(d)
            for eid in (None, AISB, AI, XCO):
                s["nextup"][f"{d}:{eid}"] = {"items": [pick(r, ROW_KEYS) for r in nextup.items(con, day, eid)],
                                             "older": nextup.older_open(con, day, eid), "upcoming": nextup.upcoming(con, day, eid)}
        s["reports"], s["gather"] = {}, {}
        for eid in (AISB, AI, XCO):
            ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
            for month in MONTHS:
                wb = reports.month_workbook(con, ent, month)
                s["reports"][f"{eid}:{month}"] = {ws.title: sheet_values(ws) for ws in wb.worksheets}
                pays, tasks, _ = reports._gather(con, ent, month)
                s["gather"][f"{eid}:{month}"] = {
                    "payments": [{"id": x["p"]["id"], **pick(x, ("status", "word", "flag", "missing", "on_file", "sql", "bank"))} for x in pays],
                    "tasks": [{"code": x["t"]["code"], "done": x["st"]["done"], "lack": x["lack"]} for x in tasks]}
    finally:
        con.close()

    s["readiness"] = {}
    for eid in (AISB, AI, XCO):
        for month in MONTHS:
            r = pick(j("get", f"/api/audit-readiness?entity_id={eid}&month={month}"), READY_KEYS)
            r["pack"] = r["pack"] and {"when": r["pack"]["when"], "changed": r["pack"]["changed"]}
            s["readiness"][f"{eid}:{month}"] = r

    s["recon"] = {}
    for eid, acct in ACCOUNTS:
        s["recon"][f"{acct}:year"] = j("get", f"/api/recon/year?entity={eid}&account={acct}&year=2026")
        for month in MONTHS:
            s["recon"][f"{acct}:{month}"] = j("get", f"/api/recon/month?entity={eid}&account={acct}&month={month}")

    s["settings_fields"] = j("get", "/api/setup/settings")["fields"]
    s["guess"] = [[w, appmod._guess_category(w)] for w in GUESS_WORDS]
    r1 = call("post", "/api/payees", 400, json={"entity_id": AISB, "name": "Bogus", "category": "bogus"})
    r2 = call("post", "/api/upload", 400, data={"doc_type": "bogus", "payment_id": str(pay(AISB, "2026-10", "Raman Consulting")),
                                                "file": (io.BytesIO(pdf("bogus")), "bogus.pdf")}, content_type="multipart/form-data")
    s["refused"] = [[r.status_code, r.get_json()] for r in (r1, r2)]

    # The audit pack cover and reconciliation pages for AISB September, built here and removed again.
    con = db.connect()
    try:
        ent = con.execute("SELECT * FROM entities WHERE id = ?", (AISB,)).fetchone()
        before = set(db.packs_of(ent, "2026-09"))
        path = auditpack.build(con, ent, "2026-09")
    finally:
        con.close()
    data = path.read_bytes()
    path.unlink()
    check("building the pack for the snapshot leaves the packs as they were", set(db.packs_of({"code": "AISB"}, "2026-09")) == before)
    reader = PdfReader(io.BytesIO(data))
    s["pack_pages"] = [pg.extract_text() for pg in reader.pages]
    s["pack_outline"] = [o.title for o in reader.outline if not isinstance(o, list)]
    return json.loads(json.dumps(clean(s), sort_keys=True, default=str))


def flat(x, path="", out=None):
    out = {} if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            flat(v, f"{path}/{k}", out)
        if not x:
            out[path] = {}
    elif isinstance(x, list):
        for i, v in enumerate(x):
            flat(v, f"{path}[{i}]", out)
        out[path + "#len"] = len(x)
    else:
        out[path] = x
    return out


def differences(a, b):
    fa, fb = flat(a), flat(b)
    keys = sorted(set(fa) | set(fb))
    return [(k, fa.get(k, "<absent>"), fb.get(k, "<absent>")) for k in keys if fa.get(k, "<absent>") != fb.get(k, "<absent>")]


def same(name, a, b, ignore=("/meta_new_keys",)):
    diff = [d for d in differences(a, b) if not d[0].startswith(ignore)]
    detail = "\n     ".join(f"{k}: {str(x)[:160]!r} != {str(y)[:160]!r}" for k, x, y in diff[:30])
    check(name, not diff, f"{len(diff)} paths differ; the first {min(len(diff), 30)}:\n     {detail}")


def rows_of(tables=("payments", "tasks", "documents", "sql_entries", "statement_lines", "statements", "months", "payees",
                    "budget_lines", "budgets")):
    with sqlite3.connect(config.DB_PATH) as r:
        return {t: [tuple(x) for x in r.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in tables}


# ---------- coverage: the seed can't quietly lose a case ----------
WHY_KINDS = {
    "payments: done, paid": r"^Done: .* (is|are) paid$",
    "payments: done, on file or in SQL": r"^Done: .*(on file|recorded in SQL)",
    "payments: documents still missing": r"still missing for",
    "payments: e-Invoice cancelled": r"\(e-Invoice cancelled by OR2610-002\)",
    "payments: none yet": r"^No .* this month yet$",
    "payments: done with none": r"^Done: no overseas claims this month$",
    "statements: not imported": r"statements? not imported yet$",
    "statements: imported": r"^Done: (statement imported|both statements imported|all \d+ statements imported)$",
    "statements: reconciled": r"^Done: reconciled",
    "statements: not reconciled": r"^(Main|FCA): ",
    "statements: balanced": r"^Done: balances add up",
    "statements: not balanced": r"line(s)? to explain on |balances don't add up",
    "pack: built": r"^Done: audit pack built",
    "pack: filed": r"^Done: month marked as filed",
    "pack: none": r"^No audit pack built",
    "pack: changed": r"added or removed since the audit pack",
    "done, own document missing": r"^Both statements imported$",
}


def coverage(s):
    pays = [p for v in s["month"].values() for p in v["payments"]]
    tasks = [(k, t) for k, v in s["month"].items() for t in v["tasks"]]
    check("coverage: payment statuses are exactly planned, paid, part paid and complete",
          {p["status"] for p in pays} == {"planned", "paid", "part_paid", "complete"}, {p["status"] for p in pays})
    codes = {p["flag"]["code"] for p in pays if p["flag"]}
    want = {"not_paid", "due_today", "not_on_statement", "waiting_sql", "waiting_statement", "past_legal", "paid_late"}
    check("coverage: every payment flag", want <= codes, want - codes)
    grey = lambda k: any(p["flag"] and (p["flag"]["code"], p["flag"]["tone"]) == ("not_paid", "grey") for p in s["month"][k]["payments"])
    check("coverage: grey in a filed month and before tracking", s["month"]["1:2026-08"]["closed_at"] and grey("1:2026-08")
          and s["month"]["2:2026-08"]["before_first"] and grey("2:2026-08"))
    rows = [r for v in s["nextup"].values() for r in v["items"]]
    check("coverage: Next up rules 1 to 13", {r["rule"] for r in rows} >= set(range(1, 14)), sorted({r["rule"] for r in rows}))
    check("coverage: Next up legal_soon, past_legal and not_on_statement (in and out)",
          {k for k in ("legal_soon", "past_legal", "not_on_statement", "not_on_statement-in") if any(r["key"].endswith(":" + k) for r in rows)}
          == {"legal_soon", "past_legal", "not_on_statement", "not_on_statement-in"})
    check("coverage: Next up has older months still open on a later date", any(v["older"] for v in s["nextup"].values()))
    whys = [t["why"] for _, t in tasks]
    lost = [k for k, rx in WHY_KINDS.items() if not any(w and re.search(rx, w) for w in whys)]
    check("coverage: each kind of checklist 'why'", not lost, lost)
    check("coverage: an item the records can't show (why None) and one ticked by hand",
          any(t["why"] is None for _, t in tasks) and any(t["done"] and not t["auto"] and t["lacking"] for _, t in tasks))
    st9 = next(t for t in s["month"]["1:2026-09"]["tasks"] if t["code"] == "statement")
    check("coverage: done by the statements but still missing its own document", st9["missing"] == ["statement"] and not st9["done"])
    rc10 = next(t for t in s["month"]["1:2026-10"]["tasks"] if t["code"] == "recon")
    check("coverage: the legacy reconciliation document is left out", rc10["required_docs"] == ["recon"] and rc10["missing"] == [])
    check("coverage: a reminder waiting for a later month", any(t["waiting"] for _, t in tasks))
    check("coverage: an e-Invoice taken back (not counted, cancelled by)",
          any(p["not_counted"].get("einvoice") for p in pays) and any(t["why"] and "cancelled by OR2610-002" in t["why"] for _, t in tasks))
    check("coverage: evidence from PV, OR, JV-free invoice proof, e-Invoice and bank lines",
          {"pv", "or", "invoice", "einvoice", "bank"} <= {k for p in pays for k in p["evidence"]})
    check("coverage: a USD line on a ringgit payment (no bank total, bank line evidence)",
          any(p["bank_total"] is None and "bank" in p["evidence"] for p in pays))
    check("coverage: part paid, and a difference accepted by a note",
          any(p["status"] == "part_paid" for p in pays) and any(p["description"].startswith("Courier") and p["status"] == "paid" for p in pays))
    check("coverage: complete through uploads only, evidence only, and a mix",
          any(p["status"] == "complete" and not p["evidence"] for p in pays)
          and any(p["status"] == "complete" and not p["documents"] for p in pays)
          and any(p["status"] == "complete" and p["evidence"] and p["documents"] for p in pays))
    check("coverage: an unknown payment type and an unknown document type",
          any(p["category"] == "bonus" and p["required"] == ["invoice", "pv", "bank"] for p in pays)
          and any(d["doc_type"] == "misc" and d["label"] == "misc" for p in pays for d in p["documents"]))
    check("coverage: a company not in SQL (no SQL vouchers asked for) and one with no checklist",
          any(p["required"] == ["invoice", "bank"] for p in s["month"]["2:2026-09"]["payments"])
          and s["month"]["3:2026-10"]["payments"] and not s["month"]["3:2026-10"]["tasks"])
    check("coverage: paid but not in SQL", any(p["not_in_sql"] for p in pays))
    items = [i for v in s["readiness"].values() for i in v["items"]]
    check("coverage: Before you print lists every kind", {i["kind"] for i in items} >= {"statement", "lines", "payment", "task", "task_open",
                                                                                       "not_in_sql", "unprintable"},
          {i["kind"] for i in items})
    check("coverage: a pack unchanged (Sep) and one out of date (Oct)",
          s["readiness"]["1:2026-09"]["pack"]["changed"] == 0 and s["readiness"]["1:2026-10"]["pack"]["changed"] > 0)
    check("coverage: SQL vouchers to print", any(v["to_print"] for v in s["readiness"].values()))
    check("coverage: a statement reconciled", any(r["status"] == "reconciled" for k, v in s["recon"].items() if k.endswith(":year")
                                                  for r in v["rows"]))
    check("coverage: the pack cover lists the index", any("Transaction / task" in p for p in s["pack_pages"]))
    check("coverage: both refused writes refused", [r[0] for r in s["refused"]] == [400, 400])


# ---------- run ----------
S0 = snapshot()
same("the snapshot is deterministic (S0 taken twice)", S0, snapshot())
coverage(S0)
raw0 = rows_of()
print(f"S0: {len(json.dumps(S0))} characters; /api/meta keys beyond the old ones: {S0['meta_new_keys'] or 'none'}")
if OPTS.write_golden:
    Path(OPTS.write_golden).write_text(json.dumps(S0, sort_keys=True, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"golden written: {OPTS.write_golden}")

db.MIGRATIONS[:] = full
db.init()
patch_clock()
with sqlite3.connect(config.DB_PATH) as _r:
    check("every update has run", _r.execute("PRAGMA user_version").fetchone()[0] == len(full))
S1 = snapshot()
print(f"S1: /api/meta keys beyond the old ones: {S1['meta_new_keys'] or 'none'}")
check("no key of /api/meta named like 'inactive' lists anything", not S1["meta"]["inactive"], S1["meta"]["inactive"])
same("S0 (update 19) equals S1 (every update)", S0, S1)
raw1 = rows_of()
check("the records' rows are unchanged by the remaining updates", raw0 == raw1,
      [t for t in raw0 if raw0[t] != raw1.get(t)])
if OPTS.golden:
    golden = json.loads(Path(OPTS.golden).read_text(encoding="utf-8"))
    same("S0 equals the golden snapshot from before Phase 4", golden, S0)
    same("S1 equals the golden snapshot from before Phase 4", golden, S1)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
