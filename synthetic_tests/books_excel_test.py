"""The Books page's reports as Excel files, and the books pages and files of the audit pack, on made-up records only.

Each report of Accounting › Books (trial balance, general ledger, profit and loss, balance sheet, customers and
suppliers) downloads as an Excel file for the same period and options as on the screen: the workbook is opened again
here and every figure, total included, must equal the screen's JSON. The amounts are numbers to 2 decimals, the totals
figures (never formulas), the title block names the company, the period and "Mirrored from SQL Account, read <date>",
the heading row is frozen and the columns have widths. The audit pack for a month holds three short books pages (the
SQL books checklist item, the statutory payables check, the trial balance against SQL's), and the auditor package holds
the month's trial balance, profit and loss and balance sheet as Excel files, listed with their fingerprints on the
month report's Files sheet. Check this pack still verifies the pack. The SQL workbooks are built to the layout of the
real exports (as in books_test), with a made-up company, accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.books_excel_test
"""
import io
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-books-excel-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import auditpack, books, booksexcel, config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXN", "name": "Example Not In SQL Sdn Bhd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-444"}]},
]}), encoding="utf-8")

COMPANY = "EXAMPLE HOLDINGS SDN BHD (202601000001 (1234567-X))"
STAMP = "14/11/2026 1:25:48 AM\nADMIN"
passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
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



# ---------- the records: SQL's journal, ledger and trial balance fetched for EXH ----------
db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def fetch(eid):
    p = j("post", "/api/sql/preview", json={"entity_id": eid, "fetch": True})
    return j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


EID, EXN = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXH", "EXN"))
ACCT = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
CHART = [("100-0000", "SHARE CAPITAL", "equity", None, "CP"), ("150-0000", "RETAINED EARNING", "equity", None, "RE"),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA"), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank", "CA"),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL"), ("530-1000", "OTHER INCOME - RENTAL", "income", None, "OI"),
         ("900-E002", "ELECTRICITY", "expense", None, "EP"), ("9S0-T002", "SALARY - EXAMPLE", "expense", None, "EP")]
write("the chart of accounts and the bank's GL code",
      ("UPDATE accounts SET gl_code = '310-1000' WHERE id = ?", (ACCT,)),
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)", (EID, *a)) for a in CHART])
save("1.xlsx", JOT)
save("2.xlsx", L1)
save("3.xlsx", trial_balance(TB1, "01/12/2025", "31/01/2026"))
fetch(EID)
check("SQL's three reports are kept for the made-up company",
      {r["report"] for r in q("SELECT report FROM ledger_batches WHERE entity_id = ?", (EID,))} >= {"journal", "gl_ledger", "trial_balance"})
READ = f"Mirrored from SQL Account, read {date.today():%d/%m/%Y}"
BOOK_TABLES = ("ledger_docs", "ledger_lines", "ledger_openings", "ledger_batches", "gl_accounts")


def book_counts():
    return {t: q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in BOOK_TABLES}


START = book_counts()


# ---------- reading a workbook back ----------

def xlsx(path, name):
    """(workbook, its first sheet) of an export, after checking the download and its file name."""
    from openpyxl import load_workbook
    r = call("get", path)
    assert r.status_code == 200, (path, r.status_code, r.data[:500])
    assert r.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", r.mimetype
    got = r.headers["Content-Disposition"]
    assert f'filename="{name}"' in got or f"filename={name}" in got, (got, name)
    wb = load_workbook(io.BytesIO(r.data))
    return wb, wb.active


def cents(v):
    """A cell's amount back in sen (an empty cell is None)."""
    if v is None:
        return None
    assert isinstance(v, (int, float)) and not isinstance(v, bool), v
    return int(round(v * 100))


def rows(ws, top=5):
    return [list(r) for r in ws.iter_rows(min_row=top + 1, values_only=True)]


def plain(ws, what):
    """The title block, the frozen heading row, widths set, no formula anywhere and amounts with 2 decimals."""
    t1, t2, t3 = (ws.cell(row=i, column=1).value or "" for i in (1, 2, 3))
    formulas = [cell.coordinate for row in ws.iter_rows() for cell in row
                if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("="))]
    money_ok = all("0.00" in cell.number_format for row in ws.iter_rows(min_row=6) for cell in row
                   if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool))
    widths = all((ws.column_dimensions[k].width or 0) > 8 for k in ("A", "B", "C"))
    return (t1 == "Example Holdings Sdn Bhd (EXH)" and what in t2 and t3.startswith(READ) and ws.freeze_panes == "A6"
            and not formulas and money_ok and widths), (t1, t2, t3, ws.freeze_panes, formulas[:3])


