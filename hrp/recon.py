"""Bank reconciliation: a bank statement against the company's books, month by month.

The books are what the company recorded for the account: for a company kept in SQL Account, the cash book vouchers
(OR in, PV out) pasted on the SQL import page; for one that isn't, the payments recorded in this app for the account.
Book closing = the book opening typed once for the account's first month, plus the movements of each month after it
(a month's closing is the next month's opening). Whatever the statement shows that the books don't (a bank charge), and
whatever the books show that the statement doesn't (a cheque not cleared yet), explains a difference between the two.

The functions that only read are year_view, month_summary, review and not_reconciled. The others change records and are
called with the request's connection; they log what they do in plain words and leave the commit to the caller.
Nothing here posts anything to SQL Account.
"""
import json
import math
import re
import sqlite3
import weakref
from datetime import date, timedelta

from . import db, statements

TOL = 0.005  # a difference this small is no difference


class ReconError(ValueError):
    """What stopped an action, in words for the person using the app."""


def _r(n):
    return round(float(n), 2)


def _money(n, cur="MYR"):
    return db.money(n, cur)


def _acct(con, account_id):
    return con.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()


def _ent(con, entity_id):
    return con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()


def _stmt(con, account_id, month):
    return con.execute("SELECT * FROM statements WHERE account_id = ? AND month = ?", (account_id, month)).fetchone()


def _name(a, month):
    return f"{a['label']} {db.month_label(month)}"


# ---------- the books ----------

def _primary(con, ent):
    """The account the SQL cash book listing is for: the company's cash book account (Setup › Bank accounts)."""
    from . import masters
    r = masters.first_active_account(con, ent["id"])
    return r["id"] if r else None


def cash_book_account(con, entity_id):
    """The company's cash book account (its row), the account SQL's cash book listing and journals are counted for; or None."""
    acct_id = _primary(con, {"id": entity_id})
    return _acct(con, acct_id) if acct_id else None


def bank_gl_code(con, acct):
    """The account's code in SQL Account's chart of accounts, which a journal line names when it moves the bank: the GL
    code set for the account in Setup; else the code of the company's chart entry named as the payment method most of
    its cash vouchers carry (a voucher keeps the bank's name as its payment method); else None."""
    code = (acct["gl_code"] or "").strip()
    if code:
        return code
    own = (acct["sql_payment_method"] or "").strip() if "sql_payment_method" in acct.keys() else ""
    if own:  # the account's own name for itself on vouchers, as set in Setup
        hit = con.execute("SELECT code FROM gl_accounts WHERE entity_id = ? AND LOWER(TRIM(name)) = LOWER(?) ORDER BY active DESC, code LIMIT 1",
                          (acct["entity_id"], own)).fetchone()
        if hit:
            return hit["code"]
    top = con.execute("""SELECT payment_method FROM sql_entries WHERE entity_id = ? AND COALESCE(kind, 'payment') = 'payment'
                         AND direction IN ('in', 'out') AND TRIM(COALESCE(payment_method, '')) <> ''
                         GROUP BY payment_method ORDER BY COUNT(*) DESC, payment_method LIMIT 1""", (acct["entity_id"],)).fetchone()
    if not top:
        return None
    hit = con.execute("SELECT code FROM gl_accounts WHERE entity_id = ? AND LOWER(TRIM(name)) = LOWER(TRIM(?)) ORDER BY active DESC, code LIMIT 1",
                      (acct["entity_id"], top["payment_method"])).fetchone()
    return hit["code"] if hit else None


def journal_moves(con, entity_id, docs, code):
    """What each journal moves on the bank account whose GL code is given: {UPPER(doc no.): net amount, money in above
    0}, for docs = [(doc no., SQL document key or None)]. A journal SQL's GL Journal of Transaction has given (update 26
    on) is counted from the current version of its account lines there, whatever else was pasted, so one deleted in
    SQL moves nothing; any other is counted from its lines pasted from SQL's grid, by document key. A journal with no
    lines, no line on that code or a net of nothing isn't in it."""
    from . import ledger
    docs = [(str(n).strip().upper(), None if k in (None, "") else str(k)) for n, k in docs if n not in (None, "")]
    if not code or not docs:
        return {}
    out, rest = {}, docs
    if ledger.ready(con):
        nets = ledger.bank_nets(con, entity_id, [n for n, _ in docs], code)
        out = {n: _r(net / 100) for n, net in nets.items()}
        rest = [(n, k) for n, k in docs if n not in nets]
    keys = sorted({k for _, k in rest if k})
    if keys and con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sql_journal_lines'").fetchone():
        got = {r["dockey"]: r["net"] for r in con.execute(
            f"""SELECT dockey, ROUND(SUM(dr - cr), 2) AS net FROM sql_journal_lines WHERE entity_id = ? AND UPPER(TRIM(code)) = ?
                AND dockey IN ({','.join('?' * len(keys))}) GROUP BY dockey""", (entity_id, code.strip().upper(), *keys))}
        for n, k in rest:
            if k in got:
                out[n] = got[k]
    return {n: v for n, v in out.items() if abs(v) >= TOL}


def journal_move(con, entity_id, doc_no, dockey=None):
    """What one journal moves on the company's cash book account (see journal_moves), or None when it moves nothing there."""
    acct = cash_book_account(con, entity_id)
    return journal_moves(con, entity_id, [(doc_no, dockey)], bank_gl_code(con, acct) if acct else None).get(str(doc_no).strip().upper())


def _rule(ent, month, rule=None):
    """How the cash book counts SQL's receipts and payments in a month: 'lines' (what each document posted to the bank
    account, from its lines in SQL's GL Journal of Transaction) from the company's first month tracked; 'listing' (the
    listing amount, as before) for a month before tracking, which keeps its state. rule: one asked for."""
    if rule in ("lines", "listing"):
        return rule
    return "listing" if db.before_tracking(ent, month) else "lines"


def movements(con, ent, acct, month, rule=None):
    """What the books hold for the account in the month: {source ('sql' or 'payments'), listing (False when an SQL
    company has no cash book entry for the month: the listing isn't pasted), items [{kind, id, ref, date, description,
    amount (money in above 0, out below), payment_id, status, doc_type, basis, bank_lines}], in, out, left_out (what an
    SQL listing holds that isn't a bank movement: {journals, invoices (customer refunds too), unknown (cash book entries
    with no direction), other_bank (receipts and payments whose lines in SQL don't touch this bank account)}),
    listing_docs (receipts and payments still counted by their listing amount, newer_docs among them: those whose
    listing was pasted after the journal read that gave their lines, edited in SQL since), gone_docs (receipts and
    payments a journal read found SQL no longer has, counted by their listing amount until confirmed as deleted in SQL),
    no_code (True when the bank account's GL code can't be found, so no line can be read)}.
    SQL: the book side is the cash book in SQL's general ledger, what each document posted to the bank account. Every
    receipt (OR) and payment (PV) dated in the month counts, whatever its status here: an ignored correction is in SQL's
    books too; only one confirmed as deleted in SQL is left out (SQL's cash book no longer has it). From the first month
    tracked (rule 'lines', see _rule), one whose current lines SQL's GL Journal of Transaction has given counts as the
    net of its lines on the bank account's GL code (bank_gl_code), money in above 0 (basis 'lines'), with each of those
    lines kept in bank_lines for matching (a receipt of 58,585.50 the bank took a fee of 36.25 from: +58,585.50 and
    -36.25, net 58,549.25); one with lines but none on the bank code moved another account and is left out (other_bank).
    One with no lines kept yet, one whose listing is newer than the lines kept, one SQL no longer has (not yet confirmed
    as deleted), and every one in a month before tracking (rule 'listing'), counts at its listing amount and direction
    (basis 'listing'). A voucher listed on several rows for different payments counts each row as its own payment's
    item, by its listing amount, with the rest of what its lines moved (a fee) on its first row. Customer invoices (IV) are left out: they move no bank balance by themselves. So is a
    journal (JV) whose bank side can't be told: its header carries only one total, so it counts only once its lines are
    known (read from SQL's GL Journal of Transaction, or pasted from its grid) and some of them are on the bank account's
    GL code; it then counts as the net of those lines, in or out (basis 'journal'). A company's other accounts have no SQL
    listing of their own and are worked out from payments, as a company that isn't in SQL is: every payment recorded for
    the account with a paid date in the month, plus the account's statement lines dated in the month that need no
    documents (bank charges and own-account transfers, marked by statements.classify or by a person): money the bank
    moved with nothing to record, counted as it stands on the statement (kind 'bank')."""
    from . import ledger
    listing_docs, no_code, gone_docs, newer_docs = 0, False, 0, 0
    if ent["uses_sql"] and acct["id"] == _primary(con, ent):
        # A voucher edited in SQL and pasted again is a row in a later paste; only the latest paste of a doc_no counts.
        # Rows of one paste all count (a voucher listed on several lines).
        rows = con.execute("""SELECT * FROM sql_entries e WHERE entity_id = ? AND substr(doc_date, 1, 7) = ?
                             AND NOT (COALESCE(doc_no, '') <> '' AND EXISTS (SELECT 1 FROM sql_entries n WHERE n.entity_id = e.entity_id
                                      AND n.doc_no = e.doc_no AND n.import_id > e.import_id)) ORDER BY doc_date, doc_no, id""",
                           (ent["id"], month)).fetchall()
        # An entry confirmed as deleted in SQL (update 31) is no longer in SQL's cash book, so it isn't counted here either.
        listed = rows
        rows = [r for r in rows if not ("deleted_in_sql" in r.keys() and r["deleted_in_sql"] and r["status"] == "ignored")]
        # A journal counts as the bank movement of its lines, so its sign gives the direction; one that moves nothing there stays out.
        # Its lines come from SQL's Journal of Transaction, by doc no., else from its pasted grid, by document key (records
        # not updated to update 22 have no document keys and no lines of either kind, nor the columns the GL code is found by).
        keyed = [r for r in rows if r["kind"] == "journal"]
        has_key = "dockey" in rows[0].keys() if rows else False
        moves = journal_moves(con, ent["id"], [(r["doc_no"], r["dockey"] if has_key else None) for r in keyed],
                              bank_gl_code(con, acct) if keyed and has_key else None)
        counted = {r["id"]: moves[r["doc_no"].strip().upper()] for r in keyed if (r["doc_no"] or "").strip().upper() in moves}
        # Receipts and payments by their lines on the bank (rule 'lines'): one item per document, whatever rows its listing has.
        vouchers = [r for r in rows if (r["kind"] or "payment") == "payment"]
        # Records not updated to update 26 keep no SQL lines (nor the chart the GL code is found by): listing amounts only.
        by_lines = _rule(ent, month, rule) == "lines"
        code = bank_gl_code(con, acct) if by_lines and vouchers and ledger.ready(con) else None
        no_code = by_lines and bool(vouchers) and not code
        got = ledger.bank_lines(con, ent["id"], [r["doc_no"] for r in vouchers], code) if code else {}
        # What the journal reads say of each document: one SQL no longer has ('gone': confirming it as deleted in SQL
        # takes it out, fetching again can't), and the SQL import of the read that last gave or saw its lines. A listing
        # pasted after that read whose rows are newer (a voucher edited in SQL: a row listed again unchanged stays with
        # its first import) can't be counted by those older lines: it counts by its listing until the journal is fetched again.
        reads = ledger.doc_reads(con, ent["id"], [r["doc_no"] for r in vouchers]) if code else {}
        gone = {k for k, v in reads.items() if v["state"] == "gone"}
        last = {}
        for r in vouchers:
            k = (r["doc_no"] or "").strip().upper()
            last[k] = max(last.get(k, 0), r["import_id"] or 0)
        newer = {k for k in got if k in reads and reads[k]["import_id"] and last.get(k, 0) > reads[k]["import_id"]}
        got = {k: v for k, v in got.items() if k not in newer}
        items, done, other_bank, listed_keys, gone_keys, newer_keys = [], set(), set(), set(), set(), set()

        def item(r, amount, basis, parts, pid=None):
            return {"kind": "sql", "id": r["id"], "ref": r["doc_no"], "date": r["doc_date"], "description": r["description"] or r["payee"] or "",
                    "amount": _r(amount), "payment_id": pid if pid is not None else r["payment_id"], "status": r["status"],
                    "doc_type": r["doc_type"], "basis": basis, "bank_lines": parts}
        for r in rows:
            key = (r["doc_no"] or "").strip().upper()
            if r["id"] in counted:
                items.append(item(r, counted[r["id"]], "journal", None))
            elif (r["kind"] or "payment") == "payment" and key and key in got:
                if key in done or key in other_bank:
                    continue  # the document is counted once, on its first row
                parts = got[key]
                if not parts or abs(sum(parts)) < 1:
                    other_bank.add(key)
                    continue
                done.add(key)
                net = sum(parts)
                its = [x for x in rows if (x["doc_no"] or "").strip().upper() == key and (x["kind"] or "payment") == "payment"]
                if len({x["payment_id"] for x in its}) > 1:
                    # A voucher listed on several rows for different payments (or some rows not linked yet): each row
                    # is its own payment's item, by its listing amount, and what the lines move beyond those amounts (a
                    # fee) goes on the first row, so the month still counts what the document posted to the bank.
                    signed = [_cents(x["amount"] or 0) * (1 if x["direction"] == "in" else -1 if x["direction"] == "out" else 0) for x in its]
                    rest = net - sum(signed)
                    for n, (x, a) in enumerate(zip(its, signed)):
                        items.append(item(x, (a + (rest if n == 0 else 0)) / 100, "lines", None))
                    continue
                pid = r["payment_id"] or next((x["payment_id"] for x in its if x["payment_id"]), None)
                items.append(item(r, net / 100, "lines", [_r(p / 100) for p in parts], pid))
            elif (r["kind"] or "payment") == "payment" and r["direction"] in ("in", "out"):
                items.append(item(r, r["amount"] if r["direction"] == "in" else -r["amount"], "listing", None))
                if by_lines:
                    (gone_keys if key in gone else newer_keys if key in newer else listed_keys).add(key or f"#{r['id']}")
        listing_docs = len(listed_keys) + len(newer_keys)
        gone_docs, newer_docs = len(gone_keys), len(newer_keys)
        left = {"journals": sum(r["kind"] == "journal" and r["id"] not in counted for r in rows),
                "invoices": sum(r["kind"] == "invoice" for r in rows),
                "unknown": sum((r["kind"] or "payment") == "payment" and r["direction"] not in ("in", "out")
                              and (r["doc_no"] or "").strip().upper() not in got for r in rows),
                "other_bank": len(other_bank)}
        listing = any((r["kind"] or "payment") == "payment" for r in listed)
        source = "sql"
    else:
        # every account in the currency, stopped ones too: stopping an account must not move past payments between books
        same = con.execute("SELECT COUNT(*) FROM accounts WHERE entity_id = ? AND currency = ?", (ent["id"], acct["currency"])).fetchone()[0]
        rows = con.execute(
            """SELECT * FROM payments WHERE entity_id = ? AND substr(paid_date, 1, 7) = ? AND amount IS NOT NULL
               AND (account_id = ? OR (account_id IS NULL AND currency = ? AND ? = 1)) ORDER BY paid_date, id""",
            (ent["id"], month, acct["id"], acct["currency"], same)).fetchall()
        items = [{"kind": "payment", "id": p["id"], "ref": None, "date": p["paid_date"], "description": p["description"],
                  "amount": _r(p["amount"] if p["direction"] == "in" else -p["amount"]), "payment_id": p["id"],
                  "status": None, "doc_type": None} for p in rows]
        items += [{"kind": "bank", "id": l["id"], "ref": None, "date": l["txn_date"], "description": l["description"],
                   "amount": _r(l["amount"]), "payment_id": None, "status": "no_docs", "doc_type": None, "line_id": l["id"]}
                  for l in con.execute("""SELECT l.* FROM statement_lines l JOIN statements s ON s.id = l.statement_id
                                          WHERE s.account_id = ? AND substr(l.txn_date, 1, 7) = ? AND l.status = 'no_docs'
                                          AND l.payment_id IS NULL ORDER BY l.txn_date, l.line_no""", (acct["id"], month))]
        left, listing, source = {"journals": 0, "invoices": 0, "unknown": 0, "other_bank": 0}, True, "payments"
    return {"source": source, "listing": listing, "items": items,
            "in": _r(sum(i["amount"] for i in items if i["amount"] > 0)),
            "out": _r(-sum(i["amount"] for i in items if i["amount"] < 0)), "left_out": left,
            "listing_docs": listing_docs, "no_code": no_code, "gone_docs": gone_docs, "newer_docs": newer_docs}


