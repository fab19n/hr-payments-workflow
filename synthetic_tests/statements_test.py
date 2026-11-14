"""The financial statements (hrp/finstatements.py): the profit and loss account and the balance sheet, on made-up
records only. A made-up chart with SQL groups and sub-accounts, documents entered here over two years, a company whose
year starts in April, and one kept in SQL with a trial balance's openings.

Run: .venv\\Scripts\\python -m synthetic_tests.statements_test
"""
import json
from datetime import date
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-statements-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, finstatements as fs, ledger  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXS", "name": "Example Statements Sdn Bhd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXA", "name": "Example April Sdn Bhd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "EXQ", "name": "Example In SQL Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
    {"code": "EXL", "name": "Example Later Opening Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-444"}]},
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


EXS, EXA, EXQ, EXL = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXS", "EXA", "EXQ", "EXL"))
# code, name, type, special, SQL group, parent
CHART = [("100-0000", "SHARE CAPITAL", "equity", None, "CP", None),
         ("150-0000", "RETAINED EARNINGS", "equity", None, "RE", None),
         ("200-0000", "MOTOR VEHICLE", "asset", None, "FA", None),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA", None),
         ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank", "CA", None),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL", None),
         ("410-0000", "TAX PAYABLE", "liability", None, "CL", None),
         ("500-0000", "SALES", "income", None, "SL", None),
         ("510-0000", "SALES RETURNS", "income", None, "SA", None),
         ("600-0000", "PURCHASES", "expense", None, "CO", None),
         ("530-0000", "RENTAL INCOME", "income", None, None, None),
         ("900-0000", "ADMINISTRATIVE EXPENSES", "expense", None, "EP", None),
         ("900-0100", "ELECTRICITY", "expense", None, "EP", "900-0000"),
         ("900-0200", "WATER", "expense", None, "EP", "900-0000"),
         ("950-0000", "INCOME TAX", "expense", None, "TX", None),
         ("990-0000", "SUSPENSE", None, None, None, None)]
write("the made-up charts",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type, parent_code) VALUES (?, ?, ?, ?, ?, ?, ?)", (e, *a))
        for e in (EXS, EXA, EXQ, EXL) for a in CHART],
      ("UPDATE entities SET fy_start = 1 WHERE id IN (?, ?, ?)", (EXS, EXQ, EXL)),
      ("UPDATE entities SET fy_start = 4 WHERE id = ?", (EXA,)))

con = db.connect()
con.arm("user", "test: the documents")
batches = {}


def doc(eid, no, d, lines):
    if eid not in batches:
        batches[eid] = ledger.new_batch(con, eid, origin="here", report="entered")
    ledger.put_document(con, eid, batches[eid], {"doc_no": no, "doc_date": d, "book": "general", "origin": "here",
                                                 "lines": [{"code": k, "dr_sen": S(dr), "cr_sen": S(cr)} for k, dr, cr in lines]})


