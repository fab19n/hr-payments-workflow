"""SQL Account's three general-ledger reports read from their Excel exports, on made-up records only.

The GL Journal of Transaction carries the account lines of every document, in sections by book (Bank Journal,
General Journal Journal, Sales Journal), each closed by its own total; the GL Ledger (Level 1, or V2 with the balance
one column wider) gives each account's balance brought forward, its rows and its closing balance, then a footer for the
control accounts; the Trial Balance gives each account's opening, period, month and year figures. hrp/sqlgl.py reads
each, places every figure by the heading its merged cell overlaps, keeps amounts as whole sen, and refuses a report that
doesn't add up to its own totals. hrp/sqlreport.read tells the three apart from the listings. The workbooks here are
built to the layout of the real exports, with made-up companies, accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.gl_reports_test
"""
import io
import os
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-gl-reports-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, sqlgl, sqlreport  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

COMPANY = "EXAMPLE HOLDINGS SDN BHD (202601000001 (1234567-X))"
STAMP = "14/11/2026 1:25:48 AM\nADMIN"


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


# ---------- a workbook as SQL Account writes it ----------

def letter(c):
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def workbook(cells, merges):
    """An .xlsx from {(row, column letter): value}, with the WindowWidth attribute SQL Account writes. A str is a shared
    string, a date a number in a dd/mm/yyyy style, a float one in the money style."""
    strings, rows = [], {}
    for (r, col), v in sorted(cells.items(), key=lambda kv: (kv[0][0], len(kv[0][1]), kv[0][1])):
        if isinstance(v, str):
            if v not in strings:
                strings.append(v)
            cell = f'<c r="{col}{r}" s="0" t="s"><v>{strings.index(v)}</v></c>'
        elif isinstance(v, datetime):
            serial = (v - datetime(1899, 12, 30)).total_seconds() / 86400
            cell = f'<c r="{col}{r}" s="3"><v>{serial!r}</v></c>'
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
    """Cells and merges of one sheet, put by row (from 1) and column (from 0), as the layouts are written down."""
    def __init__(self):
        self.cells, self.merges, self.r = {}, [], 0

    def put(self, r, c, v, to=None):
        self.cells[(r, letter(c))] = v
        if to is not None and to != c:
            self.merges.append(f"{letter(c)}{r}:{letter(to)}{r}")

    def row(self, *cells):
        """The next row: cells as (column, value) or (column, last column, value)."""
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
    """A figure as the ledger and trial balance print it: a string with commas, a credit balance in brackets."""
    return f"({-x:,.2f})" if x < 0 else f"{x:,.2f}"


def refusal(fn, data):
    try:
        fn(data)
    except sqlreport.ReportError as ex:
        return str(ex)
    return None


def read(data):
    return sqlreport.read(data)


# ---------- the GL Journal of Transaction ----------

def jot(sections, period=("01/10/2026", "30/11/2026"), break_after=None, date_after_break=False, totals=None, grand=None):
    """A GL Journal of Transaction. sections: [(label, [(doc no, dd/mm/yyyy, [(code, name, description, dr, cr)], print date?)])].
    break_after: a page break after that many lines; date_after_break: the first line after it prints its date.
    totals: {label: (dr, cr)} printed instead of the true totals; grand: a grand total row (dr, cr)."""
    s = Sheet()
    pages = 2 if break_after is not None else 1
    if period:
        s.row((0, "Date"), (1, ":"), (2, 3, f"From {period[0]} to {period[1]}"), (7, STAMP))
    else:
        s.row((7, STAMP))
    s.row((0, "Sort By"), (1, ":"), (2, 3, "PostDate;Ref1"))
    s.row((0, 5, COMPANY), (7, 8, f"Page 1 of {pages}"))
    heading = ((0, 1, "Doc Date"), (2, "A/C Code"), (3, "A/C Description"), (4, "Ref 1"), (5, 6, "Description"), (7, "Debit (MYR)"), (8, "Credit (MYR)"))
    s.row(*heading)
    n = 0
    for label, docs in sections:
        s.row((0, 6, label))
        dr_total = cr_total = 0.0
        for no, day, lines, show_date in docs:
            for k, (code, name, desc, dr, cr) in enumerate(lines):
                if break_after is not None and n == break_after:
                    s.row((7, STAMP))
                    s.row((0, 5, COMPANY), (7, 8, "Page 2 of 2"))
                    s.row(*heading)
                    s.row((0, 6, label), (7, 8, "...Continued"))
                cells = [(2, code), (3, name), (4, no), (5, 6, desc)]
                if (k == 0 and show_date) or (break_after is not None and n == break_after and date_after_break):
                    cells.append((0, 1, day))
                if dr:
                    cells.append((7, float(dr)))
                if cr:
                    cells.append((8, float(cr)))
                s.row(*cells)
                dr_total += dr
                cr_total += cr
                n += 1
        said = (totals or {}).get(label, (round(dr_total, 2), round(cr_total, 2)))
        s.row((0, 6, "Total  (MYR) :"), (7, float(said[0])), (8, float(said[1])))
    if grand:
        s.row((0, 6, "Grand Total (MYR) :"), (7, float(grand[0])), (8, float(grand[1])))
    return s.bytes()


