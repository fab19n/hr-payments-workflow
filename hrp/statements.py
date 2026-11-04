"""Reads Maybank statement PDFs and matches lines to payments.

Two layouts are handled:
- Maybank (Labuan current account, Master FCA): date line, description lines, then "amount+/- balance" on its own line.
- Maybank Islamic (AISB SME First Account-i): "date description amount+/- balance" on one line, with the rest of
  the description on indented lines below it, sometimes continuing after a page break.
Statements downloaded from Maybank2u Biz are encrypted without a password; pypdf opens them with `cryptography`.
"""
import io
import re

from pypdf import PdfReader

DATE_LINE = re.compile(r"^(\d{2})/(\d{2})\s+(.*)$")
AMOUNT_LINE = re.compile(r"^([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})(DR)?$")
INLINE_AMOUNT = re.compile(r"^(.*?)\s+([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})(DR)?$")
BEGIN = re.compile(r"BEGINNING BALANCE(?:\s+([A-Z]{3}))?\s*([\d,]+\.\d{2})?")
STMT_DATE = re.compile(r"^:?\s*(\d{2})/(\d{2})/(\d{2,4})\s*:?$")
ACCOUNT_NO = re.compile(r"^:?\s*(\d{12})$")
TOTAL = re.compile(r"^TOTAL (DEBITS?|CREDITS?)\s*:?(?:\s*([\d,]+\.\d{2}))?$")
ENDING = re.compile(r"^ENDING BALANCE\s*:?(?:\s*([\d,]+\.\d{2}))?$")
MONEY = re.compile(r"^[\d,]+\.\d{2}$")


def num(s):
    return float(s.replace(",", ""))


class StatementError(ValueError):
    pass


def parse_maybank(data):
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    raw = [l for l in text.splitlines() if l.strip()]
    lines = [l.strip() for l in raw]
    indented = [l[:1].isspace() for l in raw]
    info = {"account_number": None, "statement_date": None, "currency": "MYR", "opening": None,
            "closing": None, "total_debits": None, "total_credits": None, "lines": []}

    # A labelled number (": 123456789012") wins over a bare 12-digit one, which may be a biller's reference.
    labelled = [m.group(1) for l in lines if l.startswith(":") and (m := ACCOUNT_NO.match(l))]
    bare = [m.group(1) for l in lines if (m := ACCOUNT_NO.match(l))]
    info["account_number"] = (labelled or bare or [None])[0]
    for l in lines:
        if not info["statement_date"] and (m := STMT_DATE.search(l)):
            d, mo, y = m.groups()
            info["statement_date"] = f"{(2000 + int(y)) if len(y) == 2 else int(y):04d}-{mo}-{d}"
    if not info["statement_date"]:
        raise StatementError("Couldn't find the statement date. Is this a Maybank statement PDF?")
    year = int(info["statement_date"][:4])
    stmt_month = int(info["statement_date"][5:7])

    i, current, last = 0, None, None
    while i < len(lines):
        l = lines[i]
        if last is not None and indented[i] and not DATE_LINE.match(l):
            # Islamic layout: indented lines continue the previous transaction's description
            last["description"] += " | " + l
            i += 1
            continue
        if info["opening"] is None and (m := BEGIN.search(l)):
            if m.group(1):
                info["currency"] = m.group(1)
            if m.group(2):
                info["opening"] = num(m.group(2))
            elif i + 1 < len(lines) and re.match(r"^[\d,]+\.\d{2}$", lines[i + 1]):
                info["opening"] = num(lines[i + 1])
                i += 1
        elif (m := TOTAL.match(l)):
            # The figure sits on the same line in some layouts and on the next line in others.
            v = m.group(2) or (lines[i + 1] if i + 1 < len(lines) and MONEY.match(lines[i + 1]) else None)
            if v:
                info["total_debits" if m.group(1).startswith("DEBIT") else "total_credits"] = num(v)
        elif (m := ENDING.match(l)):
            v = m.group(1) or (lines[i + 1] if i + 1 < len(lines) and MONEY.match(lines[i + 1]) else None)
            if v:
                info["closing"] = num(v)
            last = None
        elif (m := DATE_LINE.match(l)) and info["opening"] is not None:
            d, mo, rest = m.groups()
            y = year - 1 if int(mo) > stmt_month else year  # January statements can carry December lines
            when = f"{y:04d}-{mo}-{d}"
            if (a := INLINE_AMOUNT.match(rest)):
                desc, amt, sign, bal, dr = a.groups()
                last = {"date": when, "description": desc, "amount": num(amt) * (1 if sign == "+" else -1),
                        "balance": num(bal) * (-1 if dr else 1)}
                info["lines"].append(last)
                current = None
            else:
                current, last = {"date": when, "desc": [rest]}, None
        elif current and (m := AMOUNT_LINE.match(l)):
            amt, sign, bal, dr = m.groups()
            current["amount"] = num(amt) * (1 if sign == "+" else -1)
            current["balance"] = num(bal) * (-1 if dr else 1)
            current["description"] = " | ".join(current.pop("desc"))
            info["lines"].append(current)
            current = None
        elif current:
            current["desc"].append(l)
        i += 1

    if info["opening"] is None or not info["lines"]:
        raise StatementError("Couldn't read any transactions from this statement.")
    # Every line must carry the balance forward exactly; this catches any misread line.
    bal = info["opening"]
    for n, ln in enumerate(info["lines"], 1):
        bal = round(bal + ln["amount"], 2)
        if abs(bal - ln["balance"]) > 0.005:
            raise StatementError(f"Line {n} ({ln['date']}) doesn't add up to the printed balance. Nothing was imported.")
    info["check_ok"] = info["closing"] is None or abs(bal - info["closing"]) < 0.005
    return info


