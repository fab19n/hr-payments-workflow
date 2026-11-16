"""Fetch and checks: the small gaps closed on the SQL page and the Books page, on made-up records only.

1. An export whose printed company matches no company in Setup is never taken on a guess, even with one company kept in
   SQL: Fetch lists it as from a company not in Setup, with its name, and nothing from it is kept until the owner clicks
   Take it for <company> (kept, logged and in the audit trail). The next fetch then takes it.
2. The size limits agree (Fetch's, the reader's and the upload's), and a listing in another currency is refused.
3. A voucher edited in SQL and fetched again with another amount or date: one whose earlier entry is linked to a
   payment is shown as changed in SQL and nothing moves until the owner clicks Move the link to the new amount (the
   payment's amount changes too only when asked); one whose earlier entry is linked to nothing simply replaces it, so it
   isn't listed twice. The earlier entries are kept, marked superseded; SQL's books (the ledger's versions) are untouched.
4. The check against SQL's trial balance says when the trial balance and the latest journal were read, and when the
   journal was read in a later fetch, says to export the trial balance again and shows the differences as possibly out
   of date. The Books page opens on the latest day SQL's reports kept reach.

The workbooks are built to the layout of the real exports (copied from stage1_settle_test), with made-up companies,
accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.fetch_checks_test
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

tmp = Path(tempfile.mkdtemp(prefix="hrp-fetch-checks-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, sqlfetch, sqlreport  # noqa: E402
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
STRANGER = "STRANGER TRADING SDN BHD (209901000009 (9999999-Z))"
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
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
    finally:
        con.disarm()
        con.close()


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


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


def jot(sections, period, cur="MYR", company=COMPANY, stamp=STAMP):
    """A GL Journal of Transaction (cur: the currency its headings name). sections: [(label, [(doc no, dd/mm/yyyy, [(code, name, description, dr, cr)])])]."""
    s = Sheet()
    s.row((0, "Date"), (1, ":"), (2, 3, f"From {period[0]} to {period[1]}"), (7, stamp))
    s.row((0, "Sort By"), (1, ":"), (2, 3, "PostDate;Ref1"))
    s.row((0, 5, company), (7, 8, "Page 1 of 1"))
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


def save(name, data):
    """A file in the downloads folder, each one saved a minute after the one before."""
    SAVED[0] += 1
    p = FOLDER / name
    p.write_bytes(data)
    t = datetime(2026, 11, 14, 9, 0).timestamp() + SAVED[0] * 60
    os.utime(p, (t, t))
    return p


def preview():
    return j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})


def fetch():
    p = preview()
    return j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


EID = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("900-E002", "ELECTRICITY", "expense", None)]
write("the chart of accounts", *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, *a))
                                 for a in CHART])
BANK = ("310-1000", "BANK-EXAMPLE 0001")
PV1 = ("PV2610-001", "15/10/2026", [("900-E002", "ELECTRICITY", "Electricity Sep", 1000.0, 0), (*BANK, "Electricity Sep", 0, 1000.0)])
TB = [("100-0000", "SHARE CAPITAL", (0, 10000.0), (0, 0), (0, 0), (0, 10000.0)),
      ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 0), (0, 0), (10000.0, 0))]

# ---------- 0. SQL's trial balance, fetched first ----------

save("tb.xlsx", trial_balance(TB, "01/10/2026", "31/10/2026"))
fetch()
check("SQL's trial balance of the company is fetched", len(q("SELECT id FROM ledger_batches WHERE report = 'trial_balance'")) == 1)

# ---------- 1. an export from a company not in Setup ----------

save("stranger.xlsx", jot([("Bank Journal", [PV1])], ("01/10/2026", "31/10/2026"), company=STRANGER))
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "stranger.xlsx")
check("with one company kept in SQL, an export from a company not in Setup is not taken on a guess",
      f["status"] == "unknown_company" and p.get("nothing_new") and "from a company not in Setup" in f["reason"]
      and "STRANGER TRADING SDN BHD" in f["reason"] and f.get("take_for") == "EXH" and f.get("company") == STRANGER, f)
check("nothing from it reaches the SQL entries or the ledger",
      not q("SELECT id FROM ledger_batches WHERE report = 'journal'") and not q("SELECT id FROM ledger_docs")
      and not q("SELECT id FROM sql_entries"))
r = c.post(BASE + "/api/sql/take-company", headers=H, json={"entity_id": EID, "company": COMPANY})
check("a name that already matches a company in Setup isn't taken", r.status_code == 400 and "already matches EXH" in r.get_json()["error"],
      r.get_json())
r = c.post(BASE + "/api/sql/take-company", headers=H, json={"entity_id": EID, "company": "  "})
check("an empty name isn't taken", r.status_code == 400, r.get_json())
check("an owner's refusal leaves no name kept", not q("SELECT id FROM sql_company_names"))
res = j("post", "/api/sql/take-company", json={"entity_id": EID, "company": STRANGER})
kept = q("SELECT * FROM sql_company_names")
check("Take it for EXH keeps the printed name with the company", res["added"] and len(kept) == 1 and kept[0]["entity_id"] == EID
      and kept[0]["name"] == STRANGER, kept)
check("the click is in the activity log and the audit trail",
      any("Took SQL's exports printed for \"STRANGER TRADING SDN BHD" in a["what"] for a in q("SELECT what FROM activity"))
      and q("SELECT id FROM audit_row WHERE tbl = 'sql_company_names' AND op = 'insert'"))
check("taking it again changes nothing", j("post", "/api/sql/take-company", json={"entity_id": EID, "company": STRANGER})["added"] is False
      and len(q("SELECT id FROM sql_company_names")) == 1)
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "stranger.xlsx")
check("the next fetch reads it for EXH", f["status"] == "read" and f.get("report") == "journal", f)
j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
docs = q("SELECT doc_no, version, state, dr_sen FROM ledger_docs")
check("once imported, its account lines are kept", docs == [{"doc_no": "PV2610-001", "version": 1, "state": "current", "dr_sen": 100000}], docs)

# ---------- 2. the limits, and another currency ----------

check("the size limits agree: the reader's, Fetch's and the upload's",
      sqlfetch.MAX_BYTES == sqlreport.MAX_BYTES and sqlreport.MAX_PART >= sqlreport.MAX_BYTES
      and app.config["MAX_CONTENT_LENGTH"] >= sqlfetch.MAX_BYTES)
rows = [["Payment Voucher Listing"], ["EXAMPLE HOLDINGS SDN BHD", "Page 1 of 1"], ["Doc Date", "Doc No", "Description", "Amount (USD)"],
        [date(2026, 10, 1), "PV2610-009", "EXAMPLE SUPPLIER", 10.0]]
try:
    sqlreport.listing(rows, {})
    why = None
except sqlreport.ReportError as x:
    why = str(x)
check("a listing whose amounts are headed Amount (USD) is refused with a sentence, never read as ringgit",
      why and "in USD, not ringgit (MYR)" in why, why)

# ---------- 4. the trial balance read before a later journal ----------

d = j("get", f"/api/books/trial-balance?entity={EID}")
check("the Books page opens on the latest day SQL's reports kept reach", d["to"] == "2026-10-31", d["to"])
ch = d["check"]
check("the accounts differ, and the check says when the trial balance and the latest journal were read",
      ch["outcome"] == "warn" and ch["text"].startswith("2 accounts differ from SQL's trial balance as at 31/10/2026")
      and "SQL's trial balance was read on " in ch["text"] and "the latest GL Journal of Transaction for these dates on " in ch["text"], ch["text"])
check("the journal was read in a later fetch: the differences may be out of date, and the trial balance is to be exported again",
      ch["stale"] is True and "may be out of date rather than errors" in ch["text"]
      and "export SQL's Trial Balance again for the same dates (01/10/2026 to 31/10/2026) and Fetch it" in ch["text"]
      and all(x.get("possibly_stale") for x in ch["differences"]), ch)
save("tb again.xlsx", trial_balance(TB, "01/10/2026", "31/10/2026", stamp="14/11/2026 2:00:00 AM ADMIN"))
fetch()
ch = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-10-01&to=2026-10-31")["check"]
check("a trial balance fetched after the journal: real differences, not out of date",
      ch["outcome"] == "warn" and ch["stale"] is False and "may be out of date" not in ch["text"]
      and "SQL's trial balance was read on " in ch["text"] and not any(x.get("possibly_stale") for x in ch["differences"]), ch)
save("journal unchanged.xlsx", jot([("Bank Journal", [PV1])], ("01/10/2026", "31/10/2026"), stamp="14/11/2026 3:00:00 AM\nADMIN"))
fetch()
check("a fresh export of the same journal, nothing changed in it, is read as a later fetch",
      len(q("SELECT id FROM ledger_batches WHERE report = 'journal'")) == 2
      and q("SELECT version, state FROM ledger_docs WHERE doc_no = 'PV2610-001'") == [{"version": 1, "state": "current"}])
ch = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-10-01&to=2026-10-31")["check"]
check("a journal read again with nothing changed leaves the differences as real ones, not out of date",
      ch["outcome"] == "warn" and ch["stale"] is False and "may be out of date" not in ch["text"]
      and not any(x.get("possibly_stale") for x in ch["differences"]), ch)
PV9 = ("PV2610-009", "20/10/2026", [("900-E002", "ELECTRICITY", "Electricity deposit", 50.0, 0), (*BANK, "Electricity deposit", 0, 50.0)])
save("journal changed.xlsx", jot([("Bank Journal", [PV1, PV9])], ("01/10/2026", "31/10/2026"), stamp="14/11/2026 3:30:00 AM\nADMIN"))
fetch()
ch = j("get", f"/api/books/trial-balance?entity={EID}&from=2026-10-01&to=2026-10-31")["check"]
check("a later journal that adds a document in the trial balance's dates makes the differences possibly out of date",
      ch["stale"] is True and all(x.get("possibly_stale") for x in ch["differences"]), ch)

# ---------- 3. vouchers edited in SQL and fetched again ----------

BANK_NAME = "BANK-EXAMPLE 0001"


def packet(rows):
    def attrs(r):
        return " ".join('%s="%s"' % (k, v) for k, v in r.items())
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % attrs(r) for r in rows) + "</ROWDATA></DATAPACKET>")


def pv(no, key, day, amount, desc):
    return {"DOCKEY": key, "DOCNO": no, "DOCTYPE": "PV", "DOCDATE": day, "DESCRIPTION": desc, "DOCAMT": f"{amount:.2f}",
            "CANCELLED": "FALSE", "PAYMENTMETHODDESC": BANK_NAME, "DR": "0.00", "CR": f"{amount:.2f}"}


def paste(*rows):
    pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": packet(rows)})
    return j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})


def entry(no, amount):
    return q("SELECT * FROM sql_entries WHERE doc_no = ? AND amount = ?", (no, amount))[0]


def page():
    return j("get", f"/api/sql/entries?entity={EID}")


first = paste(pv("PV2610-001", "501", "20261015", 1000.0, "EXAMPLE POWER"), pv("PV2610-002", "502", "20261016", 300.0, "EXAMPLE WATER"),
              pv("PV2610-003", "503", "20261017", 500.0, "EXAMPLE RENT"))
check("three vouchers are imported", first["added"] == 3 and "replaced" not in first, first)
for no, amount in (("PV2610-001", 1000.0), ("PV2610-003", 500.0)):
    j("post", f"/api/sql/entries/{entry(no, amount)['id']}", json={"create_payment": {}})
P1, P3 = entry("PV2610-001", 1000.0)["payment_id"], entry("PV2610-003", 500.0)["payment_id"]
pay = lambda pid: q("SELECT * FROM payments WHERE id = ?", (pid,))[0]  # noqa: E731
check("payments are made from PV2610-001 and PV2610-003, at the vouchers' amounts",
      P1 and P3 and pay(P1)["amount"] == 1000.0 and pay(P3)["amount"] == 500.0 and pay(P3)["paid_date"] == "2026-10-17")
ledger_before = q("SELECT * FROM ledger_docs ORDER BY id")

again = paste(pv("PV2610-001", "501", "20261015", 1200.0, "EXAMPLE POWER"), pv("PV2610-002", "502", "20261016", 350.0, "EXAMPLE WATER"),
              pv("PV2610-003", "503", "20261020", 450.0, "EXAMPLE RENT"))
check("fetched again after an edit in SQL: three new entries; the one linked to nothing replaces its earlier entry",
      again["added"] == 3 and again.get("replaced") == ["PV2610-002"] and again.get("changed_linked") == 2, again)
old2, new2 = entry("PV2610-002", 300.0), entry("PV2610-002", 350.0)
check("the earlier PV2610-002 is kept, marked superseded by the later one", old2["status"] == "superseded"
      and old2["superseded_by"] == new2["id"] and old2["superseded_at"] and new2["status"] == "unlinked", (old2, new2))
d = page()
unl = [u["doc_no"] for u in d["unlinked"]]
check("PV2610-002 is listed once among the entries not linked", unl.count("PV2610-002") == 1
      and [x["doc_no"] for x in d["superseded"]] == ["PV2610-002"] and d["superseded"][0]["new_amount"] == 350.0, (unl, d["superseded"]))
check("the change is in the activity log",
      any("SQL entry PV2610-002 of EXH changed in SQL from 300.00 to 350.00" in a["what"] for a in q("SELECT what FROM activity")))
ch = {x["doc_no"]: x for x in d["changed"]}
c1, c3 = ch.get("PV2610-001"), ch.get("PV2610-003")
check("a linked voucher changed in SQL is shown as changed, from the old amount to the new",
      set(ch) == {"PV2610-001", "PV2610-003"} and c1["words"] == "from 1,000.00 to 1,200.00"
      and c1["old"]["id"] == entry("PV2610-001", 1000.0)["id"] and c1["new"]["id"] == entry("PV2610-001", 1200.0)["id"]
      and c1["payment"]["id"] == P1 and c1["amount_follows"] is True, ch)
check("a changed date is said too", c3["words"] == "from 500.00 to 450.00, dated 17/10/2026 before, 20/10/2026 now", c3["words"])
check("SQL's Journal of Transaction kept still has the old figure, and the page is told so",
      c1["ledger"] == {"version": 1, "total": 1000.0, "agrees": False} and c3["ledger"] is None, (c1["ledger"], c3["ledger"]))
check("nothing moved on its own: the payments are still linked to the earlier entries, at their amounts",
      entry("PV2610-001", 1000.0)["payment_id"] == P1 and entry("PV2610-001", 1200.0)["payment_id"] is None
      and pay(P1)["amount"] == 1000.0 and pay(P3)["amount"] == 500.0)

r = c.post(BASE + f"/api/sql/entries/{c1['old']['id']}/move-link", headers=H, json={"to": c3["new"]["id"], "update_amount": True})
check("a move to another voucher's entry is refused", r.status_code == 400 and "Reload the SQL page" in r.get_json()["error"], r.get_json())
mv = j("post", f"/api/sql/entries/{c1['old']['id']}/move-link", json={"to": c1["new"]["id"], "update_amount": True})
o1, n1 = entry("PV2610-001", 1000.0), entry("PV2610-001", 1200.0)
check("Move the link to the new amount moves the payment's link, and the amount too when asked",
      mv["amount_changed"] is True and n1["payment_id"] == P1 and n1["status"] == "linked" and o1["payment_id"] is None
      and o1["status"] == "superseded" and o1["superseded_by"] == n1["id"] and pay(P1)["amount"] == 1200.0, (o1, n1, pay(P1)))
mv3 = j("post", f"/api/sql/entries/{c3['old']['id']}/move-link", json={"to": c3["new"]["id"], "update_amount": False})
check("without the second choice the payment keeps its amount; the paid date taken from the voucher follows it",
      mv3["amount_changed"] is False and pay(P3)["amount"] == 500.0 and pay(P3)["paid_date"] == "2026-10-20"
      and entry("PV2610-003", 450.0)["payment_id"] == P3, pay(P3))
acts = [a["what"] for a in q("SELECT what FROM activity")]
check("each move, and the amount changed, is in the activity log",
      sum("Moved the link of payment" in a for a in acts) == 2
      and any("Changed the amount of payment" in a and "from 1,000.00 to 1,200.00" in a for a in acts), acts[-6:])
check("and in the audit trail", len(q("""SELECT id FROM audit_row WHERE tbl = 'sql_entries' AND op = 'update'
                                         AND row_key IN (?, ?)""", (str(o1["id"]), str(n1["id"])))) >= 2,
      q("SELECT tbl, row_key, op FROM audit_row WHERE tbl = 'sql_entries' ORDER BY id DESC LIMIT 6"))
d = page()
check("the SQL page no longer shows them as changed; each earlier entry is listed as replaced",
      d["changed"] == [] and sorted(x["doc_no"] for x in d["superseded"]) == ["PV2610-001", "PV2610-002", "PV2610-003"]
      and sorted(x["doc_no"] for x in d["linked"]) == ["PV2610-001", "PV2610-003"], (d["changed"], d["superseded"]))
check("SQL's books are untouched: the ledger's versions are as they were", q("SELECT * FROM ledger_docs ORDER BY id") == ledger_before)
r = c.post(BASE + f"/api/sql/entries/{o1['id']}/move-link", headers=H, json={"to": n1["id"]})
check("a link moved once can't be moved again", r.status_code == 400, r.get_json())

# ---------- a linked voucher edited twice in SQL before the owner moves its link ----------

paste(pv("PV2610-004", "504", "20261018", 2000.0, "EXAMPLE CLEANING"))
j("post", f"/api/sql/entries/{entry('PV2610-004', 2000.0)['id']}", json={"create_payment": {}})
P4 = entry("PV2610-004", 2000.0)["payment_id"]
paste(pv("PV2610-004", "504", "20261018", 2200.0, "EXAMPLE CLEANING"))
check("edited once: shown as changed in SQL", [x["words"] for x in page()["changed"] if x["doc_no"] == "PV2610-004"]
      == ["from 2,000.00 to 2,200.00"], page()["changed"])
twice = paste(pv("PV2610-004", "504", "20261018", 2300.0, "EXAMPLE CLEANING"))
e22, e23 = entry("PV2610-004", 2200.0), entry("PV2610-004", 2300.0)
d = page()
c4 = [x for x in d["changed"] if x["doc_no"] == "PV2610-004"]
check("edited again before the link was moved: the card goes straight from the linked entry to SQL's latest figure",
      len(c4) == 1 and c4[0]["words"] == "from 2,000.00 to 2,300.00" and c4[0]["old"]["id"] == entry("PV2610-004", 2000.0)["id"]
      and c4[0]["new"]["id"] == e23["id"] and c4[0]["payment"]["id"] == P4 and twice.get("changed_linked") == 1, (c4, twice))
check("the entry in between is replaced by the latest one, so it is never offered as not linked",
      e22["status"] == "superseded" and e22["superseded_by"] == e23["id"] and twice.get("replaced") == ["PV2610-004"]
      and e22["id"] not in {u["id"] for u in d["unlinked"]}
      and [u["id"] for u in d["unlinked"] if u["doc_no"] == "PV2610-004"] == [e23["id"]], (e22, d["unlinked"]))

from hrp import nextup  # noqa: E402
with db.connect() as con:
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
    loose = con.execute("SELECT id, doc_date, description FROM sql_entries WHERE entity_id = ? AND status = 'unlinked'", (EID,)).fetchall()
    worked = {nextup._entry_cycle(ent, x) for x in loose}
    got = nextup._in_sql(con, ent, worked, [], max(worked))
want = len(loose) - 1
check("Next Up counts the changed voucher's new entry as changed in SQL, not as not linked yet, as the SQL page does",
      got and f"{want} SQL entr{'ies' if want != 1 else 'y'} not linked yet" in got[0]["text"]
      and "1 voucher changed in SQL (move the link on the SQL page)" in got[0]["text"], (got, want))
mv4 = j("post", f"/api/sql/entries/{c4[0]['old']['id']}/move-link", json={"to": e23["id"], "update_amount": True})
check("the link moves straight to the latest figure", mv4["amount_changed"] is True and pay(P4)["amount"] == 2300.0
      and entry("PV2610-004", 2300.0)["payment_id"] == P4 and not [x for x in page()["changed"] if x["doc_no"] == "PV2610-004"])

# ---------- a voucher edited back in SQL to a figure it had before ----------

back = paste(pv("PV2610-002", "502", "20261016", 300.0, "EXAMPLE WATER"))
o300, o350 = entry("PV2610-002", 300.0), entry("PV2610-002", 350.0)
d = page()
check("linked to nothing, edited back to 300.00: the 300.00 entry is SQL's again and the 350.00 one is replaced by it",
      o300["status"] == "unlinked" and o300["superseded_by"] is None and o350["status"] == "superseded"
      and o350["superseded_by"] == o300["id"] and back.get("replaced") == ["PV2610-002"], (o300, o350, back))
check("it is listed once among the entries not linked, at SQL's figure",
      [(u["id"], u["amount"]) for u in d["unlinked"] if u["doc_no"] == "PV2610-002"] == [(o300["id"], 300.0)], d["unlinked"])
check("it is named in the activity log",
      any("SQL entry PV2610-002 of EXH is back at 300.00" in a["what"] for a in q("SELECT what FROM activity")))
back1 = paste(pv("PV2610-001", "501", "20261015", 1000.0, "EXAMPLE POWER"))
d = page()
c1b = [x for x in d["changed"] if x["doc_no"] == "PV2610-001"]
o1000 = entry("PV2610-001", 1000.0)
check("linked, edited back to 1,000.00: shown as changed in SQL, from the linked 1,200.00 to 1,000.00, nothing moved",
      back1.get("changed_linked") == 1 and len(c1b) == 1 and c1b[0]["words"] == "from 1,200.00 to 1,000.00"
      and c1b[0]["new"]["id"] == o1000["id"] and o1000["status"] == "unlinked" and pay(P1)["amount"] == 1200.0
      and entry("PV2610-001", 1200.0)["payment_id"] == P1, (c1b, back1))
mvb = j("post", f"/api/sql/entries/{c1b[0]['old']['id']}/move-link", json={"to": o1000["id"], "update_amount": True})
check("and the link can be moved back to it", mvb["amount_changed"] is True and pay(P1)["amount"] == 1000.0
      and entry("PV2610-001", 1000.0)["payment_id"] == P1 and entry("PV2610-001", 1200.0)["superseded_by"] == o1000["id"])
again = paste(pv("PV2610-001", "501", "20261015", 1000.0, "EXAMPLE POWER"))
check("fetched once more at the same figure, nothing changes", again["added"] == 0 and "replaced" not in again
      and "changed_linked" not in again and entry("PV2610-001", 1000.0)["payment_id"] == P1, again)
check("SQL's books are untouched by any of it: the ledger's versions are as they were",
      q("SELECT * FROM ledger_docs ORDER BY id") == ledger_before)

# ---------- the update step, on records from before it ----------

for n, amount in ((1, 10.0), (2, 12.0)):  # a voucher listed twice before update 36: in two imports, linked to nothing
    write("an earlier import", ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, 1, 0)",
                                (EID, f"before-{n}.xlsx", db.now())))
    iid = q("SELECT MAX(id) AS i FROM sql_imports")[0]["i"]
    write("an entry", ("INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, amount, direction, doc_type, kind, status) "
                       "VALUES (?, ?, 'PV2610-050', '2026-10-25', ?, 'out', 'PV', 'payment', 'unlinked')", (iid, EID, amount)))
con = db.connect()
con.arm("migration", "Update 36")
db.MIGRATIONS[35](con)
con.commit()
con.disarm()
con.close()
old50, new50 = entry("PV2610-050", 10.0), entry("PV2610-050", 12.0)
check("update 36 marks a voucher already listed twice as replaced by its later entry, and can run again",
      old50["status"] == "superseded" and old50["superseded_by"] == new50["id"] and new50["status"] == "unlinked"
      and [u["doc_no"] for u in page()["unlinked"]].count("PV2610-050") == 1)

with db.connect() as con:
    v = con.execute("PRAGMA user_version").fetchone()[0]
check("the records are at the latest update, 38", v == len(db.MIGRATIONS) == 38, v)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
