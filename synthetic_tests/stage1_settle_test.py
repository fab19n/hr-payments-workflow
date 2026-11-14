"""Stage 1 settled: the gaps a scope audit found in mirroring SQL Account's books, on made-up records only.

1. A document in a section of SQL's Journal of Transaction this app has no listing reader for (cash sales, credit notes
   and the like) is never asked for a listing: the SQL books item counts it as checked by its own lines and SQL's trial
   balance, and the SQL page lists it in a group of its own.
2. A journal SQL deleted (marked no longer in SQL by a later Journal of Transaction) can be confirmed as deleted in SQL:
   kept, listed under Ignored, left out of the checks, and put back by Un-ignore.
3. Setup's export and import carry the statutory accounts.
4. A listing imported on its own that moves a signed-off bank reconciliation month is said in the preview, the result
   and the activity log; the month stays signed off.
5. The SQL page's orphan card leaves out documents before the first month tracked, counting them in one line.
6. The Books page opens on the latest SQL trial balance's as-at day, so the check against SQL can run.
7. A listing or GL report whose amounts are in another currency than ringgit is refused.
8. A workbook too large to read is named in Fetch's review, and the size limits agree.
9. No message still says to paste a listing where Fetch reads it (a source check).
10. A review's findings, each checked: a ringgit report whose text has "Total ... (Sdn)" is read; a large workbook SQL
    didn't write is left alone; a voucher confirmed as deleted in SQL leaves the bank reconciliation (and Un-ignore
    brings it back), saying a signed-off month it moves; a voucher listed on several rows is confirmed whole or not at
    all; the Books pages open on the newest day SQL's reports kept reach; a full Setup export always imports.

The workbooks are built to the layout of the real exports (copied from sql_books_item_test), with a made-up company,
accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.stage1_settle_test
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-stage1-settle-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # a new install that imports <setup.json> and writes its statutory accounts to <out.json>

from hrp import books, config, db, ledger, masters, setupfile, sqlbooks, sqlfetch, sqlgl, sqlreport  # noqa: E402
from hrp import app as appmod  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

if not CHILD:
    (tmp / "seed.json").write_text(json.dumps({"entities": [
        {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
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


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


if CHILD:  # ---------- a new install: imports the setup file, writes what it then holds ----------
    src, out = Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(src.read_text(encoding="utf-8"))
    res = j("post", "/api/setup/import", json={"setup": data, "reason": "test: a new install"})
    out.write_text(json.dumps({"counts": res.get("counts"), "notes": res.get("notes"), "statutory": q(
        """SELECT e.code AS company, s.kind, s.label, s.payable_code, s.employer_code, s.due_day, s.notes, s.active, s.sort
           FROM statutory_accounts s JOIN entities e ON e.id = s.entity_id ORDER BY s.sort, s.id""")}), encoding="utf-8")
    sys.exit(0)

# ---------- a workbook as SQL Account writes it (copied from books_test) ----------

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


def jot(sections, period, cur="MYR"):
    """A GL Journal of Transaction (cur: the currency its headings name). sections: [(label, [(doc no, dd/mm/yyyy, [(code, name, description, dr, cr)])])]."""
    s = Sheet()
    s.row((0, "Date"), (1, ":"), (2, 3, f"From {period[0]} to {period[1]}"), (7, STAMP))
    s.row((0, "Sort By"), (1, ":"), (2, 3, "PostDate;Ref1"))
    s.row((0, 5, COMPANY), (7, 8, "Page 1 of 1"))
    s.row((0, 1, "Doc Date"), (2, "A/C Code"), (3, "A/C Description"), (4, "Ref 1"), (5, 6, "Description"), (7, f"Debit ({cur})"), (8, f"Credit ({cur})"))
    for label, docs in sections:
        s.row((0, 6, label))
        dr_t = cr_t = 0.0
        for no, day, lines in docs:
            for k, (code, name, desc, dr, cr) in enumerate(lines):
                cells = [(2, code), (3, name), (4, no), (5, 6, desc)] + ([(0, 1, day)] if k == 0 else [])
                cells += ([(7, float(dr))] if dr else []) + ([(8, float(cr))] if cr else [])
                s.row(*cells)
                dr_t, cr_t = dr_t + dr, cr_t + cr
        s.row((0, 6, f"Total  ({cur}) :"), (7, float(round(dr_t, 2))), (8, float(round(cr_t, 2))))
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


def save(name, data, folder=FOLDER):
    """A file in the downloads folder, each one saved a minute after the one before."""
    SAVED[0] += 1
    p = folder / name
    p.write_bytes(data)
    t = datetime(2026, 11, 14, 9, 0).timestamp() + SAVED[0] * 60
    os.utime(p, (t, t))
    return p


def fetch():
    p = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
    return j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


imp = [0]


def listing(*rows):
    """SQL's listing entries kept (an import of their own): rows (doc no, date, amount, kind, doc type, direction)."""
    imp[0] += 1
    con = db.connect()
    con.arm("user", "test: a listing imported")
    try:
        iid = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, ?, 0)",
                          (EID, f"listing-{imp[0]}.xlsx", db.now(), len(rows))).lastrowid
        for no, d, amount, kind, dt, direction in rows:
            con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction,
                           doc_type, kind, status) VALUES (?, ?, ?, ?, 'Example', 'EXAMPLE POWER', ?, ?, ?, ?, ?)""",
                        (iid, EID, no, d, amount, direction, dt, kind, "unlinked" if kind == "payment" else kind))
        con.commit()
    finally:
        con.disarm()
        con.close()


def month_check(month="2026-10"):
    with db.connect() as con:
        ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone())
        return sqlbooks.month_check(con, ent, month)


EID = q("SELECT id FROM entities WHERE code = 'AISB'")[0]["id"]
ACCT = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
# Tracked from October; the financial year from September; the bank's GL code set.
write("the first month tracked, the financial year, the bank's GL code",
      ("UPDATE entities SET first_month = '2026-10', fy_start = 9 WHERE id = ?", (EID,)),
      ("UPDATE accounts SET gl_code = '310-1000' WHERE id = ?", (ACCT,)))
CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("420-1001", "EPF PAYABLE", "liability", None), ("500-0000", "SALES", "income", None),
         ("900-E001", "EPF EMPLOYER", "expense", None), ("900-E002", "ELECTRICITY", "expense", None)]
write("the chart of accounts", *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, *a))
                                 for a in CHART])

BANK = ("310-1000", "BANK-EXAMPLE 0001")
PV9 = ("PV2609-001", "10/09/2026", [("900-E002", "ELECTRICITY", "Electricity Aug", 100.0, 0), (*BANK, "Electricity Aug", 0, 100.0)])
PV10 = ("PV2610-001", "15/10/2026", [("900-E002", "ELECTRICITY", "Electricity Sep", 200.0, 0), (*BANK, "Electricity Sep", 0, 200.0)])
JV1 = ("JV2610-001", "12/10/2026", [("900-E002", "ELECTRICITY", "Accrual", 50.0, 0), ("100-0000", "SHARE CAPITAL", "Accrual", 0, 50.0)])
JV2 = ("JV2610-002", "13/10/2026", [("900-E002", "ELECTRICITY", "Accrual", 10.0, 0), ("100-0000", "SHARE CAPITAL", "Accrual", 0, 10.0)])
CS = ("CS2610-001", "20/10/2026", [(*BANK, "Cash sale", 80.0, 0), ("500-0000", "SALES", "Cash sale", 0, 80.0)])
PERIOD = ("01/09/2026", "31/10/2026")
# SQL's trial balances from 1 September (the year start) to 31 October: with JV2610-001, then after it was deleted in
# SQL and JV2610-002 entered instead. Each account: (open, period to date, month to date, year to date) as (dr, cr).
TB_A = [("100-0000", "SHARE CAPITAL", (0, 10000.0), (0, 50.0), (0, 50.0), (0, 10050.0)),
        ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 220.0), (0, 120.0), (9780.0, 0)),
        ("500-0000", "SALES", (0, 0), (0, 80.0), (0, 80.0), (0, 80.0)),
        ("900-E002", "ELECTRICITY", (0, 0), (350.0, 0), (250.0, 0), (350.0, 0))]
TB_B = [("100-0000", "SHARE CAPITAL", (0, 10000.0), (0, 10.0), (0, 10.0), (0, 10010.0)), TB_A[1], TB_A[2],
        ("900-E002", "ELECTRICITY", (0, 0), (310.0, 0), (210.0, 0), (310.0, 0))]


# ---------- 1. a document in a section with no listing this app reads ----------

save("jot-a.xlsx", jot([("Bank Journal", [PV9, PV10]), ("General Journal", [JV1]), ("Cash Sales Journal", [CS])], PERIOD))
save("tb-a.xlsx", trial_balance(TB_A, *PERIOD))
fetch()
listing(("PV2610-001", "2026-10-15", 200.0, "payment", "PV", "out"), ("JV2610-001", "2026-10-12", 50.0, "journal", "JE", None))
check("the cash sale is kept in the 'other' book", q("SELECT book FROM ledger_docs WHERE doc_no = 'CS2610-001'")[0]["book"] == "other")
with db.connect() as con:
    o = ledger.orphans(con, EID)
check("a document in a section with no listing reader is not asked for a listing, but listed in a group of its own",
      [x["doc_no"] for x in o["own_lines"]] == ["CS2610-001"] and "CS2610-001" not in [x["doc_no"] for x in o["no_listing"]], o)
ok, why = month_check()
check("the SQL books item is done, counting the cash sale as checked by its lines and SQL's trial balance",
      ok is True and why.endswith("(1 document in sections with no listing this app reads was checked by its account lines and "
                                  "SQL's trial balance)"), why)
d = j("get", f"/api/sql/entries?entity={EID}")["ledger"]["orphans"]
check("the SQL page has the group of its own", [x["doc_no"] for x in d["own_lines"]] == ["CS2610-001"], d)
src = (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8")
check("the page says plainly how those are checked", ledger.OWN_LINES_WORDS in src
      and ledger.OWN_LINES_WORDS == "No listing this app reads yet: checked by their account lines and SQL's trial balance")
# A document of a bank, general, sales or purchase section with no listing is still asked for one.
write("the journal's listing row moved to another company for a moment", ("UPDATE sql_entries SET entity_id = -1 WHERE doc_no = 'JV2610-001'", ()))
ok, why = month_check()
check("a general journal document with no listing is still asked for its listing, in Fetch's words",
      ok is False and "have no listing" not in why and "has no listing (JV2610-001): fetch SQL's listing for October 2026 on the SQL import page." in why, why)
write("the listing row back", ("UPDATE sql_entries SET entity_id = ? WHERE doc_no = 'JV2610-001'", (EID,)))
check("and done again once it is listed", month_check()[0] is True)

# ---------- 5. documents before the first month tracked stay off the orphan card ----------

check("without a first day, PV2609-001 (September, no listing) is among those with no listing",
      "PV2609-001" in [x["doc_no"] for x in o["no_listing"]], o)
check("the SQL page leaves documents before the first month tracked out, counting them in one line",
      "PV2609-001" not in [x["doc_no"] for x in d["no_listing"]] and d["before_tracking"] == 1 and d["no_listing"] == [], d)
check("the page has that one muted line", "before the first month tracked" in src and "orph.before_tracking" in src)

# ---------- 2. a journal deleted in SQL ----------

save("jot-b.xlsx", jot([("Bank Journal", [PV9, PV10]), ("General Journal", [JV2]), ("Cash Sales Journal", [CS])], PERIOD))
save("tb-b.xlsx", trial_balance(TB_B, *PERIOD, stamp="14/11/2026 2:00:00 AM ADMIN"))
fetch()
listing(("JV2610-002", "2026-10-13", 10.0, "journal", "JE", None))
check("the later journal marks JV2610-001 no longer in SQL", q("SELECT state FROM ledger_docs WHERE doc_no = 'JV2610-001'")[0]["state"] == "gone")
ok, why = month_check()
check("the month fails on the listing entry SQL no longer has", ok is False and "JV2610-001" in why and "missing from SQL's GL" in why, why)
o = j("get", f"/api/sql/entries?entity={EID}")["ledger"]["orphans"]
jv = next(x for x in o["not_in_journal"] if x["doc_no"] == "JV2610-001")
check("the SQL page offers to confirm it as deleted in SQL", jv["gone"] is True and jv["can_confirm"] is True and jv["can_ignore"] is False, jv)
check("the page's button says Deleted in SQL, and the old card text is gone",
      "Deleted in SQL</button>" in src and "Ignore one that SQL no longer has" not in src)
r = call("post", f"/api/sql/entries/{jv['ids'][0]}", json={"status": "ignored"})
check("the plain Ignore still refuses a journal", r.status_code == 400 and "it is a journal" in r.get_json()["error"], r.data[:300])
pv = q("SELECT id FROM sql_entries WHERE doc_no = 'PV2610-001'")[0]["id"]
r = call("post", "/api/sql/entries/deleted", json={"ids": [pv]})
check("an entry SQL's journal still has can't be confirmed as deleted", r.status_code == 400
      and "PV2610-001 can't be confirmed as deleted in SQL" in r.get_json()["error"]
      and q("SELECT status FROM sql_entries WHERE id = ?", (pv,))[0]["status"] == "unlinked", r.data[:300])
res = j("post", "/api/sql/entries/deleted", json={"ids": jv["ids"]})
row = q("SELECT * FROM sql_entries WHERE doc_no = 'JV2610-001'")
check("confirmed: the row is kept, marked ignored", res["doc_nos"] == ["JV2610-001"] and len(row) == 1 and row[0]["status"] == "ignored", row)
check("the activity log says so", any(x["what"] == "Confirmed as deleted in SQL (kept, listed under Ignored): JV2610-001"
                                      for x in q("SELECT what FROM activity")))
ok, why = month_check()
check("the SQL books item passes once the rest agrees", ok is True, why)
e = j("get", f"/api/sql/entries?entity={EID}")
check("it is listed under Ignored, not under Journals and invoices, nor on the orphan card",
      any(x["doc_no"] == "JV2610-001" for x in e["ignored"]) and not any(x["doc_no"] == "JV2610-001" for x in e["documents"])
      and not any(x["doc_no"] == "JV2610-001" for x in e["ledger"]["orphans"]["not_in_journal"]), e["ledger"]["orphans"])
u = j("post", f"/api/sql/entries/{row[0]['id']}/unignore", json={})
check("Un-ignore puts it back as a journal, and the check fails again",
      u["kind"] == "journal" and q("SELECT status FROM sql_entries WHERE id = ?", (row[0]["id"],))[0]["status"] == "journal"
      and month_check()[0] is False)
j("post", "/api/sql/entries/deleted", json={"ids": jv["ids"]})
check("confirmed again, done again", month_check()[0] is True)

# ---------- 6. the Books page opens on a day it can check ----------

with db.connect() as con:
    check("the default To date is the latest SQL trial balance's as-at day", books.default_to(con, EID) == "2026-10-31")
    check("never after today", books.default_to(con, EID, date(2026, 10, 30)) == "2026-10-30")
d = j("get", f"/api/books/trial-balance?entity={EID}")
check("the Trial balance tab opens on that day, from the year's start, and checks against SQL",
      (d["from"], d["to"]) == ("2026-09-01", "2026-10-31") and d["check"]["outcome"] == "ok", (d["from"], d["to"], d["check"]["text"]))
d = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-09-01&to=2026-10-20")
check("explicit dates are kept as given", (d["from"], d["to"]) == ("2026-09-01", "2026-10-20"))
check("the balance sheet opens on that day too", j("get", f"/api/books/balance-sheet?entity={EID}")["as_at"] == "2026-10-31")

# ---------- 4. a listing alone that moves a signed-off bank month ----------

write("November's bank reconciliation signed off",
      ("""INSERT INTO statements (account_id, month, opening, closing, imported_at, reconciled_at, reconciled_how)
          VALUES (?, '2026-11', 0, 0, ?, ?, 'manual')""", (ACCT, db.now(), db.now())))


def packet(rows):
    """A DATAPACKET as SQL Account copies a grid: one ROW per dictionary (copied from journal_bank_test)."""
    def attrs(r):
        return " ".join('%s="%s"' % (k, v) for k, v in r.items())
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % attrs(r) for r in rows) + "</ROWDATA></DATAPACKET>")


nov = packet([{"DOCKEY": "901", "DOCNO": "PV2611-001", "DOCTYPE": "PV", "DOCDATE": "20261105", "DESCRIPTION": "EXAMPLE POWER",
               "DOCAMT": "40.00", "CANCELLED": "FALSE", "PAYMENTMETHODDESC": "BANK-EXAMPLE 0001", "DR": "0.00", "CR": "40.00"}])
pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": nov})
check("the preview says the new entry falls in a signed-off month", pre["signed_off"] == ["2026-11"], pre.get("signed_off"))
res = j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})
check("the import says the signed-off month's books changed", [m["month"] for m in res["recon_changed"]] == ["2026-11"]
      and res["recon_changed"][0]["before"]["out"] == 0 and res["recon_changed"][0]["after"]["out"] == 40.0, res)
check("the activity log says so too", any("bank reconciliation changed for signed-off 2026-11" in x["what"] for x in q("SELECT what FROM activity")))
check("nothing is un-signed", q("SELECT reconciled_at FROM statements WHERE account_id = ? AND month = '2026-11'", (ACCT,))[0]["reconciled_at"])
pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": nov})
res = j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})
check("the same listing again changes nothing, and says nothing", pre["signed_off"] == [] and res["recon_changed"] == [], (pre["signed_off"], res))
check("the page shows the preview's warning", "p.signed_off" in src and "res.recon_changed" in src)

# ---------- 3. Setup's export and import carry the statutory accounts ----------

with db.connect() as con:
    con.arm("user", "test: statutory accounts")
    masters.create(con, "statutory_accounts", {"kind": "epf", "label": "EPF (KWSP)", "payable_code": "420-1001",
                                               "employer_code": "900-E001", "due_day": 15, "notes": "made up"}, entity_id=EID)
    con.commit()
    con.disarm()
    data = setupfile.export(con, "full")
check("the full export holds the statutory accounts", data.get("statutory_accounts") == [
    {"company": "AISB", "kind": "epf", "label": "EPF (KWSP)", "payable_code": "420-1001", "employer_code": "900-E001", "due_day": 15,
     "active": 1, "sort": 1, "notes": "made up"}], data.get("statutory_accounts"))
with db.connect() as con:
    check("a template doesn't", "statutory_accounts" not in setupfile.export(con, "template"))
    check("and records holding statutory accounts are not a new install",
          ["statutory account", 1] in setupfile.holding(con), setupfile.holding(con))
f_in, f_out = tmp / "setup.json", tmp / "imported.json"
f_in.write_text(json.dumps(data), encoding="utf-8")
root = Path(__file__).resolve().parent.parent
run = subprocess.run([sys.executable, "-m", "synthetic_tests.stage1_settle_test", "--import", str(f_in), str(f_out)], cwd=root,
                     capture_output=True, text=True, timeout=600)
got = json.loads(f_out.read_text(encoding="utf-8")) if f_out.exists() else None
check("a new install imports them, as they were", run.returncode == 0 and got and got["statutory"] == [
    {"company": "AISB", "kind": "epf", "label": "EPF (KWSP)", "payable_code": "420-1001", "employer_code": "900-E001", "due_day": 15,
     "notes": "made up", "active": 1, "sort": 1}] and ["statutory account", 1] in got["counts"], (run.stdout[-800:], run.stderr[-800:], got))
bad = json.loads(json.dumps(data))
bad["statutory_accounts"][0].update(kind="socso", payable_code="999-9999")
with db.connect() as con:  # the row's checks only (refused before anything is written)
    imp_ = setupfile._Import(con, bad)
    imp_.ents = {"AISB": EID}
    try:
        imp_.statutory()
        refused = None
    except masters.Refused as x:
        refused = str(x)
    con.rollback()
check("a statutory account naming an account the chart doesn't have is refused, as Setup refuses it",
      refused and "Statutory account EPF (KWSP) of AISB" in refused and "no account 999-9999" in refused, refused)

# ---------- 7. amounts in another currency are refused ----------

rows = [["Payment Voucher Listing"], ["Page 1 of 1"], ["Doc Date", "Doc No", "Description", "Amount (USD)"],
        [date(2026, 10, 1), "PV2610-009", "Example", 10.0]]
try:
    sqlreport.listing(rows, {})
    why = None
except sqlreport.ReportError as x:
    why = str(x)
check("a listing in US dollars is refused in a plain sentence", why and "in USD, not ringgit (MYR)" in why, why)
rows[2][3] = "Amount (MYR)"
try:
    sqlreport.listing(rows, {})
    why = None
except sqlreport.ReportError as x:
    why = str(x)
check("the same listing in ringgit is not refused for its currency", not why or "ringgit" not in why, why)
try:
    sqlreport.read(jot([("Bank Journal", [PV10])], ("01/10/2026", "31/10/2026"), cur="SGD"))
    why = None
except sqlreport.ReportError as x:
    why = str(x)
check("a GL Journal of Transaction in Singapore dollars is refused", why and "in SGD, not ringgit (MYR)" in why, why)
check("in ringgit it is read", sqlreport.read(jot([("Bank Journal", [PV10])], ("01/10/2026", "31/10/2026")))[0] == "journal")

# ---------- 8. a workbook too large to read is named ----------

big = tmp / "big"
big.mkdir()
save("Huge journal.xlsx", jot([("Bank Journal", [PV10])], ("01/10/2026", "31/10/2026")), folder=big)
keep = sqlfetch.MAX_BYTES
sqlfetch.MAX_BYTES = 100  # as if the workbook were larger than the limit
try:
    with db.connect() as con:
        g = sqlfetch.gather(con, EID, big)
finally:
    sqlfetch.MAX_BYTES = keep
f = g["files"][0] if g["files"] else {}
check("a workbook larger than the limit is named as too large to read, not counted silently",
      g["other"] == 0 and f.get("name") == "Huge journal.xlsx" and f.get("status") == "too_large"
      and f.get("reason", "").startswith("too large to read (0.0 MB"), g)
check("the limits agree: the reader's, Fetch's and the upload's",
      sqlfetch.MAX_BYTES == sqlreport.MAX_BYTES and sqlreport.MAX_PART >= sqlreport.MAX_BYTES
      and app.config["MAX_CONTENT_LENGTH"] >= sqlfetch.MAX_BYTES)

# ---------- 9. Fetch wording ----------

hrp_dir = config.PROGRAM_DIR / "hrp"
texts = {p.name: p.read_text(encoding="utf-8") for p in hrp_dir.glob("*.py")}
texts["app.js"] = src
old = ["Paste SQL listing", "Paste the latest SQL listing", "paste the cash book listing", "fetch or paste SQL's listing",
       "Fetch or paste the listing", "Fetch or paste the Journal", "Paste only the bank's cash book listing",
       "f\"Paste the {db._listed(mons)}"]
left = [(n, w) for n, t in texts.items() for w in old if w in t]
check("no message still says to paste a listing Fetch reads", not left, left)
check("the new wording names Fetch and the SQL import page",
      "Fetch SQL's cash book listing" in texts["recon.py"] and "on the SQL import page" in texts["nextup.py"]
      and "Fetch SQL's latest listings on the SQL import page" in texts["db.py"])

# ---------- 10. a review's findings ----------

from hrp import recon  # noqa: E402

# a. Only a total's own label, and only a real currency code, is taken for the report's currency.
for words in ("Total Parts (Sdn) Bhd", "Total Outstanding (Sdn)", "Total (Pte) Ltd", "Total (USD) payable to Example"):
    try:
        sqlreport.refuse_currency([["x"], [words]], None, "listing")
        why = None
    except sqlreport.ReportError as x:
        why = str(x)
    check(f"a document's own text '{words}' is not taken for the currency", why is None, why)
rows = [["Payment Voucher Listing"], ["Page 1 of 1"], ["Doc Date", "Doc No", "Description", "Amount (MYR)"],
        [date(2026, 10, 1), "PV2610-009", "Total Parts (Sdn) Bhd", 10.0], [None, None, "Total (MYR) :", 10.0]]
try:
    sqlreport.listing(rows, {})
    why = None
except sqlreport.ReportError as x:
    why = str(x)
check("a ringgit listing paying Total Parts (Sdn) Bhd is not refused for its currency", not why or "ringgit" not in why, why)
for label in ("Total (SGD) :", "Total  (USD) :", "Grand Total Amount (USD)", "Total Amount (EUR):"):
    try:
        sqlreport.refuse_currency([["x"], [label, 1.0]], None, "listing")
        why = None
    except sqlreport.ReportError as x:
        why = str(x)
    check(f"a total labelled '{label}' is still refused", why and "not ringgit (MYR)" in why, why)

# b. A large workbook SQL Account didn't write is left alone, as one that is no listing.
other_dir = tmp / "big-other"
other_dir.mkdir()
budget = io.BytesIO()
with zipfile.ZipFile(budget, "w") as z:
    z.writestr("xl/workbook.xml", '<workbook><bookViews><workbookView windowWidth="21075"/></bookViews></workbook>')
    z.writestr("xl/sharedStrings.xml", "<sst><si><t>Budget 2027</t></si><si><t>Rent</t></si></sst>")
save("Budget 2027.xlsx", budget.getvalue(), folder=other_dir)
save("Huge journal.xlsx", jot([("Bank Journal", [PV10])], ("01/10/2026", "31/10/2026")), folder=other_dir)
sqlfetch.MAX_BYTES = 100
try:
    with db.connect() as con:
        g = sqlfetch.gather(con, EID, other_dir)
finally:
    sqlfetch.MAX_BYTES = keep
check("a large budget workbook is counted as not a listing, with no advice to export a shorter period",
      g["other"] == 1 and [f["name"] for f in g["files"]] == ["Huge journal.xlsx"] and g["files"][0]["status"] == "too_large", g)

# c. A voucher confirmed as deleted in SQL leaves the bank reconciliation.
write("October's bank reconciliation signed off",
      ("""INSERT INTO statements (account_id, month, opening, closing, imported_at, reconciled_at, reconciled_how)
          VALUES (?, '2026-10', 0, 0, ?, ?, 'manual')""", (ACCT, db.now(), db.now())))
listing(("PV2610-077", "2026-10-16", 999.0, "payment", "PV", "out"))


def october():
    with db.connect() as con:
        ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone())
        return recon.movements(con, ent, recon.cash_book_account(con, EID), "2026-10")


before = october()
check("a voucher SQL's journal doesn't have counts in October's books until it is confirmed",
      any(i["ref"] == "PV2610-077" and i["amount"] == -999.0 for i in before["items"]), before["items"])
o = j("get", f"/api/sql/entries?entity={EID}")["ledger"]["orphans"]
pv77 = next(x for x in o["not_in_journal"] if x["doc_no"] == "PV2610-077")
check("the orphan card offers it as deleted in SQL", pv77["can_confirm"] is True, pv77)
res = j("post", "/api/sql/entries/deleted", json={"ids": pv77["ids"]})
after = october()
check("once confirmed, it is out of October's bank reconciliation",
      not any(i["ref"] == "PV2610-077" for i in after["items"]) and round(before["out"] - after["out"], 2) == 999.0
      and after["listing"] is True, (before["out"], after["out"]))
check("the confirmation says the signed-off month it moved", [m["month"] for m in res["recon_changed"]] == ["2026-10"]
      and res["recon_changed"][0]["before"]["out"] == before["out"] and res["recon_changed"][0]["after"]["out"] == after["out"], res)
check("and the activity log says so", any("as deleted in SQL for AISB: bank reconciliation changed for signed-off 2026-10" in x["what"]
                                          for x in q("SELECT what FROM activity")))
check("only the confirmed entry is marked (an ignored correction SQL still has keeps counting)",
      q("SELECT deleted_in_sql FROM sql_entries WHERE doc_no = 'PV2610-077'")[0]["deleted_in_sql"]
      and all(r["deleted_in_sql"] is None for r in q("SELECT deleted_in_sql FROM sql_entries WHERE doc_no NOT IN ('PV2610-077', 'JV2610-001')")))
u = j("post", f"/api/sql/entries/{pv77['ids'][0]}/unignore", json={})
back = october()
check("Un-ignore brings it back into the bank reconciliation, and says the month moved",
      back["out"] == before["out"] and [m["month"] for m in u["recon_changed"]] == ["2026-10"]
      and q("SELECT status, deleted_in_sql FROM sql_entries WHERE doc_no = 'PV2610-077'")[0] == {"status": "unlinked", "deleted_in_sql": None}, u)
check("the page says it after the toast", "reconMoved(r)" in (config.PROGRAM_DIR / "static" / "app.js").read_text(encoding="utf-8"))
j("post", "/api/sql/entries/deleted", json={"ids": pv77["ids"]})
check("confirmed again, out again", october()["out"] == after["out"])

# d. A voucher listed on several rows is confirmed whole or not at all.
listing(("PV2610-088", "2026-10-17", 30.0, "payment", "PV", "out"), ("PV2610-088", "2026-10-17", 20.0, "payment", "PV", "out"))
o = j("get", f"/api/sql/entries?entity={EID}")["ledger"]["orphans"]
pv88 = next(x for x in o["not_in_journal"] if x["doc_no"] == "PV2610-088")
r = call("post", "/api/sql/entries/deleted", json={"ids": pv88["ids"][:1]})
check("confirming one of its two rows is refused in a plain sentence, nothing changed",
      len(pv88["ids"]) == 2 and r.status_code == 400 and "PV2610-088 is listed on several rows" in r.get_json()["error"]
      and [x["status"] for x in q("SELECT status FROM sql_entries WHERE doc_no = 'PV2610-088'")] == ["unlinked", "unlinked"], r.data[:300])
res = j("post", "/api/sql/entries/deleted", json={"ids": pv88["ids"]})
check("both rows together are confirmed", res["doc_nos"] == ["PV2610-088"]
      and [x["status"] for x in q("SELECT status FROM sql_entries WHERE doc_no = 'PV2610-088'")] == ["ignored", "ignored"])

# e. The Books pages open on the newest day SQL's reports kept reach, not only the latest trial balance's.
NOV = ("PV2611-001", "05/11/2026", [("900-E002", "ELECTRICITY", "Electricity Oct", 40.0, 0), (*BANK, "Electricity Oct", 0, 40.0)])
save("jot-c.xlsx", jot([("Bank Journal", [PV9, PV10, NOV]), ("General Journal", [JV2]), ("Cash Sales Journal", [CS])],
                       ("01/09/2026", "14/11/2026")))
fetch()
check("November's voucher is kept", q("SELECT state FROM ledger_docs WHERE doc_no = 'PV2611-001'")[0]["state"] == "current")
with db.connect() as con:
    check("the default To date is the end of the later journal, past the trial balance's 31 October",
          books.default_to(con, EID, date(2026, 11, 15)) == "2026-11-14", books.default_to(con, EID, date(2026, 11, 15)))
    check("still never after today", books.default_to(con, EID, date(2026, 11, 10)) == "2026-11-10")
day = min("2026-11-14", date.today().isoformat())
d = j("get", f"/api/books/trial-balance?entity={EID}")
check("the Trial balance tab opens with November's documents, and says it needs SQL's trial balance as at that day",
      (d["from"], d["to"]) == ("2026-09-01", day) and d["check"]["outcome"] == "skipped"
      and f"No trial balance of SQL's as at {date.fromisoformat(day):%d/%m/%Y} is kept" in d["check"]["text"],
      (d["from"], d["to"], d["check"]["text"]))
check("the balance sheet opens on that day too", j("get", f"/api/books/balance-sheet?entity={EID}")["as_at"] == day)

# f. A full Setup export always imports: a statutory account whose account only SQL's lines name stays out, said.
cs = q("SELECT id FROM ledger_docs WHERE doc_no = 'CS2610-001' AND state = 'current'")[0]["id"]
write("an account line naming an account the chart lacks",
      ("INSERT INTO ledger_lines (doc_id, entity_id, seq, account_code, account_name) VALUES (?, ?, 99, '420-9999', 'SOCSO PAYABLE')", (cs, EID)))
with db.connect() as con:
    con.arm("user", "test: a statutory account on an account SQL's lines name")
    masters.create(con, "statutory_accounts", {"kind": "socso", "label": "SOCSO (PERKESO)", "payable_code": "420-9999",
                                               "due_day": 15}, entity_id=EID)
    con.commit()
    con.disarm()
    data = setupfile.export(con, "full")
check("the export leaves it out and says why", [x["kind"] for x in data["statutory_accounts"]] == ["epf"]
      and len(data.get("left_out") or []) == 1 and "SOCSO (PERKESO) of AISB" in data["left_out"][0]
      and "420-9999 isn't in the company's chart of accounts" in data["left_out"][0], data.get("left_out"))
f_in, f_out = tmp / "setup-2.json", tmp / "imported-2.json"
f_in.write_text(json.dumps(data), encoding="utf-8")
run = subprocess.run([sys.executable, "-m", "synthetic_tests.stage1_settle_test", "--import", str(f_in), str(f_out)], cwd=root,
                     capture_output=True, text=True, timeout=600)
got = json.loads(f_out.read_text(encoding="utf-8")) if f_out.exists() else None
check("a new install imports the whole file, and is told what was left out", run.returncode == 0 and got
      and [x["kind"] for x in got["statutory"]] == ["epf"]
      and any(n.startswith("Left out of the file when it was made: Statutory account SOCSO (PERKESO)") for n in got["notes"]),
      (run.stdout[-800:], run.stderr[-800:], got))

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
