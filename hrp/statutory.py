"""The statutory payables check: is what was taken off each month's salaries (and the employer's share) paid to KWSP,
PERKESO and LHDN, in full and by the due day? Worked out from the books kept (hrp/books.py): pure reads, nothing here
writes anything except install (update 29), which makes the table of the accounts to check.

How the owner's books post it. A salary payment voucher dated in payroll month M credits the payables (420-1001 EPF
PAYABLE and so on) with the employees' shares taken off. The next month a voucher to each authority debits the payable
with those shares and debits the employer's share straight to an expense account (900-E001 EPF - EMPLOYER), crediting
the bank. Contributions for M are due by the 15th of M+1 (each account's due day, Setup › Statutory accounts).

Which accounts are checked is the owner's choice (statutory_accounts, Setup): one row per kind and payable account, with
the employer's share account if there is one. Nothing is checked until at least one is confirmed; until then the page
offers the accounts suggested from the chart by their names (suggest).

How a month is worked out, per payable account:
- what each document on the account is, from its other lines (those not on a statutory account), by the chart's types:
  a document whose other lines are all on income or expense accounts (a journal correcting the salary, or topping it
  up) is a correction; one with no income or expense line at all (only the bank, say) is a payment, or a refund when
  it credits the payable; any other (a salary voucher: salary and bank) takes off when it credits and pays when it
  debits. A line on an account the chart doesn't type is taken as neither, so a company whose chart isn't typed is
  worked out as if every debit were a payment and every credit a withholding;
- withheld: what documents dated in M credit to it (each document's net on the account; listed by document), with the
  corrections to M: a correction belongs to the month of the last withholding dated on or before it (so a journal on
  5 June topping up May's goes to May), or to its own month when that withholding is older than the month before;
- paid: what payment documents debit to it, given to the months they pay. A payment first pays the month before its
  own month (the usual case), unless its amount is exactly what another month up to its own still owes, or exactly all
  that is still owed (a voucher paying two months at once); what is left after the month before goes to the oldest
  month still owed, up to the payment's own month (paid in the same month as the salary), and anything more, when
  nothing up to its own month is owed, is an overpayment of the month before. A refund credited to the payable is
  taken back from the latest month overpaid, up to its own month; any rest of it is a withholding of its own month.
  What was owed before the first month shown (the payable's opening balance there, from the books) is the oldest month
  of all, "brought forward";
- employer's share: what the same payment documents debit to the employer's share account, shared out over the months
  the document pays in proportion;
- the balance at the end of M and on the due day, from the books (the opening balance carried in, plus the lines);
- status: 'cleared' (paid in full; paid_late says when the last of it came after the due day), 'due' (not in full yet,
  the due day not passed), 'late' (the due day passed with nothing paid), 'short' or 'over' (paid differs from withheld,
  difference says by how much), 'nothing' (nothing withheld or paid that month).
Months before the company's first month tracked are worked out the same way but marked before_tracking: shown grey and
never asked for in Next up.

The tracker payment of each payment document is the payment its SQL voucher is linked to (sql_entries.payment_id); its
amount is compared with what the document pays to the statutory accounts (every kind's payable and employer's share in
it, as one voucher to PERKESO may pay SOCSO, SKBBK and EIS together).

All amounts are whole sen, so every comparison is exact.
"""
import calendar
import re
from datetime import date, timedelta

from . import db

SINCE = 29
KINDS = ("epf", "socso", "eis", "skbbk", "pcb", "hrdf", "other")
KIND_WORDS = {"epf": "EPF (KWSP)", "socso": "SOCSO (PERKESO)", "eis": "EIS (SIP)", "skbbk": "SKBBK (Lindung 24 Jam)",
              "pcb": "PCB (LHDN)", "hrdf": "HRDF", "other": "Other statutory"}
STATUS_WORDS = {"cleared": "Cleared", "due": "Due", "late": "Late", "short": "Short", "over": "Over", "nothing": "Nothing"}
PROBLEMS = ("late", "short", "over")
DUE_DAY = 15