BANK = ("310-1000", "BANK-EXAMPLE 0001")
PV3 = ("PV2610-003", "03/10/2026", [("400-S0001", "EXAMPLE PRINT SDN BHD", "Payment For Account", 360.0, 0), (*BANK, "EXAMPLE PRINT SDN BHD", 0, 360.0)], True)
PV4 = ("PV2610-004", "05/10/2026", [("900-E002", "ELECTRICITY", "EXAMPLE POWER - SEP", 100.0, 0), ("900-E002", "ELECTRICITY", "EXAMPLE POWER - OCT", 50.25, 0),
                                    (*BANK, "EXAMPLE POWER", 0, 150.25)], True)
PV5 = ("PV2610-005", "05/10/2026", [("900-T001", "TELEPHONE", "EXAMPLE TELECOM", 99.9, 0), (*BANK, "EXAMPLE TELECOM", 0, 99.9)], False)   # date not printed
OR1 = ("OR2610-001", "08/10/2026", [(*BANK, "EXAMPLE TENANT", 500.0, 0), ("300-A0003", "EXAMPLE TENANT", "Rent Oct", 0, 500.0)], True)
JV1 = ("JV2610-01", "20/10/2026", [("9S0-T002", "SALARY - EXAMPLE", "Salary Oct", 5500.0, 0), (*BANK, "Salary Oct", 0, 5500.0)], True)
JV2 = (1001.0, "21/10/2026", [("150-0000", "RETAINED EARNING", "Adjustment", 10.0, 0), ("9S0-T002", "SALARY - EXAMPLE", "Adjustment", 0, 10.0)], True)
IV1 = ("EXH/2026/10/001", "15/10/2026", [("300-A0003", "EXAMPLE TENANT", "Rent Oct", 440.0, 0), ("530-1000", "OTHER INCOME - RENTAL", "Rent Oct", 0, 440.0)], True)
PI1 = ("PI-0001", "16/10/2026", [("900-E002", "ELECTRICITY", "Bill", 99.0, 0), ("400-S0001", "EXAMPLE PRINT SDN BHD", "Bill", 0, 99.0)], True)
SECTIONS = [("Bank Journal", [PV3, PV4, PV5, OR1]), ("General Journal Journal", [JV1, JV2]), ("Sales Journal", [IV1]), ("Purchase Journal", [PI1])]

data = jot(SECTIONS, break_after=5)
rows, spans = sqlreport.read_xlsx(data)
check("the Journal of Transaction is told apart by its headings, though it prints no title", sqlgl.detect(rows, spans) == "journal")
kind, rep = read(data)
check("read() gives it as a journal with its company and printed period",
      (kind, rep["title"], rep["company"], rep["period"], rep["period_source"])
      == ("journal", "GL Journal of Transaction", COMPANY, ["2026-10-01", "2026-11-30"], "printed"), str({k: rep[k] for k in ("title", "company", "period", "period_source")}))
