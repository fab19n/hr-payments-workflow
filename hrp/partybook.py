"""Customers and suppliers (parties) and each company's chart of accounts (gl_accounts): kept in records.db from update
22 and entered in Setup, by hand or by pasting a list (a text export from SQL Account, a copy of one of its grids, or a
list from Excel).

A party's SQL code ties SQL entries to it: a voucher whose code is the code of the supplier or customer a recurring
payment is linked to counts as naming that payment, and an SQL filing rule can name a party, so a document with its
code is filed on that checklist item before any words are tried. Nothing changes while no codes are entered or a listing
carries none. Staff are never parties: they stay recurring payments, so their details aren't kept twice.

Pasting adds and updates records by code and never stops or deletes one; an empty cell never clears a field.
"""
import csv
import io
import re
import xml.etree.ElementTree as ET
from collections import Counter

SINCE = 22
KINDS = ("customer", "supplier", "related", "statutory")
SQL_EXTRA = ("code", "payment_method", "cheque_no", "dockey", "currency_code")  # sql_entries columns from update 22
MAX_TEXT, MAX_ROWS = 1_000_000, 5000

TABLES = """
CREATE TABLE IF NOT EXISTS parties (
  id INTEGER PRIMARY KEY, entity_id INTEGER REFERENCES entities(id),
  kind TEXT NOT NULL CHECK (kind IN ('customer', 'supplier', 'related', 'statutory')),
  name TEXT NOT NULL, short_name TEXT, sql_code TEXT, tin TEXT, brn TEXT,
  match_words TEXT CHECK (match_words IS NULL OR json_valid(match_words)), gl_code TEXT,
  active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS parties_code ON parties (COALESCE(entity_id, 0), sql_code) WHERE sql_code IS NOT NULL;
CREATE TABLE IF NOT EXISTS gl_accounts (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), code TEXT NOT NULL, name TEXT NOT NULL,
  type TEXT CHECK (type IS NULL OR type IN ('asset', 'liability', 'equity', 'income', 'expense')),
  special TEXT CHECK (special IS NULL OR special IN ('bank', 'cash', 'debtor_control', 'creditor_control',
                                                    'accumulated_depreciation', 'deposit', 'stock', 'opening_stock',
                                                    'closing_stock')),
  parent_code TEXT, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT,
  UNIQUE (entity_id, code)
)
"""


def install(con):
    """Update 22: the customers and suppliers and the chart of accounts (both empty: entered in Setup), a link from a
    recurring payment and from an SQL filing rule to a party, and the SQL entries' code, payment method, cheque number,
    document key and currency, kept from listings that carry them. Nothing in the records changes."""
    from . import audit, db
    for stmt in TABLES.split(";"):
        if stmt.strip():
            con.execute(stmt)
    db.add_column(con, "payees", "party_id", "INTEGER REFERENCES parties(id)")
    db.add_column(con, "filing_words", "party_id", "INTEGER REFERENCES parties(id)")
    for col in SQL_EXTRA:
        db.add_column(con, "sql_entries", col, "TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS payees_party ON payees (party_id) WHERE party_id IS NOT NULL")
    con.execute("CREATE INDEX IF NOT EXISTS sql_entries_code ON sql_entries (code, entity_id) WHERE code IS NOT NULL")
    audit.refresh(con)


def widen_specials(con):
    """Update 23: the chart of accounts keeps all of SQL Account's special account types (cash, accumulated depreciation,
    deposits and the stock accounts as well as bank and debtor and creditor control). SQLite can't change a CHECK in place, so
    the table is made again and every row copied as it was, with the same id (the trail's rows still name them). Only
    the chart's own capture triggers go with the old table (no other trigger names it); db.init puts them back after
    the step as an update step's change. Dropping every trigger instead would leave the trail looking stopped, so the
    refresh after the step would do nothing and start-up would record the triggers as missing. Nothing in the records
    changes. Records made at update 22 from this version already allow them: then nothing is done."""
    have = con.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'gl_accounts'").fetchone()
    if not have or "'deposit'" in have[0]:
        return
    make = next(s for s in TABLES.split(";") if "TABLE IF NOT EXISTS gl_accounts" in s)
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'gl_accounts'").fetchall():
        con.execute(f'DROP TRIGGER "{name}"')
    con.execute(make.replace("CREATE TABLE IF NOT EXISTS gl_accounts", "CREATE TABLE gl_accounts_new"))
    cols = ", ".join(r[1] for r in con.execute("PRAGMA table_info(gl_accounts)"))
    con.execute(f"INSERT INTO gl_accounts_new ({cols}) SELECT {cols} FROM gl_accounts")
    con.execute("DROP TABLE gl_accounts")
    con.execute("ALTER TABLE gl_accounts_new RENAME TO gl_accounts")


