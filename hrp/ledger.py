"""The account lines of every SQL document, kept as documents with versions (update 26).

SQL Account's GL Journal of Transaction prints every document (payment and receipt vouchers, journals, customer and
supplier invoices) with its account lines. Each document read is kept as a header (ledger_docs) with its lines
(ledger_lines), and each read is a batch (ledger_batches) that says where the figures came from: the file, its period
and the import. A document is (company, origin, doc no.): the same document exported again with the same lines is only
noted as seen; with other lines (or another date) it becomes a new version and the old one is kept, marked superseded.
Account lines are never changed or deleted (the audit trail refuses it): a change in SQL is always a new version.

All amounts here are whole sen (INTEGER), so every comparison is exact; the bank reconciliation still works in RM.

The checks are worked out when asked for, from the chart of accounts and the customers and suppliers as they are now,
so a code entered in Setup later is taken into account at once. Nothing here posts anything to SQL Account.
"""
import json
from datetime import date, datetime, timedelta

from .sqlgl import fingerprint, sen

SINCE = 26
BOOKS = ("bank", "general", "sales", "purchase", "other")
CONTROLS = ("debtor_control", "creditor_control")
REFUSED_HERE = "This company's books are kept in SQL Account: its entries come only from SQL."

# Not in db.SCHEMA: update 26 is the only place they are made, as partybook.TABLES are. No semicolons inside the
# comments, as install splits this text on them.
TABLES = """
CREATE TABLE IF NOT EXISTS ledger_batches (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  origin TEXT NOT NULL CHECK (origin IN ('sql', 'here')),
  report TEXT NOT NULL CHECK (report IN ('journal', 'gl_ledger', 'trial_balance', 'grid', 'legacy', 'entered')),
  sql_import_id INTEGER REFERENCES sql_imports(id),
  document_id INTEGER REFERENCES documents(id),
  file_name TEXT,
  period_from TEXT, period_to TEXT,
  period_source TEXT CHECK (period_source IS NULL OR period_source IN ('printed', 'lines')),
  sections TEXT CHECK (sections IS NULL OR json_valid(sections)),
  summary TEXT CHECK (summary IS NULL OR json_valid(summary)),
  results TEXT CHECK (results IS NULL OR json_valid(results)),
  problems INTEGER NOT NULL DEFAULT 0,
  read_at TEXT NOT NULL,
  CHECK (origin <> 'sql' OR sql_import_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ledger_batches_ent ON ledger_batches (entity_id, report, id);
CREATE TABLE IF NOT EXISTS ledger_docs (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  origin TEXT NOT NULL CHECK (origin IN ('sql', 'here')),
  doc_no TEXT NOT NULL,
  doc_key TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  doc_date TEXT NOT NULL,
  book TEXT NOT NULL CHECK (book IN ('bank', 'general', 'sales', 'purchase', 'other')),
  book_label TEXT,
  description TEXT,
  dr_sen INTEGER NOT NULL, cr_sen INTEGER NOT NULL, line_count INTEGER NOT NULL,
  fingerprint TEXT NOT NULL,
  batch_id INTEGER NOT NULL REFERENCES ledger_batches(id),
  seen_batch_id INTEGER REFERENCES ledger_batches(id),
  state TEXT NOT NULL DEFAULT 'current' CHECK (state IN ('current', 'superseded', 'gone')),
  replaced_by INTEGER REFERENCES ledger_docs(id),
  ended_batch_id INTEGER REFERENCES ledger_batches(id),
  ended_at TEXT,
  UNIQUE (entity_id, origin, doc_key, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS ledger_docs_live ON ledger_docs (entity_id, origin, doc_key) WHERE state <> 'superseded';
CREATE INDEX IF NOT EXISTS ledger_docs_date ON ledger_docs (entity_id, doc_date) WHERE state = 'current';
CREATE TABLE IF NOT EXISTS ledger_lines (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL REFERENCES ledger_docs(id),
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  seq INTEGER NOT NULL,
  account_code TEXT NOT NULL,
  account_name TEXT,
  description TEXT, project TEXT,
  dr_sen INTEGER NOT NULL DEFAULT 0, cr_sen INTEGER NOT NULL DEFAULT 0,
  UNIQUE (doc_id, seq)
);
CREATE INDEX IF NOT EXISTS ledger_lines_acct ON ledger_lines (entity_id, account_code)
"""

# Run on its own (a trigger body holds semicolons). It refuses one direction only: an entry made here for a company kept
# in SQL. SQL history is never refused, so a company that stops using SQL keeps its past documents. Its name is outside
# the audit trail's 'audit_%' triggers, so the trail never drops or rewrites it.
GUARD = f"""CREATE TRIGGER IF NOT EXISTS ledger_guard_here BEFORE INSERT ON ledger_docs
  WHEN NEW.origin = 'here' AND COALESCE((SELECT uses_sql FROM entities WHERE id = NEW.entity_id), 1) = 1
  BEGIN SELECT RAISE(ABORT, '{REFUSED_HERE.replace("'", "''")}'); END"""


class LedgerError(ValueError):
    """What stopped an action, in words for the person using the app."""


# ---------- amounts and identity ----------
# sen and the fingerprint are sqlgl's, so a document read from a file and one kept here are told apart the same way.

_sen = sen
_fingerprint = fingerprint


def _rm(n):
    return None if n is None else n / 100


def _money(n):
    return f"{_rm(n):,.2f}"


def _key(doc_no):
    return str(doc_no or "").strip().upper()


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _iso(d):
    """A date as YYYY-MM-DD, from a date, a datetime, an ISO text or dd/mm/yyyy; None when it is none of these."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    s = str(d).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _period(p):
    """(from, to) of a period given as [from, to], (from, to) or {from, to}; (None, None) when there is none."""
    if not p:
        return None, None
    if isinstance(p, dict):
        return _iso(p.get("from")), _iso(p.get("to"))
    return _iso(p[0]), _iso(p[1])


def _exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


# ---------- update 26 ----------

def install(con):
    """Update 26: the three tables and the guard, then the journal lines pasted until now copied in as documents. The
    audit triggers are made before anything is copied (audit.py: a step that creates a table and fills it refreshes in
    between), so the copied rows are recorded as added by this update, not as a baseline. Nothing is altered or dropped:
    sql_journal_lines stays as it is, and a group of lines whose journal isn't imported yet is left there (the bank
    reconciliation still reads it by document key)."""
    from . import audit
    for stmt in TABLES.split(";"):
        if stmt.strip():
            con.execute(stmt)
    con.execute(GUARD)
    audit.refresh(con)
    copy_pasted(con, None)


def ready(con):
    return con.execute("PRAGMA user_version").fetchone()[0] >= SINCE


def _guard_text(sql):
    return " ".join(str(sql or "").replace("IF NOT EXISTS ", "").split()).lower()


def guard_missing(con):
    """True when update 26 has run but ledger_guard_here is missing or isn't the one update 26 made (another program
    dropped or rewrote it). Its name is outside the audit trail's triggers, so the trail's own checks don't cover it."""
    if not ready(con) or not _exists(con, "ledger_docs"):
        return False
    r = con.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'ledger_guard_here'").fetchone()
    return r is None or _guard_text(r[0]) != _guard_text(GUARD)


def ensure_guard(con):
    """Puts ledger_guard_here back when it is missing or changed (audit.startup runs it at every start). Returns True
    when it did."""
    if not guard_missing(con):
        return False
    con.execute("DROP TRIGGER IF EXISTS ledger_guard_here")
    con.execute(GUARD)
    return True


def journal_header(con, eid, dockey):
    """The journal (its latest pasted row) that has this SQL document key, or None while its header isn't imported."""
    return con.execute("""SELECT * FROM sql_entries WHERE entity_id = ? AND kind = 'journal' AND dockey = ?
                          ORDER BY import_id DESC, id DESC LIMIT 1""", (eid, dockey)).fetchone()


def current_header(con, eid, dockey):
    """The journal header of these pasted lines, only while its document key is still the one the latest listing of its
    number has. A journal deleted and entered again in SQL under the same number gets a new key: the lines pasted under
    the old key belong to the deleted document, and the bank reconciliation never read them for that number, so they
    must not become its lines here either. None when the header isn't imported or isn't the latest."""
    head = journal_header(con, eid, dockey)
    if not head:
        return None
    latest = con.execute("""SELECT dockey FROM sql_entries WHERE entity_id = ? AND kind = 'journal' AND UPPER(TRIM(doc_no)) = ?
                            ORDER BY import_id DESC, id DESC LIMIT 1""", (eid, _key(head["doc_no"]))).fetchone()
    return head if latest and str(latest[0] or "") == str(dockey) else None


# ---------- writing ----------

