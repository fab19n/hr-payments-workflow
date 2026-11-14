"""The financial statements: the profit and loss account and the balance sheet, laid out as SQL Account prints them,
worked out from the trial balance of hrp/books.py (customers' and suppliers' codes added into their control accounts).
Pure reads: nothing here writes anything.

Where an account goes. Each account sits in the section of its SQL group (the chart's SQL type, Setup › Chart of
accounts): Sales (SL, with Sales adjustment SA taken off), Cost of sales (CO), Other income (OI, EO), Expenses (EP),
Taxation (TX) and Appropriation (AP) in the profit and loss account; Non-current assets (FA), Investments (IV), Other
assets (OA), Current assets (CA), Current liabilities (CL), Non-current liabilities (LT), Other liabilities (OL),
Capital (CP), Reserves (RV) and Retained earnings (RE) in the balance sheet. An income or expense account with no SQL
group goes under Other income or Expenses, and an asset, liability or equity account with none under Current assets,
Current liabilities or Capital, each with a note. An account with no type at all is listed under Not classified,
counted in neither statement's totals, with a note to set its type in Setup. A sub-account (parent account set in the
chart) is shown under its parent, with the parent's total.

Appropriation accounts are equity in the books (they don't start again at the year start, as SQL keeps them): the
profit and loss account shows what moved on them in the period below the profit after tax, and the balance sheet shows
their balance under equity.

All amounts are whole sen. In the statements each section's amounts are shown the way round they are usual: income,
liabilities and equity as credits above 0, costs and assets as debits above 0. Every comparison is exact.
"""
from datetime import date, timedelta

from . import books
from .ledger import _iso, _key, _money
from .partybook import GROUP_TYPE, SQL_GROUPS

GROUP_NAMES = {code: name for code, name, _ in SQL_GROUPS}
PL_GROUPS = ("SL", "SA", "CO", "OI", "EO", "EP", "TX")
BS_GROUPS = ("FA", "IV", "OA", "CA", "CL", "LT", "OL", "CP", "RV", "AP")
NOT_CLASSIFIED = "NC"
MAX_MONTHS = 24
NC_NOTE = "Not typed in the chart of accounts"

# The layouts, in SQL's order. A section: (key, title, groups, sign, total label); sign -1 shows credits above 0.
# A total: (key, label, {section or total key: +1 or -1}).
PL_LAYOUT = [
    ("section", "sales", "Sales", ("SL", "SA"), -1, "Total sales"),
    ("section", "cost_of_sales", "Cost of sales", ("CO",), 1, "Total cost of sales"),
    ("total", "gross_profit", "Gross profit", {"sales": 1, "cost_of_sales": -1}),
    ("section", "other_income", "Other income", ("OI", "EO"), -1, "Total other income"),
    ("section", "expenses", "Expenses", ("EP",), 1, "Total expenses"),
    ("total", "before_tax", "Net profit or loss before tax", {"gross_profit": 1, "other_income": 1, "expenses": -1}),
    ("section", "taxation", "Taxation", ("TX",), 1, "Total taxation"),
    ("total", "after_tax", "Net profit or loss after tax", {"before_tax": 1, "taxation": -1}),
    ("section", "appropriation", "Appropriation", ("AP",), 1, "Total appropriation"),
    ("total", "after_appropriation", "Profit or loss after appropriation", {"after_tax": 1, "appropriation": -1}),
    ("section", "not_classified", "Not classified", (NOT_CLASSIFIED,), 1, "Total not classified (debit above 0)"),
]
BS_LAYOUT = [
    ("section", "non_current_assets", "Non-current assets", ("FA",), 1, "Total non-current assets"),
    ("section", "investments", "Investments", ("IV",), 1, "Total investments"),
    ("section", "other_assets", "Other assets", ("OA",), 1, "Total other assets"),
    ("section", "current_assets", "Current assets", ("CA",), 1, "Total current assets"),
    ("section", "current_liabilities", "Current liabilities", ("CL",), -1, "Total current liabilities"),
    ("total", "net_current_assets", "Net current assets", {"current_assets": 1, "current_liabilities": -1}),
    ("section", "non_current_liabilities", "Non-current liabilities", ("LT",), -1, "Total non-current liabilities"),
    ("section", "other_liabilities", "Other liabilities", ("OL",), -1, "Total other liabilities"),
    ("total", "net_assets", "Net assets", {"non_current_assets": 1, "investments": 1, "other_assets": 1, "net_current_assets": 1,
                                           "non_current_liabilities": -1, "other_liabilities": -1}),
    ("section", "capital", "Capital", ("CP",), -1, "Total capital"),
    ("section", "reserves", "Reserves", ("RV",), -1, "Total reserves"),
    ("section", "retained", "Retained earnings brought forward", ("RE",), -1, "Total retained earnings brought forward"),
    ("section", "appropriation", "Appropriation", ("AP",), -1, "Total appropriation"),
    ("line", "profit", "Profit or loss for the year to date"),
    ("total", "total_equity", "Total equity", {"capital": 1, "reserves": 1, "retained": 1, "appropriation": 1, "profit": 1}),
    ("section", "not_classified", "Not classified", (NOT_CLASSIFIED,), 1, "Total not classified (debit above 0)"),
]
# Totals only shown when one of these sections has an account.
OPTIONAL_TOTALS = {"after_appropriation": ("appropriation",)}


