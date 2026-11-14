"""Reads listings exported from SQL Account (Excel, CSV or ODS) and matches each entry to a payment.

SQL Account's report layouts vary, so columns are detected from the header row and can be corrected on screen.
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

from . import sqlreport

FIELDS = {
    "doc_no": ("doc no", "docno", "document no", "doc. no", "pv no", "voucher no", "ref", "reference", "no."),
    "date": ("doc date", "docdate", "date", "posting date", "trans date"),
    "description": ("description", "particulars", "remark", "narration", "description 1"),
    "payee": ("payee", "pay to", "paid to", "company name", "companyname", "name", "account name", "code"),
    "amount": ("amount", "local amount", "doc amount", "total", "net amount", "localamount", "docamt"),
    "debit": ("debit", "dr", "local dr"),
    "credit": ("credit", "cr", "local cr"),
    "einvoice": ("e-invoice uuid", "irbm uuid", "uuid"),
    "doc_type": ("doc type", "doctype", "type"),
    "einvoice_status": ("e-invoice status",),
    "einvoice_link": ("e-invoice link", "irbm validationlink"),
}
# Columns kept from update 22 when a listing has them, found on the heading row once the columns above are (so the
# heading row and the columns above are chosen exactly as before). A "Code" heading may also be the payee's.
EXTRA_FIELDS = {
    "code": ("sql code", "code", "account code", "creditor code", "debtor code", "customer code", "supplier code"),
    "payment_method": ("payment method", "paymentmethoddesc", "payment method desc"),
    "cheque_no": ("cheque no", "cheque no.", "chequenumber", "cheque number", "chq no", "chq no."),
    "dockey": ("doc key", "dockey"),
    "currency_code": ("currency", "currencycode", "currency code"),
}
ALL_FIELDS = list(FIELDS) + list(EXTRA_FIELDS)

# SQL document types and what they mean here
MONEY_IN = {"OR", "RV", "CS"}          # official receipt / receipt voucher / cash sale
MONEY_OUT = {"PV", "SP", "PM"}         # payment voucher / supplier payment
JOURNAL = {"JV", "JE"}
SALES_DOCS = {"IV", "DN", "CN", "CF"}  # customer invoice, debit note, credit note, refund
PURCHASE_DOCS = {"PI", "SD", "SC"}     # supplier invoice, debit note, credit note


class SqlImportError(ValueError):
    pass


# ---------- reading ----------

def read_rows(filename, data):
    name = filename.lower()
    if data.lstrip()[:200].lstrip(b"\xef\xbb\xbf").startswith((b"<?xml", b"<DATAPACKET")) and b"<DATAPACKET" in data[:500]:
        return _read_datapacket(data)
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        printed = report_rows(data)  # a listing exported with SQL Account's print button: a printed page, not a table
        if printed:
            return printed
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        except Exception:
            # SQL Account writes workbooks openpyxl refuses (a WindowWidth attribute): read the sheet's own XML
            try:
                return sqlreport.read_xlsx(data)[0]
            except Exception:
                pass
            raise
    if name.endswith(".xls"):
        import xlrd
        book = xlrd.open_workbook(file_contents=data)
        sh = book.sheet_by_index(0)
        out = []
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                else:
                    row.append(cell.value)
            out.append(row)
        return out
    if name.endswith(".csv") or name.endswith(".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        # Rows copied from an SQL Account grid arrive tab-separated.
        delim = "\t" if "\t" in text[:2000] else ","
        return [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    if name.endswith(".ods"):
        return _read_ods(data)
    raise SqlImportError("Export the SQL report as Excel (.xlsx or .xls), CSV or ODS.")


DATAPACKET_COLUMNS = ["Doc No", "Doc Type", "Doc Date", "Description", "Company Name", "DR", "CR", "Amount",
                      "Cheque No", "e-Invoice UUID", "e-Invoice status", "e-Invoice link",
                      "SQL code", "Payment method", "Doc key", "Currency"]


def listing_rows(entries):
    """Documents read from exported listings ({doc_no, doc_type, date, description, amount, cheque_no, payee, code}), as
    rows under the headings a pasted listing gets, so both are matched the same way."""
    blank = [""] * len(DATAPACKET_COLUMNS)
    at = {name: i for i, name in enumerate(DATAPACKET_COLUMNS)}
    rows = [list(DATAPACKET_COLUMNS)]
    for e in entries:
        row = list(blank)
        row[at["Doc No"]], row[at["Doc Type"]], row[at["Doc Date"]] = e["doc_no"], e["doc_type"], e["date"]
        row[at["Description"]], row[at["Amount"]], row[at["Cheque No"]] = e["description"], f"{e['amount']:.2f}", e["cheque_no"]
        row[at["Company Name"]], row[at["SQL code"]] = e.get("payee", ""), e.get("code", "")
        rows.append(row)
    return rows


def report_rows(data):
    """The rows of a listing exported from SQL Account's print button, or None when the file is any other workbook.
    Every entry carries the document type its listing gives it (a payment voucher may be numbered CLAIMS_NOV26)."""
    try:
        rep = sqlreport.parse(data)
    except sqlreport.ReportError as ex:
        raise SqlImportError(str(ex))
    return listing_rows(rep["entries"]) if rep else None


def _first(a, *keys):
    for k in keys:
        v = (a.get(k) or "").strip()
        if v:
            return v
    return ""


def _doc_type_from(a, doc_no):
    """Listings without a DOCTYPE field. Customer invoice numbers can be free-form (ABC/2026/10/001), but the
    account code tells them apart: customers are 3xx-xxxx and suppliers 4xx-xxxx in SQL Account's chart."""
    prefix = re.match(r"[A-Za-z]*", doc_no).group(0).upper()
    if prefix in MONEY_IN | MONEY_OUT | JOURNAL | SALES_DOCS | PURCHASE_DOCS:
        return prefix
    code = _first(a, "CODE")
    if code.startswith("3"):
        return "IV"
    if code.startswith("4"):
        return "PI"
    return prefix