def book_table(con, ent, acct, upto, rule=None):
    """The book balance of the account for each month from its first book opening to the month upto: {month: {state:
    'ok' with opening, in, out, closing and the month's movements; or 'needs_listing' (an SQL month with nothing
    pasted, and every month after it up to the next opening typed)}}. A month before the first opening isn't in it.
    rule: 'listing' works the figures out as they were before receipts and payments counted by their bank lines (to show
    a month signed off then what changed); None counts each month by its own rule (_rule)."""
    anchors = {r["month"]: r["amount"] for r in con.execute(
        "SELECT month, amount FROM book_openings WHERE account_id = ? ORDER BY month", (acct["id"],))}
    out, bal, broken = {}, None, None
    m = min(anchors) if anchors else upto
    while anchors and m <= upto:
        if m in anchors:
            bal, broken = anchors[m], None  # an opening typed for a month starts the books afresh
        mv = movements(con, ent, acct, m, rule)
        if broken is None and not mv["listing"]:
            broken = m
        if broken:
            out[m] = {"state": "needs_listing", "month": broken, "movements": mv}
        else:
            out[m] = {"state": "ok", "opening": _r(bal), "in": mv["in"], "out": mv["out"], "closing": _r(bal + mv["in"] - mv["out"]),
                      "movements": mv}
            bal = out[m]["closing"]
        m = db.shift_month(m, 1)
    return out


def book_of(con, ent, acct, month, table=None):
    """The book side of one month: the book_table entry, or {state: 'needs_opening'}; with note, the words shown in
    place of a balance that can't be worked out."""
    b = (table if table is not None else book_table(con, ent, acct, month)).get(month) or {"state": "needs_opening"}
    b = dict(b)
    if b["state"] == "needs_opening":
        b["note"] = "Needs book opening"
    elif b["state"] == "needs_listing":
        b["note"] = "Fetch SQL's cash book listing" + ("" if b["month"] == month else f" for {db.month_label(b['month'])}")
    else:
        b["note"] = None
    return b


# ---------- the statement ----------

def _counts(con, sid):
    r = con.execute(
        """SELECT COUNT(*) AS total,
                  SUM(payment_id IS NULL AND status = 'unmatched') AS to_explain,
                  SUM(confirmed_at IS NOT NULL) AS confirmed,
                  SUM(NOT (payment_id IS NULL AND status = 'unmatched') AND confirmed_at IS NULL) AS to_confirm
           FROM statement_lines WHERE statement_id = ?""", (sid,)).fetchone()
    return {"total": r["total"], "to_explain": r["to_explain"] or 0, "confirmed": r["confirmed"] or 0,
            "to_confirm": r["to_confirm"] or 0, "matched": r["total"] - (r["to_explain"] or 0)}


