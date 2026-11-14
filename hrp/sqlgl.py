"""Reads the three general-ledger reports exported from SQL Account with its print button: the GL Journal of
Transaction, the GL Ledger (Local - Ledger - Detail, Level 1 or V2) and the Trial Balance (This Month vs This Year with
Opening).

Like a listing (hrp/sqlreport.py), each is the printed page laid out on a sheet: the page heading again on every page,
figures in cells merged across columns that don't line up with the headings over them. A figure is placed by the
heading its merged span overlaps most, not by its column.

The Journal of Transaction carries the account lines of every document (vouchers, receipts, journals, invoices) in
sections by book ("Bank Journal", "General Journal Journal", "Sales Journal"), each closed by its own total. The ledger
and the trial balance are read to check those lines against SQL's own figures.

Every figure is kept as an integer number of sen (sen(x) = int(round(x * 100))), so every comparison is exact. A report
that doesn't add up to its own totals is refused whole with a plain sentence (sqlreport.ReportError), never half read.
"""
import hashlib
import json
import re

from .sqlreport import PAGE, PERIOD, ReportError, _a_date, _a_number, _norm

TITLES = {"journal": "GL Journal of Transaction", "gl_ledger": "GL Ledger", "trial_balance": "Trial Balance"}
BOOKS = ("bank", "general", "sales", "purchase")
CODE_ROW = re.compile(r"^code\s*:\s*(\S+)\s*(.*)$", re.I | re.S)
FOOTER_ROW = re.compile(r"^(add|less)\s+(?:code\s*:\s*(\S+)\s*)?(.*)$", re.I | re.S)
AS_AT = re.compile(r"As At (\d{2}/\d{2}/\d{4})", re.I)
LABELS = ("date", "sort by", "project")   # the rows of what was asked for, printed over the report: "Date : From ..."


# ---------- amounts ----------

def sen(x):
    """An amount in RM as a whole number of sen. None and blank are 0."""
    return int(round((x or 0) * 100))


def rm(n):
    """A whole number of sen back as RM."""
    return n / 100


def _money(n):
    return f"{rm(n):,.2f}"


