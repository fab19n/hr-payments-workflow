"""Printed invoices (hrp/invoicepdf, update 35), on made-up records only.

1. Update 35 on records at update 34: the new columns are empty, the audit chain still checks out and start-up repairs
   nothing.
2. Amounts in words, as Malaysian invoices write them, up to billions, with cents.
3. Setup: the company's print settings (address, phone, email, website, old registration no., the bank account on
   invoices, the words under the signature), the bank account's bank address and transfer code, the customer's
   address, attention and terms (typed, and pasted from SQL's customer list), and the logo and signature images
   (PNG or JPEG only, size-limited, kept read-only by fingerprint); a missing setting is named in words.
4. A customer invoice's data from SQL's account lines: the income lines, the total on the customer's account, which
   must be the listing's; refused with a sentence when no lines were fetched or they disagree.
5. A self-billed e-Invoice's data: the supplier from MyInvois, the voucher's lines other than the bank, MyInvois's total
   (a difference noted).
6. The QR code only for a valid e-Invoice with its MyInvois link; a cancelled one says so; one without a Long ID prints
   without a QR code and says why; a plain invoice has none.
7. The routes: one invoice as PDF, a month's invoices as a zip (with what wasn't printed), the SQL page's buttons and
   print settings note, and a refusal shown as a sentence.
8. Sample PDFs are written to a temp folder for looking at.
9. Review fixes: a supplier's long address block moves the table down rather than printing over it; account lines
   under a number SQL used again on another date are refused; a description longer than a page is split across pages;
   the QR code keeps its blank margin; a backup holds the logo and signature.

Companies, customers, banks, TINs, UUIDs, documents and amounts are made up.

Run: .venv\\Scripts\\python -m synthetic_tests.invoice_pdf_test
"""
import io
import json
import math
import os
import sqlite3
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-invoice-pdf-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db, invoicepdf, ledger, masters  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert invoicepdf.ASSETS_DIR == tmp / "company-assets"

from PIL import Image, ImageDraw  # noqa: E402
from pypdf import PdfReader  # noqa: E402

SAMPLES = tmp / "samples"
SAMPLES.mkdir()

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "EXAMPLE HOLDINGS SDN BHD", "accounts": [{"label": "Main", "bank": "Example Bank Berhad", "number": "0000 1111 2222"}]},
    {"code": "EXO", "name": "EXAMPLE OTHER SDN BHD", "accounts": [{"label": "Ops", "bank": "Example Bank Berhad", "number": "0000 3333 4444"}]},
]}), encoding="utf-8")

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
    """Changes made as a person would (or as a fetch from SQL would), on a connection of its own."""
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


def text_of(data):
    """The PDF's text, its line breaks and spaces made single spaces (wrapped text reads as one line)."""
    return " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages).split())


def links_of(data):
    out = []
    for p in PdfReader(io.BytesIO(data)).pages:
        for a in p.get("/Annots") or []:
            a = a.get_object()
            uri = (a.get("/A") or {}).get("/URI")
            if uri:
                out.append(str(uri))
    return out


PAGE_H_PT = 841.89  # A4 in points


def baselines(data, page=None):
    """Each piece of text the PDF prints, with its baseline in mm from the top of its page: [(page no., text, mm)]."""
    out = []
    for n, p in enumerate(PdfReader(io.BytesIO(data)).pages, 1):
        if page and n != page:
            continue

        def seen(text, cm, tm, font, size, n=n):
            if text.strip():
                out.append((n, text.strip(), (PAGE_H_PT - (tm[5] * cm[3] + cm[5])) * 25.4 / 72))
        p.extract_text(visitor_text=seen)
    return out


def link_rects(data):
    """The links' boxes in mm from the top-left of the page: [(left, top, right, bottom)]."""
    out = []
    for p in PdfReader(io.BytesIO(data)).pages:
        for a in p.get("/Annots") or []:
            x1, y1, x2, y2 = (float(v) for v in a.get_object()["/Rect"])
            mm = 25.4 / 72
            out.append((min(x1, x2) * mm, (PAGE_H_PT - max(y1, y2)) * mm, max(x1, x2) * mm, (PAGE_H_PT - min(y1, y2)) * mm))
    return out


# ---------- 1. update 35 on records at update 34 ----------
full = db.MIGRATIONS[:]
check("update 35 is the print settings (later updates may follow)", len(full) >= 35
      and "_print_settings" in full[34].__code__.co_names, len(full))
db.MIGRATIONS[:] = full[:34]
db.init()
check("the records start at update 34", q("PRAGMA user_version")[0]["user_version"] == 34)
EXH, EXO = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXH", "EXO"))
MAIN, OPS = (q("SELECT id FROM accounts WHERE entity_id = ?", (x,))[0]["id"] for x in (EXH, EXO))
write("a customer at update 34", lambda c: c.execute(
    "INSERT INTO parties (entity_id, kind, name, sql_code) VALUES (?, 'customer', 'EXAMPLE TENANT TRADING', '300-E0001')", (EXH,)))
db.MIGRATIONS[:] = full
trail = db.init()
check("update 35 runs, with the updates after it", q("PRAGMA user_version")[0]["user_version"] == len(full))
cols = {t: {r["name"] for r in q(f"PRAGMA table_info({t})")} for t in ("entities", "accounts", "parties")}
check("the companies, bank accounts and customers get their print columns",
      set(invoicepdf.ENTITY_COLS) <= cols["entities"] and set(invoicepdf.ACCOUNT_COLS) <= cols["accounts"]
      and set(invoicepdf.PARTY_COLS) <= cols["parties"], cols)