def adds_up(con, st):
    """Opening + the lines = closing (the printed closing; the last line's balance when none is printed)."""
    if st["opening"] is None:
        return False
    lines = con.execute("SELECT amount, balance FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall()
    closing = st["closing"] if st["closing"] is not None else (lines[-1]["balance"] if lines else st["opening"])
    return abs(st["opening"] + sum(l["amount"] for l in lines) - closing) <= TOL


def _difference(st, book):
    """Bank closing minus book closing, None when either can't be worked out."""
    if book["state"] != "ok" or st is None or st["closing"] is None:
        return None
    return _r(st["closing"] - book["closing"])


def _signed(st, book, changed=None):
    """True when the statement is signed off and still holds: one signed off by review stops counting when the books
    have moved since (an SQL listing pasted late, a payment changed) so that it no longer agrees with the bank. A month
    signed off before receipts and payments counted by their bank lines, whose figures that changed (changed, from
    _changed), is judged by the figures it was signed off with until the owner confirms it again."""
    if not st or not st["reconciled_at"]:
        return False
    d = _difference(st, {"state": "ok", "closing": changed["old"]["closing"]} if changed else book)
    return not (st["reconciled_how"] == "review" and d is not None and abs(d) > TOL)


RECONFIRM = "Book figures changed since sign-off: confirm again"


def _has_rule(con):
    """True once update 32 has given statements the column book_rule_at (records still being updated have none)."""
    return "book_rule_at" in {r[1] for r in con.execute("PRAGMA table_info(statements)")}


def _rule_set(con):
    """The SET clause part that clears book_rule_at, or nothing on records without the column."""
    return ", book_rule_at = NULL" if _has_rule(con) else ""


def _pending(con, ent, acct):
    """The months of the cash book account signed off before receipts and payments counted by their bank lines and not
    confirmed again since (statements.book_rule_at empty), from the first month tracked: the months whose figures may
    have changed under the owner's sign-off."""
    if not (ent["uses_sql"] and acct["id"] == _primary(con, ent)):
        return set()
    if not _has_rule(con):
        return set()
    return {r["month"] for r in con.execute(
        "SELECT month FROM statements WHERE account_id = ? AND reconciled_at IS NOT NULL AND book_rule_at IS NULL", (acct["id"],))
        if not db.before_tracking(ent, r["month"])}


def _figures(b):
    return {"in": b["in"], "out": b["out"], "closing": b["closing"]}


def _changed(con, ent, acct, month, st, book, old_table=None):
    """For a month signed off before receipts and payments counted by their bank lines (see _pending): its book figures
    then (worked out by listing amounts) and now, {old: {in, out, closing}, new: {...}, text}, when they differ; else
    None. old_table: book_table(..., 'listing') already worked out."""
    if not st or not st["reconciled_at"] or month not in _pending(con, ent, acct) or book["state"] != "ok":
        return None
    old = (old_table if old_table is not None else book_table(con, ent, acct, month, "listing")).get(month)
    if not old or old["state"] != "ok":
        return None
    then, now_ = _figures(old), _figures(book)
    if all(abs(then[k] - now_[k]) <= TOL for k in then):
        return None
    return {"old": then, "new": now_, "text": RECONFIRM}


def _month_end(month):
    nxt = db.shift_month(month, 1) + "-01"
    return (date.fromisoformat(nxt) - timedelta(days=1)).isoformat(), nxt


def _unread(con, eid, since, end):
    """The listed receipts, payments and journals (the latest listing of each, not confirmed as deleted in SQL) dated from
    since (or any date) to end that SQL's Journal of Transaction kept has no document for, and whose section (the Bank
    Journal, the General Journal) no read covering their date included: [(book, doc no.)]. Their lines were never read, so
    SQL's balance worked out here leaves them out, whatever the dates covered. A document a read did look for and not
    find (no longer in SQL) isn't among them."""
    from . import ledger
    gone = "deleted_in_sql" in {r[1] for r in con.execute("PRAGMA table_info(sql_entries)")}
    rows = con.execute(f"""SELECT e.doc_no, e.doc_date, COALESCE(e.kind, 'payment') AS kind, e.doc_type FROM sql_entries e
                           WHERE e.entity_id = ? AND COALESCE(e.kind, 'payment') IN ('payment', 'journal') AND TRIM(COALESCE(e.doc_no, '')) <> ''
                           AND e.doc_date <= ? AND (? IS NULL OR e.doc_date >= ?)
                           {"AND NOT (e.deleted_in_sql IS NOT NULL AND e.status = 'ignored')" if gone else ""}
                           AND NOT EXISTS (SELECT 1 FROM sql_entries n WHERE n.entity_id = e.entity_id AND n.doc_no = e.doc_no
                                           AND n.import_id > e.import_id) ORDER BY e.doc_date, e.doc_no""", (eid, end, since, since)).fetchall()
    if not rows:
        return []
    kept = ledger.doc_reads(con, eid, [r["doc_no"] for r in rows])
    reads = ledger._journal_books(con, eid)
    out, seen = [], set()
    for r in rows:
        k = r["doc_no"].strip().upper()
        if k in kept or k in seen:
            continue
        seen.add(k)
        book = ledger._book_of(r["kind"], r["doc_type"])
        if not any(f <= r["doc_date"] <= t and book in books for f, t, books in reads):
            out.append((book, r["doc_no"].strip()))
    return out


def sql_check(con, ent, acct, month, book):
    """The month-end control check of the cash book account: the reconciliation's book closing against SQL's balance on
    the bank account's GL code at the last day of the month, from SQL's books kept here (its opening balance and the
    lines of its GL Journal of Transaction since). {state: 'agrees', 'differs' or 'skipped', text (in words), code,
    sql_balance, difference (book less SQL)}; None for an account that isn't a company's SQL cash book."""
    if not (ent["uses_sql"] and acct["id"] == _primary(con, ent)):
        return None
    from . import books, ledger
    code = bank_gl_code(con, acct) if ledger.ready(con) else None
    out = {"state": "skipped", "text": None, "code": code, "sql_balance": None, "difference": None}

    def skip(why):
        return dict(out, text="Not checked against SQL's bank account: " + why)
    if db.before_tracking(ent, month):
        return skip("a month before tracking began here")
    if not code:  # records not updated to update 26 have no GL codes either
        return skip("set the bank account's GL code in Setup")
    if book["state"] != "ok":
        return skip("there is no book closing yet")
    end, nxt = _month_end(month)
    B = books._Books(con, ent["id"])
    base = B.base(code, nxt)
    if base is None:
        return skip(f"no opening balance of {code} is kept: fetch SQL's trial balance or GL ledger")
    if base["as_of"] and base["as_of"] <= end and not any(a <= base["as_of"] and end <= b for a, b in ledger._coverage(con, ent["id"])):
        return skip(f"SQL's GL Journal of Transaction kept doesn't cover {date.fromisoformat(base['as_of']):%d/%m/%Y} to "
                    f"{date.fromisoformat(end):%d/%m/%Y}: fetch it for those dates")
    unread = _unread(con, ent["id"], base["as_of"], end)
    if unread:
        books_ = sorted({b for b, _ in unread})
        docs = [n for _, n in unread]
        return skip(f"SQL's GL Journal of Transaction kept doesn't include {' or '.join(ledger.BOOK_WORDS[b] for b in books_)} for "
                    f"{', '.join(docs[:5])}{f' and {len(docs) - 5} more' if len(docs) > 5 else ''}: fetch it again with all its sections")
    bal = B.closing(code, end)
    if bal is None:
        return skip(f"SQL's balance of {code} on {date.fromisoformat(end):%d/%m/%Y} can't be worked out")
    sql = _r(bal / 100)
    diff = _r(book["closing"] - sql)
    out.update(sql_balance=sql, difference=diff)
    if abs(diff) <= TOL:
        return dict(out, state="agrees", difference=0.0, text=f"Agrees with SQL's bank account {code}")
    cur = acct["currency"]
    return dict(out, state="differs", text=f"Differs from SQL's bank account {code} by {_money(abs(diff), cur)}: the book closing here is "
                                           f"{_money(book['closing'], cur)}, SQL's balance on {date.fromisoformat(end):%d/%m/%Y} is {_money(sql, cur)}")


def _status(st, counts, book, signed):
    if not st:
        return "to_import"
    if signed:
        return "reconciled"
    d = _difference(st, book)
    if st["reconciled_at"] or (d is not None and abs(d) > TOL and not counts["to_explain"] and not counts["to_confirm"]):
        return "difference"
    return "to_review"


STATUS_WORDS = {"to_import": "To import", "to_review": "To review", "difference": "Difference", "reconciled": "Reconciled"}


def _pl(n, word, words=None):
    return f"{n} {word if n == 1 else (words or word + 's')}"


def why_not(con, ent, acct, month, st, counts, book, pairs=None):
    """What stops the month being signed off, as short phrases; empty when nothing does. Besides the books agreeing with
    the bank: every line explained and confirmed, every line linked to several payments adding up, and every No money
    moved pair nil and confirmed. pairs: no_money_pairs already worked out."""
    why = []
    if not adds_up(con, st):
        why.append("the statement doesn't add up (opening plus lines is not the closing balance)")
    if counts["to_explain"]:
        why.append(f"{counts['to_explain']} line{'s' if counts['to_explain'] > 1 else ''} to explain")
    if counts["to_confirm"]:
        why.append(f"{counts['to_confirm']} line{'s' if counts['to_confirm'] > 1 else ''} to confirm")
    short = short_lines(con, st)
    if short:
        why.append(_pl(len(short), "line") + " matched, but the amounts differ")
    if pairs is None:
        pairs = no_money_pairs(con, ent, acct, month, book.get("movements"))
    bad = [p for p in pairs if not p["nil"]]
    if bad:
        why.append(f"{_pl(len(bad), 'pair')} under No money moved {'isn' if len(bad) == 1 else 'aren'}'t nil "
                   f"({_money(sum(abs(p['net']) for p in bad), acct['currency'])} left)")
    todo = [p for p in pairs if p["nil"] and not p["confirmed_at"]]
    if todo:
        why.append(f"{_pl(len(todo), 'pair')} under No money moved to confirm")
    if book["state"] != "ok":
        why.append(book["note"][0].lower() + book["note"][1:])
    else:
        d = _difference(st, book)
        if d is None or abs(d) > TOL:
            why.append("the books differ from the bank by " + (_money(d, acct["currency"]) if d is not None else "an unknown amount"))
    return why


def not_reconciled(con, ent, account_id, month):
    """For a checklist item: why the account's statement for the month isn't signed off yet (a short phrase), or None
    when it is. A month with no statement imported is 'statement not imported yet'. A month signed off before receipts
    and payments counted by their bank lines, whose book figures the lines changed, isn't done until it is confirmed again."""
    acct = _acct(con, account_id)
    st = _stmt(con, account_id, month)
    if not st:
        return "statement not imported yet"
    book = book_of(con, ent, acct, month)
    changed = _changed(con, ent, acct, month, st, book)
    if _signed(st, book, changed):
        if not changed:
            return None
        # Signed off before receipts and payments counted by their bank lines, and the lines changed its figures: the
        # sign-off stands, but the item waits for the owner to confirm the new figures (or review the month again).
        d = _difference(st, book)
        if d is not None and abs(d) > TOL:
            return f"book figures changed since sign-off and now differ from the bank by {_money(abs(d), acct['currency'])}: review the month again"
        return RECONFIRM[0].lower() + RECONFIRM[1:]
    counts = _counts(con, st["id"])
    if counts["to_explain"]:
        return f"{counts['to_explain']} line{'s' if counts['to_explain'] > 1 else ''} to explain"
    if counts["to_confirm"]:
        return f"{counts['to_confirm']} line{'s' if counts['to_confirm'] > 1 else ''} to confirm"
    if st["reconciled_at"]:
        return "the books no longer agree with the bank"
    left = why_not(con, ent, acct, month, st, counts, book)
    return left[0] if left else "ready to mark reconciled"


# ---------- the year view and the month panel ----------

def year_view(con, ent, acct, year, today=None):
    """One row per month of the year for the account: the tracked months (from the company's first month to the current
    payroll month) and any other month with an imported statement. Newest first. {account, year, years (the years with
    rows), rows [{month, label, statement_id, status, status_text, bank_closing, book_closing, book_note, reconciled_at,
    reconciled_how, document_id, before_tracking}]}."""
    cur = db.current_cycle(today)
    have = {r["month"] for r in con.execute("SELECT month FROM statements WHERE account_id = ?", (acct["id"],))}
    months, first = set(have), ent["first_month"]
    if first:
        m = first
        while m <= cur:
            months.add(m)
            m = db.shift_month(m, 1)
    else:
        months.add(cur)
    years = sorted({m[:4] for m in months}, reverse=True)
    year = str(year) if str(year) in years else (years[0] if years else str(cur[:4]))
    mine = sorted((m for m in months if m[:4] == year), reverse=True)
    table = book_table(con, ent, acct, mine[0]) if mine else {}
    pending = _pending(con, ent, acct) & set(mine)
    old_table = book_table(con, ent, acct, max(pending), "listing") if pending else {}
    rows = []
    for m in mine:
        st = _stmt(con, acct["id"], m)
        book = book_of(con, ent, acct, m, table)
        counts = _counts(con, st["id"]) if st else None
        changed = _changed(con, ent, acct, m, st, book, old_table) if m in pending else None
        status = _status(st, counts, book, _signed(st, book, changed))
        mv = book.get("movements") or {}
        rows.append({"month": m, "label": db.month_label(m), "statement_id": st["id"] if st else None, "status": status,
                     "status_text": STATUS_WORDS[status], "bank_closing": st["closing"] if st else None,
                     "book_closing": book["closing"] if book["state"] == "ok" else None, "book_note": book["note"],
                     "reconciled_at": st["reconciled_at"] if st and status == "reconciled" else None,
                     "reconciled_how": st["reconciled_how"] if st and status == "reconciled" else None,
                     "document_id": st["document_id"] if st else None, "before_tracking": db.before_tracking(ent, m),
                     "book_changed": changed if status == "reconciled" else None, "listing_docs": mv.get("listing_docs") or 0,
                     "gone_docs": mv.get("gone_docs") or 0, "locked": bool(st and st["reconciled_at"]),
                     "reopened_at": (reopens(con, st["id"]) or [{}])[0].get("at") if st and not st["reconciled_at"] else None})
    listing_months = sum(1 for r in rows if r["listing_docs"])
    return {"account": {"id": acct["id"], "label": acct["label"], "currency": acct["currency"]}, "year": year, "years": years,
            "rows": rows, "openings": [dict(r) for r in con.execute(
                "SELECT month, amount FROM book_openings WHERE account_id = ? ORDER BY month", (acct["id"],))],
            "source": "SQL cash book" if ent["uses_sql"] and acct["id"] == _primary(con, ent) else "payments recorded here",
            "listing_months": listing_months,
            "listing_note": (f"{listing_months} month{'s' if listing_months > 1 else ''} this year still count{'' if listing_months > 1 else 's'} "
                             "some receipts or payments by their listing amount: fetch SQL's GL Journal of Transaction to count them by "
                             "their bank lines.") if listing_months else None}


def _line_row(l, why):
    return {"line_id": l["id"], "date": l["txn_date"], "description": l["description"], "amount": l["amount"], "why": why}


def _links_of(con, st):
    """{line id: [(payment id, the part of the line it stands for)]} for the lines of a statement, each line's own payment
    first."""
    out = {}
    if not st:
        return out
    for r in con.execute(f"""SELECT k.line_id, k.payment_id, k.amount, (k.payment_id = l.payment_id) AS own FROM {db.line_links(con)} k
                             JOIN statement_lines l ON l.id = k.line_id WHERE k.statement_id = ? ORDER BY k.line_id, own DESC, k.payment_id""",
                         (st["id"],)):
        out.setdefault(r["line_id"], []).append((r["payment_id"], r["amount"]))
    return out


def _parted(con, st):
    """The ids of the statement's lines with a link that stands for a part of the line (not the whole line)."""
    if not st or not db.has_line_links(con):
        return set()
    return {r[0] for r in con.execute("""SELECT k.line_id FROM statement_line_payments k JOIN statement_lines l ON l.id = k.line_id
                                         WHERE l.statement_id = ? AND k.amount IS NOT NULL""", (st["id"],))}


def short_lines(con, st):
    """The lines of a statement linked to several payments whose parts don't add up to the line (a bulk transfer linked
    to some of the payments it paid): [{line_id, date, description, amount, linked, gap (line less the parts)}]."""
    out = []
    if not st:
        return out
    links = _links_of(con, st)
    parted = _parted(con, st)
    for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)):
        its = links.get(l["id"]) or []
        # several payments, or one left with the part it stood for when another was taken off the line
        if len(its) > 1 or l["id"] in parted:
            total = _r(sum(a for _, a in its))
            if abs(total - l["amount"]) > TOL:
                out.append({"line_id": l["id"], "date": l["txn_date"], "description": l["description"], "amount": l["amount"],
                            "linked": total, "gap": _r(l["amount"] - total)})
    return out


def _item_key(i):
    """How a book entry is named in a No money moved pair: an SQL document by its number, a payment by its id."""
    if i["kind"] == "sql" and i.get("ref"):
        return "sql:" + str(i["ref"]).strip().upper()
    return f"{i['kind']}:{i['id']}"


