"""The statutory payables check (update 29 and hrp/statutory.py), on made-up records only.

A made-up company's salary vouchers credit the EPF, SOCSO, EIS, SKBBK and PCB payables each month; the next month a
voucher to each authority debits the payables with those amounts and the employer's share to its own expense account.
The check confirms which accounts are which (suggested from the chart by their names), then works out for each month
what was withheld, what was paid for it and by when, and says which months are cleared, due, late, short or over.
Every company, account, document and amount here is invented.

Run: .venv\\Scripts\\python -m synthetic_tests.statutory_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-statutory-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db, ledger, nextup, statutory  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXS", "name": "Example Statutory Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-555"}]},
    {"code": "EXO", "name": "Example Other Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-666"}]},
]}), encoding="utf-8")

TODAY = date(2026, 11, 14)


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
    """Changes made as a person would, on a connection of its own."""
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


# ---------- 1. update 29 on records at update 28 ----------

full = db.MIGRATIONS[:]
check("update 29 is the statutory accounts (later updates may follow)", len(full) >= 29)
db.MIGRATIONS[:] = full[:28]
db.init()
check("the records are at update 28 while they are built", q("PRAGMA user_version")[0]["user_version"] == 28)
check("below update 29 there is no statutory accounts table", not q("SELECT 1 FROM sqlite_master WHERE name = 'statutory_accounts'"))
EID, EXO = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXS", "EXO"))
CHART = [("150-0000", "RETAINED EARNING", "equity"), ("310-1000", "BANK-EXAMPLE 0001", "asset"),
         ("420-1001", "EPF - PAYABLE", "liability"), ("420-1002", "SOCSO - PAYABLE", "liability"),
         ("420-1003", "SIP - PAYABLE", "liability"), ("420-1004", "PCB PAYABLE", "liability"),
         ("420-1005", "SKBBK PAYABLE (LINDUNG 24 JAM)", "liability"), ("900-E001", "EPF - EMPLOYER", "expense"),
         ("900-S001", "SOCSO - EMPLOYER", "expense"), ("900-S002", "SOCSO SIP - EMPLOYER", "expense"),
         ("900-E002", "ELECTRICITY", "expense"), ("9S0-T002", "SALARY - EXAMPLE", "expense"), ("420-2000", "ACCRUED AUDIT FEE", "liability")]
write("the chart of accounts and the first month tracked",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type) VALUES (?, ?, ?, ?)", (e, *a)) for e in (EID, EXO) for a in CHART],
      ("UPDATE gl_accounts SET sql_type = 'RE' WHERE code = '150-0000'", ()),
      ("UPDATE entities SET first_month = '2026-02', fy_start = 1 WHERE id = ?", (EID,)))
db.MIGRATIONS[:] = full
trail = db.init()
check("update 29 runs, with the updates after it", q("PRAGMA user_version")[0]["user_version"] == len(full))
check("the statutory accounts table is made empty", q("SELECT COUNT(*) AS n FROM statutory_accounts")[0]["n"] == 0)
check("it has its audit triggers", q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit_statutory_accounts%'")[0]["n"] >= 3)
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out after update 29", v["ok"], v)
check("start-up repaired nothing", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)

c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def footprint():
    return (q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"], q("SELECT COUNT(*) AS n FROM audit_tx")[0]["n"],
            q("SELECT COUNT(*) AS n FROM activity")[0]["n"])


# ---------- 2. the mapping, suggested from the chart and confirmed ----------

before = footprint()
d = j("get", f"/api/statutory?entity={EID}&from=2026-01&to=2026-11")
check("nothing is checked before the accounts are confirmed", d["configured"] is False and d["accounts"] == [] and d["problems"] == [], d)
sug = {(x["kind"], x["payable_code"]): x["employer_code"] for x in d["suggestion"]}
check("the chart suggests each kind by its name: SIP is EIS, SKBBK its own kind, the employer's share by EMPLOYER",
      sug == {("epf", "420-1001"): "900-E001", ("socso", "420-1002"): "900-S001", ("eis", "420-1003"): "900-S002",
              ("pcb", "420-1004"): None, ("skbbk", "420-1005"): None}, sug)
check("an accrual of something else isn't suggested", "420-2000" not in {k[1] for k in sug})
check("the name words give the kinds", [statutory.kind_of_name(n) for n in ("KWSP CARUMAN", "PERKESO", "EIS PAYABLE", "MTD PAYABLE", "HRD CORP LEVY", "RECEIPTS")]
      == ["epf", "socso", "eis", "pcb", "hrdf", None])
j("get", f"/api/statutory?entity={EID}")
j("get", f"/api/setup/statutory_accounts?entity={EID}")
check("looking at the check and the Setup list writes nothing", footprint() == before, (before, footprint()))
j("get", f"/api/statutory?entity={EID}&from=2026-13", expect=400)

r = j("post", "/api/statutory/use-suggested", json={"entity_id": EID})
check("Use these accounts adds the five suggested", r["added"] == 5, r)
rows = q("SELECT * FROM statutory_accounts WHERE entity_id = ? ORDER BY sort", (EID,))
check("each with the kind, accounts and the 15th as due day",
      {(x["kind"], x["payable_code"], x["employer_code"], x["due_day"]) for x in rows}
      == {("epf", "420-1001", "900-E001", 15), ("socso", "420-1002", "900-S001", 15), ("eis", "420-1003", "900-S002", 15),
          ("pcb", "420-1004", None, 15), ("skbbk", "420-1005", None, 15)}, rows)
check("they are recorded in the audit trail as added", {x["op"] for x in q("SELECT op FROM audit_row WHERE tbl = 'statutory_accounts'")} == {"insert"})
hist = j("get", f"/api/audit/record/statutory_accounts/{rows[0]['id']}")
check("each has its history, as other Setup records", len(hist["changes"]) >= 1, hist)
j("post", "/api/statutory/use-suggested", json={"entity_id": EID}, expect=400)
listed = j("get", f"/api/setup/statutory_accounts?entity={EID}")["rows"]
check("Setup lists them for the company", len(listed) == 5)
bad = j("post", "/api/setup/statutory_accounts", json={"entity_id": EID, "fields": {"kind": "hrdf", "label": "HRDF", "payable_code": "999-9999"}}, expect=400)
check("an account the books don't know is refused in words", "no account 999-9999" in bad["error"], bad)
dup = j("post", "/api/setup/statutory_accounts", json={"entity_id": EID, "fields": {"kind": "epf", "label": "EPF again", "payable_code": "420-1001"}}, expect=400)
check("the same kind and payable twice is refused", "already" in dup["error"], dup)
pcb_id = next(x["id"] for x in rows if x["kind"] == "pcb")
j("patch", f"/api/setup/statutory_accounts/{pcb_id}", json={"fields": {"due_day": 15, "label": "PCB (LHDN)"}})
eis_id = next(x["id"] for x in rows if x["kind"] == "eis")
j("delete", f"/api/setup/statutory_accounts/{eis_id}", json={"reason": "test: deleted by mistake"})
gone = j("get", f"/api/setup/restore?kind=statutory_accounts&entity={EID}")["rows"]
check("a deleted statutory account is listed under Show deleted", len(gone) == 1 and not gone[0].get("problem"), gone)
j("post", f"/api/setup/restore/{gone[0]['row_id']}", json={"reason": "test: put it back"})
check("and can be put back as it was", q("SELECT kind, payable_code, employer_code FROM statutory_accounts WHERE id = ?", (eis_id,))
      == [{"kind": "eis", "payable_code": "420-1003", "employer_code": "900-S002"}])
used = j("get", f"/api/setup/entities/{EID}")["used_by"]
check("the company counts its statutory accounts among what uses it", any("statutory account" in w for w, _ in used), used)

# ---------- 3. the books: an opening, a year of salary vouchers and the authorities' vouchers ----------

con = db.connect()
con.arm("import", "test: SQL documents")
con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'made-up.xlsx', ?, 0, 0)", (EID, db.now()))
IMP = con.execute("SELECT MAX(id) FROM sql_imports").fetchone()[0]
tb = ledger.new_batch(con, EID, report="trial_balance", sql_import_id=IMP, period_from="2026-01-01", period_to="2026-01-31")
# Owed at 1 January: December 2025's EPF (1,000.00), nothing else statutory.
ledger.put_openings(con, EID, tb, "2026-01-01", "sql_tb", [{"code": "310-1000", "name": "BANK-EXAMPLE 0001", "dr_sen": S(50000), "cr_sen": 0},
                                                           {"code": "420-1001", "name": "EPF - PAYABLE", "dr_sen": 0, "cr_sen": S(1000)},
                                                           {"code": "150-0000", "name": "RETAINED EARNING", "dr_sen": 0, "cr_sen": S(49000)}], True)
jb = ledger.new_batch(con, EID, report="journal", sql_import_id=IMP, period_from="2026-01-01", period_to="2026-11-30")


def L(code, dr=0, cr=0):
    return {"code": code, "dr_sen": S(dr), "cr_sen": S(cr), "description": "made up"}


def doc(no, day, *lines):
    lines = list(lines)
    bal = sum(x["dr_sen"] - x["cr_sen"] for x in lines)
    if bal:
        lines.append({"code": "310-1000", "dr_sen": max(-bal, 0), "cr_sen": max(bal, 0), "description": "made up"})
    ledger.put_document(con, EID, jb, {"doc_no": no, "doc_date": day, "book": "bank", "lines": lines})


EPF, EPF_E, SOC, SOC_E, SIP, SIP_E, PCB, SKB = 770.00, 840.00, 29.75, 103.55, 10.00, 10.00, 165.50, 5.00
months = [f"2026-{m:02d}" for m in range(1, 11)]  # salaries January to October
for m in months:
    nxt = db.shift_month(m, 1)
    tag = m[2:4] + m[5:7]
    doc(f"PV{tag}-032", f"{m}-25", L("9S0-T002", dr=7000), L("420-1001", cr=EPF), L("420-1002", cr=SOC), L("420-1003", cr=SIP),
        L("420-1004", cr=PCB), L("420-1005", cr=SKB))
    ntag = nxt[2:4] + nxt[5:7]
    doc(f"PV{ntag}-010", f"{nxt}-10", L("420-1001", dr=EPF), L("900-E001", dr=EPF_E))  # KWSP: the month's EPF and the employer's share
    perkeso = [L("420-1002", dr=20.00 if m == "2026-06" else SOC), L("900-S001", dr=SOC_E), L("420-1003", dr=SIP), L("900-S002", dr=SIP_E)]
    if m != "2026-01":  # January's SKBBK is never paid (a month before tracking)
        perkeso.append(L("420-1005", dr=SKB))
    doc(f"PV{ntag}-012", f"{nxt}-12", *perkeso)
    if m not in ("2026-07", "2026-08", "2026-09", "2026-10"):
        doc(f"PV{ntag}-014", f"{nxt}-14", L("420-1004", dr=PCB))
# The opening's December EPF, paid in January with its employer's share.
doc("PV2601-010", "2026-01-10", L("420-1001", dr=1000), L("900-E001", dr=1100))
# PCB for July and August paid in one voucher in September; September's never paid; October's not due yet.
doc("PV2609-014", "2026-09-14", L("420-1004", dr=2 * PCB))
ledger.finish_batch(con, jb)
# The tracker: June's PERKESO voucher linked to a payment of its amount, March's KWSP voucher to one of a wrong amount.
for no, amount in (("PV2607-012", 20.00 + SOC_E + SIP + SIP_E + SKB), ("PV2604-010", 1600.00)):
    pid = con.execute("""INSERT INTO payments (entity_id, month, category, description, amount, due_date, paid_date, created_at)
                         VALUES (?, ?, 'statutory', ?, ?, ?, ?, ?)""", (EID, f"2026-{no[4:6]}", f"Made-up statutory {no}", amount,
                                                                         f"2026-{no[4:6]}-15", f"2026-{no[4:6]}-{no[-2:]}", db.now())).lastrowid
    con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, amount, payment_id, status, kind)
                   VALUES (?, ?, ?, ?, ?, ?, 'linked', 'payment')""", (IMP, EID, no, f"2026-{no[4:6]}-{no[-2:]}", amount, pid))
