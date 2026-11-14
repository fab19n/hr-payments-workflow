"""Reads a listing exported from SQL Account with its print button (Export to Microsoft Excel Workbook).

That export is the printed page laid out on a sheet, not a table: title rows, a heading row whose cells are merged
differently from the figures under them, each document on one or more rows (its cheque number and the rest of its
description on the rows below), the page heading again on every page, then the report's own count and grand total.
SQL Account also writes the workbook with an attribute openpyxl refuses (WindowWidth), so the sheet is read here from
the file's XML parts.

A cell is placed by the heading its merged span lies under, not by its column: "Description" is printed over column G
while the descriptions start in column E, merged across to J.
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
MAX_PART = 30 * 1024 * 1024   # a part larger than this, unpacked, is no listing
MAX_ROWS = 200_000

# The listings read, by the title printed on them, and how their documents are typed. The doc no. alone can't say it: a
# payment voucher may be numbered CLAIMS_NOV26, and a customer invoice ABC/2026/10/001.
#   "side": the cash book, where DR is money into the bank (an official receipt) and CR money out (a payment voucher)
#   "code": an invoice listing, where a supplier's account code (4xx) makes it a supplier invoice, any other a customer's
LISTINGS = {
    "payment voucher listing": "PV", "official receipt listing": "OR", "cash book listing": "side",
    "journal voucher listing": "JV",
    "customer invoice listing": "code", "invoice listing": "code", "supplier invoice listing": "PI",
    "customer payment listing": "OR", "supplier payment listing": "SP",
}
READS = "the Cash Book, Payment Voucher, Official Receipt, Journal Voucher, Customer Invoice, Sales Invoice and Customer Payment listings"
ENDS = ("transaction summary", "account summary", "item code summary")  # the blocks printed after a listing's documents

PAGE = re.compile(r"^Page \d+ of \d+$", re.I)
PERIOD = re.compile(r"From (\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})", re.I)
CELL = re.compile(r"^([A-Z]+)(\d+)$")
DATE_FORMAT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


class ReportError(ValueError):
    """A report from SQL Account that can't be read. The message is a plain sentence for the person importing."""


# ---------- the sheet ----------

