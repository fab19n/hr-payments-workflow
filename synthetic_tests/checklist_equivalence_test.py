"""Phase 5 equivalence proof, on made-up records only: the monthly checklist, its completion rules, Next up's deadline
and naming words, the joiner and leaver reminders and the matching words move from code into tables (update 21), and
every status, checklist row, reminder, Next up row, report, SQL suggestion and guessed payment type must come out
exactly as before.

How: the records are built at update 20 (Phase 4's tables in place, the checklist, reminders and words still read from
code), snapshot S0 is taken (and S0 again, to prove the snapshot itself is deterministic), then the probes that write
run, each from the same copy of the records folder, and give P0 (twice, to prove they are deterministic). The records
folder is put back as it was, the remaining updates run, snapshot S1 is taken and the same probes run again from a copy
of the updated folder, giving P1. S0 must equal S1, P0 must equal P1, and the rows of the main tables must be
unchanged by the update. With --golden, S0/S1 and P0/P1 are also compared with a golden snapshot written by the code
from before Phase 5 (--write-golden, run on an export of that code).

The probes are the parts Phase 5 moves and that only show when something happens after the update:
  A. months set up after the update (POST /api/months/open: a company with a checklist, one without, a month before
     the others, an automatic one before the first month tracked), with the checklist rows written, their order, due
     dates and documents, and the reminders that move into the new month;
  B. recurring payments saved after the update (POST /api/payees): joiner and leaver reminders added, moved and
     removed (start date, last day, a salary over RM 3,000 and exactly 3,000, a varying amount, ticked and held
     reminders, one placed past a filed month, moved back when it is reopened and out of it when filed again, a
     director, a company that runs no payroll, a stopped payee), with the change lines the save returns,
     and the usage counts;
  C. months marked as filed after the update (the audit pack item ticked) and reopened;
  D. the SQL preview (POST /api/sql/preview) of pasted listings: documents filed on checklist items by their words
     (payroll journals, the related company's invoice and receipt, the office tenant's rental invoice, a self-billed
     payment) and, for an estimate of a type with salary words (CATEGORY_HINTS), the words for an
     estimated salary or director payment matched within +-50%;
  E. SQL vouchers added as payments (POST /api/sql/entries/create-all and one by one), their types guessed from the
     description, also after a payment type is stopped.
Next up's combined submit row, a person's reminders listed together and the statement and closing rows of a company
without a checklist are in S0/S1 and checked by the coverage checks.

The file runs on the old code and the new code alike: it uses only routes and functions that exist before Phase 5,
never imports hrp.masters by name, calls app._guess_category with one argument, and uses raw (armed) SQL only where no
route exists (statements and their lines, SQL listing rows, a payment with an unknown type, a document with an unknown
type, two legacy checklist documents). No real names: the related company's name, which the fund-received item and the
SQL filing words look for, is read from hrp.rules at run time (rules.py is frozen) and masked as <RELATED>, and the
office tenant's name, which the rental e-Invoice item's filing words look for, is read from sqlimport.TASK_RULES (kept
as the frozen default) and masked as <TENANT>, in every snapshot and probe, so neither this file nor a golden holds
them (checked).

Fixed clock: as in masters_equivalence_test.py, every hrp module's `date` is a date whose today() is 4 Nov 2026 (the
payroll month being worked on is October), and every hrp module's `now` gives 2026-11-04T09:00:00. datetime.now()
elsewhere (pack file names, pasted listing names, the "Generated" line, the audit trail) stays real and is masked.

Allowances for keys the new code may add (documented): each response is reduced to the keys it had before Phase 5, so
a key added by the new code (such as /api/meta's people_tasks or checklist_codes) is not compared; /api/meta's added
keys are listed, and any of them named like "inactive" must be empty. Table rows are read by their column names as of
update 20.

Allowance for names taken out (Phase 7): the golden was written when this file named a real utility and two real telcos
(and the frozen rules held the real related company and tenant, which the masks above already cover; the names the
rules hold now are made up, of the same length). They are made up here too. Before the golden is compared, each old
name is read from the golden by key (the utility from the first word of the October payment at the place the new one
is, the telcos from the descriptions of the vouchers PV2611-118 and PV2611-119 added as payments) and masked in the
golden as its new name is masked in the snapshot; the guess inputs that named a real supplier (GUESS_RENAMED, by index)
are compared by the type guessed only, and the first company's budget item's detail (which named suppliers) not at
all. No name is written in this file.

Run (from the program folder):
    .venv\\Scripts\\python -m synthetic_tests.checklist_equivalence_test [--write-golden PATH] [--golden PATH]
"""
import argparse
import datetime as _dt
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):  # a detail with an arrow or a quote mark prints on any console
    sys.stdout.reconfigure(errors="backslashreplace")

tmp = Path(tempfile.mkdtemp(prefix="hrp-checklist-equiv-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

import hrp  # noqa: E402
import hrp.app as appmod  # noqa: E402
from hrp import auditpack, config, db, docstore, nextup, reports, rules, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

ARGS = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ARGS.add_argument("--write-golden", metavar="PATH", help="write snapshots S0 and P0 as JSON to PATH")
ARGS.add_argument("--golden", metavar="PATH", help="also compare S0, S1, P0 and P1 with the golden snapshot in PATH")
OPTS = ARGS.parse_args()

print(f"hrp imported from {hrp.__file__}")
print(f"records folder: {tmp}")

# The related company the fund-received item and the SQL filing words look for, read from the frozen rules (never
# written in this file) and masked in every snapshot.
RELATED = rules.TASK_PAYMENTS["fund-received"]["words"][0]
# The office tenant the rental e-Invoice item's SQL filing words look for, read the same way from the frozen filing
# words (sqlimport.TASK_RULES, kept as they are before update 21) and masked as <TENANT>.
TENANT = next(w for _kinds, _way, words, code in sqlimport.TASK_RULES if code == "einv-rental" for w in words)
NAMES = (RELATED, TENANT)

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
         {"name": "Staff One (Alpha)", "category": "salary", "amount": 3500, "due_day": 28, "start_date": "2026-10-06",
          "desc_template": "Salary Alpha - {M}"},
         {"name": "Staff Two (Bravo)", "category": "salary", "amount": 2800, "due_day": 28, "end_date": "2027-01-31",
          "desc_template": "Salary Bravo - {M}"},
         {"name": "Director One", "category": "director", "amount": 2000, "due_day": 28, "desc_template": "Director allowance - {M}"},
         {"name": "KWSP contribution", "category": "statutory", "amount": 1200, "due_day": 6, "month_offset": 1,
          "desc_template": "KWSP - {M}"},
         {"name": "PERKESO SOCSO EIS", "category": "statutory", "amount": 300, "due_day": 6, "month_offset": 1,
          "desc_template": "PERKESO SOCSO EIS - {M}"},
         {"name": "LHDN PCB", "category": "statutory", "amount": 400, "due_day": 6, "month_offset": 1,
          "desc_template": "LHDN PCB - {M}"},
         {"name": "CLAUDE subscription claim", "category": "claim_overseas", "amount": 95, "due_day": 25,
          "start_date": "2026-10-01"},
         {"name": "OHM electricity", "category": "utility", "amount": 250, "due_day": 6, "month_offset": 1},
         {"name": "Office rental", "category": "rental", "amount": 3000, "due_day": 1, "month_offset": 1},
         {"name": "Delta Consulting", "category": "consultant", "amount": 5000, "due_day": 26},
         # Estimates the SQL salary words decide between (probe D).
         {"name": "Staff Five (Golf)", "category": "salary", "amount": 3000, "varies": True, "due_day": 28,
          "desc_template": "Salary Golf - {M}"},
         {"name": "Director Two (Hotel)", "category": "director", "amount": 2000, "varies": True, "due_day": 28,
          "desc_template": "Director fee Hotel - {M}"},
         {"name": "Kilo Water Works", "category": "utility", "amount": 200, "varies": True, "due_day": 6, "month_offset": 1,
          "desc_template": "Kilo water - {M}"},
     ]},
    {"code": "AI", "name": "Example International Ltd", "uses_sql": False,
     "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "XCO", "name": "Example Other Sdn Bhd", "accounts": [{"label": "Ops", "bank": "Example Bank", "number": "000-444"}]},
]}), encoding="utf-8")
AISB, AI, XCO = 1, 2, 3
MAIN, FCA, CURRENT, OPS = 1, 2, 3, 4
MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11"]
CUT = 20  # the records are built at this update; Phase 5's is the next one

