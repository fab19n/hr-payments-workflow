"""Printed debit and credit notes, foreign-currency self-billed e-Invoices, and the print settings in setup.json, on
made-up records only.

1. A customer debit note (DN) prints as Debit Note and a credit note (CN) as Credit Note, in the invoice's layout: a
   credit note's lines are its debits other than the customer's account, its total is the customer's credit, and its
   amounts print as positive figures, as SQL prints them. Refused as invoices are (no lines, lines that disagree with
   the listing). A credit note prints no bank details. Its Ref (the invoice it is set against) prints under Terms only
   when the listing gave it and that invoice is in the documents fetched.
2. The SQL page's buttons say Debit note PDF and Credit note PDF; the month's zip of customer invoices holds the debit
   and credit notes too, each named by its doc no.
3. A self-billed e-Invoice in US dollars: the amount heading is in USD, the lines add up to MyInvois's total, and
   under the total a small line says it was paid as MYR <the voucher's total> by <the PV>. In ringgit, no such line.
4. setup.json carries the print settings (the company's address, phone, email, website, old registration no., the
   words under the signature, the bank account on invoices by its name and number; the bank address and transfer
   code; the customers' address lines, attention, phone and terms) and the logo and signature images. A new install
   imports them as they were (the images stored again, by fingerprint); an image whose fingerprint doesn't match, that
   isn't PNG or JPEG, or is over 2 MB is refused; a file made before them still imports.

Companies, customers, banks, TINs, UUIDs, documents and amounts are made up.

Run: .venv\\Scripts\\python -m synthetic_tests.invoice_notes_test
"""
import base64
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
from synthetic_tests.appsource import app_source  # noqa: E402
import tempfile
import zipfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-invoice-notes-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # a new install: imports <setup.json> (after the refusals) and writes what it holds

from hrp import audit, config, db, invoicepdf, ledger, setupfile  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

from PIL import Image  # noqa: E402
from pypdf import PdfReader  # noqa: E402

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


def write(why, fn):
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        out = fn(con)
        con.commit()
        return out
    except Exception:
        con.rollback()
        raise
    finally:
        con.disarm()
        con.close()


c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def text_of(data):
    return " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages).split())


def baselines(data):
    out = []
    for p in PdfReader(io.BytesIO(data)).pages:
        def seen(text, cm, tm, font, size):
            if text.strip():
                out.append((text.strip(), (792 - (tm[5] * cm[3] + cm[5])) * 25.4 / 72, (tm[4] * cm[0] + cm[4]) * 25.4 / 72))
        p.extract_text(visitor_text=seen)
    return out


PRINT_COLS = ("address", "phone", "email", "website", "old_reg_no", "sign_label")

