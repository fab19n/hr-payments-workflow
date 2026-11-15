"""Reads the copy of SQL Account's MyInvois Transaction screen, and keeps what LHDN says of each e-Invoice.

SQL Account can't export that screen, so the owner copies its grid (Ctrl+A, Ctrl+C) with its headings, pastes it into
Excel and saves the workbook in the exports folder under any name. Fetch from SQL exports finds it by its headings (a
UUID, a Status, a Supplier TIN and a Buyer TIN column) or, in an older copy made without headings, by its shape (the
e-Invoice's 26-character UUID in the second column and a status LHDN uses in its place).

Each e-Invoice is kept once per company by its UUID (myinvois_docs, update 33). A later copy, which may hold more
e-Invoices or a status changed since (an e-Invoice cancelled), updates the ones it has; one it leaves out is kept, as
a copy may be filtered. The e-Invoices the company issued (its own invoices and its self-billed payment vouchers) fill
in the e-Invoice of the SQL document with the same number, so the checklist and the payments see them validated as a
paste of SQL's invoice grid would show. Those issued to the company are matched to its supplier invoices and payment
vouchers; the ones not found in SQL's books are listed for the owner to check. Nothing here is typed in by hand.
"""
import re
from datetime import date, datetime

from . import audit, db, sqlreport

TITLE = "MyInvois e-Invoices"

# The headings the MyInvois Transaction grid prints, and the field each one gives.
HEADINGS = {
    "doc no": "doc_no", "document no": "doc_no", "uuid": "uuid", "type": "type", "version": "version",
    "currency": "currency", "supplier name": "supplier_name", "supplier tin": "supplier_tin", "buyer name": "buyer_name",
    "buyer tin": "buyer_tin", "receiver tin": "receiver_tin", "submission id": "submission_id",
    "submission channel": "channel", "validated date": "validated_at", "received date": "received_at",
    "issued date": "issued_at", "reject date": "rejected_at", "rejected date": "rejected_at", "status": "status",
    "total amount": "total", "total excluding tax": "excl_tax", "total net amount": "net", "long id": "long_id",
}
# MyInvois's public page of an e-Invoice (the one its QR code opens), made from its UUID and Long ID.
LINK = "https://myinvois.hasil.gov.my/{uuid}/share/{long_id}"
LONG_ID = re.compile(r"^[A-Za-z0-9]{20,}$")
SIGNS = ("uuid", "status", "supplier_tin", "buyer_tin")  # the headings that make a sheet a MyInvois copy
NEEDED = ("doc_no", "uuid", "type", "status", "total")   # without these a copy can't be read
# A copy made without headings: its columns by position. The newer grid has 20 columns, the older one 15 (no Receiver
# TIN, Submission ID, Validated Date, Total Excluding Tax or Total Net Amount).
NEW_LAYOUT = ["doc_no", "uuid", "type", "version", "currency", "supplier_name", "supplier_tin", "buyer_name", "buyer_tin",
              "receiver_tin", "submission_id", "channel", "validated_at", "received_at", "issued_at", "rejected_at",
              "status", "total", "excl_tax", "net"]
OLD_LAYOUT = ["doc_no", "uuid", "type", "version", "currency", "supplier_name", "supplier_tin", "buyer_name", "buyer_tin",
              "channel", "received_at", "issued_at", "rejected_at", "status", "total"]
FIELDS = ("doc_no", "uuid", "type", "version", "currency", "supplier_name", "supplier_tin", "buyer_name", "buyer_tin",
          "receiver_tin", "submission_id", "channel", "validated_at", "received_at", "issued_at", "rejected_at", "status",
          "total_sen", "excl_tax_sen", "net_sen", "long_id")
WHEN = ("validated_at", "received_at", "issued_at", "rejected_at")
MONEY = {"total": "total_sen", "excl_tax": "excl_tax_sen", "net": "net_sen"}
UUID = re.compile(r"^[A-Z0-9]{26}$")
# The statuses LHDN gives an e-Invoice, as the grid prints them.
STATUSES = {"valid": "Valid", "cancelled": "Cancelled", "canceled": "Cancelled", "invalid": "Invalid",
            "submitted": "Submitted", "rejected": "Rejected"}
# What each status puts on the SQL document, in the words a paste of SQL's invoice grid uses (sqlimport), so every
# screen and checklist item that looks for a validated e-Invoice reads it the same way.
STATUS_WORDS = {"Valid": "Validated", "Cancelled": "Cancelled", "Invalid": "Invalid",
                "Submitted": "Submitted, not validated", "Rejected": "Rejected"}
DIRECTIONS = ("issued", "self_billed", "received", "other")
DIRECTION_WORDS = {"issued": "issued", "self_billed": "self-billed", "received": "received", "other": "other"}


class MyInvoisError(sqlreport.ReportError):
    """A MyInvois copy that can't be read. The message is a plain sentence for the person fetching."""


# ---------- reading the copy ----------