check("they are empty to begin with", all(r[c] is None for r in q("SELECT * FROM entities") for c in invoicepdf.ENTITY_COLS)
      and all(r[c] is None for r in q("SELECT * FROM parties") for c in invoicepdf.PARTY_COLS))
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail checks out after update 35", v["ok"], v)
check("start-up repaired nothing", trail and not trail["triggers_repaired"] and not trail["late_sealed"], trail)
trail = db.init()
check("a second start-up changes and repairs nothing", not trail["triggers_repaired"] and not trail["late_sealed"], trail)

# ---------- 2. amounts in words ----------
W = invoicepdf.amount_words
for sen, words in [
        (44000, "FOUR HUNDRED AND FORTY ONLY"),
        (44025, "FOUR HUNDRED AND FORTY AND CENTS TWENTY FIVE ONLY"),
        (100, "ONE ONLY"), (50, "CENTS FIFTY ONLY"), (1, "CENTS ONE ONLY"), (0, "ZERO ONLY"),
        (1900, "NINETEEN ONLY"), (2000, "TWENTY ONLY"), (10000, "ONE HUNDRED ONLY"), (10100, "ONE HUNDRED AND ONE ONLY"),
        (100000, "ONE THOUSAND ONLY"), (100500, "ONE THOUSAND AND FIVE ONLY"),
        (123425, "ONE THOUSAND TWO HUNDRED AND THIRTY FOUR AND CENTS TWENTY FIVE ONLY"),
        (1200000, "TWELVE THOUSAND ONLY"), (10000000, "ONE HUNDRED THOUSAND ONLY"),
        (250000000, "TWO MILLION FIVE HUNDRED THOUSAND ONLY"),
        (100000001, "ONE MILLION AND CENTS ONE ONLY"),
        (100009900, "ONE MILLION AND NINETY NINE ONLY"),
        (123456789099, "ONE BILLION TWO HUNDRED AND THIRTY FOUR MILLION FIVE HUNDRED AND SIXTY SEVEN THOUSAND EIGHT HUNDRED AND NINETY AND CENTS NINETY NINE ONLY"),
        (99999999999999, "NINE HUNDRED AND NINETY NINE BILLION NINE HUNDRED AND NINETY NINE MILLION NINE HUNDRED AND NINETY NINE "
                         "THOUSAND NINE HUNDRED AND NINETY NINE AND CENTS NINETY NINE ONLY")]:
    check(f"in words: {sen / 100:,.2f}", W(sen) == words, W(sen))
for bad in (-1, 1.5, True, 10 ** 14):
    try:
        W(bad)
        ok = False
    except ValueError:
        ok = True
    check(f"in words refuses {bad!r}", ok)
check("money is printed with thousands and two decimals", invoicepdf.money(123456789) == "1,234,567.89" and invoicepdf.money(5) == "0.05")

# ---------- 3. Setup ----------
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


fields = {f["key"] for f in masters.KINDS["entities"]["fields"]}
check("Setup › Companies has the print fields",
      {"old_reg_no", "address", "phone", "email", "website", "invoice_account_id", "sign_label"} <= fields, fields)
check("Setup › Bank accounts has the bank address and transfer code",
      {"bank_address", "swift_code"} <= {f["key"] for f in masters.KINDS["accounts"]["fields"]})
check("Setup › Customers and suppliers has the address, attention, phone and terms",
      set(invoicepdf.PARTY_COLS) <= {f["key"] for f in masters.KINDS["parties"]["fields"]})

with app.app_context():
    con = db.connect()
    missing = invoicepdf.missing_settings(con, con.execute("SELECT * FROM entities WHERE id = ?", (EXH,)).fetchone())
    con.close()
check("with nothing set, every missing print setting is named",
      any("No address" in m for m in missing) and any("No logo" in m for m in missing) and any("No signature" in m for m in missing)
      and any("No bank account chosen" in m for m in missing) and any("phone, email or website" in m for m in missing), missing)

j("patch", f"/api/setup/entities/{EXH}", json={"fields": {"reg_no": "202001000001", "old_reg_no": "1000001-A", "tin": "C00000000010",
                                                           "address": "1-1, Jalan Contoh 1/2,\nTaman Contoh, Jalan Sampel,\n50000 Kuala Lumpur,",
                                                           "phone": "+603-0000 0000", "email": "info@example.com", "website": "www.example.com"}})
r = j("patch", f"/api/setup/entities/{EXH}", 400, json={"fields": {"invoice_account_id": OPS}})
check("the bank account on invoices must be the company's own", "this company's bank accounts" in r["error"], r)
j("patch", f"/api/setup/accounts/{MAIN}", json={"fields": {"gl_code": "310-000", "bank_address": "Jalan Contoh, Kuala Lumpur", "swift_code": "EXMBMYKL"}})
j("patch", f"/api/setup/entities/{EXH}", json={"fields": {"invoice_account_id": str(MAIN)}})
rec = j("get", f"/api/setup/entities/{EXH}")["record"]
check("the settings are saved", rec["invoice_account_id"] == MAIN and rec["old_reg_no"] == "1000001-A" and rec["website"] == "www.example.com", rec)
r = j("post", "/api/setup/entities", 400, json={"fields": {"code": "EXN", "name": "Example New Sdn Bhd", "invoice_account_id": MAIN}})
check("a new company can't name an account before it has one", "add the company first" in r["error"], r)
used = j("get", f"/api/setup/accounts/{MAIN}")
check("the account on invoices counts as used", any("invoices" in w for w, _ in used["used_by"]), used["used_by"])


def png(size, draw):
    im = Image.new("RGB", size, "white")
    draw(ImageDraw.Draw(im))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