def _part(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise ValueError("part too large")
    return z.read(info)


def _col(ref):
    n = 0
    for ch in CELL.match(ref).group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _is_date_format(code):
    code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.', "", code)
    return bool(re.search(r"[dyhs]", code, re.I)) or ("m" in code.lower() and not re.search(r"[0#?]", code))


def _date_styles(z, names):
    """The cell styles (positions in cellXfs) whose number format shows a date or a time."""
    if "xl/styles.xml" not in names:
        return set()
    root = ET.fromstring(_part(z, "xl/styles.xml"))
    custom = {int(f.get("numFmtId")): f.get("formatCode") or "" for f in root.iter(NS + "numFmt") if (f.get("numFmtId") or "").isdigit()}
    xfs = root.find(NS + "cellXfs")
    out = set()
    for i, xf in enumerate(xfs.findall(NS + "xf") if xfs is not None else []):
        fid = int(xf.get("numFmtId") or 0)
        if fid in DATE_FORMAT_IDS or (fid in custom and _is_date_format(custom[fid])):
            out.add(i)
    return out


def _first_sheet(z, workbook, names):
    sheet = next(workbook.iter(NS + "sheet"), None)
    rid = sheet.get(DOC_REL) if sheet is not None else None
    if rid and "xl/_rels/workbook.xml.rels" in names:
        for rel in ET.fromstring(_part(z, "xl/_rels/workbook.xml.rels")).iter(PKG_REL):
            if rel.get("Id") == rid:
                target = (rel.get("Target") or "").lstrip("/")
                target = target if target.startswith("xl/") else "xl/" + target
                if target in names:
                    return target
    return sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml"))[0]


def _from_serial(n, date1904):
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    try:
        d = (base + timedelta(days=n) + timedelta(microseconds=500000)).replace(microsecond=0)
    except (OverflowError, ValueError):
        return n
    return d.date() if d.time() == time(0) else d


def _text(el):
    """The text of a shared or inline string: its own <t>, or its runs' (the phonetic guide left out)."""
    return "".join(t.text or "" for t in el.findall(NS + "t")) + "".join(
        t.text or "" for r in el.findall(NS + "r") for t in r.findall(NS + "t"))


def _value(c, shared, date_styles, date1904):
    kind, v = c.get("t"), c.find(NS + "v")
    if kind == "inlineStr":
        node = c.find(NS + "is")
        val = _text(node) if node is not None else ""
    elif v is None or v.text is None:
        return None
    elif kind == "s":
        val = shared[int(v.text)]
    elif kind in ("str", "e"):
        val = v.text
    elif kind == "b":
        return v.text == "1"
    else:
        try:
            n = float(v.text)
        except ValueError:
            return v.text
        return _from_serial(n, date1904) if int(c.get("s") or 0) in date_styles else n
    return val if val.strip() else None


def read_xlsx(data):
    """The first sheet of an .xlsx, read from its XML parts: (rows, spans). rows: one list per sheet row, a cell's value
    at its column (None where blank; dates as date or datetime, numbers as float). spans: {(row, column): last column}
    for every cell merged across columns on one row. Raises when the bytes are not a workbook."""
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    workbook = ET.fromstring(_part(z, "xl/workbook.xml"))
    date1904 = any(p.get("date1904") in ("1", "true") for p in workbook.iter(NS + "workbookPr"))
    shared = []
    if "xl/sharedStrings.xml" in names:
        shared = [_text(si) for si in ET.fromstring(_part(z, "xl/sharedStrings.xml")).iter(NS + "si")]
    date_styles = _date_styles(z, names)
    root = ET.fromstring(_part(z, _first_sheet(z, workbook, names)))
    rows, spans = [], {}
    for row in root.iter(NS + "row"):
        r = int(row.get("r") or len(rows) + 1) - 1
        if not 0 <= r < MAX_ROWS:
            raise ValueError("too many rows")
        while len(rows) <= r:
            rows.append([])
        cur, nxt = rows[r], 0
        for c in row.findall(NS + "c"):
            col = _col(c.get("r")) if c.get("r") else nxt
            nxt = col + 1
            val = _value(c, shared, date_styles, date1904)
            if val is None:
                continue
            while len(cur) <= col:
                cur.append(None)
            cur[col] = val
    for m in root.iter(NS + "mergeCell"):
        a, _, b = (m.get("ref") or "").partition(":")
        ma, mb = CELL.match(a), CELL.match(b or a)
        if ma and mb and ma.group(2) == mb.group(2):
            spans[(int(ma.group(2)) - 1, _col(a))] = _col(b or a)
    return rows, spans


# ---------- the listing ----------

def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _a_date(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(v.strip(), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _a_number(v):
    if isinstance(v, (bool, date, datetime)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        neg = s.startswith("(") and s.endswith(")")
        try:
            n = float(s.strip("()"))
        except ValueError:
            return None
        return -n if neg else n
    return None


def _first_number(values):
    return next((n for n in (_a_number(x) for x in values) if n is not None), None)


def _words(parts):
    return re.sub(r"\s+", " ", " ".join(str(p) for p in parts)).strip()


def _head_key(x):
    """Which field a heading cell names, or None: SQL prints Doc Date or Doc. Date, Doc No/Chq No or Document No,
    Amount (MYR), DR (MYR) or Debit (MYR)."""
    n = _norm(x).replace(".", "") if isinstance(x, str) else ""
    if n in ("doc date", "date"):
        return "date"
    if n.startswith(("doc no", "document no")):
        return "doc_no"
    if n in ("description", "code"):
        return n
    if n == "name":
        return "payee"
    if re.match(r"amount\b", n):
        return "amount"
    if re.match(r"(dr|debit)\b", n):
        return "debit"
    if re.match(r"(cr|credit)\b", n):
        return "credit"
    return None


def _heading(rows, spans, start):
    """The heading row after the page line: (row, {field: (first column, last column)})."""
    for i in range(start, min(len(rows), start + 25)):
        heads = {}
        for c, x in enumerate(rows[i]):
            key = _head_key(x)
            if key and key not in heads:
                heads[key] = (c, spans.get((i, c), c))
        if {"date", "doc_no"} <= heads.keys() and ("amount" in heads or {"debit", "credit"} <= heads.keys()):
            return i, heads
    return None, None


def _zone(heads, first, last):
    """The heading a cell lies under: the leftmost one its span overlaps (a wrapped description runs on under the next)."""
    hit = [k for k, (a, b) in heads.items() if a <= last and first <= b]
    return min(hit, key=lambda k: heads[k][0]) if hit else None


def _summary(rows, at):
    """The report's own count and grand totals, from the row its documents end at and the rows under it: (count or
    None, [totals]). A two-sided listing prints two totals, debit then credit."""
    count, totals = None, []
    for n, row in enumerate(rows[at:at + 12]):
        if n and any(isinstance(x, str) and _norm(x) in ENDS for x in row):
            break
        for c, x in enumerate(row):
            if not isinstance(x, str):
                continue
            after = []
            for y in row[c + 1:]:
                if isinstance(y, str) and y.strip():
                    break  # the next label on the row: its figures are not this one's
                if _a_number(y) is not None:
                    after.append(_a_number(y))
            if _norm(x).startswith("total records") and after and count is None:
                count = int(round(after[0]))
            if _norm(x).startswith("grand total") and after and not totals:
                totals = after
    return count, totals


def listing(rows, spans):
    """The listing printed on these sheet rows, or None when they are not a page printed by SQL Account.

    {title, company, period: [from, to] or None, total, entries: [{doc_no, doc_type, date, description, amount,
    cheque_no, payee, code}]}. Raises ReportError for a report of another kind, a layout not seen before, or documents
    that don't add up to the count and grand total the report prints, so a listing is never half read."""
    top = rows[:25]
    page_row = next((i for i, r in enumerate(top) if any(isinstance(x, str) and PAGE.match(x.strip()) for x in r)), None)
    if page_row is None:
        return None
    words = [_norm(x) for r in top for x in r if isinstance(x, str)]
    if any("excluding gst" in w for w in words):
        raise ReportError("This is the GST layout of a listing, which this app doesn't read. Export the same listing with the layout that has no (GST) in its name.")
    if "chart of accounts" in words:
        raise ReportError("This is the chart of accounts, not a listing of documents. Paste it in Setup › Chart of accounts › Paste a list.")
    title = next((x.strip() for r in top for x in r if isinstance(x, str) and _norm(x) in LISTINGS), None)
    if not title:
        raise ReportError(f"This is a printed report, but not a listing this app reads yet. It reads {READS}.")
    kind = LISTINGS[_norm(title)]
    head_row, heads = _heading(rows, spans, page_row + 1)
    if head_row is None:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: no row has the headings for the date, the doc no. and the amount.")
    two_sided = "amount" not in heads
    company = next((x.strip() for x in rows[page_row] if isinstance(x, str) and x.strip() and not PAGE.match(x.strip())), "")
    period = next((m for r in top for x in r if isinstance(x, str) for m in [PERIOD.search(x)] if m), None)
    money = ("amount", "debit", "credit")

    entries, cur, end_at, furniture = [], None, None, False
    for i in range(head_row + 1, len(rows)):
        cells = [(c, x) for c, x in enumerate(rows[i]) if x is not None and not (isinstance(x, str) and not x.strip())]
        if not cells:
            continue
        texts = [_norm(x) for _, x in cells if isinstance(x, str)]
        if any(t == "summary" or t.startswith("grand total") for t in texts):
            end_at = i
            break
        if any(t in ENDS for t in texts):
            break
        # A new page prints the title, the As At line, the company with the page number and the headings again
        if any(t == _norm(title) or PAGE.match(t) for t in texts):
            furniture = True
            continue
        if furniture:
            at = heads["doc_no"][0]
            furniture = _head_key(rows[i][at] if at < len(rows[i]) else None) != "doc_no"
            continue
        by = {}
        for c, x in cells:
            by.setdefault(_zone(heads, c, spans.get((i, c), c)), []).append(x)
        if "date" in by:
            day = _a_date(by["date"][0])
            if day is None:
                continue  # a label of the report's own, not a document
            doc_no = _words(by.get("doc_no", []))
            amount, dr, cr = (_first_number(by.get(k, [])) for k in money)
            if not doc_no or (amount is None and dr is None and cr is None):
                raise ReportError(f"This {title} is laid out in a way this app hasn't seen: row {i + 1} has a date but no doc no. or amount.")
            if two_sided:
                dr, cr = dr or 0.0, cr or 0.0
                if kind == "JV" and abs(dr - cr) >= 0.005:
                    raise ReportError(f"This {title} has a journal, {doc_no}, whose debit and credit differ, so nothing was taken from it.")
                if kind != "JV" and dr and cr:
                    raise ReportError(f"This {title} has a document, {doc_no}, with both a debit and a credit, so nothing was taken from it.")
                amount = dr or cr
            cur = {"doc_no": doc_no, "date": day, "description": _words(by.get("description", [])), "amount": amount, "cheque_no": "",
                   "payee": _words(by.get("payee", [])), "code": _words(by.get("code", [])).upper(), "_dr": dr or 0.0, "_cr": cr or 0.0}
            entries.append(cur)
        elif cur and not any(k in by for k in money) and any(k in by for k in ("doc_no", "description", "payee")):
            # The rows under a document: its cheque no. under the doc no., the rest of its description or name under the first part
            cur["cheque_no"] = _words([cur["cheque_no"], *by.get("doc_no", [])])
            cur["description"] = _words([cur["description"], *by.get("description", [])])
            cur["payee"] = _words([cur["payee"], *by.get("payee", [])])

    total = round(sum(e["amount"] for e in entries), 2)
    if end_at is not None:
        said_count, said = _summary(rows, end_at)
        if said_count is not None and said_count != len(entries):
            raise ReportError(f"This {title} says it has {said_count} documents, but {len(entries)} could be read, so nothing was taken from it. "
                              "Copy and paste this listing instead.")
        read = [round(sum(e["_dr"] for e in entries), 2), round(sum(e["_cr"] for e in entries), 2)] if two_sided else [total]
        if said and any(abs(a - b) >= 0.005 for a, b in zip(said, read)):
            raise ReportError(f"This {title} says its total is {' and '.join(f'{x:,.2f}' for x in said[:len(read)])}, but the documents read add up to "
                              f"{' and '.join(f'{x:,.2f}' for x in read[:len(said)])}, so nothing was taken from it. Copy and paste this listing instead.")
    for e in entries:
        e["doc_type"] = ("OR" if e["_dr"] else "PV") if kind == "side" else ("PI" if e["code"].startswith("4") else "IV") if kind == "code" else kind
        e["doc_no"] = re.sub(r"\.0$", "", e["doc_no"])  # a whole number read from the sheet as 123.0
        e["cheque_no"] = re.sub(r"(?<=\d)\.0$", "", e["cheque_no"])
        del e["_dr"], e["_cr"]
    return {"title": title, "company": company, "period": [_a_date(period.group(1)), _a_date(period.group(2))] if period else None,
            "entries": entries, "total": total}


def _sheet(data):
    """The first sheet of a workbook, or None when the bytes are not one this reader understands."""
    if data[:2] != b"PK":
        return None
    try:
        return read_xlsx(data)
    except Exception:  # not a workbook this reader understands: for the caller to try another way
        return None


def read(data):
    """What a file exported from SQL Account holds: ("listing", listing) for a listing, (kind, report) for a
    general-ledger report ('journal', 'gl_ledger' or 'trial_balance', read by hrp/sqlgl.py), or None when the file is
    anything else. The general-ledger reports are told apart first: they print a page number but no listing title, so
    listing() would take them for a report it doesn't read. Raises ReportError for an SQL report that can't be read."""
    from . import sqlgl  # sqlgl reads the sheet with this module's helpers
    sheet = _sheet(data)
    if sheet is None:
        return None
    kind = sqlgl.detect(*sheet)
    if kind:
        return kind, sqlgl.READERS[kind](*sheet)
    rep = listing(*sheet)
    return ("listing", rep) if rep is not None else None


def parse(data):
    """The listing in a file exported from SQL Account, or None when the file is anything else (another spreadsheet, or
    not a workbook at all). Raises ReportError for an SQL report that can't be read, and for SQL's general-ledger
    reports, which are read only by Fetch from SQL exports."""
    from . import sqlgl
    sheet = _sheet(data)
    if sheet is None:
        return None
    kind = sqlgl.detect(*sheet)
    if kind:
        raise ReportError(f"This is SQL's {sqlgl.TITLES[kind]}: save it in the exports folder and use Fetch from SQL exports.")
    return listing(*sheet)
