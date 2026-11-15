"""Prints SQL Account's customer invoices and self-billed e-Invoices as PDF files, laid out as SQL Account prints its
invoice: the company's header (logo, name, registration and tax numbers, address, phone, email and website), the title,
who it is to with the document number, date, account and terms, the account lines, the total in words, where to pay,
the signature, and for an e-Invoice validated by LHDN its QR code at the bottom right.

hr-payments mirrors SQL Account (read-only for now), so nothing on an invoice is typed in for it: the document comes
from SQL's listing, its lines from SQL's GL Journal of Transaction (ledger), the e-Invoice from the copy of SQL's
MyInvois Transaction screen (myinvois), and the header and footer from Setup (the company, the bank account chosen for
invoices, the customer or supplier). A setting missing is named in words and the invoice still prints what it has.

All amounts are whole sen (integers), so totals compare exactly.
"""
import hashlib
import io
import os
import re
import stat
import zipfile
from datetime import date, datetime

import segno
from fpdf import FPDF
from PIL import Image

from . import db, ledger, myinvois
from .config import DATA_DIR
from .docstore import safe

ASSETS_DIR = DATA_DIR / "company-assets"
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
            "contact": "  |  ".join(contact), "logo": image_path(e, "logo"), "signature": image_path(e, "signature"),
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


# ---------- the PDF ----------

PAGE_W = 210
L, R = 8, 202            # the left and right edges of what is printed (mm)
CODE_X, DESC_X, DIV1, DIV2 = L, 34, 32.5, 170  # the table's columns and the rules between its headings
TOP_RULE, HEAD_RULE = 68, 73
ROW = 4.2
LINES_END = 212          # the lines stop above the total's rule
FOOT_RULE = 215.5
QR_SIZE = 21


def _latin(s):
    return str(s or "").encode("latin-1", "replace").decode("latin-1")


def _fit(pdf, text, width):
    """text cut to fit width at the current font."""
    text = _latin(text)
    while text and pdf.get_string_width(text) > width:
        text = text[:-1]
    return text


def _image(pdf, path, x, y, w, h, align_bottom=False):
    """The image scaled to fit in the box, at its left (and top, or bottom), keeping its shape."""
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    pdf.image(str(path), x=x, y=y + (h - dh if align_bottom else 0), w=dw, h=dh)


def _party_block(doc):
    """The lines of who the invoice is to, at the left of the header, as [(y, text, right edge)], and where the last
    one ends (mm from the top): the name and address, a supplier's TIN, then Attn and the Buyer a little lower."""
    p, y, out = doc["party"], 37.8, []
    for text in [p["name"], *p["address"]][:6]:
        out.append((y, text, 125))
        y += 4
    if p.get("tin") and doc["kind"] == "self_billed":
        out.append((y, f"TIN : {p['tin']}", 125))
        y += 4
    y = max(y + 4.2, 58.5)
    if p.get("attn"):
        out.append((y, f"Attn : {p['attn']}", 125))
        y += 4
    if doc.get("buyer"):
        out.append((y, f"Buyer : {doc['buyer']}", R))
    return out, max(oy + 4 for oy, _, _ in out)


def _table_top(doc):
    """Where the table's top rule goes: as SQL prints it (68 mm), or lower when the block at the left runs further (a
    supplier with four address lines, its TIN, Attn and the Buyer), so no line of it is printed over the headings."""
    return max(TOP_RULE, round(_party_block(doc)[1] + 1.5, 1))


