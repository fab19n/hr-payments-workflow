"""Reading the audit trail for people: entries with filters, one entry's changes field by field, one record's history,
the changes made outside the app waiting to be accepted, the replay check and the Excel export. Capture and sealing
live in audit.py; nothing here writes except check(), which records that a check was run."""
import json
import sqlite3

from . import audit

TABLE_LABELS = {
    "entities": ("Company", "companies"), "accounts": ("Bank account", "bank accounts"),
    "payees": ("Recurring payment", "recurring payments"), "advances": ("Salary advance", "salary advances"),
    "months": ("Month", "months"), "tasks": ("Checklist item", "checklist items"), "payments": ("Payment", "payments"),
    "documents": ("Document", "documents"), "statements": ("Bank statement", "bank statements"),
    "statement_lines": ("Bank line", "bank lines"), "sql_imports": ("SQL import", "SQL imports"),
    "sql_entries": ("SQL entry", "SQL entries"), "sql_journal_lines": ("SQL journal line", "SQL journal lines"),
    "activity": ("Activity log line", "activity log lines"),
    "book_openings": ("Book opening", "book openings"), "budgets": ("Budget", "budgets"),
    "budget_lines": ("Budget line", "budget lines"), "app_settings": ("General setting", "general settings"),
    "payment_types": ("Payment type", "payment types"), "doc_types": ("Document type", "document types"),
    "required_sets": ("Required documents", "sets of required documents"),
    "checklist_items": ("Checklist template item", "checklist template items"),
    "checklist_terms": ("Checklist template wording", "checklist template wordings"),
    "people_tasks": ("Joiner or leaver reminder", "joiner and leaver reminders"),
    "people_task_terms": ("Joiner or leaver reminder wording", "joiner and leaver reminder wordings"),
    "guess_words": ("Payment type guess", "payment type guesses"), "hint_words": ("Salary words", "salary words"),
    "filing_words": ("SQL filing words", "SQL filing words"),
    "parties": ("Customer or supplier", "customers and suppliers"), "gl_accounts": ("GL account", "chart of accounts"),
    "statutory_accounts": ("Statutory account", "statutory accounts"),
    "ledger_batches": ("Ledger read", "ledger reads"), "ledger_docs": ("Ledger document", "ledger documents"),
    "ledger_lines": ("Account line", "account lines"), "ledger_openings": ("Opening balance", "opening balances"),
    # events
    "pack": ("Audit pack", "audit packs"), "backup": ("Backup", "backups"), "export": ("Export", "exports"),
    "settings": ("Setting", "settings"), "audit": ("Audit trail", "audit trail notes"), "read": ("Opened file", "opened files"),
    "restore": ("Put back", "records put back"),
}
SOURCES = {"user": "You", "auto": "Automatic", "import": "Import", "migration": "Update", "seed": "Starting data",
           "system": "System", "outside": "Outside this app"}