BANK_NOISE = {"DUITNOW", "PAYPRX", "TRANSFER", "PAYMENT", "M2UBIZ", "PYMT", "ELECTRONIC", "REMITTANCE", "GIR", "MBB"}


def words(s):
    from .sqlimport import NOISE
    return {w for w in re.findall(r"[A-Z]{3,}", (s or "").upper()) if w not in NOISE and w not in BANK_NOISE}


def overlaps(a, b):
    """Shared word, allowing the bank's truncation and longer legal names (AHMAD ~ AHMADI, KUMAR ~ KUMARAN)."""
    return any(x == y or (min(len(x), len(y)) >= 5 and (x.startswith(y) or y.startswith(x))) for x in a for y in b)


def auto_match(con, statement_id, only=None):
    """Link statement lines to payments of the same account (or only to the payments whose ids are in only).

    Lines are first narrowed to the payee's name. Then the lines that make up the payment are found: one line with
    the exact amount, or several adding up to it (Maybank splits large DuitNow transfers: 22,000 = 2,000 + 10,000
    + 10,000). The same person can appear on several lines (claim, salary), so only the right combination is taken.
    An estimated bill (TNB, PCB) matches a single named line within ±50% and takes the bank's figure (take_line_total).
    The bank's date replaces a paid date that came from an SQL voucher, but never one typed in. A line undone by hand,
    or freed by removing its payment, is left for a person to explain.
    """
    st = con.execute("SELECT * FROM statements WHERE id = ?", (statement_id,)).fetchone()
    lines = con.execute("""SELECT * FROM statement_lines WHERE statement_id = ? AND payment_id IS NULL AND status = 'unmatched'
                           AND undone_payment_id IS NULL""", (statement_id,)).fetchall()
    pays = con.execute(
        """SELECT p.*, py.match_words, py.name AS payee_name FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.account_id = ? AND p.month BETWEEN ? AND ? AND p.amount IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM statement_lines s WHERE s.payment_id = p.id)
           ORDER BY p.amount_is_estimate, p.due_date""",  # firm amounts first, so estimates can't take their lines
        (st["account_id"], shift(st["month"], -1), st["month"])).fetchall()
    if only is not None:
        pays = [p for p in pays if p["id"] in only]
    from datetime import date as _d

    def gap(p, chosen):
        due = _d.fromisoformat(p["paid_date"] or p["due_date"])
        return max(abs((_d.fromisoformat(l["txn_date"]) - due).days) for l in chosen)

    taken, matched, remaining = set(), 0, list(pays)
    # Repeatedly settle the payment whose lines sit closest to its due date, so a September transfer goes to
    # September's consultant fee and not to August's identical one.
    while remaining:
        best = None
        for p in remaining:
            key = words(p["match_words"] or p["payee_name"] or p["description"])
            if not key:
                continue
            cands = [l for l in lines if l["id"] not in taken and overlaps(key, words(l["description"]))
                     and (l["amount"] < 0) == (p["direction"] == "out")]
            chosen = _combination(cands, p["amount"])
            if not chosen and p["amount_is_estimate"] and len(cands) == 1 and p["amount"] \
                    and 0.5 <= abs(cands[0]["amount"]) / p["amount"] <= 1.5:
                chosen = cands
            if chosen and gap(p, chosen) <= 45 and (best is None or gap(p, chosen) < best[0]):
                best = (gap(p, chosen), p, chosen)
        if not best:
            break
        _, p, chosen = best
        remaining.remove(p)
        for l in chosen:
            taken.add(l["id"])
            con.execute("UPDATE statement_lines SET payment_id = ?, status = 'matched' WHERE id = ?", (p["id"], l["id"]))
        if not p["paid_date"] or p["paid_source"] == "sql":
            con.execute("UPDATE payments SET paid_date = ?, paid_source = 'bank' WHERE id = ?",
                        (max(l["txn_date"] for l in chosen), p["id"]))
        take_line_total(con, p["id"])
        matched += len(chosen)
    return matched


