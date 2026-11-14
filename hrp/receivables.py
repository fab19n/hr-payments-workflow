"""Customers and suppliers: who owes what. Worked out from the books of hrp/books.py (SQL's openings and every SQL
document's account lines). Pure reads: nothing here writes anything.

Who is listed. Every code under a debtor or creditor control account: a customer's or supplier's own code (300-A0003
under 300-0000 TRADE DEBTORS, 400-S0001 under 400-0000 TRADE CREDITORS, 305-W0001 under 305-0000 OTHER DEBTORS), as
books._Books.control finds its control account. A control account is the customers' side when the chart marks it a
debtor control, the suppliers' when a creditor control; else from the customers and suppliers in Setup that use it,
else from the chart's type (an asset for customers, a liability for suppliers). The control account's own balance (an
opening SQL printed for it that isn't split by customer, and anything posted to it directly) is listed on a line of its
own, so the lines add up to the control account's figures in the trial balance with customers and suppliers added in.

How the figures are shown. Each amount is what is owed: for a customer, what the customer owes the company (a debit
above 0); for a supplier, what the company owes the supplier (a credit above 0). Invoiced is what the sales or purchase
book added (a customer's or supplier's invoice); received or paid is what the bank book took off (a receipt or a
payment, a refund counting the other way); other is everything else (credit notes, journals, contra), signed: above 0
adds to what is owed. Closing = opening + invoiced - received or paid + other.

Ageing, at the To date. SQL's exports don't say which receipt or payment settled which invoice, so each receipt,
payment, credit note or journal that takes off what is owed is taken to settle the oldest invoice still open first
(first in, first out). The ageing counts from the code's earliest opening, and every line after it is aged, however many
later openings SQL printed (each monthly trial balance fetched, each year's opening): an opening balance with no invoices
kept behind it is the oldest and is aged as brought forward. A later opening is only a check: when it says more or less
than the earlier opening and the lines since, only that difference is brought forward at its date (more owed), or taken
off the oldest invoices (less owed).
What is left open is aged by the invoice's date (or its due date, when one is known: SQL's exports carry none): current
is not yet due or within 30 days, then 31-60, 61-90 and over 90 days. A customer or supplier with a balance the other
way round (paid in advance or overpaid) is shown as in credit, not aged.

All amounts are whole sen, so every comparison is exact.
"""
from datetime import date

from . import books
from .ledger import CONTROLS, _key, _money

SIDES = ("customers", "suppliers")
SIGN = {"customers": 1, "suppliers": -1}  # what is owed, from a debit-above-0 balance
BUCKETS = ("current", "d31_60", "d61_90", "over_90", "brought_forward")
BUCKET_WORDS = {"current": "Current", "d31_60": "31-60 days", "d61_90": "61-90 days", "over_90": "Over 90 days",
                "brought_forward": "Brought forward"}
FIFO_NOTE = ("SQL's exports don't say which receipt or payment settled which invoice, so each receipt, payment, credit note "
             "or journal is taken to settle the oldest invoice still open first. SQL's exports carry no due dates either, "
             "so invoices are aged by their own date: current is within 30 days of it. An opening balance with no invoices "
             "kept behind it is aged as brought forward.")
SIDE_WORDS = {"customers": ("customer", "customers", "received"), "suppliers": ("supplier", "suppliers", "paid")}


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _bucket(days):
    if days <= 30:
        return "current"
    if days <= 60:
        return "d31_60"
    if days <= 90:
        return "d61_90"
    return "over_90"


def _side_of(B, ctl, members):
    """'customers', 'suppliers', or None when the control account isn't a debtor or creditor account."""
    a = B.ch.accounts.get(ctl) or {}
    if a.get("special") == "debtor_control":
        return "customers"
    if a.get("special") == "creditor_control":
        return "suppliers"
    kinds = {(B.ch.parties.get(m) or {}).get("kind") for m in members} - {None}
    if "customer" in kinds and "supplier" not in kinds:
        return "customers"
    if "supplier" in kinds and "customer" not in kinds:
        return "suppliers"
    if kinds and not kinds & {"customer", "supplier"}:
        return None  # a related party's or a statutory body's code: not a customer or supplier
    t = a.get("type") or B.ch.group_type.get(a.get("sql_type"))
    if t == "asset":
        return "customers"
    if t == "liability":
        return "suppliers"
    name = str(a.get("name") or "").upper()
    if "DEBTOR" in name or "RECEIVABLE" in name:
        return "customers"
    if "CREDITOR" in name or "PAYABLE" in name:
        return "suppliers"
    return None


