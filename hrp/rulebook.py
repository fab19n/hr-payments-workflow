"""Payment types, document types and the documents each payment type needs: kept in records.db from update 20 and
edited in Setup, read through get(con).

Below update 20 (an older records.db while its update steps run, or a test that stops short of it) get(con) gives the
values rules.py has always had, frozen: an update step never reads a table a later step creates. From update 20 on it
reads the tables. The answer is cached on the connection, keyed on the records.db's update number; Setup's writes call
forget(con).

The documents a payment needs are kept as dated sets (required_sets): for a payment type, from a payroll month and, when
the set ends, to a month (not included), for every company (entity_id NULL) or one company. A payment takes the set in
force for its payroll month (payments.month): its company's own if it has one then, else the one for every company,
else, for a type that has none, the 'other' type's (as rules.required_docs always did). So a change made from a month on
never alters a month before it, and filed months keep the rules they were checked with.
"""
import json

from . import rules

SINCE = 20
# Payment types the code itself relies on: their key can't change and they can't be deleted.
SYSTEM_TYPES = ("salary", "director", "statutory", "claim_overseas", "receipt", "other")
# Of those, the ones that can't be stopped either (the app would stop working for them).
UNSTOPPABLE_TYPES = ("salary", "director", "statutory", "receipt", "other")
# Every seeded document type is the code's own; these may still be stopped once the checklist and reminders (Setup) no longer ask for them.
STOPPABLE_DOCS = ("approval", "portal", "claim", "payroll", "payslip")
# What several payments of a type are called in Next up (Pay 8 AISB bills and statutory); none: bills.
PLURALS = {"salary": "salaries", "director": "salaries", "consultant": "consultant fees", "statutory": "statutory",
           "claim": "claims", "claim_overseas": "claims", "transfer": "transfers", "receipt": "receipts"}


class Rules:
    """The rules as one records.db (or rules.py) has them."""

    def __init__(self, types, docs, sets, from_tables):
        self.from_tables = from_tables
        self.types = types                  # key -> {label, plural, direction, legal_due (offset, day) | None, system, active, sort}
        self.docs = docs                    # key -> {label, singular, plural, pack_order, from_sql, system, active, sort}
        self.sets = sets                    # [{payment_type, entity_id, from_month, to_month, docs}]
        self.categories = {k: v["label"] for k, v in types.items()}
        self.doc_types = {k: v["label"] for k, v in docs.items()}
        self.sql_only = {k for k, v in docs.items() if v["from_sql"]}
        self.doc_order = {k: v["pack_order"] for k, v in docs.items() if v["pack_order"] is not None}
        self.doc_counted = {k: (v["singular"], v["plural"]) for k, v in docs.items() if v["singular"] and v["plural"]}

    # ---- payment types ----
    def label(self, category):
        return self.categories.get(category, category)

    def active_type(self, category):
        t = self.types.get(category)
        return bool(t and t["active"])

    def direction(self, category):
        t = self.types.get(category)
        return t["direction"] if t else "out"

    def legal_due(self, category):
        t = self.types.get(category)
        return t["legal_due"] if t else None

    def plural(self, category):
        """What several payments of the type are called in a sentence; a type with none is a bill."""
        t = self.types.get(category)
        return (t and t["plural"]) or "bills"

    # ---- document types ----
    def doc_label(self, t):
        return self.doc_types.get(t, t)

    def short_doc(self, t):
        """A document type's short name, e.g. Official Receipt for Official Receipt (SQL)."""
        return self.doc_label(t).split(" (")[0]

    def counted(self, t, n):
        """n documents of the type in words: 1 payment voucher, 3 payment vouchers."""
        one, many = self.doc_counted.get(t, (self.short_doc(t),) * 2)
        return many if n > 1 else one

    def order(self, t, missing=99):
        return self.doc_order.get(t, missing)

    # ---- required documents ----
    def set_for(self, category, month=None, entity_id=None):
        """The set in force for the payment type in that payroll month (None: the latest), for that company: its own,
        else the one for every company; None when the type has none."""
        def live(s):
            if month is None:
                return s["to_month"] is None
            return s["from_month"] <= month and (s["to_month"] is None or month < s["to_month"])
        found = [s for s in self.sets if s["payment_type"] == category and live(s)]
        own = [s for s in found if entity_id is not None and s["entity_id"] == entity_id]
        every = [s for s in found if s["entity_id"] is None]
        return (own or every or [None])[0]

    def required_docs(self, category, uses_sql, month=None, entity_id=None):
        """The documents a payment of the type needs in that payroll month: the set in force (a type with none takes
        the 'other' type's), without the ones only SQL Account issues for a company not kept in SQL."""
        s = self.set_for(category, month, entity_id) or self.set_for("other", month, entity_id)
        docs = s["docs"] if s else []
        return [d for d in docs if uses_sql or d not in self.sql_only]