def _header(pdf, doc):
    c = doc["company"]
    centre = 119 if c["logo"] else PAGE_W / 2
    half = min(centre - 31 if c["logo"] else 95, R + 4 - centre)
    if c["logo"]:
        _image(pdf, c["logo"], 10, 6.5, 21, 26)
    size = 19.5
    pdf.set_font("Times", "B", size)
    while size > 10 and pdf.get_string_width(_latin(c["name"])) > 2 * half:
        size -= 0.5
        pdf.set_font("Times", "B", size)
    pdf.set_xy(centre - half, 6.2)
    pdf.cell(2 * half, 6.8, _fit(pdf, c["name"], 2 * half), align="C")
    pdf.set_font("Times", "", 8)
    y = 12.9
    for text in (c["reg_line"], c["address"], c["contact"]):
        if not text:
            continue
        for part in pdf.multi_cell(2 * half, 3.3, _latin(text), dry_run=True, output="LINES")[:2]:
            pdf.set_xy(centre - half, y)
            pdf.cell(2 * half, 3.3, part, align="C")
            y += 3.3
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_xy(L, 32.5)
    pdf.cell(R - L, 5, _latin(doc["title"]), align="C")
    # Who it is to, at the left
    pdf.set_font("Helvetica", "", 9.5)
    label_w = pdf.get_string_width(_latin(doc["party_label"])) + 2 * pdf.c_margin
    colon = max(12.0, L - 1 + label_w + 1.5)
    pdf.set_xy(L - 1, 37.8)
    pdf.cell(label_w, 4, _latin(doc["party_label"]))
    pdf.set_xy(colon, 37.8)
    pdf.cell(3, 4, ":")
    x = colon + 4
    for y, text, right in _party_block(doc)[0]:
        pdf.set_xy(x, y)
        pdf.cell(right - x, 4, _fit(pdf, text, right - x))
    # The document's number, date, account and terms, at the right
    rows = [("Doc No.", doc["doc_no"], True), ("Date", doc["date"], False), ("Account", doc["account"], False),
            ("Terms", doc["terms"], False)]
    y = 37.8
    for label, value, bold in rows:
        pdf.set_font("Helvetica", "B" if bold else "", 9.5)
        pdf.set_xy(130, y)
        pdf.cell(33.5, 5, _latin(label), align="R")
        pdf.set_xy(163.8, y)
        pdf.cell(4, 5, ":")
        pdf.set_xy(170, y)
        pdf.cell(R - 170 + 2, 5, _fit(pdf, value, R - 170 + 2))
        y += 5.1
    # The table's headings, lower down when the block at the left needs the room
    top = _table_top(doc)
    head = top + HEAD_RULE - TOP_RULE
    pdf.set_draw_color(0)
    pdf.set_line_width(0.45)
    pdf.line(L, top, R + 2, top)
    pdf.set_line_width(0.3)
    pdf.line(L, head, R + 2, head)
    pdf.line(DIV1, top, DIV1, head)
    pdf.line(DIV2, top, DIV2, head)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_xy(L, top + 0.3)
    pdf.cell(DIV1 - L, head - top - 0.3, "G/L CODE")
    pdf.set_xy(DIV1, top + 0.3)
    pdf.cell(DIV2 - DIV1, head - top - 0.3, "DESCRIPTION", align="C")
    pdf.set_xy(DIV2, top + 0.3)
    pdf.cell(R + 2 - DIV2, head - top - 0.3, _latin(f"Amount({doc['currency']})"), align="R")


def _rows(pdf, doc):
    """Each line as (code, [description lines], amount), its description wrapped to the column."""
    pdf.set_font("Helvetica", "", 8.5)
    out = []
    for x in doc["lines"]:
        parts = pdf.multi_cell(DIV2 - DESC_X - 2, ROW, _latin(x["description"]), dry_run=True, output="LINES") or [""]
        out.append((x["code"], parts, money(x["sen"])))
    return out


def _pages(rows, start=HEAD_RULE + 1.2):
    """The rows put on pages, each page's rows from start down to LINES_END. A row is kept whole on the next page when
    it doesn't fit under the rows above it; a row longer than a whole page (a very long description) is split, its code
    and amount on its first part and the rest of its description carried on to the next page."""
    room_of = lambda y: int((LINES_END - y) / ROW + 1e-9)
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


def _draw_rows(pdf, page, start=HEAD_RULE + 1.2):
    pdf.set_font("Helvetica", "", 8.5)
    y = start
    for code, parts, amount in page:
        pdf.set_xy(CODE_X, y)
        pdf.cell(DESC_X - CODE_X - 1, ROW, _fit(pdf, code, DESC_X - CODE_X - 1))
        for i, part in enumerate(parts):
            pdf.set_xy(DESC_X, y + i * ROW)
            pdf.cell(DIV2 - DESC_X - 2, ROW, part)
        pdf.set_xy(DIV2, y)
        pdf.cell(R + 2 - DIV2, ROW, amount, align="R")
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


