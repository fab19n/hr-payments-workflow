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
from datetime import date

import sqlite3

from . import appsettings, checklistbook, db, partybook, rulebook, rules

CODE = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,15}")
KEY = re.compile(r"[a-z][a-z0-9_]{1,19}")  # a payment or document type's key: also part of stored file names, so strict
TYPE_KINDS = ("payment_types", "doc_types")
WORD_KINDS = ("guess_words", "hint_words", "filing_words")
WORD = re.compile(r"[A-Z0-9][A-Z0-9 '&./-]{0,39}")
SQLCODE = re.compile(r"[A-Z0-9][A-Z0-9_./-]{0,19}")  # a code as SQL Account keeps it: 300-A001, 4000/0001
PERSONAL = ("salary", "director")  # paid to a person: staff are never customers or suppliers
BASE = "MYR"  # the books' currency (SQL Account's cash book listing is in it)
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
DAY = re.compile(r"[2-9]\d{3}-\d{2}-\d{2}")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")


def is_day(v):
    """Whether v is a date written like 2026-10-20 that is on the calendar (not 2026-11-31 or 2026-13-45)."""
    if not isinstance(v, str) or not DAY.fullmatch(v):
        return False
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


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
            _f("fy_start", "Financial year starts in", "select", options=[[n, name] for n, name in enumerate(MONTH_NAMES, 1)],
               hint="Keep it the same as the company's setting in SQL Account: SQL's reports can't tell it. The trial balance check uses it, and later reports will too. Empty: January."),
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
KINDS["payment_types"] = {
    "label": "Payment type", "plural": "payment types", "table": "payment_types", "per_entity": False, "name_field": "label",
    "columns": [{"key": "key", "label": "Key"}, {"key": "label", "label": "Name"}, {"key": "direction", "label": "Money"}],
    "fields": [
        _f("key", "Key", "key", required=True, hint="Short, lower case: water_bill. Records refer to it, so it can't change once added."),
        _f("label", "Name", "text", required=True, wide=True),
        _f("plural", "Several of them are called", "text", hint="In Next up: Pay 8 AISB bills. Empty: bills."),
        _f("direction", "Money", "select", required=True, options=[["out", "Money out (a payment)"], ["in", "Money in (received)"]]),
        _f("legal_due_offset", "Legal deadline in", "select", options=[[0, "The payroll month"], [1, "The month after"]],
           hint="For payments with a legal deadline, like statutory ones. Empty: none."),
        _f("legal_due_day", "Legal deadline day", "day"),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["doc_types"] = {
    "label": "Document type", "plural": "document types", "table": "doc_types", "per_entity": False, "name_field": "label",
    "columns": [{"key": "key", "label": "Key"}, {"key": "label", "label": "Name"}, {"key": "from_sql", "label": "From SQL"}],
    "fields": [
        _f("key", "Key", "key", required=True, hint="Short, lower case: tax_form. Stored file names begin with it, so it can't change once added."),
        _f("label", "Name", "text", required=True, wide=True),
        _f("singular", "One of them is called", "text", hint="In Next up and the audit pack: 1 tax form."),
        _f("plural", "Several of them are called", "text", hint="3 tax forms."),
        _f("pack_order", "Place in the audit pack", "number", hint="Lower comes first. Empty: after the others."),
        _f("from_sql", "Issued by SQL Account", "bool", hint="Not asked for from a company that isn't kept in SQL Account."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["guess_words"] = {
    "label": "Payment type from SQL vouchers", "plural": "payment type guesses", "table": "guess_words", "per_entity": False,
    "name_field": "label",
    "help": "When an SQL voucher is added as a payment, its description is checked against these in order; the first match "
            "gives its type. Words match anywhere in the description, in capitals.",
    "columns": [{"key": "sort", "label": "Order"}, {"key": "label", "label": "Name"}, {"key": "payment_type", "label": "Payment type"},
                {"key": "words", "label": "Words"}],
    "fields": [
        _f("label", "Name", "text", required=True, wide=True),
        _f("words", "Words", "words", required=True, wide=True, hint="Separated by commas: KWSP, PERKESO, LHDN."),
        _f("payment_type", "Payment type", "select", required=True, options_from="categories"),
        _f("sort", "Order", "number", hint="Lower is tried first. Empty: after the others."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["hint_words"] = {
    "label": "Salary words for SQL matching", "plural": "salary words", "table": "hint_words", "per_entity": False,
    "name_field": "label",
    "help": "When an estimated salary or director payment is matched with SQL vouchers, a voucher must contain one of these words.",
    "columns": [{"key": "label", "label": "Name"}, {"key": "payment_type", "label": "Payment type"}, {"key": "words", "label": "Words"}],
    "fields": [
        _f("label", "Name", "text", required=True, wide=True),
        _f("payment_type", "Payment type", "select", required=True, options_from="categories"),
        _f("words", "Words", "words", required=True, wide=True, hint="Separated by commas: SALARY, GAJI, WAGES."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["filing_words"] = {
    "label": "SQL documents on the checklist", "plural": "filing words", "table": "filing_words", "per_entity": False,
    "name_field": "label",
    "help": "An SQL document with one of these words is filed on that checklist item of its month. They act on SQL imports "
            "from now on; documents already filed stay where they are.",
    "columns": [{"key": "sort", "label": "Order"}, {"key": "label", "label": "Name"}, {"key": "doc_kind", "label": "Documents"},
                {"key": "checklist_code", "label": "Checklist item"}, {"key": "words", "label": "Words"}],
    "fields": [
        _f("label", "Name", "text", required=True, wide=True),
        _f("doc_kind", "Documents", "select", required=True,
           options=[["invoice", "Invoices"], ["journal", "Journals"], ["payment", "Payments"]]),
        _f("direction", "Money", "select", options=[["in", "Money in"], ["out", "Money out"]], hint="Empty: either."),
        _f("words", "Words", "words", required=True, wide=True, hint="In the description or the company name, in capitals."),
        _f("checklist_code", "Checklist item", "select", required=True, options_from="checklist_codes"),
        _f("party_id", "Customer or supplier", "select", options_from="parties",
           hint="An SQL document with its code is filed here, before any words."),
        _f("sort", "Order", "number", hint="Lower is tried first. Empty: after the others."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["parties"] = {
    "label": "Customer or supplier", "plural": "customers and suppliers", "table": "parties", "per_entity": True, "or_all": True,
    "order": "name COLLATE NOCASE, id", "name_field": "name", "paste": True,
    "help": "Customers pay money in and suppliers are paid money out. An SQL entry carrying a customer's or supplier's code is "
            "matched by it before any words. Staff are not added here: they stay recurring payments.",
    "columns": [{"key": "name", "label": "Name"}, {"key": "kind", "label": "Kind"}, {"key": "sql_code", "label": "SQL code"},
                {"key": "entity_id", "label": "For"}],
    "fields": [
        _f("name", "Name", "text", required=True, wide=True, hint="As SQL Account names it."),
        _f("kind", "Kind", "select", required=True, options=[["customer", "Customer (money in)"], ["supplier", "Supplier (money out)"],
                                                              ["related", "Related company"], ["statutory", "Statutory body"]]),
        _f("entity_id", "For", "company", hint="One company, or every company. Each company's SQL Account database keeps its own codes."),
        _f("sql_code", "SQL code", "sqlcode", hint="Its customer or supplier code in SQL Account, e.g. 300-A001."),
        _f("short_name", "Short name", "text"),
        _f("tin", "Tax ID (TIN)", "text", max=20),
        _f("brn", "Business registration no. (BRN)", "text", max=30),
        _f("gl_code", "Control account (GL code)", "sqlcode", hint="Its debtor or creditor control account."),
        _f("match_words", "Words in SQL descriptions", "words", wide=True, hint="Kept for reference; matching uses the code."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
KINDS["gl_accounts"] = {
    "label": "GL account", "plural": "chart of accounts", "table": "gl_accounts", "per_entity": True,
    "order": "code, id", "name_field": "name", "paste": True,
    "help": "Each company's chart of accounts in SQL Account, for reference: nothing is posted to it.",
    "columns": [{"key": "code", "label": "Code"}, {"key": "name", "label": "Name"}, {"key": "type", "label": "Type"},
                {"key": "sql_type", "label": "SQL group"}, {"key": "special", "label": "Special"}],
    # The tree view: accounts under SQL's groups (in its order), each under its parent account.
    "tree": {"groups": [[code, name, t] for code, name, t in partybook.SQL_GROUPS]},
    "fields": [
        _f("code", "Code", "sqlcode", required=True, hint="As in SQL Account, e.g. 310-000."),
        _f("name", "Name", "text", required=True, wide=True),
        _f("sql_type", "SQL group", "select", options=[[code, f"{name} ({code})"] for code, name, _ in partybook.SQL_GROUPS],
           hint="SQL Account's A/C Type. The type follows it."),
        _f("type", "Type", "select", options=[["asset", "Asset"], ["liability", "Liability"], ["equity", "Equity"],
                                              ["income", "Income"], ["expense", "Expense"]]),
        _f("special", "Special", "select", options=[["bank", "Bank account"], ["cash", "Cash"], ["debtor_control", "Debtor control"],
                                                    ["creditor_control", "Creditor control"],
                                                    ["accumulated_depreciation", "Accumulated depreciation"],
                                                    ["deposit", "Deposit / prepayment"],
                                                    ["stock", "Stock (balance sheet)"], ["opening_stock", "Opening stock"],
                                                    ["closing_stock", "Closing stock"]]),
        _f("parent_code", "Parent account", "sqlcode", hint="The account it sits under, if any."),
        _f("notes", "Notes", "textarea", wide=True),
    ],
}
GROUPS = [["Companies and banks", ["entities", "accounts", "gl_accounts"]], ["People and payments", ["payees", "parties"]],
          ["Payments and documents", ["payment_types", "doc_types", "required"]],
          ["Monthly work", ["checklist", "reminders"]],
          ["Matching words", ["guess_words", "hint_words", "filing_words"]], ["General", ["settings", "move"]]]
STOPPED_NOTE = {"entities": "Stopped: hidden from the sidebar and Next up, and its months aren't set up any more. Everything recorded stays.",
                "accounts": "Stopped: hidden from the account lists; a month with no statement for it no longer asks for one.",
                "payment_types": "Stopped: not offered for new payments or recurring payments. Payments of this type keep it.",
                "doc_types": "Stopped: not offered for uploads or required documents. Documents of this type keep it.",
                "guess_words": "Stopped: not used to guess the type of SQL vouchers added as payments.",
                "hint_words": "Stopped: not used when matching estimated payments with SQL vouchers.",
                "filing_words": "Stopped: SQL documents aren't filed on the checklist by these words.",
                "parties": "Stopped: not offered for recurring payments. Links and SQL entries already matched keep it.",
                "gl_accounts": "Stopped: kept for reference; records that name it keep it."}


def types():
    kinds = {k: {kk: vv for kk, vv in v.items()} for k, v in KINDS.items()}
    kinds["payees"] = {"label": "Recurring payment", "plural": "recurring payments", "table": "payees", "per_entity": True, "bespoke": True}
    kinds["settings"] = {"label": "General settings", "single": True, "table": "app_settings"}
    kinds["required"] = {"label": "Required documents", "bespoke": True, "table": "required_sets"}
    kinds["checklist"] = {"label": "Monthly checklist", "bespoke": True, "per_entity": True, "table": "checklist_items"}
    kinds["reminders"] = {"label": "Joiner and leaver reminders", "bespoke": True, "table": "people_tasks"}
    kinds["move"] = {"label": "Move setup", "bespoke": True}  # export and import setup.json (setupfile)
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
    if kind == "key":
        if not isinstance(v, str) or not KEY.fullmatch(v.strip().lower()):
            raise Refused(f"{label}: lower-case letters, digits and _ only, 2 to 20 characters, starting with a letter.")
        return v.strip().lower()
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
        if not is_day(v):
            raise Refused(f"{label}: dates are written like 2026-10-20.")
        return v
    if kind == "words":
        if isinstance(v, str):
            v = v.split(",")
        if not isinstance(v, list) or not all(isinstance(w, str) for w in v):
            raise Refused(f"{label}: give the words separated by commas.")
        v = list(dict.fromkeys(w.strip().upper() for w in v if w.strip()))
        if not v:
            raise Refused(f"{label}: give at least one word.")
        if any(not WORD.fullmatch(w) for w in v):
            raise Refused(f"{label}: letters, digits, spaces and ' & . / - only, up to 40 characters each.")
        return v
    if kind == "sqlcode":
        if not isinstance(v, str) or not SQLCODE.fullmatch(v.strip().upper()):
            raise Refused(f"{label}: capitals, digits and _ . / - only, up to 20 characters, as SQL Account writes it.")
        return v.strip().upper()
    if kind == "company":
        if isinstance(v, str) and v.isdigit():
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int):
            raise Refused(f"{label}: choose a company, or every company.")
        return v
    if kind == "select" and f.get("options_from") == "parties":
        if isinstance(v, str) and v.isdigit():
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int):
            raise Refused(f"{label}: choose one of the options.")
        return v  # checked against the records by _word_check
    if kind == "select" and f.get("options_from"):
        if not isinstance(v, str):
            raise Refused(f"{label}: choose one of the options.")
        return v.strip()  # checked against the records by _word_check
    if kind == "select":
        if isinstance(v, str) and v.isdigit() and int(v) in [o[0] for o in f.get("options", [])]:
            v = int(v)  # a select's value comes back from the page as text
        if v not in [o[0] for o in f.get("options", [])]:
            raise Refused(f"{label}: choose one of the options.")
        return v
    raise Refused(f"{label}: this can't be set here.")


def _row(con, kind, rid):
    r = con.execute(f"SELECT * FROM {spec(kind)['table']} WHERE id = ?", (rid,)).fetchone()
    if not r:
        raise Refused(f"This {spec(kind)['label'].lower()} has been removed.", 404)
    return _decoded(kind, dict(r))


def _party_check(con, vals, rec=None):
    """A customer or supplier: its company (or every company), a code no other one the same companies see has, a code on
    an every-company one only while the companies share one SQL Account database, and a kind that fits the recurring
    payments linked to it."""
    rec = rec or {}
    eid = vals.get("entity_id", rec.get("entity_id")) if ("entity_id" in vals or rec) else None
    if eid is not None and not con.execute("SELECT 1 FROM entities WHERE id = ?", (eid,)).fetchone():
        raise Refused("For: choose a company, or every company.")
    code = vals.get("sql_code", rec.get("sql_code"))
    if code and (("sql_code" in vals and vals["sql_code"] != rec.get("sql_code")) or ("entity_id" in vals and vals["entity_id"] != rec.get("entity_id"))):
        if con.execute("""SELECT 1 FROM parties WHERE UPPER(sql_code) = ? AND id IS NOT ?
                          AND (entity_id IS ? OR entity_id IS NULL OR ? IS NULL)""", (code.upper(), rec.get("id"), eid, eid)).fetchone():
            raise Refused(f"Another customer or supplier the same company sees already has the SQL code {code}.")
        if eid is None and len({r[0] or "" for r in con.execute("SELECT sql_database FROM entities")}) > 1:
            raise Refused("Each company keeps its own codes in SQL Account. Give the code to a customer or supplier of one "
                          "company, adding one for each company.")
    kind = vals.get("kind")
    if rec.get("id") and kind and kind != rec.get("kind"):
        way = {"customer": "out", "supplier": "in"}.get(kind)
        if way and con.execute("SELECT 1 FROM payees WHERE party_id = ? AND direction = ?", (rec["id"], way)).fetchone():
            raise Refused("A customer pays money in and a supplier is paid money out, and recurring payments linked to it "
                          "go the other way. Change their link first.")


def _shared_codes(con, entity_id, database):
    """Refuses giving a company another SQL Account database while a customer or supplier for every company has an SQL
    code: the companies would then keep their own codes, and the code would name different ones."""
    try:
        coded = [r[0] for r in con.execute("SELECT name FROM parties WHERE entity_id IS NULL AND sql_code IS NOT NULL ORDER BY name")]
    except sqlite3.OperationalError:
        return  # below update 22
    if not coded:
        return
    dbs = {(r[1] or "") if r[0] != entity_id else (database or "") for r in con.execute("SELECT id, sql_database FROM entities")}
    if entity_id is None:
        dbs.add(database or "")
    if len(dbs) > 1:
        raise Refused(f"{', '.join(coded[:3])}{' and more' if len(coded) > 3 else ''} are customers or suppliers for every company "
                      "with an SQL code. Give their codes to a customer or supplier of each company first.")


def _gl_check(con, entity_id, vals, rec=None):
    """A GL account: a code the company's chart doesn't have yet, and a parent account in it (not itself, no loop).
    With an SQL group (A/C Type), the type is the one that group falls under: set from it, and a different one refused."""
    rec = rec or {}
    group = vals["sql_type"] if "sql_type" in vals else rec.get("sql_type")
    if group and ("sql_type" in vals or "type" in vals):
        want = partybook.GROUP_TYPE[group]
        # a type other than the group's, or an emptied one while the group stays
        if vals.get("type") not in (None, want) or ("sql_type" not in vals and vals.get("type") is None):
            name = next(n for c, n, _ in partybook.SQL_GROUPS if c == group)
            raise Refused(f"Type: an account in SQL's {name} ({group}) group is {'an' if want[0] in 'aeiou' else 'a'} {want}. "
                          "Choose another SQL group, or none, to give it another type.")
        vals["type"] = want
    code = vals.get("code", rec.get("code"))
    if "code" in vals and vals["code"] != rec.get("code") and con.execute(
            "SELECT 1 FROM gl_accounts WHERE entity_id = ? AND code = ? AND id IS NOT ?", (entity_id, code, rec.get("id"))).fetchone():
        raise Refused(f"The chart of accounts already has the code {code}.")
    parent = vals.get("parent_code")
    if parent and parent != rec.get("parent_code"):
        seen, at = {code}, parent
        for _ in range(30):
            if at in seen:
                raise Refused("Parent account: an account can't sit under itself.")
            seen.add(at)
            row = con.execute("SELECT parent_code FROM gl_accounts WHERE entity_id = ? AND code = ?", (entity_id, at)).fetchone()
            if not row:
                if at == parent:
                    raise Refused(f"Parent account: the chart of accounts has no account {parent}.")
                break
            at = row[0]
            if not at:
                break


def _decoded(kind, r):
    for f in KINDS.get(kind, {}).get("fields", []):
        if f["type"] == "words" and isinstance(r.get(f["key"]), str):
            r[f["key"]] = json.loads(r[f["key"]])
    return r


def _stored(vals):
    return {k: json.dumps(v) if isinstance(v, list) else v for k, v in vals.items()}


def _word_check(con, kind, vals, rec=None):
    """A word rule's payment type in use (a guess: a money-out one) and checklist item that exists; unchanged ones stay."""
    R = rulebook.get(con)
    t = vals.get("payment_type")
    if t is not None and t != (rec or {}).get("payment_type"):
        if not R.active_type(t) or (kind == "guess_words" and R.direction(t) != "out"):
            raise Refused("Payment type: choose one in use" + (" for money out." if kind == "guess_words" else "."))
    pid = vals.get("party_id")
    if pid is not None and pid != (rec or {}).get("party_id"):
        p = con.execute("SELECT * FROM parties WHERE id = ?", (pid,)).fetchone()
        if not p or not p["active"]:
            raise Refused("Customer or supplier: choose one in use.")
    c = vals.get("checklist_code")
    if c is not None and c != (rec or {}).get("checklist_code") and not con.execute(
            "SELECT 1 FROM checklist_items WHERE code = ?", (c,)).fetchone():
        raise Refused("Checklist item: choose one of the companies' checklist items.")


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
        ("customer or supplier", "customers and suppliers", "SELECT COUNT(*) FROM parties WHERE entity_id = ?"),
        ("GL account", "GL accounts", "SELECT COUNT(*) FROM gl_accounts WHERE entity_id = ?"),
    ],
    "payment_types": [
        ("payment", "payments", "SELECT COUNT(*) FROM payments WHERE category = (SELECT key FROM payment_types WHERE id = ?)"),
        ("recurring payment", "recurring payments", "SELECT COUNT(*) FROM payees WHERE category = (SELECT key FROM payment_types WHERE id = ?)"),
        ("budget line", "budget lines", "SELECT COUNT(*) FROM budget_lines WHERE category = (SELECT key FROM payment_types WHERE id = ?)"),
        ("checklist rule", "checklist rules", """SELECT COUNT(*) FROM checklist_terms t, json_each(json_extract(t.rule, '$.categories')) j
                                                    WHERE t.rule IS NOT NULL AND j.value = (SELECT key FROM payment_types WHERE id = ?)"""),
        ("matching word rule", "matching word rules", """SELECT (SELECT COUNT(*) FROM guess_words WHERE payment_type = k.key)
                                                           + (SELECT COUNT(*) FROM hint_words WHERE payment_type = k.key)
                                                           FROM payment_types k WHERE k.id = ?"""),
    ],
    "doc_types": [
        ("document", "documents", "SELECT COUNT(*) FROM documents WHERE doc_type = (SELECT key FROM doc_types WHERE id = ?)"),
        ("set of required documents", "sets of required documents",
         "SELECT COUNT(*) FROM required_sets r, json_each(r.docs) j WHERE j.value = (SELECT key FROM doc_types WHERE id = ?)"),
        ("checklist item", "checklist items",
         "SELECT COUNT(*) FROM tasks t, json_each(t.required_docs) j WHERE j.value = (SELECT key FROM doc_types WHERE id = ?)"),
        ("checklist template", "checklist templates",
         """SELECT COUNT(*) FROM checklist_terms t WHERE (SELECT key FROM doc_types WHERE id = ?1) IN
            (SELECT value FROM json_each(t.docs) UNION SELECT value FROM json_each(COALESCE(json_extract(t.rule, '$.docs'), '[]'))
             UNION SELECT value FROM json_each(COALESCE(json_extract(t.rule, '$.on_item'), '[]')))"""),
        ("joiner or leaver reminder rule", "joiner or leaver reminder rules",
         "SELECT COUNT(*) FROM people_task_terms t, json_each(t.docs) j WHERE j.value = (SELECT key FROM doc_types WHERE id = ?)"),
    ],
    "guess_words": [], "hint_words": [], "filing_words": [],
    "parties": [
        ("recurring payment", "recurring payments", "SELECT COUNT(*) FROM payees WHERE party_id = ?"),
        ("SQL entry", "SQL entries", """SELECT COUNT(*) FROM sql_entries s, parties p WHERE p.id = ? AND p.sql_code IS NOT NULL
                                        AND s.code = p.sql_code AND (p.entity_id IS NULL OR s.entity_id = p.entity_id)"""),
        ("SQL filing word rule", "SQL filing word rules", "SELECT COUNT(*) FROM filing_words WHERE party_id = ?"),
    ],
    "gl_accounts": [
        ("bank account", "bank accounts", """SELECT COUNT(*) FROM accounts a, gl_accounts g WHERE g.id = ? AND a.entity_id = g.entity_id
                                             AND a.gl_code = g.code"""),
        ("customer or supplier", "customers and suppliers", """SELECT COUNT(*) FROM parties p, gl_accounts g WHERE g.id = ?
                                             AND p.gl_code = g.code AND (p.entity_id IS NULL OR p.entity_id = g.entity_id)"""),
        ("account under it", "accounts under it", """SELECT COUNT(*) FROM gl_accounts c, gl_accounts g WHERE g.id = ?
                                             AND c.entity_id = g.entity_id AND c.parent_code = g.code"""),
        ("SQL entry", "SQL entries", """SELECT COUNT(*) FROM sql_entries s, gl_accounts g WHERE g.id = ? AND s.entity_id = g.entity_id
                                        AND s.code = g.code"""),
        ("SQL account line", "SQL account lines", """SELECT COUNT(*) FROM ledger_lines l, gl_accounts g WHERE g.id = ?
                                                     AND l.entity_id = g.entity_id AND l.account_code = UPPER(TRIM(g.code))"""),
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
        try:
            n = con.execute(sql, (rid,)).fetchone()[0]
        except sqlite3.OperationalError as x:  # a table a later update adds (a records.db still below it)
            if "no such table" not in str(x):
                raise
            n = 0
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
    if kind in TYPE_KINDS and rec.get("id"):
        out["key"] = "Records refer to it by this key, so it can't change once added."
        used = bool(usage(con, kind, rec["id"]))
        if kind == "payment_types" and (rec.get("system") or used):
            out["direction"] = ("The app relies on this type being money " + rec["direction"] + "." if rec.get("system")
                                else "Payments of this type are money " + rec["direction"] + ", so it can't change once it has any.")
        if kind == "payment_types" and _count(con, """SELECT COUNT(*) FROM payments p JOIN months m ON m.entity_id = p.entity_id
                AND m.month = p.month WHERE p.category = ? AND m.closed_at IS NOT NULL""", rec["key"]):
            out["legal_due_offset"] = out["legal_due_day"] = (
                "Filed months judged their payments of this type by this deadline, so it can't change once one is filed. "
                "Reopen the filed months first if it really must.")
        if kind == "doc_types" and (rec.get("system") or used):
            out["from_sql"] = ("The app relies on this." if rec.get("system")
                               else "Documents and rules of this type are filed by it, so it can't change once used.")
    if kind == "parties" and rec.get("id"):
        used = dict((what, n) for what, n in usage(con, kind, rec["id"]))
        if any("SQL entr" in w for w in used):
            out["sql_code"] = "SQL entries are matched to it by this code, so it can't change once any carry it."
        if used:
            out["entity_id"] = "Recurring payments or SQL entries refer to it, so it stays with the companies it is for: add another one instead."
    if kind == "gl_accounts" and rec.get("id") and usage(con, kind, rec["id"]):
        out["code"] = "Bank accounts, customers, suppliers, other accounts or SQL entries refer to it by this code, so it can't change once used."
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
    if kind == "entities" and rec.get("code") and not _has_checklist(con, rec):
        out.append("This company has no monthly checklist yet: its months are set up with its recurring payments only. "
                   "Add its items in Setup › Monthly checklist, or copy another company's.")
    if kind == "accounts" and rec.get("id") and _count(con, "SELECT COUNT(*) FROM statements WHERE account_id = ?", rec["id"]):
        out.append("Statements have been imported for this account. If you change the account number, the next import is refused "
                   "unless the statement shows the new number.")
    return out


def _has_checklist(con, rec):
    B = checklistbook.get(con)
    if not B.from_tables:
        return rec["code"] in rules.CHECKLIST
    return bool(rec.get("id")) and any(eid == rec["id"] and ts and ts[-1]["in_use"]
                                       for (eid, _), it in B.items.items() for ts in [B.terms.get(it["id"], [])])


# ---------- reading ----------

def listing(con, kind, entity_id=None):
    s = spec(kind)
    if s["per_entity"]:
        if entity_id is None:
            raise Refused("Choose a company.")
        every = " OR entity_id IS NULL" if s.get("or_all") else ""
        rows = con.execute(f"SELECT * FROM {s['table']} WHERE (entity_id = ?{every}) ORDER BY {s.get('order', 'sort, id')}",
                           (entity_id,)).fetchall()
    else:
        rows = con.execute(f"SELECT * FROM {s['table']} ORDER BY {s.get('order', 'sort, id')}").fetchall()
    out = []
    for r in rows:
        r = _decoded(kind, dict(r))
        used = usage(con, kind, r["id"])
        out.append({**r, "used_by": used, "used_total": sum(n for _, n in used), "status": "in_use" if r.get("active", 1) else "stopped"})
    return {"rows": out}


def record(con, kind, rid):
    rec = _row(con, kind, rid)
    used = usage(con, kind, rid)
    return {"record": rec, "used_by": used, "used_total": sum(n for _, n in used), "locked": locked(con, kind, rec),
            "can_delete": not used and not rec.get("system"), "can_stop": _can_stop(kind, rec), "notes": notes(con, kind, rec)}


def _can_stop(kind, rec):
    """Whether Stop using is offered: not for the payment types and document types the app itself relies on."""
    if kind == "payment_types":
        return rec["key"] not in rulebook.UNSTOPPABLE_TYPES
    if kind == "doc_types":
        return not rec["system"] or rec["key"] in rulebook.STOPPABLE_DOCS
    return True


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


def create(con, kind, fields, entity_id=None, quiet=False):
    s = spec(kind)
    vals = _checked(kind, fields)
    for f in s["fields"]:
        if f.get("required") and vals.get(f["key"]) in (None, ""):
            raise Refused(f"{f['label']}: this can't be empty.")
    if kind == "entities":
        _unique_code(con, vals["code"])
        vals.setdefault("uses_sql", 1)
        _shared_codes(con, None, vals.get("sql_database"))
    elif kind in TYPE_KINDS:
        if con.execute(f"SELECT 1 FROM {s['table']} WHERE key = ?", (vals["key"],)).fetchone():
            raise Refused(f"There is already a {s['label'].lower()} with the key {vals['key']}.")
        _legal_pair(kind, vals)
        vals["sort"] = con.execute(f"SELECT COALESCE(MAX(sort), 0) + 1 FROM {s['table']}").fetchone()[0]
    elif kind in WORD_KINDS:
        _word_check(con, kind, vals)
        if vals.get("sort") is None:
            vals["sort"] = con.execute(f"SELECT COALESCE(MAX(sort), 0) + 1 FROM {s['table']}").fetchone()[0]
    elif kind == "parties":
        vals.setdefault("entity_id", None)
        _party_check(con, vals)
    elif kind == "gl_accounts":
        if entity_id is None or not con.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone():
            raise Refused("Choose the company whose chart of accounts it is in.")
        vals["entity_id"] = entity_id
        _gl_check(con, entity_id, vals)
    else:
        if entity_id is None or not con.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone():
            raise Refused("Choose the company the account belongs to.")
        vals["entity_id"] = entity_id
        if vals.get("cash_book") and vals.get("currency") != BASE:
            raise Refused(f"The cash book account is in {BASE}, as SQL Account's cash book listing is.")
        if vals.get("currency") == BASE and not con.execute(
                "SELECT 1 FROM accounts WHERE entity_id = ? AND cash_book = 1 AND active = 1", (entity_id,)).fetchone():
            vals["cash_book"] = 1  # a company's first account in MYR is its cash book until another is chosen
    vals = _stored({k: v for k, v in vals.items() if v is not None})
    cur = con.execute(f"INSERT INTO {s['table']} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values()))
    rid = cur.lastrowid
    if kind == "accounts" and vals.get("cash_book"):
        _only_cash_book(con, entity_id, rid)
    if not quiet:
        db.log(con, f"Added {s['label'].lower()}: {vals[s['name_field']]}")
    if kind == "entities" and _has_table(con, "checklist_items"):
        _starter_checklist(con, rid, vals, quiet)
    rulebook.forget(con)
    return rid


def _has_table(con, name):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone())


def _starter_checklist(con, rid, vals, quiet):
    """A company added here starts with a monthly checklist (checklistbook.seed_company: the starter list, or the list
    the code has for its code), in the same change, so its first month set up has one. Setup changes it from there."""
    checklistbook.seed_company(con, {"id": rid, "code": vals["code"], "uses_sql": vals.get("uses_sql", 1)}, starter=True)
    checklistbook.forget(con)
    n = con.execute("SELECT COUNT(*) FROM checklist_items WHERE entity_id = ?", (rid,)).fetchone()[0]
    if n and not quiet:
        db.log(con, f"Checklist {vals['code']}: started with {n} items")


def _legal_pair(kind, vals, rec=None):
    """A payment type's legal deadline: both the month and the day, or neither; statutory payments keep theirs."""
    if kind != "payment_types":
        return
    off = vals.get("legal_due_offset", rec.get("legal_due_offset") if rec else None)
    day = vals.get("legal_due_day", rec.get("legal_due_day") if rec else None)
    if (off is None) != (day is None):
        raise Refused("Legal deadline: give both the month and the day, or neither.")
    if rec and rec["key"] == "statutory" and day is None:
        raise Refused("Statutory payments keep their legal deadline (KWSP, PERKESO and PCB are due by a set day).")


def _only_cash_book(con, entity_id, rid):
    con.execute("UPDATE accounts SET cash_book = 0 WHERE entity_id = ? AND id != ? AND cash_book = 1", (entity_id, rid))


def update(con, kind, rid, fields, quiet=False):
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
    if kind == "entities" and "sql_database" in vals:
        _shared_codes(con, rid, vals["sql_database"])
    _legal_pair(kind, vals, rec)
    if kind == "parties":
        _party_check(con, vals, rec)
    if kind == "gl_accounts":
        _gl_check(con, rec["entity_id"], vals, rec)
    if kind in WORD_KINDS:
        _word_check(con, kind, vals, rec)
        if "sort" in vals and vals["sort"] is None:  # Order emptied: after the others
            vals["sort"] = con.execute(f"SELECT COALESCE(MAX(sort), 0) + 1 FROM {s['table']}").fetchone()[0]
    if kind == "accounts" and "cash_book" in vals:
        if vals["cash_book"]:
            if not rec["active"]:
                raise Refused("A stopped account can't be the cash book. Use it again first.")
            if vals.get("currency", rec["currency"]) != BASE:
                raise Refused(f"The cash book account is in {BASE}, as SQL Account's cash book listing is.")
            _only_cash_book(con, rec["entity_id"], rid)
        else:
            raise Refused("Each company has one cash book account. Make another account the cash book instead; this one then stops being it.")
    con.execute(f"UPDATE {s['table']} SET {', '.join(k + ' = ?' for k in vals)} WHERE id = ?", (*_stored(vals).values(), rid))
    named = ", ".join(f["label"].lower() for f in s["fields"] if f["key"] in vals)
    if not quiet:
        db.log(con, f"Changed {s['label'].lower()} {rec[s['name_field']]}: {named}")
    rulebook.forget(con)
    return notes(con, kind, {**rec, **vals})


def set_active(con, kind, rid, active):
    s = spec(kind)
    rec = _row(con, kind, rid)
    if bool(rec["active"]) == bool(active):
        return
    if kind == "entities" and not active and not con.execute("SELECT 1 FROM entities WHERE active = 1 AND id != ?", (rid,)).fetchone():
        raise Refused("This is the only company in use, so it can't be stopped. Add or use another company first.")
    if kind == "payment_types" and not active and rec["key"] in rulebook.UNSTOPPABLE_TYPES:
        raise Refused("The app relies on this payment type, so it can't be stopped.")
    if kind == "payment_types" and not active:
        _default_type(con, rec)
    if kind == "doc_types" and not active:
        if rec["system"] and rec["key"] not in rulebook.STOPPABLE_DOCS:
            raise Refused("The app relies on this document type, so it can't be stopped.")
        if rec["key"] in _checklist_docs(con):
            raise Refused("The monthly checklist asks for this document type, so it can't be stopped yet.")
        asked = [rulebook.get(con).label(s["payment_type"]) for s in rulebook.get(con).sets
                 if rec["key"] in s["docs"] and _reaches_open(con, s)]
        if asked:
            raise Refused(f"It is still required for {_words([[a, 1] for a in dict.fromkeys(asked)]).replace('1 ', '')}. "
                          "Take it off their required documents first.")
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
    rulebook.forget(con)


def _checklist_docs(con):
    """The document types the monthly checklist (its items and their payment rules) and the joiner and leaver reminders
    ask for in a month not filed."""
    B = checklistbook.get(con)
    if not B.from_tables:
        out = {d for items in rules.CHECKLIST.values() for *_, docs in items for d in docs}
        out |= {d for *_, docs in rules.PEOPLE_TASKS for d in docs}
        for r in rules.TASK_PAYMENTS.values():
            out |= set(r.get("docs", ())) | set(r.get("on_item", ()))
        return out
    out = set()
    for (eid, _), it in B.items.items():
        for t in B.terms.get(it["id"], []):
            if t["in_use"] and _reaches_open(con, {"entity_id": eid, "to_month": t["to_month"]}):
                r = t["rule"] or {}
                out |= set(t["docs"]) | set(r.get("docs", ())) | set(r.get("on_item", ()))
    for ts in B._pterms.values():
        out |= {d for t in ts if t["in_use"] and _reaches_open(con, {"entity_id": None, "to_month": t["to_month"]}) for d in t["docs"]}
    return out


def _reaches_open(con, s):
    """Whether a set of required documents is still in force for a month that isn't filed (its company's, or any
    company's for a set for every company): open months come after the last filed one."""
    if s["to_month"] is None:
        return True
    ids = [s["entity_id"]] if s["entity_id"] is not None else [r[0] for r in con.execute("SELECT id FROM entities")]
    for e in ids:
        last = _last_filed(con, e)
        if not last or s["to_month"] > db.shift_month(last, 1):
            return True
    return False


def _default_type(con, rec):
    """Refuses stopping or deleting the payment type new recurring payments start on (General settings)."""
    if rec["key"] == appsettings.get("payee_default_category"):
        raise Refused("New recurring payments start on this payment type. Choose another in General settings first.")


def delete(con, kind, rid):
    s = spec(kind)
    rec = _row(con, kind, rid)
    used = usage(con, kind, rid)
    if used:
        raise Refused(f"Used by {_words(used)}, so it can't be deleted. Stop using it instead.", 409)
    if kind == "entities" and not con.execute("SELECT 1 FROM entities WHERE active = 1 AND id != ?", (rid,)).fetchone():
        raise Refused("This is the only company in use, so it can't be deleted.")
    if rec.get("system"):
        raise Refused("The app relies on this, so it can't be deleted.")
    if kind == "payment_types":
        _default_type(con, rec)
    if kind == "payment_types":  # its own sets of required documents go with it (they are part of the type)
        con.execute("DELETE FROM required_sets WHERE payment_type = ?", (rec["key"],))
    if kind == "entities":  # so does a company's own checklist and its own sets: no month was set up with them
        if _has_table(con, "checklist_items"):
            con.execute("DELETE FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?)", (rid,))
            con.execute("DELETE FROM checklist_items WHERE entity_id = ?", (rid,))
            checklistbook.forget(con)
        if _has_table(con, "required_sets"):
            con.execute("DELETE FROM required_sets WHERE entity_id = ?", (rid,))
    con.execute(f"DELETE FROM {s['table']} WHERE id = ?", (rid,))
    if kind == "accounts" and rec["cash_book"]:
        nxt = con.execute("SELECT id FROM accounts WHERE entity_id = ? AND active = 1 AND currency = ? ORDER BY sort, id LIMIT 1",
                          (rec["entity_id"], BASE)).fetchone()
        if nxt:
            con.execute("UPDATE accounts SET cash_book = 1 WHERE id = ?", (nxt["id"],))
    db.log(con, f"Deleted {s['label'].lower()} {rec[s['name_field']]}")
    rulebook.forget(con)


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
    R = rulebook.get(con)
    if "category" in out and not (R.active_type(out["category"]) or (old and out["category"] == old["category"] and out["category"] in R.categories)):
        raise Refused("Choose one of the payment types.")  # as before Setup (the list offers only the ones in use)
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
            if out[k] is not None and not is_day(out[k]):
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
    party_check(con, ent, out, old)
    return out


def party_check(con, ent, out, old=None):
    """A recurring payment's link to a supplier or customer (optional): not for a salary or director's fee, one of the
    company's (or every company's), in use (or the one already linked), and a kind that fits money in or out."""
    if "party_id" in out and out["party_id"] in ("", 0):
        out["party_id"] = None
    if "party_id" in out and isinstance(out["party_id"], str) and out["party_id"].isdigit():
        out["party_id"] = int(out["party_id"])
    old_pid = old["party_id"] if old and "party_id" in old.keys() else None
    pid = out.get("party_id", old_pid)
    if pid is None:
        return
    if isinstance(pid, bool) or not isinstance(pid, int):
        raise Refused("Supplier or customer: choose one from the list.")
    cat = out.get("category", old["category"] if old else None)
    way = out.get("direction", old["direction"] if old else "out") or "out"
    if cat in PERSONAL:
        if "party_id" not in out and old_pid:
            out["party_id"] = None  # it became a salary or director's fee: the link goes
            return
        raise Refused("A salary or director's fee is paid to a person, not a supplier or customer. Remove the link first.")
    p = con.execute("SELECT * FROM parties WHERE id = ?", (pid,)).fetchone()
    if not p or p["entity_id"] not in (None, ent["id"]):
        raise Refused(f"That supplier or customer isn't one of {ent['name']}'s.")
    if not p["active"] and pid != old_pid:
        raise Refused("That supplier or customer is stopped. Choose one in use.")
    if (p["kind"] == "customer" and way == "out") or (p["kind"] == "supplier" and way == "in"):
        raise Refused("A customer pays money in and a supplier is paid money out: choose one that fits.")


def payee_usage(con, pid):
    """[(what, how many)] using a recurring payment: payments made from it, salary advances, budget lines and joiner or
    leaver reminders."""
    found = [
        ("payment", "payments", _count(con, "SELECT COUNT(*) FROM payments WHERE payee_id = ?", pid)),
        ("salary advance", "salary advances", _count(con, "SELECT COUNT(*) FROM advances WHERE payee_id = ?", pid)),
        ("budget line", "budget lines", _count(con, "SELECT COUNT(*) FROM budget_lines WHERE payee_id = ?", pid)),
        ("joiner or leaver reminder", "joiner or leaver reminders",
         _count(con, "SELECT COUNT(*) FROM tasks WHERE code GLOB ? OR code GLOB ?", f"joiner-*-{pid}", f"leaver-*-{pid}")),
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
    appsettings.install(con)


def first_active_account(con, entity_id):
    """The company's cash book account (else its first account in use, else its first account): what the app takes
    when no account is named."""
    r = con.execute("""SELECT id, currency FROM accounts WHERE entity_id = ? ORDER BY active DESC, cash_book DESC, sort, id LIMIT 1""",
                    (entity_id,)).fetchone()
    return r


# ---------- required documents (dated sets, rulebook) ----------

INTERNAL_DOCS = ("statement", "recon", "sqlexport")  # the app's own: a bank statement, its reconciliation, an SQL listing

def _last_filed(con, entity_id):
    """The latest month marked as filed, for the company (or any company): a change starts after it."""
    if entity_id is None:
        return con.execute("SELECT MAX(month) FROM months WHERE closed_at IS NOT NULL").fetchone()[0]
    return con.execute("SELECT MAX(month) FROM months WHERE entity_id = ? AND closed_at IS NOT NULL", (entity_id,)).fetchone()[0]


def _first_open(con, entity_id):
    last = _last_filed(con, entity_id)
    return max(db.shift_month(last, 1), db.current_cycle()) if last else db.current_cycle()


def required_view(con, entity_id=None):
    """What each payment type needs now, for every company or one, with its sets over time (newest first)."""
    if entity_id is not None and not con.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone():
        raise Refused("There is no such company.", 404)
    R = rulebook.get(con)
    types = []
    for k, t in R.types.items():
        now = R.set_for(k, None, entity_id)
        follows = now is None
        if follows:
            now = R.set_for("other", None, entity_id)
        hist = sorted((s for s in R.sets if s["payment_type"] == k and (s["entity_id"] is None or s["entity_id"] == entity_id)),
                      key=lambda s: (s["from_month"], s["entity_id"] is not None), reverse=True)
        types.append({"key": k, "label": t["label"], "active": t["active"], "direction": t["direction"],
                      "docs": now["docs"] if now else [], "own": bool(now and not follows and now["entity_id"] is not None),
                      "follows_other": follows and k != "other", "since": now["from_month"] if now and not follows else None,
                      "history": [{**s} for s in hist]})
    docs = sorted(((k, d) for k, d in R.docs.items() if k not in INTERNAL_DOCS), key=lambda kv: (R.order(kv[0], 999), kv[1]["sort"]))
    last = _last_filed(con, entity_id)
    return {"scope": entity_id, "default_from": _first_open(con, entity_id),
            "first_allowed": db.shift_month(last, 1) if last else None, "types": types,
            "doc_types": [{"key": k, "label": d["label"], "active": d["active"], "from_sql": d["from_sql"]} for k, d in docs]}


def _statuses(con, entity_id, month):
    """{payment id: status} for the payments of the open months from that month on, for the company (or every company)."""
    sql = """SELECT p.*, e.uses_sql AS e_uses_sql FROM payments p JOIN entities e ON e.id = p.entity_id
             WHERE p.month >= ? AND NOT EXISTS (SELECT 1 FROM months m WHERE m.entity_id = p.entity_id AND m.month = p.month
             AND m.closed_at IS NOT NULL)""" + (" AND p.entity_id = ?" if entity_id is not None else "")
    rows = con.execute(sql, (month, entity_id) if entity_id is not None else (month,)).fetchall()
    return {p["id"]: db.payment_status(con, p, p["e_uses_sql"])[0] for p in rows}


def required_save(con, payment_type, entity_id, docs, from_month):
    """A new set of required documents for a payment type, from a payroll month on, for every company (entity_id None)
    or one; docs None for a company: it follows every company's set again from that month. The months before keep
    their sets; a filed month is never reached. Returns {payments, now_missing, now_complete} for the open months."""
    R = rulebook.get(con)
    if payment_type not in R.types:
        raise Refused("There is no such payment type.", 404)
    if entity_id is not None and not con.execute("SELECT 1 FROM entities WHERE id = ?", (entity_id,)).fetchone():
        raise Refused("There is no such company.", 404)
    if not isinstance(from_month, str) or not MONTH.fullmatch(from_month):
        raise Refused("From which month: months are written like 2026-10.")
    last = _last_filed(con, entity_id)
    if last and from_month <= last:
        raise Refused(f"{db.month_label(last)} is filed, and filed months never change. Choose {db.month_label(db.shift_month(last, 1))} or later.")
    if docs is None and entity_id is None:
        raise Refused("Choose the documents.")
    if docs is not None:
        if not isinstance(docs, list) or len(set(docs)) != len(docs):
            raise Refused("Choose each document once.")
        for d in docs:
            if not isinstance(d, str) or not (d in R.docs and R.docs[d]["active"]) or d in INTERNAL_DOCS:
                raise Refused(f"{d} isn't a document type a payment can need.")
    exact = [s for s in R.sets if s["payment_type"] == payment_type and s["entity_id"] == entity_id
             and s["from_month"] <= from_month and (s["to_month"] is None or from_month < s["to_month"])]
    later = [s for s in R.sets if s["payment_type"] == payment_type and s["entity_id"] == entity_id and s["from_month"] > from_month]
    if docs is None and not exact and not later:
        raise Refused("This company already follows the documents set for every company.")
    if docs is not None and exact and exact[0]["docs"] == docs and not later:
        raise Refused("Nothing changes: these are the documents already required from that month.")
    before = _statuses(con, entity_id, from_month)
    con.execute("""UPDATE required_sets SET to_month = ? WHERE payment_type = ? AND entity_id IS ? AND from_month < ?
                   AND (to_month IS NULL OR to_month > ?)""", (from_month, payment_type, entity_id, from_month, from_month))
    con.execute("DELETE FROM required_sets WHERE payment_type = ? AND entity_id IS ? AND from_month >= ?", (payment_type, entity_id, from_month))
    if docs is not None:
        con.execute("INSERT INTO required_sets (payment_type, entity_id, from_month, to_month, docs, set_at) VALUES (?, ?, ?, NULL, ?, ?)",
                    (payment_type, entity_id, from_month, json.dumps(docs), db.now()))
    rulebook.forget(con)
    after = _statuses(con, entity_id, from_month)
    code = con.execute("SELECT code FROM entities WHERE id = ?", (entity_id,)).fetchone()[0] if entity_id is not None else "every company"
    what = ("follows every company's documents again" if docs is None
            else "needs " + (", ".join(R.short_doc(d) for d in docs) or "no documents"))
    db.log(con, f"Required documents: {R.label(payment_type)} ({code}) {what}, from {db.month_label(from_month)}")
    moved = [pid for pid in after if after[pid] != before.get(pid)]
    return {"payments": len(moved), "now_missing": sum(before[p] == "complete" for p in moved),
            "now_complete": sum(after[p] == "complete" for p in moved)}
