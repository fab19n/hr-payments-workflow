"""The SQL books checklist item (rules.TASK_BOOKS, update 30): whether SQL Account's books for a payroll month agree with
the mirror kept here, worked out from the records each time it is asked (nothing is stored, so it is never a tick no one
can explain). Read only.

A month is shown done when all four hold, checked in this order, and the first that fails is said in one sentence with
what to fetch or fix:
  1. the GL Journals of Transaction fetched cover the whole month (one read, or several whose periods run on from each
     other with no day missing);
  2. no listing entry dated in the month is missing from SQL's journal, and no document of the month in the journal
     lacks a listing (ledger.orphans, kept to the month);
  3. every current document dated in the month balances and agrees with its listing (ledger.doc_checks);
  4. SQL's trial balance agrees with the books here (books.check_against_sql), taken from the stored trial balance of
     SQL's whose as-at date is the nearest on or after the month's last day (the latest read of that date), from its own
     From date. A trial balance fetched later for a later day never changes the answer for a month that has its own, so
     a month shown done stays done when the next month's reports are fetched. When the nearest is as at a later day, the
     journals fetched must reach that day too, or the books here would be compared with SQL's over days not fetched.
A company not kept in SQL Account has nothing to check: the item can only be ticked by hand there."""
import calendar
from datetime import date

from . import books, db, ledger


def _span(month):
    y, m = map(int, month.split("-"))
    return f"{month}-01", date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def _nos(rows, key="doc_no", most=3):
    nos = [r[key] for r in rows]
    return ", ".join(nos[:most]) + (f" and {len(nos) - most} more" if len(nos) > most else "")


def _s(n, many="s", one=""):
    return one if n == 1 else many


def nearest_tb(con, eid, last):
    """The stored trial balance of SQL's the check reads for a month ending on last: the nearest as-at date on or after
    it, the latest read of that date; None when there is none."""
    return con.execute("""SELECT id, period_from, period_to, file_name FROM ledger_batches WHERE entity_id = ?
                          AND report = 'trial_balance' AND period_to IS NOT NULL AND period_to >= ?
                          ORDER BY period_to ASC, id DESC LIMIT 1""", (eid, last)).fetchone()


def journal_spans(con, eid):
    """The days the GL Journals of Transaction fetched cover, as [(from, to)] with no gap inside each: reads whose
    periods overlap or run on from each other (the next day) are joined into one."""
    spans = []
    for r in con.execute("""SELECT period_from, period_to FROM ledger_batches WHERE entity_id = ? AND report = 'journal'
                            AND period_from IS NOT NULL AND period_to IS NOT NULL ORDER BY period_from, period_to""", (eid,)):
        a, b = r["period_from"], r["period_to"]
        if spans and a <= books._next(spans[-1][1]):
            if b > spans[-1][1]:
                spans[-1][1] = b
        else:
            spans.append([a, b])
    return [tuple(x) for x in spans]


def _covers(spans, a, b):
    return any(f <= a and t >= b for f, t in spans)


def month_check(con, ent, month):
    """(ok, why) for the SQL books item of a company's month, as db.task_status takes it: ok True with why starting
    'Done: ', False with the one sentence saying what fails and what to fetch or fix, or None (a company not kept in
    SQL Account: nothing to check)."""
    if not ent["uses_sql"]:
        return None, "This company's books aren't kept in SQL Account, so nothing here can show this done: tick it by hand."
    if db.before_tracking(ent, month):
        return None, None  # a month before the first month tracked is never asked anything
    first, last = _span(month)
    label, upto = db.month_label(month), db.day_label(last)
    if not ledger.ready(con):
        return False, f"Fetch SQL's GL Journal of Transaction and Trial Balance up to at least {upto}."
    eid = ent["id"]
    spans = journal_spans(con, eid)
    journal = _covers(spans, first, last)
    tb = nearest_tb(con, eid, last)
    if not journal:
        if not tb:
            return False, f"Fetch SQL's GL Journal of Transaction and Trial Balance up to at least {upto}."
        return False, (f"Fetch SQL's GL Journal of Transaction for the whole of {label} (from {db.short_day(first)} to {upto}): "
                       "no journal fetched covers the whole month.")
    o = ledger.orphans(con, eid)
    missing = [x for x in o["not_in_journal"] if first <= x["doc_date"] <= last]
    if missing:
        n = len(missing)
        return False, (f"{n} document{_s(n)} of {label} in SQL's listings {'is' if n == 1 else 'are'} missing from SQL's GL "
                       f"Journal of Transaction ({_nos(missing)}): fetch the journal for {label} again, or check "
                       f"{'it' if n == 1 else 'them'} in SQL.")
    unlisted = [x for x in o["no_listing"] if first <= x["doc_date"] <= last]
    if unlisted:
        n = len(unlisted)
        return False, (f"{n} document{_s(n)} of {label} in SQL's GL Journal of Transaction {'has' if n == 1 else 'have'} no "
                       f"listing ({_nos(unlisted)}): fetch or paste SQL's listing for {label}.")
    docs = con.execute("""SELECT doc_no FROM ledger_docs WHERE entity_id = ? AND origin = 'sql' AND state = 'current'
                          AND doc_date >= ? AND doc_date <= ? ORDER BY doc_date, doc_key""", (eid, first, last)).fetchall()
    checks = ledger.doc_checks(con, eid, [d["doc_no"] for d in docs])
    bad = sorted((c for c in checks.values() if c["state"] == "current" and (not c["balanced"] or c["total_ok"] is not True)),
                 key=lambda c: c["doc_no"])
    if bad:
        n, c = len(bad), bad[0]
        words = next((w for w in c["warnings"] if w.startswith(("Its lines", "The lines", "Can't tell", "The customer",
                                                                    "The debtor", "The supplier"))), None) \
            or next((w for w in c["warnings"] if "chart of accounts" not in w), "its lines don't agree with its listing.")
        more = f" ({n - 1} more document{_s(n - 1)} of {label} too)" if n > 1 else ""
        return False, (f"{c['doc_no']} doesn't balance or agree with its listing{more}: {words} Open it on the SQL page or "
                       "Accounting › Books to see its lines.")
    if not tb:
        return False, f"Fetch SQL's Trial Balance up to at least {upto}."
    if not _covers(spans, first, tb["period_to"]):
        at = db.day_label(tb["period_to"])
        return False, (f"The nearest trial balance of SQL's kept is as at {at}, but the journals fetched stop before then: fetch "
                       f"SQL's Trial Balance as at {upto}, or its GL Journal of Transaction up to {at}.")
    res = books.check_against_sql(con, eid, tb["period_from"], tb["period_to"])
    if res["outcome"] == "ok":
        return True, (f"Done: SQL's journal covers {label}, its documents agree with the listings and SQL's trial balance as "
                      f"at {db.day_label(tb['period_to'])} agrees with the books here")
    if res["outcome"] == "warn":
        return False, f"{res['text']} See Accounting › Books › Trial balance, then fetch again what differs."
    return False, res["text"]
