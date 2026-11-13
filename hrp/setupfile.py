"""Setup moved between installs as one file, setup.json (owner decision 4, 13 Nov 2026): Setup › Move setup.

Two kinds of export. A template carries the rules only: payment types, document types, the documents each payment type
needs (the sets for every company), a starter checklist with no company (the checklist of a company chosen, else the one
new companies get), the joiner and leaver reminders, the matching words and the general settings (not the organisation
name). Everything adds the companies, their bank accounts (with the account numbers: the file is then sensitive), charts
of accounts, customers and suppliers, each company's checklist and own sets of required documents; and, only when
asked, the recurring payments and salary advances, which are personal data (staff names, amounts, bank details).

The file never holds an id: a company is named by its code, a payment or document type by its key, a GL account by its
company and code; bank accounts, customers and suppliers and recurring payments, which have no key, by a ref that means
something only inside the file. So the rows can be added to any records.db and get its own ids.

An import is made only into records that hold no company data yet (a new install), all or nothing: every row goes
through the checks Setup itself makes (masters, monthly, appsettings), any refusal undoes the whole import, and a
preview makes it and undoes it to show what it would add. The generic rules merge by key onto the ones the update steps
gave the new install (the app's own flags, such as which types it relies on, stay the code's); the matching words and
the sets of required documents in the file replace the ones it was given. A template's starter checklist is given to
each company imported without a checklist of its own and kept (checklistbook.STARTER_KEY) for companies added later.
Whether a record is in use is set last, once every reference to it has been checked."""
import json
import re
import sqlite3

from . import appsettings, checklistbook, db, masters, monthly, partybook, rulebook, rules
from .masters import MONTH, Refused

FORMAT, VERSION = "hrp-setup", 1
WHATS = ("template", "full")
MAX_ROWS = 20000  # per list; the request itself is capped at 40 MB (app.py)

ENTITY_COLS = ("code", "name", "short_name", "uses_sql", "first_month", "reg_no", "tin", "sst_no", "employer_kwsp",
               "employer_perkeso", "employer_lhdn", "sql_database", "notes", "active", "sort")
ACCOUNT_COLS = ("label", "bank", "number", "currency", "statement_format", "gl_code", "sql_payment_method", "cash_book",
                "notes", "active", "sort")
GL_COLS = ("code", "name", "type", "special", "parent_code", "sql_type", "active", "sort", "notes")
PARTY_COLS = ("kind", "name", "short_name", "sql_code", "tin", "brn", "match_words", "gl_code", "active", "sort", "notes")
PAYEE_COLS = ("name", "category", "direction", "desc_template", "amount", "amount_varies", "month_offset", "due_day",
              "bank_details", "reference", "match_words", "start_date", "end_date", "active", "sort", "notes")
ADVANCE_COLS = ("monthly_deduction", "start_month", "end_month", "note")
TYPE_COLS = {"payment_types": ("key", "label", "plural", "direction", "legal_due_offset", "legal_due_day", "active", "sort", "notes"),
             "doc_types": ("key", "label", "singular", "plural", "pack_order", "from_sql", "active", "sort", "notes")}
WORD_COLS = {"guess_words": ("label", "words", "payment_type", "active", "sort", "notes"),
             "hint_words": ("label", "words", "payment_type", "active", "sort", "notes"),
             "filing_words": ("label", "words", "doc_kind", "direction", "checklist_code", "active", "sort", "notes")}
ITEM_TERM_COLS = ("due_offset", "due_day", "title", "detail", "docs", "deadline", "submit_as", "rule")
DATED = ("from_month", "to_month", "in_use", "set_at")
CHK_TERM_COLS = DATED + ITEM_TERM_COLS + ("sort",)
PEOPLE_TERM_COLS = DATED + ("days", "salary_over", "title", "detail", "docs")
JSON_COLS = {"words", "docs", "rule", "match_words"}
# What each list is called in a preview and in a refusal, in the order an import adds them.
LISTS = [("settings", "general settings"), ("payment_types", "payment types"), ("doc_types", "document types"),
         ("starter_checklist", "starter checklist items"), ("entities", "companies"), ("accounts", "bank accounts"),
         ("gl_accounts", "GL accounts"), ("parties", "customers and suppliers"), ("checklist", "checklist items"),
         ("required_sets", "sets of required documents"), ("reminders", "joiner and leaver reminders"),
         ("guess_words", "payment type guesses"), ("hint_words", "salary words"), ("filing_words", "SQL filing words"),
         ("payees", "recurring payments"), ("advances", "salary advances")]
ONE = {"general settings": "general setting", "payment types": "payment type", "document types": "document type",
       "starter checklist items": "starter checklist item", "companies": "company", "bank accounts": "bank account",
       "GL accounts": "GL account", "customers and suppliers": "customer or supplier", "checklist items": "checklist item",
       "sets of required documents": "set of required documents", "joiner and leaver reminders": "joiner or leaver reminder",
       "payment type guesses": "payment type guess", "salary words": "salary words", "SQL filing words": "SQL filing words",
       "recurring payments": "recurring payment", "salary advances": "salary advance"}
