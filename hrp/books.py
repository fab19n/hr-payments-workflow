"""The company's books, worked out from what is kept: each account's opening balance as SQL printed it (update 28,
ledger_openings) and the account lines of the current documents (ledger_docs, ledger_lines). Pure reads: nothing here
writes anything, so every report follows the records, the chart of accounts and the financial year setting as they are
now.

How a balance is worked out. An account's balance before a day is the latest opening kept on or before that day (SQL's
trial balance preferred, else its ledger), plus the account's lines from that opening's day up to the day before. An
account a trial balance doesn't list had nothing on its From date. A customer's or supplier's own code (300-A0003) has
no opening of its own: SQL prints it inside its control account's (300-0000). Its own balance is its lines from the
control account's first opening, and the control account's own balance leaves those lines out, so neither jumps when
the control account gets a later opening (which holds them), and the two still add up to SQL's figure.

Profit and loss start again at each financial year start (Setup › Companies, January when it isn't set): an income or
expense account's balance before that day is 0, and what it held moves into retained earnings (the chart's account of
SQL type RE, else an equity account named like RETAINED). SQL prints profit and loss balances cumulatively, so a
profit and loss opening on or before the year start only says the lines from then on are complete; one kept later in
the year is taken as the year's figure so far. What the year starts moved is counted from the same day as retained
earnings' own opening, from the profit and loss figures kept that day, so both sides start from one set of figures. A
period that ends on the last day of a financial year closes before that year end's move (the move belongs to the next
period). With no retained earnings account in the chart, the amount moved is shown on a line of its own, so the trial
balance still balances.

All amounts are whole sen (debit above 0), so every comparison is exact.
"""
from datetime import date, timedelta

from .ledger import _Chart, _coverage, _dates, _exists, _iso, _key, _money, _period, fy_start_of

SOURCE_RANK = {"sql_tb": 0, "sql_ledger": 1, "here": 2}
SOURCE_WORDS = {"sql_tb": "SQL's trial balance", "sql_ledger": "SQL's GL ledger", "here": "entered here",
                "not_on_tb": "not on SQL's trial balance, so nothing", "in_control": "inside its control account",
                "fresh": "the books kept here from the start"}
OPENING_ORDER = ("sql_tb", "sql_ledger", "here", "fresh", "not_on_tb", "in_control")
UNASSIGNED ="Profit and loss carried at the year start (no retained earnings account in the chart)"


def _day(d):
    return date.fromisoformat(d)


def _next(d):
    return (_day(d) + timedelta(days=1)).isoformat()


def _dmy(d):
    return f"{_day(d):%d/%m/%Y}"


def _split(net):
    """A signed balance as (debit, credit) columns."""
    return (net, 0) if net is not None and net > 0 else (0, -net) if net is not None else (None, None)