def _party_kinds(con, eid):
    """{sql code: kind} of the customers and suppliers in Setup (the company's own winning over a shared one)."""
    out = {}
    for r in con.execute("""SELECT sql_code, kind FROM parties WHERE sql_code IS NOT NULL AND TRIM(sql_code) <> ''
                            AND (entity_id IS NULL OR entity_id = ?) ORDER BY entity_id IS NOT NULL""", (eid,)):
        out[_key(r["sql_code"])] = r["kind"]
    return out


class _Parties:
    """The books of one company, with which codes are customers' and suppliers' and under which control account."""

    def __init__(self, con, eid):
        self.B = B = books._Books(con, eid)
        kinds = _party_kinds(con, eid)
        for code, p in B.ch.parties.items():
            p["kind"] = kinds.get(code)
        members = {}
        for c in sorted(B.codes() | set(B.ch.parties)):
            ctl = B.control(c)
            if ctl:
                members.setdefault(ctl, []).append(c)
        for k, a in B.ch.accounts.items():
            if a.get("special") in CONTROLS:
                members.setdefault(k, [])
        self.controls = {}  # control account: {side, members}
        for ctl, ms in sorted(members.items()):
            side = _side_of(B, ctl, ms)
            if side:
                self.controls[ctl] = {"side": side, "members": ms}

    def name(self, code):
        """(name, where it came from): the customer or supplier in Setup, else the chart, else the name SQL printed."""
        B, code = self.B, _key(code)
        p = B.ch.parties.get(code)
        if p and p.get("name"):
            return p["name"], "party"
        if code in B.ch.accounts:
            return B.ch.accounts[code]["name"], "chart"
        if B.printed.get(code):
            return B.printed[code], "printed"
        return None, None

    def where(self, code):
        """(control account, side) of a customer's or supplier's code, or of a control account itself; (None, None)
        when the code is neither."""
        code = _key(code)
        if code in self.controls:
            return code, self.controls[code]["side"]
        ctl = self.B.control(code)
        if ctl in self.controls and code in self.controls[ctl]["members"]:
            return ctl, self.controls[ctl]["side"]
        return None, None

    def start(self, code, after):
        """Where the code's ageing for the balance before `after` is counted from, and the later openings that check it:
        (day counted from (None: from its first line), balance then, [(day, how much a later opening differs from the
        earlier one and the lines since)]), balances debit above 0; None when no opening says what it was. The earliest
        opening is the start, so every line after it is aged; each later opening on or before `after` is compared with
        the one before it plus the lines between, and only a difference is kept."""
        B = self.B
        code = _key(code)
        days = {o["as_of"] for o in B.opens.get(code, [])} | set(B.tb_sets)
        ctl = B.control(code)
        if ctl and B.sub_from(ctl):
            days.add(B.sub_from(ctl))
        chain = []  # the bases in turn, earliest first
        for d in sorted(x for x in days if x <= after):
            b = B.base(code, d)
            if b is None or b["as_of"] is None:
                continue
            if not chain or b["as_of"] > chain[-1]["as_of"]:
                chain.append(b)
        last = B.base(code, after)
        if last is None:
            return None
        if last["as_of"] is None:
            return None, 0, []
        if not chain or last["as_of"] > chain[-1]["as_of"]:
            chain.append(last)
        start_day = chain[0]["as_of"]
        diffs = []
        for prev, b in zip(chain, chain[1:]):
            gap = B.raw(code, b["as_of"], b) - B.raw(code, b["as_of"], prev)
            if gap:
                diffs.append((b["as_of"], gap))
        return start_day, B.raw(code, start_day, chain[0]), diffs

    def ageing(self, code, d_to, side):
        """The code's open items at the end of d_to, oldest first, settled first in, first out. Returns {closing_sen,
        credit, items: [{date, doc_no, origin, book, description, amount_sen, open_sen, days, bucket}], ageing:
        {bucket: sen}} in what is owed, or None when no opening says what the balance was."""
        B, sign = self.B, SIGN[side]
        after = books._next(d_to)
        st = self.start(code, after)
        if st is None:
            return None
        start_day, start_net, diffs = st
        items, credits = [], 0
        owed = sign * start_net
        if owed > 0:
            items.append({"date": start_day, "doc_no": None, "origin": None, "book": None, "amount_sen": owed,
                          "description": f"Brought forward at {books._dmy(start_day)}, with no invoices kept behind it",
                          "brought_forward": True})
        else:
            credits -= owed
        for day, gap in diffs:
            owed = sign * gap
            if owed > 0:  # dated no later than the To date: an opening the day after it is the balance at its end
                at = min(day, d_to)
                items.append({"date": at, "doc_no": None, "origin": None, "book": None, "amount_sen": owed,
                              "description": (f"Brought forward at {books._dmy(day)}: the opening kept then is {_money(owed)} "
                                              "more than the earlier opening and the lines since, with no invoices kept "
                                              "behind it"), "brought_forward": True})
            else:
                credits -= owed
        docs = {}
        for x in B.lines.get(_key(code), []):
            if (start_day is None or x["doc_date"] >= start_day) and x["doc_date"] < after:
                d = docs.setdefault(x["doc_key"], {"date": x["doc_date"], "doc_no": x["doc_no"], "origin": x["origin"],
                                                   "book": x["book"], "description": x["doc_description"] or x["description"],
                                                   "amount_sen": 0, "brought_forward": False})
                d["amount_sen"] += sign * (x["dr_sen"] - x["cr_sen"])
        for d in sorted(docs.values(), key=lambda d: (d["date"], d["doc_no"])):
            if d["amount_sen"] > 0:
                items.append(d)
            else:
                credits -= d["amount_sen"]
        items.sort(key=lambda i: (i["date"] or "", not i["brought_forward"]))  # oldest first; stable, so ties keep their order
        closing = sum(i["amount_sen"] for i in items) - credits
        ageing = {k: 0 for k in BUCKETS}
        if closing <= 0:
            return {"closing_sen": closing, "credit": closing < 0, "items": [], "ageing": ageing}
        open_items = []
        for i in items:  # oldest first: the credits settle these before any later one
            take = min(credits, i["amount_sen"])
            credits -= take
            left = i["amount_sen"] - take
            if left <= 0:
                continue
            due = i.get("due")
            days = _days(due or i["date"], d_to) if i["date"] else None
            bucket = "brought_forward" if i["brought_forward"] else _bucket(days)
            ageing[bucket] += left
            open_items.append({"date": i["date"], "doc_no": i["doc_no"], "origin": i["origin"], "book": i["book"],
                               "description": i["description"], "amount_sen": i["amount_sen"], "open_sen": left,
                               "days": days, "bucket": bucket, "bucket_words": BUCKET_WORDS[bucket]})
        return {"closing_sen": closing, "credit": False, "items": open_items, "ageing": ageing}

    def figures(self, code, d_from, d_to, side):
        """One line of the list: opening, invoiced, received or paid, other and closing, in what is owed."""
        B, sign = self.B, SIGN[side]
        after = books._next(d_to)
        opening, closing = B.balance(code, d_from), B.closing(code, d_to)
        inv = got = other = 0
        for x in B.lines.get(_key(code), []):
            if not d_from <= x["doc_date"] <= d_to:
                continue
            owed = sign * (x["dr_sen"] - x["cr_sen"])
            if x["book"] in ("sales", "purchase") and owed > 0:
                inv += owed
            elif x["book"] == "bank":
                got -= owed
            else:
                other += owed
        name, name_from = self.name(code)
        row = {"code": code, "name": name, "name_from": name_from, "own": code in self.controls,
               "opening_sen": None if opening is None else sign * opening, "invoiced_sen": inv, "received_sen": got,
               "other_sen": other, "closing_sen": None if closing is None else sign * closing, "credit": False,
               "ageing": None, "open_count": 0, "notes": []}
        if opening is None or closing is None:
            row["notes"].append(B.why(code))
            return row
        if closing != opening + sign * (inv - got + other):
            row["notes"].append(f"A later opening kept for {code} says {_money(sign * closing)} at {books._dmy(d_to)}, but "
                                f"the opening and the lines come to {_money(sign * opening + inv - got + other)}.")
        ag = self.ageing(code, d_to, side)
        if ag is not None:
            row["credit"] = ag["credit"]
            row["ageing"] = ag["ageing"]
            row["open_count"] = len(ag["items"])
        return row


