"""The books worked out here (update 28 and hrp/books.py), on made-up records only.

SQL prints each account's balance before its From date: a trial balance's Opening Balance and a GL ledger's Balance
B/F. Those are kept at import (and, for the reports read before update 28, taken again from their stored files by the
update), and the books start each account there and add the account lines. Profit and loss start again at the
financial year start, the amount moving into retained earnings. The trial balance worked out here is checked against
SQL's own for the same day. The workbooks are built to the layout of the real exports (as in ledger_fetch_test), with a
made-up company, accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.books_test
"""
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-books-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, books, config, db, ledger  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXA", "name": "Example April Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "EXU", "name": "Example Unassigned Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
    {"code": "EXN", "name": "Example Not In SQL Sdn Bhd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-444"}]},
    *[{"code": c, "name": f"Example Review {c} Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": f"000-9{i}"}]}
      for i, c in enumerate(("EXY", "EXM", "EXP", "EXS"))],
]}), encoding="utf-8")

COMPANY = "EXAMPLE HOLDINGS SDN BHD (202601000001 (1234567-X))"
STAMP = "14/11/2026 1:25:48 AM\nADMIN"


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


# ---------- a workbook as SQL Account writes it (copied from ledger_fetch_test, with the period and print time as arguments) ----------

def letter(col):
    s, col = "", col + 1
    while col:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def workbook(cells, merges):
    strings, rows = [], {}
    for (r, col), v in sorted(cells.items(), key=lambda kv: (kv[0][0], len(kv[0][1]), kv[0][1])):
        if isinstance(v, str):
            if v not in strings:
                strings.append(v)
            cell = f'<c r="{col}{r}" s="0" t="s"><v>{strings.index(v)}</v></c>'
        elif isinstance(v, datetime):
            cell = f'<c r="{col}{r}" s="3"><v>{(v - datetime(1899, 12, 30)).total_seconds() / 86400!r}</v></c>'
        elif isinstance(v, date):
            cell = f'<c r="{col}{r}" s="1"><v>{(v - date(1899, 12, 30)).days}</v></c>'
        else:
            cell = f'<c r="{col}{r}" s="2"><v>{v!r}</v></c>'
        rows.setdefault(r, []).append(cell)
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    sheet = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet {ns}><sheetData>'
             + "".join(f'<row r="{r}">{"".join(cs)}</row>' for r, cs in sorted(rows.items())) + "</sheetData>"
             + (f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges) + "</mergeCells>" if merges else "")
             + "</worksheet>")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                               '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {ns}><bookViews>'
                           '<workbookView xWindow="480" yWindow="105" WindowWidth="21075" WindowHeight="12585"/></bookViews>'
                           '<sheets><sheet sheetId="1" name="Report" r:id="rId3"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                                      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
                                      '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         '<numFmts count="3"><numFmt formatCode="dd/mm/yy h:mm AM/PM" numFmtId="164"/><numFmt formatCode="dd/mm/yyyy" numFmtId="165"/>'
                         '<numFmt formatCode="#,0.00;(#,0.00)" numFmtId="166"/></numFmts><fonts count="1"><font/></fonts><fills count="1"><fill/></fills>'
                         '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                         '<cellXfs count="4"><xf numFmtId="0" xfId="0"/><xf numFmtId="165" xfId="0" applyNumberFormat="1"/>'
                         '<xf numFmtId="166" xfId="0" applyNumberFormat="1"/><xf numFmtId="164" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>',
        "xl/sharedStrings.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings) + "</sst>",
        "xl/worksheets/sheet1.xml": sheet,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, text)
    return out.getvalue()


class Sheet:
    """Cells and merges of one sheet, by row (from 1) and column (from 0)."""
    def __init__(self):
        self.cells, self.merges, self.r = {}, [], 0

    def put(self, r, col, v, to=None):
        self.cells[(r, letter(col))] = v
        if to is not None and to != col:
            self.merges.append(f"{letter(col)}{r}:{letter(to)}{r}")

    def row(self, *cells):
        self.r += 1
        for cell in cells:
            if len(cell) == 2:
                self.put(self.r, cell[0], cell[1])
            else:
                self.put(self.r, cell[0], cell[2], cell[1])
        return self.r

    def bytes(self):
        return workbook(self.cells, self.merges)


def money(x):
    return f"({-x:,.2f})" if x < 0 else f"{x:,.2f}"


def jot(sections, period):
    """A GL Journal of Transaction. sections: [(label, [(doc no, dd/mm/yyyy, [(code, name, description, dr, cr)])])]."""
    s = Sheet()
    s.row((0, "Date"), (1, ":"), (2, 3, f"From {period[0]} to {period[1]}"), (7, STAMP))
    s.row((0, "Sort By"), (1, ":"), (2, 3, "PostDate;Ref1"))
    s.row((0, 5, COMPANY), (7, 8, "Page 1 of 1"))
    s.row((0, 1, "Doc Date"), (2, "A/C Code"), (3, "A/C Description"), (4, "Ref 1"), (5, 6, "Description"), (7, "Debit (MYR)"), (8, "Credit (MYR)"))
    for label, docs in sections:
        s.row((0, 6, label))
        dr_t = cr_t = 0.0
        for no, day, lines in docs:
            for k, (code, name, desc, dr, cr) in enumerate(lines):
                cells = [(2, code), (3, name), (4, no), (5, 6, desc)] + ([(0, 1, day)] if k == 0 else [])
                cells += ([(7, float(dr))] if dr else []) + ([(8, float(cr))] if cr else [])
                s.row(*cells)
                dr_t, cr_t = dr_t + dr, cr_t + cr
        s.row((0, 6, "Total  (MYR) :"), (7, float(round(dr_t, 2))), (8, float(round(cr_t, 2))))
    return s.bytes()


def gl_ledger(accounts, footer, period):
    """A GL Local - Ledger - Detail, Level 1. accounts: [(code, name, bf, [(date, ref or None, desc, dr, cr)])].
    footer: [(label, dr or None, cr or None)]."""
    s, end = Sheet(), 32
    s.row((0, end, "GL Local - Ledger - Detail"))
    s.row((0, end, f"From {period[0]} To {period[1]}"))
    s.row((0, 5, COMPANY), (6, end, "Page 1 of 1"))
    s.row((0, "Date"), (2, "Ref. 1/2"), (3, "Description 1"), (4, "Description 2"), (5, "Tax"), (6, 13, "Debit (MYR)"), (14, 21, "Credit (MYR)"), (22, end, "Bal. (MYR)"))
    all_dr = all_cr = all_bal = 0.0
    for code, name, bf, rows in accounts:
        s.row((0, end, f"Code : {code}  {name}"))
        s.row((3, "Balance B/F"), (27, end, money(bf)))
        bal, dr_t, cr_t = bf, 0.0, 0.0
        for day, ref, desc, dr, cr in rows:
            bal = round(bal + dr - cr, 2)
            dr_t, cr_t = dr_t + dr, cr_t + cr
            cells = [(0, day), (3, desc), (27, end, money(bal))] + ([(2, ref), (4, desc)] if ref else [])
            cells += ([(9, 13, money(dr))] if dr else []) + ([(16, 21, money(cr))] if cr else [])
            s.row(*cells)
        s.row((6, 13, money(dr_t)), (14, 21, money(cr_t)), (22, end, money(bal)))
        all_dr, all_cr, all_bal = all_dr + dr_t, all_cr + cr_t, all_bal + bal
    s.row((3, 5, "Total"), (6, 13, money(all_dr)), (14, 21, money(all_cr)), (22, end, money(all_bal)))
    s.row((3, 5, "* Reconciliation for Debit"))
    for label, dr, cr in footer:
        s.row((3, 5, label), *([(6, 13, money(dr))] if dr is not None else []), *([(14, 21, money(cr))] if cr is not None else []))
    return s.bytes()


