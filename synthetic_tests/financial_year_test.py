"""The financial year start (update 27), a plain Setup field, and the trial balance checks, on made-up records only.

SQL Account's trial balance counts profit and loss from the report's own From date, not from the financial year start:
it moves the earlier P&L into retained earnings on that date, inside Period To Date, with no document. So the financial
year can't be told from a trial balance; the owner enters it in Setup › Companies to match SQL Account. The checks
compare a P&L account's Year To Date with its lines from the From date, its Month To Date with the month's lines (unless
the From date falls inside the month after its 1st), never retained earnings' Period To Date, and note what SQL moved
when the From date isn't the 1st of the financial year (January when not set).

Run: .venv\\Scripts\\python -m synthetic_tests.financial_year_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-financial-year-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db, ledger, masters, setupfile  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXO", "name": "Example October Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXJ", "name": "Example January Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "EXA", "name": "Example Unsure Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
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


def conn(action="test"):
    con = db.connect()
    con.arm("user", action)
    return con


def business_rows():
    """Every row of every table except the audit store, as text, to compare the records before and after an update."""
    with sqlite3.connect(config.DB_PATH) as r:
        out = {}
        for (t,) in r.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'audit_%'"):
            out[t] = [tuple(x) for x in r.execute(f'SELECT * FROM "{t}" ORDER BY rowid')]
        return out


def an_import(con, eid, name="test.xlsx"):
    return con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, 0, 0)",
                       (eid, name, db.now())).lastrowid


def line(code, dr=0, cr=0):
    return {"code": code, "description": "EXAMPLE LINE", "dr_sen": int(round(dr * 100)), "cr_sen": int(round(cr * 100))}


def journal(con, eid, period, docs):
    """A GL Journal of Transaction read with a printed period, keeping the made-up documents."""
    b = ledger.new_batch(con, eid, origin="sql", report="journal", sql_import_id=an_import(con, eid, "jot.xlsx"), file_name="jot.xlsx",
                         period_from=period[0], period_to=period[1], period_source="printed",
                         sections=[{"label": "Bank Journal", "book": "bank"}, {"label": "Sales Journal", "book": "sales"}])
    for d in docs:
        ledger.put_document(con, eid, b, d)
    ledger.finish_batch(con, b, {"docs": len(docs)}, [])


def acct(code, ytd, mtd=(0, 0), open_=(0, 0)):
    """A trial balance row: Year To Date and Month To Date as (debit, credit) in RM."""
    s = lambda p: (int(round(p[0] * 100)), int(round(p[1] * 100)))  # noqa: E731
    return {"code": code, "name": "", "open": s(open_), "ptd": s(mtd), "mtd": s(mtd), "ytd": s(ytd)}


SAL, SALES, RENT, BANK, DEBT, OFFICE = "9S0-T001", "500-1000", "610-0000", "310-1000", "300-0000", "620-0000"
CHART = ((SAL, "SALARY - EXAMPLE", "expense"), (SALES, "SALES - EXAMPLE", "income"), (RENT, "RENT - EXAMPLE", "expense"),
         (BANK, "BANK - EXAMPLE", "asset"), (DEBT, "TRADE DEBTORS", "asset"), (OFFICE, "OFFICE COSTS - EXAMPLE", "expense"))

# ---------- 1. a records.db at update 26, then update 27 ----------
full = db.MIGRATIONS[:]
check("update 27 is the last one", len(full) == 27)
db.MIGRATIONS[:] = full[:26]
db.init()
EXO, EXJ, EXA = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXO", "EXJ", "EXA"))
c = conn("test: records at update 26")
for eid in (EXO, EXJ, EXA):
    for code, name, typ in CHART:
        c.execute("INSERT INTO gl_accounts (entity_id, code, name, type) VALUES (?, ?, ?, ?)", (eid, code, name, typ))
# EXO: the owner's case, journals read from 1 October to 14 November; salary's only line in range is 26 October.
journal(c, EXO, ("2026-10-01", "2026-11-14"), [
    {"doc_no": "PV2610-001", "doc_date": "2026-10-26", "book": "bank", "lines": [line(SAL, dr=5500), line(BANK, cr=5500)]},
    {"doc_no": "IV2610-001", "doc_date": "2026-10-05", "book": "sales", "lines": [line(DEBT, dr=3000), line(SALES, cr=3000)]},
    {"doc_no": "PV2611-001", "doc_date": "2026-11-03", "book": "bank", "lines": [line(RENT, dr=1200), line(BANK, cr=1200)]}])
# EXJ: the whole year fetched, 1 January to 30 November: salary and rent every month, sales in March and October.
docs = []
for m in range(1, 12):
    docs += [{"doc_no": f"PV26{m:02d}-001", "doc_date": f"2026-{m:02d}-25", "book": "bank", "lines": [line(SAL, dr=1000), line(BANK, cr=1000)]},
             {"doc_no": f"PV26{m:02d}-002", "doc_date": f"2026-{m:02d}-02", "book": "bank", "lines": [line(RENT, dr=500), line(BANK, cr=500)]}]
docs += [{"doc_no": f"IV26{m:02d}-001", "doc_date": f"2026-{m:02d}-10", "book": "sales", "lines": [line(DEBT, dr=2000), line(SALES, cr=2000)]}
         for m in (3, 10)]
journal(c, EXJ, ("2026-01-01", "2026-11-30"), docs)
# EXA: October and November read; rent moved on 10 November, and office costs of 1,000 on 25 October and 25 November
# (only trial balances that print the office costs account see those).
journal(c, EXA, ("2026-10-01", "2026-11-30"), [
    {"doc_no": "PV2611-009", "doc_date": "2026-11-10", "book": "bank", "lines": [line(RENT, dr=800), line(BANK, cr=800)]},
    {"doc_no": "PV2610-021", "doc_date": "2026-10-25", "book": "bank", "lines": [line(OFFICE, dr=1000), line(BANK, cr=1000)]},
    {"doc_no": "PV2611-021", "doc_date": "2026-11-25", "book": "bank", "lines": [line(OFFICE, dr=1000), line(BANK, cr=1000)]}])
c.commit()
c.disarm()
c.close()
check("below update 27 there is no financial year setting", "fy_start" not in {r["name"] for r in q("PRAGMA table_info(entities)")})
before = business_rows()
db.MIGRATIONS[:] = full
trail = db.init()
after = business_rows()
check("update 27 runs", q("PRAGMA user_version")[0]["user_version"] == 27)
check("every company gets an empty financial year start", [r["fy_start"] for r in q("SELECT fy_start FROM entities ORDER BY id")] == [None] * 3)
check("every other row is kept as it was",
      {t: r for t, r in after.items() if t not in ("entities", "activity")} == {t: r for t, r in before.items() if t not in ("entities", "activity")}
      and [x[:-1] for x in after["entities"]] == before["entities"] and after["activity"][:len(before["activity"])] == before["activity"])
r = db.connect()
v = audit.verify(r)
r.close()
check("the audit trail checks out after update 27", v["ok"], v)
check("start-up repaired no triggers", trail and not trail["triggers_repaired"], trail)

# ---------- 2. the trial balance checks count profit and loss from the From date ----------
c = conn("test: trial balance checks")
tb_checks = lambda eid, tb, rule=None: [x for x in ledger.report_checks(c, eid, None, tb, "trial_balance")  # noqa: E731
                                        if rule is None or x["rule"] == rule]
warns = lambda res: [(x["rule"], x["subject"], x["expected_sen"], x["actual_sen"]) for x in res if x["outcome"] == "warn"]  # noqa: E731
# The owner's case: from 1 October to 14 November. Salary: opening DR 49,500 (January to September), Period To Date CR
# 44,000 (SQL's move of the 49,500 into retained earnings, and October's 5,500), Year To Date DR 5,500 (its only line
# from 1 October). Sales opened with CR 20,000, so SQL moved a loss of 29,500.00.
tb_o = {"period": ["2026-10-01", "2026-11-14"], "accounts": [
    acct(SAL, (5500, 0), open_=(49500, 0)) | {"ptd": (550000, 4950000)}, acct(SALES, (0, 3000), open_=(0, 20000)),
    acct(RENT, (1200, 0), mtd=(1200, 0)), acct(BANK, (0, 6700), mtd=(0, 1200)), acct(DEBT, (3000, 0))]}
res = tb_checks(EXO, tb_o)
check("a trial balance from 1 October whose P&L Year To Date equals the lines from 1 October passes", warns(res) == []
      and any(x["rule"] == "tb_ytd" and x["outcome"] == "ok" and x["text"] == "3 profit and loss accounts agree with the lines dated "
              "01/10/2026-14/11/2026." for x in res)
      and any(x["rule"] == "tb_mtd" and x["outcome"] == "ok" and x["text"].startswith("5 accounts agree") for x in res)
      and not any(x["outcome"] == "skipped" and x["rule"] in ("tb_mtd", "tb_ytd") for x in res), res)
check("nothing says where the financial year starts any more", not any(x["rule"] in ("tb_fy_start", "tb_year_close") for x in res)
      and not hasattr(ledger, "detect_fy_start"), res)
moved = [x for x in res if x["rule"] == "tb_pl_moved"]
check("with the financial year not set, the move into retained earnings on 1 October is noted",
      len(moved) == 1 and moved[0]["outcome"] == "info" and moved[0]["actual_sen"] == 2950000
      and moved[0]["text"] == "SQL's trial balance counts profit and loss from its From date (01/10/2026), so it moved a loss of "
                              "29,500.00 from earlier into retained earnings. No document carries that move.", moved)
res = tb_checks(EXO, {**tb_o, "accounts": [acct(SALES, (0, 3000), open_=(0, 60000))]})
check("a profit is named as one", [x["text"] for x in res if x["rule"] == "tb_pl_moved"][0].startswith(
    "SQL's trial balance counts profit and loss from its From date (01/10/2026), so it moved a profit of 60,000.00"), res)
res = tb_checks(EXO, {**tb_o, "accounts": [acct(RENT, (1300, 0), mtd=(1200, 0))]})
check("a P&L account whose Year To Date differs from its lines warns, naming both figures",
      [w for w in warns(res) if w[0] == "tb_ytd"] == [("tb_ytd", RENT, 130000, 120000)]
      and any("Year To Date nets 1,300.00, the lines dated 01/10/2026-14/11/2026 1,200.00" in x["text"] for x in res), res)
# The whole year from 1 January: last year's figures are the opening balances, which Year To Date leaves out.
tb_j = {"period": ["2026-01-01", "2026-11-30"], "accounts": [acct(SAL, (11000, 0), mtd=(1000, 0), open_=(12000, 0)),
                                                             acct(SALES, (0, 4000), open_=(0, 4500)),
                                                             acct(RENT, (5500, 0), mtd=(500, 0), open_=(6000, 0)),
                                                             acct(BANK, (0, 16500), mtd=(0, 1500)), acct(DEBT, (4000, 0))]}
res = tb_checks(EXJ, tb_j)
check("a trial balance from 1 January passes", warns(res) == []
      and any(x["rule"] == "tb_ytd" and x["outcome"] == "ok" and x["text"].startswith("3 profit and loss accounts agree") for x in res), res)
check("and notes no move: 1 January is the 1st of the financial year when it isn't set", not any(x["rule"] == "tb_pl_moved" for x in res), res)
# From inside the as-at month, after its 1st: Month To Date holds SQL's move too, so P&L is left out of it.
tb_m = {"period": ["2026-11-10", "2026-11-14"], "accounts": [acct(RENT, (0, 0), mtd=(1200, 0), open_=(1200, 0)) | {"ptd": (0, 120000)},
                                                             acct(BANK, (0, 0), mtd=(0, 1200))]}
res = tb_checks(EXO, tb_m)
check("a trial balance from 10 November leaves P&L out of November's Month To Date, saying why", warns(res) == []
      and any(x["rule"] == "tb_mtd" and x["outcome"] == "skipped" and x["text"] == "1 profit and loss, retained earnings or "
              "unclassified account not compared: the trial balance starts on 10/11/2026, inside the month, so SQL's Month To Date "
              "holds its move of earlier profit and loss into retained earnings." for x in res)
      and any(x["rule"] == "tb_mtd" and x["outcome"] == "ok" and x["text"].startswith("1 account agrees") for x in res)
      and any(x["rule"] == "tb_ytd" and x["outcome"] == "ok" for x in res), res)
res = tb_checks(EXO, {**tb_o, "period": ["2026-11-01", "2026-11-14"], "accounts": [acct(RENT, (1200, 0), mtd=(1300, 0))]})
check("from the month's own 1st, P&L Month To Date is compared",
      [w for w in warns(res) if w[1] == RENT] == [("tb_mtd", RENT, 130000, 120000)], res)
res = tb_checks(EXA, {"period": ["2026-09-01", "2026-11-30"], "accounts": [acct(RENT, (800, 0), mtd=(800, 0))]})
check("Year To Date is not compared when the journals read don't cover the From date, saying why",
      not any(w[0] == "tb_ytd" for w in warns(res)) and any(x["rule"] == "tb_ytd" and x["outcome"] == "skipped" and "01/09/2026-30/11/2026" in x["text"]
                               and "Fetch the journal from the trial balance's From date" in x["text"] for x in res), res)
# No From date printed: read as before, from the P&L figures themselves.
tb_n = {"period": [None, "2026-11-14"], "accounts": [acct(SAL, (5500, 0)), acct(SALES, (0, 3000)), acct(RENT, (1200, 0), mtd=(1300, 0)),
                                                     acct(BANK, (0, 6700), mtd=(0, 1200)), acct(DEBT, (3000, 0))]}
res = tb_checks(EXO, tb_n)
check("with no From date, a P&L difference that reads like a closing month is skipped, as before",
      warns(res) == [] and any("year-end closing" in x["text"] for x in res) and not any(x["rule"] in ("tb_ytd", "tb_pl_moved") for x in res), res)
c.commit()
c.disarm()
c.close()

# ---------- 3. no button and no route offer a month any more ----------
cl = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    resp = getattr(cl, method)(BASE + path, headers=H, **kw)
    assert resp.status_code == expect, (method, path, resp.status_code, resp.data[:500])
    return resp.get_json()


page = j("get", f"/api/sql/entries?entity={EXO}")
check("the SQL page's checks carry no financial year", "fy_start" not in page["ledger"], page["ledger"].keys())
resp = cl.post(BASE + f"/api/entities/{EXO}/fy-start", headers=H, json={"month": 10, "entity_id": EXO})
check("the route that saved the month found is gone", resp.status_code in (404, 405)
      and q("SELECT fy_start FROM entities WHERE id = ?", (EXO,))[0]["fy_start"] is None, resp.status_code)

# ---------- 4. Setup › Companies and the setup file ----------
check("Setup › Companies has the field, with the twelve months",
      any(f["key"] == "fy_start" and f["label"] == "Financial year starts in" and len(f["options"]) == 12 and f["options"][0] == [1, "January"]
          for f in masters.KINDS["entities"]["fields"]))
rec = j("get", f"/api/setup/entities/{EXJ}")["record"]
check("and shows it on the company's record", "fy_start" in rec and rec["fy_start"] is None, rec)
fields = {k: rec[k] for k in ("code", "name")}
got = j("patch", f"/api/setup/entities/{EXJ}", json={"fields": {**fields, "fy_start": "1"}, "entity_id": EXJ})
check("Setup saves a month given as text as its number", q("SELECT fy_start FROM entities WHERE id = ?", (EXJ,))[0]["fy_start"] == 1, got)
e = j("patch", f"/api/setup/entities/{EXJ}", 400, json={"fields": {**fields, "fy_start": 13}, "entity_id": EXJ})
check("and refuses a month that isn't one", "choose one of the options" in e["error"]
      and q("SELECT fy_start FROM entities WHERE id = ?", (EXJ,))[0]["fy_start"] == 1, e)
got = j("patch", f"/api/setup/entities/{EXO}", json={"fields": {"code": "EXO", "name": "Example October Ltd", "fy_start": 10},
                                                       "entity_id": EXO})
check("the financial year is set to October in Setup", q("SELECT fy_start FROM entities WHERE id = ?", (EXO,))[0]["fy_start"] == 10, got)
c = conn("test: checks with the setting")
res = tb_checks(EXO, tb_o)
check("then a trial balance from 1 October notes no move: it is the year's 1st", warns(res) == []
      and not any(x["rule"] == "tb_pl_moved" for x in res), res)
res = tb_checks(EXO, {"period": ["2026-01-01", "2026-11-14"], "accounts": [acct(SAL, (0, 0), open_=(500, 0))]})
check("and one from 1 January does", [x["text"][:97] for x in res if x["rule"] == "tb_pl_moved"]
      == ["SQL's trial balance counts profit and loss from its From date (01/01/2026), so it moved a loss of"], res)
c.disarm()
c.close()
r = db.connect()
out = setupfile.export(r, "full")
r.close()
check("the setup file carries each company's financial year start",
      {x["code"]: x.get("fy_start") for x in out["entities"]} == {"EXO": 10, "EXJ": 1, "EXA": None}, out["entities"])

r = db.connect()
v = audit.verify(r)
r.close()
check("the audit trail still checks out at the end", v["ok"], v)
js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
check("the page has no Use <month> as the financial year button", "data-fy-use" not in js and "fyUse" not in js and "fy-start" not in js)
print("\nAll checks passed. Records folder used:", tmp)
