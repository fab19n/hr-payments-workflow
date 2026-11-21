"""Slice 1: Next up's one-row rule (owner, 19 November; build plan 4.2), on made-up records only.

One Next up row per unpaid statutory payment: while a statutory payment for the month is entered and not paid, Next up shows
only its payment row, "Pay KWSP for October", before its due date and overdue after it (rules 3 and 4 no longer add their own
row for it, and rule 14's statutory payables check says nothing about that kind and month). The rule 14 row shows when there
is no unpaid payment to point at: paid short, or never entered. A made-up company kept in SQL Account, with SQL's books for
its EPF payable (October's salary voucher takes RM 1,500.00 off the salaries) and that account confirmed for the check.

Run: .venv\\Scripts\\python -m synthetic_tests.next_one_row_test
"""
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-next-one-row-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, nextup  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXS", "name": "Example Statutory Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-404"}]},
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


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
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
EXS, ACCT = meta["entities"][0]["id"], meta["entities"][0]["accounts"][0]["id"]
M = "2026-10"
j("post", "/api/months/open", json={"entity_id": EXS, "month": M})
CHART = [("100-0000", "SHARE CAPITAL", "equity", "CP"), ("150-0000", "RETAINED EARNINGS", "equity", "RE"),
         ("310-1000", "BANK-EXAMPLE 0001", "asset", "CA"), ("420-1001", "EPF - PAYABLE", "liability", "CL"),
         ("700-0000", "SALARY - EXAMPLE", "expense", "EP")]
write("the chart and the EPF account confirmed for the check",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, sql_type) VALUES (?, ?, ?, ?, ?)", (EXS, *a)) for a in CHART],
      ("UPDATE entities SET fy_start = 1 WHERE id = ?", (EXS,)),
      ("INSERT INTO statutory_accounts (entity_id, kind, label, payable_code, due_day) VALUES (?, 'epf', 'EPF (KWSP)', '420-1001', 15)", (EXS,)))