def _footer(pdf, doc):
    pdf.set_line_width(0.45)
    pdf.line(L, FOOT_RULE, R + 2, FOOT_RULE)
    pdf.set_font("Helvetica", "", 9.5)
    # The amount in words, wrapped under itself when it is too long for one line (a large amount with cents)
    head, _, words = doc["words"].partition(" : ")
    head = _latin(f"{head} : ") if words else ""
    hw = pdf.get_string_width(head)
    parts = pdf.multi_cell(140 - hw, 4.4, _latin(words or doc["words"]), dry_run=True, output="LINES")[:3] or [""]
    pdf.set_xy(L, FOOT_RULE + 0.6)
    pdf.cell(hw, 4.4, head)
    for n, part in enumerate(parts):
        pdf.set_xy(L + hw, FOOT_RULE + 0.6 + n * 4.4)
        pdf.cell(140 - hw, 4.4, part)
    extra = (len(parts) - 1) * 4.4
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_xy(150, FOOT_RULE + 0.6)
    pdf.cell(16, 4.4, "Total :", align="R")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_xy(170, FOOT_RULE + 0.6)
    pdf.cell(R + 2 - 170, 4.4, money(doc["total_sen"]), align="R")
    c, pay = doc["company"], doc["pay_to"]
    if pay:
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_xy(L, 224 + extra)
        pdf.cell(100, 4.4, "All payments to be made to :")
        pdf.set_font("Helvetica", "B", 6.5)
        pdf.set_xy(L, 228.6 + extra)
        pdf.cell(100, 3.3, _fit(pdf, pay["name"], 100))
        y = 231.9 + extra
        for label, value in (("Bank", pay["bank"]), ("Bank Address", pay["bank_address"]), ("Account No", pay["account_no"]),
                             ("Bank Transfer Code", pay["swift"])):
            pdf.set_font("Helvetica", "", 6.5)
            pdf.set_text_color(70)
            pdf.set_xy(L, y)
            text = f"{label} : "
            w = pdf.get_string_width(text)
            pdf.cell(w, 3.3, text)
            pdf.set_text_color(0)
            pdf.set_font("Helvetica", "B", 6.5)
            pdf.cell(100 - w, 3.3, _fit(pdf, value, 100 - w))
            y += 3.35
    if c["signature"]:
        _image(pdf, c["signature"], 10, 254, 52, 17, align_bottom=True)
    pdf.set_line_width(0.4)
    pdf.line(L + 0.5, 276.4, 72, 276.4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_xy(L, 276.9)
    pdf.cell(110, 4.4, _fit(pdf, c["sign_label"], 110))
    e = doc["einvoice"]
    if e:
        qx, qy = R + 1 - QR_SIZE, 247.5
        y = 269.2
        pdf.set_font("Helvetica", "", 5.5)
        if e["state"] == "valid":
            # the lines under it start four squares below it, leaving the QR code its margin of blank paper
            y = max(y, qy + QR_SIZE + 4 * _qr(pdf, e["link"], qx, qy, QR_SIZE) + 0.1)
            lines = [f"e-Invoice UUID: {e['uuid']}"] + ([f"Validated on {e['validated_on']}"] if e["validated_on"] else [])
        elif e["state"] == "cancelled":
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(170, 0, 0)
            pdf.set_xy(120, 258)
            pdf.cell(R + 2 - 120, 5, "e-Invoice cancelled", align="R")
            pdf.set_text_color(0)
            pdf.set_font("Helvetica", "", 5.5)
            lines = [f"e-Invoice UUID: {e['uuid']}", "Cancelled on MyInvois: this e-Invoice is no longer valid."]
        elif e["state"] == "no_link":
            lines = [f"e-Invoice UUID: {e['uuid']}"] + ([f"Validated on {e['validated_on']}"] if e["validated_on"] else []) + [
                "QR code not printed: MyInvois's Long ID for it wasn't read."]
        else:
            lines = [f"e-Invoice UUID: {e['uuid']}", f"Not validated on MyInvois ({e['status'] or 'no status'}): no QR code."]
        for text in lines:
            pdf.set_xy(110, y)
            pdf.cell(R + 2 - 110, 2.4, _latin(text), align="R")
            y += 2.4


def render(doc):
    """The invoice as PDF bytes: A4 portrait, laid out as SQL Account prints its invoice. Lines that don't fit go on to
    another page with the header again; the total, payment details, signature and QR code are on the last page."""
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(L, 6, PAGE_W - R)
    pdf.set_title(_latin(f"{doc['title']} {doc['doc_no']}"))
    pdf.set_author(_latin(doc["company"]["name"]))
    pdf.set_creator("HR Payments")
    pdf.add_page()  # first: wrapping the descriptions needs a page
    start = _table_top(doc) + HEAD_RULE - TOP_RULE + 1.2
    pages = _pages(_rows(pdf, doc), start)
    for n, page in enumerate(pages, 1):
        if n > 1:
            pdf.add_page()
        _header(pdf, doc)
        _draw_rows(pdf, page, start)
        if n == len(pages):
            _footer(pdf, doc)
        else:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_xy(110, FOOT_RULE)
            pdf.cell(R + 2 - 110, 4.4, f"Continued on page {n + 1} of {len(pages)}", align="R")
        if len(pages) > 1:
            pdf.set_font("Helvetica", "", 7)
            pdf.set_xy(110, 286)
            pdf.cell(R + 2 - 110, 3, f"Page {n} of {len(pages)}", align="R")
    return bytes(pdf.output())


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
    """A zip of every invoice of the kind in the month, with a list of those that couldn't be printed and why.
    Returns (bytes, printed, [(doc no, reason)])."""
    docs = month_documents(con, ent["id"], month, kind)
    if not docs:
        what = "customer invoices" if kind == "customer" else "payment vouchers with a self-billed e-Invoice"
        raise InvoiceError(f"{ent['code']} has no {what} in {db.month_label(month)} in the SQL documents fetched.", 404)
    buf, printed, skipped, names = io.BytesIO(), 0, [], set()
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
            z.writestr(name, render(doc))
            printed += 1
        if skipped:
            z.writestr("Not printed.txt", "These documents were not printed:\r\n\r\n"
                       + "\r\n".join(f"{no}: {why}" for no, why in skipped) + "\r\n")
    return buf.getvalue(), printed, skipped
