"""The Books page's reports as Excel files: the trial balance, the general ledger, the profit and loss account, the
balance sheet, the customers' and suppliers' balances with their ageing, and the statutory payables check. Each is built from the same function as
the screen (books, finstatements, receivables), for the same period and options, so a figure in the file is the figure
on the page. Built in memory, as the budget export is (reports.budget_workbook). Pure reads: nothing here writes.

Every sheet starts with a title block: the company, the report and its period, then where the figures come from
("Mirrored from SQL Account, read 14/11/2026" for a company kept in SQL, the day SQL's reports were last read here).
The heading row is frozen, the columns have widths set, and the amounts are numbers to 2 decimals in ringgit. The
totals are written as figures, worked out here as on the screen, not as formulas the owner would have to trust.
"""
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from . import books, db, finstatements, receivables, statutory as stat
from .docstore import safe
from .ledger import _exists, _money
from .reports import BOLD, _print_setup, _put

MONEY = "#,##0.00"
SIGNED = "#,##0.00;(#,##0.00)"  # a figure the other way round in brackets, as the statements show it
DAY = "dd/mm/yyyy"
BOOK_NAMES = {"bank": "Bank", "general": "General", "sales": "Sales", "purchase": "Purchase", "other": "Other"}
REPORTS = ("trial-balance", "ledger", "profit-and-loss", "balance-sheet", "customers-and-suppliers", "statutory-payables")


def _rm(sen):
    """Sen as ringgit to 2 decimals, or None (an empty cell) when the amount isn't known."""
    return None if sen is None else round(sen / 100, 2)


def _d(iso):
    return date.fromisoformat(iso) if iso else None


def _dmy(iso):
    return f"{date.fromisoformat(iso):%d/%m/%Y}"


def last_read(con, ent):
    """When SQL's reports were last read for the company (the latest GL journal, ledger or trial balance kept), as a
    stored time, or None."""
    if not _exists(con, "ledger_batches"):
        return None
    return con.execute("SELECT MAX(read_at) FROM ledger_batches WHERE entity_id = ? AND origin = 'sql'", (ent["id"],)).fetchone()[0]


def source_line(con, ent):
    """Where the figures come from, in one sentence."""
    if ent["uses_sql"] is not None and not ent["uses_sql"]:
        return "Books kept in this app: this company's books are not kept in SQL Account."
    at = last_read(con, ent)
    if not at:
        return "Mirrored from SQL Account: nothing has been read from SQL yet."
    return f"Mirrored from SQL Account, read {_dmy(str(at)[:10])}"


def _title(ws, con, ent, heading):
    """The title block: the company, the report and its period, where the figures come from and when the file was
    made. Returns the heading row's number."""
    c = _put(ws, 1, 1, f"{ent['name']} ({ent['code']})")
    c.font = Font(bold=True, size=13)
    _put(ws, 2, 1, heading, bold=True)
    _put(ws, 3, 1, f"{source_line(con, ent)}. Exported {datetime.now():%d/%m/%Y %H:%M}.")
    return 5


