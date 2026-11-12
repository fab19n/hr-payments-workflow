"""Excel reports and the auditor package. Everything is built from the same helpers as the screens (db.payment_status,
db.status_word, db.payment_flag, db.task_status, budget.view), so a word in a report is the word on the page."""
import hashlib
import io
import os
import re
import zipfile
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

from . import auditpack, budget as stored, db, rulebook, rules
from .config import EXPORTS_DIR
from .docstore import path_of, safe
from pathlib import Path

MONEY = "#,##0.00"
DAY = "yyyy-mm-dd"
BOLD = Font(bold=True)
OUT, IN = "Money out", "Money in"


def _short(t, R):
    return R.doc_label(t).split(" (")[0].split(" /")[0]


def _day(iso):
    return date.fromisoformat(iso) if iso else None


def _put(ws, row, col, value, fmt=None, bold=False):
    c = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith("="):
        c.data_type = "s"  # text from the records is never a formula
    if fmt:
        c.number_format = fmt
    if bold:
        c.font = BOLD
    return c


def _formula(ws, row, col, text, bold=True):
    c = ws.cell(row=row, column=col, value=text)
    c.number_format = MONEY
    if bold:
        c.font = BOLD
    return c


def _table(ws, top, headers, rows, widths, fmts=None):
    """Writes a header row at row top and the rows under it: bold header, frozen below it, autofilter, widths, print setup.
    fmts: {column number: number format}. Returns (first data row, last data row); last is top when there are no rows."""
    for i, h in enumerate(headers, 1):
        c = _put(ws, top, i, h, bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r, row in enumerate(rows, top + 1):
        for i, v in enumerate(row, 1):
            c = _put(ws, r, i, v, (fmts or {}).get(i))
            if isinstance(v, str):
                c.alignment = Alignment(wrap_text=True, vertical="top")
    last = top + len(rows)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=top + 1, column=1)
    ws.auto_filter.ref = f"A{top}:{get_column_letter(len(headers))}{max(last, top + 1)}"
    _print_setup(ws, top)
    return top + 1, last


def _print_setup(ws, top):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f"{top}:{top}"


def _totals(ws, start, first, last, label_col, amount_col, groups):
    """Totals rows from row start: for each (label, {column: value}) in groups a SUMIFS over rows first to last of the
    amount column, where each group column holds that value."""
    if last < first:
        return  # no rows: nothing to add up
    a = get_column_letter(amount_col)
    for label, crit in groups:
        _put(ws, start, label_col, label, bold=True)
        tests = "".join(f',${get_column_letter(c)}${first}:${get_column_letter(c)}${last},{v}' for c, v in crit.items())
        _formula(ws, start, amount_col, f"=SUMIFS({a}{first}:{a}{last}{tests})")
        start += 1


def _quoted(v):
    return '"' + v.replace('"', '""') + '"'


def _gather(con, entity, month):
    """Everything the month report shows, worked out once."""
    today = date.today().isoformat()
    R = rulebook.get(con)
    pays = []
    for p in auditpack._payments(con, entity, month):
        ev = db.evidence(con, pay=p)
        status, missing = db.payment_status(con, p, entity["uses_sql"], ev)
        flag = db.payment_flag(con, entity, p, today)
        docs = auditpack._docs(con, "payment_id", p["id"])
        have = {d["doc_type"] for d in docs}
        entries = con.execute("SELECT doc_no FROM sql_entries WHERE payment_id = ? ORDER BY doc_date, id", (p["id"],)).fetchall()
        lines = con.execute("SELECT txn_date FROM statement_lines WHERE payment_id = ? ORDER BY txn_date", (p["id"],)).fetchall()
        on_file = [_short(d["doc_type"], R) for d in sorted(docs, key=lambda d: R.order(d["doc_type"]))]
        on_file += [ev[t]["text"] for t in R.required_docs(p["category"], entity["uses_sql"], p["month"], p["entity_id"])
                    if t in ev and t not in have]
        nc = db.not_counted(con, pay=p)
        pays.append({"p": p, "status": status, "word": db.status_word(p, status), "flag": flag and flag["text"],
                     "missing": [_short(m, R) + (f" ({nc[m]['why']})" if m in nc else "") for m in missing],
                     "on_file": on_file,
                     "sql": ", ".join(dict.fromkeys(([p["sql_ref"]] if p["sql_ref"] else []) + [e["doc_no"] for e in entries])),
                     "bank": ", ".join(dict.fromkeys(l["txn_date"] for l in lines))})
    tasks = []
    for t in con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY due_date, sort", (entity["id"], month)):
        st = db.task_status(con, entity, t)
        lack = ["Missing: " + db._listed(map(R.short_doc, st["missing"]))] if st["missing"] else []
        if not st["done"] and st["why"]:
            lack.append(st["why"])
        tasks.append({"t": t, "st": st, "lack": "; ".join(lack)})
    recon = auditpack.reconciliation(con, entity, month)
    return pays, tasks, recon