Q = f"entity={EID}&from=2025-12-01&to=2026-01-31"
QX = f"entity_id={EID}&from=2025-12-01&to=2026-01-31"
TB_KEYS = ("opening_dr_sen", "opening_cr_sen", "dr_sen", "cr_sen", "closing_dr_sen", "closing_cr_sen")

# ---------- 1. the trial balance ----------
for rollup in (1, 0):
    tb = j("get", f"/api/books/trial-balance?{Q}&rollup={rollup}")
    wb, ws = xlsx(f"/api/export/books/trial-balance.xlsx?{QX}&rollup={rollup}", "EXH Trial balance to 31-01-2026.xlsx")
    ok, why = plain(ws, "Trial balance, 01/12/2025 to 31/01/2026")
    check(f"the trial balance file (rollup {rollup}) has the title block, a frozen heading and figures only", ok, why)
    resets = any(a["reset_sen"] for a in tb["accounts"])
    heads = [ws.cell(row=5, column=i).value for i in range(1, 12)]
    check(f"its headings are the screen's columns (rollup {rollup})",
          heads[:6] == ["Code", "Name", "Opening debit", "Opening credit", "Debit", "Credit"]
          and ("Year start (debit above 0)" in heads) == resets, heads)
    got = rows(ws)
    keys = TB_KEYS[:4] + (("reset_sen",) if resets else ()) + TB_KEYS[4:]
    body = got[:len(tb["accounts"])]
    same = all([r[0] or None, r[1]] == [a["code"], a["name"]] and [cents(v) for v in r[2:2 + len(keys)]] == [a[k] for k in keys]
               for r, a in zip(body, tb["accounts"]))
    check(f"every account's figures equal the screen's (rollup {rollup}, {len(tb['accounts'])} accounts)",
          same and len(body) == len(tb["accounts"]) > 3, (body, tb["accounts"]))
    total = got[len(tb["accounts"])]
    check(f"the totals row holds the screen's totals as figures (rollup {rollup})",
          total[0] == "Total" and [cents(v) for v in total[2:2 + len(keys)]] == [tb["totals"][k] for k in keys], (total, tb["totals"]))
    words = "\n".join(str(r[0]) for r in got if r[0])
    check(f"and says whether it balances and what the check against SQL's trial balance says (rollup {rollup})",
          ("Balances: the debits and credits are equal." in words) == bool(tb["balanced"]) and tb["balanced"]
          and f"Checked against SQL's trial balance: {tb['check']['text']}" in words, words[-800:])

# ---------- 2. the general ledger, every account and one ----------
for acct, name in ((None, "EXH General ledger to 31-01-2026.xlsx"), ("310-1000", "EXH General ledger 310-1000 to 31-01-2026.xlsx"),
                   ("300-0000", "EXH General ledger 300-0000 to 31-01-2026.xlsx")):
    gl = j("get", f"/api/books/ledger?{Q}" + (f"&account={acct}" if acct else ""))
    wb, ws = xlsx(f"/api/export/books/ledger.xlsx?{QX}" + (f"&account={acct}" if acct else ""), name)
    ok, why = plain(ws, "General ledger")
    check(f"the general ledger file ({acct or 'all accounts'}) has the title block, a frozen heading and figures only", ok, why)
    got = [r for r in rows(ws) if r[0] and r[0] in {a["code"] for a in gl["accounts"]}]
    expect = []
    for a in gl["accounts"]:
        expect.append((a["code"], None, None, None, None))
        expect.append((a["code"], gl["from"], None, None, a["opening_sen"]))
        expect += [(a["code"], x["date"], x["doc_no"], x["dr_sen"] or None, x["cr_sen"] or None, x["balance_sen"]) for x in a["rows"]]
        expect.append((a["code"], "total", a["dr_sen"], a["cr_sen"]))
        expect.append((a["code"], gl["to"], None, None, a["closing_sen"]))
    seen = []
    for r in got:
        if r[4] == "Total for the period":
            seen.append((r[0], "total", cents(r[5]), cents(r[6])))
        elif r[1] is None:
            seen.append((r[0], None, None, None, None))
        elif str(r[4]).startswith(("Opening balance", "Closing balance")):
            seen.append((r[0], r[1].date().isoformat(), None, None, cents(r[7])))
        else:
            seen.append((r[0], r[1].date().isoformat(), r[2], cents(r[5]), cents(r[6]), cents(r[7])))
    check(f"its openings, lines, running balances, totals and closings equal the screen's ({acct or 'all accounts'}, "
          f"{len(gl['accounts'])} accounts)", seen == expect and gl["accounts"], (seen[:12], expect[:12]))