def take_line_total(con, payment_id):
    """An estimate, a blank amount, or an amount that came from bank lines becomes what the linked lines add up to:
    a flight paid as 3,410 + 10,000 is 13,410. The figures planned before are kept (planned_amount), so undoing the
    links can put them back. An amount recorded by an SQL voucher stays, and so does one typed in, and lines in
    another currency than the payment's, or lines that take off as much as they add, leave it alone."""
    from .db import linked_total
    p = con.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    total = linked_total(con, p)
    in_sql = con.execute("SELECT 1 FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') = 'payment'",
                         (payment_id,)).fetchone()
    from_lines = p["amount"] is None or p["amount_is_estimate"] or p["planned_is_estimate"] is not None
    if total and total > 0 and from_lines and not in_sql:
        con.execute(
            """UPDATE payments SET planned_amount = CASE WHEN planned_is_estimate IS NULL THEN amount ELSE planned_amount END,
               planned_is_estimate = COALESCE(planned_is_estimate, amount_is_estimate), amount = ?, amount_is_estimate = 0
               WHERE id = ?""", (total, payment_id))


def paying_dates(con, payment_id):
    """The dates of the bank lines linked that paid the payment: money going its way, not a refund or a charge."""
    return [r[0] for r in con.execute(
        """SELECT l.txn_date FROM statement_lines l JOIN payments p ON p.id = l.payment_id
           WHERE p.id = ? AND (l.amount < 0) = (p.direction = 'out')""", (payment_id,))]


BANK_CHARGE = re.compile(r"^(FCA CHARGES|BANK CHARGES?|SERVICE CHARGES?|COMMISSION|CHEQUE BOOK|STAMP DUTY)\b|\bTT CHARGES?\b")
OWN_TRANSFER = re.compile(r"FUND XFER (FROM|TO) FCA|OWN ACCOUNT TRANSFER", re.I)


def classify(con, statement_id):
    """Marks lines that need no supporting documents: the bank's own charges, and money moved between two of the
    same company's accounts (FCA <-> current account). A line undone by hand, or freed by removing its payment, is
    left for a person to explain. Returns how many lines were marked."""
    st = con.execute("""SELECT s.*, a.entity_id, a.label FROM statements s JOIN accounts a ON a.id = s.account_id
                        WHERE s.id = ?""", (statement_id,)).fetchone()
    marked = 0
    # Also revisits transfers marked before the other account's statement arrived, to fill in the other side.
    for l in con.execute("""SELECT * FROM statement_lines WHERE statement_id = ? AND payment_id IS NULL AND undone_payment_id IS NULL
                            AND (status = 'unmatched' OR note LIKE '%not imported yet%')""", (statement_id,)).fetchall():
        desc = l["description"].upper()
        if BANK_CHARGE.search(desc) and l["amount"] < 0:
            note = "Bank charge"
        elif OWN_TRANSFER.search(desc):
            # The other side sits in another of this company's accounts on the same day, money moving the other way.
            other = con.execute(
                """SELECT l2.*, a.label, a.currency FROM statement_lines l2 JOIN statements s2 ON s2.id = l2.statement_id
                   JOIN accounts a ON a.id = s2.account_id
                   WHERE a.entity_id = ? AND s2.account_id != ? AND l2.txn_date = ? AND (l2.amount > 0) != ?""",
                (st["entity_id"], st["account_id"], l["txn_date"], l["amount"] > 0)).fetchall()
            other = next((o for o in other if OWN_TRANSFER.search(o["description"])), None)
            note = (f"Own-account transfer {'from' if l['amount'] > 0 else 'to'} {other['label']}"
                    f" ({other['currency']} {abs(other['amount']):,.2f})" if other
                    else "Own-account transfer (other account's statement not imported yet)")
        else:
            continue
        con.execute("UPDATE statement_lines SET status = 'no_docs', note = ? WHERE id = ?", (note, l["id"]))
        marked += 1
    return marked


def _combination(cands, amount):
    """The smallest set of candidate lines adding up exactly to the amount, or None."""
    from itertools import combinations
    if cands and abs(round(sum(abs(l["amount"]) for l in cands), 2) - amount) < 0.005:
        return list(cands)  # all of them, e.g. RM70,000 sent as seven RM10,000 transfers
    cands = cands[:12]  # keeps the search small; a payee rarely has more lines in one month
    for size in range(1, min(len(cands), 6) + 1):
        for combo in combinations(cands, size):
            if abs(round(sum(abs(l["amount"]) for l in combo), 2) - amount) < 0.005:
                return list(combo)
    return None


def shift(month, n):
    from .db import shift_month
    return shift_month(month, n)
