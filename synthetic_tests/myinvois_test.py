"""MyInvois e-Invoices: a copy of SQL Account's MyInvois Transaction screen, saved from Excel, read by Fetch from SQL
exports, on made-up records only.

1. Update 33 on records at update 32: the table is made empty, the audit chain still checks out and start-up repairs
   nothing.
2. The copy is told by its headings, and an older copy made without headings by its shape (both layouts); a copy with a
   row that can't be read is refused whole; a single upload of it is sent to Fetch.
3. Which way each e-Invoice goes, by the company's TIN: issued, self-billed, received, other.
4. Fetch lists it with what is new, changed and unchanged; Import keeps it as an SQL export and fills in the e-Invoice
   of the SQL documents with the same number, so the self-billed e-Invoice checklist item is done; a status pasted from
   SQL after the copy was saved is kept.
5. A later copy that cancels an e-Invoice updates it (the audit trail shows Valid before, Cancelled after) and the
   checklist item is no longer done; e-Invoices the later copy leaves out are kept.
6. e-Invoices received are matched to supplier invoices and payment vouchers by the supplier's document number (with
   its TIN where the supplier's is known) or by TIN and amount; the rest are listed as not found in SQL's books.
7. A copy of another company's e-Invoices, or of a company not in Setup, is left out.
8. Review fixes: a cancelled attempt never replaces a document's other UUID, and a later paste of another UUID takes
   it with its own status; TIN-and-amount matches only plain invoices dated near the document, one e-Invoice to one
   document; a number named without the supplier's TIN needs its amount or name too; an issued e-Invoice fills only
   the document of its year and amount, never an ignored one; the grid pasted into the SQL box is sent to Fetch.

Companies, TINs, UUIDs, documents and amounts are made up.

Run: .venv\\Scripts\\python -m synthetic_tests.myinvois_test
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
import time as _time
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

tmp = Path(tempfile.mkdtemp(prefix="hrp-myinvois-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db, myinvois, sqlimport, sqlreport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
FOLDER = tmp / "downloads"
FOLDER.mkdir()
config.SETTINGS["sql_exports_dir"] = str(FOLDER)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}],
     "payees": [{"name": "EXAMPLE cloud subscription claim", "category": "claim_overseas", "amount": 88.44, "due_day": 25,
                 "start_date": "2026-10-01"}]},
    {"code": "EXO", "name": "Example Other Sdn Bhd", "accounts": [{"label": "Ops", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

OUR_TIN, OTHER_TIN = "C00000000010", "C00000000099"
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


# ---------- a workbook as Excel saves a pasted grid ----------

def letter(col):
    s, col = "", col + 1
    while col:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def workbook(table):
    """An .xlsx of one sheet: table is a list of rows, each a list of cells (str, float, datetime or None)."""
    strings, xml_rows = [], []
    for r, row in enumerate(table, 1):
        cells = []
        for col, v in enumerate(row):
            ref = f"{letter(col)}{r}"
            if v is None:
                continue
            if isinstance(v, str):
                if v not in strings:
                    strings.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{strings.index(v)}</v></c>')
            elif isinstance(v, datetime):
                cells.append(f'<c r="{ref}" s="1"><v>{(v - datetime(1899, 12, 30)).total_seconds() / 86400!r}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{v!r}</v></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                               '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {ns}><bookViews><workbookView windowWidth="21075"/></bookViews>'
                           '<sheets><sheet sheetId="1" name="Sheet1" r:id="rId3"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                                      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
                                      '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         '<numFmts count="1"><numFmt formatCode="yyyy-mm-dd h:mm:ss" numFmtId="164"/></numFmts><fonts count="1"><font/></fonts><fills count="1"><fill/></fills>'
                         '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                         '<cellXfs count="2"><xf numFmtId="0" xfId="0"/><xf numFmtId="164" xfId="0" applyNumberFormat="1"/></cellXfs></styleSheet>',
        "xl/sharedStrings.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings) + "</sst>",
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet {ns}><sheetData>{"".join(xml_rows)}</sheetData></worksheet>',
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, text)
    return out.getvalue()


HEAD = ["Doc No.", "UUID", "Type", "Version", "Currency", "Supplier Name", "Supplier TIN", "Buyer Name", "Buyer TIN",
        "Receiver TIN", "Submission ID", "Submission Channel", "Validated Date", "Received Date", "Issued Date", "Reject Date",
        "Status", "Total Amount", "Total Excluding Tax", "Total Net Amount"]


def uid(c):
    """A made-up UUID of 26 capitals and digits."""
    return (c * 4 + "Q5JKA274M3RP29RZR97M10")[:26]


def einv(doc, u, typ, sup, sup_tin, buy, buy_tin, status, total, issued, validated=None, rejected=None, cur="MYR"):
    return [doc, u, typ, 1.1, cur, sup, sup_tin, buy, buy_tin, buy_tin, "GF0B95E1M751P33J29RZR97M10", "IntermediaryERP",
            validated, issued, issued, rejected, status, total, total, total]


def old_row(r):
    """The same e-Invoice in the older 15-column layout (no Receiver TIN, Submission ID, Validated Date, Total
    Excluding Tax or Total Net Amount)."""
    return r[:9] + [r[11], r[13], r[14], r[15], r[16], r[17]]


US, SUP = "EXAMPLE HOLDINGS SDN BHD", "EXAMPLE SUPPLIER INC"
T = lambda d, h=10: datetime(2026, 11, d, h, 19, 44)
SELF = einv("PV2611-009", uid("A"), "Self-billed Invoice", SUP, "C00000000020", US, OUR_TIN, "Valid", 88.44, T(13), T(13, 14))
ISSUED = einv("AISB/2026/10/002", uid("B"), "Invoice", US, OUR_TIN, "EXAMPLE TENANT SDN BHD", "C00000000060", "Valid", 500.0, T(3), T(3, 11))
BY_NO = einv("INV-5521", uid("C"), "Invoice", "EXAMPLE SUPPLIES SDN BHD", "C00000000030", US, OUR_TIN, "Valid", 120.0, T(4), T(4, 12))
BY_TIN = einv("EN-88", uid("D"), "Invoice", "EXAMPLE NET SDN BHD", "C00000000040", US, OUR_TIN, "Valid", 230.5, T(5), T(5, 12))
WRONG_TIN = einv("INV-7777", uid("E"), "Invoice", "EXAMPLE VENDOR SDN BHD", "C00000000050", US, OUR_TIN, "Valid", 75.0, T(2), T(2, 12))
BEFORE = einv("OLD-1", uid("F"), "Invoice", "EXAMPLE VENDOR SDN BHD", "C00000000050", US, OUR_TIN, "Valid", 40.0,
              datetime(2026, 8, 15, 9), datetime(2026, 8, 15, 10))
OTHER = einv("ZZ-1", uid("G"), "Invoice", "EXAMPLE THIRD SDN BHD", "C00000000070", "EXAMPLE FOURTH SDN BHD", "C00000000080", "Valid", 10.0, T(6))
PASTED_LATER = einv("AISB/2026/10/003", uid("H"), "Invoice", US, OUR_TIN, "EXAMPLE TENANT SDN BHD", "C00000000060", "Cancelled", 300.0,
                    T(7), T(7, 11), T(8))
USD = einv("INV-US-1", uid("J"), "Invoice", "EXAMPLE OVERSEAS INC", "C00000000090", US, OUR_TIN, "Valid", 12.5, T(9), T(9, 12), cur="USD")
COPY1 = [HEAD, SELF, ISSUED, BY_NO, BY_TIN, WRONG_TIN, BEFORE, OTHER, PASTED_LATER, USD]

SAVED_AT = {}


def save(name, table_or_bytes, when):
    """A file in the downloads folder, saved at the time given."""
    data = table_or_bytes if isinstance(table_or_bytes, bytes) else workbook(table_or_bytes)
    p = FOLDER / name
    if p.exists():
        os.chmod(p, 0o666)
    p.write_bytes(data)
    stamp = _time.mktime(when.timetuple())
    os.utime(p, (stamp, stamp))
    return p


# ---------- 1. update 33 on records at update 32 ----------
full = db.MIGRATIONS[:]
check("update 33 is the MyInvois e-Invoices", len(full) == 33, len(full))
db.MIGRATIONS[:] = full[:32]
db.init()
check("the records start at update 32", q("PRAGMA user_version")[0]["user_version"] == 32)
EID, XID = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("AISB", "EXO"))
write("an SQL document pasted at update 32",
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'SQL listing pasted 1.xml', '2026-11-01T09:00:00', 1, 0)", (EID,)),
      ("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, doc_type, kind, status, einvoice, einvoice_status)
          VALUES (last_insert_rowid(), ?, 'AISB/2026/10/001', '2026-10-01', 'RENTAL OCTOBER 26', 400, 'IV', 'invoice', 'invoice', ?, 'Validated')""",
       (EID, uid("K"))))