r = call("get", f"/api/export/books/ledger.xlsx?{QX}&account={'A' * 300}")
got = r.headers.get("Content-Disposition", "")
check("a very long account code typed into the address is shortened in the file name, and the date stays",
      r.status_code == 200 and f"EXH General ledger {'A' * 40} to 31-01-2026.xlsx" in got, (r.status_code, got))


# ---------- 3. the profit and loss account and 4. the balance sheet ----------

def statement_rows(d):
    out = []
    for b in d["blocks"]:
        if b["kind"] == "section":
            out.append(("", b["title"], None))
            out += [((x["code"] or "") if x["kind"] == "account" else "", x["name"], x["amounts"]) for x in b["rows"]]
            out.append(("", b["total_label"], b["total"]))
        else:
            out.append(("", b["label"], b["amounts"]))
    return out


def sheet_rows(ws, n):
    """The statement's rows up to the first row with no account name: (code, name, amounts or None for a heading)."""
    got = []
    for r in rows(ws):
        if r[1] is None:
            break
        amts = r[2:2 + n]
        got.append((r[0] or "", r[1], None if all(v is None for v in amts) else [cents(v) for v in amts]))
    return got


for cols in ("total", "month"):
    pl = j("get", f"/api/books/profit-and-loss?{Q}&columns={cols}")
    wb, ws = xlsx(f"/api/export/books/profit-and-loss.xlsx?{QX}&columns={cols}", "EXH Profit and loss to 31-01-2026.xlsx")
    ok, why = plain(ws, "Profit and loss, 01/12/2025 to 31/01/2026")
    check(f"the profit and loss file ({cols}) has the title block, a frozen heading and figures only", ok, why)
    n = len(pl["columns"])
    check(f"its columns are the screen's ({cols}, {n})", [ws.cell(row=5, column=3 + i).value for i in range(n)]
          == [x["label"] + (" (comparative)" if x["role"] == "comparative" else "") for x in pl["columns"]])
    got = sheet_rows(ws, n)
    check(f"every section, account, total and the net profit equal the screen's ({cols})",
          got == statement_rows(pl) and any(b == "Net profit or loss after tax" for _, b, _ in got), (got, statement_rows(pl)))
    words = "\n".join(str(r[0]) for r in rows(ws) if r[0])
    check(f"and the check against the trial balance is said ({cols})", pl["check"]["text"] in words)

bs = j("get", f"/api/books/balance-sheet?entity={EID}&as_at=2026-01-31")
wb, ws = xlsx(f"/api/export/books/balance-sheet.xlsx?entity_id={EID}&as_at=2026-01-31", "EXH Balance sheet at 31-01-2026.xlsx")
ok, why = plain(ws, "Balance sheet at 31/01/2026")
check("the balance sheet file has the title block, a frozen heading and figures only", ok, why)
got = sheet_rows(ws, len(bs["columns"]))
check("every section, account and total, net assets and total equity, equal the screen's",
      got == statement_rows(bs) and any(b == "Total equity" for _, b, _ in got), (got, statement_rows(bs)))
check("and it balances, as the screen says", bs["balanced"] is True
      and next(c for _, b, c in got if b == "Net assets") == next(c for _, b, c in got if b == "Total equity"), bs["check"])

