"""Builds one printable PDF per entity and month: an index page, then every document in filing order."""
import io
import json
from datetime import date, datetime

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError

from . import recon, rules
from .config import PACKS_DIR
from .db import (_listed, _short_doc, day_label, evidence, latest_pack, linked_total, money, month_label, month_statements, not_counted,
                 not_in_sql, payment_flag, payment_status, short_day, status_word, task_status, waits_for)
from .docstore import path_of, verify

IMAGE_EXT = {".png", ".jpg", ".jpeg"}
COLS = (110, 25, 55)  # index columns in mm: transaction / task, status, documents
LINE = 5


class PackError(ValueError):
    """The pack could not be built. The message names the document at fault, for showing to the user."""


def _latin(s):
    return (s or "").encode("latin-1", "replace").decode("latin-1")


def _image_pdf(path):
    pdf = FPDF(unit="mm", format="A4")
    pdf.add_page()
    pdf.image(str(path), x=10, y=10, w=190, keep_aspect_ratio=True, h=277)
    return bytes(pdf.output())


def _pages(d):
    """The document's pages, or None and the reason it can't go into the PDF."""
    path = path_of(d)
    ext = path.suffix.lower()
    if not path.exists():
        return None, "file is missing from the records folder"
    if not verify(d):
        return None, "file changed since upload"
    if ext != ".pdf" and ext not in IMAGE_EXT:
        return None, "not a PDF or image - print it separately, or save it as PDF and replace it"
    try:
        reader = PdfReader(str(path)) if ext == ".pdf" else PdfReader(io.BytesIO(_image_pdf(path)))
        return list(reader.pages), None
    except FileNotDecryptedError:
        return None, "has a password - save a copy without the password and replace it"
    except Exception:
        return None, ("could not be read as PDF - save it again as PDF and replace it" if ext == ".pdf"
                      else "could not be read as an image - save it again and replace it")


_PRINTS = {}  # (document id, fingerprint, size, time on disk) -> why it can't go into the PDF (None: it can)


def _unprintable(d):
    """Why a document can't go into the PDF, or None, as _pages says it, but read once: a stored file is read-only, so
    the answer is kept until its size or its time on disk changes. For Next up, which asks on every redraw."""
    try:
        st = path_of(d).stat()
    except OSError:
        return _pages(d)[1]
    key = (d["id"], d["sha256"], st.st_size, st.st_mtime_ns)
    if key not in _PRINTS:
        _PRINTS[key] = _pages(d)[1]
    return _PRINTS[key]


def _payments(con, entity, month):
    return con.execute(
        "SELECT * FROM payments WHERE entity_id = ? AND month = ? ORDER BY due_date, id", (entity["id"], month)).fetchall()


def _tasks(con, entity, month):
    """The checklist items a month's pack covers: all but the one the pack is for, and no reminder waiting here for a
    later month (it belongs to that month's pack)."""
    return [t for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY due_date, sort",
                                   (entity["id"], month)) if t["code"] != rules.TASK_PACK and not waits_for(t)]


def _docs(con, field, ident):
    return con.execute(f"SELECT * FROM documents WHERE {field} = ? AND replaced_by IS NULL AND removed_at IS NULL",
                       (ident,)).fetchall()


def _statement_docs(con, entity, month):
    return con.execute(
        """SELECT d.*, s.account_id FROM statements s JOIN documents d ON d.id = s.document_id JOIN accounts a ON a.id = s.account_id
           WHERE a.entity_id = ? AND s.month = ? ORDER BY a.id""", (entity["id"], month)).fetchall()