patch_clock()
full = db.MIGRATIONS[:]
check(f"the code has at least the {CUT} updates of Phase 4", len(full) >= CUT, len(full))
db.MIGRATIONS[:] = full[:CUT]
db.init()
patch_clock()
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
    r = sqlite3.connect(config.DB_PATH)  # closed again: an open connection keeps records.db locked on Windows
    try:
        row = r.execute(sql, args).fetchone()
    finally:
        r.close()
    assert row, (sql, args)
    return row[0]


check(f"the records are at update {CUT} while they are built", one("PRAGMA user_version") == CUT)


def q(sql, args=()):
    """Rows read straight from records.db, as dicts (a plain connection, closed again)."""
    r = sqlite3.connect(config.DB_PATH)
    try:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]
    finally:
        r.close()


def pay(eid, month, desc):
    return one("SELECT id FROM payments WHERE entity_id = ? AND month = ? AND description LIKE ? ORDER BY id", (eid, month, desc + "%"))


def task(eid, month, code):
    return one("SELECT id FROM tasks WHERE entity_id = ? AND month = ? AND code = ?", (eid, month, code))


def payee(name):
    return one("SELECT id FROM payees WHERE name = ?", (name,))


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


FUND = f"Fund from {RELATED}"

# 1. Money received from the related company, a recurring receipt (money in: only the route sets the direction).
j("post", "/api/payees", json={"entity_id": AISB, "name": FUND, "category": "receipt",
                               "amount": 50000, "due_day": 24, "month_offset": 0, "account_id": MAIN})

# 2. Months: AISB August (filed at the end) to November (opened ahead); AI August to October, tracked from September;
#    XCO (no checklist) September and October.
for eid, months in ((AISB, MONTHS), (AI, MONTHS[:3]), (XCO, ["2026-09", "2026-10"])):
    for m in months:
        j("post", "/api/months/open", json={"entity_id": eid, "month": m})
j("post", f"/api/entities/{AI}/first-month", json={"month": "2026-09"})

# 3. Payments added by hand.
for eid, month, acct, cat, desc, amount, due, way, paid in (
        (AISB, "2026-10", MAIN, "other", "Printer lease October", 1000, "2026-10-15", "out", None),
        (AISB, "2026-10", MAIN, "other", "Courier charges October", 500, "2026-10-16", "out", None),
        (AISB, "2026-10", MAIN, "other", "Stationery due today", 150, "2026-11-04", "out", None),
        (AISB, "2026-10", MAIN, "transfer", "Transfer to AI October", 10000, "2026-10-20", "out", None),
        (AISB, "2026-10", MAIN, "claim", "Staff claim Echo October", 230, "2026-10-22", "out", None),
        (AISB, "2026-10", MAIN, "claim_overseas", "GOOGLE Workspace claim October", 60, "2026-10-27", "out", None),
        (AISB, "2026-10", MAIN, "receipt", f"Second fund from {RELATED}", 20000, "2026-10-30", "in", None),
        (AI, "2026-08", CURRENT, "other", "Old bill August", 100, "2026-08-20", "out", None),
        (AI, "2026-09", CURRENT, "consultant", "Consultant Foxtrot September", 3000, "2026-09-15", "out", None),
        (AI, "2026-09", CURRENT, "receipt", "Customer receipt September", 8000, "2026-09-20", "in", None),
        (AI, "2026-10", CURRENT, "consultant", "Consultant Foxtrot October", 3000, "2026-10-20", "out", None),
        (AI, "2026-10", CURRENT, "receipt", "Customer receipt October", 8000, "2026-10-25", "in", None),
        (XCO, "2026-09", OPS, "other", "Misc expense September", 80, "2026-09-12", "out", "2026-09-12"),
        (XCO, "2026-10", OPS, "other", "Misc expense October", 50, "2026-10-10", "out", None)):
    j("post", "/api/payments", json={"entity_id": eid, "month": month, "account_id": acct, "category": cat, "description": desc,
                                     "amount": amount, "due_date": due, "direction": way, "paid_date": paid})
# A payment type no longer known (from an older version): the readers fall back to 'other' and show the code itself.
raw("payment with an unknown type", lambda con: con.execute(
    """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
       paid_source, direction, created_at) VALUES (1, '2026-10', 1, 'bonus', 'Bonus payout October', 777, 'MYR',
       '2026-10-27', '2026-10-27', 'manual', 'out', ?)""", (FIXED_NOW,)))

# 4. Bank statements and their lines (no route builds them without a real bank PDF).
STATEMENTS = [  # (account, month, opening, closing or None to add up, check_ok, [(date, description, amount)])
    (MAIN, "2026-09", 100000, None, 1, [("2026-09-24", "IBG CREDIT RELATED CO", 50000),
                                        ("2026-09-26", "IBG DELTA CONSULTING", -5000),
                                        ("2026-09-28", "IBG STAFF TWO SALARY", -2800),
                                        ("2026-09-28", "IBG DIRECTOR FEE", -2000)]),
    (FCA, "2026-09", 5000, None, 1, []),
    (MAIN, "2026-10", 140200, None, 1, [("2026-10-15", "PRINTER LEASE PART", -600),
                                        ("2026-10-16", "COURIER SVC", -450),
                                        ("2026-10-20", "KWSP CONTRIBUTION SEP", -1200),
                                        ("2026-10-20", "IBG TRANSFER TO AI", -10000),
                                        ("2026-10-24", "IBG CREDIT RELATED CO", 50000),
                                        ("2026-10-28", "IBG ALPHA SALARY", -2935.48),
                                        ("2026-10-28", "IBG BRAVO SALARY", -2800),
                                        ("2026-10-29", "INWARD TRANSFER UNKNOWN", 1500),
                                        ("2026-10-30", "SERVICE CHARGE", -12)]),
    (FCA, "2026-10", 5000, 4900, 0, [("2026-10-25", "CLAUDE.AI SUBSCRIPTION", -22.5)]),
    (CURRENT, "2026-08", 21000, None, 1, [("2026-08-28", "OLD BILL PAYMENT", -100)]),
    (CURRENT, "2026-09", 20000, None, 1, [("2026-09-15", "IBG FOXTROT CONSULTANT", -3000), ("2026-09-20", "CUSTOMER RECEIPT", 8000)]),
    (OPS, "2026-09", 1000, None, 1, [("2026-09-12", "UNKNOWN DEBIT", -75)]),  # XCO: a line left to explain
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
        (MAIN, "2026-09", 1, AISB, "2026-09", "Fund from"), (MAIN, "2026-09", 2, AISB, "2026-09", "Delta Consulting"),
        (MAIN, "2026-09", 3, AISB, "2026-09", "Salary Bravo"), (MAIN, "2026-09", 4, AISB, "2026-09", "Director allowance"),
        (MAIN, "2026-10", 1, AISB, "2026-10", "Printer lease"), (MAIN, "2026-10", 2, AISB, "2026-10", "Courier charges"),
        (MAIN, "2026-10", 3, AISB, "2026-09", "KWSP"), (MAIN, "2026-10", 4, AISB, "2026-10", "Transfer to AI"),
        (MAIN, "2026-10", 5, AISB, "2026-10", "Fund from"), (MAIN, "2026-10", 6, AISB, "2026-10", "Salary Alpha"),
        (MAIN, "2026-10", 7, AISB, "2026-10", "Salary Bravo"),
        (FCA, "2026-10", 1, AISB, "2026-10", "CLAUDE subscription claim"),  # a USD line on a ringgit payment
        (CURRENT, "2026-09", 1, AI, "2026-09", "Consultant Foxtrot"), (CURRENT, "2026-09", 2, AI, "2026-09", "Customer receipt")):
    j("post", f"/api/statement-lines/{line(acct, month, n)}", json={"payment_id": pay(eid, pmonth, desc)})
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Courier charges')}", json={"difference_note": "Discount given by the courier"})