LOGO = png((300, 380), lambda d: (d.rectangle((0, 0, 300, 380), fill=(20, 90, 30)), d.ellipse((60, 60, 240, 260), fill=(210, 190, 40))))
SIGN = png((600, 150), lambda d: d.line([(20 + i * 5, 90 + 30 * math.sin(i / 3)) for i in range(110)], fill=(20, 30, 80), width=4))


def upload(which, name, data, expect=200):
    return j("post", f"/api/setup/entities/{EXH}/image/{which}", expect, data={"file": (io.BytesIO(data), name), "entity_id": str(EXH)},
             content_type="multipart/form-data")


r = upload("logo", "logo.gif", b"GIF89a....", 400)
check("a GIF is refused", "PNG or JPEG" in r["error"], r)
r = upload("logo", "logo.png", b"\x89PNG\r\n\x1a\nnot really an image", 400)
check("a file that isn't an image is refused", "can't be read" in r["error"], r)
r = upload("logo", "logo.png", b"\xff\xd8\xff" + b"0" * 100, 400)
check("a JPEG named .png is refused", "isn't a PNG" in r["error"], r)
r = upload("logo", "big.png", b"\x89PNG\r\n\x1a\n" + b"0" * (invoicepdf.MAX_IMAGE + 1), 400)
check("an image over 2 MB is refused", "2 MB" in r["error"], r)
r = upload("other", "x.png", LOGO, 404)
upload("logo", "Example logo.png", LOGO)
r = upload("signature", "Example signature.png", SIGN)
ent = q("SELECT * FROM entities WHERE id = ?", (EXH,))[0]
logo_file = tmp / ent["logo_file"]
check("the logo and signature are kept read-only in the records folder, by fingerprint",
      logo_file.is_file() and logo_file.parent == tmp / "company-assets" / "EXH" and not os.access(logo_file, os.W_OK)
      and ent["logo_sha256"] and ent["signature_file"], ent)
check("the print settings now only miss nothing", r["missing"] == [], r)
resp = c.get(BASE + f"/api/setup/entities/{EXH}/image/logo")
check("the logo is shown in Setup", resp.status_code == 200 and resp.data == LOGO)
r = j("get", f"/api/setup/entities/{EXO}/print")
check("another company's settings are its own", any("No logo" in m for m in r["missing"]) and r["logo"] is None, r)

# A customer's details: typed, and pasted from SQL's Maintain Customer list
PARTY = q("SELECT id FROM parties WHERE sql_code = '300-E0001'")[0]["id"]
j("patch", f"/api/setup/parties/{PARTY}", json={"fields": {"address_1": "12-3, JALAN SAMPEL 3/4,", "address_2": "TAMAN CONTOH,",
                                                           "address_3": "50000 KUALA LUMPUR.", "attention": "MR. EXAMPLE PERSON",
                                                           "credit_term": "30 Days"}})
paste = ("Code\tCompany Name\tAddress1\tAddress2\tAddress3\tAddress4\tAttention\tPhone1\tCredit Term\n"
         "300-E0002\tEXAMPLE SHOP ENTERPRISE\t8, JALAN UJIAN 5,\tTAMAN UJIAN,\t47000 SUNGAI BULOH,\tSELANGOR.\tMS. EXAMPLE BUYER\t03-0000 1111\t14 Days\n")
r = j("post", "/api/setup/parties/paste", json={"entity_id": EXH, "text": paste, "kind": "customer"})
p2 = q("SELECT * FROM parties WHERE sql_code = '300-E0002'")
check("a pasted customer list fills the address lines, attention, phone and terms",
      p2 and p2[0]["address_1"] == "8, JALAN UJIAN 5," and p2[0]["address_4"] == "SELANGOR." and p2[0]["attention"] == "MS. EXAMPLE BUYER"
      and p2[0]["phone"] == "03-0000 1111" and p2[0]["credit_term"] == "14 Days", (r, p2))

