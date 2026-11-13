"""Check this pack: whether an audit pack's file is still the one built, and what changed since in what it reads.

The owner chose (13 Nov 2026) a check, not a rebuild: rebuilding a past pack from the trail would need the code that
built it, and a mismatch could not tell changed records from changed code. So a pack is checked two ways:
- its file against the fingerprint recorded in the trail when it was built (unchanged, changed, missing, or built
  before the trail recorded packs);
- the trail's rows after the pack's own row, for that company and month: what the pack reads (auditpack.build), each
  shown as the trail shows it (auditread.describe_row), grouped and counted, and what the report can't tell said
  plainly (above all, whether the PDF would come out differently).
From Phase 7 a pack's event also records what built it (auditpack.program, the day, the Generated line, the trail entry
and check code on its cover), so an exact rebuild can be added later. Nothing here writes.
"""
import json
import sqlite3
from datetime import date, datetime

from . import audit, auditpack, auditread, rules
from .config import PACKS_DIR
from .db import _listed, day_label, month_label, packs_of
from .docstore import path_of, verify

SHOWN = 50  # changes listed per group (all are counted)
# The groups, in the order shown: key, heading, and how the summary counts them ("3 to payments").
GROUPS = (("payments", "Payments", "to payments"), ("documents", "Documents", "to documents"),
          ("tasks", "Checklist items", "to checklist items"),
          ("statements", "Bank statements and their lines", "to bank statements and their lines"),
          ("sql", "SQL vouchers linked to its payments or checklist items", "to SQL vouchers linked to them"),
          ("month", "The month (set up, filed)", "to the month itself"),
          ("rules", "Rules that reach the month", "to the rules for the month"),
          ("types", "Payment types, document types and general settings", "to payment types, document types or general settings"),
          ("company", "The company and its bank accounts", "to the company or its bank accounts"),
          ("packs", "Packs built since for this month", None))
RULE_TABLES = ("required_sets", "checklist_terms", "checklist_items")
TYPE_TABLES = ("payment_types", "doc_types", "app_settings")
OWN_TABLES = ("payments", "tasks", "months", "statements", "statement_lines", "documents", "sql_entries", "accounts")


def _fetch(con, sql, args=()):
    rf, con.row_factory = con.row_factory, sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.row_factory = rf


def _events(con, ent, month):
    """The trail's pack events for a company and month, oldest first."""
    return _fetch(con, """SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' AND entity_id = ?
                          AND json_extract(after, '$.month') = ? ORDER BY id""", (ent["id"], month))


def _name(row):
    return json.loads(row["after"] or "{}").get("file") or row["row_key"]


def _file(detail, ent, name):
    """Where the pack's file is: in the folder of the company's code when it was built, else of its code now."""
    for code in dict.fromkeys(c for c in (detail.get("company"), ent["code"]) if c):
        p = PACKS_DIR / code / name
        if p.is_file():
            return p
    return PACKS_DIR / (detail.get("company") or ent["code"]) / name


def _safe(name):
    """A pack file name as a request may give it: a name alone, never a path."""
    return (isinstance(name, str) and name.lower().endswith(".pdf") and not name.startswith(".")
            and not any(ch in name for ch in "/\\:\0"))


def packs(con, ent, month):
    """The packs built for a company and month, newest first: the files in its folder and the packs the trail
    recorded, as [{name, path (None when missing), at, event (the trail row, None for one built before the trail
    recorded packs), via, missing}]."""
    out = {p.name: {"name": p.name, "path": p, "at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes"),
                    "event": None, "via": None, "missing": False} for p in packs_of(ent, month)}
    for r in _events(con, ent, month):
        d, name = json.loads(r["after"] or "{}"), _name(r)
        path = _file(d, ent, name)
        item = out.setdefault(name, {"name": name, "path": path if path.is_file() else None, "missing": not path.is_file()})
        item.update({"event": r["id"], "at": r["at"][:16], "via": d.get("via")})  # when the trail says it was built
    return sorted(out.values(), key=lambda p: p["at"], reverse=True)


def _img(r):
    return [json.loads(x) for x in (r["before"], r["after"]) if x]