if CHILD:  # ---------- a new install ----------
    db.init()
    src, out = Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(src.read_text(encoding="utf-8"))
    res = {"refused": {}}

    def attempt(name, d):
        r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": d, "preview": True})
        res["refused"][name] = (r.status_code, (r.get_json() or {}).get("error"))

    bad = json.loads(json.dumps(data))
    bad["entities"][0]["logo"]["sha256"] = "0" * 64
    attempt("fingerprint", bad)
    gif = b"GIF89a" + b"\x00" * 50
    bad = json.loads(json.dumps(data))
    bad["entities"][0]["logo"] = {"name": "logo.gif", "sha256": hashlib.sha256(gif).hexdigest(), "data": base64.b64encode(gif).decode()}
    attempt("gif", bad)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (invoicepdf.MAX_IMAGE + 10)
    bad = json.loads(json.dumps(data))
    bad["entities"][0]["logo"] = {"name": "logo.png", "sha256": hashlib.sha256(big).hexdigest(), "data": base64.b64encode(big).decode()}
    attempt("big", bad)
    bad = json.loads(json.dumps(data))
    bad["entities"][0]["invoice_account"] = {"label": "Nowhere", "number": None}
    attempt("account", bad)
    old = json.loads(json.dumps(data))  # as a file made before update 35 holds it
    old["records_version"] = 34
    for e in old["entities"]:
        for k in setupfile.PRINT_ENTITY_COLS + setupfile.ENTITY_EXTRAS:
            e.pop(k, None)
    for a in old["accounts"]:
        for k in setupfile.PRINT_ACCOUNT_COLS:
            a.pop(k, None)
    for p in old["parties"]:
        for k in setupfile.PRINT_PARTY_COLS:
            p.pop(k, None)
    r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": old, "preview": True})
    res["old"] = (r.status_code, (r.get_json() or {}).get("error"))
    r = c.post(BASE + "/api/setup/import", headers=H, json={"setup": data, "preview": True})  # the whole file, previewed
    assets = config.DATA_DIR / "company-assets"
    res["preview"] = (r.status_code, sorted(str(x.relative_to(config.DATA_DIR)) for x in assets.rglob("*") if x.is_file())
                      if assets.exists() else [])
    res["import"] = j("post", "/api/setup/import", json={"setup": data, "reason": "test: a new install"})
    res["entities"] = q("SELECT * FROM entities ORDER BY id")
    res["accounts"] = q("SELECT * FROM accounts ORDER BY id")
    res["parties"] = q("SELECT * FROM parties ORDER BY id")
    con = db.connect()
    e = con.execute("SELECT * FROM entities WHERE code = 'EXH'").fetchone()
    res["images"] = {w: (hashlib.sha256(p.read_bytes()).hexdigest() if p else None)
                     for w in invoicepdf.IMAGES for p in [invoicepdf.image_path(e, w)]}
    res["missing"] = invoicepdf.missing_settings(con, e)
    res["again"] = setupfile.export(con, "full")
    res["audit"] = audit.verify(con)["ok"]
    con.close()
    out.write_text(json.dumps(res, default=str), encoding="utf-8")
    sys.exit(0)

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "EXAMPLE HOLDINGS SDN BHD", "accounts": [{"label": "Main", "bank": "Example Bank Berhad", "number": "0000 1111 2222"},
                                                                    {"label": "Reserve", "bank": "Example Bank Berhad", "number": "0000 5555 6666"}]},
]}), encoding="utf-8")
db.init()
EXH = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
MAIN, RESERVE = (q("SELECT id FROM accounts WHERE label = ?", (x,))[0]["id"] for x in ("Main", "Reserve"))
check("the records are at the latest update", q("PRAGMA user_version")[0]["user_version"] == len(db.MIGRATIONS) >= 35)

# ---------- the company's print settings, as Setup keeps them ----------
j("patch", f"/api/setup/entities/{EXH}", json={"fields": {"reg_no": "202001000001", "old_reg_no": "1000001-A", "tin": "C00000000010",
                                                           "address": "1-1, Jalan Contoh 1/2,\nTaman Contoh,\n50000 Kuala Lumpur",
                                                           "phone": "+603-0000 0000", "email": "info@example.com",
                                                           "website": "www.example.com", "sign_label": "Authorised signatory"}})
j("patch", f"/api/setup/accounts/{RESERVE}", json={"fields": {"bank_address": "Jalan Contoh, Kuala Lumpur", "swift_code": "EXMBMYKL"}})
j("patch", f"/api/setup/entities/{EXH}", json={"fields": {"invoice_account_id": str(RESERVE)}})


def png(size, colour):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "PNG")
    return buf.getvalue()


def jpeg(size, colour):
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "JPEG")
    return buf.getvalue()


LOGO, SIGN = png((120, 150), (20, 90, 30)), jpeg((300, 80), (230, 230, 240))
for which, name, data in (("logo", "Example logo.png", LOGO), ("signature", "Example signature.jpg", SIGN)):
    j("post", f"/api/setup/entities/{EXH}/image/{which}", data={"file": (io.BytesIO(data), name), "entity_id": str(EXH)},
      content_type="multipart/form-data")


def customers(con):
    con.execute("""INSERT INTO parties (entity_id, kind, name, sql_code, address_1, address_2, address_3, attention, phone, credit_term)
                   VALUES (?, 'customer', 'EXAMPLE TENANT TRADING', '300-E0001', '12-3, JALAN SAMPEL 3/4,', 'TAMAN CONTOH,',
                   '50000 KUALA LUMPUR.', 'MR. EXAMPLE PERSON', '03-0000 2222', '30 Days')""", (EXH,))