# ---------- 4-6. SQL documents, their account lines and e-Invoices ----------
U = lambda ch: (ch * 4 + "Q5JKA274M3RP29RZR97M10")[:26]  # made-up UUIDs
LONG = lambda ch: (ch * 6 + "LONGIDEXAMPLE0123456789")[:26]
ROWS = {}


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

    def einv(no, uuid, direction, status, total, sup, sup_tin, buy, buy_tin, long_id=None, validated="2026-07-29 14:19:44", typ="Invoice",
             currency="MYR"):
        con.execute("""INSERT INTO myinvois_docs (entity_id, uuid, doc_no, type, currency, supplier_name, supplier_tin, buyer_name, buyer_tin,
                       validated_at, issued_at, status, total_sen, direction, as_at, entry_id, long_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (EXH, uuid, no, typ, currency, sup, sup_tin, buy, buy_tin, validated if status == "Valid" else None, "2026-07-29 14:00:00",
                     status, total, direction, "2026-08-01T09:00:00", ROWS[no], long_id))

    US, TENANT = "EXAMPLE HOLDINGS SDN BHD", "EXAMPLE TENANT TRADING"
    # A: one line, e-Invoice valid with its link
    entry("EXH/2026/07/001", "2026-07-29", 440.0, "invoice", "IV", "300-E0001", "RENTAL CHARGE FOR JULY 26", "in", TENANT, U("A"))
    lines("EXH/2026/07/001", "2026-07-29", "sales", [("300-E0001", "RENTAL CHARGE FOR JULY 26", 44000, 0),
                                                     ("500-1000", "RENTAL CHARGE FOR JULY 26", 0, 44000)])
    einv("EXH/2026/07/001", U("A"), "issued", "Valid", 44000, US, "C00000000010", TENANT, "C00000000060", LONG("A"))
    # B: six lines with cents, valid e-Invoice
    six = [("500-1000", "RENTAL CHARGE FOR JULY 26", 150000), ("500-2000", "SERVICE CHARGE FOR JULY 26", 32050),
           ("500-3000", "AIR-CONDITIONING CHARGE FOR JULY 26", 12575), ("500-4000", "CAR PARK BAYS (2) FOR JULY 26", 20000),
           ("500-5000", "WATER CHARGES FOR JULY 26", 4310), ("500-6000", "ELECTRICITY CHARGES FOR JULY 26", 28890)]
    total6 = sum(x[2] for x in six)
    entry("EXH/2026/07/002", "2026-07-30", total6 / 100, "invoice", "IV", "300-E0002", "CHARGES FOR JULY 26", "in", "EXAMPLE SHOP ENTERPRISE", U("B"))
    lines("EXH/2026/07/002", "2026-07-30", "sales", [("300-E0002", "CHARGES FOR JULY 26", total6, 0)] + [(a, d, 0, s) for a, d, s in six])
    einv("EXH/2026/07/002", U("B"), "issued", "Valid", total6, US, "C00000000010", "EXAMPLE SHOP ENTERPRISE", "C00000000070", LONG("B"))
    # C: not an e-Invoice
    entry("EXH/2026/07/003", "2026-07-31", 1250.0, "invoice", "IV", "300-E0001", "LATE PAYMENT CHARGE", "in", TENANT)
    lines("EXH/2026/07/003", "2026-07-31", "sales", [("300-E0001", "LATE PAYMENT CHARGE", 125000, 0), ("510-1000", "LATE PAYMENT CHARGE", 0, 125000)])
    # D: a long description that wraps
    long_desc = ("PROVISION OF SHARED OFFICE SPACE, MEETING ROOM USE, RECEPTION AND MAIL HANDLING SERVICES, CLEANING OF COMMON "
                 "AREAS AND INTERNET ACCESS FOR THE MONTH OF JULY 2026 AS PER THE SERVICE AGREEMENT DATED 1 JANUARY 2026")
    entry("EXH/2026/07/004", "2026-07-31", 3180.0, "invoice", "IV", "300-E0001", "SHARED OFFICE JULY 26", "in", TENANT, U("D"))
    lines("EXH/2026/07/004", "2026-07-31", "sales", [("300-E0001", "SHARED OFFICE JULY 26", 318000, 0), ("520-1000", long_desc, 0, 300000),
                                                     ("520-2000", "PRINTING", 0, 18000)])
    einv("EXH/2026/07/004", U("D"), "issued", "Valid", 318000, US, "C00000000010", TENANT, "C00000000060", LONG("D"))
    # E: e-Invoice cancelled
    entry("EXH/2026/07/005", "2026-07-31", 100.0, "invoice", "IV", "300-E0001", "KEY REPLACEMENT", "in", TENANT, U("E"))
    lines("EXH/2026/07/005", "2026-07-31", "sales", [("300-E0001", "KEY REPLACEMENT", 10000, 0), ("530-1000", "KEY REPLACEMENT", 0, 10000)])
    einv("EXH/2026/07/005", U("E"), "issued", "Cancelled", 10000, US, "C00000000010", TENANT, "C00000000060", LONG("E"))
    # F: valid, but the copy read had no Long ID
    entry("EXH/2026/07/006", "2026-07-31", 60.0, "invoice", "IV", "300-E0001", "ACCESS CARD", "in", TENANT, U("F"))
    lines("EXH/2026/07/006", "2026-07-31", "sales", [("300-E0001", "ACCESS CARD", 6000, 0), ("530-2000", "ACCESS CARD", 0, 6000)])
    einv("EXH/2026/07/006", U("F"), "issued", "Valid", 6000, US, "C00000000010", TENANT, "C00000000060", None)
    # G: no account lines fetched; H: the lines disagree with the listing
    entry("EXH/2026/07/007", "2026-07-31", 75.0, "invoice", "IV", "300-E0001", "STORAGE", "in", TENANT)
    entry("EXH/2026/07/008", "2026-07-31", 99.0, "invoice", "IV", "300-E0001", "PARKING", "in", TENANT)
    lines("EXH/2026/07/008", "2026-07-31", "sales", [("300-E0001", "PARKING", 9000, 0), ("530-3000", "PARKING", 0, 9000)])
    # I: a payment voucher with a self-billed e-Invoice; J: one whose MyInvois total differs from its lines
    SUP = "EXAMPLE OVERSEAS SERVICES INC"
    entry("PV2607-009", "2026-07-25", 88.44, "payment", "PV", "400-X0001", "EXAMPLE CLOUD SUBSCRIPTION JULY 26", "out", SUP, U("I"))
    lines("PV2607-009", "2026-07-25", "bank", [("900-E001", "EXAMPLE CLOUD SUBSCRIPTION JULY 26", 8844, 0), ("310-000", "EXAMPLE CLOUD SUBSCRIPTION", 0, 8844)])
    einv("PV2607-009", U("I"), "self_billed", "Valid", 8844, SUP, "EI00000000020", US, "C00000000010", LONG("I"), typ="Self-billed Invoice")
    entry("PV2607-010", "2026-07-26", 120.0, "payment", "PV", None, "EXAMPLE DESIGN FEE JULY 26", "out", "EXAMPLE FREELANCE STUDIO", U("J"))
    lines("PV2607-010", "2026-07-26", "bank", [("900-E002", "EXAMPLE DESIGN FEE", 12000, 0), ("310-000", "EXAMPLE DESIGN FEE", 0, 12000)])
    einv("PV2607-010", U("J"), "self_billed", "Valid", 11500, "EXAMPLE FREELANCE STUDIO", "EI00000000030", US, "C00000000010", LONG("J"),
         typ="Self-billed Invoice")
    # K: a journal: nothing to print
    entry("JV2607-001", "2026-07-31", 10.0, "journal", "JV", None, "ACCRUAL")
    lines("JV2607-001", "2026-07-31", "general", [("900-E003", "ACCRUAL", 1000, 0), ("420-000", "ACCRUAL", 0, 1000)])


write("SQL documents, their lines and e-Invoices, as fetched", setup_docs)
con = db.connect()


def doc(no):
    return invoicepdf.document(con, ROWS[no])


def refused(no):
    try:
        doc(no)
    except invoicepdf.InvoiceError as x:
        return str(x)
    return None


a = doc("EXH/2026/07/001")
check("a customer invoice: its income line, account, total and words",
      a["kind"] == "customer" and a["title"] == "Invoice" and a["lines"] == [{"code": "500-1000", "description": "RENTAL CHARGE FOR JULY 26", "sen": 44000}]
      and a["total_sen"] == 44000 and a["account"] == "300-E0001" and a["date"] == "29/07/2026"
      and a["words"] == "Malaysian Ringgit : FOUR HUNDRED AND FORTY ONLY", a)
check("the customer's name, address, attention and terms come from Setup",
      a["party"]["name"] == "EXAMPLE TENANT TRADING" and a["party"]["address"] == ["12-3, JALAN SAMPEL 3/4,", "TAMAN CONTOH,", "50000 KUALA LUMPUR."]
      and a["party"]["attn"] == "MR. EXAMPLE PERSON" and a["terms"] == "30 Days", a["party"])
check("the header comes from the company's settings",
      a["company"]["reg_line"] == "(202001000001 (1000001-A))  (TIN No: C00000000010)"
      and a["company"]["address"] == "1-1, Jalan Contoh 1/2, Taman Contoh, Jalan Sampel, 50000 Kuala Lumpur,"
      and a["company"]["contact"] == "Phone: +603-0000 0000  |  email: info@example.com  |  www.example.com"
      and a["company"]["sign_label"] == "For EXAMPLE HOLDINGS SDN BHD" and a["company"]["logo"] and a["company"]["signature"], a["company"])
check("the payment block is the bank account chosen",
      a["pay_to"] == {"name": "EXAMPLE HOLDINGS SDN BHD", "bank": "Example Bank Berhad", "bank_address": "Jalan Contoh, Kuala Lumpur",
                      "account_no": "0000 1111 2222", "swift": "EXMBMYKL"}, a["pay_to"])
link_a = f"https://myinvois.hasil.gov.my/{U('A')}/share/{LONG('A')}"
check("its e-Invoice is valid, with its MyInvois link", a["einvoice"]["state"] == "valid" and a["einvoice"]["link"] == link_a
      and a["einvoice"]["validated_on"] == "29/07/2026 14:19:44", a["einvoice"])
b = doc("EXH/2026/07/002")
check("six lines with cents, in order, adding up to the total", len(b["lines"]) == 6 and b["total_sen"] == 247825
      and [x["code"] for x in b["lines"]] == ["500-1000", "500-2000", "500-3000", "500-4000", "500-5000", "500-6000"]
      and b["words"] == "Malaysian Ringgit : TWO THOUSAND FOUR HUNDRED AND SEVENTY EIGHT AND CENTS TWENTY FIVE ONLY", b["words"])
check("a customer pasted from SQL's list has its address and terms", b["party"]["address"][-1] == "SELANGOR." and b["terms"] == "14 Days")
cdoc = doc("EXH/2026/07/003")
check("an invoice with no e-Invoice has no e-Invoice block", cdoc["einvoice"] is None and not cdoc["notes"], cdoc)
e = doc("EXH/2026/07/005")
check("a cancelled e-Invoice is marked cancelled, with no link", e["einvoice"]["state"] == "cancelled" and e["einvoice"]["link"] is None
      and any("cancelled" in n for n in e["notes"]), e["einvoice"])
f = doc("EXH/2026/07/006")
check("a valid e-Invoice without a Long ID has no link and says why", f["einvoice"]["state"] == "no_link" and f["einvoice"]["link"] is None
      and any("Long ID" in n for n in f["notes"]), f)
why = refused("EXH/2026/07/007")
check("no account lines fetched: refused, asking for SQL's GL Journal of Transaction covering its date",
      why and why.endswith("Fetch SQL's GL Journal of Transaction covering 31/07/2026 to print this invoice."), why)
why = refused("EXH/2026/07/008")
check("account lines that disagree with the listing: refused, saying both figures", why and "90.00" in why and "99.00" in why, why)
why = refused("JV2607-001")
check("a journal has no invoice to print", why and "isn't a customer invoice" in why, why)
i = doc("PV2607-009")
check("a self-billed e-Invoice: its title, the supplier from MyInvois, the expense line, MyInvois's total",
      i["kind"] == "self_billed" and i["title"] == "Self-billed Invoice" and i["party_label"] == "Supplier"
      and i["party"]["name"] == "EXAMPLE OVERSEAS SERVICES INC" and i["party"]["tin"] == "EI00000000020"
      and i["lines"] == [{"code": "900-E001", "description": "EXAMPLE CLOUD SUBSCRIPTION JULY 26", "sen": 8844}]
      and i["total_sen"] == 8844 and i["buyer"] == "EXAMPLE HOLDINGS SDN BHD (TIN No: C00000000010)" and i["pay_to"] is None
      and i["einvoice"]["state"] == "valid" and not i["notes"], i)
jd = doc("PV2607-010")
check("a self-billed e-Invoice whose total differs from the voucher's lines prints MyInvois's total and says so",
      jd["total_sen"] == 11500 and any("isn't what the voucher's lines come to" in n for n in jd["notes"]), jd["notes"])
check("which documents have an invoice to print", [invoicepdf.kind_of(con, con.execute("SELECT * FROM sql_entries WHERE id = ?", (ROWS[n],)).fetchone())
                                                   for n in ("EXH/2026/07/001", "PV2607-009", "JV2607-001")] == ["customer", "self_billed", None])

# A number SQL used again: an earlier invoice with the number of one whose account lines were fetched, the same amount
def reused(con):
    imp = con.execute("SELECT import_id FROM sql_entries WHERE id = ?", (ROWS["EXH/2026/07/003"],)).fetchone()[0]
    return con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type,
                          kind, code, status) VALUES (?, ?, 'EXH/2026/07/003', '2025-07-31', 'LATE PAYMENT CHARGE', 'EXAMPLE TENANT TRADING',
                          1250.0, 'in', 'IV', 'invoice', '300-E0001', 'invoice')""", (imp, EXH)).lastrowid


