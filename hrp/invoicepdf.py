"""Prints SQL Account's customer invoices and self-billed e-Invoices as PDF files, laid out as SQL Account prints its
invoice: the company's header (logo, name, registration and tax numbers, address, phone, email and website), the title,
who it is to with the document number, date, account and terms, the account lines, the total in words, where to pay,
the signature, and for an e-Invoice validated by LHDN its QR code at the bottom right.
The page, fonts, sizes and places are those of the PDF SQL Account exports for its invoice (US Letter; Times New Roman,
Tahoma, Trebuchet MS and Segoe UI, read from where Windows keeps them, never from the records folder); a computer
without one of those fonts (or with a damaged copy) prints that part in a look-alike, never larger, and the print
settings say so. A line too long for its place is made smaller, down to half its size; one longer still has its end
cut off, and the print settings, the invoice check and the month's zip say which.

hr-payments mirrors SQL Account (read-only for now), so nothing on an invoice is typed in for it: the document comes
from SQL's listing, its lines from SQL's GL Journal of Transaction (ledger), the e-Invoice from the copy of SQL's
MyInvois Transaction screen (myinvois), and the header and footer from Setup (the company, the bank account chosen for
invoices, the customer or supplier). A setting missing is named in words and the invoice still prints what it has.

All amounts are whole sen (integers), so totals compare exactly.
"""
import hashlib
import io
import logging
import os
import re
import stat
import zipfile
from datetime import date, datetime
from pathlib import Path

import segno
from fpdf import FPDF
from PIL import Image

from . import db, ledger, myinvois
from .config import DATA_DIR, SETTINGS
from .docstore import safe

ASSETS_DIR = DATA_DIR / "company-assets"
# fontTools (which fpdf2 uses to put only the letters printed in each PDF) says each time it leaves out a font's
# tables a PDF doesn't need; that is expected, so it is kept quiet.
logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
IMAGES = {"logo": "Logo", "signature": "Signature"}
IMAGE_TYPES = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",)}
MAX_IMAGE = 2 * 1024 * 1024  # bytes
MAX_SIDE = 6000  # pixels
KINDS = ("customer", "self_billed")
CURRENCY_NAMES = {"MYR": "Malaysian Ringgit", "USD": "US Dollar", "SGD": "Singapore Dollar", "EUR": "Euro",
                  "GBP": "Pound Sterling", "AUD": "Australian Dollar", "CNY": "Chinese Yuan", "JPY": "Japanese Yen"}


class InvoiceError(ValueError):
    """An invoice that can't be printed, with the sentence the page shows (and the HTTP status)."""

    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


# ---------- update 35 ----------

ENTITY_COLS = ("old_reg_no", "address", "phone", "email", "website", "invoice_account_id", "sign_label", "logo_file",
               "logo_sha256", "signature_file", "signature_sha256")
ACCOUNT_COLS = ("bank_address", "swift_code")
PARTY_COLS = ("address_1", "address_2", "address_3", "address_4", "attention", "phone", "credit_term")


def install(con):
    """Update 35: the settings printed invoices need (see db.MIGRATIONS). Columns only, all empty: nothing else in the
    records changes."""
    for col in ENTITY_COLS:
        db.add_column(con, "entities", col, "INTEGER REFERENCES accounts(id)" if col == "invoice_account_id" else "TEXT")
    for col in ACCOUNT_COLS:
        db.add_column(con, "accounts", col, "TEXT")
    if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'parties'").fetchone():
        for col in PARTY_COLS:
            db.add_column(con, "parties", col, "TEXT")


def ready(con):
    return any(r[1] == "logo_file" for r in con.execute("PRAGMA table_info(entities)"))


# ---------- the logo and signature (Setup › Companies) ----------

def store_image(con, ent, which, filename, data):
    """Keeps a company's logo or signature: a PNG or JPEG image of at most 2 MB, saved read-only under the records
    folder (company-assets/<code>/) by its fingerprint, so an image once printed is never overwritten. The company
    then names the file and its fingerprint. Returns the stored path, relative to the records folder."""
    if which not in IMAGES:
        raise InvoiceError("There is no such image.", 404)
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in IMAGE_TYPES:
        raise InvoiceError(f"{IMAGES[which]}: upload a PNG or JPEG image.", 400)
    if not data:
        raise InvoiceError(f"{IMAGES[which]}: the file is empty.", 400)
    if len(data) > MAX_IMAGE:
        raise InvoiceError(f"{IMAGES[which]}: the image is larger than 2 MB. Save it smaller and upload it again.", 400)
    if not any(data.startswith(m) for m in IMAGE_TYPES[ext]):
        raise InvoiceError(f"{IMAGES[which]}: the file isn't a {'PNG' if ext == '.png' else 'JPEG'} image.", 400)
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
    except Exception:
        raise InvoiceError(f"{IMAGES[which]}: the image can't be read. Save it again as PNG or JPEG.", 400)
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE):
        raise InvoiceError(f"{IMAGES[which]}: the image is too large ({w} x {h} pixels). Save it smaller.", 400)
    digest = hashlib.sha256(data).hexdigest()
    folder = ASSETS_DIR / safe(ent["code"])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{which}-{digest[:16]}{ext}"
    if not (target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest):
        if target.exists():
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        target.write_bytes(data)
        os.chmod(target, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    rel = str(target.relative_to(DATA_DIR))
    con.execute(f"UPDATE entities SET {which}_file = ?, {which}_sha256 = ? WHERE id = ?", (rel, digest, ent["id"]))
    db.log(con, f"Uploaded the {which} printed on {ent['code']}'s invoices: '{filename}'")
    return rel


def clear_image(con, ent, which):
    """Takes the logo or signature off the company's invoices. The file stays in the records folder."""
    if which not in IMAGES:
        raise InvoiceError("There is no such image.", 404)
    con.execute(f"UPDATE entities SET {which}_file = NULL, {which}_sha256 = NULL WHERE id = ?", (ent["id"],))
    db.log(con, f"Removed the {which} from {ent['code']}'s invoices")


def image_path(ent, which):
    """The company's logo or signature file, only while it is still the file uploaded (its fingerprint); else None."""
    ent = dict(ent)
    rel, digest = ent.get(f"{which}_file"), ent.get(f"{which}_sha256")
    if not rel or not digest:
        return None
    p = (DATA_DIR / rel).resolve()
    try:
        p.relative_to(ASSETS_DIR.resolve())
    except ValueError:
        return None
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        return None
    return p


# ---------- amounts ----------

ONES = ["", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN",
        "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN"]
TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]
SCALES = [(10 ** 9, "BILLION"), (10 ** 6, "MILLION"), (10 ** 3, "THOUSAND")]


