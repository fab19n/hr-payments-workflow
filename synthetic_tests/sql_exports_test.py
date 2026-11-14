"""Listings exported from SQL Account as Excel files, and the one click that fetches them, on made-up records only.

SQL Account on SQL Connect hands data out only as files the person exports (print button > Export to Microsoft Excel
Workbook). That file is the printed page on a sheet: title rows, headings merged differently from the figures under
them, a document on one to three rows, a Summary with the report's count and grand total; and openpyxl refuses the
workbook (a WindowWidth attribute). hrp/sqlreport.py reads it from the file's XML parts; hrp/sqlfetch.py reads every
workbook in a folder by what it holds (exports are saved as 1.xlsx), keeps this company's listings, and puts their
documents together, each once, new or already imported. The workbooks here are built to the layout of a real export,
with made-up companies, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.sql_exports_test
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

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-exports-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, sqlfetch, sqlimport, sqlreport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # the folder setting is saved here, never in the program's own file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "SMP", "name": "Sample Trading Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
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


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


EXH = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
SMP = q("SELECT id FROM entities WHERE code = 'SMP'")[0]["id"]
EXH_LINE, SMP_LINE = "EXAMPLE HOLDINGS LTD (202601000001 (1234567-X))", "SAMPLE TRADING LTD (202601000002 (7654321-Y))"


# ---------- a workbook as SQL Account writes it ----------

def workbook(cells, merges, sql_quirk=True):
    """An .xlsx from {(row, column letter): value}. A str is a shared string, a date a number in a dd/mm/yyyy style, a
    datetime one in a date-and-time style, a float one in the money style. With sql_quirk, the workbook view carries
    the WindowWidth attribute SQL Account writes."""
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
    view = '<workbookView xWindow="480" yWindow="105" WindowWidth="21075" WindowHeight="12585"/>' if sql_quirk else '<workbookView/>'
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                               '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {ns}><bookViews>{view}</bookViews>'
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


def listing(docs, title="Payment Voucher Listing", company=EXH_LINE, period=("01/10/2026", "31/10/2026"), page_after=None,
            say_count=None, say_total=None, summary=True):
    """An exported listing laid out as SQL Account prints it. docs: (doc no, date, [description lines], cheque no, amount).
    page_after: the page furniture is printed again after that many documents."""
    cells, merges = {}, []

    def put(r, col, v, to=None):
        cells[(r, col)] = v
        if to:
            merges.append(f"{col}{r}:{to}{r}")

    def furniture(r, page, pages):
        put(r, "G", title, "L"); put(r, "O", datetime(2026, 11, 13, 19, 53), "P"); put(r, "Q", "ADMIN")
        put(r + 1, "G", f"As At {period[1]}", "J")
        if page == 1:  # the report's own heading, printed once: what was asked for
            put(r, "A", "Date"); put(r, "B", "Doc No."); put(r, "C", ":"); put(r, "D", ":"); put(r, "E", "All")
            put(r, "F", f"From {period[0]} to {period[1]}")
            put(r + 1, "A", "Currency"); put(r + 1, "B", "Incl Cancelled"); put(r + 1, "C", ":"); put(r + 1, "D", ":"); put(r + 1, "E", "No")
            put(r + 1, "F", "----")
            put(r + 2, "A", "Sort By"); put(r + 2, "B", ":"); put(r + 2, "C", "PostDate;DocNo;CurrencyCode", "F")
        put(r + 4, "A", company, "I"); put(r + 4, "P", f"Page {page} of {pages}", "Q")
        put(r + 5, "A", "Doc Date"); put(r + 5, "C", "Doc No/Chq No", "D"); put(r + 5, "G", "Description")
        put(r + 5, "K", "Cash/ Bank Code", "L"); put(r + 5, "P", "Amount (MYR)", "Q")
        return r + 6

    pages = 2 if page_after else 1
    r = furniture(2, 1, pages)
    for n, (no, day, lines, cheque, amount) in enumerate(docs):
        if page_after and n == page_after:
            r = furniture(r + 1, 2, pages)
        put(r, "A", day, "B"); put(r, "C", no, "D"); put(r, "E", lines[0], "J"); put(r, "K", "310-1000"); put(r, "M", "BANK-EXAMPLE 0001 0002 0003", "O")
        put(r, "P", float(amount), "Q")
        r += 1
        for k in range(max(len(lines) - 1, 1 if cheque else 0)):
            if k == 0 and cheque:
                put(r, "C", cheque, "D")
            if k + 1 < len(lines):
                put(r, "E", lines[k + 1], "K")
            r += 1
    if summary:
        put(r, "A", " Summary ")
        put(r + 1, "B", "Total Records  : "); put(r + 1, "D", float(len(docs) if say_count is None else say_count))
        put(r + 1, "K", "Grand Total   (MYR)"); put(r + 1, "P", float(round(sum(d[4] for d in docs), 2) if say_total is None else say_total))
        put(r + 4, "A", " Transaction Summary ")
        put(r + 5, "B", "Code"); put(r + 5, "D", "Description"); put(r + 5, "H", "Amount (MYR)")
        put(r + 6, "B", "900-E002"); put(r + 6, "D", "ELECTRICITY CHARGES"); put(r + 6, "G", 250.0)
        put(r + 7, "M", "Total Transaction :"); put(r + 7, "O", 1.0)
    return workbook(cells, merges)


D1 = ("PV2610-001", date(2026, 10, 5), ["EXAMPLE POWER - SEP 26 (14.08.26 - 13.09.26)"], "1000000001", 250.00)
D2 = ("PV2610-002", date(2026, 10, 5), ["EXAMPLE TELECOM LTD - SEP 26", "(16.09.26 - 15.10.26)"], "1000000002", 99.90)
D3 = ("CLAIMS_OCT26", date(2026, 10, 12), ["A PERSON - EXPENSES", "CLAIM - OCT 26"], "", 120.50)   # no PV prefix, no cheque no.
D4 = ("PV2610-003", date(2026, 10, 12), ["EXAMPLE SOFTWARE - SUBSCRIPTION FOR A PLAN  PRO", "(01/10/26 - 01/11/26) - EXAMPLE, INC - INVOICE NO.",
                                         "ABCD-0003 USD21.60"], "REF A1B2 & C3", 88.44)
D5 = ("PV2610-004", date(2026, 10, 20), ["EXAMPLE LANDLORD LTD - OFFICE RENTAL FOR OCT", "26"], "1000000005", 1750.00)
R1 = ("OR2610-001", date(2026, 10, 8), ["FUND RECEIVED FROM EXAMPLE PARENT"], "TT 778899", 20000.00)
R2 = ("RENT_OCT26", date(2026, 10, 9), ["EXAMPLE TENANT - RENT OCT 26"], "", 440.00)

# ---------- reading one listing ----------
one = listing([D1, D2, D3, D4])
try:
    from openpyxl import load_workbook
    load_workbook(io.BytesIO(one), read_only=True, data_only=True)
    refused = False
except Exception:
    refused = True
check("openpyxl refuses the workbook as SQL Account writes it, as it does the real export", refused)

rep = sqlreport.parse(one)
check("the listing is recognised: its title, document type, company and period",
      (rep["title"], {e["doc_type"] for e in rep["entries"]}, rep["company"], rep["period"])
      == ("Payment Voucher Listing", {"PV"}, EXH_LINE, ["2026-10-01", "2026-10-31"]), str(rep))
got = [(e["doc_no"], e["date"], e["amount"], e["cheque_no"]) for e in rep["entries"]]
check("each document is read once, with its date, amount and the cheque no. printed under its doc no.",
      got == [("PV2610-001", "2026-10-05", 250.0, "1000000001"), ("PV2610-002", "2026-10-05", 99.9, "1000000002"),
              ("CLAIMS_OCT26", "2026-10-12", 120.5, ""), ("PV2610-003", "2026-10-12", 88.44, "REF A1B2 & C3")], str(got))
check("a description printed on two or three rows is joined",
      [e["description"] for e in rep["entries"]][1:] == ["EXAMPLE TELECOM LTD - SEP 26 (16.09.26 - 15.10.26)", "A PERSON - EXPENSES CLAIM - OCT 26",
                                                         "EXAMPLE SOFTWARE - SUBSCRIPTION FOR A PLAN PRO (01/10/26 - 01/11/26) - EXAMPLE, INC - INVOICE NO. ABCD-0003 USD21.60"],
      str([e["description"] for e in rep["entries"]]))
check("the summary's transaction lines are not taken for documents, and the total is the report's", rep["total"] == 558.84, str(rep["total"]))

rows = sqlimport.read_rows("1.xlsx", one)
hr, mp = sqlimport.guess_header(rows)
recs = sqlimport.records(rows, hr, mp)
check("the SQL import reads the file: every entry a payment voucher paying money out, whatever its number",
      [(r["doc_no"], r["doc_type"], r["direction"], r["kind"], r["amount"], r["cheque_no"]) for r in recs]
      == [("PV2610-001", "PV", "out", "payment", 250.0, "1000000001"), ("PV2610-002", "PV", "out", "payment", 99.9, "1000000002"),
          ("CLAIMS_OCT26", "PV", "out", "payment", 120.5, ""), ("PV2610-003", "PV", "out", "payment", 88.44, "REF A1B2 & C3")], str(recs))

two_pages = sqlreport.parse(listing([D1, D2, D3, D4, D5], page_after=2))
check("page furniture printed again on a second page is not read as documents or as part of one",
      [e["doc_no"] for e in two_pages["entries"]] == ["PV2610-001", "PV2610-002", "CLAIMS_OCT26", "PV2610-003", "PV2610-004"]
      and two_pages["entries"][1]["description"] == "EXAMPLE TELECOM LTD - SEP 26 (16.09.26 - 15.10.26)"
      and two_pages["entries"][4]["description"] == "EXAMPLE LANDLORD LTD - OFFICE RENTAL FOR OCT 26"
      and not any("As At" in e["description"] or "Listing" in e["description"] for e in two_pages["entries"]), str(two_pages["entries"]))

receipts = sqlimport.records(*(lambda t: (t, *sqlimport.guess_header(t)))(sqlimport.read_rows("or.xlsx", listing([R1, R2], title="Official Receipt Listing"))))
check("an Official Receipt Listing is money in", [(r["doc_no"], r["doc_type"], r["direction"]) for r in receipts]
      == [("OR2610-001", "OR", "in"), ("RENT_OCT26", "OR", "in")], str(receipts))


def refusal(data):
    try:
        sqlreport.parse(data)
    except sqlreport.ReportError as ex:
        return str(ex)
    return None


check("a listing whose documents don't add up to its own grand total is refused whole",
      "says its total is 600.00" in (refusal(listing([D1, D2, D3, D4], say_total=600.0)) or ""), str(refusal(listing([D1, D2, D3, D4], say_total=600.0))))
check("a listing with fewer documents than it says is refused whole",
      "says it has 5 documents, but 4 could be read" in (refusal(listing([D1, D2, D3, D4], say_count=5)) or ""))
check("a printed report of another kind is named as one this app doesn't read yet",
      "not a listing this app reads yet" in (refusal(listing([D1], title="Journal of Transaction Listing")) or ""))
check("a listing without its summary is still read", len(sqlreport.parse(listing([D1, D2], summary=False))["entries"]) == 2)



# ---------- the other listings ----------

class Sheet:
    """Cells and merges of one sheet, put by row and column letter."""
    def __init__(self):
        self.cells, self.merges = {}, []

    def put(self, r, col, v, to=None):
        self.cells[(r, col)] = v
        if to:
            self.merges.append(f"{col}{r}:{to}{r}")

    def bytes(self):
        return workbook(self.cells, self.merges)


def cash_book(docs, company=EXH_LINE, page_after=None, say=None):
    """A Cash Book Listing. docs: (doc no, date, [description lines], cheque no, dr, cr). say: (count, dr total, cr total)."""
    s = Sheet()

    def page(r, n, pages):
        s.put(r, "G", "Cash Book Listing", "J"); s.put(r, "O", datetime(2026, 11, 13, 21, 18), "P"); s.put(r, "Q", "ADMIN")
        s.put(r + 1, "G", "As At 31/12/2026", "J")
        if n == 1:
            s.put(r, "A", "Date"); s.put(r, "B", "Doc No."); s.put(r, "E", "All"); s.put(r, "F", "From 01/12/2026 to 31/12/2026")
            s.put(r + 1, "A", "Currency"); s.put(r + 1, "B", "Incl Cancelled"); s.put(r + 1, "E", "No")
            s.put(r + 2, "A", "Sort By"); s.put(r + 2, "C", "PostDate;DocNo;CurrencyCode", "F")
        s.put(r + 3, "A", company, "I"); s.put(r + 3, "P", f"Page {n} of {pages}", "Q")
        s.put(r + 4, "A", "Doc Date"); s.put(r + 4, "C", "Doc No/Chq No", "D"); s.put(r + 4, "G", "Description")
        s.put(r + 4, "L", "Cash/ Bank"); s.put(r + 4, "N", "DR (MYR)"); s.put(r + 4, "Q", "CR (MYR)")
        return r + 5

    r = page(2, 1, 2 if page_after else 1)
    for n, (no, day, lines, cheque, dr, cr) in enumerate(docs):
        if page_after and n == page_after:
            r = page(r + 1, 2, 2)
        s.put(r, "A", day, "B"); s.put(r, "C", no, "D"); s.put(r, "E", lines[0], "J"); s.put(r, "K", "BANK-EXAMPLE 0001 0002 0003", "L")
        s.put(r, "M", float(dr), "N"); s.put(r, "P", float(cr), "Q")
        r += 1
        for k in range(max(len(lines) - 1, 1 if cheque else 0)):
            if k == 0 and cheque:
                s.put(r, "C", cheque, "D")
            if k + 1 < len(lines):
                s.put(r, "E", lines[k + 1], "K")
            r += 1
    count, dr_total, cr_total = say or (len(docs), round(sum(d[4] for d in docs), 2), round(sum(d[5] for d in docs), 2))
    s.put(r, "A", "Summary")
    s.put(r + 1, "B", "Total Records  :", "C"); s.put(r + 1, "D", float(count)); s.put(r + 1, "J", "Grand Total   (MYR)", "L")
    s.put(r + 1, "M", float(dr_total), "N"); s.put(r + 1, "P", float(cr_total), "Q")
    s.put(r + 4, "A", "Transaction Summary", "C")
    s.put(r + 5, "B", "Code"); s.put(r + 5, "D", "Description"); s.put(r + 5, "H", "Amount (MYR)")
    s.put(r + 6, "B", "900-R001", "C"); s.put(r + 6, "D", "RENTAL OF OFFICE", "F"); s.put(r + 6, "G", 3500.0, "H")
    return s.bytes()


def journals(docs, company=EXH_LINE):
    """A Journal Voucher Listing. docs: (doc no, date, [description lines], debit, credit)."""
    s = Sheet()
    s.put(2, "A", "Date"); s.put(2, "B", "Doc No."); s.put(2, "E", "All"); s.put(2, "F", "From 01/12/2026 to 31/12/2026")
    s.put(2, "G", "Journal Voucher Listing", "K"); s.put(2, "O", datetime(2026, 11, 13, 21, 17), "P"); s.put(2, "Q", "ADMIN")
    s.put(3, "A", "Currency"); s.put(3, "G", "As At 31/12/2026", "J")
    s.put(4, "A", "Sort By"); s.put(4, "C", "PostDate;DocNo;CurrencyCode", "F")
    s.put(5, "A", company, "I"); s.put(5, "P", "Page 1 of 1", "Q")
    s.put(6, "A", "Date"); s.put(6, "B", "Doc No"); s.put(6, "E", "Description"); s.put(6, "M", "Debit (MYR)", "N"); s.put(6, "P", "Credit (MYR)", "Q")
    r = 7
    for no, day, lines, debit, credit in docs:
        s.put(r, "A", day); s.put(r, "B", no, "C"); s.put(r, "E", lines[0], "L"); s.put(r, "M", float(debit), "N"); s.put(r, "P", float(credit), "Q")
        r += 1
        for extra in lines[1:]:
            s.put(r, "E", extra, "L")
            r += 1
    r += 1  # the Summary line carries the grand totals; the count is on the row under it
    s.put(r, "A", "Summary"); s.put(r, "J", "Grand Total   (MYR)", "L")
    s.put(r, "M", float(round(sum(d[3] for d in docs), 2)), "N"); s.put(r, "P", float(round(sum(d[4] for d in docs), 2)), "Q")
    s.put(r + 1, "B", "Total Records  :", "C"); s.put(r + 1, "D", float(len(docs)))
    s.put(r + 3, "A", "Transaction Summary", "C")
    s.put(r + 5, "A", "Code"); s.put(r + 5, "B", "Description"); s.put(r + 5, "E", "Local DR (MYR)", "F"); s.put(r + 5, "G", "Local CR (MYR)", "H")
    s.put(r + 6, "A", "310-1000"); s.put(r + 6, "B", "BANK-EXAMPLE 0001 0002 0003", "D"); s.put(r + 6, "E", 50000.0, "F"); s.put(r + 6, "G", 0.0, "H")
    return s.bytes()


def invoices(docs, title="Customer Invoice Listing", company=EXH_LINE, say_total=None):
    """A Customer Invoice Listing, or the Sales one (its title is just Invoice Listing). docs: (doc no, date, code, name, amount)."""
    s = Sheet()
    s.put(2, "A", "Date"); s.put(2, "B", ":"); s.put(2, "C", "From 01/12/2026 to 31/12/2026", "F")
    s.put(3, "A", "Document"); s.put(3, "C", "All")
    s.put(4, "A", "Company"); s.put(4, "C", "All")
    s.put(7, "A", "Area"); s.put(7, "B", "Currency"); s.put(7, "E", "----"); s.put(7, "G", title, "L"); s.put(7, "O", datetime(2026, 11, 13, 21, 14), "Q")
    s.put(8, "A", "Incl Cancelled"); s.put(8, "B", "Group By"); s.put(8, "E", "No"); s.put(8, "G", "As At 31/12/2026", "J")
    s.put(9, "A", "Sort By"); s.put(9, "C", "DocDate;DocNo;Code", "D")
    s.put(10, "A", company, "I"); s.put(10, "P", "Page 1 of 1", "Q")
    s.put(11, "A", "Doc. No", "B"); s.put(11, "C", "Doc. Date", "D"); s.put(11, "E", "Code"); s.put(11, "G", "Name"); s.put(11, "P", "Amount (MYR)", "Q")
    r = 12
    for no, day, code, name, amount in docs:
        s.put(r, "A", no, "B"); s.put(r, "C", day, "D"); s.put(r, "E", code, "F"); s.put(r, "G", name, "N"); s.put(r, "O", float(amount), "Q")
        r += 1
    s.put(r + 1, "J", "Grand Total Amount (MYR)", "L"); s.put(r + 1, "M", float(round(sum(d[4] for d in docs), 2) if say_total is None else say_total), "Q")
    s.put(r + 3, "A", "Transaction Summary", "C")
    s.put(r + 5, "B", "Code"); s.put(r + 5, "C", "Description"); s.put(r + 5, "H", "Amount (MYR)")
    s.put(r + 6, "B", "530-1000"); s.put(r + 6, "C", "OTHER INCOME - RENTAL", "E"); s.put(r + 6, "G", 440.0, "H")
    s.put(r + 7, "M", "Total Transaction :"); s.put(r + 7, "N", 1.0, "O")
    return s.bytes()


def customer_payments(docs, company=EXH_LINE):
    """A Customer Payment Listing. docs: (doc no, date, code, name, amount)."""
    s = Sheet()
    s.put(2, "A", "Date"); s.put(2, "B", ":"); s.put(2, "C", "From 01/12/2026 to 31/12/2026", "F")
    s.put(6, "A", "Agent"); s.put(6, "B", "Area"); s.put(6, "E", "All"); s.put(6, "G", "Customer Payment Listing", "L"); s.put(6, "O", datetime(2026, 11, 13, 21, 14), "Q")
    s.put(7, "A", "Currency"); s.put(7, "B", "Incl Cancelled"); s.put(7, "E", "No"); s.put(7, "G", "As At 31/12/2026", "J")
    s.put(8, "A", "Sort By"); s.put(8, "C", "PostDate;DocNo;Code", "E")
    s.put(9, "A", company, "I"); s.put(9, "P", "Page 1 of 1", "Q")
    s.put(10, "A", "Date"); s.put(10, "B", "Document No", "C"); s.put(10, "E", "Code"); s.put(10, "H", "Name"); s.put(10, "P", "Amount (MYR)", "Q")
    r = 11
    for no, day, code, name, amount in docs:
        s.put(r, "A", day); s.put(r, "B", no, "D"); s.put(r, "E", code, "F"); s.put(r, "G", name, "N"); s.put(r, "P", float(amount), "Q")
        r += 1
    s.put(r + 1, "A", "Grand Total Amount (MYR)", "D"); s.put(r + 1, "N", float(round(sum(d[4] for d in docs), 2)), "Q")
    return s.bytes()


C1 = ("PV2612-001", date(2026, 12, 4), ["EXAMPLE LANDLORD LTD - OFFICE RENTAL FOR DEC", "26"], "1000000021", 0, 1750.00)
C2 = ("OR2612-001", date(2026, 12, 8), ["EXAMPLE TENANT - RENT DEC 26"], "TT 445566", 440.00, 0)
C3 = ("CLAIMS_DEC26", date(2026, 12, 9), ["A PERSON - EXPENSES CLAIM - DEC 26"], "", 0, 75.25)
C4 = ("RC-PV2610-018", date(2026, 12, 10), ["EXAMPLE PARENT LTD", "REFUND OF A PAYMENT"], "", 21000.00, 0)   # money in, numbered like a voucher
book = sqlreport.parse(cash_book([C1, C2, C3, C4], page_after=2))
check("the cash book is read from both its pages: DR is an official receipt, CR a payment voucher, whatever the number",
      [(e["doc_no"], e["doc_type"], e["amount"], e["cheque_no"]) for e in book["entries"]]
      == [("PV2612-001", "PV", 1750.0, "1000000021"), ("OR2612-001", "OR", 440.0, "TT 445566"), ("CLAIMS_DEC26", "PV", 75.25, ""),
          ("RC-PV2610-018", "OR", 21000.0, "")], str(book["entries"]))
check("the page heading printed again is no part of the document above it",
      book["entries"][1]["description"] == "EXAMPLE TENANT - RENT DEC 26" and book["entries"][3]["description"] == "EXAMPLE PARENT LTD REFUND OF A PAYMENT",
      str([e["description"] for e in book["entries"]]))
check("the cash book's two grand totals are both checked",
      "says its total is 21,440.00 and 1,000.00, but the documents read add up to 21,440.00 and 1,825.25"
      in (refusal(cash_book([C1, C2, C3, C4], say=(4, 21440.0, 1000.0))) or ""), str(refusal(cash_book([C1, C2, C3, C4], say=(4, 21440.0, 1000.0)))))
book_recs = sqlimport.records(*(lambda t: (t, *sqlimport.guess_header(t)))(sqlimport.read_rows("book.xlsx", cash_book([C1, C2, C3, C4]))))
check("in the SQL import a cash book receipt is money in and a voucher money out",
      [(r["doc_no"], r["direction"], r["kind"]) for r in book_recs]
      == [("PV2612-001", "out", "payment"), ("OR2612-001", "in", "payment"), ("CLAIMS_DEC26", "out", "payment"), ("RC-PV2610-018", "in", "payment")], str(book_recs))

J1 = ("JV2612-01", date(2026, 12, 20), ["EXAMPLE TENANT - RECLASSIFICATION OF ACCOUNT WRONGLY", "CHARGED FOR RENTAL - AUG 26"], 1320.00, 1320.00)
J2 = ("JV2612-02", date(2026, 12, 26), ["EXAMPLE LEGAL FEE REIMBURSEMENT"], 50000.00, 50000.00)
jv = sqlreport.parse(journals([J1, J2]))
check("a Journal Voucher Listing is read: one amount per journal, its totals on the Summary line",
      [(e["doc_no"], e["doc_type"], e["amount"]) for e in jv["entries"]] == [("JV2612-01", "JV", 1320.0), ("JV2612-02", "JV", 50000.0)]
      and jv["entries"][0]["description"].endswith("WRONGLY CHARGED FOR RENTAL - AUG 26"), str(jv["entries"]))
jv_recs = sqlimport.records(*(lambda t: (t, *sqlimport.guess_header(t)))(sqlimport.read_rows("jv.xlsx", journals([J1, J2]))))
check("and is kept as journals", [(r["kind"], r["doc_type"]) for r in jv_recs] == [("journal", "JV")] * 2, str(jv_recs))
check("a journal whose debit and credit differ is refused",
      "whose debit and credit differ" in (refusal(journals([("JV2612-03", date(2026, 12, 27), ["LOPSIDED"], 10.0, 9.0)])) or ""))

I1 = ("EXH/2026/12/001", date(2026, 12, 15), "305-T0001", "EXAMPLE TENANT", 440.00)
I2 = ("EXH/2026/12/002", date(2026, 12, 16), "300-P0001", "EXAMPLE PARENT LTD.", 10000.00)
for name, made in (("Customer Invoice Listing", invoices([I1, I2])), ("Invoice Listing", invoices([I1, I2], title="Invoice Listing"))):
    inv = sqlreport.parse(made)
    check(f"the {name} is read: customer invoices with the customer's name and code",
          [(e["doc_no"], e["doc_type"], e["date"], e["amount"], e["payee"], e["code"]) for e in inv["entries"]]
          == [("EXH/2026/12/001", "IV", "2026-12-15", 440.0, "EXAMPLE TENANT", "305-T0001"),
              ("EXH/2026/12/002", "IV", "2026-12-16", 10000.0, "EXAMPLE PARENT LTD.", "300-P0001")], str(inv["entries"]))
inv_recs = sqlimport.records(*(lambda t: (t, *sqlimport.guess_header(t)))(sqlimport.read_rows("iv.xlsx", invoices([I1, I2]))))
check("in the SQL import they are invoices, with the name as payee and the SQL code kept",
      [(r["kind"], r["payee"], r["code"]) for r in inv_recs] == [("invoice", "EXAMPLE TENANT", "305-T0001"), ("invoice", "EXAMPLE PARENT LTD.", "300-P0001")], str(inv_recs))
check("an invoice on a supplier's account code is a supplier invoice",
      sqlreport.parse(invoices([("PI-0001", date(2026, 12, 3), "400-S0001", "EXAMPLE SUPPLIER", 99.0)], title="Invoice Listing"))["entries"][0]["doc_type"] == "PI")
check("an invoice listing is checked against its grand total, though it prints no count",
      "says its total is 5.00" in (refusal(invoices([I1, I2], say_total=5.0)) or ""))

P1 = ("OR2612-001", date(2026, 12, 8), "305-T0001", "EXAMPLE TENANT", 440.00)
P2 = ("RC-PV2610-018", date(2026, 12, 10), "300-P0001", "EXAMPLE PARENT LTD.", 21000.00)
pay = sqlreport.parse(customer_payments([P1, P2]))
check("a Customer Payment Listing is money in, with the customer's name and code",
      [(e["doc_no"], e["doc_type"], e["amount"], e["payee"], e["code"]) for e in pay["entries"]]
      == [("OR2612-001", "OR", 440.0, "EXAMPLE TENANT", "305-T0001"), ("RC-PV2610-018", "OR", 21000.0, "EXAMPLE PARENT LTD.", "300-P0001")], str(pay["entries"]))

gst = Sheet()
gst.put(1, "A", "Date"); gst.put(1, "C", "From 01/12/2026 to 31/12/2026", "E")
gst.put(5, "A", EXH_LINE, "L"); gst.put(5, "M", "Page 1 of 1", "N")
gst.put(6, "A", "Doc. Date"); gst.put(6, "C", "Doc. No. Chq. No."); gst.put(6, "D", "Description"); gst.put(6, "H", "<-------Excluding GST------->", "J")
gst.put(7, "H", "DR"); gst.put(7, "I", "CR", "J"); gst.put(8, "A", "04/12/2026", "B"); gst.put(8, "C", "PV2612-001 1000000021"); gst.put(8, "I", 1750.0, "J")
chart = Sheet()
chart.put(2, "B", "EXAMPLE HOLDINGS LTD", "C"); chart.put(3, "A", "Chart of Accounts", "G"); chart.put(4, "E", "Page 1 of 1", "G")
chart.put(5, "A", "Acc Code"); chart.put(5, "B", "Description"); chart.put(7, "A", "310-1000"); chart.put(7, "B", "BANK-EXAMPLE 0001 0002 0003")
check("the GST layout of a listing and the chart of accounts are named for what they are",
      "GST layout" in (refusal(gst.bytes()) or "") and "Paste it in Setup" in (refusal(chart.bytes()) or ""), str(refusal(gst.bytes())) + str(refusal(chart.bytes())))

plain = io.BytesIO()
from openpyxl import Workbook  # noqa: E402
wb = Workbook()
wb.active.append(["Doc No", "Doc Date", "Description", "Amount"])
wb.active.append(["PV2610-009", date(2026, 10, 30), "AN ORDINARY TABLE", 12.5])
wb.save(plain)
check("an ordinary workbook is not taken for an SQL listing, and is read as before",
      sqlreport.parse(plain.getvalue()) is None and len(sqlimport.read_rows("table.xlsx", plain.getvalue())) == 2)
quirk_table = workbook({(1, "A"): "Doc No", (1, "B"): "Doc Date", (1, "C"): "Description", (1, "D"): "Amount",
                        (2, "A"): "PV2610-009", (2, "B"): date(2026, 10, 30), (2, "C"): "A TABLE SQL ACCOUNT WROTE", (2, "D"): 12.5}, [])
tr = sqlimport.read_rows("grid.xlsx", quirk_table)
check("a plain table in a workbook openpyxl refuses is read from its XML parts",
      sqlimport.records(tr, *sqlimport.guess_header(tr))[0]["doc_no"] == "PV2610-009", str(tr))
check("a file that isn't a workbook is nothing to the report reader", sqlreport.parse(b"not a zip") is None and sqlreport.parse(b"PK broken") is None)

# ---------- one click: every export in the folder ----------

def save(name, data, age):
    """A file in the downloads folder, saved `age` minutes ago (the newest is read first)."""
    p = FOLDER / name
    p.write_bytes(data)
    t = datetime(2026, 11, 13, 12, 0).timestamp() - age * 60
    os.utime(p, (t, t))


save("1.xlsx", one, 50)                                                   # D1-D4, badly named
save("1 (1).xlsx", one, 40)                                               # the same file downloaded twice
save("x.xlsx", listing([D3, D4, D5]), 30)                                 # overlaps: D3 and D4 again, D5 new
save("Book2.xlsx", listing([R1, R2], title="Official Receipt Listing"), 20)
save("theirs.xlsx", listing([("PV2610-501", date(2026, 10, 6), ["ANOTHER COMPANY'S BILL"], "", 10.0)], company=SMP_LINE), 10)
save("whose.xlsx", listing([("PV2610-601", date(2026, 10, 6), ["NOBODY'S BILL"], "", 11.0)], company="UNKNOWN CO LTD (209901000009)"), 9)
save("ledger.xlsx", listing([D1], title="Ledger"), 8)
save("wrong total.xlsx", listing([D1, D2], say_total=1.0), 7)
save("budget.xlsx", plain.getvalue(), 6)
save("~$1.xlsx", b"an Excel lock file", 5)
(FOLDER / "notes.txt").write_text("not a workbook", encoding="utf-8")
before_files = sorted((p.name, p.stat().st_size, p.stat().st_mtime) for p in FOLDER.iterdir())

p = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
f = p["fetch"]
status = {x["name"]: x["status"] for x in f["files"]}
check("files are told apart by what they hold, not by their names",
      status == {"1 (1).xlsx": "read", "1.xlsx": "copy", "x.xlsx": "read", "Book2.xlsx": "read", "theirs.xlsx": "other_company",
                 "whose.xlsx": "unknown_company", "ledger.xlsx": "unreadable", "wrong total.xlsx": "unreadable"} and f["other"] == 1, str(status) + str(f["other"]))
per = {x["name"]: (x.get("entries"), x.get("new"), x.get("already"), x.get("repeated")) for x in f["files"] if x["status"] == "read"}
check("each listing says how many of its documents are new, and a document in two files is counted once",
      per == {"Book2.xlsx": (2, 2, 0, 0), "x.xlsx": (3, 3, 0, 0), "1 (1).xlsx": (4, 2, 0, 2)} and (f["entries"], f["new"], f["already"]) == (7, 7, 0), str(per))
reasons = {x["name"]: x["reason"] for x in f["files"]}
check("a file left out says why", "is for SMP (Sample Trading Ltd), not EXH" in reasons["theirs.xlsx"] and "matches no company" in reasons["whose.xlsx"]
      and "not a listing this app reads yet" in reasons["ledger.xlsx"] and "says its total is 1.00" in reasons["wrong total.xlsx"]
      and reasons["1.xlsx"] == "A copy of 1 (1).xlsx.", str(reasons))
check("the preview holds every document once, typed by its listing",
      sorted((r["doc_no"], r["doc_type"], r["direction"]) for r in p["records"])
      == sorted([("PV2610-001", "PV", "out"), ("PV2610-002", "PV", "out"), ("CLAIMS_OCT26", "PV", "out"), ("PV2610-003", "PV", "out"),
                 ("PV2610-004", "PV", "out"), ("OR2610-001", "OR", "in"), ("RENT_OCT26", "OR", "in")]) and not any(r["exists"] for r in p["records"]), str(p["records"]))
check("nothing is kept until Import", q("SELECT COUNT(*) n FROM sql_entries")[0]["n"] == 0 and q("SELECT COUNT(*) n FROM documents")[0]["n"] == 0)

again = j("post", "/api/sql/preview", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "picks": {}})
check("the review stays with the preview when it is read again", again["fetch"] == f)

res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
check("Import keeps the 7 documents", (res["added"], res["skipped"]) == (7, 0) and q("SELECT COUNT(*) n FROM sql_entries WHERE entity_id = ?", (EXH,))[0]["n"] == 7, str(res))
kept = q("SELECT original_name, month FROM documents WHERE entity_id = ? AND doc_type = 'sqlexport' ORDER BY id", (EXH,))
check("the table imported and the three listings it came from are kept as documents",
      len(kept) == 4 and kept[0]["original_name"].startswith("SQL exports fetched") and kept[0]["original_name"].endswith(".csv")
      and sorted(k["original_name"] for k in kept[1:]) == ["1 (1).xlsx", "Book2.xlsx", "x.xlsx"] and {k["month"] for k in kept} == {"2026-10"}, str(kept))
entry = q("SELECT * FROM sql_entries WHERE doc_no = 'PV2610-003'")[0]
check("an entry keeps its cheque no. and whole description", entry["cheque_no"] == "REF A1B2 & C3" and entry["description"].endswith("INVOICE NO. ABCD-0003 USD21.60")
      and entry["doc_type"] == "PV" and entry["direction"] == "out", str(entry))
check("nothing in the folder was moved, renamed or changed",
      sorted((x.name, x.stat().st_size, x.stat().st_mtime) for x in FOLDER.iterdir()) == before_files)

p2 = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
status2 = {x["name"]: x["status"] for x in p2["fetch"]["files"]}
check("a second click finds nothing new: the files imported are left out by their fingerprints",
      p2.get("nothing_new") is True and "token" not in p2 and p2["records"] == []
      and [status2[n] for n in ("1.xlsx", "1 (1).xlsx", "x.xlsx", "Book2.xlsx")] == ["imported_before"] * 4, str(status2))

N1 = ("PV2611-001", date(2026, 11, 5), ["EXAMPLE POWER - OCT 26"], "1000000011", 260.00)
N2 = ("PV2611-002", date(2026, 11, 5), ["EXAMPLE TELECOM LTD - OCT 26"], "1000000012", 99.90)
save("download.xlsx", listing([D5, N1, N2], period=("20/10/2026", "30/11/2026")), 1)
p3 = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
new_file = next(x for x in p3["fetch"]["files"] if x["name"] == "download.xlsx")
check("a later export shows what is new and what is already imported",
      (new_file["entries"], new_file["new"], new_file["already"]) == (3, 2, 1) and (p3["fetch"]["new"], p3["fetch"]["already"]) == (2, 1)
      and new_file["period"] == ["2026-10-20", "2026-11-30"], str(new_file))
check("the new documents come first in the preview, the one already imported marked so",
      [(r["doc_no"], r["exists"]) for r in p3["records"]] == [("PV2611-001", False), ("PV2611-002", False), ("PV2610-004", True)], str(p3["records"]))
res3 = j("post", "/api/sql/apply", json={"token": p3["token"], "header_row": p3["header_row"], "mapping": p3["mapping"], "links": {}})
check("importing it adds only the new ones", (res3["added"], res3["skipped"]) == (2, 1)
      and q("SELECT COUNT(*) n FROM sql_entries WHERE entity_id = ?", (EXH,))[0]["n"] == 9, str(res3))
log = q("SELECT what FROM activity WHERE what LIKE 'Imported SQL export%' ORDER BY id DESC LIMIT 1")[0]["what"]
check("the activity log says the import came from exported files", "read from 1 exported files in" in log and str(FOLDER) in log, log)

theirs = j("post", "/api/sql/preview", json={"entity_id": SMP, "fetch": True})
st = {x["name"]: x["status"] for x in theirs["fetch"]["files"]}
check("the other company gets its own listing and none of the first company's",
      [r["doc_no"] for r in theirs["records"]] == ["PV2610-501"] and st["theirs.xlsx"] == "read" and st["download.xlsx"] == "other_company"
      and q("SELECT COUNT(*) n FROM sql_entries WHERE entity_id = ?", (SMP,))[0]["n"] == 0, str(st))

# A registration number set in Setup places a listing whose company name is spelt differently
j("patch", f"/api/setup/entities/{SMP}", json={"fields": {"reg_no": "7654321-Y"}})
save("renamed.xlsx", listing([("PV2610-502", date(2026, 10, 7), ["A SECOND BILL"], "", 12.0)], company="SAMPLE TRDG LIMITED (202601000002 (7654321-Y))"), 0)
by_reg = j("post", "/api/sql/preview", json={"entity_id": SMP, "fetch": True})
check("a listing is placed by the registration number when the name is spelt another way",
      {x["name"]: x["status"] for x in by_reg["fetch"]["files"]}["renamed.xlsx"] == "read" and len(by_reg["records"]) == 2, str(by_reg["fetch"]["files"]))

# ---------- a month's listings together ----------
MONTH = tmp / "december"
MONTH.mkdir()
config.SETTINGS["sql_exports_dir"] = str(MONTH)
(MONTH / "a.xlsx").write_bytes(cash_book([C1, C2, C3, C4]))
(MONTH / "b.xlsx").write_bytes(customer_payments([P1, P2]))
(MONTH / "c.xlsx").write_bytes(invoices([I1, I2]))
(MONTH / "d.xlsx").write_bytes(invoices([I1, I2], title="Invoice Listing"))
(MONTH / "e.xlsx").write_bytes(journals([J1, J2]))
(MONTH / "f.xlsx").write_bytes(gst.bytes())
(MONTH / "g.xlsx").write_bytes(chart.bytes())
for n, name in enumerate("gfedcba"):  # a.xlsx the newest, so the cash book is read first
    t = datetime(2026, 12, 31, 12, 0).timestamp() - (6 - n) * 60
    os.utime(MONTH / f"{name}.xlsx", (t, t))
dec = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
st = {x["name"]: x["status"] for x in dec["fetch"]["files"]}
check("a month's listings are read together; the GST layout and the chart of accounts are left out",
      st == {"a.xlsx": "read", "b.xlsx": "read", "c.xlsx": "read", "d.xlsx": "read", "e.xlsx": "read", "f.xlsx": "unreadable", "g.xlsx": "unreadable"}
      and (dec["fetch"]["entries"], dec["fetch"]["new"]) == (8, 8), str(st) + str(dec["fetch"]["entries"]))
by_no = {r["doc_no"]: r for r in dec["records"]}
check("a receipt in the cash book and the customer payment listing is one document, with what each listing says",
      len(dec["records"]) == 8 and (by_no["OR2612-001"]["description"], by_no["OR2612-001"]["cheque_no"], by_no["OR2612-001"]["payee"], by_no["OR2612-001"]["code"])
      == ("EXAMPLE TENANT - RENT DEC 26", "TT 445566", "EXAMPLE TENANT", "305-T0001")
      and by_no["RC-PV2610-018"]["payee"] == "EXAMPLE PARENT LTD." and by_no["RC-PV2610-018"]["direction"] == "in", str(by_no["OR2612-001"]))
check("each kind of document is told apart",
      sorted((r["doc_no"], r["kind"]) for r in dec["records"]) == sorted([
          ("PV2612-001", "payment"), ("OR2612-001", "payment"), ("CLAIMS_DEC26", "payment"), ("RC-PV2610-018", "payment"),
          ("EXH/2026/12/001", "invoice"), ("EXH/2026/12/002", "invoice"), ("JV2612-01", "journal"), ("JV2612-02", "journal")]), str(dec["records"]))
res_dec = j("post", "/api/sql/apply", json={"token": dec["token"], "header_row": dec["header_row"], "mapping": dec["mapping"], "links": {}})
row = q("SELECT * FROM sql_entries WHERE doc_no = 'OR2612-001'")[0]
check("and they are imported with those details", res_dec["added"] == 8 and (row["payee"], row["code"], row["cheque_no"], row["direction"])
      == ("EXAMPLE TENANT", "305-T0001", "TT 445566", "in")
      and q("SELECT kind FROM sql_entries WHERE doc_no = 'JV2612-01'")[0]["kind"] == "journal", str(res_dec) + str(row))
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

# ---------- the same file chosen by hand ----------
up = c.post(BASE + "/api/sql/preview", headers=H, content_type="multipart/form-data",
            data={"file": (io.BytesIO(listing([N1, ("PV2611-003", date(2026, 11, 6), ["ONE MORE"], "", 5.0)])), "anything.xlsx"), "entity_id": str(EXH)})
check("an exported listing chosen with Choose file is read too", up.status_code == 200
      and [(r["doc_no"], r["exists"]) for r in up.get_json()["records"]] == [("PV2611-001", True), ("PV2611-003", False)] and "fetch" not in up.get_json(),
      up.get_data(as_text=True)[:300])
bad = c.post(BASE + "/api/sql/preview", headers=H, content_type="multipart/form-data",
             data={"file": (io.BytesIO(listing([D1], say_total=9.0)), "anything.xlsx"), "entity_id": str(EXH)})
check("and one that doesn't add up is refused with the reason", bad.status_code == 400 and "says its total is 9.00" in bad.get_json()["error"], bad.get_data(as_text=True)[:300])

# ---------- the folder ----------
meta = j("get", "/api/meta")
check("the page is told which folder is read", meta["sql_exports_dir"] == str(FOLDER) and meta["sql_exports_default"] is False)
other_dir = tmp / "elsewhere"
other_dir.mkdir()
r = j("post", "/api/settings/sql-exports-dir", json={"sql_exports_dir": str(other_dir)})
check("the folder can be changed, and is saved with the machine's settings",
      r == {"sql_exports_dir": str(other_dir), "default": False} and json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))["sql_exports_dir"] == str(other_dir))
empty = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
check("an empty folder has nothing new", empty["nothing_new"] is True and empty["fetch"]["files"] == [] and empty["fetch"]["folder"] == str(other_dir))
e1 = j("post", "/api/settings/sql-exports-dir", 400, json={"sql_exports_dir": str(tmp / "no such folder")})["error"]
e2 = j("post", "/api/settings/sql-exports-dir", 400, json={"sql_exports_dir": "downloads"})["error"]
check("a folder that isn't there, or isn't a full path, is refused", "can't be found" in e1 and "full path" in e2, e1 + " | " + e2)
r = j("post", "/api/settings/sql-exports-dir", json={"sql_exports_dir": ""})
check("left empty, the Downloads folder is read", r == {"sql_exports_dir": sqlfetch.default_folder(), "default": True})
config.SETTINGS["sql_exports_dir"] = str(tmp / "gone")
gone = j("post", "/api/sql/preview", 400, json={"entity_id": EXH, "fetch": True})["error"]
check("a folder removed since says so", "can't be found" in gone, gone)
print("\nAll SQL export checks passed.")