def build(con, entity, month):
    order = {d: i for i, d in enumerate(rules.DOC_ORDER)}

    today = date.today().isoformat()
    # (title, [docs], status, missing, what SQL or the bank statement shows instead of an upload, why what SQL shows
    # doesn't count)
    sections = []
    for p in _payments(con, entity, month):
        docs = _docs(con, "payment_id", p["id"])
        ev = evidence(con, pay=p)
        status, missing = payment_status(con, p, entity["uses_sql"], ev)
        label = status_word(p, status)
        flag = payment_flag(con, entity, p, today)
        if flag:
            label = flag["text"] if status == "planned" else f"{label}\n{flag['text']}"
        amt = f"{p['currency']} {p['amount']:,.2f}" if p["amount"] is not None else "amount not set"
        sections.append((f"{p['description']}  ({amt})", sorted(docs, key=lambda d: order.get(d["doc_type"], 99)), label, missing,
                         _proofs(rules.required_docs(p["category"], entity["uses_sql"]), docs, ev), not_counted(con, pay=p)))
    for t in _tasks(con, entity, month):
        docs = _docs(con, "task_id", t["id"])
        ev = evidence(con, task=t)
        st = task_status(con, entity, t, ev)
        # What the records show, or still lack, worded as on the month page ('Done' is in the status column).
        why = st["why"] or ""
        if why.startswith("Done: "):
            why = why[6].upper() + why[7:]
        elif why and st["done"]:
            why = "Ticked by hand. " + why
        proofs = _proofs(json.loads(t["required_docs"]), docs, ev) + st["shown"] + ([why] if why else [])
        sections.append((t["title"], sorted(docs, key=lambda d: order.get(d["doc_type"], 99)), "Done" if st["done"] else "Not done",
                         st["missing"], proofs, not_counted(con, task=t)))
    stmts = _statement_docs(con, entity, month)
    if stmts:
        sections.append(("Bank statements", list(stmts), "", [], [], {}))

    # Read every document first, so the index page can list anything that couldn't be included, after the bank
    # statements not imported.
    parts, index_rows = [], []
    not_merged = [("Bank statements", a["label"], f"{month_label(month)} statement not imported")
                  for a in month_statements(con, entity, month) if not a["statement"]]
    for title, docs, status, missing, proofs, nc in sections:
        for d in docs:
            pages, why = _pages(d)
            if why:
                not_merged.append((title, d["original_name"], why))
            else:
                parts.append((f"{title} - {rules.DOC_TYPES.get(d['doc_type'], d['doc_type'])}", d, pages))
        index_rows.append((title, status, missing, docs, proofs, nc))

    out = PdfWriter()
    for pg in PdfReader(io.BytesIO(_cover(entity, month, index_rows, not_merged))).pages:
        out.add_page(pg)
    out.add_outline_item("Index", 0)
    first = len(out.pages)
    for pg in PdfReader(io.BytesIO(_reconciliation(con, entity, month))).pages:
        out.add_page(pg)
    out.add_outline_item("Bank reconciliation", first)
    for label, d, pages in parts:
        first = len(out.pages)
        try:
            for pg in pages:
                out.add_page(pg)
        except Exception as ex:
            # A bank statement has no Replace, so there is nothing to tell the user to do with it.
            fix = "" if d["statement_id"] else " Open it, save it again as PDF, replace it and build the pack again."
            raise PackError(f"'{d['original_name']}' ({label}) could not be added to the audit pack.{fix}") from ex
        out.add_outline_item(label, first)
    target = PACKS_DIR / entity["code"]
    target.mkdir(parents=True, exist_ok=True)
    fname = target / f"Audit pack {entity['code']} {month} ({datetime.now():%Y%m%d-%H%M}).pdf"
    with open(fname, "wb") as f:
        out.write(f)
    return fname


# How each kind of thing still open is counted in a short summary, one and several.
OPEN = {"lines": ("bank line to explain", "bank lines to explain"), "payment": ("payment not complete", "payments not complete"),
        "task": ("checklist item missing documents", "checklist items missing documents"),
        "task_open": ("checklist item not done", "checklist items not done"),
        "not_in_sql": ("paid payment not recorded in SQL", "paid payments not recorded in SQL"),
        "unprintable": ("file that won't print", "files that won't print")}


def sql_to_print(con, entity, pays):
    """The SQL vouchers that stand for a document a payment must have, in place of an upload, so the pack doesn't hold
    them: {doc type: voucher numbers}. pays: [(payment, its evidence)]."""
    nos = {}
    for p, ev in pays:
        up = {d["doc_type"] for d in _docs(con, "payment_id", p["id"])}
        for t in rules.required_docs(p["category"], entity["uses_sql"]):
            if t in rules.SQL_ONLY and t in ev and t not in up:
                nos.setdefault(t, set()).update(ev[t]["ref"].split(", "))  # the voucher numbers linked (db.evidence)
    return nos


def to_print(nos):
    """The SQL vouchers to print (sql_to_print), per type as up to 3 runs (PV2609-001 to PV2609-007, PV2609-017 and
    PV2610-004 to PV2610-006), or counted from the first to the last (23 payment vouchers, PV2609-001 to PV2610-019)."""
    out = []
    for t, found in sorted(nos.items(), key=lambda kv: min(kv[1])):
        runs = _runs(found)
        out += runs if len(runs) <= 3 else [f"{len(found)} {rules.DOC_COUNTED.get(t, (t, t))[1]} ({min(found)} to {max(found)})"]
    return _listed(out) if out else ""