ROWS["earlier 003"] = write("an earlier invoice under a number used again", reused)
con.close()
con = db.connect()
why = refused("earlier 003")
check("an invoice whose number's account lines are another date's is refused, saying both dates",
      why and "dated 31/07/2026" in why and "(31/07/2025)" in why and "another document's lines" in why, why)
check("the invoice with that number and date still prints", doc("EXH/2026/07/003")["lines"][0]["code"] == "510-1000")
write("the earlier invoice taken off again", lambda c: c.execute("DELETE FROM sql_entries WHERE id = ?", (ROWS.pop("earlier 003"),)))
con.close()
con = db.connect()

# The PDFs
pdf_a = invoicepdf.render(a)
ta = text_of(pdf_a)
for words in ("EXAMPLE HOLDINGS SDN BHD", "(202001000001 (1000001-A))", "(TIN No: C00000000010)", "Invoice", "Doc No.", "EXH/2026/07/001",
              "29/07/2026", "300-E0001", "30 Days", "G/L CODE", "DESCRIPTION", "Amount(MYR)", "RENTAL CHARGE FOR JULY 26", "440.00",
              "Malaysian Ringgit : FOUR HUNDRED AND FORTY ONLY", "Total :", "All payments to be made to :", "Bank Transfer Code : EXMBMYKL",
              "Attn : MR. EXAMPLE PERSON", "For EXAMPLE HOLDINGS SDN BHD", f"e-Invoice UUID: {U('A')}", "Validated on 29/07/2026 14:19:44"):
    check(f"the e-Invoice PDF shows {words}", words in ta, ta)