check("each section with its book and its totals in sen; an unseen Purchase Journal is the purchase book",
      rep["sections"] == [
          {"label": "Bank Journal", "book": "bank", "dr_sen": 111015, "cr_sen": 111015, "docs": 4, "lines": 9},
          {"label": "General Journal Journal", "book": "general", "dr_sen": 551000, "cr_sen": 551000, "docs": 2, "lines": 4},
          {"label": "Sales Journal", "book": "sales", "dr_sen": 44000, "cr_sen": 44000, "docs": 1, "lines": 2},
          {"label": "Purchase Journal", "book": "purchase", "dr_sen": 9900, "cr_sen": 9900, "docs": 1, "lines": 2}], str(rep["sections"]))
docs = {d["doc_no"]: d for d in rep["docs"]}
check("every document is read once, across the page break, with the ...Continued line taken for no document",
      [d["doc_no"] for d in rep["docs"]] == ["PV2610-003", "PV2610-004", "PV2610-005", "OR2610-001", "JV2610-01", "1001", "EXH/2026/10/001", "PI-0001"],
      str([d["doc_no"] for d in rep["docs"]]))
check("a date not printed after the page break carries down from the line above", docs["PV2610-005"]["date"] == "2026-10-05" and docs["OR2610-001"]["date"] == "2026-10-08",
      str(docs["PV2610-005"]))
check("the same account twice in one document is two lines, in printed order",
      [(x["seq"], x["code"], x["dr_sen"], x["cr_sen"], x["description"]) for x in docs["PV2610-004"]["lines"]]
      == [(1, "900-E002", 10000, 0, "EXAMPLE POWER - SEP"), (2, "900-E002", 5025, 0, "EXAMPLE POWER - OCT"), (3, "310-1000", 0, 15025, "EXAMPLE POWER")],
      str(docs["PV2610-004"]["lines"]))
check("a document carries its book, the section as printed, its first line's description and its totals",
      {k: docs["JV2610-01"][k] for k in ("book", "book_label", "description", "dr_sen", "cr_sen", "date")}
      == {"book": "general", "book_label": "General Journal Journal", "description": "Salary Oct", "dr_sen": 550000, "cr_sen": 550000, "date": "2026-10-20"})
check("a doc no. read as a number loses its .0, and the names of the accounts are kept",
      "1001" in docs and docs["PV2610-003"]["lines"][0]["name"] == "EXAMPLE PRINT SDN BHD" and docs["PV2610-003"]["lines"][1]["code"] == "310-1000")
check("amounts are whole sen", all(isinstance(x["dr_sen"], int) and isinstance(x["cr_sen"], int) for d in rep["docs"] for x in d["lines"]))

fp = docs["PV2610-004"]["fingerprint"]
check("the fingerprint leaves out the order and the descriptions, and changes with an amount or the date",
      fp == sqlgl.fingerprint("2026-10-05", [{"code": "310-1000", "dr_sen": 0, "cr_sen": 15025}, {"account_code": "900-e002 ", "dr_sen": 5025, "cr_sen": 0},
                                              {"code": "900-E002", "dr_sen": 10000, "cr_sen": 0}])
      and fp != sqlgl.fingerprint("2026-10-05", [{"code": "310-1000", "dr_sen": 0, "cr_sen": 15026}, {"code": "900-E002", "dr_sen": 5026, "cr_sen": 0},
                                                 {"code": "900-E002", "dr_sen": 10000, "cr_sen": 0}])
      and fp != sqlgl.fingerprint("2026-10-06", docs["PV2610-004"]["lines"]) and len(fp) == 64)
check("sen and rm", (sqlgl.sen(1234.565 - 0.005), sqlgl.sen(0.1 + 0.2), sqlgl.sen(None), sqlgl.rm(12345)) == (123456, 30, 0, 123.45))

inside = read(jot(SECTIONS, break_after=3))[1]
check("a page break inside a document: the line after it, with no date, is the same document",
      [d["doc_no"] for d in inside["docs"]] == [d["doc_no"] for d in rep["docs"]] and len({d["doc_no"]: d for d in inside["docs"]}["PV2610-004"]["lines"]) == 3)