def _two(n):
    return ONES[n] if n < 20 else TENS[n // 10] + (f" {ONES[n % 10]}" if n % 10 else "")


def _three(n):
    h, r = divmod(n, 100)
    out = [f"{ONES[h]} HUNDRED"] if h else []
    if r:
        out += ["AND", _two(r)] if h else [_two(r)]
    return " ".join(out)


def number_words(n):
    """A whole number in words, as Malaysian invoices write it: 440 is FOUR HUNDRED AND FORTY, 1,005 is ONE THOUSAND
    AND FIVE, 2,500,000 is TWO MILLION FIVE HUNDRED THOUSAND. Up to 999,999,999,999."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n >= 10 ** 12:
        raise ValueError("A whole number from 0 to 999,999,999,999.")
    if n == 0:
        return "ZERO"
    out = []
    for size, word in SCALES:
        if n >= size:
            out.append(f"{_three(n // size)} {word}")
            n %= size
    if n:
        out.append(("AND " if out and n < 100 else "") + _three(n))
    return " ".join(out)


def amount_words(sen):
    """An amount in sen in words, upper case, as SQL Account prints it: 44000 is FOUR HUNDRED AND FORTY ONLY, 123425
    is ONE THOUSAND TWO HUNDRED AND THIRTY FOUR AND CENTS TWENTY FIVE ONLY, 50 is CENTS FIFTY ONLY."""
    if not isinstance(sen, int) or isinstance(sen, bool) or sen < 0:
        raise ValueError("An amount in sen, not below zero.")
    ringgit, cents = divmod(sen, 100)
    text = number_words(ringgit) if ringgit or not cents else ""
    if cents:
        text = (f"{text} AND " if text else "") + f"CENTS {_two(cents)}"
    return f"{text} ONLY"


def money(sen):
    sign = "-" if sen < 0 else ""
    r, c = divmod(abs(sen), 100)
    return f"{sign}{r:,}.{c:02d}"


def _sen(v):
    return int(round((v or 0) * 100))


def _dmy(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "")


def _dmy_time(v):
    s = str(v or "").replace("T", " ")
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return _dmy(s) if s else ""


def _key(doc_no):
    return str(doc_no or "").strip().upper()


# ---------- what an invoice holds ----------

def _cols(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _einvoice_rows(con, s, direction):
    if not myinvois.ready(con):
        return []
    return [dict(r) for r in con.execute(
        """SELECT * FROM myinvois_docs WHERE entity_id = ? AND direction = ? AND (entry_id = ? OR uuid = ?)
           ORDER BY id""", (s["entity_id"], direction, s["id"], s["einvoice"] or ""))]


def kind_of(con, s):
    """'customer' for a customer invoice (an IV), 'self_billed' for a payment voucher with a self-billed e-Invoice in
    the MyInvois copies read, else None (nothing to print)."""
    s = dict(s)
    doc_type, kind = (s.get("doc_type") or "").upper(), s.get("kind") or "payment"
    if kind == "invoice" and (doc_type == "IV" or (not doc_type and s.get("direction") == "in")):
        return "customer"
    if kind == "payment" and doc_type not in ("OR", "RV", "CS") and s.get("direction") != "in" and _einvoice_rows(con, s, "self_billed"):
        return "self_billed"
    return None


def _party(con, eid, code=None, tin=None):
    if "parties" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}:
        return None
    if code:
        p = con.execute("""SELECT * FROM parties WHERE UPPER(TRIM(sql_code)) = ? AND (entity_id = ? OR entity_id IS NULL)
                           ORDER BY entity_id IS NULL LIMIT 1""", (code.strip().upper(), eid)).fetchone()
        if p:
            return dict(p)
    if tin:
        for p in con.execute("SELECT * FROM parties WHERE (entity_id = ? OR entity_id IS NULL) AND tin IS NOT NULL ORDER BY entity_id IS NULL, id",
                             (eid,)):
            if myinvois.tin_key(p["tin"]) == myinvois.tin_key(tin):
                return dict(p)
    return None


def _lines(con, eid, doc_no, doc_date=None):
    """The current version of the document's account lines from SQL's GL Journal of Transaction, or None. With the
    listing's date, lines kept under the same number but another date (SQL reuses numbers, for example a later year's
    document numbered as an earlier one) are refused with a sentence, so an invoice never prints another document's lines."""
    if not ledger.ready(con):
        return None
    d = con.execute("""SELECT * FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND doc_key = ? AND state = 'current'""",
                    (eid, _key(doc_no))).fetchone()
    if not d:
        return None
    if doc_date and str(d["doc_date"] or "")[:10] != str(doc_date)[:10]:
        raise InvoiceError(f"{doc_no}: SQL's account lines under this number are dated {_dmy(d['doc_date'])}, not this invoice's date "
                           f"({_dmy(doc_date)}), so it isn't printed with another document's lines. If its date was changed in SQL, "
                           "fetch the invoice listing again; if the number was used again, check it in SQL.")
    return [dict(x) for x in con.execute("SELECT * FROM ledger_lines WHERE doc_id = ? ORDER BY seq", (d["id"],))]


def _fetch_first(s):
    return f"Fetch SQL's GL Journal of Transaction covering {_dmy(s['doc_date'])} to print this invoice."


def _company(con, ent):
    e = dict(ent)
    reg = ""
    if e.get("reg_no") and e.get("old_reg_no"):
        reg = f"({e['reg_no']} ({e['old_reg_no']}))"
    elif e.get("reg_no") or e.get("old_reg_no"):
        reg = f"({e.get('reg_no') or e.get('old_reg_no')})"
    tin = f"(TIN No: {e['tin']})" if e.get("tin") else ""
    lines = [x.strip() for x in str(e.get("address") or "").splitlines() if x.strip()]
    address = " ".join(x if x.endswith(",") or i == len(lines) - 1 else x + "," for i, x in enumerate(lines))
    contact = [x for x in (f"Phone: {e['phone']}" if e.get("phone") else "", f"email: {e['email']}" if e.get("email") else "",
                           e.get("website") or "") if x]
    return {"name": e["name"], "reg_line": "  ".join(x for x in (reg, tin) if x), "address": address,
            "contact": "   |   ".join(contact), "logo": image_path(e, "logo"), "signature": image_path(e, "signature"),
            "sign_label": e.get("sign_label") or f"For {e['name']}", "tin": e.get("tin")}


def _pay_to(con, ent):
    e = dict(ent)
    if not e.get("invoice_account_id"):
        return None
    a = con.execute("SELECT * FROM accounts WHERE id = ? AND entity_id = ?", (e["invoice_account_id"], e["id"])).fetchone()
    if not a:
        return None
    a = dict(a)
    return {"name": e["name"], "bank": a.get("bank") or "", "bank_address": a.get("bank_address") or "",
            "account_no": a.get("number") or "", "swift": (a.get("swift_code") or "").upper()}


def missing_settings(con, ent):
    """What the company's invoices would print without, in words, for the page's Print settings note."""
    e, out = dict(ent), []
    if not ready(con):
        return ["The records need updating before invoices can be printed: restart the app."]
    named = lambda what="": f"{what + ' ' if what else ''}in Setup › Companies › {e['code']}"
    if not e.get("address"):
        out.append(f"No address: add it {named('as Address')}.")
    if not (e.get("phone") or e.get("email") or e.get("website")):
        out.append(f"No phone, email or website: add them {named()}.")
    if not e.get("reg_no"):
        out.append(f"No registration no.: add it {named()}.")
    if not e.get("tin"):
        out.append(f"No tax ID (TIN): add it {named()}.")
    for which, label in IMAGES.items():
        if not e.get(f"{which}_file"):
            out.append(f"No {which}: upload it {named('under Printed invoices')}.")
        elif image_path(e, which) is None:
            out.append(f"The {which} file changed or is missing since it was uploaded, so it isn't printed: upload it again "
                       f"{named('under Printed invoices')}.")
    if not e.get("invoice_account_id"):
        out.append(f"No bank account chosen for All payments to be made to: choose one {named('as Bank account on invoices')}.")
    else:
        a = con.execute("SELECT * FROM accounts WHERE id = ?", (e["invoice_account_id"],)).fetchone()
        if not a:
            out.append(f"The bank account chosen for invoices is gone: choose another {named('as Bank account on invoices')}.")
        else:
            a = dict(a)
            if not a.get("active", 1):
                out.append(f"The bank account chosen for invoices ({a['label']}) is stopped.")
            gaps = [w for w, k in (("bank", "bank"), ("account number", "number"), ("bank address", "bank_address"),
                                   ("bank transfer (SWIFT) code", "swift_code")) if not a.get(k)]
            if gaps:
                out.append(f"The bank account {a['label']} has no {', '.join(gaps[:-1]) + ' or ' + gaps[-1] if len(gaps) > 1 else gaps[0]}: "
                           "add it in Setup › Bank accounts.")
    return out