def trial_balance(accounts, period_from, as_at, stamp="14/11/2026 1:33:31 AM ADMIN"):
    """A GL Trial Balance - This Month vs This Year with Opening. accounts: [(code, name, open, ptd, mtd, ytd)], each (dr, cr)."""
    s = Sheet()
    starts = {"open": (8, 12, 14, 18), "ptd": (20, 24, 28, 32), "mtd": (35, 39, 41, 42), "ytd": (45, 49, 52, 55)}

    def figures(vals):
        cells = []
        for g, (dr, cr) in zip(("open", "ptd", "mtd", "ytd"), vals):
            a, b, c_, d = starts[g]
            cells += ([(a, b, money(dr))] if dr else []) + ([(c_, d, money(cr))] if cr else [])
        return cells

    s.row((0, "Date"), (1, ":"), (2, 5, f"From {period_from} to {as_at}"), (43, stamp))
    s.row((0, "Sort By"), (1, ":"), (2, 5, "Code;Description"))
    s.row((0, "Project"), (1, ":"), (2, 5, "All"))
    s.row((5, 25, "EXAMPLE HOLDINGS SDN BHD"), (26, 37, "(202601000001 (1234567-X))"))
    s.row((0, 55, f"GL Trial Balance As At {as_at}"))
    s.row((43, 55, "Page 1 of 1"))
    s.row((0, "Acc Code"), (3, "Description"), (6, "Opening Balance"), (19, "Period To Date"), (33, "Month To Date"), (43, "Year To Date"))
    s.row((6, 12, "Debit"), (13, 18, "Credit"), (19, 24, "Debit"), (25, 32, "Credit"), (33, 39, "Debit"), (40, 42, "Credit"), (43, 49, "Debit"), (50, 55, "Credit"))
    totals = [[0.0, 0.0] for _ in range(4)]
    for code, name, *vals in accounts:
        s.row((0, 3, code), (4, 5, name), *figures(vals))
        for t, (dr, cr) in zip(totals, vals):
            t[0], t[1] = round(t[0] + dr, 2), round(t[1] + cr, 2)
    s.row((0, 5, "Grand Total Amount (MYR)"), *figures(totals))
    return s.bytes()


SAVED = [0]


def save(name, data):
    """A file in the downloads folder, each one saved a minute after the one before."""
    SAVED[0] += 1
    p = FOLDER / name
    p.write_bytes(data)
    t = datetime(2026, 11, 14, 9, 0).timestamp() + SAVED[0] * 60
    os.utime(p, (t, t))


# ---------- the made-up books of EXH (financial year from January) ----------

BANK = ("310-1000", "BANK-EXAMPLE 0001")
OR1 = ("OR2512-001", "10/12/2025", [(*BANK, "EXAMPLE TENANT", 500.0, 0), ("300-A0003", "EXAMPLE TENANT", "Rent", 0, 500.0)])
PV1 = ("PV2512-001", "20/12/2025", [("900-E002", "ELECTRICITY", "Electricity Dec", 200.0, 0), (*BANK, "Electricity Dec", 0, 200.0)])
PV2 = ("PV2601-001", "15/01/2026", [("9S0-T002", "SALARY - EXAMPLE", "Salary Jan", 1000.0, 0), (*BANK, "Salary Jan", 0, 1000.0)])
PV3 = ("PV2601-002", "20/01/2026", [("400-S0001", "EXAMPLE PRINT SDN BHD", "Payment For Account", 300.0, 0), (*BANK, "EXAMPLE PRINT", 0, 300.0)])
IV1 = ("IV2512-001", "05/12/2025", [("300-A0003", "EXAMPLE TENANT", "Rent Dec", 800.0, 0), ("530-1000", "OTHER INCOME - RENTAL", "Rent Dec", 0, 800.0)])
IV2 = ("IV2601-001", "05/01/2026", [("300-A0003", "EXAMPLE TENANT", "Rent Jan", 800.0, 0), ("530-1000", "OTHER INCOME - RENTAL", "Rent Jan", 0, 800.0)])
JOT = jot([("Bank Journal", [OR1, PV1, PV2, PV3]), ("Sales Journal", [IV1, IV2])], ("01/12/2025", "31/01/2026"))

L1 = gl_ledger([
    ("100-0000", "SHARE CAPITAL", -9000.0, []),
    ("150-0000", "RETAINED EARNING", -2000.0, []),
    ("300-0000", "TRADE DEBTORS", 1000.0, []),
    ("310-1000", "BANK-EXAMPLE 0001", 12000.0, [("10/12/2025", "OR2512-001", "EXAMPLE TENANT", 500.0, 0), ("20/12/2025", "PV2512-001", "Electricity Dec", 0, 200.0),
                                                ("15/01/2026", "PV2601-001", "Salary Jan", 0, 1000.0), ("20/01/2026", "PV2601-002", "EXAMPLE PRINT", 0, 300.0)]),
    ("400-0000", "TRADE CREDITORS", -500.0, []),
    ("530-1000", "OTHER INCOME - RENTAL", -3000.0, [("05/12/2025", "IV2512-001", "Rent Dec", 0, 800.0), ("05/01/2026", "IV2601-001", "Rent Jan", 0, 800.0)]),
    ("900-E002", "ELECTRICITY", 1500.0, [("20/12/2025", "PV2512-001", "Electricity Dec", 200.0, 0)]),
    ("9S0-T002", "SALARY - EXAMPLE", 0.0, [("15/01/2026", "PV2601-001", "Salary Jan", 1000.0, 0)]),
], [("Add Code : 300-0000  TRADE DEBTORS", 1600.0, 500.0), ("Add Code : 400-0000  TRADE CREDITORS", 300.0, None)], ("01/12/2025", "31/01/2026"))

# From 1 December 2025 (not the year start): SQL moves the earlier profit and loss (3,000.00 of rental, 1,500.00 of
# electricity) into retained earnings inside Period To Date; Year To Date of profit and loss is the lines from 1 December.
TB1 = [("100-0000", "SHARE CAPITAL", (0, 9000.0), (0, 0), (0, 0), (0, 9000.0)),
       ("150-0000", "RETAINED EARNING", (0, 2000.0), (0, 1500.0), (0, 0), (0, 3500.0)),
       ("300-0000", "TRADE DEBTORS", (1000.0, 0), (1600.0, 500.0), (800.0, 0), (2100.0, 0)),
       ("310-1000", "BANK-EXAMPLE 0001", (12000.0, 0), (500.0, 1500.0), (0, 1300.0), (11000.0, 0)),
       ("400-0000", "TRADE CREDITORS", (0, 500.0), (300.0, 0), (300.0, 0), (0, 200.0)),
       ("530-1000", "OTHER INCOME - RENTAL", (0, 3000.0), (3000.0, 1600.0), (0, 800.0), (0, 1600.0)),
       ("900-E002", "ELECTRICITY", (1500.0, 0), (200.0, 1500.0), (0, 0), (200.0, 0)),
       ("9S0-T002", "SALARY - EXAMPLE", (0, 0), (1000.0, 0), (1000.0, 0), (1000.0, 0))]

