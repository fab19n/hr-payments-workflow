"""The printed bank reconciliation statement of one account and month (PrintBankRec): the standard layout (the balance per
bank, the items between the bank and the books, the balance per books), the book entries where no money moved, the
totals check, the check against SQL's books, the sign-off note, and Prepared by and Reviewed by. Its code
(BR-yymm-<company code>-<last 4 digits of the account number>) and keyed check (formcode) are printed with a QR; the
check is worked out from every figure printed, so a statement changed after printing no longer matches.

statement() works the statement out as the month stands (reads only, except that make_key makes the key for the checks
on the first form printed); render() draws it as a PDF; preview() is what the print preview on the page shows.
Nothing here posts anything to SQL Account.
"""
import calendar
import io
from datetime import date

from fpdf import FPDF

from . import db, formcode, recon

UNICODE = {"−": "-", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
           "→": "->", " ": " "}


# Whether the PDF being drawn has a Unicode font (one the printed invoices use: Tahoma, or a free look-alike on this
# computer), and whether a character had to print as '?' without one. Set by render (one PDF at a time).
_FONT = {"uni": False, "lost": False, "cmap": set()}


def _t(s):
    s = str(s if s is not None else "")
    if _FONT["uni"]:
        # a character the font has no glyph for (Chinese in Tahoma, say) is left out by the PDF maker: say so at the foot
        if any(ord(ch) > 127 and ord(ch) not in _FONT["cmap"] for ch in s):
            _FONT["lost"] = True
        return s
    for k, v in UNICODE.items():
        s = s.replace(k, v)
    out = s.encode("latin-1", "replace").decode("latin-1")
    if out != s:
        _FONT["lost"] = True
    return out


def _n(v):
    return f"{abs(v):,.2f}" if v is not None else ""


def _s(v):
    """A signed amount as printed: +1,234.56 or -1,234.56, or a dash for nothing."""
    if v is None or abs(v) < 0.005:
        return "-"
    return ("+" if v > 0 else "−") + f"{abs(v):,.2f}"


def _day(iso):
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {calendar.month_abbr[d.month]}"