def _einvoice(rows, s, notes):
    """The e-Invoice block: {state: valid | no_link | cancelled | pending, uuid, link, validated_on, status} or None."""
    if not rows:
        if s["einvoice"]:
            notes.append(f"SQL shows e-Invoice {s['einvoice']} on {s['doc_no']}, but no copy of SQL's MyInvois Transaction screen "
                         "read here has it, so it prints without its QR code. Fetch a copy of MyInvois to add it.")
        return None
    valid = [r for r in rows if r["status"] == "Valid"]
    if valid:
        r = max(valid, key=lambda x: (x["validated_at"] or "", x["issued_at"] or "", x["id"]))
        link = myinvois.link_of(r)
        out = {"state": "valid" if link else "no_link", "uuid": r["uuid"], "link": link,
               "validated_on": _dmy_time(r["validated_at"]), "status": r["status"], "row": r}
        if not link:
            notes.append(f"e-Invoice {r['uuid']} has no Long ID in the MyInvois copies read, so its QR code can't be printed. "
                         "Copy SQL's MyInvois Transaction screen with its Long ID column and fetch it, then print again.")
        return out
    r = max(rows, key=lambda x: (x["issued_at"] or "", x["as_at"] or "", x["id"]))
    if r["status"] == "Cancelled":
        notes.append(f"e-Invoice {r['uuid']} was cancelled on MyInvois: the invoice prints with no QR code and says so.")
        return {"state": "cancelled", "uuid": r["uuid"], "link": None, "validated_on": None, "status": r["status"], "row": r}
    notes.append(f"e-Invoice {r['uuid']} is {r['status'] or 'not validated'} on MyInvois, not validated, so it prints without a QR code.")
    return {"state": "pending", "uuid": r["uuid"], "link": None, "validated_on": None, "status": r["status"], "row": r}


def document(con, sid):
    """Everything one printed invoice holds, from the records: {kind, title, doc_no, date, account, terms, party_label,
    party (name, address lines, attn, tin), buyer, company, pay_to, lines [{code, description, sen}], total_sen,
    currency, words, einvoice, notes (sentences for the page), missing (settings missing)}. Raises InvoiceError with
    a sentence when it can't be printed."""
    s = con.execute("SELECT * FROM sql_entries WHERE id = ?", (sid,)).fetchone()
    if not s:
        raise InvoiceError("This SQL document is no longer in the records.", 404)
    s = dict(s)
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (s["entity_id"],)).fetchone()
    kind = kind_of(con, s)
    if kind is None:
        raise InvoiceError(f"{s['doc_no']} isn't a customer invoice or a payment voucher with a self-billed e-Invoice, so it has "
                           "no invoice to print.")
    if s.get("deleted_in_sql"):
        raise InvoiceError(f"{s['doc_no']} was confirmed as deleted in SQL, so it isn't printed.")
    lines = _lines(con, s["entity_id"], s["doc_no"], s["doc_date"])
    if not lines:
        raise InvoiceError(f"SQL's account lines of {s['doc_no']} haven't been fetched. {_fetch_first(s)}")
    notes = []
    code = (s.get("code") or "").strip().upper()
    if kind == "customer":
        if not code:
            debits = {x["account_code"] for x in lines if x["dr_sen"] > x["cr_sen"]}
            code = next(iter(debits)) if len(debits) == 1 else ""
        if not code or not any(x["account_code"] == code for x in lines):
            raise InvoiceError(f"{s['doc_no']}: SQL's account lines don't show which line is the customer's (its listing has no "
                               "customer code). Fetch the invoice listing again, then print it.")
        total = sum(x["dr_sen"] - x["cr_sen"] for x in lines if x["account_code"] == code)
        items = [{"code": x["account_code"], "description": x["description"] or x["account_name"] or s["description"] or "",
                  "sen": x["cr_sen"] - x["dr_sen"]} for x in lines if x["account_code"] != code and x["cr_sen"] != x["dr_sen"]]
        listed = _sen(s["amount"])
        if total != listed:
            raise InvoiceError(f"{s['doc_no']}: SQL's account lines put {money(total)} on the customer's account {code}, but SQL's "
                               f"listing says {money(listed)}. Fetch the listing and the GL Journal of Transaction covering "
                               f"{_dmy(s['doc_date'])} again so they agree, then print it.")
        if sum(x["sen"] for x in items) != total:
            raise InvoiceError(f"{s['doc_no']}: SQL's account lines don't balance (the lines come to {money(sum(x['sen'] for x in items))}, "
                               f"the customer's account to {money(total)}). {_fetch_first(s)}")
        party = _party(con, s["entity_id"], code) or {}
        rows = _einvoice_rows(con, s, "issued")
        einv = _einvoice(rows, s, notes)
        name = party.get("name") or s.get("payee") or (einv or {}).get("row", {}).get("buyer_name") or code
        title, label, currency = "Invoice", "To", "MYR"
        buyer = None
        tin = None
    else:
        rows = _einvoice_rows(con, s, "self_billed")
        einv = _einvoice(rows, s, notes)
        r = einv["row"]
        banks = ledger.bank_codes(con, s["entity_id"])
        if banks:
            picked = [x for x in lines if x["account_code"] not in banks and x["dr_sen"] != x["cr_sen"]]
        else:
            picked = [x for x in lines if x["dr_sen"] > x["cr_sen"]]
        items = [{"code": x["account_code"], "description": x["description"] or x["account_name"] or s["description"] or "",
                  "sen": x["dr_sen"] - x["cr_sen"]} for x in picked]
        total = r["total_sen"]
        currency = (r["currency"] or "MYR").upper()
        if sum(x["sen"] for x in items) != total:
            notes.append(f"The e-Invoice's total on MyInvois ({currency} {money(total)}) isn't what the voucher's lines come to "
                         f"(MYR {money(sum(x['sen'] for x in items))}): it prints MyInvois's total. Check the voucher in SQL.")
        party = _party(con, s["entity_id"], code, r["supplier_tin"]) or {}
        name = r["supplier_name"] or party.get("name") or s.get("payee") or code
        tin = r["supplier_tin"] or party.get("tin")
        title, label = "Self-billed Invoice", "Supplier"
        e = dict(ent)
        buyer = e["name"] + (f" (TIN No: {e['tin']})" if e.get("tin") else "")
    company = _company(con, ent)
    return {"kind": kind, "entry_id": s["id"], "entity_code": ent["code"], "title": title, "doc_no": s["doc_no"],
            "date": _dmy(s["doc_date"]), "doc_date": s["doc_date"], "account": code, "terms": party.get("credit_term") or "",
            "party_label": label,
            "party": {"name": name, "address": [party[k] for k in ("address_1", "address_2", "address_3", "address_4") if party.get(k)],
                      "attn": party.get("attention") or "", "tin": tin},
            "buyer": buyer, "company": company, "pay_to": _pay_to(con, ent) if kind == "customer" else None,
            "lines": items, "total_sen": total, "currency": currency,
            "words": f"{CURRENCY_NAMES.get(currency, currency)} : {amount_words(total)}" if total >= 0 else "",
            "einvoice": {k: v for k, v in einv.items() if k != "row"} if einv else None,
            "notes": notes, "missing": missing_settings(con, ent)}