check("its QR code links to the e-Invoice's MyInvois page", links_of(pdf_a) == [link_a], links_of(pdf_a))
check("it is one A4 portrait page", [(round(float(p.mediabox.width)), round(float(p.mediabox.height)))
                                     for p in PdfReader(io.BytesIO(pdf_a)).pages] == [(595, 842)])
pdf_c = invoicepdf.render(cdoc)
check("a plain invoice prints no QR code and no e-Invoice line", links_of(pdf_c) == [] and "e-Invoice" not in text_of(pdf_c))
pdf_e = invoicepdf.render(e)
check("a cancelled e-Invoice prints no QR code and says it is cancelled", links_of(pdf_e) == [] and "e-Invoice cancelled" in text_of(pdf_e))
pdf_f = invoicepdf.render(f)
check("a valid e-Invoice without its link prints no QR code and says why", links_of(pdf_f) == [] and "QR code not printed" in text_of(pdf_f))
pdf_b = invoicepdf.render(b)
tb = text_of(pdf_b)
check("the six-line invoice shows each line and the total in words", all(x in tb for x in ("1,500.00", "320.50", "125.75", "200.00", "43.10", "288.90",
                                                                                        "2,478.25", "AND CENTS TWENTY FIVE ONLY")), tb)
d = doc("EXH/2026/07/004")
pdf_d = invoicepdf.render(d)
td = text_of(pdf_d)
check("a long description wraps onto more lines, all printed", "AS PER THE SERVICE AGREEMENT DATED 1 JANUARY 2026" in td
      and "PROVISION OF SHARED OFFICE SPACE" in td and "3,180.00" in td, td)
pdf_i = invoicepdf.render(i)
ti = text_of(pdf_i)
check("the self-billed PDF: its title, supplier and buyer, and no payment block",
      "Self-billed Invoice" in ti and "Supplier" in ti and "TIN : EI00000000020" in ti and "Buyer : EXAMPLE HOLDINGS SDN BHD (TIN No: C00000000010)" in ti
      and "All payments" not in ti and links_of(pdf_i) == [f"https://myinvois.hasil.gov.my/{U('I')}/share/{LONG('I')}"], ti)
many = dict(a, lines=[{"code": f"500-{n:04d}", "description": f"LINE {n} OF A LONG INVOICE", "sen": 100} for n in range(1, 61)], total_sen=6000,
            words="Malaysian Ringgit : " + W(6000))
pdf_many = invoicepdf.render(many)
pages = PdfReader(io.BytesIO(pdf_many)).pages
check("lines that don't fit go on to another page, the total and QR code on the last",
      len(pages) == 2 and "Continued on page 2 of 2" in pages[0].extract_text() and "Total :" not in pages[0].extract_text()
      and "LINE 60 OF A LONG INVOICE" in pages[1].extract_text() and "Total :" in pages[1].extract_text() and links_of(pdf_many) == [link_a])

# A supplier with four address lines, its TIN, Attn and the Buyer: the table moves down so nothing prints over its headings
i4 = dict(i, party=dict(i["party"], address=["UNIT 9-9, EXAMPLE TOWER,", "1 EXAMPLE AVENUE,", "EXAMPLE DISTRICT,", "EXAMPLE CITY 00000."],
                         attn="MR. EXAMPLE CONTACT"))