con.commit()
con.disarm()
con.close()

with db.connect() as r:
    R = statutory.report(r, EID, "2026-01", "2026-11", TODAY)
by = {a["kind"]: {x["month"]: x for x in a["months"]} for a in R["accounts"]}
acct = {a["kind"]: a for a in R["accounts"]}
check("the check runs once the accounts are confirmed", R["configured"] and set(by) == {"epf", "socso", "eis", "pcb", "skbbk"}, R["summary"])

# a clean year
epf = by["epf"]
check("EPF: every month from January to October withheld and cleared by the 15th",
      all(epf[m]["status"] == "cleared" and not epf[m]["paid_late"] and epf[m]["withheld_sen"] == S(EPF) and epf[m]["paid_sen"] == S(EPF)
          for m in months), {m: epf[m]["status"] for m in months})
check("November has nothing withheld yet", epf["2026-11"]["status"] == "nothing", epf["2026-11"])
check("the balance at each due day is nil, from the books", all(epf[m]["balance_due_sen"] == 0 for m in months[:-1]),
      [epf[m]["balance_due_sen"] for m in months])
check("October's balance at the due day isn't known yet (it is tomorrow)", epf["2026-10"]["balance_due_sen"] is None)
check("the balance at the end of a month is that month's withholding, owed", epf["2026-05"]["balance_end_sen"] == -S(EPF), epf["2026-05"])
check("the withholding is listed by document", [x["doc_no"] for x in epf["2026-03"]["credits"]] == ["PV2603-032"])
# employer share
check("the employer's share comes from the payment document", epf["2026-03"]["employer_sen"] == S(EPF_E)
      and epf["2026-03"]["payments"][0]["doc_no"] == "PV2604-010", epf["2026-03"])
