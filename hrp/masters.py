"""Setup's master records: what each kind holds, how it is checked, what uses it, what is locked once used, and how it
is added, changed, stopped, used again or deleted.

Rules (owner decisions, 12 Nov 2026): a record can be deleted only while nothing uses it, otherwise it is stopped
("Stop using"); stopping, using again and deleting take a reason, which the request carries into the audit trail
(app._trail_context). Keys that folders, files or past months depend on are locked once used. The routes in app.py are
thin: they call these functions and turn a Refused into a plain message.

Recurring payments (payees) keep their own routes and drawer (they bring changes into the months already set up), but
use payee_check, payee_usage and the advances helpers below."""
import json
import math
import re

from . import appsettings, db, rules

CODE = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,15}")
BASE = "MYR"  # the books' currency (SQL Account's cash book listing is in it)
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
DAY = re.compile(r"[2-9]\d{3}-\d{2}-\d{2}")


class Refused(Exception):
    """A change refused, with the sentence the page shows and the HTTP status (400 bad value, 404 gone, 409 in use)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _f(key, label, kind, **kw):
    return {"key": key, "label": label, "type": kind, **kw}


KINDS = {
    "entities": {
        "label": "Company", "plural": "companies", "table": "entities", "per_entity": False, "name_field": "name",
        "columns": [{"key": "code", "label": "Code"}, {"key": "name", "label": "Name"}, {"key": "first_month", "label": "First month tracked"}],
        "fields": [
            _f("code", "Code", "code", required=True, max=16,
               hint="Short, capitals: AISB. Folders and audit packs are named by it."),
            _f("name", "Name", "text", required=True, wide=True),
            _f("short_name", "Short name", "text", hint="Shown in the sidebar. Empty: the name without Sdn Bhd or Ltd."),
            _f("uses_sql", "Kept in SQL Account", "bool", default=1, hint="Payments then need their PV, JV or OR from SQL."),
            _f("first_month", "First month tracked", "month",
               hint="Months before it are never set up on their own and nothing in them counts as overdue. Empty: no limit."),
            _f("reg_no", "Registration no.", "text"),
            _f("tin", "Tax ID (TIN)", "text"),
            _f("sst_no", "SST no.", "text"),
            _f("employer_kwsp", "KWSP employer no.", "text"),
            _f("employer_perkeso", "PERKESO employer no.", "text"),
            _f("employer_lhdn", "LHDN employer no. (E)", "text"),
            _f("sql_database", "SQL Account database", "text", hint="Which SQL Account company database holds its books."),
            _f("notes", "Notes", "textarea", wide=True),
        ],
    },
    "accounts": {
        "label": "Bank account", "plural": "bank accounts", "table": "accounts", "per_entity": True, "name_field": "label",
        "columns": [{"key": "label", "label": "Account"}, {"key": "bank", "label": "Bank"}, {"key": "currency", "label": "Currency"},
                    {"key": "cash_book", "label": "Cash book"}],
        "fields": [
            _f("label", "Name", "text", required=True, hint="How the account is named in this app, e.g. Main or FCA USD."),
            _f("bank", "Bank", "text"),
            _f("number", "Account number", "text", hint="Filled from the first statement imported if left empty."),
            _f("currency", "Currency", "code", required=True, max=3, hint="Three letters: MYR, USD, SGD."),
            _f("cash_book", "Cash book account", "bool",
               hint="The account SQL Account's cash book listing is for. Each company has one, in MYR."),
            _f("gl_code", "GL account code", "text", hint="The bank account's code in SQL Account's chart of accounts."),
            _f("sql_payment_method", "SQL payment method", "text", hint="As SQL Account names it on vouchers."),
            _f("notes", "Notes", "textarea", wide=True),
        ],
    },
}
GROUPS = [["Companies and banks", ["entities", "accounts"]], ["People and payments", ["payees"]], ["General", ["settings"]]]
STOPPED_NOTE = {"entities": "Stopped: hidden from the sidebar and Next up, and its months aren't set up any more. Everything recorded stays.",
                "accounts": "Stopped: hidden from the account lists; a month with no statement for it no longer asks for one."}


def types():
    kinds = {k: {kk: vv for kk, vv in v.items()} for k, v in KINDS.items()}
    kinds["payees"] = {"label": "Recurring payment", "plural": "recurring payments", "table": "payees", "per_entity": True, "bespoke": True}
    kinds["settings"] = {"label": "General settings", "single": True, "table": "app_settings"}
    return {"groups": GROUPS, "kinds": kinds}


def spec(kind):
    if kind not in KINDS:
        raise Refused("There is no such kind of record.", 404)
    return KINDS[kind]


# ---------- checking values ----------

def check_value(f, v):
    """A field's value from the page, checked and made tidy; None for empty. Raises Refused with a plain sentence."""
    label, kind = f["label"], f["type"]
    if v is None or (isinstance(v, str) and not v.strip() and kind != "bool"):
        if f.get("required"):
            raise Refused(f"{label}: this can't be empty.")
        return None
    if kind in ("text", "textarea", "code"):
        if not isinstance(v, str):
            raise Refused(f"{label}: give it as text.")
        v = v.strip()
        if kind == "code":
            v = v.upper()
            if f["key"] == "currency":
                if not re.fullmatch(r"[A-Z]{3}", v):
                    raise Refused(f"{label}: give the three-letter code, such as MYR or USD.")
            elif not CODE.fullmatch(v):
                raise Refused(f"{label}: capitals, digits, - and _ only, up to 16 characters, starting with a letter or digit.")
        if len(v) > (2000 if kind == "textarea" else f.get("max", 200)):
            raise Refused(f"{label}: that is too long.")
        return v
    if kind == "bool":
        if v in (True, 1, "1"):
            return 1
        if v in (False, 0, "0", ""):
            return 0
        raise Refused(f"{label}: choose yes or no.")
    if kind in ("number", "money"):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise Refused(f"{label}: give a number.")
        return round(v, 2) if kind == "money" else v
    if kind == "day":
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 31:
            raise Refused(f"{label}: give a day from 1 to 31.")
        return v
    if kind == "month":
        if not isinstance(v, str) or not MONTH.fullmatch(v):
            raise Refused(f"{label}: months are written like 2026-10.")
        return v
    if kind == "date":
        if not isinstance(v, str) or not DAY.fullmatch(v):
            raise Refused(f"{label}: dates are written like 2026-10-20.")
        return v
    if kind == "select":
        if v not in [o[0] for o in f.get("options", [])]:
            raise Refused(f"{label}: choose one of the options.")
        return v
    raise Refused(f"{label}: this can't be set here.")