# ---------- 1. records at update 27 with SQL's reports read, then update 28 ----------
full = db.MIGRATIONS[:]
check("update 28 is the opening balances", len(full) >= 28 and full[27] is ledger.install_openings)
db.MIGRATIONS[:] = full[:27]
db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def fetch(eid):
    p = j("post", "/api/sql/preview", json={"entity_id": eid, "fetch": True})
    return j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


EID, EXA, EXU, EXN = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXH", "EXA", "EXU", "EXN"))
ACCT = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("150-0000", "RETAINED EARNING", "equity", None),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control"), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control"), ("530-1000", "OTHER INCOME - RENTAL", "income", None),
         ("900-E002", "ELECTRICITY", "expense", None), ("9S0-T002", "SALARY - EXAMPLE", "expense", None)]
write("the chart of accounts and the bank's GL code",
      ("UPDATE accounts SET gl_code = '310-1000' WHERE id = ?", (ACCT,)),
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (e, *a)) for e in (EID, EXA) for a in CHART],
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (e, *a)) for e in (EXU, EXN) for a in CHART
        if a[0] != "150-0000"],
      ("UPDATE gl_accounts SET sql_type = 'RE' WHERE code = '150-0000'", ()))

save("1.xlsx", JOT)
save("2.xlsx", L1)
save("3.xlsx", trial_balance(TB1, "01/12/2025", "31/01/2026"))
res = fetch(EID)
check("at update 27 a fetch keeps the journal, the ledger and the trial balance", len(res["ledger"]["files"]) == 3
      and q("PRAGMA user_version")[0]["user_version"] == 27, str(res))
check("below update 28 there is no opening balances table", not q("SELECT 1 FROM sqlite_master WHERE name = 'ledger_openings'"))
# A ledger from 1 January read too, whose stored file then goes missing: the update skips it and says so.
save("4.xlsx", gl_ledger([("310-1000", "BANK-EXAMPLE 0001", 12300.0, [("15/01/2026", "PV2601-001", "Salary Jan", 0, 1000.0),
                                                                     ("20/01/2026", "PV2601-002", "EXAMPLE PRINT", 0, 300.0)])], [], ("01/01/2026", "31/01/2026")))
fetch(EID)
gone = q("""SELECT d.stored_path FROM ledger_batches b JOIN documents d ON d.id = b.document_id WHERE b.file_name = '4.xlsx'""")[0]
p4 = config.DOCS_DIR / gone["stored_path"]
os.chmod(p4, stat.S_IWRITE | stat.S_IREAD)
p4.unlink()

db.MIGRATIONS[:] = full
trail = db.init()
check("update 28 runs, and every update after it", q("PRAGMA user_version")[0]["user_version"] == len(full))
op = q("SELECT * FROM ledger_openings WHERE entity_id = ? ORDER BY source, account_code", (EID,))
tb_rows = {r["account_code"]: (r["dr_sen"], r["cr_sen"]) for r in op if r["source"] == "sql_tb"}
led_rows = {r["account_code"]: (r["dr_sen"], r["cr_sen"]) for r in op if r["source"] == "sql_ledger"}
check("the trial balance's openings are taken again from its stored file, at its From date",
      {r["as_of"] for r in op} == {"2025-12-01"} and tb_rows == {"100-0000": (0, S(9000)), "150-0000": (0, S(2000)), "300-0000": (S(1000), 0),
                                                              "310-1000": (S(12000), 0), "400-0000": (0, S(500)), "530-1000": (0, S(3000)),
                                                              "900-E002": (S(1500), 0), "9S0-T002": (0, 0)}, str(op))
check("and the ledger's Balance B/F, as its own source", led_rows == tb_rows, str(led_rows))
logs = [r["what"] for r in q("SELECT what FROM activity ORDER BY id")]
check("the ledger whose stored file is missing is skipped and named in the activity log",
      any("'4.xlsx'" in m and "missing or has changed" in m for m in logs) and any(m.startswith("Update 28: opening balances taken from 2 stored") for m in logs), str(logs[-4:]))