# ---------- 5. customers and suppliers ----------
from hrp.receivables import BUCKETS  # noqa: E402
for side, name in (("customers", "EXH Customers to 31-01-2026.xlsx"), ("suppliers", "EXH Suppliers to 31-01-2026.xlsx"),
                   ("", "EXH Customers and suppliers to 31-01-2026.xlsx")):
    pt = j("get", f"/api/books/parties?{Q}&side={side}")
    wb, ws = xlsx(f"/api/export/books/customers-and-suppliers.xlsx?{QX}&side={side}", name)
    ok, why = plain(ws, "to 31/01/2026 (ageing at 31/01/2026)")
    check(f"the {side or 'customers and suppliers'} file has the title block, a frozen heading and figures only", ok, why)
    keys = ("opening_sen", "invoiced_sen", "received_sen", "other_sen", "closing_sen")
    expect, seen = [], []
    for ctl in pt["controls"]:
        expect.append(("control", ctl["code"]))
        expect += [("row", x["code"], *[x[k] for k in keys],
                    *([None] * len(BUCKETS) if x["credit"] or not x["ageing"] else [x["ageing"][b] for b in BUCKETS])) for x in ctl["rows"]]
        expect.append(("total", *[ctl["totals"][k] for k in keys], *[ctl["totals"]["ageing"][b] for b in BUCKETS]))
        expect.append(("tb", ctl["code"], ctl["tb"]["opening_sen"], ctl["tb"]["closing_sen"]))
    for r in rows(ws):
        if r[0] == "Total":
            seen.append(("total", *[cents(v) for v in r[2:12]]))
        elif r[1] == "In the trial balance":
            seen.append(("tb", r[0], cents(r[2]), cents(r[6])))
        elif r[1] and str(r[1]).endswith(("(customers)", "(suppliers)")):
            seen.append(("control", r[0]))
        elif r[0] and r[1] is not None:
            seen.append(("row", r[0], *[cents(v) for v in r[2:12]]))
    check(f"each code's opening, invoiced, {'paid' if side == 'suppliers' else 'received'}, other, closing and ageing, the "
          f"totals and the control account in the trial balance equal the screen's ({side or 'both'})",
          seen == expect and pt["controls"], (seen, expect))

# ---------- the same dates and options as the screen, and refusals ----------
check("a report that doesn't exist is refused", call("get", f"/api/export/books/journal.xlsx?{QX}").status_code == 404)
r = call("get", f"/api/export/books/trial-balance.xlsx?entity_id={EID}&from=2026-31-01")
check("a date that can't be read is refused in words", r.status_code == 400 and "isn't a date" in r.get_json()["error"], r.data[:200])
r = call("get", f"/api/export/books/balance-sheet.xlsx?entity_id={EID}&as_at=bad")
check("so is an as-at date", r.status_code == 400 and "as-at date" in r.get_json()["error"], r.data[:200])
dflt = j("get", f"/api/books/trial-balance?entity={EID}")
wb, ws = xlsx(f"/api/export/books/trial-balance.xlsx?entity_id={EID}",
              f"EXH Trial balance to {date.fromisoformat(dflt['to']):%d-%m-%Y}.xlsx")
check("with no dates the file is for the screen's default dates", f"{date.fromisoformat(dflt['from']):%d/%m/%Y} to "
      f"{date.fromisoformat(dflt['to']):%d/%m/%Y}" in ws["A2"].value, ws["A2"].value)
reads = q("SELECT * FROM audit_row WHERE tbl = 'read' AND op = 'event' AND row_key = 'books export'")
check("each download is noted in the audit trail as a books export",
      len(reads) >= 10 and json.loads(reads[-1]["after"])["file"].endswith(".xlsx"), len(reads))
wb, ws = xlsx(f"/api/export/books/trial-balance.xlsx?entity_id={EXN}", f"EXN Trial balance to {date.today():%d-%m-%Y}.xlsx")
check("a company not kept in SQL says its books are kept here", ws["A3"].value.startswith("Books kept in this app"), ws["A3"].value)
check("the exports wrote nothing to the books", book_counts() == START)

# ---------- the audit pack's books pages ----------
r = call("post", "/api/audit-pack", json={"entity_id": EID, "month": "2026-01"})
check("the audit pack for January builds", r.status_code == 200, r.data[:300])
pname = r.get_json()["name"]
from pypdf import PdfReader  # noqa: E402
reader = PdfReader(config.PACKS_DIR / "EXH" / pname)
titles = [o.title for o in reader.outline if not isinstance(o, list)]
pages = [" ".join(pg.extract_text().split()) for pg in reader.pages]
text = " ".join(pages)
con = db.connect()
try:
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
    chk = auditpack.books_checks(con, ent, "2026-01")
    direct = books.check_against_sql(con, EID, "2025-12-01", "2026-01-31")
finally:
    con.close()
check("it holds the SQL books check, the statutory payables check and the trial balance against SQL after the bank reconciliation",
      titles[1:5] == ["Bank reconciliation", *auditpack.BOOKS_PAGES], titles)