check("SOCSO's employer share too, from the voucher to PERKESO", by["socso"]["2026-03"]["employer_sen"] == S(SOC_E))
check("EIS takes the SIP accounts", by["eis"]["2026-03"]["employer_sen"] == S(SIP_E) and by["eis"]["2026-03"]["status"] == "cleared")
# opening balance carried
bf = acct["epf"]["brought_forward"]
check("the opening balance is carried in and paid off in January", acct["epf"]["opening_sen"] == -S(1000) and bf["owed_sen"] == S(1000)
      and bf["paid_sen"] == S(1000) and bf["still_owed_sen"] == 0, bf)
check("so January's own EPF is cleared by February's voucher, not taken by December's",
      epf["2026-01"]["payments"][0]["doc_no"] == "PV2602-010", epf["2026-01"])
# a payment voucher paying two months at once
pcb = by["pcb"]
check("PCB for July and August paid in one voucher: both cleared, July late",
      pcb["2026-07"]["status"] == "cleared" and pcb["2026-07"]["paid_late"] and pcb["2026-08"]["status"] == "cleared"
      and not pcb["2026-08"]["paid_late"] and pcb["2026-07"]["payments"][0]["doc_no"] == pcb["2026-08"]["payments"][0]["doc_no"] == "PV2609-014",
      (pcb["2026-07"], pcb["2026-08"]))