def file_name(doc):
    return safe(f"{doc['doc_no']} {doc['party']['name']}", 120) + ".pdf"


# ---------- the fonts ----------

# SQL Account prints its invoice in these Windows fonts (named in the PDF it exports): for each, its file, its name, what
# it prints, the free look-alikes used when the file isn't found (other computers, such as Linux, often have them) and
# the font built into the PDF maker used when neither is found. Font files are only read where they are installed (or
# a folder outside the records folder named in HRP_FONT_DIR): none is ever copied into the program or the records
# folder, and a file that doesn't read in full is passed over for the next one found.
FONTS = {
    "times": ("times.ttf", "Times New Roman", "the registration, address and phone lines at the top",
              [("LiberationSerif-Regular.ttf", "Liberation Serif")], ("Times", "")),
    "times-bold": ("timesbd.ttf", "Times New Roman Bold", "the company's name at the top",
                   [("LiberationSerif-Bold.ttf", "Liberation Serif Bold")], ("Times", "B")),
    "tahoma": ("tahoma.ttf", "Tahoma", "most of the invoice's words",
               [("DejaVuSans.ttf", "DejaVu Sans"), ("LiberationSans-Regular.ttf", "Liberation Sans")], ("Helvetica", "")),
    "tahoma-bold": ("tahomabd.ttf", "Tahoma Bold", "the title, the document number and Total",
                    [("DejaVuSans-Bold.ttf", "DejaVu Sans Bold"), ("LiberationSans-Bold.ttf", "Liberation Sans Bold")],
                    ("Helvetica", "B")),
    "trebuchet": ("trebuc.ttf", "Trebuchet MS", "the amounts",
                  [("DejaVuSans.ttf", "DejaVu Sans"), ("LiberationSans-Regular.ttf", "Liberation Sans")], ("Helvetica", "")),
    "segoe": ("segoeui.ttf", "Segoe UI", "the bank details' labels",
              [("DejaVuSans.ttf", "DejaVu Sans"), ("LiberationSans-Regular.ttf", "Liberation Sans")], ("Helvetica", "")),
    "segoe-bold": ("segoeuib.ttf", "Segoe UI Bold", "the bank details",
                   [("DejaVuSans-Bold.ttf", "DejaVu Sans Bold"), ("LiberationSans-Bold.ttf", "Liberation Sans Bold")],
                   ("Helvetica", "B")),
}
BUILT_IN_NAMES = {("Times", ""): "Times", ("Times", "B"): "Times Bold", ("Helvetica", ""): "Helvetica",
                  ("Helvetica", "B"): "Helvetica Bold"}

# A look-alike is never printed larger than SQL's font: it is drawn at SQL's size times the smaller of 1 and r, where r
# is how wide REFERENCE is in SQL's font over how wide it is in the look-alike, so a wider look-alike is drawn smaller
# and a narrower one keeps SQL's size. SQL_WIDTHS are REFERENCE's widths in SQL's fonts (mm at 10 pt) and
# BUILT_IN_RATIOS the ratios r for the fonts built into the PDF maker, both measured on 15/11/2026 with fpdf2 2.9.0's
# get_string_width from the Windows 11 font files above (they are numbers, not font data). A look-alike found on the
# computer is measured the same way when it is used.
REFERENCE = "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz .,:;()/-&'"
SQL_WIDTHS = {"times": 135.170, "times-bold": 142.385, "tahoma": 136.250, "tahoma-bold": 156.729, "trebuchet": 135.375,
              "segoe": 134.952, "segoe-bold": 146.089}
BUILT_IN_RATIOS = {"times": 1.0, "times-bold": 1.0, "tahoma": 0.9660, "tahoma-bold": 1.0642, "trebuchet": 0.9598,
                   "segoe": 0.9568, "segoe-bold": 0.9920}
SYSTEM_FONT_DIRS = ("/usr/share/fonts", "/usr/local/share/fonts", "~/.local/share/fonts", "~/.fonts")
FONT_DIRS = None  # tests only: a list of folders that replaces every place fonts are looked for
_system_index = {}
_font_ok_cache = {}
_print_trouble = []  # font files that failed while an invoice was being printed (named in font_notes)
_font_failed = set()  # those files, by path, size and when they last changed: passed over from then on


def _named_font_dir():
    """The folder named by HRP_FONT_DIR (or the font_dir setting) as (path or None, whether it is inside the records
    folder). A folder inside the records folder is never searched: font files are not kept there."""
    named = os.environ.get("HRP_FONT_DIR") or SETTINGS.get("font_dir") or ""
    if not str(named).strip():
        return None, False
    p = Path(named)
    try:
        inside = p.resolve().is_relative_to(Path(DATA_DIR).resolve())
    except (OSError, ValueError):
        inside = False
    return (None, True) if inside else (p, False)


def font_dirs():
    """Where SQL's fonts are looked for, in order: the folder named by HRP_FONT_DIR (or the font_dir setting), which
    must be outside the records folder, then Windows' fonts. Nothing in the records folder is ever searched."""
    if FONT_DIRS is not None:
        return [Path(d) for d in FONT_DIRS]
    named, _inside = _named_font_dir()
    windows = Path(os.environ.get("WINDIR") or r"C:\Windows") / "Fonts"
    return [d for d in (named, windows) if d is not None]