db.MIGRATIONS[:] = full
trail = db.init()
check("update 33 runs", q("PRAGMA user_version")[0]["user_version"] == 33)
check("its table is made empty", q("SELECT COUNT(*) AS n FROM myinvois_docs")[0]["n"] == 0)
check("the SQL documents get when their e-Invoice was last known, empty to begin with",
      [(r["einvoice_as_at"], r["einvoice_from"]) for r in q("SELECT * FROM sql_entries")] == [(None, None)])
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out after update 33", v["ok"], v)
check("start-up repaired nothing", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)
check("the new table is captured by the audit trail", q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit_myinvois_docs%'")[0]["n"] >= 3)

c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def preview(eid=None):
    return j("post", "/api/sql/preview", json={"entity_id": eid or EID, "fetch": True})


def fetch(eid=None):
    p = preview(eid)
    if p.get("nothing_new"):
        return p, None
    return p, j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})


# ---------- 2. reading the copy ----------
got = sqlreport.read(workbook(COPY1))
check("a copy with headings is read as MyInvois e-Invoices", got and got[0] == "myinvois" and got[1]["headings"] is True
      and len(got[1]["rows"]) == 9, str(got)[:300])
r0 = got[1]["rows"][0]
check("each e-Invoice's fields are read, amounts in sen and dates as date and time",
      r0 == {"doc_no": "PV2611-009", "uuid": uid("A"), "type": "Self-billed Invoice", "version": "1.1", "currency": "MYR",
             "supplier_name": SUP, "supplier_tin": "C00000000020", "buyer_name": US, "buyer_tin": OUR_TIN, "receiver_tin": OUR_TIN,
             "submission_id": "GF0B95E1M751P33J29RZR97M10", "channel": "IntermediaryERP", "validated_at": "2026-11-13 14:19:44",
             "received_at": "2026-11-13 10:19:44", "issued_at": "2026-11-13 10:19:44", "rejected_at": None, "status": "Valid",
             "total_sen": 8844, "excl_tax_sen": 8844, "net_sen": 8844}, r0)