def _any(r, test):
    return any(test(i) for i in _img(r))


def _reaches(i, month):
    return (i.get("from_month") or "") <= month and (i.get("to_month") is None or i["to_month"] >= month)


# What the bank reconciliation reads of another month's payment paid in this month: a change to anything else (a note, a
# payee) on such a payment isn't one to this month's pack.
RECON_FIELDS = ("paid_date", "paid_source", "amount", "currency", "account_id", "description", "direction",
                "sql_ref", "month")


def _recon_changed(r):
    b, a = (json.loads(x) if x else {} for x in (r["before"], r["after"]))
    return any(b.get(k) != a.get(k) for k in RECON_FIELDS)


def _changes(con, ent, month, after_id, token):
    """The trail's rows after after_id (not those of the pack's own entry) that touch what the month's pack reads, as
    {group key: [rows]} in trail order."""
    e, ek = ent["id"], str(ent["id"])
    rows = _fetch(con, f"""SELECT * FROM audit_row WHERE id > ? AND (token IS NULL OR token IS NOT ?)
        AND op IN ('insert', 'update', 'delete', 'event') AND (
          (tbl IN ({', '.join('?' * len(OWN_TABLES))}) AND op != 'event' AND (entity_id = ? OR (entity_id IS NULL AND token IS NULL)))
          OR (tbl = 'entities' AND row_key = ? AND op != 'event')
          OR (tbl IN ({', '.join('?' * len(RULE_TABLES + TYPE_TABLES))}) AND op != 'event')
          OR (tbl = 'pack' AND op = 'event' AND entity_id = ? AND json_extract(after, '$.month') = ?))
        ORDER BY id""", (after_id, token, *OWN_TABLES, e, ek, *RULE_TABLES, *TYPE_TABLES, e, month))
    by = {}
    for r in rows:
        by.setdefault(r["tbl"], []).append(r)
    mine = lambda i: i.get("entity_id") == e

    def ids(sql, args):
        return {x[0] for x in con.execute(sql, args)} - {None}

    def held(rs, field="id"):  # the ids the rows' images name (never None: an empty field must not match another's)
        return {i.get(field) for r in rs for i in _img(r)} - {None}

    # What the pack holds now, and anything the trail shows was held since (a payment moved to another month, a
    # statement deleted), so the documents, lines and vouchers of either are found. Two kinds of payment: the month's
    # own, printed with their documents (auditpack._payments), and another month's paid in it, read only by the bank
    # reconciliation, for the fields below and the vouchers linked to it (recon reads those by payment).
    of_month = lambda i: mine(i) and i.get("month") == month
    paid_in = lambda i: mine(i) and (i.get("paid_date") or "")[:7] == month
    own = [r for r in by.get("payments", []) if _any(r, of_month)]
    paid = [r for r in by.get("payments", []) if not _any(r, of_month) and _any(r, paid_in)]
    month_pay = ids("SELECT id FROM payments WHERE entity_id = ? AND month = ?", (e, month)) | held(own)
    paid_pay = ids("SELECT id FROM payments WHERE entity_id = ? AND substr(paid_date, 1, 7) = ?", (e, month)) | held(paid)
    pay = sorted(own + [r for r in paid if r["op"] != "update" or _recon_changed(r)], key=lambda r: r["id"])
    tasks = [r for r in by.get("tasks", []) if _any(r, lambda i: mine(i) and i.get("month") == month)]
    pack_items = {i.get("id") for r in tasks for i in _img(r) if i.get("code") == rules.TASK_PACK} - {None}
    pack_items |= ids("SELECT id FROM tasks WHERE entity_id = ? AND code = ?", (e, rules.TASK_PACK))
    tasks = [r for r in tasks if not _any(r, lambda i: i.get("id") in pack_items)]  # the pack's own item isn't in it
    task_ids = ids("SELECT id FROM tasks WHERE entity_id = ? AND month = ?", (e, month)) - pack_items
    task_ids |= held(tasks)
    accts = ids("SELECT id FROM accounts WHERE entity_id = ?", (e,)) | held([r for r in by.get("accounts", []) if _any(r, mine)])
    stmts = [r for r in by.get("statements", []) if _any(r, lambda i: i.get("month") == month and i.get("account_id") in accts)]
    stmt_ids = ids("SELECT id FROM statements WHERE month = ? AND account_id IN (SELECT id FROM accounts WHERE entity_id = ?)", (month, e))
    stmt_ids |= held(stmts)
    stmt_docs = held(stmts, "document_id")
    stmt_docs |= ids("SELECT document_id FROM statements WHERE id IN (SELECT value FROM json_each(?))", (json.dumps(sorted(stmt_ids)),))
    lines = [r for r in by.get("statement_lines", []) if _any(r, lambda i: i.get("statement_id") in stmt_ids)]
    docs = [r for r in by.get("documents", []) if _any(r, lambda i: i.get("doc_type") != "sqlexport" and i.get("task_id") not in pack_items and (
        i.get("payment_id") in month_pay or i.get("task_id") in task_ids or i.get("statement_id") in stmt_ids or i.get("id") in stmt_docs
        or (mine(i) and i.get("month") == month and not i.get("payment_id") and not i.get("task_id"))))]
    sql = [r for r in by.get("sql_entries", []) if _any(r, lambda i: i.get("payment_id") in month_pay | paid_pay or i.get("task_id") in task_ids)]
    month_rows = [r for r in by.get("months", []) if _any(r, lambda i: mine(i) and i.get("month") == month)]
    item_of = {x[0]: x[1] for x in con.execute("SELECT id, entity_id FROM checklist_items")}
    rule_rows = [r for r in by.get("required_sets", []) if _any(r, lambda i: i.get("entity_id") in (None, e) and _reaches(i, month))]
    rule_rows += [r for r in by.get("checklist_terms", []) if _any(r, lambda i: item_of.get(i.get("item_id"), e) in (None, e) and _reaches(i, month))]
    rule_rows += [r for r in by.get("checklist_items", []) if _any(r, lambda i: i.get("entity_id") in (None, e))]
    company = by.get("entities", []) + [r for r in by.get("accounts", []) if _any(r, mine)]
    return {"payments": pay, "documents": docs, "tasks": tasks, "statements": sorted(stmts + lines, key=lambda r: r["id"]),
            "sql": sql, "month": month_rows, "rules": sorted(rule_rows, key=lambda r: r["id"]),
            "types": sorted(sum((by.get(t, []) for t in TYPE_TABLES), []), key=lambda r: r["id"]),
            "company": sorted(company, key=lambda r: r["id"]), "packs": by.get("pack", [])}