class _Books:
    """Everything one company's reports read, loaded once: the chart, the openings and the current lines."""

    def __init__(self, con, eid):
        self.con, self.eid = con, eid
        ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
        self.uses_sql = ent is None or ent["uses_sql"] is None or bool(ent["uses_sql"])
        self.fy_setting = fy_start_of(con, eid)
        self.fy = self.fy_setting or 1
        self.ch = _Chart(con, eid)
        self.opens, self.tb_sets, self.printed = {}, {}, {}
        if _exists(con, "ledger_openings"):
            for r in con.execute("SELECT * FROM ledger_openings WHERE entity_id = ? ORDER BY as_of, id", (eid,)):
                code = _key(r["account_code"])
                self.opens.setdefault(code, []).append({"as_of": r["as_of"], "source": r["source"], "net": r["dr_sen"] - r["cr_sen"]})
                if r["source"] == "sql_tb":
                    self.tb_sets.setdefault(r["as_of"], set()).add(code)
                if r["account_name"]:
                    self.printed.setdefault(code, r["account_name"])
        self.lines = {}
        if _exists(con, "ledger_lines"):
            for r in con.execute("""SELECT d.doc_no, d.doc_key, d.doc_date, d.book, d.book_label, d.version, d.origin, l.seq,
                                    l.account_code, l.account_name, l.description, d.description AS doc_description, l.dr_sen, l.cr_sen
                                    FROM ledger_lines l JOIN ledger_docs d ON d.id = l.doc_id WHERE d.entity_id = ? AND d.state = 'current'
                                    ORDER BY d.doc_date, d.doc_key, l.seq""", (eid,)):
                code = _key(r["account_code"])
                self.lines.setdefault(code, []).append(dict(r))
                if r["account_name"]:
                    self.printed.setdefault(code, r["account_name"])
        self.subs = {}  # control account: the customers' and suppliers' codes with lines kept and no opening of their own
        for code in sorted(self.lines):
            ctl = self.control(code)
            if ctl and code not in self.opens:
                self.subs.setdefault(ctl, []).append(code)
        self.re_code = self._retained()

    # ---------- the chart ----------

    def _retained(self):
        """The retained earnings account: the chart's account of SQL type RE, else an equity account named like
        RETAINED; None when the chart has neither."""
        accts = self.ch.accounts
        hit = sorted(k for k, a in accts.items() if a.get("sql_type") == "RE")
        hit = hit or sorted(k for k, a in accts.items() if (a.get("type") == "equity" or a.get("sql_type") == "RE")
                            and "RETAINED" in str(a.get("name") or "").upper())
        return hit[0] if hit else None

    def control(self, code):
        """The control account a customer's or supplier's code rolls up into, or None for an account of its own."""
        ctl = self.ch.control(code)
        return ctl if ctl and ctl != _key(code) else None

    def kind(self, code):
        """'pl', 're', 'bs', or None when the chart doesn't say. A customer's or supplier's code is its control's kind."""
        k = self.ch.kind(code)
        if k is None and self.control(code):
            k = self.ch.kind(self.control(code))
        if _key(code) == self.re_code:
            return "re"
        return k

    def name(self, code):
        return self.ch.name(code, self.printed.get(_key(code)))

    def codes(self):
        out = set(self.opens) | set(self.lines)
        if self.re_code:
            out.add(self.re_code)
        return out

    def pl_codes(self):
        return sorted(c for c in self.codes() | set(self.ch.accounts) if self.kind(c) == "pl")

    # ---------- dates ----------

    def year_start(self, day):
        """The financial year start on or before day."""
        d = _day(day)
        return date(d.year if d.month >= self.fy else d.year - 1, self.fy, 1).isoformat()

    def year_starts(self, after, upto):
        """The financial year starts after `after` and on or before `upto`."""
        out, y = [], _day(after).year
        while True:
            f = date(y, self.fy, 1).isoformat()
            if f > upto:
                return out
            if f > after:
                out.append(f)
            y += 1

    # ---------- balances ----------

    def moved(self, code, a, b):
        """(debits, credits) of the account's lines dated from a (None: from the first) to before b."""
        dr = cr = 0
        for x in self.lines.get(_key(code), []):
            if (a is None or x["doc_date"] >= a) and x["doc_date"] < b:
                dr += x["dr_sen"]
                cr += x["cr_sen"]
        return dr, cr

    def net(self, code, a, b):
        dr, cr = self.moved(code, a, b)
        return dr - cr

    def base(self, code, day):
        """Where the account's balance before day starts: {as_of, net, how}, as_of None (the lines from the first) for
        a company whose books are kept here from the start, or None when nothing says what it was (reason in why)."""
        code = _key(code)
        ctl = self.control(code)
        cands = [o for o in self.opens.get(code, []) if o["as_of"] <= day]
        best = max(cands, key=lambda o: (o["as_of"], -SOURCE_RANK.get(o["source"], 9))) if cands else None
        if ctl and not best:
            b = self.base(ctl, day)
            return {"as_of": self.sub_from(ctl), "net": 0, "how": "in_control"} if b else None
        tb = max((t for t in self.tb_sets if t <= day), default=None)
        if tb and (best is None or tb > best["as_of"]) and code not in self.tb_sets[tb]:
            return {"as_of": tb, "net": 0, "how": "not_on_tb"}
        if best:
            return {"as_of": best["as_of"], "net": best["net"], "how": best["source"]}
        if not self.uses_sql:
            return {"as_of": None, "net": 0, "how": "fresh"}
        return None

    def sub_from(self, ctl):
        """The day a customer's or supplier's own balance is counted from: its control account's first opening (or the
        first SQL trial balance), the same day whichever later opening the control account has, so the code's opening
        and closing never measure from different days. None (from its first line) for books kept here."""
        if not self.uses_sql:
            return None
        days = [o["as_of"] for o in self.opens.get(_key(ctl), [])] + list(self.tb_sets)
        return min(days) if days else None

    def raw(self, code, day, base=None):
        """The balance before day with no year-start move: the opening plus the lines since. None when unknown. A control
        account's opening holds its customers' and suppliers' lines before it, which their own codes already count, so
        those are taken off here."""
        code = _key(code)
        b = base or self.base(code, day)
        if b is None:
            return None
        out = b["net"] + self.net(code, b["as_of"], day)
        if b["as_of"] is not None and self.subs.get(code):
            s = self.sub_from(code)
            for sub in self.subs[code]:
                out -= self.net(sub, s, b["as_of"])
        return out

    def pl_balance(self, code, day, start):
        """A profit and loss account's balance before day, counted from the year start `start` (on or before day). An
        opening kept later in that same financial year, on or before day, is the year's figure so far as SQL printed it,
        so the balance starts from it (the latest opening wins, as for every other account); else it is the lines from
        the year start, when an opening on or before the year start says they are complete."""
        b = self.base(code, day)
        if b and b["as_of"] and start < b["as_of"] and self.year_start(b["as_of"]) == start:
            return self.raw(code, day, b)
        if self.base(code, start) is not None:
            return self.net(code, start, day)
        return self.raw(code, day)

    def unmoved(self, code, day):
        """A profit and loss account's balance on day that an opening of retained earnings kept for that day doesn't
        hold yet: the account's own opening that day as SQL printed it, else its balance worked out to then (the year so
        far, or everything kept before it when day is a year start, as SQL prints it there). None when unknown."""
        b = self.base(code, day)
        if b is None:
            return None
        if b["as_of"] == day:
            return b["net"]
        if day == self.year_start(day):
            return self.raw(code, day, b)
        return self.pl_balance(code, day, self.year_start(day))

    def carried(self, f):
        """What the year starts on or before f (a year start) moved from profit and loss into retained earnings,
        cumulatively (debit above 0: a loss). It is counted from the day retained earnings' own opening is from (with no
        retained earnings account, the latest SQL trial balance's), so both sides start from the same figures: the profit
        and loss not yet in retained earnings that day, plus the lines from then to f. A profit and loss opening kept
        later than that day says only the year so far, so it isn't used here. With neither day known, each account's own
        latest opening is used. Returns (sen, the accounts whose balance there is unknown)."""
        r = self.base(self.re_code, f) if self.re_code else None
        at = r["as_of"] if r else max((t for t in self.tb_sets if t <= f), default=None)
        total, unknown = 0, []
        for code in self.pl_codes():
            if code not in self.opens and code not in self.lines:
                continue
            if at is None:
                b = self.base(code, f)
                v = None if b is None else self.raw(code, f, b)
            else:
                v = self.unmoved(code, at)
                v = None if v is None else v + self.net(code, at, f)
            if v is None:
                if self.lines.get(code) and any(x["doc_date"] < f for x in self.lines[code]):
                    unknown.append(code)
                continue
            total += v
        return total, unknown

    def re_counts_carried(self, day, f=None):
        """Whether the retained earnings balance before day takes in what the year starts up to f (the latest one on or
        before day unless given) moved: only when its own opening is on or before f (a later opening, as SQL printed it,
        already says what it holds)."""
        if not self.re_code:
            return True
        b = self.base(self.re_code, day)
        return b is not None and (b["as_of"] is None or b["as_of"] <= (f or self.year_start(day)))

    def balance(self, code, day, f=None):
        """The account's balance before day, profit and loss started again at the year start and retained earnings
        holding what that moved; None when no opening says what it was. f: the latest year start whose move counts (the
        one on or before day unless given)."""
        code = _key(code)
        k = self.kind(code)
        f = f or self.year_start(day)
        if k == "pl":
            return self.pl_balance(code, day, f)
        r = self.raw(code, day)
        if r is None:
            return None
        if k == "re" and self.re_counts_carried(day, f):
            r += self.carried(f)[0]
        return r

    def closing(self, code, d_to):
        """The account's balance at the end of d_to. When d_to is the last day of a financial year, this is before that
        year end's move of profit and loss into retained earnings: the move is dated the next day, the next period's."""
        return self.balance(code, _next(d_to), self.year_start(d_to))

    def reset_at(self, code, f):
        """What the year start f moves out of a profit and loss account (signed: the opposite of its balance)."""
        before = self.pl_balance(code, f, self.year_start((_day(f) - timedelta(days=1)).isoformat()))
        return None if before is None else -before

    def why(self, code):
        return (f"No opening balance of {code} is kept: fetch SQL's trial balance (with a From date) or its GL ledger "
                "for the start of the period, or a period after one.")