def _sql_rows(con, entity, month):
    """The SQL entries linked to the month's payments or checklist items, and the ones not linked dated in the month."""
    return con.execute(
        """SELECT s.*, p.description AS pay_desc FROM sql_entries s LEFT JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = :e AND (p.month = :m OR s.task_id IN (SELECT id FROM tasks WHERE entity_id = :e AND month = :m)
             OR (s.payment_id IS NULL AND s.task_id IS NULL AND substr(s.doc_date, 1, 7) = :m))
           ORDER BY s.doc_date, s.id""", {"e": entity["id"], "m": month}).fetchall()


def month_workbook(con, entity, month, files=None):
    """The month report as a workbook. files: rows for an extra 'Files' sheet (the auditor package), or None."""
    pays, tasks, recon = _gather(con, entity, month)
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"

    # Payments
    ws = wb.create_sheet("Payments")
    rows = [(_day(x["p"]["due_date"]), x["p"]["description"], rulebook.get(con).label(x["p"]["category"]),
             IN if x["p"]["direction"] == "in" else OUT, x["p"]["currency"], x["p"]["amount"], x["word"], x["flag"] or "",
             _day(x["p"]["paid_date"]), x["sql"], x["bank"], "; ".join(x["on_file"]), "; ".join(x["missing"])) for x in pays]
    first, last = _table(ws, 1, ["Due date", "Description", "Type", "Direction", "Currency", "Amount", "Status", "Note", "Paid date",
                                 "SQL voucher no.", "Bank line date(s)", "Documents on file", "Documents missing"], rows,
                         [12, 42, 24, 11, 9, 14, 12, 28, 12, 18, 22, 40, 40], {1: DAY, 6: MONEY, 9: DAY})
    combos = sorted({(r[3], r[4]) for r in rows}, key=lambda k: (k[0] != OUT, k[1]))
    _totals(ws, last + 2, first, last, 2, 6,
            [(f"Total {d.lower()} {cur}", {4: _quoted(d), 5: _quoted(cur)}) for d, cur in combos])

    # Checklist
    ws = wb.create_sheet("Checklist")
    _table(ws, 1, ["Item", "Due date", "Done", "What is missing"],
           [(x["t"]["title"], _day(x["t"]["due_date"]), "Done" if x["st"]["done"] else "Not done", x["lack"]) for x in tasks],
           [48, 12, 10, 70], {2: DAY})

    # Bank lines
    ws = wb.create_sheet("Bank lines")
    brows = []
    for a in recon:
        pay_of = {p["id"]: p["description"] for p in con.execute(
            "SELECT id, description FROM payments WHERE id IN (SELECT payment_id FROM statement_lines WHERE statement_id = ?)",
            (a["statement"]["id"] if a["statement"] else 0,))}
        for l in a["lines"]:
            what = pay_of.get(l["payment_id"]) or ("No documents needed" if l["status"] == "no_docs" else "To explain")
            brows.append((a["label"], a["currency"], _day(l["txn_date"]), l["description"], l["amount"], l["balance"], what, l["note"] or ""))
    first, last = _table(ws, 1, ["Account", "Currency", "Date", "Description", "Amount", "Balance", "Matched payment", "Note"], brows,
                         [26, 9, 12, 50, 14, 14, 42, 30], {3: DAY, 5: MONEY, 6: MONEY})
    _totals(ws, last + 2, first, last, 4, 5,
            [(f"Total {w} {cur}", {2: _quoted(cur), 5: crit}) for cur in sorted({r[1] for r in brows})
             for w, crit in (("money out", '"<0"'), ("money in", '">0"'))])

    # SQL entries
    ws = wb.create_sheet("SQL entries")
    srows = [(s["doc_no"], _day(s["doc_date"]), s["doc_type"] or "", s["description"] or "", IN if db._side(s) == "in" else OUT,
              s["amount"], s["status"], s["pay_desc"] or "") for s in _sql_rows(con, entity, month)]
    first, last = _table(ws, 1, ["Doc no", "Date", "Type", "Description", "Direction", "Amount", "Status", "Linked payment"], srows,
                         [18, 12, 8, 50, 11, 14, 12, 42], {2: DAY, 6: MONEY})
    _totals(ws, last + 2, first, last, 4, 6, [(f"Total {d.lower()}", {5: _quoted(d)}) for d in (OUT, IN)])

    if files is not None:
        ws = wb.create_sheet("Files")
        _table(ws, 1, ["File in the package", "Folder", "Belongs to", "Document type", "SHA-256", "Note"],
               [(f["name"], f["folder"], f["belongs"], f["type"], f["sha256"], f["note"]) for f in files],
               [50, 36, 50, 26, 66, 34])

    # Summary
    paid = [x for x in pays if x["p"]["paid_date"]]
    lines = [l for a in recon for l in a["lines"]]
    cells = [("Company", entity["name"]), ("Month", db.month_label(month)), ("Generated", date.today().isoformat()), None,
             ("Payments", len(pays)), ("Paid", len(paid)), ("Not paid", len(pays) - len(paid)),
             ("Complete", sum(x["status"] == "complete" for x in pays)),
             ("With documents missing", sum(bool(x["missing"]) for x in pays)), None,
             ("Checklist items", len(tasks)), ("Done", sum(x["st"]["done"] for x in tasks)),
             ("Not done", sum(not x["st"]["done"] for x in tasks)), None,
             ("Bank lines", len(lines)), ("Matched", sum(bool(l["payment_id"]) for a in recon for l in a["lines"])),
             ("To explain", sum(len(a["to_explain"]) for a in recon)),
             ("Statements not imported", sum(not a["statement"] for a in recon))]
    for i, c in enumerate(cells, 1):
        if c:
            _put(summary, i, 1, c[0], bold=True)
            _put(summary, i, 2, c[1])
            summary.cell(row=i, column=2).alignment = Alignment(horizontal="left")
    r = len(cells) + 2
    _put(summary, r, 1, "Totals (all payments / paid)", bold=True)
    for d, cur in combos:
        r += 1
        mine = [x["p"]["amount"] or 0 for x in pays if (IN if x["p"]["direction"] == "in" else OUT) == d and x["p"]["currency"] == cur]
        got = [x["p"]["amount"] or 0 for x in paid if (IN if x["p"]["direction"] == "in" else OUT) == d and x["p"]["currency"] == cur]
        _put(summary, r, 1, f"{d} {cur}")
        _put(summary, r, 2, round(sum(mine), 2), MONEY)
        _put(summary, r, 3, round(sum(got), 2), MONEY)
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 36
    summary.column_dimensions["C"].width = 16
    _print_setup(summary, 1)
    return wb


