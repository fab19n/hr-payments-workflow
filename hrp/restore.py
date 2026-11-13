"""Putting back a deleted Setup record (owner decision 2, 13 Nov 2026).

A record deleted in Setup leaves its whole row in the audit trail (the delete's before image), and the rows deleted with
it share that delete's entry: a payment type's sets of required documents, a checklist item's or reminder's wordings, a
company's own checklist and sets. Put it back inserts them again as they were:
- with the same id when it is free, else a new one (ids are reused, so a record added since may hold it); the rows
  deleted with it follow it to its new id. So a put back is chosen by the trail row of the delete, never by the key,
  which a record added since may have taken;
- only from a delete made in this app (an entry the app sealed), not a change made outside it, a baseline or an update
  step's;
- refused, with a plain reason, when its code or key is taken now, when its company or another record it names is gone,
  or when it was put back already. The checks are the ones Setup makes when a record is added;
- keeping what the app relies on: a company has one cash book, so a cash book put back after another account took over
  comes back as not the cash book, and says so; a recurring payment is brought into the months set up as one added is;
  a checklist item or reminder is brought into the open months, never a filed one (the change is refused instead).
Columns added since the delete take their defaults: the before image is matched with the table's columns as they are
now. The change is audited like any other, with the request's reason, and an event in the same entry links the record
to the delete it came from ("Put back from entry N"): the record's History shows it, and it is how a delete already put
back is known. plan() makes every check without writing (the lists of deleted records use it to say why one can't be
put back); put_back() writes. A preview runs put_back and undoes it (app._setup_call)."""
import contextvars
import json
import sqlite3

from . import audit, auditread, checklistbook, db, masters, monthly, rulebook
from .masters import Refused

APP_SOURCES = ("user", "auto", "import")  # entries the app sealed for a request (not outside, an update step or a seed)
# The tables whose deleted records can be put back, and the Setup section each is listed in.
KINDS = {"entities": "entities", "accounts": "accounts", "payment_types": "payment_types", "doc_types": "doc_types",
         "guess_words": "guess_words", "hint_words": "hint_words", "filing_words": "filing_words", "parties": "parties",
         "gl_accounts": "gl_accounts", "checklist_items": "checklist", "people_tasks": "reminders", "payees": "payees"}
TABLE_OF = {kind: tbl for tbl, kind in KINDS.items()}
PER_ENTITY = ("accounts", "parties", "gl_accounts", "checklist_items", "payees")
LISTED = 200  # deleted records listed at most per section (the newest)


def _columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def _has_table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _one(con, sql, args=()):
    return con.execute(sql, args).fetchone() is not None


def _deleted_with(con, token, table, col, value):
    """The before images of the rows of table deleted in the same entry whose col is value, in the order deleted."""
    if not _has_table(con, table):
        return []
    rows = con.execute(f"""SELECT before FROM audit_row WHERE token = ? AND tbl = ? AND op = 'delete'
                           AND json_extract(before, '$.{col}') = ? ORDER BY id""", (token, table, value)).fetchall()
    return [json.loads(r[0]) for r in rows]


def put_back_in(con, row_ids):
    """{delete row id: the entry that put it back (None while that entry isn't saved yet)} for those already put back."""
    out = {}
    ids = [int(i) for i in row_ids]
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for rid, tx in con.execute(f"""SELECT CAST(json_extract(r.after, '$.from_row') AS INTEGER), t.id
                                       FROM audit_row r LEFT JOIN audit_tx t ON t.token = r.token
                                       WHERE r.tbl = 'restore' AND r.op = 'event'
                                       AND CAST(json_extract(r.after, '$.from_row') AS INTEGER) IN ({', '.join('?' * len(part))})""",
                                   part):
            out[rid] = tx
    return out


def _with_parent(con, r, img):
    """A company's own checklist item deleted with the company: it comes back with the company, not on its own."""
    return r["tbl"] == "checklist_items" and img.get("entity_id") is not None and _one(
        con, "SELECT 1 FROM audit_row WHERE token = ? AND tbl = 'entities' AND op = 'delete' AND row_key = ?",
        (r["token"], str(img["entity_id"])))