# a late month
check("PCB for September is late: nothing paid by 15 October", pcb["2026-09"]["status"] == "late" and pcb["2026-09"]["paid_sen"] == 0
      and pcb["2026-09"]["balance_due_sen"] == -S(PCB), pcb["2026-09"])
check("PCB for October is due, not late", pcb["2026-10"]["status"] == "due", pcb["2026-10"])
# a short payment
soc = by["socso"]
check("SOCSO for June is short by the difference", soc["2026-06"]["status"] == "short" and soc["2026-06"]["difference_sen"] == S(20.00) - S(SOC)
      and "9.75 less" in soc["2026-06"]["text"], soc["2026-06"])
check("the months after it are cleared on their own", soc["2026-07"]["status"] == "cleared", soc["2026-07"])
# before tracking
skb = by["skbbk"]
check("SKBBK for January, never paid, is before tracking: shown, not a problem",
      skb["2026-01"]["status"] == "late" and skb["2026-01"]["before_tracking"]
      and not any(p["kind"] == "skbbk" for p in R["problems"]), skb["2026-01"])
check("February's SKBBK is paid by its own voucher", skb["2026-02"]["status"] == "cleared", skb["2026-02"])
# tracker payment link and amount
p6 = soc["2026-06"]["payments"][0]
check("the tracker payment linked to the voucher, its amount and paid date, agreeing with what the voucher pays",
      p6["tracker"] and p6["tracker"]["amount_sen"] == p6["doc_statutory_sen"] and p6["tracker"]["matches"]
      and p6["tracker"]["paid_date"] == "2026-07-12", p6)
