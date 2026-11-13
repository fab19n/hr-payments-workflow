"""The monthly checklist, the joiner and leaver reminders and the matching words: kept in records.db from update 21 and
edited in Setup, read through get(con).

Below update 21 (an older records.db while its update steps run, or a test that stops short of it) get(con) gives the
values the code has always had, frozen: rules.CHECKLIST and its TASK_* rules, rules.PEOPLE_TASKS, Next up's deadline
and reminder names, and the words SQL imports are guessed and filed by. From update 21 on it reads the tables. The
answer is cached on the connection, keyed on the records.db's update number; Setup's writes call forget(con).

The checklist is kept per company as items (a code that never changes, and how the item is shown done: by hand, by the
month's payments, by the bank statements, by the audit pack) and their terms: what the item is from a payroll month on
(and, when it ends, to a month, not included): its due date, title, detail, documents, whether Next up shows it as a
deadline, and, for one shown done by payments, which payments and documents. A month set up gets the items whose term
in force for that month is in use; an item is judged by the term in force for the month of the checklist item in
question, so a change made from a month on never alters the months before it, and filed months keep the rules they
were checked with. Reminders are kept the same way, their terms picked by the month of the person's start date or last
day. The matching words aren't dated: they act on SQL imports from now on, and nothing stored is guessed or filed again.
"""
import json
import sqlite3

from . import rules, sqlimport

SINCE = 21
# How an item is shown done, in the order Setup offers them: (key, label, the code a built-in one always has)
COMPLETIONS = [("hand", "Ticked by hand", None), ("payments", "Payments with their documents", None),
               ("statements", "Bank statements imported", "statement"),
               ("statements_balanced", "Statements balanced, every line explained", "records"),
               ("reconciled", "Statements reconciled", "recon"),
               ("pack", "Audit pack built (ticked when the month is filed)", "file")]
BUILT_IN = {code: key for key, _, code in COMPLETIONS if code}  # code -> completion
STATEMENTS_ARG = {"statements": False, "statements_balanced": True, "reconciled": "reconciled"}  # db._from_statements
REMINDER_PREFIXES = ("joiner-", "leaver-")

# Until update 21 these lived in nextup.py and app.py; they are the values the tables are filled with.
DEADLINES = ("kwsp", "perkeso", "epcb", "einv-rental", "einv-selfbilled", "budget")
SUBMIT = {"kwsp": "KWSP", "perkeso": "PERKESO", "epcb": "e-PCB"}
PEOPLE_NAMES = {"ecp22": "e-CP22 to LHDN", "perkeso": "PERKESO registration", "kwsp": "KWSP registration",
                "stamp": "stamping of the appointment letter", "cp22a": "CP22A to LHDN"}
OVERSEAS_PROVIDERS = ("ANTHROPIC", "CLAUDE", "GOOGLE", "OPENAI", "CHATGPT", "MICROSOFT", "ADOBE", "ZOOM", "CANVA", "DROPBOX", "HOSTGATOR")
GUESS = [("Overseas services", OVERSEAS_PROVIDERS + ("SUBSCRIPTION",), "claim_overseas"), ("Claims", ("CLAIM",), "claim"),
         ("Salaries", ("SALARY",), "salary"),
         ("Stamp duty and tax instalments (not the month's PCB)", ("STAMP", "SETEM", "CP204", "CP500", "TAX INSTAL"), "other"),
         ("Statutory", ("KWSP", "PERKESO", "LHDN", "HASIL", "SOCSO"), "statutory"), ("Rental", ("RENTAL",), "rental"),
         ("Utilities and telco", ("ELECTRIC", "WATER", "INTERNET", "BROADBAND", "TELCO", "TELEPHONE"), "utility")]
FILING_LABELS = {"payroll-jv": "Payroll journals", "fund-received": "From the related company",
                 "einv-rental": "Invoices to the office tenant"}


def _frozen_completion(code):
    if code in rules.TASK_PAYMENTS:
        return "payments", rules.TASK_PAYMENTS[code]
    if code in rules.TASK_STATEMENTS:
        return {False: "statements", True: "statements_balanced", "reconciled": "reconciled"}[rules.TASK_STATEMENTS[code]], None
    if code == rules.TASK_PACK:
        return "pack", None
    return "hand", None