def _amount(a):
    """Document total. Vouchers and invoices call it DOCAMT; the Journal listing calls it TOTALDR (= TOTALCR)."""
    v = _first(a, "LOCALDOCAMT", "DOCAMT", "LOCALAMOUNT", "AMOUNT", "LOCALTOTALDR", "TOTALDR", "TOTALDRWITHTAX")
    if v:
        return v
    # A listing not seen yet: take the first field that looks like a total
    for k, val in a.items():
        if (k.endswith("AMT") or k.startswith("TOTAL")) and (val or "").strip():
            return val.strip()
    return ""


def _read_datapacket(data):
    """SQL Account copies grid rows to the clipboard as a Delphi DATAPACKET (XML): one <ROW> per document.

    The same format comes from every listing (cash book, payment and receipt vouchers, journals, customer invoices);
    only the attributes present differ, so each column falls back through the names those listings use.
    """
    root = ET.fromstring(data.decode("utf-8-sig", errors="replace").strip().encode("utf-8"))
    rows = [DATAPACKET_COLUMNS]
    for r in root.iter("ROW"):
        a = dict(r.attrib)
        if a.get("CANCELLED", "").upper() == "TRUE":
            continue
        doc_no = _first(a, "DOCNO")
        desc = _first(a, "DESCRIPTION", "DESCRIPTION1")
        d2 = _first(a, "DESCRIPTION2")
        if d2 and d2.lower() not in ("payment for account", ".", "-"):
            desc = f"{desc} - {d2}" if desc else d2
        uuid = _first(a, "IRBM_UUID")
        # In the listings seen so far, IRBM_STATUS 2 plus a validated time means LHDN accepted the e-Invoice.
        if a.get("EIV_VALIDATED_UTC") or a.get("IRBM_STATUS") == "2":
            status = "Validated"
        elif a.get("EIV_UTC") or a.get("IRBM_STATUS") == "1":
            status = "Submitted, not validated"
        else:
            status = "UUID recorded" if uuid else ""
        rows.append([doc_no, _first(a, "DOCTYPE") or _doc_type_from(a, doc_no),
                     _first(a, "DOCDATE", "POSTDATE"), desc, _first(a, "COMPANYNAME", "COMPANY", "CODE"),
                     _first(a, "LOCALDR", "DR"), _first(a, "LOCALCR", "CR"),
                     _amount(a),
                     _first(a, "CHEQUENUMBER"), uuid, status, _first(a, "IRBM_VALIDATIONLINK"),
                     _first(a, "CODE"), _first(a, "PAYMENTMETHODDESC"), _first(a, "DOCKEY"), _first(a, "CURRENCYCODE")])
    return rows