check("its period is the issued days", got[1]["period"] == ["2026-08-15", "2026-11-13"], got[1]["period"])
got_new = sqlreport.read(workbook(COPY1[1:]))
check("a copy without headings, in the 20-column layout, is told by its shape",
      got_new and got_new[0] == "myinvois" and got_new[1]["headings"] is False and got_new[1]["rows"] == got[1]["rows"])
got_old = sqlreport.read(workbook([old_row(x) for x in COPY1[1:]]))
check("an older copy without headings, in the 15-column layout, is read too",
      got_old and got_old[0] == "myinvois" and got_old[1]["rows"][0]["validated_at"] is None
      and got_old[1]["rows"][0]["issued_at"] == "2026-11-13 10:19:44" and got_old[1]["rows"][0]["total_sen"] == 8844
      and [x["uuid"] for x in got_old[1]["rows"]] == [x["uuid"] for x in got[1]["rows"]], str(got_old)[:400])
check("another workbook is not taken for one", sqlreport.read(workbook([["Name", "Amount"], ["Rent", 100.0]])) is None)
bad = [HEAD, SELF, ISSUED[:1] + ["NOTAUUID"] + ISSUED[2:]]
try:
    sqlreport.read(workbook(bad))
    refused = None
except sqlreport.ReportError as ex:
    refused = str(ex)
check("a copy with a row that can't be read is refused whole, in a plain sentence",
      refused and refused.startswith("Row 3 of this MyInvois copy has a UUID") and "nothing was taken" in refused, refused)
bad_amount = [HEAD, SELF[:17] + ["lots"] + SELF[18:]]
try:
    sqlreport.read(workbook(bad_amount))
    refused = None
except sqlreport.ReportError as ex:
    refused = str(ex)
check("and so is one with an amount it can't read", refused and "an amount it can't read (lots)" in refused, refused)
try:
    sqlimport.read_rows("my-invoice-trans.xlsx", workbook(COPY1))
    refused = None
except sqlimport.SqlImportError as ex:
    refused = str(ex)
check("choosing the copy as a single file sends it to Fetch, rather than reading it as a listing",
      refused and "MyInvois Transaction screen" in refused and "Fetch from SQL exports" in refused, refused)

# ---------- 3. which way each e-Invoice goes ----------
ways = {x["doc_no"]: myinvois.direction(x, OUR_TIN) for x in got[1]["rows"]}
check("direction by the company's TIN: issued, self-billed, received, other",
      ways == {"PV2611-009": "self_billed", "AISB/2026/10/002": "issued", "INV-5521": "received", "EN-88": "received",
               "INV-7777": "received", "OLD-1": "received", "ZZ-1": "other", "AISB/2026/10/003": "issued", "INV-US-1": "received"}, ways)
check("a self-billed e-Invoice whose buyer is another company is other",
      myinvois.direction({**got[1]["rows"][0], "buyer_tin": "C00000000070"}, OUR_TIN) == "other")
check("and nothing is ours without a TIN", myinvois.direction(got[1]["rows"][1], "") == "other")