write("a customer with its address", customers)

# ---------- 1-3. the documents ----------
ROWS = {}
U = lambda ch: (ch * 4 + "Q5JKA274M3RP29RZR97M10")[:26]
LONG = lambda ch: (ch * 6 + "LONGIDEXAMPLE0123456789")[:26]


def setup_docs(con):
    imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing.xlsx', '2026-08-01T09:00:00', 0, 0)",
                      (EXH,)).lastrowid
    batch = ledger.new_batch(con, EXH, report="journal", sql_import_id=imp, file_name="GL Journal of Transaction.xlsx",
                             period_from="2026-07-01", period_to="2026-07-31")

    def entry(no, day, amount, kind, doc_type, code, desc, direction=None, payee=None, einvoice=None):
        ROWS[no] = con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction,
                                  doc_type, kind, code, status, einvoice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (imp, EXH, no, day, desc, payee, amount, direction, doc_type, kind, code,
                                "invoice" if kind == "invoice" else "unlinked", einvoice)).lastrowid

    def lines(no, day, book, ls):
        ledger.put_document(con, EXH, batch, {"doc_no": no, "doc_date": day, "book": book,
                                              "lines": [{"code": a, "description": d, "dr_sen": dr, "cr_sen": cr} for a, d, dr, cr in ls]})

    TENANT = "EXAMPLE TENANT TRADING"
    entry("IV-00001", "2026-07-03", 440.0, "invoice", "IV", "300-E0001", "RENTAL JULY 26", "in", TENANT)
    lines("IV-00001", "2026-07-03", "sales", [("300-E0001", "RENTAL JULY 26", 44000, 0), ("500-1000", "RENTAL JULY 26", 0, 44000)])
    # a debit note: more charged, as an invoice is
    entry("DN-00001", "2026-07-10", 55.5, "invoice", "DN", "300-E0001", "LATE CHARGE", None, TENANT)
    lines("DN-00001", "2026-07-10", "sales", [("300-E0001", "LATE CHARGE", 5550, 0), ("510-1000", "LATE CHARGE", 0, 5550)])
    # a credit note: the customer's account credited, two lines debited; the listing has no customer code
    entry("CN-00001", "2026-07-20", 150.25, "invoice", "CN", None, "RENTAL REBATE", None, TENANT)
    lines("CN-00001", "2026-07-20", "sales", [("300-E0001", "RENTAL REBATE", 0, 15025), ("500-1000", "RENTAL REBATE JULY", 10000, 0),
                                              ("500-2000", "SERVICE CHARGE REBATE", 5025, 0)])
    # credit notes refused: no lines; lines that disagree with the listing
    entry("CN-00002", "2026-07-21", 10.0, "invoice", "CN", "300-E0001", "NO LINES", None, TENANT)
    entry("CN-00003", "2026-07-22", 12.0, "invoice", "CN", "300-E0001", "DISAGREES", None, TENANT)
    lines("CN-00003", "2026-07-22", "sales", [("300-E0001", "DISAGREES", 0, 1000), ("500-1000", "DISAGREES", 1000, 0)])
    # a supplier's credit note (SC): nothing to print
    entry("SC-00001", "2026-07-22", 30.0, "invoice", "SC", "400-S0001", "SUPPLIER REBATE")
    # self-billed e-Invoices: one in US dollars (two lines), one in ringgit
    SUP = "EXAMPLE OVERSEAS SERVICES INC"
    entry("PV2607-020", "2026-07-25", 470.0, "payment", "PV", "400-X0001", "EXAMPLE CLOUD JULY 26", "out", SUP, U("U"))
    lines("PV2607-020", "2026-07-25", "bank", [("900-E001", "EXAMPLE CLOUD SUBSCRIPTION", 30000, 0), ("900-E002", "EXAMPLE CLOUD SUPPORT", 17000, 0),
                                               ("310-000", "EXAMPLE CLOUD JULY 26", 0, 47000)])
    entry("PV2607-021", "2026-07-26", 88.44, "payment", "PV", "400-X0002", "EXAMPLE DESIGN FEE", "out", "EXAMPLE STUDIO", U("M"))
    lines("PV2607-021", "2026-07-26", "bank", [("900-E003", "EXAMPLE DESIGN FEE", 8844, 0), ("310-000", "EXAMPLE DESIGN FEE", 0, 8844)])
    # the bank's GL code, so a voucher's lines other than the bank are its e-Invoice's lines
    con.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, '310-000', 'BANK-EXAMPLE', 'asset', 'bank')", (EXH,))
    # a payment to a non-resident: the service debited, withholding tax credited, the rest paid from the bank
    entry("PV2607-022", "2026-07-27", 423.0, "payment", "PV", "400-X0001", "EXAMPLE CLOUD AUG 26", "out", SUP, U("W"))
    lines("PV2607-022", "2026-07-27", "bank", [("900-E001", "EXAMPLE CLOUD SUBSCRIPTION", 47000, 0), ("460-WHT", "WITHHOLDING TAX", 0, 4700),
                                               ("310-000", "EXAMPLE CLOUD AUG 26", 0, 42300)])
    # lines that come to nothing in ringgit: no rate to print them at
    entry("PV2607-023", "2026-07-28", 0.0, "payment", "PV", "400-X0001", "EXAMPLE CLOUD REVERSAL", "out", SUP, U("Z"))
    lines("PV2607-023", "2026-07-28", "bank", [("900-E001", "EXAMPLE CLOUD SUBSCRIPTION", 5000, 0), ("460-WHT", "WITHHOLDING TAX", 0, 5000)])
    for no, uuid, cur, total, sup in (("PV2607-020", U("U"), "USD", 10000, SUP), ("PV2607-021", U("M"), "MYR", 8844, "EXAMPLE STUDIO"),
                                      ("PV2607-022", U("W"), "USD", 10000, SUP), ("PV2607-023", U("Z"), "USD", 5000, SUP)):
        con.execute("""INSERT INTO myinvois_docs (entity_id, uuid, doc_no, type, currency, supplier_name, supplier_tin, buyer_name, buyer_tin,
                       validated_at, issued_at, status, total_sen, direction, as_at, entry_id, long_id)
                       VALUES (?, ?, ?, 'Self-billed Invoice', ?, ?, 'EI00000000020', 'EXAMPLE HOLDINGS SDN BHD', 'C00000000010',
                       '2026-07-29 14:19:44', '2026-07-29 14:00:00', 'Valid', ?, 'self_billed', '2026-08-01T09:00:00', ?, ?)""",
                    (EXH, uuid, no, cur, sup, total, ROWS[no], LONG(uuid[0])))