# Not in db.SCHEMA: update 29 is the only place it is made.
TABLE = """
CREATE TABLE IF NOT EXISTS statutory_accounts (
  id INTEGER PRIMARY KEY,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  kind TEXT NOT NULL CHECK (kind IN ('epf', 'socso', 'eis', 'skbbk', 'pcb', 'hrdf', 'other')),
  label TEXT NOT NULL,
  payable_code TEXT NOT NULL,
  employer_code TEXT,
  due_day INTEGER NOT NULL DEFAULT 15 CHECK (due_day BETWEEN 1 AND 31),
  notes TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE (entity_id, kind, payable_code)
)"""


def install(con):
    """Update 29: the table of the accounts the statutory payables check reads, one row per company, kind and payable
    account. Made empty, with its audit triggers before anything goes in (as ledger.install_openings): nothing is
    suggested into it, the owner confirms the accounts in Setup or on the Statutory tab. Nothing else changes."""
    from . import audit
    con.execute(TABLE)
    audit.refresh(con)


def ready(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'statutory_accounts'").fetchone())


# ---------- the suggestion from the chart ----------

# Tried in this order, so SOCSO SIP is EIS and SKBBK is its own kind, not SOCSO. Whole words of the name only.
_KIND_WORDS = (("skbbk", ("SKBBK", "LINDUNG")), ("eis", ("SIP", "EIS")), ("epf", ("EPF", "KWSP")),
               ("socso", ("SOCSO", "PERKESO", "SOCSCO")), ("pcb", ("PCB", "MTD", "LHDN")), ("hrdf", ("HRDF", "PSMB")))


def kind_of_name(name):
    """The statutory kind a name speaks of ('epf', 'socso', ...), or None."""
    up = str(name or "").upper()
    words = set(re.findall(r"[A-Z0-9]+", up))
    if "HRD CORP" in up or "HRDCORP" in words:
        return "hrdf"
    for kind, ws in _KIND_WORDS:
        if words & set(ws):
            return kind
    return None


def _accounts(con, eid):
    """{code: {name, type}} of the company's chart in use, plus the codes its account lines name that the chart lacks
    (type None), so a company whose chart isn't entered still gets a suggestion from SQL's own names."""
    from .ledger import _exists, _key
    out = {}
    for r in con.execute("SELECT code, name, type FROM gl_accounts WHERE entity_id = ? AND active = 1 ORDER BY code", (eid,)):
        out[_key(r["code"])] = {"name": r["name"], "type": r["type"]}
    if _exists(con, "ledger_lines"):
        for r in con.execute("""SELECT account_code, MAX(account_name) AS name FROM ledger_lines WHERE entity_id = ?
                                AND account_name IS NOT NULL GROUP BY account_code ORDER BY account_code""", (eid,)):
            out.setdefault(_key(r["account_code"]), {"name": r["name"], "type": None})
    return out


def suggest(con, eid):
    """The accounts the chart's names suggest, not yet in Setup: [{kind, label, payable_code, payable_name,
    employer_code, employer_name, due_day}]. A payable is a liability (or an account of no type) whose name has PAYABLE
    or ACCRU in it; the employer's share is an expense (or no type) of the same kind with EMPLOYER in its name."""
    accts = _accounts(con, eid)
    have = set()
    if ready(con):
        have = {(r["kind"], r["payable_code"]) for r in con.execute("SELECT kind, payable_code FROM statutory_accounts WHERE entity_id = ?", (eid,))}
    payables, employers = [], {}
    for code, a in sorted(accts.items()):
        kind, up = kind_of_name(a["name"]), str(a["name"] or "").upper()
        if not kind:
            continue
        if a["type"] in (None, "liability") and ("PAYABLE" in up or "ACCRU" in up):
            payables.append((kind, code, a["name"]))
        elif a["type"] in (None, "expense") and "EMPLOYER" in re.findall(r"[A-Z]+", up):
            employers.setdefault(kind, (code, a["name"]))
    out = []
    for kind, code, name in payables:
        if (kind, code) in have:
            continue
        emp = employers.get(kind)
        out.append({"kind": kind, "label": KIND_WORDS[kind], "payable_code": code, "payable_name": name,
                    "employer_code": emp[0] if emp else None, "employer_name": emp[1] if emp else None, "due_day": DUE_DAY})
    return out


def mapping(con, eid):
    """The accounts confirmed for the company and in use, in Setup's order."""
    if not ready(con):
        return []
    return [dict(r) for r in con.execute("""SELECT * FROM statutory_accounts WHERE entity_id = ? AND active = 1
                                            ORDER BY sort, id""", (eid,))]


# ---------- months and days ----------

def _month(d):
    return d[:7]


def _first(m):
    return f"{m}-01"


def _last(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{m}-{calendar.monthrange(y, mo)[1]:02d}"


def _after(d):
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def due_date(month, day):
    """The due day of the month after the payroll month, on the month's last day when it is shorter."""
    nxt = db.shift_month(month, 1)
    y, mo = int(nxt[:4]), int(nxt[5:7])
    return date(y, mo, min(int(day or DUE_DAY), calendar.monthrange(y, mo)[1])).isoformat()


def _rm(sen):
    return f"RM {abs(sen) / 100:,.2f}"


def default_range(con, eid, today):
    """This financial year to date: (its first month, today's month)."""
    from .books import year_start
    return _month(year_start(con, eid, today.isoformat())), _month(today.isoformat())


# ---------- the documents ----------

def _docs(con, eid, codes, d_from):
    """{(origin, doc_key): {doc_no, origin, date, nets: {code: sen, debit above 0}}} of the current documents dated from
    d_from that touch any of the codes, in date order, with the nets of all their lines (the other lines say what kind
    of document it is)."""
    from .ledger import _exists, _key
    if not codes or not _exists(con, "ledger_lines"):
        return {}
    marks = ", ".join("?" * len(codes))
    out = {}
    for r in con.execute(f"""SELECT d.origin, d.doc_key, d.doc_no, d.doc_date, d.description, l.account_code, l.dr_sen, l.cr_sen
                             FROM ledger_lines l JOIN ledger_docs d ON d.id = l.doc_id
                             WHERE d.entity_id = ? AND d.state = 'current' AND d.doc_date >= ?
                             AND d.id IN (SELECT doc_id FROM ledger_lines WHERE UPPER(TRIM(account_code)) IN ({marks}))
                             ORDER BY d.doc_date, d.doc_key, l.seq""", (eid, d_from, *codes)):
        doc = out.setdefault((r["origin"], r["doc_key"]), {"doc_no": r["doc_no"], "origin": r["origin"], "date": r["doc_date"],
                                                           "description": r["description"], "nets": {}})
        code = _key(r["account_code"])
        doc["nets"][code] = doc["nets"].get(code, 0) + r["dr_sen"] - r["cr_sen"]
    return out


def _tracker(con, eid, doc_nos):
    """{doc no. upper: {id, month, amount_sen, paid_date, description, category}} of the payments the SQL vouchers are linked to."""
    out = {}
    for no in doc_nos:
        r = con.execute("""SELECT p.id, p.month, p.amount, p.paid_date, p.description, p.category FROM sql_entries s JOIN payments p
                           ON p.id = s.payment_id WHERE s.entity_id = ? AND UPPER(TRIM(s.doc_no)) = ? ORDER BY s.id LIMIT 1""",
                        (eid, no.strip().upper())).fetchone()
        if r:
            out[no.strip().upper()] = {"id": r["id"], "month": r["month"], "amount_sen": None if r["amount"] is None else int(round(r["amount"] * 100)),
                                       "paid_date": r["paid_date"], "description": r["description"], "category": r["category"]}
    return out


# ---------- one payable account ----------

def _kind_of_doc(ch, nets, all_codes):
    """What a document is to the statutory accounts, from its lines on other accounts (see the module's notes):
    'correction' (all on income or expense), 'money' (none on income or expense: a payment or a refund), or 'usual'
    (both, or an account the chart doesn't type: a debit pays, a credit takes off)."""
    kinds = {ch.kind(c) for c, v in nets.items() if c not in all_codes and v}
    if kinds == {"pl"}:
        return "correction"
    if kinds and None not in kinds and "pl" not in kinds:
        return "money"
    return "usual"


def _allocate(months, owed, amount, natural, own):
    """Gives a payment of `amount` (sen) to the months it pays: returns [(month, sen)] and what is left over. owed:
    {month: still owed}, changed in place; months: every month in order (the brought-forward one first); natural: the
    month before the payment's own; own: the payment's own month, the latest it can pay. See the module's notes for the
    order."""
    earlier = [m for m in months if m <= own and owed.get(m, 0) > 0]
    if not earlier:
        return [], amount
    if owed.get(natural, 0) == amount:
        pick = [natural]
    else:
        exact = [m for m in earlier if owed[m] == amount]
        if exact:
            pick = exact[:1]
        elif sum(owed[m] for m in earlier) == amount:
            pick = earlier
        else:
            pick = ([natural] if owed.get(natural, 0) > 0 else []) + [m for m in earlier if m != natural]
    out, left = [], amount
    for m in pick:
        if left <= 0:
            break
        take = min(left, owed[m])
        if take > 0:
            owed[m] -= take
            left -= take
            out.append((m, take))
    return out, left


def _share(total, parts):
    """total (sen) shared over parts [(key, weight)] in proportion, the remainder to the last, exactly."""
    w = sum(x for _, x in parts)
    if not parts or not w:
        return {}
    out, given = {}, 0
    for i, (k, x) in enumerate(parts):
        v = total - given if i == len(parts) - 1 else total * x // w
        out[k] = out.get(k, 0) + v
        given += v
    return out


def _one(B, ent, row, docs, all_codes, tracker, m_from, m_to, through, today):
    """The months m_from..m_to of one payable account (see the module's notes)."""
    from .ledger import _key
    pay, emp = _key(row["payable_code"]), _key(row["employer_code"]) if row["employer_code"] else None
    start = _first(m_from)
    bf_month = db.shift_month(m_from, -1)
    opening = B.balance(pay, start)
    months = [bf_month]
    m = m_from
    while m <= through:
        months.append(m)
        m = db.shift_month(m, 1)
    owed = {m: 0 for m in months}
    withheld = {m: 0 for m in months}
    credits = {m: [] for m in months}
    if opening is not None and opening < 0:
        owed[bf_month] = withheld[bf_month] = -opening
    paid = {m: [] for m in months}
    last_w = bf_month if withheld[bf_month] else None  # the month of the last withholding so far
    for d in docs.values():
        net = d["nets"].get(pay, 0)
        if not net:
            continue
        dm = _month(d["date"])
        if dm > through:
            continue
        natural = db.shift_month(dm, -1)
        what = _kind_of_doc(B.ch, d["nets"], all_codes)
        credit = {"doc_no": d["doc_no"], "origin": d["origin"], "date": d["date"], "amount_sen": -net, "description": d["description"]}
        if what == "correction":  # changes what was taken off the month it corrects, paid or not
            to = last_w if last_w and last_w >= natural else dm
            withheld[to] += -net
            owed[to] += -net
            credits[to].append({**credit, "correction": True})
            continue
        given = {}
        if net < 0 and what == "money":  # a refund: taken back from the latest month overpaid
            left = -net
            for mm in reversed([x for x in months if x <= dm and owed[x] < 0]):
                take = min(left, -owed[mm])
                owed[mm] += take
                given[mm] = given.get(mm, 0) - take
                left -= take
                if not left:
                    break
            net = -left
        if net < 0:
            # A salary is withheld for the payroll month it pays, which its description names: a September salary paid
            # late on 16 October ("... SEPT 26 (07/09/26 - 15/09/26)") is contributed with September's, so it counts
            # there. Only a named month up to two months before the document's own is taken; else its own month.
            wm = db.filing_month(d["description"] or "", d["date"])
            if not (db.shift_month(dm, -2) <= wm <= dm and wm in withheld):
                wm = dm
            withheld[wm] += -net
            owed[wm] += -net
            credits[wm].append({**credit, "amount_sen": -net, **({"for_month": wm} if wm != dm else {})})
            last_w = wm if last_w is None or wm > last_w else last_w
        elif net > 0:
            got, left = _allocate(months, owed, net, natural, dm)
            for mm, s in got:
                given[mm] = given.get(mm, 0) + s
            if left:  # more than was owed up to its own month: an overpayment of the month before the document's
                given[natural] = given.get(natural, 0) + left
                owed[natural] -= left
        if not given:
            continue
        employer = d["nets"].get(emp, 0) if emp else 0
        shares = _share(employer, sorted(given.items())) if employer else {}
        statutory = sum(v for c, v in d["nets"].items() if c in all_codes and v > 0)
        t = tracker.get(d["doc_no"].strip().upper()) if d["origin"] == "sql" else None
        for mm, s in sorted(given.items()):
            paid[mm].append({"doc_no": d["doc_no"], "origin": d["origin"], "date": d["date"], "amount_sen": s,
                             "employer_sen": shares.get(mm, 0), "doc_payable_sen": d["nets"][pay], "doc_employer_sen": employer,
                             "doc_statutory_sen": statutory, "description": d["description"],
                             "tracker": None if not t else {**t, "matches": t["amount_sen"] == statutory, "expected_sen": statutory}})
    first = ent["first_month"] if ent else None
    out = []
    for m in months[1:]:
        if m < m_from or m > m_to:
            continue
        due = due_date(m, row["due_day"])
        p_all = sum(x["amount_sen"] for x in paid[m])
        p_due = sum(x["amount_sen"] for x in paid[m] if x["date"] <= due)
        diff = p_all - withheld[m]
        if not withheld[m] and not p_all:
            status = "nothing"
        elif diff > 0:
            status = "over"
        elif diff == 0:
            status = "cleared"
        elif today.isoformat() <= due:
            status = "due"
        elif p_all == 0:
            status = "late"
        else:
            status = "short"
        late_paid = status == "cleared" and p_due < withheld[m]
        bal_end = B.balance(pay, _first(db.shift_month(m, 1)))
        bal_due = B.balance(pay, _after(due)) if due < today.isoformat() else None
        out.append({"month": m, "label": db.month_label(m), "due": due, "withheld_sen": withheld[m], "credits": credits[m],
                    "paid_sen": p_all, "paid_by_due_sen": p_due, "employer_sen": sum(x["employer_sen"] for x in paid[m]),
                    "payments": paid[m], "difference_sen": diff, "balance_end_sen": bal_end, "balance_due_sen": bal_due,
                    "status": status, "paid_late": late_paid, "before_tracking": bool(first and m < first),
                    "text": _text(row, m, status, diff, due, late_paid, paid[m])})
    bf_paid = paid[bf_month]
    return {"id": row["id"], "kind": row["kind"], "label": row["label"] or KIND_WORDS[row["kind"]], "payable_code": pay,
            "payable_name": B.name(pay)[0], "employer_code": emp, "employer_name": B.name(emp)[0] if emp else None,
            "due_day": row["due_day"], "opening_sen": opening, "opening_day": start,
            "brought_forward": {"owed_sen": withheld[bf_month], "paid_sen": sum(x["amount_sen"] for x in bf_paid),
                                "still_owed_sen": owed[bf_month] if opening is not None else None, "payments": bf_paid},
            "months": out,
            "notes": [] if opening is not None else [f"No opening balance of {pay} is kept at {date.fromisoformat(start):%d/%m/%Y}, so what "
                                                     "was owed before then is unknown and its balances can't be shown. "
                                                     "Fetch SQL's trial balance for that day."]}


def _text(row, m, status, diff, due, late_paid, payments):
    label = row["label"] or KIND_WORDS[row["kind"]]
    when = db.month_label(m)
    due_words = f"{date.fromisoformat(due):%d %b %Y}"
    if status == "cleared":
        last = max((x["date"] for x in payments), default=None)
        return (f"{label} for {when} paid in full, the last of it on {date.fromisoformat(last):%d %b %Y}, after the due day {due_words}."
                if late_paid and last else f"{label} for {when} paid in full.")
    if status == "due":
        return f"{label} for {when} is due by {due_words}."
    if status == "late":
        return f"{label} for {when} wasn't paid by {due_words}."
    if status == "short":
        return f"{label} for {when}: {_rm(-diff)} less was paid than was taken off the salaries."
    if status == "over":
        return f"{label} for {when}: {_rm(diff)} more was paid than was taken off the salaries."
    return f"Nothing was taken off the salaries for {label} in {when}."


# ---------- the report ----------

def report(con, eid, m_from=None, m_to=None, today=None):
    """The check for a company and a range of payroll months (default: this financial year to date): {entity_id, from,
    to, configured, suggestion, accounts: [one per payable account: {kind, label, payable_code, employer_code, due_day,
    opening_sen, brought_forward, months: [{month, due, withheld_sen, credits, paid_sen, employer_sen, payments,
    difference_sen, balance_end_sen, balance_due_sen, status, paid_late, before_tracking, text}], notes}], problems:
    [{kind, label, month, status, text, due, payable_code}] (tracked months only), summary}. Amounts in sen, balances
    signed (debit above 0, so a payable owed is below 0)."""
    from .books import _Books
    from .ledger import _key
    today = today or date.today()
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    d_from, d_to = default_range(con, eid, today)
    m_from, m_to = m_from or d_from, m_to or d_to
    if m_from > m_to:
        m_from, m_to = m_to, m_from
    rows = mapping(con, eid)
    base = {"entity_id": eid, "from": m_from, "to": m_to, "suggestion": suggest(con, eid), "first_month": ent["first_month"] if ent else None}
    if not rows:
        stopped = ready(con) and bool(con.execute("SELECT 1 FROM statutory_accounts WHERE entity_id = ?", (eid,)).fetchone())
        return {**base, "configured": False, "stopped": stopped, "accounts": [], "problems": [], "empty": True,
                "summary": "All the statutory accounts confirmed for this company are stopped, so nothing is checked."
                if stopped else "No statutory accounts are confirmed for this company yet, so nothing is checked."}
    B = _Books(con, eid)
    codes = sorted({_key(r["payable_code"]) for r in rows} | {_key(r["employer_code"]) for r in rows if r["employer_code"]})
    all_codes = set(codes)
    docs = _docs(con, eid, codes, _first(m_from))
    latest = max((_month(d["date"]) for d in docs.values()), default=m_to)
    through = max(m_to, latest, _month(today.isoformat()))
    tracker = _tracker(con, eid, sorted({d["doc_no"] for d in docs.values() if d["origin"] == "sql"}))
    accounts = [_one(B, ent, r, docs, all_codes, tracker, m_from, m_to, through, today) for r in rows]
    problems = [{"kind": a["kind"], "label": a["label"], "payable_code": a["payable_code"], "month": x["month"], "status": x["status"],
                 "difference_sen": x["difference_sen"], "due": x["due"], "text": x["text"]}
                for a in accounts for x in a["months"] if x["status"] in PROBLEMS and not x["before_tracking"]]
    empty = all(x["status"] == "nothing" for a in accounts for x in a["months"] if not x["before_tracking"])
    return {**base, "configured": True, "stopped": False, "accounts": accounts, "problems": problems, "empty": empty,
            "summary": _summary(accounts, problems)}


def _summary(accounts, problems):
    """In words: the problems; else how far every tracked month is cleared (a month with nothing in it is passed over,
    never counted as cleared), and the next due day."""
    if problems:
        n = len(problems)
        return f"{n} statutory payable{'s' if n != 1 else ''} to look at: " + "; ".join(p["text"] for p in problems[:4]) + (
            f"; and {n - 4} more." if n > 4 else "")
    tracked = [x for a in accounts for x in a["months"] if not x["before_tracking"]]
    if all(x["status"] == "nothing" for x in tracked):
        return "No statutory payables were taken off or paid in these months, so there was nothing to check."
    upto = None
    for m in sorted({x["month"] for x in tracked}):
        st = {x["status"] for x in tracked if x["month"] == m}
        if not st <= {"cleared", "nothing"}:
            break
        if "cleared" in st:
            upto = m
    due = sorted({x["due"] for x in tracked if x["status"] == "due"})
    words = f"All statutory payables cleared up to {db.month_label(upto)}." if upto else "Nothing is cleared yet in these months."
    if due:
        words += f" Next due by {date.fromisoformat(due[0]):%d %b %Y}."
    return words


def next_up(con, eid, today):
    """Next up's statutory rows of a company: [{kind, label, payable_code, month, status, text, due}] of the tracked
    months from a year before today's month, late or short. Empty until accounts are confirmed."""
    if not mapping(con, eid):
        return []
    m_to = _month(today.isoformat())
    return [p for p in report(con, eid, db.shift_month(m_to, -12), m_to, today)["problems"] if p["status"] in ("late", "short")]