# ---------- the company, its documents in SQL and its checklist ----------
con = db.connect()
con.arm("user", "test: set up November")
db.auto_open(con, EID, "2026-11")
con.commit()
con.disarm()
con.close()
CLAIM = q("SELECT id FROM payments WHERE entity_id = ? AND month = '2026-11' AND category = 'claim_overseas'", (EID,))[0]["id"]
write("the company's TIN, its suppliers and its SQL documents",
      ("UPDATE entities SET first_month = '2026-10' WHERE id = ?", (EID,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, tin) VALUES (?, 'supplier', 'Example Supplies', '400-E001', 'C00000000030')", (EID,)),
      ("INSERT INTO parties (entity_id, kind, name, sql_code, tin) VALUES (?, 'supplier', 'Example Net', '400-E002', 'C00000000040')", (EID,)),
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'SQL exports fetched 1.csv', '2026-11-14T08:00:00', 6, 1)", (EID,)))
IMP = q("SELECT MAX(id) AS id FROM sql_imports")[0]["id"]
ENTRY = """INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
           status, payment_id, code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
write("SQL documents imported before the copy",
      (ENTRY, (IMP, EID, "PV2611-009", "2026-11-13", "CLAIM FOR EXAMPLE CLOUD SUBSCRIPTION", "STAFF ONE", 88.44, "out", "PV", "payment", "linked", CLAIM, None)),
      (ENTRY, (IMP, EID, "aisb/2026/10/002 ", "2026-11-03", "RENTAL NOVEMBER 26", "EXAMPLE TENANT", 500.0, None, "IV", "invoice", "invoice", None, "300-T001")),
      (ENTRY, (IMP, EID, "PI-00007", "2026-11-04", "EXAMPLE SUPPLIES INV-5521 OFFICE PAPER", "EXAMPLE SUPPLIES", 120.0, None, "PI", "invoice", "invoice", None, "400-E001")),
      (ENTRY, (IMP, EID, "PV2611-020", "2026-11-05", "PAYMENT TO EXAMPLE NET", "EXAMPLE NET", 230.5, "out", "PV", "payment", "unlinked", None, "400-E002")),
      (ENTRY, (IMP, EID, "PI-00008", "2026-11-02", "EXAMPLE SUPPLIES INV-7777", "EXAMPLE SUPPLIES", 75.0, None, "PI", "invoice", "invoice", None, "400-E001")),
      ("UPDATE payments SET sql_ref = 'PV2611-009', paid_date = '2026-11-13', amount = 88.44 WHERE id = ?", (CLAIM,)))
# A document whose e-Invoice was pasted from SQL's grid after the copy was saved: what SQL said is newer.
write("a document pasted after the copy was saved",
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'SQL listing pasted 2.xml', '2026-11-14T10:30:00', 1, 0)", (EID,)),
      ("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, doc_type, kind, status, einvoice, einvoice_status)
          VALUES (last_insert_rowid(), ?, 'AISB/2026/10/003', '2026-11-07', 'RENTAL DEPOSIT', 300, 'IV', 'invoice', 'invoice', ?, 'Validated')""",
       (EID, uid("H"))))


def selfbilled_item():
    with db.connect() as r:
        ent = r.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
        task = r.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = '2026-11' AND code = 'einv-selfbilled'", (EID,)).fetchone()
        pay = r.execute("SELECT * FROM payments WHERE id = ?", (CLAIM,)).fetchone()
        return db.task_status(r, ent, task), db.evidence(r, pay=pay)


st, ev = selfbilled_item()
check("before any MyInvois copy, the self-billed e-Invoice item is not done and the claim has no e-Invoice",
      not st["done"] and "einvoice" not in ev, (st, ev))

# ---------- 7. (first) a copy no company's TIN is in is left out while the TIN isn't in Setup ----------
save("my-invoice-trans.xlsx", COPY1, datetime(2026, 11, 14, 10, 0))
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "my-invoice-trans.xlsx")
check("without the company's TIN in Setup, the copy is left out as for an unknown company",
      f["status"] == "unknown_company" and "TIN isn't in Setup yet" in f["reason"] and p.get("nothing_new"), f)
write("the company's TIN", ("UPDATE entities SET tin = ? WHERE id = ?", (OUR_TIN, EID)), ("UPDATE entities SET tin = ? WHERE id = ?", (OTHER_TIN, XID)))

# ---------- 4. Fetch and Import ----------
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "my-invoice-trans.xlsx")
check("Fetch lists the copy as MyInvois e-Invoices with what is new, changed and unchanged",
      f["status"] == "read" and f["report"] == "myinvois" and f["title"] == "MyInvois e-Invoices" and f["rows"] == 9
      and (f["new"], f["changed"], f["unchanged"]) == (9, 0, 0) and (f["issued"], f["self_billed"], f["received"], f["other"]) == (2, 1, 5, 1)
      and p["myinvois"]["files"] == [{"name": "my-invoice-trans.xlsx", "rows": 9}] and p["records"] == [], f)
res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
mi = res.get("myinvois") or {}
check("Import keeps the copy's e-Invoices", mi.get("files") and mi["files"][0]["new"] == 9
      and q("SELECT COUNT(*) AS n FROM myinvois_docs WHERE entity_id = ?", (EID,))[0]["n"] == 9, res)
kept = q("SELECT * FROM documents WHERE entity_id = ? AND doc_type = 'sqlexport' AND original_name = 'my-invoice-trans.xlsx'", (EID,))
check("the file is kept as an SQL export of the company", len(kept) == 1)
docs = {r["doc_no"]: r for r in q("SELECT * FROM myinvois_docs WHERE entity_id = ?", (EID,))}
check("each e-Invoice is kept with its direction", {k: v["direction"] for k, v in docs.items()} == ways)
ents = {r["doc_no"].strip().upper(): r for r in q("SELECT * FROM sql_entries WHERE entity_id = ?", (EID,))}
check("the self-billed PV takes its e-Invoice, validated in the words a paste of SQL's grid uses",
      (ents["PV2611-009"]["einvoice"], ents["PV2611-009"]["einvoice_status"], ents["PV2611-009"]["einvoice_from"]) == (uid("A"), "Validated", "myinvois"))
check("the issued invoice takes its e-Invoice, its number matched whatever its capitals and spaces",
      (ents["AISB/2026/10/002"]["einvoice"], ents["AISB/2026/10/002"]["einvoice_status"]) == (uid("B"), "Validated"))
check("the e-Invoice link is left as it was", ents["PV2611-009"]["einvoice_link"] is None)
check("a status pasted from SQL after the copy was saved is kept",
      ents["AISB/2026/10/003"]["einvoice_status"] == "Validated" and ents["AISB/2026/10/003"]["einvoice_from"] is None)