# ---------- small helpers ----------

def _day(d):
    return date.fromisoformat(d)


def _dmy(d):
    return f"{_day(d):%d/%m/%Y}"


def _plus(a, b):
    return None if a is None or b is None else a + b


def _times(n, a):
    return None if a is None else n * a


def _last_day(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day


def _year_back(d):
    """The same day a year before (the month's last day stays the month's last day: 29/02 goes to 28/02)."""
    x = _day(d)
    last = x.day == _last_day(x.year, x.month)
    day = _last_day(x.year - 1, x.month) if last else min(x.day, _last_day(x.year - 1, x.month))
    return date(x.year - 1, x.month, day).isoformat()


def _year_back_from(d):
    """The start of the same period a year before: the day after the day before d moved back a year, so a period
    starting 28/02/2025 compares from 28/02/2024 (not 29/02) and one starting 01/03/2025 from 01/03/2024."""
    return (_day(_year_back((_day(d) - timedelta(days=1)).isoformat())) + timedelta(days=1)).isoformat()


def _months(d_from, d_to):
    """[(from, to)] of each calendar month in the period, the first and last cut to the period."""
    out, a = [], _day(d_from)
    end = _day(d_to)
    while a <= end:
        b = min(date(a.year, a.month, _last_day(a.year, a.month)), end)
        out.append((a.isoformat(), b.isoformat()))
        a = b + timedelta(days=1)
    return out


def _chart(con, eid):
    """{code: {code, name, type, sql_type, parent_code}} of the company's chart of accounts as it is now."""
    have = {r[1] for r in con.execute("PRAGMA table_info(gl_accounts)")}
    pick = ", ".join(c if c in have else f"NULL AS {c}" for c in ("code", "name", "type", "sql_type", "parent_code"))
    return {_key(r["code"]): dict(r) for r in con.execute(
        f"SELECT {pick} FROM gl_accounts WHERE entity_id = ? ORDER BY active, code", (eid,))}


def _group(chart, code, kind):
    """(SQL group the account is shown under, a note when it is put there for want of its SQL group, or None)."""
    if code is None or kind == "re":
        return "RE", None
    a = chart.get(code) or {}
    st, t = a.get("sql_type"), a.get("type")
    if kind == "pl":
        if st in PL_GROUPS:
            return st, None
        g = "OI" if (t or GROUP_TYPE.get(st)) == "income" else "EP"
        why = f"its SQL group is {GROUP_NAMES[st]}, a balance sheet group" if st else "it has no SQL group"
        return g, (f"{code} {a.get('name') or ''} is {'an' if (t or 'income')[0] in 'aeiou' else 'a'} {t or 'income or expense'} account but {why}, so it is shown under "
                   f"{'Other income' if g == 'OI' else 'Expenses'}. Set its SQL group in Setup › Chart of accounts.")
    if kind == "bs":
        if st in BS_GROUPS:
            return st, None
        t = t if t in ("asset", "liability", "equity") else GROUP_TYPE.get(st)
        g = {"asset": "CA", "liability": "CL"}.get(t, "CP")
        why = f"its SQL group is {GROUP_NAMES[st]}, a profit and loss group" if st else "it has no SQL group"
        where = {"CA": "Current assets", "CL": "Current liabilities", "CP": "Capital"}[g]
        return g, (f"{code} {a.get('name') or ''} is {'an' if (t or 'x')[0] in 'aeiou' else 'a'} {t} account but {why}, so it is shown under {where}. Set its SQL "
                   "group in Setup › Chart of accounts.")
    return NOT_CLASSIFIED, None


# ---------- laying out the sections ----------

def _layout(layout, placed, chart, names, rolled, ncols, lines=None):
    """The blocks of a statement. placed: {group: {code: [debit-signed amount per column]}}. lines: {key: [amounts]} for a
    'line' block (the balance sheet's profit). Returns (blocks, figures {key: [display amount per column]})."""
    figures, blocks = {}, []
    lines = lines or {}
    zero = [0] * ncols
    for item in layout:
        if item[0] == "section":
            _, key, title, groups, sign, total_label = item
            codes = {}
            for g in groups:
                codes.update(placed.get(g, {}))
            if not codes:
                figures[key] = zero[:]
                continue
            rows, total = _rows(codes, chart, names, rolled, sign, ncols, groups)
            figures[key] = total
            blocks.append({"kind": "section", "key": key, "title": title, "sign": "credit" if sign < 0 else "debit",
                           "rows": rows, "total_label": total_label, "total": total})
        elif item[0] == "line":
            _, key, label = item
            figures[key] = lines.get(key, zero[:])
            blocks.append({"kind": "line", "key": key, "label": label, "amounts": figures[key]})
        else:
            _, key, label, parts = item
            amounts = zero[:]
            for k, n in parts.items():
                amounts = [_plus(a, _times(n, b)) for a, b in zip(amounts, figures.get(k, zero))]
            figures[key] = amounts
            need = OPTIONAL_TOTALS.get(key)
            if need and not any(b["key"] in need for b in blocks if b["kind"] == "section"):
                continue
            blocks.append({"kind": "total", "key": key, "label": label, "amounts": amounts})
    return blocks, figures


def _home(chart, code):
    """The SQL group an account of the chart is shown under, from its chart entry alone (for a parent with no amount)."""
    a = chart.get(code) or {}
    if a.get("sql_type") == "RE":
        return "RE"
    t = a.get("type")
    kind = "pl" if t in ("income", "expense") else "bs" if t in ("asset", "liability", "equity") else None
    return _group(chart, code, kind)[0]


def _rows(codes, chart, names, rolled, sign, ncols, groups=None):
    """The rows of one section: each account (sub-accounts under their parent, with the parent's total after them),
    amounts shown the section's way round. groups: the section's SQL groups; a parent placed in another section isn't
    brought in, so the sub-account is shown on its own. Returns (rows, section total per column)."""
    zero = [0] * ncols
    shown = {c: [_times(sign, a) for a in v] for c, v in codes.items()}
    nodes = set(shown)
    parent_of = {}
    for c in list(nodes):  # bring in the parents (and theirs) the chart names, so sub-accounts sit under them
        seen, x = {c}, c
        while True:
            p = _key((chart.get(x) or {}).get("parent_code"))
            if not p or p in seen or p == x:
                break
            if p not in shown and groups is not None and _home(chart, p) not in groups:
                break  # the parent belongs in another section: the sub-account stands on its own here
            parent_of[x] = p
            nodes.add(p)
            seen.add(p)
            x = p
    children = {}
    for c in nodes:
        p = parent_of.get(c)
        if p in nodes:
            children.setdefault(p, []).append(c)
    roots = sorted(c for c in nodes if parent_of.get(c) not in nodes)
    rows, done = [], set()

    def emit(c, depth):
        done.add(c)
        own = shown.get(c, zero[:])
        name = (chart.get(c) or {}).get("name") or names.get(c) or ""
        rows.append({"kind": "account", "code": c, "name": name, "depth": depth, "amounts": own,
                     "in_chart": c in chart, "rolled": rolled.get(c, [])})
        kids = [k for k in sorted(children.get(c, [])) if k not in done]
        if not kids:
            return own
        total = own
        for k in kids:
            total = [_plus(a, b) for a, b in zip(total, emit(k, depth + 1))]
        rows.append({"kind": "group_total", "code": c, "name": f"Total {name}".strip(), "depth": depth, "amounts": total})
        return total

    total = zero[:]
    for r in roots:
        total = [_plus(a, b) for a, b in zip(total, emit(r, 0))]
    return rows, total


# ---------- the profit and loss account ----------

def _movements(con, eid, d_from, d_to):
    """The trial balance for the period (rolled up) and {code: {kind, name, rolled, amount}}, amount the period's
    movement (closing less opening, less what a year start moved), debit above 0; None when an opening is unknown. From
    a financial year start, a profit and loss account opens at 0 (it starts again there), so its closing is the movement
    even when the only opening kept for it is later in the year (SQL's trial balance printed for a later From date)."""
    tb = books.trial_balance(con, eid, d_from, d_to, rollup=True)
    year_start = books.year_start(con, eid, d_from) == d_from
    out = {}
    for r in tb["accounts"]:
        o, c = r["opening_sen"], r["closing_sen"]
        if o is None and year_start and r["kind"] == "pl" and not r["reset_sen"]:
            o = 0
        out[r["code"]] = {"kind": r["kind"], "name": r["name"], "rolled": r["rolled"],
                          "amount": None if o is None or c is None else c - o - r["reset_sen"]}
    return tb, out


def _kept_by(B, day):
    """True when the books keep anything (an opening or a line) on or before day."""
    return any(o["as_of"] <= day for v in B.opens.values() for o in v) or \
        any(x["doc_date"] <= day for v in B.lines.values() for x in v)


def _tb_state(tb):
    """How the trial balance's own check stands: 'balanced'; 'unbalanced' (a real difference); 'no_openings' (every
    closing is known and they balance, and so do the period's debits and credits, but an opening is missing, so the
    openings can't be checked); or 'unknown' (a closing is missing too)."""
    if tb["balanced"]:
        return "balanced"
    closings = [r["closing_sen"] for r in tb["accounts"]]
    if None in closings:
        return "unknown"
    if sum(closings) != 0 or tb["totals"]["dr_sen"] != tb["totals"]["cr_sen"]:
        return "unbalanced"
    if any(r["opening_sen"] is None for r in tb["accounts"]):
        return "no_openings"
    return "unbalanced"


def _unknown(data, kinds=None):
    return sorted(c for c, v in data.items() if v["amount"] is None and c is not None and (kinds is None or v["kind"] in kinds))


def profit_and_loss(con, eid, d_from=None, d_to=None, columns="total"):
    """The profit and loss account for a period (default: this financial year to date). columns: 'total' (one column)
    or 'month' (one column per month of the period, then the total). When the period lies in one financial year and
    the books cover the same period a year before, that is added as a comparative column (else comparative.why says
    why not). Returns {from, to, columns: [{key, label, from, to, role}], blocks, figures, comparative, check, notes}:
    blocks are the sections (rows of accounts, sub-accounts under their parent, a total) and the totals between them,
    every amount a list with one figure per column, in sen, shown the section's way round."""
    if columns not in ("total", "month"):
        raise ValueError("Columns are 'total' or 'month'.")
    B = books._Books(con, eid)
    d_from, d_to = books._period_of(B, d_from, d_to)
    chart = _chart(con, eid)
    cols = []
    if columns == "month":
        ms = _months(d_from, d_to)
        if len(ms) > MAX_MONTHS:
            raise ValueError(f"Months are shown for up to {MAX_MONTHS} months at a time. Choose a shorter period.")
        cols += [{"key": f"m{i}", "label": f"{_day(a):%b %Y}", "from": a, "to": b, "role": "month"} for i, (a, b) in enumerate(ms)]
    cols.append({"key": "total", "label": f"{_dmy(d_from)} to {_dmy(d_to)}", "from": d_from, "to": d_to, "role": "total"})
    data = [_movements(con, eid, c["from"], c["to"]) for c in cols]
    tb = data[-1][0]
    notes = []

    # The same period a year before, when the period lies in one financial year and the books cover it.
    comp = {"shown": False, "from": None, "to": None, "why": None}
    if B.year_start(d_from) != B.year_start(d_to):
        comp["why"] = ("The period runs across the start of a financial year, so there is no same period of one year before "
                       "to compare it with.")
    else:
        p_from, p_to = _year_back_from(d_from), _year_back(d_to)
        comp.update({"from": p_from, "to": p_to})
        cover = books._coverage_notes(con, B, p_from, p_to)
        if not _kept_by(B, p_to):
            comp["why"] = f"Nothing is kept for {_dmy(p_from)} to {_dmy(p_to)}, the same period a year before, so there is nothing to compare with."
        elif cover:
            comp["why"] = f"Not compared with {_dmy(p_from)} to {_dmy(p_to)}: " + cover[0]
        else:
            got = _movements(con, eid, p_from, p_to)
            missing = _unknown(got[1], ("pl",))
            if missing:
                comp["why"] = (f"No opening balance is kept for {', '.join(missing)} on {_dmy(p_from)}, so the same period a year "
                               "before can't be worked out to compare with.")
            else:
                comp["shown"] = True
                cols.append({"key": "previous", "label": f"{_dmy(p_from)} to {_dmy(p_to)}", "from": p_from, "to": p_to, "role": "comparative"})
                data.append(got)
    n = len(cols)

    placed, names, rolled, moved_notes = {}, {}, {}, []
    every = set()
    for _, d in data:
        every |= {c for c in d if c is not None}
    for code in sorted(every):
        kind = next((d[code]["kind"] for _, d in data if code in d), None)
        g, why = _group(chart, code, kind)
        if g not in PL_GROUPS and g not in ("AP", NOT_CLASSIFIED):
            continue
        amounts = [(d[code]["amount"] if code in d else 0) for _, d in data]
        if not any(a is None or a for a in amounts):
            continue
        placed.setdefault(g, {})[code] = amounts
        for _, d in data:
            if code in d:
                names.setdefault(code, d[code]["name"])
                rolled.setdefault(code, d[code]["rolled"])
        if why:
            moved_notes.append(why)
    blocks, figures = _layout(PL_LAYOUT, placed, chart, names, rolled, n)
    notes += moved_notes
    if placed.get(NOT_CLASSIFIED):
        notes.append(f"{NC_NOTE}, so not counted in the profit: {', '.join(sorted(placed[NOT_CLASSIFIED]))}. The trial balance "
                     "takes them as balance sheet accounts. Set their types in Setup › Chart of accounts.")
    if placed.get("AP"):
        notes.append("Appropriation accounts are equity in the books (they don't start again at the year start), so the balance "
                     "sheet shows their balance under equity; here is what moved on them in the period, after the profit after tax.")
    unknown = sorted({c for _, d in data for c in _unknown(d, ("pl",))})
    if unknown:
        notes.append(f"No opening balance is kept for {', '.join(unknown)} at the start of a column's dates, so those amounts "
                     "and the totals they are in can't be worked out. Fetch SQL's trial balance (with a From date) for the start "
                     "of the period.")

    # The checks: the net profit is the trial balance's profit and loss movement; the months add up to the total.
    ti = next(i for i, c in enumerate(cols) if c["role"] == "total")
    net = figures["after_tax"][ti]
    pl_moves = [v["amount"] for c, v in data[ti][1].items() if v["kind"] == "pl"]
    tb_net = None if None in pl_moves else -sum(pl_moves)
    texts, ok = [], True
    if net is None or tb_net is None:
        ok = None
        texts.append("The check against the trial balance can't run: an opening balance is missing (see the notes).")
    elif net == tb_net:
        texts.append(f"The net profit or loss after tax, {_money(net)}, is the trial balance's profit and loss accounts' movement "
                     f"for {_dmy(d_from)} to {_dmy(d_to)}.")
    else:
        ok = False
        texts.append(f"The net profit or loss after tax is {_money(net)}, but the trial balance's profit and loss accounts moved "
                     f"{_money(tb_net)} (a difference of {_money(net - tb_net)}).")
    state = _tb_state(tb)
    if state == "unbalanced":
        ok = False if ok else ok
        texts.append("The trial balance for these dates doesn't balance (see the Trial balance tab).")
    elif state in ("no_openings", "unknown"):
        ok = None if ok else ok
        texts.append(f"The trial balance for these dates can't be fully checked: an opening balance at {_dmy(d_from)} is "
                     "missing (see the Trial balance tab).")
    months_ok = None
    if columns == "month":
        mi = [i for i, c in enumerate(cols) if c["role"] == "month"]
        off = []
        for b in blocks:
            for r in b.get("rows", []) + ([{"code": b["key"], "amounts": b.get("total") or b.get("amounts")}]):
                xs = [r["amounts"][i] for i in mi]
                if None not in xs and r["amounts"][ti] is not None and sum(xs) != r["amounts"][ti]:
                    off.append(r["code"])
        months_ok = not off
        if off:
            ok = False if ok else ok
            texts.append(f"The months don't add up to the total for {', '.join(dict.fromkeys(off))}: a later opening kept "
                         "inside the period doesn't follow from the lines before it.")
        else:
            texts.append("The months add up to the total.")
    if B.fy_setting is None:
        notes.append("The financial year start isn't set for this company (Setup › Companies), so it is taken as January.")
    notes += books._coverage_notes(con, B, d_from, d_to)
    return {"from": d_from, "to": d_to, "fy_start": B.fy, "fy_set": B.fy_setting is not None, "columns_mode": columns,
            "columns": cols, "blocks": blocks, "figures": figures, "comparative": comp,
            "check": {"reconciles": ok, "net_sen": net, "tb_net_sen": tb_net, "months_add_up": months_ok,
                      "tb_balanced": tb["balanced"], "text": " ".join(texts)},
            "notes": notes}


# ---------- the balance sheet ----------

def _position(con, eid, as_at):
    """The trial balance from the financial year start to as_at (rolled up) and {code: {kind, name, rolled, closing}}."""
    fy = books.year_start(con, eid, as_at)
    tb = books.trial_balance(con, eid, fy, as_at, rollup=True)
    return tb, {r["code"]: {"kind": r["kind"], "name": r["name"], "rolled": r["rolled"], "amount": r["closing_sen"]}
                for r in tb["accounts"]}


def balance_sheet(con, eid, as_at=None):
    """The balance sheet as at a day (default today): assets, liabilities, net assets, and equity with the profit or
    loss for the financial year to that day; with the end of the previous financial year as a comparative column when
    the books cover it (else comparative.why says why not). It must balance: net assets equal total equity exactly;
    when they don't, the check says by how much and why. Returns {as_at, fy_from, columns, blocks, figures, comparative,
    balanced, difference_sen, check, notes}."""
    B = books._Books(con, eid)
    as_at = _iso(as_at) or date.today().isoformat()
    chart = _chart(con, eid)
    fy_from = B.year_start(as_at)
    cols = [{"key": "now", "label": f"At {_dmy(as_at)}", "as_at": as_at, "role": "total"}]
    data = [_position(con, eid, as_at)]
    prev_at = (_day(fy_from) - timedelta(days=1)).isoformat()
    prev_from = B.year_start(prev_at)
    comp = {"shown": False, "as_at": prev_at, "why": None}
    # The comparative splits equity into what was brought forward and that year's profit, so that year's profit must be
    # known: books kept here from the start, or an opening at or before that year's start and its journal kept for it.
    prev_cover = books._coverage_notes(con, B, prev_from, prev_at)
    if not _kept_by(B, prev_at) and not any(o["as_of"] == _next(prev_at) for v in B.opens.values() for o in v):
        comp["why"] = f"Nothing is kept for {_dmy(prev_at)}, the end of the previous financial year, so there is nothing to compare with."
    elif B.uses_sql and not any(o["as_of"] <= prev_from for v in B.opens.values() for o in v):
        comp["why"] = (f"No opening balance is kept on or before {_dmy(prev_from)}, the start of the previous financial year, so "
                       f"that year's profit, and so the balance sheet at {_dmy(prev_at)}, can't be worked out to compare with. "
                       f"Fetch SQL's trial balance (with a From date) for {_dmy(prev_from)}.")
    elif prev_cover:
        comp["why"] = (f"Not compared with {_dmy(prev_at)}: that year's profit can't be worked out. " + prev_cover[0])
    else:
        got = _position(con, eid, prev_at)
        missing = _unknown(got[1])
        if missing:
            comp["why"] = (f"No opening balance is kept for {', '.join(missing)} on or before {_dmy(prev_at)}, the end of the "
                           "previous financial year, so it can't be compared.")
        else:
            comp["shown"] = True
            cols.append({"key": "previous", "label": f"At {_dmy(prev_at)}", "as_at": prev_at, "role": "comparative"})
            data.append(got)
    n = len(cols)

    placed, names, rolled, moved_notes = {}, {}, {}, []
    profit = [0] * n
    nc = [0] * n
    every = set()
    for _, d in data:
        every |= set(d)
    for code in sorted(every, key=lambda c: (c is None, c or "")):
        kind = next((d[code]["kind"] for _, d in data if code in d), None)
        amounts = [(d[code]["amount"] if code in d else 0) for _, d in data]
        if kind == "pl":
            profit = [_plus(p, _times(-1, a)) for p, a in zip(profit, amounts)]
            continue
        g, why = _group(chart, code, kind)
        if not any(a is None or a for a in amounts):
            continue
        key = code if code is not None else "—"
        placed.setdefault(g, {})[key] = amounts
        for _, d in data:
            if code in d:
                names.setdefault(key, d[code]["name"])
                rolled.setdefault(key, d[code]["rolled"])
        if g == NOT_CLASSIFIED:
            nc = [_plus(x, a) for x, a in zip(nc, amounts)]
        if why:
            moved_notes.append(why)
    blocks, figures = _layout(BS_LAYOUT, placed, chart, names, rolled, n, {"profit": profit})
    for b in blocks:  # the line of profit and loss with no retained earnings account in the chart has no code
        for r in b.get("rows", []):
            if r["code"] == "—":
                r["code"], r["in_chart"] = None, True
    notes = moved_notes[:]
    net_assets, equity = figures["net_assets"], figures["total_equity"]
    diff = [None if a is None or e is None else a - e for a, e in zip(net_assets, equity)]
    balanced = diff[0] == 0 if diff[0] is not None else None

    texts, ok = [], True
    for i, c in enumerate(cols):
        when = "" if i == 0 else f" At {_dmy(c['as_at'])}:"
        if diff[i] is None:
            ok = None if ok else ok
            texts.append(f"{when} The balance sheet can't be totalled: an opening balance is missing (see the notes).".strip())
        elif diff[i] == 0:
            if i == 0:
                texts.append(f"Balances: net assets and total equity are both {_money(net_assets[i])}.")
        else:
            ok = False
            words = (f"{when} It doesn't balance: net assets come to {_money(net_assets[i])} and total equity to "
                     f"{_money(equity[i])}, a difference of {_money(diff[i])}.").strip()
            ncs = sorted(k for k, v in (placed.get(NOT_CLASSIFIED) or {}).items() if v[i])
            if nc[i] is not None and nc[i] == -diff[i] and ncs:
                words += (f" The accounts not classified ({', '.join(ncs)}) hold {_money(abs(nc[i]))} "
                          f"{'debit' if nc[i] > 0 else 'credit'} between them and are left out of both sides: set their types "
                          "in Setup › Chart of accounts and it will balance.")
            else:
                words += " The trial balance as at that day doesn't balance either, or a balance is missing: see the Trial balance tab."
            texts.append(words)

    # Ties: the year's profit in the balance sheet is the profit and loss account's; every closing is placed once.
    pl = profit_and_loss(con, eid, fy_from, as_at)
    pl_net = pl["figures"]["after_tax"][0]
    if profit[0] is None or pl_net is None:
        ties = None
        texts.append("The profit for the year to date can't be checked against the profit and loss account: an opening balance is missing.")
    else:
        ties = profit[0] == pl_net
        texts.append(f"The profit or loss for the year to date, {_money(profit[0])}, is the profit and loss account's net profit "
                     f"or loss after tax for {_dmy(fy_from)} to {_dmy(as_at)}." if ties else
                     f"The profit or loss for the year to date here is {_money(profit[0])}, but the profit and loss account for "
                     f"{_dmy(fy_from)} to {_dmy(as_at)} says {_money(pl_net)}.")
        if not ties:
            ok = False
    # The trial balance's closings at the day must balance; a missing opening at the year start doesn't matter here when
    # every closing is known (a balance sheet is closings only).
    closings = [v["amount"] for v in data[0][1].values()]
    if None not in closings:
        if sum(closings) != 0:
            ok = False
            texts.append(f"The trial balance as at {_dmy(as_at)} doesn't balance: its closing balances come to "
                         f"{_money(abs(sum(closings)))} more {'debit' if sum(closings) > 0 else 'credit'} than "
                         f"{'credit' if sum(closings) > 0 else 'debit'} (see the Trial balance tab).")
        else:
            texts.append(f"Every account of the trial balance as at {_dmy(as_at)} is in it once.")
    if placed.get(NOT_CLASSIFIED):
        notes.append(f"{NC_NOTE}, so left out of both net assets and equity: {', '.join(sorted(placed[NOT_CLASSIFIED]))}. Set "
                     "their types in Setup › Chart of accounts.")
    missing = _unknown(data[0][1])
    if missing:
        notes.append(f"No opening balance is kept for {', '.join(missing)}, so the balance sheet can't be totalled. Fetch SQL's "
                     "trial balance (with a From date) for the start of the financial year.")
    if None in data[0][1]:
        notes.append("The chart of accounts has no retained earnings account (SQL type RE), so the profit and loss carried at "
                     "the year start is shown on a line of its own under Retained earnings brought forward.")
    if B.fy_setting is None:
        notes.append("The financial year start isn't set for this company (Setup › Companies), so it is taken as January.")
    notes += books._coverage_notes(con, B, fy_from, as_at)
    return {"as_at": as_at, "fy_from": fy_from, "fy_start": B.fy, "fy_set": B.fy_setting is not None, "columns": cols,
            "blocks": blocks, "figures": figures, "comparative": comp, "balanced": balanced, "difference_sen": diff[0],
            "check": {"balances": balanced, "ties_to_profit_and_loss": ties, "reconciles": ok if balanced is not None else None,
                      "profit_sen": profit[0], "pl_net_sen": pl_net, "text": " ".join(texts)},
            "notes": notes}


def _next(d):
    return (_day(d) + timedelta(days=1)).isoformat()