def _link(con, tbl, key, before_row):
    """One link of the chain of deletes of tbl at id key, newest first: (the newest delete before the trail row
    before_row, the delete the record there after it was put back from when that is a delete of tbl at key too, else
    None); (None, None) when there is no such delete. It doesn't depend on which record is asked about (see _same)."""
    upto, cap = ("", ()) if before_row is None else (" AND id < ?", (before_row,))
    last = con.execute(f"""SELECT MAX(id) FROM audit_row WHERE tbl = ? AND row_key = ? AND op = 'delete'{upto}""",
                       (tbl, str(key), *cap)).fetchone()[0]
    if last is None:
        return None, None
    ev = con.execute(f"""SELECT CAST(json_extract(after, '$.from_row') AS INTEGER) FROM audit_row
                         WHERE tbl = 'restore' AND op = 'event' AND row_key = ? AND id > ?{upto}
                         ORDER BY id DESC LIMIT 1""", (f"{tbl}:{key}", last, *cap)).fetchone()
    if not ev or ev[0] is None:
        return last, None
    src = con.execute("SELECT tbl, row_key FROM audit_row WHERE id = ? AND op = 'delete'", (ev[0],)).fetchone()
    return last, (ev[0] if src and src["tbl"] == tbl and src["row_key"] == str(key) else None)


# The chains of deletes worked out so far, {(tbl, key): [links]}, while deleted() lists a section: each row asks about
# the same few ids, so each chain is read once per list, not once per row. None outside deleted().
_CHAINS = contextvars.ContextVar("restore_chains", default=None)


def _same(con, tbl, key, after_row):
    """Whether the record of tbl at id key now is the one that was there when the trail row after_row was written. Ids
    are reused, so a record there now may be another one: once that id was deleted after after_row, only a put back of
    that same record under that same id brings it back; anything else that took the id since is another record. Walks
    the deletes of that id newest first, each put back from the one before it, without recursion."""
    memo = _CHAINS.get()
    links = [] if memo is None else memo.setdefault((tbl, str(key)), [])
    i, before_row = 0, None
    while True:
        if i == len(links):
            links.append(_link(con, tbl, key, before_row))
        last, src = links[i]
        if last is None or last <= after_row:
            return True
        if src is None or src <= after_row:
            return False
        before_row, i = src, i + 1  # ends: after_row < src <= last < before_row


def _moved_to(con, tbl, key, after_row):
    """The id the record of tbl at id key (as it was at the trail row after_row) moved to, when it was deleted since and
    put back under another id (whether or not it has been deleted again there); else None. Follows each delete of it
    to the put back that brought it back. Where a walk from a delete ends is the same for every row that reaches it, so
    while a list is drawn (deleted()) it is kept and read once."""
    memo = _CHAINS.get()
    first = key = str(key)
    at, path = after_row, []
    while True:
        d = con.execute("SELECT MIN(id) FROM audit_row WHERE tbl = ? AND row_key = ? AND op = 'delete' AND id > ?",
                        (tbl, key, at)).fetchone()[0]
        if d is None:
            end = key
            break
        if memo is not None and ("moved", tbl, d) in memo:
            end = memo[("moved", tbl, d)]
            break
        path.append(d)
        ev = con.execute("""SELECT id, row_key FROM audit_row WHERE tbl = 'restore' AND op = 'event'
                            AND CAST(json_extract(after, '$.from_row') AS INTEGER) = ? ORDER BY id LIMIT 1""", (d,)).fetchone()
        if not ev:
            end = key  # deleted and not put back (after a move, still where it moved to: it can't follow either way)
            break
        key, at = ev["row_key"].split(":", 1)[1], ev["id"]
    if memo is not None:
        for d in path:
            memo[("moved", tbl, d)] = end
    return None if end == first else int(end)


def _still(con, tbl, key, after_row):
    """Whether the record of tbl with id key a delete at trail row after_row names is still there: the same record, not
    one that took its id since (see _same)."""
    return _one(con, f"SELECT 1 FROM {tbl} WHERE id = ?", (key,)) and _same(con, tbl, key, after_row)


def _company(con, eid, what, after_row):
    e = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone() if eid is not None else None
    if not e or not _same(con, "entities", eid, after_row):
        new = _moved_to(con, "entities", eid, after_row) if eid is not None else None
        if new is not None:
            raise Refused(f"Its company was put back as a new record (#{new}), so the {what} can't follow it. Add it again there.", 409)
        raise Refused(f"Its company has been deleted since, so the {what} can't be put back. Put the company back first.", 409)
    return dict(e)


