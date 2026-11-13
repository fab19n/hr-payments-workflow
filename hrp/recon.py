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
from datetime import date

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


def journal_moves(con, entity_id, dockeys, code):
    """What the pasted lines of each journal (by SQL's document key) move on the bank account whose GL code is given:
    {dockey: net amount, money in above 0}. A journal with no lines, no line on that code or a net of nothing isn't in it."""
    keys = sorted({str(k) for k in dockeys if k not in (None, "")})
    if not code or not keys or not con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sql_journal_lines'").fetchone():
        return {}
    got = con.execute(f"""SELECT dockey, ROUND(SUM(dr - cr), 2) AS net FROM sql_journal_lines WHERE entity_id = ? AND UPPER(TRIM(code)) = ?
                          AND dockey IN ({','.join('?' * len(keys))}) GROUP BY dockey""", (entity_id, code.strip().upper(), *keys)).fetchall()
    return {r["dockey"]: r["net"] for r in got if abs(r["net"]) >= TOL}


def journal_move(con, entity_id, dockey):
    """What one journal moves on the company's cash book account (see journal_moves), or None when it moves nothing there."""
    acct = cash_book_account(con, entity_id)
    return journal_moves(con, entity_id, [dockey], bank_gl_code(con, acct) if acct else None).get(str(dockey))


def movements(con, ent, acct, month):
    """What the books hold for the account in the month: {source ('sql' or 'payments'), listing (False when an SQL
    company has no cash book entry for the month: the listing isn't pasted), items [{kind, id, ref, date, description,
    amount (money in above 0, out below), payment_id, status, doc_type}], in, out, left_out (what an SQL listing holds
    that isn't a bank movement: {journals, invoices (customer refunds too), unknown (cash book entries with no direction)}}.
    SQL: every receipt (OR) and payment (PV) dated in the month, whatever its status here: an ignored correction is in
    SQL's books too. Customer invoices (IV) are left out: they move no bank balance by themselves. So is a journal (JV)
    whose bank side can't be told: its header carries only one total, so it counts only once its lines have been pasted
    (sql_journal_lines) and some of them are on the bank account's GL code (bank_gl_code); it then counts as the net of
    those lines, in or out, like a voucher. A company's other accounts have no SQL listing of their own and
    are worked out from payments, as a company that isn't in SQL is: every payment recorded for the account with a paid
    date in the month, plus the account's statement lines dated in the month that need no documents (bank charges and
    own-account transfers, marked by statements.classify or by a person): money the bank moved with nothing to record,
    counted as it stands on the statement (kind 'bank')."""
    if ent["uses_sql"] and acct["id"] == _primary(con, ent):
        # A voucher edited in SQL and pasted again is a row in a later paste; only the latest paste of a doc_no counts.
        # Rows of one paste all count (a voucher listed on several lines).
        rows = con.execute("""SELECT * FROM sql_entries e WHERE entity_id = ? AND substr(doc_date, 1, 7) = ?
                             AND NOT (COALESCE(doc_no, '') <> '' AND EXISTS (SELECT 1 FROM sql_entries n WHERE n.entity_id = e.entity_id
                                      AND n.doc_no = e.doc_no AND n.import_id > e.import_id)) ORDER BY doc_date, doc_no, id""",
                           (ent["id"], month)).fetchall()
        # A journal counts as the bank movement of its lines, so its sign gives the direction; one that moves nothing there stays out.
        # (Records not updated yet have no document keys, so no journal can have lines.)
        keyed = [r for r in rows if r["kind"] == "journal" and "dockey" in r.keys() and r["dockey"]]
        moves = journal_moves(con, ent["id"], [r["dockey"] for r in keyed], bank_gl_code(con, acct) if keyed else None)
        counted = {r["id"]: moves[r["dockey"]] for r in keyed if r["dockey"] in moves}
        items = []
        for r in rows:
            if r["id"] in counted:
                amount = counted[r["id"]]
            elif (r["kind"] or "payment") == "payment" and r["direction"] in ("in", "out"):
                amount = r["amount"] if r["direction"] == "in" else -r["amount"]
            else:
                continue
            items.append({"kind": "sql", "id": r["id"], "ref": r["doc_no"], "date": r["doc_date"], "description": r["description"] or r["payee"] or "",
                          "amount": _r(amount), "payment_id": r["payment_id"], "status": r["status"], "doc_type": r["doc_type"]})
        left = {"journals": sum(r["kind"] == "journal" and r["id"] not in counted for r in rows),
                "invoices": sum(r["kind"] == "invoice" for r in rows),
                "unknown": sum((r["kind"] or "payment") == "payment" and r["direction"] not in ("in", "out") for r in rows)}
        listing = any((r["kind"] or "payment") == "payment" for r in rows)
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
        left, listing, source = {"journals": 0, "invoices": 0, "unknown": 0}, True, "payments"
    return {"source": source, "listing": listing, "items": items,
            "in": _r(sum(i["amount"] for i in items if i["amount"] > 0)),
            "out": _r(-sum(i["amount"] for i in items if i["amount"] < 0)), "left_out": left}