def journal_lines(data):
    """The lines of a journal copied from SQL Account's journal detail grid, or None when the data is anything else.

    Expanding a journal in SQL and copying its detail grid gives a DATAPACKET of its own whose rows have a DTLKEY and the
    DOCKEY of the journal (the document key its header row carries too), the account CODE and DR and CR, but no DOCNO.
    Returns [{dockey, dtlkey, seq, code, description, project, dr, cr}], the amounts in the company's currency (LOCALDR
    and LOCALCR, else DR and CR). A listing of documents, which has a DOCNO on every row, is never read as lines."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if b"<DATAPACKET" not in data[:500]:
        return None
    try:
        root = ET.fromstring(data.decode("utf-8-sig", errors="replace").strip().encode("utf-8"))
    except ET.ParseError:
        return None
    out = []
    for r in root.iter("ROW"):
        a = dict(r.attrib)
        if _first(a, "DOCNO") or not (_first(a, "DTLKEY") and _first(a, "DOCKEY") and _first(a, "CODE")):
            return None
        seq = _first(a, "SEQ")
        out.append({"dockey": _first(a, "DOCKEY"), "dtlkey": _first(a, "DTLKEY"), "seq": int(seq) if seq.isdigit() else None,
                    "code": _first(a, "CODE").upper(), "description": _first(a, "DESCRIPTION", "DESCRIPTION2"),
                    "project": _first(a, "PROJECT"), "dr": to_amount(_first(a, "LOCALDR", "DR")) or 0.0,
                    "cr": to_amount(_first(a, "LOCALCR", "CR")) or 0.0})
    return out or None


ACCOUNT_HEADINGS = ("account", "account code", "gl code", "code", "acc code", "account no")
DOC_NO_HEADINGS = ("doc no", "docno", "document no", "doc. no", "doc number", "document number", "voucher no")


def text_journal_lines(data):
    """The lines of a journal copied as plain text from SQL Account's expanded journal, or None when the text is anything else.

    The text is tab-separated with a heading row that has an account column (Account, Account Code, GL Code or Code) and
    debit and credit columns, and no document number column: it carries no document key, so the caller must be told
    which journal the lines belong to. The local amounts (Local DR, Local CR) are preferred to DR and CR, and the tax
    columns (DR (Tax)) are used only when nothing else is there. Returns [{dockey: None, dtlkey: None, seq, code,
    description, project, dr, cr}] in the order pasted, blank rows left out."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    # A file that isn't text (an Excel .xlsx is a zip, starting PK) is never pasted lines, whatever bytes it holds
    if data[:2] == b"PK" or b"\x00" in data[:4096]:
        return None
    text = data.decode("utf-8-sig", errors="replace")
    if "	" not in text[:3000] or "<DATAPACKET" in text[:500]:
        return None
    try:
        rows = [r for r in csv.reader(io.StringIO(text), delimiter="	", quoting=csv.QUOTE_NONE)]
    except csv.Error:  # not tab-separated text after all
        return None
    for h, row in enumerate(rows[:10]):
        names = [_norm(x) for x in row]
        if any(n in DOC_NO_HEADINGS for n in names):
            return None
        acct = next((i for i, n in enumerate(names) if n in ACCOUNT_HEADINGS), None)
        if acct is None:
            continue

        def pick(*wanted):
            return next((i for w in wanted for i, n in enumerate(names) if n == w), None)
        dr, cr = pick("local dr", "dr", "debit"), pick("local cr", "cr", "credit")
        if dr is None or cr is None:
            dr, cr = pick("local dr (tax)", "dr (tax)"), pick("local cr (tax)", "cr (tax)")
        if dr is None or cr is None:
            continue
        desc, proj = pick("description", "desc"), pick("project")

        def cell(r, i):
            return (r[i] if i is not None and i < len(r) else "").strip()
        out = []
        for r in rows[h + 1:]:
            code = cell(r, acct).upper()
            if not code and not (cell(r, dr) or cell(r, cr)):
                continue
            if not code:
                return None
            out.append({"dockey": None, "dtlkey": None, "seq": len(out) + 1, "code": code, "description": cell(r, desc),
                        "project": cell(r, proj), "dr": to_amount(cell(r, dr)) or 0.0, "cr": to_amount(cell(r, cr)) or 0.0})
        return out or None
    return None