def account_choices(con, eid):
    """[{code, name, control}] of every account the books know (the chart, and every code with a line or an opening),
    for the account search."""
    B = _Books(con, eid)
    return [{"code": c, "name": B.name(c)[0], "control": B.control(c)} for c in sorted(B.codes() | set(B.ch.accounts))]


def year_start(con, eid, day):
    """The company's financial year start on or before day (January when the setting is empty)."""
    fy = fy_start_of(con, eid) or 1
    d = _day(day)
    return date(d.year if d.month >= fy else d.year - 1, fy, 1).isoformat()


# ---------- opening_at ----------

def opening_at(con, eid, code, day):
    """The account's balance before day (sen, debit above 0), or None when no opening is kept on or before day and its
    lines don't start a fresh account. Returns {code, day, balance, as_of, how, how_words, why}: as_of and how say which
    opening it started from (SQL's trial balance or ledger, an account not on SQL's trial balance, a customer's or
    supplier's code inside its control account, or the books kept here from the start); why says what is missing."""
    B, code, day = _Books(con, eid), _key(code), _iso(day)
    b = B.base(code, day)
    bal = B.balance(code, day)
    return {"code": code, "day": day, "balance": bal, "as_of": b and b["as_of"], "how": b and b["how"],
            "how_words": SOURCE_WORDS.get(b["how"]) if b else None, "why": None if bal is not None else B.why(code)}