def _has_pairs(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recon_pairs'").fetchone() is not None


def no_money_pairs(con, ent, acct, month, mv=None):
    """The pairs of book entries of the month that cancel each other out and never touched the bank (a voucher and its
    reversal; a receipt and a payment for the same amount on the same day), found as the SQL import page finds a
    correction (sqlimport.CORRECTION_WORDS, or an in and an out of one amount on one day): [{key, docs [{key, kind, ref,
    date, description, amount}], net, nil, reason (as kept, else the one filled in from the documents), suggested,
    confirmed_at}]. An entry whose payment is on a bank line moved money, so it is never one of a pair."""
    from .sqlimport import CORRECTION_WORDS
    mv = mv or movements(con, ent, acct, month)
    on_line = {r[0] for r in con.execute(f"SELECT DISTINCT payment_id FROM {db.line_links(con)}")}
    cands = [i for i in mv["items"] if i["kind"] in ("sql", "payment") and abs(i["amount"]) >= TOL
             and not (i["payment_id"] and i["payment_id"] in on_line)]
    cands.sort(key=lambda i: (i["date"] or "", str(i.get("ref") or ""), i["id"]))
    used, found = set(), []

    def name(i):
        return (i.get("ref") or i.get("description") or "").strip()
    # A reversal or contra that names another entry of the month, whatever the amounts (one keyed wrongly isn't nil).
    for i in cands:
        if _item_key(i) in used or not CORRECTION_WORDS.search(i["description"] or ""):
            continue
        text = (i["description"] or "").upper()
        other = next((o for o in cands if o is not i and _item_key(o) not in used and o.get("ref")
                      and str(o["ref"]).strip().upper() in text and (o["amount"] > 0) != (i["amount"] > 0)), None)
        if other:
            used |= {_item_key(i), _item_key(other)}
            found.append((other, i, "reversal"))
    # An in and an out of the same amount on the same day.
    for i in cands:
        if _item_key(i) in used:
            continue
        other = next((o for o in cands if o is not i and _item_key(o) not in used and o["date"] == i["date"]
                      and abs(abs(o["amount"]) - abs(i["amount"])) < TOL and (o["amount"] > 0) != (i["amount"] > 0)), None)
        if other:
            used |= {_item_key(i), _item_key(other)}
            found.append((i, other, "same day"))
    kept = {}
    if found and _has_pairs(con):
        kept = {r["pair_key"]: r for r in con.execute("SELECT * FROM recon_pairs WHERE account_id = ? AND month = ?", (acct["id"], month))}
    out = []
    for a, b, how in found:
        docs = [{"key": _item_key(x), "kind": x["kind"], "ref": x.get("ref"), "date": x["date"], "description": x["description"] or "",
                 "amount": x["amount"]} for x in (a, b)]
        key = "|".join(sorted(d["key"] for d in docs))
        net = _r(a["amount"] + b["amount"])
        same = a["date"] == b["date"]
        if how == "reversal":
            why = (f"Reversal: {name(b)} reverses {name(a)} ({(a['description'] or '').strip() or 'no description'})"
                   f"{' the same day' if same else ''}; no money moved")
        else:
            why = f"{name(a)} and {name(b)} are money in and out of the same amount on {db.day_label(a['date'])}; no money moved"
        k = kept.get(key)
        out.append({"key": key, "docs": docs, "net": net, "nil": abs(net) <= TOL, "suggested": why,
                    "reason": (k["reason"] if k and k["reason"] else why), "confirmed_at": k["confirmed_at"] if k else None})
    return out


def _lists(con, ent, acct, month, st, mv, pairs=None):
    """The lists of a reconciliation statement. books_only: what the books hold for the month that no line of this
    statement is linked to. bank_only: the statement's lines the month's books don't hold. Both with a note saying why.
    differ: payments the books and the statement both hold, for different amounts (a payment of 18,000 with only
    a line of 8,000 linked so far): {description, ref, book, bank, amount (bank minus book)}. A line linked to several
    payments counts the part each stands for. The entries of a No money moved pair (pairs, from no_money_pairs) are
    listed there, not in books_only."""
    lines = con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall() if st else []
    links = _links_of(con, st)
    on_stmt = {pid for its in links.values() for pid, _ in its}
    in_books = {i["payment_id"] for i in mv["items"] if i["payment_id"]}
    bank_items = {i["line_id"] for i in mv["items"] if i.get("line_id")}  # charges and transfers counted from the statement
    paired = {d["key"] for p in (pairs if pairs is not None else no_money_pairs(con, ent, acct, month, mv)) for d in p["docs"]}
    books_only = []
    for i in mv["items"]:
        pid = i["payment_id"]
        if (pid and pid in on_stmt) or i.get("line_id") or _item_key(i) in paired:
            continue
        if pid:
            elsewhere = con.execute(
                f"""SELECT s.month FROM {db.line_links(con)} l JOIN statements s ON s.id = l.statement_id WHERE l.payment_id = ?
                   ORDER BY s.month LIMIT 1""", (pid,)).fetchone()
            why = f"On the {db.month_label(elsewhere['month'])} statement" if elsewhere else "Not on a bank statement yet (not cleared?)"
        elif i["status"] == "ignored":
            why = "Ignored here as a correction: SQL still holds it"
        elif i["kind"] == "sql":
            why = "Not linked to a payment or a bank line"
        else:
            why = "Not on a bank statement yet"
        books_only.append({"kind": i["kind"], "ref": i["ref"], "date": i["date"], "description": i["description"],
                           "amount": i["amount"], "why": why})
    bank_only = []
    for l in lines:
        pid = l["payment_id"]
        its = links.get(l["id"]) or []
        if len(its) > 1:
            # A line paying several payments: the part of each the month's books don't hold is on the statement only.
            for p_id, part in its:
                if p_id in in_books:
                    continue
                p = con.execute("SELECT description, paid_date FROM payments WHERE id = ?", (p_id,)).fetchone()
                why = (f"Part for {p['description']}: payment is dated {db.day_label(p['paid_date'])}, in another month"
                       if p and p["paid_date"] else f"Part for {p['description'] if p else 'a payment'}: not in this month's books")
                bank_only.append(dict(_line_row(l, why), amount=_r(part), kind="line"))
            continue
        if (pid and pid in in_books) or l["id"] in bank_items:
            continue
        if not pid:
            why = ("No payment needed: " + l["note"]) if l["status"] == "no_docs" and l["note"] else \
                "No documents needed" if l["status"] == "no_docs" else "Not explained yet"
        elif mv["source"] == "sql":
            v = con.execute("SELECT doc_no, doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal') "
                            "ORDER BY doc_date LIMIT 1", (pid,)).fetchone()
            why = f"SQL {v['doc_no']} is dated {db.day_label(v['doc_date'])}, in another month" if v else "No SQL voucher for it yet"
        else:
            p = con.execute("SELECT paid_date FROM payments WHERE id = ?", (pid,)).fetchone()
            why = f"Payment is dated {db.day_label(p['paid_date'])}, in another month" if p and p["paid_date"] else "Payment has no paid date"
        bank_only.append(dict(_line_row(l, why), kind="line"))
    bank_sum, book_sum, named = {}, {}, {}
    for its in links.values():
        for p_id, part in its:
            bank_sum[p_id] = bank_sum.get(p_id, 0) + part
    for i in mv["items"]:
        if i["payment_id"]:
            book_sum[i["payment_id"]] = book_sum.get(i["payment_id"], 0) + i["amount"]
            named.setdefault(i["payment_id"], []).append(i)
    differ = []
    for pid in sorted(bank_sum.keys() & book_sum.keys()):
        if abs(bank_sum[pid] - book_sum[pid]) > TOL:
            its = named[pid]
            differ.append({"payment_id": pid, "description": its[0]["description"], "ref": ", ".join(i["ref"] for i in its if i["ref"]),
                           "book": _r(book_sum[pid]), "bank": _r(bank_sum[pid]), "amount": _r(bank_sum[pid] - book_sum[pid])})
    return books_only, bank_only, differ


def _lock_fields(st):
    """What a statement's lock says: locked (signed off, so its lines and its payments' bank fields can't change), when
    and how, the note the app wrote at sign-off, the free note and the declared Prepared by."""
    keys = st.keys()
    note = st["sign_note"] if "sign_note" in keys else None
    try:
        lines = json.loads(note) if note else []
    except ValueError:
        lines = [note]
    return {"locked": bool(st["reconciled_at"]), "locked_at": st["reconciled_at"], "locked_how": st["reconciled_how"],
            "sign_note": lines if st["reconciled_at"] else [], "free_note": st["reconciled_note"] if st["reconciled_at"] else None,
            "prepared_by": (st["prepared_by"] if "prepared_by" in keys else None) if st["reconciled_at"] else None}


def reopens(con, statement_id):
    """The times a statement's sign-off was reopened, newest first: [{at, reason, was_at, was_how}]."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recon_reopens'").fetchone():
        return []
    return [dict(r) for r in con.execute("SELECT at, reason, was_at, was_how FROM recon_reopens WHERE statement_id = ? ORDER BY id DESC",
                                         (statement_id,))]


def statement_code(con, ent, acct, month):
    """The printed reconciliation statement's code: BR-yymm-<company code>-<last 4 digits of the account number>."""
    from . import formcode
    return formcode.code("BR", month, ent["code"], acct["number"], acct["id"])


def recon_task(con, ent, month, code=None):
    """The month's bank reconciliation checklist item (the one shown done by the statements being reconciled), where
    the signed statement is filed as a document: {id, title, documents [{id, original_name, uploaded_at}]}, or None.
    code: one statement's code (BR-...): only the documents filed for it (their name starts with it; the page names the
    signed copy so when it is uploaded), as the item is shared by every account of the company."""
    t = None
    if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checklist_items'").fetchone():
        t = con.execute("""SELECT t.* FROM tasks t JOIN checklist_items ci ON ci.entity_id = t.entity_id AND ci.code = t.code
                           WHERE t.entity_id = ? AND t.month = ? AND ci.completion = 'reconciled' ORDER BY t.id LIMIT 1""",
                        (ent["id"], month)).fetchone()
    t = t or con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? AND code = 'recon'", (ent["id"], month)).fetchone()
    if not t:
        return None
    docs = [dict(d) for d in con.execute("""SELECT id, original_name, uploaded_at FROM documents WHERE task_id = ? AND replaced_by IS NULL
                                            AND removed_at IS NULL ORDER BY id""", (t["id"],))]
    if code:
        docs = [d for d in docs if d["original_name"].upper().startswith(code.upper())]
    return {"id": t["id"], "title": t["title"], "documents": docs}


def _gl_or_none(con, acct):
    """The bank account's GL code (bank_gl_code), or None on records not updated to update 26 (no GL codes kept)."""
    from . import ledger
    return bank_gl_code(con, acct) if ledger.ready(con) else None


def month_summary(con, ent, acct, month):
    """The panel of a month: statement figures, book against bank, line counts, the reconciliation statement and
    whether it can be signed off. statement is None while not imported (the books' side is still shown)."""
    st = _stmt(con, acct["id"], month)
    book = book_of(con, ent, acct, month)
    mv = book.get("movements") or movements(con, ent, acct, month)
    counts = _counts(con, st["id"]) if st else None
    changed = _changed(con, ent, acct, month, st, book)
    signed = _signed(st, book, changed)
    status = _status(st, counts, book, signed)
    pairs = no_money_pairs(con, ent, acct, month, mv)
    books_only, bank_only, differ = _lists(con, ent, acct, month, st, mv, pairs)
    diff = _difference(st, book)
    n, nw, g = mv.get("listing_docs") or 0, mv.get("newer_docs") or 0, mv.get("gone_docs") or 0
    notes = []
    if n:
        notes.append(f"{n} receipt{'s' if n > 1 else ''} or payment{'s' if n > 1 else ''} this month {'are' if n > 1 else 'is'} still "
                     f"counted by {'their' if n > 1 else 'its'} listing amount: fetch SQL's GL Journal of Transaction to count them by their bank lines."
                     + (f" {nw} of them {'were' if nw > 1 else 'was'} pasted again after the journal was read (edited in SQL since), "
                        "so the lines kept are out of date." if nw else ""))
    elif mv.get("no_code"):
        notes.append("Receipts and payments are counted by their listing amounts: set the bank account's GL code in Setup to count them "
                     "by their lines on the bank account.")
    if g:
        notes.append(f"{g} receipt{'s' if g > 1 else ''} or payment{'s' if g > 1 else ''} this month {'are' if g > 1 else 'is'} no longer in "
                     f"SQL, so {'they are' if g > 1 else 'it is'} counted by {'their' if g > 1 else 'its'} listing amount for now: if SQL deleted "
                     f"{'them' if g > 1 else 'it'}, click Deleted in SQL on the SQL import page (unlink {'their payments' if g > 1 else 'its payment'} "
                     "first) to leave {} out. Fetching the journal again won't change this.".format('them' if g > 1 else 'it'))
    listing_note = " ".join(notes) or None
    out = {"account": {"id": acct["id"], "label": acct["label"], "currency": acct["currency"]}, "month": month,
           "label": db.month_label(month), "status": status, "status_text": STATUS_WORDS[status],
           "before_tracking": db.before_tracking(ent, month), "uses_sql": bool(ent["uses_sql"]),
           "source": mv["source"], "left_out": mv["left_out"], "statement": None,
           "book": {k: book.get(k) for k in ("state", "opening", "in", "out", "closing", "note")},
           "bank_closing": None, "difference": diff, "lines": counts, "books_only": books_only, "bank_only": bank_only, "differ": differ,
           "reconciliation": None, "reconciled_at": None, "reconciled_how": None, "reconciled_note": None,
           "can_sign": False, "why_not": ["the statement isn't imported yet"],
           "listing_docs": n, "gone_docs": g, "listing_note": listing_note, "sql_check": sql_check(con, ent, acct, month, book),
           "book_changed": changed if signed else None, "can_reconfirm": False, "reconfirm_why": None,
           "pairs": pairs, "short_lines": [], "locked": False, "locked_at": None, "locked_how": None, "sign_note": [],
           "prepared_by": None, "free_note": None, "reopens": reopens(con, st["id"]) if st else [],
           "statement_code": statement_code(con, ent, acct, month),
           "recon_task": recon_task(con, ent, month, statement_code(con, ent, acct, month)),
           "source_text": "SQL cash book" if mv["source"] == "sql" else "payments recorded here",
           "bank_gl": _gl_or_none(con, acct) if mv["source"] == "sql" else None}
    if not st:
        return out
    out.update(_lock_fields(st))
    out["short_lines"] = short_lines(con, st)
    lines = con.execute("SELECT amount FROM statement_lines WHERE statement_id = ?", (st["id"],)).fetchall()
    out["statement"] = {"id": st["id"], "opening": st["opening"], "closing": st["closing"], "document_id": st["document_id"],
                        "money_in": _r(sum(l["amount"] for l in lines if l["amount"] > 0)),
                        "money_out": _r(-sum(l["amount"] for l in lines if l["amount"] < 0)), "adds_up": adds_up(con, st)}
    out["bank_closing"] = st["closing"]
    if signed:
        out.update(reconciled_at=st["reconciled_at"], reconciled_how=st["reconciled_how"], reconciled_note=st["reconciled_note"])
    if out["book_changed"]:
        # Confirming again keeps the sign-off, so it is offered only while the new figures still agree with the bank.
        ok = diff is not None and abs(diff) <= TOL
        out["can_reconfirm"] = ok
        out["reconfirm_why"] = None if ok else (f"The new book closing differs from the bank by {_money(diff, acct['currency'])}: reopen "
                                                "the month and review it." if diff is not None else "The book closing can't be worked out.")
    if book["state"] == "ok" and diff is not None:
        brought = _r(st["opening"] - book["opening"])
        b_out = _r(-sum(i["amount"] for i in books_only if i["amount"] < 0))
        b_in = _r(sum(i["amount"] for i in books_only if i["amount"] > 0))
        x_net = _r(sum(i["amount"] for i in bank_only))
        d_net = _r(sum(i["amount"] for i in differ))
        out["reconciliation"] = {"brought_forward": brought, "books_out": b_out, "books_in": b_in, "bank_net": x_net,
                                 "differ": d_net, "other": _r(diff - brought - b_out + b_in - x_net - d_net)}
    left = why_not(con, ent, acct, month, st, counts, dict(book, movements=mv), pairs)
    out["why_not"], out["can_sign"] = left, not left and not out["locked"]
    # Before tracking: the statement adding up and (the books agreeing, or a note), the person's tick is asked for on top.
    out["can_sign_before_tracking"] = out["before_tracking"] and out["statement"]["adds_up"] and not out["locked"]
    out["book_matches"] = diff is not None and abs(diff) <= TOL
    return out


# ---------- the review of a statement ----------

def date_gap(con, line, payment_id):
    """(days, date, kind) between a bank line and the date the books hold for the payment: the SQL voucher's date
    (the one nearest the line's, kind 'voucher'), else a paid date typed in ('payment'). (0, None, None) when the books
    have no date of their own for it (a date that came from a bank line is the bank's)."""
    if not payment_id:
        return 0, None, None
    if "id" in line.keys() and con.execute(f"SELECT COUNT(*) FROM {db.line_links(con)} WHERE line_id = ?", (line["id"],)).fetchone()[0] > 1:
        return 0, None, None  # a line paying several payments keeps each one's own date
    d = date.fromisoformat(line["txn_date"])
    vs = [r["doc_date"] for r in con.execute(
        "SELECT doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')", (payment_id,))]
    if vs:
        best = min(vs, key=lambda v: abs((date.fromisoformat(v) - d).days))
        return abs((date.fromisoformat(best) - d).days), best, "voucher"
    p = con.execute("SELECT paid_date, paid_source FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if p and p["paid_date"] and p["paid_source"] not in ("bank", "sql"):
        return abs((date.fromisoformat(p["paid_date"]) - d).days), p["paid_date"], "payment"
    return 0, None, None


def review(con, ent, st):
    """What the review screen shows for a statement: its figures and month summary, every line (open ones first, with
    the suggestions for them; matched ones with the payment and its id, its SQL voucher numbers and dates, the days the
    bank's date differs from the voucher's or payment's, and whether the line still needs the date tick: only while it
    is not confirmed), and the payments a line can be linked to."""
    acct = _acct(con, st["account_id"])
    summary = month_summary(con, ent, acct, st["month"])
    sugg = statements.suggest(con, ent["id"], st["id"])
    links = _links_of(con, st)
    short = {x["line_id"]: x for x in short_lines(con, st)}
    rows = []
    for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall():
        pid = l["payment_id"]
        row = {"id": l["id"], "line_no": l["line_no"], "txn_date": l["txn_date"], "description": l["description"], "amount": l["amount"],
               "balance": l["balance"], "status": l["status"], "note": l["note"], "confirmed_at": l["confirmed_at"],
               "state": "matched" if pid else "explained" if l["status"] == "no_docs" else "open",
               "payment_id": pid, "payment": None, "payment_desc": None, "vouchers": [], "suggestions": sugg.get(l["id"], []),
               "gap_days": 0, "book_date": None, "book_date_kind": None, "needs_date_tick": False, "group": None, "short": None}
        its = links.get(l["id"]) or []
        if len(its) > 1 or l["id"] in short:
            # One line paying several payments (a bulk transfer): each with the part of the line it stands for (or one
            # left with its part when the others were taken off: the line is short until it is linked again).
            row["group"] = [dict(con.execute("SELECT id, description, month, amount, currency, direction FROM payments WHERE id = ?",
                                             (p_id,)).fetchone(), part=_r(part)) for p_id, part in its]
            row["short"] = short.get(l["id"])
        if pid:
            p = con.execute("SELECT id, description, month, amount, currency, paid_date, direction FROM payments WHERE id = ?", (pid,)).fetchone()
            row["payment"], row["payment_desc"] = dict(p), p["description"]
            if row["group"]:
                row["payment_desc"] = f"Linked to {_pl(len(row['group']), 'payment')}"
            row["vouchers"] = [dict(r) for r in con.execute(
                """SELECT doc_no, doc_date, doc_type FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')
                   ORDER BY doc_date""", (pid,))]
            if not row["group"]:  # a line paying several payments has no one date to keep (it is linked from the dialog)
                row["gap_days"], row["book_date"], row["book_date_kind"] = date_gap(con, l, pid)
                row["needs_date_tick"] = bool(row["gap_days"]) and not l["confirmed_at"]  # a confirmed line had its tick then
        rows.append(row)
    pays = [dict(p) for p in con.execute(
        f"""SELECT p.id, p.month, p.description, p.amount, p.currency, p.direction, p.due_date, p.paid_date,
                  (SELECT SUM(ABS(s.amount)) FROM {db.line_links(con)} s WHERE s.payment_id = p.id) AS linked,
                  CASE WHEN p.paid_source IN ('bank', 'sql') THEN NULL ELSE p.paid_date END AS typed_date
           FROM payments p WHERE p.account_id = ? AND p.month BETWEEN ? AND ? ORDER BY p.due_date, p.id""",
        (st["account_id"], db.shift_month(st["month"], -1), st["month"]))]
    parts = bank_parts(con, ent["id"], [p["id"] for p in pays])
    linked = _linked_amounts(con, parts)
    for p in pays:  # the dates the books hold for it, so the page can tell when a bank date differs
        p["voucher_dates"] = [r["doc_date"] for r in con.execute(
            "SELECT doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')", (p["id"],))]
        # A receipt or payment SQL posted to the bank in several lines (the amount and a fee): each line, and those no
        # bank line is linked to yet, so a fee line can be linked to the same document.
        bp = parts.get(p["id"])
        p["bank_lines"] = bp["lines"] if bp else None
        p["bank_net"] = bp["net"] if bp else None
        p["open_lines"] = open_lines(bp, linked.get(p["id"], [])) if bp else None
    return {"summary": summary, "lines": rows, "payments": pays, "statement_id": st["id"]}


# ---------- matching a document by its bank lines ----------

FEE_DAYS = 3  # a fee line is dated within this many days of the line it was taken from


def bank_parts(con, entity_id, payment_ids):
    """What the SQL receipts and payments linked to each payment posted to the company's cash book account, for matching
    bank lines to them: {payment id: {net (money in above 0), lines (each line on the bank account's GL code, in order),
    docs}}. Only for a payment of the cash book account (or of no account) whose every SQL receipt or payment (the latest
    listing of each, not confirmed as deleted in SQL, dated from the first month tracked) has current lines in SQL's GL
    Journal of Transaction, each listed for that payment alone and not pasted again since those lines were read; any
    other payment isn't in it and is matched by its amount as before."""
    from . import ledger
    ids = sorted({int(x) for x in payment_ids if x})
    if not ids or not ledger.ready(con):
        return {}
    ent = _ent(con, entity_id)
    acct = cash_book_account(con, entity_id) if ent and ent["uses_sql"] else None
    code = bank_gl_code(con, acct) if acct else None
    if not code:
        return {}
    gone = "deleted_in_sql" in {r[1] for r in con.execute("PRAGMA table_info(sql_entries)")}
    docs = {}
    for part in ledger._chunks(ids):
        for r in con.execute(f"""SELECT e.payment_id, e.doc_no, e.doc_date FROM sql_entries e JOIN payments p ON p.id = e.payment_id
                                 WHERE e.entity_id = ? AND COALESCE(e.kind, 'payment') = 'payment' AND e.payment_id IN ({','.join('?' * len(part))})
                                 AND (p.account_id IS NULL OR p.account_id = ?) AND TRIM(COALESCE(e.doc_no, '')) <> ''
                                 {"AND NOT (e.deleted_in_sql IS NOT NULL AND e.status = 'ignored')" if gone else ""}
                                 AND NOT EXISTS (SELECT 1 FROM sql_entries n WHERE n.entity_id = e.entity_id AND n.doc_no = e.doc_no
                                                 AND n.import_id > e.import_id)
                                 ORDER BY e.doc_date, e.doc_no""", (entity_id, *part, acct["id"])):
            docs.setdefault(r["payment_id"], {}).setdefault(r["doc_no"].strip().upper(), r["doc_date"])
    keys = {k for d in docs.values() for k in d}
    got = ledger.bank_lines(con, entity_id, keys, code)
    # A document listed on several rows for different payments (or with a row not linked yet) holds the bank lines of
    # them all, so no one payment can be matched by them; nor can one whose latest listing was pasted after the journal
    # read that gave its lines (edited in SQL since: the lines kept are out of date). Each is matched by its amount.
    shared, latest = set(), {}
    for part in ledger._chunks(keys):
        q = f"""SELECT UPPER(TRIM(e.doc_no)) AS k, e.payment_id, e.import_id FROM sql_entries e WHERE e.entity_id = ?
                AND COALESCE(e.kind, 'payment') = 'payment' AND UPPER(TRIM(e.doc_no)) IN ({','.join('?' * len(part))})
                {"AND NOT (e.deleted_in_sql IS NOT NULL AND e.status = 'ignored')" if gone else ""}
                AND NOT EXISTS (SELECT 1 FROM sql_entries n WHERE n.entity_id = e.entity_id AND n.doc_no = e.doc_no AND n.import_id > e.import_id)"""
        pids = {}
        for r in con.execute(q, (entity_id, *part)):
            pids.setdefault(r["k"], set()).add(r["payment_id"])
            latest[r["k"]] = max(latest.get(r["k"], 0), r["import_id"] or 0)
        shared |= {k for k, v in pids.items() if len(v) > 1}
    reads = ledger.doc_reads(con, entity_id, keys)
    stale = {k for k, v in reads.items() if v["import_id"] and latest.get(k, 0) > v["import_id"]}
    out = {}
    for pid, mine in docs.items():
        if any(db.before_tracking(ent, d[:7]) for d in mine.values()) or any(k not in got or k in shared or k in stale for k in mine):
            continue
        lines = [x for k in mine for x in got[k]]
        net = sum(lines)
        if lines and abs(net) >= 1:
            out[pid] = {"net": _r(net / 100), "lines": [_r(x / 100) for x in lines], "docs": list(mine)}
    return out


def _cents(n):
    return int(round(float(n) * 100))


def _linked_amounts(con, parts):
    """{payment id: [the amounts of the bank lines linked to it]} for the payments in parts."""
    out = {}
    ids = list(parts)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in con.execute(f"SELECT payment_id, amount FROM {db.line_links(con)} WHERE payment_id IN ({','.join('?' * len(chunk))}) "
                             "ORDER BY line_id", chunk):
            out.setdefault(r["payment_id"], []).append(r["amount"])
    return out


def open_lines(bp, linked):
    """The bank lines of a document (bp, from bank_parts) that no linked bank line stands for yet: all of them while
    nothing is linked; none once the linked lines add up to its net movement (one net line, or every line one for one);
    else those whose amount no linked line has, or, when a linked line isn't one of its lines (SQL posted the amount and
    the charge as one line), what is still to come: its net less the lines linked."""
    if not linked:
        return list(bp["lines"])
    rest = _cents(bp["net"]) - sum(_cents(a) for a in linked)
    if not rest:
        return []
    left = list(bp["lines"])
    for a in linked:
        hit = next((i for i, x in enumerate(left) if _cents(x) == _cents(a)), None)
        if hit is None:
            return [_r(rest / 100)]
        left.pop(hit)
    return left


# ---------- actions (the caller commits) ----------

def _lines_of(con, st, ids):
    """The statement's lines with the ids given, refusing any id that isn't one of its lines."""
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise ReconError("Those lines couldn't be read.")
    found = {l["id"]: l for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ?", (st["id"],))}
    if any(i not in found for i in ids):
        raise ReconError("A line chosen isn't on this statement, so nothing was changed.")
    return [found[i] for i in dict.fromkeys(ids)]


# ---------- the lock: a signed-off month ----------

class Locked(ReconError):
    """A change refused because it would change a month that is signed off (locked)."""


def lock_words(st, what):
    return (f"{st['label']} {db.month_label(st['month'])} is marked reconciled and locked, so {what}. "
            "Reopen the month on Bank and reconciliation first (it asks for a reason).")


def refuse_locked(con, statement_ids, what="its bank lines can't change"):
    """Refuses (Locked) when any of these statements is signed off: a signed-off month is locked until it is reopened."""
    ids = sorted({int(i) for i in statement_ids if i})
    for sid in ids:
        st = con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = ?", (sid,)).fetchone()
        if st and st["reconciled_at"]:
            raise Locked(lock_words(st, what))


def refuse_locked_lines(con, line_ids, what="its bank lines can't be linked, explained, confirmed or undone"):
    """Refuses (Locked) a change to bank lines of a signed-off month."""
    ids = [int(i) for i in line_ids if i]
    if not ids:
        return
    sids = {r[0] for r in con.execute(f"SELECT DISTINCT statement_id FROM statement_lines WHERE id IN ({','.join('?' * len(ids))})", ids)}
    refuse_locked(con, sids, what)


def is_locked(st):
    return bool(st and st["reconciled_at"])


def book_source(con, ent, acct):
    """'sql' when the account's books are the company's SQL cash book, else 'payments' (the payments recorded here)."""
    return "sql" if ent["uses_sql"] and acct["id"] == _primary(con, ent) else "payments"


BANK_FIELDS = ("account_id", "paid_date", "amount", "direction", "currency")


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 0.005
    return (a if a not in ("", None) else None) == (b if b not in ("", None) else None)


def carried_signed(con, acct_id, month):
    """The statements of later months of the account that are signed off and whose books carry on from this month's
    closing (the account's books have an opening at or before the month, and none is typed in between): a change to
    this month's books changes their opening. Their ids."""
    anchors = sorted(r[0] for r in con.execute("SELECT month FROM book_openings WHERE account_id = ?", (acct_id,)))
    if not any(a <= month for a in anchors):
        return []  # no books run through this month, so nothing carries on from it
    nxt = next((a for a in anchors if a > month), None)
    return [r[0] for r in con.execute("""SELECT id FROM statements WHERE account_id = ? AND month > ? AND (? IS NULL OR month < ?)
                                         AND reconciled_at IS NOT NULL ORDER BY month""", (acct_id, month, nxt, nxt))]


def book_month_locked(con, acct_id, month):
    """The signed-off statements a change to the account's books in this month would change: the month's own, and the
    later ones carrying on from it. Their ids (empty when none)."""
    st = _stmt(con, acct_id, month)
    return ([st["id"]] if st and st["reconciled_at"] else []) + carried_signed(con, acct_id, month)


def signed_figures(con, scope=None):
    """What every signed-off statement's book side is now, for a change that isn't to one payment or line (Setup's bank
    accounts, the first month tracked, a book opening) to compare after: {statement id: (book source, before tracking,
    book state, opening, in, out, closing)}, whatever the book source (an SQL cash book's opening too). scope: {account
    id: the earliest month}, only those accounts' statements from that month on (None: every one)."""
    out = {}
    rows = con.execute("""SELECT s.id, s.month, s.account_id FROM statements s WHERE s.reconciled_at IS NOT NULL
                          ORDER BY s.account_id, s.month""").fetchall()
    by = {}
    for r in rows:
        if scope is None or (r["account_id"] in scope and r["month"] >= scope[r["account_id"]]):
            by.setdefault(r["account_id"], []).append(r)
    for aid, sts in by.items():
        a = _acct(con, aid)
        ent = _ent(con, a["entity_id"]) if a else None
        if not a or not ent:
            continue
        table = book_table(con, ent, a, sts[-1]["month"])
        for st in sts:
            b = table.get(st["month"]) or {"state": "needs_opening"}
            src = book_source(con, ent, a)
            # before tracking matters to the SQL cash book only (its receipts and payments count by listing amounts then)
            out[st["id"]] = (src, src == "sql" and bool(db.before_tracking(ent, st["month"])), b["state"],
                             b.get("opening"), b.get("in"), b.get("out"), b.get("closing"))
    return out


# ---------- the central guard: a signed-off month's figures never change ----------

# The tables whose rows the guard reads the audit trail of, to find the accounts a transaction touched.
GUARD_TBLS = ("payments", "statement_lines", "statement_line_payments", "statements", "book_openings", "accounts", "entities",
              "recon_pairs")
# A payment's columns the books read: a change to any other (notes, a reference) touches no book.
_PAY_KEYS = ("id", "entity_id", "account_id", "paid_date", "amount", "direction", "currency")
_ALL = "0000-00"  # every month of the account


def _touched(con, since):
    """The accounts the transaction in progress wrote something their books or lines depend on, read from the audit
    trail's rows after since: {account id: the earliest month touched (_ALL for every month)}. A payment touches the
    account it is on, before and after (or, with none, the company's accounts in its currency) from its paid month; a
    line or link its statement's account from the earlier of its date and its statement's month; a statement, book
    opening or pair its account from its month; a change to an account or a company every account of that company.
    None when the trail isn't kept here (old records): then every account counts."""
    if not getattr(con, "audited", lambda: False)() or not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit\\_%\\_i' ESCAPE '\\'").fetchone():
        return None
    # Worked out once per transaction and carried on from the last row read (a bulk step asks again after each item):
    # started afresh when the transaction is another, or rows read before may be gone. A rollback to a savepoint takes
    # rows back and their ids are used again, so rows at or below the last id read could be new ones: the connection's
    # rollbacks are watched (_watch_rollbacks), and the last row read must still be the very same row (its fingerprint:
    # id, time, table, row, change), or everything from the transaction's start is read again.
    since = since or 0
    _watch_rollbacks(con)
    top = con.execute("SELECT COALESCE(MAX(id), 0) FROM audit_row").fetchone()[0]
    cache = getattr(con, "_touch_cache", None)
    if (not cache or cache["since"] != since or top < cache["last"]
            or cache["last"] > since and _row_print(con, cache["last"]) != cache["print"]):
        cache = {"since": since, "last": since, "print": None, "out": {}, "gone": {}, "lines": {}}
    out, gone, lines = cache["out"], cache["gone"], cache["lines"]

    def add(aid, month):
        if aid is None:
            return
        month = month or _ALL
        out[aid] = min(out.get(aid, "9999-99"), month)

    def company(eid, currency=None):
        for r in con.execute("SELECT id FROM accounts WHERE entity_id = ? AND (? IS NULL OR currency = ?)", (eid, currency, currency)):
            add(r[0], _ALL if currency is None else None)

    rows = [(r["tbl"], *(json.loads(x) if x else {} for x in (r["before"], r["after"]))) for r in con.execute(
        f"SELECT tbl, before, after FROM audit_row WHERE id > ? AND id <= ? AND op IN ('insert', 'update', 'delete') "
        f"AND tbl IN ({','.join('?' * len(GUARD_TBLS))}) ORDER BY id", (cache["last"], top, *GUARD_TBLS))]
    # Statements and lines as the transaction saw them, so a line of a statement deleted with it (or a link of a line
    # deleted) is still placed: their before images.
    for t, b, a in rows:
        for x in (b, a):
            if x and x.get("id") and t == "statements":
                gone[x["id"]] = (x.get("account_id"), x.get("month"))
            if x and x.get("id") and t == "statement_lines":
                lines[x["id"]] = (x.get("statement_id"), x.get("txn_date"))

    def statement(sid, txn=None):
        st = con.execute("SELECT account_id, month FROM statements WHERE id = ?", (sid,)).fetchone() if sid else None
        acct, month = (st["account_id"], st["month"]) if st else gone.get(sid, (None, None))
        if acct:
            add(acct, min(month or "9999-99", (txn or month or "9999-99")[:7]))

    for t, b, a in rows:
        imgs = [x for x in (b, a) if x]
        if t == "payments":
            if b and a and all(b.get(k) == a.get(k) for k in _PAY_KEYS):
                continue
            for x in imgs:
                if not x.get("paid_date"):
                    continue
                if x.get("account_id"):
                    add(x["account_id"], x["paid_date"][:7])
                elif x.get("entity_id"):
                    for acc in con.execute("SELECT id FROM accounts WHERE entity_id = ? AND currency = ?", (x["entity_id"], x.get("currency") or "MYR")):
                        add(acc[0], x["paid_date"][:7])
        elif t == "statement_lines":
            for x in imgs:
                statement(x.get("statement_id"), x.get("txn_date"))
        elif t == "statement_line_payments":
            for x in imgs:
                l = con.execute("SELECT statement_id, txn_date FROM statement_lines WHERE id = ?", (x.get("line_id"),)).fetchone()
                sid, txn = (l["statement_id"], l["txn_date"]) if l else lines.get(x.get("line_id"), (None, None))
                statement(sid, txn)
        elif t in ("statements", "book_openings", "recon_pairs"):
            for x in imgs:
                add(x.get("account_id"), x.get("month"))
        elif t == "accounts":
            for x in imgs:
                add(x.get("id"), _ALL)
                if x.get("entity_id"):
                    company(x["entity_id"])
        elif t == "entities":
            for x in imgs:
                if x.get("id"):
                    company(x["id"])
    cache["last"], cache["print"] = top, (_row_print(con, top) if top > since else None)
    try:
        con._touch_cache = cache
    except AttributeError:
        pass
    return dict(out)


def _row_print(con, row_id):
    """What makes one audit row that very row, to tell it from a row written with its id after a rollback."""
    r = con.execute("SELECT id, at, tbl, row_key, op, before, after FROM audit_row WHERE id = ?", (row_id,)).fetchone()
    return tuple(r) if r else None


def _watch_rollbacks(con):
    """Forgets what the guard read on this connection whenever it runs a ROLLBACK, of the whole transaction or to a
    savepoint, however it is run (a cursor, executemany, plain SQL): SQLite's statement trace sees every one."""
    if getattr(con, "_rollback_watch", False):
        return
    ref = weakref.ref(con)

    def seen(sql):
        if sql and sql.lstrip()[:8].upper() == "ROLLBACK":
            c = ref()
            if c is not None:
                c._touch_cache = None
    try:
        con.set_trace_callback(seen)
        con._rollback_watch = True
    except (AttributeError, sqlite3.ProgrammingError):  # a plain or closed connection: the fingerprint still checks
        pass


def guard_reset(con):
    """After a ROLLBACK TO: the rows the guard read since may be gone, and their ids used again; it reads afresh."""
    try:
        con._touch_cache = None
    except AttributeError:
        pass

def guard_figures(con, scope=None):
    """What a signed-off statement holds, for the guard to compare: {statement id: (reconciled_at, figures)}, for the
    accounts in scope ({account id: the earliest month}: only their statements from that month on; None: every one).
    figures: the book source, before tracking (for an SQL cash book, whose receipts and payments count by listing
    amounts then), for books kept here the book state, opening, in, out, closing and every entry the month's books count
    with its amount (an SQL cash book's figures move with SQL itself, asked to be confirmed again, so they aren't held
    here), and on both every line (its payment, status, note, confirmation) and every link of a line to a payment."""
    out = {}
    if scope is not None and not scope:
        return out
    rows = con.execute("SELECT id, month, account_id, reconciled_at FROM statements WHERE reconciled_at IS NOT NULL "
                       "ORDER BY account_id, month").fetchall()
    by = {}
    for r in rows:
        if scope is None or (r["account_id"] in scope and r["month"] >= scope[r["account_id"]]):
            by.setdefault(r["account_id"], []).append(r)
    links = db.line_links(con)
    for aid, sts in by.items():
        a = _acct(con, aid)
        ent = _ent(con, a["entity_id"]) if a else None
        if not a or not ent:
            continue
        src = book_source(con, ent, a)
        table = book_table(con, ent, a, sts[-1]["month"]) if src == "payments" else {}
        for st in sts:
            b = table.get(st["month"]) or {"state": "needs_opening"}
            fig = (src, src == "sql" and bool(db.before_tracking(ent, st["month"])))
            if src == "payments":
                fig += (b["state"], b.get("opening"), b.get("in"), b.get("out"), b.get("closing"),
                        tuple(sorted((i["kind"], i["id"], i["amount"]) for i in (b.get("movements") or {}).get("items", []))))
            fig += (tuple(tuple(x) for x in con.execute(
                        "SELECT id, payment_id, status, COALESCE(note, ''), confirmed_at IS NOT NULL FROM statement_lines "
                        "WHERE statement_id = ? ORDER BY id", (st["id"],))),
                    tuple(tuple(x) for x in con.execute(
                        f"SELECT line_id, payment_id, amount FROM {links} WHERE statement_id = ? ORDER BY line_id, payment_id", (st["id"],))))
            out[st["id"]] = (st["reconciled_at"], fig)
    return out


class _Guard:
    """The backstop of the lock, at the commit every write of a request goes through (audit.Connection): a statement
    signed off before the transaction and still signed off with the same sign-off after it must hold exactly the same
    figures. A sign-off or a reopen changes the sign-off itself, so it is never caught; pinning payments to the account
    that already counted them moves no figure. Anything else that would move one is refused, the whole transaction
    rolled back, whatever route it came from. Only the accounts the transaction touched are worked out (_touched, from
    the audit trail, so a write through a cursor or any statement form is seen too), each from the earliest month
    touched; "before" is read from the records as last committed, through a read-only connection."""

    def check(self, con):
        hit = _guard_hit(con)
        if hit:
            raise Locked(lock_words(hit, "this change can't be saved: it would change the figures of that month"))


GUARD = _Guard()


def _committed():
    """A read-only connection to records.db as last committed (the transaction in progress isn't seen)."""
    import sqlite3
    from pathlib import Path
    from .config import DB_PATH
    r = sqlite3.connect(f"file:{Path(DB_PATH).as_posix()}?mode=ro", uri=True, timeout=5)
    r.row_factory = sqlite3.Row
    return r


def _guard_hit(con):
    """The first signed-off statement (by month) of the accounts the transaction touched whose figures differ from the
    records as last committed, as a row with the account's label; or None."""
    import sqlite3
    scope = _touched(con, getattr(con, "_mark", 0))
    if scope is not None and not scope:
        return None
    # Nothing signed off among those statements (as the transaction sees them, and no statement's sign-off touched):
    # nothing to compare.
    stmts_touched = con.execute("SELECT 1 FROM audit_row WHERE id > ? AND tbl = 'statements' LIMIT 1", (getattr(con, "_mark", 0),)).fetchone()
    if scope is not None and not stmts_touched and not any(r["month"] >= scope[r["account_id"]] for r in con.execute(
            f"SELECT account_id, month FROM statements WHERE reconciled_at IS NOT NULL AND account_id IN ({','.join('?' * len(scope))})",
            tuple(scope))):
        return None
    try:
        r = _committed()
        try:
            before = guard_figures(r, scope)
        finally:
            r.close()
    except sqlite3.OperationalError as ex:
        # The records as last committed can't be read just now (another program holds them): the guard never fails a
        # change for its own sake. The per-route checks of the lock still applied; this is said in the activity log.
        db.log(con, f"The bank reconciliation lock's final check couldn't read the records ({ex}); the change was saved on "
                    "the checks made along the way")
        return None
    if not before:
        return None
    now = guard_figures(con, scope)
    # A sign-off changes only by sign_off, sign_off_before_tracking and reopen (they name the statement on the
    # connection: _allow); any other way a signed-off month loses or changes its sign-off is refused like a figure.
    # Allowed: a statement whose sign-off is now exactly what the app's own sign-off or reopen wrote (_allow); a later
    # write over it in the same transaction makes it another change, refused like any other.
    allowed = getattr(con, "_recon_signoffs", None) or {}
    hit = [sid for sid, (at, fig) in before.items()
           if (sid not in now or now[sid][0] != at) and not (sid in allowed and (now[sid][0] if sid in now else None) == allowed[sid])
           or sid in now and now[sid][0] == at and now[sid][1] != fig]
    if not hit:
        return None
    return con.execute("""SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id
                          WHERE s.id IN (SELECT value FROM json_each(?)) ORDER BY s.month LIMIT 1""", (json.dumps(hit),)).fetchone()


def _allow(con, statement_id):
    """Says on the connection, right after the app's own sign-off or reopen wrote it, that this statement's sign-off is
    now this value (its reconciled_at, None once reopened): the guard lets exactly that through, for this transaction
    (audit.Connection forgets it at the commit or a rollback)."""
    at = con.execute("SELECT reconciled_at FROM statements WHERE id = ?", (statement_id,)).fetchone()
    try:
        con._recon_signoffs = {**(getattr(con, "_recon_signoffs", None) or {}), statement_id: at[0] if at else None}
    except AttributeError:  # a plain sqlite3 connection (no guard on it either)
        pass


def guard_ok(con):
    """For a bulk step tried inside a savepoint (one match, one link of an import): False when what the transaction did
    so far changes a signed-off month's figures, so the caller undoes just that step. True on a connection without the
    guard."""
    return getattr(con, "guard", None) is None or _guard_hit(con) is None


def sole_map(con):
    """{(company id, currency): the company's one account in that currency (sole_account), or None} for every company
    and currency it has accounts in."""
    out = {}
    for r in con.execute("SELECT entity_id, currency, COUNT(*) AS n, MIN(id) AS id FROM accounts GROUP BY entity_id, currency"):
        out[(r["entity_id"], r["currency"])] = r["id"] if r["n"] == 1 else None
    return out


def pin_no_account(con, before_sole, before_ids):
    """After a Setup change to bank accounts: the payments with no account of each company and currency whose one
    account (before_sole) no longer counts them (another account in that currency was added, put back or switched to
    it) are set to that account, where their books already counted them, so no book figure moves. Logged. before_ids:
    the account ids there were before, to name the new ones. Returns how many payments were set."""
    now = sole_map(con)
    total = 0
    for (eid, cur), acct_id in before_sole.items():
        if not acct_id or now.get((eid, cur)) == acct_id or not _acct(con, acct_id):
            continue
        n = con.execute("UPDATE payments SET account_id = ? WHERE entity_id = ? AND account_id IS NULL AND COALESCE(currency, 'MYR') = ?",
                        (acct_id, eid, cur)).rowcount
        if n:
            new = [r["label"] for r in con.execute(
                f"""SELECT label FROM accounts WHERE entity_id = ? AND currency = ? AND id NOT IN ({','.join('?' * len(before_ids)) or 'NULL'})
                    ORDER BY id""", (eid, cur, *before_ids))]
            label = _acct(con, acct_id)["label"]
            db.log(con, f"{n} payment{'s' if n > 1 else ''} with no bank account {'were' if n > 1 else 'was'} set to {label}, the account "
                        f"their books already counted them in, before {' and '.join(new) if new else 'the bank accounts were changed'}"
                        f"{' was added' if new else ''}")
            total += n
    return total


def refuse_figures_changed(con, before, what):
    """Refuses (Locked) when a signed-off statement's book side (signed_figures) is no longer what it was."""
    now = signed_figures(con)
    hit = sorted((sid for sid in before if now.get(sid) != before[sid]),
                 key=lambda sid: con.execute("SELECT month FROM statements WHERE id = ?", (sid,)).fetchone()[0])
    if hit:
        st = con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = ?", (hit[0],)).fetchone()
        raise Locked(lock_words(st, what))


def refuse_carried(con, acct_id, month, what):
    """Refuses (Locked) a change to an account's books in a month when a later signed-off month carries on from it."""
    refuse_locked(con, carried_signed(con, acct_id, month), what)


def payment_lock(con, before, after, what=None):
    """Refuses (Locked) a change to a payment's bank fields (BANK_FIELDS: its account, paid date, amount, direction,
    currency) that would change a signed-off month: before and after are the payment as it is and as it would be (dicts
    or rows with entity_id and those fields; None for a payment not there yet or being removed). Locked are: the months
    whose statement holds a line linked to it, and the months whose books count it (the payments recorded here, by its
    account, or the company's one account in its currency, and paid date, before and after). A payment moved to
    another account, or taken off its account, also refuses when either account's statement is signed off for a month
    its paid date falls in, whatever its books are (the move frees and finds its lines, as _account_moved does)."""
    before = dict(before) if before is not None else None
    after = dict(after) if after is not None else None
    if before and after and all(_same(before.get(k), after.get(k)) for k in BANK_FIELDS):
        return
    moved = before and after and not _same(before.get("account_id"), after.get("account_id"))
    only_moved = moved and all(_same(before.get(k), after.get(k)) for k in BANK_FIELDS if k != "account_id")
    new_id = after.get("account_id") if after else None
    if only_moved and not new_id and before.get("account_id") \
            and sole_account(con, before["entity_id"], before.get("currency") or "MYR") == before["account_id"]:
        return  # taken off the company's only account in its currency: its books and bank lines stay as they are
    sids = set()
    if before and before.get("id"):
        linked = con.execute(f"""SELECT DISTINCT k.statement_id, s.account_id FROM {db.line_links(con)} k JOIN statements s ON s.id = k.statement_id
                                 WHERE k.payment_id = ?""", (before["id"],)).fetchall()
        # Only moved: the lines freed are those on other accounts than the new one (taken off: on the old account).
        sids |= {r[0] for r in linked if not only_moved or (r[1] != new_id if new_id else r[1] == before.get("account_id"))}
    # The account whose books count a state: its own, or for one with no account the company's one account in its
    # currency. Put on that account from none (or the other way) it is counted in the same books: no book changes.
    eff = lambda x: x.get("account_id") or sole_account(con, x["entity_id"], x.get("currency") or "MYR")
    if moved and _same(eff(before), eff(after)):
        moved = False
        if only_moved:
            refuse_locked(con, sids, what or f"the bank account of {before.get('description') or 'this payment'} can't change")
            return
    # A payment with no amount isn't in any month's books (movements counts amounts only), so its paid date moves none.
    states = [x for x in (before, after) if x and x.get("amount") is not None]
    months = [x["paid_date"][:7] for x in states if x.get("paid_date")]
    carried = []
    for x in states:
        acct_id = x.get("account_id") or sole_account(con, x["entity_id"], x.get("currency") or "MYR")
        if not acct_id:
            continue
        a = _acct(con, acct_id)
        if not a:
            continue
        mine = months if moved else ([x["paid_date"][:7]] if x.get("paid_date") else [])
        if book_source(con, _ent(con, a["entity_id"]), a) != "payments":
            continue  # the SQL cash book's figures come from SQL, not from the payment (its lines are checked above)
        books_here = True
        for m in mine:
            st = _stmt(con, acct_id, m)
            if st:
                sids.add(st["id"])
            if books_here:  # a later month carrying on from this one's closing changes with it
                carried.extend((m, sid) for sid in carried_signed(con, acct_id, m))
    desc = (before or after or {}).get("description") or "this payment"
    refuse_locked(con, sids, what or f"the bank account, paid date and amount of {desc} can't change")
    for m, sid in carried:
        refuse_locked(con, [sid], f"{desc} can't change in {db.month_label(m)}, whose closing balance it carries on from")


def line_changed(con, line_ids):
    """A bank line's link or explanation changed or was taken off: its confirmation goes (logged). A signed-off month is
    locked, so a change to one of its lines is refused before it is made (refuse_locked_lines); a line of one reaching
    here is refused too, and the caller rolls back."""
    refuse_locked_lines(con, line_ids)
    done = {}
    for lid in line_ids:
        l = con.execute("SELECT l.id, l.statement_id, l.confirmed_at FROM statement_lines l WHERE l.id = ?", (lid,)).fetchone()
        if not l:
            continue
        if l["confirmed_at"]:
            con.execute("UPDATE statement_lines SET confirmed_at = NULL WHERE id = ?", (lid,))
            done[l["statement_id"]] = done.get(l["statement_id"], 0) + 1
    for sid, n in done.items():
        st = con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = ?", (sid,)).fetchone()
        db.log(con, f"Cleared the confirmation of {n} bank line{'s' if n > 1 else ''} on {_name(st, st['month'])}: changed")


def sole_account(con, entity_id, currency):
    """The account whose books count the company's payments with no account in this currency, by the rule movements
    uses: its one account in that currency (stopped ones counted too), as the accounts are now; None when it has none
    or several (then no book counts them)."""
    rows = con.execute("SELECT id FROM accounts WHERE entity_id = ? AND currency = ?", (entity_id, currency)).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def recheck(con, account_ids, months, why):
    """The books of these accounts would change in these months (a payment moved from one bank account to another):
    refused (Locked) when any of their statements for those months is signed off, as the month is locked. Until slice 4
    this took the sign-off away; a locked month is now reopened, with a reason, before anything in it changes."""
    sids = []
    for aid in dict.fromkeys(a for a in account_ids if a):
        for month in sorted(set(m for m in months if m)):
            st = _stmt(con, aid, month)
            if st:
                sids.append(st["id"])
    refuse_locked(con, sids, f"it can't change ({why})")


def _confirm(con, l):
    """Confirm one line (1 when it was not confirmed before)."""
    if not l["payment_id"] and l["status"] == "unmatched":
        raise ReconError(f"The line of {db.short_day(l['txn_date'])} ({l['amount']:,.2f}) is still to explain, so it can't be confirmed.")
    if l["confirmed_at"]:
        return 0
    con.execute("UPDATE statement_lines SET confirmed_at = ? WHERE id = ?", (db.now(), l["id"]))
    return 1


def confirm_lines(con, st, ids):
    """A person confirms lines that are linked or explained. Returns how many were newly confirmed. A line whose bank date
    differs from the voucher's or payment's is refused: it is confirmed with its tick (apply)."""
    refuse_locked(con, [st["id"]], "its lines can't be confirmed")
    a = _acct(con, st["account_id"])
    lines = _lines_of(con, st, ids)
    for l in lines:
        gap = date_gap(con, l, l["payment_id"])
        if gap[0] and not l["confirmed_at"]:
            raise ReconError(f"The bank date of {db.short_day(l['txn_date'])} ({l['amount']:,.2f}) differs by {gap[0]} day{'s' if gap[0] > 1 else ''} "
                             f"from the {gap[2]} date. Select the row and tick \"keep the {gap[2]} date\" to confirm it.")
    new = sum(_confirm(con, l) for l in lines)
    if new:
        db.log(con, f"Confirmed {new} bank line{'s' if new > 1 else ''} on {_name(a, st['month'])}")
    return new


def confirm_matched(con, st):
    """Confirm every matched or explained line not confirmed yet, except those whose bank date differs from the voucher's
    or payment's: each of those needs its own tick (apply). Returns (confirmed, left for a date tick)."""
    refuse_locked(con, [st["id"]], "its lines can't be confirmed")
    todo, skipped = [], 0
    for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ? AND confirmed_at IS NULL ORDER BY line_no", (st["id"],)):
        if l["payment_id"] or l["status"] != "unmatched":
            if date_gap(con, l, l["payment_id"])[0]:
                skipped += 1
            else:
                todo.append(l["id"])
    return (confirm_lines(con, st, todo) if todo else 0), skipped


def apply_rows(con, ent, st, rows, checked, change):
    """Apply the rows chosen on the review screen, all or nothing (the caller rolls back on an error). Each row is a
    line_id and what it is: payment_id (link it; the link it already has stays), create_payment {description, category},
    no_docs (with note), or nothing for a line already linked or explained, which is just confirmed. keep_date: the tick
    needed when the bank's date differs from the voucher's or payment's date (the payment keeps that date, the bank's
    doesn't replace it). change(con, line, body) is the endpoint's own way to link, create or explain a line.
    Returns {linked, created, explained, confirmed}. A signed-off month is locked: refused."""
    refuse_locked(con, [st["id"]], "its lines can't be linked, explained, confirmed or undone")
    if not checked:
        raise ReconError("Tick \"I've checked these rows\" first.")
    if not isinstance(rows, list) or not rows:
        raise ReconError("Select at least one row.")
    a = _acct(con, st["account_id"])
    lines = {l["id"]: l for l in _lines_of(con, st, [r.get("line_id") for r in rows if isinstance(r, dict)])}
    if len(lines) != len(rows):
        raise ReconError("Each row must name a line of this statement, once.")
    plan = []
    for r in rows:
        l = lines[int(r["line_id"])]
        label = f"the line of {db.short_day(l['txn_date'])} ({l['amount']:,.2f})"
        if (r.get("create_payment") or r.get("no_docs")) and l["payment_id"]:
            raise ReconError(f"{label[0].upper() + label[1:]} is already linked to a payment: undo that first to explain it another way.")
        if r.get("create_payment"):
            cp = r["create_payment"]
            if not isinstance(cp, dict) or not str(cp.get("description") or "").strip():
                raise ReconError(f"Give the payment for {label} a description.")
            plan.append((l, {"create_payment": {"description": str(cp["description"]).strip(), "category": str(cp.get("category") or "other")}}, None))
        elif r.get("no_docs"):
            plan.append((l, {"status": "no_docs", "note": str(r.get("note") or "").strip() or None}, None))
        elif r.get("payment_id"):
            try:
                pid = int(r["payment_id"])
            except (TypeError, ValueError):
                raise ReconError(f"The payment chosen for {label} couldn't be read.")
            p = con.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
            if not p or p["entity_id"] != ent["id"] or p["account_id"] not in (None, st["account_id"]):
                raise ReconError(f"The payment chosen for {label} isn't one of this account's payments.")
            plan.append((l, {"payment_id": pid} if l["payment_id"] != pid else None, pid))
        elif l["payment_id"] or l["status"] != "unmatched":
            plan.append((l, None, l["payment_id"]))
        else:
            raise ReconError(f"Choose what {label} is, or leave it unselected.")
    # The date tick is checked for every row before anything changes; a line already confirmed and left as it is had
    # its tick when it was confirmed.
    kept = {int(r["line_id"]) for r in rows if r.get("keep_date") is True}
    # A line already confirmed, left as it is and not ticked is passed over by the date step too: it changes nothing,
    # not even the payment's paid date (a voucher linked after the line was confirmed doesn't move it without a tick).
    left = {l["id"] for l, body, pid in plan if body is None and l["confirmed_at"] and l["id"] not in kept}
    for l, body, pid in plan:
        gap, when, kind = date_gap(con, l, pid)
        if gap and l["id"] not in kept and l["id"] not in left:
            what = "voucher" if kind == "voucher" else "payment"
            raise ReconError(f"The bank date of {db.short_day(l['txn_date'])} ({l['amount']:,.2f}) differs by {gap} day{'s' if gap > 1 else ''} from the "
                             f"{what} date, {db.short_day(when)}. Tick \"keep the {what} date\" on that row to apply it.")
    n = {"linked": 0, "created": 0, "explained": 0, "confirmed": 0}
    for l, body, pid in plan:
        if body:
            change(con, l, body)
            n["created" if "create_payment" in body else "linked" if "payment_id" in body else "explained"] += 1
        if l["id"] in left:
            continue
        fresh = con.execute("SELECT * FROM statement_lines WHERE id = ?", (l["id"],)).fetchone()
        gap, when, kind = date_gap(con, fresh, fresh["payment_id"])
        if gap and kind == "voucher":
            # The tick says keep the voucher's date: linking gave the payment the bank's. A paid date that would change
            # a signed-off month's books is refused (the caller rolls back).
            was = con.execute("SELECT * FROM payments WHERE id = ?", (fresh["payment_id"],)).fetchone()
            con.execute("UPDATE payments SET paid_date = ?, paid_source = 'sql' WHERE id = ?", (when, fresh["payment_id"]))
            payment_lock(con, was, con.execute("SELECT * FROM payments WHERE id = ?", (fresh["payment_id"],)).fetchone())
        n["confirmed"] += _confirm(con, fresh)
    db.log(con, f"Applied {len(plan)} row{'s' if len(plan) > 1 else ''} on {_name(a, st['month'])} (checked by a person): "
                f"{n['linked']} linked, {n['created']} payment{'s' if n['created'] != 1 else ''} created, {n['explained']} explained, "
                f"{n['confirmed']} confirmed. Nothing was posted to SQL Account")
    return n


def _has_signoff_cols(con):
    return "sign_note" in {r[1] for r in con.execute("PRAGMA table_info(statements)")}


def _clean_text(v, limit, what):
    v = (v or "").strip() if isinstance(v, str) or v is None else None
    if v is None:
        raise ReconError(f"The {what} couldn't be read.")
    if len(v) > limit:
        raise ReconError(f"Keep the {what} to {limit} characters.")
    return v


def sign_note_lines(con, ent, acct, month, s=None):
    """The note the app writes at sign-off, as the month stands: each confirmed No money moved pair with its reason and
    amounts, each line explained without documents, and anything left as a reconciling item. A list of sentences."""
    s = s or month_summary(con, ent, acct, month)
    st = _stmt(con, acct["id"], month)

    def amt(n):
        return ("+" if n > 0 else "−") + f"{abs(n):,.2f}"
    pr = [p for p in s["pairs"] if p["confirmed_at"]]
    out = ["No money moved: " + (" ".join(
        " and ".join(f"{d['ref'] or d['description']} {d['description'] if d['ref'] else ''} {amt(d['amount'])}".replace("  ", " ")
                     for d in p["docs"]) + f", net nil. Reason: {p['reason'].strip().rstrip('.')}." for p in pr) if pr else "none.")]
    nd = con.execute("""SELECT * FROM statement_lines WHERE statement_id = ? AND status = 'no_docs' AND payment_id IS NULL ORDER BY line_no""",
                     (st["id"],)).fetchall() if st else []
    out.append("Explained without documents: " + ("; ".join(
        f"{db.short_day(l['txn_date'])} {l['description'].replace(' | ', ' · ')} {amt(l['amount'])}" + (f", {l['note']}" if l["note"] else "")
        for l in nd) + "." if nd else "none."))
    left = [f"{db.short_day(x['date'])} {(x.get('ref') + ' ') if x.get('ref') else ''}{x['description']} {amt(x['amount'])}, {x['why'][0].lower() + x['why'][1:]}"
            for x in s["books_only"]] + [f"{db.short_day(x['date'])} {x['description'].replace(' | ', ' · ')} {amt(x['amount'])}, "
                                         f"{x['why'][0].lower() + x['why'][1:]}" for x in s["bank_only"] if not x["why"].startswith(("No payment needed", "No documents needed"))]
    out.append("Reconciling items left: " + ("; ".join(left) + "." if left else "none."))
    return out


def sign_off(con, ent, st, note=None, prepared_by=None):
    """Mark the statement reconciled: it adds up, every line is confirmed, every No money moved pair is nil and
    confirmed, and the books agree with the bank. The month is locked from then on. Kept with it: the note the app
    writes as the month stands (sign_note_lines), the optional free note and the name of who prepared it (declared, not
    verified)."""
    a = _acct(con, st["account_id"])
    if st["reconciled_at"]:
        raise ReconError(f"{_name(a, st['month'])} is already marked reconciled.")
    note = _clean_text(note, 500, "note")
    prepared_by = _clean_text(prepared_by, 80, "Prepared by name")
    s = month_summary(con, ent, a, st["month"])
    if not s["can_sign"]:
        raise ReconError("Can't mark it reconciled yet: " + "; ".join(s["why_not"]) + ".")
    con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review', reconciled_note = ? WHERE id = ?",
                (db.now(), note or None, st["id"]))
    _allow(con, st["id"])  # the app's own sign-off: the lock's guard lets exactly this one through
    if _has_rule(con):  # signed off with receipts and payments counted by their bank lines
        con.execute("UPDATE statements SET book_rule_at = reconciled_at WHERE id = ?", (st["id"],))
    lines = sign_note_lines(con, ent, a, st["month"], s)
    if _has_signoff_cols(con):
        con.execute("UPDATE statements SET sign_note = ?, prepared_by = ? WHERE id = ?", (json.dumps(lines), prepared_by or None, st["id"]))
    db.log(con, f"Marked {_name(a, st['month'])} as reconciled: book closing {_money(s['book']['closing'], a['currency'])} "
                f"= bank closing {_money(st['closing'], a['currency'])}. The month is locked"
                + (f". Prepared by {prepared_by} (declared)" if prepared_by else "") + (f". Note: {note}" if note else "")
                + ". Sign-off note: " + " ".join(lines))


def later_signed(con, acct, month):
    """The first later month of the account that is signed off and carries on from this month's closing (no book
    opening typed in between), as its statement row with the account's label; or None. None too when the account's books
    don't run through this month (no opening at or before it): nothing carries on from it."""
    if not con.execute("SELECT 1 FROM book_openings WHERE account_id = ? AND month <= ?", (acct["id"], month)).fetchone():
        return None
    anchors = {r[0] for r in con.execute("SELECT month FROM book_openings WHERE account_id = ? AND month > ?", (acct["id"], month))}
    for st in con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.account_id = ? AND s.month > ? "
                          "ORDER BY s.month", (acct["id"], month)).fetchall():
        if any(month < m <= st["month"] for m in anchors):
            return None  # its books start afresh from an opening typed in after this month
        if st["reconciled_at"]:
            return st
    return None


def reopen(con, ent, st, reason):
    """Reopen a signed-off month, with a reason (required): the sign-off goes, so the month's lines can change again and
    it needs the sign-off again. Kept: the reopening and its reason, with the sign-off it undid (its date, how, notes and
    Prepared by), in recon_reopens and the activity log, and so in the audit trail. Refused while a later month of the
    account that carries on from this one's closing is signed off: that one is reopened first."""
    a = _acct(con, st["account_id"])
    reason = _clean_text(reason, 300, "reason")
    if not reason:
        raise ReconError("Say why you're reopening this month.")
    if not st["reconciled_at"]:
        raise ReconError(f"{_name(a, st['month'])} isn't marked as reconciled, so there is nothing to reopen.")
    later = later_signed(con, a, st["month"])
    if later:
        raise ReconError(f"{db.month_label(later['month'])} is marked reconciled and carries on from {db.month_label(st['month']).split(' ')[0]}'s "
                         f"closing balance, so this month can't be reopened on its own. Reopen {db.month_label(later['month'])} first.")
    keys = st.keys()
    was_note = st["sign_note"] if "sign_note" in keys else None
    was_by = st["prepared_by"] if "prepared_by" in keys else None
    if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'recon_reopens'").fetchone():
        con.execute("""INSERT INTO recon_reopens (statement_id, at, reason, was_at, was_how, was_note, was_sign_note, was_prepared_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (st["id"], db.now(), reason, st["reconciled_at"], st["reconciled_how"], st["reconciled_note"], was_note, was_by))
    extra = ", sign_note = NULL, prepared_by = NULL" if _has_signoff_cols(con) else ""
    con.execute(f"UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL{_rule_set(con)}{extra} WHERE id = ?",
                (st["id"],))
    _allow(con, st["id"])  # the app's own reopen: the lock's guard lets exactly this one through
    old = " ".join(json.loads(was_note)) if was_note else ""
    db.log(con, f"Reopened {_name(a, st['month'])}: {reason}. It was marked reconciled on {db.day_label(st['reconciled_at'][:10])}"
                f" ({st['reconciled_how'] or 'review'})" + (f" by {was_by} (declared)" if was_by else "")
                + (f"; its note: {st['reconciled_note']}" if st["reconciled_note"] else "") + (f"; its sign-off note: {old}" if old else "")
                + ". It needs the sign-off again")


def confirm_pair(con, ent, acct, month, key, reason, on=True):
    """Confirm (on) or unconfirm a No money moved pair of the month, with its reason (required to confirm; kept with the
    sign-off). Refused in a locked month, for a pair that isn't there now, and for one that isn't nil."""
    st = _stmt(con, acct["id"], month)
    if st:
        refuse_locked(con, [st["id"]], "its No money moved pairs can't change")
    if not _has_pairs(con):
        raise ReconError("The records need update 40 for No money moved pairs. Restart the app.")
    pair = next((p for p in no_money_pairs(con, ent, acct, month) if p["key"] == key), None)
    if not pair:
        raise ReconError("That pair isn't in this month's books any more, so nothing was changed.")
    reason = _clean_text(reason if reason is not None else pair["reason"], 300, "reason")
    title = " and ".join(d["ref"] or d["description"] for d in pair["docs"])
    if on:
        if not reason:
            raise ReconError("Give the pair a reason first: it is kept with the sign-off.")
        if not pair["nil"]:
            raise ReconError(f"The two entries don't cancel: {_money(abs(pair['net']), acct['currency'])} is left. A pair that isn't nil can't "
                             "be confirmed, and the remainder stays a difference to explain until the entry is corrected.")
    con.execute("""INSERT INTO recon_pairs (account_id, month, pair_key, reason, confirmed_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (account_id, month, pair_key) DO UPDATE SET reason = excluded.reason, confirmed_at = excluded.confirmed_at""",
                (acct["id"], month, key, reason or None, db.now() if on else None))
    db.log(con, (f"Confirmed the No money moved pair {title} on {_name(acct, month)}: {reason}" if on
                 else f"Took back the confirmation of the No money moved pair {title} on {_name(acct, month)}"))
    return {"title": title}


def confirm_book_change(con, ent, st):
    """The owner confirms again a month signed off before receipts and payments counted by their lines on the bank
    account, whose book figures that changed: the sign-off stays, now with the new figures (statements.book_rule_at),
    and the old and new figures are logged. Refused when nothing changed, or when the new figures no longer agree with
    the bank (the sign-off is then undone and the month reviewed)."""
    a = _acct(con, st["account_id"])
    if not st["reconciled_at"]:
        raise ReconError("This month isn't marked as reconciled.")
    s = month_summary(con, ent, a, st["month"])
    ch = s["book_changed"]
    if not ch:
        raise ReconError("Nothing to confirm: this month's book figures haven't changed since it was signed off.")
    if not s["can_reconfirm"]:
        raise ReconError(s["reconfirm_why"] or "The new book figures can't be confirmed.")
    con.execute("UPDATE statements SET book_rule_at = ? WHERE id = ?", (db.now(), st["id"]))
    cur, o, n = a["currency"], ch["old"], ch["new"]
    db.log(con, f"Confirmed again the reconciled sign-off of {_name(a, st['month'])}, now counting SQL's receipts and payments by their "
                f"lines on the bank account: in {_money(o['in'], cur)}, out {_money(o['out'], cur)}, closing {_money(o['closing'], cur)} "
                f"before; in {_money(n['in'], cur)}, out {_money(n['out'], cur)}, closing {_money(n['closing'], cur)} now")


def sign_off_before_tracking(con, ent, st, note, checked, prepared_by=None):
    """Mark a month before the company's first tracked month as reconciled: the statement adds up, the books agree
    with the bank or a note says why not, and a person ticks that it was reconciled outside this app. The month is
    locked from then on, as any month signed off."""
    a = _acct(con, st["account_id"])
    if st["reconciled_at"]:
        raise ReconError(f"{_name(a, st['month'])} is already marked reconciled.")
    if not db.before_tracking(ent, st["month"]):
        raise ReconError("Only a month before tracking began can be marked reconciled this way.")
    prepared_by = _clean_text(prepared_by, 80, "Prepared by name")
    if not checked:
        raise ReconError("Tick that this month was reconciled before tracking began.")
    if not adds_up(con, st):
        raise ReconError("The statement doesn't add up (opening plus lines is not the closing balance), so it can't be marked.")
    note = (note or "").strip()
    book = book_of(con, ent, a, st["month"])
    d = _difference(st, book)
    if not (d is not None and abs(d) <= TOL) and not note:
        raise ReconError("The books don't agree with the bank here, so say in a short note how it was reconciled.")
    con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'before tracking', reconciled_note = ? WHERE id = ?",
                (db.now(), note or None, st["id"]))
    _allow(con, st["id"])  # the app's own sign-off before tracking: the lock's guard lets exactly this one through
    if _has_signoff_cols(con) and prepared_by:
        con.execute("UPDATE statements SET prepared_by = ? WHERE id = ?", (prepared_by, st["id"]))
    db.log(con, f"Marked {_name(a, st['month'])} as reconciled before tracking" + (f": {note}" if note else "")
           + (f". Prepared by {prepared_by} (declared)" if prepared_by else "") + ". The month is locked")


def set_book_opening(con, ent, acct, month, amount):
    """Type the book balance an account starts the month with. Later months carry on from it. The amount must come as a
    number (text such as "25" or "25abc" is refused here, whatever the page did with it)."""
    try:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError
        amount = _r(amount)
        if not math.isfinite(amount) or abs(amount) > 1e12:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ReconError("Type the book balance as a number.")
    if not ("2015-01" <= month <= db.shift_month(date.today().strftime("%Y-%m"), 12)):
        raise ReconError("Choose the month the account's books start from: between January 2015 and a year from now.")
    if acct["entity_id"] != ent["id"]:
        raise ReconError("That account isn't this company's.")
    # The opening changes this month's books and every later month's up to the next opening typed: a signed-off one
    # among them is locked. One that moves no figure (the same amount again) is saved. The book side is compared
    # whatever the book source: guard_figures leaves an SQL cash book's figures out (they move with SQL), but a book
    # opening typed here moves them as well.
    scope = {acct["id"]: month}  # the account's signed-off months from this one on (this one included)
    before = signed_figures(con, scope)
    was = con.execute("SELECT amount FROM book_openings WHERE account_id = ? AND month = ?", (acct["id"], month)).fetchone()
    con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (account_id, month) DO UPDATE SET amount = excluded.amount, set_at = excluded.set_at",
                (acct["id"], month, amount, db.now()))
    now = signed_figures(con, scope)
    hit = sorted((con.execute("SELECT month FROM statements WHERE id = ?", (sid,)).fetchone()[0] for sid in before if now.get(sid) != before[sid]))
    if hit:
        raise Locked(lock_words({"label": acct["label"], "month": hit[0]}, "a book opening that changes it can't be saved"))
    db.log(con, f"Set the book opening of {acct['label']} for {db.month_label(month)} to {_money(amount, acct['currency'])}"
           + (f" (was {_money(was['amount'], acct['currency'])})" if was else ""))
