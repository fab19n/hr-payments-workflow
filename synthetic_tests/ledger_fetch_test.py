"""One click fetches SQL's listings and its general-ledger reports together, on made-up records only.

Fetch from SQL exports reads every workbook in the folder: the listings as before, and SQL's GL Journal of
Transaction, GL Ledger (Level 1) and Trial Balance. The preview says what keeping the account lines would do (new,
changed, unchanged, no longer in SQL) and which journals start counting in the bank reconciliation, without writing
anything. Import keeps each report as a stored SQL export, every journal document with its lines (with versions), and
the ledger and trial balance checks against those lines. The SQL page then shows each entry's lines and checks, and the
latest checks against SQL's reports. The workbooks here are built to the layout of the real exports, with a made-up
company, accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.ledger_fetch_test
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-ledger-fetch-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, recon  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
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
    for sql, args in statements:
        con.execute(sql, args)
    con.commit()
    con.close()


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
ACCT = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("150-0000", "RETAINED EARNING", "equity", None),
         ("300-0000", "TRADE DEBTORS", "asset", "debtor_control"), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("400-0000", "TRADE CREDITORS", "liability", "creditor_control"), ("530-1000", "OTHER INCOME - RENTAL", "income", None),
         ("900-E002", "ELECTRICITY", "expense", None), ("900-T001", "TELEPHONE", "expense", None), ("9S0-T002", "SALARY - EXAMPLE", "expense", None)]
write("the chart of accounts and the bank's GL code",
      ("UPDATE accounts SET gl_code = '310-1000' WHERE id = ?", (ACCT,)),
      *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, *a)) for a in CHART],
      ("UPDATE gl_accounts SET sql_type = 'RE' WHERE entity_id = ? AND code = '150-0000'", (EID,)))


# ---------- a workbook as SQL Account writes it (as in gl_reports_test) ----------

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


def jot(sections, period=("01/11/2026", "30/11/2026")):
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


def gl_ledger(accounts, footer):
    """A GL Local - Ledger - Detail, Level 1, for November. accounts: [(code, name, bf, [(date, ref or None, desc, dr, cr)])].
    footer: [(label, dr or None, cr or None)]."""
    s, end = Sheet(), 32
    s.row((0, end, "GL Local - Ledger - Detail"))
    s.row((0, end, "From 01/11/2026 To 30/11/2026"))
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


def trial_balance(accounts, period_from, as_at="14/11/2026"):
    """A GL Trial Balance - This Month vs This Year with Opening. accounts: [(code, name, open, ptd, mtd, ytd)], each (dr, cr)."""
    s = Sheet()
    starts = {"open": (8, 12, 14, 18), "ptd": (20, 24, 28, 32), "mtd": (35, 39, 41, 42), "ytd": (45, 49, 52, 55)}

    def figures(vals):
        cells = []
        for g, (dr, cr) in zip(("open", "ptd", "mtd", "ytd"), vals):
            a, b, c_, d = starts[g]
            cells += ([(a, b, money(dr))] if dr else []) + ([(c_, d, money(cr))] if cr else [])
        return cells

    s.row((0, "Date"), (1, ":"), (2, 5, f"From {period_from} to {as_at}"), (43, "14/11/2026 1:33:31 AM ADMIN"))
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


def pv_listing(docs):
    """A Payment Voucher Listing for November. docs: (doc no, date, description, amount)."""
    s = Sheet()
    s.put(2, 6, "Payment Voucher Listing", 11); s.put(2, 0, "Date"); s.put(2, 5, "From 01/11/2026 to 30/11/2026")
    s.put(3, 6, "As At 30/11/2026", 9)
    s.put(6, 0, COMPANY, 8); s.put(6, 15, "Page 1 of 1", 16)
    s.put(7, 0, "Doc Date"); s.put(7, 2, "Doc No/Chq No", 3); s.put(7, 6, "Description"); s.put(7, 10, "Cash/ Bank Code", 11); s.put(7, 15, "Amount (MYR)", 16)
    r = 8
    for no, day, desc, amount in docs:
        s.put(r, 0, day, 1); s.put(r, 2, no, 3); s.put(r, 4, desc, 9); s.put(r, 10, "310-1000"); s.put(r, 15, float(amount), 16)
        r += 1
    s.put(r, 0, " Summary ")
    s.put(r + 1, 1, "Total Records  : "); s.put(r + 1, 3, float(len(docs)))
    s.put(r + 1, 10, "Grand Total   (MYR)"); s.put(r + 1, 15, float(round(sum(d[3] for d in docs), 2)))
    return s.bytes()


def jv_listing(docs):
    """A Journal Voucher Listing for November. docs: (doc no, date, description, debit, credit)."""
    s = Sheet()
    s.put(2, 0, "Date"); s.put(2, 1, "Doc No."); s.put(2, 4, "All"); s.put(2, 5, "From 01/11/2026 to 30/11/2026")
    s.put(2, 6, "Journal Voucher Listing", 10); s.put(2, 14, datetime(2026, 11, 13, 21, 17), 15); s.put(2, 16, "ADMIN")
    s.put(3, 0, "Currency"); s.put(3, 6, "As At 30/11/2026", 9)
    s.put(4, 0, "Sort By"); s.put(4, 2, "PostDate;DocNo;CurrencyCode", 5)
    s.put(5, 0, COMPANY, 8); s.put(5, 15, "Page 1 of 1", 16)
    s.put(6, 0, "Date"); s.put(6, 1, "Doc No"); s.put(6, 4, "Description"); s.put(6, 12, "Debit (MYR)", 13); s.put(6, 15, "Credit (MYR)", 16)
    r = 7
    for no, day, desc, debit, credit in docs:
        s.put(r, 0, day); s.put(r, 1, no, 2); s.put(r, 4, desc, 11); s.put(r, 12, float(debit), 13); s.put(r, 15, float(credit), 16)
        r += 1
    r += 1
    s.put(r, 0, "Summary"); s.put(r, 9, "Grand Total   (MYR)", 11)
    s.put(r, 12, float(round(sum(d[3] for d in docs), 2)), 13); s.put(r, 15, float(round(sum(d[4] for d in docs), 2)), 16)
    s.put(r + 1, 1, "Total Records  :", 2); s.put(r + 1, 3, float(len(docs)))
    return s.bytes()


def save(name, data, age):
    """A file in the downloads folder, saved `age` minutes ago."""
    p = FOLDER / name
    p.write_bytes(data)
    t = datetime(2026, 11, 14, 12, 0).timestamp() - age * 60
    os.utime(p, (t, t))


def counts():
    return {t: q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in ("ledger_batches", "ledger_docs", "ledger_lines", "documents", "sql_imports", "sql_entries")}


# ---------- November: listings, the journal, the ledger and a trial balance ----------

BANK = ("310-1000", "BANK-EXAMPLE 0001")
PV1 = ("PV2611-001", "05/11/2026", [("400-S0001", "EXAMPLE PRINT SDN BHD", "Payment For Account", 360.0, 0), (*BANK, "EXAMPLE PRINT SDN BHD", 0, 360.0)])
OR1 = ("OR2611-001", "08/11/2026", [(*BANK, "EXAMPLE TENANT", 500.0, 0), ("300-A0003", "EXAMPLE TENANT", "Rent Nov", 0, 500.0)])
JV1 = ("JV2611-01", "20/11/2026", [("9S0-T002", "SALARY - EXAMPLE", "Salary Nov", 5500.0, 0), (*BANK, "Salary Nov", 0, 5500.0)])
JV2 = ("JV2611-02", "21/11/2026", [("900-E002", "ELECTRICITY", "Reclass", 10.0, 0), ("900-T001", "TELEPHONE", "Reclass", 0, 10.0)])
JV2B = ("JV2611-02", "21/11/2026", [("900-E002", "ELECTRICITY", "Reclass", 12.0, 0), ("900-T001", "TELEPHONE", "Reclass", 0, 12.0)])
IV1 = ("IV2611-001", "10/11/2026", [("300-A0003", "EXAMPLE TENANT", "Rent Nov", 440.0, 0), ("530-1000", "OTHER INCOME - RENTAL", "Rent Nov", 0, 440.0)])

save("1.xlsx", pv_listing([("PV2611-001", date(2026, 11, 5), "EXAMPLE PRINT SDN BHD", 360.0)]), 60)
save("2.xlsx", jv_listing([("JV2611-01", date(2026, 11, 20), "Salary Nov", 5500.0, 5500.0), ("JV2611-02", date(2026, 11, 21), "Reclass", 10.0, 10.0),
                           ("JV2611-03", date(2026, 11, 25), "Accrual", 75.0, 75.0)]), 55)
save("3.xlsx", jot([("Bank Journal", [PV1, OR1]), ("General Journal Journal", [JV1, JV2]), ("Sales Journal", [IV1])]), 50)
save("4.xlsx", gl_ledger([
    ("100-0000", "SHARE CAPITAL", -9000.0, []),
    ("150-0000", "RETAINED EARNING", 49104.29, [("30/11/2026", None, "PROFIT/(LOSS)", 5070.0, 0)]),
    ("310-1000", "BANK-EXAMPLE 0001", 10000.0, [("05/11/2026", "PV2611-001\n9900897945", "EXAMPLE PRINT SDN BHD", 0, 360.0),
                                                ("08/11/2026", "OR2611-001", "EXAMPLE TENANT", 500.0, 0),
                                                ("20/11/2026", "JV2611-01", "Salary Nov", 0, 5500.0)]),
    ("530-1000", "OTHER INCOME - RENTAL", 0.0, [("10/11/2026", "IV2611-001", "Rent Nov", 0, 440.0)]),
    ("900-E002", "ELECTRICITY", 0.0, [("21/11/2026", "JV2611-02", "Reclass", 10.0, 0)]),
    ("900-T001", "TELEPHONE", 0.0, [("21/11/2026", "JV2611-02", "Reclass", 0, 10.0)]),
    ("9S0-T002", "SALARY - EXAMPLE", 0.0, [("20/11/2026", "JV2611-01", "Salary Nov", 5500.0, 0)]),
], [("Less Retained Earning", 5070.0, None), ("Add Code : 300-0000  TRADE DEBTORS", 440.0, 500.0), ("Add Code : 400-0000  TRADE CREDITORS", 360.0, None)]), 45)
# Dated 14/11 while the journal runs to 30/11: only the lines up to 14/11 are its month to date. The period starts in
# October, so November is not the first month of the financial year and profit and loss accounts are compared too.
TB_A = [("100-0000", "SHARE CAPITAL", (0, 9000.0), (0, 0), (0, 0), (0, 9000.0)),
        ("300-0000", "TRADE DEBTORS", (0, 0), (440.0, 500.0), (440.0, 500.0), (0, 60.0)),
        ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (500.0, 360.0), (500.0, 360.0), (10140.0, 0)),
        ("400-0000", "TRADE CREDITORS", (0, 1000.0), (360.0, 0), (360.0, 0), (0, 640.0)),
        ("530-1000", "OTHER INCOME - RENTAL", (0, 0), (0, 440.0), (0, 440.0), (0, 440.0))]
save("5.xlsx", trial_balance(TB_A, "01/10/2026"), 40)

# A signed-off November: the journal moving the bank is reported as changing it.
write("a signed-off bank statement for November",
      ("INSERT INTO statements (account_id, month, opening, closing, imported_at, reconciled_at, reconciled_how) VALUES (?, '2026-11', 0, 0, ?, ?, 'manual')",
       (ACCT, db.now(), db.now())))

before = counts()
p = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
f = {x["name"]: x for x in p["fetch"]["files"]}
check("the fetch reads the listings and the three general-ledger reports",
      all(f[n]["status"] == "read" for n in ("1.xlsx", "2.xlsx", "3.xlsx", "4.xlsx", "5.xlsx"))
      and [f[n].get("report") for n in ("3.xlsx", "4.xlsx", "5.xlsx")] == ["journal", "gl_ledger", "trial_balance"], str(p["fetch"]["files"]))
check("the journal's file entry has its documents and lines, the others their accounts",
      (f["3.xlsx"]["docs"], f["3.xlsx"]["lines"], f["4.xlsx"]["accounts"], f["5.xlsx"]["accounts"]) == (5, 10, 7, 5), str(f["3.xlsx"]))
check("the listings' new entries are still offered", p["fetch"]["new"] == 4 and len(p["records"]) == 4, str(p["fetch"]))
L = p["ledger"]
check("the preview counts the journal's documents as new", L["refused"] is None and L["totals"] == {"docs": 5, "lines": 10, "new": 5, "changed": 0, "same": 0, "back": 0, "gone": 0},
      str(L["totals"]))
check("the ledger and trial balance are checked on import", [x["kind"] for x in L["files"]] == ["journal", "gl_ledger", "trial_balance"]
      and L["files"][1]["note"].startswith("Checked"), str(L["files"]))
cnt = L["counting"]
check("the preview names the journal that will count in the bank reconciliation, and its signed-off month",
      cnt["bank_code"] == "310-1000" and [(x["doc_no"], x["amount"], x["listed"], x["signed_off"]) for x in cnt["journals"]] == [("JV2611-01", -5500.0, True, True)]
      and cnt["signed_off"] == ["2026-11"], str(cnt))
check("the preview writes nothing", counts() == before, str((before, counts())))

res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
check("Import keeps the listing entries and the reports' lines", res["added"] == 4 and len(res["ledger"]["files"]) == 3, str(res))
kept = {x["kind"]: x for x in res["ledger"]["files"]}
check("the journal's documents are all new", {k: kept["journal"]["summary"][k] for k in ("docs", "lines", "new", "changed", "same", "gone")}
      == {"docs": 5, "lines": 10, "new": 5, "changed": 0, "same": 0, "gone": 0}, str(kept["journal"]["summary"]))
check("the ledger agrees with the lines, footer and PROFIT/(LOSS) included", kept["gl_ledger"]["problems"] == 0, str(kept["gl_ledger"]["results"]))
tb_res = kept["trial_balance"]["results"]
check("the trial balance dated 14/11 agrees with the lines up to 14/11, with the journal running to 30/11",
      kept["trial_balance"]["problems"] == 0 and any(r["rule"] == "tb_mtd" and r["outcome"] == "ok" for r in tb_res)
      and not any(r["rule"] == "tb_mtd" and r["outcome"] == "skipped" for r in tb_res), str(tb_res))
check("the balance-sheet balances agree with the ledger kept in the same fetch",
      any(r["rule"] == "tb_balance" and r["outcome"] == "ok" for r in tb_res)
      and not any(r["rule"] == "tb_year_close" for r in tb_res), str(tb_res))  # these made-up books have no year-end move to note
check("the bank reconciliation change of signed-off November is reported", [x["month"] for x in res["ledger"]["recon_changed"]] == ["2026-11"],
      str(res["ledger"]["recon_changed"]))
check("each report is kept as a stored SQL export, with its batch",
      q("SELECT COUNT(*) AS n FROM ledger_batches b JOIN documents d ON d.id = b.document_id WHERE b.entity_id = ? AND d.doc_type = 'sqlexport' "
        "AND b.report IN ('journal', 'gl_ledger', 'trial_balance')", (EID,))[0]["n"] == 3)
logs = [r["what"] for r in q("SELECT what FROM activity ORDER BY id")]
jl = next((m for m in logs if m.startswith("Read GL Journal of Transaction '3.xlsx'")), "")
check("the activity log has a line per report, naming the signed-off month",
      "5 documents (5 new, 0 changed, 0 unchanged, 0 no longer in SQL), 10 lines" in jl and "signed-off 2026-11" in jl
      and any(m.startswith("Read Trial Balance '5.xlsx'") and "trial balance check: 0 differences" in m for m in logs), jl)

with db.connect() as con:
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
    mv = recon.movements(con, ent, recon.cash_book_account(con, EID), "2026-11")
check("the fetched journal counts in the bank reconciliation", any(i["ref"] == "JV2611-01" and i["amount"] == -5500.0 for i in mv["items"]), str(mv["items"]))

d = j("get", f"/api/sql/entries?entity={EID}")
by_no = {x["doc_no"]: x for x in d["unlinked"] + d["documents"]}
lines = {int(k): v for k, v in d["lines"].items()}
pv = lines.get(by_no["PV2611-001"]["id"])
check("the entries show the payment's lines, balanced and agreeing with the listing", pv and pv["n"] == 2 and pv["balanced"] and pv["total_ok"] is True
      and pv["version"] == 1 and pv["unknown"] == [], str(pv))
check("a journal's lines agree with its listing total", lines.get(by_no["JV2611-01"]["id"], {}).get("total_ok") is True, str(lines))
check("a listing journal the journal of transaction lacks shows no lines", lines.get(by_no["JV2611-03"]["id"]) == {"n": 0}, str(lines))
orph = d["ledger"]["orphans"]
check("the documents with no listing and the listing entry missing from the journal are named",
      sorted(x["doc_no"] for x in orph["no_listing"]) == ["IV2611-001", "OR2611-001"] and [x["doc_no"] for x in orph["not_in_journal"]] == ["JV2611-03"], str(orph))
reads = d["ledger"]["reads"]
check("the latest read of each report is given with its results", set(reads) == {"journal", "gl_ledger", "trial_balance"}
      and reads["gl_ledger"]["problems"] == 0 and reads["journal"]["summary"]["new"] == 5, str(reads.keys()))
imp_lines = {i["filename"]: i["lines"] for i in d["imports"]}
check("the imported file counts its lines", max(imp_lines.values()) == 10, str(imp_lines))

doc = j("get", f"/api/ledger/doc?entity={EID}&doc_no=pv2611-001")
v = doc["versions"][0]
check("one document's lines: codes, names from the chart or as printed, debits and credits",
      [(x["code"], x["name_from"], x["dr"], x["cr"]) for x in v["lines"]] == [("400-S0001", "printed", 360.0, 0.0), ("310-1000", "chart", 0.0, 360.0)]
      and v["lines"][0]["control"] == "400-0000" and v["totals"] == {"dr": 360.0, "cr": 360.0} and v["batch"]["report"] == "journal"
      and doc["checks"] == [] and doc["bank_codes"] == ["310-1000"], str(doc))
check("a document SQL's journal never gave is refused plainly", "hasn't given the lines" in j("get", f"/api/ledger/doc?entity={EID}&doc_no=JV2611-03", 404)["error"])

# ---------- a second fetch: SQL's reports only, one document changed and one deleted in SQL ----------

save("6.xlsx", jot([("Bank Journal", [OR1]), ("General Journal Journal", [JV1, JV2B]), ("Sales Journal", [IV1])]), 20)
# The first month of a financial year: Month To Date holds SQL's closing of last year's profit and loss (1,000.00 of
# rental income, 1,000.00 of electricity), while Year To Date started again and equals the lines.
TB_B = [("100-0000", "SHARE CAPITAL", (0, 9000.0), (0, 0), (0, 0), (0, 9000.0)),
        ("300-0000", "TRADE DEBTORS", (0, 0), (440.0, 500.0), (440.0, 500.0), (0, 60.0)),
        ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (500.0, 0), (500.0, 0), (10500.0, 0)),
        ("400-0000", "TRADE CREDITORS", (0, 1000.0), (0, 0), (0, 0), (0, 1000.0)),
        ("530-1000", "OTHER INCOME - RENTAL", (0, 1000.0), (1000.0, 440.0), (1000.0, 440.0), (0, 440.0)),
        ("900-E002", "ELECTRICITY", (1000.0, 0), (0, 1000.0), (0, 1000.0), (0, 0))]
save("7.xlsx", trial_balance(TB_B, "01/11/2026"), 15)
before = counts()
p2 = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
f2 = {x["name"]: x for x in p2["fetch"]["files"]}
check("the reports read before are imported before", all(f2[n]["status"] == "imported_before" for n in ("1.xlsx", "2.xlsx", "3.xlsx", "4.xlsx", "5.xlsx")), str(f2))
check("a reports-only fetch has no entries, only account lines", p2["records"] == [] and p2["header_row"] == -1 and p2["ledger"]["totals"]
      == {"docs": 4, "lines": 8, "new": 0, "changed": 1, "same": 3, "back": 0, "gone": 1}, str(p2.get("ledger")))
check("the preview names the document no longer in SQL", [x["doc_no"] for x in p2["ledger"]["gone"]] == ["PV2611-001"], str(p2["ledger"]["gone"]))
check("the reports-only preview writes nothing", counts() == before)
res2 = j("post", "/api/sql/apply", json={"token": p2["token"], "header_row": p2["header_row"], "mapping": p2["mapping"], "links": {}})
s2 = next(x for x in res2["ledger"]["files"] if x["kind"] == "journal")["summary"]
check("Import keeps the change as a new version and marks the deleted document", res2["added"] == 0
      and (s2["changed"], s2["same"], s2["gone"], s2["gone_docs"]) == (1, 3, 1, ["PV2611-001"]), str(s2))
check("the reports-only import holds no entries and no listing file",
      q("SELECT entries, document_id FROM sql_imports ORDER BY id DESC LIMIT 1")[0] == {"entries": 0, "document_id": None})
name2 = q("SELECT filename FROM sql_imports ORDER BY id DESC LIMIT 1")[0]["filename"]
check("and is named after the reports it read, not after a table of entries never made",
      name2.startswith("SQL reports fetched") and "6.xlsx" in name2 and "7.xlsx" in name2 and ".csv" not in name2, name2)
doc2 = j("get", f"/api/ledger/doc?entity={EID}&doc_no=JV2611-02")
check("the changed document has two versions, the old lines kept",
      [(x["version"], x["state"], x["totals"]["dr"]) for x in doc2["versions"]] == [(2, "current", 12.0), (1, "superseded", 10.0)], str(doc2["versions"]))
gone = j("get", f"/api/ledger/doc?entity={EID}&doc_no=PV2611-001")
check("the deleted document is kept, marked no longer in SQL", gone["versions"][0]["state"] == "gone"
      and any("no longer in SQL" in x for x in gone["checks"]), str(gone["checks"]))
tb2 = next(x for x in res2["ledger"]["files"] if x["kind"] == "trial_balance")["results"]
check("a first-month trial balance leaves profit and loss out of Month To Date",
      any(r["rule"] == "tb_mtd" and r["outcome"] == "skipped" and "year-end closing" in r["text"] for r in tb2)
      and not any(r["rule"] == "tb_mtd" and r["subject"] == "530-1000" for r in tb2), str(tb2))
check("its balances are checked against the ledger read again from its stored file",
      [r["subject"] for r in tb2 if r["rule"] == "tb_balance" and r["outcome"] == "warn"] == ["310-1000"], str(tb2))
d2 = j("get", f"/api/sql/entries?entity={EID}")
l2 = {int(k): v for k, v in d2["lines"].items()}
by2 = {x["doc_no"]: x for x in d2["unlinked"] + d2["documents"]}
check("the entries show the changed and the deleted document", l2[by2["JV2611-02"]["id"]]["version"] == 2 and l2[by2["PV2611-001"]["id"]]["state"] == "gone",
      str(l2))
check("the listing entry of the deleted document is named as missing from the journal",
      sorted(x["doc_no"] for x in d2["ledger"]["orphans"]["not_in_journal"]) == ["JV2611-03", "PV2611-001"], str(d2["ledger"]["orphans"]))
nij = {x["doc_no"]: x for x in d2["ledger"]["orphans"]["not_in_journal"]}
check("only the unlinked voucher among them can be ignored there, not the journal",
      nij["PV2611-001"]["can_ignore"] is True and nij["JV2611-03"]["can_ignore"] is False, str(nij))
e2 = j("post", f"/api/sql/entries/{nij['JV2611-03']['ids'][0]}", 400, json={"status": "ignored"})
check("and ignoring the journal is refused in words", "can't be ignored" in e2["error"], str(e2))

# ---------- a company not kept in SQL ----------

save("8.xlsx", jot([("General Journal Journal", [("JV2612-01", "02/12/2026", JV1[2])])], period=("01/12/2026", "31/12/2026")), 5)
write("the company stops using SQL", ("UPDATE entities SET uses_sql = 0 WHERE id = ?", (EID,)))
before = counts()
p3 = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
check("the preview says the lines can't be kept", p3["ledger"]["refused"] == ledger.NOT_SQL, str(p3.get("ledger")))
e3 = j("post", "/api/sql/apply", 400, json={"token": p3["token"], "header_row": p3["header_row"], "mapping": p3["mapping"], "links": {}})
check("Import is refused with a plain sentence, and nothing is kept", e3["error"] == ledger.NOT_SQL and counts() == before, str(e3))
write("the company uses SQL again", ("UPDATE entities SET uses_sql = 1 WHERE id = ?", (EID,)))
p4 = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
check("the refused file is read again by the next fetch", {x["name"]: x["status"] for x in p4["fetch"]["files"]}["8.xlsx"] == "read")

print("All ledger fetch checks passed.")
