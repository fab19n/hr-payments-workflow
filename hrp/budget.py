"""A company's stored budget for a payroll month (payments.month), kept as set up and then edited by hand: its lines,
the payment each is linked to, and what was paid against them. A budget covers the payments of its payroll month, which
includes the bills and statutory payments paid early in the month after. Changing a line never changes a payment."""
import calendar
import math
import re
from datetime import date

from . import db

MATCHED = 0.01  # paid within this of the budget is 'Matched'
_NAMES = {n: i for i in range(1, 13) for n in (calendar.month_abbr[i], calendar.month_name[i])}
_MONTH_TEXT = re.compile(r"\b(" + "|".join(sorted(_NAMES, key=len, reverse=True)) + r")\b(?: (\d{4}))?")


def header(con, eid, month):
    return con.execute("SELECT * FROM budgets WHERE entity_id = ? AND month = ?", (eid, month)).fetchone()


def default_as_at(hdr):
    """The date of the bank balance kept with the budget, else today."""
    return hdr["as_at"] if hdr and hdr["as_at"] else date.today().isoformat()


def lines(con, eid, month):
    return con.execute("SELECT * FROM budget_lines WHERE entity_id = ? AND month = ? ORDER BY sort, id", (eid, month)).fetchall()


def _out_payments(con, eid, month):
    return con.execute(
        """SELECT p.*, py.bank_details FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.month = ? AND p.direction = 'out' ORDER BY p.due_date, p.id""", (eid, month)).fetchall()


def next_month_text(text):
    """A description for the month after: 'Oct 2026' becomes 'Nov 2026', 'October' becomes 'November'."""
    def swap(m):
        n = _NAMES[m[1]]
        year = int(m[2]) if m[2] else None
        if n == 12:
            n, year = 1, year + 1 if year else None
        else:
            n += 1
        name = calendar.month_name[n] if len(m[1]) > 3 else calendar.month_abbr[n]
        return f"{name} {year}" if year else name
    return _MONTH_TEXT.sub(swap, text or "")


# ---------- what was paid against a line ----------

def actual(con, pay):
    """What was paid on a linked payment: its bank lines' total, else its amount once it is paid, else None."""
    if not pay:
        return None
    found = db.linked_total(con, pay)
    if found is not None:
        return found
    return pay["amount"] if pay["paid_date"] else None


def status(budget, paid, currency):
    """How what was paid compares with the line's budget: {code, text, tone, diff}."""
    if paid is None:
        return {"code": "not_paid", "text": "Not paid yet", "tone": "grey", "diff": None}
    if budget is None:
        return {"code": "no_budget", "text": "No budget set", "tone": "grey", "diff": None}
    diff = round(paid - budget, 2)
    if abs(diff) <= MATCHED:
        return {"code": "matched", "text": "Matched", "tone": "ok", "diff": diff}
    if diff < 0:
        return {"code": "under", "text": f"Under by {db.money(-diff, currency)}", "tone": "warn", "diff": diff}
    return {"code": "over", "text": f"Over by {db.money(diff, currency)}", "tone": "bad", "diff": diff}


def line_left(con, line, pay, as_at):
    """What of a line is still to pay from a bank balance taken on as_at: nothing once its payment was paid by then (with
    bank lines linked, those dated by then are taken off the budget instead), else the budget. None for a blank amount."""
    if line["amount"] is None:
        return None
    if not pay:
        return line["amount"]
    if db.linked_total(con, pay) is None:
        return 0 if pay["paid_date"] and pay["paid_date"] <= as_at else line["amount"]
    by_then = sum(-r[0] for r in con.execute(
        "SELECT amount FROM statement_lines WHERE payment_id = ? AND txn_date <= ?", (pay["id"], as_at)))
    left = round(line["amount"] - by_then, 2)
    return left if left > MATCHED else 0


def payment_left(con, pay, as_at):
    """What of a payment is still to pay as at a date: by its budget line when the month's stored budget has one for it,
    else by the payment itself (db.still_to_pay)."""
    line = con.execute("SELECT * FROM budget_lines WHERE payment_id = ?", (pay["id"],)).fetchone()
    return line_left(con, line, pay, as_at) if line else db.still_to_pay(con, pay, as_at)


def _add(totals, cur, n):
    totals[cur] = round(totals.get(cur, 0) + (n or 0), 2)