def _gone(con, tbl, key, after_row, gone, moved):
    """Refuses when the record of tbl at key a delete at trail row after_row names isn't there now: moved (with the new
    id) when it was put back under another id, else gone ("... Put that back first.")."""
    if _still(con, tbl, key, after_row):
        return
    new = _moved_to(con, tbl, key, after_row)
    raise Refused(moved.format(new=new) if new is not None else gone, 409)


def _type_gone(con, key):
    return not _one(con, "SELECT 1 FROM payment_types WHERE key = ?", (key,))


def _docs_gone(con, docs):
    return [d for d in docs if not _one(con, "SELECT 1 FROM doc_types WHERE key = ?", (d,))]


def _docs_stopped(con, docs):
    """The document types named that are there but stopped (Setup refuses stopping one asked for in a month not filed)."""
    return [d for d in docs if _one(con, "SELECT 1 FROM doc_types WHERE key = ? AND active = 0", (d,))]


def _term_problem(con, t, entity_id=None, coming=False):
    """Why a checklist item's or reminder's wording can't come back: a document type or payment type it names is gone,
    or, when it is in use and reaches a month not filed, a document type it asks for is stopped (as Setup refuses
    stopping one the checklist asks for: masters._checklist_docs). entity_id: its company (None for a reminder);
    coming: that company comes back with it, so has no month filed."""
    rule = json.loads(t["rule"]) if t.get("rule") else {}
    docs = list(dict.fromkeys(json.loads(t.get("docs") or "[]") + list(rule.get("docs") or []) + list(rule.get("on_item") or [])))
    gone = _docs_gone(con, docs)
    if gone:
        return f"it asks for {', '.join(gone)}, a document type deleted since. Put that back first."
    gone = [c for c in rule.get("categories") or [] if _type_gone(con, c)]
    if gone:
        return f"its payments rule names {', '.join(gone)}, a payment type deleted since. Put that back first."
    stopped = _docs_stopped(con, docs)
    if stopped and t.get("in_use", 1) and (coming or masters._reaches_open(
            con, {"entity_id": entity_id, "to_month": t.get("to_month")})):
        return f"it asks for {', '.join(stopped)}, a document type stopped since. Use it again first."
    return None


def _sets(con, sets, notes, after_row, entity=None, ptype=None):
    """The sets of required documents that can come back: their payment type, documents and company still there (or
    coming back with them: entity, ptype), and, for a set in force for a month not filed, no document type stopped
    since. The others are left out, and a note says so. after_row: the trail row of the delete being put back."""
    out = []
    for s in sets:
        eid = s.get("entity_id")
        docs = json.loads(s.get("docs") or "[]")
        gone = _docs_gone(con, docs)
        stopped = _docs_stopped(con, docs)
        if s["payment_type"] != ptype and _type_gone(con, s["payment_type"]):
            notes.append(f"The required documents from {db.month_label(s['from_month'])} are left out: their payment type "
                         f"{s['payment_type']} has been deleted since.")
        elif eid is not None and eid != entity and not _still(con, "entities", eid, after_row):
            notes.append(f"A company's own required documents from {db.month_label(s['from_month'])} are left out: that "
                         "company has been deleted since.")
        elif gone:
            notes.append(f"The required documents from {db.month_label(s['from_month'])} are left out: they name "
                         f"{', '.join(gone)}, a document type deleted since.")
        elif stopped and (eid is not None and eid == entity or masters._reaches_open(con, s)):
            notes.append(f"The required documents from {db.month_label(s['from_month'])} are left out: they name "
                         f"{', '.join(stopped)}, a document type stopped since.")
        else:
            out.append(s)
    return out


def _row(con, row_id):
    r = con.execute("SELECT * FROM audit_row WHERE id = ?", (row_id,)).fetchone()
    if not r or r["op"] != "delete" or r["tbl"] not in KINDS or not r["before"]:
        raise Refused("Only a deleted Setup record can be put back.", 404)
    tx = con.execute("SELECT * FROM audit_tx WHERE token = ?", (r["token"],)).fetchone() if r["token"] else None
    if not tx or tx["source"] not in APP_SOURCES:
        raise Refused("Only a record deleted in this app can be put back; this delete was made outside it.", 409)
    return r, tx


def plan(con, row_id):
    """Everything put_back needs, checked, without writing: {row, tx, table, kind, img, keep_id, children, notes}.
    Raises Refused with the reason it can't be put back. Setup's own checks (a code taken, a parent account missing)
    say a value is wrong (400); here nothing was typed, the records changed since, so they come back as 409."""
    try:
        return _plan(con, row_id)
    except Refused as x:
        if x.status == 400:
            x.status = 409
        raise