notes = mi.get("notes", [])
check("Import says per document what was filled in, and what was kept",
      any(n.startswith("PV2611-009: self-billed e-Invoice AAAAQ5JK… filled in from MyInvois, Validated") for n in notes)
      and any(n.startswith("aisb/2026/10/002 : issued e-Invoice") for n in notes)
      and any(n.startswith("AISB/2026/10/003: kept its e-Invoice status from SQL (Validated)") for n in notes), notes)
st, ev = selfbilled_item()
check("the claim's self-billed e-Invoice is shown by its SQL voucher, so the checklist item is done",
      st["done"] and st["auto"] and ev.get("einvoice", {}).get("ref") == f"e-Invoice {uid('A')}", (st, ev))

# ---------- 6. received e-Invoices ----------
check("a received e-Invoice is matched to the supplier invoice that names the supplier's number",
      docs["INV-5521"]["entry_id"] == ents["PI-00007"]["id"] and docs["INV-5521"]["matched_by"] == "doc_no")
check("one is matched by the supplier's TIN and the amount when the number is nowhere",
      docs["EN-88"]["entry_id"] == ents["PV2611-020"]["id"] and docs["EN-88"]["matched_by"] == "tin_amount")
check("a document naming the number but whose supplier has another TIN is not a match", docs["INV-7777"]["entry_id"] is None)
d = j("get", f"/api/sql/entries?entity={EID}")
m = d["myinvois"]
check("the SQL page lists the valid e-Invoices received but not in SQL's books, from the first month tracked",
      [r["doc_no"] for r in m["unmatched"]] == ["INV-US-1", "INV-7777"] and m["since"] == "2026-10", [r["doc_no"] for r in m["unmatched"]])
check("it shows each e-Invoice with the SQL document it is in, and the copy read",
      len(m["rows"]) == 9 and m["counts"] == {"issued": 2, "self_billed": 1, "received": 5, "other": 1}
      and next(r for r in m["rows"] if r["doc_no"] == "INV-5521")["entry_doc_no"] == "PI-00007"
      and m["sources"][0]["name"] == "my-invoice-trans.xlsx" and m["sources"][0]["saved"] == "2026-11-14T10:00:00", m["sources"])
pv = next(x for x in d["einvoices"] if x["doc_no"] == "PV2611-009")
check("the e-Invoices card shows what MyInvois says beside the SQL document",
      pv["myinvois"] == {"uuid": uid("A"), "type": "Self-billed Invoice", "status": "Valid", "validated_at": "2026-11-13 14:19:44",
                         "direction": "self_billed"}, pv)
p, _ = fetch()
check("the same copy is not read again", p.get("nothing_new") and next(x for x in p["fetch"]["files"] if x["name"] == "my-invoice-trans.xlsx")["status"] == "imported_before")

# ---------- 5. a later copy: one e-Invoice cancelled, the rest filtered out ----------
CANCELLED = SELF[:15] + [T(14, 9), "Cancelled"] + SELF[17:]
save("my-invoice-trans (2).xlsx", [HEAD, CANCELLED, ISSUED], datetime(2026, 11, 14, 11, 0))
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "my-invoice-trans (2).xlsx")
check("Fetch reads the later copy (another fingerprint): one changed, one unchanged",
      f["status"] == "read" and (f["new"], f["changed"], f["unchanged"]) == (0, 1, 1), f)
before_audit = q("SELECT MAX(id) AS id FROM audit_row")[0]["id"]
res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
row = q("SELECT * FROM myinvois_docs WHERE entity_id = ? AND uuid = ?", (EID, uid("A")))[0]
check("the cancelled e-Invoice takes its new status and reject date", (row["status"], row["rejected_at"]) == ("Cancelled", "2026-11-14 09:19:44"))
check("the SQL document says it is cancelled", q("SELECT einvoice_status FROM sql_entries WHERE doc_no = 'PV2611-009'")[0]["einvoice_status"] == "Cancelled")
trail_rows = q("SELECT before, after FROM audit_row WHERE tbl = 'myinvois_docs' AND op = 'update' AND id > ?", (before_audit,))
check("the audit trail keeps the status before and after",
      any(json.loads(t["before"]).get("status") == "Valid" and json.loads(t["after"]).get("status") == "Cancelled" for t in trail_rows), trail_rows)
check("e-Invoices the later copy leaves out are kept", q("SELECT COUNT(*) AS n FROM myinvois_docs WHERE entity_id = ?", (EID,))[0]["n"] == 9)
st, ev = selfbilled_item()
check("the self-billed e-Invoice item is no longer done once MyInvois says it is cancelled", not st["done"] and "einvoice" not in ev, (st, ev))
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail still checks out", v["ok"], v)

# An older copy found later changes nothing.
save("my-invoice-trans (old).xlsx", [HEAD, SELF], datetime(2026, 11, 13, 18, 0))
p = preview()
f = next(x for x in p["fetch"]["files"] if x["name"] == "my-invoice-trans (old).xlsx")
check("a copy saved before the one read last is counted as left as the later copy says", (f["new"], f["changed"], f["older"]) == (0, 0, 1), f)
j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
check("and its older status changes nothing", q("SELECT status FROM myinvois_docs WHERE uuid = ?", (uid("A"),))[0]["status"] == "Cancelled"
      and q("SELECT einvoice_status FROM sql_entries WHERE doc_no = 'PV2611-009'")[0]["einvoice_status"] == "Cancelled")