def keep_sql_types(con):
    """Update 24: each account in the chart keeps SQL Account's account group (its A/C Type: FA, CA, CL, ...), so the
    chart can be shown as SQL groups it, as a tree. Empty for accounts already there until they are pasted again or
    changed. Nothing else in the records changes."""
    from . import db
    codes = ", ".join(f"'{code}'" for code, _, _ in SQL_GROUPS)
    db.add_column(con, "gl_accounts", "sql_type", f"TEXT CHECK (sql_type IS NULL OR sql_type IN ({codes}))")


def _has_sql_type(con):
    return "sql_type" in {r[1] for r in con.execute("PRAGMA table_info(gl_accounts)")}


def ready(con):
    return con.execute("PRAGMA user_version").fetchone()[0] >= SINCE


def payee_codes(con, entity_id):
    """{payee id: the SQL code of the supplier or customer it is linked to}, for the company (none below update 22)."""
    if not ready(con):
        return {}
    return {r[0]: r[1].upper() for r in con.execute(
        """SELECT py.id, pt.sql_code FROM payees py JOIN parties pt ON pt.id = py.party_id
           WHERE py.entity_id = ? AND pt.sql_code IS NOT NULL AND pt.sql_code != ''
           AND (pt.entity_id IS NULL OR pt.entity_id = ?)""", (entity_id, entity_id))}


def coded(codes, p, r):
    """True when the SQL entry r carries the code of the party payment p's recurring payment is linked to."""
    c = codes.get(p["payee_id"]) if codes else None
    return bool(c and (r.get("code") or "").upper() == c)


# ---------- reading a pasted list ----------

def datapacket_table(text):
    """A grid copied from SQL Account (a DATAPACKET): every attribute is a column, in the order first seen."""
    root = ET.fromstring(text.strip().lstrip("﻿").encode("utf-8"))
    rows = [dict(r.attrib) for r in root.iter("ROW")]
    head = list(dict.fromkeys(k for r in rows for k in r))
    return [head] + [[(r.get(k) or "").strip() for k in head] for r in rows]


def _rule_line(cells):
    return all(re.fullmatch(r"[-=+|:\s]*", c or "") for c in cells)


def _tidy(rows):
    rows = [r for r in rows if any(c.strip() for c in r) and not _rule_line(r)]
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i].strip() for r in rows)]
    return [[r[i].strip() for i in keep] for r in rows]


def _fixed(lines):
    """Columns cut where every line has a run of two or more spaces (a report printed to a text file)."""
    width = max(len(l) for l in lines)
    pad = [l.ljust(width) for l in lines]
    blank = [all(l[i] == " " for l in pad) for i in range(width)]
    cuts, i = [], 0
    while i < width:
        if blank[i]:
            j = i
            while j < width and blank[j]:
                j += 1
            if j - i >= 2 or i == 0:
                cuts.append((i, j))
            i = j
        else:
            i += 1
    starts = [0] + [j for i, j in cuts if j < width and i > 0]
    if cuts and cuts[0][0] == 0:
        starts[0] = cuts[0][1]
    spans = [(s, starts[k + 1] if k + 1 < len(starts) else width) for k, s in enumerate(starts)]
    return [[l[a:b].strip() for a, b in spans] for l in pad]