p3 = epf["2026-03"]["payments"][0]
check("a tracker payment of another amount is shown as differing", p3["tracker"] and not p3["tracker"]["matches"]
      and p3["tracker"]["expected_sen"] == S(EPF + EPF_E), p3)
check("a voucher not linked shows none", epf["2026-05"]["payments"][0]["tracker"] is None)
probs = {(p["kind"], p["month"], p["status"]) for p in R["problems"]}
check("the problems are the tracked ones", probs == {("pcb", "2026-09", "late"), ("socso", "2026-06", "short")}, probs)
check("the summary names them", R["summary"].startswith("2 statutory payables to look at"), R["summary"])

# a stopped account is left out
write("stop SKBBK", ("UPDATE statutory_accounts SET active = 0 WHERE kind = 'skbbk' AND entity_id = ?", (EID,)))
with db.connect() as r:
    R2 = statutory.report(r, EID, "2026-02", "2026-05", TODAY)
check("a stopped account is left out of the check", "skbbk" not in {a["kind"] for a in R2["accounts"]})
check("with no problem in the months asked, the summary says cleared up to the last of them",
      R2["summary"] == "All statutory payables cleared up to May 2026.", R2["summary"])

# ---------- 4. Next up ----------

with db.connect() as r:
    rows14 = [x for x in nextup.items(r, TODAY, EID) if x["rule"] == 14]
check("Next up has one row per account and month late or short in a tracked month",
      sorted((x["month"], x["key"].split(":")[-2]) for x in rows14) == [("2026-06", "socso"), ("2026-09", "pcb")], rows14)
late = next(x for x in rows14 if x["month"] == "2026-09")
check("each goes to the Statutory tab, overdue, with what is owed", late["go"]["view"] == "books" and late["go"]["tab"] == "statutory"
      and late["state"] == "overdue" and late["amount"] == PCB and late["due"] == "2026-10-15", late)
check("and opens the tab on its own month to today, whatever period the tab showed last",
      late["go"]["from"] == "2026-09-01" and late["go"]["to"] == TODAY.isoformat(), late["go"])
with db.connect() as r:
    other = [x for x in nextup.items(r, TODAY, EXO) if x["rule"] == 14]
check("a company with no statutory accounts confirmed has none", other == [])