OPS = {"insert": "Added", "update": "Changed", "delete": "Removed", "baseline": "As it stood", "event": "Done"}
FIELD_LABELS = {
    "description": "Description", "amount": "Amount", "paid_date": "Paid date", "due_date": "Due date",
    "bank_ref": "Bank reference", "sql_ref": "SQL voucher no.", "einvoice_ref": "e-Invoice UIN", "notes": "Notes",
    "category": "Type", "account_id": "Bank account", "difference_note": "Reason for the difference",
    "amount_is_estimate": "Estimate", "planned_amount": "Planned amount", "planned_is_estimate": "Planned as estimate",
    "paid_source": "Paid date from", "undo_link": "Link to undo", "payee_id": "Recurring payment", "entity_id": "Company",
    "payment_id": "Payment", "task_id": "Checklist item", "statement_id": "Bank statement", "done_at": "Ticked",
    "note": "Note", "title": "Title", "detail": "Detail", "required_docs": "Documents asked for", "closed_at": "Filed",
    "generated_at": "Set up", "name": "Name", "desc_template": "Description each month", "amount_varies": "Amount varies",
    "month_offset": "Paid in", "due_day": "Due day", "bank_details": "Bank details", "reference": "Reference",
    "match_words": "Matching words", "active": "Active", "start_date": "Start date", "end_date": "Last day",
    "direction": "Money in or out", "doc_type": "Document type", "original_name": "File", "removed_at": "Removed",
    "replaced_by": "Replaced by", "status": "Status", "txn_date": "Date", "balance": "Balance", "confirmed_at": "Confirmed",
    "reconciled_at": "Reconciled", "reconciled_how": "Reconciled how", "reconciled_note": "Reconciliation note",
    "doc_no": "Doc no.", "doc_date": "Doc date", "payee": "Payee", "label": "Label", "number": "Account number",
    "currency": "Currency", "monthly_deduction": "Monthly deduction", "start_month": "From", "end_month": "Until",
    "first_month": "First month tracked", "fy_start": "Financial year starts in","uses_sql": "Kept in SQL Account", "code": "Code", "what": "Line",
    "balance_as_at": "Balance as at", "as_at": "Balance as at", "details": "Details", "month": "Month",
    "short_name": "Short name", "reg_no": "Registration no.", "tin": "Tax ID (TIN)", "sst_no": "SST no.",
    "employer_kwsp": "KWSP employer no.", "employer_perkeso": "PERKESO employer no.", "employer_lhdn": "LHDN employer no.", "payable_code": "Payable account",
    "employer_code": "Employer's share account", "kind": "Kind",
    "sql_database": "SQL Account database", "bank": "Bank", "statement_format": "Statement format", "gl_code": "GL account code",
    "sql_payment_method": "SQL payment method", "cash_book": "Cash book account", "key": "Key", "value": "Value",
    "plural": "Several are called", "singular": "One is called", "pack_order": "Place in the audit pack",
    "from_sql": "Issued by SQL Account", "legal_due_offset": "Legal deadline in", "legal_due_day": "Legal deadline day",
    "system": "Used by the app", "payment_type": "Payment type", "from_month": "From", "to_month": "Until",
    "docs": "Documents", "set_at": "Set",
    "completion": "Shown done by", "in_use": "In use", "due_offset": "Due in", "deadline": "A deadline in Next up",
    "submit_as": "Submitted as", "rule": "Payments that show it done", "sort": "Order", "item_id": "Checklist template item",
    "people_task_id": "Reminder", "days": "Days from the date", "salary_over": "Salary over",
    "words": "Words", "doc_kind": "Documents", "checklist_code": "Checklist item",
    "sql_code": "SQL code", "brn": "Business registration no. (BRN)", "party_id": "Supplier or customer",
    "type": "Account type", "sql_type": "SQL group", "special": "Special account", "parent_code": "Parent account", "payment_method": "Payment method",
    "cheque_no": "Cheque no.", "dockey": "SQL doc key", "currency_code": "Currency (SQL)",
    # a record put back (restore.put_back's event)
    "record": "Record", "from_entry": "Put back from entry", "from_row": "Trail row of the delete", "as_key": "Put back as", "deleted_at": "Deleted",
    "with": "Put back with it",
    # an audit pack built (app._pack_event): its file and what built it
    "file": "File", "sha256": "Fingerprint (SHA-256)", "size": "Size in bytes", "via": "Built for", "today": "Statuses worked out on",
    "generated": "Generated (printed on the cover)", "trail_entry": "Audit trail entry (printed on the cover)",
    "check_code": "Check code", "code_commit": "Program version (git commit)", "code_files": "Program files' fingerprint",
    "python": "Python", "fpdf2": "fpdf2", "pypdf": "pypdf",
}
NAME_FIELDS = ("description", "name", "title", "label", "doc_no", "original_name", "what", "code", "payment_type", "month", "key")
# Bank details and account numbers, wherever they are kept (a budget line's details are filled from the payee's bank
# details): masked in the trail's views and export until someone asks to see them.
SENSITIVE = {("payees", "bank_details"), ("accounts", "number"), ("budget_lines", "details")}
NOISE = {"id", "created_at", "sort", "line_no"}  # not shown in a change list (still in the trail)
BASELINE_SHOWN = 200


def _label(tbl, n=1):
    one, many = TABLE_LABELS.get(tbl, (tbl.replace("_", " ").capitalize(), tbl.replace("_", " ")))
    return one if n == 1 else many


def field_label(name):
    return FIELD_LABELS.get(name) or name.replace("_", " ").capitalize()