def _frozen():
    order = {d: i for i, d in enumerate(rules.DOC_ORDER)}
    types = {k: {"label": v, "plural": PLURALS.get(k), "direction": "in" if k == "receipt" else "out",
                 "legal_due": tuple(rules.LEGAL_DUE[k]) if k in rules.LEGAL_DUE else None, "system": int(k in SYSTEM_TYPES),
                 "active": 1, "sort": i} for i, (k, v) in enumerate(rules.CATEGORIES.items())}
    docs = {k: {"label": v, "singular": rules.DOC_COUNTED.get(k, (None, None))[0], "plural": rules.DOC_COUNTED.get(k, (None, None))[1],
                "pack_order": order.get(k), "from_sql": int(k in rules.SQL_ONLY), "system": 1, "active": 1, "sort": i}
            for i, (k, v) in enumerate(rules.DOC_TYPES.items())}
    sets = [{"payment_type": k, "entity_id": None, "from_month": "0000-00", "to_month": None, "docs": list(v)}
            for k, v in rules.REQUIRED_DOCS.items()]
    return Rules(types, docs, sets, from_tables=False)


FROZEN = _frozen()


def from_tables(con):
    """The rules as the tables have them (no version check: update 20's own check uses it)."""
    def rows(sql):
        cur = con.execute(sql)
        names = [c[0] for c in cur.description]
        return [dict(zip(names, tuple(r))) for r in cur.fetchall()]
    types = {r["key"]: {"label": r["label"], "plural": r["plural"], "direction": r["direction"],
                        "legal_due": (r["legal_due_offset"], r["legal_due_day"]) if r["legal_due_day"] is not None else None,
                        "system": r["system"], "active": r["active"], "sort": r["sort"]}
             for r in rows("SELECT * FROM payment_types ORDER BY sort, id")}
    docs = {r["key"]: {k: r[k] for k in ("label", "singular", "plural", "pack_order", "from_sql", "system", "active", "sort")}
            for r in rows("SELECT * FROM doc_types ORDER BY sort, id")}
    sets = [{"payment_type": r["payment_type"], "entity_id": r["entity_id"], "from_month": r["from_month"],
             "to_month": r["to_month"], "docs": json.loads(r["docs"])}
            for r in rows("SELECT * FROM required_sets ORDER BY id")]
    return Rules(types, docs, sets, from_tables=True)


def get(con):
    """The rules for this records.db: the tables from update 20 on, rules.py's values before it."""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    cached = getattr(con, "_rulebook", None)
    if cached is not None and cached[0] == v:
        return cached[1]
    r = from_tables(con) if v >= SINCE else FROZEN
    try:
        con._rulebook = (v, r)
    except AttributeError:
        pass  # a plain sqlite3 connection can't hold it: read again next time
    return r


def forget(con):
    """After a change to the tables, so the next get(con) reads them again."""
    try:
        con._rulebook = None
    except AttributeError:
        pass


