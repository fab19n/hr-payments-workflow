"""SQLite storage and month generation."""
import calendar
import json
import re
import sqlite3
from datetime import date, datetime, timedelta

from . import appsettings, audit, checklistbook, partybook, rulebook, rules
from .config import BACKUP_DIR, DB_PATH, PACKS_DIR, SEED_PATH
from .sqlimport import MONEY_IN, MONEY_OUT, PURCHASE_DOCS, SALES_DOCS

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, uses_sql INTEGER NOT NULL DEFAULT 1,
  first_month TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id),
  label TEXT NOT NULL, bank TEXT, number TEXT, currency TEXT NOT NULL DEFAULT 'MYR'
);
CREATE TABLE IF NOT EXISTS payees (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id),
  account_id INTEGER REFERENCES accounts(id),
  name TEXT NOT NULL, category TEXT NOT NULL, desc_template TEXT NOT NULL,
  amount REAL, amount_varies INTEGER NOT NULL DEFAULT 0,
  month_offset INTEGER NOT NULL DEFAULT 0, due_day INTEGER NOT NULL DEFAULT 26,
  bank_details TEXT, reference TEXT, match_words TEXT,
  active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT,
  start_date TEXT, end_date TEXT, direction TEXT NOT NULL DEFAULT 'out'
);
CREATE TABLE IF NOT EXISTS advances (
  id INTEGER PRIMARY KEY, payee_id INTEGER NOT NULL REFERENCES payees(id),
  monthly_deduction REAL NOT NULL, start_month TEXT NOT NULL, end_month TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS months (
  entity_id INTEGER NOT NULL, month TEXT NOT NULL, generated_at TEXT NOT NULL, opening_balance REAL, closed_at TEXT,
  PRIMARY KEY (entity_id, month)
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, month TEXT NOT NULL, code TEXT NOT NULL,
  title TEXT NOT NULL, detail TEXT, due_date TEXT NOT NULL, required_docs TEXT NOT NULL DEFAULT '[]',
  done_at TEXT, note TEXT, sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE (entity_id, month, code)
);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, month TEXT NOT NULL,
  account_id INTEGER REFERENCES accounts(id), payee_id INTEGER REFERENCES payees(id),
  category TEXT NOT NULL, description TEXT NOT NULL,
  amount REAL, currency TEXT NOT NULL DEFAULT 'MYR', amount_is_estimate INTEGER NOT NULL DEFAULT 0,
  due_date TEXT NOT NULL, paid_date TEXT, bank_ref TEXT, sql_ref TEXT, einvoice_ref TEXT,
  direction TEXT NOT NULL DEFAULT 'out', notes TEXT, created_at TEXT NOT NULL,
  paid_source TEXT, planned_amount REAL, planned_is_estimate INTEGER, difference_note TEXT, undo_link TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY, payment_id INTEGER REFERENCES payments(id), task_id INTEGER REFERENCES tasks(id),
  statement_id INTEGER, entity_id INTEGER NOT NULL, month TEXT NOT NULL, doc_type TEXT NOT NULL,
  original_name TEXT NOT NULL, stored_path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  uploaded_at TEXT NOT NULL, replaced_by INTEGER REFERENCES documents(id), note TEXT, removed_at TEXT
);
CREATE TABLE IF NOT EXISTS statements (
  id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id), month TEXT NOT NULL,
  statement_date TEXT, opening REAL, closing REAL, total_debits REAL, total_credits REAL,
  document_id INTEGER REFERENCES documents(id), imported_at TEXT NOT NULL, check_ok INTEGER NOT NULL DEFAULT 0,
  reconciled_at TEXT, reconciled_how TEXT, reconciled_note TEXT
);
CREATE TABLE IF NOT EXISTS statement_lines (
  id INTEGER PRIMARY KEY, statement_id INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
  line_no INTEGER NOT NULL, txn_date TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL,
  balance REAL NOT NULL, payment_id INTEGER REFERENCES payments(id), status TEXT NOT NULL DEFAULT 'unmatched',
  note TEXT, undone_payment_id INTEGER, confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS sql_imports (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), filename TEXT NOT NULL,
  document_id INTEGER REFERENCES documents(id), imported_at TEXT NOT NULL, entries INTEGER NOT NULL, linked INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sql_entries (
  id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES sql_imports(id), entity_id INTEGER NOT NULL,
  doc_no TEXT NOT NULL, doc_date TEXT NOT NULL, description TEXT, payee TEXT, amount REAL NOT NULL,
  direction TEXT, einvoice TEXT, doc_type TEXT, kind TEXT, einvoice_status TEXT, einvoice_link TEXT,
  task_id INTEGER REFERENCES tasks(id),
  payment_id INTEGER REFERENCES payments(id), status TEXT NOT NULL DEFAULT 'unlinked',
  UNIQUE (entity_id, doc_no, doc_date, amount)
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, what TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS book_openings (
  account_id INTEGER NOT NULL REFERENCES accounts(id), month TEXT NOT NULL, amount REAL NOT NULL, set_at TEXT NOT NULL,
  PRIMARY KEY (account_id, month)
);
CREATE TABLE IF NOT EXISTS budgets (
  entity_id INTEGER NOT NULL, month TEXT NOT NULL, set_up_at TEXT NOT NULL, balance REAL, as_at TEXT,
  PRIMARY KEY (entity_id, month)
);
CREATE TABLE IF NOT EXISTS budget_lines (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, month TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  details TEXT, amount REAL, currency TEXT NOT NULL DEFAULT 'MYR', payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL,
  payee_id INTEGER, category TEXT, sort INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS budget_line_payment ON budget_lines(payment_id) WHERE payment_id IS NOT NULL;
"""
BUDGET_TABLES = SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS budgets"):]
BOOK_OPENINGS = SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS book_openings"):SCHEMA.index("CREATE TABLE IF NOT EXISTS budgets")]


def connect():
    """A connection whose writes are captured in the audit trail (audit.Connection). Request handlers arm it with who
    and why (app.con); the update steps and the seed are armed in init."""
    con = sqlite3.connect(DB_PATH, factory=audit.Connection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA recursive_triggers = ON")  # so a future INSERT OR REPLACE still records the row it replaces
    con.mark()
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


def log(con, what):
    con.execute("INSERT INTO activity (at, what) VALUES (?, ?)", (now(), what))


# ---------- updates to an existing records.db ----------

def _has_col(con, table, col):
    return col in {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def add_column(con, table, col, decl):
    if col not in {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        audit.refresh(con)  # once the trail has started, so the step's own changes to the new column are captured


def _later_columns(con):
    for col in ("start_date", "end_date"):
        add_column(con, "payees", col, "TEXT")
    for col in ("direction", "einvoice", "doc_type", "kind", "einvoice_status", "einvoice_link"):
        add_column(con, "sql_entries", col, "TEXT")
    add_column(con, "sql_entries", "task_id", "INTEGER")


def _link_sources(con):
    for col, decl in (("paid_source", "TEXT"), ("planned_amount", "REAL"), ("planned_is_estimate", "INTEGER"),
                      ("difference_note", "TEXT"), ("undo_link", "TEXT")):
        add_column(con, "payments", col, decl)
    add_column(con, "statement_lines", "undone_payment_id", "INTEGER")
    # Where the paid dates set so far came from is not recorded: a bank line linked, else an SQL voucher, else typed in.
    # The amounts planned before links replaced them are not known, so planned_amount stays empty for those.
    con.execute("""UPDATE payments SET paid_source = CASE
                     WHEN EXISTS (SELECT 1 FROM statement_lines l WHERE l.payment_id = payments.id) THEN 'bank'
                     WHEN EXISTS (SELECT 1 FROM sql_entries s WHERE s.payment_id = payments.id) THEN 'sql'
                     ELSE 'manual' END
                   WHERE paid_date IS NOT NULL AND paid_source IS NULL""")


def _line_totals(con):
    from . import statements
    for (pid,) in con.execute("""SELECT id FROM payments p WHERE amount_is_estimate = 1
                                 AND EXISTS (SELECT 1 FROM statement_lines l WHERE l.payment_id = p.id)""").fetchall():
        statements.take_line_total(con, pid)


def _plans_before_links(con):
    for p in con.execute("""SELECT * FROM payments WHERE payee_id IS NOT NULL AND amount IS NOT NULL AND amount_is_estimate = 0
                            AND planned_is_estimate IS NULL AND undo_link IS NULL""").fetchall():
        vouchers = con.execute("SELECT SUM(amount) FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') = 'payment'",
                               (p["id"],)).fetchone()[0]
        found = round(vouchers, 2) if vouchers is not None else linked_total(con, p)
        payee = con.execute("SELECT * FROM payees WHERE id = ?", (p["payee_id"],)).fetchone()
        plan = planned(con, payee, p["month"]) if payee else None
        if found is not None and plan and plan["amount_is_estimate"] and same_amount(p["amount"], found):
            con.execute("UPDATE payments SET planned_amount = ?, planned_is_estimate = 1 WHERE id = ?", (plan["amount"], p["id"]))


def _checklist_from_data(con):
    add_column(con, "months", "closed_at", "TEXT")  # step 9's, read when the reminders are placed below
    for ent in con.execute("SELECT * FROM entities").fetchall():
        for code, _, title, detail, docs in rules.CHECKLIST.get(ent["code"], []):
            if code in rules.CHECKLIST_CHANGED:
                con.execute("UPDATE tasks SET title = ?, detail = ?, required_docs = ? WHERE entity_id = ? AND code = ?",
                            (title, detail, json.dumps(docs), ent["id"], code))
    for p in con.execute("SELECT * FROM payees").fetchall():
        sync_reminders(con, p)


def _reconciliation(con):
    for col in ("reconciled_at", "reconciled_how", "reconciled_note"):
        add_column(con, "statements", col, "TEXT")
    add_column(con, "statement_lines", "confirmed_at", "TEXT")
    con.executescript(BOOK_OPENINGS)
    # The Bank reconciliation item is done by signing the month off (Bank statements page), not by filing a document.
    con.execute("UPDATE tasks SET detail = ?, required_docs = '[]' WHERE code = 'recon'", (rules.RECON_DETAIL,))


# Update 13's due date for the self-billed e-Invoice item, frozen here: it was read from the first company's checklist
# in rules.CHECKLIST, whose codes and wording may change, while what the step does must not.
SELFBILLED_DUE = (1, 7)


def _selfbilled_by_7th(con):
    offset, day = SELFBILLED_DUE
    for t in con.execute("SELECT id, month FROM tasks WHERE code = 'einv-selfbilled' AND done_at IS NULL").fetchall():
        con.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (due(t["month"], offset, day), t["id"]))


def _payslips_retyped(con):
    con.execute("UPDATE documents SET doc_type = 'payslip' WHERE doc_type = 'other' AND LOWER(original_name) LIKE '%payslip%' "
                "AND payment_id IN (SELECT id FROM payments WHERE category IN ('salary', 'director'))")


# Each step runs once per records.db, in order; PRAGMA user_version holds how many have run.
# To add one, append it at the end (never reorder or remove a step). Steps also run on a new install,
# after SCHEMA, so a step must check before it changes anything (add_column does).
MIGRATIONS = [
    # 1. Payee start/end dates and the SQL e-Invoice fields, added after the first release.
    _later_columns,
    # 2. Paid dates for payments linked to an SQL voucher before vouchers set them. Earlier versions filled these in
    #    on every start, so every records.db already has them, and doing it again could only put back a paid date
    #    cleared by hand. Left empty so the numbering stays.
    lambda con: None,
    # 3. Where a paid date came from (bank, sql or manual), the amount planned before an SQL voucher or bank line
    #    replaced it (so undoing the link can restore it), what the last SQL voucher linked replaced (so unlinking it
    #    puts exactly that back), a note accepting a difference with the bank lines, and the payment a bank line was
    #    undone from (so matching again doesn't link it back).
    _link_sources,
    # 4. The first month each company is tracked in this app (empty: no limit). Months before it are never opened
    #    automatically and nothing in them counts as overdue.
    lambda con: add_column(con, "entities", "first_month", "TEXT"),
    # 5. When a document was removed from its payment or checklist item. The file and its record are kept; a removed
    #    one is left out of the lists, the counts and the audit pack.
    lambda con: add_column(con, "documents", "removed_at", "TEXT"),
    # 6. Estimates matched to bank lines before linked lines made up an estimate's amount take their lines' total now,
    #    as a link made today would (a fund requisition, matched as several 10,000 lines, still showed 'estimate').
    _line_totals,
    # 7. What was planned for payments whose estimate an SQL voucher or bank lines replaced before planned figures were
    #    kept: the payee's plan for the month as it stands, so undoing those links brings the estimate back as it does
    #    for links made now. Only where the amount is still exactly what the links add up to.
    _plans_before_links,
    # 8. Checklist items the records now show done: the payroll item becomes one PV per person, and the documents the
    #    payments already ask for (portal acknowledgements, the fund receipt's OR and e-Invoice, self-billed e-Invoices)
    #    are no longer asked for again on the item. Ticks stay. Joiner and leaver reminders are added to the months
    #    already set up.
    _checklist_from_data,
    # 9. When a month was marked as filed (empty: still open). Nothing in a filed month counts as to do.
    lambda con: add_column(con, "months", "closed_at", "TEXT"),
    # 10. The stored budget of each company and payroll month: its lines (with the payment each is linked to) and its
    #     header (when it was set up, the bank balance and the date it was taken, kept here, not in the browser).
    lambda con: con.executescript(BUDGET_TABLES),
    # 11. Which way a recurring payment goes (out, or in for money received such as a tenant's rent).
    lambda con: add_column(con, "payees", "direction", "TEXT NOT NULL DEFAULT 'out'"),
    # 12. SQL documents filed on the checklist item of the month they belong to (they were filed by the nearest due
    #     date). Only the link moves; nothing is ticked or unticked.
    lambda con: refile_documents(con),
    # 13. Self-billed e-Invoices are due by the 7th of the next month (they were set for the 10th). Moves the due date of
    #     the items not done yet; done ones keep theirs.
    _selfbilled_by_7th,
    # 14. Each person's payslip is a document of its own (salary and director payments ask for it). Payslips already
    #     uploaded as 'Other' to those payments become Payslip. Only doc_type changes; the files keep their names.
    _payslips_retyped,
    # 15. Bank reconciliation: when a person confirmed each bank line, when a statement was signed off as reconciled (and
    #     how: by review, or before tracking, with a note), and the book balance typed in for an account's first month.
    #     Nothing is signed off or confirmed by this step. The checklist item no longer asks for a document.
    _reconciliation,
    # 16. The audit trail's store: the change rows, the sealed entries (a hash chain) and the one-row context that says
    #     who is making a change. Nothing in the records changes.
    audit.install,
    # 17. Audit capture turned on: triggers on every table write each change, before and after, into the trail, and
    #     one baseline row per existing row records the records as they stand. Nothing in the records changes.
    audit.start,
    # 18. An index of the rows each audit entry seals that another program wrote (accepted outside changes), so the
    #     check for new ones stays quick however many have been accepted. Nothing in the records changes.
    audit.sealed_index,
    # 19. Setup: companies get a short name, registration, tax and employer numbers, their SQL database, notes, and
    #     active and sort; bank accounts their statement format, GL code, SQL payment method, cash book, notes, and
    #     active and sort; General settings get a table, filled with the values used until now. Each company's first
    #     account becomes its cash book, as the app took it to be. Nothing else in the records changes.
    lambda con: _setup_columns(con),
    # 20. Payment types, document types and the documents each payment type needs, kept in the records from now on
    #     (Setup), filled with the values the app has had in code, and checked to read back exactly as they were.
    #     Required documents become dated sets, so a change from a month on never alters the months before it.
    #     Nothing in the records changes.
    rulebook.install,
    # 21. The monthly checklist (each company's items, how each is shown done, Next up's deadlines), the joiner and
    #     leaver reminders and the words SQL imports are guessed and filed by, kept in the records from now on (Setup),
    #     filled with the values the app has had in code and checked to read back exactly as they were. The checklist
    #     and reminders are dated, so a change from a month on never alters the months before it. Nothing in the
    #     records changes.
    checklistbook.install,
    # 22. Customers and suppliers and each company's chart of accounts (entered in Setup), a link from a recurring
    #     payment or an SQL filing rule to a customer or supplier, and the code, payment method, cheque number, document
    #     key and currency of SQL entries, kept from listings that carry them. Nothing in the records changes.
    partybook.install,
    # 23. The chart of accounts keeps all of SQL Account's special account types (cash, accumulated depreciation,
    #     deposits, the stock accounts), so a chart printed from SQL Account reads in whole. The table is made again
    #     with every row as it was. Nothing in the records changes.
    partybook.widen_specials,
    # 24. Each account in the chart keeps SQL Account's account group (its A/C Type: FA, CA, CL, ...), so the chart can
    #     be shown as a tree grouped as SQL prints it. Empty for the accounts already there. Nothing else changes.
    partybook.keep_sql_types,
    # 25. The lines of SQL journals pasted from SQL Account's journal detail grid (the account, debit and credit of each
    #     line, by the journal's document key and the import that brought them), so a journal that moves the bank
    #     counts in the bank reconciliation. Empty to begin with. Nothing in the records changes.
    lambda con: _journal_lines_table(con),
]


JOURNAL_LINES = """
CREATE TABLE IF NOT EXISTS sql_journal_lines (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), dockey TEXT NOT NULL,
  import_id INTEGER NOT NULL REFERENCES sql_imports(id), dtlkey TEXT, seq INTEGER, code TEXT NOT NULL,
  description TEXT, project TEXT, dr REAL NOT NULL DEFAULT 0, cr REAL NOT NULL DEFAULT 0
)"""


def _journal_lines_table(con):
    con.execute(JOURNAL_LINES)
    con.execute("CREATE INDEX IF NOT EXISTS sql_journal_lines_key ON sql_journal_lines (entity_id, dockey)")


def _setup_columns(con):
    from . import masters
    masters.install(con)


def filing_month(description, doc_date):
    """The payroll month an SQL document belongs to: the month its description names (RENTAL CHARGE FOR OCTOBER 26),
    else the month it is dated in."""
    return named_month(description) or doc_date[:7]


# The SQL documents filed on the checklist item of the month they belong to: customer invoices and journals. A payment or
# receipt voucher (a self-billed PV, the OR for the fund received) belongs to the month of its payment, which can be the
# month before the one it is dated in, so it stays with the item whose due date is nearest.
FILED_BY_MONTH = ("invoice", "journal")


def item_for(con, entity_id, code, description, doc_date, kind="invoice"):
    """The checklist item (id, title, month, due_date) an SQL document is filed on: for an invoice or journal
    (FILED_BY_MONTH) the item of its own month (filing_month) when the company has one; else the one whose due date is
    nearest the document date, within 45 days, else None."""
    rows = con.execute("SELECT id, title, month, due_date FROM tasks WHERE entity_id = ? AND code = ?", (entity_id, code)).fetchall()
    month = filing_month(description, doc_date)
    own = next((t for t in rows if t["month"] == month), None)
    if own and kind in FILED_BY_MONTH:
        return own
    day = date.fromisoformat(doc_date)
    best = min(rows, key=lambda t: abs((date.fromisoformat(t["due_date"]) - day).days), default=None)
    return best if best and abs((date.fromisoformat(best["due_date"]) - day).days) <= 45 else None


def refile_documents(con):
    """Moves each SQL invoice and journal (FILED_BY_MONTH) filed on a checklist item of another month than its own
    (filing_month) to the item of the same kind in its own month, when the company has that item. Ticks stay as they are. Each move is logged. Returns the
    moves as (doc no, month it was on, month it is on now)."""
    moved = []
    for s in con.execute("""SELECT s.id, s.entity_id, s.doc_no, s.doc_date, s.description, t.code, t.month, t.id AS tid
                            FROM sql_entries s JOIN tasks t ON t.id = s.task_id
                            WHERE s.kind IN ('invoice', 'journal') ORDER BY s.id""").fetchall():
        right = con.execute("SELECT id FROM tasks WHERE entity_id = ? AND code = ? AND month = ?",
                            (s["entity_id"], s["code"], filing_month(s["description"], s["doc_date"]))).fetchone()
        if right and right["id"] != s["tid"]:
            con.execute("UPDATE sql_entries SET task_id = ? WHERE id = ?", (right["id"], s["id"]))
            moved.append((s["doc_no"], s["month"], filing_month(s["description"], s["doc_date"])))
            log(con, f"Filed SQL document {s['doc_no']} on the {month_label(moved[-1][2])} checklist item, "
                     f"not {month_label(s['month'])}'s ({s['code']})")
    return moved


def copy_before_update(con):
    target = BACKUP_DIR / f"records-before-update-{datetime.now():%Y%m%d-%H%M%S}.db"
    dst = sqlite3.connect(target)
    con.backup(dst)
    dst.close()
    return target


def init():
    con = connect()
    version = con.execute("PRAGMA user_version").fetchone()[0]
    pending = MIGRATIONS[version:]
    holds_data = (con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'entities'").fetchone()
                  and con.execute("SELECT 1 FROM entities").fetchone())
    copy = copy_before_update(con) if pending and holds_data else None
    con.executescript(SCHEMA)  # before arming: executescript commits whatever is pending first
    if copy:
        con.arm("migration", "Saved a copy before updating")
        log(con, f"Saved a copy of the records before updating them: backups\\{copy.name}")
        con.commit()
    for n, step in enumerate(pending, version + 1):
        con.arm("migration", f"Update {n}")
        step(con)
        audit.refresh(con)  # a step that changed a table's columns, or added a table, is captured from here on
        con.execute(f"PRAGMA user_version = {n}")
        con.commit()
    con.disarm()
    appsettings.load(con)
    trail = audit.startup(con)
    if not con.execute("SELECT 1 FROM entities").fetchone() and SEED_PATH.exists():
        con.arm("seed", "Loaded starting data from seed.json")
        load_seed(con, json.loads(SEED_PATH.read_text(encoding="utf-8")))
    con.commit()
    con.disarm()
    con.close()
    return trail


def load_seed(con, seed):
    """seed.json lives in the records folder (never in the program folder) and is read once, on first start."""
    for e in seed["entities"]:
        cur = con.execute("INSERT INTO entities (code, name, uses_sql) VALUES (?, ?, ?)",
                          (e["code"], e["name"], 1 if e.get("uses_sql", True) else 0))
        eid = cur.lastrowid
        if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checklist_items'").fetchone():
            checklistbook.seed_company(con, {"id": eid, "code": e["code"]})  # update 21 ran before any company existed
            checklistbook.seed_filing(con, {r[0] for r in con.execute("SELECT code FROM checklist_items WHERE entity_id = ?", (eid,))})
        acct_ids = {}
        for a in e.get("accounts", []):
            c = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, ?, ?, ?, ?)",
                            (eid, a["label"], a.get("bank"), a.get("number"), a.get("currency", "MYR")))
            acct_ids[a["label"]] = c.lastrowid
        default_acct = next(iter(acct_ids.values()), None)
        if default_acct and "cash_book" in {r["name"] for r in con.execute("PRAGMA table_info(accounts)")}:
            con.execute("UPDATE accounts SET cash_book = 1 WHERE id = ?", (default_acct,))  # the first account, as until now
        for i, p in enumerate(e.get("payees", [])):
            c = con.execute(
                """INSERT INTO payees (entity_id, account_id, name, category, desc_template, amount, amount_varies,
                   month_offset, due_day, bank_details, reference, match_words, sort, notes, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, acct_ids.get(p.get("account"), default_acct), p["name"], p["category"],
                 p.get("desc_template", p["name"] + " - {M}"), p.get("amount"), 1 if p.get("varies") else 0,
                 p.get("month_offset", 0), p.get("due_day", 26), p.get("bank_details"), p.get("reference"),
                 p.get("match_words"), i, p.get("notes"), p.get("start_date"), p.get("end_date")))
            for adv in p.get("advances", []):
                con.execute("INSERT INTO advances (payee_id, monthly_deduction, start_month, end_month, note) VALUES (?, ?, ?, ?, ?)",
                            (c.lastrowid, adv["monthly_deduction"], adv["start_month"], adv["end_month"], adv.get("note")))
    if seed.get("names") and con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checklist_items'").fetchone():
        checklistbook.fill_names(con, seed["names"])  # the real names for the placeholders (rules.PLACEHOLDERS)
    log(con, "Loaded starting data from seed.json")


# ---------- months ----------

def shift_month(month, n):
    y, m = map(int, month.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def due(month, offset, day):
    y, m = map(int, shift_month(month, offset).split("-"))
    return date(y, m, min(day, calendar.monthrange(y, m)[1])).isoformat()


def month_label(month, short=False):
    y, m = map(int, month.split("-"))
    return f"{calendar.month_abbr[m] if short else calendar.month_name[m]} {y}"


def day_label(iso):
    """A date as 26 Oct 2026."""
    d = date.fromisoformat(iso)
    return f"{d.day} {calendar.month_abbr[d.month]} {d.year}"


def short_day(iso):
    """A date as 26 Oct."""
    d = date.fromisoformat(iso)
    return f"{d.day} {calendar.month_abbr[d.month]}"


def advance_for(con, payee_id, month):
    return con.execute(
        "SELECT * FROM advances WHERE payee_id = ? AND start_month <= ? AND end_month >= ?",
        (payee_id, month, month)).fetchall()


def current_cycle(today=None):
    """The payroll month being worked on: until the rollover day (General settings, the 10th unless changed) you're
    still closing last month's cycle."""
    t = today or date.today()
    return shift_month(f"{t.year:04d}-{t.month:02d}", -1 if t.day <= appsettings.get("cycle_rollover_day") else 0)


def before_tracking(ent, month):
    """True for a month before the first month the company is tracked in this app."""
    return bool(ent["first_month"]) and month < ent["first_month"]


def ensure_month(con, entity_id, month):
    """Create the checklist and planned payments for a payroll month the first time it is set up. True when it was
    set up now."""
    if con.execute("SELECT 1 FROM months WHERE entity_id = ? AND month = ?", (entity_id, month)).fetchone():
        return False
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    for t in checklistbook.get(con).checklist(ent, month):
        con.execute(
            "INSERT OR IGNORE INTO tasks (entity_id, month, code, title, detail, due_date, required_docs, sort) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_id, month, t["code"], t["title"], t["detail"], due(month, t["due_offset"], t["due_day"]), json.dumps(t["docs"]), t["sort"]))
    for p in con.execute("SELECT * FROM payees WHERE entity_id = ? AND active = 1 ORDER BY sort", (entity_id,)):
        if employed_in(p, month):
            create_payment_from_payee(con, p, month)
    con.execute("INSERT INTO months (entity_id, month, generated_at) VALUES (?, ?, ?)", (entity_id, month, now()))
    log(con, f"Opened {month_label(month)} for {ent['code']}")
    from . import budget
    budget.link_new(con, entity_id, month)
    for p in con.execute("SELECT * FROM payees WHERE entity_id = ? AND (start_date IS NOT NULL OR end_date IS NOT NULL)",
                         (entity_id,)).fetchall():
        sync_reminders(con, p)
    return True


def closed_at(con, entity_id, month):
    """When a month was marked as filed, else None. A filed month is done with: nothing in it counts as to do on the
    Overview (or in the list of what to do next), and its pages flag nothing in it (Overdue, Past legal deadline), though
    they still show each item as it is."""
    r = con.execute("SELECT closed_at FROM months WHERE entity_id = ? AND month = ?", (entity_id, month)).fetchone()
    return r["closed_at"] if r else None


def auto_open(con, entity_id, month):
    """Sets up a month the app needs (for an import, or the current cycle) unless it is before the first month
    tracked. True when it was set up now."""
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return not before_tracking(ent, month) and ensure_month(con, entity_id, month)


def runs_payroll(con, entity_id):
    """True for a company that runs Malaysian payroll: it has a statutory recurring payment (KWSP, PERKESO or LHDN)."""
    return bool(con.execute("SELECT 1 FROM payees WHERE entity_id = ? AND category = 'statutory' AND active = 1",
                            (entity_id,)).fetchone())


def short_name(name):
    """The name in brackets (Ali for Muhammad Ali bin Abu (Ali)), else the whole name."""
    m = re.search(r"\(([^()]+)\)\s*$", name)
    return (m.group(1) if m else name).strip()


def reminders_for(con, p):
    """The joiner and leaver reminders (checklistbook: Setup's, by the month of the date) a payee's start date and last day give: only for a salary,
    on a company that runs Malaysian payroll. {task code: (its fields, the month of the date it comes from)}; its month
    is the one being worked on when it falls due (current_cycle), so a CP22A, due a month before the last day, is in
    the month before."""
    if p["category"] != "salary" or not runs_payroll(con, p["entity_id"]):
        return {}
    out = {}
    book = checklistbook.get(con)
    for r in book.people():
        kind, key = r["kind"], r["key"]
        day = p["start_date"] if kind == "joiner" else p["end_date"]
        t = day and book.people_term(key, day[:7])
        if not t or (t["salary_over"] is not None and (p["amount"] or 0) <= t["salary_over"]):
            continue
        on = date.fromisoformat(day) + timedelta(days=t["days"])
        out[f"{kind}-{key}-{p['id']}"] = ({
            "month": current_cycle(on), "title": checklistbook.fill(t["title"], name=short_name(p["name"])),
            "detail": checklistbook.fill(t["detail"], date=day_label(day)), "due_date": on.isoformat(),
            "required_docs": json.dumps(t["docs"])}, day[:7])
    return out


def held(con, task_id):
    """True when anything is filed on a checklist item: a document (removed or replaced ones too) or an SQL document."""
    return any(con.execute(f"SELECT 1 FROM {t} WHERE task_id = ?", (task_id,)).fetchone() for t in ("documents", "sql_entries"))


def reminder_month(con, ent, month, event):
    """The month set up, from the first month tracked, that a reminder for month goes into: that month; while it is
    still to come, the latest month set up (so it shows before it falls due, and moves on as months are set up); for a
    past month not set up, the month of the date it comes from (event). A month marked as filed takes none (one still to
    come only waits there): the next month set up that isn't filed does. Returns (that month, None); (None, the latest
    month set up) when every month from the one it goes into on is filed, as it goes into the month after once that is
    set up; (None, None) when none of these is set up."""
    rows = [r for r in con.execute("SELECT month, closed_at FROM months WHERE entity_id = ? ORDER BY month", (ent["id"],))
            if not before_tracking(ent, r["month"])]
    if rows and month > rows[-1]["month"]:
        return rows[-1]["month"], None
    set_up = {r["month"] for r in rows}
    at = month if month in set_up else event if event in set_up else None
    if not at:
        return None, None
    at = next((r["month"] for r in rows if r["month"] >= at and not r["closed_at"]), None)
    return (at, None) if at else (None, rows[-1]["month"])


def waits_for(task, con=None):
    """The month a checklist item not ticked falls due in when that is later than the month it is in, else None: a
    joiner or leaver reminder waiting in the latest month set up (reminder_month). It shows on that month's page but
    isn't part of that month: its counts and its audit pack leave it out. A ticked one stays where it is, so it counts."""
    if task["done_at"]:
        return None
    if not checklistbook.is_reminder(task["code"]) and (con is None or checklistbook.get(con).from_tables):
        return None  # from update 21 a checklist item belongs to its month whatever day it is due
    own = current_cycle(date.fromisoformat(task["due_date"]))
    return own if own > task["month"] else None


def sync_reminders(con, p):
    """Brings a payee's joiner and leaver reminders (reminders_for) into the months set up (reminder_month): adds the
    ones missing, moves the ones not ticked to the month and due date the dates give now (with what is filed on them),
    and removes the ones not ticked with nothing filed that it no longer gives or can't place (a date cleared, no longer
    a salary, a past month not set up). Ticked ones stay as they are. Logs and returns what changed, then what it left
    as it was or can't add yet. One in a month marked as filed stays as it is too (the warning before filing named it),
    unless it only waits there for a later month, or the dates now give it another due date: then it moves as one in a
    month still open does, and the change says it left the filed month. While every month from the one the dates give
    is filed, one already set up stays where it is, as it was, until the next month is set up, and the save says so."""
    want = reminders_for(con, p)
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (p["entity_id"],)).fetchone()
    rules_ = checklistbook.get(con).people()  # every rule, stopped ones too: their reminders are looked after as well
    codes = [f"{r['kind']}-{r['key']}-{p['id']}" for r in rules_]
    sorts = {c: 100 + r["sort"] for c, r in zip(codes, rules_)}
    changes, notes = [], []
    for code in codes:
        have = con.execute("SELECT * FROM tasks WHERE entity_id = ? AND code = ? ORDER BY month", (ent["id"], code)).fetchall()
        w, event = want.get(code, (None, None))
        if any(t["done_at"] or (closed_at(con, ent["id"], t["month"]) and not waits_for(t, con)
                                and (not w or t["due_date"] == w["due_date"])) for t in have):
            continue
        at, filed = reminder_month(con, ent, w["month"], event) if w else (None, None)
        for t in have[1:] if at or filed else have:
            if held(con, t["id"]):
                notes.append(f"{month_label(t['month'])}: kept {t['title']}, as a document is filed on it: tick it once it's done")
            else:
                con.execute("DELETE FROM tasks WHERE id = ?", (t["id"],))
                changes.append(f"{month_label(t['month'])}: removed {t['title']}")
        if not at:
            then = filed and f"{month_label(shift_month(filed, 1))} is set up, as {month_label(filed)} is marked as filed"
            if then and have:
                was = have[0]
                notes.append(f"{month_label(was['month'])}: kept {was['title']}, due {day_label(was['due_date'])}, until {then}: "
                             f"it then moves there, due {day_label(w['due_date'])}")
            elif then:
                notes.append(f"{w['title']}, due {day_label(w['due_date'])}: added once {then}")
            elif w and not before_tracking(ent, w["month"]) and not con.execute(
                    "SELECT 1 FROM months WHERE entity_id = ? AND month >= ?", (ent["id"], w["month"])).fetchone():
                notes.append(f"{w['title']}, due {day_label(w['due_date'])}: added once {month_label(w['month'])} is set up")
            continue
        fields = {**w, "month": at}
        later = f" (moves to {month_label(w['month'])} once that month is set up)" if at < w["month"] else ""
        if have and any(have[0][k] != v for k, v in fields.items()):
            was = have[0]
            con.execute(f"UPDATE tasks SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?", (*fields.values(), was["id"]))
            what = (f"now due {day_label(w['due_date'])}" if was["due_date"] != w["due_date"]
                    else f"moved from {month_label(was['month'])}" if was["month"] != at else "updated")
            if was["month"] != at and closed_at(con, ent["id"], was["month"]) and not waits_for(was, con):
                what += f", moved from {month_label(was['month'])}, which is marked as filed"
            changes.append(f"{month_label(at)}: {w['title']} {what}{later}")
        elif not have:
            con.execute(f"INSERT INTO tasks (entity_id, code, sort, {', '.join(fields)}) VALUES (?, ?, ?, {', '.join('?' * len(fields))})",
                        (ent["id"], code, sorts[code], *fields.values()))
            changes.append(f"{month_label(at)}: added {w['title']}, due {day_label(w['due_date'])}{later}")
    for x in changes:
        log(con, f"Checklist reminder for {p['name']} in {x}")
    return changes + notes


def describe(template, month):
    return (template.replace("{M}", month_label(month, short=True))
                    .replace("{M+1}", month_label(shift_month(month, 1), short=True)))


def employed_in(p, month):
    """A payee with a start or end date (joiner, leaver, fixed-term contract) only appears in the months it covers."""
    return (not p["start_date"] or p["start_date"][:7] <= month) and (not p["end_date"] or p["end_date"][:7] >= month)


def days_covered(p, month):
    """(days covered, days in month) when a start or end date falls inside the month, else None. A last day before
    the start covers no days."""
    y, m = map(int, month.split("-"))
    first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    start = max(first, date.fromisoformat(p["start_date"])) if p["start_date"] else first
    end = min(last, date.fromisoformat(p["end_date"])) if p["end_date"] else last
    if start == first and end == last:
        return None
    return max((end - start).days + 1, 0), last.day


def planned(con, p, month):
    """The payment a recurring payee adds to a month, as payment fields, or None when there is nothing to pay (no
    days covered, or a salary that would be zero or less)."""
    amount, notes = p["amount"], []
    salary = p["category"] in ("salary", "director")
    part = days_covered(p, month) if salary else None
    if part and amount is not None:
        # Calendar-day proration for the joining or leaving month, e.g. 27 of 31 days.
        amount = round(amount * part[0] / part[1], 2)
        notes.append(f"Prorated {part[0]} of {part[1]} days (full month {p['amount']:,.2f})")
    for adv in advance_for(con, p["id"], month):
        if amount is not None:
            amount -= adv["monthly_deduction"]
        notes.append(f"Less advance recovery {adv['monthly_deduction']:,.2f}" + (f" ({adv['note']})" if adv["note"] else ""))
    if salary and ((part and not part[0]) or (amount is not None and amount <= 0)):
        return None
    acct = con.execute("SELECT currency FROM accounts WHERE id = ?", (p["account_id"],)).fetchone()
    return {"account_id": p["account_id"], "category": p["category"], "description": describe(p["desc_template"], month),
            "amount": amount, "currency": acct["currency"] if acct else "MYR", "amount_is_estimate": p["amount_varies"],
            "due_date": due(month, p["month_offset"], p["due_day"]), "notes": "; ".join(notes) or None,
            "direction": (p["direction"] if "direction" in p.keys() else None) or "out"}


def create_payment_from_payee(con, p, month):
    """Adds a recurring payee's payment to the month. Returns its id, or None when there is nothing to pay."""
    v = planned(con, p, month)
    if v is None:
        return None
    return con.execute(
        f"INSERT INTO payments (entity_id, month, payee_id, {', '.join(v)}, created_at) VALUES (?, ?, ?, {', '.join('?' * len(v))}, ?)",
        (p["entity_id"], month, p["id"], *v.values(), now())).lastrowid


def same_amount(a, b):
    return (a is None and b is None) or (a is not None and b is not None and round(a, 2) == round(b, 2))


def recorded(con, pay):
    """True once anything is recorded on a payment: a paid date, a document, an SQL voucher (linked, or its number
    typed in) or a bank line."""
    return bool(pay["paid_date"] or pay["sql_ref"]) or any(
        con.execute(f"SELECT 1 FROM {t} WHERE payment_id = ?", (pay["id"],)).fetchone()
        for t in ("documents", "sql_entries", "statement_lines"))


# How each field a recurring payment's update changes is named in the activity log (currency follows the account).
CHANGED = {"amount": "amount", "amount_is_estimate": "estimate", "due_date": "due date", "category": "type",
           "description": "description", "account_id": "bank account", "currency": None, "notes": "note", "direction": None}


def _due_in(con, p, month):
    """The payment a payee plans for the month while it is active and employed then, else {}."""
    return (p and p["active"] and employed_in(p, month) and planned(con, p, month)) or {}


def _not_due_why(p, month):
    """Why a payee plans nothing for the month, as the activity log puts it."""
    if not p["active"]:
        return "stopped"
    part = days_covered(p, month) if employed_in(p, month) else (0, 0)
    return "not employed then" if part and not part[0] else "nothing to pay: the amount is 0 or less after advances"


def _fmt(v):
    return "blank" if v is None else f"{v:,.2f}"


def _as_planned(p, was):
    """True while a payment still has the amount, estimate mark, due date, bank account and type the payee planned for
    it: a figure typed in or confirmed as the real one, or a payment moved to another date or account by hand, is no
    longer the payee's plan."""
    return bool(was) and same_amount(p["amount"], was["amount"]) and all(
        p[k] == was[k] for k in ("amount_is_estimate", "due_date", "account_id", "category", "direction"))


def _typed_on(p, was):
    """A note, bank reference or e-Invoice number typed on a payment."""
    return bool(p["bank_ref"] or p["einvoice_ref"]) or p["notes"] not in (None, was.get("notes"))


def _sync_months(con, entity_id, t, filed=False):
    """The months a recurring payment's change reaches: set up, from the current cycle (and the first month tracked)
    on, and not marked as filed; with filed=True, the filed ones in that range instead (left as they were)."""
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return [m for (m,) in con.execute(f"""SELECT month FROM months WHERE entity_id = ? AND month >= ?
                                          AND closed_at IS {'NOT ' if filed else ''}NULL ORDER BY month""",
                                      (entity_id, max(current_cycle(t), ent["first_month"] or ""))).fetchall()]


def plans(con, p, today=None):
    """{month: what the payee plans then} over the months sync_payee walks, as things stand now: taken before a change
    the payee's own row doesn't show (a salary advance added, changed or removed), and handed to sync_payee as
    was_plans, so it compares with the plans from before the change."""
    t = today or date.today()
    months = _sync_months(con, p["entity_id"], t) + _sync_months(con, p["entity_id"], t, filed=True)
    return {m: _due_in(con, p, m) for m in months}


def sync_payee(con, old, new, today=None, was_plans=None):
    """Brings a saved recurring payment into the months already set up, from the current cycle on, for the payments
    not due yet. One whose due date has passed is left as it was: it was most likely paid and only waits for the bank
    statement or SQL. A month whose planned payment the save doesn't change is left alone. A month it is now due in,
    and wasn't before, gets its payment. A payment nobody has touched (nothing recorded on it, and still the amount,
    estimate mark, due date, bank account and type the payee gave before) takes the new figures, or is removed when
    the payee is now stopped, not employed that month or has nothing to pay then (a salary of 0 or less after
    advances), unless a note or reference was typed on it. A description or note typed by hand stays, and so does a
    payment added by hand to a month the payee wasn't due in. Returns (what changed, payments left as they were
    although the change would alter them)."""
    t = today or date.today()
    changes, kept = [], []
    for month in _sync_months(con, new["entity_id"], t, filed=True):  # filed months never change: say so where it would
        was = was_plans.get(month, {}) if was_plans is not None else _due_in(con, old, month)
        if _due_in(con, new, month) != was and con.execute("SELECT 1 FROM payments WHERE payee_id = ? AND month = ?",
                                                           (new["id"], month)).fetchone():
            kept.append(f"{month_label(month)}: left as it was, as the month is marked as filed")
    for month in _sync_months(con, new["entity_id"], t):
        label = month_label(month)
        want = _due_in(con, new, month)
        was = was_plans.get(month, {}) if was_plans is not None else _due_in(con, old, month)
        if want == was:
            continue
        pays = con.execute("SELECT * FROM payments WHERE payee_id = ? AND month = ? ORDER BY id", (new["id"], month)).fetchall()
        for p in pays:
            sets = {k: v for k, v in want.items() if p[k] != v and (k not in ("description", "notes") or p[k] == was.get(k))}
            if want and not sets:
                continue
            if recorded(con, p) or not _as_planned(p, was) or (not want and _typed_on(p, was)):
                kept.append(f"{label}: {p['description']}")
            elif p["due_date"] < t.isoformat():
                kept.append(f"{label}: {p['description']}, due {day_label(p['due_date'])}, probably paid already")
            elif not want:
                con.execute("DELETE FROM payments WHERE id = ?", (p["id"],))
                changes.append(f"{label}: removed {p['description']} ({_not_due_why(new, month)})")
            else:
                con.execute(f"UPDATE payments SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), p["id"]))
                changes.append(f"{label}: {p['description']}: " + ", ".join(
                    f"amount {_fmt(p['amount'])} → {_fmt(v)}" if k == "amount" else CHANGED[k] for k, v in sets.items() if CHANGED[k]))
        if want and not pays and not was:
            if want["due_date"] < t.isoformat():
                kept.append(f"{label}: {want['description']} not added, as it was due {day_label(want['due_date'])}")
            else:
                create_payment_from_payee(con, new, month)
                changes.append(f"{label}: added {want['description']}, {_fmt(want['amount'])}")
    for x in changes:
        log(con, f"Recurring payment {new['name']} updated in {x}")
    return changes, kept


def linked_total(con, pay):
    """What the bank lines linked to a payment add up to, in its currency and counted its way: money going the other
    way (a refund, a transfer the bank returned, a charge on a receipt) is taken off, as SQL refunds are. None when no
    line is linked, or when a line is in another currency (a USD line on an RM payment) and the two can't be compared."""
    lines = con.execute(
        """SELECT l.amount, a.currency FROM statement_lines l JOIN statements s ON s.id = l.statement_id
           JOIN accounts a ON a.id = s.account_id WHERE l.payment_id = ?""", (pay["id"],)).fetchall()
    if not lines or any(l["currency"] != pay["currency"] for l in lines):
        return None
    sign = -1 if pay["direction"] == "out" else 1
    return round(sum(sign * l["amount"] for l in lines), 2)


def _proof(ref, note):
    return {"ref": ref, "text": f"{ref} ({note})"}


# How a refund or credit note e-Invoice says it takes back another document's e-Invoice (OR2601-004: 'SELF-BILLED
# REFUND FOR DUPLICATED SELF-BILLED E-INVOICE ... (PV2601-002 ...)'). A refund alone may be partial, so it isn't enough.
TAKES_BACK = re.compile(r"\b(REVERS(E|ED|AL|ING)\b(?!\W+CHARGE)|DUPLICATE[DS]?\b|CANCEL)", re.I)


def taken_back_by(con, s):
    """The refund or credit note that takes back the e-Invoice on an SQL document (s): another document of the company
    that is itself an e-Invoice and names this one, saying it reverses, cancels or duplicates it (OR2601-004 for
    PV2601-002). Its doc no, or None."""
    if not (s["einvoice"] or s["einvoice_status"]):
        return None
    named = re.compile(rf"(?<![\w-]){re.escape(s['doc_no'])}(?![\w-])", re.I)
    return next((o["doc_no"] for o in con.execute(
        """SELECT doc_no, description FROM sql_entries WHERE entity_id = ? AND id != ? AND einvoice IS NOT NULL
           AND description LIKE ? ORDER BY doc_date, id""", (s["entity_id"], s["id"], f"%{s['doc_no']}%"))
                 if named.search(o["description"]) and TAKES_BACK.search(o["description"])), None)


def _validated(s):
    return (s["einvoice_status"] or "").startswith("Validated")


def _einvoices(con, sql, pay):
    """The SQL documents with an e-Invoice LHDN validated that may stand for the e-Invoice a payment or checklist item
    needs, each with the refund or credit note that takes it back (None when nothing does): those linked to it (sql),
    and unless one of them counts, for a payment the ones its e-Invoice UIN names on a document of the same side
    (purchases for money out, sales for money in) not linked to another payment."""
    found = [(s, taken_back_by(con, s)) for s in sql if _validated(s)]
    if not any(by is None for _, by in found) and pay and (pay["einvoice_ref"] or "").strip():
        seen = {s["id"] for s, _ in found}
        found += [(s, taken_back_by(con, s)) for s in con.execute(
                      "SELECT * FROM sql_entries WHERE entity_id = ? AND einvoice = ? AND (payment_id IS NULL OR payment_id = ?)",
                      (pay["entity_id"], pay["einvoice_ref"].strip(), pay["id"]))
                  if s["id"] not in seen and _side(s) == pay["direction"] and _validated(s)]
    return found


def _listed(items):
    """a, b and c."""
    items = list(dict.fromkeys(items))
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _side(s):
    """in for a receipt or a sales document, out for a payment voucher or a purchase document."""
    t = (s["doc_type"] or "").upper()
    return "in" if t in MONEY_IN | SALES_DOCS else "out" if t in MONEY_OUT | PURCHASE_DOCS else s["direction"]


def _bank_lines(days):
    """The bank lines linked to a payment, by date: Bank line 26 Sep, or 7 bank lines, 22 Sep."""
    if len(days) == 1:
        return f"Bank line {short_day(days[0])}"
    seen = list(dict.fromkeys(days))
    when = ", ".join(map(short_day, seen)) if len(seen) <= 3 else f"{short_day(seen[0])} to {short_day(seen[-1])}"
    return f"{len(days)} bank lines, {when}"


def _linked_sql(con, pay, task):
    field, ident = ("payment_id", pay["id"]) if pay else ("task_id", task["id"])
    return con.execute(f"SELECT * FROM sql_entries WHERE {field} = ? ORDER BY doc_date, id", (ident,)).fetchall()


def _einvoice_proof(found):
    return _proof("e-Invoice " + ", ".join(dict.fromkeys(s["einvoice"] or s["doc_no"] for s in found)), "validated, print from SQL")


def evidence(con, pay=None, task=None):
    """What the records imported here already show for the documents a payment or checklist item needs, so they count
    without an upload (one can still be added): a linked SQL voucher (PV, OR, JV) stands for that voucher, printed from
    SQL; an e-Invoice LHDN validated that no refund or credit note takes back (_einvoices: on a linked SQL document, or
    the one the payment's e-Invoice UIN names) stands for the e-Invoice; and the bank lines linked to a payment stand
    for the bank receipt, on the statements of the months named. A receipt's invoice is the sales e-Invoice issued in
    SQL for it: that one, or the one filed on the checklist item for the month's receipts (_item_proof).
    Returns {doc type: {"ref": what shows it, "text": what to print, for the screens and the audit pack}}."""
    out = _own_evidence(con, pay, task)
    if pay and pay["category"] == "receipt" and "invoice" not in out:
        proof = out.get("einvoice") or _item_proof(con, pay)
        if proof:
            out["invoice"] = proof
    return out


def _invoice_proof(sql):
    """The proof of the customer invoices (IV) among the SQL documents linked to a receipt: Invoice ABC/2026/10/001
    (print from SQL), or None."""
    nos = [s["doc_no"] for s in sql if (s["doc_type"] or "").upper() == "IV"]
    return _proof("Invoice " + ", ".join(dict.fromkeys(nos)), "print from SQL") if nos else None


def _own_evidence(con, pay=None, task=None):
    """evidence() of the payment's or item's own records, before what is filed on a checklist item stands in."""
    sql = _linked_sql(con, pay, task)
    vouchers = {}
    for s in sql:
        t = rules.SQL_VOUCHERS.get((s["doc_type"] or re.match(r"[A-Za-z]*", s["doc_no"]).group(0)).upper())
        if t:
            vouchers.setdefault(t, {})[s["doc_no"]] = True
    out = {t: _proof(", ".join(nos), "print from SQL") for t, nos in vouchers.items()}
    if pay and pay["direction"] == "in" and _invoice_proof(sql):
        out["invoice"] = _invoice_proof(sql)  # the sales invoice issued in SQL for the money received
    einv =[s for s, by in _einvoices(con, sql, pay) if not by]
    if einv:
        out["einvoice"] = _einvoice_proof(einv)
    if pay:
        lines = con.execute("""SELECT l.txn_date, s.month FROM statement_lines l JOIN statements s ON s.id = l.statement_id
                               WHERE l.payment_id = ? ORDER BY l.txn_date""", (pay["id"],)).fetchall()
        if lines:
            mons = list(dict.fromkeys(calendar.month_abbr[int(l["month"][5:7])] for l in lines))
            out["bank"] = _proof(_bank_lines([l["txn_date"] for l in lines]),
                                 f"on the {' and '.join(mons)} bank statement{'s' if len(mons) > 1 else ''}")
    return out


def not_counted(con, pay=None, task=None):
    """Why the validated e-Invoices on a payment's or checklist item's SQL documents don't stand for the one it needs,
    when evidence() leaves them all out: a refund or credit note took them back. For the screens and the audit pack to
    show beside an e-Invoice still missing. Returns {"einvoice": {"why": "on PV2601-002, cancelled by OR2601-004",
    "hint": what it means and what to do}}, or {}."""
    found = _einvoices(con, _linked_sql(con, pay, task), pay)
    if not found or any(by is None for _, by in found):
        return {}
    docs, by = _listed(s["doc_no"] for s, _ in found), _listed(b for _, b in found)
    s_, was, it = ("", "was", "it doesn't") if len({s["doc_no"] for s, _ in found}) == 1 else ("s", "were", "they don't")
    todo = "Upload the valid e-Invoice, or enter its UIN above if it is in SQL." if pay else f"Upload the valid e-Invoice{s_}."
    return {"einvoice": {"why": f"on {docs}, cancelled by {by}",
                         "hint": f"The e-Invoice{s_} on {docs} {was} cancelled by {by} (a refund or credit note), so {it} count. {todo}"}}


def _uploaded(con, field, ident):
    """The document types uploaded to a payment or checklist item (field: payment_id or task_id)."""
    return {r["doc_type"] for r in con.execute(
        f"SELECT doc_type FROM documents WHERE {field} = ? AND replaced_by IS NULL AND removed_at IS NULL", (ident,))}


def missing_docs(con, required, field, ident, ev):
    """The document types required that are neither uploaded to the payment or checklist item (field: payment_id or
    task_id) nor shown by its evidence (ev, from evidence())."""
    have = _uploaded(con, field, ident)
    return [d for d in required if d not in have and d not in ev]


def payment_status(con, pay, uses_sql, ev=None):
    """planned -> paid -> complete, or part_paid while the bank lines linked add up to less than the amount and no
    note accepts the difference. A required document counts when uploaded or shown by evidence (ev, from evidence(),
    looked up when not given). Returns (status, missing doc types)."""
    ev = evidence(con, pay=pay) if ev is None else ev
    required = rulebook.get(con).required_docs(pay["category"], uses_sql, pay["month"], pay["entity_id"])  # as in force then
    missing = missing_docs(con, required, "payment_id", pay["id"], ev)
    if not pay["paid_date"]:
        return "planned", missing
    if part_paid(pay, linked_total(con, pay)):
        return "part_paid", missing
    return ("complete" if not missing else "paid"), missing


def part_paid(pay, found):
    """True while the bank lines linked to a payment (found, from linked_total) add up to less than its amount and no
    note accepts the difference."""
    return found is not None and pay["amount"] is not None and pay["amount"] - found > 0.01 and not pay["difference_note"]


def not_in_sql(ent, pay):
    """True for a payment paid but not recorded in SQL yet (no SQL voucher number on it), for a company kept in SQL."""
    return bool(ent["uses_sql"] and pay["paid_date"] and not pay["sql_ref"])


def status_word(pay, status):
    """A payment's status as a word: Complete, Paid, Part paid or Not paid; for money in Received, Received, Part
    received and Not received."""
    if pay["direction"] == "in":
        return {"complete": "Received", "paid": "Received", "part_paid": "Part received"}.get(status, "Not received")
    return {"complete": "Complete", "paid": "Paid", "part_paid": "Part paid"}.get(status, "Not paid")


def money(n, currency="MYR"):
    """An amount as the screens show it: RM 10,000.00, USD 1,250.00."""
    return f"{'RM' if currency == 'MYR' else currency} {n:,.2f}"


def _short_doc(t, R=None):
    """A document type's short name: Payment Voucher for Payment Voucher (SQL). R: rulebook.get(con) (without, rules.py's)."""
    return (R or rulebook.FROZEN).short_doc(t)


# ---------- what the dates mean today ----------

def legal_due(pay, R=None):
    """A payment's legal deadline (its payment type's: statutory payments by the 15th after the payroll month), else
    None. It takes the payment's month as the payroll month; a payment created from an SQL voucher has the voucher's
    month. R: rulebook.get(con) (the app always passes it; without, rules.py's values, for callers with no records at hand)."""
    r = (R or rulebook.FROZEN).legal_due(pay["category"])
    return due(pay["month"], *r) if r else None


def _flag(code, text, tone, hint=None):
    return {"code": code, "text": text, "tone": tone, "hint": hint}


def payment_flag(con, ent, pay, today):
    """What a payment's dates mean on the day given (today, e.g. 2026-11-04), in the words every screen uses. Not paid
    yet: Past legal deadline for a statutory payment after the 15th; else Not paid while it isn't due, Due today, and
    once past due why it still shows as not paid: Not on <Mon> statement once a statement of an account of the company
    in its currency is imported for the month it fell due without a line linked; until then Waiting for SQL record
    (companies in SQL) while no SQL voucher is linked and it fell due after the latest voucher imported, else Waiting
    for <Mon> statement. Money in says it its own way: Not received yet while it isn't due, Not received where money out
    says Not paid once past due (a month filed, a bank line cleared by hand), the same variants otherwise. Paid: a note
    when a statutory payment was paid after its legal deadline, else None. Nothing
    counts in a month before the first month tracked, and nothing is to do in a month marked as filed (it says Not
    paid, or the note for a late payment). Returns {code, text, tone (grey, warn or bad), hint} or None."""
    legal = legal_due(pay, rulebook.get(con))
    money_in = pay["direction"] == "in"
    not_paid = "Not received" if money_in else "Not paid"
    if before_tracking(ent, pay["month"]):
        return None if pay["paid_date"] else _flag("not_paid", not_paid, "grey")
    if pay["paid_date"]:
        if legal and pay["paid_date"] > legal:
            return _flag("paid_late", f"Paid after legal deadline ({short_day(legal)})", "bad",
                         f"Paid {short_day(pay['paid_date'])}, after the legal deadline of {short_day(legal)}. Keep any "
                         "late-payment notice with this payment.")
        return None
    if closed_at(con, ent["id"], pay["month"]):
        return _flag("not_paid", not_paid, "grey")
    if legal and today > legal:
        return _flag("past_legal", f"Past legal deadline ({short_day(legal)})", "bad",
                     f"Not recorded as paid by the legal deadline of {short_day(legal)}. Pay it now, or link its bank line "
                     "or SQL voucher if it was paid; a late-payment charge may follow.")
    deadline = f" Legal deadline {short_day(legal)}." if legal else ""
    due_on, mon = pay["due_date"], calendar.month_abbr[int(pay["due_date"][5:7])]
    probably = "Probably received" if money_in else "Probably paid"
    if due_on > today:
        return _flag("not_paid", "Not received yet" if money_in else "Not paid", "grey", deadline.strip() or None)
    if due_on == today:
        todo = ("Expected today: enter the date it was received once it is in." if money_in
                else "Pay it today, or enter the paid date once it has gone out.")
        return _flag("due_today", "Due today", "warn", todo + deadline)
    if con.execute("""SELECT 1 FROM statements s JOIN accounts a ON a.id = s.account_id
                      WHERE a.entity_id = ? AND a.currency = ? AND s.month = ?""",
                   (ent["id"], pay["currency"], due_on[:7])).fetchone():
        if con.execute("SELECT 1 FROM statement_lines WHERE payment_id = ?", (pay["id"],)).fetchone():
            return _flag("not_paid", not_paid, "grey", deadline.strip() or None)  # its paid date was cleared by hand
        other_way = ("enter the date it was received if it came in another way" if money_in
                     else "enter the paid date if it went out another way")
        return _flag("not_on_statement", f"Not on {mon} statement", "bad",
                     f"The {mon} bank statement is imported, but no line on it is linked to this payment. Link its line on "
                     f"the Bank statements page, or {other_way}." + deadline)
    # (a journal is linked to a payment only when its lines move the bank, so it records the payment in SQL like a voucher)
    if ent["uses_sql"] and not con.execute("SELECT 1 FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')",
                                           (pay["id"],)).fetchone():
        latest = con.execute("SELECT MAX(doc_date) FROM sql_entries WHERE entity_id = ? AND COALESCE(kind, 'payment') = 'payment'",
                             (ent["id"],)).fetchone()[0]
        if not latest or due_on > latest:
            upto = f"the SQL entries imported go up to {short_day(latest)}" if latest else "no SQL listing is imported yet"
            return _flag("waiting_sql", "Waiting for SQL record", "warn",
                         f"{probably}: {upto}. Paste the latest SQL listing to record it." + deadline)
    return _flag("waiting_statement", f"Waiting for {mon} statement", "warn",
                 f"{probably}: the {mon} bank statement isn't imported yet. Import it on the Bank statements page to "
                 "confirm this payment." + deadline)


def task_flag(con, ent, task, today, done=None):
    """What a checklist item's due date means on the day given: Overdue or Due today while it isn't done (done, from
    task_status; else while it isn't ticked), else None. Nothing counts in a month before the first month tracked, or
    in one marked as filed."""
    if (task["done_at"] if done is None else done) or before_tracking(ent, task["month"]) \
            or closed_at(con, ent["id"], task["month"]):
        return None
    if task["due_date"] < today:
        return _flag("overdue", "Overdue", "bad")
    return _flag("due_today", "Due today", "warn") if task["due_date"] == today else None


# ---------- what the records show a checklist item is ----------

def task_status(con, ent, task, ev=None):
    """A checklist item's status, worked out here for the month page, the Overview and the audit pack. done: ticked by
    hand, or what it asks for shows in the records (auto), as the item is for its month (checklistbook): the month's
    payments, its bank statements or an audit pack built since its documents last changed, and
    the documents it asks for itself are filed. why: what the records show ('Done: both statements imported') or still
    lack ('AI MBB FCA (USD) statement not imported yet'), None for an item they can't show. missing: the documents it
    asks for not filed (ev: its evidence(), looked up when not given). lacking: what a tick by hand would leave out, in
    words. shown: what to print from SQL for the documents filed on the item for its payments (on_item). waiting: the
    later month it falls due in while it waits in this one (waits_for), left out of this month's counts and pack."""
    code, month = task["code"], task["month"]
    shown = []
    kind, rule = checklistbook.get(con).completion(ent["id"], code, month)  # as the item is for the task's own month
    if kind == "payments" and rule:
        ok, why, shown = _from_payments(con, ent, task, rule)
    elif kind in checklistbook.STATEMENTS_ARG:
        ok, why = _from_statements(con, ent, month, checklistbook.STATEMENTS_ARG[kind])
    elif kind == "pack":
        ok, why = _from_pack(con, ent, month)
    else:
        ok, why = None, None
    ev = evidence(con, task=task) if ev is None else ev
    # The reconciliation is the sign-off itself: a company set up before it asked for a filed document keeps none to file.
    required = [d for d in json.loads(task["required_docs"]) if not (code == "recon" and d == "recon")]
    missing = missing_docs(con, required, "task_id", task["id"], ev)
    if ok and missing:
        why = why[6].upper() + why[7:]  # what the records show, without 'Done: ': its own document is still to file
    lacking = ([why] if ok is False else []) + ([f"Still missing: {_listed(map(rulebook.get(con).short_doc, missing))}"] if missing else [])
    auto = bool(ok) and not missing
    return {"done": bool(task["done_at"]) or auto, "auto": auto, "why": why, "missing": missing, "lacking": lacking,
            "shown": shown, "waiting": waits_for(task, con)}


def _counted(n, many):
    """Two or more things, as both statements or all 3 statements (many: what several are called)."""
    return f"both {many}" if n == 2 else f"all {n} {many}"


def _names(group, among):
    """The descriptions of a group of payments: a, b and c, or the first three and how many more. Each is cut to 40
    characters (SQL descriptions run long), or as much longer as still tells apart the payments among; one that shares
    its description with another of them also gets its date."""
    descs = [p["description"] for p in among]
    for n in (40, 60, 80, None):
        cut = {s: s if not n or len(s) <= n else s[:n - 3].rstrip() + "..." for s in descs}
        if len(set(cut.values())) == len(cut):
            break
    names = [cut[p["description"]] + (f" ({short_day(p['paid_date'] or p['due_date'])})" if descs.count(p["description"]) > 1 else "")
             for p in group]
    return _listed(names) if len(names) <= 3 else f"{', '.join(names[:3])} and {len(names) - 3} more"


def _covers(rule, p):
    """True when a checklist item's payments rule (checklistbook) covers the payment."""
    words = rule.get("words")
    return ((not rule.get("categories") or p["category"] in rule["categories"])
            and (not rule.get("direction") or p["direction"] == rule["direction"])
            and (not words or bool(re.search(rf"\b({'|'.join(map(re.escape, words))})\b",
                                             f"{p['description']} {p['payee_name'] or ''}", re.I))))


MONTH_NAMED = re.compile(r"\b(JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUNE?|JULY?|AUG(?:UST)?|SEPT?(?:EMBER)?"
                         r"|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?)\.?\s*'?(\d{4}|\d{2})\b", re.I)


def named_month(text):
    """The month a description names: 2026-10 for EXPENSES FOR OCTOBER 26 or OCT 2026, else None."""
    m = MONTH_NAMED.search(text or "")
    if not m:
        return None
    y = int(m.group(2))
    return f"{y + 2000 if y < 100 else y:04d}-{[a.upper() for a in calendar.month_abbr].index(m.group(1)[:3].upper()):02d}"


def _for_month(s, month):
    """True when an SQL document filed on a checklist item is for the item's month: the month its description names,
    else the one being worked on at its date. Filed by the nearest due date, one dated early in a month can sit on the
    month before's item. An invoice or journal is filed by its own month (filing_month), so it counts there."""
    if s["kind"] in FILED_BY_MONTH:
        return filing_month(s["description"], s["doc_date"]) == month
    return (named_month(s["description"]) or current_cycle(date.fromisoformat(s["doc_date"]))) == month


def _on_item(con, task, docs):
    """What the documents filed on a checklist item for its payments (its payments rule's on_item) stand for:
    ({doc type: None for an upload, which stands for every payment, else the amount the item's validated e-Invoices for
    its month add up to, which stands for payments up to that much}, the proof of those e-Invoices, to print from SQL)."""
    have = _uploaded(con, "task_id", task["id"])
    cover, shown = {d: None for d in docs if d in have}, []
    if "einvoice" in docs and "einvoice" not in cover:
        found = [s for s, by in _einvoices(con, [s for s in _linked_sql(con, None, task) if _for_month(s, task["month"])], None)
                 if not by]
        if found:
            cover["einvoice"] = round(sum(s["amount"] for s in found), 2)
            shown.append(_einvoice_proof(found))
    return cover, shown


def _item_payments(con, entity_id, month, rule):
    """The month's payments a checklist item's payments rule covers, in due order."""
    return [p for p in con.execute(
        """SELECT p.*, py.name AS payee_name FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.month = ? ORDER BY p.due_date, p.id""", (entity_id, month)) if _covers(rule, p)]


def _allocated(con, rule, pays, cover):
    """Goes through the payments a checklist item covers in order, giving each what is filed on the item (cover, from
    _on_item: an upload stands for every payment, e-Invoices for payments up to what they add up to, used up as it
    goes). Yields (the payment, the documents it still lacks, or None for a paid one where paying counts, the documents
    the item stands for)."""
    for p in pays:
        if rule.get("paid") and p["paid_date"]:
            yield p, None, []
            continue
        miss, took = missing_docs(con, rule["docs"], "payment_id", p["id"], _own_evidence(con, pay=p)), []
        for d in [d for d in miss if d in cover]:
            if cover[d] is None or cover[d] + 0.01 >= (p["amount"] or 0):
                miss.remove(d)
                took.append(d)
                if cover[d] is not None:
                    cover[d] -= p["amount"] or 0
        yield p, miss, took


def _item_proof(con, pay):
    """For a receipt, the proof of the sales e-Invoice filed on the checklist item for the month's receipts that stands
    for it (the item's e-Invoices cover the receipts in order, up to what they add up to, as the item counts them),
    else None."""
    for code, rule in checklistbook.get(con).einvoice_rules(pay["entity_id"], pay["month"]):
        task = con.execute(
            "SELECT * FROM tasks WHERE entity_id = ? AND month = ? AND code = ?", (pay["entity_id"], pay["month"], code)).fetchone()
        pays = task and _item_payments(con, pay["entity_id"], pay["month"], rule)
        if pays and any(p["id"] == pay["id"] for p in pays):
            cover, proofs = _on_item(con, task, rule["on_item"])
            for p, _, took in _allocated(con, rule, pays, cover):
                if p["id"] == pay["id"]:
                    return proofs[0] if "einvoice" in took else None
    return None


def _from_payments(con, ent, task, rule):
    """(ok, why, shown) for a checklist item the month's payments show: ok when each one it covers has the documents
    named, on it or (on_item) on the checklist item, or is paid where paying counts; None while there is none and
    rule none can't tell yet. shown: what to print from SQL for the item's own e-Invoices (_on_item). The words say
    whether the documents are on file, recorded in SQL, or both."""
    one, many = rule["name"]
    pays = _item_payments(con, task["entity_id"], task["month"], rule)
    if not pays:
        if rule.get("none") and _from_statements(con, ent, task["month"], False)[0]:
            return True, f"Done: {rule['none']}", []
        return (None if rule.get("none") else False), f"No {one} this month yet", []
    cover, proofs = _on_item(con, task, rule.get("on_item", []))
    shown = [x["text"] for x in proofs]
    paid, lacking, from_sql, from_files = 0, {}, False, False
    for p, miss, took in _allocated(con, rule, pays, cover):
        if miss is None:
            paid += 1
            continue
        up = _uploaded(con, "payment_id", p["id"])
        for d in (d for d in rule["docs"] if d not in miss):
            filed = cover[d] is None if d in took else d in up
            from_files, from_sql = from_files or filed, from_sql or not filed
        if miss:
            group, takers = lacking.setdefault(_listed(map(rulebook.get(con).short_doc, miss)), ([], []))
            group.append(p)
            if "einvoice" in miss:
                takers += [by for _, by in _einvoices(con, _linked_sql(con, p, None), p) if by]
    n, docs = len(pays), _listed(map(rulebook.get(con).short_doc, rule["docs"]))
    who = f"the {one}" if n == 1 else _counted(n, many)
    if lacking:
        unpaid = ", not paid yet" if rule.get("paid") else ""
        return False, "; ".join(
            f"{d} still missing for " + (_names(group, pays) if n == 1 else who if len(group) == n
                                         else f"{len(group)} of {n} {many}: {_names(group, pays)}")
            + (f" (e-Invoice cancelled by {_listed(takers)})" if takers else "") + unpaid
            for d, (group, takers) in lacking.items()), shown
    if paid == n:
        return True, f"Done: {who} {'is' if n == 1 else 'are'} paid", shown
    how = "recorded in SQL" if from_sql and not from_files else "on file or recorded in SQL" if from_sql else "on file"
    return True, (f"Done: {who} paid or with the {docs} {how}" if paid else f"Done: {docs} {how} for {who}"), shown


def month_statements(con, ent, month):
    """Each bank account of the company with its statement for the month, in account order: {id, label, statement (its
    id, None while not imported), check_ok (balances add up), to_explain (lines not explained yet)}."""
    sts = {s["account_id"]: s for s in con.execute(
        """SELECT s.id, s.account_id, s.check_ok, (SELECT COUNT(*) FROM statement_lines l WHERE l.statement_id = s.id
           AND l.status = 'unmatched') AS to_explain FROM statements s JOIN accounts a ON a.id = s.account_id
           WHERE a.entity_id = ? AND s.month = ?""", (ent["id"], month))}
    out = []
    # a stopped account counts only in a month it has a statement for (so it stops asking for new ones)
    stopped = "AND (active = 1 OR id IN (SELECT account_id FROM statements WHERE month = ?))" if _has_col(con, "accounts", "active") else ""
    for a in con.execute(f"SELECT id, label FROM accounts WHERE entity_id = ? {stopped} ORDER BY id",
                         (ent["id"], month) if stopped else (ent["id"],)).fetchall():
        s = sts.get(a["id"])
        out.append({"id": a["id"], "label": a["label"], "statement": s["id"] if s else None,
                    "check_ok": bool(s and s["check_ok"]), "to_explain": s["to_explain"] if s else 0})
    return out


def _from_statements(con, ent, month, balanced):
    """(ok, why) for a checklist item the month's bank statements show: one imported for every account of the
    company, and when balanced is True each one balancing with no line left to explain. None for a company with no
    account."""
    accts = month_statements(con, ent, month)
    if not accts:
        return None, None
    absent = [a["label"] for a in accts if not a["statement"]]
    if absent:
        return False, f"{_listed(absent)} statement{'s' if len(absent) > 1 else ''} not imported yet"
    n = len(accts)
    if not balanced:
        return True, "Done: statement imported" if n == 1 else f"Done: {_counted(n, 'statements')} imported"
    if balanced == "reconciled":
        from . import recon
        off = [f"{a['label']}: {w}" for a in accts if (w := recon.not_reconciled(con, ent, a["id"], month))]
        if off:
            return False, "; ".join(off)
        return True, "Done: reconciled" + (f" on {_counted(n, 'statements')}" if n > 1 else "")
    off = [f"balances don't add up on {a['label']}" for a in accts if not a["check_ok"]]
    for a in accts:
        k = a["to_explain"]
        if k:
            off.append(f"{k} line{'s' if k > 1 else ''} to explain on {a['label']}")
    if off:
        why = "; ".join(off)
        return False, why[0].upper() + why[1:]
    return True, "Done: balances add up and every line is explained" + (f" on {_counted(n, 'statements')}" if n > 1 else "")


def packs_of(ent, month):
    """The audit packs built for a company and month (as auditpack.build names them), oldest first."""
    return sorted((PACKS_DIR / ent["code"]).glob(f"Audit pack {ent['code']} {month} (*).pdf"), key=lambda p: p.stat().st_mtime)


def latest_pack(con, ent, month):
    """The newest audit pack built for a company and month, or None: {path, when (3 Nov 22:27), changed (documents
    added or removed since it was built)}. Only what a pack holds counts: not the copy of an SQL listing kept on each
    paste, nor a document on the audit pack item itself. A checklist item's documents belong to the month it is in now
    (a reminder moves on), none to one waiting there."""
    packs = packs_of(ent, month)
    if not packs:
        return None
    built = datetime.fromtimestamp(packs[-1].stat().st_mtime)
    stamp = built.isoformat(timespec="seconds")
    n = sum(1 for t in con.execute(
        """SELECT t.code, t.month, t.due_date, t.done_at FROM documents d LEFT JOIN tasks t ON t.id = d.task_id
           WHERE d.entity_id = ? AND COALESCE(t.month, d.month) = ? AND d.doc_type != 'sqlexport'
           AND (d.uploaded_at > ? OR d.removed_at > ?)""",
        (ent["id"], month, stamp, stamp)) if t["month"] is None or (t["code"] != rules.TASK_PACK and not waits_for(t, con)))
    return {"path": packs[-1], "when": f"{built.day} {calendar.month_abbr[built.month]} {built:%H:%M}", "changed": n}


def _from_pack(con, ent, month):
    """(ok, why) for the audit pack item: a pack built for the month since its documents were last added or removed,
    or the month marked as filed (on paper, or with what was still open, as the warning named it)."""
    pack = latest_pack(con, ent, month)
    if pack and not pack["changed"]:
        return True, f"Done: audit pack built {pack['when']}"
    filed = closed_at(con, ent["id"], month)
    if filed:
        return True, f"Done: month marked as filed {short_day(filed[:10])}"
    if not pack:
        return False, "No audit pack built for this month yet"
    n = pack["changed"]
    return False, f"{n} document{'s' if n > 1 else ''} added or removed since the audit pack of {pack['when']}: build it again"


def open_estimate(con, pay, found):
    """The estimate a payment was planned at while its amount is only what the bank lines linked so far add up to (found,
    from linked_total) and that is less, so the rest may still be sent: until the figure is confirmed, an SQL voucher
    records it, or a note accepts the difference. Else None."""
    if not pay["planned_is_estimate"] or pay["planned_amount"] is None or found is None or pay["difference_note"] \
            or pay["planned_amount"] - found <= 0.01:
        return None
    in_sql = con.execute("SELECT 1 FROM sql_entries WHERE payment_id = ?", (pay["id"],)).fetchone()
    return None if in_sql else pay["planned_amount"]


def budgeted_at(con, pay, found):
    """What a payment is budgeted at, given what the bank lines linked to it add up to (found, from linked_total): its
    amount, but with lines linked the estimate while one is still open, and what the lines add up to when a note accepts
    the difference."""
    if found is None or pay["amount"] is None:
        return pay["amount"]
    return found if pay["difference_note"] else max(pay["amount"], open_estimate(con, pay, found) or 0)


def still_to_pay(con, pay, as_at):
    """What of a payment is still to be paid from a bank balance taken on as_at (e.g. 2026-10-20). With bank lines
    linked, the lines decide, whatever the paid date: what it is budgeted at (budgeted_at) less the lines dated by then,
    so a transfer after that date still counts. With none, nothing when it was paid by then, as it is already out of
    that balance, else its amount, blank included."""
    found = linked_total(con, pay)
    if found is None or pay["amount"] is None:
        return 0 if pay["paid_date"] and pay["paid_date"] <= as_at else pay["amount"]
    due = budgeted_at(con, pay, found)
    sign = -1 if pay["direction"] == "out" else 1
    by_then = sum(sign * r[0] for r in con.execute(
        "SELECT amount FROM statement_lines WHERE payment_id = ? AND txn_date <= ?", (pay["id"], as_at)))
    left = round(due - by_then, 2)
    return left if left > 0.01 else 0
