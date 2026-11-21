"""Slice 1: the Overview's 13 cards (hrp/overview.py, GET /api/overview/<card>) and the page that draws them
(static/js/pages/overview.js), on made-up records only.

Three made-up companies: one kept in SQL Account with a month of payments, a bank statement, a stored budget and SQL books
(customers and suppliers, sales and expenses), one kept here whose month is filed, and one kept in SQL Account with nothing
fetched and its month before the first month tracked. The server part checks each card's figures against what the records
hold (worked out by hand here, or read from the page the card links to: the month's checklist, the Budget), the Customers
overdue rules (only balances older than 30 days count, balances brought forward from before tracking shown apart as Before
tracking), the empty and out-of-date states, that a card that fails leaves the others answering, and the "Never on the
Overview" list: no pay figure, IC or registration number, bank account number, bank details or address in any card's answer
or in Recent activity.

The page part runs the page script in Node against a small stand-in for the page, with the server's answers: every card drawn
in its row, each card's link and each Needs attention counter opening its page (or its interim landing: today's Books tabs
until slice 7), the HR cards and Requests waiting with no link, Paid without approval hidden, one card that can't load
saying "Could not load, try again" while the others show (and Try again reading that card alone), the company lines with All
companies, one company's Overview, a company with nothing yet, the rollover banner counting the rows of the company it names,
and Add a payment asking which company from the Overview.

Run: .venv\\Scripts\\python -m synthetic_tests.overview_cards_test
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-overview-cards-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, nextup  # noqa: E402
from hrp import overview as ov  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

ACCT_NO, BANK_DETAILS, REG_NO, ADDRESS = "000-555-1234", "Example Bank 9988776655", "200101012345", "12 Example Road, Test Town"
SALARY = 98765.43
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": ACCT_NO}]},
    {"code": "EXH", "name": "Example Here Trading", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-202"}]},
    {"code": "EXN", "name": "Example New Sdn Bhd", "accounts": [{"label": "Operating", "bank": "Example Bank", "number": "000-303"}]},
]}), encoding="utf-8")

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:900])


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


def write(why, *statements):
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
    finally:
        con.disarm()
        con.close()


def S(rm):
    return int(round(rm * 100))


meta = j("get", "/api/meta")
ids = {e["code"]: e["id"] for e in meta["entities"]}
EXA, EXH, EXN = ids["EXA"], ids["EXH"], ids["EXN"]
acct = {e["code"]: e["accounts"][0]["id"] for e in meta["entities"]}
M, TODAY = "2026-10", date(2026, 11, 20)

# ---------- the records ----------
j("post", "/api/setup/checklist", json={"action": "add", "entity_id": EXA, "from_month": M,
                                         "fields": {"completion": "hand", "title": "File the portal receipt", "detail": "", "due_offset": 0, "due_day": 20, "docs": ["portal"]}})
for e in (EXA, EXH):
    j("post", "/api/months/open", json={"entity_id": e, "month": M})
j("post", "/api/months/open", json={"entity_id": EXA, "month": "2026-11"})
write("the first month tracked, an address and a registration number",
      ("UPDATE entities SET first_month = '2026-11' WHERE id = ?", (EXN,)),
      ("UPDATE entities SET address = ?, old_reg_no = ? WHERE id = ?", (ADDRESS, REG_NO, EXA)),
      ("INSERT INTO payees (entity_id, name, category, desc_template, amount, bank_details, active) VALUES (?, 'Test Payee', 'other', 'Test Payee', 10, ?, 0)",
       (EXA, BANK_DETAILS)))


def pay(eid, desc, cat, amount, due, paid=None):
    body = {"entity_id": eid, "month": M, "description": desc, "category": cat, "amount": amount,
            "account_id": acct["EXA" if eid == EXA else "EXH"], "due_date": due, "paid_date": paid}
    return j("post", "/api/payments", json=body)["id"]


lease = pay(EXA, "Office lease - test", "other", 1200, "2026-10-05", "2026-10-05")
j("patch", f"/api/payments/{lease}", json={"sql_ref": "PV-TEST-001"})
internet = pay(EXA, "Internet - test", "utility", 200, "2026-10-20", "2026-10-20")
water = pay(EXA, "Water bill - test", "utility", 45, "2026-10-20")
cleaning = pay(EXA, "Cleaning service - test", "other", 300, "2026-11-18")
salary = pay(EXA, "Salaries - test", "salary", SALARY, "2026-11-19")
kwsp = pay(EXA, "KWSP", "statutory", 1500, "2026-11-15")
courier = pay(EXA, "Courier - test", "other", 85.5, "2026-11-25")
printer = pay(EXA, "Printer lease - test", "other", 410, "2026-12-10")
here_bill = pay(EXH, "Electricity - test", "utility", 60, "2026-11-10")
# EXN, tracked from November: a salary is all it has to pay (one person's pay), and a director's fee paid in part.
NPAY, NDIR = 4321.09, 2650
j("post", "/api/months/open", json={"entity_id": EXN, "month": "2026-11"})
n_salary = j("post", "/api/payments", json={"entity_id": EXN, "month": "2026-11", "description": "Salary - Test Payee", "category": "salary",
                                            "amount": NPAY, "account_id": acct["EXN"], "due_date": "2026-11-15"})["id"]
n_dir = j("post", "/api/payments", json={"entity_id": EXN, "month": "2026-11", "description": "Director fee - Test Payee", "category": "director",
                                         "amount": NDIR, "account_id": acct["EXN"], "due_date": "2026-11-05", "paid_date": "2026-11-05"})["id"]
j("post", "/api/budget/setup", json={"entity_id": EXN, "month": "2026-11"})
j("post", "/api/budget/header", json={"entity_id": EXN, "month": "2026-11", "balance": 1000, "as_at": "2026-11-20"})
j("post", "/api/months/close", json={"entity_id": EXH, "month": M, "closed": True})

# The October statement of EXA's Main account: the lease's line, a receipt not explained, part of the internet bill.
con = db.connect()
con.arm("import", "test: a bank statement")
sid = con.execute("""INSERT INTO statements (account_id, month, statement_date, opening, closing, imported_at, check_ok)
                     VALUES (?, ?, '2026-10-31', 50000, 53650, ?, 1)""", (acct["EXA"], M, db.now())).lastrowid
for n, (day, desc, amt, pid, status, bal) in enumerate((("2026-10-05", "LEASE", -1200, lease, "matched", 48800),
                                                       ("2026-10-12", "RECEIPT", 5000, None, "unmatched", 53800),
                                                       ("2026-10-20", "INTERNET", -150, internet, "matched", 53650)), 1):
    con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (sid, n, day, desc, amt, bal, pid, status))
# EXN's November statement: part of the director's fee went out.
nsid = con.execute("""INSERT INTO statements (account_id, month, statement_date, opening, closing, imported_at, check_ok)
                      VALUES (?, '2026-11', '2026-11-30', 20000, 19000, ?, 1)""", (acct["EXN"], db.now())).lastrowid
con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status)
               VALUES (?, 1, '2026-11-05', 'TRANSFER', -1000, 19000, ?, 'matched')""", (nsid, n_dir))
