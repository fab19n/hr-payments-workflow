"""Stage 1 leftovers, on made-up records only.

1. Setup › Companies lists the company names SQL prints on its exports that the owner confirmed for the company with
   Take it for on the SQL page, each with when and by whom. Remove asks for a second click (saying the files are held
   again on the next Fetch), is in the activity log and the audit trail, and the next Fetch holds such files again.
   The names go in a full Setup export and come back with an import into a new install (this file run again with
   --import in a fresh records folder); a name that matches a company there refuses the whole import; a file made
   before the names were exported still imports.
2. The check against SQL's trial balance: a document marked no longer in SQL that a later GL Journal of Transaction
   finds again counts as a change after the trial balance, as one added, changed or found deleted does. The batch
   that found it again is kept on the document. Update 37 fills both from the audit trail for records before it. The
   SQL page and the audit pack's trial balance page say "possibly out of date" then, as the Books page does.
3. Replace on upload retires only a current document of the same payment or checklist item.
4. A new payroll cutoff day that would move an SQL document or a reminder in or out of a filed month is refused.
5. The README describes the stage 1 features and lists every synthetic test.

The workbooks are built to the layout of the real exports (copied from fetch_checks_test), with made-up companies,
accounts, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.stage1_leftovers_test
"""
import copy
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