dated = read(jot(SECTIONS, break_after=5, date_after_break=True))[1]
check("a line that prints its date after the page break reads the same", dated["docs"] == rep["docs"])
check("a grand total that agrees is accepted", len(read(jot(SECTIONS, grand=(7159.15, 7159.15)))[1]["docs"]) == 8)

no_period = read(jot(SECTIONS, period=None))[1]
check("without a printed period, the period is the first and last line dates and says it came from the lines",
      (no_period["period"], no_period["period_source"]) == (["2026-10-03", "2026-10-21"], "lines"), str((no_period["period"], no_period["period_source"])))

J = sqlreport.ReportError
cases = [
    ("a section whose lines don't add up to its total", jot(SECTIONS, totals={"Sales Journal": (440.0, 444.0)}), "Sales Journal says its total is 440.00 debit and 444.00 credit"),
    ("a document whose debit and credit differ",
     jot([("Bank Journal", [("PV2610-009", "06/10/2026", [("900-E002", "ELECTRICITY", "Bill", 100.0, 0), (*BANK, "Bill", 0, 90.0)], True),
                            ("PV2610-010", "06/10/2026", [("900-E002", "ELECTRICITY", "Bill", 0, 0), (*BANK, "Bill", 10.0, 0)], True)])]),
     "PV2610-009 with 100.00 debit and 90.00 credit"),
    ("a doc no. in two sections", jot([("Bank Journal", [PV3]), ("General Journal Journal", [("pv2610-003", "03/10/2026", JV1[2], True)])]),
     "has pv2610-003 in both its Bank Journal and its General Journal Journal"),
    ("a line with both a debit and a credit",
     jot([("General Journal Journal", [("JV2610-09", "20/10/2026", [("9S0-T002", "SALARY", "x", 5.0, 5.0), (*BANK, "x", 0, 0)], True)])]),
     "JV2610-09 on row 6 with both a debit and a credit"),
    ("a line dated outside the printed period", jot([("Bank Journal", [PV3, ("PV2612-001", "01/12/2026", PV3[2], True)])]), "PV2612-001 is dated 2026-12-01"),
    ("a section that starts with a line with no date", jot([("Bank Journal", [PV5])]), "starts with a line of PV2610-005 that has no date"),
    ("a document with two dates", jot([("Bank Journal", [PV3, ("PV2610-003", "04/10/2026", PV3[2], True)])]), "PV2610-003 with lines dated 2026-10-03 and 2026-10-04"),
    ("a grand total that doesn't agree", jot(SECTIONS, grand=(7159.15, 7000.0)), "grand total is 7,159.15 debit and 7,000.00 credit"),
]
for name, made, said in cases:
    why = refusal(read, made)
    check(f"refused whole: {name}", said in (why or ""), str(why))
cut = jot([("Bank Journal", [PV3])])
rows, spans = sqlreport.read_xlsx(cut)
last = max(i for i, r in enumerate(rows) if any(x is not None for x in r))
check("refused whole: a section with no Total row", "Bank Journal has no Total row" in (refusal(lambda d: sqlgl.journal(rows[:last], spans), cut) or ""))
check("a line with no Ref 1 is refused",
      "with no Ref 1" in (refusal(read, jot([("Bank Journal", [("", "03/10/2026", PV3[2], True)])])) or ""))
check("chosen by hand, the journal is named and sent to Fetch",
      refusal(sqlreport.parse, data) == "This is SQL's GL Journal of Transaction: save it in the exports folder and use Fetch from SQL exports.", str(refusal(sqlreport.parse, data)))


# ---------- the GL Ledger ----------