# ---------- the general ledger ----------

def _period_of(B, d_from, d_to):
    d_to = _iso(d_to) or date.today().isoformat()
    d_from = _iso(d_from) or B.year_start(d_to)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _resets(B, code, d_from, d_to):
    """[(year start, signed amount)] that the year starts inside the period move on this account: out of a profit and
    loss account, into retained earnings. None amounts when unknown."""
    k = B.kind(code)
    out = []
    for f in B.year_starts(d_from, d_to):
        if k == "pl":
            out.append((f, B.reset_at(code, f)))
        elif k == "re":
            if not B.re_counts_carried(f):
                continue
            total = 0
            for c in B.pl_codes():
                r = B.reset_at(c, f)
                total -= r or 0
            out.append((f, total))
    return [(f, a) for f, a in out if a]


def ledger_report(con, eid, code=None, d_from=None, d_to=None):
    """The general ledger for a period: per account, its opening (the balance before d_from), every current line in the
    period (date, doc no., book, description, debit, credit, running balance), the year-start move of profit and loss
    when the period holds a year start, its totals and its closing (the balance after d_to). code: one account, or None
    for every account with a balance or a line. A customer's or supplier's code is shown under its own code, with its
    control account named; one control account asked for is followed by its customers' and suppliers' codes, which the
    trial balance adds into it. Amounts in sen. Returns {from, to, fy_start, accounts: [...], notes: [sentences]}."""
    B = _Books(con, eid)
    d_from, d_to = _period_of(B, d_from, d_to)
    after = _next(d_to)

    def active(c):
        return B.moved(c, d_from, after) != (0, 0) or (B.balance(c, d_from) or 0) or (B.closing(c, d_to) or 0)

    subs = []
    if code:
        codes = [_key(code)]
        subs = sorted(c for c in B.codes() if B.control(c) == codes[0] and active(c))
        codes += subs
    else:
        codes = sorted(c for c in B.codes() if active(c))
    accounts, notes = [], []
    for c in codes:
        opening = B.balance(c, d_from)
        b = B.base(c, d_from)
        rows = [{"kind": "line", "date": x["doc_date"], "doc_no": x["doc_no"], "origin": x["origin"], "book": x["book"],
                 "book_label": x["book_label"], "description": x["description"] or x["doc_description"], "dr_sen": x["dr_sen"],
                 "cr_sen": x["cr_sen"], "seq": x["seq"]}
                for x in B.lines.get(c, []) if d_from <= x["doc_date"] <= d_to]
        for f, amount in _resets(B, c, d_from, d_to):
            words = ("Year start: the year's profit and loss moved to retained earnings" if B.kind(c) == "pl"
                     else "Year start: the profit and loss of the year before carried in")
            rows.append({"kind": "year_start", "date": f, "doc_no": None, "origin": None, "book": None, "book_label": None, "description": words,
                         "dr_sen": max(amount or 0, 0), "cr_sen": max(-(amount or 0), 0), "seq": -1})
        rows.sort(key=lambda r: (r["date"], r["kind"] != "year_start", r["doc_no"] or "", r["seq"]))
        run = opening or 0
        for r in rows:
            run += r["dr_sen"] - r["cr_sen"]
            r["balance_sen"] = run
            del r["seq"]
        closing = B.closing(c, d_to)
        name, name_from = B.name(c)
        acct = {"code": c, "name": name, "name_from": name_from, "kind": B.kind(c), "control": B.control(c),
                "opening_sen": opening, "opening_as_of": b and b["as_of"], "opening_how": b and b["how"],
                "opening_words": SOURCE_WORDS.get(b["how"]) if b else None,
                "rows": rows, "dr_sen": sum(r["dr_sen"] for r in rows if r["kind"] == "line"),
                "cr_sen": sum(r["cr_sen"] for r in rows if r["kind"] == "line"), "closing_sen": closing, "notes": []}
        if opening is None:
            acct["notes"].append(B.why(c) + " The running balance starts from 0.")
        elif closing is not None and closing != run:
            acct["notes"].append(f"A later opening kept for {c} says {_money(closing)} after {_dmy(d_to)}, but the opening and the "
                                 f"lines come to {_money(run)} (a difference of {_money(closing - run)}).")
        if acct["control"]:
            acct["notes"].append(f"A customer's or supplier's account: it rolls up into {acct['control']}" + (
                f", whose opening holds its balance before {_dmy(b['as_of'])}; its own balance here is its lines from then."
                if b and b["as_of"] else "; its own balance here is its lines."))
        accounts.append(acct)
    if subs:
        closings = [a["closing_sen"] for a in accounts]
        together = None if None in closings else sum(closings)
        accounts[0]["subs"] = subs
        accounts[0]["notes"].append(
            f"The trial balance, with customers and suppliers added into their control accounts, shows {codes[0]} with "
            f"{', '.join(subs)} added in: {'their ledgers follow' if len(subs) > 1 else 'its ledger follows'} below"
            + (f", and together they close at {_money(together)}." if together is not None else "."))
    if code and not B.lines.get(codes[0]) and codes[0] not in B.opens and not B.ch.known(codes[0]):
        notes.append(f"{codes[0]} is not in the chart of accounts, and no line or opening is kept for it.")
    notes += _coverage_notes(con, B, d_from, d_to)
    return {"from": d_from, "to": d_to, "fy_start": B.fy, "fy_set": B.fy_setting is not None, "accounts": accounts, "notes": notes}