def _norm(x):
    return re.sub(r"\s+", " ", str(x or "").replace(".", " ").strip().lower()).strip()


def _cells(row):
    return [x for x in row if x is not None and not (isinstance(x, str) and not x.strip())]


def _headed(rows):
    """{field: column} when the first row with anything in it is the grid's heading row, else None."""
    first = next((r for r in rows if _cells(r)), None)
    if first is None:
        return None
    cols = {}
    for i, x in enumerate(first):
        f = HEADINGS.get(_norm(x)) if isinstance(x, str) else None
        if f and f not in cols:
            cols[f] = i
    return cols if all(s in cols for s in SIGNS) else None


def _shaped(rows):
    """{field: column} of a copy made without headings, told by its shape: a UUID in the second column and a status
    LHDN uses where the layout puts it, on most rows. None when the sheet isn't one."""
    filled = [r for r in rows if _cells(r)]
    if not filled:
        return None
    width = max(len(r) for r in filled)
    layout = NEW_LAYOUT if width > len(OLD_LAYOUT) else OLD_LAYOUT
    at = layout.index("status")

    def looks(r):
        u = r[1] if len(r) > 1 else None
        s = r[at] if len(r) > at else None
        return isinstance(u, str) and bool(UUID.match(u.strip())) and _norm(s) in STATUSES

    if sum(1 for r in filled if looks(r)) * 2 <= len(filled):
        return None
    return {f: i for i, f in enumerate(layout)}


def detect(rows):
    """('headings' or 'shape', {field: column}) when these sheet rows are a copy of the MyInvois Transaction grid,
    else None."""
    cols = _headed(rows)
    if cols is not None:
        return "headings", cols
    cols = _shaped(rows)
    return ("shape", cols) if cols is not None else None


def _text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))  # a number read as 123.0
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return re.sub(r"\s+", " ", str(v)).strip()


def _tin(v):
    return re.sub(r"[\s-]", "", _text(v)).upper()


def tin_key(v):
    """A TIN as compared here: capitals, without spaces or dashes."""
    return _tin(v)


def _when(v):
    """A date and time as YYYY-MM-DD HH:MM:SS (or YYYY-MM-DD for a date alone); None when blank. Raises ValueError
    when the cell holds something else."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, datetime):
        return v.replace(microsecond=0).isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        got = sqlreport._from_serial(float(v), False)  # a date Excel kept as a plain number
        if isinstance(got, (datetime, date)):
            return _when(got)
        raise ValueError
    s = re.sub(r"\s+", " ", str(v).strip().replace("T", " "))
    s = re.sub(r"(\.\d+)?(Z|[+-]\d\d:?\d\d)?$", "", s) if re.match(r"^\d{4}-", s) else s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %I:%M:%S %p",
                "%d/%m/%Y %I:%M %p", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s, fmt).isoformat(sep=" ")
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError


def _read_month_first(rows, cols):
    """Whether Excel read this copy's dates month first: its date columns hold both real dates and day-first text
    whose day can't be a month (13/11/2026 2:19:44 PM)."""
    text = real = False
    for r in rows:
        for c in cols:
            v = r[c] if c < len(r) else None
            if isinstance(v, (datetime, date)):
                real = True
            elif isinstance(v, str):
                m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/\d{4}", v)
                if m and int(m.group(1)) > 12:
                    text = True
    return text and real


def link_of(row):
    """The e-Invoice's page on MyInvois, when its copy gave the Long ID; else None."""
    keys = row.keys() if hasattr(row, "keys") else row
    long_id = row["long_id"] if "long_id" in keys else None
    return LINK.format(uuid=row["uuid"], long_id=long_id) if long_id else None