def gl_ledger(accounts, v2=False, break_in=None, repeat_code=False, footer=True, closing=None):
    """A GL Local - Ledger - Detail (Level 1, or V2 with the balance one column wider). accounts: [(code, name, bf,
    [(date, ref, desc1, desc2, dr, cr)], virtual?)] with the running balance worked out. break_in: a page break after
    that account's first row. closing: {code: closing printed instead of the true one}."""
    end = 33 if v2 else 32
    s = Sheet()

    def page(n, pages):
        s.row((0, end, "GL Local - Ledger - Detail"))
        s.row((0, end, "From 01/10/2026 To 30/11/2026"))
        s.row((0, 5, COMPANY), (6, end, f"Page {n} of {pages}"))
        s.row((0, "Date"), (2, "Ref. 1/2"), (3, "Description 1"), (4, "Description 2"), (5, "Tax"), (6, 13, "Debit (MYR)"), (14, 21, "Credit (MYR)"), (22, end, "Bal. (MYR)"))

    page(1, 2 if break_in else 1)
    all_dr = all_cr = 0.0
    for code, name, bf, lines in accounts:
        s.row((0, end, f"Code : {code}  {name}"))
        s.row((3, "Balance B/F"), (27, end, money(bf)))
        bal, dr_t, cr_t = bf, 0.0, 0.0
        for k, (day, ref, d1, d2, dr, cr) in enumerate(lines):
            bal = round(bal + dr - cr, 2)
            dr_t, cr_t = dr_t + dr, cr_t + cr
            cells = [(0, day), (3, d1), (25 if not ref else 27, end, money(bal))]
            if ref:
                cells += [(2, ref), (4, d2)]
            if dr:
                cells.append((8 if not ref else 9, 13, money(dr)))
            if cr:
                cells.append((16, 21, money(cr)))
            s.row(*cells)
            if code == break_in and k == 0:
                page(2, 2)
                if repeat_code:
                    s.row((0, end, f"Code : {code}  {name}"))
        s.row((6, 13, money(dr_t)), (14, 21, money(cr_t)), (22, end, money((closing or {}).get(code, bal))))
        all_dr, all_cr = all_dr + dr_t, all_cr + cr_t
    if footer:
        s.row((3, 5, "Total"), (6, 13, money(all_dr)), (14, 21, money(all_cr)), (22, end, money(-11410.24)))
        s.row((3, 5, "* Reconciliation for Debit"))
        s.row((3, 5, "Less Retained Earning"), (6, 13, money(60757.75)))
        s.row((3, 5, "Add Code : 300-0000  TRADE DEBTORS"), (6, 13, money(31000.0)), (14, 21, money(31000.0)))
        s.row((3, 5, "Add Code : 400-0000  TRADE CREDITORS"), (6, 13, money(1974.84)))
        s.row((3, 5, "Total Debit balance with T..."), (7, 13, money(490805.46)), (14, 21, money(490805.46)))
    return s.bytes()


ACCOUNTS = [
    ("150-0000", "RETAINED EARNING", 49104.29, [("30/11/2026", None, "PROFIT/(LOSS)", None, 60757.75, 0)]),
    ("310-1000", "BANK-EXAMPLE 0001", -100.0, [("03/10/2026", "PV2610-003\n9900897945", "EXAMPLE PRINT SDN BHD", "Payment For Account", 0, 360.0),
                                               ("08/10/2026", "OR2610-001", "EXAMPLE TENANT", "Rent Oct", 500.0, 0),
                                               ("20/10/2026", "JV2610-01", "Salary Oct", "Salary Oct", 0, 5500.0)]),
    ("9S0-T002", "SALARY - EXAMPLE", 49500.0, [("26/10/2026", "PV2610-034\n9900897945", "EXAMPLE - SALARY", "EXAMPLE - SALARY", 5500.0, 0)]),
    ("920-0000", "NOTHING THIS PERIOD", 0.0, []),
]
led_data = gl_ledger(ACCOUNTS, break_in="310-1000")
check("the ledger is told apart by its Code rows and Balance B/F", sqlgl.detect(*sqlreport.read_xlsx(led_data)) == "gl_ledger")
kind, led = read(led_data)
check("read() gives it as the GL Ledger with its company and period",
      (kind, led["title"], led["company"], led["period"]) == ("gl_ledger", "GL Ledger", COMPANY, ["2026-10-01", "2026-11-30"]), str((kind, led["company"], led["period"])))
acc = {a["code"]: a for a in led["accounts"]}
check("every account is read once, with its name", [a["code"] for a in led["accounts"]] == ["150-0000", "310-1000", "9S0-T002", "920-0000"]
      and acc["9S0-T002"]["name"] == "SALARY - EXAMPLE", str([a["code"] for a in led["accounts"]]))