pdf_i4 = invoicepdf.render(i4)
top4 = invoicepdf._table_top(i4)
bl4 = baselines(pdf_i4)
heading = [mm for _, t, mm in bl4 if t.startswith("G/L CODE")]
left = [(t, mm) for _, t, mm in bl4 if any(t.startswith(w) for w in ("EXAMPLE OVERSEAS", "UNIT 9-9", "1 EXAMPLE AVENUE", "EXAMPLE DISTRICT",
                                                                      "EXAMPLE CITY", "TIN :", "Attn :", "Buyer :"))]
check("a self-billed invoice with four address lines, TIN, Attn and Buyer prints every line of the block above the table",
      top4 > invoicepdf.TOP_RULE and len(left) == 8 and all(mm < top4 - 0.5 for _, mm in left) and heading and heading[0] > top4
      and all(mm > top4 + invoicepdf.HEAD_RULE - invoicepdf.TOP_RULE for _, t, mm in bl4 if t.startswith("900-E001")), (top4, left, heading))
check("one with three address lines, TIN, Attn and Buyer does too",
      (lambda d: invoicepdf._party_block(d)[1] <= invoicepdf._table_top(d) - 1)(dict(i4, party=dict(i4["party"], address=i4["party"]["address"][:3]))))
check("an invoice whose block fits keeps the table where SQL prints it", invoicepdf._table_top(a) == invoicepdf.TOP_RULE
      and invoicepdf._table_top(i) == invoicepdf.TOP_RULE)
check("the block's lines are all in the PDF", all(w in text_of(pdf_i4) for w in ("EXAMPLE CITY 00000.", "Attn : MR. EXAMPLE CONTACT",
                                                                                 "Buyer : EXAMPLE HOLDINGS SDN BHD (TIN No: C00000000010)")))

# One line whose description is longer than a page: split across pages, never over the total, payment block, signature or QR
huge = " ".join(f"PART{n:03d}" for n in range(1, 700))
one_huge = dict(a, lines=[{"code": "500-1000", "description": huge, "sen": 44000}])
pdf_huge = invoicepdf.render(one_huge)
hp = PdfReader(io.BytesIO(pdf_huge)).pages
parts = [(n, t, mm) for n, t, mm in baselines(pdf_huge) if t.startswith("PART")]
words = " ".join(t for _, t, _ in parts).split()
check("a description longer than a page goes on to the next pages, in order, every word printed once",
      len(hp) >= 2 and words == huge.split() and "Continued on page 2" in hp[0].extract_text() and "Total :" not in hp[0].extract_text()
      and "Total :" in hp[-1].extract_text(), (len(hp), words[:3], words[-3:]))
check("and none of it runs past where the lines stop", all(mm <= invoicepdf.LINES_END for _, _, mm in parts), max(mm for _, _, mm in parts))
check("its code and amount are printed once, on its first part", text_of(pdf_huge).count("500-1000") == 1
      and [n for n, t, _ in baselines(pdf_huge) if t == "440.00"][:1] == [1], text_of(pdf_huge).count("500-1000"))
rows = [("500-1", ["x"] * 3, "1.00"), ("500-2", ["y"] * 80, "2.00"), ("500-3", ["z"] * 2, "3.00")]
pg = invoicepdf._pages(rows)
check("a long row after others fills the rest of the page first, and a short row after it follows on",
      [sum(len(r[1]) for r in p) for p in pg] == [32, 32, 21] and pg[0][1][0] == "500-2" and pg[1][0][0] == "" and pg[1][0][2] == ""
      and pg[2][-1] == ("500-3", ["z"] * 2, "3.00"), [[(r[0], len(r[1])) for r in p] for p in pg])
check("a short row that doesn't fit under others still moves whole to the next page",
      [[(r[0], len(r[1])) for r in p] for p in invoicepdf._pages([("A", ["a"] * 30, ""), ("B", ["b"] * 5, "")])] == [[("A", 30)], [("B", 5)]])

# The QR code keeps its margin of blank paper (four of its squares) above the e-Invoice UUID lines
import segno  # noqa: E402
qr_box = link_rects(pdf_a)[0]
square = invoicepdf.QR_SIZE / len(segno.make(link_a, error="m", micro=False).matrix)
cap = 5.5 * 0.75 * 25.4 / 72  # the 5.5 pt text's capital height, in mm
uuid_top = [mm - cap for _, t, mm in baselines(pdf_a) if t.startswith("e-Invoice UUID")]
check("the e-Invoice UUID line starts at least four QR squares below the QR code",
      uuid_top and uuid_top[0] >= qr_box[3] + 4 * square and uuid_top[0] < 285, (qr_box, square, uuid_top))

for name, data in (("1 customer e-Invoice, 1 line.pdf", pdf_a), ("2 customer e-Invoice, 6 lines with cents.pdf", pdf_b),
                   ("3 customer invoice, not an e-Invoice.pdf", pdf_c), ("4 self-billed e-Invoice.pdf", pdf_i),
                   ("5 long description wrapping.pdf", pdf_d), ("6 e-Invoice cancelled.pdf", pdf_e), ("7 two pages.pdf", pdf_many),
                   ("8 self-billed, supplier with 4 address lines.pdf", pdf_i4), ("9 one line longer than a page.pdf", pdf_huge)):
    (SAMPLES / name).write_bytes(data)

# A logo changed on disk since it was uploaded is not printed, and the settings say so
os.chmod(logo_file, stat.S_IWRITE | stat.S_IREAD)
logo_file.write_bytes(LOGO + b"x")
ent = con.execute("SELECT * FROM entities WHERE id = ?", (EXH,)).fetchone()
check("a logo changed since upload isn't printed, and the settings say so", invoicepdf.image_path(ent, "logo") is None
      and any("changed or is missing" in m for m in invoicepdf.missing_settings(con, ent)))