rows28 = q("SELECT op FROM audit_row WHERE tbl = 'ledger_openings'")
check("the openings are recorded in the audit trail as added by the update, not as a baseline",
      rows28 and {r["op"] for r in rows28} == {"insert"} and len(rows28) == len(op), str({r["op"] for r in rows28}))
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out after update 28", v["ok"], v)
check("start-up repaired nothing", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)
check("the guards are in place", q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'ledger_openings_guard%'")[0]["n"] == 2)

# ---------- 2. the guard: openings entered here only for a company not kept in SQL ----------
try:
    write("an opening entered here for a company kept in SQL",
          ("INSERT INTO ledger_openings (entity_id, account_code, as_of, dr_sen, cr_sen, source, set_at) VALUES (?, '310-1000', '2026-01-01', 100, 0, 'here', ?)",
           (EID, db.now())))
    refused = None
except sqlite3.DatabaseError as ex:
    refused = str(ex)
check("the records refuse an opening entered here for a company kept in SQL", refused == ledger.REFUSED_OPENING, refused)
try:
    write("an SQL opening turned into one entered here", ("UPDATE ledger_openings SET source = 'here' WHERE entity_id = ? AND account_code = '310-1000'", (EID,)))
    refused = None
except sqlite3.DatabaseError as ex:
    refused = str(ex)
check("and refuse turning one of SQL's into one entered here", refused == ledger.REFUSED_OPENING, refused)
con = db.connect()
con.arm("user", "test: openings entered here")
try:
    ledger.put_openings(con, EID, None, "2026-01-01", "here", [{"code": "310-1000", "dr_sen": 100, "cr_sen": 0}], False)
    said = None
except ledger.LedgerError as ex:
    said = str(ex)
check("and so does the app, in words", said == ledger.REFUSED_OPENING, said)
got = ledger.put_openings(con, EXN, None, "2026-01-01", "here", [{"code": "310-1000", "dr_sen": S(700), "cr_sen": 0},
                                                                 {"code": "100-0000", "dr_sen": 0, "cr_sen": S(700)}], False)
con.commit()
check("a company whose books are kept here can enter its openings", got["added"] == 2, str(got))
o = books.opening_at(con, EXN, "310-1000", "2026-02-01")
check("and they are read as entered here", (o["balance"], o["as_of"], o["how"]) == (S(700), "2026-01-01", "here"), str(o))
o = books.opening_at(con, EXN, "9S0-T002", "2026-02-01")
check("an account with no opening in books kept here starts fresh", (o["balance"], o["how"]) == (0, "fresh"), str(o))
con.disarm()
con.close()
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DROP TRIGGER ledger_openings_guard_here")
raw.commit()
with db.connect() as r:
    check("a guard dropped by another program is noticed", ledger.guard_missing(r))
raw.close()
trail = db.init()
check("and start-up puts it back, naming the guard it put back (not another one)",
      trail["triggers_repaired"] == ["ledger_openings_guard_here"] and not q(
    "SELECT 1 FROM sqlite_master WHERE name = 'ledger_openings_guard_here' AND sql IS NULL")
      and q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name = 'ledger_openings_guard_here'")[0]["n"] == 1, trail)
with db.connect() as r:
    check("and nothing is missing after", not ledger.guard_missing(r))

# ---------- 3. at import: the openings kept, and replaced by a later read for the same day ----------
save("5.xlsx", gl_ledger([("100-0000", "SHARE CAPITAL", -9000.0, []),
                          ("310-1000", "BANK-EXAMPLE 0001", 12300.0, [("15/01/2026", "PV2601-001", "Salary Jan", 0, 1000.0),
                                                                     ("20/01/2026", "PV2601-002", "EXAMPLE PRINT", 0, 300.0)]),
                          ("530-1000", "OTHER INCOME - RENTAL", -3800.0, [("05/01/2026", "IV2601-001", "Rent Jan", 0, 800.0)]),
                          ("9S0-T002", "SALARY - EXAMPLE", 0.0, [("15/01/2026", "PV2601-001", "Salary Jan", 1000.0, 0)])], [], ("01/01/2026", "31/01/2026")))
res = fetch(EID)
f5 = res["ledger"]["files"][0]
check("a ledger read at import keeps its Balance B/F as openings at its From date",
      f5["summary"]["openings"] == {"as_of": "2026-01-01", "accounts": 4, "added": 4, "changed": 0, "same": 0, "removed": 0}, str(f5["summary"]))
check("the activity log says so", any("opening balances at 01/01/2026 kept for 4 accounts" in m for m in [r["what"] for r in q("SELECT what FROM activity")]))
with db.connect() as con:
    o = books.opening_at(con, EID, "310-1000", "2026-01-15")
    check("the latest opening on or before the day is the start: the ledger's at 1 January", (o["balance"], o["as_of"], o["how"]) == (S(12300), "2026-01-01", "sql_ledger"), str(o))
    o = books.opening_at(con, EID, "310-1000", "2026-01-16")
    check("plus the lines after it", o["balance"] == S(11300), str(o))
    o = books.opening_at(con, EID, "310-1000", "2025-12-15")
    check("on the same day SQL's trial balance is preferred to its ledger", (o["balance"], o["as_of"], o["how"]) == (S(12500), "2025-12-01", "sql_tb"), str(o))
    o = books.opening_at(con, EID, "530-1000", "2026-01-20")
    check("a profit and loss account starts again at the year start, whatever SQL's cumulative B/F says", o["balance"] == -S(800), str(o))
    o = books.opening_at(con, EID, "530-1000", "2026-01-01")
    check("its balance before the year start day is 0", o["balance"] == 0, str(o))
    o = books.opening_at(con, EID, "530-1000", "2025-12-31")
    check("and the day before, the year's profit and loss so far", o["balance"] == -S(3800), str(o))
    o = books.opening_at(con, EID, "300-A0003", "2025-12-20")
    check("a customer's own code starts inside its control account", (o["balance"], o["how"]) == (S(300), "in_control"), str(o))
    o = books.opening_at(con, EID, "310-1000", "2025-11-30")
    check("before any opening kept, the balance is unknown, and it says so", o["balance"] is None and "No opening balance" in o["why"], str(o))
    o = books.opening_at(con, EID, "100-0000", "2026-03-01")
    check("an account on the trial balance's opening with no line keeps its figure", o["balance"] == -S(9000), str(o))

TB1B = [(code, name, *vals) for code, name, *vals in TB1]
TB1B[1] = ("150-0000", "RETAINED EARNING", (0, 2100.0), (0, 1500.0), (0, 0), (0, 3600.0))
TB1B[3] = ("310-1000", "BANK-EXAMPLE 0001", (12100.0, 0), (500.0, 1500.0), (0, 1300.0), (11100.0, 0))
before_ids = {r["account_code"]: r["id"] for r in q("SELECT * FROM ledger_openings WHERE entity_id = ? AND source = 'sql_tb'", (EID,))}
save("6.xlsx", trial_balance(TB1B, "01/12/2025", "31/01/2026", stamp="14/11/2026 2:10:00 AM ADMIN"))
res = fetch(EID)
s6 = res["ledger"]["files"][0]["summary"]["openings"]
after = {r["account_code"]: r for r in q("SELECT * FROM ledger_openings WHERE entity_id = ? AND source = 'sql_tb'", (EID,))}
check("a trial balance read again for the same day replaces the figures kept", s6["changed"] == 2 and s6["same"] == 6
      and (after["310-1000"]["dr_sen"], after["150-0000"]["cr_sen"]) == (S(12100), S(2100)), str(s6))
check("in place, so the audit trail keeps what they said before",
      {k: r["id"] for k, r in after.items()} == before_ids and any(
          json.loads(x["before"])["dr_sen"] == S(12000) and json.loads(x["after"])["dr_sen"] == S(12100)
          for x in q("SELECT before, after FROM audit_row WHERE tbl = 'ledger_openings' AND op = 'update'")), str(after))
check("the ledger's openings for that day are left as they were", q("SELECT dr_sen FROM ledger_openings WHERE entity_id = ? AND source = 'sql_ledger' AND account_code = '310-1000' AND as_of = '2025-12-01'",
                                                                    (EID,))[0]["dr_sen"] == S(12000))
save("7.xlsx", trial_balance(TB1, "01/12/2025", "31/01/2026", stamp="14/11/2026 2:20:00 AM ADMIN"))
s7 = fetch(EID)["ledger"]["files"][0]["summary"]["openings"]
check("and read again as first printed, they go back", s7["changed"] == 2
      and q("SELECT dr_sen FROM ledger_openings WHERE entity_id = ? AND source = 'sql_tb' AND account_code = '310-1000'", (EID,))[0]["dr_sen"] == S(12000), str(s7))
with db.connect() as con:
    con.arm("user", "test: a trial balance that no longer lists an account")
    got = ledger.put_openings(con, EID, after["310-1000"]["batch_id"], "2025-12-01", "sql_tb",
                              [{"code": k, "dr_sen": v[0], "cr_sen": v[1]} for k, v in tb_rows.items() if k != "9S0-T002"], True)
    left = con.execute("SELECT COUNT(*) FROM ledger_openings WHERE entity_id = ? AND source = 'sql_tb' AND as_of = '2025-12-01'", (EID,)).fetchone()[0]
    con.rollback()
    con.disarm()
check("an account a later trial balance no longer lists is taken off that day's openings", got["removed"] == 1 and left == 7, str(got))

# ---------- 4. the general ledger ----------
with db.connect() as con:
    L = books.ledger_report(con, EID, "310-1000", "2025-12-01", "2026-01-31")
    a = L["accounts"][0]
    check("the ledger of one account: its opening, every line with a running balance, its totals and closing",
          (a["opening_sen"], a["opening_how"], [r["doc_no"] for r in a["rows"]], [r["balance_sen"] for r in a["rows"]], a["dr_sen"], a["cr_sen"], a["closing_sen"])
          == (S(12000), "sql_tb", ["OR2512-001", "PV2512-001", "PV2601-001", "PV2601-002"], [S(12500), S(12300), S(11300), S(11000)], S(500), S(1500), S(11000))
          and a["notes"] == [], str(a))
    L = books.ledger_report(con, EID, "530-1000", "2025-12-01", "2026-01-31")
    a = L["accounts"][0]
    check("a profit and loss account's ledger shows the year start moving its balance to retained earnings",
          [(r["kind"], r["date"], r["dr_sen"], r["cr_sen"], r["balance_sen"]) for r in a["rows"]]
          == [("line", "2025-12-05", 0, S(800), -S(3800)), ("year_start", "2026-01-01", S(3800), 0, 0), ("line", "2026-01-05", 0, S(800), -S(800))]
          and a["opening_sen"] == -S(3000) and a["closing_sen"] == -S(800) and a["notes"] == [], str(a))
    L = books.ledger_report(con, EID, "150-0000", "2025-12-01", "2026-01-31")
    a = L["accounts"][0]
    check("and retained earnings' ledger shows it arriving", [(r["kind"], r["cr_sen"]) for r in a["rows"]] == [("year_start", S(2100))]
          and (a["opening_sen"], a["closing_sen"]) == (-S(2000), -S(4100)), str(a))
    L = books.ledger_report(con, EID, None, "2025-12-01", "2026-01-31")
    by = {x["code"]: x for x in L["accounts"]}
    check("all accounts: a customer's code under its own code, with its control account named",
          "300-A0003" in by and by["300-A0003"]["control"] == "300-0000" and by["300-A0003"]["opening_how"] == "in_control"
          and by["300-A0003"]["closing_sen"] == S(1100) and by["400-S0001"]["control"] == "400-0000", str(by.get("300-A0003")))

# ---------- 5. the trial balance ----------
    T = books.trial_balance(con, EID, "2025-12-01", "2026-01-31")
    by = {x["code"]: x for x in T["accounts"]}
    check("the trial balance balances", T["balanced"] and T["totals"]["closing_dr_sen"] == T["totals"]["closing_cr_sen"] == S(14400)
          and T["totals"]["opening_dr_sen"] == S(14500) and T["totals"]["reset_sen"] == 0, str(T["totals"]))
    check("the January year start inside the period moves profit and loss into retained earnings",
          (by["530-1000"]["reset_sen"], by["900-E002"]["reset_sen"], by["150-0000"]["reset_sen"], by["150-0000"]["closing_sen"])
          == (S(3800), -S(1700), -S(2100), -S(4100)) and by["900-E002"]["closing_sen"] == 0 and by["9S0-T002"]["closing_sen"] == S(1000), str(by["150-0000"]))
    check("customer and supplier codes are shown apart unless rolled up", "300-A0003" in by and by["300-0000"]["closing_sen"] == S(1000))
    R = books.trial_balance(con, EID, "2025-12-01", "2026-01-31", rollup=True)
    rb = {x["code"]: x for x in R["accounts"]}
    check("rolled up, they are added into their control accounts", "300-A0003" not in rb and rb["300-0000"]["rolled"] == ["300-A0003"]
          and (rb["300-0000"]["closing_dr_sen"], rb["400-0000"]["closing_cr_sen"]) == (S(2100), S(200)) and R["balanced"]
          and R["totals"]["closing_dr_sen"] == S(14100), str(rb["300-0000"]))
    T = books.trial_balance(con, EID, "2026-01-01", "2026-01-31")
    by = {x["code"]: x for x in T["accounts"]}
    check("from the year start day, profit and loss open at 0 and retained earnings hold the year before",
          T["balanced"] and by["530-1000"]["opening_sen"] == 0 and by["150-0000"]["opening_sen"] == -S(4100) and not any(x["reset_sen"] for x in T["accounts"]),
          str(T["totals"]))

# ---------- 6. an April financial year, and a chart with no retained earnings account ----------
write("EXA's year starts in April", ("UPDATE entities SET fy_start = 4 WHERE id = ?", (EXA,)))
con = db.connect()
con.arm("user", "test: EXA's books")
imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXA, db.now())).lastrowid
tb_b = ledger.new_batch(con, EXA, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx", period_from="2026-01-01", period_to="2026-12-31")
ledger.put_openings(con, EXA, tb_b, "2026-01-01", "sql_tb", [{"code": "310-1000", "dr_sen": S(5000), "cr_sen": 0}, {"code": "100-0000", "dr_sen": 0, "cr_sen": S(3000)},
                                                           {"code": "150-0000", "dr_sen": 0, "cr_sen": S(1000)}, {"code": "530-1000", "dr_sen": 0, "cr_sen": S(1500)},
                                                           {"code": "900-E002", "dr_sen": S(500), "cr_sen": 0}], True)
jb = ledger.new_batch(con, EXA, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-01-01", period_to="2026-12-31",
                      period_source="printed", sections=[{"label": "Bank Journal", "book": "bank"}])
for d in ({"doc_no": "OR2602-001", "doc_date": "2026-02-15", "book": "bank", "lines": [{"code": "310-1000", "dr_sen": S(400), "cr_sen": 0}, {"code": "530-1000", "dr_sen": 0, "cr_sen": S(400)}]},
          {"doc_no": "PV2605-001", "doc_date": "2026-05-10", "book": "bank", "lines": [{"code": "900-E002", "dr_sen": S(100), "cr_sen": 0}, {"code": "310-1000", "dr_sen": 0, "cr_sen": S(100)}]}):
    ledger.put_document(con, EXA, jb, d)
imp_u = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (EXU, db.now())).lastrowid
tb_u = ledger.new_batch(con, EXU, origin="sql", report="trial_balance", sql_import_id=imp_u, file_name="tb.xlsx", period_from="2026-01-01", period_to="2026-01-31")
ledger.put_openings(con, EXU, tb_u, "2026-01-01", "sql_tb", [{"code": "310-1000", "dr_sen": S(1000), "cr_sen": 0}, {"code": "530-1000", "dr_sen": 0, "cr_sen": S(1000)}], True)
con.commit()
T = books.trial_balance(con, EXA, "2026-01-01", "2026-12-31")
by = {x["code"]: x for x in T["accounts"]}
check("with the year starting in April, profit and loss of January to March move into retained earnings on 1 April",
      T["balanced"] and (by["530-1000"]["opening_sen"], by["530-1000"]["reset_sen"], by["530-1000"]["closing_sen"]) == (-S(1500), S(1900), 0)
      and (by["900-E002"]["reset_sen"], by["900-E002"]["closing_sen"]) == (-S(500), S(100))
      and (by["150-0000"]["opening_sen"], by["150-0000"]["reset_sen"], by["150-0000"]["closing_sen"]) == (-S(1000), -S(1400), -S(2400)), str(by))