# ---------- 7. another company's copy ----------
OTHERS = [HEAD, einv("EXO-1", uid("L"), "Invoice", "EXAMPLE OTHER SDN BHD", OTHER_TIN, "EXAMPLE BUYER SDN BHD", "C00000000061", "Valid", 99.0, T(10))]
save("other.xlsx", OTHERS, datetime(2026, 11, 14, 12, 0))
STRANGER = [HEAD, einv("ST-1", uid("M"), "Invoice", "EXAMPLE STRANGER SDN BHD", "C00000000071", "EXAMPLE BUYER SDN BHD", "C00000000061", "Valid", 9.0, T(10))]
save("stranger.xlsx", STRANGER, datetime(2026, 11, 14, 12, 5))
p = preview()
fs = {x["name"]: x for x in p["fetch"]["files"]}
check("a copy of another company's e-Invoices is left out for it", fs["other.xlsx"]["status"] == "other_company" and "EXO" in fs["other.xlsx"]["reason"], fs["other.xlsx"])
check("a copy of a company not in Setup is left out as unknown", fs["stranger.xlsx"]["status"] == "unknown_company"
      and "Setup › Companies" in fs["stranger.xlsx"]["reason"], fs["stranger.xlsx"])
check("neither is kept", not q("SELECT 1 FROM myinvois_docs WHERE uuid IN (?, ?)", (uid("L"), uid("M"))))
save("broken.xlsx", bad, datetime(2026, 11, 14, 12, 10))
p = preview()
fb = next(x for x in p["fetch"]["files"] if x["name"] == "broken.xlsx")
check("a malformed copy is named in Fetch with why, and nothing of it is kept",
      fb["status"] == "unreadable" and fb["reason"].startswith("Row 3 of this MyInvois copy") and not q("SELECT 1 FROM documents WHERE original_name = 'broken.xlsx'"), fb)

# A document imported after the copy was read takes its e-Invoice then.
LATE = einv("PV2611-030", uid("N"), "Self-billed Invoice", SUP, "C00000000020", US, OUR_TIN, "Valid", 15.0, T(14), T(14, 15))
save("my-invoice-trans (3).xlsx", [HEAD, LATE], datetime(2026, 11, 14, 13, 0))
p = preview()
res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
check("a self-billed e-Invoice whose PV isn't in SQL's documents yet says so",
      any(n.startswith("PV2611-030: self-billed e-Invoice") and "no SQL document with this number yet" in n for n in res["myinvois"]["notes"]), res["myinvois"]["notes"])
txt = "Doc No\tDoc Date\tDescription\tAmount\tDoc Type\nPV2611-030\t14/11/2026\tCLAIM FOR EXAMPLE CLOUD STORAGE\t15.00\tPV\n"
pp = j("post", "/api/sql/preview", json={"entity_id": EID, "text": txt})
j("post", "/api/sql/apply", json={"token": pp["token"], "header_row": pp["header_row"], "mapping": pp["mapping"], "links": {}})
late = q("SELECT einvoice, einvoice_status FROM sql_entries WHERE doc_no = 'PV2611-030'")
check("once the PV is imported, it takes its e-Invoice from MyInvois", late == [{"einvoice": uid("N"), "einvoice_status": "Validated"}], late)