def _entries(con, rows):
    """The trail entry of each row, by row id: its own entry, or for a row written outside the app the entry that
    accepted it (None while it waits to be accepted)."""
    toks = sorted({r["token"] for r in rows if r["token"]})
    by_tok = {}
    for i in range(0, len(toks), 500):
        part = toks[i:i + 500]
        by_tok.update({t["token"]: t for t in _fetch(con, f"SELECT * FROM audit_tx WHERE token IN ({', '.join('?' * len(part))})", part)})
    out = {r["id"]: by_tok.get(r["token"]) for r in rows if r["token"]}
    loose = [r["id"] for r in rows if not r["token"]]
    if loose and audit._exists(con, "audit_sealed"):
        sealed = {}
        for i in range(0, len(loose), 500):
            part = loose[i:i + 500]
            sealed.update(con.execute(f"SELECT row_id, tx_id FROM audit_sealed WHERE row_id IN ({', '.join('?' * len(part))})", part).fetchall())
        txs = {}
        tids = sorted(set(sealed.values()))
        for i in range(0, len(tids), 500):
            part = tids[i:i + 500]
            txs.update({t["id"]: t for t in _fetch(con, f"SELECT * FROM audit_tx WHERE id IN ({', '.join('?' * len(part))})", part)})
        out.update({i: txs.get(sealed.get(i)) for i in loose})
    return out