# 6. An SQL listing (raw rows: the listing parser needs a real SQL Account export), its vouchers then linked by the route.
SQL = [  # doc no, date, description, amount, direction, doc type, kind, e-Invoice UIN, e-Invoice status, item (month, code)
    ("PV2609-001", "2026-09-28", "SALARY BRAVO SEP 2026", 2800, "out", "PV", "payment", None, None, None),
    ("PV2609-002", "2026-09-28", "DIRECTOR FEE SEP 2026", 2000, "out", "PV", "payment", None, None, None),
    ("PV2609-003", "2026-09-26", "DELTA CONSULTING SEP 2026", 5000, "out", "PV", "payment", None, None, None),
    ("OR2609-001", "2026-09-24", f"FUND FROM {RELATED} SEP 2026", 50000, "in", "OR", "payment", None, None, None),
    ("PV2610-001", "2026-10-20", "KWSP SEP 2026", 1200, "out", "PV", "payment", None, None, None),
    ("PV2610-002", "2026-10-06", "LHDN PCB SEP 2026", 400, "out", "PV", "payment", None, None, None),
    ("PV2610-003", "2026-10-28", "SALARY ALPHA OCT 2026", 2935.48, "out", "PV", "payment", None, None, None),
    ("PV2610-004", "2026-10-28", "SALARY BRAVO OCT 2026", 2800, "out", "PV", "payment", None, None, None),
    ("PV2610-005", "2026-10-27", "GOOGLE WORKSPACE CLAIM", 60, "out", "PV", "payment", "UIN-SB-005", "Validated", None),
    ("PV2610-010", "2026-10-25", "CLAUDE SUBSCRIPTION CLAIM", 95, "out", "PV", "payment", "UIN-SB-010", "Validated", None),
    ("OR2610-001", "2026-10-24", f"FUND FROM {RELATED} OCT 2026", 50000, "in", "OR", "payment", None, None, None),
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
for no, month, desc in (("PV2609-001", "2026-09", "Salary Bravo"), ("PV2609-002", "2026-09", "Director allowance"),
                        ("PV2609-003", "2026-09", "Delta Consulting"), ("OR2609-001", "2026-09", "Fund from"),
                        ("PV2610-001", "2026-09", "KWSP"), ("PV2610-002", "2026-09", "LHDN PCB"),
                        ("PV2610-003", "2026-10", "Salary Alpha"), ("PV2610-004", "2026-10", "Salary Bravo"),
                        ("PV2610-005", "2026-10", "GOOGLE Workspace"), ("PV2610-010", "2026-10", "CLAUDE subscription"),
                        ("OR2610-001", "2026-10", "Fund from")):  # OR2610-002 stays unlinked (Next up rule 7)
    j("post", f"/api/sql/entries/{SQLID[no]}", json={"payment_id": pay(AISB, month, desc)})

# 7. Paid dates typed in.
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Director allowance')}", json={"paid_date": "2026-10-28"})
j("patch", f"/api/payments/{pay(AISB, '2026-10', 'Staff claim Echo')}", json={"paid_date": "2026-10-22"})

# 8. Documents (small PDFs; one text file that won't print; one removed, one replaced; one of an unknown type).
old_slip = upload("payslip", "payslip Bravo Sep v1.pdf", payment_id=pay(AISB, "2026-09", "Salary Bravo"))
upload("payslip", "payslip Bravo Sep v2.pdf", payment_id=pay(AISB, "2026-09", "Salary Bravo"), replaces=old_slip)
upload("payslip", "payslip director Sep.pdf", payment_id=pay(AISB, "2026-09", "Director allowance"))
upload("invoice", "invoice Delta Sep.pdf", payment_id=pay(AISB, "2026-09", "Delta Consulting"))
upload("invoice", "invoice Foxtrot Sep.pdf", payment_id=pay(AI, "2026-09", "Consultant Foxtrot"))
upload("payslip", "payslip Alpha Oct.pdf", payment_id=pay(AISB, "2026-10", "Salary Alpha"))
for t in ("pv", "payslip", "bank"):
    upload(t, f"director Oct {t}.pdf", payment_id=pay(AISB, "2026-10", "Director allowance"))
upload("portal", "perkeso acknowledgement Oct.pdf", payment_id=pay(AISB, "2026-10", "PERKESO"))
upload("portal", "kwsp acknowledgement Oct.pdf", task_id=task(AISB, "2026-10", "kwsp"))
upload("claim", "claude claim form.pdf", payment_id=pay(AISB, "2026-10", "CLAUDE subscription"))
upload("approval", "claude claim approval.pdf", payment_id=pay(AISB, "2026-10", "CLAUDE subscription"))
upload("claim", "google claim form.pdf", payment_id=pay(AISB, "2026-10", "GOOGLE Workspace"))
upload("claim", "echo claim form.pdf", payment_id=pay(AISB, "2026-10", "Staff claim Echo"))
upload("approval", "transfer approval.pdf", payment_id=pay(AISB, "2026-10", "Transfer to AI"))
upload("approval", "budget approval Oct.pdf", task_id=task(AISB, "2026-10", "budget"))
upload("payroll", "payroll summary Oct.pdf", task_id=task(AISB, "2026-10", "payroll-calc"))
upload("invoice", "AI invoices Oct.pdf", task_id=task(AI, "2026-10", "invoices"))
gone = upload("bank", "delta bank slip wrong.pdf", payment_id=pay(AISB, "2026-10", "Delta Consulting"))
j("post", f"/api/documents/{gone}/remove", json={})
upload("other", "delta notes.txt", payment_id=pay(AISB, "2026-10", "Delta Consulting"), data=b"Notes, not a PDF.\n")


def unknown_doc(con):
    ent = con.execute("SELECT * FROM entities WHERE id = 1").fetchone()
    pid = con.execute("SELECT id FROM payments WHERE entity_id = 1 AND month = '2026-10' AND description LIKE 'Delta%'").fetchone()[0]
    docstore.store(con, entity=ent, month="2026-10", folder="misc", doc_type="misc", filename="delta misc.pdf",
                   data=pdf("delta misc"), payment_id=pid)


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
         (re.compile(r"Audit trail entry \d+ . check code \S+"), "<trail>"),
         (re.compile(r"\s+".join(map(re.escape, RELATED.split())), re.I), "<RELATED>"),
         (re.compile(re.escape(RELATED.split()[0]), re.I), "<RELATED>"),
         (re.compile(r"\s+".join(map(re.escape, TENANT.split())), re.I), "<TENANT>")]
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
NEXT_DATES = ["2026-10-28", "2026-11-01", "2026-11-04", "2026-11-13", "2026-11-16", "2026-12-01", "2026-12-08"]
# The words the payment type is guessed from (app._guess_category, one argument): every group, in the order it is
# tried, and the examples that pin the order.
GUESS_WORDS = ["CLAUDE.AI subscription", "Google Workspace", "ANTHROPIC", "OPENAI API", "CHATGPT PLUS", "MICROSOFT 365", "ADOBE CC",
               "ZOOM", "CANVA", "DROPBOX", "HOSTGATOR", "Annual SUBSCRIPTION", "Staff claim", "SALARY OCT", "Stamp duty",
               "SETEM", "CP204 instalment", "CP500", "TAX INSTALMENT", "KWSP Oct", "PERKESO", "LHDN PCB", "HASIL", "SOCSO",
               "Office RENTAL", "ELECTRIC bill", "BROADBAND", "TELEPHONE", "Printer toner", "PCB", "SALARY CLAIM", "KWSP CLAIM",
               "LHDN STAMP DUTY", "CLAIM FOR ZOOM SUBSCRIPTION", "SALARY KWSP", "RENTAL ELECTRIC", "TIMESTAMP", "zooming", "reclaims",
               "", None]
ACCOUNTS = [(AISB, MAIN), (AISB, FCA), (AI, CURRENT), (XCO, OPS)]
# Table columns as of update 20, so a column added later is not compared.
TASK_COLS = ("id", "entity_id", "month", "code", "title", "detail", "due_date", "required_docs", "done_at", "note", "sort")
PAYMENT_COLS = ("id", "entity_id", "month", "account_id", "payee_id", "category", "description", "amount", "currency",
                "amount_is_estimate", "due_date", "paid_date", "sql_ref", "einvoice_ref", "direction", "notes", "paid_source")