check("a balance brought forward in brackets is a credit", acc["310-1000"]["bf_sen"] == -10000 and acc["150-0000"]["bf_sen"] == 4910429)
check("the PROFIT/(LOSS) row, with no Ref, is kept apart as virtual",
      acc["150-0000"]["rows"] == [] and [(v["date"], v["description"], v["dr_sen"], v["bal_sen"]) for v in acc["150-0000"]["virtual"]]
      == [("2026-11-30", "PROFIT/(LOSS)", 6075775, 10986204)] and acc["150-0000"]["closing_sen"] == 10986204, str(acc["150-0000"]))
check("the rows of an account are read across the page break, the Ref split into doc no. and cheque no.",
      [(x["date"], x["doc_no"], x["cheque_no"], x["dr_sen"], x["cr_sen"], x["bal_sen"]) for x in acc["310-1000"]["rows"]]
      == [("2026-10-03", "PV2610-003", "9900897945", 0, 36000, -46000), ("2026-10-08", "OR2610-001", "", 50000, 0, 4000),
          ("2026-10-20", "JV2610-01", "", 0, 550000, -546000)]
      and (acc["310-1000"]["dr_sen"], acc["310-1000"]["cr_sen"], acc["310-1000"]["closing_sen"]) == (50000, 586000, -546000), str(acc["310-1000"]))
check("descriptions 1 and 2 are kept", (acc["9S0-T002"]["rows"][0]["description"], acc["9S0-T002"]["rows"][0]["description2"]) == ("EXAMPLE - SALARY", "EXAMPLE - SALARY"))
check("an account with no rows still has its balance and a totals row of nothing",
      (acc["920-0000"]["bf_sen"], acc["920-0000"]["rows"], acc["920-0000"]["dr_sen"], acc["920-0000"]["cr_sen"], acc["920-0000"]["closing_sen"]) == (0, [], 0, 0, 0))
check("the footer: Less Retained Earning, and each Add Code with one or two amounts",
      [(f["side"], f["op"], f["code"], f["name"], f["dr_sen"], f["cr_sen"], f["amount_sen"]) for f in led["footer"]] == [
          ("debit", "less", None, "Retained Earning", 6075775, None, 6075775),
          ("debit", "add", "300-0000", "TRADE DEBTORS", 3100000, 3100000, 0),
          ("debit", "add", "400-0000", "TRADE CREDITORS", 197484, None, 197484),
          ("debit", "total", None, "Total Debit balance with T...", 49080546, 49080546, 0)], str(led["footer"]))
check("the grand total row is kept", led["total"] == {"dr_sen": 6675775, "cr_sen": 586000, "bal_sen": -1141024}, str(led["total"]))
v2 = read(gl_ledger(ACCOUNTS, v2=True, break_in="310-1000"))[1]
check("the V2 layout, its balance one column wider, reads the same", v2["accounts"] == led["accounts"] and v2["footer"] == led["footer"])
again = read(gl_ledger(ACCOUNTS, break_in="310-1000", repeat_code=True))[1]
check("an account whose Code row is printed again on the next page is still one account", again["accounts"] == led["accounts"])
check("a ledger without its footer is still read", len(read(gl_ledger(ACCOUNTS, footer=False))[1]["accounts"]) == 4)
why = refusal(read, gl_ledger(ACCOUNTS, closing={"9S0-T002": 54000.0}))
check("refused whole: an account whose balance brought forward and rows don't come to its closing balance",
      "account 9S0-T002 brings forward 49,500.00 and moves 5,500.00, but closes at 54,000.00" in (why or ""), str(why))
broken = gl_ledger(ACCOUNTS)
broken_rows, broken_spans = sqlreport.read_xlsx(broken)
at = next(i for i, r in enumerate(broken_rows) if "PV2610-034\n9900897945" in r)
broken_rows[at][9] = "5,000.00"   # the row no longer adds up to the account's totals row
why = refusal(lambda d: sqlgl.gl_ledger(broken_rows, broken_spans), broken)
check("refused whole: an account whose rows don't add up to its totals row", "account 9S0-T002 says its total is 5,500.00 debit" in (why or ""), str(why))
check("chosen by hand, the ledger is sent to Fetch", "This is SQL's GL Ledger:" in (refusal(sqlreport.parse, led_data) or ""))