def _row_out(r, tx, names):
    d = auditread.describe_row(r, names)
    outside = not r["token"]
    d.update({"entry": tx["id"] if tx else None, "actor": tx["actor"] if tx else None, "reason": tx["reason"] if tx else None,
              "source": "outside" if outside else (tx["source"] if tx else None),
              "source_label": ("Outside this app" + ("" if tx else ", not accepted yet")) if outside
              else auditread.SOURCES.get(tx["source"], tx["source"]) if tx else "",
              "headline": auditread.headline(tx) if tx else "", "late": bool(tx and tx["late"]), "outside": outside})
    return d


def _documents_now(con, ent, month):
    """The files of what the pack would hold now, each checked against its fingerprint taken at upload."""
    owners = [(p["description"], auditpack._docs(con, "payment_id", p["id"])) for p in auditpack._payments(con, ent, month)]
    owners += [(t["title"], auditpack._docs(con, "task_id", t["id"])) for t in auditpack._tasks(con, ent, month)]
    owners += [("Bank statements", [d]) for d in auditpack._statement_docs(con, ent, month)]
    problems, n = [], 0
    for title, docs in owners:
        for d in docs:
            n += 1
            why = "file is missing from the records folder" if not path_of(d).exists() else None if verify(d) else "file changed since upload"
            if why:
                problems.append({"owner": title, "name": d["original_name"], "why": why, "id": d["id"]})
    return {"checked": n, "problems": problems}


FILE_TEXT = {
    "unchanged": "The file is the one built: its fingerprint matches the one recorded when it was built.",
    "changed": "The file has changed since it was built: its fingerprint no longer matches the one recorded then. "
               "Don't give this copy to the auditor. Build the pack again.",
    "missing": "The file is no longer in the audit packs folder. The trail still records that it was built, with its fingerprint.",
    "not_recorded": "Built before the audit trail recorded packs, so there is no fingerprint to check the file against.",
}