def view(con, eid, month, as_at):
    """The stored budget as at a date: each line with what was paid and how that compares, what is still to pay from the
    balance and what is already out of it (per currency), the month's payments for the link lists, and those not on any
    line."""
    pays = {p["id"]: p for p in _out_payments(con, eid, month)}
    out, to_pay, in_balance, sums = [], {}, {}, {}
    for ln in lines(con, eid, month):
        pay = pays.get(ln["payment_id"]) or (con.execute("SELECT * FROM payments WHERE id = ?", (ln["payment_id"],)).fetchone()
                                              if ln["payment_id"] else None)
        paid = actual(con, pay)
        st = status(ln["amount"], paid, ln["currency"])
        if paid is None and pay and pay["paid_date"]:
            st = {"code": "paid_no_amount", "text": "Paid, no amount", "tone": "grey", "diff": None}
        left = line_left(con, ln, pay, as_at)
        done = left == 0 and bool(pay and pay["paid_date"])
        cur = ln["currency"]
        s = sums.setdefault(cur, {"budget": 0, "paid": 0, "diff": 0})
        _add(s, "budget", ln["amount"])
        if paid is not None:
            _add(s, "paid", paid)
            _add(s, "diff", st["diff"])
        _add(in_balance if done else to_pay, cur, ln["amount"] if done else left)
        out.append({**{k: ln[k] for k in ("id", "description", "details", "amount", "currency", "payment_id")},
                    "paid": paid, "status": st, "to_pay": left, "in_balance": done,
                    "due_date": pay["due_date"] if pay else None, "paid_date": pay["paid_date"] if pay else None})
    linked = {ln["payment_id"] for ln in out if ln["payment_id"]}
    row = lambda p: {k: p[k] for k in ("id", "description", "amount", "currency", "due_date", "paid_date")}
    return {"lines": out, "totals": to_pay, "in_balance": in_balance, "sums": sums,
            "payments": [{**row(p), "line_id": next((x["id"] for x in out if x["payment_id"] == p["id"]), None)} for p in pays.values()],
            "not_in_budget": [row(p) for p in pays.values() if p["id"] not in linked]}


# ---------- setting up, and editing ----------