# ---------- 8. review fixes ----------
X, Y, X2, Y2, Z = uid("P"), uid("R"), uid("S"), uid("U"), uid("V")
ENT2 = """INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, doc_type, kind, status, code,
          einvoice, einvoice_status) VALUES (last_insert_rowid(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
write("documents for the review fixes",
      ("INSERT INTO parties (entity_id, kind, name, sql_code, tin) VALUES (?, 'supplier', 'Example Line', '400-E003', 'C00000000041')", (EID,)),
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'SQL listing pasted 3.txt', '2026-11-01T09:00:00', 1, 0)", (EID,)),
      (ENT2, (EID, "IV-00050", "2026-11-01", "SERVICES NOVEMBER", "EXAMPLE TENANT", 150.0, "IV", "invoice", "invoice", "300-T001", X, "Validated")))
write("more documents for the review fixes",
      ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'SQL exports fetched 2.csv', '2026-11-01T09:05:00', 9, 0)", (EID,)),
      (ENT2, (EID, "IV-00051", "2026-11-01", "SERVICES EXTRA", "EXAMPLE TENANT", 150.0, "IV", "invoice", "invoice", "300-T001", None, None)),
      ("UPDATE sql_entries SET import_id = (SELECT MAX(id) FROM sql_imports) WHERE doc_no = 'IV-00051'", ()),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "PV2610-030", "2026-10-25", "PAYMENT TO EXAMPLE LINE OCTOBER", "EXAMPLE LINE", 230.5, "PV", "payment", "unlinked", "400-E003", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "PV2612-031", "2026-12-03", "PAYMENT TO EXAMPLE LINE DECEMBER", "EXAMPLE LINE", 99.0, "PV", "payment", "unlinked", "400-E003", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "PI-00009", "2026-11-03", "EXAMPLE PRINTERS INV-0001 TONER", "EXAMPLE PRINTERS", 80.0, "PI", "invoice", "invoice", "400-P001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "PI-00010", "2026-11-03", "EXAMPLE INKWORKS INV-0002 INK", "EXAMPLE INKWORKS", 45.0, "PI", "invoice", "invoice", "400-P002", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00001", "2025-01-05", "RENTAL JANUARY 25", "EXAMPLE TENANT", 100.0, "IV", "invoice", "invoice", "300-T001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00001", "2026-01-05", "RENTAL JANUARY 26", "EXAMPLE TENANT", 250.0, "IV", "invoice", "invoice", "300-T001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00002", "2026-02-01", "RENTAL FEBRUARY 26", "EXAMPLE TENANT", 60.0, "IV", "invoice", "invoice", "300-T001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00002", "2026-02-02", "RENTAL FEBRUARY 26 DUPLICATE", "EXAMPLE TENANT", 60.0, "IV", "invoice", "ignored", "300-T001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00003", "2026-03-01", "RENTAL MARCH 26", "EXAMPLE TENANT", 70.0, "IV", "invoice", "invoice", "300-T001", None, None)),
      (ENT2.replace("last_insert_rowid()", "(SELECT MAX(id) FROM sql_imports)"),
       (EID, "IV-00003", "2025-03-01", "RENTAL MARCH 25", "EXAMPLE TENANT", 70.0, "IV", "invoice", "invoice", "300-T001", None, None)))
D = lambda y, mo, d: datetime(y, mo, d, 10, 0)
TEN = "EXAMPLE TENANT SDN BHD"
LINE, INK = ("EXAMPLE LINE SDN BHD", "C00000000041"), ("EXAMPLE INKWORKS SDN BHD", "C00000000077")
COPY4 = [HEAD,
         einv("IV-00050", Y, "Invoice", US, OUR_TIN, TEN, "C00000000060", "Cancelled", 150.0, D(2026, 10, 31), None, D(2026, 10, 31)),
         einv("IV-00051", Y2, "Invoice", US, OUR_TIN, TEN, "C00000000060", "Cancelled", 150.0, D(2026, 10, 31), None, D(2026, 10, 31)),
         einv("EN-10", uid("W"), "Invoice", *LINE, US, OUR_TIN, "Valid", 230.5, D(2026, 10, 20), D(2026, 10, 20)),
         einv("EN-11", uid("X"), "Invoice", *LINE, US, OUR_TIN, "Valid", 230.5, D(2026, 11, 20), D(2026, 11, 20)),
         einv("EN-CN1", uid("Y"), "Credit Note", *LINE, US, OUR_TIN, "Valid", 230.5, D(2026, 10, 22), D(2026, 10, 22)),
         einv("EN-12", uid("Z"), "Invoice", *LINE, US, OUR_TIN, "Valid", 99.0, D(2026, 12, 1), D(2026, 12, 1)),
         einv("EN-13", uid("1"), "Invoice", *LINE, US, OUR_TIN, "Valid", 99.0, D(2026, 12, 2), D(2026, 12, 2)),
         einv("INV-0001", uid("2"), "Invoice", *INK, US, OUR_TIN, "Valid", 999.0, D(2026, 11, 3), D(2026, 11, 3)),
         einv("INV-0002", uid("3"), "Invoice", *INK, US, OUR_TIN, "Valid", 12.0, D(2026, 11, 3), D(2026, 11, 3)),
         einv("IV-00001", Z, "Invoice", US, OUR_TIN, TEN, "C00000000060", "Valid", 250.0, D(2026, 1, 5), D(2026, 1, 5)),
         einv("IV-00002", uid("4"), "Invoice", US, OUR_TIN, TEN, "C00000000060", "Valid", 60.0, D(2026, 2, 1), D(2026, 2, 1)),
         einv("IV-00003", uid("5"), "Invoice", US, OUR_TIN, TEN, "C00000000060", "Valid", 70.0, D(2026, 3, 1), D(2026, 3, 1))]
save("my-invoice-trans (4).xlsx", COPY4, datetime(2026, 11, 2, 8, 0))
p = preview()
res = j("post", "/api/sql/apply", json={"token": p["token"], "header_row": p["header_row"], "mapping": p["mapping"], "links": {}})
notes = res["myinvois"]["notes"]
e50 = q("SELECT einvoice, einvoice_status, einvoice_from FROM sql_entries WHERE doc_no = 'IV-00050'")[0]
check("a cancelled attempt in a later copy never replaces the document's own validated UUID it doesn't name",
      (e50["einvoice"], e50["einvoice_status"], e50["einvoice_from"]) == (X, "Validated", None)
      and any(n.startswith("IV-00050: kept its e-Invoice PPPPQ5JK… (Validated); MyInvois holds only") for n in notes), (e50, notes))
e51 = q("SELECT einvoice, einvoice_status, einvoice_from FROM sql_entries WHERE doc_no = 'IV-00051'")[0]
check("a document without an e-Invoice still takes the cancelled one", (e51["einvoice"], e51["einvoice_status"], e51["einvoice_from"]) == (Y2, "Cancelled", "myinvois"), e51)
grid = ("Doc No\tDoc Date\tDescription\tAmount\tDoc Type\tE-Invoice UUID\tE-Invoice Status\n"
        f"IV-00050\t01/11/2026\tSERVICES NOVEMBER\t150.00\tIV\t{X}\tValidated\n"
        f"IV-00051\t01/11/2026\tSERVICES EXTRA\t150.00\tIV\t{X2}\tValidated\n")
pp = j("post", "/api/sql/preview", json={"entity_id": EID, "text": grid})
j("post", "/api/sql/apply", json={"token": pp["token"], "header_row": pp["header_row"], "mapping": pp["mapping"], "links": {}})
got50 = q("SELECT einvoice, einvoice_status FROM sql_entries WHERE doc_no = 'IV-00050'")[0]
got51 = q("SELECT einvoice, einvoice_status, einvoice_from FROM sql_entries WHERE doc_no = 'IV-00051'")[0]
check("pasting SQL's grid again leaves the validated UUID as it was", (got50["einvoice"], got50["einvoice_status"]) == (X, "Validated"), got50)
check("a paste with another UUID than MyInvois filled in takes SQL's UUID with its status, never the old UUID as validated",
      (got51["einvoice"], got51["einvoice_status"], got51["einvoice_from"]) == (X2, "Validated", None), got51)
docs = {r["doc_no"]: r for r in q("SELECT * FROM myinvois_docs WHERE entity_id = ?", (EID,))}
ents = {r["doc_no"]: r for r in q("SELECT * FROM sql_entries WHERE entity_id = ? AND doc_no IN ('PV2610-030', 'PV2612-031', 'PI-00009', 'PI-00010')", (EID,))}
check("by TIN and amount, an invoice links to the payment dated near it",
      docs["EN-10"]["entry_id"] == ents["PV2610-030"]["id"] and docs["EN-10"]["matched_by"] == "tin_amount", docs["EN-10"])
check("a later month's invoice is not taken for an earlier payment, nor a credit note for any",
      docs["EN-11"]["entry_id"] is None and docs["EN-CN1"]["entry_id"] is None, (docs["EN-11"], docs["EN-CN1"]))
check("two e-Invoices after one document by TIN and amount: neither is linked",
      docs["EN-12"]["entry_id"] is None and docs["EN-13"]["entry_id"] is None)
unm = [r["doc_no"] for r in j("get", f"/api/sql/entries?entity={EID}")["myinvois"]["unmatched"]]
check("so they are listed as not found in SQL's books", {"EN-11", "EN-CN1", "EN-12", "EN-13", "INV-0001"} <= set(unm) and "EN-10" not in unm, unm)
check("a supplier number named by another supplier's document, without a TIN, amount or name to back it, is not a match",
      docs["INV-0001"]["entry_id"] is None)
check("one whose document names the supplier is", docs["INV-0002"]["entry_id"] == ents["PI-00010"]["id"] and docs["INV-0002"]["matched_by"] == "doc_no")
check("short and digits-only numbers are never taken as named in a description",
      not myinvois._mentions("RENEWAL 2026 LICENCE", "2026") and not myinvois._mentions("REF A12 X", "A12")
      and myinvois._mentions("EXAMPLE INV-0002 INK", "INV-0002") and myinvois._mentions("REF 20261105", "20261105"))
iv1 = {r["doc_date"]: r for r in q("SELECT * FROM sql_entries WHERE doc_no = 'IV-00001'")}
check("an issued e-Invoice fills only the document of its year and amount, not another year's with the same number",
      iv1["2026-01-05"]["einvoice"] == Z and iv1["2025-01-05"]["einvoice"] is None
      and docs["IV-00001"]["entry_id"] == iv1["2026-01-05"]["id"], iv1)
iv2 = {r["status"]: r for r in q("SELECT * FROM sql_entries WHERE doc_no = 'IV-00002'")}
check("an ignored document with the same number is left alone", iv2["invoice"]["einvoice"] == uid("4") and iv2["ignored"]["einvoice"] is None, iv2)
iv3 = q("SELECT einvoice FROM sql_entries WHERE doc_no = 'IV-00003'")
check("when amount and date don't settle which document it is, none is filled in and Import says so",
      all(r["einvoice"] is None for r in iv3) and docs["IV-00003"]["entry_id"] is None
      and any(n.startswith("IV-00003: issued e-Invoice") and "could be more than one" in n for n in notes), notes)
tsv = "\n".join("\t".join("" if v is None else (v.strftime("%d/%m/%Y %H:%M:%S") if isinstance(v, datetime) else str(v)) for v in row)
                for row in COPY4[:4])
for label, text in (("with its headings", tsv), ("without headings", tsv.split("\n", 1)[1])):
    r = j("post", "/api/sql/preview", 400, json={"entity_id": EID, "text": text})
    check(f"pasting the MyInvois grid {label} into the SQL box says to save it from Excel and use Fetch",
          "MyInvois Transaction screen" in r["error"] and "Excel" in r["error"] and "Fetch from SQL exports" in r["error"], r)
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out at the end", v["ok"], v)

print(f"\nAll {len(passed)} checks passed.")
