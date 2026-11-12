"""What to do next: the list at the top of the Overview (and of a company's month page), worked out from the records on
the day given. Nothing is stored: a row goes as soon as the records show what it asked for."""
import calendar
from collections import Counter
from datetime import date, timedelta

from . import appsettings, auditpack, budget, db, rulebook, rules

# Days (General settings): a row due within SOON is 'soon'; payments and checklist items show from AHEAD days before;
# a backup is asked for after BACKUP days without one.
def _soon():
    return appsettings.get("soon_days")


def _ahead():
    return appsettings.get("ahead_days")
P1, P2, P3 = 1, 2, 3
STATES = ("overdue", "today", "soon", "later")  # most urgent first

# Checklist items with a deadline outside the office, shown from SOON days before (rule 1). KWSP, PERKESO and e-PCB
# due the same day are one row.
DEADLINES = ("kwsp", "perkeso", "epcb", "einv-rental", "einv-selfbilled", "budget")
SUBMIT = {"kwsp": "KWSP", "perkeso": "PERKESO", "epcb": "e-PCB"}
# Checklist items another row stands for: the statement (import it, rule 6) and the audit pack (rule 12).
COVERED = ("statement", rules.TASK_PACK)
STATEMENT_DUE, CLOSE_DUE = (1, 5), (1, 10)  # as the checklist's statement and audit pack items
# How each joiner or leaver reminder (rules.PEOPLE_TASKS) is named when a person's are listed together.
PEOPLE = {"ecp22": "e-CP22 to LHDN", "perkeso": "PERKESO registration", "kwsp": "KWSP registration",
          "stamp": "stamping of the appointment letter", "cp22a": "CP22A to LHDN"}
BACKED_UP = "Backup created: "  # how a backup is logged (app.backup)


def window(con, today):
    """The months the list goes through on the day given: per company, the months set up that aren't marked as filed
    and aren't before the first month tracked, from the month before the current cycle on (a later one only for what
    falls due within AHEAD days). Returns ([(company, month)], the older ones still open [(company, month)])."""
    start = db.shift_month(db.current_cycle(today), -1)
    shown, older = [], []
    for e in con.execute("SELECT * FROM entities WHERE active = 1 ORDER BY sort, id").fetchall():  # companies in use
        for r in con.execute("SELECT month, closed_at FROM months WHERE entity_id = ? ORDER BY month", (e["id"],)).fetchall():
            if not r["closed_at"] and not db.before_tracking(e, r["month"]):
                (older if r["month"] < start else shown).append((e, r["month"]))
    return shown, older


def older_open(con, today, entity_id=None):
    """The months still open before the window, for one muted line: Older months still open: August 2026 (one company
    with entity_id). What they hold that costs money or risks a penalty is in the list all the same (items)."""
    return [{"entity_id": e["id"], "month": m, "label": db.month_label(m)} for e, m in window(con, today)[1]
            if entity_id in (None, e["id"])]


def items(con, today, entity_id=None):
    """The list for the day given (a date), for one company with entity_id: one row per thing to do, {key, rule (1-13),
    entity_id, entity, month, text (one sentence), due (a date, or None), state (overdue, today, soon: within SOON
    days, or later), priority (1-3), amount, currency, go: where it is done {view, entity_id, month, and payment_id
    (payment_ids for a row of several), task_id (task_ids for a row of several), account_id or filter, as_at for the
    Budget page}}. Most urgent first: by priority, then overdue before today before soon before later, then by due
    date. The older months still open (window) give only the rows for payments not found (3 and 4), part paid (8) and
    lines to explain (9), and what falls due soon (5)."""
    shown, older = window(con, today)
    out = []
    for e in con.execute("SELECT * FROM entities WHERE active = 1 ORDER BY sort, id").fetchall():  # companies in use
        months, past = ([m for x, m in found if x["id"] == e["id"]] for found in (shown, older))
        if entity_id in (None, e["id"]) and (months or past):
            out += _company(con, e, months, past, today)
    if entity_id is None:
        out += _backup(con, today)
    iso, soon = today.isoformat(), (today + timedelta(days=_soon())).isoformat()
    for r in out:
        d = r["due"]
        r["state"] = ("later" if not d else "overdue" if d < iso else "today" if d == iso else "soon" if d <= soon else "later")
    return sorted(out, key=lambda r: (r["priority"], STATES.index(r["state"]), r["due"] or "9999"))