check("the note names the year start", any("01/04/2026" in n for n in T["notes"]), str(T["notes"]))
check("and opening_at follows it", books.opening_at(con, EXA, "530-1000", "2026-04-01")["balance"] == 0
      and books.opening_at(con, EXA, "530-1000", "2026-03-31")["balance"] == -S(1900))
T = books.trial_balance(con, EXU, "2026-01-01", "2026-01-31")
un = [x for x in T["accounts"] if x["code"] is None]
check("with no retained earnings account, what the year start moved is a line of its own, and the trial balance still balances",
      T["balanced"] and len(un) == 1 and un[0]["name"] == books.UNASSIGNED and un[0]["opening_sen"] == -S(1000)
      and any("no retained earnings account" in n for n in T["notes"]), str(T["accounts"]))
con.disarm()
con.close()

# ---------- 7. against SQL's own trial balance ----------
with db.connect() as con:
    ch = books.check_against_sql(con, EID, "2025-12-01", "2026-01-31")
check("the trial balance agrees with SQL's, read again from its stored file", ch["outcome"] == "ok" and ch["differences"] == []
      and ch["agree"] == 8 and ch["sql"]["file_name"] == "7.xlsx" and ch["text"].startswith("Agrees with SQL's trial balance as at 31/01/2026"), str(ch))