def _read_ods(data):
    T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
    TX = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("content.xml"))
    sheet = next(root.iter(T + "table"))
    rows = []
    for row in sheet.iter(T + "table-row"):
        cells = []
        for c in row:
            if c.tag not in (T + "table-cell", T + "covered-table-cell"):
                continue
            rep = min(int(c.get(T + "number-columns-repeated", "1")), 60)
            vt = c.get(O + "value-type")
            if vt in ("float", "currency", "percentage"):
                v = float(c.get(O + "value"))
            elif vt == "date":
                v = c.get(O + "date-value")
            else:
                v = " ".join("".join(p.itertext()) for p in c.iter(TX + "p")) or None
            cells.extend([v] * rep)
        while cells and cells[-1] in (None, ""):
            cells.pop()
        rows.append(cells)
        if len(rows) > 5000:
            break
    return rows


# ---------- interpreting ----------

def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower().replace("_", " "))


def guess_header(rows):
    """The header is the first row (within the top 30) naming at least two known columns."""
    best = (None, {})
    for i, row in enumerate(rows[:30]):
        mapping = {}
        for col, cell in enumerate(row):
            n = _norm(cell)
            if not n:
                continue
            for field, names in FIELDS.items():
                if field not in mapping and n in names:
                    mapping[field] = col
                    break
        if len(mapping) >= 2 and len(mapping) > len(best[1]):
            best = (i, mapping)
        if len(mapping) >= 4:
            break
    if best[0] is None:
        mapping = infer_columns(rows)
        if mapping:
            return -1, mapping  # no heading row: data starts at the first row
        raise SqlImportError("Couldn't find the column headings. The export needs a heading row such as Doc No, Date, Description, Amount.")
    return best[0], extra_columns(rows[best[0]], best[1])


def extra_columns(header, mapping):
    """The mapping with the columns kept from update 22 (EXTRA_FIELDS) added from the heading row, the others as they were."""
    out = dict(mapping)
    used = set(mapping.values())
    for col, cell in enumerate(header):
        n = _norm(cell)
        for field, names in EXTRA_FIELDS.items():
            if field not in out and n in names and (col not in used or (field == "code" and n == "code")):
                out[field] = col
                break
    return out


DOC_NO = re.compile(r"^[A-Z]{2,4}[-/]?\d{2,}[-/]?\d*$")
DECIMAL = re.compile(r"^\(?-?[\d,]*\.\d{2}\)?$")


def infer_columns(rows):
    """Works out the columns from their contents, for rows pasted without the heading row."""
    data = [r for r in rows if sum(1 for c in r if str(c or "").strip()) >= 3][:200]
    if not data:
        return None
    width = max(len(r) for r in data)

    def share(col, test):
        vals = [str(r[col]).strip() for r in data if col < len(r) and str(r[col] or "").strip()]
        return (sum(1 for v in vals if test(v)) / len(vals)) if vals else 0, vals

    mapping, decimals, texts = {}, [], []
    for col in range(width):
        s_doc, vals = share(col, lambda v: bool(DOC_NO.match(v.upper())))
        s_date, _ = share(col, lambda v: to_date(v) is not None)
        s_dec, _ = share(col, lambda v: bool(DECIMAL.match(v)))
        if s_doc > 0.8 and "doc_no" not in mapping:
            mapping["doc_no"] = col
        elif s_date > 0.8:
            mapping.setdefault("date", col)  # the first date column is the document date
        elif s_dec > 0.8:
            decimals.append(col)
        elif vals:
            texts.append((sum(len(v) for v in vals) / len(vals), col))
    if len(decimals) >= 2:
        mapping["debit"], mapping["credit"] = decimals[-2], decimals[-1]
    elif decimals:
        mapping["amount"] = decimals[0]
    if texts:
        mapping["description"] = max(texts)[1]
    return mapping if {"doc_no", "date"} <= mapping.keys() and decimals else None