def upcoming(con, today, entity_id=None):
    """When there is nothing to do: the next thing that falls due after the day given, as {text, due}, or None. It is the
    soonest checklist item not done or payment out not paid in the months the list goes through (one company with
    entity_id)."""
    iso, found = today.isoformat(), []
    for e, m in window(con, today)[0]:
        if entity_id not in (None, e["id"]):
            continue
        for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? AND due_date > ? AND done_at IS NULL "
                             "ORDER BY due_date, sort", (e["id"], m, iso)):
            if not db.task_status(con, e, t)["done"]:
                found.append((t["due_date"], f"{_mon(m)} {e['code']}: {t['title']}"))
                break
        p = con.execute("SELECT * FROM payments WHERE entity_id = ? AND month = ? AND direction = 'out' AND paid_date IS NULL "
                        "AND due_date > ? ORDER BY due_date, id LIMIT 1", (e["id"], m, iso)).fetchone()
        if p:
            found.append((p["due_date"], f"Pay {db._names([p], [p])} from {e['code']}"))
    return dict(zip(("due", "text"), min(found))) if found else None


def _row(rule, e, month, text, due, priority, go, key, amount=None, currency=None):
    return {"key": f"{rule}:{e['id'] if e else '-'}:{month or '-'}:{key}", "rule": rule, "entity_id": e and e["id"],
            "entity": e and e["code"], "month": month, "text": text, "due": due, "priority": priority,
            "amount": amount, "currency": currency if amount is not None else None,
            "go": dict(go, entity_id=e and e["id"], month=month)}


def _mon(month):
    return calendar.month_abbr[int(month[5:7])]


def _s(n, many="s", one=""):
    return one if n == 1 else many


def _company(con, e, months, past, today):
    """The rows of one company, from its months in the window and the older ones still open (past)."""
    iso, cur = today.isoformat(), db.current_cycle(today)
    R = rulebook.get(con)
    ahead, soon = ((today + timedelta(days=n)).isoformat() for n in (_ahead(), _soon()))
    worked = [m for m in months if m <= cur]  # a later month only gives what falls due soon
    pays = []
    for m in months + past:
        for p in con.execute("SELECT * FROM payments WHERE entity_id = ? AND month = ? ORDER BY due_date, id", (e["id"], m)):
            ev = db.evidence(con, pay=p)
            status, missing = db.payment_status(con, p, e["uses_sql"], ev)
            pays.append({"p": p, "ev": ev, "status": status, "missing": missing,
                         "flag": None if p["paid_date"] else db.payment_flag(con, e, p, iso)})
    tasks = []
    for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND due_date <= ? AND done_at IS NULL ORDER BY due_date, sort",
                         (e["id"], ahead)):
        if t["month"] in months and not db.task_status(con, e, t)["done"]:
            tasks.append(t)
    rows = _deadlines(e, tasks, today, R) + _people(con, e, tasks, iso)
    rows += _not_found(e, [x for x in pays if x["p"]["month"] in worked + past], iso, soon, R)
    rows += _to_pay(con, e, pays, iso, ahead)
    for m in worked + past:
        mine = [x for x in pays if x["p"]["month"] == m]
        accts = db.month_statements(con, e, m)
        if m in worked:
            rows += _statements(e, m, accts, pays, today)
        rows += _explain(con, e, m, accts) + _part_paid(con, e, mine)
        if m in worked:
            rows += _documents(con, e, m, mine) + _ready(con, e, m, accts, mine)
    rows += _in_sql(con, e, worked, pays, cur)
    for m in months:
        rows += _checklist(e, m, [t for t in tasks if t["month"] == m])
    return rows


def _task_go(ts):
    """Go to the month page, to the checklist item (the first one, for a row that stands for several, which are all in
    task_ids). The bank reconciliation item goes to the Bank statements page, where it is done."""
    if len(ts) == 1 and ts[0]["code"] == "recon":
        return {"view": "bank"}
    go = {"view": "entity", "task_id": ts[0]["id"]}
    return dict(go, task_ids=[t["id"] for t in ts]) if len(ts) > 1 else go


def _pay_go(group):
    """Go to the payment's drawer, or to the month page with the payments the row counts for several."""
    if len(group) == 1:
        return {"view": "entity", "payment_id": group[0]["id"]}
    return {"view": "entity", "payment_ids": [p["id"] for p in group]}