# EXS: a year before (2025), then January to March 2026.
doc(EXS, "JV-1", "2025-01-02", [("310-1000", 50000, 0), ("100-0000", 0, 50000)])
doc(EXS, "SI-1", "2025-03-10", [("300-C0001", 10000, 0), ("500-0000", 0, 10000)])
doc(EXS, "PI-1", "2025-03-15", [("600-0000", 4000, 0), ("400-0000", 0, 4000)])
doc(EXS, "PV-1", "2025-04-01", [("900-0100", 500, 0), ("310-1000", 0, 500)])
doc(EXS, "SI-2", "2026-01-15", [("300-C0001", 20000, 0), ("500-0000", 0, 20000)])
doc(EXS, "CN-1", "2026-02-05", [("510-0000", 1000, 0), ("300-C0001", 0, 1000)])
doc(EXS, "PI-2", "2026-02-10", [("600-0000", 8000, 0), ("400-0000", 0, 8000)])
doc(EXS, "OR-1", "2026-02-20", [("310-1000", 1200, 0), ("530-0000", 0, 1200)])
doc(EXS, "PV-2", "2026-03-05", [("900-0100", 300, 0), ("900-0200", 200, 0), ("310-1000", 0, 500)])
doc(EXS, "PV-3", "2026-03-31", [("900-0000", 100, 0), ("310-1000", 0, 100)])
doc(EXS, "JV-2", "2026-03-31", [("950-0000", 2000, 0), ("410-0000", 0, 2000)])
doc(EXS, "JV-3", "2026-03-20", [("200-0000", 30000, 0), ("310-1000", 0, 30000)])
doc(EXS, "OR-2", "2026-03-25", [("310-1000", 15000, 0), ("300-C0001", 0, 15000)])
# EXA: the financial year starts in April.
doc(EXA, "OR-A1", "2026-02-10", [("310-1000", 5000, 0), ("500-0000", 0, 5000)])
doc(EXA, "OR-A2", "2026-04-10", [("310-1000", 3000, 0), ("500-0000", 0, 3000)])
doc(EXA, "PV-A1", "2026-05-10", [("900-0100", 400, 0), ("310-1000", 0, 400)])
# EXQ: kept in SQL; its trial balance's openings at 1 January 2026 and its journal for 2026.
imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXQ, db.now())).lastrowid
tb_b = ledger.new_batch(con, EXQ, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx", period_from="2026-01-01", period_to="2026-12-31")
ledger.put_openings(con, EXQ, tb_b, "2026-01-01", "sql_tb", [{"code": "310-1000", "dr_sen": S(9000), "cr_sen": 0},
                                                           {"code": "100-0000", "dr_sen": 0, "cr_sen": S(6000)},
                                                           {"code": "150-0000", "dr_sen": 0, "cr_sen": S(3000)}], True)
jb = ledger.new_batch(con, EXQ, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-01-01",
                      period_to="2026-12-31", period_source="printed", sections=[{"label": "Bank Journal", "book": "bank"}])
ledger.put_document(con, EXQ, jb, {"doc_no": "OR2602-001", "doc_date": "2026-02-15", "book": "bank",
                                   "lines": [{"code": "310-1000", "dr_sen": S(700), "cr_sen": 0}, {"code": "500-0000", "dr_sen": 0, "cr_sen": S(700)}]})
# EXL: kept in SQL, with only SQL's GL ledger printed from 1 March (its sales Balance B/F the year so far).
lb = ledger.new_batch(con, EXL, origin="sql", report="gl_ledger", sql_import_id=imp, file_name="gl.xlsx", period_from="2026-03-01", period_to="2026-03-31")
ledger.put_openings(con, EXL, lb, "2026-03-01", "sql_ledger", [{"code": "310-1000", "dr_sen": S(2000), "cr_sen": 0},
                                                             {"code": "500-0000", "dr_sen": 0, "cr_sen": S(2000)}], False)
con.commit()
con.disarm()


def block(d, key):
    return next((b for b in d["blocks"] if b["key"] == key), None)


def rows(d, key, col=0):
    b = block(d, key)
    return {(r["kind"], r["code"]): r["amounts"][col] for r in b["rows"]} if b else {}


def fig(d, key, col=0):
    return d["figures"][key][col]


# ---------- 1. the profit and loss account ----------
P = fs.profit_and_loss(con, EXS, "2026-01-01", "2026-03-31")
check("the sections come in SQL's order, with only the sections that have accounts",
      [(b["kind"], b["key"]) for b in P["blocks"]] == [("section", "sales"), ("section", "cost_of_sales"), ("total", "gross_profit"),
                                                       ("section", "other_income"), ("section", "expenses"), ("total", "before_tax"),
                                                       ("section", "taxation"), ("total", "after_tax")], str([b["key"] for b in P["blocks"]]))
check("sales are shown as credits, the sales returns taken off", rows(P, "sales") == {("account", "500-0000"): S(20000), ("account", "510-0000"): -S(1000)}
      and fig(P, "sales") == S(19000), str(rows(P, "sales")))
check("cost of sales and gross profit", fig(P, "cost_of_sales") == S(8000) and fig(P, "gross_profit") == S(11000))
check("an income account with no SQL group goes under Other income, with a note", rows(P, "other_income") == {("account", "530-0000"): S(1200)}
      and any(n.startswith("530-0000 RENTAL INCOME is an income account but it has no SQL group") for n in P["notes"]), str(P["notes"]))
check("sub-accounts sit under their parent, with the parent's total after them",
      [(r["kind"], r["code"], r["depth"], r["amounts"][0]) for r in block(P, "expenses")["rows"]]
      == [("account", "900-0000", 0, S(100)), ("account", "900-0100", 1, S(300)), ("account", "900-0200", 1, S(200)),
          ("group_total", "900-0000", 0, S(600))] and fig(P, "expenses") == S(600), str(block(P, "expenses")["rows"]))
check("the parent's total is named", block(P, "expenses")["rows"][-1]["name"] == "Total ADMINISTRATIVE EXPENSES")
check("profit before tax, taxation and profit after tax", (fig(P, "before_tax"), fig(P, "taxation"), fig(P, "after_tax")) == (S(11600), S(2000), S(9600)))
check("it reconciles to the trial balance", P["check"]["reconciles"] is True and P["check"]["tb_net_sen"] == S(9600)
      and "is the trial balance's profit and loss accounts' movement" in P["check"]["text"], P["check"]["text"])
check("the same period a year before is the comparative column", P["comparative"]["shown"]
      and [c["role"] for c in P["columns"]] == ["total", "comparative"] and P["columns"][1]["from"] == "2025-01-01" and P["columns"][1]["to"] == "2025-03-31"
      and (fig(P, "sales", 1), fig(P, "cost_of_sales", 1), fig(P, "expenses", 1), fig(P, "after_tax", 1)) == (S(10000), S(4000), 0, S(6000)),
      str(P["comparative"]))
check("an account with nothing in the period but something in the comparative is still listed", rows(P, "expenses", 1)[("account", "900-0100")] == 0
      and rows(P, "sales", 1)[("account", "510-0000")] == 0)

M = fs.profit_and_loss(con, EXS, "2026-01-01", "2026-03-31", columns="month")
check("months: one column per month, then the total, then the comparative",
      [(c["role"], c["label"]) for c in M["columns"]] == [("month", "Jan 2026"), ("month", "Feb 2026"), ("month", "Mar 2026"),
                                                         ("total", "01/01/2026 to 31/03/2026"), ("comparative", "01/01/2025 to 31/03/2025")],
      str(M["columns"]))
check("each month's figures", M["figures"]["after_tax"] == [S(20000), -S(7800), -S(2600), S(9600), S(6000)], str(M["figures"]["after_tax"]))
check("the months add up to the total on every row", M["check"]["months_add_up"] is True
      and all(sum(r["amounts"][:3]) == r["amounts"][3] for b in M["blocks"] if b["kind"] == "section" for r in b["rows"])
      and all(sum(v[:3]) == v[3] for v in M["figures"].values()), M["check"]["text"])
check("months over two years are refused in words", "up to 24 months" in j("get", f"/api/books/profit-and-loss?entity={EXS}&from=2024-01-01&to=2026-03-31&columns=month", 400)["error"])

# ---------- 2. the balance sheet ----------
BS = fs.balance_sheet(con, EXS, "2026-03-31")
check("the balance sheet's sections", [(b["kind"], b["key"]) for b in BS["blocks"]] == [
    ("section", "non_current_assets"), ("section", "current_assets"), ("section", "current_liabilities"), ("total", "net_current_assets"),
    ("total", "net_assets"), ("section", "capital"), ("section", "retained"), ("line", "profit"), ("total", "total_equity")],
      str([b["key"] for b in BS["blocks"]]))
ca = {r["code"]: r for r in block(BS, "current_assets")["rows"]}
check("a customer's code is rolled into trade debtors", ca["300-0000"]["amounts"][0] == S(14000) and ca["300-0000"]["rolled"] == ["300-C0001"]
      and "300-C0001" not in ca, str(ca))
check("assets and liabilities", (fig(BS, "non_current_assets"), fig(BS, "current_assets"), fig(BS, "current_liabilities"),
                                 fig(BS, "net_current_assets"), fig(BS, "net_assets")) == (S(30000), S(49100), S(14000), S(35100), S(65100)),
      str(BS["figures"]))
check("equity: capital, retained earnings brought forward and this year's profit", (fig(BS, "capital"), fig(BS, "retained"), fig(BS, "profit"),
                                                                                     fig(BS, "total_equity")) == (S(50000), S(5500), S(9600), S(65100)))
check("it balances, and the year's profit is the profit and loss account's", BS["balanced"] is True and BS["difference_sen"] == 0
      and BS["check"]["ties_to_profit_and_loss"] is True and BS["check"]["reconciles"] is True and BS["check"]["text"].startswith("Balances"),
      BS["check"]["text"])
check("the end of the previous financial year is the comparative", BS["comparative"]["shown"] and BS["columns"][1]["as_at"] == "2025-12-31"
      and (fig(BS, "net_assets", 1), fig(BS, "capital", 1), fig(BS, "retained", 1), fig(BS, "profit", 1), fig(BS, "total_equity", 1))
      == (S(55500), S(50000), 0, S(5500), S(55500)), str(BS["figures"]))

# An unclassified account: listed apart, left out of both sides, and the difference it makes explained.
con.arm("user", "test: a line to an account with no type")
doc(EXS, "JV-4", "2026-03-31", [("990-0000", 700, 0), ("310-1000", 0, 700)])
con.commit()
con.disarm()
BS = fs.balance_sheet(con, EXS, "2026-03-31")
check("an account with no type is listed under Not classified", rows(BS, "not_classified") == {("account", "990-0000"): S(700)}
      and any(n.startswith("Not typed in the chart of accounts") and "990-0000" in n for n in BS["notes"]), str(BS["notes"]))
check("the balance sheet doesn't balance by its amount, and says why", BS["balanced"] is False and BS["difference_sen"] == -S(700)
      and "a difference of -700.00" in BS["check"]["text"] and "not classified (990-0000) hold 700.00 debit" in BS["check"]["text"]
      and BS["check"]["reconciles"] is False, BS["check"]["text"])
P = fs.profit_and_loss(con, EXS, "2026-01-01", "2026-03-31")
check("the profit and loss account lists it too, out of the profit", rows(P, "not_classified") == {("account", "990-0000"): S(700)}
      and fig(P, "after_tax") == S(9600) and P["check"]["reconciles"] is True
      and any("Set their types in Setup" in n and "990-0000" in n for n in P["notes"]))

# ---------- 3. a financial year starting in April ----------
P = fs.profit_and_loss(con, EXA, None, "2026-05-31")
check("the default period is the financial year to date, from 1 April", (P["from"], P["to"]) == ("2026-04-01", "2026-05-31")
      and (fig(P, "sales"), fig(P, "expenses"), fig(P, "after_tax")) == (S(3000), S(400), S(2600)), str(P["figures"]))
check("with nothing kept a year before, no comparative, and it says why", not P["comparative"]["shown"] and len(P["columns"]) == 1
      and P["comparative"]["why"].startswith("Nothing is kept for 01/04/2025 to 31/05/2025"), str(P["comparative"]))
BS = fs.balance_sheet(con, EXA, "2026-05-31")
check("the year to date runs from 1 April, January to March brought forward in retained earnings", BS["fy_from"] == "2026-04-01"
      and (fig(BS, "current_assets"), fig(BS, "retained"), fig(BS, "profit"), fig(BS, "total_equity")) == (S(7600), S(5000), S(2600), S(7600))
      and BS["balanced"] is True and BS["check"]["reconciles"] is True, str(BS["figures"]))
check("its comparative is 31 March", BS["comparative"]["shown"] and BS["columns"][1]["as_at"] == "2026-03-31"
      and (fig(BS, "retained", 1), fig(BS, "profit", 1), fig(BS, "total_equity", 1)) == (0, S(5000), S(5000)), str(BS["figures"]))
P = fs.profit_and_loss(con, EXA, "2026-03-01", "2026-04-30")
check("a period across the year start has no comparative, and says why", not P["comparative"]["shown"]
      and "runs across the start of a financial year" in P["comparative"]["why"] and fig(P, "sales") == S(3000), str(P["comparative"]))

# ---------- 4. a company kept in SQL ----------
P = fs.profit_and_loss(con, EXQ, "2026-01-01", "2026-03-31")
check("kept in SQL from a trial balance at 1 January: this year's profit, no comparative before it", fig(P, "after_tax") == S(700)
      and not P["comparative"]["shown"] and P["comparative"]["why"].startswith("Nothing is kept"), str(P["comparative"]))
BS = fs.balance_sheet(con, EXQ, "2026-03-31")
check("its balance sheet balances", BS["balanced"] is True and fig(BS, "total_equity") == S(9700) and BS["check"]["reconciles"] is True,
      str(BS["figures"]) + BS["check"]["text"])
check("with only a trial balance at 1 January 2026 kept, 2025's profit isn't known, so there is no 31/12/2025 column, and it says why",
      not BS["comparative"]["shown"] and len(BS["columns"]) == 1
      and "No opening balance is kept on or before 01/01/2025, the start of the previous financial year" in BS["comparative"]["why"],
      str(BS["comparative"]))
BS = fs.balance_sheet(con, EXQ, "2025-06-30")
check("before any opening kept, the amounts are unknown, nothing is claimed, and it says why",
      BS["balanced"] is None and BS["check"]["reconciles"] is None and fig(BS, "net_assets") is None
      and "can't be totalled" in BS["check"]["text"] and not BS["comparative"]["shown"]
      and any(n.startswith("No opening balance is kept for 100-0000") for n in BS["notes"]), str(BS["check"]))

P = fs.profit_and_loss(con, EXL, "2026-01-01", "2026-03-31")
check("from the year start, a profit and loss account opens at 0 even when SQL's only opening for it is later in the year",
      fig(P, "sales") == S(2000) and P["check"]["net_sen"] == P["check"]["tb_net_sen"] == S(2000), str(P["figures"]) + P["check"]["text"])
check("a missing opening at the From date is not called a trial balance that doesn't balance: it can't be fully checked",
      P["check"]["reconciles"] is None and "doesn't balance" not in P["check"]["text"]
      and "can't be fully checked: an opening balance at 01/01/2026 is missing" in P["check"]["text"], P["check"]["text"])
con.arm("user", "test: a GL ledger's opening of retained earnings")
lb2 = ledger.new_batch(con, EXL, origin="sql", report="gl_ledger", sql_import_id=imp, file_name="gl2.xlsx", period_from="2026-03-01", period_to="2026-03-31")
ledger.put_openings(con, EXL, lb2, "2026-03-01", "sql_ledger", [{"code": "150-0000", "dr_sen": 0, "cr_sen": 0}], False)
con.commit()
con.disarm()
BS = fs.balance_sheet(con, EXL, "2026-03-31")
check("every closing known and balancing, the balance sheet reconciles though an opening at the year start is missing",
      BS["balanced"] is True and BS["check"]["ties_to_profit_and_loss"] is True and BS["check"]["reconciles"] is True
      and "doesn't balance" not in BS["check"]["text"] and "is in it once" in BS["check"]["text"], BS["check"]["text"])
tb_fake = {"balanced": False, "totals": {"dr_sen": 100, "cr_sen": 100},
           "accounts": [{"opening_sen": None, "closing_sen": 500}, {"opening_sen": 0, "closing_sen": -400}]}
check("closings that don't balance are still a trial balance that doesn't balance", fs._tb_state(tb_fake) == "unbalanced")
tb_fake["accounts"][1]["closing_sen"] = -500
check("closings that balance with an opening missing can't be fully checked", fs._tb_state(tb_fake) == "no_openings")
tb_fake["accounts"][0]["closing_sen"] = None
check("a closing missing is unknown", fs._tb_state(tb_fake) == "unknown")

# A sub-account in another section from its parent: no phantom parent, no second total of the parent's name.
write("a sub-account of an expense placed under Taxation",
      ("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type, parent_code) VALUES (?, '950-0100', 'DEFERRED TAX', 'expense', NULL, 'TX', '900-0000')", (EXS,)))
con.arm("user", "test: a line to the sub-account")
doc(EXS, "JV-9", "2026-03-31", [("950-0100", 50, 0), ("410-0000", 0, 50)])
con.commit()
con.disarm()
P = fs.profit_and_loss(con, EXS, "2026-01-01", "2026-03-31")
tax_rows = [(r["kind"], r["code"], r["depth"], r["amounts"][0]) for r in block(P, "taxation")["rows"]]
check("a sub-account whose parent is in another section stands on its own, with no parent row or total brought in",
      tax_rows == [("account", "950-0000", 0, S(2000)), ("account", "950-0100", 0, S(50))] and fig(P, "taxation") == S(2050)
      and [r["name"] for r in block(P, "expenses")["rows"] if r["kind"] == "group_total"] == ["Total ADMINISTRATIVE EXPENSES"]
      and fig(P, "expenses") == S(600), str(tax_rows))

# The same period a year before starts on the same day: 28 February stays 28 February.
check("a period starting 28/02/2025 compares from 28/02/2024, not 29/02",
      (fs._year_back_from("2025-02-28"), fs._year_back("2025-02-28")) == ("2024-02-28", "2024-02-29"))
check("other start days move back a year", [fs._year_back_from(x) for x in ("2025-03-01", "2026-01-01", "2024-02-29", "2025-04-15")]
      == ["2024-03-01", "2025-01-01", "2023-03-01", "2024-04-15"])
P = fs.profit_and_loss(con, EXS, "2025-02-28", "2025-03-31")
check("so a profit and loss account from 28/02/2025 compares from 28/02/2024", P["comparative"]["from"] == "2024-02-28", str(P["comparative"]))

# ---------- 5. the routes the page reads ----------
trail_before = q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"]
d = j("get", f"/api/books/profit-and-loss?entity={EXS}&from=2026-01-01&to=2026-03-31&columns=month")
check("the profit and loss route gives what the page reads", {"from", "to", "columns", "columns_mode", "blocks", "figures", "comparative", "check", "notes"} <= d.keys()
      and d["columns_mode"] == "month" and all({"key", "label", "role"} <= c.keys() for c in d["columns"])
      and all({"kind", "key"} <= b.keys() for b in d["blocks"])
      and all({"kind", "code", "name", "depth", "amounts"} <= r.keys() for b in d["blocks"] if b["kind"] == "section" for r in b["rows"])
      and {"reconciles", "text"} <= d["check"].keys(), str(d.keys()))
d = j("get", f"/api/books/profit-and-loss?entity={EXS}")
check("with no dates, the financial year to date", d["to"] == date.today().isoformat() and d["from"] == f"{date.today().year}-01-01", str((d["from"], d["to"])))
d = j("get", f"/api/books/balance-sheet?entity={EXS}&as_at=2026-03-31")
check("the balance sheet route gives what the page reads", {"as_at", "fy_from", "columns", "blocks", "figures", "comparative", "balanced", "difference_sen", "check", "notes"} <= d.keys()
      and d["as_at"] == "2026-03-31" and {"balances", "reconciles", "text"} <= d["check"].keys(), str(d.keys()))
check("an as-at date that isn't one is refused in words", "isn't a date" in j("get", f"/api/books/balance-sheet?entity={EXS}&as_at=20260331", 400)["error"])
check("so are columns that aren't total or month", "Columns" in j("get", f"/api/books/profit-and-loss?entity={EXS}&columns=weeks", 400)["error"])
for path in (f"/api/books/balance-sheet?entity={EXS}&as_at=0001-01-01", f"/api/books/balance-sheet?entity={EXS}&as_at=0001-06-30",
             f"/api/books/balance-sheet?entity={EXS}&as_at=9999-12-31", f"/api/books/profit-and-loss?entity={EXS}&from=0001-01-01&to=0001-03-31",
             f"/api/books/profit-and-loss?entity={EXS}&from=9999-01-01&to=9999-12-31&columns=month",
             f"/api/books/trial-balance?entity={EXS}&from=9999-01-01&to=9999-12-31"):
    e = j("get", path, 400)["error"]
    check(f"a date far out of range is refused in words, not a failure ({path.split('?')[0]})", "out of range" in e and "year must be" not in e, e)
d = j("get", f"/api/books/balance-sheet?entity={EXA}&as_at=2020-06-30")
check("a company with nothing kept at the day has no section in its statement (the page shows its empty message)",
      not any(b["kind"] == "section" for b in d["blocks"]) and all(not any(b["amounts"]) for b in d["blocks"] if b["kind"] == "line"), str(d["blocks"]))
d = j("get", f"/api/books/profit-and-loss?entity={EXA}&from=2020-04-01&to=2020-06-30")
check("nor in its profit and loss account", not any(b["kind"] == "section" for b in d["blocks"]), str(d["blocks"]))
check("the routes write nothing", q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"] == trail_before)

# ---------- 6. the page ----------
js = (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8")
check("the Books page has the Profit and loss and Balance sheet tabs, reading the routes",
      'data-bk-tab="pl"' in js and 'data-bk-tab="bs"' in js and "/api/books/profit-and-loss" in js and "/api/books/balance-sheet" in js
      and 'id="bkMonths"' in js and "data-bk-acct" in js)
check("the page calls a statement empty when no section is listed, not when there are no blocks (the totals are always there)",
      "function fsEmpty(d)" in js and 'b.kind === "section"' in js and "d.blocks.length ?" not in js
      and "if (fsEmpty(d))" in js and js.count('fsBanner(null, "Nothing to check"') == 2)
fn = re.search(r"function fsEmpty\(d\) \{.*?\n\}", js.replace("\r\n", "\n"), re.S).group(0)
probe = fn + """
const z = [{kind: "total", key: "gross_profit", amounts: [0]}, {kind: "line", key: "profit", amounts: [0]}];
console.log(JSON.stringify([fsEmpty({blocks: z}), fsEmpty({blocks: z.concat([{kind: "section", key: "sales"}])}),
                            fsEmpty({blocks: [{kind: "line", key: "profit", amounts: [5]}]})]));"""
out = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=60)
check("fsEmpty: totals alone are empty; a section or a profit line with an amount is not", out.stdout.strip() == "[true,false,false]", out.stdout + out.stderr)
con.close()
print("All statements tests passed.")