# ---------- 5. the routes write nothing ----------

before = footprint()
d = j("get", f"/api/statutory?entity={EID}&from=2026-01&to=2026-11")
check("the route gives the same check", d["configured"] and len(d["accounts"]) == 4)
j("get", f"/api/statutory?entity={EID}&from=2026-01-01&to=2026-11-30")
j("get", f"/api/statutory?entity={EXO}")
check("the statutory route writes nothing", footprint() == before, (before, footprint()))

# ---------- 6. a Next up row early in a financial year ----------

write("the financial year starts in November", ("UPDATE entities SET fy_start = 11 WHERE id = ?", (EID,)))
d = j("get", f"/api/statutory?entity={EID}")
check("the tab's own default (this financial year to date) starts after September's late PCB",
      d["from"] == "2026-11" and not any(p["month"] == "2026-09" for p in d["problems"]), (d["from"], d["problems"]))
with db.connect() as r:
    late = next(x for x in nextup.items(r, TODAY, EID) if x["rule"] == 14 and x["month"] == "2026-09")
d = j("get", f"/api/statutory?entity={EID}&from={late['go']['from']}&to={late['go']['to']}")
check("the period the Next up row opens lists the month it names", ("pcb", "2026-09", "late") in
      {(p["kind"], p["month"], p["status"]) for p in d["problems"]}, d["problems"])
write("the financial year back to January", ("UPDATE entities SET fy_start = 1 WHERE id = ?", (EID,)))

# ---------- 7. payments in the salary's own month, corrections and a refund (the other company) ----------

j("post", "/api/setup/statutory_accounts", json={"entity_id": EXO, "fields": {"kind": "epf", "label": "EPF", "payable_code": "420-1001",
                                                                             "employer_code": "900-E001"}})
d = j("get", f"/api/statutory?entity={EXO}&from=2026-01&to=2026-06")
check("accounts confirmed but no documents: not called cleared, as nothing was checked",
      d["configured"] and d["empty"] and not d["problems"] and d["summary"].startswith("No statutory payables were taken off or paid")
      and "cleared" not in d["summary"], d["summary"])

con = db.connect()
con.arm("import", "test: SQL documents of the other company")
con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'made-up-2.xlsx', ?, 0, 0)", (EXO, db.now()))
IMP2 = con.execute("SELECT MAX(id) FROM sql_imports").fetchone()[0]
jb2 = ledger.new_batch(con, EXO, report="journal", sql_import_id=IMP2, period_from="2026-01-01", period_to="2026-11-30")


def doc2(no, day, *lines):
    lines = list(lines)
    bal = sum(x["dr_sen"] - x["cr_sen"] for x in lines)
    if bal:
        lines.append({"code": "310-1000", "dr_sen": max(-bal, 0), "cr_sen": max(bal, 0), "description": "made up"})
    ledger.put_document(con, EXO, jb2, {"doc_no": no, "doc_date": day, "book": "bank", "lines": lines})


for m in ("01", "02", "03", "04", "05", "06"):
    doc2(f"PV-S{m}", f"2026-{m}-25", L("9S0-T002", dr=7000), L("420-1001", cr=1000))
doc2("PV-P01", "2026-01-30", L("420-1001", dr=1000), L("900-E001", dr=1100))   # January paid in January, after the salary
doc2("JV-C02", "2026-02-27", L("420-1001", dr=100), L("9S0-T002", cr=100))     # 100.00 taken off February's in error
doc2("PV-P02", "2026-03-10", L("420-1001", dr=900), L("900-E001", dr=1100))    # February's corrected 900.00
doc2("JV-C03", "2026-04-05", L("9S0-T002", dr=50), L("420-1001", cr=50))       # 50.00 more for March, journalled in April
doc2("PV-P03", "2026-04-10", L("420-1001", dr=1050), L("900-E001", dr=1100))   # March's 1,050.00
doc2("PV-P04", "2026-05-10", L("420-1001", dr=1200), L("900-E001", dr=1100))   # April's, 200.00 too much
doc2("OR-R04", "2026-05-20", L("420-1001", cr=200))                            # KWSP refunds the 200.00 to the bank
doc2("PV-P05", "2026-06-10", L("420-1001", dr=1000), L("900-E001", dr=1100))
doc2("PV-P06", "2026-07-10", L("420-1001", dr=1000), L("900-E001", dr=1100))
ledger.finish_batch(con, jb2)
con.commit()
con.disarm()
con.close()