def _month_end(month):
    y, m = map(int, month.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def _masked(acct):
    digits = formcode.account_digits(acct["number"], acct["id"])
    return f"{acct['label']} ····{digits}"


def statement(con, ent, acct, month, make_key=False, printed_by=None, today=None):
    """The statement as the month stands: {code, check, figures, head, rec (rows), rec_line, rec_notes, pairs, pair_notes,
    totals, tot_line, gl_head, gl, note, note_foot, signers, sign_text, sign_line, signed, printed, printed_by, ...}.
    make_key: make the key for the checks when there is none (printing); otherwise formcode.NoKey when there is none."""
    s = recon.month_summary(con, ent, acct, month)
    cur = acct["currency"]
    st = s["statement"]
    code = s["statement_code"]
    end = _month_end(month)
    signed = bool(s["locked"])
    src = "SQL's cash book" + (f", {s['bank_gl']}" if s["bank_gl"] else "") if s["source"] == "sql" else "payments recorded in this app"
    out = {"code": code, "company": ent["name"], "company_code": ent["code"], "account": _masked(acct), "account_label": acct["label"],
           "currency": cur,
           "month": month, "month_label": db.month_label(month), "as_at": f"{end.day} {calendar.month_abbr[end.month]} {end.year}",
           "printed": (today or date.today()).strftime("%a %d %b %Y").replace(" 0", " "), "printed_by": printed_by,
           "signed": signed, "status_text": s["status_text"], "imported": st is not None}
    keys = ent.keys()
    out["reg"] = (f"Registration no. {ent['reg_no']}" if "reg_no" in keys and ent["reg_no"] else "")
    out["address"] = " ".join(x.strip() for x in str(ent["address"] if "address" in keys and ent["address"] else "").splitlines() if x.strip())

    # Part 1: the reconciliation.
    rows, b = [], s["book"]
    bank_close = st["closing"] if st else None
    rows.append({"date": _day(end.isoformat()), "ref": "", "item": "Balance per bank statement", "why": "", "each": "",
                 "total": bank_close, "kind": "sum"})
    rc = s["reconciliation"] or {}
    b_in = [x for x in s["books_only"] if x["amount"] > 0]
    b_out = [x for x in s["books_only"] if x["amount"] < 0]

    def group(title, items, sign=1, why_of=None):
        tot = round(sum(sign * x["amount"] for x in items), 2)
        rows.append({"date": "", "ref": "", "item": title, "why": "", "each": "", "total": tot if items else None, "kind": "head"})
        for x in items:
            rows.append({"date": _day(x["date"]), "ref": x.get("ref") or "", "item": (x.get("description") or "").replace(" | ", " · "),
                         "why": why_of(x) if why_of else x["why"], "each": sign * x["amount"], "total": None, "kind": "item"})
        return tot
    adj = bank_close if bank_close is not None else 0
    adj += group("Add: money in the books, not yet on the bank", b_in)
    adj += group("Less: payments in the books, not yet cleared", b_out)
    sqlco = s["source"] == "sql" and not s["before_tracking"]

    def bank_why(x):
        w = x["why"]
        if sqlco and w.startswith("No payment needed"):
            return w.replace("No payment needed: ", "") + ": enter it in SQL Account"
        return w
    adj += group("Add or less: on the bank, not yet in the books", s["bank_only"], -1, bank_why)
    if s["differ"]:
        adj += group("Add or less: matched, but the amounts differ", [dict(x, date=end.isoformat(), why="Statement less books")
                                                                       for x in s["differ"]], -1)
    if rc and abs(rc.get("brought_forward") or 0) >= 0.005:
        rows.append({"date": "", "ref": "", "item": "Less: brought forward from last month (bank opening less book opening)", "why": "",
                     "each": "", "total": -rc["brought_forward"], "kind": "head"})
        adj -= rc["brought_forward"]
    if rc and abs(rc.get("other") or 0) >= 0.005:
        rows.append({"date": "", "ref": "", "item": "Not explained by any of these", "why": "", "each": "", "total": -rc["other"], "kind": "head"})
        adj -= rc["other"]
    adj = round(adj, 2)
    rows.append({"date": "", "ref": "", "item": "Adjusted bank balance", "why": "", "each": "", "total": adj if st else None, "kind": "sum"})
    rows.append({"date": _day(end.isoformat()), "ref": "", "item": f"Balance per books ({src})", "why": "", "each": "",
                 "total": b["closing"] if b["state"] == "ok" else None, "kind": "sum"})
    out["rec"] = rows
    diff = s["difference"]
    if not st:
        out["rec_line"] = f"The {db.month_label(month)} statement isn't imported yet, so there is no bank balance to reconcile."
    elif b["state"] != "ok":
        out["rec_line"] = f"There is no balance per books yet: {b['note']}."
    elif abs(diff or 0) < 0.005:
        out["rec_line"] = ("The adjusted bank balance is the balance per books: nothing is outstanding on either side."
                           if not (s["books_only"] or s["bank_only"] or s["differ"]) else
                           "The adjusted bank balance is the balance per books: the items above make up the whole difference.")
    else:
        out["rec_line"] = (f"The bank is {_n(diff)} {'above' if diff > 0 else 'below'} the books, and the items above make up the difference."
                           + ("" if signed else " Not signed off" + (f": {'; '.join(s['why_not'])}." if s["why_not"] else ".")))
    notes = []
    if st and b["state"] == "ok":
        first = f"1 {calendar.month_abbr[int(month[5:7])]} {month[:4]}"
        if abs((st["opening"] or 0) - (b["opening"] or 0)) < 0.005:
            notes.append(f"Opening balances agree: statement and books {cur} {_n(st['opening'])} at {first}.")
        else:
            notes.append(f"Opening balances: statement {_n(st['opening'])}, books {_n(b['opening'])} at {first}; the "
                         f"{_n(st['opening'] - b['opening'])} between them is brought forward.")
    out["rec_notes"] = notes

    # Part 2: the book entries where no money moved.
    out["pairs"] = [{"docs": [{"ref": d["ref"] or "", "date": _day(d["date"]), "description": d["description"],
                               "in": d["amount"] if d["amount"] > 0 else None, "out": -d["amount"] if d["amount"] < 0 else None}
                              for d in p["docs"]],
                     "net": "Net nil" if p["nil"] else f"Net {_n(p['net'])}, not nil", "reason": p["reason"],
                     "status": f"Confirmed {_day(p['confirmed_at'])}" if p["confirmed_at"] else "Not confirmed yet"} for p in s["pairs"]]
    if not s["pairs"]:
        out["pair_notes"] = ["None. No book entries cancel each other out this month."]
    elif s["source"] == "sql":
        out["pair_notes"] = ["What to do in SQL Account: each pair stays in SQL's books. Tick both entries of each pair as cleared in "
                             f"{db.month_label(month)} in SQL's bank reconciliation, since they net to nil, so SQL's clearing report agrees."]
    else:
        out["pair_notes"] = []

    # Part 3: the totals check.
    pin = round(sum(d["amount"] for p in s["pairs"] for d in p["docs"] if d["amount"] > 0), 2)
    pout = round(-sum(d["amount"] for p in s["pairs"] for d in p["docs"] if d["amount"] < 0), 2)
    bk_in, bk_out = (b.get("in") or 0, b.get("out") or 0) if b["state"] == "ok" else (None, None)
    xin = round(sum(x["amount"] for x in s["bank_only"] if x["amount"] > 0), 2)
    xout = round(-sum(x["amount"] for x in s["bank_only"] if x["amount"] < 0), 2)
    oin = round(sum(x["amount"] for x in b_in), 2)
    oout = round(-sum(x["amount"] for x in b_out), 2)
    st_in = s["statement"]["money_in"] if st else None
    st_out = s["statement"]["money_out"] if st else None
    totals = []
    if bk_in is not None:
        moved_in, moved_out = round(bk_in - pin, 2), round(bk_out - pout, 2)
        totals = [(f"Per the books ({src})", bk_in, bk_out, True), ("Less: book entries where no money moved (part 2)", -pin, -pout, False),
                  ("Books, money that moved", moved_in, moved_out, True), ("Add: on the statement, not in the books", xin, xout, False),
                  ("Less: in the books, not on the statement", -oin, -oout, False)]
        if s["differ"]:
            # Each difference goes in its payment's own column (the sign of the books' amount): a payment out of 18,000
            # with 8,000 on the statement takes 10,000 off the money out; a receipt short on the statement off the money in.
            d_in = round(sum(x["amount"] for x in s["differ"] if x["book"] > 0), 2)
            d_out = round(-sum(x["amount"] for x in s["differ"] if x["book"] < 0), 2)
            totals.append(("Add or less: matched, but the amounts differ", d_in, d_out, False))
        else:
            d_in = d_out = 0
        if st:
            totals.append(("Per the statement (total credits and debits)", st_in, st_out, True))
            calc_in, calc_out = round(moved_in + xin - oin + d_in, 2), round(moved_out + xout - oout + d_out, 2)
            n = s["lines"]["total"] if s["lines"] else 0
            if abs(calc_in - st_in) < 0.005 and abs(calc_out - st_out) < 0.005:
                out["tot_line"] = f"The debit and credit totals tally with the statement: {n} line{'s' if n != 1 else ''}, {_n(st_in)} in and {_n(st_out)} out."
            else:
                out["tot_line"] = (f"The totals don't tally with the statement by {_n(st_in - calc_in)} in and {_n(st_out - calc_out)} out: "
                                   "money brought forward from another month, or not explained, is in part 1.")
        else:
            out["tot_line"] = "The statement isn't imported yet, so there are no credit and debit totals to check against."
    else:
        out["tot_line"] = "There are no book figures for the month yet, so the totals can't be checked."
    out["totals"] = [{"label": k, "in": i, "out": o, "bold": bold} for k, i, o, bold in totals]

    # Part 4: the check against SQL's books.
    ck = s["sql_check"]
    if ck:
        out["gl_head"] = "Check against SQL's bank account"
        gl = [ck["text"] + ("." if ck["text"] and not ck["text"].endswith(".") else "")]
        if ck["state"] in ("agrees", "differs") and ck["sql_balance"] is not None:
            gl[0] = (f"{ck['text']} at {out['as_at']}: SQL's balance {_n(ck['sql_balance'])}, the book closing here "
                     f"{_n(b['closing'])}." if ck["state"] == "agrees" else gl[0])
        lo = s["left_out"]
        bits = []
        if lo.get("journals") or lo.get("invoices"):
            bits.append(f"{lo['journals']} journal{'s' if lo['journals'] != 1 else ''} and {lo['invoices']} customer invoice{'s' if lo['invoices'] != 1 else ''}")
        if lo.get("unknown"):
            bits.append(f"{lo['unknown']} cash book entr{'y' if lo['unknown'] == 1 else 'ies'} with no money in or out shown")
        if lo.get("other_bank"):
            bits.append(f"{lo['other_bank']} receipt{'s' if lo['other_bank'] != 1 else ''} or payment{'s' if lo['other_bank'] != 1 else ''} "
                        "whose lines don't touch this bank account")
        if bits:
            gl.append("Not counted as bank movements: " + "; ".join(bits) + ".")
    elif ent["uses_sql"]:
        primary = recon.cash_book_account(con, ent["id"])
        out["gl_head"] = "Check against SQL's books"
        gl = [f"Not checked against SQL: only {primary['label'] if primary else 'the cash book account'} is SQL's cash book here. "
              "This account's book side is the payments recorded in this app and the lines explained without documents."]
    else:
        out["gl_head"] = "Check against SQL's books"
        gl = [f"Kept here: there is no check against SQL. The book side is the payments recorded in this app."]
    out["gl"] = gl

    # Part 5: the sign-off note.
    if signed:
        out["note"] = list(s["sign_note"] or []) + [f"Note: {s['free_note']}" if s["free_note"] else "Note: none."]
        if s["locked_how"] == "before tracking" and not s["sign_note"]:
            out["note"] = [f"Reconciled before tracking began here: {s['free_note'] or 'no note given'}."]
        out["note_foot"] = f"Written by the app at sign-off on {db.day_label(s['locked_at'][:10])}, as the month stood. Nothing here is written by hand."
    else:
        out["note"] = ["Not signed off yet, so there is no sign-off note. At sign-off the app writes it here: each confirmed pair with its reason "
                       "and amounts, each line explained without documents, anything left as a reconciling item, and the optional note."]
        out["note_foot"] = "Print the statement again after the sign-off: the sign-off changes it, so this copy's check no longer matches."

    # Part 6: Prepared by and Reviewed by.
    who = s["prepared_by"] if signed else None
    out["signers"] = [{"role": "Prepared by", "name": who or "",
                       "note": (f"Signed off in the app on {db.day_label(s['locked_at'][:10])}" if signed else "Not signed off in the app yet")},
                      {"role": "Reviewed by", "name": "", "note": f"An approver of {ent['code']}"}]
    out["sign_text"] = ("Prepared by is the person who signed the month off in the app. " if signed else
                        "Prepared by is the person who signs the month off in the app; it is blank until then. ") + \
        f"An approver of {ent['code']} reviews it. By signing, the reviewer confirms parts 1 to 5."
    if signed:
        out["sign_line"] = (f"Signed off on {db.day_label(s['locked_at'][:10])}" + (f" by {who} (declared, not verified)" if who else "")
                            + ". The month is locked.")
    else:
        out["sign_line"] = "Not signed off" + (f": {'; '.join(s['why_not'])}." if s["why_not"] else " yet: it is ready to sign off.")
    out["prep_line"] = (f"Printed by {printed_by}, as declared on this computer (declared, not verified)." if printed_by
                        else "Printed from this app; no name was given for who printed it.")

    # The figures the check is worked out from: everything the statement prints (every row with its date and why, the
    # pairs with their dates, descriptions, reasons and nets, the notes, the totals line with its count of lines, the
    # sign-off line and its date, the names), as one canonical text. Left out on purpose: when and by whom this copy was
    # printed, so printing the same statement again gives the same check.
    out["file"] = file_name(out)
    out["figures"] = [figures_text(out)]
    figs = out["figures"]
    out["check"] = formcode.check(con, code, figs, make=make_key)
    out["file"] = file_name(out)
    return out


def file_name(data):
    from .docstore import safe
    return safe(f"{data['code']} Bank reconciliation {data['account_label']} {data['month_label']}", 120) + ".pdf"


NOT_CHECKED = ("printed", "printed_by", "prep_line", "check", "file", "figures")


def figures_text(data):
    """What the keyed check covers: the statement as previewed, less when and by whom it was printed, as sorted JSON."""
    import json
    return json.dumps({k: v for k, v in preview(data).items() if k not in NOT_CHECKED}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def preview(data):
    """What the print preview on Bank and reconciliation shows: the head, the parts' words and figures, as JSON."""
    keep = ("code", "check", "company", "account", "currency", "month_label", "as_at", "printed", "printed_by", "signed", "sign_line",
            "rec", "rec_line", "rec_notes", "pairs", "pair_notes", "totals", "tot_line", "gl_head", "gl", "note", "note_foot", "signers",
            "sign_text", "prep_line", "file", "reg", "address")
    return {k: data.get(k) for k in keep}


class _Sheet(FPDF):
    def __init__(self, data):
        super().__init__(unit="mm", format="A4")
        self.d = data
        self.set_margins(15, 12, 15)
        self.set_auto_page_break(True, 16)
        # The printed invoices' font (invoicepdf.font_choice), so names in any script the font has print as written;
        # without one, the PDF maker's own Helvetica, which prints only Latin-1 (the rest as '?', said at the foot).
        _FONT.update(uni=False, lost=False)
        try:
            from .invoicepdf import font_choice
            reg, bold = font_choice("tahoma"), font_choice("tahoma-bold")
            if reg["kind"] != "built-in" and bold["kind"] != "built-in":
                self.add_font("bkr", "", str(reg["path"]))
                self.add_font("bkr", "B", str(bold["path"]))
                _FONT["cmap"] = set(self.fonts["bkr"].cmap) & set(self.fonts["bkrB"].cmap)
                _FONT["uni"] = True
        except Exception:  # a font that can't be read: Helvetica, as before
            _FONT["uni"] = False

    def set_font(self, family=None, style="", size=0):
        if _FONT["uni"] and family == "Helvetica":
            family, style = "bkr", style.replace("I", "")
        return super().set_font(family, style, size)

    def header(self):
        d = self.d
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 7.5)
        self.cell(0, 4, _t(f"Bank reconciliation statement · {d['company']} · {d['account']} · {d['month_label']} (continued)"),
                  new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 4, _t(f"{d['code']} · Check {d['check']}"), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        d = self.d
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.cell(130, 4, _t(f"{d['code']} · {d['check']} · {d['company']} · {d['account']}, {d['month_label']}"))
        self.cell(0, 4, f"Page {self.page_no()} of {{nb}}", align="R")


def render(data):
    """The statement as a PDF (A4 portrait, the header repeated from page 2), as bytes."""
    d = data
    pdf = _Sheet(d)
    pdf.alias_nb_pages()
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin
    # Head: the title and company on the left, the code, check and QR on the right.
    top = pdf.get_y()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(W - 50, 7, "Bank reconciliation statement", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(W - 50, 5, _t(d["company"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    for line in (d.get("reg"), d.get("address")):
        if line:
            pdf.multi_cell(W - 50, 4, _t(line), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(W - 50, 5, _t(d["account"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(W - 50, 4.5, _t(f"{d['month_label']} · {d['currency']} · Printed {d['printed']}"), new_x="LMARGIN", new_y="NEXT")
    left_end = pdf.get_y()
    pdf.image(io.BytesIO(formcode.qr_png(d["code"], d["check"])), x=pdf.w - pdf.r_margin - 18, y=top, w=18, h=18)
    pdf.set_xy(pdf.w - pdf.r_margin - 70, top)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(50, 5, _t(d["code"]), align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(50, 5, _t(f"Check: {d['check']}"), align="R")
    pdf.set_y(max(left_end, top + 20))
    pdf.set_font("Helvetica", "", 7.5)
    pdf.multi_cell(W, 3.6, _t(f"Scan with the phone to upload the signed statement, or type the code {d['code']} and the check {d['check']}. "
                              "If the reconciliation changes after printing, the check no longer matches and the statement is printed again."),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font("Helvetica", "B" if not d["signed"] else "", 8.5)
    pdf.set_line_width(0.6 if not d["signed"] else 0.3)
    pdf.multi_cell(W, 5, _t(d["sign_line"]), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.set_line_width(0.2)

    def part(n, title, sub):
        pdf.ln(3)
        if pdf.will_page_break(14):
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(W, 6, _t(f"{n}  {title}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 7.5)
        pdf.cell(W, 4, _t(sub), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)

    def say(text, size=8.5, style=""):
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(W, 4, _t(text), new_x="LMARGIN", new_y="NEXT")

    def row(cells, widths, aligns, style="", border=""):
        pdf.set_font("Helvetica", style, 8.5)
        texts = [_t(c) for c in cells]
        h = max(4.5, *(pdf.multi_cell(w, 4.5, t, dry_run=True, output="HEIGHT") for w, t in zip(widths, texts)))
        if pdf.will_page_break(h):
            pdf.add_page()
        x, y = pdf.l_margin, pdf.get_y()
        for w, t, a in zip(widths, texts, aligns):
            pdf.set_xy(x, y)
            pdf.multi_cell(w, 4.5, t, align=a, border=border)
            x += w
        pdf.set_xy(pdf.l_margin, y + h)

    cur = d["currency"]
    part(1, f"Reconciliation at {d['as_at']}", "The bank balance, the items between the bank and the books, and the book balance")
    widths = (16, 24, 90, 25, 25)
    row(("Date", "Reference", "Item", "Each", cur), widths, "LLLRR", "B", "B")
    for r in d["rec"]:
        item = r["item"] + (f" · {r['why']}" if r["why"] else "")
        tot = "-" if r["kind"] == "head" and r["total"] is None else ("" if r["total"] is None and r["kind"] == "item"
                                                                     else (_s(r["total"]) if r["kind"] == "head" else _n(r["total"]) if r["total"] is not None else "-"))
        row((r["date"], r["ref"], ("    " if r["kind"] == "item" else "") + item, _s(r["each"]) if r["kind"] == "item" else "", tot),
            widths, "LLLRR", "B" if r["kind"] != "item" else "", "T" if r["kind"] == "sum" else "")
    say(d["rec_line"], 8.5, "B")
    for n in d["rec_notes"]:
        say(n, 8)

    part(2, "Book entries where no money moved", "Pairs of book entries that cancel out and never touched the bank")
    if d["pairs"]:
        w2 = (28, 16, 86, 25, 25)
        row(("Document", "Date", "Description", "Money in", "Money out"), w2, "LLLRR", "B", "B")
        for p in d["pairs"]:
            for i, x in enumerate(p["docs"]):
                row((x["ref"], x["date"], x["description"], _n(x["in"]) if x["in"] else "", _n(x["out"]) if x["out"] else ""), w2, "LLLRR",
                    "", "T" if i == 0 else "")
            row((p["net"], "", f"Reason: {p['reason']}. {p['status']}.", "", ""), w2, "LLLRR", "I")
    for n in d["pair_notes"]:
        say(n, 8)

    part(3, "Totals check", "Money in and money out per the books, against the statement's total credits and debits")
    if d["totals"]:
        w3 = (120, 30, 30)
        row((cur, "Money in", "Money out"), w3, "LRR", "B", "B")
        for t in d["totals"]:
            row(((t["label"] if t["bold"] else "    " + t["label"]), _n(t["in"]) if t["bold"] else _s(t["in"]),
                 _n(t["out"]) if t["bold"] else _s(t["out"])), w3, "LRR", "B" if t["bold"] else "", "T" if t["bold"] else "")
    say(d["tot_line"], 8.5, "B")

    part(4, d["gl_head"], "For a company kept in SQL Account: SQL's balance on the bank's GL account at the month end")
    for n in d["gl"]:
        say(n)

    part(5, "Sign-off note", "Written by the app at sign-off, as the month stood")
    for n in d["note"]:
        say(n)
    say(d["note_foot"], 7.5)

    part(6, "Prepared by and Reviewed by", "")
    say(d["sign_text"], 8)
    pdf.ln(2)
    for sg in d["signers"]:
        if pdf.will_page_break(22):
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(W, 5, _t(sg["role"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.cell(20, 6, "Name")
        pdf.cell(80, 6, _t(sg["name"]), border="B")
        pdf.set_font("Helvetica", "", 7.5)
        pdf.cell(0, 6, _t("  " + sg["note"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.cell(20, 8, "Signature")
        pdf.cell(80, 8, "", border="B")
        pdf.cell(12, 8, "  Date")
        pdf.cell(40, 8, "", border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
    say(d["prep_line"], 7.5)
    if _FONT["lost"]:
        say("Some names or descriptions hold characters this computer's font for printed forms can't print, so they show "
            "as '?' or are left out here: check them against the app, or install a font that has them (Tahoma or DejaVu "
            "Sans for most scripts) and print the statement again.", 7.5, "B")
    return bytes(pdf.output())