def new_batch(c, eid, *, origin="sql", report, sql_import_id=None, document_id=None, file_name=None, period_from=None,
              period_to=None, period_source=None, sections=None):
    """One read of SQL figures (a file, a paste, or the copy of pasted lines): where the documents written with it came
    from. Returns its id."""
    return c.execute("""INSERT INTO ledger_batches (entity_id, origin, report, sql_import_id, document_id, file_name, period_from,
                        period_to, period_source, sections, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (eid, origin, report, sql_import_id, document_id, file_name, _iso(period_from), _iso(period_to),
                      period_source, None if sections is None else json.dumps(sections, separators=(",", ":")), _now())).lastrowid


def finish_batch(c, batch_id, summary=None, results=None):
    """Writes what a batch found: its summary and its report checks (problems = how many are warnings)."""
    c.execute("UPDATE ledger_batches SET summary = ?, results = ?, problems = ? WHERE id = ?",
              (None if summary is None else json.dumps(summary, separators=(",", ":")),
               None if results is None else json.dumps(results, separators=(",", ":")),
               sum(1 for r in results or [] if r.get("outcome") == "warn"), batch_id))


def _uses_sql(c, eid):
    r = c.execute("SELECT uses_sql FROM entities WHERE id = ?", (eid,)).fetchone()
    return r is None or r[0] is None or bool(r[0])


def _clean_lines(lines):
    out = []
    for i, x in enumerate(lines, 1):
        out.append({"seq": i, "code": str(x.get("code") or x.get("account_code") or "").strip().upper(),
                    "name": x.get("name") or x.get("account_name"), "description": x.get("description"),
                    "project": x.get("project"), "dr_sen": int(x.get("dr_sen") or 0), "cr_sen": int(x.get("cr_sen") or 0)})
    return out


def _insert_doc(c, eid, origin, batch_id, doc, key, version, lines, fp):
    doc_date = _iso(doc.get("doc_date") or doc.get("date"))
    did = c.execute("""INSERT INTO ledger_docs (entity_id, origin, doc_no, doc_key, version, doc_date, book, book_label, description,
                       dr_sen, cr_sen, line_count, fingerprint, batch_id, seen_batch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (eid, origin, str(doc["doc_no"]).strip(), key, version, doc_date, doc.get("book") or "other",
                     doc.get("book_label"), lines[0]["description"] if lines else None, sum(x["dr_sen"] for x in lines),
                     sum(x["cr_sen"] for x in lines), len(lines), fp, batch_id, batch_id)).lastrowid
    c.executemany("""INSERT INTO ledger_lines (doc_id, entity_id, seq, account_code, account_name, description, project, dr_sen, cr_sen)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  [(did, eid, x["seq"], x["code"], x["name"], x["description"], x["project"], x["dr_sen"], x["cr_sen"]) for x in lines])
    return did


def put_document(c, eid, batch_id, doc):
    """Keeps one document as read: doc = {doc_no, doc_date (or date), book, book_label, lines: [{code, name, description,
    project, dr_sen, cr_sen}], origin (default 'sql')}. The only writer of ledger_docs and ledger_lines. Returns
    {result, id, version, note}, where result is
    - 'new': not seen before (or only in versions since replaced): version 1, or the next number;
    - 'same': the same date and lines as the version kept (only noted as seen in this batch);
    - 'back': the same as a version marked no longer in SQL, which becomes current again;
    - 'changed': other lines or another date: the version kept is superseded (kept, with what replaced it) and this
      becomes the next version. note is "number reused?" when the date moved more than 180 days.
    An entry made here (origin 'here') is refused for a company kept in SQL, here and by ledger_guard_here."""
    origin = doc.get("origin") or "sql"
    if origin not in ("sql", "here"):
        raise LedgerError("A document comes from SQL or is entered here.")
    if origin == "here" and _uses_sql(c, eid):
        raise LedgerError(REFUSED_HERE)
    key = _key(doc["doc_no"])
    if not key:
        raise LedgerError("A document needs its number.")
    doc_date = _iso(doc.get("doc_date") or doc.get("date"))
    if not doc_date:
        raise LedgerError(f"{doc['doc_no']} has no date.")
    lines = _clean_lines(doc.get("lines") or [])
    fp = _fingerprint(doc_date, lines)
    live = c.execute("SELECT * FROM ledger_docs WHERE entity_id = ? AND origin = ? AND doc_key = ? AND state <> 'superseded'",
                     (eid, origin, key)).fetchone()
    if live and live["fingerprint"] == fp:
        if live["state"] == "current":
            c.execute("UPDATE ledger_docs SET seen_batch_id = ? WHERE id = ?", (batch_id, live["id"]))
            return {"result": "same", "id": live["id"], "version": live["version"], "note": None}
        c.execute("UPDATE ledger_docs SET state = 'current', ended_batch_id = NULL, ended_at = NULL, seen_batch_id = ? WHERE id = ?",
                  (batch_id, live["id"]))
        return {"result": "back", "id": live["id"], "version": live["version"], "note": None}
    if live:
        c.execute("UPDATE ledger_docs SET state = 'superseded', ended_batch_id = ?, ended_at = ? WHERE id = ?",
                  (batch_id, _now(), live["id"]))
    top = c.execute("SELECT MAX(version) FROM ledger_docs WHERE entity_id = ? AND origin = ? AND doc_key = ?", (eid, origin, key)).fetchone()[0]
    version = (top or 0) + 1
    did = _insert_doc(c, eid, origin, batch_id, {**doc, "doc_date": doc_date}, key, version, lines, fp)
    note = None
    if live:
        c.execute("UPDATE ledger_docs SET replaced_by = ? WHERE id = ?", (did, live["id"]))
        moved = abs((date.fromisoformat(doc_date) - date.fromisoformat(live["doc_date"])).days)
        note = "number reused?" if moved > 180 else None
    return {"result": "changed" if live else "new", "id": did, "version": version, "note": note}


def mark_gone(c, eid, batch_id, period_from, period_to, books, seen_keys):
    """After a Journal of Transaction is read: the current SQL documents dated in its printed period, in a book it has
    a section for, that it doesn't hold, were deleted (or renumbered) in SQL, and are marked 'gone' (kept, with the
    batch that found it). Only when the batch's period was printed: a period worked out from the lines' own dates can't
    tell a deleted document from one outside the file. Returns [{id, doc_no, doc_date, book}]."""
    b = c.execute("SELECT period_source FROM ledger_batches WHERE id = ?", (batch_id,)).fetchone()
    p_from, p_to = _iso(period_from), _iso(period_to)
    if not b or b["period_source"] != "printed" or not p_from or not p_to:
        return []
    books, seen = set(books), {_key(k) for k in seen_keys}
    gone, at = [], _now()
    for d in c.execute("""SELECT id, doc_no, doc_key, doc_date, book FROM ledger_docs WHERE entity_id = ? AND origin = 'sql'
                          AND state = 'current' AND doc_date BETWEEN ? AND ? ORDER BY doc_date, doc_key""", (eid, p_from, p_to)).fetchall():
        if d["book"] in books and d["doc_key"] not in seen:
            c.execute("UPDATE ledger_docs SET state = 'gone', ended_batch_id = ?, ended_at = ? WHERE id = ?", (batch_id, at, d["id"]))
            gone.append({"id": d["id"], "doc_no": d["doc_no"], "doc_date": d["doc_date"], "book": d["book"]})
    return gone


def copy_pasted(c, eid):
    """Copies journal lines pasted from SQL's grid (sql_journal_lines) into the ledger, for one company or (eid None)
    all: each journal whose header is imported and that the ledger doesn't have yet in any state becomes version 1,
    dated as its header, in a 'legacy' batch per import. Lines whose journal isn't imported yet stay where they are and
    are copied once it is. Lines pasted under a document key the latest listing of its number no longer has (the journal
    was deleted and entered again in SQL) are left where they are too (see current_header). Never deletes anything, and
    running it again copies nothing twice. Returns how many documents it copied."""
    if not _exists(c, "sql_journal_lines"):
        return 0
    groups = c.execute(f"""SELECT entity_id, dockey, MAX(import_id) AS imp FROM sql_journal_lines
                           {'WHERE entity_id = ?' if eid is not None else ''} GROUP BY entity_id, dockey
                           ORDER BY imp DESC, entity_id, dockey""", (eid,) if eid is not None else ()).fetchall()
    batches, n = {}, 0
    for g in groups:
        head = current_header(c, g["entity_id"], g["dockey"])
        if not head:
            continue
        key = _key(head["doc_no"])
        if not key or c.execute("SELECT 1 FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND doc_key = ?",
                                (g["entity_id"], key)).fetchone():
            continue
        at = (g["entity_id"], g["imp"])
        if at not in batches:
            had = c.execute("SELECT id FROM ledger_batches WHERE entity_id = ? AND report = 'legacy' AND sql_import_id = ? ORDER BY id LIMIT 1",
                            at).fetchone()
            if had:
                batches[at] = had["id"]
            else:
                imp = c.execute("SELECT * FROM sql_imports WHERE id = ?", (g["imp"],)).fetchone()
                batches[at] = new_batch(c, g["entity_id"], origin="sql", report="legacy", sql_import_id=g["imp"],
                                        document_id=imp["document_id"] if imp else None, file_name=imp["filename"] if imp else None)
        lines = c.execute("""SELECT * FROM sql_journal_lines WHERE entity_id = ? AND dockey = ? ORDER BY COALESCE(seq, id), id""",
                          (g["entity_id"], g["dockey"])).fetchall()
        put_document(c, g["entity_id"], batches[at], {
            "doc_no": head["doc_no"], "doc_date": head["doc_date"], "book": "general", "book_label": None,
            "lines": [{"code": x["code"], "description": x["description"], "project": x["project"],
                       "dr_sen": _sen(x["dr"]), "cr_sen": _sen(x["cr"])} for x in lines]})
        n += 1
    return n


# ---------- reading: the listing, names and the bank ----------

def _chunks(keys, n=500):
    keys = list(keys)
    for i in range(0, len(keys), n):
        yield keys[i:i + n]


def listing_of(con, eid, keys=None):
    """What SQL's listings say of each document: {doc_key: {doc_no, ids, kind, doc_type, direction, code, doc_date,
    dates, total, total_sen, earlier}}. Only the rows of the latest import of a doc no. count, as in the bank
    reconciliation (a voucher edited in SQL and pasted again), and all of them (a voucher listed on several rows), so
    total is their sum when they go the same way; else None (can't tell). earlier: the totals (sen) of earlier imports.
    A row listed again unchanged stays with the import that first brought it, so when one row of a voucher on several
    rows is edited in SQL, the latest import holds only the edited row: when it holds fewer rows than an earlier import
    did, partial is True and total is None (can't tell), rather than a total that leaves the unchanged rows out.
    can_ignore: every row is still unlinked (only those can be ignored)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(sql_entries)")}
    code = "code" if "code" in cols else "NULL AS code"
    base = f"""SELECT id, import_id, doc_no, doc_date, amount, direction, kind, doc_type, status, {code}
               FROM sql_entries WHERE entity_id = ? AND TRIM(COALESCE(doc_no, '')) <> ''"""
    if keys is None:
        got = con.execute(base + " ORDER BY import_id, id", (eid,)).fetchall()
    else:
        got = []
        for part in _chunks({_key(k) for k in keys}):
            got += con.execute(base + f" AND UPPER(TRIM(doc_no)) IN ({','.join('?' * len(part))}) ORDER BY import_id, id",
                               (eid, *part)).fetchall()
    by = {}
    for r in got:
        by.setdefault(_key(r["doc_no"]), []).append(r)
    out = {}
    for k, rs in by.items():
        last = max(r["import_id"] for r in rs)
        mine = [r for r in rs if r["import_id"] == last]
        dirs = {r["direction"] for r in mine}
        earlier = {}
        for r in rs:
            if r["import_id"] != last:
                earlier.setdefault(r["import_id"], []).append(r)
        partial = len(mine) < max((len(e) for e in earlier.values()), default=0)
        total = sum(_sen(r["amount"]) for r in mine) if len(dirs) == 1 and not partial else None
        out[k] = {"doc_no": mine[0]["doc_no"], "ids": [r["id"] for r in mine], "kind": mine[0]["kind"] or "payment",
                  "doc_type": mine[0]["doc_type"], "direction": mine[0]["direction"] if len(dirs) == 1 else None,
                  "code": next((r["code"] for r in mine if r["code"]), None), "doc_date": min(r["doc_date"] for r in mine),
                  "dates": sorted({r["doc_date"] for r in mine}), "total": _rm(total), "total_sen": total,
                  "ignored": all(r["status"] == "ignored" for r in mine), "partial": partial,
                  "can_ignore": all(r["status"] == "unlinked" for r in mine),
                  "earlier": [sum(_sen(r["amount"]) for r in e) for e in earlier.values()
                              if len({r["direction"] for r in e}) == 1]}
    return out


class _Chart:
    """The company's chart of accounts and customers and suppliers as they are now, for names and control accounts."""

    def __init__(self, con, eid, footer_codes=()):
        from . import partybook
        sql_type = "sql_type" if "sql_type" in {r[1] for r in con.execute("PRAGMA table_info(gl_accounts)")} else "NULL AS sql_type"
        self.accounts = {_key(r["code"]): dict(r) for r in con.execute(
            f"SELECT code, name, type, special, {sql_type} FROM gl_accounts WHERE entity_id = ? ORDER BY active, code", (eid,))}
        self.parties = {}
        for r in con.execute("""SELECT name, sql_code, gl_code, entity_id FROM parties WHERE sql_code IS NOT NULL AND TRIM(sql_code) <> ''
                                AND (entity_id IS NULL OR entity_id = ?) ORDER BY entity_id IS NOT NULL""", (eid,)):
            self.parties[_key(r["sql_code"])] = dict(r)  # the company's own, read last, wins over a shared one
        self.footer = {_key(c) for c in footer_codes if c}
        self.group_type = partybook.GROUP_TYPE

    def control(self, code):
        """The account a code rolls up into: a chart code is its own; a customer's or supplier's code goes to the
        party's control account (its GL code); else the debtor or creditor control (or a ledger footer's Add Code) with
        the same prefix before '-'; else None."""
        code = _key(code)
        if code in self.accounts:
            return code
        p = self.parties.get(code)
        if p and (p["gl_code"] or "").strip():
            return _key(p["gl_code"])
        if "-" not in code:
            return None
        prefix = code.split("-")[0]
        same = lambda k: k.split("-")[0] == prefix and k != code  # noqa: E731
        hits = sorted(k for k, a in self.accounts.items() if same(k) and a["special"] in CONTROLS)
        hits = hits or sorted(k for k in self.accounts if same(k) and k in self.footer)
        hits = hits or sorted(k for k in self.footer if same(k))
        return hits[0] if hits else None

    def is_party_control(self, code):
        """True when the code rolls up into a debtor or creditor control account."""
        ctl = self.control(code)
        return bool(ctl and ((self.accounts.get(ctl) or {}).get("special") in CONTROLS or ctl in self.footer))

    def known(self, code):
        code = _key(code)
        return code in self.accounts or code in self.parties or self.control(code) is not None

    def kind(self, code):
        """'pl' (income or expense), 're' (retained earnings), 'bs' (balance sheet), or None when the chart doesn't say."""
        a = self.accounts.get(_key(code))
        if not a:
            return None
        if a["sql_type"] == "RE":
            return "re"
        t = a["type"] or self.group_type.get(a["sql_type"])
        return "pl" if t in ("income", "expense") else "bs" if t in ("asset", "liability", "equity") else None

    def name(self, code, printed=None):
        """(name, where it came from: 'chart', 'party', 'printed' or None)."""
        code = _key(code)
        if code in self.accounts:
            return self.accounts[code]["name"], "chart"
        p = self.parties.get(code)
        if p:
            ctl = self.control(code)
            return p["name"] + (f" · sub-ledger of {ctl}" if ctl else ""), "party"
        return (printed, "printed") if printed else (None, None)


def control_of(con, eid, code, footer_codes=()):
    """The control account a code rolls up into (see _Chart.control): worked out when asked, never stored, so it follows
    the chart and the customers and suppliers as they are in Setup now."""
    return _Chart(con, eid, footer_codes).control(code)


def account_names(con, eid, codes, printed=None):
    """{code: {name, name_from, control}} from the chart, then the customers and suppliers, then the name SQL printed
    (printed: {code: name})."""
    ch, printed = _Chart(con, eid), printed or {}
    out = {}
    for code in codes:
        k = _key(code)
        name, src = ch.name(k, printed.get(code) or printed.get(k))
        out[k] = {"name": name, "name_from": src, "control": ch.control(k)}
    return out


def bank_codes(con, eid):
    """The company's bank and cash GL codes, upper case: the GL codes of its bank accounts (Setup), the chart's bank and
    cash accounts, and the code the bank reconciliation finds for the cash book."""
    from . import recon
    codes = {_key(r[0]) for r in con.execute("SELECT gl_code FROM accounts WHERE entity_id = ? AND TRIM(COALESCE(gl_code, '')) <> ''", (eid,))}
    codes |= {_key(r[0]) for r in con.execute("SELECT code FROM gl_accounts WHERE entity_id = ? AND special IN ('bank', 'cash')", (eid,))}
    acct = recon.cash_book_account(con, eid)
    code = recon.bank_gl_code(con, acct) if acct else None
    if code:
        codes.add(_key(code))
    return codes


def bank_nets(con, eid, keys, code):
    """What each document moves on one GL code: {doc_key: net sen, debit above 0}, for every key the ledger has any SQL
    document for, in any state. Only the current version counts, so a document no longer in SQL gives 0 (and is never
    read from the pasted lines again)."""
    code = _key(code)
    out = {}
    for part in _chunks({_key(k) for k in keys if k}):
        for r in con.execute(f"""SELECT d.doc_key, COALESCE(SUM(CASE WHEN d.state = 'current' AND l.account_code = ?
                                                                   THEN l.dr_sen - l.cr_sen ELSE 0 END), 0) AS net
                                 FROM ledger_docs d LEFT JOIN ledger_lines l ON l.doc_id = d.id
                                 WHERE d.entity_id = ? AND d.origin = 'sql' AND d.doc_key IN ({','.join('?' * len(part))})
                                 GROUP BY d.doc_key""", (code, eid, *part)):
            out[r["doc_key"]] = r["net"]
    return out


# ---------- per document checks (live) ----------

def _book_of(kind, doc_type):
    from .sqlimport import PURCHASE_DOCS
    if kind == "journal":
        return "general"
    if kind == "invoice":
        return "purchase" if (doc_type or "").upper() in PURCHASE_DOCS else "sales"
    return "bank"


BOOK_WORDS = {"bank": "the Bank Journal", "general": "the General Journal", "sales": "the Sales Journal",
              "purchase": "the Purchase Journal", "other": "another section"}
KIND_WORDS = {"payment": "a payment or receipt", "journal": "a journal", "invoice": "an invoice"}


def _total_check(L, lines, banks, ch):
    """(ok True/False/None, rule, sentence) for the lines against the listing's total. None: can't tell."""
    total, kind = L["total_sen"], L["kind"]
    if total is None:
        if L.get("partial"):
            return None, None, ("Can't tell whether the lines agree with the listing: its latest listing has only some of this "
                                "document's rows (one may have been edited in SQL).")
        return None, None, "Can't tell whether the lines agree with the listing: its rows for this document go both ways."
    dr = sum(x["dr_sen"] for x in lines)
    if kind == "payment":
        if not banks:
            return None, "bank", "Can't tell whether the lines agree with the listing: set the bank account's GL code in Setup."
        per = {}
        for x in lines:
            if x["account_code"] in banks:
                per[x["account_code"]] = per.get(x["account_code"], 0) + x["dr_sen"] - x["cr_sen"]
        net = sum(per.values())

        def fits(n):
            return abs(n) == total and (L["direction"] not in ("in", "out") or (n > 0 if L["direction"] == "in" else n < 0))
        # All the bank codes together, or one of them: money moved between two of the company's own bank accounts nets
        # to nothing over both, but the account the voucher is paid from still moves the listing's amount.
        if fits(net) or any(fits(n) for n in per.values()):
            return True, "bank", None
        way = {"in": "money in", "out": "money out"}.get(L["direction"], "")
        moved = f"{'money in' if net > 0 else 'money out'} of {_money(abs(net))}" if net else "nothing"
        text = (f"The lines on the bank account move {moved}, but the listing has {_money(total)}{' ' + way if way else ''} "
                f"(checked on the bank account's lines).")
        return False, "bank", _earlier(text, abs(net), L)
    if kind == "invoice":
        code = _key(L["code"])
        on = [x for x in lines if code and x["account_code"] == code]
        rule, words = "party", "the customer's or supplier's line"
        if not on:
            on = [x for x in lines if ch.is_party_control(x["account_code"])]
            rule, words = "control", "the debtor or creditor line"
        if on:
            figure = abs(sum(x["dr_sen"] - x["cr_sen"] for x in on))
            if figure == total:
                return True, rule, None
            if dr == total:
                return True, "debits", None
            return False, rule, _earlier(f"{words.capitalize()} comes to {_money(figure)}, but the listing has {_money(total)} "
                                         f"(checked on {words}).", figure, L)
    if dr == total:
        return True, "debits", None
    return False, "debits", _earlier(f"The lines' debits add up to {_money(dr)}, but the listing has {_money(total)} "
                                     f"(checked on the total of the debits).", dr, L)


def _earlier(text, figure, L):
    return text + (" SQL's lines match an earlier listing of this document." if figure in L["earlier"] else "")


def _lines_of(con, ids):
    out = {}
    for part in _chunks(ids):
        for x in con.execute(f"SELECT * FROM ledger_lines WHERE doc_id IN ({','.join('?' * len(part))}) ORDER BY doc_id, seq", part):
            out.setdefault(x["doc_id"], []).append(x)
    return out


def doc_checks(con, eid, keys):
    """The checks on each document's lines, worked out now (nothing is stored, so they follow the chart as it is in
    Setup): {doc_key: {doc_id, doc_no, n, version, state, balanced, total_ok (None: can't tell or no listing), rule,
    unknown (codes the chart doesn't know), warnings (sentences)}}. Only documents the ledger has (current or no longer
    in SQL) are in it. keys: doc nos. or sql_entries rows (anything with doc_no)."""
    keys = {_key(k["doc_no"] if not isinstance(k, str) else k) for k in keys}
    docs = []
    for part in _chunks(keys):
        docs += con.execute(f"""SELECT * FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND state <> 'superseded'
                                AND doc_key IN ({','.join('?' * len(part))})""", (eid, *part)).fetchall()
    if not docs:
        return {}
    lines = _lines_of(con, [d["id"] for d in docs])
    listing = listing_of(con, eid, [d["doc_key"] for d in docs])
    ch, banks = _Chart(con, eid), bank_codes(con, eid)
    out = {}
    for d in docs:
        ls = lines.get(d["id"], [])
        dr, cr = sum(x["dr_sen"] for x in ls), sum(x["cr_sen"] for x in ls)
        warn = []
        if d["state"] == "gone":
            warn.append(f"{d['doc_no']} is no longer in SQL's Journal of Transaction: it was deleted or renumbered in SQL.")
        if dr != cr:
            warn.append(f"Its lines don't balance: the debits add up to {_money(dr)} and the credits to {_money(cr)}.")
        L, total_ok, rule = listing.get(d["doc_key"]), None, None
        if L:
            total_ok, rule, text = _total_check(L, ls, banks, ch)
            if text:
                warn.append(text)
            if d["doc_date"] not in L["dates"]:
                warn.append(f"SQL's journal dates it {d['doc_date']}, but the listing dates it {L['doc_date']}.")
            want = _book_of(L["kind"], L["doc_type"])
            if d["book"] != want and not (L["kind"] == "journal" and d["book"] == "other"):
                warn.append(f"It is in {BOOK_WORDS.get(d['book'], 'another section')} of SQL's journal, but the listing has it as "
                            f"{KIND_WORDS.get(L['kind'], 'another kind of document')}.")
        unknown = [] if not ch.accounts else sorted({x["account_code"] for x in ls if not ch.known(x["account_code"])})
        if not ch.accounts:
            warn.append("Enter the chart of accounts in Setup to check the account codes.")
        elif unknown:
            warn.append(f"Not in the chart of accounts: {', '.join(unknown)}.")
        out[d["doc_key"]] = {"doc_id": d["id"], "doc_no": d["doc_no"], "n": len(ls), "version": d["version"], "state": d["state"],
                             "balanced": dr == cr, "total_ok": total_ok, "rule": rule, "unknown": unknown, "warnings": warn}
    return out


def _journal_books(con, eid):
    """[(from, to, books)] of the company's Journal of Transaction reads with a period."""
    out = []
    for b in con.execute("""SELECT period_from, period_to, sections FROM ledger_batches WHERE entity_id = ? AND report = 'journal'
                            AND period_from IS NOT NULL AND period_to IS NOT NULL ORDER BY id""", (eid,)):
        books = {s.get("book") for s in json.loads(b["sections"] or "[]")}
        out.append((b["period_from"], b["period_to"], books))
    return out


def orphans(con, eid):
    """{no_listing: current SQL documents no listing has, not_in_journal: listing entries dated in a Journal of
    Transaction read, in a book it covered, with no current document (deleted or renumbered in SQL)}. Each entry of
    not_in_journal has all its row ids, and can_ignore: whether every row is still unlinked (a linked voucher, a journal
    or an invoice is never ignored from there: it would show as linked and ignored at once)."""
    listing = listing_of(con, eid)
    docs = con.execute("""SELECT id, doc_no, doc_key, doc_date, book, version FROM ledger_docs WHERE entity_id = ? AND origin = 'sql'
                          AND state = 'current' ORDER BY doc_date, doc_key""", (eid,)).fetchall()
    current = {d["doc_key"] for d in docs}
    no_listing = [{"id": d["id"], "doc_no": d["doc_no"], "doc_date": d["doc_date"], "book": d["book"], "version": d["version"]}
                  for d in docs if d["doc_key"] not in listing]
    reads = _journal_books(con, eid)
    missing = []
    for k, L in sorted(listing.items(), key=lambda kv: (kv[1]["doc_date"], kv[0])):
        if k in current or L["ignored"]:
            continue
        book = _book_of(L["kind"], L["doc_type"])
        if any(f <= L["doc_date"] <= t and book in books for f, t, books in reads):
            missing.append({"ids": L["ids"], "doc_no": L["doc_no"], "doc_date": L["doc_date"], "kind": L["kind"],
                            "doc_type": L["doc_type"], "amount": L["total"], "book": book, "can_ignore": L["can_ignore"]})
    return {"no_listing": no_listing, "not_in_journal": missing}


def doc_view(con, eid, doc_no):
    """One document as SQL's journals gave it: {doc_no, versions (newest first): [{version, state, doc_date, book,
    book_label, batch: {report, file_name, read_at, document_id}, lines: [{seq, code, name, name_from, control,
    description, dr, cr}], totals: {dr, cr}}], checks: [sentences]}. Amounts in RM."""
    key = _key(doc_no)
    docs = con.execute("SELECT * FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND doc_key = ? ORDER BY version DESC",
                       (eid, key)).fetchall()
    ch = _Chart(con, eid)
    lines = _lines_of(con, [d["id"] for d in docs])
    versions = []
    for d in docs:
        b = con.execute("SELECT report, file_name, read_at, document_id FROM ledger_batches WHERE id = ?", (d["batch_id"],)).fetchone()
        ls = []
        for x in lines.get(d["id"], []):
            name, src = ch.name(x["account_code"], x["account_name"])
            ls.append({"seq": x["seq"], "code": x["account_code"], "name": name, "name_from": src, "control": ch.control(x["account_code"]),
                       "description": x["description"], "dr": _rm(x["dr_sen"]), "cr": _rm(x["cr_sen"])})
        versions.append({"version": d["version"], "state": d["state"], "doc_date": d["doc_date"], "book": d["book"],
                         "book_label": d["book_label"], "batch": dict(b) if b else None, "lines": ls,
                         "totals": {"dr": _rm(d["dr_sen"]), "cr": _rm(d["cr_sen"])}})
    checks = doc_checks(con, eid, [key]).get(key, {}).get("warnings", [])
    return {"doc_no": docs[0]["doc_no"] if docs else doc_no, "versions": versions, "checks": checks}


# ---------- report checks (stored with the batch) ----------

def _coverage(con, eid):
    """The dates the company's Journal of Transaction reads cover, merged: [(from, to)]."""
    spans = sorted((f, t) for f, t, _ in _journal_books(con, eid))
    out = []
    for f, t in spans:
        if out and date.fromisoformat(f) <= date.fromisoformat(out[-1][1]) + timedelta(days=1):  # touching spans join
            out[-1] = (out[-1][0], max(out[-1][1], t))
        else:
            out.append((f, t))
    return out


def _intersect(f, t, cover):
    return [(max(f, a), min(t, b)) for a, b in cover if max(f, a) <= min(t, b)]


def _inside(d, window):
    return any(a <= d <= b for a, b in window)


def _lines_in(con, eid, window):
    """{code: [dr sen, cr sen]} of the current SQL documents' lines dated in the window."""
    out = {}
    for a, b in window:
        for r in con.execute("""SELECT l.account_code, SUM(l.dr_sen) AS dr, SUM(l.cr_sen) AS cr FROM ledger_lines l
                                JOIN ledger_docs d ON d.id = l.doc_id WHERE d.entity_id = ? AND d.origin = 'sql' AND d.state = 'current'
                                AND d.doc_date BETWEEN ? AND ? GROUP BY l.account_code""", (eid, a, b)):
            got = out.setdefault(r["account_code"], [0, 0])
            got[0] += r["dr"]
            got[1] += r["cr"]
    return out


def _result(rule, subject, outcome, expected, actual, text):
    return {"rule": rule, "subject": subject, "outcome": outcome, "expected_sen": expected, "actual_sen": actual, "text": text}


def _dates(f, t):
    return f"{date.fromisoformat(f):%d/%m/%Y}-{date.fromisoformat(t):%d/%m/%Y}"


def _roll(lines, targets, ch):
    """The lines' figures per account of a report: a code the report has is its own; one it lacks goes into its control
    account when the report has that. Returns (figures, rolled {control: codes}, left {code: [dr, cr]})."""
    mine, rolled, left = {}, {}, {}
    for code, (dr, cr) in lines.items():
        to = code if code in targets else ch.control(code)
        if to not in targets:
            left[code] = [dr, cr]
            continue
        if to != code:
            rolled.setdefault(to, set()).add(code)
        got = mine.setdefault(to, [0, 0])
        got[0] += dr
        got[1] += cr
    return mine, rolled, left


def _ledger_checks(con, eid, rep):
    rule = "ledger_account"
    f, t = _period(rep.get("period"))
    if not f or not t:
        return [_result(rule, None, "skipped", None, None, "SQL's ledger prints no period, so it can't be compared with the lines.")]
    window = _intersect(f, t, _coverage(con, eid))
    if not window:
        return [_result(rule, None, "skipped", None, None, f"No GL Journal of Transaction read covers the ledger's dates ({_dates(f, t)}), "
                                                              "so its accounts can't be compared with the lines.")]
    res = []
    if window != [(f, t)]:
        res.append(_result(rule, None, "info", None, None, "Compared for " + ", ".join(_dates(a, b) for a, b in window)
                           + f" only: the journals read cover part of the ledger's dates ({_dates(f, t)})."))
    footer = {}
    for x in rep.get("footer") or []:
        if x.get("op") == "add" and x.get("code"):
            got = footer.setdefault(_key(x["code"]), [0, 0])
            got[0] += x.get("dr_sen") or 0
            got[1] += x.get("cr_sen") or 0
    ch = _Chart(con, eid, footer)
    accts = {_key(a["code"]): a for a in rep.get("accounts") or []}
    led = {}
    for code, a in accts.items():
        got = led.setdefault(code, [0, 0])
        for r in a.get("rows") or []:  # B/F and rows with no reference (PROFIT/(LOSS)) are not documents: left out
            if _inside(_iso(r.get("date")) or "", window):
                got[0] += r.get("dr_sen") or 0
                got[1] += r.get("cr_sen") or 0
    # The footer's Add Code amounts are the control accounts' movements over the ledger's whole period: they can be
    # added only when the lines read cover all of it. Otherwise those accounts are not compared, and say why.
    whole = window == [(f, t)]
    for code, (dr, cr) in footer.items():
        got = led.setdefault(code, [0, 0])
        if whole:
            got[0] += dr
            got[1] += cr
    mine, rolled, left = _roll(_lines_in(con, eid, window), set(led), ch)
    controls = set(rolled) | set(footer)
    agree = 0
    for code in sorted(footer) if not whole else []:
        name = ch.name(code, (accts.get(code) or {}).get("name"))[0] or ""
        res.append(_result(rule, code, "skipped", None, None,
                           f"{f'{code} {name}'.strip()}: not compared, as SQL's ledger gives its movements (Add Code) for "
                           f"{_dates(f, t)} only as a whole, and the journals read don't cover all those dates."))
    for code in sorted(set(led) | set(mine)):
        if not whole and code in footer:
            continue
        L, M = led.get(code, [0, 0]), mine.get(code, [0, 0])
        name = ch.name(code, (accts.get(code) or {}).get("name"))[0] or ""
        label = f"{code} {name}".strip()
        if L == M:
            agree += 1
            continue
        if code in controls:
            if L[0] - L[1] == M[0] - M[1]:
                agree += 1
                continue
            res.append(_result(rule, code, "warn", L[0] - L[1], M[0] - M[1],
                               f"{label}: SQL's ledger nets {_money(L[0] - L[1])}, the lines {_money(M[0] - M[1])} (sub-ledger roll-up)."))
        elif code not in mine:
            res.append(_result(rule, code, "warn", L[0] - L[1], 0, f"{label}: SQL's ledger has debits of {_money(L[0])} and credits of "
                                                                    f"{_money(L[1])}, but no line of the journals read is on it."))
        else:
            res.append(_result(rule, code, "warn", L[0] - L[1], M[0] - M[1],
                               f"{label}: SQL's ledger has debits of {_money(L[0])} and credits of {_money(L[1])}; the lines have "
                               f"{_money(M[0])} and {_money(M[1])} (a difference of {_money((M[0] - M[1]) - (L[0] - L[1]))})."))
    for code, (dr, cr) in sorted(left.items()):
        res.append(_result(rule, code, "warn", 0, dr - cr, f"{code}: the lines have debits of {_money(dr)} and credits of {_money(cr)}, "
                                                           "but SQL's ledger has no such account."))
    res.append(_result(rule, None, "ok", None, None, f"{agree} account{'s agree' if agree != 1 else ' agrees'} with the lines."))
    return res


def _balance_at(acct, as_at):
    """An account's running balance in the ledger at the last row dated on or before as_at, else its B/F."""
    best = None
    for r in (acct.get("rows") or []) + (acct.get("virtual") or []):
        d = _iso(r.get("date"))
        if d and d <= as_at and r.get("bal_sen") is not None and (best is None or d >= best[0]):
            best = (d, r["bal_sen"])
    return best[1] if best else acct.get("bf_sen") or 0


def _net(pair):
    pair = pair or (0, 0)
    return (pair[0] or 0) - (pair[1] or 0)


def _pl_comparable(accts, mine, ch):
    """Whether the trial balance's profit and loss Month To Date can be compared with the lines (mine: the lines dated
    from the 1st of the as-at month, by account), told from the P&L figures themselves rather than from the printed
    period, which says nothing about where the financial year starts. In the year's first month SQL's year-end closing
    sits in Month To Date, while Year To Date started again and equals the lines; in a later month Year To Date also
    holds the earlier months, while Month To Date equals the lines. Comparable when some account reads as a later month
    and none as a closing month, or when every account agrees on both (nothing was closed); anything else can't be
    told apart, and the accounts are skipped."""
    pl = [code for code in accts if ch.kind(code) == "pl"]
    if not pl:
        return False
    closing = later = 0
    all_agree = True
    for code in pl:
        m, mtd, ytd = _net(mine.get(code)), _net(accts[code].get("mtd")), _net(accts[code].get("ytd"))
        closing += ytd == m and mtd != m
        later += ytd != m and mtd == m
        all_agree = all_agree and mtd == m
    return not closing and (later > 0 or all_agree)


def _footer_net(ledger_rep):
    """{code: net sen} of the ledger footer's Add Code movements (debit above 0)."""
    out = {}
    for x in (ledger_rep or {}).get("footer") or []:
        if x.get("op") == "add" and x.get("code"):
            k = _key(x["code"])
            out[k] = out.get(k, 0) + (x.get("dr_sen") or 0) - (x.get("cr_sen") or 0)
    return out


def _tb_checks(con, eid, rep, ledger_rep):
    res = []
    as_at = _period(rep.get("period"))[1]
    if not as_at:
        return [_result("tb_mtd", None, "skipped", None, None, "The trial balance prints no as-at date, so it can't be checked.")]
    accts = {_key(a["code"]): a for a in rep.get("accounts") or []}
    ch = _Chart(con, eid)
    start = as_at[:8] + "01"

    # 1. Month To Date against the lines dated from the 1st of the month to the as-at date.
    rule = "tb_mtd"
    if not any(a <= start and as_at <= b for a, b in _coverage(con, eid)):
        res.append(_result(rule, None, "skipped", None, None, f"No GL Journal of Transaction read covers {_dates(start, as_at)}, "
                                                              "so Month To Date can't be compared with the lines."))
    else:
        mine, rolled, left = _roll(_lines_in(con, eid, [(start, as_at)]), set(accts), ch)
        later_month = _pl_comparable(accts, mine, ch)
        agree, held = 0, []
        for code in sorted(set(accts) | set(mine)):
            T = tuple((accts.get(code) or {}).get("mtd") or (0, 0))
            M = mine.get(code, [0, 0])
            if ch.kind(code) in ("pl", "re", None) and not later_month:
                held.append(code)
                continue
            same = (T[0] == M[0] and T[1] == M[1]) if (T[0] and T[1]) else _net(T) == M[0] - M[1]
            if same:
                agree += 1
                continue
            label = f"{code} {ch.name(code, (accts.get(code) or {}).get('name'))[0] or ''}".strip()
            res.append(_result(rule, code, "warn", _net(T), M[0] - M[1],
                               f"{label}: the trial balance's Month To Date nets {_money(_net(T))}, the lines dated "
                               f"{_dates(start, as_at)} {_money(M[0] - M[1])}" + (" (sub-ledger roll-up)." if code in rolled else ".")))
        for code, (dr, cr) in sorted(left.items()):
            res.append(_result(rule, code, "warn", 0, dr - cr, f"{code}: the lines dated {_dates(start, as_at)} net {_money(dr - cr)}, "
                                                               "but the trial balance has no such account."))
        if held:
            res.append(_result(rule, None, "skipped", None, None,
                               f"{len(held)} profit and loss, retained earnings or unclassified account{'s' if len(held) != 1 else ''} "
                               "not compared: the month may hold SQL's year-end closing."))
        res.append(_result(rule, None, "ok", None, None, f"{agree} account{'s agree' if agree != 1 else ' agrees'} with the lines for the month."))

    # 2. Balance-sheet Year To Date against the ledger's running balance; 3. what the year-end closing moved.
    rule = "tb_balance"
    lf, lt = _period((ledger_rep or {}).get("period"))
    if not ledger_rep or not lf or not lt or not (lf <= as_at <= lt):
        res.append(_result(rule, None, "skipped", None, None, f"No SQL ledger read covers {date.fromisoformat(as_at):%d/%m/%Y}, "
                                                              "so the balances can't be compared."))
        return res
    led = {_key(a["code"]): a for a in ledger_rep.get("accounts") or []}
    footer = _footer_net(ledger_rep)
    agree, closed, compared_pl, warned, unsure = 0, 0, 0, 0, []
    for code, a in sorted(accts.items()):
        la = led.get(code)
        if not la:
            continue
        kind = ch.kind(code)
        bal, ytd = _balance_at(la, as_at), _net(a.get("ytd"))
        # A debtor or creditor control account: the Level 1 ledger prints no rows for it, only its B/F, and gives its
        # movements in the footer (Add Code) for the whole period. Its balance is known only at the period's end.
        sub = (code in footer or (ch.accounts.get(code) or {}).get("special") in CONTROLS) \
            and not (la.get("rows") or la.get("virtual"))
        if sub and kind == "bs":
            if as_at != lt:
                unsure.append(code)
                continue
            bal = (la.get("bf_sen") or 0) + footer.get(code, 0)
        if kind == "pl":
            closed += bal - ytd
            compared_pl += 1
            continue
        if kind != "bs":
            continue
        if bal == ytd:
            agree += 1
            continue
        label = f"{code} {ch.name(code, a.get('name'))[0] or ''}".strip()
        warned += 1
        res.append(_result(rule, code, "warn", ytd, bal, f"{label}: the trial balance's Year To Date nets {_money(ytd)}, SQL's ledger "
                                                         f"balance at {date.fromisoformat(as_at):%d/%m/%Y} is {_money(bal)}."))
    for code in unsure:
        label = f"{code} {ch.name(code, accts[code].get('name'))[0] or ''}".strip()
        res.append(_result(rule, code, "skipped", None, None,
                           f"{label}: not compared, as SQL's ledger prints no lines for this debtor or creditor control account, "
                           f"only its movements for {_dates(lf, lt)} as a whole, and the trial balance is dated "
                           f"{date.fromisoformat(as_at):%d/%m/%Y}."))
    if not agree and not warned and not unsure:
        res.append(_result(rule, None, "skipped", None, None, "No balance-sheet account could be compared: set the account types "
                                                              "in the chart of accounts in Setup."))
    else:
        res.append(_result(rule, None, "ok", None, None, f"{agree} balance-sheet account{'s agree' if agree != 1 else ' agrees'} with SQL's ledger."))
    if compared_pl and closed:
        # closed is the profit and loss accounts' balances that SQL zeroed at the year start (debit above 0): a credit
        # net is a profit carried into retained earnings, a debit net a loss.
        what = f"a profit of {_money(-closed)}" if closed < 0 else f"a loss of {_money(closed)}"
        res.append(_result("tb_year_close", None, "info", None, closed,
                           f"At the start of the financial year SQL moved {what} from the profit and loss accounts into retained "
                           "earnings. No document carries that move, so profit and loss Period To Date is not compared."))
    return res


def report_checks(con, eid, batch, rep, kind, ledger_rep=None):
    """The checks of SQL's ledger (kind 'gl_ledger') or trial balance ('trial_balance') against the current lines, as
    results to store with the batch: [{rule, subject, outcome ('ok' | 'warn' | 'skipped' | 'info'), expected_sen,
    actual_sen, text}]. A check that can't run says why; none passes silently. For a trial balance, ledger_rep is the
    ledger the caller read again from its stored file (None: the balance check is skipped). batch: the batch row (kept
    for the caller's reference; the dates come from the report)."""
    if kind == "gl_ledger":
        return _ledger_checks(con, eid, rep)
    if kind == "trial_balance":
        return _tb_checks(con, eid, rep, ledger_rep)
    return []


# ---------- the bank reconciliation of signed-off months ----------

def recon_snapshot(con, ent, months):
    """{month: {in, out}} of the cash book's books for the given months whose statement is signed off, to tell which
    signed-off months a read changes. Nothing is ever un-signed: the change is only reported."""
    from . import recon
    acct = recon.cash_book_account(con, ent["id"])
    if not acct:
        return {}
    out = {}
    for m in sorted(set(months)):
        st = con.execute("SELECT reconciled_at FROM statements WHERE account_id = ? AND month = ?", (acct["id"], m)).fetchone()
        if st and st["reconciled_at"]:
            mv = recon.movements(con, ent, acct, m)
            out[m] = {"in": mv["in"], "out": mv["out"]}
    return out


def recon_changed(before, after):
    """[{month, before, after}] of the signed-off months whose books moved between two snapshots."""
    return [{"month": m, "before": before[m], "after": after.get(m)} for m in sorted(before) if before[m] != after.get(m)]


# ---------- a fetch of SQL's general-ledger reports ----------

NOT_SQL = "This company's books aren't kept in SQL Account, so SQL's account lines and reports can't be kept for it."
REPORT_ORDER = {"journal": 0, "gl_ledger": 1, "trial_balance": 2}
NO_PERIOD = "No period printed: documents deleted in SQL can't be told from this file."


def _ordered(gl):
    """The reports in the order they are applied: journals first, the oldest saved first so the newest wins, then the
    ledgers, then the trial balances (which are checked against the lines and the ledger kept before them)."""
    return sorted(gl, key=lambda g: (REPORT_ORDER.get(g["kind"], 9), g.get("saved") or "", g["name"].lower()))


def _period_words(p):
    f, t = _period(p)
    if f and t:
        return _dates(f, t)
    return f"as at {date.fromisoformat(t):%d/%m/%Y}" if t else "no period printed"


def _bank_code(con, eid):
    """The cash book account and its GL code (upper case), as the bank reconciliation finds them."""
    from . import recon
    acct = recon.cash_book_account(con, eid)
    code = recon.bank_gl_code(con, acct) if acct else None
    return acct, (_key(code) or None)


def _signed_off(con, acct, month):
    if not acct:
        return False
    st = con.execute("SELECT reconciled_at FROM statements WHERE account_id = ? AND month = ?", (acct["id"], month)).fetchone()
    return bool(st and st["reconciled_at"])


def _journal_keys(con, eid, keys):
    """{doc_key: dockey} of the journals the listings have under these numbers (the key finds their pasted lines)."""
    if "dockey" not in {r[1] for r in con.execute("PRAGMA table_info(sql_entries)")}:
        return {}
    out = {}
    for part in _chunks({_key(k) for k in keys}):
        for r in con.execute(f"""SELECT doc_no, dockey FROM sql_entries WHERE entity_id = ? AND kind = 'journal'
                                 AND UPPER(TRIM(doc_no)) IN ({','.join('?' * len(part))}) ORDER BY import_id, id""", (eid, *part)):
            out[_key(r["doc_no"])] = r["dockey"] or out.get(_key(r["doc_no"]))
    return out


def _held(con, eid, key):
    """The live version the ledger holds of a document (current or no longer in SQL), or None."""
    if not ready(con):
        return None
    r = con.execute("""SELECT doc_no, doc_key, doc_date, book, fingerprint, state FROM ledger_docs WHERE entity_id = ?
                       AND origin = 'sql' AND doc_key = ? AND state <> 'superseded'""", (eid, key)).fetchone()
    return dict(r) if r else None


def preview(con, eid, gl, listed=()):
    """What keeping these reports would do, worked out without writing anything (the fetch preview):
    {refused (a sentence, or None), files: [{name, kind, title, period, docs, lines, new, changed, same, back, gone, note}
    for a journal, {name, kind, title, period, accounts, note} for a ledger or trial balance], totals {docs, lines, new,
    changed, same, back, gone}, gone: [{doc_no, doc_date, book, payment, bank_move}], counting: {bank_code, journals:
    [{doc_no, doc_date, month, amount, before, listed, signed_off}], signed_off: [months]}}.
    The journals are taken in the order Import applies them, so a document in two files ends as the newer one says.
    listed: the doc nos. of the journals in the listings the same fetch is importing (they count once imported)."""
    from . import recon
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    acct, code = _bank_code(con, eid)
    totals = dict.fromkeys(("docs", "lines", "new", "changed", "same", "back", "gone"), 0)
    files, gone, after = [], [], {}   # after: doc_key -> what the ledger would hold once the files before it are kept
    for g in _ordered(gl):
        rep = g["rep"]
        f = {"name": g["name"], "kind": g["kind"], "title": rep["title"], "period": _period_words(rep.get("period"))}
        if g["kind"] != "journal":
            files.append({**f, "accounts": len(rep.get("accounts") or []), "note": "Checked against the account lines on import."})
            continue
        n = dict.fromkeys(("new", "changed", "same", "back", "gone"), 0)
        seen = set()
        for d in rep["docs"]:
            k, day, lines = _key(d["doc_no"]), _iso(d.get("date") or d.get("doc_date")), _clean_lines(d["lines"])
            fp = _fingerprint(day, lines)
            was = after.get(k) or _held(con, eid, k)
            n["new" if not was else ("same" if was["state"] == "current" else "back") if was["fingerprint"] == fp else "changed"] += 1
            seen.add(k)
            after[k] = {"doc_no": d["doc_no"], "doc_key": k, "doc_date": day, "book": d["book"], "fingerprint": fp, "state": "current",
                        "bank": sum(x["dr_sen"] - x["cr_sen"] for x in lines if code and x["code"] == code)}
        p_from, p_to = _period(rep.get("period"))
        note = None
        if rep.get("period_source") == "printed" and p_from and p_to:
            books = {s["book"] for s in rep["sections"]}
            held = [dict(r) for r in con.execute("""SELECT doc_no, doc_key, doc_date, book, fingerprint, state FROM ledger_docs
                                                    WHERE entity_id = ? AND origin = 'sql' AND state = 'current' AND doc_date BETWEEN ? AND ?""",
                                                 (eid, p_from, p_to)) if r["doc_key"] not in after] if ready(con) else []
            held += [x for x in after.values() if x["state"] == "current" and p_from <= x["doc_date"] <= p_to]
            for x in held:
                if x["book"] in books and x["doc_key"] not in seen:
                    n["gone"] += 1
                    after[x["doc_key"]] = {**x, "state": "gone", "bank": 0}
                    gone.append({"doc_no": x["doc_no"], "doc_date": x["doc_date"], "book": x["book"]})
        else:
            note = NO_PERIOD
        lines_n = sum(len(d["lines"]) for d in rep["docs"])
        files.append({**f, "docs": len(rep["docs"]), "lines": lines_n, **n, "note": note})
        totals["docs"] += len(rep["docs"])
        totals["lines"] += lines_n
        for k in n:
            totals[k] += n[k]
    # what each document no longer in SQL was linked to, and what it moves on the bank now
    keys = [x["doc_no"] for x in gone]
    now_bank = bank_nets(con, eid, keys, code) if code and keys and ready(con) else {}
    gone_listing = listing_of(con, eid, keys) if keys else {}
    for x in gone:
        p = con.execute("""SELECT p.description FROM sql_entries s JOIN payments p ON p.id = s.payment_id WHERE s.entity_id = ?
                           AND UPPER(TRIM(s.doc_no)) = ? ORDER BY s.id DESC LIMIT 1""", (eid, _key(x["doc_no"]))).fetchone()
        x["payment"] = p["description"] if p else None
        x["bank_move"] = _rm(now_bank.get(_key(x["doc_no"]))) or None
        # A listed journal counts in the bank reconciliation by its lines, in the month of its listing row: once no
        # longer in SQL it stops counting there. A voucher keeps counting from its listing, so nothing changes for it.
        L = gone_listing.get(_key(x["doc_no"]))
        x["month"], x["signed_off"] = (_listing_month(con, acct, L["dates"]) if L and L["kind"] == "journal" and x["bank_move"]
                                       else (None, False))
    # the journals that start counting in the bank reconciliation (or count another figure)
    counting, listed = [], {_key(k) for k in listed}
    if code:
        moving = [x for x in after.values() if x["state"] == "current" and x["bank"]]
        listing = listing_of(con, eid, [x["doc_no"] for x in moving]) if moving else {}
        dockeys = _journal_keys(con, eid, [x["doc_no"] for x in moving]) if moving else {}
        for x in sorted(moving, key=lambda x: (x["doc_date"], x["doc_key"])):
            L = listing.get(x["doc_key"])
            if x["doc_key"] in listed:
                L = {**(L or {}), "kind": "journal"}
            if (L and L["kind"] != "journal") or (not L and x["book"] not in ("general", "other")):
                continue  # vouchers and receipts count from the listing, as before
            before = recon.journal_moves(con, eid, [(x["doc_no"], dockeys.get(x["doc_key"]))], code).get(x["doc_key"])
            if before is not None and _sen(before) == x["bank"]:
                continue
            # The bank reconciliation files a journal under its listing row's date, which SQL's journal may date
            # otherwise (re-dated in SQL): the month is the listing's once it is listed, the journal's until then.
            month, signed = _listing_month(con, acct, (L or {}).get("dates") or [x["doc_date"]])
            counting.append({"doc_no": x["doc_no"], "doc_date": x["doc_date"], "month": month, "amount": _rm(x["bank"]),
                             "before": before, "listed": bool(L), "signed_off": signed})
    return {"refused": None if ent["uses_sql"] else NOT_SQL, "files": files, "totals": totals, "gone": gone,
            "counting": {"bank_code": code, "journals": counting,
                         "signed_off": sorted({x["month"] for x in counting + gone if x.get("signed_off")})}}


def _listing_month(con, acct, dates):
    """(month, signed off) of the dates a document is listed on: the first signed-off month among them, else the first."""
    months = sorted({str(d)[:7] for d in dates if d})
    signed = [m for m in months if _signed_off(con, acct, m)]
    return (signed[0], True) if signed else (months[0] if months else None, False)


def _fetch_months(con, eid, gl):
    """The months whose bank reconciliation keeping these journals can change: the journals' own dates, and the
    listing dates of every document they hold or may mark no longer in SQL (the current documents dated in a printed
    period), as the bank reconciliation files a journal under its listing row's date."""
    keys, months = set(), set()
    for g in gl:
        if g["kind"] != "journal":
            continue
        rep = g["rep"]
        for d in rep["docs"]:
            keys.add(_key(d["doc_no"]))
            if d.get("date"):
                months.add(str(_iso(d["date"]) or d["date"])[:7])
        p_from, p_to = _period(rep.get("period"))
        if rep.get("period_source") == "printed" and p_from and p_to and ready(con):
            for r in con.execute("""SELECT doc_key, doc_date FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND state = 'current'
                                    AND doc_date BETWEEN ? AND ?""", (eid, p_from, p_to)):
                keys.add(r["doc_key"])
                months.add(r["doc_date"][:7])
    for L in (listing_of(con, eid, keys) if keys else {}).values():
        months |= {str(d)[:7] for d in L["dates"] if d}
    return months


def _stored_ledger(con, eid, as_at):
    """SQL's ledger read again from the file kept for the latest ledger read whose period holds the date, or None."""
    from .docstore import path_of
    from .sqlreport import ReportError, read
    for d in con.execute("""SELECT d.* FROM ledger_batches b JOIN documents d ON d.id = b.document_id WHERE b.entity_id = ?
                            AND b.report = 'gl_ledger' AND b.period_from <= ? AND b.period_to >= ? ORDER BY b.id DESC""",
                         (eid, as_at, as_at)).fetchall():
        try:
            got = read(path_of(d).read_bytes())
        except (OSError, ReportError):
            continue
        if got and got[0] == "gl_ledger":
            return got[1]
    return None


def apply_fetch(c, ent, imp, gl):
    """Keeps SQL's general-ledger reports a fetch read, in the import's transaction (imp: its sql_imports id): each
    file as an 'sqlexport' document (its fingerprint is how the next fetch knows it is done), one batch per file, every
    document of a Journal of Transaction kept by put_document (the oldest file first, so the newest wins) and the ones
    SQL no longer has marked, then the ledger and the trial balance checked against the lines, their results stored.
    The bank reconciliation of signed-off months is worked out before and after: a month that moved is reported (in
    the journals' summary and the activity log), never un-signed. Returns {files: [{name, kind, title, period,
    batch_id, summary, results, problems}], recon_changed}. Refused for a company whose books aren't kept in SQL."""
    from .docstore import store
    if not ent["uses_sql"]:
        raise LedgerError(NOT_SQL)
    eid = ent["id"]
    before = recon_snapshot(c, ent, _fetch_months(c, eid, gl))
    files, journals, checked = [], [], []
    for g in _ordered(gl):
        rep, kind = g["rep"], g["kind"]
        p_from, p_to = _period(rep.get("period"))
        did = store(c, entity=ent, month=g["month"], folder="_SQL exports", doc_type="sqlexport", filename=g["name"], data=g["data"])
        source = rep.get("period_source") if kind == "journal" else ("printed" if p_to else None)
        batch = new_batch(c, eid, origin="sql", report=kind, sql_import_id=imp, document_id=did, file_name=g["name"],
                          period_from=p_from, period_to=p_to, period_source=source,
                          sections=rep.get("sections") if kind == "journal" else None)
        f = {"name": g["name"], "kind": kind, "title": rep["title"], "period": _period_words(rep.get("period")), "batch_id": batch,
             "results": [], "problems": 0}
        if kind == "journal":
            s = dict.fromkeys(("new", "changed", "same", "back"), 0)
            reused = []
            for d in rep["docs"]:
                got = put_document(c, eid, batch, {**d, "origin": "sql"})
                s[got["result"]] += 1
                if got["note"]:
                    reused.append(d["doc_no"])
            gone = mark_gone(c, eid, batch, p_from, p_to, {x["book"] for x in rep["sections"]}, [d["doc_no"] for d in rep["docs"]])
            f["summary"] = {"docs": len(rep["docs"]), "lines": sum(len(d["lines"]) for d in rep["docs"]), **s, "gone": len(gone),
                            "gone_docs": [x["doc_no"] for x in gone], "reused": reused,
                            "note": None if source == "printed" else NO_PERIOD}
            journals.append(f)
        else:
            f["summary"] = {"accounts": len(rep.get("accounts") or [])}
            checked.append((f, rep))
        files.append(f)
    copy_pasted(c, eid)
    for f, rep in checked:
        led = None
        if f["kind"] == "trial_balance":
            as_at = _period(rep.get("period"))[1]
            led = _stored_ledger(c, eid, as_at) if as_at else None
        f["results"] = report_checks(c, eid, None, rep, f["kind"], led)
        f["problems"] = sum(1 for r in f["results"] if r["outcome"] == "warn")
        finish_batch(c, f["batch_id"], f["summary"], f["results"])
    changed = recon_changed(before, recon_snapshot(c, ent, before))
    for f in journals:
        f["summary"]["recon_changed"] = changed
        finish_batch(c, f["batch_id"], f["summary"], [])
    return {"files": files, "recon_changed": changed}


def log_line(ent, f):
    """The activity log's line for one report kept, in words."""
    s = f.get("summary") or {}
    head = f"Read {f['title']} '{f['name']}' for {ent['code']}, {f['period']}"
    if f["kind"] == "journal":
        text = (f"{head}: {s['docs']} documents ({s['new']} new, {s['changed']} changed, {s['same']} unchanged, "
                + (f"{s['back']} back in SQL, " if s["back"] else "") + f"{s['gone']} no longer in SQL), {s['lines']} lines")
        if s.get("recon_changed"):
            text += "; bank reconciliation changed for signed-off " + ", ".join(x["month"] for x in s["recon_changed"])
        return text
    what = "ledger check" if f["kind"] == "gl_ledger" else "trial balance check"
    n = f.get("problems") or 0
    return f"{head}: {s.get('accounts', 0)} accounts; {what}: {n} difference{'s' if n != 1 else ''}"


# ---------- what the SQL page shows ----------

def entry_lines(con, eid, entries):
    """For the SQL page: {entry id: {n, version, state, balanced, total_ok, unknown, warnings (how many)}} of the
    listing entries the ledger has lines for (checked now), and {n: 0} for one dated in a Journal of Transaction read
    that covered its book but has no document for it."""
    if not ready(con):
        return {}
    entries = [x for x in entries if (x.get("doc_no") or "").strip()]
    checks = doc_checks(con, eid, [x["doc_no"] for x in entries]) if entries else {}
    reads = _journal_books(con, eid)
    out = {}
    for x in entries:
        ch = checks.get(_key(x["doc_no"]))
        if ch:
            out[x["id"]] = {**{k: ch[k] for k in ("n", "version", "state", "balanced", "total_ok", "unknown")}, "warnings": len(ch["warnings"])}
        elif any(f <= x["doc_date"] <= t and _book_of(x.get("kind"), x.get("doc_type")) in books for f, t, books in reads):
            out[x["id"]] = {"n": 0}
    return out


def latest_reads(con, eid):
    """{report: the latest read of each of SQL's general-ledger reports: {id, file_name, read_at, period_from, period_to,
    period_source, summary, results, problems, document_id}}."""
    if not ready(con):
        return {}
    out = {}
    for kind in REPORT_ORDER:
        b = con.execute("""SELECT id, file_name, read_at, period_from, period_to, period_source, summary, results, problems, document_id
                           FROM ledger_batches WHERE entity_id = ? AND report = ? ORDER BY id DESC LIMIT 1""", (eid, kind)).fetchone()
        if b:
            out[kind] = {**dict(b), "summary": json.loads(b["summary"] or "null"), "results": json.loads(b["results"] or "[]")}
    return out


def import_lines(con, eid):
    """{sql_imports id: how many account lines the documents first kept with that import hold}."""
    if not ready(con):
        return {}
    return {r[0]: r[1] for r in con.execute("""SELECT b.sql_import_id, SUM(d.line_count) FROM ledger_batches b JOIN ledger_docs d
                                               ON d.batch_id = b.id WHERE b.entity_id = ? GROUP BY b.sql_import_id""", (eid,))}