def mask(tbl, field, value, show):
    if show or value in (None, "") or (tbl, field) not in SENSITIVE:
        return value
    s = str(value)
    return "••••" + s[-4:] if len(s) > 4 else "••••"


def _record_name(img, key):
    img = img or {}
    for f in NAME_FIELDS:
        if img.get(f) not in (None, ""):
            return str(img[f])
    return f"#{key}"


class _Names:
    """Today's names for ids a change refers to (a bank account, a recurring payment, a company, a payment)."""

    LOOKUP = {"account_id": ("accounts", "label"), "payee_id": ("payees", "name"), "entity_id": ("entities", "code"),
              "payment_id": ("payments", "description"), "task_id": ("tasks", "title")}

    def __init__(self, con):
        self.con, self.cache = con, {}

    def __call__(self, field, value):
        if value is None or field not in self.LOOKUP:
            return value
        k = (field, value)
        if k not in self.cache:
            t, col = self.LOOKUP[field]
            r = self.con.execute(f"SELECT {col} FROM {t} WHERE id = ?", (value,)).fetchone()
            self.cache[k] = f"{r[0]} (#{value})" if r else f"#{value} (removed)"
        return self.cache[k]


def describe_row(r, names, show=False):
    """One audit_row as {table, op, key, record, entity_id, fields: [{name, label, before, after}]}: for a change only
    the fields that changed; for an addition or removal every field that holds something; for an event its details."""
    tbl, op = r["tbl"], r["op"]
    before = json.loads(r["before"]) if r["before"] else None
    after = json.loads(r["after"]) if r["after"] else None
    out = {"id": r["id"], "at": r["at"], "table": tbl, "table_label": _label(tbl), "op": op, "op_label": OPS[op],
           "key": r["row_key"], "entity_id": r["entity_id"], "record": _record_name(after or before, r["row_key"]), "fields": []}
    if op == "event":
        out["record"] = r["row_key"]
        out["fields"] = [{"name": k, "label": field_label(k), "before": None, "after": mask(tbl, k, v, show)} for k, v in (after or {}).items()]
        return out
    keys = list((after or before or {}).keys())
    for k in keys:
        if k in NOISE:
            continue
        b = before.get(k) if before else None
        a = after.get(k) if after else None
        if op == "update" and b == a:
            continue
        if op != "update" and (a if after else b) in (None, ""):
            continue
        out["fields"].append({"name": k, "label": field_label(k), "before": mask(tbl, k, names(k, b), show),
                              "after": mask(tbl, k, names(k, a), show)})
    return out


def _rows_of(con, tx):
    if tx["null_rows"] is not None:
        return con.execute("SELECT * FROM audit_row WHERE token IS NULL AND id IN (SELECT value FROM json_each(?)) ORDER BY id",
                           (tx["null_rows"],)).fetchall()
    return con.execute("SELECT * FROM audit_row WHERE token = ? ORDER BY id", (tx["token"],)).fetchall()


def headline(tx):
    """One line for an entry: its first activity-log line, else what changed in words (Changed 2 payments, added 1 bank line)."""
    if tx["summary"]:
        first = tx["summary"].split("\n")[0]
        more = tx["summary"].count("\n")
        return first + (f" (and {more} more)" if more else "")
    counts = json.loads(tx["counts"] or "{}")
    if counts.get("audit", {}).get("event") and len(counts) == 1:
        return tx["action"]
    parts = []
    for tbl, ops in counts.items():
        for op, n in ops.items():
            if op == "baseline":
                parts.append(f"recorded {n} {_label(tbl, n)} as they stood")
            elif op == "event":
                parts.append(f"{_label(tbl, n).lower()}" if tbl != "read" else "opened a file")
            else:
                parts.append(f"{OPS[op].lower()} {n} {_label(tbl, n).lower()}")
    text = ", ".join(parts) or tx["action"]
    return text[0].upper() + text[1:]


def _tx_out(tx, companies):
    return {"id": tx["id"], "at": tx["at"], "actor": tx["actor"], "machine": tx["machine"], "source": tx["source"],
            "source_label": SOURCES.get(tx["source"], tx["source"]), "action": tx["action"], "reason": tx["reason"],
            "entity_id": tx["entity_id"], "company": companies.get(tx["entity_id"]), "headline": headline(tx),
            "summary": tx["summary"], "counts": json.loads(tx["counts"] or "{}"), "late": bool(tx["late"]),
            "check_code": tx["hash"][:8]}