def _row(con, kind, rid):
    r = con.execute(f"SELECT * FROM {spec(kind)['table']} WHERE id = ?", (rid,)).fetchone()
    if not r:
        raise Refused(f"This {spec(kind)['label'].lower()} has been removed.", 404)
    return dict(r)


# ---------- what uses a record, and what that locks ----------

USES = {  # (one, many, how to count)
    "entities": [
        ("bank account", "bank accounts", "SELECT COUNT(*) FROM accounts WHERE entity_id = ?"),
        ("recurring payment", "recurring payments", "SELECT COUNT(*) FROM payees WHERE entity_id = ?"),
        ("month set up", "months set up", "SELECT COUNT(*) FROM months WHERE entity_id = ?"),
        ("payment", "payments", "SELECT COUNT(*) FROM payments WHERE entity_id = ?"),
        ("checklist item", "checklist items", "SELECT COUNT(*) FROM tasks WHERE entity_id = ?"),
        ("document", "documents", "SELECT COUNT(*) FROM documents WHERE entity_id = ?"),
        ("SQL import", "SQL imports", "SELECT COUNT(*) FROM sql_imports WHERE entity_id = ?"),
        ("budget", "budgets", "SELECT COUNT(*) FROM budgets WHERE entity_id = ?"),
        ("budget line", "budget lines", "SELECT COUNT(*) FROM budget_lines WHERE entity_id = ?"),
    ],
    "accounts": [
        ("payment", "payments", "SELECT COUNT(*) FROM payments WHERE account_id = ?"),
        ("recurring payment", "recurring payments", "SELECT COUNT(*) FROM payees WHERE account_id = ?"),
        ("bank statement", "bank statements", "SELECT COUNT(*) FROM statements WHERE account_id = ?"),
        ("book opening", "book openings", "SELECT COUNT(*) FROM book_openings WHERE account_id = ?"),
    ],
}


def usage(con, kind, rid):
    """[(what, how many)] for the uses that are not zero."""
    out = []
    for one, many, sql in USES[kind]:
        n = con.execute(sql, (rid,)).fetchone()[0]
        if n:
            out.append([one if n == 1 else many, n])
    return out