def _coverage_notes(con, B, d_from, d_to):
    if not B.uses_sql:
        return []
    cover = _coverage(con, B.eid)
    if any(a <= d_from and d_to <= b for a, b in cover):
        return []
    have = ", ".join(_dates(a, b) for a, b in cover) or "no dates yet"
    return [f"The GL Journal of Transaction reads kept cover {have}, not all of {_dates(d_from, d_to)}: lines dated outside them "
            "are missing here. Fetch the journal for the whole period."]


# ---------- the trial balance ----------

def trial_balance(con, eid, d_from=None, d_to=None, rollup=False):
    """The trial balance for a period: per account, its opening (the balance before d_from), its period debits and
    credits, what a year start inside the period moved (profit and loss into retained earnings), and its closing (the
    balance after d_to), each balance in debit and credit columns, with grand totals that must balance. rollup: each
    customer's and supplier's code added into its control account, as SQL prints its trial balance. Amounts in sen.
    Returns {from, to, fy_start, rollup, accounts: [...], totals, balanced, notes, openings: [{as_of, how, accounts}]}."""
    B = _Books(con, eid)
    d_from, d_to = _period_of(B, d_from, d_to)
    after = _next(d_to)
    rows, notes, unknown, unclassified, jumps, starts = {}, [], [], [], [], {}
    for c in sorted(B.codes()):
        opening, closing = B.balance(c, d_from), B.closing(c, d_to)
        dr, cr = B.moved(c, d_from, after)
        reset = sum(a or 0 for _, a in _resets(B, c, d_from, d_to))
        if not (opening or closing or dr or cr or reset) and opening is not None and closing is not None:
            continue
        b = B.base(c, d_from)
        if b and b["how"] != "in_control":  # a customer's or supplier's code is counted in its control account's
            key = (b["as_of"], b["how"])
            starts[key] = starts.get(key, 0) + 1
        if opening is None or closing is None:
            unknown.append(c)
        elif closing != opening + dr - cr + reset:
            jumps.append((c, closing - (opening + dr - cr + reset)))
        if B.kind(c) is None:
            unclassified.append(c)
        name, name_from = B.name(c)
        rows[c] = {"code": c, "name": name, "name_from": name_from, "kind": B.kind(c), "control": B.control(c),
                   "opening_sen": opening, "dr_sen": dr, "cr_sen": cr, "reset_sen": reset, "closing_sen": closing, "rolled": []}
    if not B.re_code:
        o, cl = B.carried(B.year_start(d_from))[0], B.carried(B.year_start(d_to))[0]
        if o or cl:
            rows[None] = {"code": None, "name": UNASSIGNED, "name_from": None, "kind": "re", "control": None, "opening_sen": o,
                          "dr_sen": 0, "cr_sen": 0, "reset_sen": cl - o, "closing_sen": cl, "rolled": []}
            notes.append("The chart of accounts has no retained earnings account (SQL type RE, or an equity account named "
                         "RETAINED), so what the year start moves from profit and loss is shown on a line of its own.")
    if rollup:
        for c in [k for k in rows if k is not None and rows[k]["control"]]:
            sub = rows.pop(c)
            ctl = sub["control"]
            into = rows.get(ctl)
            if into is None:
                name, name_from = B.name(ctl)
                into = rows[ctl] = {"code": ctl, "name": name, "name_from": name_from, "kind": B.kind(ctl), "control": None,
                                    "opening_sen": 0, "dr_sen": 0, "cr_sen": 0, "reset_sen": 0, "closing_sen": 0, "rolled": []}
            for k in ("opening_sen", "closing_sen"):
                into[k] = None if into[k] is None or sub[k] is None else into[k] + sub[k]
            for k in ("dr_sen", "cr_sen", "reset_sen"):
                into[k] += sub[k]
            into["rolled"].append(c)
    out = sorted(rows.values(), key=lambda r: (r["code"] is None, r["code"] or ""))
    for r in out:
        r["opening_dr_sen"], r["opening_cr_sen"] = _split(r["opening_sen"])
        r["closing_dr_sen"], r["closing_cr_sen"] = _split(r["closing_sen"])
        r["rolled"].sort()
    known = all(r["opening_sen"] is not None and r["closing_sen"] is not None for r in out)
    tot = {k: (sum(r[k] for r in out) if known or k in ("dr_sen", "cr_sen", "reset_sen") else None)
           for k in ("opening_dr_sen", "opening_cr_sen", "dr_sen", "cr_sen", "reset_sen", "closing_dr_sen", "closing_cr_sen")}
    balanced = known and tot["opening_dr_sen"] == tot["opening_cr_sen"] and tot["dr_sen"] == tot["cr_sen"] \
        and tot["closing_dr_sen"] == tot["closing_cr_sen"] and tot["reset_sen"] == 0
    if unknown:
        notes.append(f"No opening balance is kept for {', '.join(unknown)}, so {'their' if len(unknown) > 1 else 'its'} balances "
                     "can't be shown and the totals can't be checked. Fetch SQL's trial balance (with a From date) or its GL "
                     "ledger for the start of the period.")
    elif not balanced:
        notes.append(f"The trial balance doesn't balance: the openings come to {_money(tot['opening_dr_sen'])} debit and "
                     f"{_money(tot['opening_cr_sen'])} credit, the closings to {_money(tot['closing_dr_sen'])} and "
                     f"{_money(tot['closing_cr_sen'])}.")
    for c, d in jumps:
        notes.append(f"{c}: a later opening kept for this account doesn't follow from the earlier one and the lines "
                     f"(a difference of {_money(d)}); its closing is the later opening's.")
    if unclassified:
        notes.append(f"Not typed in the chart of accounts, so taken as balance-sheet accounts (never started again at the year "
                     f"start): {', '.join(unclassified)}. Set their types in Setup.")
    f_in = B.year_starts(d_from, d_to)
    if f_in:
        notes.append(f"The period holds the start of the financial year ({', '.join(_dmy(f) for f in f_in)}): profit and loss start "
                     "again there, and what they held moves into retained earnings (the Year start column).")
    if B.fy_setting is None:
        notes.append("The financial year start isn't set for this company (Setup › Companies), so it is taken as January.")
    carried_unknown = B.carried(B.year_start(d_to))[1]
    if carried_unknown:
        notes.append(f"No opening is kept for {', '.join(carried_unknown)} before the year start, so what they moved into "
                     "retained earnings there is not counted.")
    notes += _coverage_notes(con, B, d_from, d_to)
    return {"from": d_from, "to": d_to, "fy_start": B.fy, "fy_set": B.fy_setting is not None, "rollup": bool(rollup),
            "retained": B.re_code, "accounts": out, "totals": tot, "balanced": balanced, "notes": notes,
            "openings": [{"as_of": a, "how": h, "words": SOURCE_WORDS.get(h), "accounts": n}
                         for (a, h), n in sorted(starts.items(), key=lambda kv: (kv[0][0] or "", OPENING_ORDER.index(kv[0][1])))]}


