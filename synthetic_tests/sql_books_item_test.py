"""The SQL books checklist item (update 30, hrp/sqlbooks.py), on made-up records only.

A company kept in SQL Account gets the item "SQL books agree with SQL Account", due the 15th of the next month, from the
earliest month not filed and never before the first month tracked; a company kept here gets none. The app shows it done
from SQL's own reports, worked out each time: a GL Journal of Transaction covering the whole month, every listing entry
of the month in it and every document of the month in a listing, each document balancing and agreeing with its
listing, and SQL's trial balance agreeing with the books here. Each failing condition is said in a sentence. The
workbooks are built to the layout of the real exports (copied from books_test), with a made-up company, accounts,
documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.sql_books_item_test
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

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-books-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, checklistbook, config, db, nextup, rules, sqlbooks  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

# AISB has a checklist in the code (rules.CHECKLIST), so seed.json gives it one; AI is kept here (not in SQL).
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "AI", "name": "Example Kept Here Ltd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
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


def open_months(eid, *months):
    con = db.connect()
    con.arm("user", "test: months set up")
    try:
        for m in months:
            db.ensure_month(con, eid, m)
        con.commit()
    finally:
        con.disarm()
        con.close()


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


# ---------- 1. update 30 on records at update 29 ----------

full = db.MIGRATIONS[:]
check("update 30 is the SQL books item", len(full) >= 30 and full[29] is checklistbook.install_sql_books)
db.MIGRATIONS[:] = full[:29]
db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EID, AI = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("AISB", "AI"))
ACCT = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
# August was set up before the first month tracked was set (September); September is filed; October is open.
open_months(EID, "2026-08", "2026-09", "2026-10")
open_months(AI, "2026-10")
write("the first month tracked, September filed, the financial year from September, the bank's GL code",
      ("UPDATE entities SET first_month = '2026-09', fy_start = 9 WHERE id = ?", (EID,)),
      ("UPDATE months SET closed_at = '2026-10-12T10:00:00' WHERE entity_id = ? AND month = '2026-09'", (EID,)),
      ("UPDATE accounts SET gl_code = '310-1000' WHERE id = ?", (ACCT,)))
check("below update 30 no company has the item", not q("SELECT 1 FROM checklist_items WHERE code = 'sql-books'"))
old_items = q("SELECT * FROM checklist_items ORDER BY id")
old_terms = q("SELECT * FROM checklist_terms ORDER BY id")
untouched = q("SELECT * FROM tasks WHERE (entity_id = ? AND month IN ('2026-08', '2026-09')) OR entity_id = ? ORDER BY id", (EID, AI))

db.MIGRATIONS[:] = full
trail = db.init()
check("update 30 runs", q("PRAGMA user_version")[0]["user_version"] == len(full))
check("the checklist's items may now be shown done by SQL's books",
      "'books'" in q("SELECT sql FROM sqlite_master WHERE name = 'checklist_items'")[0]["sql"])
check("every item and term there before is kept as it was, with its id",
      q(f"SELECT * FROM checklist_items WHERE id <= {old_items[-1]['id']} ORDER BY id") == old_items
      and q(f"SELECT * FROM checklist_terms WHERE id <= {old_terms[-1]['id']} ORDER BY id") == old_terms)
item = q("SELECT * FROM checklist_items WHERE entity_id = ? AND code = 'sql-books'", (EID,))
term = item and q("SELECT * FROM checklist_terms WHERE item_id = ?", (item[0]["id"],))
check("the company kept in SQL gets the item, built in, shown done by SQL's books, from the earliest month not filed",
      len(item) == 1 and item[0]["completion"] == "books" and item[0]["system"] == 1 and len(term) == 1
      and term[0]["from_month"] == "2026-10" and term[0]["to_month"] is None and term[0]["in_use"] == 1, (item, term))
check("due the 15th of the next month, at the end of the checklist, asking for no document and no deadline outside",
      (term[0]["due_offset"], term[0]["due_day"], term[0]["docs"], term[0]["deadline"]) == (1, 15, "[]", 0)
      and term[0]["sort"] == 1 + max(t["sort"] for t in old_terms if t["item_id"] in {i["id"] for i in old_items if i["entity_id"] == EID})
      and term[0]["title"] == "SQL books agree with SQL Account" and term[0]["detail"] == rules.BOOKS_DETAIL, term)
check("the company kept here gets none", not q("SELECT 1 FROM checklist_items WHERE entity_id = ? AND code = 'sql-books'", (AI,)))
oct_task = q("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-10' AND code = 'sql-books'", (EID,))
check("the month set up and not filed gets the item, due 15 Nov",
      len(oct_task) == 1 and oct_task[0]["due_date"] == "2026-11-15" and oct_task[0]["done_at"] is None, oct_task)
check("the filed month, the month before the first month tracked and the company kept here are untouched",
      q("SELECT * FROM tasks WHERE (entity_id = ? AND month IN ('2026-08', '2026-09')) OR entity_id = ? ORDER BY id", (EID, AI)) == untouched)
check("the update says what it added in the activity log",
      any(r["what"] == "Checklist AISB: added SQL books agree with SQL Account, from October 2026" for r in q("SELECT what FROM activity"))
      and any(r["what"] == "Checklist AISB in October 2026: added SQL books agree with SQL Account, due 15 Nov 2026"
              for r in q("SELECT what FROM activity")), [r["what"] for r in q("SELECT what FROM activity")][-4:])
with db.connect() as con:
    v = audit.verify(con)
check("the audit trail checks out, with the new item recorded as added", v["ok"] and trail["outside"] == 0
      and q("SELECT 1 FROM audit_row WHERE tbl = 'checklist_items' AND op = 'insert' AND row_key = ?", (str(item[0]["id"]),)), (v, trail))
check("the items' audit triggers are back", len(q("""SELECT name FROM sqlite_master WHERE type = 'trigger'
                                                     AND tbl_name IN ('checklist_items', 'checklist_terms') AND name LIKE 'audit%'""")) >= 6)

# Run again (update 30 on records that have it): nothing more is added.
before = (q("SELECT * FROM checklist_items ORDER BY id"), q("SELECT * FROM checklist_terms ORDER BY id"), q("SELECT * FROM tasks ORDER BY id"))
with sqlite3.connect(config.DB_PATH) as r:
    r.execute("PRAGMA user_version = 29")
db.init()
check("update 30 run again adds nothing", (q("SELECT * FROM checklist_items ORDER BY id"), q("SELECT * FROM checklist_terms ORDER BY id"),
                                           q("SELECT * FROM tasks ORDER BY id")) == before)

# A month set up later gets the item; a month before the first month tracked is never asked.
open_months(EID, "2026-11")
nov = q("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-11' AND code = 'sql-books'", (EID,))
check("a month set up after the update gets the item", len(nov) == 1 and nov[0]["due_date"] == "2026-12-15", nov)
with db.connect() as con:
    ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone())
    aug = con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-08' AND code = 'inputs'", (EID,)).fetchone()
    check("a month before the first month tracked is never asked",
          not any(t["code"] == "sql-books" for t in checklistbook.get(con).checklist(ent, "2026-08"))
          and sqlbooks.month_check(con, ent, "2026-08") == (None, None) and db.task_flag(con, ent, aug, "2026-12-01") is None)
    ai = dict(con.execute("SELECT * FROM entities WHERE id = ?", (AI,)).fetchone())
    check("a company kept here has nothing to check", sqlbooks.month_check(con, ai, "2026-10")[0] is None)

# Setup: the item is shown with its kind, its due day can be changed from a month on, and a company kept here can't add it.
v = j("get", f"/api/setup/checklist?entity={EID}")
mine = next((x for x in v["items"] if x["code"] == "sql-books"), None)
check("Setup lists the item, built in, with how it is shown done",
      mine and mine["completion"] == "books" and mine["system"] == 1 and not mine["can_delete"]
      and any(x["key"] == "books" and x["code"] == "sql-books" for x in v["completions"]) and v["uses_sql"] is True, mine)
f = {"title": mine["now"]["title"], "detail": mine["now"]["detail"], "due_offset": 1, "due_day": 20, "docs": [], "deadline": 1}
res = j("post", "/api/setup/checklist", json={"action": "change", "entity_id": EID, "item_id": mine["id"], "from_month": "2026-11", "fields": f})
check("its due day is changed from November on, and never shown as a deadline outside the office",
      q("SELECT due_date FROM tasks WHERE entity_id = ? AND month = '2026-11' AND code = 'sql-books'", (EID,))[0]["due_date"] == "2026-12-20"
      and q("SELECT due_date FROM tasks WHERE entity_id = ? AND month = '2026-10' AND code = 'sql-books'", (EID,))[0]["due_date"] == "2026-11-15"
      and q("SELECT deadline FROM checklist_terms WHERE item_id = ? AND from_month = '2026-11'", (mine["id"],))[0]["deadline"] == 0, res)
r = c.post(BASE + "/api/setup/checklist", headers=H, json={"action": "add", "entity_id": AI, "from_month": "2026-11",
                                                          "fields": {"completion": "books", "title": "Books", "due_offset": 1, "due_day": 15}})
check("a company kept here can't add an item shown done by SQL's books", r.status_code >= 400
      and "aren't kept in SQL Account" in (r.get_json() or {}).get("error", ""), r.data[:300])
res = j("post", "/api/setup/entities", json={"fields": {"code": "EXN", "name": "Example New Sdn Bhd"}, "reason": "test"})
res2 = j("post", "/api/setup/entities", json={"fields": {"code": "EXK", "name": "Example New Kept Here Ltd", "uses_sql": False}, "reason": "test"})
codes = {e: [r["code"] for r in q("SELECT i.code FROM checklist_items i JOIN entities e ON e.id = i.entity_id WHERE e.code = ?", (e,))]
         for e in ("EXN", "EXK")}
check("a company added in Setup kept in SQL starts with the item; one kept here doesn't",
      "sql-books" in codes["EXN"] and codes["EXK"] and "sql-books" not in codes["EXK"], codes)


# ---------- 2. shown done by SQL's books, each condition in its own words ----------

def status(month="2026-10"):
    with db.connect() as con:
        ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone())
        t = con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? AND code = 'sql-books'", (EID, month)).fetchone()
        return db.task_status(con, ent, t)


def fetch():
    p = j("post", "/api/sql/preview", json={"entity_id": EID, "fetch": True})
    return j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("900-E002", "ELECTRICITY", "expense", None)]
write("the chart of accounts", *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, *a))
                                 for a in CHART])
BANK = ("310-1000", "BANK-EXAMPLE 0001")
PV9 = ("PV2609-001", "10/09/2026", [("900-E002", "ELECTRICITY", "Electricity Aug", 100.0, 0), (*BANK, "Electricity Aug", 0, 100.0)])
PV10 = ("PV2610-001", "15/10/2026", [("900-E002", "ELECTRICITY", "Electricity Sep", 200.0, 0), (*BANK, "Electricity Sep", 0, 200.0)])
PV11 = ("PV2610-002", "20/10/2026", [("900-E002", "ELECTRICITY", "Electricity extra", 300.0, 0), (*BANK, "Electricity extra", 0, 300.0)])
# SQL's trial balance from 1 September (the year start) to 31 October: right, and one with the bank 50.00 off.
TB = [("100-0000", "SHARE CAPITAL", (0, 10000.0), (0, 0), (0, 0), (0, 10000.0)),
      ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 600.0), (0, 500.0), (9400.0, 0)),
      ("900-E002", "ELECTRICITY", (0, 0), (600.0, 0), (500.0, 0), (600.0, 0))]
TB_OFF = [TB[0], ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 550.0), (0, 450.0), (9450.0, 0)),
          ("900-E002", "ELECTRICITY", (0, 0), (550.0, 0), (450.0, 0), (550.0, 0))]

s = status()
check("with nothing fetched it says to fetch both reports up to the month's last day",
      s["done"] is False and s["auto"] is False and s["why"] == "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least 31 Oct 2026."
      and s["lacking"] == [s["why"]], s)
save("1.xlsx", jot([("Bank Journal", [PV9, PV10])], ("01/09/2026", "15/10/2026")))
fetch()
check("a journal not covering the whole month counts as none while no trial balance is kept either",
      status()["why"] == "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least 31 Oct 2026.", status())
save("2.xlsx", trial_balance(TB_OFF, "01/09/2026", "31/10/2026"))
fetch()
check("with the trial balance kept, it asks for a journal over the whole month",
      status()["why"] == "Fetch SQL's GL Journal of Transaction for the whole of October 2026 (from 1 Oct to 31 Oct 2026): no journal "
                         "fetched covers the whole month.", status())
# The rest of the month fetched as a journal of its own: the two reads run on from each other with no day missing, so
# together they cover October.
save("3.xlsx", jot([("Bank Journal", [PV11])], ("16/10/2026", "31/10/2026")))
fetch()
with db.connect() as con:
    check("two journal reads running on from each other are joined into one span",
          sqlbooks.journal_spans(con, EID) == [("2026-09-01", "2026-10-31")], sqlbooks.journal_spans(con, EID))
check("journals fetched in two parts that together cover the month count as covering it",
      "no journal fetched covers the whole month" not in status()["why"], status())
imp = [0]


def listing(*rows):
    """SQL's listing of payment vouchers pasted (an import of its own): rows (doc no, date, amount, status)."""
    imp[0] += 1
    con = db.connect()
    con.arm("user", "test: a listing pasted")
    try:
        iid = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, ?, 0)",
                          (EID, f"listing-{imp[0]}.xlsx", db.now(), len(rows))).lastrowid
        for no, d, amount, st in rows:
            con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction,
                           doc_type, kind, status) VALUES (?, ?, ?, ?, 'Electricity', 'EXAMPLE POWER', ?, 'out', 'PV', 'payment', ?)""",
                        (iid, EID, no, d, amount, st))
        con.commit()
    finally:
        con.disarm()
        con.close()


listing(("PV2610-003", "2026-10-25", 50.0, "unlinked"))
check("a listing entry of the month not in the journal is named",
      status()["why"] == "1 document of October 2026 in SQL's listings is missing from SQL's GL Journal of Transaction (PV2610-003): "
                         "fetch the journal for October 2026 again, or check it in SQL.", status())
write("the entry ignored", ("UPDATE sql_entries SET status = 'ignored' WHERE doc_no = 'PV2610-003'", ()))
check("documents of the month in the journal with no listing are named, not September's",
      status()["why"] == "2 documents of October 2026 in SQL's GL Journal of Transaction have no listing (PV2610-001, PV2610-002): "
                         "fetch or paste SQL's listing for October 2026.", status())
listing(("PV2609-001", "2026-09-10", 100.0, "unlinked"), ("PV2610-001", "2026-10-15", 200.0, "unlinked"),
        ("PV2610-002", "2026-10-20", 350.0, "unlinked"))
why = status()["why"]
check("a document not agreeing with its listing is named with what differs",
      why.startswith("PV2610-002 doesn't balance or agree with its listing: The lines on the bank account have credits of 300.00")
      and "the listing has 350.00 money out" in why and why.endswith("Open it on the SQL page or Accounting › Books to see its lines."), why)
listing(("PV2610-002", "2026-10-20", 300.0, "unlinked"))
why = status()["why"]
check("SQL's trial balance not agreeing is said, with what differs and where to look",
      why.startswith("2 accounts differ from SQL's trial balance as at 31/10/2026") and "See Accounting › Books › Trial balance" in why
      and status()["done"] is False, why)
keep = sqlbooks.nearest_tb
sqlbooks.nearest_tb = lambda con, eid, last: None  # as if no trial balance as at the month's end or later were kept
try:
    check("with no trial balance as at the month's end or later it asks for one",
          status()["why"] == "Fetch SQL's Trial Balance up to at least 31 Oct 2026.", status())
finally:
    sqlbooks.nearest_tb = keep

# Next up, on a day after the due date: the item is among the month's overdue checklist items (rule 10).
with db.connect() as con:
    rows = nextup.items(con, date(2026, 11, 20), EID)
books_id = oct_task[0]["id"]
listed = [r for r in rows if r["rule"] == 10 and books_id in (r["go"].get("task_ids") or [r["go"].get("task_id")])]
check("overdue and not done, it is in Next up with the month's other checklist items",
      len(listed) == 1 and listed[0]["state"] == "overdue" and listed[0]["month"] == "2026-10", [(r["rule"], r["text"]) for r in rows])

save("4.xlsx", trial_balance(TB, "01/09/2026", "31/10/2026", stamp="14/11/2026 2:10:00 AM ADMIN"))
fetch()
s = status()
check("with all four holding it is shown done by the app, saying why",
      s["done"] is True and s["auto"] is True and s["lacking"] == []
      and s["why"] == "Done: SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at "
                      "31 Oct 2026 agrees with the books here", s)
check("nothing is ticked: it is worked out from the records",
      q("SELECT done_at FROM tasks WHERE id = ?", (books_id,))[0]["done_at"] is None)
with db.connect() as con:
    rows = nextup.items(con, date(2026, 11, 20), EID)
check("once done it leaves Next up", not any(books_id in (r["go"].get("task_ids") or [r["go"].get("task_id")]) for r in rows))
m = j("get", f"/api/month?entity={EID}&month=2026-10")
t = next(x for x in m["tasks"] if x["code"] == "sql-books")
check("the month page shows it done by the app", t["done"] is True and t["auto"] is True and t["flag"] is None and t["why"].startswith("Done: "), t)
check("November isn't done: neither report reaches its last day",
      status("2026-11")["why"] == "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least 30 Nov 2026.", status("2026-11"))

# October is filed, then SQL's trial balance as at 30 Nov is fetched before November's journal (the usual order mid
# cycle), with a November electricity bill of 70.00 the books here don't have yet. October has its own trial balance as
# at 31 Oct, which still agrees, so it stays done: the later one is never read for it.
j("post", "/api/months/close", json={"entity_id": EID, "month": "2026-10", "closed": True})
TB_NOV = [TB[0], ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 670.0), (0, 70.0), (9330.0, 0)),
          ("900-E002", "ELECTRICITY", (0, 0), (670.0, 0), (70.0, 0), (670.0, 0))]
save("5.xlsx", trial_balance(TB_NOV, "01/09/2026", "30/11/2026", stamp="14/11/2026 3:00:00 AM ADMIN"))
fetch()
s = status()
check("a filed month stays done when a later trial balance that differs is fetched",
      s["done"] is True and s["auto"] is True and "as at 31 Oct 2026 agrees" in s["why"], s)
m = j("get", f"/api/month?entity={EID}&month=2026-10")
check("and the month page still shows it done", next(x for x in m["tasks"] if x["code"] == "sql-books")["done"] is True)
with db.connect() as con:
    check("the trial balance read for October is the one nearest its end", sqlbooks.nearest_tb(con, EID, "2026-10-31")["period_to"] == "2026-10-31")
    check("November's is the one as at 30 Nov", sqlbooks.nearest_tb(con, EID, "2026-11-30")["period_to"] == "2026-11-30")
    nov_tb = sqlbooks.nearest_tb(con, EID, "2026-11-30")
    ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone())
    check("November, with no journal for it yet, asks for the journal over the whole month",
          sqlbooks.month_check(con, ent, "2026-11")[1].startswith("Fetch SQL's GL Journal of Transaction for the whole of November 2026"))
sqlbooks.nearest_tb = lambda con, eid, last: nov_tb  # as if October had no trial balance of its own, only the one as at 30 Nov
try:
    with db.connect() as con:
        ok, why = sqlbooks.month_check(con, ent, "2026-10")
    check("a trial balance as at a day the journals don't reach is never compared: it says what to fetch",
          ok is False and why == "The nearest trial balance of SQL's kept is as at 30 Nov 2026, but the journals fetched stop before "
                                 "then: fetch SQL's Trial Balance as at 31 Oct 2026, or its GL Journal of Transaction up to 30 Nov 2026.", why)
finally:
    sqlbooks.nearest_tb = keep

# A person can still tick it by hand, as any other item shown done by the records.
nov_id = nov[0]["id"]
j("post", f"/api/tasks/{nov_id}", json={"done": True})
check("ticked by hand it counts as done, and the log keeps what was lacking",
      status("2026-11")["done"] is True and status("2026-11")["auto"] is False
      and any(r["what"].startswith("Ticked task: SQL books agree with SQL Account (2026-11), although: Fetch SQL's GL Journal")
              for r in q("SELECT what FROM activity")))

# Filed months are never changed by the update, run once more on records with September filed.
filed = q("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-09' ORDER BY id", (EID,))
with sqlite3.connect(config.DB_PATH) as r:
    r.execute("PRAGMA user_version = 29")
db.init()
check("the filed month is still as it was after the update runs again",
      q("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-09' ORDER BY id", (EID,)) == filed
      and not any(x["code"] == "sql-books" for x in filed))
with db.connect() as con:
    check("and the audit trail checks out", audit.verify(con)["ok"])

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