def _side_arg(side):
    side = (side or "").strip().lower() or None
    if side in (None, "both", "all"):
        return SIDES
    if side not in SIDES:
        raise ValueError("Side is 'customers' or 'suppliers'.")
    return (side,)


def balances(con, eid, d_from=None, d_to=None, side=None):
    """Who owes what for a period (default: this financial year to date): per debtor or creditor control account, one
    line per customer's or supplier's code (and one for what the control account holds itself), with its opening,
    invoiced, received or paid, other and closing, and its ageing at the To date; the totals checked against the control
    account's figures in the trial balance with customers and suppliers added in. side: 'customers', 'suppliers' or
    None for both. Amounts in sen, as what is owed. Returns {from, to, sides, controls: [{code, name, side, rows,
    totals, tb, ties, text}], ties, text, ageing_note, notes}."""
    P = _Parties(con, eid)
    B = P.B
    d_from, d_to = books._period_of(B, d_from, d_to)
    sides = _side_arg(side)
    tb = {r["code"]: r for r in books.trial_balance(con, eid, d_from, d_to, rollup=True)["accounts"] if r["code"]}
    controls, notes = [], []
    for ctl, info in P.controls.items():
        s = info["side"]
        if s not in sides:
            continue
        sign = SIGN[s]
        rows = []
        for code in [ctl] + [m for m in info["members"] if m != ctl]:
            r = P.figures(code, d_from, d_to, s)
            keep = r["opening_sen"] is None or r["closing_sen"] is None or any(
                r[k] for k in ("opening_sen", "invoiced_sen", "received_sen", "other_sen", "closing_sen"))
            if keep:
                rows.append(r)
        t = tb.get(ctl)
        if not rows and t is None:
            continue
        own = next((r for r in rows if r["own"]), None)
        if own:
            own["name_words"] = "Held on the control account itself, not split by " + SIDE_WORDS[s][0]
        totals = {}
        for k in ("opening_sen", "closing_sen"):
            vals = [r[k] for r in rows]
            totals[k] = None if None in vals else sum(vals)
        for k in ("invoiced_sen", "received_sen", "other_sen"):
            totals[k] = sum(r[k] for r in rows)
        totals["ageing"] = {b: sum((r["ageing"] or {}).get(b, 0) for r in rows if not r["credit"]) for b in BUCKETS}
        totals["in_credit_sen"] = sum(r["closing_sen"] for r in rows if r["credit"])
        tbf = {  # nothing in the trial balance for the control account: it has nothing there
            "opening_sen": 0 if t is None else (None if t["opening_sen"] is None else sign * t["opening_sen"]),
            "closing_sen": 0 if t is None else (None if t["closing_sen"] is None else sign * t["closing_sen"]),
            "moved_sen": 0 if t is None else sign * (t["dr_sen"] - t["cr_sen"])}
        name = P.name(ctl)[0] or ctl
        who = SIDE_WORDS[s][1]
        moved = totals["invoiced_sen"] - totals["received_sen"] + totals["other_sen"]
        if None in (totals["opening_sen"], totals["closing_sen"], tbf["opening_sen"], tbf["closing_sen"]):
            ties = None
            text = (f"{ctl} {name}: can't be checked against the trial balance, as no opening balance is kept for "
                    f"{', '.join(r['code'] for r in rows if r['opening_sen'] is None or r['closing_sen'] is None) or ctl}.")
        else:
            ties = (totals["opening_sen"], moved, totals["closing_sen"]) == (tbf["opening_sen"], tbf["moved_sen"], tbf["closing_sen"])
            if ties:
                text = (f"{ctl} {name}: the {who} add up to the control account in the trial balance, "
                        f"{_money(totals['opening_sen'])} at the start and {_money(totals['closing_sen'])} at the end.")
            else:
                parts = []
                for k, w in (("opening_sen", "the opening"), ("moved_sen", "the period's movement"), ("closing_sen", "the closing")):
                    mine = moved if k == "moved_sen" else totals[k]
                    if mine != tbf[k]:
                        parts.append(f"{w} here is {_money(mine)}, the trial balance's {_money(tbf[k])} "
                                     f"(a difference of {_money(mine - tbf[k])})")
                jumps = [r["code"] for r in rows if any(n.startswith("A later opening") for n in r["notes"])]
                why = (f" A later opening kept for {', '.join(jumps)} doesn't follow from the earlier one and the lines."
                       if jumps else " The trial balance adds a code into the control account that isn't listed here; see "
                       "the Trial balance tab with customers and suppliers added in.")
                text = f"{ctl} {name}: the {who} don't add up to the control account in the trial balance: {'; '.join(parts)}.{why}"
        controls.append({"code": ctl, "name": name, "side": s, "rows": rows, "totals": totals, "tb": tbf, "ties": ties, "text": text})
    known = [c["ties"] for c in controls]
    ties = None if not controls or None in known else all(known)
    if not controls:
        text = f"No {' or '.join(SIDE_WORDS[s][0] for s in sides)} balance is kept for these dates."
    elif ties:
        text = (f"Every control account ties: the {' and '.join(SIDE_WORDS[s][1] for s in sides)} listed add up to "
                "their control accounts in the trial balance.")
    elif ties is False:
        text = "Not every control account ties to the trial balance: " + " ".join(c["text"] for c in controls if c["ties"] is False)
    else:
        text = "Not every control account can be checked: " + " ".join(c["text"] for c in controls if c["ties"] is None)
    unnamed = sorted(r["code"] for c in controls for r in c["rows"] if not r["own"] and r["name_from"] != "party")
    if unnamed:
        notes.append(f"Not in Setup › Customers and suppliers, so named from the chart or the name SQL printed: {', '.join(unnamed)}.")
    notes += books._coverage_notes(con, B, d_from, d_to)
    return {"from": d_from, "to": d_to, "sides": list(sides), "controls": controls, "ties": ties, "text": text,
            "ageing_note": FIFO_NOTE, "buckets": [{"key": b, "words": BUCKET_WORDS[b]} for b in BUCKETS], "notes": notes}