def fingerprint(doc_date, lines):
    """What a document says, to tell a changed one from the same one exported again: sha256 (hex) of the canonical JSON
    [doc_date, sorted [(account code, dr sen, cr sen)]]. The book, descriptions and the order of the lines are left out,
    so a pasted grid and the Journal of Transaction of the same journal agree. lines: dicts with code (or account_code),
    dr_sen and cr_sen."""
    key = sorted([str(x.get("code", x.get("account_code")) or "").strip().upper(), int(x["dr_sen"]), int(x["cr_sen"])] for x in lines)
    return hashlib.sha256(json.dumps([doc_date, key], separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def book_of(label):
    """The book a section of the Journal of Transaction belongs to, from its first word."""
    first = (_norm(label).split() or [""])[0]
    return first if first in BOOKS else "other"


# ---------- the sheet ----------

def _cells(rows, spans, i):
    """The cells of a row that hold something: [(first column, last column, value)]."""
    return [(c, spans.get((i, c), c), x) for c, x in enumerate(rows[i])
            if x is not None and not (isinstance(x, str) and not x.strip())]


def _texts(cells):
    return [_norm(x) for _, _, x in cells if isinstance(x, str)]


def _place(heads, first, last):
    """The heading a cell lies under: the one its span overlaps most, the leftmost of those that overlap as much."""
    hit = [(min(b, last) - max(a, first) + 1, -a, k) for k, (a, b) in heads.items() if a <= last and first <= b]
    return max(hit)[2] if hit else None


def _by_head(heads, cells):
    by = {}
    for a, b, x in cells:
        by.setdefault(_place(heads, a, b), []).append(x)
    return by


def _number(values):
    """The first figure among the values, or None (text such as the print time is not one)."""
    return next((n for n in (_a_number(x) for x in values or []) if n is not None), None)


def _words(values):
    return re.sub(r"\s+", " ", " ".join(str(x) for x in values or [] if isinstance(x, str))).strip()


def _ref(x):
    """A document number as printed: a whole number read from the sheet as 123.0 loses its .0."""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return re.sub(r"\.0$", "", str(x).strip()) if x is not None else ""


def _code(x):
    return _ref(x).upper()


def _is_page_row(cells):
    return any(isinstance(x, str) and PAGE.match(x.strip()) for _, _, x in cells)


def _company(rows, spans):
    """The company line: the text printed beside the first page number."""
    for i in range(min(len(rows), 40)):
        cells = _cells(rows, spans, i)
        if _is_page_row(cells):
            return " ".join(x.strip() for _, _, x in cells if isinstance(x, str) and not PAGE.match(x.strip()))
    return ""


def _period(rows, upto):
    for r in rows[:upto]:
        for x in r:
            m = PERIOD.search(x) if isinstance(x, str) else None
            if m:
                return [_a_date(m.group(1)), _a_date(m.group(2))]
    return None


def _heads(rows, spans, i, key):
    heads = {}
    for a, b, x in _cells(rows, spans, i):
        k = key(x)
        if k and k not in heads:
            heads[k] = (a, b)
    return heads


# ---------- which report ----------

def _jot_key(x):
    n = _norm(x).replace(".", "") if isinstance(x, str) else ""
    if n in ("doc date", "date"):
        return "date"
    if n == "a/c code":
        return "code"
    if n == "a/c description":
        return "name"
    if n in ("ref 1", "ref1"):
        return "ref"
    if n == "description":
        return "description"
    if n == "project":
        return "project"
    if re.match(r"(dr|debit)\b", n):
        return "debit"
    if re.match(r"(cr|credit)\b", n):
        return "credit"
    return None


def _ledger_key(x):
    n = _norm(x).replace(".", "") if isinstance(x, str) else ""
    if n == "date":
        return "date"
    if n.startswith("ref"):
        return "ref"
    if n in ("description 1", "description"):
        return "description"
    if n == "description 2":
        return "description2"
    if n == "tax":
        return "tax"
    if re.match(r"(dr|debit)\b", n):
        return "debit"
    if re.match(r"(cr|credit)\b", n):
        return "credit"
    if n.startswith("bal"):
        return "balance"
    return None


TB_GROUPS = {"opening balance": "open", "period to date": "ptd", "month to date": "mtd", "year to date": "ytd"}
JOT_HEADS = {"date", "code", "name", "ref", "debit", "credit"}
LEDGER_HEADS = {"date", "ref", "debit", "credit", "balance"}


def _jot_heading(rows, spans, i):
    heads = _heads(rows, spans, i, _jot_key)
    return heads if JOT_HEADS <= heads.keys() else None


def _ledger_heading(rows, spans, i):
    heads = _heads(rows, spans, i, _ledger_key)
    return heads if LEDGER_HEADS <= heads.keys() else None


def _tb_heading(row):
    return {_norm(x) for x in row if isinstance(x, str)} >= TB_GROUPS.keys()


def detect(rows, spans):
    """Which general-ledger report these sheet rows are, by their headings (SQL prints no title on the Journal of
    Transaction): 'journal', 'gl_ledger', 'trial_balance', or None for anything else (a listing among them)."""
    code_row = bf = False
    for i, row in enumerate(rows):
        texts = [x.strip() for x in row if isinstance(x, str)]
        if not texts:
            continue
        if _tb_heading(row):
            return "trial_balance"
        if _jot_heading(rows, spans, i):
            return "journal"
        code_row = code_row or any(CODE_ROW.match(t) for t in texts)
        bf = bf or any(_norm(t) == "balance b/f" for t in texts)
        if code_row and bf:
            return "gl_ledger"
    return None


# ---------- the GL Journal of Transaction ----------

def journal(rows, spans):
    """The GL Journal of Transaction on these sheet rows.

    {title, company, period: [from, to] or None, period_source: 'printed' | 'lines' | None,
     sections: [{label, book, dr_sen, cr_sen, docs, lines}],
     docs: [{doc_no, date, book, book_label, description, dr_sen, cr_sen, fingerprint,
             lines: [{seq, code, name, description, project, dr_sen, cr_sen}]}]}

    When no period is printed, the period is the first and last line dates (period_source 'lines'). Raises ReportError
    when a section doesn't add up to its total, a document doesn't balance or has two dates, a doc no. is in two
    sections, a line has no doc no. or account, or both a debit and a credit, or is dated outside the printed period."""
    title = TITLES["journal"]
    head_row = next((i for i in range(len(rows)) if _jot_heading(rows, spans, i)), None)
    if head_row is None:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: no row has the headings Doc Date, A/C Code, Ref 1, Debit and Credit.")
    heads = _jot_heading(rows, spans, head_row)
    printed = _period(rows, head_row)

    sections, docs, where = [], {}, {}   # where: doc key -> the section label it was first read in
    sec, last_line, grand = None, None, None
    for i in range(head_row + 1, len(rows)):
        cells = _cells(rows, spans, i)
        if not cells:
            continue
        texts = _texts(cells)
        first = cells[0][2]
        if _is_page_row(cells) or _jot_heading(rows, spans, i):
            continue  # the company line with the page number, and the headings printed again
        if isinstance(first, str) and _norm(first) in LABELS and len(cells) > 1 and _norm(cells[1][2]) == ":":
            continue  # "Date : From ... to ..." printed again
        if isinstance(first, str) and _norm(first).startswith("grand total"):
            by = _by_head(heads, cells[1:])
            grand = (sen(_number(by.get("debit"))), sen(_number(by.get("credit"))), i)
            continue
        if isinstance(first, str) and _norm(first).startswith("total"):
            if sec is None or sec["closed"]:
                raise ReportError(f"This {title} has a total on row {i + 1} that closes no journal section, so nothing was taken from it.")
            by = _by_head(heads, cells[1:])
            said = (sen(_number(by.get("debit"))), sen(_number(by.get("credit"))))
            if said != (sec["dr_sen"], sec["cr_sen"]):
                raise ReportError(f"This {title}'s {sec['label']} says its total is {_money(said[0])} debit and {_money(said[1])} credit, "
                                  f"but its lines add up to {_money(sec['dr_sen'])} and {_money(sec['cr_sen'])}, so nothing was taken from it. "
                                  "Export it again.")
            sec["closed"] = True
            continue
        if isinstance(first, str) and _norm(re.sub(r"\.{2,}\s*continued", "", first, flags=re.I)).endswith("journal") \
                and all(isinstance(x, str) and "continued" in _norm(x) for _, _, x in cells[1:]):
            label = re.sub(r"\s+", " ", re.sub(r"\.{2,}\s*continued", "", first, flags=re.I)).strip()
            continued = "continued" in _norm(first) or len(cells) > 1
            if continued and sec is not None and not sec["closed"] and _norm(sec["label"]) == _norm(label):
                last_line = None
                continue  # the same section on the next page: its date carries on
            if sec is not None and not sec["closed"]:
                raise ReportError(f"This {title}'s {sec['label']} has no Total row, so nothing was taken from it. Export it again.")
            sec = {"label": label, "book": book_of(label), "dr_sen": 0, "cr_sen": 0, "docs": [], "lines": 0, "closed": False, "day": None}
            sections.append(sec)
            last_line = None
            continue

        by = _by_head(heads, cells)
        dr, cr = _number(by.get("debit")), _number(by.get("credit"))
        code, ref = _code(by["code"][0]) if by.get("code") else "", _ref(by["ref"][0]) if by.get("ref") else ""
        if not code and not ref and dr is None and cr is None:
            # Not a line: the print time over a new page, or the rest of a description wrapped under the line above
            if last_line is not None and (by.get("description") or by.get("name")):
                last_line["description"] = _words([last_line["description"], *by.get("description", [])])
                last_line["name"] = _words([last_line["name"], *by.get("name", [])])
            continue
        if sec is None or sec["closed"]:
            raise ReportError(f"This {title} has a line on row {i + 1} outside any journal section, so nothing was taken from it.")
        if not code or not ref:
            raise ReportError(f"This {title} has a line on row {i + 1} with no {'Ref 1' if not ref else 'A/C Code'}, so nothing was taken from it.")
        if dr and cr:
            raise ReportError(f"This {title} has a line of {ref} on row {i + 1} with both a debit and a credit, so nothing was taken from it.")
        if by.get("date"):
            day = _a_date(by["date"][0])
            if day is None:
                raise ReportError(f"This {title} has a line of {ref} on row {i + 1} whose date can't be read, so nothing was taken from it.")
            sec["day"] = day
        elif sec["day"] is None:
            raise ReportError(f"This {title}'s {sec['label']} starts with a line of {ref} that has no date, so nothing was taken from it.")
        day = sec["day"]
        if printed and printed[0] and printed[1] and not printed[0] <= day <= printed[1]:
            raise ReportError(f"This {title} is for {printed[0]} to {printed[1]}, but {ref} is dated {day}, so nothing was taken from it.")
        key = ref.upper()
        if where.get(key, sec["label"]) != sec["label"]:
            raise ReportError(f"This {title} has {ref} in both its {where[key]} and its {sec['label']}, so nothing was taken from it.")
        where[key] = sec["label"]
        doc = docs.get(key)
        if doc is None:
            doc = docs[key] = {"doc_no": ref, "date": day, "book": sec["book"], "book_label": sec["label"], "lines": []}
            sec["docs"].append(key)
        elif doc["date"] != day:
            raise ReportError(f"This {title} has {ref} with lines dated {doc['date']} and {day}, so nothing was taken from it.")
        line = {"seq": len(doc["lines"]) + 1, "code": code, "name": _words(by.get("name")), "description": _words(by.get("description")),
                "project": _words(by.get("project")), "dr_sen": sen(dr), "cr_sen": sen(cr)}
        doc["lines"].append(line)
        last_line = line
        sec["dr_sen"] += line["dr_sen"]
        sec["cr_sen"] += line["cr_sen"]
        sec["lines"] += 1

    if sec is not None and not sec["closed"]:
        raise ReportError(f"This {title}'s {sec['label']} has no Total row, so nothing was taken from it. Export it again.")
    for doc in docs.values():
        doc["dr_sen"] = sum(x["dr_sen"] for x in doc["lines"])
        doc["cr_sen"] = sum(x["cr_sen"] for x in doc["lines"])
        if doc["dr_sen"] != doc["cr_sen"]:
            raise ReportError(f"This {title} has {doc['doc_no']} with {_money(doc['dr_sen'])} debit and {_money(doc['cr_sen'])} credit, "
                              "which don't balance, so nothing was taken from it.")
        doc["description"] = doc["lines"][0]["description"]
        doc["fingerprint"] = fingerprint(doc["date"], doc["lines"])
    if grand is not None:
        read = (sum(s["dr_sen"] for s in sections), sum(s["cr_sen"] for s in sections))
        if grand[:2] != read or grand[0] != grand[1]:
            raise ReportError(f"This {title}'s grand total is {_money(grand[0])} debit and {_money(grand[1])} credit, but its lines add up to "
                              f"{_money(read[0])} and {_money(read[1])}, so nothing was taken from it.")

    days = [d["date"] for d in docs.values()]
    if printed and printed[0] and printed[1]:
        period, source = printed, "printed"
    elif days:
        period, source = [min(days), max(days)], "lines"
    else:
        period, source = None, None
    return {"title": title, "company": _company(rows, spans), "period": period, "period_source": source,
            "sections": [{"label": s["label"], "book": s["book"], "dr_sen": s["dr_sen"], "cr_sen": s["cr_sen"],
                          "docs": len(s["docs"]), "lines": s["lines"]} for s in sections],
            "docs": list(docs.values())}


# ---------- the GL Ledger ----------

def gl_ledger(rows, spans):
    """The GL Ledger (Local - Ledger - Detail, Level 1 or V2) on these sheet rows.

    {title, company, period: [from, to] or None,
     accounts: [{code, name, bf_sen, rows: [{date, doc_no, cheque_no, description, description2, dr_sen, cr_sen, bal_sen}],
                 virtual: [rows with no Ref, such as PROFIT/(LOSS)], dr_sen, cr_sen, closing_sen}],
     total: {dr_sen, cr_sen, bal_sen} or None,
     footer: [{side, op ('add' | 'less' | 'total'), code, name, dr_sen, cr_sen, amount_sen}]}

    Balances are signed, a debit balance above 0 and a credit balance (printed in brackets) below. A footer amount_sen is
    its debit less its credit, or None when it prints neither. Raises ReportError when an account's balance brought
    forward and its rows don't come to its closing balance, or its rows don't add up to its totals row."""
    title = TITLES["gl_ledger"]
    head_row = next((i for i in range(len(rows)) if _ledger_heading(rows, spans, i)), None)
    if head_row is None:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: no row has the headings Date, Ref, Debit, Credit and Bal.")
    heads = _ledger_heading(rows, spans, head_row)
    top = {_norm(x) for r in rows[:head_row] for x in r if isinstance(x, str)}

    accounts, acct, last, total, footer, side = [], None, None, None, [], None

    def close_missing(at):
        if acct is not None and "closing_sen" not in acct:
            raise ReportError(f"This {title}'s account {acct['code']} has no totals row before row {at + 1}, so nothing was taken from it. Export it again.")

    for i in range(head_row + 1, len(rows)):
        cells = _cells(rows, spans, i)
        if not cells:
            continue
        texts = _texts(cells)
        if _is_page_row(cells) or _ledger_heading(rows, spans, i):
            continue
        if len(cells) == 1 and isinstance(cells[0][2], str) and (texts[0] in top or PERIOD.search(cells[0][2])):
            continue  # the title and the period printed again over a new page
        joined = " ".join(x.strip() for _, _, x in cells if isinstance(x, str))
        m = CODE_ROW.match(joined) if len(texts) == 1 else None
        if m and total is None:
            code = m.group(1).upper()
            if acct is not None and acct["code"] == code and "closing_sen" not in acct:
                continue  # the same account carried over to a new page
            close_missing(i)
            acct = {"code": code, "name": re.sub(r"\s+", " ", m.group(2)).strip(), "bf_sen": 0, "rows": [], "virtual": []}
            accounts.append(acct)
            last = None
            continue
        by = _by_head(heads, cells)
        words = [_norm(x) for x in by.get("description", []) + by.get("description2", []) + by.get("tax", []) if isinstance(x, str)]
        dr, cr, bal = _number(by.get("debit")), _number(by.get("credit")), _number(by.get("balance"))
        if total is None and not by.get("date") and not by.get("ref") and any(w == "total" for w in words):
            close_missing(i)
            total = {"dr_sen": sen(dr), "cr_sen": sen(cr), "bal_sen": sen(bal)}
            acct = None
            continue
        if total is not None:
            # The footer: what the grand total leaves out or adds, by account
            text = " ".join(x.strip() for _, _, x in cells if isinstance(x, str) and _a_number(x) is None)
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if "reconciliation for" in _norm(text):
                side = "credit" if "credit" in _norm(text) else "debit"
                continue
            fm = FOOTER_ROW.match(text)
            op = fm.group(1).lower() if fm else ("total" if _norm(text).startswith("total") else "other")
            footer.append({"side": side, "op": op, "code": (fm.group(2) or "").upper() or None if fm else None,
                           "name": (fm.group(3) if fm else text).strip(), "dr_sen": None if dr is None else sen(dr),
                           "cr_sen": None if cr is None else sen(cr),
                           "amount_sen": None if dr is None and cr is None else sen(dr) - sen(cr)})
            continue
        if acct is None or "closing_sen" in acct:
            if dr is not None or cr is not None or bal is not None:
                raise ReportError(f"This {title} has figures on row {i + 1} outside any account, so nothing was taken from it.")
            continue
        if "balance b/f" in words:
            acct["bf_sen"] = sen(bal)
            continue
        day = _a_date(by["date"][0]) if by.get("date") else None
        ref = by.get("ref", [None])[0]
        if day is not None or (ref is not None and (dr is not None or cr is not None)):
            if day is None:
                if last is None:
                    raise ReportError(f"This {title}'s account {acct['code']} has a row with no date on row {i + 1}, so nothing was taken from it.")
                day = last["date"]
            no, _, cheque = (str(ref).replace("\r", "") if ref is not None else "").partition("\n")
            last = {"date": day, "doc_no": _ref(no) if ref is not None else "", "cheque_no": _ref(cheque.strip()) if cheque.strip() else "",
                    "description": _words(by.get("description")), "description2": _words(by.get("description2")),
                    "dr_sen": sen(dr), "cr_sen": sen(cr), "bal_sen": None if bal is None else sen(bal)}
            (acct["rows"] if last["doc_no"] else acct["virtual"]).append(last)
            continue
        if dr is not None or cr is not None:
            # The account's totals row: its debits, its credits and its closing balance
            acct["dr_sen"], acct["cr_sen"], acct["closing_sen"] = sen(dr), sen(cr), sen(bal)
            moved = acct["rows"] + acct["virtual"]
            got = (sum(x["dr_sen"] for x in moved), sum(x["cr_sen"] for x in moved))
            if got != (acct["dr_sen"], acct["cr_sen"]):
                raise ReportError(f"This {title}'s account {acct['code']} says its total is {_money(acct['dr_sen'])} debit and {_money(acct['cr_sen'])} credit, "
                                  f"but its rows add up to {_money(got[0])} and {_money(got[1])}, so nothing was taken from it. Export it again.")
            if acct["bf_sen"] + got[0] - got[1] != acct["closing_sen"]:
                raise ReportError(f"This {title}'s account {acct['code']} brings forward {_money(acct['bf_sen'])} and moves {_money(got[0] - got[1])}, "
                                  f"but closes at {_money(acct['closing_sen'])}, so nothing was taken from it. Export it again.")
            continue
        if last is not None and (by.get("description") or by.get("description2")):
            last["description"] = _words([last["description"], *by.get("description", [])])
            last["description2"] = _words([last["description2"], *by.get("description2", [])])
    close_missing(len(rows))
    return {"title": title, "company": _company(rows, spans), "period": _period(rows, head_row + 1), "accounts": accounts,
            "total": total, "footer": footer}


# ---------- the Trial Balance ----------

def trial_balance(rows, spans):
    """The Trial Balance (This Month vs This Year with Opening) on these sheet rows.

    {title, company (the name and the registration no., printed in two cells, joined), period: [from or None, as at],
     accounts: [{code, name, open, ptd, mtd, ytd}], grand: {open, ptd, mtd, ytd}}, each figure a pair [dr_sen, cr_sen].

    Raises ReportError when the columns don't add up to the Grand Total row, a pair's grand debit and credit differ, or
    an account's opening balance and period to date don't come to its year to date."""
    title = TITLES["trial_balance"]
    head_row = next((i for i, r in enumerate(rows) if _tb_heading(r)), None)
    if head_row is None:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: no row has the headings Opening Balance, Period To Date, Month To Date and Year To Date.")
    groups = sorted((a, TB_GROUPS[_norm(x)]) for a, _, x in _cells(rows, spans, head_row) if isinstance(x, str) and _norm(x) in TB_GROUPS)
    sub_row = next((i for i in range(head_row + 1, min(len(rows), head_row + 4))
                    if sum(t in ("debit", "credit") for t in _texts(_cells(rows, spans, i))) >= 8), None)
    if sub_row is None:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: no Debit and Credit under its headings.")
    heads = {}
    for a, b, x in _cells(rows, spans, sub_row):
        n = _norm(x) if isinstance(x, str) else ""
        group = next((g for start, g in reversed(groups) if start <= a), None)
        if n in ("debit", "credit") and group and (group, n) not in heads:
            heads[(group, n)] = (a, b)
    if len(heads) != 8:
        raise ReportError(f"This {title} is laid out in a way this app hasn't seen: its Debit and Credit columns can't be told apart.")
    first_figure = min(a for a, _ in heads.values())

    top_text = [(i, x) for i, r in enumerate(rows[:head_row]) for x in r if isinstance(x, str)]
    as_at = next((_a_date(m.group(1)) for _, x in top_text for m in [AS_AT.search(x)] if m), None)
    printed = _period(rows, head_row)
    if as_at is None and printed:
        as_at = printed[1]
    if as_at is None:
        raise ReportError(f"This {title} doesn't print the date it is as at, so nothing was taken from it.")
    title_at = next((i for i, x in top_text if AS_AT.search(x) and "trial balance" in _norm(x)), None)
    company = ""
    if title_at:
        company = " ".join(x.strip() for _, _, x in _cells(rows, spans, title_at - 1) if isinstance(x, str))
    company = company or _company(rows, spans)

    def figures(cells):
        out = {g: [0, 0] for g in TB_GROUPS.values()}
        found = False
        for a, b, x in cells:
            if b < first_figure:
                continue
            n = _a_number(x)
            k = _place(heads, a, b)
            if n is None or k is None:
                continue
            out[k[0]][0 if k[1] == "debit" else 1] += sen(n)
            found = True
        return out, found

    accounts, grand = [], None
    for i in range(sub_row + 1, len(rows)):
        cells = _cells(rows, spans, i)
        if not cells or _is_page_row(cells) or _tb_heading(rows[i]):
            continue
        texts = _texts(cells)
        if texts and all(t in ("debit", "credit") for t in texts):
            continue  # the Debit and Credit headings printed again
        first_col, _, first = cells[0]
        if isinstance(first, str) and _norm(first).startswith("grand total"):
            grand, _ = figures(cells)
            break
        vals, found = figures(cells)
        is_label = len(cells) > 1 and isinstance(cells[1][2], str) and cells[1][2].strip() == ":"
        code_like = isinstance(first, float) or (isinstance(first, str) and not re.search(r"\s", first.strip()))
        code = _code(first) if first_col == 0 and not is_label and code_like else ""
        if not code:
            if found:
                raise ReportError(f"This {title} has figures on row {i + 1} that belong to no account, so nothing was taken from it.")
            continue  # the print heading, the company and the title printed again over a new page
        name = " ".join(x.strip() for a, b, x in cells[1:] if isinstance(x, str) and b < first_figure)
        accounts.append({"code": code, "name": name, **vals})
    if grand is None:
        raise ReportError(f"This {title} has no Grand Total row, so nothing was taken from it. Export it again.")

    for g, label in (("open", "Opening Balance"), ("ptd", "Period To Date"), ("mtd", "Month To Date"), ("ytd", "Year To Date")):
        read = [sum(a[g][0] for a in accounts), sum(a[g][1] for a in accounts)]
        if read != grand[g]:
            raise ReportError(f"This {title}'s {label} accounts add up to {_money(read[0])} debit and {_money(read[1])} credit, but its Grand Total says "
                              f"{_money(grand[g][0])} and {_money(grand[g][1])}, so nothing was taken from it. Export it again.")
        if grand[g][0] != grand[g][1]:
            raise ReportError(f"This {title}'s {label} grand total is {_money(grand[g][0])} debit and {_money(grand[g][1])} credit, which don't balance, "
                              "so nothing was taken from it.")
    for a in accounts:
        net = lambda pair: pair[0] - pair[1]  # noqa: E731
        if net(a["open"]) + net(a["ptd"]) != net(a["ytd"]):
            raise ReportError(f"This {title}'s account {a['code']} opens at {_money(net(a['open']))} and moves {_money(net(a['ptd']))} in the period, "
                              f"but its Year To Date is {_money(net(a['ytd']))}, so nothing was taken from it. Export it again.")
    return {"title": title, "company": company, "period": [printed[0] if printed else None, as_at], "accounts": accounts, "grand": grand}


READERS = {"journal": journal, "gl_ledger": gl_ledger, "trial_balance": trial_balance}