def book_table(con, ent, acct, upto):
    """The book balance of the account for each month from its first book opening to the month upto: {month: {state:
    'ok' with opening, in, out, closing and the month's movements; or 'needs_listing' (an SQL month with nothing
    pasted, and every month after it up to the next opening typed)}}. A month before the first opening isn't in it."""
    anchors = {r["month"]: r["amount"] for r in con.execute(
        "SELECT month, amount FROM book_openings WHERE account_id = ? ORDER BY month", (acct["id"],))}
    out, bal, broken = {}, None, None
    m = min(anchors) if anchors else upto
    while anchors and m <= upto:
        if m in anchors:
            bal, broken = anchors[m], None  # an opening typed for a month starts the books afresh
        mv = movements(con, ent, acct, m)
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
        b["note"] = "Paste SQL listing" + ("" if b["month"] == month else f" for {db.month_label(b['month'])}")
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


def _signed(st, book):
    """True when the statement is signed off and still holds: one signed off by review stops counting when the books
    have moved since (an SQL listing pasted late, a payment changed) so that it no longer agrees with the bank."""
    if not st or not st["reconciled_at"]:
        return False
    d = _difference(st, book)
    return not (st["reconciled_how"] == "review" and d is not None and abs(d) > TOL)


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
    when it is. A month with no statement imported is 'statement not imported yet'."""
    acct = _acct(con, account_id)
    st = _stmt(con, account_id, month)
    if not st:
        return "statement not imported yet"
    book = book_of(con, ent, acct, month)
    if _signed(st, book):
        return None
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
    rows = []
    for m in mine:
        st = _stmt(con, acct["id"], m)
        book = book_of(con, ent, acct, m, table)
        counts = _counts(con, st["id"]) if st else None
        status = _status(st, counts, book, _signed(st, book))
        rows.append({"month": m, "label": db.month_label(m), "statement_id": st["id"] if st else None, "status": status,
                     "status_text": STATUS_WORDS[status], "bank_closing": st["closing"] if st else None,
                     "book_closing": book["closing"] if book["state"] == "ok" else None, "book_note": book["note"],
                     "reconciled_at": st["reconciled_at"] if st and status == "reconciled" else None,
                     "reconciled_how": st["reconciled_how"] if st and status == "reconciled" else None,
                     "document_id": st["document_id"] if st else None, "before_tracking": db.before_tracking(ent, m)})
    return {"account": {"id": acct["id"], "label": acct["label"], "currency": acct["currency"]}, "year": year, "years": years,
            "rows": rows, "openings": [dict(r) for r in con.execute(
                "SELECT month, amount FROM book_openings WHERE account_id = ? ORDER BY month", (acct["id"],))],
            "source": "SQL cash book" if ent["uses_sql"] and acct["id"] == _primary(con, ent) else "payments recorded here"}


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
    signed = _signed(st, book)
    status = _status(st, counts, book, signed)
    books_only, bank_only, differ = _lists(con, ent, acct, month, st, mv)
    diff = _difference(st, book)
    out = {"account": {"id": acct["id"], "label": acct["label"], "currency": acct["currency"]}, "month": month,
           "label": db.month_label(month), "status": status, "status_text": STATUS_WORDS[status],
           "before_tracking": db.before_tracking(ent, month), "uses_sql": bool(ent["uses_sql"]),
           "source": mv["source"], "left_out": mv["left_out"], "statement": None,
           "book": {k: book.get(k) for k in ("state", "opening", "in", "out", "closing", "note")},
           "bank_closing": None, "difference": diff, "lines": counts, "books_only": books_only, "bank_only": bank_only, "differ": differ,
           "reconciliation": None, "reconciled_at": None, "reconciled_how": None, "reconciled_note": None,
           "can_sign": False, "why_not": ["the statement isn't imported yet"]}
    if not st:
        return out
    lines = con.execute("SELECT amount FROM statement_lines WHERE statement_id = ?", (st["id"],)).fetchall()
    out["statement"] = {"id": st["id"], "opening": st["opening"], "closing": st["closing"], "document_id": st["document_id"],
                        "money_in": _r(sum(l["amount"] for l in lines if l["amount"] > 0)),
                        "money_out": _r(-sum(l["amount"] for l in lines if l["amount"] < 0)), "adds_up": adds_up(con, st)}
    out["bank_closing"] = st["closing"]
    if signed:
        out.update(reconciled_at=st["reconciled_at"], reconciled_how=st["reconciled_how"], reconciled_note=st["reconciled_note"])
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
    the suggestions for them; matched ones with the payment, its SQL voucher numbers and dates, and the days the bank's
    date differs from the voucher's or payment's), and the payments a line can be linked to."""
    acct = _acct(con, st["account_id"])
    summary = month_summary(con, ent, acct, st["month"])
    sugg = statements.suggest(con, ent["id"], st["id"])
    rows = []
    for l in con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall():
        pid = l["payment_id"]
        row = {"id": l["id"], "line_no": l["line_no"], "txn_date": l["txn_date"], "description": l["description"], "amount": l["amount"],
               "balance": l["balance"], "status": l["status"], "note": l["note"], "confirmed_at": l["confirmed_at"],
               "state": "matched" if pid else "explained" if l["status"] == "no_docs" else "open",
               "payment": None, "payment_desc": None, "vouchers": [], "suggestions": sugg.get(l["id"], []), "gap_days": 0, "book_date": None, "book_date_kind": None}
        if pid:
            p = con.execute("SELECT id, description, month, amount, currency, paid_date, direction FROM payments WHERE id = ?", (pid,)).fetchone()
            row["payment"], row["payment_desc"] = dict(p), p["description"]
            row["vouchers"] = [dict(r) for r in con.execute(
                """SELECT doc_no, doc_date, doc_type FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')
                   ORDER BY doc_date""", (pid,))]
            row["gap_days"], row["book_date"], row["book_date_kind"] = date_gap(con, l, pid)
        rows.append(row)
    pays = [dict(p) for p in con.execute(
        """SELECT p.id, p.month, p.description, p.amount, p.currency, p.direction, p.due_date, p.paid_date,
                  (SELECT SUM(ABS(s.amount)) FROM statement_lines s WHERE s.payment_id = p.id) AS linked,
                  CASE WHEN p.paid_source IN ('bank', 'sql') THEN NULL ELSE p.paid_date END AS typed_date
           FROM payments p WHERE p.account_id = ? AND p.month BETWEEN ? AND ? ORDER BY p.due_date, p.id""",
        (st["account_id"], db.shift_month(st["month"], -1), st["month"]))]
    for p in pays:  # the dates the books hold for it, so the page can tell when a bank date differs
        p["voucher_dates"] = [r["doc_date"] for r in con.execute(
            "SELECT doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')", (p["id"],))]
    return {"summary": summary, "lines": rows, "payments": pays, "statement_id": st["id"]}


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


