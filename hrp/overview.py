"""The Overview's cards (slice 1, build plan section 4.4): one function per card, each read on its own route
(GET /api/overview/<card>), so a card that fails never hides the others. Pure reads: nothing here writes anything.

Every card gives, per company in view (all companies in use, or the one the switcher chose), its figures or the
sentence it shows when there is nothing: {entity_id, code, kind ('sql' or 'here'), kind_label, ...}. The page adds the
companies up where they agree (core of pages/overview.js). The figures are counts and totals only: never a person's pay,
an IC or passport number, a bank account number, an address, a tax or EPF number, a leave type, a medical detail, one
person's claim, or an age (the "Never on the Overview" list); a bank account is named by its label alone.

The cards: Needs attention, Checklist, Due and overdue, Funds to request, Paid without approval on file (hidden until
slice 11 builds approvals), Bank, Profit or loss, Customers overdue, Suppliers due, On leave, Dates coming up, Headcount
(the HR cards: "Add your staff to see this" until slices 12 and 13) and Requests waiting ("Nothing waiting" until
slice 11). Cards follow the month on show unless they say "today" (Due and overdue, the customers and suppliers, HR)."""
import calendar
from datetime import date, timedelta

from . import auditread, books, budget, db, finstatements, pages, receivables, rulebook

STALE_DAYS = 3  # SQL's data or a statement that stops more than this many days before today is shown as out of date
DUE_AHEAD = 7  # Due and overdue: what falls due within this many days of today
SUPPLIERS_AHEAD = 14  # Suppliers due: bills due within this many days of today
ACTIVITY_SHOWN = 6
NO_CHECKLIST = "No checklist for this month yet"
NO_STAFF = "Add your staff to see this"
NO_SQL = "Nothing fetched from SQL yet"


def _first(month):
    return f"{month}-01"