def statement(con, eid, code, d_from=None, d_to=None):
    """One customer's or supplier's statement for a period: every line on its code with a running balance (debit above
    0, as in the ledger), its opening and closing, and the invoices still open at the To date with their age (settled
    first in, first out). Returns {code, name, name_from, control, control_name, side, from, to, opening_sen,
    closing_sen, owed_sen, credit, rows, open_items, ageing, ageing_note, notes}. Raises ValueError when the code isn't a
    customer's or supplier's."""
    P = _Parties(con, eid)
    B = P.B
    code = _key(code or "")
    ctl, side = P.where(code)
    if not code:
        raise ValueError("Give the code of a customer or supplier.")
    if side is None:
        raise ValueError(f"{code} isn't a customer's or supplier's code under a debtor or creditor control account.")
    d_from, d_to = books._period_of(B, d_from, d_to)
    opening, closing = B.balance(code, d_from), B.closing(code, d_to)
    rows = []
    run = opening or 0
    for x in B.lines.get(code, []):
        if d_from <= x["doc_date"] <= d_to:
            run += x["dr_sen"] - x["cr_sen"]
            rows.append({"date": x["doc_date"], "doc_no": x["doc_no"], "origin": x["origin"], "book": x["book"],
                         "book_label": x["book_label"], "description": x["description"] or x["doc_description"],
                         "dr_sen": x["dr_sen"], "cr_sen": x["cr_sen"], "balance_sen": run})
    notes = []
    if opening is None:
        notes.append(B.why(code) + " The running balance starts from 0.")
    elif closing is not None and closing != run:
        notes.append(f"A later opening kept for {code} says {_money(closing)} after {books._dmy(d_to)}, but the opening and "
                     f"the lines come to {_money(run)}.")
    if code == ctl:
        notes.append(f"What {ctl} holds itself: an opening SQL printed for it that isn't split by {SIDE_WORDS[side][0]}, and "
                     "anything posted to it directly.")
    ag = P.ageing(code, d_to, side)
    name, name_from = P.name(code)
    sign = SIGN[side]
    return {"code": code, "name": name, "name_from": name_from, "control": ctl, "control_name": P.name(ctl)[0], "side": side,
            "from": d_from, "to": d_to, "opening_sen": opening, "closing_sen": closing,
            "owed_sen": None if closing is None else sign * closing, "credit": bool(ag and ag["credit"]), "rows": rows,
            "open_items": ag["items"] if ag else [], "ageing": ag["ageing"] if ag else None, "ageing_note": FIFO_NOTE,
            "buckets": [{"key": b, "words": BUCKET_WORDS[b]} for b in BUCKETS], "notes": notes}