def line_changed(con, line_ids):
    """A bank line's link or explanation changed or was taken off: its confirmation goes, and the sign-off of its
    statement with it (logged when either was there)."""
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
        if st["reconciled_at"]:
            con.execute("UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL WHERE id = ?", (sid,))
            db.log(con, f"Removed the reconciled sign-off of {_name(st, st['month'])}: a bank line was changed"
                   + (f" ({n} confirmation{'s' if n > 1 else ''} cleared)" if n else ""))
        elif n:
            db.log(con, f"Cleared the confirmation of {n} bank line{'s' if n > 1 else ''} on {_name(st, st['month'])}: changed")


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
    # The date tick is checked for every row before anything changes.
    kept = {int(r["line_id"]) for r in rows if r.get("keep_date") is True}
    for l, body, pid in plan:
        gap, when, kind = date_gap(con, l, pid)
        if gap and l["id"] not in kept:
            what = "voucher" if kind == "voucher" else "payment"
            raise ReconError(f"The bank date of {db.short_day(l['txn_date'])} ({l['amount']:,.2f}) differs by {gap} day{'s' if gap > 1 else ''} from the "
                             f"{what} date, {db.short_day(when)}. Tick \"keep the {what} date\" on that row to apply it.")
    n = {"linked": 0, "created": 0, "explained": 0, "confirmed": 0}
    for l, body, pid in plan:
        if body:
            change(con, l, body)
            n["created" if "create_payment" in body else "linked" if "payment_id" in body else "explained"] += 1
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
    db.log(con, f"Marked {_name(a, st['month'])} as reconciled: book closing {_money(s['book']['closing'], a['currency'])} "
                f"= bank closing {_money(st['closing'], a['currency'])}")


def undo_sign_off(con, st):
    a = _acct(con, st["account_id"])
    if not st["reconciled_at"]:
        raise ReconError("This month isn't marked as reconciled.")
    con.execute("UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL, reconciled_note = NULL WHERE id = ?", (st["id"],))
    db.log(con, f"Undid the reconciled sign-off of {_name(a, st['month'])}")


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
    """Type the book balance an account starts the month with. Later months carry on from it."""
    try:
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