write("SQL documents, their lines and e-Invoices, as fetched", setup_docs)
con = db.connect()
doc = lambda no: invoicepdf.document(con, ROWS[no])


def refused(no):
    try:
        doc(no)
    except invoicepdf.InvoiceError as x:
        return str(x)
    return None


row = lambda no: con.execute("SELECT * FROM sql_entries WHERE id = ?", (ROWS[no],)).fetchone()
check("debit and credit notes are customer documents to print; a supplier's credit note isn't",
      [invoicepdf.kind_of(con, row(n)) for n in ("IV-00001", "DN-00001", "CN-00001", "SC-00001")] == ["customer", "customer", "customer", None])
dn = doc("DN-00001")
check("a debit note: titled Debit Note, its line and total as an invoice's, with the bank details",
      dn["title"] == "Debit Note" and dn["lines"] == [{"code": "510-1000", "description": "LATE CHARGE", "sen": 5550}]
      and dn["total_sen"] == 5550 and dn["words"] == "Malaysian Ringgit : FIFTY FIVE AND CENTS FIFTY ONLY" and dn["pay_to"]
      and dn["pay_to"]["account_no"] == "0000 5555 6666" and dn["terms"] == "30 Days", dn)
cn = doc("CN-00001")
check("a credit note: titled Credit Note, its debits as positive lines, the customer's credit as its total",
      cn["title"] == "Credit Note" and cn["account"] == "300-E0001"
      and cn["lines"] == [{"code": "500-1000", "description": "RENTAL REBATE JULY", "sen": 10000},
                          {"code": "500-2000", "description": "SERVICE CHARGE REBATE", "sen": 5025}]
      and cn["total_sen"] == 15025 and cn["words"] == "Malaysian Ringgit : ONE HUNDRED AND FIFTY AND CENTS TWENTY FIVE ONLY", cn)