def is_reminder(code):
    return code.startswith(REMINDER_PREFIXES)


def _live(t, month):
    return t["from_month"] <= month and (t["to_month"] is None or month < t["to_month"])


class Book:
    """The checklist, reminders and words as one records.db (or the code) has them."""

    def __init__(self, items=None, terms=None, people=None, pterms=None, guess=None, hints=None, filing=None, filing_codes=None):
        self.from_tables = items is not None
        self.items = items or {}            # (entity_id, code) -> {id, entity_id, code, completion, system, name}
        self.terms = terms or {}            # item id -> [term] by from_month
        self._people = people               # [{id, key, kind, short_name, sort}] in (sort, id) order
        self._pterms = pterms or {}         # people task key -> [term]
        self.guess = guess if guess is not None else [(words, cat) for _, words, cat in GUESS]
        self.hints = hints if hints is not None else dict(sqlimport.CATEGORY_HINTS)
        self.filing = filing if filing is not None else list(sqlimport.TASK_RULES)
        self.filing_codes = filing_codes or [None] * len(self.filing)  # per rule: (company or None, a party's SQL code)

    # ---- the checklist ----
    def checklist(self, ent, month):
        """The items a month set up gets, in order: [{code, due_offset, due_day, title, detail, docs, sort}]."""
        if not self.from_tables:
            return [{"code": code, "due_offset": off, "due_day": day, "title": title, "detail": detail, "docs": list(docs), "sort": i}
                    for i, (code, (off, day), title, detail, docs) in enumerate(rules.CHECKLIST.get(ent["code"], []))]
        out = []
        for (eid, code), it in self.items.items():
            t = eid == ent["id"] and next((t for t in self.terms.get(it["id"], []) if _live(t, month)), None)
            if t and t["in_use"]:
                out.append({**t, "code": code, "item_id": it["id"]})
        return sorted(out, key=lambda t: (t["sort"], t["item_id"]))

    def term(self, entity_id, code, month):
        """The term in force for the item in that month; for a month before its first term, its first; None: no such item."""
        it = self.items.get((entity_id, code))
        ts = it and self.terms.get(it["id"])
        if not ts:
            return None
        return next((t for t in ts if _live(t, month)), None) or (ts[0] if month < ts[0]["from_month"] else ts[-1])

    def completion(self, entity_id, code, month):
        """How a checklist item of that code and month is shown done: (completion, payments rule or None)."""
        if is_reminder(code):
            return "hand", None
        if not self.from_tables:
            return _frozen_completion(code)
        it = self.items.get((entity_id, code))
        if not it:
            return "hand", None
        t = self.term(entity_id, code, month)
        return it["completion"], (t["rule"] if t and it["completion"] == "payments" else None)

    def einvoice_rules(self, entity_id, month):
        """[(code, rule)] of the items shown done by payments that take e-Invoices filed on the item, in order."""
        if not self.from_tables:
            return [(c, r) for c, r in rules.TASK_PAYMENTS.items() if "einvoice" in r.get("on_item", ())]
        out = []
        for (eid, code), it in self.items.items():
            if eid == entity_id and it["completion"] == "payments":
                t = self.term(eid, code, month)
                if t and t["rule"] and "einvoice" in t["rule"].get("on_item", ()):
                    out.append((t["sort"], it["id"], code, t["rule"]))
        return [(c, r) for _, _, c, r in sorted(out)]

    def deadline(self, entity_id, code, month):
        """Whether Next up shows the item as a deadline outside the office (rule 1)."""
        if not self.from_tables:
            return code in DEADLINES
        t = self.term(entity_id, code, month)
        return bool(t and t["deadline"])

    def submit_as(self, entity_id, code, month):
        """The name an item is submitted as when several due the same day make one Next up row (KWSP), else None."""
        if not self.from_tables:
            return SUBMIT.get(code)
        t = self.term(entity_id, code, month)
        return (t and t["deadline"] and t["submit_as"]) or None

    def order(self, entity_id, code, month):
        if not self.from_tables:
            return list(SUBMIT).index(code) if code in SUBMIT else len(SUBMIT)
        t = self.term(entity_id, code, month)
        return t["sort"] if t else 1 << 30

    def due_of(self, entity_id, code, month, fallback):
        """(month offset, day) a company's item of that code is due in that month (the statement, the audit pack), else
        fallback (a company without one)."""
        if not self.from_tables:
            return fallback
        t = self.term(entity_id, code, month)
        return (t["due_offset"], t["due_day"]) if t and _live(t, month) and t["in_use"] else fallback

    # ---- joiner and leaver reminders ----
    def people(self):
        """Every reminder rule, stopped ones too, in order: [{key, kind, short_name, sort}]."""
        if self._people is None:
            return [{"key": key, "kind": kind, "short_name": PEOPLE_NAMES.get(key), "sort": i}
                    for i, (kind, key, *_) in enumerate(rules.PEOPLE_TASKS)]
        return self._people

    def people_term(self, key, event_month):
        """What the rule asks for a person whose start date or last day is in that month: {days, salary_over, title,
        detail, docs}, or None (stopped then, or no such rule)."""
        if self._people is None:
            for kind, k, days, over, title, detail, docs in rules.PEOPLE_TASKS:
                if k == key:
                    return {"days": days, "salary_over": over, "title": title, "detail": detail, "docs": list(docs)}
            return None
        t = next((t for t in self._pterms.get(key, []) if _live(t, event_month)), None)
        return t if t and t["in_use"] else None

    def people_name(self, key):
        return next((p["short_name"] for p in self.people() if p["key"] == key), None)


