"""Reads listings exported from SQL Account (Excel, CSV or ODS) and matches each entry to a payment.

SQL Account's report layouts vary, so columns are detected from the header row and can be corrected on screen.
"""
import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

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
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
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
                      "Cheque No", "e-Invoice UUID", "e-Invoice status", "e-Invoice link"]


def _first(a, *keys):
    for k in keys:
        v = (a.get(k) or "").strip()
        if v:
            return v
    return ""


def _doc_type_from(a, doc_no):
    """Listings without a DOCTYPE field. Customer invoice numbers can be free-form (AISB/2026/10/001), but the
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
                     _first(a, "CHEQUENUMBER"), uuid, status, _first(a, "IRBM_VALIDATIONLINK")])
    return rows


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
    return best


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
                    "einvoice_link": str(get("einvoice_link") or "").strip()})
    if not out:
        raise SqlImportError("No entries were found under the heading row. Check that Doc No, Date and Amount point to the right columns.")
    return out


# ---------- matching ----------

# Words that say nothing about who was paid: months, years and accounting terms. "AUG" in a claim and in a TNB
# bill must not make them look alike.
NOISE = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "SEPT", "OCT", "NOV", "DEC",
         "PAYMENT", "SALARY", "FEE", "FOR", "THE", "AND", "SDN", "BHD", "LTD", "MONTH", "CLAIM", "CLAIMS",
         "EXPENSES", "EXPENSE", "CONTRIBUTION", "CHARGE", "CHARGES", "RENTAL", "DEDUCTION", "ACCOUNT",
         "SUBSCRIPTION", "INVOICE", "PLAN", "PRO", "ADVANCE", "AUDIT", "BILL", "FROM", "WITH"}


def _words(s):
    return {w for w in re.findall(r"[A-Z]{3,}", (s or "").upper()) if w not in NOISE}


CATEGORY_HINTS = {"salary": ("SALARY", "GAJI", "WAGES", "PAYROLL"),
                  "director": ("DIRECTOR", "ALLOWANCE", "ALL'CE", "SALARY")}


def refs_of(text):
    """The voucher numbers in a payment's SQL ref box, e.g. "PV2611-012, PV2611-016"."""
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
    (OR2610-002 refunding a duplicated self-billed e-Invoice, PV2610-026 replacing the PV). An entry with no direction
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


def propose(con, entity_id, recs):
    """Suggest which payment each SQL voucher records.

    A voucher whose number is typed in a payment's SQL ref box (and not linked yet) goes to that payment, and step 2
    or 3 can add the payment's other vouchers. The rest are matched payment by payment, firm amounts first, so an
    estimate can never take a voucher a fixed payment needs:
    1. one voucher with exactly the amount (named, or unnamed within 15 days);
    2. several named vouchers adding up exactly (SOCSO and SKBBK paid separately for one payment);
    3. for an estimate, the named voucher(s) closest to it within ±50% (TNB, PCB, KWSP vary every month).
    A voucher must share a real name word with the payment; months and accounting terms don't count.
    """
    for r in recs:
        task = task_for(con, entity_id, r)
        r["task_id"], r["task_title"] = (task["id"], task["title"]) if task else (None, None)
        r["payment_id"] = r["payment_desc"] = None
    open_recs = [r for r in recs if r["kind"] == "payment"]  # journals and invoices record no bank payment
    pays = con.execute(
        """SELECT p.*, py.name AS payee_name, py.match_words FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.amount IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM sql_entries s WHERE s.payment_id = p.id)
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
            named = bool(pwords & _words(r["description"] + " " + r["payee"]))
            if gap <= 15 or (named and gap <= 31):  # up to 31 days late (a leaver's final pay) only with the name
                pairs.append((gap, not named, p["amount_is_estimate"], p["id"], r["row"], p, r))
    for gap, _, _, pid, row, p, r in sorted(pairs, key=lambda x: x[:5]):
        if pid not in done and row not in taken:
            assign(p, [r])
    # Pass 2: several named vouchers adding up (SOCSO + SKBBK), then estimates (TNB, PCB) within ±50%. A payment
    # with only some of its numbers typed (SOCSO's but not SKBBK's) is topped up the same way.
    for p in pays:
        have = typed.get(p["id"])
        if p["id"] in done and not have:
            continue
        base = round(sum(_signed(r, p) for r in have), 2) if have else None
        if have and abs(base - p["amount"]) < 0.005:
            continue
        pd, pwords = pinfo(p)
        hints = CATEGORY_HINTS.get(p["category"])
        near = [r for r in open_recs if r["row"] not in taken
                and not (r.get("direction") and p["direction"] != r["direction"])
                and abs((date.fromisoformat(r["date"]) - pd).days) <= 15
                and pwords & _words(r["description"] + " " + r["payee"])]
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


# Which checklist task an SQL document is evidence for: (kinds, direction, words any of which must appear, task code)
TASK_RULES = [
    ({"journal"}, None, ("PAYROLL", "SALARY", "SALARIES", "WAGES", "GAJI"), "payroll-jv"),
    ({"invoice"}, None, ("AGRINEXUS INTERNATIONAL",), "fund-received"),
    ({"payment"}, "in", ("AGRINEXUS INTERNATIONAL",), "fund-received"),
    ({"invoice"}, None, ("WE LOAF",), "einv-rental"),
]


def task_for(con, entity_id, r):
    text = f"{r['description']} {r['payee']}".upper()
    code = None
    for kinds, direction, words, c in TASK_RULES:
        if r["kind"] in kinds and (direction is None or r.get("direction") == direction) and any(w in text for w in words):
            code = c
            break
    if not code and r["kind"] == "payment" and r.get("einvoice") and r.get("direction") == "out":
        code = "einv-selfbilled"  # a payment carrying its own e-Invoice is a self-billed one (overseas provider)
    if not code:
        return None
    # The same task exists every month; take the one whose due date is nearest the document date.
    rows = con.execute("SELECT id, title, due_date FROM tasks WHERE entity_id = ? AND code = ?", (entity_id, code)).fetchall()
    rd = date.fromisoformat(r["date"])
    best = min(rows, key=lambda t: abs((date.fromisoformat(t["due_date"]) - rd).days), default=None)
    return best if best and abs((date.fromisoformat(best["due_date"]) - rd).days) <= 45 else None


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