def _count(con, sql, *args):
    return con.execute(sql, args).fetchone()[0]


def locked(con, kind, rec):
    """{field: why it can't change now}."""
    out = {}
    if kind == "entities" and rec.get("id"):
        if any(_count(con, f"SELECT COUNT(*) FROM {t} WHERE entity_id = ?", rec["id"]) for t in ("months", "payments", "documents")):
            out["code"] = "Folders, uploaded documents and audit packs are named by this code, so it can't change once the company has records."
        if _count(con, "SELECT COUNT(*) FROM months WHERE entity_id = ? AND closed_at IS NOT NULL", rec["id"]):
            out["uses_sql"] = ("Months already filed were checked with this setting, so it can't change once a month is filed. "
                               "Reopen the filed months first if it really must.")
    if kind == "accounts" and rec.get("id"):
        if _count(con, "SELECT COUNT(*) FROM months WHERE entity_id = ? AND closed_at IS NOT NULL", rec["entity_id"]):
            out["cash_book"] = ("Filed months were reconciled with the SQL cash book on the account that is the cash book now, so it "
                                "can't move once a month is filed. Reopen the filed months first if it really must.")
        if _count(con, "SELECT COUNT(*) FROM statements WHERE account_id = ?", rec["id"]) or \
                _count(con, "SELECT COUNT(*) FROM payments WHERE account_id = ?", rec["id"]):
            out["currency"] = "Its payments and statements are in this currency, so it can't change once it has any."
    return out


def notes(con, kind, rec):
    out = []
    if not rec.get("active", 1):
        out.append(STOPPED_NOTE[kind])
    if kind == "entities" and rec.get("code") and rec["code"] not in rules.CHECKLIST:
        out.append("This company has no monthly checklist yet: its months are set up with its recurring payments only. "
                   "Checklists will be edited in Setup in a later update.")
    if kind == "accounts" and rec.get("id") and _count(con, "SELECT COUNT(*) FROM statements WHERE account_id = ?", rec["id"]):
        out.append("Statements have been imported for this account. If you change the account number, the next import is refused "
                   "unless the statement shows the new number.")
    return out


# ---------- reading ----------

def listing(con, kind, entity_id=None):
    s = spec(kind)
    if s["per_entity"]:
        if entity_id is None:
            raise Refused("Choose a company.")
        rows = con.execute(f"SELECT * FROM {s['table']} WHERE entity_id = ? ORDER BY sort, id", (entity_id,)).fetchall()
    else:
        rows = con.execute(f"SELECT * FROM {s['table']} ORDER BY sort, id").fetchall()
    out = []
    for r in rows:
        r = dict(r)
        used = usage(con, kind, r["id"])
        out.append({**r, "used_by": used, "used_total": sum(n for _, n in used), "status": "in_use" if r.get("active", 1) else "stopped"})
    return {"rows": out}


def record(con, kind, rid):
    rec = _row(con, kind, rid)
    used = usage(con, kind, rid)
    return {"record": rec, "used_by": used, "used_total": sum(n for _, n in used), "locked": locked(con, kind, rec),
            "can_delete": not used, "notes": notes(con, kind, rec)}


# ---------- changing ----------

def _checked(kind, fields, rec=None):
    if not isinstance(fields, dict):
        raise Refused("Nothing to save.")
    known = {f["key"]: f for f in spec(kind)["fields"]}
    out = {}
    for k, v in fields.items():
        if k not in known:
            raise Refused(f"{k} can't be set here.")
        out[k] = check_value(known[k], v)
    return out


def _unique_code(con, code, rid=None):
    if code and con.execute("SELECT 1 FROM entities WHERE code = ? AND id IS NOT ?", (code, rid)).fetchone():
        raise Refused(f"Another company already has the code {code}.")