def clean(x):
    """Times dropped to whether they are set (a fixed clock gives them anyway), paths and links dropped, masks applied
    (to keys too)."""
    if isinstance(x, dict):
        return {clean(str(k)): (bool(v) if str(k).endswith("_at") and k not in KEEP_AT else clean(v)) for k, v in x.items() if k not in DROP}
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


def month_view(eid, month):
    """The month page of a company (GET /api/month), reduced to the keys it had before."""
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
    return {"set_up": v["set_up"], "before_first": v["before_first"], "closed_at": v["closed_at"], "tasks": tasks, "payments": pays}


def next_rows(days, entities=(None, AISB, AI, XCO)):
    """Next up (nextup.items, older_open, upcoming) on each day given, for every company and for one."""
    out = {}
    con = db.connect()
    try:
        con.execute("PRAGMA query_only = ON")
        for d in days:
            day = D.fromisoformat(d)
            for eid in entities:
                out[f"{d}:{eid}"] = {"items": [pick(r, ROW_KEYS) for r in nextup.items(con, day, eid)],
                                     "older": nextup.older_open(con, day, eid), "upcoming": nextup.upcoming(con, day, eid)}
    finally:
        con.close()
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

    s["month"] = {f"{eid}:{month}": month_view(eid, month) for eid in (AISB, AI, XCO) for month in MONTHS}

    s["overview"] = {}
    for month in MONTHS:
        v = j("get", f"/api/overview?month={month}")
        s["overview"][month] = [{"code": e["entity"]["code"], **pick(e, OVERVIEW_KEYS)} for e in v["entities"]]

    nx = j("get", "/api/next")
    s["next_route"] = {"today": nx["today"], "items": [pick(r, ROW_KEYS) for r in nx["items"]], "older": nx["older_open_months"],
                       "next_due": nx["next_due"]}
    s["nextup"] = next_rows(NEXT_DATES)
    con = db.connect()
    try:
        con.execute("PRAGMA query_only = ON")
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
        # The reminders each payee's dates give (db.reminders_for, read only).
        s["reminders_for"] = {p["name"]: {k: [v[0], v[1]] for k, v in db.reminders_for(con, p).items()}
                              for p in con.execute("SELECT * FROM payees ORDER BY id").fetchall()}
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
    # Whether Setup says a company has no monthly checklist (the note's wording may change; whether it is said may not).
    s["no_checklist_note"] = {eid: any("no monthly checklist" in n for n in j("get", f"/api/setup/entities/{eid}")["notes"])
                              for eid in (AISB, AI, XCO)}
    s["payee_usage"] = {p["name"]: j("get", f"/api/payees/{p['id']}/usage")
                        for p in q("SELECT id, name FROM payees WHERE start_date IS NOT NULL OR end_date IS NOT NULL ORDER BY id")}
    r1 = call("post", "/api/payees", 400, json={"entity_id": AISB, "name": "Bogus", "category": "bogus"})
    r2 = call("post", "/api/upload", 400, data={"doc_type": "bogus", "payment_id": str(pay(AISB, "2026-10", "Delta Consulting")),
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


# ---------- the probes that write, each from the same copy of the records folder ----------

def remove(path):
    """Removes a file or folder, documents too (the app stores them read-only)."""
    def force(fn, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        fn(p)
    if path.is_dir():
        shutil.rmtree(path, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))
    elif path.exists():
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


def save_folder(name):
    """A copy of the whole records folder (records.db, the audit head file, documents, packs), taken with every
    connection closed."""
    dst = tmp.with_name(tmp.name + "-" + name)
    remove(dst)
    shutil.copytree(tmp, dst)  # copy2: file times (the packs' are read) and read-only marks kept
    return dst


def restore(src):
    """Puts the records folder back as the copy has it."""
    for child in tmp.iterdir():
        remove(child)
    for child in src.iterdir():
        (shutil.copytree if child.is_dir() else shutil.copy2)(child, tmp / child.name)
    auditpack._PRINTS.clear()


def last_id(table):
    return one(f"SELECT COALESCE(MAX(id), 0) FROM {table}")


def activity_since(n):
    return [r["what"] for r in q("SELECT what FROM activity WHERE id > ? ORDER BY id", (n,))]


def task_rows(where="1", args=()):
    return q(f"SELECT {', '.join(TASK_COLS)} FROM tasks WHERE {where} ORDER BY entity_id, month, sort, id", args)


def reminder_rows():
    return task_rows("code LIKE 'joiner-%' OR code LIKE 'leaver-%'")


def payment_rows(after):
    return q(f"SELECT {', '.join(PAYMENT_COLS)} FROM payments WHERE id > ? ORDER BY id", (after,))


def probe_open():
    """A. Months set up after the update: their checklist rows, payments and the reminders that move into them."""
    a0, t0, p0 = last_id("activity"), last_id("tasks"), last_id("payments")
    asks = [(AISB, "2026-12", False), (AISB, "2026-07", False), (AI, "2026-11", False), (XCO, "2026-11", False),
            (AI, "2026-07", True), (AISB, "2026-12", False), (XCO, "2026-12", True), (AISB, "2027-01", True)]
    out = {"opened": [[eid, m, auto, j("post", "/api/months/open", json={"entity_id": eid, "month": m, "auto": auto})["opened"]]
                      for eid, m, auto in asks]}
    out["new_tasks"] = task_rows("id > ?", (t0,))
    out["tasks"] = {f"{eid}:{m}": task_rows("entity_id = ? AND month = ?", (eid, m))
                    for eid, m in ((AISB, "2026-12"), (AISB, "2026-07"), (AI, "2026-11"), (XCO, "2026-11"), (AISB, "2027-01"))}
    out["reminders"] = reminder_rows()
    out["payments"] = payment_rows(p0)
    out["month"] = {f"{eid}:{m}": month_view(eid, m)
                    for eid, m in ((AISB, "2026-12"), (AISB, "2026-07"), (AI, "2026-11"), (XCO, "2026-11"), (AISB, "2027-01"),
                                   (AISB, "2026-11"))}
    out["overview"] = {m: [{"code": e["entity"]["code"], **pick(e, OVERVIEW_KEYS)} for e in j("get", f"/api/overview?month={m}")["entities"]]
                       for m in ("2026-07", "2026-12", "2027-01")}
    out["nextup"] = next_rows(["2026-11-04", "2026-12-08", "2027-01-04", "2027-02-02"])
    out["activity"] = activity_since(a0)
    return out


PAYEE_FIELDS = ("id", "name", "category", "desc_template", "amount", "amount_varies", "month_offset", "due_day", "bank_details",
                "reference", "match_words", "notes", "account_id", "start_date", "end_date", "direction")


def save_payee(fields, expect=200):
    r = call("post", "/api/payees", expect, json=fields).get_json()
    return {k: r.get(k) for k in ("ok", "id", "changes", "kept", "error")}


def probe_payees():
    """B. Recurring payments saved after the update: the joiner and leaver reminders they add, move and remove."""
    a0 = last_id("activity")
    alpha, bravo = payee("Staff One (Alpha)"), payee("Staff Two (Bravo)")
    steps = []

    def step(name, fields, expect=200):
        if "id" in fields:  # the page sends the whole recurring payment, as saved, with the changes
            fields = {**q("SELECT * FROM payees WHERE id = ?", (fields["id"],))[0], **fields}
            fields = {k: v for k, v in fields.items() if k in PAYEE_FIELDS}
        steps.append([name, save_payee(fields, expect), [[t["code"], t["month"], t["due_date"], t["title"]] for t in reminder_rows()]])
        return steps[-1][1]

    charlie = step("a joiner on exactly RM 3,000 (no stamping)",
                   {"entity_id": AISB, "name": "Staff Three (Charlie)", "category": "salary", "amount": 3000, "due_day": 28,
                    "month_offset": 0, "account_id": MAIN, "start_date": "2026-10-20", "desc_template": "Salary Charlie - {M}"})["id"]
    step("over RM 3,000 now (stamping added)", {"id": charlie, "amount": 3200})
    step("a varying amount with no usual amount (stamping removed)", {"id": charlie, "amount": None, "amount_varies": 1})
    step("back over RM 3,000", {"id": charlie, "amount": 4000, "amount_varies": 0})
    # Start 20 Oct: the KWSP registration is due 27 Oct (October's cycle), e-CP22, PERKESO and stamping on 19 Nov
    # (after the rollover day, so November's cycle).
    ticked = task(AISB, "2026-10", f"joiner-kwsp-{charlie}")
    j("post", f"/api/tasks/{ticked}", json={"done": True})
    held = one("SELECT id FROM tasks WHERE code = ?", (f"joiner-perkeso-{charlie}",))
    upload("portal", "perkeso registration charlie.pdf", task_id=held)
    step("start date moved (the ticked one stays, the others move)", {"id": charlie, "start_date": "2026-11-10"})
    step("start date cleared (the held one is kept)", {"id": charlie, "start_date": None})
    step("a joiner's start date moved earlier", {"id": alpha, "start_date": "2026-09-28"})
    step("a joiner's start date cleared", {"id": alpha, "start_date": None})
    step("a leaver's last day brought forward", {"id": bravo, "end_date": "2026-11-15"})
    step("a leaver's last day later again", {"id": bravo, "end_date": "2027-02-28"})
    step("a leaver's last day cleared", {"id": bravo, "end_date": None})
    step("a joiner and leaver around the filed month",
         {"entity_id": AISB, "name": "Staff Six (India)", "category": "salary", "amount": 3100, "due_day": 28, "month_offset": 0,
          "account_id": MAIN, "start_date": "2026-07-01", "end_date": "2026-09-30", "desc_template": "Salary India - {M}"})
    # The CP22A is due 31 Aug (August's cycle) but went into September, as August is filed. With August reopened, the
    # next save moves it back, its due date unchanged.
    reopened = j("post", "/api/months/close", json={"entity_id": AISB, "month": "2026-08", "closed": False})
    steps.append(["August reopened", {"ok": reopened, "id": None, "changes": None, "kept": None, "error": None},
                  [[t["code"], t["month"], t["due_date"], t["title"]] for t in reminder_rows()]])
    step("saved again with August open (the CP22A moves back to its own month)",
         {"id": payee("Staff Six (India)"), "notes": "Fixed-term cover"})
    # August filed again with the CP22A in it; a later last day then moves it out of the filed month (due 1 Oct, in
    # September's cycle, before the rollover day).
    refiled = j("post", "/api/months/close", json={"entity_id": AISB, "month": "2026-08", "closed": True})
    steps.append(["August filed again", {"ok": refiled, "id": None, "changes": None, "kept": None, "error": None},
                  [[t["code"], t["month"], t["due_date"], t["title"]] for t in reminder_rows()]])
    step("a last day moved out of the filed month", {"id": payee("Staff Six (India)"), "end_date": "2026-10-31"})
    step("a joiner far ahead (waits in the latest month set up until its own is)",
         {"entity_id": AISB, "name": "Staff Seven (Juliet)", "category": "salary", "amount": 5000, "due_day": 28, "month_offset": 0,
          "account_id": MAIN, "start_date": "2027-03-02", "desc_template": "Salary Juliet - {M}"})
    step("a varying salary over RM 3,000 (stamping)",
         {"entity_id": AISB, "name": "Staff Eight (Kilo)", "category": "salary", "amount": 3500, "amount_varies": 1, "due_day": 28,
          "month_offset": 0, "account_id": MAIN, "start_date": "2026-11-02", "desc_template": "Salary Kilo - {M}"})
    step("a director with a start date (no reminders)",
         {"entity_id": AISB, "name": "Director Three (Lima)", "category": "director", "amount": 4000, "due_day": 28,
          "month_offset": 0, "account_id": MAIN, "start_date": "2026-10-15"})
    step("a salary in a company that runs no payroll (no reminders)",
         {"entity_id": XCO, "name": "Staff Nine (Mike)", "category": "salary", "amount": 3500, "due_day": 28, "month_offset": 0,
          "account_id": OPS, "start_date": "2026-10-15", "end_date": "2026-12-31"})
    step("a salary changed to another type (reminders removed)",
         {"id": payee("Staff Eight (Kilo)"), "category": "consultant"})
    step("refused: last day before the start", {"id": payee("Staff Six (India)"), "end_date": "2026-06-30"}, 400)
    stopped = {"stop": j("post", f"/api/payees/{payee('Staff Seven (Juliet)')}/stop", json={"reason": "test: left before starting"}),
               "use": j("post", f"/api/payees/{payee('Staff Seven (Juliet)')}/use", json={"reason": "test: starting after all"})}
    return {"steps": steps, "stop_use": stopped, "reminders": reminder_rows(),
            "usage": {p["name"]: j("get", f"/api/payees/{p['id']}/usage") for p in q("SELECT id, name FROM payees ORDER BY id")},
            "month": {m: month_view(AISB, m) for m in ("2026-09", "2026-10", "2026-11")},
            "nextup": next_rows(["2026-11-04", "2026-11-13", "2026-12-01"], (None, AISB, XCO)),
            "activity": activity_since(a0)}


def probe_filing():
    """C. Months marked as filed after the update (the audit pack item ticked), and one reopened."""
    a0 = last_id("activity")
    out = {"close": [[eid, m, closed, j("post", "/api/months/close", json={"entity_id": eid, "month": m, "closed": closed})]
                     for eid, m, closed in ((AISB, "2026-09", True), (AI, "2026-09", True), (XCO, "2026-09", True),
                                            (AISB, "2026-09", False), (AISB, "2026-10", True))]}
    out["tasks"] = {f"{eid}:{m}": task_rows("entity_id = ? AND month = ?", (eid, m))
                    for eid, m in ((AISB, "2026-09"), (AI, "2026-09"), (XCO, "2026-09"), (AISB, "2026-10"))}
    out["month"] = {f"{eid}:{m}": month_view(eid, m) for eid, m in ((AISB, "2026-09"), (AISB, "2026-10"), (AI, "2026-09"))}
    out["readiness"] = {m: pick(j("get", f"/api/audit-readiness?entity_id={AISB}&month={m}"), ("closed_at", "still_open", "ready"))
                        for m in ("2026-09", "2026-10")}
    out["nextup"] = next_rows(["2026-11-04"])
    out["activity"] = activity_since(a0)
    return out


def listing(rows):
    head = ["Doc No", "Doc Type", "Doc Date", "Description", "Company Name", "Amount", "e-Invoice UUID"]
    return "\n".join("\t".join(str(c) for c in r) for r in [head] + rows) + "\n"


SQL_AISB = [  # pasted rows of an SQL listing for AISB
    ("JV2611-001", "JV", "2026-11-30", "PAYROLL ACCRUAL NOVEMBER 26", "", "9100.10", ""),
    ("JV2610-009", "JV", "2026-11-02", "SALARIES AND WAGES OCT 2026", "", "7735.48", ""),
    ("JV2611-002", "JV", "2026-11-30", "DEPRECIATION NOV 2026", "", "512.40", ""),
    ("JV2611-003", "JV", "2026-11-30", "GAJI STAF NOV 2026", "", "1200.20", ""),
    ("IV2611-001", "IV", "2026-11-24", "MONTHLY OPERATING EXPENSES NOVEMBER 26", RELATED, "50000.00", "UIN-IV-201"),
    ("OR2611-001", "OR", "2026-11-24", f"FUND FROM {RELATED} NOV 2026", "", "50000.00", ""),
    ("PV2611-050", "PV", "2026-11-20", f"RECHARGE TO {RELATED}", "", "1234.56", ""),
    ("IV2611-003", "IV", "2026-11-03", "RENTAL CHARGE FOR NOVEMBER 26", TENANT, "1500.00", "UIN-IV-203"),
    ("PV2611-051", "PV", "2026-11-25", "CANVA PRO SUBSCRIPTION NOV", "", "49.90", "UIN-SB-051"),
    ("OR2611-052", "OR", "2026-11-26", "REFUND OF DEPOSIT", "", "300.25", "UIN-OR-052"),
    ("PI2611-001", "PI", "2026-11-12", "PAYROLL SERVICE FEE NOV 2026", "Example Payroll Bureau", "150.75", ""),
    ("JV2701-001", "JV", "2027-01-15", "WAGES JANUARY 2027", "", "8000.30", ""),
    ("PV2611-060", "PV", "2026-11-27", "GAJI GOLF NOV 2026", "", "2700.15", ""),
    ("PV2611-061", "PV", "2026-11-27", "GOLF BONUS NOV 2026", "", "2990.35", ""),
    ("PV2611-062", "PV", "2026-11-27", "HOTEL ALL'CE NOV 2026", "", "1800.45", ""),
    ("PV2611-063", "PV", "2026-11-27", "HOTEL TRAVEL NOV 2026", "", "1990.55", ""),
    ("PV2612-064", "PV", "2026-12-01", "KILO WATER NOV 2026", "", "180.65", ""),
]
SQL_AI = [  # and for AI, a company without these checklist items
    ("JV2610-101", "JV", "2026-10-31", "PAYROLL OCT 2026", "", "4000.40", ""),
    ("IV2610-101", "IV", "2026-10-24", "SERVICES OCTOBER 26", RELATED, "8000.00", "UIN-IV-301"),
    ("PV2610-101", "PV", "2026-10-25", "DROPBOX PLAN OCT", "", "70.70", "UIN-SB-101"),
]
REC_KEYS = ("row", "doc_no", "date", "description", "payee", "amount", "direction", "einvoice", "doc_type", "kind", "task_id",
            "task_title", "payment_id", "payment_desc", "exists", "picked", "linked_to", "linked_amount")


def probe_sql_preview():
    """D. SQL listings previewed after the update: the checklist item each document is filed on, by its words, and the
    payments suggested, the salary words deciding between estimates."""
    before = rows_of()
    out = {}
    for eid, rows in ((AISB, SQL_AISB), (AI, SQL_AI)):
        r = j("post", "/api/sql/preview", json={"entity_id": eid, "text": listing(rows)})
        out[eid] = {"header_row": r["header_row"], "headers": r["headers"], "mapping": r["mapping"], "fields": [f for f in r["fields"] if f not in LATER_SQL_FIELDS],
                    "records": [pick(x, REC_KEYS) for x in r["records"]], "candidates": r["candidates"]}
    out["records_unchanged"] = rows_of() == before
    return out


GUESS_SQL = [  # doc no, date, description, payee, amount, direction, e-Invoice: vouchers added as payments, type guessed
    ("PV2611-101", "2026-11-05", "SALARY CLAIM NOV", None, 111.11, "out", None),
    ("PV2611-102", "2026-11-05", "LHDN STAMP DUTY", None, 112.12, "out", None),
    ("PV2611-103", "2026-11-05", "SALARY KWSP", None, 113.13, "out", None),
    ("PV2611-104", "2026-11-05", "ADOBE SUBSCRIPTION NOV", None, 114.14, "out", "UIN-SB-104"),
    ("PV2611-105", "2026-11-06", "ANNUAL SUBSCRIPTION RENEWAL", None, 115.15, "out", None),
    ("PV2611-106", "2026-11-06", "CLAIM FOR ZOOM SUBSCRIPTION", None, 116.16, "out", None),
    ("PV2611-107", "2026-11-06", "KWSP CLAIM", None, 117.17, "out", None),
    ("PV2611-108", "2026-11-06", "CP204 INSTALMENT NOV", None, 118.18, "out", None),
    ("PV2611-109", "2026-11-07", "TAX INSTALMENT", None, 119.19, "out", None),
    ("PV2611-110", "2026-11-07", "SETEM HASIL", None, 120.20, "out", None),
    ("PV2611-111", "2026-11-07", "CP500 PAYMENT", None, 121.21, "out", None),
    ("PV2611-112", "2026-11-07", "PERKESO NOV 2026", None, 122.22, "out", None),
    ("PV2611-113", "2026-11-08", "HASIL PCB", None, 123.23, "out", None),
    ("PV2611-114", "2026-11-08", "SOCSO ARREARS", None, 124.24, "out", None),
    ("PV2611-115", "2026-11-08", "LHDN PCB NOV", None, 125.25, "out", None),
    ("PV2611-116", "2026-11-08", "RENTAL OHM RECHARGE", None, 126.26, "out", None),
    ("PV2611-117", "2026-11-09", "OHM ELECTRIC NOV", None, 127.27, "out", None),
    ("PV2611-118", "2026-11-09", "BROADBAND BIZ NOV", None, 128.28, "out", None),
    ("PV2611-119", "2026-11-09", "TELEPHONE NOV", None, 129.29, "out", None),
    ("PV2611-120", "2026-11-09", "PRINTER TONER", None, 130.30, "out", None),
    ("PV2611-121", "2026-11-10", "TIMESTAMP SERVICE", None, 131.31, "out", None),
    ("PV2611-122", "2026-11-10", "OFFICE RENTAL NOV", None, 132.32, "out", None),
    ("PV2611-123", "2026-11-10", None, "Some Vendor", 133.33, "out", None),
    ("OR2611-124", "2026-11-10", "CUSTOMER DEPOSIT SALARY", None, 134.34, "in", None),
    ("JV2611-125", "2026-11-11", "SALARY JOURNAL", None, 135.35, None, None),  # no direction: left for a person
    ("PV2611-126", "2026-11-11", "GOOGLE CLOUD NOV", None, 136.36, "out", None),  # these three one by one
    ("PV2611-127", "2026-11-11", "MISC ITEM", None, 137.37, "out", None),
    ("PV2611-128", "2026-11-11", "MISC REFUNDABLE", None, 138.38, "out", None),
]
LATER_SQL = [("PV2611-131", "2026-11-12", "OFFICE RENTAL DEC", None, 141.41, "out", None),
             ("PV2611-132", "2026-11-12", "RENTAL OF PROJECTOR", None, 142.42, "out", None)]


def add_entries(rows):
    def run(con):
        imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (1, 'Cash book.xlsx', ?, ?, 0)",
                          (FIXED_NOW, len(rows))).lastrowid
        return {no: con.execute(
            """INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, einvoice, doc_type,
               kind, status) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'payment', 'unlinked')""",
            (imp, no, d, desc, who, amt, way, uin, re.match(r"[A-Z]*", no).group(0))).lastrowid
            for no, d, desc, who, amt, way, uin in rows}
    return raw("SQL cash book rows", run)


def probe_create():
    """E. SQL vouchers added as payments after the update, their payment type guessed from the description."""
    a0, p0 = last_id("activity"), last_id("payments")
    ids = add_entries(GUESS_SQL)
    out = {"one_by_one": [j("post", f"/api/sql/entries/{ids[no]}", json={"create_payment": cp})
                          for no, cp in (("PV2611-126", {}), ("PV2611-127", {"category": "utility"}),
                                         ("PV2611-128", {"category": "receipt"}))]}
    out["create_all"] = j("post", "/api/sql/entries/create-all", json={"entity_id": AISB})
    out["payments"] = payment_rows(p0)
    # A guessed type that is stopped gives Other payment.
    rental = one("SELECT id FROM payment_types WHERE key = 'rental'")
    out["stop_rental"] = call("post", f"/api/setup/payment_types/{rental}/stop", json={"reason": "test: no more rent"}).status_code
    p1 = last_id("payments")
    add_entries(LATER_SQL)
    out["create_all_after_stop"] = j("post", "/api/sql/entries/create-all", json={"entity_id": AISB})
    out["payments_after_stop"] = payment_rows(p1)
    out["entries"] = q("SELECT doc_no, status, payment_id FROM sql_entries WHERE entity_id = 1 ORDER BY id")
    out["activity"] = activity_since(a0)
    return out


PROBES = [("open", probe_open), ("payees", probe_payees), ("filing", probe_filing), ("sql_preview", probe_sql_preview),
          ("create", probe_create)]


def probes(base):
    """Each probe from the same copy of the records folder; the folder is left as the copy has it."""
    out = {}
    for name, fn in PROBES:
        restore(base)
        out[name] = fn()
    restore(base)
    return json.loads(json.dumps(clean(out), sort_keys=True, default=str))


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


# Column pickers a later update adds to the SQL page (update 22 keeps an entry's SQL code, payment method, cheque number,
# document key and currency): left out of the snapshot, as the column guesses and records themselves are compared.
LATER_SQL_FIELDS = ("code", "payment_method", "cheque_no", "dockey", "currency_code")


# The columns each table had the first time it was read (before the remaining updates): a later update may add columns,
# which are compared apart: they must still be empty.
_COLS = {}


def _known(r, t):
    have = [c[1] for c in r.execute(f'PRAGMA table_info("{t}")')]
    cols = _COLS.setdefault(t, have)
    rows = [tuple(x) for x in r.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{t}" ORDER BY rowid')]
    new = [c for c in have if c not in cols]
    filled = bool(new) and r.execute(f'SELECT 1 FROM "{t}" WHERE {" OR ".join(chr(34) + c + chr(34) + " IS NOT NULL" for c in new)}').fetchone()
    return rows, filled


def rows_of(tables=("payments", "tasks", "documents", "sql_entries", "statement_lines", "statements", "months", "payees",
                    "budget_lines", "budgets")):
    r = sqlite3.connect(config.DB_PATH)
    out = {}
    try:
        for t in tables:
            out[t], filled = _known(r, t)
            if filled:
                out[t + " (columns a later update added)"] = "not empty"
        return out
    finally:
        r.close()


# ---------- coverage: the seed and the probes can't quietly lose a case ----------
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
    check("coverage: Next up joins KWSP, PERKESO and e-PCB due the same day into one submit row",
          any(r["rule"] == 1 and re.match(r"^Submit \w{3} KWSP, PERKESO and e-PCB \(legal deadline \d+ \w{3}\)$", r["text"]) for r in rows),
          sorted({r["text"] for r in rows if r["rule"] == 1}))
    check("coverage: Next up lists a person's reminders due together in one row (rule 2)",
          any(r["rule"] == 2 and re.search(r": [^,]+, [^,]+ and ", r["text"]) for r in rows),
          sorted({r["text"] for r in rows if r["rule"] == 2}))
    xco = {r["rule"]: r for r in rows if r["entity"] == "XCO"}
    check("coverage: Next up statement and closing rows for a company without a checklist (rules 6, 7, 9, 11)",
          {6, 7, 9, 11} <= set(xco) and xco[6]["due"] == "2026-11-05" and xco[9]["due"] == "2026-10-10", sorted(xco))
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
    check("coverage: a receipt's invoice shown by the e-Invoice filed on the fund-received item",
          any(p["direction"] == "in" and "invoice" in p["evidence"] and p["evidence"]["invoice"]["ref"].startswith("e-Invoice")
              for p in pays), [p["evidence"].get("invoice") for p in pays if p["direction"] == "in"])
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
    check("coverage: Setup notes the company with no checklist only", s["no_checklist_note"] == {"1": False, "2": False, "3": True},
          s["no_checklist_note"])
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
    check("coverage: payee usage counts joiner and leaver reminders",
          any(n for v in s["payee_usage"].values() for label, n in v["used_by"] if "reminder" in label))
    guess = dict((w or "", c) for w, c in s["guess"])
    check("coverage: every type guess group and the precedence examples",
          {"claim_overseas", "claim", "salary", "other", "statutory", "rental", "utility"} == set(guess.values())
          and guess["SALARY CLAIM"] == "claim" and guess["LHDN STAMP DUTY"] == "other" and guess["SALARY KWSP"] == "salary"
          and guess["CLAIM FOR ZOOM SUBSCRIPTION"] == "claim_overseas" and guess["RENTAL ELECTRIC"] == "rental", guess)
    check_no_names("coverage: no snapshot holds the related company's or the tenant's name", s)


def check_no_names(name, s):
    words = {RELATED.split()[0].lower(), TENANT.lower()}  # the tenant's first word alone is a common word
    leak = [k for k, v in flat(s).items() if any(w in (k + " " + str(v)).lower() for w in words)]
    check(name, not leak, [k[:120] for k in leak[:10]])


def probe_coverage(p):
    check_no_names("probes: none holds the related company's or the tenant's name", p)
    o = p["open"]
    check("probe A: months opened after the update (a later month, an earlier one, a company without a checklist; "
          "none automatically before tracking, none twice)",
          [x[3] for x in o["opened"]] == [True, True, True, True, False, False, True, True], o["opened"])
    items = {k: [t for t in v if not t["code"].startswith(("joiner-", "leaver-"))] for k, v in o["tasks"].items()}
    check("probe A: the checklist written in its order (AISB 15 items, AI 5, XCO none) with due dates by month",
          [len(items[k]) for k in ("1:2026-12", "1:2026-07", "2:2026-11", "3:2026-11")] == [15, 15, 5, 0]
          and [t["sort"] for t in o["tasks"]["1:2026-12"]] == sorted(t["sort"] for t in o["tasks"]["1:2026-12"]),
          {k: len(v) for k, v in items.items()})
    check("probe A: a reminder moves into the month set up", any(t["month"] in ("2026-12", "2027-01") for t in o["reminders"]),
          o["reminders"])
    b = p["payees"]
    lines = [x for _, r, _ in b["steps"] for x in (r["changes"] or []) + (r["kept"] or [])]
    for what, rx in (("added", r": added "), ("now due", r" now due "), ("removed", r": removed "), ("kept, filed on it", r"as a document is filed on it"),
                     ("moved", r"^\w+ \d{4}: .* moved from \w+ \d{4}$"),
                     ("moved out of a filed month", r"moved from \w+ \d{4}, which is marked as filed"),
                     ("waits in the latest month set up", r"\(moves to \w+ \d{4} once that month is set up\)")):
        check(f"probe B: a reminder change line '{what}'", any(re.search(rx, x) for x in lines), lines)
    stamp = lambda i: [c for c, *_ in b["steps"][i][2] if c.startswith("joiner-stamp-")]
    check("probe B: stamping only for a salary over RM 3,000 (not exactly 3,000, not a varying salary with no amount)",
          not any(c.endswith(f"-{b['steps'][0][1]['id']}") for c in stamp(0)) and any(c.endswith(f"-{b['steps'][0][1]['id']}") for c in stamp(1))
          and not any(c.endswith(f"-{b['steps'][0][1]['id']}") for c in stamp(2)))
    by_step = {n: {c: (m, due) for c, m, due, _ in rows} for n, _, rows in b["steps"]}
    charlie = b["steps"][0][1]["id"]
    check("probe B: a ticked reminder stays where it is when the start date moves; one not ticked moves",
          by_step["start date moved (the ticked one stays, the others move)"].get(f"joiner-kwsp-{charlie}") == ("2026-10", "2026-10-27")
          and by_step["start date moved (the ticked one stays, the others move)"].get(f"joiner-stamp-{charlie}") == ("2026-11", "2026-12-10"),
          by_step["start date moved (the ticked one stays, the others move)"])
    kilo = next(r["id"] for n, r, _ in b["steps"] if n == "a varying salary over RM 3,000 (stamping)")
    check("probe B: a varying salary with a usual amount over RM 3,000 gets the stamping reminder, removed when no longer a salary",
          f"joiner-stamp-{kilo}" in by_step["a varying salary over RM 3,000 (stamping)"]
          and not any(c.endswith(f"-{kilo}") for c in by_step["a salary changed to another type (reminders removed)"]))
    india = by_step["saved again with August open (the CP22A moves back to its own month)"]
    check("probe B: a reminder past a filed month moves back when the month is reopened, and out when it is filed again",
          [by_step[n].get(c) for n in ("a joiner and leaver around the filed month",
                                       "saved again with August open (the CP22A moves back to its own month)",
                                       "a last day moved out of the filed month")
           for c in [next(c for c in india if c.startswith("leaver-cp22a-"))]]
          == [("2026-09", "2026-08-31"), ("2026-08", "2026-08-31"), ("2026-09", "2026-10-01")], india)
    check("probe B: no reminders for a director or in a company that runs no payroll",
          not any(c.endswith(f"-{r['id']}") for n, r, rows in b["steps"] if n.startswith(("a director", "a salary in a company"))
                  for c in by_step[n]))
    check("probe B: a refused save refused", any(r["error"] for _, r, _ in b["steps"]))
    c = p["filing"]
    check("probe C: filing ticks the audit pack item where there is one",
          [x[3]["pack_ticked"] for x in c["close"]] == [True, True, False, True, True], c["close"])
    d = p["sql_preview"]
    recs = {r["doc_no"]: r for r in d["1"]["records"]}
    filed = {no: (r["task_title"] or "").split(":")[0] for no, r in recs.items()}
    check("probe D: documents filed on checklist items by their words (journals, the related company, self-billed)",
          recs["JV2611-001"]["task_id"] and recs["JV2610-009"]["task_id"] and recs["JV2611-003"]["task_id"]
          and recs["IV2611-001"]["task_id"] and recs["OR2611-001"]["task_id"] and recs["PV2611-051"]["task_id"]
          and recs["JV2701-001"]["task_id"] and recs["IV2611-003"]["task_id"]
          and not any(recs[n]["task_id"] for n in ("JV2611-002", "PV2611-050", "OR2611-052", "PI2611-001")), filed)
    check("probe D: each filed on its item (payroll journal, related company, tenant's rental e-Invoice, self-billed)",
          [recs[n]["task_title"].split(" (")[0].split(":")[0] for n in ("JV2611-001", "IV2611-001", "OR2611-001", "IV2611-003", "PV2611-051")]
          == ["Salary PVs in SQL", "Fund received from <RELATED>", "Fund received from <RELATED>",
              "e-Invoice to the office tenant for rental", "Self-billed e-Invoices for overseas providers"], filed)
    check("probe D: a company without those items files nothing", not any(r["task_id"] for r in d["2"]["records"]))
    golf, bonus = recs["PV2611-060"], recs["PV2611-061"]
    check("probe D: the salary words pick the estimated salary's voucher (GAJI, not the nearer amount)",
          golf["payment_id"] and not bonus["payment_id"] and (golf["payment_desc"] or "").startswith("Salary Golf"), [golf, bonus])
    check("probe D: the director words pick the estimated director payment's voucher (ALL'CE)",
          recs["PV2611-062"]["payment_id"] and not recs["PV2611-063"]["payment_id"], [recs["PV2611-062"], recs["PV2611-063"]])
    check("probe D: an estimate of a type with no salary words takes the nearest voucher", recs["PV2612-064"]["payment_id"])
    check("probe D: the preview leaves the records as they were", d["records_unchanged"] is True)
    e = p["create"]
    made = {r["sql_ref"]: r["category"] for r in e["payments"] + e["payments_after_stop"]}
    check("probe E: each guess group and the precedence examples",
          made.get("PV2611-101") == "claim" and made.get("PV2611-102") == "other" and made.get("PV2611-103") == "salary"
          and made.get("PV2611-104") == "claim_overseas" and made.get("OR2611-124") == "receipt"
          and {"claim_overseas", "claim", "salary", "other", "statutory", "rental", "utility", "receipt"} <= set(made.values())
          and "JV2611-125" not in made, made)
    check("probe E: one by one: guessed, chosen, a money-in type refused for money out",
          [made.get(n) for n in ("PV2611-126", "PV2611-127", "PV2611-128")] == ["claim_overseas", "utility", "other"])
    check("probe E: a stopped type guessed gives Other payment",
          e["stop_rental"] == 200 and made.get("PV2611-131") == "other" and made.get("PV2611-132") == "other")


# ---------- names taken out (Phase 7) ----------
GUESS_RENAMED = (25, 35)  # GUESS_WORDS: the utility example and the rental one that named it


def renamed(golden, s, p):
    """[(old name, new name, mask)]: each old name read from the golden by key (see the docstring)."""
    new_pays, old_pays = s["month"]["1:2026-10"]["payments"], golden["S"]["month"]["1:2026-10"]["payments"]
    k = next(i for i, x in enumerate(new_pays) if x["description"].split()[0] == "OHM")
    check("the golden has the payment <UTILITY> stands for at the same place",
          old_pays[k]["id"] == new_pays[k]["id"] and old_pays[k]["category"] == new_pays[k]["category"] == "utility")
    out = [(old_pays[k]["description"].split()[0], "OHM", "<UTILITY>")]
    made = lambda x, no: next(r["description"] for r in x["create"]["payments"] if r["sql_ref"] == no)
    for no, mask in (("PV2611-118", "<TELCO1>"), ("PV2611-119", "<TELCO2>")):
        old, new = made(golden["P"], no).split(), made(p, no).split()
        n = 0
        while n < min(len(old), len(new)) - 1 and old[-1 - n] == new[-1 - n]:
            n += 1  # the words both end with (BIZ NOV) are not the name
        out.append((" ".join(old[:len(old) - n]), " ".join(new[:len(new) - n]), mask))
    return out


def masked(x, names):
    """x with each name masked as a whole word or words, in keys and values, any case; the first company's budget
    item's detail blanked (the other company's is compared)."""
    rxs = [(re.compile(r"\b" + r"\s+".join(map(re.escape, n.split())) + r"\b", re.I), m) for n, m in names]

    def walk(v):
        if isinstance(v, dict):
            out = {walk(k): walk(w) for k, w in v.items()}
            if out.get("code") == "budget" and "detail" in out and out.get("entity_id") == AISB:
                out["detail"] = "<budget detail>"
            return out
        if isinstance(v, list):
            return [walk(w) for w in v]
        if isinstance(v, str):
            for rx, m in rxs:
                v = rx.sub(m, v)
        return v
    return walk(x)


# ---------- run ----------
S0 = snapshot()
same("the snapshot is deterministic (S0 taken twice)", S0, snapshot())
coverage(S0)
raw0 = rows_of()
print(f"S0: {len(json.dumps(S0))} characters; /api/meta keys beyond the old ones: {S0['meta_new_keys'] or 'none'}")

base0 = save_folder(f"update{CUT}")
P0 = probes(base0)
same("the probes are deterministic (P0 taken twice, each from the same copy)", P0, probes(base0))
probe_coverage(P0)
check("the records folder is back as it was after the probes", rows_of() == raw0)
print(f"P0: {len(json.dumps(P0))} characters")
if OPTS.write_golden:
    Path(OPTS.write_golden).write_text(json.dumps({"S": S0, "P": P0}, sort_keys=True, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"golden written: {OPTS.write_golden}")

# Update 30 adds a new checklist item, SQL books agree with SQL Account, to each company kept in SQL, by design (it is
# proved in sql_books_item_test). The proof runs its table change only (the items table may then hold the new kind),
# so the item doesn't show here as a difference. On code without update 30 nothing is replaced.
_books = next((i for i, s in enumerate(full) if getattr(s, "__name__", "") == "install_sql_books"), None)
if _books is not None:
    full = full[:_books] + [sys.modules[full[_books].__module__]._widen_completions] + full[_books + 1:]
db.MIGRATIONS[:] = full
db.init()
patch_clock()
check("every update has run", one("PRAGMA user_version") == len(full))
print(f"updates run after the cut: {len(full) - CUT}")
S1 = snapshot()
print(f"S1: /api/meta keys beyond the old ones: {S1['meta_new_keys'] or 'none'}")
check("no key of /api/meta named like 'inactive' lists anything", not S1["meta"]["inactive"], S1["meta"]["inactive"])
same(f"S0 (update {CUT}) equals S1 (every update)", S0, S1)
raw1 = rows_of()
check("the records' rows are unchanged by the remaining updates", raw0 == raw1,
      [t for t in raw0 if raw0[t] != raw1.get(t)])
base1 = save_folder("updated")
P1 = probes(base1)
same(f"P0 (probes at update {CUT}) equals P1 (the same probes after every update)", P0, P1)
if OPTS.golden:
    golden = json.loads(Path(OPTS.golden).read_text(encoding="utf-8"))
    pairs = renamed(golden, S0, P0)
    keep = ("/meta_new_keys",) + tuple(f"/guess[{i}][0]" for i in GUESS_RENAMED)
    golden = masked(golden, [(old, m) for old, _, m in pairs])
    check("the golden holds none of the old names once masked", not any(
        re.search(r"\b" + re.escape(old.split()[0]) + r"\b", f"{k} {v}", re.I) for old, _, _ in pairs
        for k, v in flat(golden).items() if not k.startswith(tuple("/S" + x for x in keep))))
    new = lambda x: masked(x, [(n, m) for _, n, m in pairs])
    same("S0 equals the golden snapshot from before Phase 5", golden["S"], new(S0), keep)
    same("S1 equals the golden snapshot from before Phase 5", golden["S"], new(S1), keep)
    same("P0 equals the golden probes from before Phase 5", golden["P"], new(P0))
    same("P1 equals the golden probes from before Phase 5", golden["P"], new(P1))
for d in (base0, base1):
    remove(d)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