def check(con, event=None, ent=None, month=None, name=None):
    """One pack, by its trail row (event) or by company, month and file name: {name, company, month, label, pack (when,
    who, what was printed on its cover and what built it), file {state, text}, changes {total, summary, groups,
    outside, late, packs_since}, documents (its files now), cannot_tell: [what this can't say, in words]}. None when
    there is no such pack."""
    if event is not None:
        rows = _fetch(con, "SELECT * FROM audit_row WHERE id = ? AND tbl = 'pack' AND op = 'event'", (event,))
        if not rows:
            return None
        r = rows[0]
        d = json.loads(r["after"] or "{}")
        found = _fetch(con, "SELECT * FROM entities WHERE id = ?", (r["entity_id"],))
        ent = dict(found[0]) if found else {"id": r["entity_id"], "code": d.get("company") or "", "name": d.get("company") or ""}
        month, name = d.get("month"), _name(r)
    else:
        if not _safe(name):
            return None
        r = next((x for x in reversed(_events(con, ent, month)) if _name(x) == name), None)
        d = json.loads(r["after"] or "{}") if r else {}
    path = _file(d, ent, name)
    if r is None and not path.is_file():
        return None

    # the file against its recorded fingerprint
    if r is None or not d.get("sha256"):
        state = "not_recorded"
    elif not path.is_file():
        state = "missing"
    else:
        state = "unchanged" if audit.file_sha256(path) == d["sha256"] else "changed"

    # where it stands in the trail: its own row, or for a pack built before the trail recorded packs the last row
    # written before its file's time on disk
    cannot = []
    tx = None
    if r is not None:
        after_id, token = r["id"], r["token"]
        tx = _entries(con, [r]).get(r["id"])
        built_at = tx["at"] if tx else r["at"]
    else:
        built_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="milliseconds")
        after_id, token = con.execute("SELECT COALESCE(MAX(id), 0) FROM audit_row WHERE at <= ?", (built_at,)).fetchone()[0], None
        cannot.append(f"It was built before the audit trail recorded packs, so what changed is counted from its file's time on "
                      f"disk ({day_label(built_at[:10])} {built_at[11:16]}), which is only as good as that time."
                      + ("" if after_id else " The trail started after that, so changes made before it started aren't known."))

    groups = _changes(con, ent, month, after_id, token)
    every = [x for rs in groups.values() for x in rs]
    entries = _entries(con, every)
    names = auditread._Names(con)
    out_groups, phrases, total = [], [], 0
    for key, label, phrase in GROUPS:
        rs = groups[key]
        if not rs:
            continue
        out_groups.append({"key": key, "label": label, "count": len(rs), "more": max(0, len(rs) - SHOWN),
                           "rows": [_row_out(x, entries.get(x["id"]), names) for x in rs[:SHOWN]]})
        if phrase:
            total += len(rs)
            phrases.append(f"{len(rs)} {phrase}")
    outside = sum(1 for x in every if not x["token"])
    late = sum(1 for x in every if (entries.get(x["id"]) or {"late": 0})["late"])
    since = len(groups["packs"])
    summary = (f"{total} change{'s' if total != 1 else ''} since it was built: {_listed(phrases)}." if total
               else "Nothing the pack reads has changed since it was built.")
    if since:
        summary += f" A pack for this month has been built {since} more time{'s' if since != 1 else ''} since."

    # what was printed on its cover and what built it: recorded from Phase 7 on; for an older pack the trail entry and
    # check code are worked out (the entry before the pack's own, sealed while the build held the records)
    printed = {"generated": d.get("generated"), "trail_entry": d.get("trail_entry"), "check_code": d.get("check_code"), "worked_out": False}
    if r is not None and "trail_entry" not in d and tx and tx["id"] > 1:
        prev = con.execute("SELECT id, hash FROM audit_tx WHERE id = ?", (tx["id"] - 1,)).fetchone()
        if prev:
            printed.update(trail_entry=prev[0], check_code=prev[1][:8], worked_out=True)
    prog = {k: d.get(k) for k in ("code_commit", "code_files", "python", "fpdf2", "pypdf")}
    now = auditpack.program()
    if not prog["code_files"] and not prog["code_commit"]:
        same = None
        cannot.append("It was built before packs recorded which version of the program built them, so a pack built now "
                      "could differ in wording or layout even with nothing listed here.")
    else:
        # the program's own files decide (they also catch changes not committed); the commit only when they weren't recorded
        code = "code_files" if prog["code_files"] and now["code_files"] else "code_commit"
        moved = (["the program"] if prog[code] != now[code] else []) + [k for k in ("fpdf2", "pypdf", "python") if prog[k] and prog[k] != now[k]]
        same = not moved
        if moved:
            cannot.append(f"{_listed(moved)[0].upper() + _listed(moved)[1:]} {'has' if len(moved) == 1 else 'have'} been updated since "
                          "it was built, so a pack built now could differ in wording or layout even with nothing listed here.")
    today = d.get("today") or (built_at or "")[:10]
    cannot.insert(0, "Whether the PDF would come out differently if built again: this lists changes to what the pack reads, "
                     "not the PDF itself. A change listed may not show in it (a note, say), and a change undone still counts.")
    if today and today != date.today().isoformat():
        cannot.append(f"Statuses such as Past legal deadline were worked out on {day_label(today)}; built today, some could read differently.")
    cannot.append("Changes that reach the pack only indirectly are not listed, such as a recurring payment, SQL entries not "
                  "linked to its payments or checklist items, or book openings.")
    if outside:
        cannot.append(f"{outside} of the changes {'was' if outside == 1 else 'were'} made outside this app. One found by the "
                      "trail check is dated when it was found, which may be after it was made.")
    return {"name": name, "company": ent["code"], "entity_id": ent["id"], "month": month, "label": month_label(month) if month else "",
            "recorded": r is not None,
            "pack": {"event": r["id"] if r is not None else None, "entry": tx["id"] if tx else None, "at": built_at,
                     "actor": tx["actor"] if tx else None, "reason": tx["reason"] if tx else None, "via": d.get("via"),
                     "sha256": d.get("sha256"), "size": d.get("size"), "today": d.get("today"), "printed": printed,
                     "program": prog, "same_program": same},
            "file": {"state": state, "text": FILE_TEXT[state], "exists": path.is_file()},
            "changes": {"total": total, "summary": summary, "groups": out_groups, "outside": outside, "late": late,
                        "packs_since": since},
            "documents": _documents_now(con, ent, month) if month else {"checked": 0, "problems": []},
            "cannot_tell": cannot}