# ---------- against SQL's trial balance ----------

def _stored_tb(con, eid, d_from, d_to):
    """The latest SQL trial balance kept as at d_to (one from d_from first), read again from its stored file:
    (batch, report) or (None, why)."""
    from .docstore import path_of, verify
    from .sqlreport import ReportError, read
    if not _exists(con, "ledger_batches"):
        return None, "No trial balance of SQL's is kept yet."
    found = con.execute("""SELECT b.*, d.stored_path, d.sha256 FROM ledger_batches b LEFT JOIN documents d ON d.id = b.document_id
                           WHERE b.entity_id = ? AND b.report = 'trial_balance' AND b.period_to = ?
                           ORDER BY b.period_from IS ? DESC, b.id DESC""", (eid, d_to, d_from)).fetchall()
    if not found:
        return None, (f"No trial balance of SQL's as at {_dmy(d_to)} is kept, so this one can't be checked against SQL's. "
                      "Fetch SQL's Trial Balance for the same dates.")
    bad = 0
    for b in found:
        if not b["stored_path"] or not verify(b):
            bad += 1
            continue
        try:
            got = read(path_of(b).read_bytes())
        except (OSError, ReportError):
            got = None
        if got and got[0] == "trial_balance":
            return b, got[1]
        bad += 1
    return None, (f"SQL's trial balance as at {_dmy(d_to)} was kept, but its stored file is missing or has changed since it "
                  "was kept, so it can't be read again.")