with db.connect() as con:
    ch = books.check_against_sql(con, EID, "2025-12-01", "2026-01-30")
check("with no SQL trial balance for that day, the check is skipped and says why", ch["outcome"] == "skipped" and "30/01/2026" in ch["text"], str(ch))
# SQL's trial balance from 1 January holds 100.00 more salary paid from the bank than the lines kept here.
TB_D = [("100-0000", "SHARE CAPITAL", (0, 9000.0), (0, 0), (0, 0), (0, 9000.0)),
        ("150-0000", "RETAINED EARNING", (0, 2000.0), (0, 2100.0), (0, 0), (0, 4100.0)),
        ("300-0000", "TRADE DEBTORS", (1300.0, 0), (800.0, 0), (800.0, 0), (2100.0, 0)),
        ("310-1000", "BANK-EXAMPLE 0001", (12300.0, 0), (0, 1400.0), (0, 1400.0), (10900.0, 0)),
        ("400-0000", "TRADE CREDITORS", (0, 500.0), (300.0, 0), (300.0, 0), (0, 200.0)),
        ("530-1000", "OTHER INCOME - RENTAL", (0, 3800.0), (3800.0, 800.0), (0, 800.0), (0, 800.0)),
        ("900-E002", "ELECTRICITY", (1700.0, 0), (0, 1700.0), (0, 0), (0, 0)),
        ("9S0-T002", "SALARY - EXAMPLE", (0, 0), (1100.0, 0), (1100.0, 0), (1100.0, 0))]
save("8.xlsx", trial_balance(TB_D, "01/01/2026", "31/01/2026", stamp="14/11/2026 3:00:00 AM ADMIN"))
fetch(EID)
with db.connect() as con:
    ch = books.check_against_sql(con, EID, "2026-01-01", "2026-01-31")
    again = books.check_against_sql(con, EID, "2025-12-01", "2026-01-31")
diff = {(d["code"], d["what"]): (d["sql_sen"], d["here_sen"], d["diff_sen"]) for d in ch["differences"]}
check("a deliberate difference is named, account by account, with the amounts", ch["outcome"] == "warn" and diff == {
    ("9S0-T002", "profit and loss from SQL's From date"): (S(1100), S(1000), -S(100)),
    ("310-1000", "closing"): (S(10900), S(11000), S(100)),
    ("310-1000", "period"): (-S(1400), -S(1300), S(100))} and ch["text"].startswith("2 accounts differ"), str(ch["differences"]))
check("in plain words", any(d["text"].startswith("310-1000 BANK-EXAMPLE 0001: its balance at 31/01/2026: SQL's trial balance has 10,900.00, the books here 11,000.00")
                            for d in ch["differences"]), str([d["text"] for d in ch["differences"]]))
check("the check picks SQL's trial balance from the period's own From date", again["outcome"] == "ok" and again["sql"]["file_name"] == "7.xlsx", str(again))

# ---------- 8. the routes the page reads ----------
trail_before = q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"]
d = j("get", f"/api/books/trial-balance?entity={EID}&from=2025-12-01&to=2026-01-31&rollup=1")
check("the trial balance route gives the rows, totals and the check", d["balanced"] and d["rollup"] and d["check"]["outcome"] == "ok"
      and {"accounts", "totals", "notes", "openings", "from", "to", "fy_start"} <= d.keys()
      and all({"code", "name", "opening_dr_sen", "opening_cr_sen", "dr_sen", "cr_sen", "reset_sen", "closing_dr_sen", "closing_cr_sen", "rolled"} <= x.keys()
              for x in d["accounts"]), str(d.keys()))
check("its openings are named by where they came from", d["openings"] and d["openings"][0]["as_of"] == "2025-12-01" and d["openings"][0]["how"] == "sql_tb", str(d["openings"]))
d = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-01-01&to=2026-01-31")
check("and the differences from SQL's", d["check"]["outcome"] == "warn" and len(d["check"]["differences"]) == 3 and not d["rollup"], str(d["check"]))
d = j("get", f"/api/books/ledger?entity={EID}&account=310-1000&from=2025-12-01&to=2026-01-31")
check("the ledger route gives the account's lines, and the accounts to search", d["account"] == "310-1000" and len(d["accounts"]) == 1
      and d["accounts"][0]["closing_sen"] == S(11000) and {"rows", "opening_sen", "control", "notes"} <= d["accounts"][0].keys()
      and any(x["code"] == "300-A0003" and x["control"] == "300-0000" for x in d["choices"]), str(d["accounts"][0].keys()))
d = j("get", f"/api/books/ledger?entity={EID}")
today = date.today().isoformat()
check("with no dates, the current financial year to date", (d["from"], d["to"]) == (f"{today[:4]}-01-01", today), str((d["from"], d["to"])))
check("a date that isn't one is refused in words", "isn't a date" in j("get", f"/api/books/trial-balance?entity={EID}&from=2026-13-01", 400)["error"])
check("so is a From date after the To date", "after" in j("get", f"/api/books/ledger?entity={EID}&from=2026-02-01&to=2026-01-01", 400)["error"])
check("the routes write nothing", q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"] == trail_before)

# ---------- 9. the page ----------
js = (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8")
check("the SQL page's card is called Journals and invoices", "<h2>Journals and invoices</h2>" in js and "Journals and customer invoices" not in js
      and "Customer Invoice listings to see them here" not in js)
check("the sidebar has Accounting › Books", '["Accounting", [["books", "Books"]]]' in js and "viewBooks(main)" in js
      and "/api/books/trial-balance" in js and "/api/books/ledger" in js and "/api/ledger/doc" in js)

# ---------- 10. a year's last day, later openings, part of SQL's ledger, customers' codes, books kept here ----------
REV = {x: q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXY", "EXM", "EXP", "EXS")}
write("the chart of the review companies",
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (e, *a)) for e in REV.values() for a in CHART],
      ("UPDATE gl_accounts SET sql_type = 'RE' WHERE code = '150-0000'", ()))
con = db.connect()
con.arm("user", "test: the review companies' books")


def rbatch(eid, report, f, t):
    imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)", (eid, db.now())).lastrowid
    return ledger.new_batch(con, eid, origin="sql", report=report, sql_import_id=imp, file_name=f"{report}.xlsx", period_from=f, period_to=t,
                            period_source="printed" if report == "journal" else None,
                            sections=[{"label": "Bank Journal", "book": "bank"}] if report == "journal" else None)


def rdoc(eid, b, no, d, lines):
    ledger.put_document(con, eid, b, {"doc_no": no, "doc_date": d, "book": "bank",
                                      "lines": [{"code": c, "dr_sen": S(dr), "cr_sen": S(cr)} for c, dr, cr in lines]})