def _sen(v):
    """Ringgit (or the e-Invoice's own currency) in sen, or None when blank. Raises ValueError for anything else."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    n = sqlreport._a_number(v)
    if n is None:
        raise ValueError
    return int(round(n * 100))


def _status(v):
    s = _text(v)
    return STATUSES.get(s.lower(), s)


def parse(rows):
    """The e-Invoices of a MyInvois copy, or None when the rows are not one.

    {title, company: '', period: [first, last issued day] or None, headings: True/False, rows: [{doc_no, uuid, type,
    version, currency, supplier_name, supplier_tin, buyer_name, buyer_tin, receiver_tin, submission_id, channel,
    validated_at, received_at, issued_at, rejected_at, status, total_sen, excl_tax_sen, net_sen}]}. A copy with any row
    that can't be read is refused whole (MyInvoisError), so it is never half taken."""
    found = detect(rows)
    if not found:
        return None
    how, cols = found
    if how == "headings":
        lacking = [f for f in NEEDED if f not in cols]
        if lacking:
            names = {"doc_no": "Doc No.", "uuid": "UUID", "type": "Type", "status": "Status", "total": "Total Amount"}
            raise MyInvoisError(f"This MyInvois copy has no {' or '.join(names[f] for f in lacking)} column, so nothing was "
                                "taken from it. Copy the whole MyInvois Transaction grid again, with its headings.")
    start = next(i for i, r in enumerate(rows) if _cells(r)) + (1 if how == "headings" else 0)
    again = "Copy the whole MyInvois Transaction grid again" + (", with its headings." if how == "headings" else ".")
    out, seen = [], {}
    # Excel can read the grid's day-first dates month-first as it pastes them: 12/11/2026 becomes 11 December, while
    # 13/11/2026 (no 13th month) stays text. A copy whose date columns hold such day-first text beside real dates was
    # read that way, so its real dates have their day and month swapped back.
    month_first = _read_month_first(rows[start:], [cols[f] for f in WHEN if f in cols])
    for i in range(start, len(rows)):
        r = rows[i]
        if not _cells(r):
            continue
        get = lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else None
        rec = {f: _text(get(f)) for f in ("doc_no", "uuid", "type", "version", "currency", "supplier_name", "buyer_name",
                                         "submission_id", "channel")}
        rec["uuid"] = rec["uuid"].upper()
        for f in ("supplier_tin", "buyer_tin", "receiver_tin"):
            rec[f] = _tin(get(f))
        rec["status"] = _status(get("status"))
        problem = None
        if not UUID.match(rec["uuid"]):
            problem = f"a UUID that isn't one LHDN gives ({rec['uuid'] or 'blank'})"
        elif not rec["doc_no"]:
            problem = "no Doc No."
        elif not rec["status"]:
            problem = "no Status"
        elif how == "shape" and rec["status"] not in STATUS_WORDS:
            problem = f"a status this app doesn't know ({rec['status']})"
        rec["long_id"] = _text(get("long_id")) if "long_id" in cols else ""
        if problem is None and rec["long_id"] and not LONG_ID.match(rec["long_id"]):
            problem = f"a Long ID that isn't one LHDN gives ({rec['long_id']})"
        if problem is None:
            for f in WHEN:
                try:
                    v = get(f)
                    if month_first and isinstance(v, datetime) and v.day <= 12:
                        v = v.replace(month=v.day, day=v.month)
                    rec[f] = _when(v)
                except ValueError:
                    problem = f"a date it can't read under {f.replace('_at', '').replace('_', ' ').title()} Date ({_text(get(f))})"
                    break
        if problem is None:
            for f, key in MONEY.items():
                try:
                    rec[key] = _sen(get(f))
                except ValueError:
                    problem = f"an amount it can't read ({_text(get(f))})"
                    break
            if problem is None and rec["total_sen"] is None:
                problem = "no Total Amount"
        if problem is None and rec["uuid"] in seen and seen[rec["uuid"]] != rec:
            problem = f"the UUID {rec['uuid']} twice, with different details"
        if problem:
            raise MyInvoisError(f"Row {i + 1} of this MyInvois copy has {problem}, so nothing was taken from it. {again}")
        if rec["uuid"] in seen:
            continue
        rec["currency"] = rec["currency"].upper() or "MYR"
        seen[rec["uuid"]] = rec
        out.append({f: rec[f] for f in FIELDS})
    if not out:
        raise MyInvoisError(f"This MyInvois copy has no e-Invoices in it, so there is nothing to take. {again}")
    days = sorted(x["issued_at"][:10] for x in out if x["issued_at"])
    return {"title": TITLE, "company": "", "period": [days[0], days[-1]] if days else None,
            "headings": how == "headings", "rows": out}


# ---------- whose copy it is ----------

def owner(entities, rep):
    """The company a copy belongs to: the one whose TIN (Setup › Companies) is the supplier's or buyer's on the most
    e-Invoices, or None when no company's TIN appears in it."""
    best, most = None, 0
    for e in entities:
        tin = tin_key(e["tin"] if "tin" in e.keys() else "")
        if len(tin) < 6:
            continue
        n = sum(1 for x in rep["rows"] if tin in (x["supplier_tin"], x["buyer_tin"]))
        if n > most:
            best, most = e, n
    return best


def direction(row, tin):
    """Which way an e-Invoice goes for the company with this TIN: 'issued' (it is the supplier, not self-billed),
    'self_billed' (a self-billed one, it is the buyer: it issued it for an overseas supplier), 'received' (it is the
    buyer of an ordinary one) or 'other'."""
    tin = tin_key(tin)
    selfbilled = "self-billed" in (row["type"] or "").lower().replace("self billed", "self-billed")
    if not tin:
        return "other"
    if selfbilled:
        return "self_billed" if row["buyer_tin"] == tin else "other"
    if row["supplier_tin"] == tin:
        return "issued"
    if row["buyer_tin"] == tin:
        return "received"
    return "other"


# ---------- the records (update 33) ----------