# ---------- update 20 ----------

TABLES = """
CREATE TABLE IF NOT EXISTS payment_types (
  id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL, plural TEXT,
  direction TEXT NOT NULL DEFAULT 'out' CHECK (direction IN ('out', 'in')),
  legal_due_offset INTEGER CHECK (legal_due_offset IS NULL OR legal_due_offset IN (0, 1)),
  legal_due_day INTEGER CHECK (legal_due_day IS NULL OR legal_due_day BETWEEN 1 AND 31),
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT,
  CHECK ((legal_due_offset IS NULL) = (legal_due_day IS NULL))
);
CREATE TABLE IF NOT EXISTS doc_types (
  id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, label TEXT NOT NULL, singular TEXT, plural TEXT, pack_order INTEGER,
  from_sql INTEGER NOT NULL DEFAULT 0, system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS required_sets (
  id INTEGER PRIMARY KEY, payment_type TEXT NOT NULL, entity_id INTEGER REFERENCES entities(id),
  from_month TEXT NOT NULL, to_month TEXT, docs TEXT NOT NULL CHECK (json_valid(docs)), set_at TEXT,
  CHECK (to_month IS NULL OR to_month > from_month)
);
CREATE INDEX IF NOT EXISTS required_sets_type ON required_sets (payment_type, from_month)
"""


def install(con):
    """Update 20: the three tables, filled with the values rules.py has (payment types in their order, the legal due
    date of statutory payments, Next up's words for several payments; document types with their counted names, pack
    order and which come from SQL Account; one set of required documents per payment type for every company, from the
    start). Then a check that the tables read back exactly as rules.py: any difference stops the update, so the records
    can't come out of it judged by other rules."""
    from . import audit
    for stmt in TABLES.split(";"):
        if stmt.strip():
            con.execute(stmt)
    audit.refresh(con)  # the rows below go into the audit trail as added, not as a baseline
    f = FROZEN
    for k, t in f.types.items():
        due = t["legal_due"] or (None, None)
        con.execute("""INSERT OR IGNORE INTO payment_types (key, label, plural, direction, legal_due_offset, legal_due_day, system, active, sort)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""", (k, t["label"], t["plural"], t["direction"], due[0], due[1], t["system"], t["sort"]))
    for k, d in f.docs.items():
        con.execute("""INSERT OR IGNORE INTO doc_types (key, label, singular, plural, pack_order, from_sql, system, active, sort)
                       VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?)""", (k, d["label"], d["singular"], d["plural"], d["pack_order"], d["from_sql"], d["sort"]))
    if not con.execute("SELECT 1 FROM required_sets").fetchone():
        for s in f.sets:
            con.execute("INSERT INTO required_sets (payment_type, entity_id, from_month, to_month, docs) VALUES (?, NULL, '0000-00', NULL, ?)",
                        (s["payment_type"], json.dumps(s["docs"])))
    t = from_tables(con)
    for name in ("categories", "doc_types", "sql_only", "doc_order", "doc_counted"):
        if getattr(t, name) != getattr(f, name) or (name in ("categories", "doc_types") and list(getattr(t, name)) != list(getattr(f, name))):
            raise RuntimeError(f"Update 20 stopped: the {name} it wrote don't read back as rules.py has them.")
    if any((t.types[k]["legal_due"], t.types[k]["direction"], t.plural(k)) != (f.types[k]["legal_due"], f.types[k]["direction"], f.plural(k))
           for k in f.types):
        raise RuntimeError("Update 20 stopped: the payment types it wrote don't read back as rules.py has them.")
    for k in list(f.types) + ["no-such-type"]:
        for uses_sql in (0, 1):
            if t.required_docs(k, uses_sql, "2026-01", 1) != f.required_docs(k, uses_sql):
                raise RuntimeError(f"Update 20 stopped: the documents required for {k} don't read back as rules.py has them.")
    forget(con)