def ropens(eid, b, as_of, src, figs, complete):
    ledger.put_openings(con, eid, b, as_of, src, [{"code": c, "dr_sen": S(max(v, 0)), "cr_sen": S(max(-v, 0))} for c, v in figs], complete)


def follows(T):
    return not any("doesn't follow" in n for n in T["notes"])


# A period ending on the last day of the financial year closes before that year end's move, which belongs to the next.
EY = REV["EXY"]
ropens(EY, rbatch(EY, "trial_balance", "2026-01-01", "2026-01-31"), "2026-01-01", "sql_tb",
       [("310-1000", 10000), ("100-0000", -8000), ("150-0000", -1000), ("530-1000", -1500), ("900-E002", 500)], True)
jb = rbatch(EY, "journal", "2026-01-01", "2027-01-31")
rdoc(EY, jb, "OR2603-001", "2026-03-01", [("310-1000", 400, 0), ("530-1000", 0, 400)])
rdoc(EY, jb, "PV2605-001", "2026-05-01", [("900-E002", 100, 0), ("310-1000", 0, 100)])
con.commit()
T = books.trial_balance(con, EY, "2026-01-01", "2026-12-31")
by = {x["code"]: x for x in T["accounts"]}
check("a trial balance to the year's last day closes profit and loss at the year's figures, before the year end's move",
      T["balanced"] and follows(T) and (by["530-1000"]["closing_sen"], by["900-E002"]["closing_sen"], by["150-0000"]["closing_sen"])
      == (-S(400), S(100), -S(2000)) and not any(x["reset_sen"] for x in T["accounts"]), str(T["notes"]))
a = books.ledger_report(con, EY, "530-1000", "2026-01-01", "2026-12-31")["accounts"][0]
check("and the ledger's closing is its running balance, with no note", a["closing_sen"] == a["rows"][-1]["balance_sen"] == -S(400)
      and a["notes"] == [], str(a))
T = books.trial_balance(con, EY, "2027-01-01", "2027-01-31")
by = {x["code"]: x for x in T["accounts"]}
check("the next year opens with the move done", T["balanced"] and by["150-0000"]["opening_sen"] == -S(2300) and "530-1000" not in by, str(T["accounts"]))
T = books.trial_balance(con, EY, "2026-12-01", "2027-01-31")
by = {x["code"]: x for x in T["accounts"]}
check("a period holding the year start shows the move in its Year start column", T["balanced"] and follows(T)
      and (by["530-1000"]["reset_sen"], by["150-0000"]["reset_sen"], by["150-0000"]["closing_sen"]) == (S(400), -S(300), -S(2300)), str(T["notes"]))

# A later opening of a profit and loss account in the same year is the year so far: the latest opening wins.
EM = REV["EXM"]
ropens(EM, rbatch(EM, "trial_balance", "2026-01-01", "2026-01-31"), "2026-01-01", "sql_tb",
       [("310-1000", 10000), ("100-0000", -8000), ("150-0000", -1000), ("530-1000", -1500), ("900-E002", 500)], True)
ropens(EM, rbatch(EM, "trial_balance", "2026-04-01", "2026-06-30"), "2026-04-01", "sql_tb",
       [("310-1000", 10600), ("100-0000", -8000), ("150-0000", -2000), ("530-1000", -600)], True)
rdoc(EM, rbatch(EM, "journal", "2026-04-01", "2026-06-30"), "OR2605-001", "2026-05-01", [("310-1000", 400, 0), ("530-1000", 0, 400)])
con.commit()
o = books.opening_at(con, EM, "530-1000", "2026-04-01")
check("a profit and loss opening kept later in the year is the year's figure so far", (o["balance"], o["as_of"], o["how"]) == (-S(600), "2026-04-01", "sql_tb"), str(o))
T = books.trial_balance(con, EM, "2026-04-01", "2026-06-30")
by = {x["code"]: x for x in T["accounts"]}
check("so the trial balance from that day balances", T["balanced"] and follows(T)
      and (by["530-1000"]["opening_sen"], by["530-1000"]["closing_sen"]) == (-S(600), -S(1000)), str(T["notes"]))
T = books.trial_balance(con, EM, "2026-01-01", "2026-06-30")
check("and one from the year start too", T["balanced"], str(T["notes"]))

# SQL's GL ledger printed for one profit and loss account mid-year doesn't drop the year before from retained earnings.
EP = REV["EXP"]
ropens(EP, rbatch(EP, "trial_balance", "2026-01-01", "2026-01-31"), "2026-01-01", "sql_tb",
       [("310-1000", 10000), ("100-0000", -8000), ("150-0000", -1000), ("530-1000", -1500), ("900-E002", 500)], True)
jb = rbatch(EP, "journal", "2026-01-01", "2027-01-31")
rdoc(EP, jb, "PV2602-001", "2026-02-01", [("900-E002", 50, 0), ("310-1000", 0, 50)])
rdoc(EP, jb, "PV2605-001", "2026-05-01", [("900-E002", 100, 0), ("310-1000", 0, 100)])
con.commit()
before = books.trial_balance(con, EP, "2027-01-01", "2027-01-31")
ropens(EP, rbatch(EP, "gl_ledger", "2026-04-01", "2026-06-30"), "2026-04-01", "sql_ledger", [("900-E002", 50)], False)
con.commit()
T = books.trial_balance(con, EP, "2027-01-01", "2027-01-31")
re_open = lambda X: {x["code"]: x for x in X["accounts"]}["150-0000"]["opening_sen"]  # noqa: E731
check("a mid-year ledger of one profit and loss account leaves retained earnings as they were", before["balanced"] and T["balanced"]
      and re_open(before) == re_open(T) == -S(1850), str((re_open(before), re_open(T), T["notes"])))
check("and that account's balance in the year uses it", books.opening_at(con, EP, "900-E002", "2026-06-01")["balance"] == S(150))

# A customer's code counts from its control account's first opening, so a later opening of the control doesn't make it jump.
ES = REV["EXS"]
ropens(ES, rbatch(ES, "trial_balance", "2026-01-01", "2026-01-31"), "2026-01-01", "sql_tb",
       [("310-1000", 10000), ("100-0000", -8000), ("150-0000", -1000), ("300-0000", 1000), ("530-1000", -2000)], True)
jb = rbatch(ES, "journal", "2026-01-01", "2026-12-31")
rdoc(ES, jb, "IV2602-001", "2026-02-05", [("300-A0003", 800, 0), ("530-1000", 0, 800)])
rdoc(ES, jb, "OR2605-001", "2026-05-05", [("310-1000", 300, 0), ("300-A0003", 0, 300)])
ropens(ES, rbatch(ES, "trial_balance", "2026-04-01", "2026-04-30"), "2026-04-01", "sql_tb",
       [("310-1000", 10000), ("100-0000", -8000), ("150-0000", -3000), ("300-0000", 1800), ("530-1000", -800)], True)
con.commit()
T = books.trial_balance(con, ES, "2026-01-01", "2026-06-30")
by = {x["code"]: x for x in T["accounts"]}
check("a customer's code and its control account each follow on, with no false note", T["balanced"] and follows(T)
      and (by["300-A0003"]["opening_sen"], by["300-A0003"]["closing_sen"]) == (0, S(500))
      and (by["300-0000"]["opening_sen"], by["300-0000"]["closing_sen"]) == (S(1000), S(1000)), str(T["notes"]))