FULL_ONLY = ("entities", "accounts", "gl_accounts", "parties", "checklist", "payees", "advances")
HEAD = ("format", "format_version", "records_version", "made", "what", "holds")
# Records that are a company's data: an import is refused while any of them holds a row.
HOLDING = [("entities", "company", "companies"), ("accounts", "bank account", "bank accounts"),
           ("payees", "recurring payment", "recurring payments"), ("advances", "salary advance", "salary advances"),
           ("parties", "customer or supplier", "customers and suppliers"), ("gl_accounts", "GL account", "GL accounts"),
           ("checklist_items", "checklist item", "checklist items"), ("months", "month set up", "months set up"),
           ("tasks", "checklist item in a month", "checklist items in months"), ("payments", "payment", "payments"),
           ("documents", "document", "documents"), ("statements", "bank statement", "bank statements"),
           ("sql_imports", "SQL import", "SQL imports"), ("budgets", "budget", "budgets"),
           ("budget_lines", "budget line", "budget lines"), ("book_openings", "book opening", "book openings")]
ITEM_CODE = re.compile(r"[a-z0-9][a-z0-9_-]{0,59}")
FORMAT_KEY = re.compile(r"[a-z0-9_]{1,30}")


def _version(con):
    return con.execute("PRAGMA user_version").fetchone()[0]


def _has(con, table):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone())


# ---------- export ----------

def _out(row, cols, json_cols=JSON_COLS):
    """A row's columns as the file keeps them (JSON columns as values, not text); a column the records don't have yet
    (below a later update) is left out."""
    keys = row.keys()
    out = {}
    for c in cols:
        if c in keys:
            v = row[c]
            out[c] = json.loads(v) if c in json_cols and isinstance(v, str) else v
    return out


def _terms(con, table, key_col, key, cols):
    return [_out(t, cols) for t in con.execute(f"SELECT * FROM {table} WHERE {key_col} = ? ORDER BY from_month, id", (key,))]


def _starter_from(con, entity_id):
    """The company-less starter checklist a template carries: the items of the company chosen as they are in the
    current payroll month (those in use), else the starter checklist new companies get here."""
    if entity_id is None:
        return [{"code": code, "completion": kind, **{k: term[k] for k in ITEM_TERM_COLS}}
                for code, kind, term in checklistbook.starter_items(con)]
    e = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not e:
        raise Refused("There is no such company.", 404)
    B = checklistbook.get(con)
    if not B.from_tables:
        raise Refused("The checklist can be exported once the records are updated.", 409)
    return [{"code": t["code"], "completion": B.items[(e["id"], t["code"])]["completion"], **{k: t[k] for k in ITEM_TERM_COLS}}
            for t in B.checklist(dict(e), db.current_cycle())]