def _runs(nos):
    """Voucher numbers as the runs to print: PV2609-001 to PV2609-007, PV2609-017, PV2610-004 to PV2610-006."""
    runs = []
    for no in sorted(set(nos)):
        head, _, n = no.rpartition("-")
        last = runs[-1][-1] if runs else None
        if last and n.isdigit() and last[0] == head and last[1].isdigit() and int(n) == int(last[1]) + 1:
            runs[-1].append((head, n, no))
        else:
            runs.append([(head, n, no)])
    return [x for r in runs for x in ([f"{r[0][2]} to {r[-1][2]}"] if len(r) > 2 else [no for *_, no in r])]


def readiness(con, entity, month, cached=False):
    """What still stands between a month and a clean printed pack ("Before you print"), worked out here for the Audit
    page, the warning before a month is marked as filed and its line in the activity log (and, with cached, for Next
    up, which leaves out re-reading a file whose size and time on disk haven't changed). In this order: each account
    whose statement for the month isn't imported; lines left to explain on the month's statements; each payment not
    complete, with what it lacks (not paid yet: why, in its status words; paid: the documents neither uploaded nor shown
    by SQL or the bank); each checklist item the pack covers with its own documents missing, then each other one not
    done (filing a month stops counting it); for a company kept in SQL, payments paid but not recorded there; and each
    file the pack can't print (not a PDF or image, a password, missing or changed).
    Returns {items: [{kind, title, detail, fix: where it is fixed (payment, task, account or sql), id}], summary: the
    same counted in short lines, ready: nothing listed, pack: the latest pack built {name, when, changed} or None,
    pack_open: no pack built or one out of date, in words (None when it is up to date), still_open: the summary and
    pack_open, which marking the month as filed warns of and logs, to_print: the SQL vouchers the pack doesn't hold,
    to print from SQL (to_print), or an empty string}."""
    today = date.today().isoformat()
    items = []

    def add(kind, title, detail, fix, ident=None):
        items.append({"kind": kind, "title": title, "detail": detail, "fix": fix, "id": ident})

    mon = month_label(month)
    accts = month_statements(con, entity, month)
    for a in accts:
        if not a["statement"]:
            add("statement", a["label"], f"{mon} statement not imported yet", "account", a["id"])
    for a in accts:
        if a["to_explain"]:
            n = a["to_explain"]
            add("lines", a["label"], f"{n} line{'s' if n > 1 else ''} to explain on the {mon} statement", "account", a["id"])
    pays = _payments(con, entity, month)
    evs = {p["id"]: evidence(con, pay=p) for p in pays}
    for p in pays:
        status, missing = payment_status(con, p, entity["uses_sql"], evs[p["id"]])
        if status == "complete":
            continue
        what = []
        if status == "planned":
            what.append((payment_flag(con, entity, p, today) or {"text": status_word(p, status)})["text"])
        elif status == "part_paid":
            what.append(f"Part paid: {money(linked_total(con, p), p['currency'])} of {money(p['amount'], p['currency'])}")
        if missing and status != "planned":  # not paid yet says it all
            nc = not_counted(con, pay=p)
            what.append("Missing " + _listed(_short_doc(m) + (f" ({nc[m]['why']})" if m in nc else "") for m in missing))
        add("payment", p["description"], ". ".join(what), "payment", p["id"])
    tasks = _tasks(con, entity, month)
    sts = [task_status(con, entity, t) for t in tasks]
    for t, st in zip(tasks, sts):
        if st["missing"]:
            add("task", t["title"], "Missing " + _listed(map(_short_doc, st["missing"])), "task", t["id"])
    for t, st in zip(tasks, sts):
        if not st["done"] and not st["missing"]:
            add("task_open", t["title"], f"{st['why'] or 'Not ticked yet'}, due {short_day(t['due_date'])}", "task", t["id"])
    for p in pays:
        if not_in_sql(entity, p):
            add("not_in_sql", p["description"], f"Paid {short_day(p['paid_date'])}, not recorded in SQL yet", "sql")
    why_not = _unprintable if cached else (lambda d: _pages(d)[1])
    owners = [(p["description"], "payment", p["id"], _docs(con, "payment_id", p["id"])) for p in pays]
    owners += [(t["title"], "task", t["id"], _docs(con, "task_id", t["id"])) for t in tasks]
    owners += [("Bank statements", "account", d["account_id"], [d]) for d in _statement_docs(con, entity, month)]
    for title, fix, ident, docs in owners:
        for d in docs:
            why = why_not(d)
            if why:
                add("unprintable", d["original_name"], f"On {title}: {why}", fix, ident)

    absent = [x["title"] for x in items if x["kind"] == "statement"]
    summary = [f"{_listed(absent)} statement{'s' if len(absent) > 1 else ''} not imported"] if absent else []
    receipts = {p["id"] for p in pays if p["direction"] == "in"}  # money in is counted apart from payments out
    for kind, (one, many) in OPEN.items():
        if kind == "lines":
            n = sum(a["to_explain"] for a in accts)
        elif kind == "payment":
            n = sum(x["kind"] == kind and x["id"] not in receipts for x in items)
        else:
            n = sum(x["kind"] == kind for x in items)
        if n:
            summary.append(f"{n} {one if n == 1 else many}")
        k = kind == "payment" and sum(x["kind"] == kind and x["id"] in receipts for x in items)
        if k:
            summary.append(f"{k} receipt{'s' if k > 1 else ''} not complete")
    pack = latest_pack(con, entity, month)
    n = pack and pack["changed"]
    pack_open = ("No audit pack built yet" if not pack else
                 f"Pack out of date: {n} document{'s' if n > 1 else ''} added or removed since {pack['when']}" if n else None)
    return {"items": items, "summary": summary, "ready": not items,
            "pack": pack and {"name": pack["path"].name, "when": pack["when"], "changed": n},
            "pack_open": pack_open, "still_open": summary + ([pack_open] if pack_open else []),
            "to_print": to_print(sql_to_print(con, entity, [(p, evs[p["id"]]) for p in pays]))}