R = books.trial_balance(con, ES, "2026-01-01", "2026-06-30", rollup=True)
check("rolled up, they still add up to SQL's figure", R["balanced"] and {x["code"]: x for x in R["accounts"]}["300-0000"]["closing_sen"] == S(1500))
a = books.ledger_report(con, ES, "300-A0003", "2026-01-01", "2026-06-30")["accounts"][0]
check("and the customer's ledger closes at its running balance", a["closing_sen"] == a["rows"][-1]["balance_sen"] == S(500)
      and not any("later opening" in n for n in a["notes"]), str(a["notes"]))
T = books.trial_balance(con, ES, "2026-04-01", "2026-06-30")
by = {x["code"]: x for x in T["accounts"]}
check("from the control account's later opening, the customer's code still opens at its own lines", T["balanced"] and follows(T)
      and by["300-A0003"]["opening_sen"] == S(800) and by["300-0000"]["opening_sen"] == S(1000), str(T["notes"]))

# Books kept here: the documents entered here, and no SQL check.
eb = ledger.new_batch(con, EXN, origin="here", report="entered")
ledger.put_document(con, EXN, eb, {"doc_no": "JV-H1", "doc_date": "2026-01-10", "book": "general", "origin": "here",
                                   "lines": [{"code": "310-1000", "dr_sen": S(100), "cr_sen": 0}, {"code": "530-1000", "dr_sen": 0, "cr_sen": S(100)}]})
con.commit()
con.disarm()
con.close()
d = j("get", f"/api/books/trial-balance?entity={EXN}&from=2026-01-01&to=2026-01-31")
check("a company whose books are kept here isn't checked against SQL, and says why", d["check"]["outcome"] == "skipped"
      and "kept here, not in SQL" in d["check"]["text"] and "Fetch" not in d["check"]["text"], str(d["check"]))
d = j("get", f"/api/books/ledger?entity={EXN}&account=530-1000&from=2026-01-01&to=2026-01-31")
check("its ledger lines say they were entered here", [(r["doc_no"], r["origin"]) for r in d["accounts"][0]["rows"]] == [("JV-H1", "here")], str(d["accounts"]))

# A rolled-up control account opens a ledger that ends where the trial balance row does.
tb = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-01-01&to=2026-01-31&rollup=1")
row = {x["code"]: x for x in tb["accounts"]}["300-0000"]
d = j("get", f"/api/books/ledger?entity={EID}&account=300-0000&from=2026-01-01&to=2026-01-31")
check("the ledger of a control account is followed by the customers' codes the trial balance adds in",
      [x["code"] for x in d["accounts"]] == ["300-0000", *row["rolled"]] and d["accounts"][0]["subs"] == row["rolled"]
      and sum(x["closing_sen"] for x in d["accounts"]) == row["closing_sen"] == S(2100)
      and any("together they close at 2,100.00" in n for n in d["accounts"][0]["notes"]), str([x["notes"] for x in d["accounts"]]))
js = (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8")
check("the page offers a doc no.'s lines only for SQL's documents, and words books kept here apart",
      'r.origin === "sql" ? `<button type="button" class="linkish mono" data-bk-doc=' in js
      and "sqlCheckBanner(ent()?.uses_sql ? d.check : null)" in js and "The books kept here for this company" in js
      and "${ent()?.uses_sql ? \" Fetch SQL's reports on the SQL import page.\" : \"\"}" in js)

# SQL can carry a customer's movements on its control account and print the customer's own code at nil, as it did for
# Other Debtors on real books: 305-0000 opens at 1,760.00, the receipt from 305-W0001 is SQL's Period To Date on
# 305-0000, while the books here keep it on 305-W0001. With no chart account for the code and no customer record saying
# its control, the two are still compared together, as the '-0000' account of its family.
write("a company whose customer has no record", ("INSERT INTO entities (code, name, uses_sql, fy_start) VALUES ('EXG', 'Example Group Ltd', 1, 1)", ()))
EG = q("SELECT id FROM entities WHERE code = 'EXG'")[0]["id"]
write("its chart", *[("INSERT INTO gl_accounts (entity_id, code, name, type, sql_type) VALUES (?, ?, ?, ?, ?)", (EG, *a)) for a in (
    ("100-0000", "SHARE CAPITAL", "equity", None), ("150-0000", "RETAINED EARNING", "equity", "RE"),
    ("305-0000", "OTHER DEBTORS", "asset", None), ("310-1000", "BANK-EXAMPLE 0001", "asset", None))])
con = db.connect()
con.arm("user", "test: the group's books")
ropens(EG, rbatch(EG, "trial_balance", "2026-01-01", "2026-02-28"), "2026-01-01", "sql_tb",
       [("305-0000", 1760), ("310-1000", 8240), ("100-0000", -10000)], True)
gb = rbatch(EG, "journal", "2026-01-01", "2026-02-28")
rdoc(EG, gb, "OR2602-001", "2026-02-01", [("310-1000", 1760, 0), ("305-W0001", 0, 1760)])
con.commit()
con.disarm()
con.close()


def sql_tb(other_debtors_ytd):
    z = [0, 0]
    return {"period": ["2026-01-01", "2026-02-28"], "accounts": [
        {"code": "100-0000", "name": "SHARE CAPITAL", "open": [0, S(10000)], "ptd": z, "mtd": z, "ytd": [0, S(10000)]},
        {"code": "150-0000", "name": "RETAINED EARNING", "open": z, "ptd": z, "mtd": z, "ytd": z},
        {"code": "305-0000", "name": "OTHER DEBTORS", "open": [S(1760), 0], "ptd": [0, S(1760)], "mtd": z,
         "ytd": [S(other_debtors_ytd), 0]},
        {"code": "305-W0001", "name": "EXAMPLE CUSTOMER", "open": z, "ptd": z, "mtd": z, "ytd": z},
        {"code": "310-1000", "name": "BANK-EXAMPLE 0001", "open": [S(8240), 0], "ptd": [S(1760), 0], "mtd": [S(1760), 0], "ytd": [S(10000), 0]}]}


real_stored_tb = books._stored_tb
try:
    books._stored_tb = lambda con, eid, f, t: ({"file_name": "group.xlsx", "read_at": "2026-02-28T09:00:00"}, sql_tb(0))
    with db.connect() as con:
        ch = books.check_against_sql(con, EG, "2026-01-01", "2026-02-28")
    check("a customer's code with no record is compared within its family's control account, as SQL prints it",
          ch["outcome"] == "ok" and ch["differences"] == [], str(ch))
    books._stored_tb = lambda con, eid, f, t: ({"file_name": "group.xlsx", "read_at": "2026-02-28T09:00:00"}, sql_tb(50))
    with db.connect() as con:
        ch = books.check_against_sql(con, EG, "2026-01-01", "2026-02-28")
    check("and a real difference in that group is still named, on the control account with its customer's code",
          ch["outcome"] == "warn" and [(d["code"], d["what"], d["diff_sen"]) for d in ch["differences"]] == [("305-0000", "closing", -S(50))]
          and "305-W0001" in ch["differences"][0]["text"], str(ch["differences"]))
finally:
    books._stored_tb = real_stored_tb

print("All books checks passed.")