def workbook_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def month_report_name(entity, month):
    return f"{entity['code']} {month} month report.xlsx"


def budget_workbook(con, entity, month, as_at=None):
    """The month's stored budget as a workbook, or LookupError when none is set up."""
    hdr = stored.header(con, entity["id"], month)
    if not hdr:
        raise LookupError(f"No budget is set up for {db.month_label(month)} yet.")
    as_at = as_at or stored.default_as_at(hdr)
    v = stored.view(con, entity["id"], month, as_at)
    desc = {p["id"]: p["description"] for p in con.execute("SELECT id, description FROM payments WHERE entity_id = ? AND month = ?",
                                                           (entity["id"], month))}
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    _put(ws, 1, 1, f"{entity['name']} - Budget for {db.month_label(month)}", bold=True)
    _put(ws, 2, 1, "Bank balance", bold=True)
    _put(ws, 2, 2, hdr["balance"], MONEY)
    _put(ws, 3, 1, "As at", bold=True)
    _put(ws, 3, 2, _day(as_at), DAY)
    ws.cell(row=2, column=2).alignment = ws.cell(row=3, column=2).alignment = Alignment(horizontal="left")
    rows = [(i, x["description"], x["details"] or "", x["currency"], x["amount"], x["paid"], x["status"]["text"],
             desc.get(x["payment_id"], "")) for i, x in enumerate(v["lines"], 1)]
    top = 5
    first, last = _table(ws, top, ["No.", "Description", "Details", "Currency", "Budget", "Paid", "Against budget", "Linked payment"], rows,
                         [6, 44, 36, 9, 14, 14, 22, 44], {5: MONEY, 6: MONEY})
    ws.freeze_panes = ws.cell(row=top + 1, column=1)
    r = last + 2
    for cur in sorted({x[3] for x in rows}):
        _put(ws, r, 2, f"Total {cur}", bold=True)
        for col in (5, 6):
            a = get_column_letter(col)
            _formula(ws, r, col, f"=SUMIFS({a}{first}:{a}{last},$D${first}:$D${last},{_quoted(cur)})")
        r += 1
    return wb