def reconciliation(con, entity, month):
    """Each account of the company with what its statement for the month shows, for the bank reconciliation pages and the
    Excel report: [{label, currency, statement: the statements row or None, lines: its lines, sum (the lines added up),
    difference (opening + lines - closing), balanced, matched (lines linked to a payment), to_explain (lines left),
    no_docs (lines marked as needing no documents), recon (the month's reconciliation: recon.month_summary), no_line: paid payments on the account with no bank line anywhere that were
    paid in the statement's month (whatever their payroll month) or belong to the month's payroll (paid in another month)}]. A payment with no account of its own counts for the only account in its currency."""
    accts = con.execute("SELECT * FROM accounts WHERE entity_id = ? ORDER BY id", (entity["id"],)).fetchall()
    pays = con.execute(
        """SELECT * FROM payments WHERE entity_id = ? AND paid_date IS NOT NULL AND paid_date <> ''
           AND (substr(paid_date, 1, 7) = ? OR month = ?) AND NOT EXISTS
           (SELECT 1 FROM statement_lines l WHERE l.payment_id = payments.id) ORDER BY paid_date, id""",
        (entity["id"], month, month)).fetchall()
    out = []
    for a in accts:
        st = con.execute("SELECT * FROM statements WHERE account_id = ? AND month = ?", (a["id"], month)).fetchone()
        lines = con.execute("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (st["id"],)).fetchall() if st else []
        total = round(sum(l["amount"] for l in lines), 2)
        diff = round(st["opening"] + total - st["closing"], 2) if st and st["opening"] is not None and st["closing"] is not None else None
        same = [x for x in accts if x["currency"] == a["currency"]]
        no_line = [p for p in pays if p["account_id"] == a["id"] or (p["account_id"] is None and p["currency"] == a["currency"] and len(same) == 1)]
        out.append({"label": a["label"], "currency": a["currency"], "statement": st, "lines": lines, "sum": total, "difference": diff,
                    "balanced": diff is not None and abs(diff) <= 0.01,
                    "matched": [l for l in lines if l["payment_id"]],
                    "to_explain": [l for l in lines if l["status"] == "unmatched" and not l["payment_id"]],
                    "no_docs": [l for l in lines if l["status"] == "no_docs" and not l["payment_id"]], "no_line": no_line,
                    "recon": recon.month_summary(con, entity, a, month)})
    return out


def _no_line_note(p, month):
    """Why a paid payment with no bank line is listed on the month's page."""
    paid = p["paid_date"][:7]
    if paid != month:  # a payment of this month paid in another month: its statement is the one to check
        return f"{month_label(p['month'])} payment paid in {month_label(paid)}, check that statement"
    base = "paid per SQL, not on the statement" if p["sql_ref"] else "not on the statement"
    return base if p["month"] == month else f"{month_label(p['month'])} payment, {base}"


def _reconciled(r, say, table, heading, cur):
    """The reconciliation of one account: whether it is signed off, book against bank, and the two lists that explain a
    difference between them."""
    heading("Reconciled with the books")
    if r["status"] == "reconciled":
        how = "before tracking began" + (f" ({r['reconciled_note']})" if r["reconciled_note"] else "")             if r["reconciled_how"] == "before tracking" else "after checking every line"
        say(f"Reconciled on {day_label(r['reconciled_at'][:10])}, {how}.")
    else:
        say(f"Not reconciled yet ({r['status_text'].lower()}). " + ("; ".join(r["why_not"]).capitalize() + "." if r["why_not"] else ""))
    b = r["book"]
    if b["state"] == "ok":
        say(f"Book closing {money(b['closing'], cur)} (opening {money(b['opening'], cur)}, in {money(b['in'], cur)}, out {money(b['out'], cur)}). "
            f"Bank closing {money(r['bank_closing'], cur) if r['bank_closing'] is not None else 'not on statement'}. "
            + (f"Difference {money(r['difference'], cur)}." if r["difference"] is not None else ""))
    else:
        say(f"Book closing: {b['note']}. Bank closing {money(r['bank_closing'], cur) if r['bank_closing'] is not None else 'not on statement'}.")
    if r["left_out"]["journals"] or r["left_out"]["invoices"]:
        j, i = r["left_out"]["journals"], r["left_out"]["invoices"]
        say(f"Not counted as bank movements: {j} journal{'s' if j != 1 else ''} and {i} customer invoice{'s' if i != 1 else ''} (customer refunds included) in the SQL listing.")
    if r["left_out"].get("unknown"):
        u = r["left_out"]["unknown"]
        say(f"Not counted: {u} cash book entr{'ies' if u != 1 else 'y'} with no money in or out shown, so the books may differ by that amount.")
    head = ("Date", "Description", "Amount", "Why")
    if r["books_only"]:
        table(f"In the books, not on this statement ({len(r['books_only'])})", head,
              [(x["date"], (x["ref"] + " " if x["ref"] else "") + x["description"], f"{x['amount']:,.2f}", x["why"]) for x in r["books_only"]])
    else:
        say("Nothing in the books is missing from this statement.")
    if r["bank_only"]:
        table(f"On the statement, not in the books ({len(r['bank_only'])})", head,
              [(x["date"], x["description"], f"{x['amount']:,.2f}", x["why"]) for x in r["bank_only"]])
    else:
        say("Every line on this statement is in the books.")
    if r["differ"]:
        table(f"Matched, but the amounts differ ({len(r['differ'])})", ("Payment", "Description", "Bank minus books", "Books / bank"),
              [(x["ref"] or "", x["description"], f"{x['amount']:,.2f}", f"{x['book']:,.2f} / {x['bank']:,.2f}") for x in r["differ"]])
    rc = r["reconciliation"]
    if rc and abs(rc["other"]) > 0.005:
        say(f"Not explained by the lists: {money(rc['other'], cur)}.")


def _reconciliation(con, entity, month):
    """The bank reconciliation pages: one section per account of the company for the month."""
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _latin(f"{entity['name']} - Bank reconciliation {month_label(month)}"), new_x="LMARGIN", new_y="NEXT")
    cols = (22, 100, 30, 38)

    def heading(text):
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _latin(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)

    def say(text):
        pdf.multi_cell(0, LINE, _latin(text), new_x="LMARGIN", new_y="NEXT")

    def table(title, head, rows):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _latin(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 8.5)
        for w, t in zip(cols, head):
            pdf.cell(w, 5, t, border="B")
        pdf.ln(5)
        pdf.set_font("Helvetica", "", 8.5)
        for r in rows:
            cells = [_latin(str(s)) for s in r]
            h = max(LINE, *(pdf.multi_cell(w, LINE, s, dry_run=True, output="HEIGHT") for w, s in zip(cols, cells)))
            if pdf.will_page_break(h):
                pdf.add_page()
            x, y = pdf.l_margin, pdf.get_y()
            for i, (w, s) in enumerate(zip(cols, cells)):
                pdf.set_xy(x, y)
                pdf.multi_cell(w, LINE, s, align="R" if i == 2 else "L")
                x += w
            pdf.set_y(y + h)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)

    for a in reconciliation(con, entity, month):
        cur, st = a["currency"], a["statement"]
        heading(a["label"] if a["label"].endswith(")") else f"{a['label']} ({cur})")
        if not st:
            say(f"The {month_label(month)} statement is not imported.")
            continue
        n = lambda v: "not on statement" if v is None else money(v, cur)
        say(f"Opening balance {n(st['opening'])}. Closing balance {n(st['closing'])}. "
            f"Total debits {n(st['total_debits'])}. Total credits {n(st['total_credits'])}. {len(a['lines'])} lines.")
        if a["difference"] is None:
            say("Check: the statement has no opening or closing balance to check against.")
        else:
            say(f"Check: opening {money(st['opening'], cur)} + lines {money(a['sum'], cur)} = {money(st['opening'] + a['sum'], cur)}; "
                f"closing {money(st['closing'], cur)}. " + ("The balances add up." if a["balanced"]
                                                              else f"THE BALANCES DO NOT ADD UP (difference {money(a['difference'], cur)})."))
        m = a["matched"]
        say(f"Lines matched to a payment: {len(m)}. Money out {money(-sum(l['amount'] for l in m if l['amount'] < 0), cur)}, "
            f"money in {money(sum(l['amount'] for l in m if l['amount'] > 0), cur)}.")
        _reconciled(a["recon"], say, table, heading, cur)
        if a["no_docs"]:
            say(f"Lines marked as needing no documents: {len(a['no_docs'])}, total {money(sum(l['amount'] for l in a['no_docs']), cur)}.")
        if a["to_explain"]:
            table(f"Lines still to explain ({len(a['to_explain'])}, total {money(sum(l['amount'] for l in a['to_explain']), cur)})",
                  ("Date", "Description", "Amount", "Note"),
                  [(l["txn_date"], l["description"], f"{l['amount']:,.2f}", l["note"] or "") for l in a["to_explain"]])
        else:
            say("No lines left to explain.")
        if a["no_line"]:
            table(f"Paid with no bank line ({len(a['no_line'])})", ("Paid", "Payment", "Amount", "Note"),
                  [(p["paid_date"], p["description"], "" if p["amount"] is None else f"{p['amount']:,.2f}",
                    _no_line_note(p, month)) for p in a["no_line"]])
        else:
            say("Every payment paid in the month on this account has a bank line.")
    return bytes(pdf.output())