TABLE = """
CREATE TABLE IF NOT EXISTS myinvois_docs (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), uuid TEXT NOT NULL, doc_no TEXT NOT NULL,
  type TEXT, version TEXT, currency TEXT, supplier_name TEXT, supplier_tin TEXT, buyer_name TEXT, buyer_tin TEXT,
  receiver_tin TEXT, submission_id TEXT, channel TEXT, validated_at TEXT, received_at TEXT, issued_at TEXT,
  rejected_at TEXT, status TEXT NOT NULL, total_sen INTEGER NOT NULL, excl_tax_sen INTEGER, net_sen INTEGER,
  direction TEXT NOT NULL CHECK (direction IN ('issued', 'self_billed', 'received', 'other')),
  as_at TEXT NOT NULL,
  first_import_id INTEGER REFERENCES sql_imports(id), last_import_id INTEGER REFERENCES sql_imports(id),
  first_document_id INTEGER REFERENCES documents(id), last_document_id INTEGER REFERENCES documents(id),
  entry_id INTEGER REFERENCES sql_entries(id), matched_by TEXT,
  UNIQUE (entity_id, uuid)
)"""


def install(con):
    """Update 33: the e-Invoices read from MyInvois copies (myinvois_docs), and on each SQL document when its e-Invoice
    was last known (einvoice_as_at) and whether MyInvois filled it (einvoice_from). Made empty, with their audit
    triggers before anything goes in (as statutory.install); a document's e-Invoice already pasted keeps its import's
    date as when it was known. Nothing else changes."""
    con.execute(TABLE)
    con.execute("CREATE INDEX IF NOT EXISTS myinvois_docs_entity ON myinvois_docs (entity_id, direction)")
    audit.refresh(con)
    db.add_column(con, "sql_entries", "einvoice_as_at", "TEXT")
    db.add_column(con, "sql_entries", "einvoice_from", "TEXT")