check("a credit note prints no bank details and, with no Ref in its listing, no Ref", cn["pay_to"] is None and cn["ref"] is None, cn)
why = refused("CN-00002")
check("a credit note with no account lines is refused as an invoice is", why and "haven't been fetched" in why, why)
check("and the refusal calls it a credit note, not an invoice",
      why.endswith("Fetch SQL's GL Journal of Transaction covering 21/07/2026 to print this credit note."), why)
try:
    invoicepdf._lines(con, EXH, "CN-00001", "2026-07-25", invoicepdf._printed_name(dict(row("CN-00001")), "customer"))
    why = None
except invoicepdf.InvoiceError as x:
    why = str(x)
check("a credit note whose lines are dated another day says it isn't this credit note's date",
      why and "not this credit note's date (25/07/2026)" in why and "invoice's date" not in why, why)
check("a debit note's and a self-billed voucher's sentences name them so",
      invoicepdf._fetch_first({"doc_type": "DN", "doc_date": "2026-07-10"}).endswith("to print this debit note.")
      and invoicepdf._fetch_first({"doc_type": "PV", "doc_date": "2026-07-10"}, "self_billed").endswith("to print this self-billed invoice.")
      and invoicepdf._fetch_first({"doc_type": "IV", "doc_date": "2026-07-10"}).endswith("to print this invoice."))
why = refused("CN-00003")
check("a credit note whose lines disagree with the listing is refused", why and "SQL's listing says 12.00" in why, why)
why = refused("SC-00001")
check("a supplier's credit note has nothing to print", why and "isn't a customer invoice, debit note or credit note" in why, why)

pdf = invoicepdf.render(cn)
t = text_of(pdf)
check("the credit note's PDF: its title, its lines and total as positive figures",
      "Credit Note" in t and "100.00" in t and "50.25" in t and "150.25" in t and "-100.00" not in t and "-150.25" not in t
      and "All payments to be made to" not in t, t)
pos = {x[0]: x for x in baselines(pdf)}
check("the title sits where the invoice's does", abs(pos["Credit Note"][1] - invoicepdf.TITLE_Y) < 0.3, pos.get("Credit Note"))
t = text_of(invoicepdf.render(dn))
check("the debit note's PDF: its title and bank details", "Debit Note" in t and "55.50" in t and "All payments to be made to" in t, t)

# The Ref: only when the listing gave it and the invoice is in the documents fetched
s = dict(row("CN-00001"))
check("a Ref naming an invoice fetched is found", invoicepdf._credit_ref(con, dict(s, knockoff_doc=" iv-00001 ")) == "IV-00001")
check("a Ref naming an invoice not fetched prints nothing", invoicepdf._credit_ref(con, dict(s, knockoff_doc="IV-09999")) is None)
pdf = invoicepdf.render(dict(cn, ref="IV-00001"))
pos = {x[0]: x for x in baselines(pdf)}
check("the Ref prints under Terms, in the right block",
      "Ref :" in text_of(pdf) and abs(pos["IV-00001"][1] - invoicepdf.REF_Y) < 0.3 and abs(pos["IV-00001"][2] - invoicepdf.RIGHT_VALUE_X) < 0.3
      and pos["IV-00001"][1] > pos["30 Days"][1], pos.get("IV-00001"))
check("a credit note without a Ref prints no Ref line", "Ref :" not in text_of(invoicepdf.render(cn)))

# ---------- 2. the page's buttons and the month's zip ----------
d = j("get", f"/api/sql/entries?entity={EXH}")
kinds = {x["doc_no"]: (x.get("print_kind"), x.get("doc_type")) for x in d["documents"]}
check("the SQL page offers printing on the debit and credit notes",
      kinds.get("DN-00001") == ("customer", "DN") and kinds.get("CN-00001") == ("customer", "CN"), kinds)