def budget_report_name(entity, month):
    return f"{entity['code']} {month} budget.xlsx"


# ---------- auditor package ----------

def _file_name(name, limit=100):
    """A safe file name cut to limit characters, keeping its extension so the file still opens."""
    ext = Path(name).suffix
    ext = "." + safe(ext[1:], 9) if len(ext) > 1 else ""
    return safe(Path(name).stem, max(limit - len(ext), 10)) + ext


def _fingerprint(path):
    """SHA-256 of a file read in chunks, or None when it can't be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _unique(taken, folder, name):
    base, dot, ext = name.rpartition(".")
    base, ext = (base, "." + ext) if dot else (name, "")
    out, n = f"{folder}{name}", 2
    while out.lower() in taken:
        out = f"{folder}{base} ({n}){ext}"
        n += 1
    taken.add(out.lower())
    return out


def _folders(con, entity, month):
    """[(folder, what it belongs to, document)] for every document the package may hold."""
    out, used = [], set()

    def folder(path):
        n, f = 2, path
        while f.lower() in used:
            f = f"{path[:-1]} ({n})/"
            n += 1
        used.add(f.lower())
        return f
    for p in auditpack._payments(con, entity, month):
        docs = auditpack._docs(con, "payment_id", p["id"])
        if docs:
            f = folder(f"Payments/{safe(p['due_date'] + ' ' + p['description'], 80)} #{p['id']}/")
            out += [(f, f"Payment: {p['description']} (due {p['due_date']})", d) for d in docs]
    for t in auditpack._tasks(con, entity, month):
        docs = auditpack._docs(con, "task_id", t["id"])
        if docs:
            f = folder(f"Checklist/{safe(t['title'], 80)}/")
            out += [(f, f"Checklist: {t['title']}", d) for d in docs]
    labels = {a["id"]: a["label"] for a in con.execute("SELECT id, label FROM accounts WHERE entity_id = ?", (entity["id"],))}
    out += [("Bank statements/", f"Bank statement: {labels.get(d['account_id'], '')}", d)
            for d in auditpack._statement_docs(con, entity, month)]
    return out


def auditor_package(con, entity, month):
    """Builds a fresh audit pack and the zip for the auditor: the pack, the month report with a Files sheet, and the
    original files. A file whose fingerprint no longer matches is left out and listed. Returns (zip path, files in it,
    files left out)."""
    pack = auditpack.build(con, entity, month)
    pack_bytes = pack.read_bytes()
    report_name = month_report_name(entity, month)
    taken = {pack.name.lower(), report_name.lower()}
    files = [{"name": pack.name, "folder": "", "belongs": "Audit pack", "type": "Audit pack PDF",
              "sha256": hashlib.sha256(pack_bytes).hexdigest(), "note": ""},
             {"name": report_name, "folder": "", "belongs": "Month report", "type": "Excel report", "sha256": "", "note": "This file"}]
    blobs, left_out = [], 0
    for folder, belongs, d in _folders(con, entity, month):
        label = rulebook.get(con).doc_label(d["doc_type"])
        src = path_of(d)
        if _fingerprint(src) != d["sha256"]:
            left_out += 1
            files.append({"name": "", "folder": folder, "belongs": belongs, "type": label, "sha256": d["sha256"],
                          "note": f"changed or missing on disk: {d['original_name']} left out"})
            continue
        name = _unique(taken, folder, _file_name(d["original_name"]))
        blobs.append((name, src))
        files.append({"name": name, "folder": folder, "belongs": belongs, "type": label, "sha256": d["sha256"], "note": ""})
    report = workbook_bytes(month_workbook(con, entity, month, files))
    target = EXPORTS_DIR / entity["code"]
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now()
    out = target / f"Auditor package {entity['code']} {month} ({stamp:%Y%m%d-%H%M}).zip"
    if out.exists():
        out = target / f"Auditor package {entity['code']} {month} ({stamp:%Y%m%d-%H%M%S}).zip"
    tmp = out.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(pack.name, pack_bytes)
            z.writestr(report_name, report)
            for name, src in blobs:
                z.write(src, name)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out, len(blobs) + 2, left_out
