"""Builds one printable PDF per entity and month: an index page, then every document in filing order."""
import io
import json
from datetime import date, datetime

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter
from pypdf.errors import FileNotDecryptedError

from . import rules
from .config import PACKS_DIR
from .db import (_listed, _short_doc, evidence, latest_pack, linked_total, money, month_label, month_statements, not_counted,
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