FROZEN = Book()


def _rows(con, sql, *args):
    cur = con.execute(sql, args)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, tuple(r))) for r in cur.fetchall()]


def from_tables(con):
    """The book as the tables have it (no version check: update 21's own check uses it)."""
    items = {(r["entity_id"], r["code"]): r for r in _rows(con, "SELECT * FROM checklist_items ORDER BY id")}
    terms = {}
    for t in _rows(con, "SELECT * FROM checklist_terms ORDER BY item_id, from_month, id"):
        t["docs"] = json.loads(t["docs"])
        t["rule"] = json.loads(t["rule"]) if t["rule"] else None
        terms.setdefault(t["item_id"], []).append(t)
    people = _rows(con, "SELECT * FROM people_tasks ORDER BY sort, id")
    keys = {p["id"]: p["key"] for p in people}
    pterms = {}
    for t in _rows(con, "SELECT * FROM people_task_terms ORDER BY people_task_id, from_month, id"):
        t["docs"] = json.loads(t["docs"])
        pterms.setdefault(keys.get(t["people_task_id"]), []).append(t)
    guess = [(tuple(json.loads(r["words"])), r["payment_type"])
             for r in _rows(con, "SELECT * FROM guess_words WHERE active = 1 ORDER BY sort, id")]
    hints = {}
    for r in _rows(con, "SELECT * FROM hint_words WHERE active = 1 ORDER BY sort, id"):
        hints[r["payment_type"]] = hints.get(r["payment_type"], ()) + tuple(json.loads(r["words"]))
    rows = _rows(con, "SELECT * FROM filing_words WHERE active = 1 ORDER BY sort, id")
    filing = [({r["doc_kind"]}, r["direction"], tuple(json.loads(r["words"])), r["checklist_code"]) for r in rows]
    parties = {}
    if any(r.get("party_id") for r in rows):  # update 22: a rule can name a customer or supplier
        parties = {p["id"]: (p["entity_id"], (p["sql_code"] or "").upper())
                   for p in _rows(con, "SELECT id, entity_id, sql_code FROM parties WHERE active = 1 AND sql_code IS NOT NULL")}
    codes = [parties.get(r.get("party_id")) for r in rows]
    return Book(items, terms, people, pterms, guess, hints, filing, codes)


def get(con):
    """The book for this records.db: the tables from update 21 on, the code's values before it."""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    cached = getattr(con, "_checklistbook", None)
    if cached is not None and cached[0] == v:
        return cached[1]
    b = from_tables(con) if v >= SINCE else FROZEN
    try:
        con._checklistbook = (v, b)
    except AttributeError:
        pass  # a plain sqlite3 connection can't hold it: read again next time
    return b