def _deadlines(e, tasks, today, R):
    """Rule 1: KWSP, PERKESO and e-PCB to submit, e-Invoices to issue and the budget, from SOON days before they're due."""
    soon = (today + timedelta(days=_soon())).isoformat()
    rows, submit = [], {}
    for t in tasks:
        if t["code"] not in DEADLINES or t["due_date"] > soon:
            continue
        if t["code"] in SUBMIT:
            submit.setdefault((t["month"], t["due_date"]), []).append(t)
        else:
            rows.append(_row(1, e, t["month"], f"{_mon(t['month'])} {e['code']}: {t['title']}", t["due_date"], P1, _task_go([t]), t["code"]))
    for (m, d), ts in submit.items():
        names = [SUBMIT[c] for c in SUBMIT if any(t["code"] == c for t in ts)]
        legal = db.due(m, *R.legal_due("statutory"))
        rows.append(_row(1, e, m, f"Submit {_mon(m)} {db._listed(names)} (legal deadline {db.short_day(legal)})", d, P1,
                         _task_go(ts), f"submit-{d}"))
    return rows


def _people(con, e, tasks, iso):
    """Rule 2: a joiner's or leaver's filings due within AHEAD days, one row per person and due date. P1, but for a
    leaver who has gone already (a CP22A due before the last day can't be on time any more): P2."""
    groups = {}
    for t in tasks:
        if t["code"].startswith(("joiner-", "leaver-")):
            kind, key, pid = t["code"].split("-", 2)
            groups.setdefault((pid, kind, t["due_date"], t["month"]), []).append((key, t))
    rows = []
    for (pid, kind, d, m), found in groups.items():
        p = con.execute("SELECT name, start_date, end_date FROM payees WHERE id = ?", (int(pid),)).fetchone()
        day = p and (p["start_date"] if kind == "joiner" else p["end_date"])
        if day:
            verb = ("joined" if day <= iso else "joins") if kind == "joiner" else ("left" if day < iso else "leaves")
            text = f"{db.short_name(p['name'])} {verb} {db.short_day(day)}: {db._listed(PEOPLE.get(k, t['title']) for k, t in found)}"
        else:
            text = db._listed(t["title"] for _, t in found)
        gone = kind == "leaver" and day and day < iso
        rows.append(_row(2, e, m, text, d, P2 if gone else P1, _task_go([t for _, t in found]), f"{kind}-{pid}-{d}"))
    return rows


def _code(x, iso, soon, R):
    """What a payment not paid yet is in rules 3 and 4: not_on_statement, past_legal, or legal_soon (its legal deadline
    today or within SOON days, and no word of it yet: it is past due, or due after the deadline; rule 5 asks for one
    that falls due before it), else None."""
    f, p = x["flag"], x["p"]
    if f and f["code"] in ("not_on_statement", "past_legal"):
        return f["code"]
    legal = db.legal_due(p, R)
    return "legal_soon" if f and legal and iso <= legal <= soon and (p["due_date"] < iso or p["due_date"] > legal) else None


def _not_found(e, pays, iso, soon, R):
    """Rules 3 and 4, one row per company, month and direction: payments past due that aren't on a statement already
    imported (Not on <Mon> statement), and statutory payments not paid by the legal deadline (Past legal deadline), or
    past due with the deadline a few days away. Up to 3 are named, more are counted by type."""
    groups = {}
    for x in pays:
        code = _code(x, iso, soon, R)
        if code:
            groups.setdefault((code, x["p"]["month"], x["p"]["direction"]), []).append(x["p"])
    rows = []
    for (code, m, way), ps in groups.items():
        n, one = len(ps), len(ps) == 1
        same = len({p["currency"] for p in ps}) == 1 and all(p["amount"] is not None for p in ps)
        total = round(sum(p["amount"] for p in ps), 2) if same else None
        if code != "not_on_statement":
            legal = db.legal_due(ps[0], R)
            what = (f"{n} {e['code']} statutory payments are" if n > 3
                    else f"{db._names(ps, ps)} for {e['code']} {'is' if one else 'are'}")
            text = (f"{what} past the legal deadline of {db.short_day(legal)}: pay now or record the payment{_s(n)} (penalty risk)"
                    if code == "past_legal" else
                    f"{what} not recorded as paid, and the legal deadline is {db.short_day(legal)}: pay or record the "
                    f"payment{_s(n)} before then")
            rows.append(_row(4, e, m, text, legal, P1, _pay_go(ps), code, total, ps[0]["currency"]))
        else:
            mons = list(dict.fromkeys(_mon(p["due_date"]) for p in ps))
            what = f"{n} {_kinds(ps, R)} are" if n > 3 else f"{db._names(ps, ps)} {'is' if one else 'are'}"
            other = (f"enter the date{_s(n)} received" if way == "in" else f"enter the paid date{_s(n)}")
            text = (f"{what} not on the {e['code']} {db._listed(mons)} statement{_s(len(mons))}: link "
                    f"{'its bank line' if one else 'their bank lines'} or {other}")
            rows.append(_row(3, e, m, text, min(p["due_date"] for p in ps), P1, _pay_go(ps),
                             code if way == "out" else f"{code}-in", total, ps[0]["currency"]))
    return rows