def export(con, what, payees=False, entity_id=None):
    """The setup as setup.json holds it: a template (rules only, with a starter checklist taken from entity_id's checklist
    or the one new companies get) or everything (full; payees: with the recurring payments and salary advances)."""
    if what not in WHATS:
        raise Refused("Choose the template or everything.")
    full = what == "full"
    out = {"format": FORMAT, "format_version": VERSION, "records_version": _version(con), "made": db.now(), "what": what}
    if full:
        out["holds"] = ["Bank account numbers, and the companies' registration, tax and employer numbers."] + (
            ["Recurring payments: staff names, amounts and bank details. This is personal data."] if payees else [])
    settings = {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM app_settings") if k in appsettings.SPEC}
    if not full:
        settings.pop("organisation_name", None)  # the organisation's own name stays with it
    out["settings"] = settings
    for kind, cols in TYPE_COLS.items():
        out[kind] = [_out(r, cols) for r in con.execute(f"SELECT * FROM {kind} ORDER BY sort, id")]
    codes = {r["id"]: r["code"] for r in con.execute("SELECT id, code FROM entities")}
    stored = checklistbook.stored_starter(con)
    if not full:
        out["starter_checklist"] = _starter_from(con, entity_id)
    elif stored is not None:  # the starter checklist a template brought here goes along; else the code's is used there too
        out["starter_checklist"] = stored
    out["required_sets"] = [{"payment_type": r["payment_type"], "company": codes.get(r["entity_id"]), "from_month": r["from_month"],
                             "to_month": r["to_month"], "docs": json.loads(r["docs"]), "set_at": r["set_at"]}
                            for r in con.execute("SELECT * FROM required_sets ORDER BY id")
                            if full or r["entity_id"] is None]
    out["reminders"] = [{**_out(p, ("key", "kind", "short_name", "sort", "notes")),
                         "terms": _terms(con, "people_task_terms", "people_task_id", p["id"], PEOPLE_TERM_COLS)}
                        for p in con.execute("SELECT * FROM people_tasks ORDER BY sort, id").fetchall()]
    party_ref = {}
    if full:
        out["entities"] = [_out(r, ENTITY_COLS) for r in con.execute("SELECT * FROM entities ORDER BY sort, id")]
        acct_ref = {}
        out["accounts"] = []
        for r in con.execute("SELECT * FROM accounts ORDER BY entity_id, sort, id").fetchall():
            acct_ref[r["id"]] = f"a{len(acct_ref) + 1}"
            out["accounts"].append({"ref": acct_ref[r["id"]], "company": codes[r["entity_id"]], **_out(r, ACCOUNT_COLS)})
        out["gl_accounts"] = [{"company": codes[r["entity_id"]], **_out(r, GL_COLS)}
                              for r in con.execute("SELECT * FROM gl_accounts ORDER BY entity_id, code, id")]
        out["parties"] = []
        for r in con.execute("SELECT * FROM parties ORDER BY id").fetchall():
            party_ref[r["id"]] = f"p{len(party_ref) + 1}"
            out["parties"].append({"ref": party_ref[r["id"]], "company": codes.get(r["entity_id"]), **_out(r, PARTY_COLS)})
        out["checklist"] = [{"company": codes[it["entity_id"]], "code": it["code"], "completion": it["completion"], "notes": it["notes"],
                             "system": it["system"], "terms": _terms(con, "checklist_terms", "item_id", it["id"], CHK_TERM_COLS)}
                            for it in con.execute("SELECT * FROM checklist_items ORDER BY entity_id, id").fetchall()]
        if payees:
            payee_ref = {}
            out["payees"] = []
            for r in con.execute("SELECT * FROM payees ORDER BY entity_id, sort, id").fetchall():
                payee_ref[r["id"]] = f"y{len(payee_ref) + 1}"
                pid = r["party_id"] if "party_id" in r.keys() else None
                out["payees"].append({"ref": payee_ref[r["id"]], "company": codes[r["entity_id"]],
                                      "account": acct_ref.get(r["account_id"]), "party": party_ref.get(pid),
                                      **_out(r, PAYEE_COLS, json_cols=())})  # a payee's match_words are plain text
            out["advances"] = [{"payee": payee_ref[r["payee_id"]], **_out(r, ADVANCE_COLS)}
                               for r in con.execute("SELECT * FROM advances ORDER BY id")]
    starter_codes = {x["code"] for x in out.get("starter_checklist", [])}
    for kind, cols in WORD_COLS.items():
        rows = []
        for r in con.execute(f"SELECT * FROM {kind} ORDER BY sort, id").fetchall():
            if kind == "filing_words" and not full and r["checklist_code"] not in starter_codes:
                continue  # a template's filing words go with its starter checklist: no other item is there to file on
            row = _out(r, cols)
            if kind == "filing_words":
                pid = r["party_id"] if "party_id" in r.keys() else None
                row["party"] = party_ref.get(pid) if full else None
            rows.append(row)
        out[kind] = rows
    return out


# ---------- import ----------

def holding(con):
    """[(what, how many)] of the company data these records hold; empty for a new install."""
    out = []
    for table, one, many in HOLDING:
        if _has(con, table):
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if n:
                out.append([one if n == 1 else many, n])
    return out


class _At:
    """Names the row a refusal is about ("Company EXH: Name: this can't be empty."), and turns what SQLite itself
    refuses, and a value of the wrong shape, into a plain refusal, so the whole import is undone."""

    def __init__(self, where):
        self.where = where

    def __enter__(self):
        return self

    def __exit__(self, t, x, tb):
        if t is None:
            return False
        if t is Refused and getattr(x, "placed", False):
            return False
        if t is Refused:
            msg = str(x)
        elif issubclass(t, sqlite3.IntegrityError):
            msg = f"the records can't hold this ({x})."
        elif issubclass(t, (TypeError, ValueError, KeyError, AttributeError)):
            msg = "this can't be read. The file may have been changed by hand."
        else:
            return False
        y = Refused(f"{self.where}: {msg}", getattr(x, "status", 400))
        y.placed = True
        raise y from None


def _only(r, allowed):
    """Refuses a row that isn't one, or holds a field this app doesn't know (a typing slip, or a newer app's file)."""
    if not isinstance(r, dict):
        raise Refused("this can't be read.")
    for k in r:
        if k not in allowed:
            raise Refused(f"{k} can't be set here.")


def _flag(r, key, label, default=1):
    v = r.get(key, default)
    return default if v is None else masters.check_value({"key": key, "label": label, "type": "bool"}, v)


def _sort(r):
    v = r.get("sort", 0)
    if v is None:
        return 0
    if isinstance(v, bool) or not isinstance(v, int) or abs(v) > 1_000_000_000:
        raise Refused("Order: give a whole number.")
    return v


def _set_at(r):
    v = r.get("set_at")
    if v is not None and (not isinstance(v, str) or len(v) > 40):
        raise Refused("Set: give a date and time.")
    return v


def _range(t):
    f, to = t.get("from_month"), t.get("to_month")
    if f != "0000-00" and (not isinstance(f, str) or not MONTH.fullmatch(f)):
        raise Refused("From: months are written like 2026-10.")
    if to is not None and (not isinstance(to, str) or not MONTH.fullmatch(to) or to <= f):
        raise Refused("Until: give a month after From, or nothing.")
    return f, to


def _apart(spans, what):
    """Refuses dated terms or sets that overlap: each must end before the next starts."""
    spans = sorted(spans)
    for (f1, t1), (f2, _) in zip(spans, spans[1:]):
        if t1 is None or t1 > f2:
            raise Refused(f"{what} overlap in time: each must end before the next starts.")


def _same_title(title, f, to, others):
    """Refuses a title another item in use (others: [(title, from, until)]) has in an overlapping span, as Setup's
    add and change do (monthly._same_title): the lower-cased titles are compared, an Until of None runs on."""
    low = title.strip().lower()
    for t2, f2, to2 in others:
        if t2.strip().lower() == low and (to is None or to > f2) and (to2 is None or to2 > f):
            raise Refused(f"Another item in use is called {title}. Give this one another title.")


def _insert(con, table, vals):
    vals = masters._stored(vals)
    return con.execute(f"INSERT INTO {table} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values())).lastrowid


class _Import:
    def __init__(self, con, data):
        self.con, self.data, self.full = con, data, data["what"] == "full"
        self.ents, self.accounts, self.parties, self.payees = {}, {}, {}, {}
        self.later = []  # (table, id, active, what): whether in use, set once every reference has been checked
        self.counts = []

    def rows(self, name):
        v = self.data.get(name, [])
        label = dict(LISTS)[name]
        if not isinstance(v, list) or len(v) > MAX_ROWS:
            raise Refused(f"The file's {label} can't be read.")
        for r in v:
            if not isinstance(r, dict):
                raise Refused(f"The file's {label} can't be read.")
        if name in self.data:
            self.counts.append([ONE[label] if len(v) == 1 else label, len(v)])
        return v

    def ent(self, code, every=False):
        """The id a company code in the file has in these records; None for every company where that is allowed."""
        if code is None and every:
            return None
        if code not in self.ents:
            raise Refused(f"there is no company {code} in this file." if code is not None else "say which company it is for.")
        return self.ents[code]

    def ref(self, r, refs):
        ref = r.get("ref")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 40:
            raise Refused("it has no ref, which the file's other rows name it by.")
        if ref in refs:
            raise Refused(f"the ref {ref} is in the file twice.")
        return ref

    def fields(self, kind, r, keys):
        """The row's fields Setup's form has, checked as Setup checks them (masters._checked), and the required ones."""
        vals = masters._checked(kind, {k: r[k] for k in keys if k in r and r[k] is not None})
        for f in masters.KINDS[kind]["fields"]:
            if f.get("required") and f["key"] in keys and vals.get(f["key"]) in (None, ""):
                raise Refused(f"{f['label']}: this can't be empty.")
        return vals

    # ---- the generic rules ----
    def types(self):
        for kind, cols in TYPE_COLS.items():
            seen = set()
            label = masters.KINDS[kind]["label"]
            for r in self.rows(kind):
                with _At(f"{label} {r.get('key')}"):
                    _only(r, cols)
                    key = masters.check_value({"key": "key", "label": "Key", "type": "key", "required": True}, r.get("key"))
                    if key in seen:
                        raise Refused("this key is in the file twice.")
                    seen.add(key)
                    fields = {k: r[k] for k in cols if k in r and k not in ("active", "sort")}
                    have = self.con.execute(f"SELECT id FROM {kind} WHERE key = ?", (key,)).fetchone()
                    if have:  # the app's own row (update 20): changed as Setup would, its system flag kept
                        rid = have[0]
                        masters.update(self.con, kind, rid, fields, quiet=True)
                    else:
                        rid = masters.create(self.con, kind, fields, quiet=True)
                    self.con.execute(f"UPDATE {kind} SET sort = ? WHERE id = ?", (_sort(r), rid))
                    self.later.append((kind, rid, _flag(r, "active", "In use"), f"{label} {key}"))
        rulebook.forget(self.con)

    def starter(self):
        if "starter_checklist" not in self.data:
            return
        items = []
        for r in self.rows("starter_checklist"):
            with _At(f"Starter checklist item {r.get('code')}"):
                _only(r, ("code", "completion") + ITEM_TERM_COLS)
                code, completion = self.item(r, {x["code"] for x in items})
                t = monthly._term_fields(self.con, {k: r.get(k) for k in ITEM_TERM_COLS}, completion)
                _same_title(t["title"], "0000-00", None, [(x["title"], "0000-00", None) for x in items])
                items.append({"code": code, "completion": completion, **t})
        self.con.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                         (checklistbook.STARTER_KEY, json.dumps(items)))

    def item(self, r, taken):
        """A checklist item's code and how it is shown done: a built-in item (the statements, the reconciliation, the
        audit pack) keeps its own code and way."""
        code, completion = r.get("code"), r.get("completion")
        if not isinstance(code, str) or not ITEM_CODE.fullmatch(code) or checklistbook.is_reminder(code):
            raise Refused("Code: lower-case letters, digits, - and _ only, starting with a letter or digit.")
        if code in taken:
            raise Refused("this item is in the file twice.")
        if completion not in [k for k, _, _ in checklistbook.COMPLETIONS]:
            raise Refused("Say how the item is shown done.")
        built = {k: c for c, k in checklistbook.BUILT_IN.items()}
        if checklistbook.BUILT_IN.get(code, completion) != completion or built.get(completion, code) != code:
            raise Refused("a built-in item keeps its own code and the way it is shown done.")
        return code, completion

    # ---- the companies ----
    def companies(self):
        for r in self.rows("entities"):
            with _At(f"Company {r.get('code')}"):
                _only(r, ENTITY_COLS)
                vals = self.fields("entities", r, [c for c in ENTITY_COLS if c not in ("active", "sort")])
                if vals["code"] in self.ents:
                    raise Refused("this company is in the file twice.")
                masters._unique_code(self.con, vals["code"])
                vals.setdefault("uses_sql", 1)
                vals.update(active=_flag(r, "active", "In use"), sort=_sort(r))
                self.ents[vals["code"]] = _insert(self.con, "entities", vals)
        if self.ents and not self.con.execute("SELECT 1 FROM entities WHERE active = 1").fetchone():
            raise Refused("At least one company must be in use.")

    def bank_accounts(self):
        cash = {}
        for r in self.rows("accounts"):
            with _At(f"Bank account {r.get('label')} of {r.get('company')}"):
                _only(r, ("ref", "company") + ACCOUNT_COLS)
                ref = self.ref(r, self.accounts)
                eid = self.ent(r.get("company"))
                vals = self.fields("accounts", r, ("label", "bank", "number", "currency", "gl_code", "sql_payment_method", "notes"))
                book = _flag(r, "cash_book", "Cash book account", 0)
                if book and vals["currency"] != masters.BASE:
                    raise Refused(f"The cash book account is in {masters.BASE}, as SQL Account's cash book listing is.")
                if book and eid in cash:
                    raise Refused("its company already has a cash book account in this file. Each company has one.")
                fmt = r.get("statement_format")
                if fmt is not None:
                    if not isinstance(fmt, str) or not FORMAT_KEY.fullmatch(fmt):
                        raise Refused("Statement format: this can't be read.")
                    vals["statement_format"] = fmt
                active = _flag(r, "active", "In use")
                vals.update(entity_id=eid, cash_book=book, sort=_sort(r), active=1)
                aid = _insert(self.con, "accounts", vals)
                self.accounts[ref] = aid
                self.later.append(("accounts", aid, active, f"Bank account {vals['label']}"))
                if book:
                    cash[eid] = aid
                elif eid not in cash and vals["currency"] == masters.BASE and active:
                    cash.setdefault(("first", eid), aid)
        for eid in set(self.ents.values()) - set(cash):  # none chosen: the first account in MYR in use, as Setup does
            first = cash.get(("first", eid))
            if first and not self.con.execute("SELECT 1 FROM accounts WHERE entity_id = ? AND cash_book = 1", (eid,)).fetchone():
                self.con.execute("UPDATE accounts SET cash_book = 1 WHERE id = ?", (first,))

    def chart(self):
        rows = self.rows("gl_accounts")
        for r in rows:
            with _At(f"GL account {r.get('code')} of {r.get('company')}"):
                _only(r, ("company",) + GL_COLS)
        pending = list(rows)
        while pending:  # an account goes in after the account it sits under (_gl_check wants the parent there)
            have = {(r["company"], r["code"]) for r in self.con.execute(
                "SELECT e.code AS company, g.code FROM gl_accounts g JOIN entities e ON e.id = g.entity_id")}
            ready = [r for r in pending if not r.get("parent_code") or (r.get("company"), r.get("parent_code")) in have]
            for r in ready or pending[:1]:  # none ready: the first one's check says what is wrong
                pending.remove(r)
                with _At(f"GL account {r.get('code')} of {r.get('company')}"):
                    eid = self.ent(r.get("company"))
                    vals = self.fields("gl_accounts", r, ("code", "name", "sql_type", "type", "special", "parent_code", "notes"))
                    masters._gl_check(self.con, eid, vals)
                    vals.update(entity_id=eid, active=_flag(r, "active", "In use"), sort=_sort(r))
                    _insert(self.con, "gl_accounts", vals)

    def customers_and_suppliers(self):
        for r in self.rows("parties"):
            with _At(f"Customer or supplier {r.get('name')}"):
                _only(r, ("ref", "company") + PARTY_COLS)
                ref = self.ref(r, self.parties)
                vals = self.fields("parties", r, ("name", "kind", "sql_code", "short_name", "tin", "brn", "gl_code", "match_words", "notes"))
                vals["entity_id"] = self.ent(r.get("company"), every=True)
                masters._party_check(self.con, vals)
                active = _flag(r, "active", "In use")
                vals.update(sort=_sort(r), active=1)
                self.parties[ref] = _insert(self.con, "parties", vals)
                self.later.append(("parties", self.parties[ref], active, f"Customer or supplier {vals['name']}"))

    def checklists(self):
        taken = {}
        titles = {}  # company id: [(title, from, until)] of the terms in use so far
        for r in self.rows("checklist"):
            with _At(f"Checklist item {r.get('code')} of {r.get('company')}"):
                _only(r, ("company", "code", "completion", "notes", "system", "terms"))
                eid = self.ent(r.get("company"))
                code, completion = self.item(r, taken.setdefault(eid, set()))
                taken[eid].add(code)
                terms = r.get("terms")
                if not isinstance(terms, list) or not terms:
                    raise Refused("it has no wording.")
                out = []
                for t in terms:
                    _only(t, CHK_TERM_COLS)
                    f, to = _range(t)
                    v = monthly._term_fields(self.con, {k: t.get(k) for k in ITEM_TERM_COLS}, completion)
                    out.append({**v, "from_month": f, "to_month": to, "in_use": _flag(t, "in_use", "In use"), "sort": _sort(t),
                                "set_at": _set_at(t)})
                _apart([(t["from_month"], t["to_month"]) for t in out], "Its wordings")
                mine = [(t["title"], t["from_month"], t["to_month"]) for t in out if t["in_use"]]
                for t in mine:
                    _same_title(*t, titles.setdefault(eid, []))
                titles[eid] += mine
                notes = masters.check_value({"key": "notes", "label": "Notes", "type": "textarea"}, r.get("notes"))
                company = next(c for c, i in self.ents.items() if i == eid)
                # built in only when the file says so and the code is on that company's frozen list (as seed_company gives
                # it): a company added in Setup has the starter checklist, not built in, whatever its code
                system = int(bool(_flag(r, "system", "Built in", default=0))
                             and code in {x[0] for x in rules.CHECKLIST.get(company, [])})
                out.sort(key=lambda t: t["from_month"])
                iid = _insert(self.con, "checklist_items", {"entity_id": eid, "code": code, "completion": completion, "system": system,
                                                            "name": out[-1]["title"], "notes": notes})
                for t in out:
                    _insert(self.con, "checklist_terms", {**t, "item_id": iid, "rule": json.dumps(t["rule"]) if t["rule"] else None})
        for code, eid in self.ents.items():  # a company with no checklist in the file starts with the starter checklist
            if eid not in taken:
                uses_sql = self.con.execute("SELECT uses_sql FROM entities WHERE id = ?", (eid,)).fetchone()[0]
                checklistbook.seed_company(self.con, {"id": eid, "code": code, "uses_sql": uses_sql}, starter=True)
        checklistbook.forget(self.con)

    # ---- dated rules and words ----
    def required_sets(self):
        if "required_sets" not in self.data:
            return
        R = rulebook.get(self.con)
        self.con.execute("DELETE FROM required_sets")  # the file's sets take the place of the ones update 20 gave
        spans = {}
        for r in self.rows("required_sets"):
            with _At(f"Required documents for {r.get('payment_type')}" + (f" ({r['company']})" if r.get("company") else "")):
                _only(r, ("payment_type", "company", "from_month", "to_month", "docs", "set_at"))
                if r.get("payment_type") not in R.types:
                    raise Refused("there is no such payment type.")
                eid = self.ent(r.get("company"), every=True)
                f, to = _range(r)
                docs = r.get("docs")
                if not isinstance(docs, list) or len(set(map(str, docs))) != len(docs):
                    raise Refused("Choose each document once.")
                for d in docs:
                    if not isinstance(d, str) or d not in R.docs or d in masters.INTERNAL_DOCS:
                        raise Refused(f"{d} isn't a document type a payment can need.")
                spans.setdefault((r["payment_type"], eid), []).append((f, to))
                _insert(self.con, "required_sets", {"payment_type": r["payment_type"], "entity_id": eid, "from_month": f,
                                                    "to_month": to, "docs": json.dumps(docs), "set_at": _set_at(r)})
        for (t, _), s in spans.items():
            with _At(f"Required documents for {t}"):
                _apart(s, "Its sets")
        rulebook.forget(self.con)

    def reminders(self):
        seen = set()
        for r in self.rows("reminders"):
            with _At(f"Joiner or leaver reminder {r.get('key')}"):
                _only(r, ("key", "kind", "short_name", "sort", "notes", "terms"))
                key = r.get("key")
                if not isinstance(key, str) or not masters.KEY.fullmatch(key):
                    raise Refused("Key: lower-case letters, digits and _ only, 2 to 20 characters, starting with a letter.")
                if key in seen:
                    raise Refused("this reminder is in the file twice.")
                seen.add(key)
                if r.get("kind") not in ("joiner", "leaver"):
                    raise Refused("Say whether it is for joiners or leavers.")
                terms = r.get("terms")
                if not isinstance(terms, list) or not terms:
                    raise Refused("it has no wording.")
                out = []
                for t in terms:
                    _only(t, PEOPLE_TERM_COLS)
                    f, to = _range(t)
                    v = monthly._people_fields(self.con, {k: t.get(k) for k in ("days", "salary_over", "title", "detail", "docs")})
                    out.append({**v, "from_month": f, "to_month": to, "in_use": _flag(t, "in_use", "In use"), "set_at": _set_at(t)})
                _apart([(t["from_month"], t["to_month"]) for t in out], "Its wordings")
                vals = {"short_name": monthly._short_name(r.get("short_name")), "sort": _sort(r),
                        "notes": masters.check_value({"key": "notes", "label": "Notes", "type": "textarea"}, r.get("notes"))}
                have = self.con.execute("SELECT * FROM people_tasks WHERE key = ?", (key,)).fetchone()
                if have:  # one of the app's own (update 21): its wording is the file's, its system flag the code's
                    if have["kind"] != r["kind"]:
                        raise Refused(f"this reminder is for {have['kind']}s in this app.")
                    pid = have["id"]
                    self.con.execute("UPDATE people_tasks SET short_name = ?, sort = ?, notes = ? WHERE id = ?", (*vals.values(), pid))
                    self.con.execute("DELETE FROM people_task_terms WHERE people_task_id = ?", (pid,))
                else:
                    pid = _insert(self.con, "people_tasks", {"key": key, "kind": r["kind"], "system": 0, **vals})
                for t in sorted(out, key=lambda t: t["from_month"]):
                    _insert(self.con, "people_task_terms", {**t, "people_task_id": pid})
        checklistbook.forget(self.con)

    def words(self):
        codes = {r[0] for r in self.con.execute("SELECT DISTINCT code FROM checklist_items")}
        codes |= {x["code"] for x in checklistbook.stored_starter(self.con) or []}
        if checklistbook.stored_starter(self.con) is None:
            codes |= {x[0] for x in rules.STARTER}
        for kind, cols in WORD_COLS.items():
            if kind not in self.data:
                continue
            label = masters.KINDS[kind]["label"]
            self.con.execute(f"DELETE FROM {kind}")  # the file's words take the place of the ones update 21 gave
            allowed = cols + (("party",) if kind == "filing_words" else ())
            for r in self.rows(kind):
                with _At(f"{label}: {r.get('label')}"):
                    _only(r, allowed)
                    keys = [c for c in cols if c not in ("active", "sort")]
                    vals = self.fields(kind, r, keys)
                    if kind == "filing_words":
                        if vals["checklist_code"] not in codes:
                            raise Refused(f"Checklist item: {vals['checklist_code']} is on no company's checklist, nor the starter checklist.")
                        if r.get("party") is not None:
                            if r["party"] not in self.parties:
                                raise Refused(f"there is no customer or supplier {r['party']} in this file.")
                            vals["party_id"] = self.parties[r["party"]]
                    masters._word_check(self.con, kind, {k: v for k, v in vals.items() if k != "checklist_code"})
                    rid = _insert(self.con, kind, {**vals, "sort": _sort(r), "active": 1})
                    self.later.append((kind, rid, _flag(r, "active", "In use"), f"{label} {vals['label']}"))
        checklistbook.forget(self.con)

    # ---- recurring payments ----
    def recurring(self):
        R = rulebook.get(self.con)
        for r in self.rows("payees"):
            with _At(f"Recurring payment {r.get('name')}"):
                _only(r, ("ref", "company", "account", "party") + PAYEE_COLS)
                ref = self.ref(r, self.payees)
                eid = self.ent(r.get("company"))
                ent = dict(self.con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone())
                vals = {k: r[k] for k in PAYEE_COLS if k in r and k != "sort"}
                if not isinstance(vals.get("name"), str) or not vals["name"].strip():
                    raise Refused("Give the payee a name.")
                if vals.get("category") not in R.types:
                    raise Refused("Choose one of the payment types.")
                way = vals.get("direction") or R.direction(vals["category"])
                if way not in ("in", "out") or R.direction(vals["category"]) != way:
                    raise Refused("Its type and Money in or out don't fit together.")
                vals["direction"] = way
                if not vals.get("desc_template"):
                    vals["desc_template"] = vals["name"].strip() + " - {M}"
                for k, refs, what in (("account", self.accounts, "bank account"), ("party", self.parties, "customer or supplier")):
                    if r.get(k) is not None and r[k] not in refs:
                        raise Refused(f"there is no {what} {r[k]} in this file.")
                vals["account_id"] = self.accounts.get(r.get("account"))
                vals["party_id"] = self.parties.get(r.get("party"))
                vals = masters.payee_check(self.con, ent, vals)
                vals.update(entity_id=eid, sort=_sort(r))
                self.payees[ref] = (_insert(self.con, "payees", vals), vals)
        for r in self.rows("advances"):
            with _At(f"Salary advance of {r.get('payee')}"):
                _only(r, ("payee",) + ADVANCE_COLS)
                if r.get("payee") not in self.payees:
                    raise Refused(f"there is no recurring payment {r.get('payee')} in this file.")
                pid, p = self.payees[r["payee"]]
                if p["category"] not in masters.PERSONAL:
                    raise Refused("Salary advances are recovered from a salary or director's fee only.")
                v = masters.advance_check(self.con, {k: r.get(k) for k in ADVANCE_COLS})
                _insert(self.con, "advances", {"payee_id": pid, "note": v.pop("note", None), **v})

    # ---- last: in use or stopped, and the settings ----
    def finish(self):
        for table, rid, active, what in self.later:
            self.con.execute(f"UPDATE {table} SET active = ? WHERE id = ?", (active, rid))
        rulebook.forget(self.con)
        for r in self.con.execute("SELECT key FROM payment_types WHERE active = 0"):
            if r[0] in rulebook.UNSTOPPABLE_TYPES:
                raise Refused(f"Payment type {r[0]}: the app relies on it, so it stays in use.")
        for r in self.con.execute("SELECT key FROM doc_types WHERE active = 0 AND system = 1"):
            if r[0] not in rulebook.STOPPABLE_DOCS:
                raise Refused(f"Document type {r[0]}: the app relies on it, so it stays in use.")
        self.stopped_in_use()
        s = self.data.get("settings", {})
        if not isinstance(s, dict):
            raise Refused("The file's general settings can't be read.")
        R = rulebook.get(self.con)
        out_types = {k: t["label"] for k, t in R.types.items() if t["active"] and t["direction"] == "out"}
        try:
            v = appsettings.check(s, out_types)
            # the type new recurring payments start on, the file's or the one kept, must be one still in use
            appsettings.check({"payee_default_category": v.get("payee_default_category", appsettings.get("payee_default_category"))},
                              out_types)
        except ValueError as x:
            raise Refused(f"General settings: {x}")
        appsettings.save(self.con, v)
        if "settings" in self.data:
            self.counts.insert(0, [ONE["general settings"] if len(v) == 1 else "general settings", len(v)])

    def stopped_in_use(self):
        """Refuses the stopped records Setup never leaves something in use on (masters.set_active): a bank account
        recurring payments in use pay from, a document type the checklist or a set of required documents asks for.
        A stopped cash book while another account is in use is left alone: Setup can reach it (stop the other
        account, stop the cash book, use the other one again), so an export of it must import."""
        checklistbook.forget(self.con)
        for a in self.con.execute("SELECT id, label FROM accounts WHERE active = 0 ORDER BY id").fetchall():
            users = [r[0] for r in self.con.execute("SELECT name FROM payees WHERE account_id = ? AND active = 1 ORDER BY name",
                                                    (a["id"],))]
            if users:
                raise Refused(f"Bank account {a['label']}: Recurring payments are paid from this account: {', '.join(users[:5])}"
                              f"{f' and {len(users) - 5} more' if len(users) > 5 else ''}. Move them to another account "
                              "first.")
        stopped = [r[0] for r in self.con.execute("SELECT key FROM doc_types WHERE active = 0 ORDER BY key")]
        if stopped:
            # Only wordings and sets with no end count. The file carries no filed months, and Setup lets an ended one
            # ask for a stopped document type when it ended at a filed month (masters._reaches_open), so that must import.
            B = checklistbook.get(self.con)
            if B.from_tables:
                asked = set()
                for it in B.items.values():
                    for t in B.terms.get(it["id"], []):
                        if t["in_use"] and t["to_month"] is None:
                            r = t["rule"] or {}
                            asked |= set(t["docs"]) | set(r.get("docs", ())) | set(r.get("on_item", ()))
                for ts in B._pterms.values():
                    asked |= {d for t in ts if t["in_use"] and t["to_month"] is None for d in t["docs"]}
            else:
                asked = masters._checklist_docs(self.con)
            R = rulebook.get(self.con)
            for key in stopped:
                if key in asked:
                    raise Refused(f"Document type {key}: The monthly checklist asks for this document type, so it can't be "
                                  "stopped yet.")
                need = [R.label(x["payment_type"]) for x in R.sets if key in x["docs"] and x["to_month"] is None]
                if need:
                    raise Refused(f"Document type {key}: It is still required for "
                                  f"{masters._words([[n, 1] for n in dict.fromkeys(need)]).replace('1 ', '')}. "
                                  "Take it off their required documents first.")

    def run(self):
        self.types()
        self.starter()
        self.companies()
        self.bank_accounts()
        self.chart()
        self.customers_and_suppliers()
        self.checklists()
        self.required_sets()
        self.reminders()
        self.words()
        self.recurring()
        self.finish()
        rulebook.forget(self.con)
        checklistbook.forget(self.con)


def load(con, data):
    """Adds a setup file's rows to records that hold no company data (see the module's notes). The caller rolls back on
    a refusal (and after a preview) and commits otherwise. Returns {what, counts: [[what, how many]], notes}."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise Refused("This isn't a setup file from this app.")
    fv, rv = data.get("format_version"), data.get("records_version")
    if isinstance(fv, bool) or not isinstance(fv, int) or isinstance(rv, bool) or not isinstance(rv, int):
        raise Refused("This setup file can't be read: it doesn't say which version made it.")
    if fv > VERSION:
        raise Refused("This setup file is written in a newer form than this app reads. Update this app first.")
    if fv != VERSION:
        raise Refused("This setup file is written in a form this app doesn't read.")
    here = _version(con)
    if rv > here:
        raise Refused(f"This setup file was made by a newer version of the app (records at update {rv}; these are at "
                      f"update {here}). Update this app first.")
    if data.get("what") not in WHATS:
        raise Refused("This setup file doesn't say whether it is a template or everything.")
    holds, made = data.get("holds"), data.get("made")
    if holds is not None and (not isinstance(holds, list) or not all(isinstance(h, str) for h in holds)):
        raise Refused("This setup file can't be read.")
    if made is not None and (not isinstance(made, str) or len(made) > 40):
        raise Refused("This setup file can't be read.")
    names = {n for n, _ in LISTS}
    for k in data:
        if k not in names and k not in HEAD:
            raise Refused(f"This setup file holds something this app doesn't know ({k}). It may come from a newer version.")
    if data["what"] == "template" and any(data.get(k) for k in FULL_ONLY):
        raise Refused("A template holds the rules only, but this one holds companies or what belongs to them.")
    held = holding(con)
    if held:
        raise Refused(f"A setup file is imported only into new records, holding no company yet. These hold {masters._words(held)}.", 409)
    if _version(con) < partybook.SINCE:
        raise Refused("A setup file can be imported once the records are updated.", 409)
    try:
        imp = _Import(con, data)
        imp.run()
    except sqlite3.IntegrityError as x:
        raise Refused(f"The records can't hold this file ({x}).")
    n = sum(c for what, c in imp.counts if "general setting" not in what)
    db.log(con, f"Imported a setup {'template' if data['what'] == 'template' else 'file (everything)'} made "
                f"{str(data.get('made') or '')[:10] or 'on an unknown day'}: " +
           (", ".join(f"{c} {w}" for w, c in imp.counts if c) or "nothing"))
    notes = []
    if "starter_checklist" in data:
        notes.append("Companies added later start with the file's starter checklist.")
    notes += [f"The file holds: {h}" for h in data.get("holds") or []]
    return {"what": data["what"], "made": data.get("made"), "counts": imp.counts, "rows": n, "notes": notes}