first = next(i for i, p in enumerate(pages) if "- SQL books check" in p)
check("each on a short page of its own", all(f"Example Holdings Sdn Bhd - January 2026 - {t}" in pages[first + i]
                                             for i, t in enumerate(auditpack.BOOKS_PAGES)), pages[first:first + 3])
check("the trial balance page says what the check against SQL's trial balance as at 31/01/2026 says",
      chk["trial_balance"]["outcome"] == direct["outcome"] == "ok" and " ".join(direct["text"].split()) in pages[first + 2]
      and "Agrees with SQL's trial balance." in pages[first + 2], (chk["trial_balance"], direct["text"]))
check("the SQL books page says what the checklist item says",
      chk["sql_books"]["state"] in ("done", "not_done") and " ".join(chk["sql_books"]["text"].split())[:80] in pages[first], chk["sql_books"])
check("the statutory page says nothing is confirmed yet", "No statutory accounts are confirmed for this company yet" in pages[first + 1])
check("building the pack wrote nothing to the books", book_counts() == START)
ev = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
pc = j("get", f"/api/audit-pack/check?event={ev['id']}")
check("Check this pack verifies the pack with its books pages", pc["file"]["state"] == "unchanged" and pc["changes"]["total"] == 0, pc["changes"])
write("an account renamed in the chart", ("UPDATE gl_accounts SET name = 'ELECTRICITY AND WATER' WHERE entity_id = ? AND code = '900-E002'", (EID,)))
pc = j("get", f"/api/audit-pack/check?event={ev['id']}")
books_group = next((g for g in pc["changes"]["groups"] if g["key"] == "books"), None)
check("and an account renamed in the chart since is a change to what its books pages read",
      books_group and books_group["count"] == 1 and pc["file"]["state"] == "unchanged", pc["changes"])
write("the name put back", ("UPDATE gl_accounts SET name = 'ELECTRICITY' WHERE entity_id = ? AND code = '900-E002'", (EID,)))

# ---------- the auditor package's books files ----------
r = call("post", "/api/auditor-export", json={"entity_id": EID, "month": "2026-01"})
check("the auditor package for January builds", r.status_code == 200, r.data[:300])
from openpyxl import load_workbook  # noqa: E402
want = ["Books/EXH Trial balance to 31-01-2026.xlsx", "Books/EXH Profit and loss to 31-01-2026.xlsx",
        "Books/EXH Balance sheet at 31-01-2026.xlsx"]
with zipfile.ZipFile(config.EXPORTS_DIR / "EXH" / r.get_json()["name"]) as z:
    names = z.namelist()
    blobs = {n: z.read(n) for n in want if n in names}
    report = load_workbook(io.BytesIO(z.read("EXH 2026-01 month report.xlsx")))
check("it holds the month's trial balance, profit and loss and balance sheet as Excel files", all(n in blobs for n in want), names)
listed = {(x[1] or "") + (x[0] or "").split("/")[-1]: x[4] for x in report["Files"].iter_rows(min_row=2, values_only=True)}
check("each listed on the Files sheet with its fingerprint",
      all(listed.get(n) == hashlib.sha256(blobs[n]).hexdigest() for n in want), listed)
tbm = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-01-01&to=2026-01-31&rollup=1")
ws = load_workbook(io.BytesIO(blobs[want[0]])).active
got = rows(ws)
check("the trial balance in it is January's, as the screen shows it",
      all([cents(v) for v in x[2:8]] == [a[k] for k in TB_KEYS] for x, a in zip(got, tbm["accounts"]))
      and [cents(v) for v in got[len(tbm["accounts"])][2:8]] == [tbm["totals"][k] for k in TB_KEYS]
      and "01/01/2026 to 31/01/2026" in ws["A2"].value, got)
plj = j("get", f"/api/books/profit-and-loss?entity={EID}&to=2026-01-31")
ws = load_workbook(io.BytesIO(blobs[want[1]])).active
check("the profit and loss in it is the financial year to January's end", sheet_rows(ws, len(plj["columns"])) == statement_rows(plj)
      and "01/01/2026 to 31/01/2026" in ws["A2"].value, ws["A2"].value)
bsj = j("get", f"/api/books/balance-sheet?entity={EID}&as_at=2026-01-31")
ws = load_workbook(io.BytesIO(blobs[want[2]])).active
check("the balance sheet in it is at January's end", sheet_rows(ws, len(bsj["columns"])) == statement_rows(bsj))

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