def create(con, kind, fields, entity_id=None):
    s = spec(kind)
    vals = _checked(kind, fields)
    for f in s["fields"]:
        if f.get("required") and vals.get(f["key"]) in (None, ""):
            raise Refused(f"{f['label']}: this can't be empty.")
    if kind == "entities":
        _unique_code(con, vals["code"])
        vals.setdefault("uses_sql", 1)
    else:
        if entity_id is None or not con.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone():
            raise Refused("Choose the company the account belongs to.")
        vals["entity_id"] = entity_id
        if vals.get("cash_book") and vals.get("currency") != BASE:
            raise Refused(f"The cash book account is in {BASE}, as SQL Account's cash book listing is.")
        if vals.get("currency") == BASE and not con.execute(
                "SELECT 1 FROM accounts WHERE entity_id = ? AND cash_book = 1 AND active = 1", (entity_id,)).fetchone():
            vals["cash_book"] = 1  # a company's first account in MYR is its cash book until another is chosen
    vals = {k: v for k, v in vals.items() if v is not None}
    cur = con.execute(f"INSERT INTO {s['table']} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values()))
    rid = cur.lastrowid
    if kind == "accounts" and vals.get("cash_book"):
        _only_cash_book(con, entity_id, rid)
    db.log(con, f"Added {s['label'].lower()}: {vals[s['name_field']]}")
    return rid


def _only_cash_book(con, entity_id, rid):
    con.execute("UPDATE accounts SET cash_book = 0 WHERE entity_id = ? AND id != ? AND cash_book = 1", (entity_id, rid))


def update(con, kind, rid, fields):
    s = spec(kind)
    rec = _row(con, kind, rid)
    vals = _checked(kind, fields, rec)
    vals = {k: v for k, v in vals.items() if v != rec.get(k)}
    for k in vals:
        why = locked(con, kind, rec).get(k)
        if why:
            raise Refused(why)
    for f in s["fields"]:
        if f.get("required") and f["key"] in vals and vals[f["key"]] in (None, ""):
            raise Refused(f"{f['label']}: this can't be empty.")
    if not vals:
        return []
    if kind == "entities" and "code" in vals:
        _unique_code(con, vals["code"], rid)
    if kind == "accounts" and "cash_book" in vals:
        if vals["cash_book"]:
            if not rec["active"]:
                raise Refused("A stopped account can't be the cash book. Use it again first.")
            if vals.get("currency", rec["currency"]) != BASE:
                raise Refused(f"The cash book account is in {BASE}, as SQL Account's cash book listing is.")
            _only_cash_book(con, rec["entity_id"], rid)
        else:
            raise Refused("Each company has one cash book account. Make another account the cash book instead; this one then stops being it.")
    con.execute(f"UPDATE {s['table']} SET {', '.join(k + ' = ?' for k in vals)} WHERE id = ?", (*vals.values(), rid))
    named = ", ".join(f["label"].lower() for f in s["fields"] if f["key"] in vals)
    db.log(con, f"Changed {s['label'].lower()} {rec[s['name_field']]}: {named}")
    return notes(con, kind, {**rec, **vals})


def set_active(con, kind, rid, active):
    s = spec(kind)
    rec = _row(con, kind, rid)
    if bool(rec["active"]) == bool(active):
        return
    if kind == "entities" and not active and not con.execute("SELECT 1 FROM entities WHERE active = 1 AND id != ?", (rid,)).fetchone():
        raise Refused("This is the only company in use, so it can't be stopped. Add or use another company first.")
    if kind == "accounts" and not active and rec["cash_book"] and con.execute(
            "SELECT 1 FROM accounts WHERE entity_id = ? AND active = 1 AND id != ?", (rec["entity_id"], rid)).fetchone():
        raise Refused("This is the company's cash book account. Make another account the cash book first.")
    if kind == "accounts" and not active:
        users = [r[0] for r in con.execute("SELECT name FROM payees WHERE account_id = ? AND active = 1 ORDER BY name", (rid,))]
        if users:
            raise Refused(f"Recurring payments are paid from this account: {', '.join(users[:5])}"
                          f"{f' and {len(users) - 5} more' if len(users) > 5 else ''}. Move them to another account first.")
    con.execute(f"UPDATE {s['table']} SET active = ? WHERE id = ?", (1 if active else 0, rid))
    if kind == "accounts" and active:
        # one cash book in use per company: this one takes it back only if no other account in use has it
        other = con.execute("SELECT 1 FROM accounts WHERE entity_id = ? AND cash_book = 1 AND active = 1 AND id != ?",
                            (rec["entity_id"], rid)).fetchone()
        if other:
            con.execute("UPDATE accounts SET cash_book = 0 WHERE id = ? AND cash_book = 1", (rid,))
        elif rec["currency"] == BASE:
            con.execute("UPDATE accounts SET cash_book = 1 WHERE id = ?", (rid,))
            _only_cash_book(con, rec["entity_id"], rid)
    db.log(con, f"{'Using again' if active else 'Stopped using'} {s['label'].lower()} {rec[s['name_field']]}")


def delete(con, kind, rid):
    s = spec(kind)
    rec = _row(con, kind, rid)
    used = usage(con, kind, rid)
    if used:
        raise Refused(f"Used by {_words(used)}, so it can't be deleted. Stop using it instead.", 409)
    if kind == "entities" and not con.execute("SELECT 1 FROM entities WHERE active = 1 AND id != ?", (rid,)).fetchone():
        raise Refused("This is the only company in use, so it can't be deleted.")
    con.execute(f"DELETE FROM {s['table']} WHERE id = ?", (rid,))
    if kind == "accounts" and rec["cash_book"]:
        nxt = con.execute("SELECT id FROM accounts WHERE entity_id = ? AND active = 1 AND currency = ? ORDER BY sort, id LIMIT 1",
                          (rec["entity_id"], BASE)).fetchone()
        if nxt:
            con.execute("UPDATE accounts SET cash_book = 1 WHERE id = ?", (nxt["id"],))
    db.log(con, f"Deleted {s['label'].lower()} {rec[s['name_field']]}")


def _words(used):
    parts = [f"{n} {label}" for label, n in used]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------- recurring payments (payees) ----------

PAYEE_TEXT = {"name": 200, "desc_template": 200, "bank_details": 300, "reference": 200, "match_words": 300, "notes": 2000}


def payee_check(con, ent, vals, old=None):
    """A recurring payment's fields from the page, checked: the type is one of the payment types, the day of the month
    1-31, paid in the same or the next month, an amount a number, dates real dates with the last day not before the
    start, and the account one of the company's own that is in use. Raises Refused."""
    out = dict(vals)
    for k, n in PAYEE_TEXT.items():
        if k in out and out[k] is not None:
            if not isinstance(out[k], str):
                raise Refused(f"{k.replace('_', ' ').capitalize()}: give it as text.")
            out[k] = out[k].strip()
            if len(out[k]) > n:
                raise Refused(f"{k.replace('_', ' ').capitalize()}: that is too long.")
    if "name" in out and not out["name"]:
        raise Refused("Give the payee a name.")
    if "category" in out and out["category"] not in rules.CATEGORIES:
        raise Refused("Choose one of the payment types.")
    if "account_id" in out and not out["account_id"]:
        out["account_id"] = None  # an empty picker is no account, not account 0
    if out.get("account_id") is not None and (isinstance(out["account_id"], bool) or not isinstance(out["account_id"], int)):
        raise Refused("Choose one of the company's bank accounts.")
    if "due_day" in out:
        d = out["due_day"]
        if isinstance(d, bool) or not isinstance(d, int) or not 1 <= d <= 31:
            raise Refused("Day of month: give a day from 1 to 31.")
    if "month_offset" in out and out["month_offset"] not in (0, 1):
        raise Refused("Paid in: choose the same month or the next month.")
    if "amount" in out and out["amount"] is not None:
        a = out["amount"]
        if isinstance(a, bool) or not isinstance(a, (int, float)) or not math.isfinite(a):
            raise Refused("Usual amount: give a number, or leave it empty if it changes every month.")
        if a < 0:
            raise Refused("Usual amount: give the amount without a minus sign; choose Money in or Money out for its direction.")
    for k in ("amount_varies", "active"):
        if k in out:
            if out[k] not in (0, 1, True, False):
                raise Refused(f"{k.replace('_', ' ').capitalize()}: choose yes or no.")
            out[k] = int(bool(out[k]))
    for k in ("start_date", "end_date"):
        if k in out:
            out[k] = out[k] or None
            if out[k] is not None and (not isinstance(out[k], str) or not DAY.fullmatch(out[k])):
                raise Refused(f"{'Start date' if k == 'start_date' else 'Last day'}: dates are written like 2026-10-20.")
    start = out.get("start_date", old["start_date"] if old else None)
    end = out.get("end_date", old["end_date"] if old else None)
    if start and end and end < start:
        raise Refused("The last day is before the start date.")
    if "account_id" in out and out["account_id"]:
        acct = con.execute("SELECT * FROM accounts WHERE id = ?", (out["account_id"],)).fetchone()
        if not acct or acct["entity_id"] != ent["id"]:
            raise Refused(f"That bank account isn't one of {ent['name']}'s accounts.")
        if not acct["active"] and (not old or old["account_id"] != acct["id"]):
            raise Refused("That bank account is stopped. Choose an account in use.")
    return out


def payee_usage(con, pid):
    """[(what, how many)] using a recurring payment: payments made from it, salary advances, budget lines and joiner or
    leaver reminders."""
    codes = [f"{kind}-{key}-{pid}" for kind, key, *_ in rules.PEOPLE_TASKS]  # as db.sync_reminders names them
    found = [
        ("payment", "payments", _count(con, "SELECT COUNT(*) FROM payments WHERE payee_id = ?", pid)),
        ("salary advance", "salary advances", _count(con, "SELECT COUNT(*) FROM advances WHERE payee_id = ?", pid)),
        ("budget line", "budget lines", _count(con, "SELECT COUNT(*) FROM budget_lines WHERE payee_id = ?", pid)),
        ("joiner or leaver reminder", "joiner or leaver reminders",
         _count(con, f"SELECT COUNT(*) FROM tasks WHERE code IN ({','.join('?' * len(codes))})", *codes)),
    ]
    return [[one if n == 1 else many, n] for one, many, n in found if n]


def advance_check(con, vals, old=None):
    out = {}
    if "monthly_deduction" in vals or old is None:
        d = vals.get("monthly_deduction")
        if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d) or d <= 0:
            raise Refused("Monthly deduction: give an amount above 0.")
        out["monthly_deduction"] = round(d, 2)
    for k, label in (("start_month", "From"), ("end_month", "Until")):
        if k in vals or old is None:
            v = vals.get(k)
            if not isinstance(v, str) or not MONTH.fullmatch(v):
                raise Refused(f"{label}: months are written like 2026-10.")
            out[k] = v
    if "note" in vals:
        n = vals["note"]
        if n is not None and (not isinstance(n, str) or len(n) > 300):
            raise Refused("Note: give some text, at most 300 characters.")
        out["note"] = (n or "").strip() or None
    start = out.get("start_month", old["start_month"] if old else None)
    end = out.get("end_month", old["end_month"] if old else None)
    if start and end and end < start:
        raise Refused("Until is before From.")
    return out