def to_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip().split("T")[0]
    if re.match(r"^\S+ \d{1,2}:\d{2}", s):  # "12/09/2026 00:00:00"
        s = s.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def to_amount(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("RM", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def records(rows, header_row, mapping):
    out = []
    for i, row in enumerate(rows[header_row + 1:], start=header_row + 2):
        get = lambda f: row[mapping[f]] if f in mapping and mapping[f] is not None and mapping[f] < len(row) else None
        doc_no = str(get("doc_no") or "").strip()
        doc_type = (str(get("doc_type") or "").strip() or re.match(r"[A-Za-z]*", doc_no).group(0)).upper()
        # Cash book: DR = money into the bank (OR), CR = money paid out (PV). Other listings only carry an amount.
        dr, cr = to_amount(get("debit")), to_amount(get("credit"))
        direction = None
        if dr or cr:
            amount, direction = (dr, "in") if dr else (cr, "out")
        else:
            amount = to_amount(get("amount"))
            if amount is None and (dr is not None or cr is not None):
                amount = 0.0
        if doc_type in MONEY_IN:
            direction = "in"
        elif doc_type in MONEY_OUT:
            direction = "out"
        kind = "journal" if doc_type in JOURNAL else "invoice" if doc_type in SALES_DOCS | PURCHASE_DOCS else "payment"
        d = to_date(get("date"))
        if not doc_no or amount is None or not d:
            continue  # sub-totals, blank lines, report footers
        if doc_no.lower().startswith(("total", "grand")):
            continue
        out.append({"row": i, "doc_no": doc_no, "date": d, "description": str(get("description") or "").strip(),
                    "payee": str(get("payee") or "").strip(), "amount": round(abs(amount), 2), "direction": direction,
                    "einvoice": str(get("einvoice") or "").strip(), "doc_type": doc_type, "kind": kind,
                    "einvoice_status": str(get("einvoice_status") or "").strip(),
                    "einvoice_link": str(get("einvoice_link") or "").strip(),
                    **{f: _text(get(f), upper=f in ("code", "currency_code")) for f in EXTRA_FIELDS}})
    if not out:
        raise SqlImportError("No entries were found under the heading row. Check that Doc No, Date and Amount point to the right columns.")
    return out


def _text(v, upper=False):
    """A cell as text: a whole number read from a spreadsheet as 123.0 becomes 123."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    v = str(v if v is not None else "").strip()
    return v.upper() if upper else v


# ---------- matching ----------

# Words that say nothing about who was paid: months, years and accounting terms. "AUG" in a claim and in an
# electricity bill must not make them look alike.
NOISE = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "SEPT", "OCT", "NOV", "DEC",
         "PAYMENT", "SALARY", "FEE", "FOR", "THE", "AND", "SDN", "BHD", "LTD", "MONTH", "CLAIM", "CLAIMS",
         "EXPENSES", "EXPENSE", "CONTRIBUTION", "CHARGE", "CHARGES", "RENTAL", "DEDUCTION", "ACCOUNT",
         "SUBSCRIPTION", "INVOICE", "PLAN", "PRO", "ADVANCE", "AUDIT", "BILL", "FROM", "WITH"}


def _words(s):
    return {w for w in re.findall(r"[A-Z]{3,}", (s or "").upper()) if w not in NOISE}


# Words an estimated salary or director payment's SQL vouchers must hold (until update 21; Setup's from then on).
CATEGORY_HINTS = {"salary": ("SALARY", "GAJI", "WAGES", "PAYROLL"),
                  "director": ("DIRECTOR", "ALLOWANCE", "ALL'CE", "SALARY")}


def refs_of(text):
    """The voucher numbers in a payment's SQL ref box, e.g. "PV2601-003, PV2601-007"."""
    return [x for x in re.split(r"[,;\s]+", (text or "").upper()) if x]


def linked_vouchers(con, entity_id):
    """Voucher numbers already linked to a payment, with the payment and the amount linked."""
    return {r["doc_no"].upper(): r for r in con.execute(
        """SELECT s.doc_no, s.amount, p.id AS payment_id, p.description FROM sql_entries s JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = ? ORDER BY s.id""", (entity_id,))}


# Whole words only (not CONTRACTOR, or REVERSE CHARGE, the service tax on imported services). A refund or replacement
# isn't one by its words: a supplier's refund of an overpaid PV, or a new cheque for a stale one, names the voucher too
# and is money that moved. One made only in the books comes as a receipt and a payment on the same day.
CORRECTION_WORDS = re.compile(r"\b(REVERS(E|ED|AL|ING)\b(?!\W+CHARGE)|CONTRA\b)", re.I)


def corrections(con, entity_id):
    """Ids of the vouchers not linked yet that look like corrections made only in the books, where no money moved: a
    reversal or contra by its description, or one of a receipt and a payment for the same amount on the same day
    (an OR refunding a duplicated self-billed e-Invoice, a second PV replacing the first). An entry with no direction
    (neither a receipt nor a payment) is never one of a pair."""
    entries = con.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND COALESCE(kind, 'payment') = 'payment'",
                          (entity_id,)).fetchall()
    sides = {(s["doc_date"], s["amount"], s["direction"]) for s in entries}
    other = {"in": "out", "out": "in"}
    return {s["id"] for s in entries if s["status"] == "unlinked" and (
        CORRECTION_WORDS.search(s["description"] or "")
        or (s["direction"] in other and (s["doc_date"], s["amount"], other[s["direction"]]) in sides))}


def payments_by_ref(con, entity_id):
    """Payments whose SQL ref box names a voucher that isn't linked yet (typed by hand), by voucher number.
    A number already linked is left out: a new row with it is that voucher changed in SQL, for a person to check."""
    linked, out = linked_vouchers(con, entity_id), {}
    for p in con.execute("SELECT id, description, sql_ref FROM payments WHERE entity_id = ? AND sql_ref IS NOT NULL ORDER BY id",
                         (entity_id,)):
        for ref in refs_of(p["sql_ref"]):
            if ref not in linked:
                out.setdefault(ref, p)
    return out


def receipt_invoice(r):
    """True for a customer invoice (IV): the sales invoice for money to be received, which can be linked to a receipt."""
    return r["kind"] == "invoice" and r["doc_type"] == "IV"


def _propose_receipts(con, entity_id, recs):
    """Suggest the money-in payment each customer invoice (IV) is for: a payment made from a Money in payee, with the same
    payee words (the payee's match words and name against the invoice's description and name; the payment's own description
    isn't used, as words like Rent would fit any customer) and exactly the amount, in the
    month the invoice belongs to (db.filing_month), else the nearest due date within 45 days. Each payment takes one
    invoice. An invoice already linked to a payment (as imported before) is left alone."""
    from . import partybook
    from .db import filing_month
    invoices = sorted((r for r in recs if receipt_invoice(r)), key=lambda r: (r["date"], r["row"]))
    if not invoices:
        return
    codes = partybook.payee_codes(con, entity_id)  # a customer's SQL code names the payments of its recurring payments
    taken = {x[0] for x in con.execute("SELECT payment_id FROM sql_entries WHERE entity_id = ? AND payment_id IS NOT NULL "
                                       "AND doc_type = 'IV'", (entity_id,))}
    pays = con.execute(
        """SELECT p.*, py.name AS payee_name, py.match_words FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.direction = 'in' AND p.payee_id IS NOT NULL AND p.amount IS NOT NULL ORDER BY p.due_date, p.id""", (entity_id,)).fetchall()
    for r in invoices:
        if con.execute("SELECT 1 FROM sql_entries WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ? "
                       "AND payment_id IS NOT NULL", (entity_id, r["doc_no"], r["date"], r["amount"])).fetchone():
            continue
        text, month, day = _words(r["description"] + " " + r["payee"]), filing_month(r["description"], r["date"]), date.fromisoformat(r["date"])
        fits = [p for p in pays if p["id"] not in taken and abs(p["amount"] - r["amount"]) < 0.005
                and (_words(" ".join(filter(None, [p["match_words"], p["payee_name"]]))) & text or partybook.coded(codes, p, r))]
        best = min(fits, key=lambda p: (p["month"] != month, abs((date.fromisoformat(p["due_date"]) - day).days)), default=None)
        if best and (best["month"] == month or abs((date.fromisoformat(best["due_date"]) - day).days) <= 45):
            taken.add(best["id"])
            r["payment_id"], r["payment_desc"] = best["id"], best["description"]


def propose(con, entity_id, recs):
    """Suggest which payment each SQL voucher records.

    A voucher whose number is typed in a payment's SQL ref box (and not linked yet) goes to that payment, and step 2
    or 3 can add the payment's other vouchers. The rest are matched payment by payment, firm amounts first, so an
    estimate can never take a voucher a fixed payment needs:
    1. one voucher with exactly the amount (named, or unnamed within 15 days);
    2. several named vouchers adding up exactly (SOCSO and SKBBK paid separately for one payment);
    3. for an estimate, the named voucher(s) closest to it within ±50% (electricity, PCB, KWSP vary every month).
    A voucher must share a real name word with the payment; months and accounting terms don't count.
    """
    for r in recs:
        task = task_for(con, entity_id, r)
        r["task_id"], r["task_title"] = (task["id"], task["title"]) if task else (None, None)
        r["payment_id"] = r["payment_desc"] = None
    _propose_receipts(con, entity_id, recs)
    open_recs = [r for r in recs if r["kind"] == "payment"]  # journals and invoices record no bank payment
    from . import checklistbook, partybook
    book = checklistbook.get(con)
    codes = partybook.payee_codes(con, entity_id)  # a supplier's or customer's SQL code names its recurring payments' payments
    pays = con.execute(
        """SELECT p.*, py.name AS payee_name, py.match_words FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.amount IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sql_entries s WHERE s.payment_id = p.id AND COALESCE(s.kind, 'payment') IN ('payment', 'journal'))
           ORDER BY p.amount_is_estimate, p.due_date""", (entity_id,)).fetchall()
    def pinfo(p):
        return (date.fromisoformat(p["paid_date"] or p["due_date"]),
                _words(" ".join(filter(None, [p["description"], p["payee_name"], p["match_words"]]))))

    def assign(p, chosen):
        done.add(p["id"])
        for r in chosen:
            taken.add(r["row"])
            r["payment_id"], r["payment_desc"] = p["id"], p["description"]

    taken, done, typed = set(), set(), {}
    by_ref = payments_by_ref(con, entity_id)
    for r in open_recs:
        p = by_ref.get(r["doc_no"].upper())
        if p:
            assign(p, [r])
            typed.setdefault(p["id"], []).append(r)
    # Pass 1: single vouchers with the exact amount, closest date first across all payments, so September's
    # salary voucher goes to September's salary even though August's has the same amount.
    pairs = []
    for p in pays:
        pd, pwords = pinfo(p)
        for r in open_recs:
            if (r.get("direction") and p["direction"] != r["direction"]) or abs(r["amount"] - p["amount"]) >= 0.005:
                continue
            gap = abs((date.fromisoformat(r["date"]) - pd).days)
            named = bool(pwords & _words(r["description"] + " " + r["payee"])) or partybook.coded(codes, p, r)
            if gap <= 15 or (named and gap <= 31):  # up to 31 days late (a leaver's final pay) only with the name
                pairs.append((gap, not named, p["amount_is_estimate"], p["id"], r["row"], p, r))
    for gap, _, _, pid, row, p, r in sorted(pairs, key=lambda x: x[:5]):
        if pid not in done and row not in taken:
            assign(p, [r])
    # Pass 2: several named vouchers adding up (SOCSO + SKBBK), then estimates (bills, PCB) within ±50%. A payment
    # with only some of its numbers typed (SOCSO's but not SKBBK's) is topped up the same way.
    for p in pays:
        have = typed.get(p["id"])
        if p["id"] in done and not have:
            continue
        base = round(sum(_signed(r, p) for r in have), 2) if have else None
        if have and abs(base - p["amount"]) < 0.005:
            continue
        pd, pwords = pinfo(p)
        hints = book.hints.get(p["category"])
        near = [r for r in open_recs if r["row"] not in taken
                and not (r.get("direction") and p["direction"] != r["direction"])
                and abs((date.fromisoformat(r["date"]) - pd).days) <= 15
                and (pwords & _words(r["description"] + " " + r["payee"]) or partybook.coded(codes, p, r))]
        chosen = _sum_to(near, p["amount"], exact=True, base=base)
        if not chosen and p["amount_is_estimate"]:
            text_ok = [r for r in near if not hints or any(h in (r["description"] + " " + r["payee"]).upper() for h in hints)]
            chosen = _sum_to(text_ok, p["amount"], exact=False, base=base)
        if chosen:
            assign(p, chosen)
    return recs


def _signed(r, p):
    """A voucher's amount as it counts towards the payment: money moving the other way (a refund) is taken off."""
    return -r["amount"] if r.get("direction") and r["direction"] != p["direction"] else r["amount"]


def _sum_to(recs, amount, exact, base=None):
    """Smallest combination of vouchers adding up to the amount (exact), or closest within ±50% (estimate).
    base is what the vouchers already chosen add up to: the combination tops it up, and must bring an estimate closer."""
    from itertools import combinations
    recs = recs[:10]
    best, best_diff = None, None if base is None else abs(base - amount)
    for size in range(2 if exact and base is None else 1, min(len(recs), 4) + 1):
        for combo in combinations(recs, size):
            total = round((base or 0) + sum(r["amount"] for r in combo), 2)
            if exact:
                if abs(total - amount) < 0.005:
                    return list(combo)
            elif amount and 0.5 <= total / amount <= 1.5 and (best_diff is None or abs(total - amount) < best_diff):
                best, best_diff = list(combo), abs(total - amount)
    return best


# Which checklist task an SQL document is evidence for: (kinds, direction, words any of which must appear, task code).
# The words SQL documents were filed by until update 21 (checklistbook: Setup's from then on, filled with these). The
# rules for the related company's fund and the tenant's rent belong to the checklist codes only rules.CHECKLIST has
# (its names are made up); update 21 and seed.json add them only for a company whose checklist has those codes.
TASK_RULES = [
    ({"journal"}, None, ("PAYROLL", "SALARY", "SALARIES", "WAGES", "GAJI"), "payroll-jv"),
    ({"invoice"}, None, ("NORTHWIND INTERNATIONAL",), "fund-received"),
    ({"payment"}, "in", ("NORTHWIND INTERNATIONAL",), "fund-received"),
    ({"invoice"}, None, ("CONTOSO CAFE",), "einv-rental"),
]


def task_for(con, entity_id, r):
    text = f"{r['description']} {r['payee']}".upper()
    code = None
    from . import checklistbook
    book = checklistbook.get(con)
    rcode = (r.get("code") or "").upper()
    fits = lambda kinds, direction: r["kind"] in kinds and (direction is None or r.get("direction") == direction)
    # A rule naming a customer or supplier whose SQL code the document carries comes first; then the words, in order.
    for i, (kinds, direction, words, c) in enumerate(book.filing):
        party = book.filing_codes[i] if i < len(book.filing_codes) else None  # (company or None, SQL code) of a party named
        if rcode and party and party[1] == rcode and party[0] in (None, entity_id) and fits(kinds, direction):
            code = c
            break
    else:
        for kinds, direction, words, c in book.filing:
            if fits(kinds, direction) and any(w in text for w in words):
                code = c
                break
    if not code and r["kind"] == "payment" and r.get("einvoice") and r.get("direction") == "out":
        code = "einv-selfbilled"  # a payment carrying its own e-Invoice is a self-billed one (overseas provider)
    if not code:
        return None
    # The same task exists every month; take, for an invoice or journal, the one of the month it belongs to (the month its
    # description names, else the month it is dated in); any other document, or one without that month's item, takes the
    # item whose due date is nearest the document date.
    from .db import item_for
    return item_for(con, entity_id, code, r["description"], r["date"], r["kind"])


def candidates(con, entity_id, months, also=()):
    """Payments a voucher can be linked to: those of these months, plus any in also (proposed for a number typed on
    a payment of an earlier month), so the list shows every suggestion."""
    also = sorted(set(also))
    q, a = ",".join("?" * len(months)), ",".join("?" * len(also))
    return [dict(r) for r in con.execute(
        f"""SELECT id, month, description, amount, due_date, paid_date, sql_ref, direction FROM payments WHERE entity_id = ?
            AND (month IN ({q}) OR id IN ({a})) ORDER BY due_date""",
        (entity_id, *months, *also))]


def months_of(recs):
    ms = {r["date"][:7] for r in recs}
    out = set()
    for m in ms:
        y, mo = map(int, m.split("-"))
        prev = f"{y - (mo == 1):04d}-{12 if mo == 1 else mo - 1:02d}"
        out |= {m, prev}
    return sorted(out)