def _kinds(ps, R=None):
    R = R or rulebook.FROZEN
    """What several payments are called in a sentence, by their types' words (Pay 8 AISB bills and statutory)."""
    return db._listed(R.plural(p["category"]) for p in ps)


def _to_pay(con, e, pays, iso, ahead):
    """Rule 5: payments out not paid yet that fall due within AHEAD days, one row per month, due date and currency
    with what is still to pay (as the Budget page has it as at today, which Go opens; a stored budget counts its lines, and a payment with no line
    counts as it is), how many are estimates and how many have no amount yet. A date shared by two months says which month each row is for."""
    groups = {}
    for x in pays:
        p = x["p"]
        if p["direction"] == "out" and not p["paid_date"] and iso <= p["due_date"] <= ahead:
            groups.setdefault((p["due_date"], p["currency"], p["month"]), []).append(p)
    shared = Counter(key[:2] for key in groups)
    rows = []
    for (d, cur, m), ps in sorted(groups.items()):
        left = [budget.payment_left(con, p, iso) for p in ps]
        known = [v for v in left if v is not None]
        total = round(sum(known), 2) if known else None
        one, blank = len(ps) == 1, left.count(None)
        est = sum(1 for p, v in zip(ps, left) if p["amount_is_estimate"] and v is not None)
        notes = ([("estimate" if one else f"{est} estimate{_s(est)}")] if est else []) + (
            [f"no amount{_s(len(ps))} yet"] if not known else [f"{blank} without an amount"] if blank else [])
        what = f"{db._names(ps, ps)} from {e['code']}" if one else f"{len(ps)} {e['code']} {_kinds(ps, rulebook.get(con))}"
        month = f" for {_mon(m)}" if shared[d, cur] > 1 else ""
        text = (f"Pay {what}{month} by {db.short_day(d)}" + (f": {db.money(total, cur)}" if known else "")
                + (f" ({', '.join(notes)})" if notes else ""))
        rows.append(_row(5, e, m, text, d, P1 if d == iso else P2, {"view": "budget", "as_at": iso}, f"{d}-{cur}", total, cur))
    return rows


def _statements(e, m, accts, pays, today):
    """Rule 6: the month's statements not imported once the month is over, with how many payments wait for them."""
    absent = [a for a in accts if not a["statement"]]
    if not absent or m >= today.isoformat()[:7]:
        return []
    waiting = [x["p"] for x in pays if x["flag"] and x["flag"]["code"] == "waiting_statement" and x["p"]["due_date"][:7] == m]
    n, k = (sum(1 for p in waiting if p["direction"] == way) for way in ("out", "in"))  # payments out, apart from money in
    counted = " and ".join(([f"{n} payment{_s(n)}"] if n else []) + ([f"{k} receipt{_s(k)}"] if k else []))
    text = (f"Import the {_mon(m)} statement{_s(len(absent))} for {db._listed(a['label'] for a in absent)}"
            + (f": {counted} waiting" if counted else ""))
    return [_row(6, e, m, text, db.due(m, *STATEMENT_DUE), P2, {"view": "bank", "account_id": absent[0]["id"]}, "import")]