def check_against_sql(con, eid, d_from=None, d_to=None):
    """This trial balance against SQL's own for the same as-at day, read again from its stored file: each account's
    closing against SQL's Year To Date, and for balance-sheet accounts the period's movements against SQL's Period To
    Date (when SQL's From date is the period's). SQL counts profit and loss from its own From date and moves the earlier
    amounts into retained earnings inside Period To Date, so a profit and loss account is compared with its lines from
    SQL's From date, and retained earnings with this closing plus the year's profit and loss before that date. Customer
    and supplier codes are added into their control accounts, as SQL prints them.
    Returns {outcome ('ok' | 'warn' | 'skipped'), text, differences: [{code, name, what, sql_sen, here_sen, diff_sen,
    text}], agree, compared, sql: {file_name, read_at, period_from, period_to}}."""
    B = _Books(con, eid)
    d_from, d_to = _period_of(B, d_from, d_to)
    if not B.uses_sql:
        return {"outcome": "skipped", "text": "This company's books are kept here, not in SQL, so there is no SQL trial balance "
                "to check against.", "differences": [], "agree": 0, "compared": 0, "sql": None}
    batch, rep = _stored_tb(con, eid, d_from, d_to)
    if batch is None:
        return {"outcome": "skipped", "text": rep, "differences": [], "agree": 0, "compared": 0, "sql": None}
    tb_from, _ = _period(rep.get("period"))
    src = {"file_name": batch["file_name"], "read_at": batch["read_at"], "period_from": tb_from, "period_to": d_to}
    mine = {(r["code"] or ""): r for r in trial_balance(con, eid, d_from, d_to, rollup=True)["accounts"]}
    after = _next(d_to)
    sql = {_key(a["code"]): a for a in rep.get("accounts") or []}
    same_from = tb_from == d_from
    diffs, agree, compared, skipped = [], 0, 0, []

    def label(code):
        return f"{code} {B.name(code)[0] or (sql.get(code) or {}).get('name') or ''}".strip()

    def net(pair):
        pair = pair or (0, 0)
        return (pair[0] or 0) - (pair[1] or 0)

    def differ(code, what, theirs, ours, words):
        diffs.append({"code": code, "name": B.name(code)[0] or (sql.get(code) or {}).get("name"), "what": what, "sql_sen": theirs,
                      "here_sen": ours, "diff_sen": ours - theirs,
                      "text": f"{label(code)}: {words} SQL's trial balance has {_money(theirs)}, the books here {_money(ours)} "
                              f"(a difference of {_money(ours - theirs)})."})

    # SQL's retained earnings hold the profit and loss from before its From date; the books here hold what the year
    # starts moved. From a date after the latest year start, add the year's profit and loss before SQL's From date;
    # from a date before it, take off the profit and loss from SQL's From date to the year start, which SQL still
    # shows on the profit and loss accounts.
    pl_before, f_last = 0, B.year_start(d_to)  # the closings are before a year end's move on the day after d_to
    if tb_from and tb_from >= f_last:
        pl_before = sum(B.balance(c, tb_from) or 0 for c in B.pl_codes())
    elif tb_from:
        pl_before = -sum(B.net(c, tb_from, f_last) for c in B.pl_codes())
    every = sorted((set(sql) | {k for k in mine if k}) - {""})
    listed = set(every)
    chart = {_key(k) for k in B.ch.accounts}

    def group_of(code):
        """The control account a customer's or supplier's code is compared within. SQL's trial balance can carry such a
        code's movements on the control account and print the code itself at nil (Other Debtors 1,760.00 against a
        customer's -1,760.00), so the two only agree as a group. Known from the chart or the customer's record, else, for
        a code that isn't an account in the chart, the '-0000' account of its family when SQL or the books here list one."""
        ctl = B.control(code)
        if ctl:
            return ctl if ctl in listed else None  # a control neither side lists: the code is compared on its own
        family = f"{code.split('-')[0]}-0000"
        if code not in chart and family != code and (family in sql or family in mine):
            return family
        return None

    members = {}
    for code in every:
        g = group_of(code)
        if g:
            members.setdefault(g, []).append(code)
    for code in every:
        if group_of(code):
            continue  # compared within its control account
        r, a = mine.get(code), sql.get(code)
        kind = B.kind(code)
        theirs = net((a or {}).get("ytd"))
        if r is not None and r["closing_sen"] is None:
            skipped.append(code)
            continue
        group = members.get(code, [])
        if any((mine.get(m) or {}).get("closing_sen", 0) is None for m in group):
            skipped.append(code)
            continue
        if kind == "pl":
            start = tb_from or B.year_start(d_to)
            ours = B.net(code, start, after) if tb_from else (r or {}).get("closing_sen") or 0
            for c in B.lines:  # a customer's or supplier's code rolls into its control account, as SQL prints it
                if B.control(c) == code:
                    ours += B.net(c, start, after)
            what = "profit and loss from SQL's From date"
            words = f"its lines from {_dmy(start)} to {_dmy(d_to)}:"
        else:
            ours = (r or {}).get("closing_sen") or 0
            what, words = "closing", f"its balance at {_dmy(d_to)}:"
            if group:
                theirs += sum(net((sql.get(m) or {}).get("ytd")) for m in group)
                ours += sum((mine.get(m) or {}).get("closing_sen") or 0 for m in group)
                words = f"its balance at {_dmy(d_to)}, with its {len(group)} customer or supplier code{'s' if len(group) != 1 else ''} ({', '.join(group)}):"
            if kind == "re" and pl_before:
                ours += pl_before
                words = (f"its balance at {_dmy(d_to)}, counting profit and loss into it up to {_dmy(tb_from)} as SQL does "
                         "from its From date:")
        compared += 1
        ok = theirs == ours
        if not ok:
            differ(code, what, theirs, ours, words)
        if kind not in ("pl", "re") and same_from and r is not None:
            ptd = net((a or {}).get("ptd")) + sum(net((sql.get(m) or {}).get("ptd")) for m in group)
            mv = r["dr_sen"] - r["cr_sen"] + sum((mine.get(m) or {}).get("dr_sen", 0) - (mine.get(m) or {}).get("cr_sen", 0) for m in group)
            if ptd != mv:
                ok = False
                differ(code, "period", ptd, mv, f"the movements from {_dmy(d_from)} to {_dmy(d_to)}:")
        if ok:
            agree += 1
    extra = []
    if not same_from:
        extra.append(f"SQL's trial balance runs from {_dmy(tb_from) if tb_from else 'no From date'}, not {_dmy(d_from)}, so the "
                     "period's movements aren't compared, only the balances.")
    if skipped:
        extra.append(f"Not compared, as no opening balance is kept for them: {', '.join(skipped)}.")
    if diffs:
        n = len({d["code"] for d in diffs})
        text = f"{n} account{'s differ' if n != 1 else ' differs'} from SQL's trial balance as at {_dmy(d_to)}; {agree} agree."
        outcome = "warn"
    else:
        text = f"Agrees with SQL's trial balance as at {_dmy(d_to)}: all {agree} account{'s' if agree != 1 else ''} compared."
        outcome = "ok"
    return {"outcome": outcome, "text": " ".join([text] + extra), "differences": diffs, "agree": agree, "compared": compared, "sql": src}