def _companies(con):
    return {r[0]: r[1] for r in con.execute("SELECT id, code FROM entities")}


def _has_row(cond):
    """SQL: entry t has a row r where cond holds (cond's ? placeholders are bound twice, once per branch). The token
    branch is pinned to the token index: left to itself SQLite may pick the entity or tbl index and scan the trail."""
    return (f"(EXISTS (SELECT 1 FROM audit_row r INDEXED BY audit_row_token WHERE r.token = t.token AND {cond})"
            f" OR (t.null_rows IS NOT NULL AND EXISTS (SELECT 1 FROM json_each(t.null_rows) j CROSS JOIN audit_row r ON r.id = j.value"
            f" WHERE {cond})))")


def entries(con, f, limit=50):
    """Entries newest first, filtered: f has optional from / to (YYYY-MM-DD), entity_id, tbl, source, q (words in the
    summary, action, reason or any value changed) and before_id (for the next page). Returns {entries, more}."""
    where, args = ["1 = 1"], []
    if f.get("from"):
        where.append("t.at >= ?"); args.append(f["from"])
    if f.get("to"):
        where.append("t.at < date(?, '+1 day')"); args.append(f["to"])
    if f.get("entity_id") is not None:
        where.append(f"(t.entity_id = ? OR {_has_row('r.entity_id = ?')})")
        args += [f["entity_id"]] * 3
    if f.get("tbl"):
        where.append(_has_row("r.tbl = ?")); args += [f["tbl"]] * 2
    if f.get("source"):
        where.append("t.source = ?"); args.append(f["source"])
    for word in (f.get("q") or "").split():
        like = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        # values only, not field names: "amount" must not match every payment because each row has an amount field
        values = ("r.op != 'baseline' AND (EXISTS (SELECT 1 FROM json_each(r.after) ja WHERE CAST(ja.value AS TEXT) LIKE ? ESCAPE '\\')"
                  " OR EXISTS (SELECT 1 FROM json_each(r.before) jb WHERE CAST(jb.value AS TEXT) LIKE ? ESCAPE '\\') OR r.row_key = ?)")
        where.append(f"""(t.summary LIKE ? ESCAPE '\\' OR t.action LIKE ? ESCAPE '\\' OR t.reason LIKE ? ESCAPE '\\'
                         OR t.actor LIKE ? ESCAPE '\\' OR {_has_row(values)})""")
        args += [like] * 4 + [like, like, word] * 2
    if f.get("before_id"):
        where.append("t.id < ?"); args.append(int(f["before_id"]))
    rows = _fetch(con, f"SELECT * FROM audit_tx t WHERE {' AND '.join(where)} ORDER BY t.id DESC LIMIT ?", args + [limit + 1])
    comp = _companies(con)
    return {"entries": [_tx_out(t, comp) for t in rows[:limit]], "more": len(rows) > limit}


def _fetch(con, sql, args=()):
    rf, con.row_factory = con.row_factory, sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.row_factory = rf


def entry(con, tx_id, show=False):
    """One entry with every change it holds, field by field (a baseline lists the first BASELINE_SHOWN records)."""
    tx = _fetch(con, "SELECT * FROM audit_tx WHERE id = ?", (tx_id,))
    if not tx:
        return None
    tx = tx[0]
    rf, con.row_factory = con.row_factory, sqlite3.Row
    try:
        rows = _rows_of(con, tx)
    finally:
        con.row_factory = rf
    names = _Names(con)
    base = [r for r in rows if r["op"] == "baseline"]
    shown = [r for r in rows if r["op"] != "baseline"] + base[:BASELINE_SHOWN]
    out = _tx_out(tx, _companies(con))
    out["changes"] = [describe_row(r, names, show) for r in shown]
    out["not_shown"] = max(0, len(base) - BASELINE_SHOWN)
    out["prev_hash"], out["hash"] = tx["prev_hash"], tx["hash"]
    return out