with db.connect() as r:
    R3 = statutory.report(r, EXO, "2026-01", "2026-06", TODAY)
x3 = {x["month"]: x for x in R3["accounts"][0]["months"]}
check("a payment dated in the salary's own month pays that month, not the month before",
      x3["2026-01"]["status"] == "cleared" and [p["doc_no"] for p in x3["2026-01"]["payments"]] == ["PV-P01"]
      and R3["accounts"][0]["brought_forward"]["paid_sen"] == 0, (x3["2026-01"], R3["accounts"][0]["brought_forward"]))
check("a correction journal against the salary lowers that month's withholding, not paying the month before",
      x3["2026-02"]["status"] == "cleared" and x3["2026-02"]["withheld_sen"] == S(900) and x3["2026-02"]["paid_sen"] == S(900)
      and any(c["doc_no"] == "JV-C02" and c.get("correction") for c in x3["2026-02"]["credits"])
      and x3["2026-01"]["paid_sen"] == S(1000), (x3["2026-01"], x3["2026-02"]))
check("a top-up journalled the month after belongs to the month it tops up",
      x3["2026-03"]["status"] == "cleared" and x3["2026-03"]["withheld_sen"] == S(1050)
      and x3["2026-04"]["withheld_sen"] == S(1000), (x3["2026-03"], x3["2026-04"]))
check("a refund to the bank is taken back from the month overpaid, not counted as the next month's withholding",
      x3["2026-04"]["status"] == "cleared" and x3["2026-04"]["paid_sen"] == S(1000)
      and [(p["doc_no"], p["amount_sen"]) for p in x3["2026-04"]["payments"]] == [("PV-P04", S(1200)), ("OR-R04", -S(200))]
      and x3["2026-05"]["withheld_sen"] == S(1000) and x3["2026-05"]["status"] == "cleared", (x3["2026-04"], x3["2026-05"]))
check("so the other company has nothing to look at", R3["problems"] == [] and x3["2026-06"]["status"] == "cleared"
      and R3["summary"] == "All statutory payables cleared up to June 2026." and not R3["empty"], (R3["problems"], R3["summary"]))

# A salary for August paid late, on 3 September, names its payroll month; KWSP is paid for August with it included, as
# on real books (a September salary paid on 16 October): August takes its withholding, not September.
con = db.connect()
con.arm("import", "test: a late salary")
jb3 = ledger.new_batch(con, EXO, report="journal", sql_import_id=IMP2, period_from="2026-07-01", period_to="2026-09-30")
for no, day, lines in (
        ("PV-S07", "2026-07-25", [{**L("9S0-T002", dr=7000), "description": "A PERSON - SALARY - JUL 26"}, L("420-1001", cr=1000)]),
        ("PV-S08", "2026-08-25", [{**L("9S0-T002", dr=7000), "description": "A PERSON - SALARY - AUG 26"}, L("420-1001", cr=1000)]),
        ("PV-S08L", "2026-09-03", [{**L("9S0-T003", dr=1500), "description": "ANOTHER PERSON - SALARY - AUG 26 (01/08/26 - 15/08/26)"},
                                   L("420-1001", cr=165)]),
        ("PV-P07", "2026-08-10", [L("420-1001", dr=1000), L("900-E001", dr=1100)]),
        ("PV-P08", "2026-09-10", [L("420-1001", dr=1165), L("900-E001", dr=1300)])):
    bal = sum(x["dr_sen"] - x["cr_sen"] for x in lines)
    lines.append({"code": "310-1000", "dr_sen": max(-bal, 0), "cr_sen": max(bal, 0), "description": "made up"})
    ledger.put_document(con, EXO, jb3, {"doc_no": no, "doc_date": day, "book": "bank", "lines": lines})