tmp = Path(tempfile.mkdtemp(prefix="hrp-stage1-leftovers-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # part 1's new install: --import <setup.json> <what it holds afterwards>

from hrp import audit, books, config, db, sqlfetch  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

if not CHILD:
    (tmp / "seed.json").write_text(json.dumps({"entities": [
        {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
        {"code": "EXI", "name": "Example International Ltd", "uses_sql": False,
         "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
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


# ---------- part 1's new install ----------

if CHILD:
    src, dst = Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(src.read_text(encoding="utf-8"))
    check("[new install] it holds no company data, so it may import", j("get", "/api/setup/import")["empty"] is True)
    bad = copy.deepcopy(data)
    bad["company_names"][0]["name"] = "EXAMPLE HOLDINGS SDN BHD (202601000001)"
    r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": bad, "preview": True})
    check("[new install] a name that matches a company in the file refuses the whole import",
          r.status_code == 400 and "already matches company EXH" in r.get_json()["error"] and not q("SELECT id FROM entities"), r.get_json())
    bad = copy.deepcopy(data)
    bad["company_names"][0]["company"] = "EXI"
    r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": bad, "preview": True})
    check("[new install] a name for a company not kept in SQL is refused",
          r.status_code == 400 and "only a company kept in SQL Account" in r.get_json()["error"], r.get_json())
    bad = copy.deepcopy(data)
    bad["company_names"].append(dict(bad["company_names"][0]))
    r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": bad, "preview": True})
    check("[new install] a name twice in the file is refused", r.status_code == 400 and "in the file twice" in r.get_json()["error"], r.get_json())
    older = copy.deepcopy(data)
    del older["company_names"]
    older["records_version"] = 35
    pv = j("post", "/api/setup/import", json={"setup": older, "preview": True})
    check("[new install] a file made before the names were exported still imports (preview)",
          pv["preview"] is True and dict(pv["counts"]).get("companies") == 2 and "printed company names" not in dict(pv["counts"])
          and "printed company name" not in dict(pv["counts"]) and not q("SELECT id FROM entities"), pv)
    pv = j("post", "/api/setup/import", json={"setup": data, "preview": True})
    check("[new install] the preview counts the printed company name", dict(pv["counts"]).get("printed company name") == 1, pv["counts"])
    j("post", "/api/setup/import", json={"setup": data, "reason": "test: a new install"})
    got = q("""SELECT e.code AS company, n.name, n.name_key, n.confirmed_at, n.confirmed_by FROM sql_company_names n
               JOIN entities e ON e.id = n.entity_id""")
    r = c.get(BASE + "/api/setup/export?what=full", headers=H)
    dst.write_text(json.dumps({"names": got, "export": json.loads(r.data)["company_names"]}), encoding="utf-8")
    print(f"\nAll {len(passed)} checks passed in the new install. Records folder used: {tmp}")
    sys.exit(0)


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


def file_in(p, name):
    return next(x for x in p["fetch"]["files"] if x["name"] == name)


EID = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
EXI = q("SELECT id FROM entities WHERE code = 'EXI'")[0]["id"]
CHART = [("100-0000", "SHARE CAPITAL", "equity", None), ("310-1000", "BANK-EXAMPLE 0001", "asset", "bank"),
         ("900-E002", "ELECTRICITY", "expense", None)]
write("the chart of accounts", *[("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, *a))
                                 for a in CHART])
BANK = ("310-1000", "BANK-EXAMPLE 0001")
OCT = ("01/10/2026", "31/10/2026")
PV1 = ("PV2610-001", "15/10/2026", [("900-E002", "ELECTRICITY", "Electricity Sep", 1000.0, 0), (*BANK, "Electricity Sep", 0, 1000.0)])
PV9 = ("PV2610-009", "20/10/2026", [("900-E002", "ELECTRICITY", "Electricity deposit", 50.0, 0), (*BANK, "Electricity deposit", 0, 50.0)])
TB = [("100-0000", "SHARE CAPITAL", (0, 10000.0), (0, 0), (0, 0), (0, 10000.0)),
      ("310-1000", "BANK-EXAMPLE 0001", (10000.0, 0), (0, 0), (0, 0), (10000.0, 0))]

# ---------- 1. printed company names in Setup › Companies ----------

names = j("get", f"/api/setup/entities/{EID}/sql-names")
check("a company with no name confirmed lists none", names == {"ready": True, "names": []}, names)
save("stranger.xlsx", jot([("Bank Journal", [PV1])], OCT, company=STRANGER))
check("an export printed for a company not in Setup is held", file_in(preview(), "stranger.xlsx")["status"] == "unknown_company")
j("post", "/api/sql/take-company", json={"entity_id": EID, "company": STRANGER})
names = j("get", f"/api/setup/entities/{EID}/sql-names")["names"]
check("Setup › Companies lists the name taken, with when and by whom it was confirmed",
      len(names) == 1 and names[0]["name"] == STRANGER and names[0]["confirmed_at"][:4] == str(date.today().year)
      and names[0]["confirmed_by"] == audit.who()[0], names)
check("another company lists none of it", j("get", f"/api/setup/entities/{EXI}/sql-names")["names"] == [])
check("the next fetch reads the file for EXH", file_in(preview(), "stranger.xlsx")["status"] == "read")
r = c.delete(BASE + f"/api/setup/entities/{EXI}/sql-names/{names[0]['id']}", headers=H, json={})
check("a name can't be removed through another company", r.status_code == 400 and "Reload the page" in r.get_json()["error"]
      and len(q("SELECT id FROM sql_company_names")) == 1, r.get_json())
r = c.delete(BASE + f"/api/setup/entities/{EID}/sql-names/99999", headers=H, json={})
check("a name no longer kept can't be removed", r.status_code == 400, r.get_json())
r = c.delete(BASE + f"/api/setup/entities/{EID}/sql-names/{names[0]['id']}", json={})
check("a remove from another website is refused", r.status_code == 403 and len(q("SELECT id FROM sql_company_names")) == 1)
gone = j("delete", f"/api/setup/entities/{EID}/sql-names/{names[0]['id']}", json={})
check("Remove takes the name off the company, and says the list is ready to show (not that the records need an update)",
      gone["removed"] == STRANGER and gone["names"] == [] and gone["ready"] is True
      and not q("SELECT id FROM sql_company_names"), gone)
acts = [a["what"] for a in q("SELECT what FROM activity")]
check("the remove is in the activity log, saying the files are held again on the next Fetch",
      any(f'Removed the printed company name "{STRANGER}" from EXH' in a and "the next Fetch holds" in a for a in acts), acts[-3:])
dels = q("SELECT a.before, t.action FROM audit_row a JOIN audit_tx t ON t.token = a.token WHERE a.tbl = 'sql_company_names' AND a.op = 'delete'")
check("and in the audit trail, with the row as it was", len(dels) == 1 and json.loads(dels[0]["before"])["name"] == STRANGER
      and "sql-names" in dels[0]["action"], dels)
check("the next fetch holds the file again, as from a company not in Setup",
      file_in(preview(), "stranger.xlsx")["status"] == "unknown_company")
js = Path(__file__).resolve().parents[1].joinpath("static", "app.js").read_text(encoding="utf-8")
check("the page's Remove asks for a second click, saying under the list that the files are held again on the next Fetch",
      "data-sql-name-remove" in js and 'btn.textContent = "Click again to remove"' in js
      and 'files printing it are held again on the next Fetch, until Take it for is clicked again.`' in js
      and 'id="suNamesConfirm"' in js and "Printed company names" in js)
draw = js[js.index("async function drawSqlNames"):js.index("async function removeSqlName")]
remove = js[js.index("async function removeSqlName"):js.index("// A company's printed invoices")]
check("after Remove the list is drawn from what is left, as ready, inside a table wrapper that keeps the drawer's gutter",
      '<div class="tbl-wrap"><table><thead><tr><th>Name as printed' in draw and "drawSqlNames(id, { ready: true, ...r })" in remove)
j("post", "/api/sql/take-company", json={"entity_id": EID, "company": STRANGER})
kept = q("SELECT * FROM sql_company_names")
check("taken again, it is listed again", len(kept) == 1 and kept[0]["confirmed_by"] == audit.who()[0])

# ---------- Setup export and import ----------

r = c.get(BASE + "/api/setup/export?what=full", headers=H)
full = json.loads(r.data)
check("a full Setup export carries the printed company names, by company code, with when and by whom",
      full["company_names"] == [{"company": "EXH", "name": STRANGER, "confirmed_at": kept[0]["confirmed_at"],
                                 "confirmed_by": kept[0]["confirmed_by"]}], full.get("company_names"))
r = c.get(BASE + "/api/setup/export?what=template", headers=H)
check("a template carries none", "company_names" not in json.loads(r.data))
src_file, out_file = tmp / "setup full.json", tmp / "child out.json"
src_file.write_text(json.dumps(full), encoding="utf-8")
run = subprocess.run([sys.executable, "-m", "synthetic_tests.stage1_leftovers_test", "--import", str(src_file), str(out_file)],
                     cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=600)
print("\n".join("  " + line for line in run.stdout.splitlines()))
check("the new install's checks pass", run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:])
got = json.loads(out_file.read_text(encoding="utf-8"))
check("the new install keeps the name for EXH, with when and by whom, and exports it again as it came",
      got["names"] == [{"company": "EXH", "name": STRANGER, "name_key": kept[0]["name_key"], "confirmed_at": kept[0]["confirmed_at"],
                        "confirmed_by": kept[0]["confirmed_by"]}] and got["export"] == full["company_names"], got)

# ---------- a full export leaves out names its own import would refuse ----------

write("EXH no longer kept in SQL Account", ("UPDATE entities SET uses_sql = 0 WHERE id = ?", (EID,)))
out = json.loads(c.get(BASE + "/api/setup/export?what=full", headers=H).data)
check("a name of a company no longer kept in SQL stays out of a full export, said in left out",
      out["company_names"] == [] and any(STRANGER in x and "no longer kept in SQL Account" in x for x in out.get("left_out", [])),
      (out.get("company_names"), out.get("left_out")))
write("EXH kept in SQL Account again", ("UPDATE entities SET uses_sql = 1 WHERE id = ?", (EID,)))
MATCHES_EXI = "EXAMPLE INTERNATIONAL LTD (209901000002)"
write("a name that now matches EXI", ("INSERT INTO sql_company_names (entity_id, name_key, name, confirmed_at) VALUES (?, ?, ?, ?)",
                                      (EID, sqlfetch._key(MATCHES_EXI), MATCHES_EXI, db.now())))
out = json.loads(c.get(BASE + "/api/setup/export?what=full", headers=H).data)
check("a name that now matches a company in Setup stays out too, said; the others go",
      [x["name"] for x in out["company_names"]] == [STRANGER]
      and any(MATCHES_EXI in x and "now matches company EXI" in x for x in out.get("left_out", [])),
      (out.get("company_names"), out.get("left_out")))
src_file.write_text(json.dumps(out), encoding="utf-8")
run = subprocess.run([sys.executable, "-m", "synthetic_tests.stage1_leftovers_test", "--import", str(src_file), str(out_file)],
                     cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=600)
check("that export imports into a new install", run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:])
write("the matching name taken off again", ("DELETE FROM sql_company_names WHERE name_key = ?", (sqlfetch._key(MATCHES_EXI),)))

# ---------- 2. a document found again after it was marked deleted in SQL ----------

write("the stranger's name is left out of the rest", ("DELETE FROM sql_company_names", ()))
(FOLDER / "stranger.xlsx").unlink()


def tb_check():
    return j("get", f"/api/books/trial-balance?entity={EID}&from=2026-10-01&to=2026-10-31")["check"]


def doc(no):
    return q("SELECT * FROM ledger_docs WHERE doc_no = ? AND state <> 'superseded'", (no,))[0]


save("j1.xlsx", jot([("Bank Journal", [PV1, PV9])], OCT, stamp="14/11/2026 1:00:00 AM\nADMIN"))
fetch()
save("j2.xlsx", jot([("Bank Journal", [PV1])], OCT, stamp="14/11/2026 2:00:00 AM\nADMIN"))
fetch()
check("a journal without PV2610-009 marks it no longer in SQL", doc("PV2610-009")["state"] == "gone" and doc("PV2610-001")["state"] == "current")
save("tb.xlsx", trial_balance(TB, *OCT))
fetch()
ch = tb_check()
check("SQL's trial balance read after it: the differences are real ones, not out of date", ch["outcome"] == "warn" and ch["stale"] is False, ch["text"])
save("j3.xlsx", jot([("Bank Journal", [PV1])], OCT, stamp="14/11/2026 3:00:00 AM\nADMIN"))
fetch()
check("a later journal with nothing changed leaves them as real ones", tb_check()["stale"] is False)
tb_batch = q("SELECT * FROM ledger_batches WHERE report = 'trial_balance' ORDER BY id DESC LIMIT 1")[0]
save("j4.xlsx", jot([("Bank Journal", [PV1, PV9])], OCT, stamp="14/11/2026 4:00:00 AM\nADMIN"))
fetch()
d9 = doc("PV2610-009")
j4 = q("SELECT id FROM ledger_batches WHERE report = 'journal' ORDER BY id DESC LIMIT 1")[0]["id"]
check("a later journal that holds PV2610-009 again brings it back, same version, and keeps the batch that did",
      d9["state"] == "current" and d9["version"] == 1 and d9["back_batch_id"] == j4 and d9["batch_id"] < tb_batch["id"]
      and d9["ended_batch_id"] is None, d9)
ch = tb_check()
check("that counts as a change after the trial balance: the differences may be out of date",
      ch["stale"] is True and "may be out of date rather than errors" in ch["text"]
      and all(x.get("possibly_stale") for x in ch["differences"]), ch["text"])
tb_read = j("get", f"/api/sql/entries?entity={EID}")["ledger"]["reads"]["trial_balance"]
check("the SQL page's check against SQL's trial balance is told it is possibly out of date, as Books says",
      tb_read["stale"] is True and any(r["outcome"] == "warn" for r in tb_read["results"]), tb_read)
check("and the SQL page shows it so", 'kind === "trial_balance" && b.stale && warns.length' in js
      and "<b>Possibly out of date</b><span>A GL Journal of Transaction read after this trial balance" in js)


def tb_page():
    """The audit pack's trial balance page for October (auditpack.books_checks and _books_pages), as text."""
    from pypdf import PdfReader
    from hrp import auditpack
    with db.connect() as con:
        ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
        chk = auditpack.books_checks(con, ent, "2026-10")
    pages = PdfReader(io.BytesIO(auditpack._books_pages({**chk, "head": "EXH - October 2026"}))).pages
    return chk["trial_balance"], " ".join(pages[2].extract_text().split())


tbp, text = tb_page()
check("the audit pack's trial balance page says possibly out of date, as Books does, not a plain Differs",
      tbp["stale"] is True and "Possibly out of date: SQL's trial balance was read before a later GL Journal of Transaction." in text
      and "Differs from SQL's trial balance." not in text and "may be out of date rather than errors" in text, text[:600])
with db.connect() as con:
    check("only for the trial balance's dates: a period after the document's date sees no change",
          books._changed_after(con, EID, tb_batch, "2026-10-21", "2026-10-31") is False
          and books._changed_after(con, EID, tb_batch, "2026-10-01", "2026-10-31") is True)
check("the bring-back is in the audit trail, with the batch that did it",
      any(json.loads(a["before"])["state"] == "gone" and json.loads(a["after"])["state"] == "current"
          and json.loads(a["after"])["back_batch_id"] == j4
          for a in q("SELECT before, after FROM audit_row WHERE tbl = 'ledger_docs' AND op = 'update' AND row_key = ?", (str(d9["id"]),))))
save("tb2.xlsx", trial_balance(TB, *OCT, stamp="14/11/2026 5:00:00 AM ADMIN"))
fetch()
check("a trial balance fetched after that is up to date again", tb_check()["stale"] is False)
check("and the SQL page no longer says possibly out of date",
      j("get", f"/api/sql/entries?entity={EID}")["ledger"]["reads"]["trial_balance"]["stale"] is False)
tbp, text = tb_page()
check("and the audit pack's page says it differs again", tbp["stale"] is False and "Differs from SQL's trial balance." in text
      and "Possibly out of date" not in text, text[:400])

# ---------- update 37, on records from before it ----------

write("as before update 37", ("UPDATE ledger_docs SET back_batch_id = NULL", ()),
      ("INSERT INTO sql_company_names (entity_id, name_key, name, confirmed_at) VALUES (?, ?, ?, ?)",
       (EID, sqlfetch._key(STRANGER), STRANGER, db.now())))
check("as before update 37: no batch kept and no one named", doc("PV2610-009")["back_batch_id"] is None
      and q("SELECT confirmed_by FROM sql_company_names")[0]["confirmed_by"] is None)
con = db.connect()
con.arm("migration", "Update 37")
db.MIGRATIONS[36](con)
con.commit()
con.disarm()
con.close()
check("update 37 fills, from the audit trail, the batch that found a document again", doc("PV2610-009")["back_batch_id"] == j4)
check("and who confirmed a name kept before it",
      q("SELECT confirmed_by FROM sql_company_names")[0]["confirmed_by"] == audit.who()[0])
check("the latest trial balance check reads as before", tb_check()["stale"] is False)
with db.connect() as con:
    check("and the trial balance before the bring-back sees it as a change after it",
          books._changed_after(con, EID, tb_batch, "2026-10-01", "2026-10-31") is True)
    v = con.execute("PRAGMA user_version").fetchone()[0]
check("the records are at the latest update, 38", v == len(db.MIGRATIONS) == 38, v)


# ---------- 3. Replace on upload retires only a document of the same payment ----------

CYC = db.current_cycle()
acct = {e: q("SELECT id FROM accounts WHERE entity_id = ?", (e,))[0]["id"] for e in (EID, EXI)}
pay = {e: j("post", "/api/payments", json={"entity_id": e, "month": CYC, "account_id": acct[e], "description": f"Test {e}",
                                           "amount": 10})["id"] for e in (EID, EXI)}
pay2 = j("post", "/api/payments", json={"entity_id": EID, "month": CYC, "account_id": acct[EID], "description": "Another",
                                        "amount": 5})["id"]


def upload(pid, name, replaces=None, expect=200):
    form = {"doc_type": "other", "file": (io.BytesIO(b"%PDF-1.4 made up " + name.encode()), name), "payment_id": str(pid)}
    if replaces:
        form["replaces"] = str(replaces)
    r = c.post(BASE + "/api/upload", headers=H, data=form, content_type="multipart/form-data")
    assert r.status_code == expect, (r.status_code, r.data[:400])
    return r.get_json()


def live(pid):
    return [d["id"] for d in q("SELECT id FROM documents WHERE payment_id = ? AND replaced_by IS NULL AND removed_at IS NULL", (pid,))]


first_doc = upload(pay[EID], "exh.pdf")["id"]
before = q("SELECT COUNT(*) AS n FROM documents")[0]["n"]
r = upload(pay[EXI], "exi.pdf", replaces=first_doc, expect=400)
check("another company's payment can't retire EXH's document, and nothing is stored",
      "isn't a current document of this payment" in r["error"] and live(pay[EID]) == [first_doc]
      and q("SELECT COUNT(*) AS n FROM documents")[0]["n"] == before and live(pay[EXI]) == [], r)
r = upload(pay2, "other.pdf", replaces=first_doc, expect=400)
check("nor another payment of the same company", live(pay[EID]) == [first_doc] and live(pay2) == [], r)
new_doc = upload(pay[EID], "exh v2.pdf", replaces=first_doc)["id"]
check("a document replaced on its own payment is retired as before", live(pay[EID]) == [new_doc]
      and q("SELECT replaced_by FROM documents WHERE id = ?", (first_doc,))[0]["replaced_by"] == new_doc)
r = upload(pay[EID], "exh v3.pdf", replaces=first_doc, expect=400)
check("one already replaced can't be replaced again", live(pay[EID]) == [new_doc], r)
upload(pay[EID], "exh v3.pdf", replaces=99999, expect=400)
check("nor one that doesn't exist", live(pay[EID]) == [new_doc])

# ---------- 4. the payroll month's cutoff day never changes a filed month ----------

from hrp import appsettings  # noqa: E402

write("a filed August and a voucher dated 8 September",
      ("INSERT INTO months (entity_id, month, generated_at, closed_at) VALUES (?, '2026-08', ?, ?)", (EID, db.now(), db.now())),
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'made up.xlsx', ?, 1, 0)", (EID, db.now())),
      ("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, kind)
          VALUES ((SELECT MAX(id) FROM sql_imports), ?, 'PV2609-001', '2026-09-08', 'WATER BILL', 12.0, 'payment')""", (EID,)))
r = c.patch(BASE + "/api/setup/settings", headers=H, json={"values": {"cycle_rollover_day": 5}})
why = (r.get_json() or {}).get("error", "")
check("a new day that would move a voucher out of a filed month is refused, naming it",
      r.status_code == 409 and "PV2609-001" in why and "August 2026" in why and "September 2026" in why
      and "Reopen those months first" in why and appsettings.get("cycle_rollover_day") == 10, why)
r = c.patch(BASE + "/api/setup/settings", headers=H, json={"values": {"cycle_rollover_day": 12}})
check("a day that moves nothing in a filed month is saved", r.status_code == 200 and appsettings.get("cycle_rollover_day") == 12,
      r.data[:300])
j("patch", "/api/setup/settings", json={"values": {"cycle_rollover_day": 10}})
write("the voucher's description names its month", ("UPDATE sql_entries SET description = 'WATER BILL SEP 2026' WHERE doc_no = 'PV2609-001'", ()))
r = c.patch(BASE + "/api/setup/settings", headers=H, json={"values": {"cycle_rollover_day": 5}})
check("a document placed by the month its description names doesn't stop it", r.status_code == 200, r.data[:300])
j("patch", "/api/setup/settings", json={"values": {"cycle_rollover_day": 10}})
check("the setting's hint says filed months never change",
      "is refused, so filed months never change" in appsettings.SPEC["cycle_rollover_day"][3])

# ---------- 5. the README ----------

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
flat = " ".join(readme.split())
check("the README describes the Books page, its Excel files, the statutory check and the SQL books item",
      all(w in flat for w in ("**Books**", "**trial balance**", "**profit and loss**", "**balance sheet**", "**customers and suppliers**",
                              "**statutory payables**", "hrp/booksexcel.py", "SQL books agree with SQL Account", "financial year")))
check("the audit pack's books pages and the auditor package's Books folder",
      "three books pages" in flat and "a `Books` folder of Excel files" in flat and "**Auditor package**" in flat)
check("printed invoices, debit and credit notes and self-billed invoices, and the month zip",
      "**Printed invoices**" in flat and "debit note" in flat and "self-billed" in flat and "one zip" in flat)
check("the Supplier Invoice and Supplier Payment listings, Take it for and the printed company names in Setup",
      "Supplier Invoice and Supplier Payment listings" in flat and "**Take it for**" in flat and "Setup › Companies" in flat)
check("the exports and company-assets folders in the records folder table",
      "| `exports\\<company>\\` |" in readme and "| `company-assets\\` |" in readme)
check("months before tracking, and the cutoff day's refusal next to 'Filed months never change'",
      "**First month tracked**" in flat and "Before tracking" in flat
      and "Filed months never change: a change of **Payroll month runs until**" in flat)
check("the internet sentence says the app contacts nothing itself and MyInvois links open only when clicked",
      "makes no internet connections" not in flat and "contacts nothing on the internet itself" in flat and "myinvois.hasil.gov.my" in flat)
tests = sorted(x.stem for x in Path(__file__).resolve().parent.glob("*_test.py"))
check("every synthetic test is listed", all(t in flat for t in tests), [t for t in tests if t not in flat])

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