# ---------- the Trial Balance ----------

def trial_balance(accounts, break_after=None, grand=None):
    """A GL Trial Balance - This Month vs This Year with Opening. accounts: [(code, name, open, ptd, mtd, ytd)], each
    figure (dr, cr), blank when 0. grand: the Grand Total printed instead of the true one."""
    s = Sheet()
    starts = {"open": (8, 12, 14, 18), "ptd": (20, 24, 28, 32), "mtd": (35, 39, 41, 42), "ytd": (45, 49, 52, 55)}   # a figure starts inside its column

    def page(n, pages, first):
        if first:
            s.row((0, "Date"), (1, ":"), (2, 5, "From 01/10/2026 to 14/11/2026"), (43, "14/11/2026 1:33:31 AM ADMIN"))
            s.row((0, "Sort By"), (1, ":"), (2, 5, "Code;Description"))
            s.row((0, "Project"), (1, ":"), (2, 5, "All"))
        s.row((5, 25, "EXAMPLE HOLDINGS SDN BHD"), (26, 37, "(202601000001 (1234567-X))"))
        s.row((0, 55, "GL Trial Balance As At 14/11/2026"))
        s.row((43, 55, f"Page {n} of {pages}"))
        s.row((0, "Acc Code"), (3, "Description"), (6, "Opening Balance"), (19, "Period To Date"), (33, "Month To Date"), (43, "Year To Date"))
        s.row((6, 12, "Debit"), (13, 18, "Credit"), (19, 24, "Debit"), (25, 32, "Credit"), (33, 39, "Debit"), (40, 42, "Credit"), (43, 49, "Debit"), (50, 55, "Credit"))

    def figures(vals):
        cells = []
        for g, (dr, cr) in zip(("open", "ptd", "mtd", "ytd"), vals):
            a, b, c, d = starts[g]
            if dr:
                cells.append((a, b, money(dr)))
            if cr:
                cells.append((c, d, money(cr)))
        return cells

    page(1, 2 if break_after else 1, True)
    totals = [[0.0, 0.0] for _ in range(4)]
    for n, (code, name, *vals) in enumerate(accounts):
        if break_after and n == break_after:
            page(2, 2, False)
        s.row((0, 3, code), (4, 5, name), *figures(vals))
        for t, (dr, cr) in zip(totals, vals):
            t[0], t[1] = round(t[0] + dr, 2), round(t[1] + cr, 2)
    s.row((0, 5, "Grand Total Amount (MYR)"), *figures(grand or totals))
    return s.bytes()


TB = [
    ("100-0000", "SHARE CAPITAL", (0, 200332.28), (115727.99, 0), (0, 0), (0, 84604.29)),
    ("150-0000", "RETAINED EARNING", (120832.28, 0), (0, 71727.99), (0, 0), (49104.29, 0)),
    ("310-1000", "BANK-EXAMPLE 0001", (30000.0, 0), (0, 0), (0, 5500.0), (30000.0, 0)),
    ("920-0000", "NOTHING THIS YEAR", (0, 0), (0, 0), (0, 0), (0, 0)),
    ("9S0-T002", "SALARY - EXAMPLE", (49500.0, 0), (0, 44000.0), (5500.0, 0), (5500.0, 0)),
]
tb_data = trial_balance(TB, break_after=3)
check("the trial balance is told apart by its four headings", sqlgl.detect(*sqlreport.read_xlsx(tb_data)) == "trial_balance")
kind, tb = read(tb_data)
check("read() gives it with the company name and registration no. joined, and the period to its as-at date",
      (kind, tb["title"], tb["company"], tb["period"]) == ("trial_balance", "Trial Balance", COMPANY, ["2026-10-01", "2026-11-14"]), str((kind, tb["company"], tb["period"])))