def _explain(con, e, m, accts):
    """Rule 9: the lines on the month's statements left to explain, with the receipts among them."""
    lines = [a for a in accts if a["to_explain"]]
    if not lines:
        return []
    n = sum(a["to_explain"] for a in lines)
    receipts = con.execute(
        """SELECT a.currency, COUNT(*) AS n FROM statement_lines l JOIN statements s ON s.id = l.statement_id
           JOIN accounts a ON a.id = s.account_id WHERE a.entity_id = ? AND s.month = ? AND l.status = 'unmatched'
           AND l.amount > 0 GROUP BY a.currency ORDER BY a.currency""", (e["id"], m)).fetchall()
    got = ", ".join(f"{r['n']} {'RM' if r['currency'] == 'MYR' else r['currency']} receipt{_s(r['n'])}" for r in receipts)
    text = f"Explain {n} line{_s(n)} on the {e['code']} {_mon(m)} statement{_s(len(lines))}" + (f" ({got})" if got else "")
    return [_row(9, e, m, text, db.due(m, *CLOSE_DUE), P2, {"view": "bank", "account_id": lines[0]["id"], "filter": "to_explain"}, "explain")]


def _in_sql(con, e, worked, pays, cur):
    """Rule 7, for a company kept in SQL: the payments of these months not recorded there yet, paid (as the Overview
    counts them, db.not_in_sql) or past due and waiting for their SQL voucher (Waiting for SQL record), and the SQL
    entries of these months not linked to a payment yet (the month of an entry is its payroll cycle, as for a payment
    made early the month after)."""
    if not e["uses_sql"]:
        return []
    unrecorded = [x["p"] for x in pays if x["p"]["month"] in worked
                  and (db.not_in_sql(e, x["p"]) or x["flag"] and x["flag"]["code"] == "waiting_sql")]
    loose = [m for m in (db.current_cycle(date.fromisoformat(s["doc_date"])) for s in con.execute(
        "SELECT doc_date FROM sql_entries WHERE entity_id = ? AND status = 'unlinked' ORDER BY doc_date", (e["id"],)))
        if m in worked or m > cur and not db.before_tracking(e, m)]
    if not unrecorded and not loose:
        return []
    k = len(loose)
    unlinked = f"{k} SQL entr{_s(k, 'ies', 'y')} not linked yet"
    if unrecorded:
        n = len(unrecorded)
        mons = list(dict.fromkeys(_mon(d) for d in sorted(p["paid_date"] or p["due_date"] for p in unrecorded)))
        kinds = list(dict.fromkeys("Official Receipt" if p["direction"] == "in" else "Payment Voucher" for p in unrecorded))
        what = db._names(unrecorded, unrecorded) if n == 1 else f"{n} {_kinds(unrecorded, rulebook.get(con))}"
        text = (f"Paste the {db._listed(mons)} {db._listed(kinds)} listing{_s(len(mons) * len(kinds))}: {what} not recorded"
                + (f"; {unlinked}" if k else ""))
    else:
        text = f"Link or ignore {unlinked}"
    m = min([p["month"] for p in unrecorded] + loose)
    return [_row(7, e, m, text, db.due(m, *CLOSE_DUE), P2, {"view": "sql"}, "sql")]


def _part_paid(con, e, mine):
    """Rule 8: paid with bank lines that add up to less than the amount, and no note accepting the difference."""
    rows = []
    for x in mine:
        if x["status"] == "part_paid":
            p = x["p"]
            found = db.linked_total(con, p)
            text = (f"{db._names([p], [p])} is part paid: {db.money(found, p['currency'])} of {db.money(p['amount'], p['currency'])} "
                    f"found on the {e['code']} statements")
            rows.append(_row(8, e, p["month"], text, None, P2, _pay_go([p]), f"part-{p['id']}",
                             round(p["amount"] - found, 2), p["currency"]))
    return rows


def _documents(con, e, m, mine):
    """Rule 11: the documents still missing on the month's paid payments, part paid ones too (what SQL or the bank
    shows counts), counted by type, and the SQL vouchers that stand for an upload, to print from SQL for the pack (the
    Audit page names them too)."""
    paid = [x for x in mine if x["missing"] and x["status"] in ("paid", "part_paid")]
    if not paid:
        return []
    nos = auditpack.sql_to_print(con, e, [(x["p"], x["ev"]) for x in mine])
    R = rulebook.get(con)
    text = f"{_mon(m)} {e['code']}: {_missed(paid, R)} missing on {len(paid)} paid payment{_s(len(paid))}" + (
        f"; print {auditpack.to_print(nos, R)} from SQL" if nos else "")
    return [_row(11, e, m, text, db.due(m, *CLOSE_DUE), P3, {"view": "audit"}, "documents")]