def _font_ok(path):
    """Whether a font file reads and prints: every table its header lists is inside the file (a file cut short fails
    this), and a test PDF with a few letters in it comes out. Remembered by path, size and when the file last changed."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _font_ok_cache:
        ok = False
        try:
            with open(path, "rb") as fh:
                data = fh.read()
            tables = int.from_bytes(data[4:6], "big")
            ok = 0 < tables and len(data) >= 12 + 16 * tables and all(
                int.from_bytes(data[20 + 16 * n:24 + 16 * n], "big") + int.from_bytes(data[24 + 16 * n:28 + 16 * n], "big")
                <= len(data) for n in range(tables))
            if ok:
                test = FPDF()
                test.add_page()
                test.add_font("hrp-test", "", str(path))
                test.set_font("hrp-test", "", 10)
                test.text(10, 10, REFERENCE)
                test.output()
        except Exception:
            ok = False
        _font_ok_cache[key] = ok
    return _font_ok_cache[key]


def _in_folder(folder, name):
    p = folder / name
    if p.is_file():
        return p
    try:
        return next((folder / n for n in os.listdir(folder) if n.lower() == name.lower() and (folder / n).is_file()), None)
    except OSError:
        return None


def _in_system(name):
    """A font file anywhere under the usual font folders of Linux, found once and remembered."""
    if FONT_DIRS is not None:
        return None
    if not _system_index:
        _system_index[""] = ""
        for top in SYSTEM_FONT_DIRS:
            for root, _dirs, files in os.walk(os.path.expanduser(top)):
                for f in files:
                    _system_index.setdefault(f.lower(), Path(root) / f)
    return _system_index.get(name.lower())


def _find(name, system=False):
    """The first font file of this name that reads and prints, in the folders searched (and, for a look-alike, the
    computer's own font folders). A damaged or empty copy is passed over, so a good one later in the search is used."""
    for d in font_dirs():
        p = _in_folder(d, name)
        if p and _font_ok(p) and not _failed(p):
            return p
    if system:
        p = _in_system(name)
        if p and _font_ok(p) and not _failed(p):
            return p
    return None


def _font_key(path):
    st = os.stat(path)
    return (str(path), st.st_size, st.st_mtime_ns)


def _failed(path):
    """Whether this font file failed while an invoice was being printed (and hasn't changed since)."""
    try:
        return _font_key(path) in _font_failed
    except OSError:
        return True


def font_choice(key):
    """Which font prints this part of the invoice: {kind: sql | look-alike | built-in, name, path, built_in}."""
    file, name, _what, alikes, built_in = FONTS[key]
    p = _find(file)
    if p:
        return {"kind": "sql", "name": name, "path": p}
    for alike, alike_name in alikes:
        p = _find(alike, system=True)
        if p:
            return {"kind": "look-alike", "name": alike_name, "path": p}
    return {"kind": "built-in", "name": BUILT_IN_NAMES[built_in], "built_in": built_in}


def font_notes():
    """In words, which of SQL's fonts this computer lacks and what invoices print instead (empty when all are found),
    for the invoice check and the print settings."""
    out, files = [], []
    for key, (file, name, what, _alikes, _built_in) in FONTS.items():
        f = font_choice(key)
        if f["kind"] == "sql":
            continue
        instead = (f"{f['name']}, a free look-alike on this computer" if f["kind"] == "look-alike"
                   else f"{f['name']}, the PDF maker's own look-alike")
        out.append(f"SQL's font {name} ({what}) isn't on this computer (or its file is damaged), so invoices print it in "
                   f"{instead}, never larger than SQL's size.")
        files.append(file)
    if FONT_DIRS is None and _named_font_dir()[1]:
        out.append("The fonts folder named in HRP_FONT_DIR (or the font_dir setting) is inside the records folder, so it "
                   "isn't used: font files are never kept in the records folder. Name a folder outside it.")
    if files:
        out.append(f"To print exactly as SQL does, install {', '.join(files)} on this computer from a Windows computer's "
                   "Fonts folder, or put licensed copies of them in a folder outside the records folder and name that "
                   "folder in HRP_FONT_DIR.")
    if _print_trouble:
        out.append(f"A font file ({', '.join(sorted(set(_print_trouble)))}) failed while an invoice was being printed, so "
                   "that invoice was printed in the PDF maker's own look-alikes. Install a good copy of the font, then print "
                   "it again.")
    return out


class _Fonts:
    """The fonts of one PDF: each loaded the first time it is used, at its scale (1 for SQL's own font)."""

    def __init__(self, pdf, built_in_only=False):
        self.pdf, self.loaded, self.core, self.built_in_only = pdf, {}, False, built_in_only

    def info(self, key):
        if key not in self.loaded:
            f = dict(font_choice(key))
            if self.built_in_only:
                f = {"kind": "built-in", "name": BUILT_IN_NAMES[FONTS[key][4]], "built_in": FONTS[key][4]}
            if f["kind"] != "built-in":
                try:
                    family = f"hrp-{key}"
                    self.pdf.add_font(family, "", str(f["path"]))
                    f.update(family=family, style="", core=False, scale=1.0)
                    if f["kind"] == "look-alike":
                        self.pdf.set_font(family, "", 10)
                        f["scale"] = min(1.0, SQL_WIDTHS[key] / self.pdf.get_string_width(REFERENCE))
                except Exception:  # a font file that can't be read: the built-in look-alike instead
                    f = {"kind": "built-in", "name": BUILT_IN_NAMES[FONTS[key][4]], "built_in": FONTS[key][4]}
            if f["kind"] == "built-in":
                f.update(family=f["built_in"][0], style=f["built_in"][1], core=True, scale=min(1.0, BUILT_IN_RATIOS[key]))
            self.loaded[key] = f
        return self.loaded[key]

    def set(self, key, size):
        """Sets the font for SQL's font key at SQL's size; returns the size used (smaller for a wider look-alike)."""
        f = self.info(key)
        self.core = f["core"]
        self.pdf.set_font(f["family"], f["style"], size * f["scale"])
        return size * f["scale"]

    def clean(self, text):
        """The text as the font can print it: any character with a TrueType font, Latin-1 only with a built-in one."""
        text = str(text or "")
        return text.encode("latin-1", "replace").decode("latin-1") if self.core else text


# ---------- the PDF: SQL Account's invoice, measured from the PDF SQL exports ----------
# Every position is in mm from the page's top-left corner; text is placed by its baseline, as SQL's PDF places it.

PAGE_W, PAGE_H = 215.9, 279.4  # US Letter, as SQL prints
RULE_W = 0.75 * 25.4 / 72      # its rules are 0.75 pt
LOGO_BOX = (10.66, 7.46, 26.32, 25.40)
HEAD_CX, HEAD_W = 121.4, 168.6  # the header's lines are centred in the band from 37.0 to 205.6
NAME_Y, REG_Y, ADDRESS_Y, CONTACT_Y = 12.84, 16.62, 19.80, 22.99
TITLE_CX, TITLE_Y = 107.72, 37.04  # "Invoice" starts at 99.8, centred on the page
LABEL_X, PARTY_X, PARTY_Y, STEP, ATTN_Y = 11.19, 21.23, 41.48, 4.04, 61.69
BLOCK_RIGHT = 148.0     # where the lines beside the document's number, date, account and terms must stop
RIGHT_VALUE_X = 170.62
# The labels at the right, right-aligned where SQL's end (its starts 150.43, 154.43, 150.41 and 153.09 in Tahoma):
RIGHT_BLOCK = (("Doc No.  :", "tahoma-bold", 167.52, 41.48, "tahoma-bold", 9, 41.16, "doc_no"),
               ("Date   :", "tahoma", 166.27, 46.58, "tahoma", 10, 46.58, "date"),
               ("Account  :", "tahoma", 166.27, 51.58, "tahoma", 10, 51.58, "account"),
               ("Terms  :", "tahoma", 166.27, 56.57, "tahoma", 10, 56.57, "terms"))
L, R = 10.66, 205.57    # the table's rules run between these
TOP_RULE, HEAD_RULE = 68.06, 73.14
DIV1, DIV2 = 36.98, 170.10  # the rules between the headings (in the heading band only)
HEAD_TEXT_Y = 71.69
CODE_X, DESC_X, DESC_CX, AMOUNT_R = 11.19, 36.74, 103.16, 205.05
FIRST_ROW, ROW, ROW_TOP = 77.14, 4.50, 3.21  # a row's baseline, its height, and from its cell's top to its baseline
DESC_W = DIV2 - DESC_X - 0.5
FOOT_RULE = 212.69
LINES_END = FOOT_RULE - ROW  # rows stop here, leaving room above the rule for "Continued on page ..."
WORDS_X, WORDS_Y, WORDS_W, WORDS_STEP = 11.56, 216.20, 132.0, 4.04
TOTAL_R = 169.59             # "Total :" starts at 158.29
PAY_Y, BANK_X, BANK_NAME_Y = 223.20, 11.45, 227.17
BANK_YS = (230.40, 233.62, 236.84, 240.07)
BANK_SIZE = 6.91
SIGN_BOX = (13.43, 253.69, 48.0, 10.0)
SIGN_RULE_Y, SIGN_RULE = 271.93, (12.03, 75.36)
FOR_X, FOR_Y = 12.56, 275.45
QR_X, QR_Y, QR_SIZE = 181.91, 243.69, 20.0
QR_R = QR_X + QR_SIZE
UUID_SIZE, UUID_STEP = 5.5, 2.4
DESCENT = 0.9                # below a 10 pt line's baseline


MIN_SHRINK = 0.5  # a line too long for its room is made smaller, but never below half its size (it would be unreadable)
# The parts of an invoice that can be too long for their room, in words, with where to shorten them ({code}: the company)
CUT_FIELDS = {
    "company_name": ("The company's name in the header", "in Setup › Companies › {code}", True),
    "reg_line": ("The registration no. and TIN line in the header", "in Setup › Companies › {code}", True),
    "address": ("The company's address in the header", "in Setup › Companies › {code}", True),
    "contact": ("The phone, email and website line in the header", "in Setup › Companies › {code}", True),
    "party": ("A line of who the invoice is to (name, address, TIN, Attn or Buyer)",
              "in the customer's or supplier's record (Setup, or SQL)", False),
    "doc_no": ("The document number", "in SQL", False),
    "date": ("The date", "", False),
    "account": ("The account code", "in SQL", False),
    "terms": ("The terms", "in the customer's record in Setup", False),
    "code": ("An account code in the lines", "in SQL", False),
    "description": ("A line's description", "in SQL", False),
    "amount": ("An amount", "", False),
    "words": ("The amount in words", "", False),
    "bank_name": ("The company's name in the bank details", "in Setup › Companies › {code}", True),
    "bank": ("The bank's name", "in Setup › Bank accounts", True),
    "bank_address": ("The bank's address", "in Setup › Bank accounts", True),
    "account_no": ("The bank account number", "in Setup › Bank accounts", True),
    "swift": ("The bank transfer (SWIFT) code", "in Setup › Bank accounts", True),
    "sign_label": ("The words under the signature", "in Setup › Companies › {code}", True),
    "einvoice": ("A line under the QR code", "", False),
}


class _Printer:
    """Puts text on the PDF by its baseline in SQL's fonts and sizes (a look-alike scaled down when wider), shrinking
    (never enlarging) a line that would overrun its room. A line still too long at half its size has its end cut off,
    and is noted in cut as (field, the full text, what printed). With trace, notes each piece printed (for the tests)."""

    def __init__(self, pdf, trace=None, built_in_only=False):
        self.pdf, self.fonts, self.trace = pdf, _Fonts(pdf, built_in_only), trace
        self.cut, self.printed = [], {}

    def put(self, key, size, x, base, text, align="L", fit=None, what=None):
        """Prints text from x (align L), ending at x (R) or centred on x (C), its baseline at base. Returns where it ends."""
        pdf = self.pdf
        used = self.fonts.set(key, size)
        text = self.fonts.clean(text)
        w = pdf.get_string_width(text)
        if fit and w > fit:
            used = max(used * fit / w * 0.999, used * MIN_SHRINK)
            pdf.set_font_size(used)
            full = text
            while text and pdf.get_string_width(text) > fit:
                text = text[:-1]
            if text != full:
                self.cut.append((what, full, text))
            w = pdf.get_string_width(text)
        if text:
            self.printed.setdefault(key, set()).add(text)
        x0 = x if align == "L" else x - w if align == "R" else x - w / 2
        if text:
            pdf.text(x0, base, text)
            if self.trace is not None:
                self.trace.append({"page": pdf.page, "text": text, "x": x0, "w": w, "base": base, "size": used,
                                   "sql_size": size, "font": key, "font_name": self.fonts.info(key)["name"]})
        return x0 + w

    def wrap(self, key, size, text, width):
        """The text's lines when wrapped to width at the font and size (the font is left set)."""
        self.fonts.set(key, size)
        return self.pdf.multi_cell(width, ROW, self.fonts.clean(text), dry_run=True, output="LINES") or [""]

    def width(self, key, size, text):
        self.fonts.set(key, size)
        return self.pdf.get_string_width(self.fonts.clean(text))

    def rule(self, x1, y1, x2, y2):
        self.pdf.set_draw_color(0)
        self.pdf.set_line_width(RULE_W)
        self.pdf.line(x1, y1, x2, y2)


def _image(pdf, path, x, y, w, h):
    """The image scaled to fit in the box, at its top left, keeping its shape."""
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pdf.image(str(path), x=x, y=y, w=iw * scale, h=ih * scale)


def _party_block(doc):
    """The lines of who the invoice is to, at the left, as [(baseline, text, right edge)], and where the last one ends
    (mm from the top): the name and address (and a supplier's TIN) a line apart, then Attn where SQL prints it (or a
    blank line lower when the address runs further), then the Buyer."""
    p, out = doc["party"], []
    texts = [p["name"], *p["address"]][:6]
    if p.get("tin") and doc["kind"] == "self_billed":
        texts.append(f"TIN : {p['tin']}")
    for n, text in enumerate(texts):
        out.append((PARTY_Y + n * STEP, text))
    y = max(ATTN_Y, out[-1][0] + 2 * STEP)
    if p.get("attn"):
        out.append((y, f"Attn : {p['attn']}"))
        y += STEP
    if doc.get("buyer"):
        out.append((y, f"Buyer : {doc['buyer']}"))
    return [(b, t, BLOCK_RIGHT if b < 59 else R) for b, t in out], max(b for b, _ in out) + DESCENT


def _table_top(doc):
    """Where the table's top rule goes: where SQL prints it (68.06 mm), or lower when the block at the left runs
    further (a supplier with four address lines, its TIN, Attn and the Buyer), so no line of it prints over the headings."""
    return max(TOP_RULE, round(_party_block(doc)[1] + 1.2, 2))


def _header(pg, doc):
    c = doc["company"]
    if c["logo"]:
        _image(pg.pdf, c["logo"], *LOGO_BOX)
    pg.put("times-bold", 15.86, HEAD_CX, NAME_Y, c["name"], "C", HEAD_W, "company_name")
    for base, text, what in ((REG_Y, c["reg_line"], "reg_line"), (ADDRESS_Y, c["address"], "address"),
                             (CONTACT_Y, c["contact"], "contact")):
        if text:
            pg.put("times", 7.99, HEAD_CX, base, text, "C", HEAD_W, what)
    pg.put("tahoma-bold", 12, TITLE_CX, TITLE_Y, doc["title"], "C", 90)
    # Who it is to, at the left ("Supplier  :" is longer than "To  :", so its lines start further right)
    x = max(PARTY_X, pg.put("tahoma", 10, LABEL_X, PARTY_Y, f"{doc['party_label']}  :") + 1.0)
    for base, text, right in _party_block(doc)[0]:
        pg.put("tahoma", 10, x, base, text, "L", right - x, "party")
    # The document's number, date, account and terms, at the right
    for label, key, end, base, vkey, vsize, vbase, field in RIGHT_BLOCK:
        pg.put(key, 10, end, base, label, "R")
        pg.put(vkey, vsize, RIGHT_VALUE_X, vbase, doc[field], "L", R - RIGHT_VALUE_X, field)
    # The table's headings, lower down when the block at the left needs the room
    top = _table_top(doc)
    head = top + HEAD_RULE - TOP_RULE
    pg.rule(L, top, R, top)
    pg.rule(L, head, R, head)
    pg.rule(DIV1, top, DIV1, head)
    pg.rule(DIV2, top, DIV2, head)
    base = top + HEAD_TEXT_Y - TOP_RULE
    pg.put("tahoma", 9, CODE_X, base, "G/L CODE")
    pg.put("tahoma", 9, DESC_CX, base, "DESCRIPTION", "C")
    pg.put("tahoma", 9, AMOUNT_R, base, f"Amount({doc['currency']})", "R")


def _rows(pg, doc):
    """Each line as (code, [description lines], amount), its description wrapped to the column."""
    return [(x["code"], pg.wrap("tahoma", 9, x["description"], DESC_W), money(x["sen"])) for x in doc["lines"]]


def _pages(rows, start=FIRST_ROW):
    """The rows put on pages, each page's rows from the baseline start down to LINES_END. A row is kept whole on the
    next page when it doesn't fit under the rows above it; a row longer than a whole page (a very long description) is
    split, its code and amount on its first part and the rest of its description carried on to the next page."""
    room_of = lambda b: max(0, int((LINES_END - (b - ROW_TOP)) / ROW + 1e-9))
    full = room_of(start)
    pages, page, y = [], [], start
    for code, parts, amount in rows:
        first = True
        while True:
            room = room_of(y)
            if len(parts) <= room:
                page.append((code if first else "", parts, amount if first else ""))
                y += len(parts) * ROW
                break
            if room and (not page or len(parts) > full):
                page.append((code if first else "", parts[:room], amount if first else ""))
                parts, first = parts[room:], False
            pages.append(page)
            page, y = [], start
    pages.append(page)
    return pages


def _draw_rows(pg, page, start=FIRST_ROW):
    y = start
    for code, parts, amount in page:
        pg.put("tahoma", 9, CODE_X, y, code, "L", DIV1 - CODE_X - 0.4, "code")
        for i, part in enumerate(parts):
            pg.put("tahoma", 9, DESC_X, y + i * ROW, part, "L", DESC_W, "description")
        pg.put("trebuchet", 9, AMOUNT_R, y, amount, "R", AMOUNT_R - DIV2 - 0.5, "amount")
        y += len(parts) * ROW


def _qr(pdf, link, x, y, size):
    """The QR code of the link, drawn as squares (sharp at any zoom), and a link over it. Returns the size of one of
    its squares (mm): the QR standard asks for four of them of blank paper all round it, so a phone reads it."""
    qr = segno.make(link, error="m", micro=False)
    matrix = qr.matrix
    n = len(matrix)
    m = size / n
    pdf.set_fill_color(0)
    for j, row in enumerate(matrix):
        i = 0
        while i < n:
            if row[i]:
                start = i
                while i < n and row[i]:
                    i += 1
                pdf.rect(x + start * m, y + j * m, (i - start) * m, m + 0.02, style="F")
            else:
                i += 1
    pdf.link(x, y, size, size, link)
    return m


def _footer(pg, doc):
    pdf = pg.pdf
    pg.rule(11.03, FOOT_RULE, R, FOOT_RULE)
    # The amount in words, wrapped within its cell when too long for one line (up to three lines, smaller if need be)
    size = 10
    parts = pg.wrap("tahoma", size, doc["words"], WORDS_W)
    while len(parts) > 3 and size > 6:
        size -= 0.25
        parts = pg.wrap("tahoma", size, doc["words"], WORDS_W)
    for n, part in enumerate(parts[:3]):
        pg.put("tahoma", size, WORDS_X, WORDS_Y + n * WORDS_STEP, part, "L", WORDS_W, "words")
    extra = (min(len(parts), 3) - 1) * WORDS_STEP
    pg.put("tahoma-bold", 10, TOTAL_R, WORDS_Y, "Total :", "R")
    pg.put("trebuchet", 10, AMOUNT_R, WORDS_Y, money(doc["total_sen"]), "R", AMOUNT_R - RIGHT_VALUE_X, "amount")
    c, pay = doc["company"], doc["pay_to"]
    if pay:
        pg.put("tahoma", 10, WORDS_X, PAY_Y + extra, "All payments to be made to :")
        pg.put("segoe-bold", BANK_SIZE, BANK_X, BANK_NAME_Y + extra, pay["name"], "L", 130, "bank_name")
        for base, (label, value, what) in zip(BANK_YS, (("Bank", pay["bank"], "bank"), ("Bank Address", pay["bank_address"], "bank_address"),
                                                        ("Account No", pay["account_no"], "account_no"),
                                                        ("Bank Transfer Code", pay["swift"], "swift"))):
            pdf.set_text_color(70)
            end = pg.put("segoe", BANK_SIZE, BANK_X, base + extra, f"{label} :")
            pdf.set_text_color(0)
            end += pg.width("segoe", BANK_SIZE, " ")
            pg.put("segoe-bold", BANK_SIZE, end, base + extra, value, "L", BANK_X + 130 - end, what)
    if c["signature"]:
        _image(pdf, c["signature"], *SIGN_BOX)
    pg.rule(SIGN_RULE[0], SIGN_RULE_Y, SIGN_RULE[1], SIGN_RULE_Y)
    pg.put("tahoma", 10, FOR_X, FOR_Y, c["sign_label"], "L", 135, "sign_label")
    e = doc["einvoice"]
    if e:
        cap = UUID_SIZE * 0.8 * 25.4 / 72
        y = QR_Y + QR_SIZE + 2.0 + cap
        if e["state"] == "valid":
            # the lines under it start four squares below it, leaving the QR code its margin of blank paper
            y = QR_Y + QR_SIZE + max(2.0, 4 * _qr(pdf, e["link"], QR_X, QR_Y, QR_SIZE)) + cap
            lines = [f"e-Invoice UUID: {e['uuid']}"] + ([f"Validated on {e['validated_on']}"] if e["validated_on"] else [])
        elif e["state"] == "cancelled":
            pdf.set_text_color(170, 0, 0)
            pg.put("tahoma-bold", 10, QR_R, QR_Y + 11.5, "e-Invoice cancelled", "R")
            pdf.set_text_color(0)
            lines = [f"e-Invoice UUID: {e['uuid']}", "Cancelled on MyInvois: this e-Invoice is no longer valid."]
        elif e["state"] == "no_link":
            lines = [f"e-Invoice UUID: {e['uuid']}"] + ([f"Validated on {e['validated_on']}"] if e["validated_on"] else []) + [
                "QR code not printed: MyInvois's Long ID for it wasn't read."]
        else:
            lines = [f"e-Invoice UUID: {e['uuid']}", f"Not validated on MyInvois ({e['status'] or 'no status'}): no QR code."]
        for text in lines:
            pg.put("tahoma", UUID_SIZE, QR_R, y, text, "R", 60, "einvoice")
            y += UUID_STEP


def render(doc, trace=None, cut=None):
    """The invoice as PDF bytes: US Letter portrait, laid out as SQL Account prints its invoice, in its fonts (or
    look-alikes no larger, where this computer lacks them). Lines that don't fit go on to another page with the header
    again; the total, payment details, signature and QR code are on the last page. With trace (a list), each piece of
    text printed is noted in it, with its place, font and size; with cut (a list), each line too long to print in full
    is noted in it as (field, the full text, what printed).
    A font file that loads but fails when the PDF is made (a damaged file) is found, passed over from then on (and
    named in font_notes), and the invoice is printed again with the next font found; if that can't be told, with the
    PDF maker's own look-alikes."""
    pdf, pg = _draw(doc, trace)
    try:
        data = bytes(pdf.output())
    except Exception:
        used = {k: f for k, f in pg.fonts.loaded.items() if not f["core"]}
        if not used:
            raise
        bad = []
        for key, f in used.items():
            try:
                test = FPDF()
                test.add_page()
                test.add_font("hrp-test", "", str(f["path"]))
                test.set_font("hrp-test", "", 10)
                for n, text in enumerate(sorted(pg.printed.get(key, ()))):
                    test.text(10, 10 + (n % 50) * 5, text)
                test.output()
            except Exception:
                bad.append(f["path"])
        for p in bad:
            try:
                _font_failed.add(_font_key(p))
            except OSError:
                pass
            _print_trouble.append(str(p))
        if trace is not None:
            trace.clear()
        pdf, pg = _draw(doc, trace, built_in_only=not bad)
        if not bad:
            _print_trouble.extend(str(f["path"]) for f in used.values())
        data = bytes(pdf.output())
    if cut is not None:
        cut.extend(pg.cut)
    return data


def _draw(doc, trace=None, built_in_only=False):
    """The invoice drawn on a new PDF (not yet made into bytes): (pdf, the printer that drew it)."""
    pdf = FPDF(unit="mm", format="Letter")
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.c_margin = 0
    pdf.set_title(f"{doc['title']} {doc['doc_no']}")
    pdf.set_author(doc["company"]["name"])
    pdf.set_creator("HR Payments")
    pg = _Printer(pdf, trace, built_in_only)
    pdf.add_page()  # first: wrapping the descriptions needs a page
    start = _table_top(doc) + FIRST_ROW - TOP_RULE
    pages = _pages(_rows(pg, doc), start)
    for n, page in enumerate(pages, 1):
        if n > 1:
            pdf.add_page()
        _header(pg, doc)
        _draw_rows(pg, page, start)
        if n == len(pages):
            _footer(pg, doc)
        else:
            pg.put("tahoma", 8, AMOUNT_R, FOOT_RULE - 1.7, f"Continued on page {n + 1} of {len(pages)}", "R")
        if len(pages) > 1:
            pg.put("tahoma", 7, AMOUNT_R, 277.6, f"Page {n} of {len(pages)}", "R")
    return pdf, pg


def cut_notes(cuts, code=""):
    """In words, each line too long to print in full (from render's cut), once per field, saying where to shorten it."""
    out, seen = [], set()
    for what, full, shown in cuts:
        phrase, where, _setup = CUT_FIELDS.get(what, ("A piece of text", "", False))
        if (what, full) in seen:
            continue
        seen.add((what, full))
        tail = shown[-30:].lstrip()
        out.append(f"{phrase} is too long for its place on the invoice, even at half SQL's size, so its end is cut off "
                   f"(it prints up to \"...{tail}\")" + (f": shorten it {where.format(code=code)}." if where else "."))
    return out


def setup_cuts(con, ent):
    """In words, which of the company's print settings (its header, the bank details and the words under the
    signature) are too long to print in full on its invoices (empty when all fit), for the print settings."""
    e = dict(ent)
    company = dict(_company(con, ent), logo=None, signature=None)
    doc = {"kind": "customer", "title": "Invoice", "doc_no": "", "date": "", "account": "", "terms": "", "party_label": "To",
           "party": {"name": "", "address": [], "attn": "", "tin": None}, "buyer": None, "company": company,
           "pay_to": _pay_to(con, ent), "lines": [], "total_sen": 0, "currency": "MYR", "words": "", "einvoice": None}
    _pdf, pg = _draw(doc)
    return cut_notes([x for x in pg.cut if CUT_FIELDS.get(x[0], ("", "", False))[2]], e.get("code") or "")


# ---------- a month's invoices ----------

def month_documents(con, eid, month, kind):
    """The SQL documents of a month that have an invoice of this kind to print: [(sql_entries id, doc_no)], one per
    document number (the latest import's row), in date and number order."""
    if kind not in KINDS:
        raise InvoiceError("Choose customer invoices or self-billed e-Invoices.", 400)
    gone = "AND deleted_in_sql IS NULL" if "deleted_in_sql" in _cols(con, "sql_entries") else ""
    want = "kind = 'invoice'" if kind == "customer" else "COALESCE(kind, 'payment') = 'payment'"
    rows = con.execute(f"""SELECT * FROM sql_entries WHERE id IN (SELECT MAX(id) FROM sql_entries WHERE entity_id = ? AND {want}
                           AND substr(doc_date, 1, 7) = ? AND status <> 'ignored' {gone} GROUP BY UPPER(TRIM(doc_no)))
                           ORDER BY doc_date, doc_no""", (eid, month)).fetchall()
    return [(r["id"], r["doc_no"]) for r in rows if kind_of(con, r) == kind]


def print_months(con, eid):
    """{customer: [months with customer invoices], self_billed: [months with self-billed e-Invoices]}, newest first,
    for the SQL page's All invoices of a month."""
    out = {"customer": [r[0] for r in con.execute(
        """SELECT DISTINCT substr(doc_date, 1, 7) FROM sql_entries WHERE entity_id = ? AND kind = 'invoice' AND status <> 'ignored'
           AND (UPPER(COALESCE(doc_type, '')) = 'IV' OR (doc_type IS NULL AND direction = 'in')) ORDER BY 1 DESC""", (eid,))],
        "self_billed": []}
    if myinvois.ready(con):
        out["self_billed"] = [r[0] for r in con.execute(
            """SELECT DISTINCT substr(s.doc_date, 1, 7) FROM sql_entries s JOIN myinvois_docs m ON m.entity_id = s.entity_id
               AND m.direction = 'self_billed' AND (m.entry_id = s.id OR m.uuid = s.einvoice)
               WHERE s.entity_id = ? AND COALESCE(s.kind, 'payment') = 'payment' AND s.status <> 'ignored' ORDER BY 1 DESC""", (eid,))]
    return out


def month_zip(con, ent, month, kind):
    """A zip of every invoice of the kind in the month, with a list of those that couldn't be printed and why, and of
    those printed with a line too long for its place (its end cut off). Returns (bytes, printed, [(doc no, reason)])."""
    docs = month_documents(con, ent["id"], month, kind)
    if not docs:
        what = "customer invoices" if kind == "customer" else "payment vouchers with a self-billed e-Invoice"
        raise InvoiceError(f"{ent['code']} has no {what} in {db.month_label(month)} in the SQL documents fetched.", 404)
    buf, printed, skipped, names, short = io.BytesIO(), 0, [], set(), []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for sid, doc_no in docs:
            try:
                doc = document(con, sid)
            except InvoiceError as x:
                skipped.append((doc_no, str(x)))
                continue
            name, n = file_name(doc), 2
            while name.lower() in names:
                name = file_name(doc)[:-4] + f" ({n}).pdf"
                n += 1
            names.add(name.lower())
            cuts = []
            z.writestr(name, render(doc, cut=cuts))
            short += [(doc_no, n) for n in cut_notes(cuts, ent["code"])]
            printed += 1
        if skipped:
            z.writestr("Not printed.txt", "These documents were not printed:\r\n\r\n"
                       + "\r\n".join(f"{no}: {why}" for no, why in skipped) + "\r\n")
        if short:
            z.writestr("Text cut short.txt", "These invoices were printed with a line too long for its place, its end cut off:"
                       "\r\n\r\n" + "\r\n".join(f"{no}: {why}" for no, why in short) + "\r\n")
    return buf.getvalue(), printed, skipped