def _plan(con, row_id):
    r, tx = _row(con, row_id)
    tbl = r["tbl"]
    if not _has_table(con, tbl):
        raise Refused("These records can be put back once the records are updated.", 409)
    done = put_back_in(con, [r["id"]])
    if r["id"] in done:
        entry = done[r["id"]]
        raise Refused(f"This was put back already{f' (entry {entry})' if entry else ''}.", 409)
    img = json.loads(r["before"])
    if _with_parent(con, r, img):
        raise Refused("It was deleted with its company: put the company back to bring it back.", 409)
    label = auditread._label(tbl).lower()
    p = {"row": dict(r), "tx": dict(tx), "table": tbl, "kind": KINDS[tbl], "img": img, "children": {}, "notes": [],
         "keep_id": not _one(con, f"SELECT 1 FROM {tbl} WHERE id = ?", (img.get("id"),))}
    if not p["keep_id"]:
        p["notes"].append(f"Its number (#{img.get('id')}) has been given to another {label} since, so it comes back with a new "
                          "one. Its history before the delete stays under the old number.")
    if tbl == "entities":
        masters._unique_code(con, img["code"])
        masters._shared_codes(con, None, img.get("sql_database"))
        items = []
        for it in _deleted_with(con, r["token"], "checklist_items", "entity_id", img["id"]):
            terms = _deleted_with(con, r["token"], "checklist_terms", "item_id", it["id"])
            for t in terms:
                why = _term_problem(con, t, img["id"], coming=True)
                if why:
                    raise Refused(f"Its checklist item {it.get('name') or it['code']} can't come back: {why}", 409)
            items.append((it, terms))
        p["children"]["checklist_items"] = items
        p["children"]["required_sets"] = _sets(con, _deleted_with(con, r["token"], "required_sets", "entity_id", img["id"]),
                                               p["notes"], r["id"], entity=img["id"])
    elif tbl == "accounts":
        _company(con, img["entity_id"], "bank account", r["id"])
        if img.get("cash_book"):
            other = con.execute("SELECT label FROM accounts WHERE entity_id = ? AND cash_book = 1 AND active = 1",
                                (img["entity_id"],)).fetchone()
            if other:
                p["img"] = {**img, "cash_book": 0}
                p["notes"].append(f"It was the company's cash book account. {other[0]} is the cash book now, so this one comes "
                                  "back as not the cash book. Make it the cash book again in its drawer if it should be.")
        elif img.get("currency") == masters.BASE and img.get("active", 1) and not _one(
                con, "SELECT 1 FROM accounts WHERE entity_id = ? AND cash_book = 1 AND active = 1", (img["entity_id"],)):
            p["img"] = {**img, "cash_book": 1}
            p["notes"].append("The company has no cash book account now, so this one becomes its cash book, as a company's "
                              f"first account in {masters.BASE} does.")
    elif tbl in ("payment_types", "doc_types"):
        if _one(con, f"SELECT 1 FROM {tbl} WHERE key = ?", (img["key"],)):
            raise Refused(f"There is a {label} with the key {img['key']} now, so this one can't be put back.", 409)
        if tbl == "payment_types":
            p["children"]["required_sets"] = _sets(
                con, _deleted_with(con, r["token"], "required_sets", "payment_type", img["key"]), p["notes"], r["id"],
                ptype=img["key"])
    elif tbl in masters.WORD_KINDS:
        if tbl != "filing_words" and _type_gone(con, img["payment_type"]):
            raise Refused(f"Its payment type {img['payment_type']} has been deleted since. Put that back first.", 409)
        if tbl == "filing_words":
            if not _one(con, "SELECT 1 FROM checklist_items WHERE code = ?", (img["checklist_code"],)):
                raise Refused(f"No company's checklist has the item {img['checklist_code']} now, so these words can't be put back.", 409)
            if img.get("party_id") is not None:
                _gone(con, "parties", img["party_id"], r["id"],
                      "The customer or supplier it names has been deleted since. Put that back first.",
                      "The customer or supplier it names was put back as a new record (#{new}), so these words can't follow "
                      "it. Add them again there.")
                if not _one(con, "SELECT 1 FROM parties WHERE id = ? AND active = 1", (img["party_id"],)):
                    raise Refused("The customer or supplier it names is stopped now. Use it again first.", 409)
            masters._word_check(con, tbl, img)  # as a word rule added is checked
    elif tbl == "parties":
        if img.get("entity_id") is not None:
            _company(con, img["entity_id"], "customer or supplier", r["id"])
        masters._party_check(con, {"entity_id": img.get("entity_id"), "sql_code": img.get("sql_code")})
    elif tbl == "gl_accounts":
        _company(con, img["entity_id"], "GL account", r["id"])
        masters._gl_check(con, img["entity_id"], {k: img[k] for k in ("code", "parent_code", "sql_type", "type") if img.get(k) is not None})
    elif tbl == "checklist_items":
        ent = _company(con, img["entity_id"], "checklist item", r["id"])
        if _one(con, "SELECT 1 FROM checklist_items WHERE entity_id = ? AND code = ?", (img["entity_id"], img["code"])):
            raise Refused(f"{ent['code']}'s checklist has an item with the code {img['code']} now, so this one can't be put back.", 409)
        terms = _deleted_with(con, r["token"], "checklist_terms", "item_id", img["id"])
        for t in terms:
            why = _term_problem(con, t, ent["id"])
            if why:
                raise Refused(f"It can't be put back: {why}", 409)
        m = masters._first_open(con, ent["id"])
        live = next((t for t in terms if t["in_use"] and checklistbook._live(t, m)), None)
        if live and any(x["title"].strip().lower() == live["title"].strip().lower()
                        for x in checklistbook.get(con).checklist(ent, m)):
            raise Refused(f"Another item in use is called {live['title']} now, so this one can't be put back.", 409)
        p["children"]["checklist_terms"] = terms
    elif tbl == "people_tasks":
        if _one(con, "SELECT 1 FROM people_tasks WHERE key = ?", (img["key"],)):
            raise Refused(f"There is a reminder with the key {img['key']} now, so this one can't be put back.", 409)
        terms = _deleted_with(con, r["token"], "people_task_terms", "people_task_id", img["id"])
        for t in terms:
            why = _term_problem(con, t)
            if why:
                raise Refused(f"It can't be put back: {why}", 409)
        p["children"]["people_task_terms"] = terms
    elif tbl == "payees":
        ent = _company(con, img["entity_id"], "recurring payment", r["id"])
        if _type_gone(con, img["category"]):
            raise Refused(f"Its payment type {img['category']} has been deleted since. Put that back first.", 409)
        if img.get("account_id") is not None:
            _gone(con, "accounts", img["account_id"], r["id"],
                  "The bank account it was paid from has been deleted since. Put that back first.",
                  "The bank account it was paid from was put back as a new record (#{new}), so the recurring payment can't "
                  "follow it. Add it again there.")
            if img.get("active", 1) and not _one(con, "SELECT 1 FROM accounts WHERE id = ? AND active = 1", (img["account_id"],)):
                # as Setup refuses stopping an account a recurring payment in use is paid from (masters.set_active)
                raise Refused("The bank account it was paid from is stopped now. Use it again first.", 409)
        if img.get("party_id") is not None:
            _gone(con, "parties", img["party_id"], r["id"],
                  "The supplier or customer it was linked to has been deleted since. Put that back first.",
                  "The supplier or customer it was linked to was put back as a new record (#{new}), so the recurring "
                  "payment can't follow it. Add it again there.")
        fields = {k: img[k] for k in ("name", "category", "account_id", "due_day", "month_offset", "amount", "amount_varies",
                                      "active", "start_date", "end_date", "party_id") if k in img}
        masters.payee_check(con, ent, fields, old=img)
    return p


