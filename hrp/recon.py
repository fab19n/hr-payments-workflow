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
import math
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


def why_not(con, ent, acct, month, st, counts, book):
    """What stops the month being signed off, as short phrases; empty when nothing does."""
    why = []
    if not adds_up(con, st):
        why.append("the statement doesn't add up (opening plus lines is not the closing balance)")
    if counts["to_explain"]:
        why.append(f"{counts['to_explain']} line{'s' if counts['to_explain'] > 1 else ''} to explain")
    if counts["to_confirm"]:
        why.append(f"{counts['to_confirm']} line{'s' if counts['to_confirm'] > 1 else ''} to confirm")
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
                     "gone_docs": mv.get("gone_docs") or 0})
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


def _lists(con, ent, acct, month, st, mv):
    """The lists of a reconciliation statement. books_only: what the books hold for the month that no line of this
    statement is linked to. bank_only: the statement's lines the month's books don't hold. Both with a note saying why.
    differ: payments the books and the statement both hold, for different amounts (a payment of 18,000 with only
    a line of 8,000 linked so far): {description, ref, book, bank, amount (bank minus book)}."""
    lines = con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall() if st else []
    on_stmt = {l["payment_id"] for l in lines if l["payment_id"]}
    in_books = {i["payment_id"] for i in mv["items"] if i["payment_id"]}
    bank_items = {i["line_id"] for i in mv["items"] if i.get("line_id")}  # charges and transfers counted from the statement
    books_only = []
    for i in mv["items"]:
        pid = i["payment_id"]
        if (pid and pid in on_stmt) or i.get("line_id"):
            continue
        if pid:
            elsewhere = con.execute(
                """SELECT s.month FROM statement_lines l JOIN statements s ON s.id = l.statement_id WHERE l.payment_id = ?
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
    for l in lines:
        if l["payment_id"]:
            bank_sum[l["payment_id"]] = bank_sum.get(l["payment_id"], 0) + l["amount"]
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
    books_only, bank_only, differ = _lists(con, ent, acct, month, st, mv)
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
           "book_changed": changed if signed else None, "can_reconfirm": False, "reconfirm_why": None}
    if not st:
        return out
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
        out["reconfirm_why"] = None if ok else (f"The new book closing differs from the bank by {_money(diff, acct['currency'])}: undo the "
                                                "sign-off and review the month." if diff is not None else "The book closing can't be worked out.")
    if book["state"] == "ok" and diff is not None:
        brought = _r(st["opening"] - book["opening"])
        b_out = _r(-sum(i["amount"] for i in books_only if i["amount"] < 0))
        b_in = _r(sum(i["amount"] for i in books_only if i["amount"] > 0))
        x_net = _r(sum(i["amount"] for i in bank_only))
        d_net = _r(sum(i["amount"] for i in differ))
        out["reconciliation"] = {"brought_forward": brought, "books_out": b_out, "books_in": b_in, "bank_net": x_net,
                                 "differ": d_net, "other": _r(diff - brought - b_out + b_in - x_net - d_net)}
    left = why_not(con, ent, acct, month, st, counts, book)
    out["why_not"], out["can_sign"] = left, not left
    # Before tracking: the statement adding up and (the books agreeing, or a note), the person's tick is asked for on top.
    out["can_sign_before_tracking"] = out["before_tracking"] and out["statement"]["adds_up"]
    out["book_matches"] = diff is not None and abs(diff) <= TOL
    return out


# ---------- the review of a statement ----------

def date_gap(con, line, payment_id):
    """(days, date, kind) between a bank line and the date the books hold for the payment: the SQL voucher's date
    (the one nearest the line's, kind 'voucher'), else a paid date typed in ('payment'). (0, None, None) when the books
    have no date of their own for it (a date that came from a bank line is the bank's)."""
    if not payment_id:
        return 0, None, None
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
    rows = []
    for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall():
        pid = l["payment_id"]
        row = {"id": l["id"], "line_no": l["line_no"], "txn_date": l["txn_date"], "description": l["description"], "amount": l["amount"],
               "balance": l["balance"], "status": l["status"], "note": l["note"], "confirmed_at": l["confirmed_at"],
               "state": "matched" if pid else "explained" if l["status"] == "no_docs" else "open",
               "payment_id": pid, "payment": None, "payment_desc": None, "vouchers": [], "suggestions": sugg.get(l["id"], []),
               "gap_days": 0, "book_date": None, "book_date_kind": None, "needs_date_tick": False}
        if pid:
            p = con.execute("SELECT id, description, month, amount, currency, paid_date, direction FROM payments WHERE id = ?", (pid,)).fetchone()
            row["payment"], row["payment_desc"] = dict(p), p["description"]
            row["vouchers"] = [dict(r) for r in con.execute(
                """SELECT doc_no, doc_date, doc_type FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')
                   ORDER BY doc_date""", (pid,))]
            row["gap_days"], row["book_date"], row["book_date_kind"] = date_gap(con, l, pid)
            row["needs_date_tick"] = bool(row["gap_days"]) and not l["confirmed_at"]  # a confirmed line had its tick then
        rows.append(row)
    pays = [dict(p) for p in con.execute(
        """SELECT p.id, p.month, p.description, p.amount, p.currency, p.direction, p.due_date, p.paid_date,
                  (SELECT SUM(ABS(s.amount)) FROM statement_lines s WHERE s.payment_id = p.id) AS linked,
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
        for r in con.execute(f"SELECT payment_id, amount FROM statement_lines WHERE payment_id IN ({','.join('?' * len(chunk))}) ORDER BY id", chunk):
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


def line_changed(con, line_ids, keep_before_tracking=False):
    """A bank line's link or explanation changed or was taken off: its confirmation goes, and the sign-off of its
    statement with it (logged when either was there). keep_before_tracking: a statement signed off before tracking
    keeps its sign-off (a payment moved to another account: its books are not reviewed here, as recheck says)."""
    done = {}
    for lid in line_ids:
        l = con.execute("SELECT l.id, l.statement_id, l.confirmed_at FROM statement_lines l WHERE l.id = ?", (lid,)).fetchone()
        if not l:
            continue
        if l["confirmed_at"]:
            con.execute("UPDATE statement_lines SET confirmed_at = NULL WHERE id = ?", (lid,))
            done.setdefault(l["statement_id"], [0, False])[0] += 1
        done.setdefault(l["statement_id"], [0, False])
    for sid, (n, _) in done.items():
        st = con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = ?", (sid,)).fetchone()
        if st["reconciled_at"] and not (keep_before_tracking and st["reconciled_how"] == "before tracking"):
            con.execute(f"UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL{_rule_set(con)} WHERE id = ?", (sid,))
            db.log(con, f"Removed the reconciled sign-off of {_name(st, st['month'])}: a bank line was changed"
                   + (f" ({n} confirmation{'s' if n > 1 else ''} cleared)" if n else ""))
        elif n:
            db.log(con, f"Cleared the confirmation of {n} bank line{'s' if n > 1 else ''} on {_name(st, st['month'])}: changed")


def sole_account(con, entity_id, currency):
    """The account whose books count the company's payments with no account in this currency, by the rule movements
    uses: its one account in that currency (stopped ones counted too), as the accounts are now; None when it has none
    or several (then no book counts them)."""
    rows = con.execute("SELECT id FROM accounts WHERE entity_id = ? AND currency = ?", (entity_id, currency)).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def recheck(con, account_ids, months, why):
    """The books of these accounts changed in these months (a payment moved from one bank account to another): the
    sign-off of each of their statements for those months goes, so the month is reviewed again (logged, with why). A
    month signed off before tracking keeps its state: its books are not reviewed here."""
    for aid in dict.fromkeys(a for a in account_ids if a):
        for month in sorted(set(m for m in months if m)):
            st = con.execute("SELECT s.*, a.label FROM statements s JOIN accounts a ON a.id = s.account_id "
                             "WHERE s.account_id = ? AND s.month = ?", (aid, month)).fetchone()
            if not st or not st["reconciled_at"] or st["reconciled_how"] == "before tracking":
                continue
            con.execute(f"UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL{_rule_set(con)} WHERE id = ?",
                        (st["id"],))
            db.log(con, f"Removed the reconciled sign-off of {_name(st, month)}: {why}")


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
    Returns {linked, created, explained, confirmed}."""
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
            # The tick says keep the voucher's date: linking gave the payment the bank's.
            con.execute("UPDATE payments SET paid_date = ?, paid_source = 'sql' WHERE id = ?", (when, fresh["payment_id"]))
        n["confirmed"] += _confirm(con, fresh)
    db.log(con, f"Applied {len(plan)} row{'s' if len(plan) > 1 else ''} on {_name(a, st['month'])} (checked by a person): "
                f"{n['linked']} linked, {n['created']} payment{'s' if n['created'] != 1 else ''} created, {n['explained']} explained, "
                f"{n['confirmed']} confirmed. Nothing was posted to SQL Account")
    return n


def sign_off(con, ent, st):
    """Mark the statement reconciled: it adds up, every line is confirmed, and the books agree with the bank."""
    a = _acct(con, st["account_id"])
    s = month_summary(con, ent, a, st["month"])
    if not s["can_sign"]:
        raise ReconError("Can't mark it reconciled yet: " + "; ".join(s["why_not"]) + ".")
    con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review', reconciled_note = NULL WHERE id = ?", (db.now(), st["id"]))
    if _has_rule(con):  # signed off with receipts and payments counted by their bank lines
        con.execute("UPDATE statements SET book_rule_at = reconciled_at WHERE id = ?", (st["id"],))
    db.log(con, f"Marked {_name(a, st['month'])} as reconciled: book closing {_money(s['book']['closing'], a['currency'])} "
                f"= bank closing {_money(st['closing'], a['currency'])}")


def undo_sign_off(con, st):
    a = _acct(con, st["account_id"])
    if not st["reconciled_at"]:
        raise ReconError("This month isn't marked as reconciled.")
    con.execute(f"UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL{_rule_set(con)} WHERE id = ?", (st["id"],))
    db.log(con, f"Undid the reconciled sign-off of {_name(a, st['month'])}")


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


def sign_off_before_tracking(con, ent, st, note, checked):
    """Mark a month before the company's first tracked month as reconciled: the statement adds up, the books agree
    with the bank or a note says why not, and a person ticks that it was reconciled outside this app."""
    a = _acct(con, st["account_id"])
    if not db.before_tracking(ent, st["month"]):
        raise ReconError("Only a month before tracking began can be marked reconciled this way.")
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
    db.log(con, f"Marked {_name(a, st['month'])} as reconciled before tracking" + (f": {note}" if note else ""))


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
    was = con.execute("SELECT amount FROM book_openings WHERE account_id = ? AND month = ?", (acct["id"], month)).fetchone()
    con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (account_id, month) DO UPDATE SET amount = excluded.amount, set_at = excluded.set_at",
                (acct["id"], month, amount, db.now()))
    db.log(con, f"Set the book opening of {acct['label']} for {db.month_label(month)} to {_money(amount, acct['currency'])}"
           + (f" (was {_money(was['amount'], acct['currency'])})" if was else ""))