check("the month's customer prints include July", "2026-07" in d["invoice_print"]["months"]["customer"], d["invoice_print"])
r = c.get(BASE + f"/api/invoices/month.zip?entity={EXH}&month=2026-07&kind=customer", headers=H)
z = zipfile.ZipFile(io.BytesIO(r.data))
names = sorted(n for n in z.namelist() if n.endswith(".pdf"))
check("the month's zip holds the invoice, the debit note and the credit note, named by doc no.",
      r.status_code == 200 and [n.split(" ")[0] for n in names] == ["CN-00001", "DN-00001", "IV-00001"], z.namelist())
nottext = z.read("Not printed.txt").decode()
check("and says which credit notes weren't printed and why", "CN-00002" in nottext and "CN-00003" in nottext, nottext)
check("the credit note in the zip is the credit note", "Credit Note" in text_of(z.read(next(n for n in names if n.startswith("CN-00001")))))
r = c.get(BASE + f"/api/invoices/{ROWS['CN-00001']}.pdf?entity_id={EXH}", headers=H)
check("one credit note opens as a PDF", r.status_code == 200 and r.data[:4] == b"%PDF")
js = app_source()
check("the page's buttons name debit and credit notes", 'DN: "debit note", CN: "credit note"' in js and "All invoices, debit and credit notes of" in js)

# ---------- 3. a self-billed e-Invoice in another currency ----------
us = doc("PV2607-020")
check("in US dollars: the lines at the voucher's rate add up to MyInvois's total",
      us["currency"] == "USD" and [x["sen"] for x in us["lines"]] == [6383, 3617] and sum(x["sen"] for x in us["lines"]) == 10000
      and us["total_sen"] == 10000 and us["words"].startswith("US Dollar : ONE HUNDRED ONLY"), us)
check("it says it was paid as MYR by the voucher", us["paid_as"] == "Paid as MYR 470.00 by PV2607-020"
      and not any("isn't what the voucher's lines come to" in n for n in us["notes"]), us)
pdf = invoicepdf.render(us)
t = text_of(pdf)
pos = {x[0]: x for x in baselines(pdf)}
check("the PDF: the heading in USD, the total, and the line under it",
      "Amount(USD)" in t and "100.00" in t and "Paid as MYR 470.00 by PV2607-020" in t
      and pos["Paid as MYR 470.00 by PV2607-020"][1] > pos["100.00"][1], t)
my = doc("PV2607-021")
check("in ringgit nothing changes: no Paid as line", my["currency"] == "MYR" and my["paid_as"] is None
      and [x["sen"] for x in my["lines"]] == [8844] and "Paid as" not in text_of(invoicepdf.render(my)), my)
check("with one line in US dollars its amount is the total", invoicepdf._at_rate([{"sen": 47000}], 10000) == [{"sen": 10000}])
wht = doc("PV2607-022")
check("in US dollars with a withholding tax credit line: both lines at the voucher's rate, adding up to MyInvois's total",
      wht["currency"] == "USD" and [(x["code"], x["sen"]) for x in wht["lines"]] == [("900-E001", 11111), ("460-WHT", -1111)]
      and sum(x["sen"] for x in wht["lines"]) == wht["total_sen"] == 10000 and wht["paid_as"] == "Paid as MYR 423.00 by PV2607-022", wht)
check("and the note on the rate is true: USD 100.00 for MYR 423.00",
      any("at the voucher's rate (USD 100.00 for MYR 423.00)" in n for n in wht["notes"]), wht["notes"])
t = text_of(invoicepdf.render(wht))
check("the PDF prints the converted lines, never SQL's ringgit lines, under Amount(USD)",
      "Amount(USD)" in t and "111.11" in t and "470.00" not in t and "47.00" not in t, t)
check("signed lines at a rate always add up to the total",
      all(sum(invoicepdf._at_rate([{"sen": a}, {"sen": b}, {"sen": c_}], tot)[i]["sen"] for i in range(3)) == tot
          for a, b, c_, tot in ((47000, -4700, 1, 10000), (33333, -1, -2, 7), (100, 200, -150, 99999), (5, 5, -9, 1))))
why = refused("PV2607-023")
check("in US dollars with lines that come to nothing in ringgit: refused, not printed as ringgit under USD",
      why and "can't be printed at the voucher's rate" in why and "MYR 0.00" in why, why)
con.close()

# ---------- 4. setup.json carries the print settings and images ----------
with db.connect() as r:
    data = setupfile.export(r, "full")