def _missed(paid, R=None):
    R = R or rulebook.FROZEN
    """The documents missing on paid payments, counted by type, most missed first, and past 5 types the 4 most missed
    and the rest together: 9 bank receipts, 8 approvals, 8 claim forms, 7 invoices and 7 other documents."""
    counted = sorted(Counter(t for x in paid for t in x["missing"]).items(), key=lambda kv: (-kv[1], R.order(kv[0])))
    named = [f"{n} {R.counted(t, n)}" for t, n in counted]
    if len(named) > 5:
        rest = sum(n for _, n in counted[4:])
        named = named[:4] + [f"{rest} other document{_s(rest)}"]
    return db._listed(named)


def _ready(con, e, m, accts, mine):
    """Rule 12: Before you print is clear and no pack is built since the month's documents last changed (build and
    print it, naming the SQL vouchers to print); or a pack is built and the month isn't marked as filed (print and
    file it, then mark the month as filed). Before you print reads every document (kept for the files that haven't
    changed), so only once what is cheaper to check is clear: the month's payments complete and in SQL, its statements
    explained and its checklist done (as Before you print checks them)."""
    pack = db.latest_pack(con, e, m)
    if pack and not pack["changed"]:
        return [_row(12, e, m, f"{_mon(m)} {e['code']}: pack built {pack['when']}; mark the month as filed once it is printed",
                     None, P3, {"view": "audit"}, "filed")]
    if any(x["status"] != "complete" or db.not_in_sql(e, x["p"]) for x in mine) \
            or any(not a["statement"] or a["to_explain"] for a in accts):
        return []
    if any(st["missing"] or not st["done"] for st in (db.task_status(con, e, t) for t in auditpack._tasks(con, e, m))):
        return []
    r = auditpack.readiness(con, e, m, cached=True)
    if not r["ready"] or not r["pack_open"]:
        return []
    n = r["pack"] and r["pack"]["changed"]
    what = (f"build the pack again ({n} document{_s(n)} added or removed since {r['pack']['when']})" if n
            else "build and print the pack") + (f"; print {r['to_print']} from SQL" if r["to_print"] else "")
    return [_row(12, e, m, f"{_mon(m)} {e['code']} is ready: {what}", None, P3, {"view": "audit"}, "pack")]


def _checklist(e, m, tasks):
    """Rule 10: the month's other checklist items not done that are due within AHEAD days, as one row."""
    ts = [t for t in tasks if t["code"] not in DEADLINES + COVERED and not t["code"].startswith(("joiner-", "leaver-"))]
    if not ts:
        return []
    names = [t["title"] for t in ts]
    if len(ts) == 1:
        text = f"{_mon(m)} {e['code']}: {names[0]}"
    else:
        plain = len(ts) == 2 and not any(" and " in n or "," in n for n in names)  # else 'A and B and C' reads as more
        listed = db._listed(names) if plain else f"{names[0]} and {len(ts) - 1} more"
        text = f"Finish {len(ts)} {_mon(m)} {e['code']} checklist items: {listed}"
    return [_row(10, e, m, text, ts[0]["due_date"], P3, _task_go(ts), "checklist")]


def _backup(con, today):
    """Rule 13: no backup made in the last AHEAD days, or statements or SQL listings imported since the last one (as
    the activity log has them, up to the day given)."""
    end = f"{today.isoformat()}T23:59:59"
    last = con.execute("SELECT MAX(at) FROM activity WHERE what LIKE ? AND at <= ?", (BACKED_UP + "%", end)).fetchone()[0]
    if not last:
        return [_row(13, None, None, "Last backup: never", None, P3, {"view": "settings"}, "backup")]
    days = (today - date.fromisoformat(last[:10])).days
    since = sum(con.execute(f"SELECT COUNT(*) FROM {t} WHERE imported_at > ? AND imported_at <= ?", (last, end)).fetchone()[0]
                for t in ("statements", "sql_imports"))
    every = appsettings.get("backup_reminder_days")
    if days < every and not since:
        return []
    text = (f"Last backup: {db.short_day(last[:10])}" + (f", {days} days ago" if days >= every else "")
            + (f"; {since} import{_s(since)} since" if since else ""))
    return [_row(13, None, None, text, None, P3, {"view": "settings"}, "backup")]