def _insert(con, table, img, keep_id=True):
    """Inserts a row from its before image: the columns the table has now (one added since takes its default), with the
    same id when keep_id and it is free. Returns the id."""
    vals = {c: img[c] for c in _columns(con, table) if c in img}
    if "id" in vals and (not keep_id or _one(con, f"SELECT 1 FROM {table} WHERE id = ?", (vals["id"],))):
        del vals["id"]
    return con.execute(f"INSERT INTO {table} ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values())).lastrowid


def put_back(con, row_id):
    """Puts back the record a delete row removed (see the module's notes). Returns {kind, table, label, name, id, same_id,
    notes, lines, affected, deleted}; raises Refused."""
    p = plan(con, row_id)
    tbl, img, kids, r, tx = p["table"], p["img"], p["children"], p["row"], p["tx"]
    name = auditread._record_name(img, r["row_key"])
    label = auditread._label(tbl)
    lines, affected, put = [], {"tasks": 0, "payments": 0, "now_missing": 0, "now_complete": 0}, {}
    try:
        new_id = _insert(con, tbl, img, p["keep_id"])
        if tbl == "entities":
            for it, terms in kids["checklist_items"]:
                iid = _insert(con, "checklist_items", {**it, "entity_id": new_id})
                for t in terms:
                    _insert(con, "checklist_terms", {**t, "item_id": iid})
                put["checklist_terms"] = put.get("checklist_terms", 0) + len(terms)
            put["checklist_items"] = len(kids["checklist_items"])
            for s in kids["required_sets"]:
                _insert(con, "required_sets", {**s, "entity_id": new_id})
            put["required_sets"] = len(kids["required_sets"])
        elif tbl == "payment_types":
            for s in kids["required_sets"]:
                _insert(con, "required_sets", s)
            put["required_sets"] = len(kids["required_sets"])
        elif tbl == "checklist_items":
            for t in kids["checklist_terms"]:
                _insert(con, "checklist_terms", {**t, "item_id": new_id})
            put["checklist_terms"] = len(kids["checklist_terms"])
        elif tbl == "people_tasks":
            for t in kids["people_task_terms"]:
                _insert(con, "people_task_terms", {**t, "people_task_id": new_id})
            put["people_task_terms"] = len(kids["people_task_terms"])
        elif tbl == "accounts" and img.get("cash_book"):
            masters._only_cash_book(con, img["entity_id"], new_id)
        rulebook.forget(con)
        checklistbook.forget(con)
        if tbl == "checklist_items":
            lines, affected = _checklist_into_months(con, img, new_id)
        elif tbl == "people_tasks":
            lines, affected = _reminders_into_months(con)
        elif tbl == "payees":
            new = con.execute("SELECT * FROM payees WHERE id = ?", (new_id,)).fetchone()
            changes, kept = db.sync_payee(con, None, new)
            changes += db.sync_reminders(con, new)
            lines = changes + kept
            affected["payments"] = con.execute("SELECT COUNT(*) FROM payments WHERE payee_id = ?", (new_id,)).fetchone()[0]
            affected["tasks"] = con.execute("SELECT COUNT(*) FROM tasks WHERE code GLOB ? OR code GLOB ?",
                                            (f"joiner-*-{new_id}", f"leaver-*-{new_id}")).fetchone()[0]
    except sqlite3.IntegrityError as x:
        raise Refused(f"It can't be put back as it was: the records refuse it now ({x}).", 409)
    eid = new_id if tbl == "entities" else img.get("entity_id")
    audit.event(con, "restore", f"{tbl}:{new_id}", {
        "record": f"{label} {name}", "table": tbl, "key": r["row_key"], "as_key": str(new_id), "from_entry": tx["id"], "from_row": r["id"],
        "deleted_at": tx["at"], "with": {auditread._label(t, n): n for t, n in put.items() if n}}, entity_id=eid)
    db.log(con, f"Put back {label.lower()} {name} (deleted in entry {tx['id']})"
           + ("" if p["keep_id"] else f", as #{new_id}"))
    rulebook.forget(con)
    checklistbook.forget(con)
    return {"ok": True, "kind": p["kind"], "table": tbl, "label": label, "name": name, "id": new_id, "same_id": p["keep_id"],
            "notes": p["notes"], "lines": lines, "affected": affected,
            "deleted": {"entry": tx["id"], "at": tx["at"], "actor": tx["actor"], "reason": tx["reason"], "key": r["row_key"]}}


def _checklist_into_months(con, img, new_id):
    """A checklist item put back, brought into its company's months set up and not filed (filed ones never change)."""
    ent = dict(con.execute("SELECT * FROM entities WHERE id = ?", (img["entity_id"],)).fetchone())
    m = con.execute("SELECT MIN(month) FROM months WHERE entity_id = ? AND closed_at IS NULL", (ent["id"],)).fetchone()[0]
    if not m:
        return [], {"tasks": 0, "payments": 0, "now_missing": 0, "now_complete": 0}
    before_filed = monthly._filed_tasks(con, ent["id"])
    before = masters._statuses(con, ent["id"], m)
    lines, n = monthly._bring_into_line(con, ent, img["code"], m)
    for x in lines:
        db.log(con, f"Checklist {ent['code']} in {x}")
    monthly._keep_filed(con, before_filed, ent["id"])
    checklistbook.forget(con)
    after = masters._statuses(con, ent["id"], m)
    moved = [pid for pid in after if after[pid] != before.get(pid)]
    return lines, {"tasks": n, "payments": len(moved), "now_missing": sum(before.get(q) == "complete" for q in moved),
                   "now_complete": sum(after[q] == "complete" for q in moved)}


def _reminders_into_months(con):
    """A reminder put back, brought into the months set up for every person with a start date or last day (as a
    reminder added is); one in a filed month is never added or changed."""
    before_filed = monthly._filed_tasks(con)
    lines, n = [], 0
    for payee in con.execute("SELECT * FROM payees WHERE start_date IS NOT NULL OR end_date IS NOT NULL ORDER BY entity_id, sort, id").fetchall():
        for x in db.sync_reminders(con, payee):
            lines.append(f"{payee['name']}: {x}")
            n += 1
    monthly._keep_filed(con, before_filed)
    return lines, {"tasks": n, "payments": 0, "now_missing": 0, "now_complete": 0}


def deleted(con, kind, entity_id=None):
    """The records of a Setup section deleted in this app and not put back since, newest first, each with when, who and
    why it was deleted and, when it can't be put back now, why: {label, plural, rows: [...]}. A company's own checklist
    deleted with the company is left out (it comes back with the company)."""
    tbl = TABLE_OF.get(kind)
    if not tbl:
        raise Refused("There is no such kind of record.", 404)
    if tbl in PER_ENTITY and entity_id is None:
        raise Refused("Choose a company.")
    rows = con.execute(f"""SELECT r.*, t.id AS tx_id, t.at AS tx_at, t.actor, t.reason FROM audit_row r
                           JOIN audit_tx t ON t.token = r.token
                           WHERE r.tbl = ? AND r.op = 'delete' AND t.source IN ({', '.join('?' * len(APP_SOURCES))})
                           ORDER BY r.id DESC""", (tbl, *APP_SOURCES)).fetchall()
    done = put_back_in(con, [r["id"] for r in rows])
    chains = _CHAINS.set({})  # nothing is written while listing, so a chain read once holds for the whole list
    try:
        out = _listed(con, tbl, rows, done, entity_id)
    finally:
        _CHAINS.reset(chains)
    return {"kind": kind, "table": tbl, "label": auditread._label(tbl), "plural": auditread._label(tbl, 2), "rows": out}


def _listed(con, tbl, rows, done, entity_id):
    out = []
    for r in rows:
        if r["id"] in done or not r["before"]:
            continue
        img = json.loads(r["before"])
        if tbl in PER_ENTITY:
            # a record of a company deleted since is never this company's, even when this company took its id since
            mine = (img.get("entity_id") == entity_id and _same(con, "entities", entity_id, r["id"])) or (
                tbl == "parties" and img.get("entity_id") is None)
            if not mine:
                continue
        if _with_parent(con, r, img):
            continue
        try:
            plan(con, r["id"])
            problem = None
        except Refused as x:
            problem = str(x)
        out.append({"row_id": r["id"], "entry": r["tx_id"], "at": r["tx_at"], "actor": r["actor"], "reason": r["reason"],
                    "table": tbl, "key": r["row_key"], "name": auditread._record_name(img, r["row_key"]),
                    "entity_id": img.get("entity_id"), "problem": problem})
        if len(out) >= LISTED:
            break
    return out


def mark(con, changes):
    """Marks each change that is a delete of a record that could be put back: put_back True while it can be tried, or
    put_back_in the entry that put it back. For the audit trail's entries and a record's history."""
    dels = [ch for ch in changes if ch.get("op") == "delete" and ch.get("table") in KINDS]
    done = put_back_in(con, [ch["id"] for ch in dels])
    for ch in dels:
        if ch["id"] in done:
            ch["put_back_in"] = done[ch["id"]]
            continue
        r = con.execute("""SELECT r.*, t.source FROM audit_row r LEFT JOIN audit_tx t ON t.token = r.token
                           WHERE r.id = ?""", (ch["id"],)).fetchone()
        ch["put_back"] = bool(r and r["source"] in APP_SOURCES and r["before"] and _has_table(con, r["tbl"])
                              and not _with_parent(con, r, json.loads(r["before"])))
    return changes