def _head(ws, top, headers, widths, nums=()):
    """The heading row, bold (nums: the amount columns, their headings to the right), frozen below it, the column
    widths and the print setup."""
    for i, h in enumerate(headers, 1):
        c = _put(ws, top, i, h, bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right" if i in nums else "left")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=top + 1, column=1)
    _print_setup(ws, top)


def _row(ws, r, values, fmts, bold=False, indent=0):
    """One row of values from column 1; fmts: {column: number format}. A None value leaves its cell empty."""
    for i, v in enumerate(values, 1):
        if v is None:
            continue
        c = _put(ws, r, i, v, fmts.get(i), bold)
        if indent and i == 2 and isinstance(v, str):
            c.alignment = Alignment(indent=indent)
    return r + 1


def _notes(ws, r, notes):
    """Sentences under a report, one per row in column 1."""
    for n in notes:
        if n:
            _put(ws, r, 1, n)
            r += 1
    return r


def _file(ent, words, day, at=False):
    """A safe file name: '<CODE> Trial balance to 31-01-2026.xlsx'. Only the words are shortened when they are long (an
    account code typed into the address), so the date always stays in the name."""
    head = safe(f"{ent['code']} {words}", 90)
    return safe(f"{head} {'at' if at else 'to'} {date.fromisoformat(day):%d-%m-%Y}", 120) + ".xlsx"


# ---------- the trial balance ----------

def trial_balance(con, ent, d_from=None, d_to=None, rollup=False):
    """The trial balance as on the Books page, with its check against SQL's own trial balance (a company kept in SQL).
    Returns (workbook, file name)."""
    d = books.trial_balance(con, ent["id"], d_from, d_to, rollup=rollup)
    wb = Workbook()
    ws = wb.active
    ws.title = "Trial balance"
    top = _title(ws, con, ent, f"Trial balance, {_dmy(d['from'])} to {_dmy(d['to'])}"
                 + (" (customers and suppliers added into their control accounts)" if d["rollup"] else ""))
    resets = any(r["reset_sen"] for r in d["accounts"])
    heads = ["Code", "Name", "Opening debit", "Opening credit", "Debit", "Credit"] + (["Year start (debit above 0)"] if resets else []) \
        + ["Closing debit", "Closing credit"] + (["Added in"] if d["rollup"] else [])
    n = 8 + resets
    fmts = {i: (SIGNED if resets and i == 7 else MONEY) for i in range(3, n + 1)}
    _head(ws, top, heads, [14, 40] + [15] * (n - 2) + ([30] if d["rollup"] else []), fmts)
    r = top + 1
    for a in d["accounts"]:
        o = (None, None) if a["opening_sen"] is None else (a["opening_dr_sen"], a["opening_cr_sen"])
        cl = (None, None) if a["closing_sen"] is None else (a["closing_dr_sen"], a["closing_cr_sen"])
        vals = [a["code"] or "", a["name"] or "", *map(_rm, o), _rm(a["dr_sen"]), _rm(a["cr_sen"])]
        vals += ([_rm(a["reset_sen"])] if resets else []) + [*map(_rm, cl)] + ([", ".join(a["rolled"])] if d["rollup"] else [])
        r = _row(ws, r, vals, fmts)
    t = d["totals"]
    vals = ["Total", "", _rm(t["opening_dr_sen"]), _rm(t["opening_cr_sen"]), _rm(t["dr_sen"]), _rm(t["cr_sen"])]
    vals += ([_rm(t["reset_sen"])] if resets else []) + [_rm(t["closing_dr_sen"]), _rm(t["closing_cr_sen"])]
    r = _row(ws, r, vals, fmts, bold=True) + 1
    _put(ws, r, 1, "Balances: the debits and credits are equal." if d["balanced"] else "Doesn't balance (see the notes below).", bold=True)
    r += 1
    if ent["uses_sql"]:
        ch = books.check_against_sql(con, ent["id"], d["from"], d["to"])
        _put(ws, r, 1, f"Checked against SQL's trial balance: {ch['text']}")
        r += 1
        for x in ch["differences"]:
            _put(ws, r, 1, x["text"])
            r += 1
    _notes(ws, r + 1, d["notes"])
    return wb, _file(ent, "Trial balance", d["to"])


# ---------- the general ledger ----------

def ledger(con, ent, account=None, d_from=None, d_to=None):
    """The general ledger as on the Books page: one account (and the customers' and suppliers' codes under it, when it
    is a control account) or every account, each with its opening, its lines with the running balance, its totals and
    its closing. Returns (workbook, file name)."""
    d = books.ledger_report(con, ent["id"], account, d_from, d_to)
    wb = Workbook()
    ws = wb.active
    ws.title = "General ledger"
    top = _title(ws, con, ent, f"General ledger{' of ' + account if account else ', all accounts'}, "
                               f"{_dmy(d['from'])} to {_dmy(d['to'])}")
    _head(ws, top, ["Account", "Date", "Doc No", "Book", "Description", "Debit", "Credit", "Balance (debit above 0)"],
          [14, 12, 16, 10, 52, 15, 15, 16], (6, 7, 8))
    fmts = {2: DAY, 6: MONEY, 7: MONEY, 8: SIGNED}
    r = top + 1
    for a in d["accounts"]:
        r = _row(ws, r, [a["code"], None, None, None, f"{a['code']} {a['name'] or ''}".strip()], fmts, bold=True)
        words = "Opening balance" + (f" ({a['opening_words']}" + (f" at {_dmy(a['opening_as_of'])}" if a["opening_as_of"] else "") + ")"
                                     if a["opening_words"] else "")
        r = _row(ws, r, [a["code"], _d(d["from"]), None, None, words, None, None, _rm(a["opening_sen"])], fmts)
        for x in a["rows"]:
            r = _row(ws, r, [a["code"], _d(x["date"]), x["doc_no"], BOOK_NAMES.get(x["book"], x["book"]) if x["book"] else None,
                             x["description"] or "", _rm(x["dr_sen"]) or None, _rm(x["cr_sen"]) or None, _rm(x["balance_sen"])], fmts)
        r = _row(ws, r, [a["code"], None, None, None, "Total for the period", _rm(a["dr_sen"]), _rm(a["cr_sen"])], fmts, bold=True)
        r = _row(ws, r, [a["code"], _d(d["to"]), None, None, "Closing balance", None, None, _rm(a["closing_sen"])], fmts, bold=True)
        r = _notes(ws, r, a["notes"]) + 1
    if not d["accounts"]:
        _put(ws, r, 1, f"No line or opening balance is kept for {account or 'any account'} in these dates.")
        r += 1
    _notes(ws, r, d["notes"])
    return wb, _file(ent, f"General ledger {safe(account, 40)}" if account else "General ledger", d["to"])


# ---------- the profit and loss account and the balance sheet ----------

def _statement(ws, top, d):
    """The blocks of a statement (finstatements) under a heading of its columns. Returns the next free row."""
    cols = d["columns"]
    fmts = {i: SIGNED for i in range(3, 3 + len(cols))}
    _head(ws, top, ["Code", "Account"] + [c["label"] + (" (comparative)" if c["role"] == "comparative" else "") for c in cols],
          [14, 46] + [18] * len(cols), fmts)
    r = top + 1
    for b in d["blocks"]:
        if b["kind"] == "section":
            r = _row(ws, r, ["", b["title"]], fmts, bold=True)
            for x in b["rows"]:
                if x["kind"] == "group_total":
                    r = _row(ws, r, ["", x["name"], *map(_rm, x["amounts"])], fmts, bold=True, indent=x["depth"] + 1)
                else:
                    r = _row(ws, r, [x["code"] or "", x["name"] or "", *map(_rm, x["amounts"])], fmts, indent=x["depth"] + 1)
            r = _row(ws, r, ["", b["total_label"], *map(_rm, b["total"])], fmts, bold=True)
        else:
            r = _row(ws, r, ["", b["label"], *map(_rm, b["amounts"])], fmts, bold=b["kind"] == "total")
    return r + 1


def profit_and_loss(con, ent, d_from=None, d_to=None, columns="total"):
    """The profit and loss account as on the Books page (one column, or one per month), with the comparative column
    when the screen shows one. Returns (workbook, file name)."""
    d = finstatements.profit_and_loss(con, ent["id"], d_from, d_to, columns)
    wb = Workbook()
    ws = wb.active
    ws.title = "Profit and loss"
    top = _title(ws, con, ent, f"Profit and loss, {_dmy(d['from'])} to {_dmy(d['to'])}")
    r = _statement(ws, top, d)
    _put(ws, r, 1, "Income is shown as a credit above 0 and costs as a debit above 0; a figure in brackets is the other way round.")
    r = _notes(ws, r + 1, [d["check"]["text"], ("No comparative column: " + d["comparative"]["why"]) if d["comparative"]["why"] else None])
    _notes(ws, r, d["notes"])
    return wb, _file(ent, "Profit and loss", d["to"])


def balance_sheet(con, ent, as_at=None):
    """The balance sheet as at a day, as on the Books page, with the end of the previous financial year when the
    screen shows it. Returns (workbook, file name)."""
    d = finstatements.balance_sheet(con, ent["id"], as_at)
    wb = Workbook()
    ws = wb.active
    ws.title = "Balance sheet"
    top = _title(ws, con, ent, f"Balance sheet at {_dmy(d['as_at'])} (profit or loss for the year from {_dmy(d['fy_from'])})")
    r = _statement(ws, top, d)
    _put(ws, r, 1, "Assets are shown as debits above 0, liabilities and equity as credits above 0; a figure in brackets is the other way round.")
    r = _notes(ws, r + 1, [d["check"]["text"], ("No comparative column: " + d["comparative"]["why"]) if d["comparative"]["why"] else None])
    _notes(ws, r, d["notes"])
    return wb, _file(ent, "Balance sheet", d["as_at"], at=True)


# ---------- customers and suppliers ----------

def parties(con, ent, d_from=None, d_to=None, side=None):
    """Who owes what, as on the Books page: per control account, each customer's or supplier's opening, invoiced,
    received or paid, other and closing, with the ageing at the To date, the totals, and the control account in the
    trial balance. side: 'customers', 'suppliers' or None for both. Returns (workbook, file name)."""
    d = receivables.balances(con, ent["id"], d_from, d_to, side)
    sides = d["sides"]
    who = "Customers and suppliers" if len(sides) > 1 else sides[0].capitalize()
    got = "Received or paid" if len(sides) > 1 else "Received" if sides[0] == "customers" else "Paid"
    words = {b["key"]: b["words"] for b in d["buckets"]}
    wb = Workbook()
    ws = wb.active
    ws.title = who[:31]
    top = _title(ws, con, ent, f"{who}, {_dmy(d['from'])} to {_dmy(d['to'])} (ageing at {_dmy(d['to'])})")
    _head(ws, top, ["Code", "Name", "Opening", "Invoiced", got, "Other", "Closing"] + [words[b] for b in receivables.BUCKETS] + ["Note"],
          [14, 40] + [15] * 10 + [50], range(3, 13))
    fmts = {i: SIGNED for i in range(3, 13)}
    r = top + 1
    for c in d["controls"]:
        r = _row(ws, r, [c["code"], f"{c['name']} ({'customers' if c['side'] == 'customers' else 'suppliers'})"], fmts, bold=True)
        for x in c["rows"]:
            age = [None] * len(receivables.BUCKETS) if x["credit"] or not x["ageing"] else [_rm(x["ageing"][b]) for b in receivables.BUCKETS]
            note = "; ".join((["In credit (paid in advance or overpaid)"] if x["credit"] else []) + x["notes"])
            r = _row(ws, r, [x["code"], (x.get("name_words") if x["own"] else x["name"]) or "", _rm(x["opening_sen"]), _rm(x["invoiced_sen"]),
                             _rm(x["received_sen"]), _rm(x["other_sen"]), _rm(x["closing_sen"]), *age, note or None], fmts)
        t = c["totals"]
        r = _row(ws, r, ["Total", "", _rm(t["opening_sen"]), _rm(t["invoiced_sen"]), _rm(t["received_sen"]), _rm(t["other_sen"]),
                         _rm(t["closing_sen"]), *[_rm(t["ageing"][b]) for b in receivables.BUCKETS],
                         f"In credit: {_money(t['in_credit_sen'])}" if t["in_credit_sen"] else None], fmts, bold=True)
        tb = c["tb"]
        r = _row(ws, r, [c["code"], "In the trial balance", _rm(tb["opening_sen"]), None, None, None, _rm(tb["closing_sen"]),
                         None, None, None, None, None, None if tb["moved_sen"] is None else f"Moved {_money(tb['moved_sen'])} in the period"], fmts)
        _put(ws, r, 1, c["text"])
        r += 2
    if not d["controls"]:
        _put(ws, r, 1, d["text"])
        r += 2
    else:
        _put(ws, r, 1, d["text"])
        r += 1
    _notes(ws, r, ["Each amount is what is owed; a figure in brackets is the other way round.", d["ageing_note"], *d["notes"]])
    return wb, _file(ent, who, d["to"])


# ---------- the statutory payables check ----------

def statutory_payables(con, ent, m_from=None, m_to=None):
    """The statutory payables check as on the Books page (statutory.report), for a range of payroll months (written
    2026-10; default this financial year to date): per payable account, each month's amount withheld, paid, the
    employer's share paid with it, the difference, the balance at the month's end and at its due date, and what it
    says, then the account's notes, the payments posted to another kind's account and the summary. Returns (workbook,
    file name)."""
    d = stat.report(con, ent["id"], m_from, m_to)
    wb = Workbook()
    ws = wb.active
    ws.title = "Statutory payables"
    span = db.month_label(d["from"]) + ("" if d["from"] == d["to"] else f" to {db.month_label(d['to'])}")
    top = _title(ws, con, ent, f"Statutory payables check, {span} (payroll months)")
    _head(ws, top, ["Month", "Due", "Withheld", "Paid", "Employer's share paid", "Difference", "Balance at month end",
                    "Balance at the due date", "Status", "What it says"], [16, 12, 15, 15, 17, 15, 17, 17, 12, 70], range(3, 9))
    fmts = {2: DAY, **{i: MONEY for i in range(3, 6)}, **{i: SIGNED for i in range(6, 9)}}
    r = top + 1
    for a in d["accounts"]:
        r = _row(ws, r, [f"{a['label']} ({a['payable_code']}{', employer ' + a['employer_code'] if a['employer_code'] else ''})"],
                 fmts, bold=True)
        for x in a["months"]:
            status = stat.STATUS_WORDS.get(x["status"], x["status"]) + (", paid late" if x["paid_late"] else "")
            if x["before_tracking"]:
                status += " (before the first month tracked)"
            r = _row(ws, r, [x["label"], _d(x["due"]), _rm(x["withheld_sen"]), _rm(x["paid_sen"]), _rm(x["employer_sen"]),
                             _rm(x["difference_sen"]), _rm(x["balance_end_sen"]), _rm(x["balance_due_sen"]), status, x["text"]], fmts)
        r = _notes(ws, r, a["notes"]) + 1
    if not d["accounts"]:
        r += 1
    _put(ws, r, 1, d["summary"], bold=True)
    r += 1
    _notes(ws, r, [x["text"] for x in d.get("postings") or []]
           + ["Balances are signed: a payable still owed shows in brackets. Amounts are in ringgit."])
    y, m = map(int, d["to"].split("-"))
    return wb, _file(ent, "Statutory payables check", date.fromordinal(date(y + m // 12, m % 12 + 1, 1).toordinal() - 1).isoformat())