def history(con, tbl, key, show=False):
    """Every change to one record, newest first, each with when, who, how and why."""
    # a recurring payment's history includes its salary advances (rows of their own table, tied by payee_id)
    # and a checklist template item's or reminder's history its wordings over time (checklist_terms, people_task_terms)
    parent = {"payees": ("advances", "payee_id"), "checklist_items": ("checklist_terms", "item_id"),
              "people_tasks": ("people_task_terms", "people_task_id")}.get(tbl)
    child = (f"""OR (r.tbl = '{parent[0]}' AND r.op != 'event'
                 AND CAST(json_extract(COALESCE(r.after, r.before), '$.{parent[1]}') AS TEXT) = ?)""" if parent else "")
    # a record put back (restore.put_back): the event naming the delete it came from, under the key it had then and the
    # key it came back with (a new one when its id had been given to another record since)
    put = """OR (r.tbl = 'restore' AND r.op = 'event' AND json_extract(r.after, '$.table') = ?
              AND (json_extract(r.after, '$.key') = ? OR json_extract(r.after, '$.as_key') = ?))"""
    rows = _fetch(con, f"""SELECT r.*, t.id AS tx_id, t.actor, t.source, t.action, t.reason, t.late
                          FROM audit_row r LEFT JOIN audit_tx t ON t.token = r.token
                          WHERE (r.tbl = ? AND r.row_key = ?) {child} {put} ORDER BY r.id DESC""",
                  (tbl, str(key)) + ((str(key),) if child else ()) + (tbl, str(key), str(key)))
    names = _Names(con)
    out = []
    for r in rows:
        d = describe_row(r, names, show)
        outside = r["tx_id"] is None and r["token"] is None
        if outside:  # a token-less row: sealed by an 'outside' entry, or still waiting to be accepted
            sealed = con.execute("""SELECT t.id, t.actor, t.source, t.action, t.reason FROM audit_tx t, json_each(t.null_rows) j
                                    WHERE t.null_rows IS NOT NULL AND j.value = ?""", (r["id"],)).fetchone()
        d.update({"tx_id": r["tx_id"], "actor": r["actor"], "source": r["source"], "action": r["action"], "reason": r["reason"],
                  "source_label": SOURCES.get(r["source"], r["source"]), "late": bool(r["late"])})
        if outside:
            if sealed:
                d.update({"tx_id": sealed[0], "actor": sealed[1], "source": sealed[2], "action": sealed[3], "reason": sealed[4],
                          "source_label": SOURCES.get(sealed[2], sealed[2])})
            else:
                d.update({"source": "outside", "source_label": "Outside this app, not accepted yet"})
        out.append(d)
    return {"table": tbl, "table_label": _label(tbl), "key": str(key), "changes": out}


OUTSIDE_SHOWN = 200


def outside(con, show=False):
    """The changes made outside the app that nobody has accepted yet, oldest first, field by field: {total, changes
    (at most OUTSIDE_SHOWN), upto_id (the last row listed: Accept seals up to it and no further)}."""
    total = audit.outside_rows(con)
    rows = _fetch(con, f"SELECT * FROM audit_row WHERE {audit.uncovered(con)} ORDER BY id LIMIT {OUTSIDE_SHOWN}")
    names = _Names(con)
    return {"total": total, "changes": [describe_row(r, names, show) for r in rows], "upto_id": rows[-1]["id"] if rows else None}


def replay(con, limit=50):
    """Whether each record now is what the trail last recorded for it. A difference means it was changed while the
    audit triggers were missing (another program), which the hash chain alone can't show. Columns added since a record
    was last recorded are not compared. Returns {"checked", "problems": [...]}."""
    problems, checked = [], 0
    for t in audit.audited_tables(con):
        if t == "activity":
            continue
        key, _, obj = audit._exprs(con, t, "X")
        live = {k: json.loads(v) for k, v in con.execute(f"SELECT {key}, {obj} FROM {audit._q(t)} AS X")}
        last = {}
        for k, op, before, after in con.execute(
                "SELECT row_key, op, before, after FROM audit_row WHERE tbl = ? AND op != 'event' ORDER BY id", (t,)):
            last[k] = None if op == "delete" else json.loads(after)
        checked += len(live)
        for k, now in live.items():
            if k not in last:
                problems.append({"table": t, "table_label": _label(t), "key": k, "record": _record_name(now, k),
                                 "problem": "is in the records but not in the trail", "op": "insert", "before": None, "after": now})
            elif last[k] is None:
                problems.append({"table": t, "table_label": _label(t), "key": k, "record": _record_name(now, k),
                                 "problem": "was removed in the trail but is still in the records", "op": "insert", "before": None, "after": now})
            else:
                diff = [c for c in now if c in last[k] and now[c] != last[k][c]]
                if diff:
                    problems.append({"table": t, "table_label": _label(t), "key": k, "record": _record_name(now, k),
                                     "problem": "differs from the trail in " + ", ".join(field_label(c) for c in diff),
                                     "op": "update", "before": last[k], "after": now})
        for k, img in last.items():
            if img is not None and k not in live:
                problems.append({"table": t, "table_label": _label(t), "key": k, "record": _record_name(img, k),
                                 "problem": "is in the trail but no longer in the records", "op": "delete", "before": img, "after": None})
    public = [{k: v for k, v in p.items() if k not in ("op", "before", "after")} for p in problems[:limit]]
    return {"checked": checked, "problems": public, "more": max(0, len(problems) - limit), "count": len(problems),
            "_all": problems}