def forget(con):
    try:
        con._checklistbook = None
    except AttributeError:
        pass


def fill(text, **values):
    """A reminder's title or detail with {name} and {date} filled in (no other braces are allowed in them)."""
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text


# ---------- update 21 ----------

TABLES = """
CREATE TABLE IF NOT EXISTS checklist_items (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), code TEXT NOT NULL,
  completion TEXT NOT NULL DEFAULT 'hand'
    CHECK (completion IN ('hand', 'payments', 'statements', 'statements_balanced', 'reconciled', 'pack')),
  system INTEGER NOT NULL DEFAULT 0, name TEXT, notes TEXT,
  UNIQUE (entity_id, code)
);
CREATE TABLE IF NOT EXISTS checklist_terms (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES checklist_items(id),
  from_month TEXT NOT NULL, to_month TEXT, in_use INTEGER NOT NULL DEFAULT 1,
  due_offset INTEGER NOT NULL CHECK (due_offset BETWEEN -12 AND 12),
  due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
  title TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', docs TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(docs)),
  deadline INTEGER NOT NULL DEFAULT 0, submit_as TEXT, rule TEXT CHECK (rule IS NULL OR json_valid(rule)),
  sort INTEGER NOT NULL DEFAULT 0, set_at TEXT,
  CHECK (to_month IS NULL OR to_month > from_month)
);
CREATE INDEX IF NOT EXISTS checklist_terms_item ON checklist_terms (item_id, from_month);
CREATE TABLE IF NOT EXISTS people_tasks (
  id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL CHECK (kind IN ('joiner', 'leaver')),
  short_name TEXT, system INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS people_task_terms (
  id INTEGER PRIMARY KEY, people_task_id INTEGER NOT NULL REFERENCES people_tasks(id),
  from_month TEXT NOT NULL, to_month TEXT, in_use INTEGER NOT NULL DEFAULT 1,
  days INTEGER NOT NULL CHECK (days BETWEEN -366 AND 366), salary_over REAL,
  title TEXT NOT NULL, detail TEXT NOT NULL, docs TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(docs)), set_at TEXT,
  CHECK (to_month IS NULL OR to_month > from_month)
);
CREATE INDEX IF NOT EXISTS people_task_terms_task ON people_task_terms (people_task_id, from_month);
CREATE TABLE IF NOT EXISTS guess_words (
  id INTEGER PRIMARY KEY, label TEXT NOT NULL, words TEXT NOT NULL CHECK (json_valid(words)), payment_type TEXT NOT NULL,
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS hint_words (
  id INTEGER PRIMARY KEY, label TEXT NOT NULL, words TEXT NOT NULL CHECK (json_valid(words)), payment_type TEXT NOT NULL,
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS filing_words (
  id INTEGER PRIMARY KEY, label TEXT NOT NULL, words TEXT NOT NULL CHECK (json_valid(words)),
  doc_kind TEXT NOT NULL CHECK (doc_kind IN ('invoice', 'journal', 'payment')),
  direction TEXT CHECK (direction IS NULL OR direction IN ('in', 'out')), checklist_code TEXT NOT NULL,
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT
)
"""
WORD_TABLES = ("guess_words", "hint_words", "filing_words")


def add_item(con, entity_id, code, completion, system, term, from_month="0000-00", in_use=1):
    """An item and its first term (term: due_offset, due_day, title, detail, docs, deadline, submit_as, rule, sort)."""
    iid = con.execute("INSERT INTO checklist_items (entity_id, code, completion, system, name) VALUES (?, ?, ?, ?, ?)",
                      (entity_id, code, completion, system, term["title"])).lastrowid
    add_term(con, iid, term, from_month, in_use)
    return iid