def _last(month):
    y, m = map(int, month.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def _set_up(con, eid, month):
    return bool(con.execute("SELECT 1 FROM months WHERE entity_id = ? AND month = ?", (eid, month)).fetchone())


def _sen(x):
    return None if x is None else int(round(x * 100))


def sql_runs_to(con, eid):
    """The last day SQL's data kept for the company runs to (the latest trial balance's as-at day, or the end of the latest
    GL Journal of Transaction or GL Ledger fetched), or None when nothing is fetched yet."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ledger_batches'").fetchone():
        return None
    return con.execute("""SELECT MAX(period_to) FROM ledger_batches WHERE entity_id = ? AND period_to IS NOT NULL
                          AND report IN ('trial_balance', 'journal', 'gl_ledger')""", (eid,)).fetchone()[0]


def _stale(day, today):
    return bool(day) and (today - date.fromisoformat(day)).days > STALE_DAYS


# ---------- Payments ----------

def attention(con, e, month, today):
    """Needs attention for the month: payments past due (the red words: not on the statement imported, past the legal
    deadline), part paid, checklist items whose documents are missing, statement lines left to explain, and payments
    paid but not recorded in SQL (Kept in SQL Account only, else None). A month filed counts nothing; a month before the
    first month tracked counts only the lines to explain (bank reconciliation still covers it)."""
    iso, eid = today.isoformat(), e["id"]
    out = {"filed": bool(db.closed_at(con, eid, month)), "before_tracking": db.before_tracking(e, month),
           "past_due": 0, "part_paid": 0, "docs_missing": 0, "to_explain": 0, "not_in_sql": 0 if e["uses_sql"] else None}
    if out["filed"]:
        return out
    if out["before_tracking"]:
        out["to_explain"] = con.execute(
            """SELECT COUNT(*) FROM statement_lines l JOIN statements s ON s.id = l.statement_id JOIN accounts a ON a.id = s.account_id
               WHERE a.entity_id = ? AND s.month = ? AND l.status = 'unmatched' AND s.reconciled_at IS NULL""", (eid, month)).fetchone()[0]
        return out
    for p in con.execute("SELECT * FROM payments WHERE entity_id = ? AND month = ?", (eid, month)).fetchall():
        status, _ = db.payment_status(con, p, e["uses_sql"])
        if status == "part_paid":
            out["part_paid"] += 1
        if not p["paid_date"]:
            f = db.payment_flag(con, e, p, iso)
            if f and f["tone"] == "bad":
                out["past_due"] += 1
        if e["uses_sql"] and db.not_in_sql(e, p):
            out["not_in_sql"] += 1
    for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ?", (eid, month)).fetchall():
        st = db.task_status(con, e, t)
        if st["missing"] and not st["waiting"]:
            out["docs_missing"] += 1
    out["to_explain"] = sum(a["to_explain"] for a in db.month_statements(con, e, month))
    return out


def checklist(con, e, month, today):
    """The month's checklist: items done of the total (a reminder waiting for its own month isn't counted), when the
    month was filed, and the first month tracked for a month before it."""
    done = total = 0
    for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ?", (e["id"], month)).fetchall():
        st = db.task_status(con, e, t)
        if not st["waiting"]:
            total += 1
            done += bool(st["done"])
    out = {"done": done, "total": total, "filed_at": db.closed_at(con, e["id"], month)}
    if not total:
        out["empty"] = NO_CHECKLIST
        if db.before_tracking(e, month):
            out["tracked_from"] = e["first_month"]
    return out


def due(con, e, month, today):
    """Due and overdue, from today (not the month on show): payments out not paid yet that are overdue, and those that
    fall due in the next 7 days, each counted with what is still to pay per currency (as the Budget page has it as at
    today). Every open month counts (not filed, not before tracking). link_month: the month of the oldest of them, which
    the card's link opens (the register's Not paid tab until To pay comes with slice 11). A payment of a pay type (a salary, a
    director's allowance: rulebook.pay_type) is counted but never added to the amounts (pay_n), so no amount shown can be one
    person's pay."""
    iso, ahead = today.isoformat(), (today + timedelta(days=DUE_AHEAD)).isoformat()
    R = rulebook.get(con)
    over = {"n": 0, "sums": {}, "pay_n": 0}
    soon = {"n": 0, "sums": {}, "pay_n": 0}
    first = None
    for p in con.execute("""SELECT * FROM payments WHERE entity_id = ? AND direction = 'out' AND paid_date IS NULL
                            AND due_date <= ? ORDER BY due_date, id""", (e["id"], ahead)).fetchall():
        if db.before_tracking(e, p["month"]) or db.closed_at(con, e["id"], p["month"]):
            continue
        box = over if p["due_date"] < iso else soon
        box["n"] += 1
        first = first or p["month"]
        if R.pay_type(p["category"], p["month"], e["id"]):
            box["pay_n"] += 1
            continue
        left = budget.payment_left(con, p, iso)
        if left is not None:
            box["sums"][p["currency"]] = round(box["sums"].get(p["currency"], 0) + left, 2)
    return {"overdue": over, "soon": soon, "link_month": first, "days": DUE_AHEAD}


def funds(con, e, month, today):
    """Funds to request for the month: what is still to pay in ringgit less the bank balance kept with the stored budget,
    on the budget's balance date (slice 8's rules: never worked out from a blank balance). bank: the label of the
    company's own account the balance is for (budget.bank_account), never its number. When what is still to pay is pay alone
    (only pay-type payments left: a salary, a director's allowance), still_to_pay and the balance are not given, as either
    with the funds figure would show that pay (pay_only)."""
    eid = e["id"]
    if not _set_up(con, eid, month):
        return {"empty": NO_CHECKLIST, "set_up": False}
    hdr = budget.header(con, eid, month)
    as_at = budget.default_as_at(hdr)
    totals = budget.view(con, eid, month, as_at)["totals"] if hdr else budget.worked_out(con, eid, month, as_at)[2]
    bal = budget.balance_for(hdr, as_at)
    acct = budget.bank_account(con, eid)["account"]
    out = {"set_up": True, "stored": bool(hdr), "as_at": as_at, "still_to_pay": round(totals.get("MYR") or 0, 2),
           "balance": bal, "funds": budget.funds_to_request(totals, bal), "bank": acct["label"] if acct else None}
    if bal is None:
        out["empty"] = "Enter the bank balance to see funds to request"
    if _pay_only(con, e, month, as_at, bool(hdr)):
        out.update({"still_to_pay": None, "balance": None, "pay_only": True})
    return out


def _pay_only(con, e, month, as_at, stored):
    """True when what is still to pay in ringgit for the month is made of pay-type payments alone (rulebook.pay_type)."""
    R = rulebook.get(con)
    pay = other = 0
    for p in con.execute("SELECT * FROM payments WHERE entity_id = ? AND month = ? AND direction = 'out' AND currency = 'MYR'",
                         (e["id"], month)).fetchall():
        if (budget.payment_left(con, p, as_at) or 0) > 0:
            if R.pay_type(p["category"], month, e["id"]):
                pay += 1
            else:
                other += 1
    if stored:  # a budget line of its own (no payment behind it) is never pay
        other += con.execute("""SELECT COUNT(*) FROM budget_lines WHERE entity_id = ? AND month = ? AND payment_id IS NULL
                                AND currency = 'MYR' AND COALESCE(amount, 0) > 0""", (e["id"], month)).fetchone()[0]
    return bool(pay) and not other


def unapproved(con, e, month, today):
    """Paid without approval on file: hidden until approvals are built (slice 11)."""
    return {"hidden": True}


# ---------- Accounting ----------

def bank(con, e, month, today):
    """The month's statements: each account's balance at its latest statement line, with that line's date, and the
    month's money in and out per currency. runs_to: the day the statements reach (their statement date, else their
    last line); stale when that is before the month's end and more than a few days before today. Accounts are named by
    their label alone."""
    accts, totals, runs = [], {}, []
    for s in con.execute("""SELECT s.id, s.statement_date, s.closing, a.label, a.currency FROM statements s
                            JOIN accounts a ON a.id = s.account_id WHERE a.entity_id = ? AND s.month = ? ORDER BY a.id""",
                         (e["id"], month)).fetchall():
        last = con.execute("SELECT txn_date, balance FROM statement_lines WHERE statement_id = ? ORDER BY txn_date DESC, line_no DESC LIMIT 1",
                           (s["id"],)).fetchone()
        moved = con.execute("""SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0),
                               COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) FROM statement_lines WHERE statement_id = ?""",
                            (s["id"],)).fetchone()
        cur = s["currency"] or "MYR"
        bal = last["balance"] if last else s["closing"]
        day = last["txn_date"] if last else s["statement_date"]
        accts.append({"label": s["label"], "currency": cur, "balance": bal, "date": day})
        t = totals.setdefault(cur, {"balance": 0, "in": 0, "out": 0})
        t["balance"] = round(t["balance"] + (bal or 0), 2)
        t["in"] = round(t["in"] + moved[0], 2)
        t["out"] = round(t["out"] + moved[1], 2)
        runs.append(max(x for x in (s["statement_date"], day) if x) if (s["statement_date"] or day) else None)
    if not accts:
        return {"empty": f"No statement imported for {db.month_label(month)}"}
    runs_to = min((r for r in runs if r), default=None)
    return {"accounts": accts, "totals": totals, "runs_to": runs_to,
            "stale": bool(runs_to) and runs_to < _last(month) and _stale(runs_to, today)}


def _books_state(con, e, today):
    """(None, runs_to) when the company's books can be read, else (the empty sentence, None)."""
    if not e["uses_sql"]:
        return "No books yet", None
    to = sql_runs_to(con, e["id"])
    return (NO_SQL, None) if not to else (None, to)


def pl(con, e, month, today):
    """Profit or loss for the month and the financial year to its end, from SQL's books (finstatements), up to the day
    SQL's data runs to. month_sen None when SQL's data stops before the month starts. Profit above 0."""
    empty, to = _books_state(con, e, today)
    if empty:
        return {"empty": empty}
    eid, first, last = e["id"], _first(month), _last(month)
    upto = min(last, to)
    fig = lambda a, b: finstatements.profit_and_loss(con, eid, a, b)["figures"]["after_tax"][0]  # noqa: E731
    month_sen = fig(first, upto) if upto >= first else None
    fy = books.year_start(con, eid, upto)
    return {"month_sen": month_sen, "ytd_sen": fig(fy, upto), "fy_start": fy, "upto": upto, "sql_to": to,
            "stale": _stale(to, today) and to < last}


def customers(con, e, month, today):
    """Customers overdue, as at today: balances older than 30 days inside the tracked period, and apart from them the
    balances brought forward from before tracking (receivables.customers_overdue)."""
    empty, to = _books_state(con, e, today)
    if empty == NO_SQL:
        return {"empty": empty}
    r = receivables.customers_overdue(con, e["id"], today.isoformat())
    out = {k: r[k] for k in ("overdue_sen", "overdue_count", "before_tracking_sen", "before_tracking_count", "count")}
    out.update({"sql_to": to, "stale": _stale(to, today)})
    if not r["count"]:
        out["empty"] = "No balances"
    return out


def suppliers(con, e, month, today):
    """Suppliers due, as at today: bills overdue and bills due in the next 14 days (receivables.suppliers_due), with the
    balances brought forward from before tracking apart."""
    empty, to = _books_state(con, e, today)
    if empty == NO_SQL:
        return {"empty": empty}
    r = receivables.suppliers_due(con, e["id"], today.isoformat(), SUPPLIERS_AHEAD)
    out = {k: r[k] for k in ("overdue_sen", "overdue_count", "due_sen", "due_count", "before_tracking_sen", "before_tracking_count", "count")}
    out.update({"sql_to": to, "stale": _stale(to, today), "days": SUPPLIERS_AHEAD})
    if not r["count"]:
        out["empty"] = "No balances"
    return out


# ---------- HR (slices 11 to 14 fill these) ----------

def _no_staff(con, e, month, today):
    return {"empty": NO_STAFF}


def requests(con, e, month, today):
    return {"empty": "Nothing waiting"}


CARDS = {"attention": attention, "checklist": checklist, "due": due, "funds": funds, "unapproved": unapproved,
         "bank": bank, "pl": pl, "customers": customers, "suppliers": suppliers,
         "leave": _no_staff, "dates": _no_staff, "headcount": _no_staff, "requests": requests}


def companies(con, entity_id=None):
    return [e for e in con.execute("SELECT * FROM entities WHERE active = 1 ORDER BY sort, id").fetchall()
            if entity_id in (None, e["id"])]


def card(con, name, month, entity_id=None, today=None):
    """One card for the companies in view: {card, month, label, today, companies: [{entity_id, code, kind, kind_label,
    ...the card's own figures}]}. Raises KeyError for a card that doesn't exist."""
    fn = CARDS[name]
    today = today or date.today()
    out = []
    for e in companies(con, entity_id):
        kind = pages.kind_of(e["uses_sql"])
        out.append({"entity_id": e["id"], "code": e["code"], "kind": kind, "kind_label": pages.KINDS[kind], **fn(con, e, month, today)})
    return {"card": name, "month": month, "label": db.month_label(month), "today": today.isoformat(), "companies": out}


# ---------- the top part: the rollover banner and Recent activity ----------

def rollover(con, month, entity_id=None):
    """The month after the one on show, and the companies in view that have it set up already (the rollover banner)."""
    nxt = db.shift_month(month, 1)
    return {"month": month, "next_month": nxt, "next_label": db.month_label(nxt),
            "set_up": [e["id"] for e in companies(con, entity_id) if _set_up(con, e["id"], nxt)]}


# What a change did, in words with no figure or name in them: by the route that made it, else by what it changed.
ROUTE_WORDS = {"/api/statements": "Imported a bank statement", "/api/sql/apply": "Imported from SQL",
               "/api/sql/preview": None, "/api/backup": "Made a backup", "/api/months/open": "Set up a month",
               "/api/months/close": "Marked a month as filed, or reopened it", "/api/audit-pack": "Built an audit pack",
               "/api/upload": "Uploaded a document", "/api/recon/sign-off": "Signed off a bank reconciliation",
               "/api/recon/reopen": "Reopened a bank reconciliation", "/api/payments": "Added a payment",
               "/api/payroll-check": "Checked a payroll workbook", "/api/budget/setup": "Set up a budget",
               "/api/setup/import": "Imported a setup file", "/api/auditor-export": "Built an auditor package"}


def _words(tx):
    path = (tx["action"] or "").split(" ", 1)[-1]
    if path in ROUTE_WORDS:
        return ROUTE_WORDS[path]
    parts = []
    for tbl, ops in (tx["counts"] or {}).items():
        if tbl in ("read", "audit"):
            continue
        for op, n in ops.items():
            if op in auditread.OPS and op not in ("baseline", "event"):
                parts.append(f"{auditread.OPS[op].lower()} {n} {auditread._label(tbl, n).lower()}")
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] if text else None


def activity(con, entity_id=None):
    """Recent activity from the audit trail, newest first: what was done in words with no figure or name in it (the route
    it came from, else what it changed: Changed 2 payments), who, which company and when. Opening a file and the trail's
    own checks are left out."""
    out = []
    before = None
    for _ in range(5):  # a few pages of the trail at most, for the newest few changes
        f = {"entity_id": entity_id, "before_id": before}
        got = auditread.entries(con, f, limit=50)
        for tx in got["entries"]:
            if tx["source"] in ("migration", "seed"):
                continue
            words = _words(tx)
            if words:
                out.append({"id": tx["id"], "at": tx["at"], "who": tx["actor"], "source": tx["source_label"],
                            "company": tx["company"], "text": words})
            if len(out) >= ACTIVITY_SHOWN:
                return out
        if not got["more"] or not got["entries"]:
            break
        before = got["entries"][-1]["id"]
    return out