by = {a["code"]: a for a in tb["accounts"]}
check("every account across the page break, its figures placed by the column they overlap, in sen",
      [a["code"] for a in tb["accounts"]] == ["100-0000", "150-0000", "310-1000", "920-0000", "9S0-T002"]
      and {k: by["150-0000"][k] for k in ("name", "open", "ptd", "mtd", "ytd")}
      == {"name": "RETAINED EARNING", "open": [12083228, 0], "ptd": [0, 7172799], "mtd": [0, 0], "ytd": [4910429, 0]}
      and (by["9S0-T002"]["open"], by["9S0-T002"]["ptd"], by["9S0-T002"]["mtd"], by["9S0-T002"]["ytd"]) == ([4950000, 0], [0, 4400000], [550000, 0], [550000, 0])
      and by["310-1000"]["mtd"] == [0, 550000], str(tb["accounts"]))
check("an account with no figures (Show Zero Balance) is read with zeros",
      {k: by["920-0000"][k] for k in ("open", "ptd", "mtd", "ytd")} == {"open": [0, 0], "ptd": [0, 0], "mtd": [0, 0], "ytd": [0, 0]})
check("the grand total is kept", tb["grand"] == {"open": [20033228, 20033228], "ptd": [11572799, 11572799], "mtd": [550000, 550000], "ytd": [8460429, 8460429]},
      str(tb["grand"]))
bad_grand = trial_balance(TB, grand=[(200332.28, 200332.28), (115727.99, 115727.99), (5500.0, 5500.0), (84604.29, 84000.0)])
why = refusal(read, bad_grand)
check("refused whole: a column that doesn't add up to the Grand Total", "Year To Date accounts add up to 84,604.29 debit and 84,604.29 credit, but its Grand Total says 84,604.29 and 84,000.00" in (why or ""), str(why))
lopsided = [*TB[:4], ("9S0-T002", "SALARY - EXAMPLE", (49500.0, 0), (0, 44000.0), (5500.0, 0), (5500.0, 0)), ("999-0000", "SUSPENSE", (0, 0), (0, 0), (1.0, 0), (0, 0))]
why = refusal(read, trial_balance(lopsided))
check("refused whole: a Grand Total whose debit and credit differ", "Month To Date grand total is 5,501.00 debit and 5,500.00 credit, which don't balance" in (why or ""), str(why))
broken_tb = [*TB[:4], ("9S0-T002", "SALARY - EXAMPLE", (49500.0, 0), (0, 44000.0), (5500.0, 0), (5400.0, 0)), ("100-0001", "ROUNDING", (0, 0), (0, 0), (0, 0), (100.0, 0))]
why = refusal(read, trial_balance(broken_tb))
check("refused whole: an account whose opening and period to date don't come to its year to date",
      "account 9S0-T002 opens at 49,500.00 and moves -44,000.00 in the period, but its Year To Date is 5,400.00" in (why or ""), str(why))
check("chosen by hand, the trial balance is sent to Fetch", "This is SQL's Trial Balance:" in (refusal(sqlreport.parse, tb_data) or ""))


# ---------- read() tells the reports and the listings apart ----------

def listing(docs):
    """A Payment Voucher Listing as SQL Account prints it. docs: (doc no, date, description, amount)."""
    s = Sheet()
    s.put(2, 6, "Payment Voucher Listing", 11); s.put(2, 0, "Date"); s.put(2, 5, "From 01/10/2026 to 31/10/2026")
    s.put(3, 6, "As At 31/10/2026", 9)
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


pv = listing([("PV2610-001", date(2026, 10, 5), "EXAMPLE POWER - SEP 26", 250.0), ("PV2610-002", date(2026, 10, 6), "EXAMPLE TELECOM", 99.9)])
got = read(pv)
check("a listing is read as before, and named a listing", got[0] == "listing" and got[1] == sqlreport.parse(pv)
      and [(e["doc_no"], e["amount"]) for e in got[1]["entries"]] == [("PV2610-001", 250.0), ("PV2610-002", 99.9)], str(got))
check("a listing is no general-ledger report", sqlgl.detect(*sqlreport.read_xlsx(pv)) is None)
plain = workbook({(1, "A"): "Doc No", (1, "B"): "Amount", (2, "A"): "PV2610-009", (2, "B"): 12.5}, [])
check("a plain table, or a file that isn't a workbook, is nothing to read()", read(plain) is None and read(b"not a zip") is None and read(b"PK broken") is None)
print("\nAll GL report checks passed.")