def ready(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'myinvois_docs'").fetchone())


def _as_at(saved):
    """A file's saved time as kept here (YYYY-MM-DDTHH:MM:SS, as db.now())."""
    return str(saved or db.now())[:19].replace(" ", "T")


def _differs(old, new):
    """The fields a copy changes. A copy without the Long ID column (an older layout) never clears a Long ID kept."""
    return [f for f in FIELDS if f != "uuid" and not (f == "long_id" and not new[f])
            and (old[f] if old[f] != "" else None) != (new[f] if new[f] != "" else None)]


def compare(con, entity_id, rep, saved):
    """What keeping this copy would do, without writing anything: {rows, new, changed, unchanged, older, issued,
    self_billed, received, other}. A copy saved before the one already read (older) changes nothing."""
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    out = dict.fromkeys(("new", "changed", "unchanged", "older") + DIRECTIONS, 0)
    out["rows"] = len(rep["rows"])
    at = _as_at(saved)
    for r in rep["rows"]:
        out[direction(r, ent["tin"])] += 1
        old = con.execute("SELECT * FROM myinvois_docs WHERE entity_id = ? AND uuid = ?", (entity_id, r["uuid"])).fetchone()
        if old is None:
            out["new"] += 1
        elif not _differs(old, r):
            out["unchanged"] += 1
        elif at < old["as_at"]:
            out["older"] += 1
        else:
            out["changed"] += 1
    return out


def keep(con, ent, import_id, document_id, rep, saved):
    """Keeps the e-Invoices of one copy: a new UUID is added, one already kept takes this copy's status, dates and
    details when the copy was saved no earlier than the one it was last read from. One the copy leaves out is kept.
    Returns {rows, new, changed, unchanged, older}."""
    at = _as_at(saved)
    out = dict.fromkeys(("new", "changed", "unchanged", "older"), 0)
    out["rows"] = len(rep["rows"])
    for r in rep["rows"]:
        way = direction(r, ent["tin"])
        old = con.execute("SELECT * FROM myinvois_docs WHERE entity_id = ? AND uuid = ?", (ent["id"], r["uuid"])).fetchone()
        if old is None:
            con.execute(f"""INSERT INTO myinvois_docs (entity_id, {', '.join(FIELDS)}, direction, as_at, first_import_id,
                            last_import_id, first_document_id, last_document_id)
                            VALUES (?, {', '.join('?' for _ in FIELDS)}, ?, ?, ?, ?, ?, ?)""",
                        (ent["id"], *(r[f] if r[f] != "" else None for f in FIELDS), way, at, import_id, import_id,
                         document_id, document_id))
            out["new"] += 1
            continue
        changed = _differs(old, r)
        if at < old["as_at"]:
            out["older" if changed else "unchanged"] += 1
            continue
        out["changed" if changed else "unchanged"] += 1
        sets = {f: (r[f] if r[f] != "" else None) for f in changed}
        if way != old["direction"]:
            sets["direction"] = way
        sets.update(as_at=at, last_import_id=import_id, last_document_id=document_id)
        con.execute(f"UPDATE myinvois_docs SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), old["id"]))
    return out


# ---------- linking to SQL's documents ----------

def doc_key(s):
    """A document number as compared here: capitals, without spaces."""
    return re.sub(r"\s+", "", str(s or "")).upper()


def _mentions(text, no):
    """Whether a document's text names this document number as a word of its own (INV-123, not INV-1234). A number too
    short to tell apart (fewer than 4 letters and digits), or one of digits only shorter than 6 (2026, 1001), is never
    taken as named: such numbers turn up in many descriptions."""
    no = re.sub(r"\s+", " ", str(no or "")).strip().upper()
    bare = re.sub(r"[^A-Z0-9]", "", no)
    if len(bare) < 4 or (bare.isdigit() and len(bare) < 6):
        return False
    return bool(re.search(rf"(?<![A-Z0-9]){re.escape(no)}(?![A-Z0-9])", re.sub(r"\s+", " ", str(text or "")).upper()))


# Words in a company's name that don't tell one supplier from another.
NAME_FILLER = {"SDN", "BHD", "BERHAD", "PLT", "LTD", "LIMITED", "INC", "CO", "CORP", "CORPORATION", "COMPANY", "THE", "AND"}


def _named(s, name):
    """Whether an SQL document's payee or description names this supplier: the first two words of its name that tell
    it apart (one, when that is all it has), each as a word of its own."""
    words = [w for w in re.findall(r"[A-Z0-9]+", str(name or "").upper()) if len(w) >= 3 and w not in NAME_FILLER][:2]
    if not words:
        return False
    payee = s["payee"] if "payee" in s.keys() else ""
    text = " ".join(re.findall(r"[A-Z0-9]+", f"{payee or ''} {s['description'] or ''}".upper()))
    return all(re.search(rf"(?<![A-Z0-9]){w}(?![A-Z0-9])", text) for w in words)


def _plain_invoice(d):
    """Whether an e-Invoice is an ordinary invoice, not a credit, debit or refund note (which never stands for a
    supplier invoice or payment by its amount alone)."""
    t = (d["type"] or "").lower()
    return "invoice" in t and not any(w in t for w in ("credit", "debit", "refund"))


def _near(doc_date, issued):
    """Whether an SQL document's date can be the e-Invoice's: no more than a week before it was issued, and in the
    month it was issued or the next one."""
    try:
        when, day = date.fromisoformat(str(doc_date)[:10]), date.fromisoformat(str(issued)[:10])
    except ValueError:
        return False
    nxt = (day.year + (day.month == 12), day.month % 12 + 1)
    return (when - day).days >= -7 and (when.year, when.month) <= nxt


def _sen_of(s):
    """An SQL document's amount in sen."""
    return int(round((s["amount"] or 0) * 100))


def _best(group):
    """The e-Invoice that speaks for a document number when MyInvois has more than one with it (one cancelled and
    issued again): a valid one, else the latest issued."""
    return max(group, key=lambda x: (x["status"] == "Valid", x["issued_at"] or "", x["as_at"], x["id"]))


def _known_at(con, s):
    """When the e-Invoice on an SQL document was last known: when MyInvois or a paste last set it, else when the
    document was imported."""
    if s["einvoice_as_at"]:
        return s["einvoice_as_at"]
    imp = con.execute("SELECT imported_at FROM sql_imports WHERE id = ?", (s["import_id"],)).fetchone()
    return imp["imported_at"] if imp else None


def _short(uuid):
    return f"{uuid[:8]}…"


def link(con, entity_id):
    """Links the company's MyInvois e-Invoices to its SQL documents, and says what was done, one sentence per document.

    Issued and self-billed: the SQL documents with the same number (capitals and spaces aside) take the e-Invoice's
    UUID and status (Valid as 'Validated', the word a paste of SQL's grid uses), unless what they show was pasted
    after the copy was saved. Ignored documents and those deleted in SQL are left alone; when several share the number
    (another year's), only the one with the e-Invoice's amount, dated no later than its issue, is filled, and none when
    that doesn't settle it. A cancelled, invalid or rejected e-Invoice never replaces another UUID on the document.
    Received: matched to a supplier invoice (PI) or payment voucher by the supplier's document number (its own number,
    or named in its description) whose supplier has the e-Invoice's TIN where Customers and suppliers has it, and
    otherwise the same amount or the supplier's name; else, for an ordinary invoice, by that TIN and the same amount
    when only one document dated near it has both and no other e-Invoice takes it. Returns [sentences]."""
    if not ready(con):
        return []
    notes = []
    docs = con.execute("SELECT * FROM myinvois_docs WHERE entity_id = ? ORDER BY id", (entity_id,)).fetchall()
    entries = con.execute("SELECT * FROM sql_entries WHERE entity_id = ? ORDER BY id", (entity_id,)).fetchall()
    by_no = {}
    for s in entries:
        by_no.setdefault(doc_key(s["doc_no"]), []).append(s)

    def set_link(d, entry_id, how):
        if (d["entry_id"], d["matched_by"]) != (entry_id, how):
            con.execute("UPDATE myinvois_docs SET entry_id = ?, matched_by = ? WHERE id = ?", (entry_id, how, d["id"]))

    groups = {}
    for d in docs:
        if d["direction"] in ("issued", "self_billed"):
            groups.setdefault(doc_key(d["doc_no"]), []).append(d)
    live = lambda s: s["status"] != "ignored" and not (s["deleted_in_sql"] if "deleted_in_sql" in s.keys() else None)
    for key, group in groups.items():
        best = _best(group)
        kind = DIRECTION_WORDS[best["direction"]]
        mine = [s for s in by_no.get(key, []) if live(s)]
        if len(mine) > 1:
            # SQL's numbering restarts each year: only the document with the e-Invoice's amount, dated no later than it
            # was issued, can be it.
            day = (best["issued_at"] or "")[:10]
            mine = [s for s in mine if _sen_of(s) == best["total_sen"] and (not day or str(s["doc_date"] or "")[:10] <= day)]
            if len(mine) != 1:
                for d in group:
                    set_link(d, None, None)
                notes.append(f"{best['doc_no']}: {kind} e-Invoice {_short(best['uuid'])} ({best['status']}) could be more than one "
                             "SQL document with this number, so none was filled in. Check in SQL which one it is.")
                continue
        for d in group:
            set_link(d, mine[0]["id"] if mine else None, "doc_no" if mine else None)
        if not mine:
            notes.append(f"{best['doc_no']}: {kind} e-Invoice {_short(best['uuid'])} ({best['status']}) has no SQL document "
                         "with this number yet; it is filled in once the document is imported.")
            continue
        for s in mine:
            pick = best
            if s["einvoice"] and s["einvoice"] != best["uuid"] and best["status"] != "Valid":
                # A cancelled, invalid or rejected attempt never replaces a UUID it doesn't name: what MyInvois says of
                # the document's own UUID speaks for it, when the copies hold it.
                pick = next((d for d in group if d["uuid"] == s["einvoice"]), None)
                if pick is None:
                    notes.append(f"{s['doc_no']}: kept its e-Invoice {_short(s['einvoice'])} ({s['einvoice_status'] or 'UUID recorded'}); "
                                 f"MyInvois holds only {_short(best['uuid'])} ({best['status']}) for this number.")
                    continue
            word = STATUS_WORDS.get(pick["status"], pick["status"])
            url = link_of(pick)
            if s["einvoice"] == pick["uuid"] and s["einvoice_status"] == word:
                if url and not s["einvoice_link"]:  # a copy with the Long ID gives the page an earlier one lacked
                    con.execute("UPDATE sql_entries SET einvoice_link = ? WHERE id = ?", (url, s["id"]))
                continue
            known = _known_at(con, s)
            if s["einvoice_from"] != "myinvois" and (s["einvoice"] or s["einvoice_status"]) and known and known > pick["as_at"]:
                notes.append(f"{s['doc_no']}: kept its e-Invoice status from SQL ({s['einvoice_status'] or 'UUID recorded'}), "
                             f"pasted after this MyInvois copy was saved.")
                continue
            con.execute("""UPDATE sql_entries SET einvoice = ?, einvoice_status = ?, einvoice_as_at = ?, einvoice_from = 'myinvois',
                           einvoice_link = CASE WHEN ? IS NOT NULL THEN ? WHEN einvoice = ? THEN einvoice_link END WHERE id = ?""",
                        (pick["uuid"], word, pick["as_at"], url, url, pick["uuid"], s["id"]))
            was = s["einvoice_status"]
            notes.append(f"{s['doc_no']}: {kind} e-Invoice {_short(pick['uuid'])} filled in from MyInvois, {word}"
                         + (f" (was {was})" if was and was != word else "") + ".")
    received = [d for d in docs if d["direction"] == "received"]
    if received:
        parties = {}
        for p in con.execute("""SELECT sql_code, tin FROM parties WHERE sql_code IS NOT NULL AND tin IS NOT NULL AND tin <> ''
                                AND (entity_id IS NULL OR entity_id = ?) ORDER BY entity_id IS NULL""", (entity_id,)):
            parties.setdefault(p["sql_code"].strip().upper(), tin_key(p["tin"]))
        has_code = "code" in entries[0].keys() if entries else False
        purchases = [s for s in entries if s["status"] != "ignored" and not (s["deleted_in_sql"] if "deleted_in_sql" in s.keys() else None)
                     and (((s["kind"] or "") == "invoice" and (s["doc_type"] or "").upper() == "PI")
                          or ((s["kind"] or "payment") == "payment" and ((s["doc_type"] or "").upper() in ("PV", "SP", "PM")
                                                                         or s["direction"] == "out")))]

        def party_tin(s):
            return parties.get((s["code"] or "").strip().upper()) if has_code else None

        # By the supplier's number: the document's supplier must have the e-Invoice's TIN where Customers and suppliers
        # has it; where it doesn't, the same amount or the supplier's name on the document must say so too.
        taken, left = set(), []
        for d in received:
            hits = [s for s in purchases if (doc_key(s["doc_no"]) == doc_key(d["doc_no"]) or _mentions(s["description"], d["doc_no"]))
                    and (party_tin(s) == d["supplier_tin"]
                         or (party_tin(s) is None and (_sen_of(s) == d["total_sen"] or _named(s, d["supplier_name"]))))]
            hit = max(hits, key=lambda s: ((s["doc_type"] or "").upper() == "PI", s["id"])) if hits else None
            if hit:
                taken.add(hit["id"])
                set_link(d, hit["id"], "doc_no")
            else:
                left.append(d)
        # Else by TIN and amount: an ordinary invoice in ringgit, to the one document of that supplier with its amount,
        # dated when it can be the e-Invoice's, that no other e-Invoice takes.
        claims = {}
        for d in left:
            issued = d["issued_at"] or d["received_at"]
            hits = [] if d["currency"] != "MYR" or not _plain_invoice(d) or not issued else [
                s for s in purchases if s["id"] not in taken and party_tin(s) == d["supplier_tin"]
                and _sen_of(s) == d["total_sen"] and _near(s["doc_date"], issued)]
            claims[d["id"]] = hits[0]["id"] if len(hits) == 1 else None
        wanted = {}
        for e in claims.values():
            if e:
                wanted[e] = wanted.get(e, 0) + 1
        rest = []
        for d in left:
            e = claims[d["id"]]
            ok = e is not None and wanted[e] == 1  # two e-Invoices after one document: neither is taken for it
            set_link(d, e if ok else None, "tin_amount" if ok else None)
            if ok:
                taken.add(e)
            else:
                rest.append(d)
        _by_amount(con, entity_id, rest, purchases, taken, set_link, party_tin)
    return notes


def _by_amount(con, entity_id, rest, purchases, taken, set_link, party_tin=lambda s: None):
    """The last resort for a received e-Invoice still unmatched, as on real books: a supplier's e-Invoice carries the
    supplier's number, while it is paid by the company's own voucher (an electricity bill paid by PV2611-001), often
    inside a staff claim that pays several receipts at once. So, for an ordinary invoice in ringgit:
    - 'amount': the one payment voucher or supplier invoice, not taken by another e-Invoice, for its amount, dated when
      it can be the e-Invoice's;
    - else 'line': the one current SQL document dated when it can be the e-Invoice's with exactly one line debiting its
      amount to an account other than the bank (the laptop line of a claim voucher).
    A document whose supplier has another TIN in Customers and suppliers never fits. Either is taken only when exactly one document fits and no other e-Invoice wants the same one, and the page says it
    was matched by amount, so it reads as a likely match to look at, not a certainty."""
    from . import ledger
    cands = {}

    def fits_tin(s, d):
        t = party_tin(s)
        return t is None or t == d["supplier_tin"]

    for d in rest:
        issued = d["issued_at"] or d["received_at"]
        if d["currency"] != "MYR" or not _plain_invoice(d) or not issued or not d["total_sen"]:
            continue
        hits = [s for s in purchases if s["id"] not in taken and _sen_of(s) == d["total_sen"] and _near(s["doc_date"], issued)
                and fits_tin(s, d)]
        if len(hits) == 1:
            cands[d["id"]] = (hits[0]["id"], "amount")
    left = [d for d in rest if d["id"] not in cands]
    if left and ledger.ready(con):
        bank = {c.strip().upper() for c in ledger.bank_codes(con, entity_id)}
        by_key = {}
        for s in purchases:
            by_key.setdefault(doc_key(s["doc_no"]), []).append(s)
        lines = con.execute("""SELECT d.doc_key, d.doc_date, l.account_code, l.dr_sen FROM ledger_lines l JOIN ledger_docs d ON d.id = l.doc_id
                               WHERE d.entity_id = ? AND d.state = 'current' AND d.origin = 'sql' AND l.dr_sen > 0""", (entity_id,)).fetchall()
        for d in left:
            issued = d["issued_at"] or d["received_at"]
            if d["currency"] != "MYR" or not _plain_invoice(d) or not issued or not d["total_sen"]:
                continue
            docs = {r["doc_key"] for r in lines if r["dr_sen"] == d["total_sen"] and r["account_code"].strip().upper() not in bank
                    and _near(r["doc_date"], issued)}
            ents = [s for k in docs for s in by_key.get(doc_key(k), []) if s["id"] not in taken and fits_tin(s, d)]
            if len(docs) == 1 and len({s["id"] for s in ents}) == 1:
                cands[d["id"]] = (ents[0]["id"], "line")
    # Else 'sum': one voucher paying several e-Invoices of the same supplier at once (two copier rental invoices of
    # 93.28 and 86.88 paid by one 180.16 voucher), when exactly one group of them and exactly one voucher fit.
    from itertools import combinations
    open_ = [d for d in rest if d["id"] not in cands and d["currency"] == "MYR" and _plain_invoice(d)
             and (d["issued_at"] or d["received_at"]) and d["total_sen"] and d["supplier_tin"]]
    by_tin = {}
    for d in open_:
        by_tin.setdefault(d["supplier_tin"], []).append(d)
    def day(d):
        try:
            return date.fromisoformat(str(d["issued_at"] or d["received_at"])[:10])
        except ValueError:
            return None

    for group in by_tin.values():
        group = [d for d in group if day(d)]
        if len(group) < 2 or len(group) > 40:
            continue
        fits = []
        for n in (2, 3):
            for combo in combinations(group, n):
                days = [day(d) for d in combo]
                if (max(days) - min(days)).days > 45:  # only e-Invoices of about the same billing period are paid together
                    continue
                total = sum(d["total_sen"] for d in combo)
                last = max(d["issued_at"] or d["received_at"] for d in combo)
                hits = [s for s in purchases if s["id"] not in taken and _sen_of(s) == total and _near(s["doc_date"], last)
                        and fits_tin(s, combo[0])]
                if len(hits) == 1:
                    fits.append((combo, hits[0]["id"]))
        # A supplier billing the same amount each month can make one voucher's total from more than one group (this
        # month's two invoices, or last month's first with this month's second). The invoices of one billing period are
        # the ones paid together, so the group whose e-Invoices lie closest together wins, when it is strictly closest;
        # groups are then taken closest first, never reusing an e-Invoice or a voucher. A tie stays unmatched.
        def span(combo):
            ds = [day(d) for d in combo]
            return (max(ds) - min(ds)).days

        best = {}
        for combo, e in fits:
            best.setdefault(e, []).append((span(combo), combo))
        chosen = []
        for e, opts in best.items():
            opts.sort(key=lambda x: x[0])
            if len(opts) == 1 or opts[0][0] < opts[1][0]:
                chosen.append((opts[0][0], opts[0][1], e))
        used = set()
        for _, combo, e in sorted(chosen, key=lambda x: x[0]):
            if any(d["id"] in used for d in combo):
                continue
            for d in combo:
                used.add(d["id"])
                cands[d["id"]] = (e, "sum")
    wanted = {}
    for e, how in cands.values():
        if how != "sum":
            wanted[e] = wanted.get(e, 0) + 1
    for d in rest:
        e, how = cands.get(d["id"], (None, None))
        if e is not None and how == "sum":
            set_link(d, e, how)  # the group shares its one voucher
        elif e is not None and wanted.get(e) == 1 and how != "line":
            set_link(d, e, how)
            taken.add(e)
        elif e is not None and how == "line":
            set_link(d, e, how)  # a claim voucher pays several receipts: other e-Invoices may take other lines of it
        else:
            set_link(d, None, None)


def view(con, ent):
    """What the SQL page shows of MyInvois for a company: {rows: [each e-Invoice with the SQL document it links to],
    unmatched: [the valid e-Invoices received, issued from the first month tracked, found in none of SQL's
    documents], by_entry: {SQL document id: its e-Invoice}, sources: [{name, saved, read_at}], counts: {direction: n}}."""
    if not ready(con):
        return None
    rows = [dict(r) for r in con.execute(
        """SELECT m.*, s.doc_no AS entry_doc_no, s.doc_date AS entry_date, s.kind AS entry_kind
           FROM myinvois_docs m LEFT JOIN sql_entries s ON s.id = m.entry_id
           WHERE m.entity_id = ? ORDER BY COALESCE(m.issued_at, m.received_at, '') DESC, m.id DESC""", (ent["id"],))]
    since = f"{ent['first_month']}-01" if ent["first_month"] else ""
    unmatched = [r for r in rows if r["direction"] == "received" and r["status"] == "Valid" and not r["entry_id"]
                 and (r["issued_at"] or r["received_at"] or "")[:10] >= since]
    by_uuid = {r["uuid"]: r for r in rows}
    by_entry = {}
    for s in con.execute("SELECT id, einvoice FROM sql_entries WHERE entity_id = ? AND einvoice IS NOT NULL", (ent["id"],)):
        r = by_uuid.get(s["einvoice"])
        if r:
            by_entry[s["id"]] = {k: r[k] for k in ("uuid", "type", "status", "validated_at", "direction")}
    sources = [dict(r) for r in con.execute(
        """SELECT d.original_name AS name, MAX(m.as_at) AS saved, d.uploaded_at AS read_at FROM myinvois_docs m
           JOIN documents d ON d.id = m.last_document_id WHERE m.entity_id = ? GROUP BY d.id ORDER BY d.uploaded_at DESC LIMIT 5""",
        (ent["id"],))]
    counts = dict.fromkeys(DIRECTIONS, 0)
    for r in rows:
        counts[r["direction"]] += 1
    return {"rows": rows, "unmatched": unmatched, "by_entry": by_entry, "sources": sources, "counts": counts,
            "since": ent["first_month"]}


def log_line(ent, name, kept):
    return (f"Read MyInvois copy '{name}' for {ent['code']}: {kept['rows']} e-Invoices, {kept['new']} new, "
            f"{kept['changed']} changed, {kept['unchanged']} unchanged"
            + (f", {kept['older']} left as a later copy says" if kept["older"] else ""))
