"""Setup phase 6 on made-up records only: customers and suppliers, each company's chart of accounts, pasting a list of
either, the link from a recurring payment to a supplier or customer, and SQL entries' codes (update 22).

Run: .venv\\Scripts\\python -m synthetic_tests.parties_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-parties-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, partybook  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}],
     "payees": [{"name": "Staff One", "category": "salary", "amount": 3000, "due_day": 26},
                {"name": "Office Landlord", "category": "rental", "amount": 2000, "due_day": 5},
                {"name": "Paper Supplies", "category": "utility", "amount": 300, "due_day": 10, "varies": True}]},
    {"code": "AI", "name": "Example International Ltd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


# ---------- 1. update 22 ----------
full = db.MIGRATIONS[:]
db.MIGRATIONS[:] = full[:21]
db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


check("below update 22 there are no customers or suppliers", j("get", "/api/meta")["parties"] == [])
pay = j("get", "/api/payees?entity=1")
landlord = next(p for p in (pay if isinstance(pay, list) else pay.get("payees", pay.get("rows", []))) if p["name"] == "Office Landlord")
j("post", "/api/payees", json={**{k: landlord[k] for k in ("id", "name", "category", "amount", "due_day")}, "party_id": None})
check("and a recurring payment saved with no link still saves", True)

# Records that ran update 22 before it allowed all of SQL Account's special account types: the table as it was then,
# with accounts saved in it, is made again by update 23 with the same rows and ids, and the trail still checks out.
db.MIGRATIONS[:] = full[:22]
db.init()
from hrp import audit  # noqa: E402
with db.connect() as r:
    r.arm("migration", "Update 22")  # as update 22 made the table before this version
    r.execute("DROP TABLE gl_accounts")  # its capture triggers go with it; the refresh below puts them on the old one
    r.execute("""CREATE TABLE gl_accounts (
      id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), code TEXT NOT NULL, name TEXT NOT NULL,
      type TEXT CHECK (type IS NULL OR type IN ('asset', 'liability', 'equity', 'income', 'expense')),
      special TEXT CHECK (special IS NULL OR special IN ('bank', 'debtor_control', 'creditor_control')),
      parent_code TEXT, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT,
      UNIQUE (entity_id, code))""")
    audit.refresh(r)
j("post", "/api/setup/gl_accounts", json={"entity_id": 1, "fields": {"code": "900-OLD1", "name": "Old bank", "type": "asset", "special": "bank"}})
j("post", "/api/setup/gl_accounts", json={"entity_id": 1, "fields": {"code": "900-OLD2", "name": "Old sub", "parent_code": "900-OLD1"}})
with db.connect() as r:
    before = [tuple(x) for x in r.execute("SELECT * FROM gl_accounts ORDER BY id")]
    try:
        r.execute("INSERT INTO gl_accounts (entity_id, code, name, special) VALUES (1, 'X', 'X', 'cash')")
        narrow = False
    except sqlite3.IntegrityError:
        narrow = True
check("records made before update 23 only allow three special types", narrow and len(before) == 2)
db.MIGRATIONS[:] = full
trail = db.init()
with db.connect() as r:
    after = [tuple(x) for x in r.execute("SELECT * FROM gl_accounts ORDER BY id")]
    table_sql = r.execute("SELECT sql FROM sqlite_master WHERE name = 'gl_accounts'").fetchone()[0]
    v = audit.verify(r)
check("update 23 makes the chart again with every row and id as it was (update 24's SQL group left empty)",
      [a[:10] for a in after] == before and all(a[10] is None for a in after) and "'deposit'" in table_sql, (before, after))
check("and the trail still checks out, with nothing written outside the app", v["ok"] and not v["outside"], v)
check("and start-up finds no capture trigger missing", trail and trail["triggers_repaired"] == [], trail)
j("post", "/api/setup/gl_accounts", json={"entity_id": 1, "fields": {"code": "900-OLD3", "name": "Petty cash", "special": "cash"}})
with db.connect() as r:
    hist = r.execute("SELECT COUNT(*) FROM audit_row WHERE tbl = 'gl_accounts' AND op = 'insert'").fetchone()[0]
    for code in ("900-OLD1", "900-OLD2", "900-OLD3"):
        r.arm("system", "test: tidy the chart")
        r.execute("DELETE FROM gl_accounts WHERE code = ?", (code,))
    r.commit()
check("a cash account saves after it, and changes to the chart are still in the trail", hist == 3, hist)
with db.connect() as cc:
    check("update 22 adds the tables and columns", partybook.ready(cc)
          and db._has_col(cc, "payees", "party_id") and db._has_col(cc, "sql_entries", "code") and db._has_col(cc, "filing_words", "party_id"))

CYC = db.current_cycle()
for e in (1, 2):
    j("post", "/api/months/open", json={"entity_id": e, "month": CYC})

# ---------- 2. customers and suppliers by hand ----------
types = j("get", "/api/setup/types")
check("Setup lists them with the chart of accounts", dict((g[0], g[1]) for g in types["groups"])["People and payments"] == ["payees", "parties"]
      and "gl_accounts" in dict((g[0], g[1]) for g in types["groups"])["Companies and banks"])
acme = j("post", "/api/setup/parties", json={"fields": {"name": "Acme Paper Trading", "kind": "supplier", "entity_id": 1, "sql_code": "400-a001"}})
check("a supplier of one company is added, its code in capitals", acme["record"]["sql_code"] == "400-A001" and acme["record"]["entity_id"] == 1)
j("post", "/api/setup/parties", 400, json={"fields": {"name": "Acme again", "kind": "supplier", "entity_id": 1, "sql_code": "400-A001"}})
check("two the same company sees can't share a code", True)
board = j("post", "/api/setup/parties", json={"fields": {"name": "Example Statutory Board", "kind": "statutory", "entity_id": None}})
rows = j("get", "/api/setup/parties?entity=1")["rows"]
check("a company's list shows its own and every company's", {r["name"] for r in rows} == {"Acme Paper Trading", "Example Statutory Board"})
check("and the other company's list only every company's", [r["name"] for r in j("get", "/api/setup/parties?entity=2")["rows"]] == ["Example Statutory Board"])
j("patch", "/api/setup/entities/2", json={"fields": {"sql_database": "AI_DB"}})
e = j("patch", f"/api/setup/parties/{board['id']}", 400, json={"fields": {"sql_code": "STAT-01"}})["error"]
check("an every-company one can't take a code while the companies keep separate SQL databases", "own codes" in e, e)
cust = j("post", "/api/setup/parties", json={"fields": {"name": "Tenant Bakery", "kind": "customer", "entity_id": 1, "sql_code": "300-T001"}})

# ---------- 3. the chart of accounts ----------
bank = j("post", "/api/setup/gl_accounts", json={"entity_id": 1, "fields": {"code": "310-000", "name": "Cash at bank", "type": "asset", "special": "bank"}})
j("post", "/api/setup/gl_accounts", 400, json={"entity_id": 1, "fields": {"code": "310-000", "name": "Again"}})
check("an account code is once per company", True)
j("post", "/api/setup/gl_accounts", 400, json={"entity_id": 1, "fields": {"code": "310-001", "name": "Sub", "parent_code": "999-999"}})
sub = j("post", "/api/setup/gl_accounts", json={"entity_id": 1, "fields": {"code": "310-001", "name": "Main account", "parent_code": "310-000"}})
check("a parent account must be in the chart", sub["record"]["parent_code"] == "310-000")
j("patch", f"/api/setup/gl_accounts/{bank['id']}", 400, json={"fields": {"parent_code": "310-001"}})
check("an account can't sit under itself", True)
check("an account under another uses it, so its code is locked", "code" in j("get", f"/api/setup/gl_accounts/{bank['id']}")["locked"])
j("post", "/api/setup/gl_accounts", json={"entity_id": 2, "fields": {"code": "310-000", "name": "Cash at bank"}})
check("another company's chart may have the same code", True)

# ---------- 4. pasting a list ----------


def paste(what, text, expect=200, **kw):
    return j("post", f"/api/setup/{what}/paste", expect, json={"entity_id": 1, "text": text, **kw})


tab = "Code\tCompany Name\tTIN\n400-B001\tBeta Stationery\tC1234567890\n400-A001\tAcme Paper Trading Sdn Bhd\t\n400-B001\tDuplicate\t\n"
p = paste("parties", tab, kind="supplier", preview=True)
check("a tab list is read with its headings", p["how"] == "tab" and p["mapping"] == {"sql_code": 0, "name": 1, "tin": 2}, p)
check("the preview says what each row does", [r["action"] for r in p["rows"]] == ["add", "update", "error"]
      and p["rows"][1]["changes"][0][0] == "Name" and "twice" in p["rows"][2]["message"], p["rows"])
check("and saves nothing", len(j("get", "/api/setup/parties?entity=1")["rows"]) == 3)
p = paste("parties", tab, kind="supplier", reason="From SQL Account")
rows = {r["sql_code"]: r for r in j("get", "/api/setup/parties?entity=1")["rows"] if r["sql_code"]}
check("saving adds the new ones and updates by code", rows["400-B001"]["tin"] == "C1234567890"
      and rows["400-A001"]["name"] == "Acme Paper Trading Sdn Bhd" and p["counts"] == {"add": 1, "update": 1, "same": 0, "error": 1}, p["counts"])
paste("parties", "Code\tCompany Name\tTIN\n400-B001\tBeta Stationery\t\n", kind="supplier")
check("an empty cell never clears a field", j("get", f"/api/setup/parties/{rows['400-B001']['id']}")["record"]["tin"] == "C1234567890")
check("rows missing from a paste stay as they were", "300-T001" in {r["sql_code"] for r in j("get", "/api/setup/parties?entity=1")["rows"]})
pipe = "+----------+----------------------+\n| Code     | Description          |\n+----------+----------------------+\n| 500-000  | Salaries             |\n| 510-100  | Office rental        |\n+----------+----------------------+\n"
p = paste("gl_accounts", pipe, preview=True)
check("a bordered | table is read", p["how"] == "pipe" and [r["code"] for r in p["rows"]] == ["500-000", "510-100"], p)
fixed = "Code      Description                 Type\n100-000   Fixed Assets                Asset\n200-000   Trade Creditors Control     Liability\n500-000   Salaries And Wages          Expense\n"
p = paste("gl_accounts", fixed)
check("a fixed-width report is read, its types as words", p["how"] == "fixed" and p["counts"]["add"] == 3, p)
gl = {r["code"]: r for r in j("get", "/api/setup/gl_accounts?entity=1")["rows"]}
check("and the accounts are in the chart", gl["200-000"]["name"] == "Trade Creditors Control" and gl["200-000"]["type"] == "liability")


# A chart printed from SQL Account to a text file (made up, laid out as its report is): a page header and the heading
# row on every page, each page shifted a few places, group headings with SQL's type, sub-accounts printed further in,
# a page break, and totals at the end.
def printed(cells):
    s = ""
    for at, text in cells:
        s = s.ljust(at) + text
    return s


def report_page(shift, n, accounts, ff):
    head = [printed([(148 + shift, "13/11/2026 09:15:02 AM")]), printed([(22 + shift, "Example Holdings Sdn Bhd (123456-X)")]),
            printed([(72 + shift, "Chart Of Account")]), printed([(159 + shift, f"Page {n} of 2")]),
            printed([(2 + shift, "Acc Code"), (24 + shift, "Description"), (109 + shift, "A/C Type"), (119 + shift, "Special Type"),
                     (133 + shift, "Tax Code"), (143 + shift, "SIC")])]
    body = []
    for a in accounts:
        if len(a) == 2:  # a group heading: its name and SQL's type
            body.append(printed([(2 + shift, a[0]), (109 + shift, a[1])]))
        else:
            code, name, typ, special, deep = a
            body.append(printed([(6 + shift + 2 * deep, code), (24 + shift + n, name), (110 + shift + n, typ)]
                                + ([(124 + shift, special)] if special else [])))
    return ("\f" if ff else "") + "\r\n".join(head + body)


page1 = report_page(0, 1, [("NON-CURRENT ASSETS", "FA"), ("910-000", "Plant and machinery", "FA", "", 0),
                           ("910-005", "Acc. Dep.  plant", "FA", "AD", 1), ("CURRENT ASSETS", "CA"),
                           ("930-000", "Trade debtors", "CA", "DC", 0), ("931-000", "Bank accounts", "CA", "BA", 0),
                           ("931-001", "Petty cash", "CA", "CH", 1)], False)
page2 = report_page(3, 2, [("931-002", "Cash in hand", "CA", "CH", 1), ("932-000", "Stock", "CA", "BS", 0),
                           ("PREPAYMENT", "Prepayment paid", "CA", "DP", 0), ("INVESTMENT", "IV"), ("940-001", "Shares", "IV", "", 1),
                           ("CURRENT LIABILITIES", "CL"), ("950-000", "Trade creditors", "CL", "CC", 0),
                           ("OTHER LIABILITIES", "OL"), ("951-000", "Deposits received", "OL", "DP", 0), ("RESERVE", "RV"),
                           ("960-000", "Revaluation reserve", "RV", "", 0), ("APPROPRIATION ACCOUNT", "AP"),
                           ("961-000", "Dividend", "AP", "", 0), ("REVENUE", "SL"), ("970-000", "Sales", "SL", "", 0),
                           ("971-000", "Sales returns", "SA", "", 0), ("972-000", "Gain on disposal", "EO", "", 0),
                           ("COST OF GOODS SOLD", "CO"), ("980-000", "Opening stock", "CO", "OS", 0),
                           ("981-000", "Closing stock", "CO", "CS", 0), ("TAXATION", "TX"), ("990-000", "Income tax", "TX", "", 0)], True)
report = page1 + "\r\n" + page2 + "\r\n" + printed([(102, "Continued")]) + "\r\n" + printed([(108, "Total Accounts : 19")]) + "\r\n\f"
want = ["910-000", "910-005", "930-000", "931-000", "931-001", "931-002", "932-000", "PREPAYMENT", "940-001", "950-000", "951-000",
        "960-000", "961-000", "970-000", "971-000", "972-000", "980-000", "981-000", "990-000"]
p = paste("gl_accounts", report, preview=True)
check("a chart printed from SQL Account is read as a report, page by page", p["how"] == "report" and p["header_row"] == 0
      and p["mapping"] == {"code": 0, "name": 1, "type": 2, "special": 3, "parent_code": 6} and p["read_note"].startswith("2 pages. 20 other lines were left out"), p)
check("its page headers, group headings and totals are left out", [r["code"] for r in p["rows"]] == want, [r["code"] for r in p["rows"]])
check("every row adds, with SQL's type and special codes all known", p["counts"] == {"add": 19, "update": 0, "same": 0, "error": 0}
      and not any(r["message"] for r in p["rows"]), p["rows"])
check("a name with two spaces in it stays one name", p["rows"][1]["name"] == "Acc. Dep. plant", p["rows"][1])
p2 = paste("gl_accounts", report.replace("\f", "").replace("\r\n", "\n"), preview=True)
check("and it reads the same without page breaks or with plain line ends", [(r["code"], r["name"]) for r in p2["rows"]]
      == [(r["code"], r["name"]) for r in p["rows"]] and p2["mapping"] == p["mapping"], p2)
paste("gl_accounts", report, entity_id=2)
gl2 = {r["code"]: r for r in j("get", "/api/setup/gl_accounts?entity=2")["rows"]}
check("a sub-account sits under the account printed above it, across a page break too",
      gl2["910-005"]["parent_code"] == "910-000" and gl2["931-001"]["parent_code"] == "931-000" and gl2["931-002"]["parent_code"] == "931-000", gl2)
check("and a group heading ends what it can sit under", not gl2["940-001"]["parent_code"] and not gl2["930-000"]["parent_code"], gl2["940-001"])
check("SQL's account types become the chart's five", [gl2[c]["type"] for c in ("910-000", "940-001", "951-000", "960-000", "961-000", "971-000", "972-000", "980-000", "990-000")]
      == ["asset", "asset", "liability", "equity", "equity", "income", "income", "expense", "expense"], gl2)
check("and every special type is kept", [gl2[c]["special"] for c in ("910-005", "930-000", "931-000", "931-001", "PREPAYMENT", "932-000", "950-000", "951-000", "980-000", "981-000")]
      == ["accumulated_depreciation", "debtor_control", "bank", "cash", "deposit", "stock", "creditor_control", "deposit", "opening_stock", "closing_stock"], gl2)
check("pasting the same report again changes nothing", paste("gl_accounts", report, entity_id=2, preview=True)["counts"]["same"] == 19)
check("each account keeps SQL's group, from its A/C Type", [gl2[c]["sql_type"] for c in ("910-000", "940-001", "PREPAYMENT", "951-000", "960-000", "961-000", "971-000", "972-000", "990-000")]
      == ["FA", "IV", "CA", "OL", "RV", "AP", "SA", "EO", "TX"], gl2)
words = "Code      Description          Type" + chr(10) + "920-000   Office equipment     Fixed Assets" + chr(10) + "920-100   Rent                 Expenses" + chr(10) + "920-200   Misc                 Sundry" + chr(10)
pw = {r["code"]: r for r in paste("gl_accounts", "Report" + chr(10) + words, entity_id=2)["rows"]}
gw = {r["code"]: r for r in j("get", "/api/setup/gl_accounts?entity=2")["rows"]}
check("a type given in words gives the group too, and a word that isn't one is left out as before",
      (gw["920-000"]["sql_type"], gw["920-000"]["type"], gw["920-100"]["sql_type"], gw["920-200"]["sql_type"], gw["920-200"]["type"]) == ("FA", "asset", "EP", None, None)
      and "not recognised" in (pw["920-200"]["message"] or ""), (gw, pw))
types = j("get", "/api/setup/types")["kinds"]["gl_accounts"]
check("the chart's tree has SQL's groups in its order", [g[0] for g in types["tree"]["groups"]][:4] == ["FA", "IV", "OA", "CA"]
      and types["tree"]["groups"][-1] == ["AP", "Appropriation account", "equity"], types.get("tree"))
g1 = j("post", "/api/setup/gl_accounts", json={"entity_id": 2, "fields": {"code": "955-000", "name": "Accrued fees", "sql_type": "CL"}})
rec = lambda i: j("get", f"/api/setup/gl_accounts/{i}")["record"]
check("by hand, the type follows the SQL group", rec(g1["id"])["type"] == "liability", rec(g1["id"]))
e = j("patch", f"/api/setup/gl_accounts/{g1['id']}", 400, json={"fields": {"type": "asset"}})["error"]
check("and another type is refused while the group says otherwise", "Current liabilities (CL)" in e and rec(g1["id"])["type"] == "liability", e)
j("patch", f"/api/setup/gl_accounts/{g1['id']}", json={"fields": {"sql_type": "CA"}})
check("changing the group changes the type", rec(g1["id"])["type"] == "asset")
j("patch", f"/api/setup/gl_accounts/{g1['id']}", json={"fields": {"sql_type": None, "type": "expense"}})
check("and with no group any type can be chosen", rec(g1["id"])["sql_type"] is None and rec(g1["id"])["type"] == "expense", rec(g1["id"]))
j("patch", f"/api/setup/gl_accounts/{g1['id']}", json={"fields": {"sql_type": "CL"}})
e = j("patch", f"/api/setup/gl_accounts/{g1['id']}", 400, json={"fields": {"type": None}})["error"]
check("emptying the type of an account with a group is refused, not ignored", "Current liabilities (CL)" in e and rec(g1["id"])["type"] == "liability", e)
nl = chr(10)
plain = "Code      Description            Type" + nl + "960-000   Revaluation reserve    Equity" + nl + "980-000   Opening stock          Expenses" + nl
pp = paste("gl_accounts", "Chart" + nl + plain, entity_id=2)
gp = {r["code"]: r for r in j("get", "/api/setup/gl_accounts?entity=2")["rows"]}
check("a type in words keeps an account in the narrower SQL group of that type it is in",
      (gp["960-000"]["sql_type"], gp["980-000"]["sql_type"]) == ("RV", "CO") and pp["counts"]["error"] == 0, (pp, gp["960-000"], gp["980-000"]))
paste("gl_accounts", "Chart" + nl + plain.replace("Equity", "RE    "), entity_id=2)
check("and SQL's own code moves it", rec(gp["960-000"]["id"])["sql_type"] == "RE")
one_page = printed([(2, "Acc Code"), (24, "Description"), (109, "A/C Type")]) + "\n" + printed([(6, "990-100"), (24, "Zakat"), (110, "TX")])
check("a list lined up with spaces and nothing else is still read as columns", paste("gl_accounts", one_page, preview=True)["how"] == "fixed")
split = lambda t: partybook.split_columns(t, "gl_accounts")[1]
check("a page break on a line of its own, or none at all, gives the same rows and parents",
      split(report.replace("\f", "\f\r\n")) == split(report) == split(report.replace("\f", "")), split(report.replace("\f", "")))


def listing_page(n, rows):  # a printed customer listing: figures right-aligned, some starting left of their heading
    return ("\f" if n > 1 else "") + "\r\n".join(
        [printed([(150, f"Page {n} of 2")]), printed([(30, "Example Holdings Sdn Bhd")]),
         printed([(2, "Code"), (16, "Company Name"), (50, "Balance"), (64, "Credit Limit")])]
        + [printed([(2, code), (16, name), (57 - len(bal), bal), (76 - len(lim), lim)]) for code, name, bal, lim in rows])


custs = [(f"300-C{i:03}", f"Customer {i} Sdn Bhd", f"{i * 1234567.5:,.2f}", f"{i * 1000:,.2f}") for i in range(1, 9)]
listing = listing_page(1, custs[:4]) + "\r\n" + listing_page(2, custs[4:]) + "\r\n"
p = paste("parties", listing, kind="customer", preview=True)
check("a printed listing with figures like 12,000.00 on every line is read as a report, not split at the commas",
      p["how"] == "report" and p["mapping"] == {"sql_code": 0, "name": 1} and [r["code"] for r in p["rows"]] == [c[0] for c in custs], p)
check("and a figure right-aligned under a shorter heading isn't taken into the name",
      [r["name"] for r in p["rows"]] == [c[1] for c in custs], [r["name"] for r in p["rows"]])
odd_line = "Code      Name\n100-000   Fixed assets\n200 000   Creditors\n300-000   Sales\n"
p = paste("gl_accounts", odd_line, preview=True)
check("a lined-up list with one odd line is still read as columns, the odd line shown as a problem",
      p["how"] == "fixed" and [r["code"] for r in p["rows"]] == ["100-000", "200 000", "300-000"] and p["rows"][1]["action"] == "error", p)
mid = "\r\n".join([printed([(6, "930-000"), (24, "Trade debtors"), (110, "CA"), (124, "DC")]),
                   printed([(6, "930-001"), (24, "Trade debtors - export"), (110, "CA")])]) + "\r\n" + page2
p = paste("gl_accounts", mid, preview=True)
check("a paste that starts mid-page keeps the accounts above the first heading row, and says so",
      p["how"] == "report" and [r["code"] for r in p["rows"]][:3] == ["930-000", "930-001", "931-002"]
      and "The first 2 rows came before any heading row" in p["read_note"], p["read_note"])
commas = 'Code,Name\n600-000,"Utilities, telco"\n'
p = paste("gl_accounts", commas, preview=True)
check("a comma list keeps a quoted name whole", p["how"] == "comma" and p["rows"][0]["name"] == "Utilities, telco", p)
xml = ('<?xml version="1.0"?><DATAPACKET Version="2.0"><METADATA><FIELDS><FIELD attrname="CODE" fieldtype="string"/>'
       '<FIELD attrname="COMPANYNAME" fieldtype="string"/></FIELDS></METADATA><ROWDATA><ROW CODE="300-C001" COMPANYNAME="Gamma Cafe"/>'
       '<ROW CODE="300-C002" COMPANYNAME="Delta Shop"/></ROWDATA></DATAPACKET>')
p = paste("parties", xml, kind="customer", preview=True)
check("a grid copied from SQL Account is read", p["how"] == "sql" and [r["code"] for r in p["rows"]] == ["300-C001", "300-C002"], p)
p = paste("parties", "300-D001  Epsilon Traders\n300-D002  Zeta Supplies\n", kind="customer", preview=True)
check("a list without headings takes the code-like column as the code", p["header_row"] == -1 and p["rows"][0]["code"] == "300-D001"
      and p["rows"][0]["name"] == "Epsilon Traders", p)
paste("parties", tab, preview=True, kind="nobody", expect=400)
check("a kind not offered is refused", True)

# ---------- 5. a recurring payment linked to a supplier ----------
meta = j("get", "/api/meta")
check("/api/meta gives the customers and suppliers", any(x["sql_code"] == "400-A001" for x in meta["parties"]))
staff = next(p for p in j("get", "/api/payees?entity=1") if p["name"] == "Staff One") if isinstance(j("get", "/api/payees?entity=1"), list) else None
payees = j("get", "/api/payees?entity=1")
payees = payees if isinstance(payees, list) else payees.get("payees", payees.get("rows", []))
by = {p["name"]: p for p in payees}
base = lambda p: {k: p[k] for k in ("id", "name", "category", "amount", "due_day")}
e = j("post", "/api/payees", 400, json={**base(by["Staff One"]), "party_id": acme["id"]})["error"]
check("a salary can't be linked: it is paid to a person", "person" in e, e)
e = j("post", "/api/payees", 400, json={**base(by["Paper Supplies"]), "party_id": cust["id"]})["error"]
check("a customer can't be linked to money out", "customer" in e.lower(), e)
other = j("post", "/api/setup/parties", json={"fields": {"name": "AI Supplier", "kind": "supplier", "entity_id": 2}})
j("post", "/api/payees", 400, json={**base(by["Paper Supplies"]), "party_id": other["id"]})
check("another company's supplier can't be linked", True)
j("post", "/api/payees", json={**base(by["Paper Supplies"]), "party_id": acme["id"]})
with sqlite3.connect(config.DB_PATH) as raw:
    linked = raw.execute("SELECT party_id FROM payees WHERE name = 'Paper Supplies'").fetchone()[0]
check("a supplier is linked to a recurring payment", linked == acme["id"])
check("and the supplier counts it", any("recurring payment" in u[0] for u in j("get", f"/api/setup/parties/{acme['id']}")["used_by"]))
e = j("patch", f"/api/setup/parties/{acme['id']}", 400, json={"fields": {"kind": "customer"}})["error"]
check("a supplier linked to money out can't become a customer", "other way" in e, e)

# ---------- 6. SQL entries keep their code, and a code names the payment ----------
paper = next(p for p in j("get", f"/api/month?entity=1&month={CYC}")["payments"] if p["description"].startswith("Paper Supplies"))
due = paper["due_date"]
y, m, d = map(int, due.split("-"))
from datetime import date, timedelta  # noqa: E402
far = (date(y, m, d) + timedelta(days=20)).isoformat()
head = ["Doc No", "Doc Type", "Doc Date", "Description", "Company Name", "Amount", "Code", "Cheque No"]
text = "\n".join("\t".join(r) for r in [head, ["PV2611-901", "PV", far, "OFFICE ITEMS", "", f"{paper['amount']:.2f}", "400-A001", "000123"]]) + "\n"
r = j("post", "/api/sql/preview", json={"entity_id": 1, "text": text})
rec = r["records"][0]
check("a listing's code and cheque number are read", rec["code"] == "400-A001" and rec["cheque_no"] == "000123"
      and r["mapping"].get("code") == 6 and "code" in r["fields"], (rec, r["mapping"]))
check("a voucher 20 days off is matched by the supplier's code, which words alone wouldn't", rec["payment_id"] == paper["id"], rec)
text2 = text.replace("400-A001", "400-Z999")
r2 = j("post", "/api/sql/preview", json={"entity_id": 1, "text": text2})
check("another code doesn't match it", r2["records"][0]["payment_id"] is None, r2["records"][0])
j("post", "/api/sql/apply", json={"token": r["token"], "header_row": r["header_row"], "mapping": r["mapping"],
                                  "links": {str(rec["row"]): paper["id"]}})
with sqlite3.connect(config.DB_PATH) as raw:
    got = raw.execute("SELECT code, cheque_no FROM sql_entries WHERE doc_no = 'PV2611-901'").fetchone()
check("and kept on the SQL entry", got == ("400-A001", "000123"), got)
check("the supplier's code is now locked: SQL entries carry it", "sql_code" in j("get", f"/api/setup/parties/{acme['id']}")["locked"])

# ---------- 7. a filing rule naming a party ----------
fw = j("post", "/api/setup/filing_words", json={"fields": {"label": "Tenant invoices", "doc_kind": "invoice", "words": "NOTHING LIKE THIS",
                                                         "checklist_code": "einv-rental", "party_id": cust["id"]}})
inv = "\n".join("\t".join(r) for r in [head, ["IV2611-777", "IV", f"{CYC}-25", "RENTAL", "", "2000.00", "300-T001", ""]]) + "\n"
r = j("post", "/api/sql/preview", json={"entity_id": 1, "text": inv})
check("an SQL document with the customer's code is filed on the rule's checklist item", r["records"][0]["task_title"] and
      "tenant" in r["records"][0]["task_title"].lower(), r["records"][0])

# ---------- 7b. review fixes ----------
p = paste("gl_accounts", "Code\tDescription\tType\n101-000\tLand\tFixed Assets\n301-000\tBank\tCurrent Assets\n401-000\tTrade creditors\tCurrent Liabilities\n"
          "402-000\tAccruals\tCL\n901-000\tSuspense\tWhatever\n", preview=True)
check("a chart's plural and SQL type names are read; an unknown one is left empty with a note",
      [r["action"] for r in p["rows"]] == ["add"] * 5 and "not recognised" in (p["rows"][4]["message"] or ""), p["rows"])
p = paste("gl_accounts", "Code\tName\tParent\n700-100\tWages\t700-000\n700-000\tStaff costs\t\n")
gl = {r["code"]: r for r in j("get", "/api/setup/gl_accounts?entity=1")["rows"]}
check("an account listed before its parent still gets it", gl["700-100"]["parent_code"] == "700-000", p["rows"])
p = paste("parties", "Code,Company Name,TIN\n400-X002,Beta Sdn Bhd, Kuala Lumpur,C222\n400-X003,Gamma Bhd,C333\n400-X004,Delta Bhd,C444\n",
          kind="supplier", preview=True)
check("a comma inside an unquoted name is caught, not saved wrongly", p["rows"][0]["action"] == "error" and p["rows"][1]["action"] == "add", p["rows"])
p = paste("parties", 'Code\tCompany Name\n400-Q001\t"Quote Trading\n400-Q002\tOther Ltd\n', kind="supplier", preview=True)
check("a stray quote in a tab list doesn't swallow the lines after it", [r["code"] for r in p["rows"]] == ["400-Q001", "400-Q002"], p["rows"])
paste("parties", "x" * 6000, kind="supplier", preview=True, expect=400)
check("a line far too long to be a row is refused plainly", True)
p = paste("parties", "Code\tCompany Name\n300-T001\tTenant As Supplier\n", kind="supplier", preview=True)
check("a paste never turns a customer into a supplier", p["rows"][0]["action"] == "error" and "customer" in p["rows"][0]["message"], p["rows"])
both = "\n".join("\t".join(r) for r in [head, ["IV2611-778", "IV", f"{CYC}-25", "PAYROLL CHARGES", "", "100.00", "300-T001", ""]]) + "\n"
j("post", "/api/setup/filing_words", json={"fields": {"label": "Payroll invoices", "doc_kind": "invoice", "words": "PAYROLL",
                                                     "checklist_code": "payroll-jv", "sort": 0}})
r = j("post", "/api/sql/preview", json={"entity_id": 1, "text": both})
check("a filing rule naming the customer comes before word rules", "tenant" in (r["records"][0]["task_title"] or "").lower(), r["records"][0])
three = j("post", "/api/setup/entities", json={"fields": {"code": "XX", "name": "Example Third Co"}})
j("post", "/api/setup/parties", json={"fields": {"name": "XX Supplier", "kind": "supplier", "entity_id": three["id"]}})
e = j("delete", f"/api/setup/entities/{three['id']}", 409, json={"reason": "Wrong company"})["error"]
check("a company with customers or suppliers can't be deleted, and says why", "customer or supplier" in e, e)
j("patch", "/api/setup/entities/2", json={"fields": {"sql_database": None}})
j("patch", "/api/setup/entities/1", json={"fields": {"sql_database": None}})
j("patch", f"/api/setup/parties/{board['id']}", json={"fields": {"sql_code": "STAT-01"}})
e = j("patch", "/api/setup/entities/2", 400, json={"fields": {"sql_database": "AI_DB"}})["error"]
check("a company can't take its own SQL database while an every-company party has a code", "every company" in e, e)

# ---------- 8. the trail ----------
from hrp import audit  # noqa: E402
hist = j("get", f"/api/audit/record/parties/{acme['id']}")
check("a supplier has a history", len(hist["changes"]) >= 2, hist)
with db.connect() as cc:
    vr = audit.verify(cc)
    un = cc.execute("SELECT COUNT(*) FROM audit_tx WHERE action = 'Unattributed app write'").fetchone()[0]
check("every change was attributed and the trail checks out", vr["ok"] and un == 0, vr)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
