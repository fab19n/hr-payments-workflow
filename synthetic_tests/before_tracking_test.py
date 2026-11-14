"""SQL entries of months before the first month tracked, on made-up records only.

A company tracked here from October 2026 fetches SQL's listings for the whole year from January. Every document is kept
in the books mirror, but those of months before October (both the month they are dated in and the month the app files
them in, the month the description names, are before it) ask for nothing: they are left out of the SQL entries not
linked, the probable corrections, Create payments for all, Next up and the preview's suggestions (except one for a
tracked payment due close by: 30 September for what October pays), and the import sets up no month before October.
One dated in a tracked month is always tracked, whatever its description names (a day number, a range). A voucher of
30 September naming October is created in October, and Next up counts it there. The Overview of a month before
tracking still counts its bank lines to explain until its statement is signed off, the toasts after unlinking say
which list a voucher goes back to, and an invoice of 25 September is still offered to October's receipt. The SQL page lists them apart, read-only. A second company with no first month tracked
fetches the same documents and behaves as before. The workbooks are built to the layout of a real export (copied from
sql_exports_test.py), with made-up companies, documents and amounts.

Run: .venv\\Scripts\\python -m synthetic_tests.before_tracking_test
"""
import io
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

tmp = Path(tempfile.mkdtemp(prefix="hrp-before-tracking-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, nextup  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
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


EXH = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
SMP = q("SELECT id FROM entities WHERE code = 'SMP'")[0]["id"]
EXH_LINE, SMP_LINE = "EXAMPLE HOLDINGS LTD (202601000001 (1234567-X))", "SAMPLE TRADING LTD (202601000002 (7654321-Y))"
write("first month tracked", ("UPDATE entities SET first_month = '2026-10' WHERE id = ?", (EXH,)))
check("EXH is tracked from October 2026, SMP has no first month", q("SELECT code, first_month FROM entities ORDER BY id")
      == [{"code": "EXH", "first_month": "2026-10"}, {"code": "SMP", "first_month": None}])


# ---------- a workbook as SQL Account writes it (copied from sql_exports_test.py) ----------

def workbook(cells, merges):
    """An .xlsx from {(row, column letter): value}, with the WindowWidth attribute SQL Account writes."""
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
    view = '<workbookView xWindow="480" yWindow="105" WindowWidth="21075" WindowHeight="12585"/>'
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


def listing(docs, title="Payment Voucher Listing", company=EXH_LINE, period=("01/01/2026", "30/11/2026")):
    """An exported listing laid out as SQL Account prints it. docs: (doc no, date, [description lines], cheque no, amount)."""
    cells, merges = {}, []

    def put(r, col, v, to=None):
        cells[(r, col)] = v
        if to:
            merges.append(f"{col}{r}:{to}{r}")

    put(2, "G", title, "L"); put(2, "O", datetime(2026, 11, 13, 19, 53), "P"); put(2, "Q", "ADMIN")
    put(3, "G", f"As At {period[1]}", "J")
    put(2, "A", "Date"); put(2, "B", "Doc No."); put(2, "C", ":"); put(2, "D", ":"); put(2, "E", "All")
    put(2, "F", f"From {period[0]} to {period[1]}")
    put(3, "A", "Currency"); put(3, "B", "Incl Cancelled"); put(3, "C", ":"); put(3, "D", ":"); put(3, "E", "No")
    put(3, "F", "----")
    put(4, "A", "Sort By"); put(4, "B", ":"); put(4, "C", "PostDate;DocNo;CurrencyCode", "F")
    put(6, "A", company, "I"); put(6, "P", "Page 1 of 1", "Q")
    put(7, "A", "Doc Date"); put(7, "C", "Doc No/Chq No", "D"); put(7, "G", "Description")
    put(7, "K", "Cash/ Bank Code", "L"); put(7, "P", "Amount (MYR)", "Q")
    r = 8
    for no, day, lines, cheque, amount in docs:
        put(r, "A", day, "B"); put(r, "C", no, "D"); put(r, "E", lines[0], "J"); put(r, "K", "310-1000"); put(r, "M", "BANK-EXAMPLE 0001 0002 0003", "O")
        put(r, "P", float(amount), "Q")
        r += 1
        for k in range(max(len(lines) - 1, 1 if cheque else 0)):
            if k == 0 and cheque:
                put(r, "C", cheque, "D")
            if k + 1 < len(lines):
                put(r, "E", lines[k + 1], "K")
            r += 1
    put(r, "A", " Summary ")
    put(r + 1, "B", "Total Records  : "); put(r + 1, "D", float(len(docs)))
    put(r + 1, "K", "Grand Total   (MYR)"); put(r + 1, "P", float(round(sum(d[4] for d in docs), 2)))
    return workbook(cells, merges)


def invoices(docs, company=EXH_LINE):
    """A Customer Invoice Listing for January to November. docs: (doc no, date, code, name, amount)."""
    cells, merges = {}, []

    def put(r, col, v, to=None):
        cells[(r, col)] = v
        if to:
            merges.append(f"{col}{r}:{to}{r}")

    put(2, "A", "Date"); put(2, "B", ":"); put(2, "C", "From 01/01/2026 to 30/11/2026", "F")
    put(3, "A", "Document"); put(3, "C", "All")
    put(4, "A", "Company"); put(4, "C", "All")
    put(7, "A", "Area"); put(7, "B", "Currency"); put(7, "E", "----"); put(7, "G", "Customer Invoice Listing", "L"); put(7, "O", datetime(2026, 11, 13, 21, 14), "Q")
    put(8, "A", "Incl Cancelled"); put(8, "B", "Group By"); put(8, "E", "No"); put(8, "G", "As At 30/11/2026", "J")
    put(9, "A", "Sort By"); put(9, "C", "DocDate;DocNo;Code", "D")
    put(10, "A", company, "I"); put(10, "P", "Page 1 of 1", "Q")
    put(11, "A", "Doc. No", "B"); put(11, "C", "Doc. Date", "D"); put(11, "E", "Code"); put(11, "G", "Name"); put(11, "P", "Amount (MYR)", "Q")
    r = 12
    for no, day, code, name, amount in docs:
        put(r, "A", no, "B"); put(r, "C", day, "D"); put(r, "E", code, "F"); put(r, "G", name, "N"); put(r, "O", float(amount), "Q")
        r += 1
    put(r + 1, "J", "Grand Total Amount (MYR)", "L"); put(r + 1, "M", float(round(sum(d[4] for d in docs), 2)), "Q")
    return workbook(cells, merges)


# ---------- the made-up year: one supplier bill a month, January to November ----------

def year(prefix):
    """The same documents for each company, numbered with its own prefix (doc no, date, lines, cheque, amount)."""
    docs = [(f"{prefix}26{m:02d}-001", date(2026, m, 15), ["EXAMPLE SUPPLIER - OFFICE SUPPLIES"], f"10000{m:05d}", 1000.0 + m)
            for m in range(1, 12)]
    docs += [
        (f"{prefix}2609-002", date(2026, 9, 30), ["EXAMPLE STATIONER - PAPER"], "", 930.00),               # 30 Sep: before October
        (f"{prefix}2610-009", date(2026, 10, 20), ["EXAMPLE LANDLORD - RENTAL FOR SEP 26"], "", 1750.00),  # names September, dated October
        (f"{prefix}2602-003", date(2026, 2, 20), ["REVERSAL OF A WRONG ENTRY"], "", 55.00),                # a correction, Feb
        (f"{prefix}2610-004", date(2026, 10, 22), ["REVERSAL OF A WRONG ENTRY"], "", 66.00),              # a correction, Oct
    ]
    return docs


save_age = [100]


def save(name, data):
    """A file in the downloads folder, each saved a minute after the one before."""
    p = FOLDER / name
    p.write_bytes(data)
    save_age[0] -= 1
    t = datetime(2026, 11, 13, 12, 0).timestamp() - save_age[0] * 60
    os.utime(p, (t, t))


save("exh.xlsx", listing(year("PV")))
save("exh-iv.xlsx", invoices([("IV2603-001", date(2026, 3, 10), "300-T001", "EXAMPLE TENANT", 440.0),
                              ("IV2610-001", date(2026, 10, 10), "300-T001", "EXAMPLE TENANT", 440.0)]))
save("smp.xlsx", listing(year("PV"), company=SMP_LINE))
save("smp-iv.xlsx", invoices([("IV2603-001", date(2026, 3, 10), "300-T001", "EXAMPLE TENANT", 440.0),
                              ("IV2610-001", date(2026, 10, 10), "300-T001", "EXAMPLE TENANT", 440.0)], company=SMP_LINE))

# An October payment for each company: one the October bill is for, and one the bill dated 30 September would fit
# (same amount, named, one day apart) were it tracked.
for eid in (EXH, SMP):
    j("post", "/api/payments", json={"entity_id": eid, "month": "2026-10", "description": "Example Supplier office supplies",
                                     "amount": 1010.0, "due_date": "2026-10-15", "category": "other"})
    j("post", "/api/payments", json={"entity_id": eid, "month": "2026-10", "description": "Example Stationer paper",
                                     "amount": 930.0, "due_date": "2026-10-01", "category": "other"})

BEFORE = {"PV2601-001", "PV2602-001", "PV2603-001", "PV2604-001", "PV2605-001", "PV2606-001", "PV2607-001", "PV2608-001",
          "PV2609-001", "PV2609-002", "PV2602-003"}
# PV2610-009 names September but is dated in October, a tracked month, so it is tracked.
TRACKED = {"PV2610-001", "PV2611-001", "PV2610-004", "PV2610-009"}
NEAR = {"PV2609-002"}  # dated 30 September, a day before the October payment it fits: suggested it in the preview
ALL = BEFORE | TRACKED


def months_open(eid):
    return [r["month"] for r in q("SELECT month FROM months WHERE entity_id = ? ORDER BY month", (eid,))]


# ---------- the preview ----------
check("no month is set up before the fetch", months_open(EXH) == [] and months_open(SMP) == [])
pe = j("post", "/api/sql/preview", json={"entity_id": EXH, "fetch": True})
recs = {r["doc_no"]: r for r in pe["records"]}
check("the preview reads the whole year", set(recs) == ALL | {"IV2603-001", "IV2610-001"}, str(sorted(recs)))
check("each document before October is marked before tracking, by the months it is dated and filed in",
      {n for n, r in recs.items() if r["before_tracking"]} == BEFORE - NEAR | {"IV2603-001"},
      str(sorted(n for n, r in recs.items() if r["before_tracking"])))
check("nothing before October is suggested a payment or a checklist item, but for one due close by in October",
      all(recs[n]["payment_id"] is None and recs[n]["task_id"] is None for n in BEFORE - NEAR | {"IV2603-001"}),
      str([(n, recs[n]["payment_id"], recs[n]["task_id"]) for n in BEFORE]))
check("the bill dated 30 September is suggested the October payment due the next day, as the suggestion is for October",
      recs["PV2609-002"]["payment_desc"] == "Example Stationer paper" and recs["PV2609-002"]["before_tracking"] is False,
      str(recs["PV2609-002"]))
check("the bill dated in October naming September is tracked, by its own date", recs["PV2610-009"]["before_tracking"] is False)
check("the October bill is still suggested its October payment", recs["PV2610-001"]["payment_id"] is not None
      and recs["PV2610-001"]["payment_desc"] == "Example Supplier office supplies", str(recs["PV2610-001"]))
check("the preview sets up nothing for good", months_open(EXH) == [])

ps = j("post", "/api/sql/preview", json={"entity_id": SMP, "fetch": True})
srecs = {r["doc_no"]: r for r in ps["records"]}
check("with no first month, nothing is before tracking", not any(r["before_tracking"] for r in srecs.values()))
check("with no first month, the bill dated 30 September is suggested the October payment it fits, as before",
      srecs["PV2609-002"]["payment_desc"] == "Example Stationer paper" and srecs["PV2610-001"]["payment_desc"] == "Example Supplier office supplies",
      str(srecs["PV2609-002"]))

# ---------- the import ----------
re_ = j("post", "/api/sql/apply", json={"token": pe["token"], "header_row": pe["header_row"], "mapping": pe["mapping"],
                                        "links": {str(recs["PV2610-001"]["row"]): recs["PV2610-001"]["payment_id"]}})
check("every document is kept in the books mirror", re_["added"] == len(ALL) + 2
      and {r["doc_no"] for r in q("SELECT doc_no FROM sql_entries WHERE entity_id = ?", (EXH,))} == ALL | {"IV2603-001", "IV2610-001"}, str(re_))
check("the import sets up no month before October", months_open(EXH) == ["2026-10", "2026-11"], str(months_open(EXH)))
check("documents before October stay not linked, and are filed on no checklist item",
      all(r["status"] == "unlinked" and r["task_id"] is None for r in q("SELECT * FROM sql_entries WHERE entity_id = ? AND kind = 'payment'", (EXH,))
          if r["doc_no"] in BEFORE)
      and q("SELECT task_id FROM sql_entries WHERE entity_id = ? AND doc_no = 'IV2603-001'", (EXH,))[0]["task_id"] is None)

rs = j("post", "/api/sql/apply", json={"token": ps["token"], "header_row": ps["header_row"], "mapping": ps["mapping"], "links": {}})
check("with no first month, the import sets up every month it needs, as before",
      months_open(SMP) == ["2025-12"] + [f"2026-{m:02d}" for m in range(1, 12)], str(months_open(SMP)))

# ---------- the SQL page ----------
d = j("get", f"/api/sql/entries?entity={EXH}")
check("the page says the first month tracked", d["first_month"] == "2026-10")
check("SQL entries not linked holds October and November only (the probable correction among them)",
      {u["doc_no"] for u in d["unlinked"]} == {"PV2611-001", "PV2610-004", "PV2610-009"}, str([u["doc_no"] for u in d["unlinked"]]))
check("the probable correction listed is October's, not February's",
      [u["doc_no"] for u in d["unlinked"] if u["correction"]] == ["PV2610-004"], str([(u["doc_no"], u["correction"]) for u in d["unlinked"]]))
check("the before-tracking group holds every entry before October, with what the page shows",
      {u["doc_no"] for u in d["before_tracking"]} == BEFORE
      and all(k in u for u in d["before_tracking"] for k in ("id", "doc_no", "doc_date", "description", "amount", "direction")), str(d["before_tracking"][:1]))
check("the invoice before October is marked before tracking in the documents list, the October one isn't",
      {x["doc_no"]: x["before_tracking"] for x in d["documents"]} == {"IV2603-001": True, "IV2610-001": False}, str(d["documents"]))
check("the lines button can be drawn for them: the page's lines are keyed by entry id", isinstance(d["lines"], dict))
check("the October bill linked by hand is under Linked to payments", [x["doc_no"] for x in d["linked"]] == ["PV2610-001"])

ds = j("get", f"/api/sql/entries?entity={SMP}")
check("with no first month, every entry not linked is listed as before and none is before tracking",
      {u["doc_no"] for u in ds["unlinked"]} == ALL and ds["before_tracking"] == [] and ds["first_month"] is None,
      str(sorted(u["doc_no"] for u in ds["unlinked"])))
check("with no first month, both reversals are probable corrections",
      sorted(u["doc_no"] for u in ds["unlinked"] if u["correction"]) == ["PV2602-003", "PV2610-004"])

# ---------- Next up ----------
con = db.connect()
TODAY = date(2026, 11, 14)


def sql_row(eid):
    rows_ = [r for r in nextup.items(con, TODAY, eid) if r["rule"] == 7]
    return rows_[0]["text"] if rows_ else ""


exh_text = sql_row(EXH)
n = re.search(r"(\d+) SQL entr", exh_text)
check("Next up counts only the entries of tracked months (November's, and the bill naming September dated in October)",
      n and int(n.group(1)) == 3, exh_text)
smp_text = sql_row(SMP)
n2 = re.search(r"(\d+) SQL entr", smp_text)
check("with no first month, Next up counts the October-cycle bill naming September too, as before",
      n2 and int(n2.group(1)) == 4, smp_text)
con.close()

# ---------- Create payments for all ----------
ca = j("post", "/api/sql/entries/create-all", json={"entity_id": EXH})
check("Create payments for all adds payments for November's bill and the October one only, and leaves the October correction",
      (ca["created"], ca["linked"], ca["corrections"]) == (2, 0, ["PV2610-004"]), str(ca))
check("no payment was made in a month before October", q("SELECT COUNT(*) n FROM payments WHERE entity_id = ? AND month < '2026-10'", (EXH,))[0]["n"] == 0)
check("entries before October are still not linked, kept in the mirror",
      {r["doc_no"] for r in q("SELECT doc_no FROM sql_entries WHERE entity_id = ? AND status = 'unlinked'", (EXH,))} == BEFORE | {"PV2610-004"})
d2 = j("get", f"/api/sql/entries?entity={EXH}")
check("afterwards only the October correction waits", [u["doc_no"] for u in d2["unlinked"]] == ["PV2610-004"] and len(d2["before_tracking"]) == len(BEFORE))

cs = j("post", "/api/sql/entries/create-all", json={"entity_id": SMP})
check("with no first month, Create payments for all adds payments for the whole year, as before",
      cs["created"] + cs["linked"] == len(ALL) - 2 and sorted(cs["corrections"]) == ["PV2602-003", "PV2610-004"], str(cs))

# ---------- the month pills' data ----------
ov = j("get", "/api/overview?month=2026-09")
by = {x["entity"]["code"]: x for x in ov["entities"]}
check("the Overview marks September before tracking for EXH, not for SMP, and carries first_month for the pill",
      by["EXH"]["before_first"] is True and by["SMP"]["before_first"] is False and by["EXH"]["entity"]["first_month"] == "2026-10")
mo = j("get", f"/api/month?entity={EXH}&month=2026-09")
check("the month page of September says it is before tracking", mo["before_first"] is True and mo["entity"]["first_month"] == "2026-10")
mo10 = j("get", f"/api/month?entity={EXH}&month=2026-10")
check("October, the first month tracked, is not", mo10["before_first"] is False)

# ---------- a voucher dated in a tracked month is never before tracking, whatever its description names ----------
con = db.connect()
ent = con.execute("SELECT * FROM entities WHERE id = ?", (EXH,)).fetchone()
misread = [("PAYMENT INV DATED OCT 15", "2026-11-20"), ("SERVICE MAY 2026 - NOV 2026", "2026-11-03"), ("JAN 0012 CLAIM", "2026-11-02")]
check("a November voucher naming a day (OCT 15), a range (MAY 2026 - NOV 2026) or a number read as a year is tracked",
      not any(db.entry_before_tracking(ent, t, day) for t, day in misread),
      str([(t, db.filing_month(t, day), db.entry_before_tracking(ent, t, day)) for t, day in misread]))
check("one dated before October and naming a month before it is before tracking; one of 30 September naming October isn't",
      db.entry_before_tracking(ent, "SALARY SEP 2026", "2026-09-25") and not db.entry_before_tracking(ent, "RENTAL OCT 26", "2026-09-30"))
check("the month a tracked entry is counted in: its own, or for 30 September naming October, October",
      db.entry_month(ent, "SALARY NOV 2026", "2026-11-03") == "2026-11" and db.entry_month(ent, "RENTAL OCT 26", "2026-09-30") == "2026-10")
imp = q("SELECT id FROM sql_imports WHERE entity_id = ? ORDER BY id LIMIT 1", (EXH,))[0]["id"]
added = [("PV2611-050", "2026-11-20", "PAYMENT INV DATED OCT 15", 301.0), ("PV2611-051", "2026-11-03", "SERVICE MAY 2026 - NOV 2026", 302.0),
         ("PV2611-052", "2026-11-02", "JAN 0012 CLAIM", 303.0), ("PV2609-050", "2026-09-30", "RENTAL OCT 26", 2200.0)]
con.close()
write("vouchers fetched later", *[("INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, "
                                   "doc_type, kind, status) VALUES (?, ?, ?, ?, ?, '', ?, 'out', 'PV', 'payment', 'unlinked')",
                                   (imp, EXH, no, day, text, amt)) for no, day, text, amt in added])
d3 = j("get", f"/api/sql/entries?entity={EXH}")
check("the SQL page lists them under SQL entries not linked, not under Before tracking",
      {u["doc_no"] for u in d3["unlinked"]} == {"PV2610-004"} | {a[0] for a in added}
      and not {a[0] for a in added} & {u["doc_no"] for u in d3["before_tracking"]}, str([u["doc_no"] for u in d3["unlinked"]]))
con = db.connect()
check("Next up puts the voucher of 30 September naming October in October",
      nextup._entry_cycle(ent, {"doc_date": "2026-09-30", "description": "RENTAL OCT 26"}) == "2026-10")
n3 = re.search(r"(\d+) SQL entr", sql_row(EXH))
check("Next up counts every entry the SQL page lists as not linked", n3 and int(n3.group(1)) == len(d3["unlinked"]), sql_row(EXH))
con.close()
ca2 = j("post", "/api/sql/entries/create-all", json={"entity_id": EXH})
made = {r["sql_ref"]: r["month"] for r in q("SELECT sql_ref, month FROM payments WHERE entity_id = ? AND sql_ref LIKE 'PV26%-05%'", (EXH,))}
check("Create payments for all makes them all, the 30 September voucher naming October in October",
      ca2["created"] == 4 and made == {"PV2611-050": "2026-11", "PV2611-051": "2026-11", "PV2611-052": "2026-11", "PV2609-050": "2026-10"},
      f"{ca2} {made}")
check("still no payment in a month before October", q("SELECT COUNT(*) n FROM payments WHERE entity_id = ? AND month < '2026-10'", (EXH,))[0]["n"] == 0)

# ---------- an invoice of 25 September is still offered to October's receipt ----------
write("a tenant paying rent", ("INSERT INTO payees (entity_id, name, category, desc_template, match_words, direction) "
                               "VALUES (?, 'Example Tenant B', 'receipt', 'Rent {month}', 'EXAMPLE TENANT B', 'in')", (EXH,)))
TENANT = q("SELECT id FROM payees WHERE name = 'Example Tenant B'")[0]["id"]
j("post", "/api/payments", json={"entity_id": EXH, "month": "2026-10", "description": "Rent from Example Tenant B",
                                 "amount": 2500.0, "due_date": "2026-10-05", "category": "other"})
RENT = q("SELECT id FROM payments WHERE description = 'Rent from Example Tenant B'")[0]["id"]
write("the rent is money in from the tenant", ("UPDATE payments SET direction = 'in', payee_id = ? WHERE id = ?", (TENANT, RENT)))
from hrp import sqlimport  # noqa: E402


def iv(day):
    return {"row": 1, "doc_no": f"IV{day[2:4]}{day[5:7]}-077", "date": day, "description": "RENTAL FOR OCTOBER", "payee": "EXAMPLE TENANT B",
            "amount": 2500.0, "kind": "invoice", "doc_type": "IV", "code": "300-T002", "direction": None, "einvoice": None}


con = db.connect()
near_iv, far_iv = sqlimport.propose(con, EXH, [iv("2026-09-25")])[0], sqlimport.propose(con, EXH, [iv("2026-08-01")])[0]
check("an invoice of 25 September is suggested October's receipt, and isn't shown as before tracking",
      near_iv["payment_id"] == RENT and near_iv["before_tracking"] is False, str(near_iv))
check("one of 1 August is suggested nothing and stays before tracking", far_iv["payment_id"] is None and far_iv["before_tracking"] is True, str(far_iv))
con.close()

# ---------- the Overview still counts a before-tracking month's bank lines until its statement is signed off ----------
acct = q("SELECT id FROM accounts WHERE entity_id = ? ORDER BY id LIMIT 1", (EXH,))[0]["id"]
write("a September statement", ("INSERT INTO statements (account_id, month, statement_date, opening, closing, imported_at, check_ok) "
                                 "VALUES (?, '2026-09', '2026-09-30', 0, -150, '2026-11-14', 1)", (acct,)))
ST = q("SELECT id FROM statements WHERE account_id = ? AND month = '2026-09'", (acct,))[0]["id"]
write("its lines", *[("INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance) VALUES (?, ?, ?, ?, ?, ?)",
                      (ST, k, f"2026-09-1{k}", f"EXAMPLE CHARGE {k}", -50.0 * k, -50.0 * k)) for k in (1, 2)])
sep = {x["entity"]["code"]: x for x in j("get", "/api/overview?month=2026-09")["entities"]}["EXH"]
check("September, before tracking, still counts its 2 bank lines to explain", sep["before_first"] and sep["unmatched_lines"] == 2,
      str(sep["unmatched_lines"]))
write("signed off before tracking", ("UPDATE statements SET reconciled_at = '2026-11-14', reconciled_how = 'before_tracking' WHERE id = ?", (ST,)))
sep = {x["entity"]["code"]: x for x in j("get", "/api/overview?month=2026-09")["entities"]}["EXH"]
check("once its statement is signed off, they aren't counted", sep["unmatched_lines"] == 0, str(sep["unmatched_lines"]))
js = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
check("the Overview keeps the bank lines and payment pills beside the grey pill for such a month",
      "flags.splice(0, flags.length, BEFORE_PILL, ...kept)" in js and "bank lines not explained`, true)" in js)


# ---------- unlinking says which list a voucher goes back to ----------
def link(doc_no, pid):
    sid = q("SELECT id FROM sql_entries WHERE entity_id = ? AND doc_no = ?", (EXH, doc_no))[0]["id"]
    j("post", f"/api/sql/entries/{sid}", json={"payment_id": pid})
    return sid


for desc in ("Example October claim A", "Example October claim B"):
    j("post", "/api/payments", json={"entity_id": EXH, "month": "2026-10", "description": desc, "amount": 1009.0,
                                     "due_date": "2026-10-20", "category": "other"})
CLAIM_A = q("SELECT id FROM payments WHERE description = 'Example October claim A'")[0]["id"]
CLAIM_B = q("SELECT id FROM payments WHERE description = 'Example October claim B'")[0]["id"]
sa = link("PV2609-001", CLAIM_A)
ua = j("post", f"/api/sql/entries/{sa}/unlink", json={})
check("unlinking a September voucher says it goes back under Before tracking", ua["before_tracking"] is True and ua["doc_no"] == "PV2609-001", str(ua))
sid10 = q("SELECT id FROM sql_entries WHERE entity_id = ? AND doc_no = 'PV2610-001'", (EXH,))[0]["id"]
pay10 = q("SELECT payment_id FROM sql_entries WHERE id = ?", (sid10,))[0]["payment_id"]
u10 = j("post", f"/api/sql/entries/{sid10}/unlink", json={})
check("unlinking an October voucher says it goes back under SQL entries not linked", u10["before_tracking"] is False, str(u10))
link("PV2610-001", pay10)
link("PV2608-001", CLAIM_B)
rm = j("delete", f"/api/payments/{CLAIM_B}", json={})
check("removing the payment says its September voucher goes back under Before tracking",
      rm["unlinked"] == ["PV2608-001"] and rm["before_tracking"] == ["PV2608-001"], str(rm))
check("the page lists both under Before tracking",
      {"PV2608-001", "PV2609-001"} <= {u["doc_no"] for u in j("get", f"/api/sql/entries?entity={EXH}")["before_tracking"]})
check("the toasts name the list the server says", "back under Before tracking on the SQL page" in js
      and 'r.before_tracking ? "Before tracking" : "SQL entries not linked"' in js)

print("All before-tracking checks passed.")