def _spans(line):
    """The cells of a printed line as [(where it starts, its text)]: cut where two or more spaces fall."""
    return [(m.start(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", line)]


def _heading_fields(cells, kind):
    """{field: index} for the cells of a line that head a field of `kind`, the first cell for each field."""
    found = {}
    for i, (_, c) in enumerate(cells):
        n = _norm(c)
        for field, words in HEADINGS[kind].items():
            if n in words:
                found.setdefault(field, i)
                break
    return found


def _place(cells, cols):
    """A printed line's cells under the headings of its page (cols: [(start, end, column)], left to right) as
    {column: text}. A cell goes under the last heading starting no more than 2 places to its right; but a cell that
    follows another under that heading and ends within 2 places of where a later heading ends (a figure right-aligned
    under a shorter heading, such as 1,000.00 under Balance) goes under that one."""
    row = {}
    for s, t in cells:
        e = s + len(t)
        n = max([i for i, (cs, _, _) in enumerate(cols) if cs <= s + 2], default=0)
        k = cols[n][2]
        if row.get(k):
            k = next((ci for cs, ce, ci in cols[n + 1:] if abs(e - ce) <= 2), k)
        row[k] = f"{row[k]} {t}" if row.get(k) else t
    return row


def _report(text, kind):
    """A report printed to a text file, as SQL Account's listings are: a page header, then a heading row naming the
    code and the name, on every page, with the columns shifted a little from page to page. Returns (rows, a heading row
    first, and a note on the reading), or None when no line heads the code and the name, or when nothing shows it is a
    printed report (one heading row, no page break, nothing above it): a list lined up with spaces is read as
    fixed-width columns, as before.

    Each line is cut where two or more spaces fall and its cells placed under its own page's headings (_place). Left
    out: a page header (from a page break to the next heading row) and lines without both a code (with no space in it)
    and a name: page headings, totals, and group headings such as CURRENT ASSETS (a code-column word with a type and no
    name). Lines above the first heading row are read with its columns (shifted up to 6 places, nearest first, as their
    own page may be), so a paste that starts mid-page keeps the accounts it starts with. An account printed further in than the one above it sits under that one: that gives a
    Parent column. A group heading ends the accounts it could sit under; a page header doesn't."""
    head = cols = None
    rows, parents, stack, before = [], [], [], []
    pages = breaks = left = early = 0
    in_header = False

    def take(cells, first):
        nonlocal left, early, stack
        # A line above the first heading row is from a page whose own heading row wasn't pasted, shifted a few places
        # from this one: the nearest shift that gives it a code and a name is taken.
        for d in ((0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6) if first else (0,)):
            at = [(cs + d, ce + d, ci) for cs, ce, ci in cols]
            row = _place(cells, at)
            code, name = row.get(code_i, ""), row.get(name_i, "")
            if d == 0 and code and not name and type_i is not None and row.get(type_i):
                stack = []  # a group heading: no account sits under one before it
            if code and name and " " not in code:
                break
        else:
            left += 1
            return
        code_at = next(s for s, t in cells if code.startswith(t))
        indent = code_at - next(cs for cs, _, ci in at if ci == code_i)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parents.append(stack[-1][1] if stack else "")
        stack.append((indent, code.upper()))
        rows.append([row.get(i, "") for i in range(len(head))])
        early += first

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if "\f" in line:
            breaks += 1
            in_header = True  # a page break, on a line of its own too: the page header runs to the next heading row
        line = line.replace("\f", "").replace("\t", " ").rstrip()
        if not line.strip():
            continue
        cells = _spans(line)
        found = _heading_fields(cells, kind)
        if all(f in found for f in REQUIRED[kind]) and len(found) >= 2:
            labels = [c for _, c in cells]
            if head is None:
                head = labels
                code_i, name_i, type_i = found[REQUIRED[kind][0]], found["name"], found.get("type")
            # this page's columns: where each heading starts and ends, and which column of the first page it is
            cols = [(s, s + len(c), head.index(c)) for s, c in cells if c in head]
            pages, in_header = pages + 1, False
            if pages == 1:
                for b in before:
                    take(b, True)
            continue
        if cols is None:
            before.append(cells)
        elif in_header:
            left += 1
        else:
            take(cells, False)
    if head is None or not (pages > 1 or breaks or before):
        return None
    if any(parents):
        head = head + [PARENT_HEADING]
        rows = [r + [p] for r, p in zip(rows, parents)]
    note = (f"{pages} page{'s' if pages != 1 else ''}."
            + (f" {left} other line{'s were' if left != 1 else ' was'} left out: page headings, group headings, totals "
               "and any line without both a code and a name." if left else "")
            + (f" The first {early} row{'s' if early != 1 else ''} came before any heading row and {'were' if early != 1 else 'was'} "
               "read with the first one's columns: check them." if early else "")
            + (" The Parent column comes from how far in each code is printed." if any(parents) else ""))
    return [head] + rows, note


def split_columns(text, kind=None):
    """Pasted text as (how it was read, rows of cells, for each row whether it has more or fewer cells than most, a
    note on the reading or None): a DATAPACKET ('sql'); else the separator (tab, |, ;, comma) found on at least 80% of
    the lines, splitting them into 2 or more cells, the one on most lines, tab first on a tie; else, given the kind, a
    printed report with a heading row naming the code and the name ('report', see _report); else fixed-width columns
    ('fixed'); else one column ('one'). Quotes count only with ; and comma."""
    if len(text) > MAX_TEXT:
        raise ValueError("That is too much text to read at once: paste at most 5,000 rows.")
    if "<DATAPACKET" in text[:500]:
        try:
            rows = _tidy(datapacket_table(text))
        except ET.ParseError:
            raise ValueError("This looks like a copy from SQL Account, but it is cut short. Copy it again.")
        return "sql", rows, [False] * len(rows), None
    lines = [l.rstrip(" ") for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    if len(lines) > MAX_ROWS + 50:
        raise ValueError("That is too many rows: paste at most 5,000 at a time.")
    if not lines:
        raise ValueError("Paste the list first.")
    if max(len(l) for l in lines) > 5000:
        raise ValueError("A line of the list is too long to be one row. Check that what was pasted is the list.")
    real = [l for l in lines if not _rule_line([l])]
    report = _report(text, kind) if kind in HEADINGS else None
    if report and len(report[0]) < 2:
        report = None
    best = None
    for name, d in (("tab", "\t"), ("pipe", "|"), ("semicolon", ";"), ("comma", ",")):
        # how many lines the separator is on; a comma inside a figure (12,000.00) doesn't count
        probe = [re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", l) for l in real] if name == "comma" else real
        share = sum(d in l for l in probe) / len(real)
        if share < 0.8 or (best is not None and share <= best[0]):
            continue
        quoting = csv.QUOTE_MINIMAL if name in ("semicolon", "comma") else csv.QUOTE_NONE
        try:
            rows = [next(csv.reader([l], delimiter=d, skipinitialspace=True, quoting=quoting), []) for l in real]
        except csv.Error:
            continue
        if name == "pipe":
            rows = [r[1:] if r and not r[0].strip() else r for r in rows]
            rows = [r[:-1] if r and not r[-1].strip() else r for r in rows]
        counts = [len(r) - next((i for i, c in enumerate(reversed(r)) if c.strip()), len(r)) for r in rows]
        width = Counter(counts).most_common(1)[0][0]  # cells per row, an empty last cell or two not counted
        if width >= 2:
            best = (share, name, rows, [n != width for n in counts])
    if best:
        _, name, rows, odd = best
        keep = [i for i, r in enumerate(rows) if any(c.strip() for c in r) and not _rule_line(r)]
        rows = _tidy([[c.strip() for c in rows[i]] for i in keep])
        # A printed report whose lines happen to carry the separator (an address with a comma on most lines) is still a
        # report: its heading row isn't split by it, so the separator reading finds no heading row.
        if not (report and guess_columns(kind, rows)[0] == -1):
            return name, rows, [odd[i] for i in keep], None
    if report:
        rows, note = report
        return "report", rows, [False] * len(rows), note
    rows = _tidy(_fixed(real))
    if rows and max(len(r) for r in rows) >= 2:
        return "fixed", rows, [False] * len(rows), None
    return "one", [[l.strip()] for l in real], [False] * len(real), None


def _type_of(v):
    """An account type from how a chart names it (Fixed Assets, Current Liabilities, CA, Sales), else None."""
    n = _norm(v)
    if n in TYPE_WORDS:
        return TYPE_WORDS[n]
    if n in TYPE_CODES:
        return TYPE_CODES[n]
    for word, t in (("asset", "asset"), ("liabilit", "liability"), ("equity", "equity"), ("capital", "equity"),
                    ("retained", "equity"), ("reserve", "equity"), ("income", "income"), ("revenue", "income"),
                    ("sales", "income"), ("expense", "expense"), ("cost", "expense")):
        if word in n:
            return t
    return None


def _special_of(v):
    """A special account type from how a chart names it (Bank, Debtor control, BA, AD), else None."""
    n = _norm(v)
    if n in SPECIAL_WORDS:
        return SPECIAL_WORDS[n]
    if n in SPECIAL_CODES:
        return SPECIAL_CODES[n]
    for word, t in (("bank", "bank"), ("debtor", "debtor_control"), ("receivable", "debtor_control"),
                    ("creditor", "creditor_control"), ("payable", "creditor_control"), ("depreciat", "accumulated_depreciation"),
                    ("opening stock", "opening_stock"), ("closing stock", "closing_stock"), ("stock", "stock"),
                    ("cash", "cash"), ("deposit", "deposit"), ("prepay", "deposit")):
        if word in n:
            return t
    return None


# What each field may be headed in a list, after the heading is made lower case and spaces tidied.
HEADINGS = {
    "parties": {"sql_code": ("code", "sql code", "customer code", "supplier code", "creditor code", "debtor code", "account code",
                             "acc code", "acc. code"),
                "name": ("company name", "companyname", "name", "customer name", "supplier name", "description", "company"),
                "kind": ("kind",),
                "short_name": ("short name", "shortname"),
                "tin": ("tin", "tin no", "tin no.", "tax id", "tax identification no", "tax identification no."),
                "brn": ("brn", "new brn", "registration no", "registration no.", "reg no", "reg. no.", "business registration no",
                        "roc", "company reg no"),
                "gl_code": ("control account", "controlaccount", "control a/c", "gl code", "control ac"),
                "notes": ("remark", "remarks", "note", "notes")},
    "gl_accounts": {"code": ("code", "account code", "acc code", "acc. code", "gl code", "account no", "account no."),
                    "name": ("description", "name", "account name", "account", "description 1"),
                    "type": ("type", "acc type", "account type", "acctype", "a/c type", "ac type"),
                    "special": ("special", "special account type", "special type", "specialacctype"),
                    "parent_code": ("parent", "parent code", "parent account", "parentcode", "parent (from the indent)"),
                    "notes": ("remark", "remarks", "note", "notes")},
}
REQUIRED = {"parties": ("sql_code", "name"), "gl_accounts": ("code", "name")}
TYPE_WORDS = {"asset": "asset", "assets": "asset", "fixed asset": "asset", "current asset": "asset", "liability": "liability",
              "liabilities": "liability", "current liability": "liability", "long term liability": "liability",
              "equity": "equity", "capital": "equity", "retained earning": "equity", "income": "income", "sales": "income",
              "revenue": "income", "other income": "income", "expense": "expense", "expenses": "expense", "cost of sales": "expense",
              "cost of goods sold": "expense"}
# SQL Account's own short account types (A/C Type): fixed assets, investments, other and current assets; current,
# other and long-term liabilities; capital, reserves, retained earnings, appropriation; sales and their adjustments,
# other and extraordinary income; cost of goods sold, expenses, taxation.
TYPE_CODES = {"fa": "asset", "iv": "asset", "oa": "asset", "ca": "asset", "cl": "liability", "ol": "liability",
              "lt": "liability", "ll": "liability", "cp": "equity", "rv": "equity", "re": "equity", "ap": "equity",
              "sl": "income", "sa": "income", "oi": "income", "eo": "income", "co": "expense", "cs": "expense",
              "ep": "expense", "ex": "expense", "tx": "expense"}
# SQL Account's short special account types: bank, cash, debtor and creditor control, accumulated depreciation,
# deposits (prepayments paid or received), and the stock accounts (on the balance sheet, opening and closing).
SPECIAL_CODES = {"ba": "bank", "ch": "cash", "dc": "debtor_control", "cc": "creditor_control",
                 "ad": "accumulated_depreciation", "dp": "deposit", "bs": "stock", "os": "opening_stock",
                 "cs": "closing_stock"}
PARENT_HEADING = "Parent (from the indent)"
# SQL Account's account groups (its A/C Type), in the order its chart of accounts prints them, with the chart's own
# five types each falls under. The tree view of the chart groups accounts by these.
SQL_GROUPS = [("FA", "Non-current assets", "asset"), ("IV", "Investment", "asset"), ("OA", "Other assets", "asset"),
              ("CA", "Current assets", "asset"), ("CL", "Current liabilities", "liability"),
              ("OL", "Other liabilities", "liability"), ("CP", "Equity", "equity"), ("RV", "Reserve", "equity"),
              ("RE", "Retained earnings", "equity"), ("LT", "Non-current liabilities", "liability"),
              ("SL", "Revenue", "income"), ("SA", "Revenue adjustment", "income"), ("CO", "Cost of goods sold", "expense"),
              ("OI", "Other income", "income"), ("EO", "Extraordinary income", "income"), ("EP", "Expenses", "expense"),
              ("TX", "Taxation", "expense"), ("AP", "Appropriation account", "equity")]
GROUP_TYPE = {code: t for code, _, t in SQL_GROUPS}
GROUP_WORDS = {**{name.lower(): code for code, name, _ in SQL_GROUPS},
               "fixed asset": "FA", "fixed assets": "FA", "non current assets": "FA", "investments": "IV",
               "current asset": "CA", "current liability": "CL", "long term liabilities": "LT", "long term liability": "LT",
               "non current liabilities": "LT", "capital": "CP", "reserves": "RV", "retained earning": "RE",
               "sales": "SL", "sales adjustment": "SA", "extra ordinary income": "EO", "expense": "EP", "tax": "TX",
               "appropriation": "AP"}


def group_of(v):
    """SQL's account group (FA, CA, ...) from how a chart names an account's type, else None."""
    n = _norm(v)
    if n.upper() in GROUP_TYPE:
        return n.upper()
    return GROUP_WORDS.get(n.replace("-", " ")) or GROUP_WORDS.get(n)
SPECIAL_WORDS = {"bank": "bank", "bank account": "bank", "debtor control": "debtor_control", "trade debtor": "debtor_control",
                 "debtor": "debtor_control", "creditor control": "creditor_control", "trade creditor": "creditor_control",
                 "creditor": "creditor_control", "cash": "cash", "cash in hand": "cash", "petty cash": "cash",
                 "accumulated depreciation": "accumulated_depreciation", "stock": "stock", "opening stock": "opening_stock",
                 "closing stock": "closing_stock", "deposit": "deposit", "prepayment": "deposit"}


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower().replace("_", " "))


def guess_columns(kind, rows):
    """(heading row index or -1, {field: column}). The heading row is the first of the top 20 naming the code and the
    name; without one, the column whose cells look most like codes is the code and the longest text column the name."""
    names = HEADINGS[kind]
    for i, row in enumerate(rows[:20]):
        mapping = {}
        for col, cell in enumerate(row):
            n = _norm(cell)
            for field, words in names.items():
                if field not in mapping and n in words:
                    mapping[field] = col
                    break
        if all(f in mapping for f in REQUIRED[kind]):
            return i, mapping
    width = max(len(r) for r in rows)
    look = re.compile(r"[A-Z0-9]{1,8}([-/.][A-Z0-9]{1,10})+|[0-9]{3,10}")
    sample = rows[:200]
    score = [sum(bool(look.fullmatch((r[c] if c < len(r) else "").strip().upper())) for r in sample) for c in range(width)]
    code = max(range(width), key=lambda c: score[c]) if width else None
    if code is None or score[code] == 0:
        return -1, {}
    rest = [c for c in range(width) if c != code]
    name = max(rest, key=lambda c: sum(len(r[c]) if c < len(r) else 0 for r in sample), default=None)
    out = {REQUIRED[kind][0]: code}
    if name is not None:
        out["name"] = name
    return -1, out


def headings(rows, header_row):
    if header_row >= 0:
        return [str(c) for c in rows[header_row]]
    first = rows[0] if rows else []
    return [f"Column {i + 1}: {str(c)[:25]}" for i, c in enumerate(first)]


# ---------- adding and updating from a list ----------

def _cell(row, mapping, field):
    i = mapping.get(field)
    return row[i].strip() if i is not None and isinstance(i, int) and 0 <= i < len(row) and row[i].strip() else None


def paste(con, kind, b):
    """Reads a pasted list and adds or updates records by code (see the module's notes). b: {entity_id, text, scope,
    kind, header_row, mapping}. Returns what each row does and the counts; the caller undoes it all for a preview."""
    from . import db, masters
    from .masters import Refused
    if kind not in HEADINGS:
        raise Refused("A list can be pasted for customers and suppliers, or the chart of accounts.", 404)
    if not ready(con):
        raise Refused("Lists can be pasted once the records are updated.", 409)
    eid = b.get("entity_id")
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone() if isinstance(eid, int) and not isinstance(eid, bool) else None
    if not ent:
        raise Refused("Choose a company.")
    text = b.get("text")
    if not isinstance(text, str) or not text.strip():
        raise Refused("Paste the list first.")
    try:
        how, rows, odd, read_note = split_columns(text, kind)
    except ValueError as x:
        raise Refused(str(x))
    if not rows:
        raise Refused("No rows were found in the list.")
    header_row, mapping = b.get("header_row"), b.get("mapping")
    if not isinstance(mapping, dict) or not isinstance(header_row, int) or isinstance(header_row, bool) or not -1 <= header_row < len(rows):
        header_row, mapping = guess_columns(kind, rows)
    width = max(len(r) for r in rows)
    mapping = {f: c for f, c in mapping.items() if f in HEADINGS[kind] and isinstance(c, int) and not isinstance(c, bool) and 0 <= c < width}
    spec = masters.spec(kind)
    fields = {f["key"]: f for f in spec["fields"]}
    out = {"how": how, "read_note": read_note, "headers": headings(rows, header_row), "header_row": header_row, "mapping": mapping,
           "fields": [{"key": f, "label": fields[f]["label"], "required": f in REQUIRED[kind]} for f in HEADINGS[kind]],
           "rows": [], "counts": {"add": 0, "update": 0, "same": 0, "error": 0}}
    missing = [fields[f]["label"] for f in REQUIRED[kind] if f not in mapping]
    if missing:
        out["message"] = f"Say which column holds the {' and the '.join(m.lower() for m in missing)}."
        return out
    data, odd = rows[header_row + 1:], odd[header_row + 1:]
    if len(data) > MAX_ROWS:
        raise Refused("That is too many rows: paste at most 5,000 at a time.")
    scope = None
    if kind == "parties":
        scope = None if b.get("scope") == "all" else ent["id"]
        fixed_kind = b.get("kind")
        if fixed_kind is not None and fixed_kind not in KINDS:
            raise Refused("Say whether these are customers, suppliers, related companies or statutory bodies.")
    key = REQUIRED[kind][0]
    seen, parents = {}, []
    groups = kind == "gl_accounts" and _has_sql_type(con)
    for n, (row, uneven) in enumerate(zip(data, odd), start=header_row + 2):
        code = (_cell(row, mapping, key) or "").upper()
        name = _cell(row, mapping, "name")
        res = {"row": n, "code": code, "name": name, "action": "same", "changes": [], "message": None}
        out["rows"].append(res)
        try:
            if uneven and how in ("comma", "semicolon"):
                raise Refused("This row has more or fewer columns than the others: check for a comma inside a name.")
            if not code:
                raise Refused("No code in this row.")
            if code in seen:
                raise Refused(f"This code appears twice (row {seen[code]}).")
            seen[code] = n
            vals, notes, exact = {}, [], False
            for f in HEADINGS[kind]:
                v = _cell(row, mapping, f)
                if v is None or f == key:
                    continue
                if f == "kind":
                    v = v.lower()
                if f == "type" and groups and group_of(v):
                    vals["sql_type"] = group_of(v)
                    vals["type"] = GROUP_TYPE[vals["sql_type"]]  # the type an SQL group falls under (masters checks it)
                    exact = v.strip().upper() in GROUP_TYPE  # SQL's own code (FA, RE), not a word such as Equity
                    continue
                if f in ("type", "special"):
                    got = _type_of(v) if f == "type" else _special_of(v)
                    if got is None:
                        notes.append(f"{fields[f]['label']} {v} not recognised: left as it was.")
                        continue
                    v = got
                if f == "parent_code":
                    parents.append((n, code, v.upper(), res, notes))
                    continue
                if f in fields and fields[f]["type"] not in ("text", "textarea") and f != "kind":
                    try:
                        masters.check_value(fields[f], v)
                    except Refused as x:  # an optional value that can't be read: the rest of the row still counts
                        notes.append(f"{x} Left as it was.")
                        continue
                vals[f] = v
            if kind == "parties" and b.get("kind"):
                vals["kind"] = b["kind"]
            if notes:
                res["message"] = " ".join(notes)
            if kind == "parties":
                have = con.execute("SELECT * FROM parties WHERE UPPER(sql_code) = ? AND entity_id IS ?", (code, scope)).fetchone()
                other = con.execute("""SELECT 1 FROM parties WHERE UPPER(sql_code) = ? AND entity_id IS NOT ?
                                       AND (entity_id IS NULL OR ? IS NULL OR entity_id = ?)""", (code, scope, scope, scope)).fetchone()
                if other:
                    raise Refused("A customer or supplier with this code is kept for " +
                                  ("every company" if scope is not None else "one company") + ": change it there.")
            else:
                have = con.execute("SELECT * FROM gl_accounts WHERE entity_id = ? AND code = ?", (ent["id"], code)).fetchone()
                # A type in words (Equity, Expenses) names SQL's broad group, but an account already in a narrower one of
                # that type (Retained earnings, Cost of goods sold) stays in it: only SQL's own code moves it.
                if (have and not exact and vals.get("sql_type") and have["sql_type"]
                        and GROUP_TYPE.get(have["sql_type"]) == vals.get("type")):
                    del vals["sql_type"]
            sp = con.execute("SAVEPOINT paste_row")
            try:
                if have and kind == "parties" and vals.get("kind") and vals["kind"] != have["kind"]:
                    raise Refused(f"A {have['kind']} already has this code: a paste doesn't change what kind it is. Change it in "
                                  "its own record if it really must.")
                if have:
                    rec = masters._decoded(kind, dict(have))
                    changes = {k: v for k, v in masters._checked(kind, vals, rec).items() if v is not None and v != rec.get(k)}
                    if changes:
                        masters.update(con, kind, have["id"], changes, quiet=True)
                        res["action"] = "update"
                        res["changes"] = [[fields[k]["label"], "" if rec.get(k) is None else str(rec.get(k)), str(v)] for k, v in changes.items()]
                        if not rec.get("active", 1):
                            res["message"] = " ".join(filter(None, [res["message"], "Stopped: it stays stopped."]))
                else:
                    if kind == "parties" and "kind" not in vals:
                        raise Refused("Say whether it is a customer or a supplier (choose above, or map a Kind column).")
                    new = {**vals, key: code}
                    if kind == "parties":
                        new["entity_id"] = scope
                    masters.create(con, kind, new, entity_id=ent["id"], quiet=True)
                    res["action"] = "add"
                con.execute("RELEASE paste_row")
            except Exception:
                con.execute("ROLLBACK TO paste_row")
                con.execute("RELEASE paste_row")
                raise
        except Refused as x:
            res["action"], res["message"], res["changes"] = "error", str(x), []
        out["counts"][res["action"]] += 1
    # Parent accounts last, so an account may come before the one it sits under
    for n, code, parent, res, notes in parents:
        if res["action"] == "error":
            continue
        have = con.execute("SELECT * FROM gl_accounts WHERE entity_id = ? AND code = ?", (ent["id"], code)).fetchone()
        if not have or have["parent_code"] == parent:
            continue
        con.execute("SAVEPOINT paste_parent")
        try:
            masters.update(con, kind, have["id"], {"parent_code": parent}, quiet=True)
            con.execute("RELEASE paste_parent")
            res["changes"].append([fields["parent_code"]["label"], have["parent_code"] or "", parent])
            if res["action"] == "same":
                res["action"] = "update"
                out["counts"]["same"] -= 1
                out["counts"]["update"] += 1
        except Refused as x:
            con.execute("ROLLBACK TO paste_parent")
            con.execute("RELEASE paste_parent")
            res["message"] = " ".join(filter(None, [res["message"], f"{x} Left as it was."]))
    c = out["counts"]
    what = "customers and suppliers" if kind == "parties" else "the chart of accounts"
    db.log(con, f"Pasted {what} for {ent['code'] if scope is not None or kind != 'parties' else 'every company'}: "
                f"{c['add']} added, {c['update']} changed, {c['same']} as they were, {c['error']} skipped")
    return out