logo_file.write_bytes(LOGO)
con.close()

# ---------- 7. the routes and the SQL page ----------
resp = c.get(BASE + f"/api/invoices/{ROWS['EXH/2026/07/001']}.pdf?entity_id={EXH}")
check("one invoice opens as PDF, shown in the browser, named by its number and customer",
      resp.status_code == 200 and resp.mimetype == "application/pdf" and resp.data.startswith(b"%PDF")
      and "inline" in resp.headers["Content-Disposition"] and "EXH_2026_07_001 EXAMPLE TENANT TRADING.pdf" in resp.headers["Content-Disposition"],
      (resp.status_code, resp.headers.get("Content-Disposition")))
check("and its QR code is there", links_of(resp.data) == [link_a])
resp = c.get(BASE + f"/api/invoices/{ROWS['EXH/2026/07/007']}.pdf")
check("one that can't be printed says why, as a sentence", resp.status_code == 409 and resp.mimetype == "text/html"
      and b"GL Journal of Transaction covering 31/07/2026" in resp.data, resp.data[:300])
r = j("get", f"/api/invoices/{ROWS['EXH/2026/07/006']}/check")
check("the check says what the invoice notes", r["ok"] and r["kind"] == "customer" and any("Long ID" in n for n in r["notes"]), r)
r = j("get", f"/api/invoices/{ROWS['JV2607-001']}/check", 409)
check("the check refuses a journal", "isn't a customer invoice" in r["error"], r)
resp = c.get(BASE + f"/api/invoices/month.zip?entity={EXH}&month=2026-07&kind=customer")
z = zipfile.ZipFile(io.BytesIO(resp.data))
names = z.namelist()
check("the month's customer invoices come as a zip, with what wasn't printed and why",
      resp.status_code == 200 and resp.mimetype == "application/zip" and len([n for n in names if n.endswith(".pdf")]) == 6
      and "Not printed.txt" in names and "EXH/2026/07/007" in z.read("Not printed.txt").decode() and "EXH/2026/07/008" in z.read("Not printed.txt").decode(),
      names)
check("each PDF in the zip is an invoice", all(z.read(n).startswith(b"%PDF") for n in names if n.endswith(".pdf")))
resp = c.get(BASE + f"/api/invoices/month.zip?entity={EXH}&month=2026-07&kind=self_billed")
z = zipfile.ZipFile(io.BytesIO(resp.data))
check("and the self-billed ones", resp.status_code == 200 and sorted(z.namelist()) == ["PV2607-009 EXAMPLE OVERSEAS SERVICES INC.pdf",
                                                                                     "PV2607-010 EXAMPLE FREELANCE STUDIO.pdf"], z.namelist())
resp = c.get(BASE + f"/api/invoices/month.zip?entity={EXH}&month=2026-06&kind=customer")
check("a month with none says so", resp.status_code == 404 and b"no customer invoices" in resp.data, resp.data[:300])
resp = c.get(BASE + f"/api/invoices/month.zip?entity={EXH}&month=2026-07&kind=other")
check("an unknown kind is refused", resp.status_code == 400)
page = j("get", f"/api/sql/entries?entity={EXH}")
kinds = {x["doc_no"]: x["print_kind"] for x in page["documents"]}
check("the SQL page offers Invoice PDF on customer invoices only", kinds.get("EXH/2026/07/001") == "customer" and kinds.get("JV2607-001") is None, kinds)
einv_kinds = {x["doc_no"]: x["print_kind"] for x in page["einvoices"]}
check("and on the vouchers with a self-billed e-Invoice", einv_kinds.get("PV2607-009") == "self_billed", einv_kinds)
check("and in the MyInvois list", any(r["print_entry"] == ROWS["PV2607-009"] for r in page["myinvois"]["rows"]), page["myinvois"]["rows"][:2])
check("with the months to print and no settings missing", page["invoice_print"] == {"missing": [], "months": {"customer": ["2026-07"],
                                                                                                              "self_billed": ["2026-07"]}},
      page["invoice_print"])
resp = c.delete(BASE + f"/api/setup/entities/{EXH}/image/signature", headers=H, json={})
check("the signature can be taken off the invoices", resp.status_code == 200 and any("No signature" in m for m in resp.get_json()["missing"]))
check("its file stays in the records folder", (tmp / ent["signature_file"]).is_file())
upload("signature", "Example signature.png", SIGN)

# A backup holds the logo and signature, at their places in the records folder
out = j("post", "/api/backup", json={})
ent = q("SELECT * FROM entities WHERE id = ?", (EXH,))[0]
with zipfile.ZipFile(out["file"]) as bz:
    held = bz.namelist()
    same = all(bz.read(ent[k].replace("\\", "/")) == (tmp / ent[k]).read_bytes() for k in ("logo_file", "signature_file"))
check("a backup holds the logo and signature, under company-assets as the records name them",
      ent["logo_file"].replace("\\", "/") in held and ent["signature_file"].replace("\\", "/") in held and same
      and all(n.startswith("company-assets/EXH/") for n in held if "logo-" in n or "signature-" in n), held)

# ---------- the audit trail ----------
with db.connect() as r:
    v = audit.verify(r)
check("the audit trail still checks out", v["ok"], v)
check("the settings changes are in the trail", q("""SELECT COUNT(*) AS n FROM audit_row WHERE tbl = 'entities' AND after LIKE '%logo_sha256%'""")[0]["n"] > 0)

print(f"\nSample PDFs: {SAMPLES}")
for p in sorted(SAMPLES.iterdir()):
    print(f"  {p}")
print(f"\nAll {len(passed)} checks passed.")