ledger.finish_batch(con, jb3)
con.commit()
con.disarm()
con.close()
with db.connect() as r:
    R4 = statutory.report(r, EXO, "2026-07", "2026-09", TODAY)
x4 = {x["month"]: x for x in R4["accounts"][0]["months"]}
check("a salary paid late is withheld in the payroll month its description names, so both months clear",
      x4["2026-08"]["status"] == "cleared" and x4["2026-08"]["withheld_sen"] == S(1165) and x4["2026-08"]["paid_sen"] == S(1165)
      and x4["2026-09"]["withheld_sen"] == 0 and x4["2026-09"]["status"] == "nothing"
      and [(c["doc_no"], c.get("for_month")) for c in x4["2026-08"]["credits"]] == [("PV-S08", None), ("PV-S08L", "2026-08")],
      (x4["2026-08"], x4["2026-09"]))
check("a payment putting its employer's share on its own kind's account is not reported", R4["postings"] == [], R4["postings"])

# An EPF payment that puts its employer's share on the EIS employer account, as a real SOCSO payment did.
j("post", "/api/setup/statutory_accounts", json={"entity_id": EXO, "fields": {"kind": "eis", "label": "EIS", "payable_code": "420-1003",
                                                                             "employer_code": "900-S002"}})
con = db.connect()
con.arm("import", "test: a misposted employer's share")
jb4 = ledger.new_batch(con, EXO, report="journal", sql_import_id=IMP2, period_from="2026-10-01", period_to="2026-10-31")
ledger.put_document(con, EXO, jb4, {"doc_no": "PV-X10", "doc_date": "2026-10-12", "book": "bank", "lines": [
    L("420-1001", dr=1000), L("900-S002", dr=1100), {"code": "310-1000", "dr_sen": 0, "cr_sen": S(2100), "description": "made up"}]})
ledger.finish_batch(con, jb4)
con.commit()
con.disarm()
con.close()
with db.connect() as r:
    R5 = statutory.report(r, EXO, "2026-09", "2026-09", TODAY)
p5 = R5["postings"]
check("an employer's share put on another kind's employer account is named, with the account it belongs on",
      [(p["doc_no"], p["month"], p["amount_sen"], p["code"], p["expected"]) for p in p5] == [("PV-X10", "2026-09", S(1100), "900-S002", ["900-E001"])]
      and "pays EPF, but puts RM 1,100.00 of employer's share on 900-S002" in p5[0]["text"]
      and "EPF's employer share account is 900-E001" in p5[0]["text"], p5)
d5 = j("get", f"/api/statutory?entity={EXO}&from=2026-09&to=2026-09")
check("the page is given it", [p["doc_no"] for p in d5["postings"]] == ["PV-X10"]
      and "Employer's share on another account" in (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8"), d5.get("postings"))

# ---------- 8. every account stopped ----------

write("stop every statutory account", ("UPDATE statutory_accounts SET active = 0 WHERE entity_id = ?", (EID,)))
d = j("get", f"/api/statutory?entity={EID}")
check("with every account stopped the check says so, not that the chart has none",
      not d["configured"] and d["stopped"] and d["suggestion"] == [] and "stopped" in d["summary"], d)
d = j("get", f"/api/statutory?entity={EXO}")
check("a company with an account in use isn't called stopped", d["configured"] and not d["stopped"], d["summary"])
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out at the end", v["ok"], v)

print(f"All statutory checks passed. Records folder used: {tmp}")