def _new_line(con, eid, month, sort, description, details, amount, currency, pay=None, payee_id=None, category=None):
    cur = con.execute(
        """INSERT INTO budget_lines (entity_id, month, description, details, amount, currency, payment_id, payee_id, category, sort)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (eid, month, description, details, amount, currency, pay["id"] if pay else None,
         pay["payee_id"] if pay else payee_id, pay["category"] if pay else category, sort))
    return cur.lastrowid


def _from_payment(con, eid, month, sort, p):
    return _new_line(con, eid, month, sort, p["description"], p["bank_details"], db.budgeted_at(con, p, db.linked_total(con, p)),
                     p["currency"], p)


def _match(old, free, want):
    """Pairs lines with payments of the same currency: same payee and same description first, then the same payee, then
    the same description (want(line) is the description to look for). Returns {line id: payment}."""
    match = {}
    same = lambda p, ln: p["currency"] == ln["currency"]
    tests = (lambda p, ln: ln["payee_id"] and p["payee_id"] == ln["payee_id"] and p["description"].strip().lower() == want(ln),
             lambda p, ln: ln["payee_id"] and p["payee_id"] == ln["payee_id"],
             lambda p, ln: p["description"].strip().lower() == want(ln))
    for test in tests:
        for ln in old:
            if ln["id"] not in match:
                p = next((p for p in free if same(p, ln) and test(p, ln)), None)
                if p:
                    match[ln["id"]] = p
                    free.remove(p)
    return match


def _copy(con, eid, month, prev):
    """The previous month's lines, with their amounts, details and order, each linked to this month's payment of the
    same payee (the one with the same description once the month names move on, if the payee has several), else to the
    one whose description is the same then; no match stays unlinked."""
    old = lines(con, eid, prev)
    match = _match(old, _out_payments(con, eid, month), lambda ln: next_month_text(ln["description"]).strip().lower())
    for i, ln in enumerate(old):
        _new_line(con, eid, month, i, next_month_text(ln["description"]), ln["details"], ln["amount"], ln["currency"],
                  match.get(ln["id"]), ln["payee_id"], ln["category"])
    return len(old)


def link_new(con, eid, month):
    """Links the month's lines that have no payment to payments added since (the recurring ones when the month is opened),
    as set up does. Does nothing without a stored budget."""
    if not header(con, eid, month):
        return
    free = [p for p in _out_payments(con, eid, month)
            if not con.execute("SELECT 1 FROM budget_lines WHERE payment_id = ?", (p["id"],)).fetchone()]
    open_ = [ln for ln in lines(con, eid, month) if not ln["payment_id"]]
    for lid, p in _match(open_, free, lambda ln: ln["description"].strip().lower()).items():
        con.execute("UPDATE budget_lines SET payment_id = ?, payee_id = ?, category = ? WHERE id = ?",
                    (p["id"], p["payee_id"], p["category"], lid))


def set_up(con, eid, month):
    """Stores the month's budget: a copy of the month before's when that has one, else a line for each payment out of
    the month. Returns how many lines."""
    if header(con, eid, month):
        raise ValueError("This month's budget is already set up.")
    con.execute("INSERT INTO budgets (entity_id, month, set_up_at) VALUES (?, ?, ?)", (eid, month, db.now()))
    prev = db.shift_month(month, -1)
    if header(con, eid, prev):
        n, how = _copy(con, eid, month, prev), f"copied from {db.month_label(prev)}"
    else:
        for i, p in enumerate(_out_payments(con, eid, month)):
            _from_payment(con, eid, month, i, p)
        n, how = len(lines(con, eid, month)), "made from its payments"
    db.log(con, f"Budget set up for {db.month_label(month)}: {n} lines {how}")
    return n


def _amount(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ValueError("That amount isn't a number.")
    if not math.isfinite(n) or n < 0:
        raise ValueError("Enter an amount of 0 or more.")
    return round(n, 2)


def _linkable(con, ln, pid):
    p = con.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    if not p or p["entity_id"] != ln["entity_id"] or p["month"] != ln["month"] or p["direction"] != "out":
        raise ValueError("Choose one of this month's payments out.")
    if p["currency"] != ln["currency"]:
        raise ValueError(f"That payment is in {p['currency']}, this line in {ln['currency']}.")
    other = con.execute("SELECT 1 FROM budget_lines WHERE payment_id = ? AND id != ?", (pid, ln["id"])).fetchone()
    if other:
        raise ValueError("That payment is already on another line.")
    return p


def add_line(con, eid, month, fields):
    """A new line at the end: blank, or made from one of the month's payments (payment_id) not on a line yet."""
    if not header(con, eid, month):
        raise ValueError("Set up this month's budget first.")
    top = con.execute("SELECT COALESCE(MAX(sort), -1) FROM budget_lines WHERE entity_id = ? AND month = ?", (eid, month)).fetchone()[0]
    if fields.get("payment_id"):
        p = con.execute("SELECT p.*, py.bank_details FROM payments p LEFT JOIN payees py ON py.id = p.payee_id WHERE p.id = ?",
                        (fields["payment_id"],)).fetchone()
        if not p or p["entity_id"] != eid or p["month"] != month or p["direction"] != "out":
            raise ValueError("Choose one of this month's payments out.")
        if con.execute("SELECT 1 FROM budget_lines WHERE payment_id = ?", (p["id"],)).fetchone():
            raise ValueError("That payment is already on a line.")
        lid = _from_payment(con, eid, month, top + 1, p)
    else:
        currency = fields.get("currency") or "MYR"
        if currency not in {r[0] for r in con.execute("SELECT currency FROM accounts WHERE entity_id = ?", (eid,))} | {"MYR"}:
            raise ValueError("This company has no account in that currency.")
        lid = _new_line(con, eid, month, top + 1, (fields.get("description") or "").strip(), None, _amount(fields.get("amount")), currency)
    db.log(con, f"Budget {db.month_label(month)}: added a line")
    return lid


def update_line(con, lid, fields):
    ln = con.execute("SELECT * FROM budget_lines WHERE id = ?", (lid,)).fetchone()
    if not ln:
        raise LookupError("This line has already been removed.")
    sets = {}
    if "description" in fields:
        sets["description"] = (fields["description"] or "").strip()
    if "details" in fields:
        sets["details"] = (fields["details"] or "").strip() or None
    if "amount" in fields:
        sets["amount"] = _amount(fields["amount"])
    if "payment_id" in fields:
        pid = fields["payment_id"] or None
        sets["payment_id"] = pid
        if pid:
            p = _linkable(con, ln, pid)
            sets.update(payee_id=p["payee_id"], category=p["category"])
    if sets:
        con.execute(f"UPDATE budget_lines SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), lid))
        db.log(con, f"Budget {db.month_label(ln['month'])}: changed {ln['description'] or 'a line'} "
                    f"({', '.join(k.replace('_id', '') for k in sets)})")


def delete_lines(con, ids):
    """Removes lines from the budget (their payments are not touched). Returns how many were removed."""
    n = 0
    for lid in ids:
        ln = con.execute("SELECT * FROM budget_lines WHERE id = ?", (lid,)).fetchone()
        if ln:
            con.execute("DELETE FROM budget_lines WHERE id = ?", (lid,))
            n += 1
    if n:
        db.log(con, f"Budget: removed {n} line{'s' if n > 1 else ''}")
    return n


def update_header(con, eid, month, fields):
    if not header(con, eid, month):
        raise ValueError("Set up this month's budget first.")
    sets = {}
    if "balance" in fields:
        sets["balance"] = None if fields["balance"] in (None, "") else _balance(fields["balance"])
    if "as_at" in fields:
        sets["as_at"] = fields["as_at"] or None
    if sets:
        con.execute(f"UPDATE budgets SET {', '.join(k + ' = ?' for k in sets)} WHERE entity_id = ? AND month = ?",
                    (*sets.values(), eid, month))


def _balance(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise ValueError("That balance isn't a number.")
    if not math.isfinite(n):
        raise ValueError("That balance isn't a number.")
    return round(n, 2)