def add_term(con, item_id, term, from_month, in_use=1, set_at=None):
    con.execute("""INSERT INTO checklist_terms (item_id, from_month, to_month, in_use, due_offset, due_day, title, detail,
                   docs, deadline, submit_as, rule, sort, set_at) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, from_month, in_use, term["due_offset"], term["due_day"], term["title"], term["detail"] or "",
                 json.dumps(term["docs"]), int(bool(term.get("deadline"))), term.get("submit_as"),
                 json.dumps(term["rule"]) if term.get("rule") else None, term["sort"], set_at))


def _frozen_term(code, i, off, day, title, detail, docs):
    kind, rule = _frozen_completion(code)
    return kind, {"due_offset": off, "due_day": day, "title": title, "detail": detail, "docs": list(docs),
                  "deadline": int(code in DEADLINES), "submit_as": SUBMIT.get(code),
                  "rule": json.loads(json.dumps(rule)) if rule else None, "sort": i}


def seed_company(con, ent, starter=False):
    """Without starter (update 21 itself, and a new install's seed.json, which is loaded after the update steps), a
    company whose code the code had a checklist for gets those items, built in, as it would have before update 21; any
    other company is left without one, as before. With starter (a company added in Setup, or imported without a
    checklist of its own) every company, whatever its code, gets the starter checklist (starter_items) as items it may
    change, stop or delete: the per-code lists name the first install's own arrangements. Nothing for a company that
    has items."""
    if con.execute("SELECT 1 FROM checklist_items WHERE entity_id = ?", (ent["id"],)).fetchone():
        return
    frozen = None if starter else rules.CHECKLIST.get(ent["code"])
    if frozen is not None:
        for i, (code, (off, day), title, detail, docs) in enumerate(frozen):
            kind, term = _frozen_term(code, i, off, day, title, detail, docs)
            add_item(con, ent["id"], code, kind, 1, term)
    elif starter:
        for code, kind, term in starter_items(con, ent.get("uses_sql", 1)):
            add_item(con, ent["id"], code, kind, 0, term)


# A setup template's starter checklist (setupfile), kept in app_settings under this key, which General settings doesn't
# show (appsettings.SPEC leaves it out): a JSON list of {code, completion, title, detail, due_offset, due_day, docs,
# deadline, submit_as, rule}, in order. Kept there rather than in a table of its own so no update step is needed; it is
# audited and backed up with the other settings.
STARTER_KEY = "starter_checklist"


def stored_starter(con):
    """The starter checklist a setup template brought, or None (the code's, rules.STARTER, is used)."""
    try:
        r = con.execute("SELECT value FROM app_settings WHERE key = ?", (STARTER_KEY,)).fetchone()
    except sqlite3.OperationalError:  # below update 19: no settings table
        return None
    return json.loads(r[0]) if r else None


def starter_items(con, uses_sql=1):
    """The starter checklist a new company gets, as [(code, completion, term)] in order: the one a setup template brought,
    else rules.STARTER. A company not kept in SQL Account goes without the items asking for SQL vouchers."""
    stored = stored_starter(con)
    if stored is None:
        items = [(code, *_frozen_term(code, i, off, day, title, detail, docs))
                 for i, (code, (off, day), title, detail, docs) in enumerate(rules.STARTER)]
    else:
        items = [(x["code"], x["completion"], {k: x.get(k) for k in ("due_offset", "due_day", "title", "detail", "docs",
                                                                      "deadline", "submit_as", "rule")}) for x in stored]
    items = [x for x in items if uses_sql or x[0] not in rules.STARTER_SQL_ONLY]
    return [(code, kind, {**term, "sort": i}) for i, (code, kind, term) in enumerate(items)]


def _filing_codes(con):
    """The checklist codes the code's SQL filing words are seeded for: the starter checklist's (every company added in
    Setup has them) and any a company's checklist has. The words for the related company and the tenant
    (sqlimport.TASK_RULES) are only meaningful for the codes of rules.CHECKLIST, so a new install doesn't get them."""
    return {code for code, *_ in rules.STARTER} | {r[0] for r in con.execute("SELECT DISTINCT code FROM checklist_items")}


def seed_filing(con, codes):
    """The code's SQL filing words (sqlimport.TASK_RULES) for these checklist codes, for each code with none yet: update
    21, and a company from seed.json given a checklist of rules.CHECKLIST."""
    have = {r[0] for r in con.execute("SELECT DISTINCT checklist_code FROM filing_words")}
    for i, (kinds, direction, words, code) in enumerate(sqlimport.TASK_RULES):
        if code in codes and code not in have:
            for kind in sorted(kinds):
                con.execute("""INSERT INTO filing_words (label, words, doc_kind, direction, checklist_code, sort)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (FILING_LABELS.get(code, code), json.dumps(list(words)), kind, direction, code, i))


# Where the placeholder names (rules.PLACEHOLDERS) can be: text columns, and JSON ones (rule, words).
NAME_COLUMNS = (("checklist_items", "name", False), ("checklist_terms", "title", False),
                ("checklist_terms", "detail", False), ("checklist_terms", "rule", True), ("filing_words", "words", True))


def fill_names(con, names):
    """seed.json's real names for the placeholders (rules.PLACEHOLDERS), written into the checklists and filing words
    just seeded: the placeholder as written gets the name as given, the placeholder in capitals gets it in capitals.
    Each placeholder is first swapped for a marker the text can't hold (private-use characters, valid in JSON), then
    each marker for its name, so a name that itself holds a placeholder's words is written as given. Names for anything
    else are refused, as is an empty name."""
    if not names:
        return
    if (not isinstance(names, dict) or any(k not in rules.PLACEHOLDERS for k in names)
            or any(not isinstance(v, str) or not v.strip() or "\ue000" in v or "\ue001" in v for v in names.values())):
        raise ValueError("seed.json: \"names\" gives a real name for one of " + ", ".join(rules.PLACEHOLDERS))
    pairs = []
    for k, v in names.items():
        pairs += [(k, v.strip()), (k.upper(), v.strip().upper())]
    pairs.sort(key=lambda p: -len(p[0]))  # a longer placeholder first, so none is found inside another
    for table, col, is_json in NAME_COLUMNS:
        enc = (lambda t: json.dumps(t)[1:-1]) if is_json else (lambda t: t)
        steps = [(enc(old), f"\ue000{i}\ue001") for i, (old, _) in enumerate(pairs)]
        steps += [(f"\ue000{i}\ue001", enc(new)) for i, (_, new) in enumerate(pairs)]
        for old, new in steps:
            con.execute(f"UPDATE {table} SET {col} = replace({col}, ?, ?) WHERE instr({col}, ?) > 0", (old, new, old))


def install(con):
    """Update 21: the tables, filled with the values the code has had: each company's checklist (for the companies the
    code had one for) with how each item is shown done and Next up's deadlines; an item for any other checklist code a
    company's months hold, not added to new months, so those items are judged as before; the five joiner and leaver
    reminders; and the matching words (the SQL filing words only for the codes a checklist has or the starter
    checklist brings). Then a check that the tables read back exactly as the code has them: any
    difference stops the update."""
    from . import audit
    for stmt in TABLES.split(";"):
        if stmt.strip():
            con.execute(stmt)
    audit.refresh(con)  # the rows below go into the audit trail as added, not as a baseline
    ents = [dict(r) for r in con.execute("SELECT * FROM entities ORDER BY id")]
    for e in ents:
        seed_company(con, e)
    # Codes a company's months hold that its checklist doesn't (older wording, another company's): kept, not in use.
    for r in con.execute("""SELECT t.entity_id, t.code, t.title, t.detail, t.required_docs, t.month, t.due_date FROM tasks t
                            WHERE t.code NOT LIKE 'joiner-%' AND t.code NOT LIKE 'leaver-%'
                            AND NOT EXISTS (SELECT 1 FROM checklist_items i WHERE i.entity_id = t.entity_id AND i.code = t.code)
                            ORDER BY t.entity_id, t.code, t.month DESC""").fetchall():
        if con.execute("SELECT 1 FROM checklist_items WHERE entity_id = ? AND code = ?", (r["entity_id"], r["code"])).fetchone():
            continue
        y, m = map(int, r["month"].split("-"))
        dy, dm, dd = map(int, r["due_date"].split("-"))
        off = max(-12, min(12, (dy - y) * 12 + dm - m))
        kind, term = _frozen_term(r["code"], 1000, off, dd, r["title"], r["detail"] or "", json.loads(r["required_docs"] or "[]"))
        add_item(con, r["entity_id"], r["code"], kind, 0, term, in_use=0)
    if not con.execute("SELECT 1 FROM people_tasks").fetchone():
        for i, (kind, key, days, over, title, detail, docs) in enumerate(rules.PEOPLE_TASKS):
            pid = con.execute("INSERT INTO people_tasks (key, kind, short_name, system, sort) VALUES (?, ?, ?, 1, ?)",
                              (key, kind, PEOPLE_NAMES.get(key), i)).lastrowid
            con.execute("""INSERT INTO people_task_terms (people_task_id, from_month, to_month, in_use, days, salary_over, title,
                           detail, docs) VALUES (?, '0000-00', NULL, 1, ?, ?, ?, ?, ?)""",
                        (pid, days, over, title, detail, json.dumps(list(docs))))
    if not any(con.execute(f"SELECT 1 FROM {t}").fetchone() for t in WORD_TABLES):
        for i, (label, words, cat) in enumerate(GUESS):
            con.execute("INSERT INTO guess_words (label, words, payment_type, sort) VALUES (?, ?, ?, ?)",
                        (label, json.dumps(list(words)), cat, i))
        for i, (cat, words) in enumerate(sqlimport.CATEGORY_HINTS.items()):
            con.execute("INSERT INTO hint_words (label, words, payment_type, sort) VALUES (?, ?, ?, ?)",
                        ({"salary": "Salaries", "director": "Director payments"}.get(cat, cat), json.dumps(list(words)), cat, i))
        seed_filing(con, _filing_codes(con))
    check(con, from_tables(con), ents)
    forget(con)


def check(con, b, ents):
    """Raises unless the book b answers as the code did (update 21 stops then, so nothing is judged by other rules)."""
    f = FROZEN

    def stop(what):
        raise RuntimeError(f"Update 21 stopped: the {what} it wrote don't read back as the code has them.")
    norm = lambda x: json.loads(json.dumps(x))
    for e in ents:
        for month in ("2026-01", "2027-06"):
            if [{k: t[k] for k in ("code", "due_offset", "due_day", "title", "detail", "docs", "sort")} for t in b.checklist(e, month)] \
                    != f.checklist(e, month):
                stop(f"checklist items of {e['code']}")
    pairs = {(r[0], r[1]) for r in con.execute("SELECT entity_id, code FROM tasks")}
    pairs |= {(e["id"], code) for e in ents for code, *_ in rules.CHECKLIST.get(e["code"], [])}
    for eid, code in pairs:
        for month in ("2026-01", "2027-06"):
            if norm(b.completion(eid, code, month)) != norm(f.completion(eid, code, month)):
                stop(f"rules for checklist item {code}")
            if not is_reminder(code) and (b.deadline(eid, code, month), b.submit_as(eid, code, month)) != \
                    (f.deadline(eid, code, month), f.submit_as(eid, code, month)):
                stop(f"deadlines for checklist item {code}")
        if norm(b.einvoice_rules(eid, "2026-01")) != norm([x for x in f.einvoice_rules(eid, "2026-01")
                                                            if (eid, x[0]) in b.items and b.items[(eid, x[0])]["completion"] == "payments"]):
            stop("e-Invoice rules")
    for e in ents:
        for code, fb in (("statement", (1, 5)), ("file", (1, 10))):
            if b.due_of(e["id"], code, "2026-01", fb) != fb:
                stop(f"due dates of {e['code']}'s {code} item")
    if [(p["key"], p["kind"], p["short_name"]) for p in b.people()] != [(p["key"], p["kind"], p["short_name"]) for p in f.people()]:
        stop("joiner and leaver reminders")
    for p in f.people():
        if norm(b.people_term(p["key"], "2026-01")) is None or \
                {k: norm(b.people_term(p["key"], "2026-01"))[k] for k in ("days", "salary_over", "title", "detail", "docs")} != \
                norm(f.people_term(p["key"], "2026-01")):
            stop(f"terms of the {p['key']} reminder")
    codes = _filing_codes(con)
    if b.guess != f.guess or b.hints != f.hints or [(set(k), d, w, c) for k, d, w, c in b.filing] != \
            [(set(k), d, w, c) for k, d, w, c in f.filing if c in codes for _ in sorted(k)]:
        stop("matching words")