def _proofs(required, docs, ev):
    """What stands for the documents required but not uploaded (from db.evidence), e.g. PV2609-020 (print from SQL)."""
    have = {d["doc_type"] for d in docs}
    return [ev[t]["text"] for t in required if t in ev and t not in have]


def _index_head(pdf):
    pdf.set_font("Helvetica", "B", 9)
    for w, text in zip(COLS, ("Transaction / task", "Status", "Documents")):
        pdf.cell(w, 6, text, border="B")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8.5)


def _cover(entity, month, rows, not_merged):
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _latin(f"{entity['name']} - Audit pack {month_label(month)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _latin(f"Generated {datetime.now():%d %b %Y %H:%M}. Documents follow in the order below."), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    _index_head(pdf)
    short = lambda t: rules.DOC_TYPES.get(t, t).split(" (")[0].split(" /")[0]
    for title, label, missing, docs, proofs, nc in rows:
        doc_txt = "; ".join(filter(None, [", ".join(short(d["doc_type"]) for d in docs), *proofs]))
        if missing:
            doc_txt = (doc_txt + ". " if doc_txt else "") + "MISSING: " + ", ".join(
                short(m) + (f" ({nc[m]['why']})" if m in nc else "") for m in missing)
        cells = [_latin(s) for s in (title, label, doc_txt)]
        # Measure the whole row first, so a row that doesn't fit starts the next page instead of breaking inside a cell.
        h = max(LINE, *(pdf.multi_cell(w, LINE, s, dry_run=True, output="HEIGHT") for w, s in zip(COLS, cells)))
        if pdf.will_page_break(h):
            pdf.add_page()
            _index_head(pdf)
        x, y = pdf.l_margin, pdf.get_y()
        for w, s in zip(COLS, cells):
            pdf.set_xy(x, y)
            pdf.multi_cell(w, LINE, s)
            x += w
        pdf.set_y(y + h + 1)
    if not_merged:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Not included in this PDF - print or check separately", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        for title, name, why in not_merged:
            pdf.multi_cell(0, LINE, _latin(f"- {title}: {name} ({why})"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