con.commit()
con.disarm()
con.close()
j("post", "/api/budget/setup", json={"entity_id": EXA, "month": M})
j("post", "/api/budget/header", json={"entity_id": EXA, "month": M, "balance": 60000, "as_at": "2026-11-20"})

# SQL's books for EXA: a trial balance at 1 January, sales, a receipt, expenses, purchases; data to 17 November.
CHART = [("100-0000", "SHARE CAPITAL", "equity", None, "CP"), ("150-0000", "RETAINED EARNINGS", "equity", None, "RE"),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA"), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank", "CA"),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL"), ("500-0000", "SALES", "income", None, "SL"),
         ("600-0000", "PURCHASES", "expense", None, "CO"), ("610-0000", "RENT", "expense", None, "EP")]
write("the made-up chart", *[("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)", (EXA, *a)) for a in CHART],
      ("UPDATE entities SET fy_start = 1 WHERE id = ?", (EXA,)))
con = db.connect()
con.arm("import", "test: the SQL documents")
imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXA, db.now())).lastrowid
tb = ledger.new_batch(con, EXA, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx", period_from="2026-01-01", period_to="2026-11-17")
ledger.put_openings(con, EXA, tb, "2026-01-01", "sql_tb", [{"code": "300-0000", "dr_sen": S(4000), "cr_sen": 0}, {"code": "310-1000", "dr_sen": S(50000), "cr_sen": 0},
                                                           {"code": "400-0000", "dr_sen": 0, "cr_sen": S(3000)}, {"code": "100-0000", "dr_sen": 0, "cr_sen": S(51000)}], True)
jb = ledger.new_batch(con, EXA, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-01-01",
                      period_to="2026-11-17", period_source="printed", sections=[{"label": "Sales Journal", "book": "sales"}])


def doc(no, d, book, lines):
    ledger.put_document(con, EXA, jb, {"doc_no": no, "doc_date": d, "book": book, "lines": [
        {"code": x[0], "dr_sen": S(x[1]), "cr_sen": S(x[2]), "name": None} for x in lines]})


doc("IV-0301", "2026-03-10", "sales", [("300-A0003", 2000, 0), ("500-0000", 0, 2000)])
doc("OR-0320", "2026-03-20", "bank", [("310-1000", 2000, 0), ("300-A0003", 0, 2000)])
doc("IV-0901", "2026-09-01", "sales", [("300-A0001", 3000, 0), ("500-0000", 0, 3000)])
doc("PI-0915", "2026-09-15", "purchase", [("600-0000", 900, 0), ("400-S0001", 0, 900)])
doc("OR-1001", "2026-10-01", "bank", [("310-1000", 1000, 0), ("300-A0001", 0, 1000)])
doc("JV-1010", "2026-10-10", "general", [("610-0000", 1200, 0), ("310-1000", 0, 1200)])
doc("IV-1015", "2026-10-15", "sales", [("300-A0002", 700, 0), ("500-0000", 0, 700)])
doc("IV-1025", "2026-10-25", "sales", [("300-A0001", 2000, 0), ("500-0000", 0, 2000)])
doc("PI-1101", "2026-11-01", "purchase", [("600-0000", 600, 0), ("400-S0001", 0, 600)])
doc("PI-1115", "2026-11-15", "purchase", [("600-0000", 500, 0), ("400-S0001", 0, 500)])
ledger.finish_batch(con, jb)
con.commit()
con.disarm()
con.close()


def card(name, eid, month=M, today=TODAY):
    with db.connect() as r:
        got = ov.card(r, name, month, eid, today)
    return got["companies"][0] if eid else got


month = j("get", f"/api/month?entity={EXA}&month={M}")
here = j("get", f"/api/month?entity={EXH}&month={M}")

# ---------- Needs attention ----------
a = card("attention", EXA)
missing = sum(1 for t in month["tasks"] if t["missing"] and not t["waiting"])
check("Needs attention counts past due (not on the statement, past the legal deadline), part paid, lines to explain, not in SQL",
      (a["past_due"], a["part_paid"], a["to_explain"], a["not_in_sql"]) == (2, 1, 1, 1), a)
check("...and the checklist items whose documents are missing, as the Monthly checklist's Missing documents filter lists them",
      a["docs_missing"] == missing and missing >= 1, (a["docs_missing"], missing))
h = card("attention", EXH)
check("a month filed counts nothing, and a company kept here has no Not in SQL counter",
      h["filed"] and h["not_in_sql"] is None and all(not h[k] for k in ("past_due", "part_paid", "docs_missing", "to_explain")), h)
n = card("attention", EXN)
check("a month before the first month tracked counts only the lines to explain", n["before_tracking"] and n["past_due"] == 0 and n["to_explain"] == 0, n)

# ---------- Checklist ----------
cl = card("checklist", EXA)
T = [t for t in month["tasks"] if not t["waiting"]]
check("Checklist: items done of the month's total, as the Monthly checklist counts them",
      (cl["done"], cl["total"]) == (sum(t["done"] for t in T), len(T)) and cl["total"] > 0 and not cl.get("empty"), cl)
ch = card("checklist", EXH)
check("...a filed month says when it was filed", ch["filed_at"] == here["closed_at"] and ch["total"] == len([t for t in here["tasks"] if not t["waiting"]]), ch)
cn = card("checklist", EXN)
check("...no checklist: 'No checklist for this month yet', with the first month tracked",
      cn["empty"] == "No checklist for this month yet" and cn["tracked_from"] == "2026-11", cn)

# ---------- Due and overdue ----------
d = card("due", EXA)
check("Due and overdue counts from today: payments not paid that are overdue (with what is still to pay)",
      d["overdue"]["n"] == 4 and d["overdue"]["sums"] == {"MYR": round(45 + 300 + 1500, 2)}, d)
check("...the salary among them counted, never added to the amounts", d["overdue"]["pay_n"] == 1 and d["soon"]["pay_n"] == 0, d)
check("...and those due in the next 7 days (later ones left out)", d["soon"] == {"n": 1, "sums": {"MYR": 85.5}, "pay_n": 0} and d["days"] == 7, d)
check("...its link opens the month of the oldest of them", d["link_month"] == M, d)
dh = card("due", EXH)
check("...a filed month's payments are not counted", dh["overdue"]["n"] == 0 and dh["soon"]["n"] == 0, dh)
dn = card("due", EXN)
check("...when the only payment overdue is a salary, the card counts it and shows no amount at all (one person's pay)",
      dn["overdue"] == {"n": 1, "sums": {}, "pay_n": 1} and str(NPAY) not in json.dumps(dn), dn)
fn = card("funds", EXN, "2026-11")
check("Funds to request: with pay alone left to pay, neither what is still to pay nor the balance is given",
      fn.get("pay_only") is True and fn["still_to_pay"] is None and fn["balance"] is None
      and fn["funds"] is None and fn["empty"] == "Funds to request: salaries only, open the Budget"
      and not ({str(NPAY), f"{NPAY:,.2f}"} & set(re.findall(r"[\d,.]+", json.dumps(fn)))), fn)
check("...while a month with other bills to pay gives them", not card("funds", EXA).get("pay_only") and card("funds", EXA)["still_to_pay"] is not None)

# ---------- Funds to request ----------
f = card("funds", EXA)
bud = j("get", f"/api/budget?entity={EXA}&month={M}")
check("Funds to request is the Budget's: still to pay less the balance on its balance date",
      f["funds"] == bud["funds_to_request"] and f["still_to_pay"] == round(bud["totals"]["MYR"], 2) and f["balance"] == 60000
      and f["funds"] == round(max(0, f["still_to_pay"] - 60000), 2) and f["as_at"] == "2026-11-20", (f, bud["funds_to_request"]))
check("...naming the company's own account by its label", f["bank"] == "Main", f)
fh = card("funds", EXH)
check("...no balance entered: 'Enter the bank balance to see funds to request', never worked out from 0",
      fh["funds"] is None and fh["empty"] == "Enter the bank balance to see funds to request", fh)
check("...a month not set up says so", card("funds", EXN)["empty"] == "No checklist for this month yet")
check("Paid without approval on file stays hidden", card("unapproved", EXA) == {**card("unapproved", EXA), "hidden": True})

# ---------- Bank ----------
b = card("bank", EXA)
check("Bank: each account's balance at its latest statement line, with its date, by its label",
      b["accounts"] == [{"label": "Main", "currency": "MYR", "balance": 53650, "date": "2026-10-20"}], b)
check("...the month's money in and out", b["totals"] == {"MYR": {"balance": 53650, "in": 5000, "out": 1350}} and not b["stale"], b)
check("...no statement: 'No statement imported for <month>'", card("bank", EXA, "2026-11")["empty"] == "No statement imported for November 2026")
write("a statement that stops early", ("UPDATE statements SET statement_date = NULL WHERE id = ?", (sid,)))
check("...one that stops before the month's end, days ago, is out of date ('Statement runs to')",
      card("bank", EXA)["stale"] and card("bank", EXA)["runs_to"] == "2026-10-20")
write("the statement's date back", ("UPDATE statements SET statement_date = '2026-10-31' WHERE id = ?", (sid,)))

# ---------- Profit or loss ----------
p = card("pl", EXA)
check("Profit or loss: the month (sales 2,700 less rent 1,200) and the financial year to the month's end",
      p["month_sen"] == S(1500) and p["ytd_sen"] == S(7700 - 2100) and p["fy_start"] == "2026-01-01" and p["sql_to"] == "2026-11-17", p)
check("...a month SQL's data covers is not out of date", p["stale"] is False)
pn = card("pl", EXA, "2026-11", date(2026, 11, 25))
check("...a month it stops in, more than 3 days ago, is ('SQL data runs to ..., fetch again')", pn["stale"] and pn["upto"] == "2026-11-17", pn)
check("...a company kept here: 'No books yet'; one with nothing fetched: 'Nothing fetched from SQL yet'",
      card("pl", EXH)["empty"] == "No books yet" and card("pl", EXN)["empty"] == "Nothing fetched from SQL yet")

# ---------- Customers overdue: older than 30 days, brought forward apart as Before tracking ----------
cu = card("customers", EXA)
check("Customers overdue counts only what is older than 30 days (61-90: 2,000 of IV-0901 after the receipt; 31-60: IV-1015's 700)",
      cu["overdue_sen"] == S(2700) and cu["overdue_count"] == 2, cu)
check("...an invoice of 26 days is not overdue, and a customer settled in full not listed", cu["count"] == 3, cu)
check("...the balance brought forward from before tracking is not counted as overdue: it is given apart",
      cu["before_tracking_sen"] == S(4000) and cu["before_tracking_count"] == 1, cu)
cu31 = card("customers", EXA, today=date(2026, 11, 25))
check("...at 30 days an invoice turns overdue (IV-1025 is 31 days old on 25 November)", cu31["overdue_sen"] == S(4700) and cu31["overdue_count"] == 2, cu31)
check("...and is out of date when SQL's data is more than 3 days old", cu31["stale"] and not cu["stale"])
check("...a company kept here with no books: 'No balances'; nothing fetched: 'Nothing fetched from SQL yet'",
      card("customers", EXH)["empty"] == "No balances" and card("customers", EXN)["empty"] == "Nothing fetched from SQL yet")
su = card("suppliers", EXA)
check("Suppliers due: bills overdue (older than 30 days) and due in the next 14 days, brought forward apart",
      (su["overdue_sen"], su["overdue_count"], su["due_sen"], su["due_count"], su["before_tracking_sen"]) == (S(900), 1, S(600), 1, S(3000)), su)

# ---------- HR and requests ----------
check("the HR cards read 'Add your staff to see this', Requests waiting 'Nothing waiting'",
      all(card(k, EXA)["empty"] == "Add your staff to see this" for k in ("leave", "dates", "headcount")) and card("requests", EXA)["empty"] == "Nothing waiting")

# ---------- the routes: one per card, all companies or one, a failing card alone ----------
CARDS = list(ov.CARDS)
check("13 cards, each on its own route", len(CARDS) == 13 and all(call("get", f"/api/overview/{k}?month={M}").status_code == 200 for k in CARDS))
allc = j("get", f"/api/overview/checklist?month={M}")
check("...with All companies every company in use, with its kind", [x["code"] for x in allc["companies"]] == ["EXA", "EXH", "EXN"]
      and [x["kind_label"] for x in allc["companies"]] == ["Kept in SQL Account", "Kept here", "Kept in SQL Account"], allc)
one = j("get", f"/api/overview/checklist?month={M}&entity_id={EXH}")
check("...or the one company the switcher chose", [x["code"] for x in one["companies"]] == ["EXH"])
check("an unknown card, a bad month or company is refused", call("get", f"/api/overview/salaries?month={M}").status_code == 404
      and call("get", "/api/overview/bank?month=2026-13").status_code == 400 and call("get", f"/api/overview/bank?month={M}&entity_id=999").status_code == 404)
real = ov.CARDS["bank"]
ov.CARDS["bank"] = lambda *a: 1 / 0
failed = call("get", f"/api/overview/bank?month={M}")
others = [call("get", f"/api/overview/{k}?month={M}").status_code for k in CARDS if k != "bank"]
ov.CARDS["bank"] = real
check("a card that fails answers with its own error, and every other card still answers",
      failed.status_code == 500 and "could not be worked out" in failed.get_json()["error"] and set(others) == {200}, (failed.status_code, others))
ro = j("get", f"/api/overview/rollover?month={M}")
check("the rollover banner's route: the next month and the companies that have it set up", ro["next_month"] == "2026-11" and ro["set_up"] == [EXA, EXN], ro)
act = j("get", "/api/overview/activity")["items"]
act_h = j("get", f"/api/overview/activity?entity_id={EXH}")["items"]
check("Recent activity: the newest changes from the audit trail, newest first, in words with who, company and when",
      len(act) == 6 and all(set(x) == {"id", "at", "who", "source", "company", "text"} and x["text"] for x in act)
      and [x["id"] for x in act] == sorted((x["id"] for x in act), reverse=True), act)
check("...for the company the switcher chose: what was done, by the route it came from",
      [x["text"] for x in act_h][:3] == ["Marked a month as filed, or reopened it", "Added a payment", "Set up a month"] and {x["company"] for x in act_h} == {"EXH"}, act_h)

# ---------- never on the Overview ----------
payloads = [j("get", f"/api/overview/{k}?month={m}{q}") for k in CARDS for m in (M, "2026-11") for q in ("", f"&entity_id={EXA}")]
payloads.append({"activity": j("get", "/api/overview/activity")})
text = json.dumps(payloads)
PAY_WORDS = (str(SALARY), f"{SALARY:,.2f}", str(S(SALARY)), str(NPAY), f"{NPAY:,.2f}", str(S(NPAY)), "Salaries - test", "Test Payee")
bad = [w for w in (ACCT_NO, BANK_DETAILS, REG_NO, ADDRESS, "Example Bank", "Example Alpha Sdn Bhd") + PAY_WORDS if w in text]
check("no card and no activity line holds a pay figure, a bank account number, bank details, a registration number, an address or a name",
      not bad, bad)
keys = set()


def walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            keys.add(k)
            walk(v)
    elif isinstance(x, list):
        for v in x:
            walk(v)


walk(payloads)
check("...nor any field for one", not keys & {"number", "bank_details", "address", "ic", "passport", "tax_no", "epf_no", "old_reg_no", "name", "description", "salary"},
      keys & {"number", "bank_details", "address", "ic", "passport", "tax_no", "epf_no", "old_reg_no", "name", "description", "salary"})

# Next up on the Overview: a pay-type payment (salary, director's allowance) never with its name or amount
with db.connect() as r:
    days = [date(2026, 11, d) for d in (1, 8, 12, 16, 20, 26)]
    nrows = [x for day in days for x in nextup.items(r, day)] + [x for day in days for x in nextup.items(r, day, EXN)]
    nexts = [nextup.upcoming(r, day) for day in days]
ntext = json.dumps([[x["text"] for x in nrows], nexts])
check("Next up names no one's pay: no salary or allowance description, no pay amount, on any day",
      not [w for w in PAY_WORDS + ("Director fee",) if w in ntext], [w for w in PAY_WORDS + ("Director fee",) if w in ntext])
sal_rows = [x for x in nrows if x["key"].endswith(":pay-2026-11")]
check("...a month's salaries due soon are one row, counted, with no amount: 'Pay salaries for November (1 payment)'",
      sal_rows and all(x["text"] == "Pay salaries for November (1 payment)" and x["amount"] is None and x["rule"] == 5 for x in sal_rows), sal_rows[:2])
part = [x for x in nrows if x["rule"] == 8 and x["entity_id"] == EXN]
check("...a part-paid allowance says so with no amounts", part and all(x["text"] == "A director allowance payment is part paid: not all of it is found on the EXN statements"
                                                                        and x["amount"] is None for x in part), part[:1])
check("...and no row carries a pay amount", not [x for x in nrows if x["amount"] in (SALARY, NPAY, NDIR, round(NDIR - 1000, 2))],
      [x["text"] for x in nrows if x["amount"] in (SALARY, NPAY, NDIR, round(NDIR - 1000, 2))])

# ---------- the page ----------
routes = {"/api/meta": j("get", "/api/meta"), "/api/audit/status?quick=1": {"ok": True}}
with db.connect() as r:
    items = nextup.items(r, TODAY)
    routes["/api/next"] = {"today": TODAY.isoformat(), "items": items, "older_open_months": nextup.older_open(r, TODAY), "next_due": None}
    for scope in (EXA, EXN):  # one company's Overview reads that company's list
        routes[f"/api/next?entity_id={scope}"] = {"today": TODAY.isoformat(), "items": nextup.items(r, TODAY, scope),
                                                  "older_open_months": nextup.older_open(r, TODAY, scope), "next_due": None}
    # EXH has nothing to do: its Overview says so with its own next due (made up here), never another company's
    routes[f"/api/next?entity_id={EXH}"] = {"today": TODAY.isoformat(), "items": [], "older_open_months": [],
                                            "next_due": {"due": "2026-12-01", "text": "Pay Test bill from EXH"}}
    for scope in (None, EXA, EXN, EXH):
        q = f"month={M}" + (f"&entity_id={scope}" if scope else "")
        for k in CARDS:
            if not (k == "pl" and scope is None):  # Profit or loss can't load with All companies: the failing card
                routes[f"/api/overview/{k}?{q}"] = ov.card(r, k, M, scope, TODAY)
        routes[f"/api/overview/rollover?{q}"] = ov.rollover(r, M, scope)
        routes[f"/api/overview/activity?{q}"] = {"items": ov.activity(r, scope)}
    pl_all = ov.card(r, "pl", M, None, TODAY)
fx = tmp / "fixture.json"
fx.write_text(json.dumps({"exa": EXA, "exh": EXH, "exn": EXN, "month": M, "routes": routes, "pl_all": pl_all, "cards": CARDS}), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, posts = [], asked = [], focused = [], delay = {};
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, classList: { add() {}, remove() {} },
  setAttribute() {}, getAttribute() { return null; }, focus() { focused.push(id); }, remove() { delete els[id]; }, querySelectorAll() { return []; }, querySelector() { return null; },
  addEventListener() {}, contains() { return false; } };
const document = { querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, addEventListener() {}, activeElement: null };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") { posts.push([init.method, path, init.body && typeof init.body === "string" ? JSON.parse(init.body) : null]); return { ok: true, status: 200, json: async () => ({ ok: true, id: 9999 }) }; }
  asked.push(path);
  if (delay[path]) await new Promise(res => setTimeout(res, delay[path]));
  const r = fx.routes[path];
  if (r === undefined) return { ok: false, status: 500, json: async () => ({ error: "not stubbed: " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
// The page's today is 5 November 2026: still October's payroll cycle (the rollover day is the 10th), with November set up for EXA.
class FixedDate extends Date { constructor(...a) { if (a.length) super(...a); else super(2026, 10, 5, 10, 0, 0); } static now() { return new FixedDate().getTime(); } }
const ctx = vm.createContext({ document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, Date: FixedDate,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, window: {} });
const run = code => vm.runInContext(code, ctx);
const pause = () => new Promise(r => setTimeout(r, 30));
const out = {};
const slots = () => Object.fromEntries(fx.cards.map(k => [k, { html: el("ov-c-" + k).innerHTML, hidden: !!el("ov-c-" + k).hidden }]));
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  await pause();
  const show = async (scope) => { run(`state.view = "overview"; state.entity = ${scope || fx.exa}; state.month = "${fx.month}"; state.day = dayKey(); state.addr = { all: ${!scope}, id: null, params: {} }`);
    await run("render()"); await run("OV.done"); const main = el("main").innerHTML;
    return { main, cards: slots(), act: el("ovAct").innerHTML, roll: (main.match(/<div id="ovRollBox">([\s\S]*?)<\/div>\s*<div class="ov-head">/) || [, ""])[1], next: (main.match(/<div class="ov-next" id="nextUp">([\s\S]*?)<\/div>\s*<section class="card ov-act"/) || [, ""])[1] }; };
  await show(null); asked.length = 0;
  out.all = await show(null);
  out.asked = asked.slice();
  // Try again on the card that failed: only it is read again
  fx.routes[`/api/overview/pl?month=${fx.month}`] = fx.pl_all; asked.length = 0;
  await run(`ovRetry("pl")`); out.retried = { pl: el("ov-c-pl").innerHTML, asked: asked.slice() };
  out.exa = await show(fx.exa);
  out.exn = await show(fx.exn);
  asked.length = 0; out.exh = await show(fx.exh); out.exh_asked = asked.slice();
  // Try again moves the focus only when its answer was drawn on the page it was asked for
  await show(fx.exa); focused.length = 0;
  await run(`ovRetry("checklist")`); out.focus_same = focused.slice();
  delay[`/api/overview/checklist?month=${fx.month}&entity_id=${fx.exa}`] = 250; delay[`/api/overview/activity?month=${fx.month}&entity_id=${fx.exa}`] = 250;
  const late = run(`ovRetry("checklist")`), lateAct = run(`ovActivity(OV.seq, true)`);
  await pause(); await show(fx.exn); focused.length = 0;
  await late; await lateAct; out.focus_late = focused.slice();
  delete delay[`/api/overview/checklist?month=${fx.month}&entity_id=${fx.exa}`]; delete delay[`/api/overview/activity?month=${fx.month}&entity_id=${fx.exa}`];
  // the totals with All companies, on made-up answers: never an unknown figure as 0, never one currency added into another
  run(`state.view = "overview"; state.month = "${fx.month}"; state.addr = { all: true, id: null, params: {} }`);
  const co = (id, code, more) => ({ entity_id: id, code, kind: "sql", kind_label: "Kept in SQL Account", ...more });
  const calm = (card, cs) => run(`ovCalm(${JSON.stringify(card)}, ${JSON.stringify({ companies: cs })})`);
  const fund = (n, more) => ({ set_up: true, funds: n, still_to_pay: 10000, balance: 1000, as_at: "2026-11-20", bank: "Main", ...more });
  const acct = (cur, bal, inn = 0, outt = 0) => ({ accounts: [{ label: "Main", currency: cur, balance: bal, date: "2026-10-31" }], runs_to: "2026-10-31", stale: false });
  const bank = (totals) => ({ ...acct("MYR", 0), totals });
  const zeroes = { past_due: 0, part_paid: 0, docs_missing: 0, to_explain: 0, not_in_sql: 0, filed: false, filed_at: null, before_tracking: false };
  const pl = (m, y) => ({ month_sen: m, ytd_sen: y, upto: "2026-10-31", sql_to: "2026-11-17", fy_start: "2026-01-01", stale: false });
  out.t = {
    funds_unknown: calm("funds", [co(1, "AAA", fund(5000)), co(2, "BBB", fund(null, { empty: "Enter the bank balance to see funds to request", still_to_pay: 80000, balance: null }))]),
    // filed months: always shown with their day
    att_all_filed: run(`ovAttention(${JSON.stringify({ companies: [co(1, "AAA", { ...zeroes, filed: true, filed_at: "2026-10-03T09:00:00" }), co(2, "BBB", { ...zeroes, filed: true, filed_at: "2026-10-05T09:00:00" })] })})`),
    att_one_filed: run(`ovAttention(${JSON.stringify({ companies: [co(1, "AAA", { ...zeroes, filed: true, filed_at: "2026-10-03T09:00:00" }), co(2, "BBB", { ...zeroes })] })})`),
    att_filed_busy: run(`ovAttention(${JSON.stringify({ companies: [co(1, "AAA", { ...zeroes, filed: true, filed_at: "2026-10-03T09:00:00" }), co(2, "BBB", { ...zeroes, past_due: 2 })] })})`),
    att_single_filed: run(`state.addr = { all: false, id: null, params: {} }; state.entity = 1; ovAttention(${JSON.stringify({ companies: [co(1, "AAA", { ...zeroes, filed: true, filed_at: "2026-10-03T09:00:00" })] })})`),
    cl_single_filed_open: calm("checklist", [co(1, "AAA", { done: 4, total: 6, filed_at: "2026-10-03T09:00:00" })]),
    _all_again: run(`state.addr = { all: true, id: null, params: {} }; ""`),
    cl_all_filed: calm("checklist", [co(1, "AAA", { done: 6, total: 6, filed_at: "2026-10-03T09:00:00" }), co(2, "BBB", { done: 4, total: 6, filed_at: "2026-10-05T09:00:00" })]),
    cl_one_filed: calm("checklist", [co(1, "AAA", { done: 6, total: 6, filed_at: "2026-10-03T09:00:00" }), co(2, "BBB", { done: 4, total: 6, filed_at: null })]),
    due_mixed: calm("due", [co(1, "AAA", { overdue: { n: 3, sums: { MYR: 739 }, pay_n: 0 }, soon: { n: 2, sums: { MYR: 1200 }, pay_n: 0 }, days: 7, link_month: "2026-10" }),
                            co(2, "BBB", { overdue: { n: 1, sums: { USD: 100 }, pay_n: 0 }, soon: { n: 1, sums: {}, pay_n: 1 }, days: 7, link_month: "2026-10" })]),
    funds_pay: calm("funds", [co(1, "AAA", fund(5000)), co(2, "BBB", fund(null, { empty: "Funds to request: salaries only, open the Budget", pay_only: true, still_to_pay: null, balance: null }))]),
    funds_known: calm("funds", [co(1, "AAA", fund(5000)), co(2, "BBB", fund(2000))]),
    bank_mixed: calm("bank", [co(1, "AAA", bank({ MYR: { balance: 80000, in: 100, out: 50 } })), co(2, "BBB", bank({ USD: { balance: 17480, in: 0, out: 0 } }))]),
    bank_both: calm("bank", [co(1, "AAA", bank({ MYR: { balance: 80000, in: 100, out: 50 }, USD: { balance: 100, in: 0, out: 0 } })),
                              co(2, "BBB", bank({ MYR: { balance: -1250, in: 0, out: 10 }, USD: { balance: 50, in: 0, out: 0 } }))]),
    bank_neg: calm("bank", [co(1, "AAA", bank({ MYR: { balance: -1250, in: 0, out: 1250 } }))]),
    pl_unknown: calm("pl", [co(1, "AAA", pl(150000, 560000)), co(2, "BBB", pl(null, null))]),
    pl_known: calm("pl", [co(1, "AAA", pl(150000, 560000)), co(2, "BBB", pl(-50000, 0))]),
  };
  // the addresses the links write, read back
  out.parse = {};
  for (const k of Object.keys(out.exa.cards)) for (const m of out.exa.cards[k].html.matchAll(/href="(#[^"]+)"/g)) out.parse[m[1].replace(/&amp;/g, "&")] = JSON.parse(run(`JSON.stringify(parseAddr(${JSON.stringify(m[1].replace(/&amp;/g, "&"))}))`));
  out.mark = run(`JSON.stringify([{ id: 1, paid_date: null, flag: { tone: "bad" } }, { id: 2, paid_date: null, flag: { tone: "warn" } }, { id: 3, paid_date: "2026-10-01", flag: null }].filter(markFor("past_due").pay).map(p => p.id))`);
  // the rollover banner dismissed stays away for this month and company choice
  await show(null); await run(`ovRoll("dismiss")`); out.dismissed = (await show(null)).roll;
  // Add a payment from the Overview asks which company
  await show(null); await run("addPaymentDrawer()");
  out.np_all = { drawer: el("drawer").innerHTML, errs: run("JSON.stringify(npErrors())") };
  run(`npCompany(${fx.exh})`); out.np_pick = { acct: el("ap-acct").innerHTML, eyebrow: el("np-eyebrow").textContent };
  el("ap-desc").value = "Stationery - test"; el("ap-cat").value = run("npDefault('out')"); el("ap-amt").value = "12.50";
  posts.length = 0; await run("npSave()"); out.np_saved = posts.filter(p => p[1] === "/api/payments");
  await run("closeDrawer(true)");
  await show(fx.exa); await run("addPaymentDrawer()"); out.np_one = el("drawer").innerHTML; await run("closeDrawer(true)");
  run(`state.view = "entity"; state.entity = ${fx.exa}`); await run("addPaymentDrawer()"); out.np_reg = el("drawer").innerHTML; await run("closeDrawer(true)");
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
res = subprocess.run([shutil.which("node"), str(probe), app_bundle(tmp / "app.js"), str(fx)], capture_output=True, text=True, encoding="utf-8", timeout=120)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the page script ran", o is not None, res.stderr[-1500:])
if o is None:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    raise SystemExit(1)

A, X, N = o["all"], o["exa"], o["exn"]
order = re.findall(r'id="ov-c-(\w+)"', A["main"])
check("the cards stand in four rows: Needs attention; Payments; Accounting; HR",
      order == ["attention", "checklist", "due", "funds", "unapproved", "bank", "pl", "customers", "suppliers", "leave", "dates", "headcount", "requests"]
      and re.findall(r'class="rh">([^<]+)<', A["main"]) == [f"Payments · October 2026", "Accounting · October 2026, balances as at today", "HR · today"], order)
top = {"date": "Thursday 5 November 2026 · Payroll month" in A["main"], "heading": "October 2026 cycle</h1>" in A["main"],
       "budget": f'href="#/EXA/{M}/payments/budget">' in A["main"], "add": 'id="addPayment"' in A["main"], "next": "data-next-go=" in A["next"],
       "older": "Next up" in A["next"], "activity": "Recent activity" in A["main"] and "<li>" in A["act"]}
check("the top part: the date, the month's heading, Open budget, Add a payment, Next up with Go, Recent activity", all(top.values()), top)
check("the per-company cards, the tiles and 'Show tasks for' are gone", "Show tasks for" not in A["main"] and 'class="stat"' not in A["main"] and "fully documented" not in A["main"])
check("Paid without approval on file stays hidden", 'id="ov-c-unapproved" hidden></div>' in A["main"] and not A["cards"]["unapproved"]["html"])
cards = A["cards"]
check("a card that can't load says 'Could not load, try again', with Try again...",
      "Could not load, try again" in cards["pl"]["html"] and 'data-ov-retry="pl"' in cards["pl"]["html"] and "The other cards are not affected" in cards["pl"]["html"])
check("...and the other cards still show", all("Could not load" not in cards[k]["html"] and cards[k]["html"] for k in cards if k not in ("pl", "unapproved")))
check("Try again reads that card alone, and draws it", o["retried"]["asked"] == [f"/api/overview/pl?month={M}"] and "Profit RM 1,500" in o["retried"]["pl"], o["retried"])
check("each card was read on its own route", sum(1 for x in o["asked"] if x.startswith("/api/overview/") and "rollover" not in x and "activity" not in x) == 12, o["asked"])
att = cards["attention"]["html"]
check("Needs attention, All companies: a block per company with its kind, counters grey at zero, Not in SQL only for SQL companies",
      att.count('class="ova"') == 3 and "Kept here" in att and f'id="ov-ctr-not_in_sql-{EXA}"' in att and f'id="ov-ctr-not_in_sql-{EXH}"' not in att
      and '<b class="ctr-n bad">2</b><span>Past due</span>' in att and '<b class="ctr-n">0</b>' in att and f"Filed {db.short_day(here['closed_at'][:10])}: nothing in it counts" in att, att[:900])
due_all = cards["due"]["html"]
check("Due and overdue with All companies: the companies added up, a line per company, 'Today'",
      '<b class="ovh bad">5 overdue · RM 1,845</b><span class="sub ovn">1 due in the next 7 days · RM 86</span>' in due_all and '<span class="ovco">EXN</span><b class="bad">1 payment overdue</b>' in due_all and '<span class="ovco">EXA</span>' in due_all and '<span class="ovco">EXH</span>' in due_all and 'class="tday">Today' in due_all, due_all)
check("Customers overdue shows the balances from before tracking apart, labelled 'Before tracking'",
      "RM 2,700" in X["cards"]["customers"]["html"] and "Before tracking RM 4,000" in X["cards"]["customers"]["html"] and "2 balances over 30 days" in X["cards"]["customers"]["html"],
      X["cards"]["customers"]["html"])
check("Funds to request, one company: its figure and where it comes from (the company's own account label)",
      "Main on 20 Nov" in X["cards"]["funds"]["html"] and 'class="ovh ' in X["cards"]["funds"]["html"])
check("one company's Overview: no company lines, and Next up lists only that company's rows (and those of no company)",
      'class="ovk"' not in X["cards"]["due"]["html"] and {k.split(":")[1] for k in re.findall(r'data-next-go="([^"]+)"', X["next"])} <= {str(EXA), "-"}
      and {k.split(":")[1] for k in re.findall(r'data-next-go="([^"]+)"', N["next"])} == {str(EXN)}
      and 'class="cp info">EXA</span>' in X["next"], [re.findall(r'data-next-go="([^"]+)"', x["next"]) for x in (X, N)])
check("a company with nothing yet: its empty sentences", "No checklist for this month yet" in N["cards"]["checklist"]["html"] and "Tracked from November 2026" in N["cards"]["checklist"]["html"]
      and "Nothing fetched from SQL yet" in N["cards"]["pl"]["html"] and "No statement imported for October 2026" in N["cards"]["bank"]["html"]
      and "Nothing needs attention" in N["cards"]["attention"]["html"] and '<b class="ovh bad">1 overdue</b>' in N["cards"]["due"]["html"] and str(NPAY) not in N["cards"]["due"]["html"], {k: v["html"][-300:] for k, v in N["cards"].items() if k in ("checklist", "due")})
check("the HR cards and Requests waiting: their sentence and no link", all("Add your staff to see this" in X["cards"][k]["html"] and 'href="#' not in X["cards"][k]["html"] for k in ("leave", "dates", "headcount"))
      and "Nothing waiting" in X["cards"]["requests"]["html"] and 'href="#' not in X["cards"]["requests"]["html"])

# the links: each card and each counter opens its page or its interim landing
P = o["parse"]


def lands(view, **params):
    return any(v and v["view"] == view and v["entity"] == EXA and all(v["params"].get(k) == w for k, w in params.items()) for v in P.values())


check("Checklist opens the Monthly checklist", lands("checklist") and f"#/EXA/{M}/payments/checklist" in P, list(P))
check("Due and overdue opens the register's Not paid tab (until To pay)", lands("entity", tab="unpaid") and f"#/EXA/{M}/payments/register?tab=unpaid" in P)
check("Funds to request opens the Budget", f"#/EXA/{M}/payments/budget" in P)
check("Bank opens Bank and reconciliation", f"#/EXA/{M}/accounting/bank" in P)
check("Profit or loss opens today's Books, profit and loss tab (until slice 7)", lands("books", tab="pl"))
check("Customers overdue and Suppliers due open today's Books parties tab, customers and suppliers (until slice 7)",
      f"#/EXA/{M}/accounting/parties" in P and f"#/EXA/{M}/accounting/parties?tab=suppliers" in P)
check("Needs attention: Past due opens the register's Not paid tab with them marked", f"#/EXA/{M}/payments/register?mark=past_due&tab=unpaid" in P and o["mark"] == "[1]", o["mark"])
check("...Part paid the Needs attention tab, Documents missing the checklist's filter, Lines to explain the bank's, Not in SQL its tab",
      f"#/EXA/{M}/payments/register?mark=part_paid&tab=attention" in P and f"#/EXA/{M}/payments/checklist?tab=missing" in P
      and f"#/EXA/{M}/accounting/bank?filter=to_explain" in P and f"#/EXA/{M}/payments/register?tab=nosql" in P, list(P))
check("every link is an address of the app", all(v is not None for v in P.values()), [k for k, v in P.items() if v is None])

# the rollover banner: names the company with November set up and counts only its October rows
rows_exa_oct = sum(1 for r in items if r["month"] == M and r["entity_id"] == EXA)
check("the rollover banner names the company whose next month is set up, counting only its rows of the month on show",
      "EXA and EXN&#39;s November is set up" in A["roll"] and f"which is still open: {rows_exa_oct} thing" in A["roll"] and rows_exa_oct > 0, (A["roll"], rows_exa_oct))
check("...on that company's Overview: November has started", "November has started" in X["roll"] and f"{rows_exa_oct} thing" in X["roll"], X["roll"])
check("...not for a company without it", N["roll"] == "", N["roll"])
check("...and Dismiss keeps it away", o["dismissed"].strip() == "", o["dismissed"])

# one company's Overview reads that company's Next up from the server: its rows, its next due
check("one company's Overview asks the server for that company's list, and says its own next due, never another company's",
      f"/api/next?entity_id={EXH}" in o["exh_asked"] and "/api/next" not in o["exh_asked"]
      and "Pay Test bill from EXH" in o["exh"]["next"] and "All caught up" in o["exh"]["next"] and "data-next-go" not in o["exh"]["next"], o["exh_asked"])
check("Try again moves the focus to the card once its answer is drawn", o["focus_same"] == ["ov-link-checklist"], o["focus_same"])
check("...but an answer that came back after the page moved on moves no focus (cards and Recent activity)", o["focus_late"] == [], o["focus_late"])

# the totals with All companies
t = {k: re.sub(r"\s+", " ", v) for k, v in o["t"].items()}


def head(h):
    m = re.search(r'<b class="ovh[^"]*">([^<]*)</b>(?:<span class="sub ovn">([^<]*)</span>)?', h)
    return (m.group(1), m.group(2) or "") if m else (None, None)


check("Funds to request: a company with no balance entered means no total, naming it, with each company's line kept",
      head(t["funds_unknown"]) == ("No total", "BBB: bank balance not entered") and "RM 5,000" not in head(t["funds_unknown"])[0]
      and '<span class="ovco">BBB</span><b class="muted">Balance not entered</b>' in t["funds_unknown"] and "RM 5,000.00" in t["funds_unknown"], head(t["funds_unknown"]))
check("...and with every balance entered, the total", head(t["funds_known"])[0] == "RM 7,000", head(t["funds_known"]))
check("Bank: each currency totalled on its own, never one label over two currencies",
      head(t["bank_mixed"]) == ("RM 80,000", "in RM 100 · out RM 50 · also USD 17,480") and "MYR+USD" not in t["bank_mixed"], head(t["bank_mixed"]))
check("...companies added up per currency (ringgit with ringgit, dollars with dollars)", head(t["bank_both"]) == ("RM 78,750", "in RM 100 · out RM 60 · also USD 150"), head(t["bank_both"]))
check("...an overdrawn balance keeps its minus sign", head(t["bank_neg"])[0] == "-RM 1,250", head(t["bank_neg"]))
check("...the company line shows it the same way (-RM 1,250.00, never RM -1,250.00)",
      '<span class="ovco">BBB</span><b class="">-RM 1,250.00 · USD 50.00</b>' in t["bank_both"] and "RM -" not in t["bank_both"], t["bank_both"][-700:])
plain = {k: re.sub(r"<[^>]+>", "|", v) for k, v in t.items()}
check("every company's month filed, every counter 0: Needs attention still shows each company filed, with its day",
      "Nothing needs attention" in plain["att_all_filed"] and "|AAA||Filed 3 Oct|" in plain["att_all_filed"] and "|BBB||Filed 5 Oct|" in plain["att_all_filed"],
      plain["att_all_filed"][-400:])
check("...one filed and one open: the filed one says so, the open one has nothing to do",
      "|AAA||Filed 3 Oct|" in plain["att_one_filed"] and "|BBB||Nothing to do|" in plain["att_one_filed"], plain["att_one_filed"][-400:])
check("...and beside a company with something to do, the filed one's block says its day", "Filed 3 Oct: nothing in it counts as to do" in plain["att_filed_busy"])
check("...one company's Overview: the month was filed on its day", "October 2026 was filed on 3 Oct" in plain["att_single_filed"], plain["att_single_filed"][-300:])
check("Checklist, every company filed: each line says Filed <day>",
      "|AAA||6 of 6 · Filed 3 Oct|" in plain["cl_all_filed"] and "|BBB||4 of 6 · Filed 5 Oct|" in plain["cl_all_filed"], plain["cl_all_filed"][-500:])
check("...one filed and one open: only the filed one says so", "|AAA||6 of 6 · Filed 3 Oct|" in plain["cl_one_filed"] and "|BBB||4 of 6|" in plain["cl_one_filed"])
check("...one company filed with items still open: the note says both", "2 still to do · October 2026 was filed on 3 Oct" in plain["cl_single_filed_open"], plain["cl_single_filed_open"][-400:])
check("the server gives the day a month was filed on the Needs attention card", card("attention", EXH)["filed_at"] == here["closed_at"])
check("Due and overdue, one company: the number overdue with its amount, and the number due soon with its amount",
      '<b class="ovh bad">4 overdue · RM 1,845</b><span class="sub ovn">1 due in the next 7 days · RM 86</span>' in X["cards"]["due"]["html"], X["cards"]["due"]["html"][-900:])
check("...with All companies, the amounts added per currency, never one into another", head(t["due_mixed"]) == ("4 overdue · RM 739 and USD 100", "3 due in the next 7 days · RM 1,200"),
      head(t["due_mixed"]))
check("Profit or loss, Customers overdue and Suppliers due say the date SQL's data runs to on the card: in one company's note",
      all("SQL data to 17 Nov" in re.sub(r"<[^>]+>", "", X["cards"][k]["html"].split("<details")[0]) for k in ("pl", "customers", "suppliers")),
      {k: X["cards"][k]["html"][-500:] for k in ("pl",)})
check("...and on each SQL company's line with All companies (not on a company kept here)",
      all(ln.get("EXA", "").endswith("· to 17 Nov") and "to " not in ln.get("EXH", "x") and "to " not in ln.get("EXN", "x")
          for ln in ({m[0]: re.sub(r"<[^>]+>", "", m[1]) for m in re.findall(r'<span class="ovco">(\w+)</span><b[^>]*>(.*?)</b></span>', h)}
                     for h in (o["retried"]["pl"], A["cards"]["customers"]["html"], A["cards"]["suppliers"]["html"]))), A["cards"]["customers"]["html"][-900:])
check("Needs attention is named once (its card's heading), not by a hidden heading too",
      'aria-labelledby="ov-h-attention"' in A["main"] and ">Needs attention</h2>" not in A["main"])
css_now = (Path(__file__).resolve().parents[1] / "static" / "app.css").read_text(encoding="utf-8")
ovtt = re.search(r"^\.ovtt \{([^}]*)\}", css_now, re.M).group(1)
check("a card's title is never cut off: it wraps (no nowrap, no ellipsis)", "nowrap" not in ovtt and "ellipsis" not in ovtt, ovtt)
check("Funds to request with a company whose left to pay is salaries only: no total, and why, never a figure for it",
      head(t["funds_pay"]) == ("No total", "BBB: salaries only, open the Budget") and '<b class="muted">Salaries only</b>' in t["funds_pay"], head(t["funds_pay"]))
check("Profit or loss: a company whose month can't be worked out is not counted as 0; the total says it leaves it out",
      head(t["pl_unknown"]) == ("Profit RM 1,500", "this month, the companies together · leaves out BBB: the month can&#39;t be worked out"), head(t["pl_unknown"]))
check("...and with both known, the companies together", head(t["pl_known"])[0] == "Profit RM 1,000", head(t["pl_known"]))

# Add a payment from the Overview
na = o["np_all"]
check("Add a payment from the Overview asks which company (none chosen with All companies)",
      'id="ap-co"' in na["drawer"] and '<option value="" disabled selected>Choose a company</option>' in na["drawer"] and json.loads(na["errs"]).get("co") == "Choose a company.", na["errs"])
check("...its bank accounts follow the company chosen", "Current" in o["np_pick"]["acct"] and "Main" not in o["np_pick"]["acct"] and "EXH" in o["np_pick"]["eyebrow"], o["np_pick"])
check("...and the payment is added to that company's month", len(o["np_saved"]) == 1 and o["np_saved"][0][2]["entity_id"] == EXH and o["np_saved"][0][2]["month"] == M, o["np_saved"])
check("...one company's Overview starts on that company; the register asks nothing", f'<option value="{EXA}" selected>' in o["np_one"] and 'id="ap-co"' not in o["np_reg"])

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "overview_cards_test" in readme)

shutil.rmtree(tmp, ignore_errors=True)
print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