e = next(x for x in data["entities"] if x["code"] == "EXH")
check("the export holds the company's print settings",
      all(e.get(k) for k in PRINT_COLS) and e["invoice_account"] == {"label": "Reserve", "number": "0000 5555 6666"}
      and "invoice_account_id" not in e and "logo_file" not in e, e)
check("and its logo and signature, with their fingerprints",
      base64.b64decode(e["logo"]["data"]) == LOGO and e["logo"]["sha256"] == hashlib.sha256(LOGO).hexdigest()
      and base64.b64decode(e["signature"]["data"]) == SIGN and e["signature"]["name"] == "signature.jpg", {k: e.get(k, {}).get("name") for k in ("logo", "signature")})
a = next(x for x in data["accounts"] if x["label"] == "Reserve")
p = data["parties"][0]
check("the bank account's address and transfer code, and the customer's address, attention, phone and terms",
      a["bank_address"] == "Jalan Contoh, Kuala Lumpur" and a["swift_code"] == "EXMBMYKL"
      and (p["address_1"], p["address_3"], p["attention"], p["phone"], p["credit_term"])
      == ("12-3, JALAN SAMPEL 3/4,", "50000 KUALA LUMPUR.", "MR. EXAMPLE PERSON", "03-0000 2222", "30 Days"), (a, p))
check("the file says it holds the signature", any("signature" in h for h in data["holds"]), data["holds"])

f_in, f_out = tmp / "setup.json", tmp / "imported.json"
f_in.write_text(json.dumps(data), encoding="utf-8")
root = Path(__file__).resolve().parent.parent
run = subprocess.run([sys.executable, "-m", "synthetic_tests.invoice_notes_test", "--import", str(f_in), str(f_out)], cwd=root,
                     capture_output=True, text=True, timeout=600)
got = json.loads(f_out.read_text(encoding="utf-8")) if f_out.exists() else None
check("the new install ran", run.returncode == 0 and got, (run.stdout[-1500:], run.stderr[-1500:]))
rf = got["refused"]
check("an image whose fingerprint doesn't match is refused", rf["fingerprint"][0] == 400 and "fingerprint" in rf["fingerprint"][1], rf)
check("an image that isn't PNG or JPEG is refused", rf["gif"][0] == 400 and "PNG or JPEG" in rf["gif"][1], rf)
check("an image over 2 MB is refused", rf["big"][0] == 400 and "2 MB" in rf["big"][1], rf)
check("a bank account on invoices the file doesn't have is refused", rf["account"][0] == 400 and "Nowhere" in rf["account"][1], rf)
check("a file made before the print settings still imports", got["old"][0] == 200, got["old"])
check("previewing the whole file, with its logo and signature, leaves no image file behind",
      got["preview"] == [200, []], got["preview"])
ent = next(x for x in got["entities"] if x["code"] == "EXH")
acc = {x["label"]: x for x in got["accounts"]}
check("the company's print settings are imported as they were", all(ent[k] == e[k] for k in PRINT_COLS)
      and ent["invoice_account_id"] == acc["Reserve"]["id"], ent)
check("the logo and signature are stored again, by fingerprint", got["images"] == {"logo": hashlib.sha256(LOGO).hexdigest(),
                                                                                  "signature": hashlib.sha256(SIGN).hexdigest()}, got["images"])
check("the bank account's address and transfer code, and the customer's details, are imported",
      acc["Reserve"]["bank_address"] == "Jalan Contoh, Kuala Lumpur" and acc["Reserve"]["swift_code"] == "EXMBMYKL"
      and all(got["parties"][0][k] == p[k] for k in setupfile.PRINT_PARTY_COLS), (acc, got["parties"]))
check("the new install misses no print setting", got["missing"] == [], got["missing"])
same = ("entities", "accounts", "parties")
check("exported again, the new install's companies, bank accounts and customers are the file's",
      all(got["again"][k] == data[k] for k in same), [k for k in same if data.get(k) != got["again"].get(k)])
check("the new install's audit trail checks out", got["audit"])

with db.connect() as r:
    v = audit.verify(r)
check("the audit trail still checks out at the end", v["ok"], v)
print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