# ---------- update 19 ----------

def install(con):
    """Update 19: Setup's columns and General settings. Companies get a short name, registration and employer numbers,
    the SQL database, notes, and active and sort; bank accounts the statement format, GL code, SQL payment method,
    cash book, notes, and active and sort. Each company's first account becomes its cash book, as the app took it to
    be until now. Nothing else in the records changes."""
    for col, decl in (("short_name", "TEXT"), ("reg_no", "TEXT"), ("tin", "TEXT"), ("sst_no", "TEXT"), ("employer_kwsp", "TEXT"),
                      ("employer_perkeso", "TEXT"), ("employer_lhdn", "TEXT"), ("sql_database", "TEXT"), ("notes", "TEXT"),
                      ("active", "INTEGER NOT NULL DEFAULT 1"), ("sort", "INTEGER NOT NULL DEFAULT 0")):
        db.add_column(con, "entities", col, decl)
    for col, decl in (("statement_format", "TEXT NOT NULL DEFAULT 'maybank'"), ("gl_code", "TEXT"), ("sql_payment_method", "TEXT"),
                      ("cash_book", "INTEGER NOT NULL DEFAULT 0"), ("notes", "TEXT"), ("active", "INTEGER NOT NULL DEFAULT 1"),
                      ("sort", "INTEGER NOT NULL DEFAULT 0")):
        db.add_column(con, "accounts", col, decl)
    con.execute("""UPDATE accounts SET cash_book = 1 WHERE id IN (SELECT MIN(id) FROM accounts GROUP BY entity_id)
                   AND NOT EXISTS (SELECT 1 FROM accounts a2 WHERE a2.entity_id = accounts.entity_id AND a2.cash_book = 1)""")
    appsettings.install(con, bool(con.execute("SELECT 1 FROM entities").fetchone()))


def first_active_account(con, entity_id):
    """The company's cash book account (else its first account in use, else its first account): what the app takes
    when no account is named."""
    r = con.execute("""SELECT id, currency FROM accounts WHERE entity_id = ? ORDER BY active DESC, cash_book DESC, sort, id LIMIT 1""",
                    (entity_id,)).fetchone()
    return r