def check(con):
    """The full check people run from the page: the whole hash chain, the triggers, the head file and the replay. The
    result is recorded in the trail as an event (the caller commits)."""
    v = audit.verify(con)
    rp = replay(con)
    # Each record that differs from the trail was changed while the triggers were missing. It goes into the trail as
    # a change made outside the app (no token), so it shows on the page and in the record's history and is accepted
    # with a reason like any other, instead of being absorbed silently by the record's next edit.
    for p in rp.pop("_all"):
        con.execute("INSERT INTO audit_row (token, tbl, row_key, op, entity_id, before, after) VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                    (p["table"], p["key"], p["op"], (p["after"] or p["before"] or {}).get("entity_id"),
                     json.dumps(p["before"], ensure_ascii=False, separators=(",", ":")) if p["before"] is not None else None,
                     json.dumps(p["after"], ensure_ascii=False, separators=(",", ":")) if p["after"] is not None else None))
    con.mark()  # these stay for the person to accept: not sealed as the app's own when this check is saved
    ok = v["ok"] and not rp["count"]
    audit.event(con, "audit", "check", {"ok": ok, "entries_checked": v["checked"], "chain_problems": v["problems"][:20],
                                        "records_checked": rp["checked"], "record_problems": rp["count"],
                                        "records": [f"{p['table_label']} {p['record']} {p['problem']}" for p in rp["problems"][:20]],
                                        "check_code": v["check_code"]})
    return {**v, "ok": ok, "replay": rp}


def export_rows(con, f, show=False, cap=5000):
    """Rows for the Excel export: one per field changed (an event: one per detail), for the entries the filters find
    (at most cap entries; baselines are summarised in one row)."""
    rows, before_id, n, cut = [], None, 0, False
    while n < cap:
        page = entries(con, {**f, "before_id": before_id}, limit=min(500, cap - n))
        for e in page["entries"]:
            d = entry(con, e["id"], show)
            base_rows = sum(ops.get("baseline", 0) for ops in e["counts"].values())
            head = [e["at"].replace("T", " ")[:19], e["actor"], e["source_label"], e["company"] or "", e["headline"], e["reason"] or "", e["id"], e["check_code"]]
            if base_rows:
                rows.append(head + ["", f"{base_rows} records as they stood", "As it stood", "", "", ""])
            for ch in d["changes"]:
                if ch["op"] == "baseline":
                    continue
                for fld in ch["fields"] or [{"label": "", "before": None, "after": None}]:
                    rows.append(head + [ch["table_label"], ch["record"], ch["op_label"], fld["label"],
                                        _cell(fld["before"]), _cell(fld["after"])])
            if not d["changes"]:
                rows.append(head + ["", "", "", "", "", ""])
            n += 1
        if not page["more"] or not page["entries"]:
            break
        before_id = page["entries"][-1]["id"]
        cut = n >= cap
    return rows, cut


def _cell(v):
    if v is None:
        return ""
    return v if isinstance(v, (int, float, str)) else json.dumps(v, ensure_ascii=False)


EXPORT_HEAD = ["When", "Made by", "Source", "Company", "What happened", "Reason", "Entry", "Check code",
               "Record type", "Record", "Change", "Field", "Before", "After"]