con = db.connect()
con.arm("import", "test: SQL's books")
imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXS, db.now())).lastrowid
tb = ledger.new_batch(con, EXS, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx", period_from="2026-01-01", period_to="2026-11-30")
ledger.put_openings(con, EXS, tb, "2026-01-01", "sql_tb", [{"code": "310-1000", "dr_sen": S(20000), "cr_sen": 0}, {"code": "100-0000", "dr_sen": 0, "cr_sen": S(20000)}], True)
jb = ledger.new_batch(con, EXS, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-01-01",
                      period_to="2026-11-30", period_source="printed", sections=[{"label": "Cash Book", "book": "bank"}])


def doc(no, d, lines):
    ledger.put_document(con, EXS, jb, {"doc_no": no, "doc_date": d, "book": "bank", "lines": [
        {"code": x[0], "dr_sen": S(x[1]), "cr_sen": S(x[2]), "description": "made up"} for x in lines]})


doc("PV2610-025", "2026-10-25", [("700-0000", 10000, 0), ("420-1001", 0, 1500), ("310-1000", 0, 8500)])
ledger.finish_batch(con, jb)
con.commit()
con.disarm()
con.close()


def rows(day):
    with db.connect() as r:
        return nextup.items(r, day, EXS)


def about_kwsp(rs):
    return [r for r in rs if "KWSP" in r["text"]]


LATE, EARLY = date(2026, 11, 20), date(2026, 11, 12)

# ---------- never entered: the rule 14 row ----------
rs = rows(LATE)
r14 = [r for r in rs if r["rule"] == 14]
check("no KWSP payment entered: the statutory check's row shows (rule 14), late",
      len(r14) == 1 and r14[0]["month"] == M and r14[0]["text"].startswith("EXS: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026")
      and r14[0]["state"] == "overdue", r14)
check("...and it is the only row about it", len(about_kwsp(rs)) == 1, about_kwsp(rs))

# ---------- entered and not paid: only its payment row ----------
kwsp = j("post", "/api/payments", json={"entity_id": EXS, "month": M, "description": "KWSP", "category": "statutory", "amount": 1500,
                                        "account_id": ACCT, "due_date": "2026-11-15"})["id"]
clean = j("post", "/api/payments", json={"entity_id": EXS, "month": M, "description": "Cleaning service - test", "category": "other", "amount": 300,
                                         "account_id": ACCT, "due_date": "2026-11-15"})["id"]
rs = rows(EARLY)
k = about_kwsp(rs)
check("before its due date: one row, 'Pay KWSP for October', with what is still to pay (rule 5)",
      len(k) == 1 and k[0]["text"] == "Pay KWSP for October: RM 1,500.00" and k[0]["rule"] == 5 and k[0]["due"] == "2026-11-15"
      and k[0]["state"] == "soon" and k[0]["amount"] == 1500, k)
check("...opening the payment", k and k[0]["go"]["view"] == "entity" and k[0]["go"]["payment_id"] == kwsp, k and k[0]["go"])
other = [r for r in rs if r["rule"] == 5 and r is not k[0]]
check("...never grouped with a bill due the same day, which keeps its own row",
      len(other) == 1 and other[0]["text"] == "Pay Cleaning service - test from EXS by 15 Nov: RM 300.00", other)
rs = rows(LATE)
k = about_kwsp(rs)
check("after its due date: still that one row, overdue, saying the legal deadline is past",
      len(k) == 1 and k[0]["text"].startswith("Pay KWSP for October: RM 1,500.00") and "past the legal deadline of 15 Nov" in k[0]["text"]
      and k[0]["state"] == "overdue" and k[0]["priority"] == 1, k)
check("...rule 14 says nothing about EPF for October, and rules 3 and 4 add no row of their own for it",
      not [r for r in rs if r["rule"] == 14] and not [r for r in rs if r["rule"] in (3, 4) and r["key"].endswith((":past_legal", ":legal_soon", ":not_on_statement"))
                                                   and "KWSP" in r["text"]], [r["text"] for r in rs])
with db.connect() as r:
    e = r.execute("SELECT * FROM entities WHERE id = ?", (EXS,)).fetchone()
    covered = nextup._unpaid_statutory(r, e)
check("the kinds an unpaid payment stands for are read from its name", covered == {("epf", M)}, covered)
j("patch", f"/api/payments/{clean}", json={"description": "PERKESO"})
j("patch", f"/api/payments/{clean}", json={"category": "statutory"})
with db.connect() as r:
    covered = nextup._unpaid_statutory(r, e)
check("...and a PERKESO payment stands for SOCSO, EIS and SKBBK (collected together)",
      covered == {("epf", M), ("socso", M), ("eis", M), ("skbbk", M)}, covered)
j("delete", f"/api/payments/{clean}", json={})

# ---------- paid short: the rule 14 row ----------
con = db.connect()
con.arm("import", "test: KWSP paid short")
jb2 = ledger.new_batch(con, EXS, origin="sql", report="journal", sql_import_id=imp, file_name="jot2.xlsx", period_from="2026-11-01",
                       period_to="2026-11-30", period_source="printed", sections=[{"label": "Cash Book", "book": "bank"}])
ledger.put_document(con, EXS, jb2, {"doc_no": "PV2611-010", "doc_date": "2026-11-10", "book": "bank", "lines": [
    {"code": "420-1001", "dr_sen": S(1000), "cr_sen": 0, "description": "made up"}, {"code": "310-1000", "dr_sen": 0, "cr_sen": S(1000), "description": "made up"}]})
ledger.finish_batch(con, jb2)
con.commit()
con.disarm()
con.close()
j("patch", f"/api/payments/{kwsp}", json={"paid_date": "2026-11-10", "amount": 1000})
rs = rows(LATE)
r14 = [r for r in rs if r["rule"] == 14]
check("paid short: no payment row, and the statutory check's row shows what is still owed",
      len(r14) == 1 and "RM 500.00 less was paid" in r14[0]["text"] and r14[0]["amount"] == 500
      and not [r for r in rs if r["text"].startswith("Pay KWSP")], [r["text"] for r in rs])

# ---------- a month filed: its unpaid payment points at nothing, so the check's row shows ----------
j("patch", f"/api/payments/{kwsp}", json={"paid_date": None, "amount": 1500})
check("unpaid again: the payment row is back, the check's row gone", [r["rule"] for r in about_kwsp(rows(LATE))] == [4])
j("post", "/api/months/close", json={"entity_id": EXS, "month": M, "closed": True})
rs = rows(LATE)
check("in a month filed the payment has no row, so the check's row shows",
      [r["rule"] for r in about_kwsp(rs)] == [14], [r["text"] for r in rs])

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "next_one_row_test" in readme)

shutil.rmtree(tmp, ignore_errors=True)
print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
