"""Customers and suppliers: who owes what (hrp/receivables.py), on made-up records only. A made-up company kept in SQL,
with a trial balance's openings at 1 January 2026 and SQL documents in the sales, purchase, bank and general books:
customers part-paid, overpaid and with an opening brought forward, a code with no record in Setup named as SQL printed
it, a supplier, and what the control accounts hold themselves. A second company with lines and no opening.

Run: .venv\\Scripts\\python -m synthetic_tests.receivables_test
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-receivables-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, receivables as rv  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXR", "name": "Example Receivables Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXV", "name": "Example No Opening Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "EXW", "name": "Example Monthly Fetch Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
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


def write(why, *statements):
    """Changes made as a person would in Setup, on a connection of its own."""
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.disarm()
        con.close()


def S(rm):
    return int(round(rm * 100))


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EXR, EXV = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXR", "EXV"))
# code, name, type, special, SQL group
CHART = [("100-0000", "SHARE CAPITAL", "equity", None, "CP"),
         ("150-0000", "RETAINED EARNINGS", "equity", None, "RE"),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA"),
         ("305-0000", "OTHER DEBTORS", "asset", None, "CA"),
         ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank", "CA"),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL"),
         ("500-0000", "SALES", "income", None, "SL"),
         ("600-0000", "PURCHASES", "expense", None, "CO")]
write("the made-up chart and customers and suppliers",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)", (e, *a))
        for e in (EXR, EXV) for a in CHART],
      ("UPDATE entities SET fy_start = 1 WHERE id IN (?, ?)", (EXR, EXV)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'customer', 'Example Alpha Trading', '300-A0001', '300-0000')", (EXR,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'customer', 'Example Beta Stores', '300-A0002', '300-0000')", (EXR,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'customer', 'Example Gamma Retail', '300-A0003', '300-0000')", (EXR,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'supplier', 'Example Paper Supplies', '400-S0001', '400-0000')", (EXR,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'related', 'Example Director', '320-D0001', NULL)", (EXR,)))

con = db.connect()
con.arm("user", "test: the SQL documents")
imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXR, db.now())).lastrowid
tb_b = ledger.new_batch(con, EXR, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx",
                        period_from="2026-01-01", period_to="2026-12-31")
# SQL's trial balance at 1 January: trade debtors 4,000.00 not split by customer, Beta's own 1,000.00, creditors 3,000.00.
ledger.put_openings(con, EXR, tb_b, "2026-01-01", "sql_tb", [{"code": "300-0000", "dr_sen": S(4000), "cr_sen": 0},
                                                           {"code": "300-A0002", "dr_sen": S(1000), "cr_sen": 0},
                                                           {"code": "310-1000", "dr_sen": S(20000), "cr_sen": 0},
                                                           {"code": "400-0000", "dr_sen": 0, "cr_sen": S(3000)},
                                                           {"code": "100-0000", "dr_sen": 0, "cr_sen": S(22000)}], True)
jb = ledger.new_batch(con, EXR, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-01-01",
                      period_to="2026-12-31", period_source="printed", sections=[{"label": "Sales Journal", "book": "sales"}])


def doc(eid, no, d, book, lines, batch=None):
    ledger.put_document(con, eid, batch or jb, {"doc_no": no, "doc_date": d, "book": book, "lines": [
        {"code": x[0], "dr_sen": S(x[1]), "cr_sen": S(x[2]), "name": x[3] if len(x) > 3 else None} for x in lines]})


# Alpha: three invoices, a receipt that pays the first and part of the second, a credit note, and a fourth invoice.
doc(EXR, "IV-0001", "2026-01-10", "sales", [("300-A0001", 1000, 0), ("500-0000", 0, 1000)])
doc(EXR, "IV-0002", "2026-03-15", "sales", [("300-A0001", 2000, 0), ("500-0000", 0, 2000)])
doc(EXR, "OR-0001", "2026-04-01", "bank", [("310-1000", 1600, 0), ("300-A0001", 0, 1600)])
doc(EXR, "IV-0003", "2026-05-20", "sales", [("300-A0001", 1500, 0), ("500-0000", 0, 1500)])
doc(EXR, "IV-0004", "2026-06-20", "sales", [("300-A0001", 300, 0), ("500-0000", 0, 300)])
doc(EXR, "CN-0001", "2026-06-25", "sales", [("500-0000", 200, 0), ("300-A0001", 0, 200)])
# Beta: an opening brought forward, part-paid, and a later invoice.
doc(EXR, "OR-0010", "2026-02-01", "bank", [("310-1000", 600, 0), ("300-A0002", 0, 600)])
doc(EXR, "IV-0010", "2026-06-10", "sales", [("300-A0002", 500, 0), ("500-0000", 0, 500)])
# Gamma: overpaid.
doc(EXR, "IV-0020", "2026-02-01", "sales", [("300-A0003", 800, 0), ("500-0000", 0, 800)])
doc(EXR, "OR-0020", "2026-02-15", "bank", [("310-1000", 1000, 0), ("300-A0003", 0, 1000)])
# An other debtor with no record in Setup: named as SQL printed it.
doc(EXR, "IV-0030", "2026-04-10", "sales", [("305-W0001", 250, 0, "EXAMPLE WIDGET CO"), ("500-0000", 0, 250)])
# A journal straight to the control account.
doc(EXR, "JV-0001", "2026-03-31", "general", [("500-0000", 500, 0), ("300-0000", 0, 500)])
# The supplier: two invoices, one part-paid.
doc(EXR, "PI-0001", "2026-02-01", "purchase", [("600-0000", 700, 0), ("400-S0001", 0, 700)])
doc(EXR, "PV-0001", "2026-03-01", "bank", [("400-S0001", 500, 0), ("310-1000", 0, 500)])
doc(EXR, "PI-0002", "2026-05-15", "purchase", [("600-0000", 900, 0), ("400-S0001", 0, 900)])
# A related party's code under no debtor or creditor account: never listed.
doc(EXR, "JV-0002", "2026-02-02", "general", [("310-1000", 100, 0), ("320-D0001", 0, 100)])
# EXV: lines, no opening kept.
imp2 = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'y.xlsx', ?, 0, 0)", (EXV, db.now())).lastrowid
jb2 = ledger.new_batch(con, EXV, origin="sql", report="journal", sql_import_id=imp2, file_name="jot2.xlsx", period_from="2026-01-01",
                       period_to="2026-12-31", period_source="printed", sections=[{"label": "Sales Journal", "book": "sales"}])
doc(EXV, "IV-9001", "2026-02-01", "sales", [("300-Z0001", 100, 0, "EXAMPLE ZETA"), ("500-0000", 0, 100)], jb2)
con.commit()
con.disarm()


def ctl(d, code):
    return next((x for x in d["controls"] if x["code"] == code), None)


def row(d, code):
    return next((r for x in d["controls"] for r in x["rows"] if r["code"] == code), None)


# ---------- 1. the balances, tied to the control accounts ----------
D = rv.balances(con, EXR, "2026-01-01", "2026-06-30", "customers")
check("the customers' side lists the debtor control accounts only", [x["code"] for x in D["controls"]] == ["300-0000", "305-0000"]
      and D["sides"] == ["customers"], str([x["code"] for x in D["controls"]]))
T = ctl(D, "300-0000")
check("one line per customer's code, the control account's own first", [r["code"] for r in T["rows"]] == ["300-0000", "300-A0001", "300-A0002", "300-A0003"],
      str([r["code"] for r in T["rows"]]))
a = row(D, "300-A0001")
check("Alpha: opening, invoiced, received, other and closing",
      (a["name"], a["opening_sen"], a["invoiced_sen"], a["received_sen"], a["other_sen"], a["closing_sen"])
      == ("Example Alpha Trading", 0, S(4800), S(1600), -S(200), S(3000)), str(a))
own = row(D, "300-0000")
check("the control account's own line: the opening not split by customer, and the journal to it",
      (own["own"], own["opening_sen"], own["other_sen"], own["closing_sen"]) == (True, S(4000), -S(500), S(3500))
      and own["name_words"].startswith("Held on the control account itself"), str(own))
check("the totals tie to trade debtors in the trial balance with customers added in",
      T["ties"] is True and (T["totals"]["opening_sen"], T["totals"]["closing_sen"]) == (S(5000), S(7200))
      and (T["tb"]["opening_sen"], T["tb"]["closing_sen"], T["tb"]["moved_sen"]) == (S(5000), S(7200), S(2200))
      and "add up to the control account in the trial balance" in T["text"], T["text"])
check("and the whole side ties", D["ties"] is True and D["text"].startswith("Every control account ties"), D["text"])

# ---------- 2. ageing, first in first out ----------
check("Alpha's receipt and credit note settle the oldest first: IV-0002 part-open over 90 days, IV-0003 31-60, IV-0004 current",
      a["ageing"] == {"current": S(300), "d31_60": S(1500), "d61_90": 0, "over_90": S(1200), "brought_forward": 0} and a["open_count"] == 3, str(a["ageing"]))
b = row(D, "300-A0002")
check("Beta's opening is brought forward and paid first; what is left of it is aged as brought forward",
      (b["opening_sen"], b["received_sen"], b["closing_sen"]) == (S(1000), S(600), S(900))
      and b["ageing"] == {"current": S(500), "d31_60": 0, "d61_90": 0, "over_90": 0, "brought_forward": S(400)}, str(b))
g = row(D, "300-A0003")
check("Gamma overpaid: in credit, not aged", g["closing_sen"] == -S(200) and g["credit"] is True
      and not any(g["ageing"].values()), str(g))
check("the control account's own opening is aged as brought forward", own["ageing"]["brought_forward"] == S(3500), str(own["ageing"]))
check("the totals' ageing leaves out a customer in credit, which is shown apart",
      T["totals"]["ageing"] == {"current": S(800), "d31_60": S(1500), "d61_90": 0, "over_90": S(1200), "brought_forward": S(3900)}
      and T["totals"]["in_credit_sen"] == -S(200)
      and sum(T["totals"]["ageing"].values()) + T["totals"]["in_credit_sen"] == T["totals"]["closing_sen"], str(T["totals"]))
check("the page is told plainly that the oldest invoice is taken as settled first",
      "don't say which receipt or payment settled which invoice" in D["ageing_note"] and "oldest" in D["ageing_note"])
check("the bucket edges: 30 days is current, 31 is 31-60, 90 is 61-90, 91 is over 90",
      [rv._bucket(n) for n in (0, 30, 31, 60, 61, 90, 91)] == ["current", "current", "d31_60", "d31_60", "d61_90", "d61_90", "over_90"])

# ---------- 3. a code with no record in Setup ----------
w = row(D, "305-W0001")
check("a code with no customer record is named as SQL printed it, under its family's control account",
      (w["name"], w["name_from"], w["closing_sen"]) == ("EXAMPLE WIDGET CO", "printed", S(250))
      and w["ageing"]["d61_90"] == S(250) and ctl(D, "305-0000")["ties"] is True, str(w))
check("and a note says it isn't in Setup", any("305-W0001" in n and "Not in Setup" in n for n in D["notes"]), str(D["notes"]))
check("the control account's own line is named from the chart", row(D, "305-0000") is None
      and own["name"] == "TRADE DEBTORS" and own["name_from"] == "chart", str(row(D, "305-0000")))
check("a related party's code is never listed", row(D, "320-D0001") is None
      and row(rv.balances(con, EXR, "2026-01-01", "2026-06-30"), "320-D0001") is None)

# ---------- 4. the suppliers ----------
P = rv.balances(con, EXR, "2026-01-01", "2026-06-30", "suppliers")
check("the suppliers' side lists trade creditors", [x["code"] for x in P["controls"]] == ["400-0000"], str([x["code"] for x in P["controls"]]))
s = row(P, "400-S0001")
check("the supplier: what the company owes, credits above 0",
      (s["name"], s["opening_sen"], s["invoiced_sen"], s["received_sen"], s["other_sen"], s["closing_sen"])
      == ("Example Paper Supplies", 0, S(1600), S(500), 0, S(1100)), str(s))
check("the payment settles the oldest invoice: PI-0001's rest over 90 days, PI-0002 31-60",
      s["ageing"] == {"current": 0, "d31_60": S(900), "d61_90": 0, "over_90": S(200), "brought_forward": 0}, str(s["ageing"]))
T = ctl(P, "400-0000")
check("the suppliers tie to trade creditors", T["ties"] is True and (T["totals"]["opening_sen"], T["totals"]["closing_sen"]) == (S(3000), S(4100))
      and T["tb"]["closing_sen"] == S(4100), T["text"])
check("both sides at once", [x["side"] for x in rv.balances(con, EXR, "2026-01-01", "2026-06-30")["controls"]] == ["customers", "customers", "suppliers"])

# ---------- 5. a period starting later, and the checks failing plainly ----------
D2 = rv.balances(con, EXR, "2026-04-01", "2026-06-30", "customers")
a2 = row(D2, "300-A0001")
check("from 1 April, Alpha opens with what it owed then", (a2["opening_sen"], a2["invoiced_sen"], a2["received_sen"], a2["closing_sen"])
      == (S(3000), S(1800), S(1600), S(3000)) and D2["ties"] is True, str(a2))
real_tb = rv.books.trial_balance


def off_tb(*args, **kw):
    out = real_tb(*args, **kw)
    for r in out["accounts"]:
        if r["code"] == "300-0000":
            r["closing_sen"] += 100
    return out


rv.books.trial_balance = off_tb
try:
    D3 = rv.balances(con, EXR, "2026-01-01", "2026-06-30", "customers")
finally:
    rv.books.trial_balance = real_tb
T3 = ctl(D3, "300-0000")
check("when the totals don't tie, it says so plainly, by how much and why", T3["ties"] is False and D3["ties"] is False
      and "don't add up to the control account" in T3["text"] and "a difference of -1.00" in T3["text"]
      and "Trial balance tab" in T3["text"], T3["text"])
V = rv.balances(con, EXV, "2026-01-01", "2026-06-30", "customers")
check("with no opening kept, nothing is claimed and it says why", V["ties"] is None and ctl(V, "300-0000")["ties"] is None
      and row(V, "300-Z0001")["opening_sen"] is None and "can't be checked" in ctl(V, "300-0000")["text"], str(V["controls"]))

# ---------- 6. a statement ----------
St = rv.statement(con, EXR, "300-a0001", "2026-01-01", "2026-06-30")
check("Alpha's statement: every line with its running balance",
      [(r["doc_no"], r["balance_sen"]) for r in St["rows"]] == [("IV-0001", S(1000)), ("IV-0002", S(3000)), ("OR-0001", S(1400)),
                                                                 ("IV-0003", S(2900)), ("IV-0004", S(3200)), ("CN-0001", S(3000))]
      and St["closing_sen"] == S(3000) and St["owed_sen"] == S(3000) and St["control"] == "300-0000", str(St["rows"]))
check("its open invoices with their age, the oldest part-paid",
      [(i["doc_no"], i["open_sen"], i["days"], i["bucket"]) for i in St["open_items"]]
      == [("IV-0002", S(1200), 107, "over_90"), ("IV-0003", S(1500), 41, "d31_60"), ("IV-0004", S(300), 10, "current")], str(St["open_items"]))
Sb = rv.statement(con, EXR, "300-A0002", "2026-01-01", "2026-06-30")
check("Beta's statement shows the brought forward still open", Sb["opening_sen"] == S(1000)
      and [(i["doc_no"], i["open_sen"], i["bucket"]) for i in Sb["open_items"]] == [(None, S(400), "brought_forward"), ("IV-0010", S(500), "current")],
      str(Sb["open_items"]))
Sg = rv.statement(con, EXR, "300-A0003", "2026-01-01", "2026-06-30")
check("Gamma's statement: in credit, nothing open", Sg["credit"] is True and Sg["open_items"] == [] and Sg["owed_sen"] == -S(200))
Ss = rv.statement(con, EXR, "400-S0001", "2026-01-01", "2026-06-30")
check("the supplier's statement: owed to them, credit in the ledger", Ss["side"] == "suppliers" and Ss["closing_sen"] == -S(1100)
      and Ss["owed_sen"] == S(1100) and [i["doc_no"] for i in Ss["open_items"]] == ["PI-0001", "PI-0002"])
try:
    rv.statement(con, EXR, "500-0000", "2026-01-01", "2026-06-30")
    check("an account that isn't a customer's or supplier's is refused", False)
except ValueError as ex:
    check("an account that isn't a customer's or supplier's is refused in words", "isn't a customer's or supplier's code" in str(ex), str(ex))

# ---------- 6b. a customer with several openings of its own: every invoice after the first is aged ----------
# EXW's SQL trial balance is fetched again each month, so customer 300-A0001 has its own opening at 1 Jan (100.00), then
# 1 Jul (3,100.00: agrees with the opening and the two invoices since), 1 Aug (3,300.00: 200.00 more than the lines say)
# and 1 Sep (3,000.00: 300.00 less).
EXW = q("SELECT id FROM entities WHERE code = 'EXW'")[0]["id"]
write("EXW's chart and customer",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)", (EXW, *a)) for a in CHART],
      ("UPDATE entities SET fy_start = 1 WHERE id = ?", (EXW,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'customer', 'Example Alpha Trading', '300-A0001', '300-0000')", (EXW,)))
con = db.connect()
con.arm("user", "test: EXW's SQL documents")
imp3 = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'w.xlsx', ?, 0, 0)", (EXW, db.now())).lastrowid
jb3 = ledger.new_batch(con, EXW, origin="sql", report="journal", sql_import_id=imp3, file_name="jot3.xlsx", period_from="2026-01-01",
                       period_to="2026-12-31", period_source="printed", sections=[{"label": "Sales Journal", "book": "sales"}])
for day, alpha in (("2026-01-01", 100), ("2026-07-01", 3100), ("2026-08-01", 3300), ("2026-09-01", 3000)):
    tbw = ledger.new_batch(con, EXW, origin="sql", report="trial_balance", sql_import_id=imp3, file_name=f"tb-{day}.xlsx",
                           period_from=day, period_to="2026-12-31")
    ledger.put_openings(con, EXW, tbw, day, "sql_tb", [{"code": "300-A0001", "dr_sen": S(alpha), "cr_sen": 0},
                                                       {"code": "100-0000", "dr_sen": 0, "cr_sen": S(alpha)}], True)
doc(EXW, "IV-W001", "2026-03-10", "sales", [("300-A0001", 1000, 0), ("500-0000", 0, 1000)], jb3)
doc(EXW, "IV-W002", "2026-05-10", "sales", [("300-A0001", 2000, 0), ("500-0000", 0, 2000)], jb3)
con.commit()
con.disarm()
Sw = rv.statement(con, EXW, "300-A0001", "2026-01-01", "2026-06-30")
check("ageing to the day before a later opening of the customer's own ages every invoice since its first opening",
      Sw["ageing"] == {"current": 0, "d31_60": S(2000), "d61_90": 0, "over_90": S(1000), "brought_forward": S(100)}
      and [(i["doc_no"], i["date"], i["open_sen"], i["days"], i["bucket"]) for i in Sw["open_items"]]
      == [(None, "2026-01-01", S(100), 180, "brought_forward"), ("IV-W001", "2026-03-10", S(1000), 112, "over_90"),
          ("IV-W002", "2026-05-10", S(2000), 51, "d31_60")], Sw["open_items"])
check("no open item is dated after the To date", all(i["date"] <= "2026-06-30" for i in Sw["open_items"]))
Sw = rv.statement(con, EXW, "300-A0001", "2026-01-01", "2026-07-30")
check("a later opening that agrees with the lines changes nothing: the invoices are still aged",
      Sw["ageing"] == {"current": 0, "d31_60": 0, "d61_90": S(2000), "over_90": S(1000), "brought_forward": S(100)}, Sw["ageing"])
Sw = rv.statement(con, EXW, "300-A0001", "2026-01-01", "2026-07-31")
check("an opening the day after the To date (the balance at its end) only adds its difference, dated the To date",
      Sw["ageing"] == {"current": 0, "d31_60": 0, "d61_90": S(2000), "over_90": S(1000), "brought_forward": S(300)}
      and [(i["date"], i["open_sen"]) for i in Sw["open_items"] if i["bucket"] == "brought_forward"]
      == [("2026-01-01", S(100)), ("2026-07-31", S(200))] and sum(Sw["ageing"].values()) == Sw["owed_sen"], Sw["open_items"])
Sw = rv.statement(con, EXW, "300-A0001", "2026-01-01", "2026-08-30")
check("a later opening that says more brings only the difference forward, at its date",
      Sw["ageing"] == {"current": 0, "d31_60": 0, "d61_90": 0, "over_90": S(3000), "brought_forward": S(300)}
      and [(i["date"], i["open_sen"]) for i in Sw["open_items"] if i["bucket"] == "brought_forward"]
      == [("2026-01-01", S(100)), ("2026-08-01", S(200))]
      and sum(Sw["ageing"].values()) == Sw["owed_sen"] == S(3300), Sw["open_items"])
Sw = rv.statement(con, EXW, "300-A0001", "2026-01-01", "2026-09-30")
check("a later opening that says less settles the oldest first",
      Sw["ageing"] == {"current": 0, "d31_60": 0, "d61_90": 0, "over_90": S(2800), "brought_forward": S(200)}
      and [(i["doc_no"], i["open_sen"]) for i in Sw["open_items"]] == [("IV-W001", S(800)), ("IV-W002", S(2000)), (None, S(200))]
      and sum(Sw["ageing"].values()) == Sw["owed_sen"] == S(3000), Sw["open_items"])
Dw = rv.balances(con, EXW, "2026-01-01", "2026-06-30", "customers")
check("the balances list ages the same way", row(Dw, "300-A0001")["ageing"] == {"current": 0, "d31_60": S(2000), "d61_90": 0,
                                                                              "over_90": S(1000), "brought_forward": S(100)}
      and ctl(Dw, "300-0000")["totals"]["ageing"]["brought_forward"] == S(100), row(Dw, "300-A0001"))

# ---------- 7. the routes the page reads ----------
trail_before = q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"]
d = j("get", f"/api/books/parties?entity={EXR}&from=2026-01-01&to=2026-06-30&side=customers")
check("the list route gives what the page reads", {"from", "to", "sides", "controls", "ties", "text", "ageing_note", "buckets", "notes"} <= d.keys()
      and all({"code", "name", "side", "rows", "totals", "tb", "ties", "text"} <= x.keys() for x in d["controls"])
      and all({"code", "name", "name_from", "own", "opening_sen", "invoiced_sen", "received_sen", "other_sen", "closing_sen", "credit", "ageing", "notes"} <= r.keys()
              for x in d["controls"] for r in x["rows"])
      and {"opening_sen", "closing_sen", "moved_sen"} <= d["controls"][0]["tb"].keys() and d["ties"] is True, str(d.keys()))
d = j("get", f"/api/books/parties?entity={EXR}&side=suppliers")
check("with no dates, the financial year to date", d["to"] == date.today().isoformat() and d["from"] == f"{date.today().year}-01-01"
      and d["sides"] == ["suppliers"], str((d["from"], d["to"])))
check("a side that isn't one is refused in words", "Side is" in j("get", f"/api/books/parties?entity={EXR}&side=everyone", 400)["error"])
d = j("get", f"/api/books/party?entity={EXR}&code=300-A0001&from=2026-01-01&to=2026-06-30")
check("the statement route gives what the page reads", {"code", "name", "control", "side", "from", "to", "opening_sen", "closing_sen", "owed_sen",
                                                        "credit", "rows", "open_items", "ageing", "ageing_note", "notes"} <= d.keys()
      and all({"date", "doc_no", "origin", "book", "description", "dr_sen", "cr_sen", "balance_sen"} <= r.keys() for r in d["rows"])
      and all({"date", "doc_no", "origin", "amount_sen", "open_sen", "days", "bucket", "bucket_words"} <= i.keys() for i in d["open_items"]), str(d.keys()))
check("a code that isn't a customer's or supplier's is refused in words",
      "isn't a customer's or supplier's" in j("get", f"/api/books/party?entity={EXR}&code=500-0000", 400)["error"])
check("an empty code asks for one in plain words",
      j("get", f"/api/books/party?entity={EXR}&code=", 400)["error"] == "Give the code of a customer or supplier.")
check("a date that isn't one is refused in words", "isn't a date" in j("get", f"/api/books/parties?entity={EXR}&to=20260630", 400)["error"])
check("the routes write nothing", q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"] == trail_before)

# ---------- 8. the page ----------
js = (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8")
check("the Books page has the Customers and suppliers tab, reading the routes",
      'data-bk-tab="parties"' in js and "/api/books/parties" in js and "/api/books/party?" in js
      and 'data-bk-side="customers"' in js and 'data-bk-side="suppliers"' in js and "data-bk-party=" in js
      and "function partiesHtml(d)" in js and "function partyHtml(d)" in js and "d.ageing_note" in js)
src = js.replace("\r\n", "\n")
parts = [re.search(p, src, re.S).group(0) for p in (
    r"const esc = s => .*?\n", r"const rmPlain = n => .*?\n", r"const rmCell = n => .*?\n", r"const drCr = n => .*?\n",
    r"const BOOK_NAMES = .*?\n", r"const fsAmt = n => .*?\n", r"function fsBanner\(.*?\n\}\n", r"const AR_AGE = .*?\n",
    r"function partiesHtml\(d\) \{.*?\n\}\n", r"function partyHtml\(d\) \{.*?\n\}\n")]
lst = j("get", f"/api/books/parties?entity={EXR}&from=2026-01-01&to=2026-06-30&side=customers")
one = j("get", f"/api/books/party?entity={EXR}&code=300-A0001&from=2026-01-01&to=2026-06-30")
probe = ("const state = {books: {side: 'customers'}}; const ent = () => ({uses_sql: true}); const fmtDate = x => x; const shortDate = x => x;\n"
         + "".join(parts) + f"\nconsole.log(JSON.stringify([partiesHtml({json.dumps(lst)}), partyHtml({json.dumps(one)}), "
         + f"partiesHtml({json.dumps({**lst, 'controls': []})})]));")
out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
html = json.loads(out.stdout) if out.returncode == 0 else ["", "", ""]
check("the page draws the list, with each code opening its statement, the ties and the customer in credit",
      'data-bk-party="300-A0001"' in html[0] and "Example Alpha Trading" in html[0] and "In credit" in html[0]
      and "Ties to the trial balance" in html[0] and "Not in Setup" in html[0] and "<script" not in html[0], out.stderr[:800])
check("the page draws the statement, with doc nos opening their lines and the open invoices aged",
      'data-bk-doc="IV-0002"' in html[1] and "Over 90 days" in html[1] and "Still open at" in html[1], out.stderr[:800])
check("an empty list says so", "No customer balance is kept" in html[2], html[2][:400])
con.close()
print("All receivables tests passed.")
