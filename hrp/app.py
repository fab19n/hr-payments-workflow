"""Local web app. Listens on 127.0.0.1 only, so nothing outside this PC can reach it."""
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path, PureWindowsPath

import pyzipper
from flask import Flask, abort, g, jsonify, make_response, request, send_file

from . import auditpack, config, budget as stored, db, nextup, reports, rules, sqlimport, statements
from .config import BACKUP_DIR, DATA_DIR, DB_PATH, EXPORTS_DIR, PACKS_DIR, SETTINGS, PROGRAM_DIR
from .docstore import path_of, store, verify

app = Flask(__name__, static_folder=str(PROGRAM_DIR / "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
app.json.sort_keys = False  # lists such as the payment types keep the order in rules.py

ALLOWED_HOSTS = {f"127.0.0.1:{SETTINGS['port']}", f"localhost:{SETTINGS['port']}"}


@app.before_request
def guard():
    # Blocks other websites open in the same browser from reaching this app (DNS rebinding / cross-site posts).
    if request.host not in ALLOWED_HOSTS:
        abort(403)
    if request.method not in ("GET", "HEAD") and request.headers.get("X-HRP") != "1":
        abort(403)


@app.after_request
def headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                               "frame-src 'self'; object-src 'self'; frame-ancestors 'none'")
    return resp


def con():
    # One connection per request, closed afterwards; an open connection keeps records.db locked on Windows.
    if "con" not in g:
        g.con = db.connect()
        if request.method in ("GET", "HEAD"):
            # Looking at a page never changes the records, so another website can't make it do so through a link.
            g.con.execute("PRAGMA query_only = ON")
    return g.con


@app.teardown_appcontext
def close_con(_exc):
    c = g.pop("con", None)
    if c is not None:
        c.close()


def rows(cur):
    return [dict(r) for r in cur]


def err(msg, code=400):
    return jsonify({"error": msg}), code


MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])", re.ASCII)


def month_from(value):
    """A month taken from a request, e.g. 2026-10; anything else is refused before it reaches the records."""
    if not isinstance(value, str) or not MONTH.fullmatch(value):
        abort(make_response(*err("That isn't a month. Months are written like 2026-10.")))
    return value


DAY = re.compile(r"[2-9]\d{3}-\d{2}-\d{2}", re.ASCII)  # from the year 2000 on, as the Budget page's date box allows


def iso_day(value):
    """value when it is a date written like 2026-10-20, else None."""
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) and DAY.fullmatch(value) else None
    except ValueError:
        return None


def day_from(value):
    """A date taken from a request, e.g. 2026-10-20, or today when none is given; anything else is refused."""
    if not value:
        return date.today().isoformat()
    return iso_day(value) or abort(make_response(*err("That isn't a date. Dates are written like 2026-10-20.")))


def id_from(value):
    """An id taken from a request; anything else is refused before it reaches the records."""
    try:
        return int(value)
    except ValueError:
        abort(make_response(*err("That isn't a company.")))


def entity(c, eid):
    e = c.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    if not e:
        abort(404)
    return e


@app.get("/")
def index():
    return send_file(PROGRAM_DIR / "static" / "index.html")


@app.get("/api/meta")
def meta():
    c = con()
    ents = rows(c.execute("SELECT * FROM entities ORDER BY id"))
    for e in ents:
        e["accounts"] = rows(c.execute("SELECT * FROM accounts WHERE entity_id = ?", (e["id"],)))
    return jsonify({
        "entities": ents, "doc_types": rules.DOC_TYPES, "categories": rules.CATEGORIES,
        "required": {k: rules.REQUIRED_DOCS[k] for k in rules.REQUIRED_DOCS}, "sql_only": sorted(rules.SQL_ONLY),
        "data_dir": str(DATA_DIR), "backup_dir": SETTINGS.get("backup_dir") or "",
    })


def docs_for(c, field, ident):
    out = rows(c.execute(f"""SELECT * FROM documents WHERE {field} = ? AND replaced_by IS NULL AND removed_at IS NULL
                             ORDER BY uploaded_at""", (ident,)))
    for d in out:
        d["label"] = rules.DOC_TYPES.get(d["doc_type"], d["doc_type"])
    return out


@app.get("/api/month")
def month_view():
    eid, month = int(request.args["entity"]), month_from(request.args.get("month"))
    c = con()
    e = entity(c, eid)
    today = date.today().isoformat()
    tasks = rows(c.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY due_date, sort", (eid, month)))
    for t in tasks:
        t["evidence"] = db.evidence(c, task=t)
        t.update(db.task_status(c, e, t, t["evidence"]))
        t["required_docs"] = json.loads(t["required_docs"])
        t["documents"] = docs_for(c, "task_id", t["id"])
        t["sql_docs"] = _taken_back(c, rows(c.execute(
            """SELECT id, entity_id, doc_no, doc_type, amount, einvoice, einvoice_status, einvoice_link FROM sql_entries
               WHERE task_id = ? ORDER BY doc_date""", (t["id"],))))
        t["not_counted"] = db.not_counted(c, task=t)
        t["flag"] = db.task_flag(c, e, t, today, t["done"])
    pays = rows(c.execute(
        """SELECT p.*, a.label AS account_label, py.bank_details, py.reference AS payee_ref
           FROM payments p LEFT JOIN accounts a ON a.id = p.account_id LEFT JOIN payees py ON py.id = p.payee_id
           WHERE p.entity_id = ? AND p.month = ? ORDER BY p.due_date, p.id""", (eid, month)))
    for p in pays:
        p["evidence"] = db.evidence(c, pay=p)
        p["status"], p["missing"] = db.payment_status(c, p, e["uses_sql"], p["evidence"])
        p["not_counted"] = db.not_counted(c, pay=p)
        p["flag"] = db.payment_flag(c, e, p, today)
        p["documents"] = docs_for(c, "payment_id", p["id"])
        p["required"] = rules.required_docs(p["category"], e["uses_sql"])
        p["bank_lines"] = rows(c.execute("SELECT id, txn_date, amount, description FROM statement_lines WHERE payment_id = ?", (p["id"],)))
        p["bank_total"] = db.linked_total(c, p)
        p["sql_entries"] = rows(c.execute(
            "SELECT id, doc_no, doc_date, amount, direction, kind FROM sql_entries WHERE payment_id = ? ORDER BY doc_date, id", (p["id"],)))
        p["not_in_sql"] = db.not_in_sql(e, p)
    return jsonify({"entity": dict(e), "month": month, "label": db.month_label(month), "tasks": tasks, "payments": pays,
                    "set_up": _set_up(c, eid, month), "before_first": db.before_tracking(e, month),
                    "closed_at": db.closed_at(c, eid, month)})


def _taken_back(c, docs):
    """Marks each SQL document whose e-Invoice a refund or credit note takes back (db.taken_back_by), so no screen
    calls that e-Invoice validated."""
    for x in docs:
        x["taken_back_by"] = db.taken_back_by(c, x)
    return docs


def _set_up(c, eid, month):
    return bool(c.execute("SELECT 1 FROM months WHERE entity_id = ? AND month = ?", (eid, month)).fetchone())


def _budget(c, eid, month, as_at):
    """A month's payments out, split at the date the bank balance was taken (as_at): what is still to be paid from that
    balance (to_pay, part paid ones with only the rest, due what that is the rest of, and estimate set while the lines
    linked so far fall short of one), with its total per currency, and what was paid by then and so is already out of
    it. Money received is left out."""
    to_pay, paid, totals = [], [], {}
    for p in c.execute(
            """SELECT p.*, py.bank_details FROM payments p LEFT JOIN payees py ON py.id = p.payee_id
               WHERE p.entity_id = ? AND p.month = ? AND p.direction = 'out' ORDER BY p.due_date, p.id""", (eid, month)):
        left = db.still_to_pay(c, p, as_at)
        row = {k: p[k] for k in ("id", "description", "amount", "currency", "amount_is_estimate", "due_date", "paid_date",
                                 "bank_details")}
        if left == 0 and p["paid_date"]:
            paid.append(row)
        else:
            found = db.linked_total(c, p)
            to_pay.append({**row, "to_pay": left, "due": db.budgeted_at(c, p, found), "estimate": db.open_estimate(c, p, found)})
            totals[p["currency"]] = round(totals.get(p["currency"], 0) + (left or 0), 2)
    return to_pay, paid, totals


@app.get("/api/budget")
def budget():
    """The month's stored budget when it has one (as at the date asked for, else the one kept with it), else the list worked
    out from its payments, which can be set up (POST /api/budget/setup)."""
    eid, month = int(request.args["entity"]), month_from(request.args.get("month"))
    c = con()
    e = entity(c, eid)
    hdr = stored.header(c, eid, month)
    as_at = day_from(request.args["as_at"]) if request.args.get("as_at") else stored.default_as_at(hdr)
    out = {"entity": dict(e), "month": month, "label": db.month_label(month), "set_up": _set_up(c, eid, month), "as_at": as_at,
           "stored": bool(hdr)}
    if hdr:
        return jsonify({**out, "saved_as_at": hdr["as_at"], "balance": hdr["balance"], **stored.view(c, eid, month, as_at)})
    to_pay, paid, totals = _budget(c, eid, month, as_at)
    return jsonify({**out, "to_pay": to_pay, "paid": paid, "totals": totals,
                    "previous": bool(stored.header(c, eid, db.shift_month(month, -1)))})


def _budget_totals(c, eid, month, as_at):
    """What is still to pay as at a date per currency, from the stored budget when the month has one (as the Budget page
    has it), else from the payments."""
    if stored.header(c, eid, month):
        return stored.view(c, eid, month, as_at)["totals"]
    return _budget(c, eid, month, as_at)[2]


def _budget_call(fn):
    """Runs a change to a stored budget; what it refuses comes back as a plain message."""
    c = con()
    try:
        out = fn(c)
    except LookupError as x:
        c.rollback()
        return err(str(x), 404)
    except ValueError as x:
        c.rollback()
        return err(str(x))
    c.commit()
    return jsonify({"ok": True, "result": out})


def _body():
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else {}


def _budget_key(b):
    c = con()
    return entity(c, int(b["entity_id"]))["id"], month_from(b.get("month"))


@app.post("/api/budget/setup")
def budget_setup():
    b = _body()
    eid, month = _budget_key(b)
    return _budget_call(lambda c: stored.set_up(c, eid, month))


@app.post("/api/budget/header")
def budget_header():
    b = _body()
    eid, month = _budget_key(b)
    if b.get("as_at") and not iso_day(b["as_at"]):
        return err("That isn't a date. Dates are written like 2026-10-20.")
    return _budget_call(lambda c: stored.update_header(c, eid, month, b))


@app.post("/api/budget/lines")
def budget_add_line():
    b = _body()
    eid, month = _budget_key(b)
    return _budget_call(lambda c: stored.add_line(c, eid, month, b))


@app.post("/api/budget/lines/delete")
def budget_delete_lines():
    ids = _body().get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return err("Choose the lines to delete.")
    return _budget_call(lambda c: stored.delete_lines(c, ids))


@app.patch("/api/budget/lines/<int:lid>")
def budget_update_line(lid):
    return _budget_call(lambda c: stored.update_line(c, lid, _body()))


@app.delete("/api/budget/lines/<int:lid>")
def budget_delete_line(lid):
    return _budget_call(lambda c: stored.delete_lines(c, [lid]))


@app.get("/api/overview")
def overview():
    """as_at_<company id>: the date of the bank balance on that company's Budget page (default today). One that can't
    be read is taken as today too, so a bad date kept in the browser can't hide the whole page. A month marked as filed
    (closed_at) is done with: what is past due, missing or left to explain in it isn't counted."""
    month = month_from(request.args.get("month"))
    c = con()
    out = []
    today = date.today().isoformat()
    for e in c.execute("SELECT * FROM entities ORDER BY id").fetchall():
        as_at = iso_day(request.args.get(f"as_at_{e['id']}")) or stored.default_as_at(stored.header(c, e["id"], month))
        pays = c.execute("SELECT * FROM payments WHERE entity_id = ? AND month = ?", (e["id"], month)).fetchall()
        st = [db.payment_status(c, p, e["uses_sql"]) for p in pays]
        flags = [db.payment_flag(c, e, p, today) for p in pays]
        tasks = c.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ?", (e["id"], month)).fetchall()
        sts = [db.task_status(c, e, t) for t in tasks]
        task_flags = [f["code"] for f in (db.task_flag(c, e, t, today, s["done"]) for t, s in zip(tasks, sts)) if f]
        counted = [s for s in sts if not s["waiting"]]  # a reminder waiting for its own month isn't counted here
        todo = {
            # Money out; money received is counted apart in receipts (below).
            "paid_missing": sum(1 for (s, _), p in zip(st, pays) if s == "paid" and p["direction"] != "in"),
            "part_paid": sum(1 for (s, _), p in zip(st, pays) if s == "part_paid" and p["direction"] != "in"),
            "payment_flags": _flag_counts(zip(flags, pays)),
            "overdue_tasks": task_flags.count("overdue"), "due_today_tasks": task_flags.count("due_today"),
            "not_in_sql": sum(1 for p in pays if db.not_in_sql(e, p)),
            # On the month's own statements, as Before you print counts them.
            "unmatched_lines": sum(a["to_explain"] for a in db.month_statements(c, e, month)),
        }
        filed = db.closed_at(c, e["id"], month)
        if filed:
            todo = {k: [] if isinstance(v, list) else 0 for k, v in todo.items()}
        out.append({
            "entity": dict(e), "set_up": _set_up(c, e["id"], month), "before_first": db.before_tracking(e, month),
            "closed_at": filed, "payments": len(pays),
            "planned": sum(1 for s, _ in st if s == "planned"),
            # Money received, counted apart (the figures above hold payments out and money in together).
            "receipts": {"payments": sum(1 for p in pays if p["direction"] == "in"),
                         "planned": sum(1 for (s, _), p in zip(st, pays) if p["direction"] == "in" and s == "planned"),
                         "complete": sum(1 for (s, _), p in zip(st, pays) if p["direction"] == "in" and s == "complete"),
                         "paid_missing": sum(1 for (s, _), p in zip(st, pays) if p["direction"] == "in" and s == "paid"),
                         "part_paid": sum(1 for (s, _), p in zip(st, pays) if p["direction"] == "in" and s == "part_paid")},
            "complete": sum(1 for s, _ in st if s == "complete"),
            "tasks": len(counted), "tasks_done": sum(s["done"] for s in counted),
            "budget": _budget_totals(c, e["id"], month, as_at), "budget_as_at": as_at,
            **todo,
        })
    return jsonify({"month": month, "label": db.month_label(month), "entities": out})


@app.get("/api/next")
def next_up():
    """What to do next (nextup.items) on today's date, for the Overview, or with entity_id for one company's month page,
    the older months still open, and the next thing that falls due (next_due) for a list with nothing in it."""
    c = con()
    today = date.today()
    eid = entity(c, id_from(request.args["entity_id"]))["id"] if request.args.get("entity_id") else None
    found = nextup.items(c, today, eid)
    return jsonify({"today": today.isoformat(), "items": found, "older_open_months": nextup.older_open(c, today, eid),
                    "next_due": None if found else nextup.upcoming(c, today, eid)})


def _flag_counts(flags):
    """How many payments show each word (db.payment_flag), the overdue ones first, money in apart from money out (way:
    in or out). Not paid is left out, as the count of payments not paid yet holds those. flags: (flag, payment) pairs."""
    out = {}
    for f, p in flags:
        if f and f["code"] != "not_paid":
            way = p["direction"]
            out.setdefault((f["code"], f["text"], way), {"code": f["code"], "text": f["text"], "tone": f["tone"], "way": way,
                                                         "n": 0})["n"] += 1
    return sorted(out.values(), key=lambda x: x["tone"] != "bad")


@app.post("/api/months/open")
def open_month():
    """Sets up a month: its checklist and recurring payments. The page asks for the current cycle and the month
    before when it loads (auto), which leaves out months before the first month tracked."""
    b = request.get_json()
    c = con()
    e = entity(c, int(b["entity_id"]))
    month = month_from(b.get("month"))
    opened = db.auto_open(c, e["id"], month) if b.get("auto") else db.ensure_month(c, e["id"], month)
    c.commit()
    return jsonify({"opened": opened})


@app.post("/api/months/close")
def close_month():
    """Marks a month as filed (closed: true) or reopens it (false). Filing ticks the audit pack item, and the log keeps
    what was still open then, if anything (auditpack.readiness still_open): a month filed outside the app (on paper)
    can be marked too. Reopening leaves the tick, for unticking by hand. pack_ticked: the audit pack item is ticked."""
    b = request.get_json()
    c = con()
    e = entity(c, int(b["entity_id"]))
    month = month_from(b.get("month"))
    label = f"{e['code']} {db.month_label(month)}"
    if not _set_up(c, e["id"], month):
        return err(f"{db.month_label(month)} isn't set up for {e['code']}, so there is nothing to mark as filed.")
    was = db.closed_at(c, e["id"], month)
    if b.get("closed") and not was:
        still = auditpack.readiness(c, e, month)["still_open"]
        at = db.now()
        c.execute("UPDATE months SET closed_at = ? WHERE entity_id = ? AND month = ?", (at, e["id"], month))
        c.execute("UPDATE tasks SET done_at = ? WHERE entity_id = ? AND month = ? AND code = ? AND done_at IS NULL",
                  (at, e["id"], month, rules.TASK_PACK))
        db.log(c, f"Marked {label} as filed" + (f", although: {'; '.join(still)}" if still else ""))
    ticked = bool(c.execute("SELECT 1 FROM tasks WHERE entity_id = ? AND month = ? AND code = ? AND done_at IS NOT NULL",
                            (e["id"], month, rules.TASK_PACK)).fetchone())
    if not b.get("closed") and was:
        c.execute("UPDATE months SET closed_at = NULL WHERE entity_id = ? AND month = ?", (e["id"], month))
        db.log(c, f"Reopened {label} (filed {db.day_label(was[:10])})" + ("; the audit pack item stays ticked" if ticked else ""))
    c.commit()
    return jsonify({"closed_at": db.closed_at(c, e["id"], month), "pack_ticked": ticked})


@app.post("/api/entities/<int:eid>/first-month")
def set_first_month(eid):
    c = con()
    e = entity(c, eid)
    month = request.get_json().get("month") or None
    if month:
        month_from(month)
    c.execute("UPDATE entities SET first_month = ? WHERE id = ?", (month, eid))
    db.log(c, f"First month tracked for {e['code']}: {db.month_label(month) if month else 'none (no limit)'}")
    c.commit()
    return jsonify({"ok": True})


def _untracked(c, e):
    """What the months before the first month tracked hold that nothing was ever recorded on: payments with no paid
    date, document, SQL voucher or bank line, and checklist items not ticked with no document."""
    pays = [p["id"] for p in c.execute("SELECT * FROM payments WHERE entity_id = ? AND month < ?", (e["id"], e["first_month"]))
            if not db.recorded(c, p)]
    tasks = [t["id"] for t in c.execute(
        """SELECT id FROM tasks t WHERE entity_id = ? AND month < ? AND done_at IS NULL
           AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.task_id = t.id)
           AND NOT EXISTS (SELECT 1 FROM sql_entries s WHERE s.task_id = t.id)""", (e["id"], e["first_month"]))]
    return pays, tasks


@app.get("/api/months/tidy")
def tidy_count():
    c = con()
    e = entity(c, int(request.args["entity"]))
    if not e["first_month"]:
        return err("Set the first month tracked in this app first.")
    pays, tasks = _untracked(c, e)
    return jsonify({"payments": len(pays), "tasks": len(tasks), "before": e["first_month"]})


@app.post("/api/months/tidy")
def tidy_months():
    c = con()
    e = entity(c, int(request.get_json()["entity_id"]))
    if not e["first_month"]:
        return err("Set the first month tracked in this app first.")
    pays, tasks = _untracked(c, e)
    c.executemany("DELETE FROM payments WHERE id = ?", [(i,) for i in pays])
    c.executemany("DELETE FROM tasks WHERE id = ?", [(i,) for i in tasks])
    db.log(c, f"Tidied up the months before {db.month_label(e['first_month'])} for {e['code']}: removed {len(pays)} payments "
              f"and {len(tasks)} checklist items nothing was recorded on")
    c.commit()
    return jsonify({"payments": len(pays), "tasks": len(tasks)})


@app.post("/api/tasks/<int:tid>")
def update_task(tid):
    body = request.get_json()
    c = con()
    t = c.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone() or abort(404)
    if "done" in body:
        # The page asks 'Tick anyway?' first; the log keeps what was missing then.
        lacking = db.task_status(c, entity(c, t["entity_id"]), t)["lacking"] if body["done"] else []
        c.execute("UPDATE tasks SET done_at = ? WHERE id = ?", (db.now() if body["done"] else None, tid))
        db.log(c, f"{'Ticked' if body['done'] else 'Unticked'} task: {t['title']} ({t['month']})"
                  + (f", although: {'; '.join(lacking)}" if lacking else ""))
    if "note" in body:
        c.execute("UPDATE tasks SET note = ? WHERE id = ?", (body["note"], tid))
    c.commit()
    return jsonify({"ok": True})


PAY_FIELDS = ("description", "amount", "paid_date", "due_date", "bank_ref", "sql_ref", "einvoice_ref", "notes", "category", "account_id",
              "difference_note")
# How each of them is named in the activity log.
PAY_FIELD_NAMES = {"description": "description", "amount": "amount", "paid_date": "paid date", "due_date": "due date",
                   "bank_ref": "bank reference", "sql_ref": "SQL voucher no.", "einvoice_ref": "e-Invoice UIN", "notes": "notes",
                   "category": "type", "account_id": "bank account", "difference_note": "reason for the difference"}


def own_account(c, e, account_id):
    """The bank account chosen, refused unless it is one of the company's own; None when none is chosen."""
    if not account_id:
        return None
    acct = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not acct or acct["entity_id"] != e["id"]:
        abort(make_response(*err(f"That bank account isn't one of {e['name']}'s accounts. Choose one of {e['code']}'s own accounts.")))
    return acct


@app.post("/api/payments")
def create_payment():
    b = request.get_json()
    c = con()
    e = entity(c, int(b["entity_id"]))
    month = month_from(b.get("month"))
    acct = own_account(c, e, b.get("account_id"))
    if not b.get("description"):
        return err("Give the payment a description.")
    cur = c.execute(
        """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
           paid_source, direction, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (e["id"], month, acct["id"] if acct else None, b.get("category", "other"), b["description"],
         b.get("amount"), acct["currency"] if acct else "MYR", b.get("due_date") or b.get("paid_date") or date.today().isoformat(),
         b.get("paid_date"), "manual" if b.get("paid_date") else None, b.get("direction", "out"), b.get("notes"), db.now()))
    db.log(c, f"Added payment: {b['description']} ({month})")
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.patch("/api/payments/<int:pid>")
def update_payment(pid):
    b = request.get_json()
    c = con()
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone() or abort(404)
    sets = {k: (v if v != "" else None) for k, v in b.items() if k in PAY_FIELDS}
    if "account_id" in sets:
        acct = own_account(c, entity(c, p["entity_id"]), sets["account_id"])
        sets["account_id"] = acct["id"] if acct else None
    if b.get("amount_confirmed") or ("amount" in sets and _amount_changed(p["amount"], sets["amount"])):
        # A figure typed in is confirmed: SQL and the bank no longer replace it, and undoing a link keeps it.
        sets.update(amount_is_estimate=0, planned_amount=None, planned_is_estimate=None, undo_link=None)
    if "paid_date" in sets and sets["paid_date"] != p["paid_date"]:
        sets["paid_source"] = "manual" if sets["paid_date"] else None
    if sets:
        c.execute(f"UPDATE payments SET {', '.join(k + ' = ?' for k in sets)} WHERE id = ?", (*sets.values(), pid))
        named = [PAY_FIELD_NAMES[k] for k in sets if k in PAY_FIELD_NAMES] + (["amount confirmed"] if b.get("amount_confirmed") else [])
        db.log(c, f"Updated payment: {p['description']} ({', '.join(named)})")
    c.commit()
    return jsonify({"ok": True})


def _amount_changed(old, new):
    if old is None or new is None:
        return (old is None) != (new is None)
    return round(float(old), 2) != round(float(new), 2)


@app.delete("/api/payments/<int:pid>")
def delete_payment(pid):
    c = con()
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    if not p:
        return err("This payment has already been removed.", 404)
    if c.execute("SELECT 1 FROM documents WHERE payment_id = ? AND replaced_by IS NULL AND removed_at IS NULL", (pid,)).fetchone():
        return err("This payment has documents attached, so it can't be removed. If it was added by mistake, remove its "
                   "documents first; the files are kept on this PC.")
    vouchers = [r["doc_no"] for r in c.execute("SELECT doc_no FROM sql_entries WHERE payment_id = ? ORDER BY doc_no", (pid,))]
    try:
        # Its bank lines go back to the lines waiting to be explained, marked so matching again doesn't give them to
        # another payment, and its SQL vouchers back under 'not linked'. Documents taken off it or replaced stay on
        # record, noting the payment they were filed on.
        lines = c.execute("UPDATE statement_lines SET payment_id = NULL, status = 'unmatched', undone_payment_id = ? "
                          "WHERE payment_id = ?", (pid, pid)).rowcount
        # (A customer invoice or journal keeps its status: only the link goes.)
        c.execute("UPDATE sql_entries SET payment_id = NULL, status = CASE WHEN kind IN ('invoice', 'journal') THEN status "
                  "ELSE 'unlinked' END WHERE payment_id = ?", (pid,))
        kept = c.execute("UPDATE documents SET payment_id = NULL, note = COALESCE(note || '; ', '') || ? WHERE payment_id = ?",
                         (f"Filed on payment {p['description']} ({p['month']}), removed {db.now()[:10]}", pid)).rowcount
        c.execute("DELETE FROM payments WHERE id = ?", (pid,))
        db.log(c, f"Removed payment: {p['description']} ({p['month']})"
                  + (f"; SQL {', '.join(vouchers)} now not linked" if vouchers else "")
                  + (f"; {lines} bank line{'s' if lines > 1 else ''} back to explain" if lines else "")
                  + (f"; the {kept} document{'s' if kept > 1 else ''} taken off it kept on record" if kept else ""))
        c.commit()
    except sqlite3.Error:
        c.rollback()
        return err("This payment couldn't be removed, so nothing was changed. Try again, or set its amount to 0 and add a note.")
    return jsonify({"ok": True, "unlinked": vouchers, "lines": lines})


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return err("Choose a file to upload.")
    doc_type = request.form.get("doc_type", "other")
    if doc_type not in rules.DOC_TYPES:
        return err("Unknown document type.")
    c = con()
    pid, tid = request.form.get("payment_id"), request.form.get("task_id")
    if pid:
        owner = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone() or abort(404)
        folder = f"{owner['due_date']} {owner['description']} #{owner['id']}"
    elif tid:
        owner = c.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone() or abort(404)
        folder = f"_Checklist - {owner['title']}"
    else:
        return err("Upload has no payment or task.")
    e = entity(c, owner["entity_id"])
    try:
        did = store(c, entity=e, month=owner["month"], folder=folder, doc_type=doc_type, filename=f.filename, data=f.read(),
                    payment_id=pid, task_id=tid, note=request.form.get("note"))
    except ValueError as ex:
        return err(str(ex))
    replaces = request.form.get("replaces")
    if replaces:
        c.execute("UPDATE documents SET replaced_by = ? WHERE id = ?", (did, replaces))
    db.log(c, f"Uploaded {rules.DOC_TYPES[doc_type]} '{f.filename}' to {folder}")
    c.commit()
    return jsonify({"id": did})


@app.get("/api/documents/<int:did>/file")
def doc_file(did):
    c = con()
    d = c.execute("SELECT * FROM documents WHERE id = ?", (did,)).fetchone() or abort(404)
    p = path_of(d)
    if not p.exists():
        abort(404)
    return send_file(p, as_attachment=request.args.get("download") == "1", download_name=d["original_name"])


@app.post("/api/documents/<int:did>/remove")
def remove_document(did):
    """Takes a document off its payment or checklist item: it leaves the lists, the counts and the audit pack. The file
    stays on disk, read-only, and its record stays, so what was filed can still be traced."""
    c = con()
    d = c.execute("SELECT * FROM documents WHERE id = ?", (did,)).fetchone() or abort(404)
    if not (d["payment_id"] or d["task_id"]):
        return err("Only a document uploaded to a payment or a checklist item can be removed.")
    if d["removed_at"] or d["replaced_by"]:
        return err("This document has already been removed or replaced.")
    owner = (c.execute("SELECT description AS name, month FROM payments WHERE id = ?", (d["payment_id"],)) if d["payment_id"]
             else c.execute("SELECT title AS name, month FROM tasks WHERE id = ?", (d["task_id"],))).fetchone()
    c.execute("UPDATE documents SET removed_at = ? WHERE id = ?", (db.now(), did))
    db.log(c, f"Removed {rules.DOC_TYPES.get(d['doc_type'], d['doc_type'])} '{d['original_name']}' from {owner['name']} "
              f"({owner['month']}); the file is kept")
    c.commit()
    return jsonify({"ok": True})


@app.get("/api/documents/<int:did>/history")
def doc_history(did):
    c = con()
    out, cur = [], did
    while cur:
        d = c.execute("SELECT * FROM documents WHERE replaced_by = ?", (cur,)).fetchone()
        if not d:
            break
        out.append(dict(d))
        cur = d["id"]
    return jsonify(out)


# ---------- payees ----------

@app.get("/api/payees")
def payees():
    c = con()
    month = month_from(request.args["month"]) if request.args.get("month") else None
    out = rows(c.execute(
        """SELECT py.*, COALESCE(a.currency, 'MYR') AS currency FROM payees py LEFT JOIN accounts a ON a.id = py.account_id
           WHERE py.entity_id = ? ORDER BY py.active DESC, py.sort, py.name""", (request.args["entity"],)))
    for p in out:
        p["advances"] = rows(c.execute("SELECT * FROM advances WHERE payee_id = ?", (p["id"],)))
        if month:
            p["in_month"] = bool(c.execute("SELECT 1 FROM payments WHERE payee_id = ? AND month = ?", (p["id"], month)).fetchone())
            p["employed"] = db.employed_in(p, month)
    return jsonify(out)


PAYEE_FIELDS = ("name", "category", "desc_template", "amount", "amount_varies", "month_offset", "due_day", "bank_details",
                "reference", "match_words", "active", "notes", "account_id", "start_date", "end_date", "direction")


@app.post("/api/payees")
def save_payee():
    """Saves a recurring payment, and brings the change into the months already set up (db.sync_payee)."""
    b = request.get_json()
    c = con()
    vals = {k: b.get(k) for k in PAYEE_FIELDS if k in b}
    if not vals.get("name"):
        return err("Give the payee a name.")
    vals.setdefault("desc_template", vals["name"] + " - {M}")
    # Money in is a receipt and a receipt is money in; a payment going out is any other type.
    way = vals.get("direction") or ("in" if vals.get("category") == "receipt" else None)
    if way not in (None, "in", "out"):
        return err("Choose Money in or Money out.")
    if way == "in":
        vals["direction"], vals["category"] = "in", "receipt"
    elif way == "out":
        vals["direction"] = "out"
        if vals.get("category") == "receipt":
            vals["category"] = "other"
    old = c.execute("SELECT * FROM payees WHERE id = ?", (b["id"],)).fetchone() if b.get("id") else None
    if b.get("id") and not old:
        return err("This recurring payment has been removed.", 404)
    e = entity(c, old["entity_id"] if old else int(b["entity_id"]))
    own_account(c, e, vals.get("account_id"))
    if old:
        c.execute(f"UPDATE payees SET {', '.join(k + ' = ?' for k in vals)} WHERE id = ?", (*vals.values(), old["id"]))
        db.log(c, f"Updated recurring payment: {vals['name']}")
        pid = old["id"]
    else:
        vals["entity_id"] = e["id"]
        pid = c.execute(f"INSERT INTO payees ({', '.join(vals)}) VALUES ({', '.join('?' * len(vals))})", tuple(vals.values())).lastrowid
        db.log(c, f"Added recurring payment: {vals['name']}")
    new = c.execute("SELECT * FROM payees WHERE id = ?", (pid,)).fetchone()
    changes, kept = db.sync_payee(c, old, new)
    changes += db.sync_reminders(c, new)
    c.commit()
    return jsonify({"ok": True, "changes": changes, "kept": kept})


@app.post("/api/payees/<int:pid>/add-to-month")
def payee_to_month(pid):
    c = con()
    p = c.execute("SELECT * FROM payees WHERE id = ?", (pid,)).fetchone() or abort(404)
    month = month_from(request.get_json().get("month"))
    label = db.month_label(month)
    if not db.employed_in(p, month):
        return err(f"{p['name']} isn't employed in {label}"
                   + (f" (starts {db.day_label(p['start_date'])})." if p["start_date"] and p["start_date"][:7] > month
                      else f" (last day {db.day_label(p['end_date'])})."))
    # Setting the month up first, so it can't add the payee a second time later.
    opened = db.ensure_month(c, p["entity_id"], month)
    if c.execute("SELECT 1 FROM payments WHERE payee_id = ? AND month = ?", (pid, month)).fetchone():
        if not opened:
            return err(f"{p['name']} already has a payment in {label}.")
    elif db.create_payment_from_payee(c, p, month) is None:
        return err(f"There is nothing to pay {p['name']} in {label}: no days worked, or the amount after advances is zero.")
    else:
        db.log(c, f"Added {p['name']} to {label}")
    stored.link_new(c, p["entity_id"], month)
    c.commit()
    return jsonify({"ok": True, "opened": opened})


# ---------- bank statements ----------

@app.post("/api/statements")
def import_statement():
    f = request.files.get("file")
    acct_id = request.form.get("account_id")
    if not f or not acct_id:
        return err("Choose the account and the statement PDF.")
    data = f.read()
    try:
        info = statements.parse_maybank(data)
    except statements.StatementError as ex:
        return err(str(ex))
    except Exception:
        return err("This PDF couldn't be read as a Maybank statement.")
    c = con()
    acct = c.execute("SELECT * FROM accounts WHERE id = ?", (acct_id,)).fetchone() or abort(404)
    if acct["number"] and info["account_number"] and acct["number"].replace(" ", "") != info["account_number"]:
        return err(f"This statement is for account {info['account_number']}, not {acct['label']} ({acct['number']}).")
    if not acct["number"] and info["account_number"]:
        c.execute("UPDATE accounts SET number = ? WHERE id = ?", (info["account_number"], acct["id"]))
    month = info["statement_date"][:7]
    if c.execute("SELECT 1 FROM statements WHERE account_id = ? AND month = ?", (acct["id"], month)).fetchone():
        return err(f"A statement for {acct['label']} {db.month_label(month)} is already imported.")
    e = entity(c, acct["entity_id"])
    cur = c.execute(
        """INSERT INTO statements (account_id, month, statement_date, opening, closing, total_debits, total_credits, imported_at, check_ok)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (acct["id"], month, info["statement_date"], info["opening"], info["closing"], info["total_debits"],
         info["total_credits"], db.now(), 1 if info["check_ok"] else 0))
    sid = cur.lastrowid
    did = store(c, entity=e, month=month, folder=f"_Bank statements", doc_type="statement",
                filename=f"{acct['label']} {month} - {f.filename}", data=data, statement_id=sid)
    c.execute("UPDATE statements SET document_id = ? WHERE id = ?", (did, sid))
    for n, l in enumerate(info["lines"], 1):
        c.execute("INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance) VALUES (?, ?, ?, ?, ?, ?)",
                  (sid, n, l["date"], l["description"], l["amount"], l["balance"]))
    # A month's statement holds that payroll month's payments and the previous cycle's (statutory on the 6th)
    for m in (db.shift_month(month, -1), month):
        db.auto_open(c, e["id"], m)
    matched = statements.auto_match(c, sid)
    no_docs = sum(statements.classify(c, s["id"]) for s in c.execute(
        "SELECT s.id FROM statements s JOIN accounts a ON a.id = s.account_id WHERE a.entity_id = ?", (e["id"],)).fetchall())
    db.log(c, f"Imported statement {acct['label']} {month}: {len(info['lines'])} lines, {matched} matched automatically, "
              f"{no_docs} bank charges or own transfers")
    c.commit()
    return jsonify({"id": sid, "lines": len(info["lines"]), "matched": matched, "no_docs": no_docs, "month": month,
                    "check_ok": info["check_ok"]})


@app.get("/api/statements")
def list_statements():
    c = con()
    sts = rows(c.execute(
        """SELECT s.*, a.label AS account_label, a.currency FROM statements s JOIN accounts a ON a.id = s.account_id
           WHERE a.entity_id = ? ORDER BY s.month DESC, a.id""", (request.args["entity"],)))
    for s in sts:
        s["lines"] = rows(c.execute(
            """SELECT l.*, p.description AS payment_desc, p.month AS payment_month FROM statement_lines l
               LEFT JOIN payments p ON p.id = l.payment_id WHERE l.statement_id = ? ORDER BY l.line_no""", (s["id"],)))
    return jsonify(sts)


@app.post("/api/statement-lines/<int:lid>")
def update_line(lid):
    b = request.get_json()
    c = con()
    l = c.execute(
        """SELECT l.*, s.month, s.account_id, a.entity_id FROM statement_lines l JOIN statements s ON s.id = l.statement_id
           JOIN accounts a ON a.id = s.account_id WHERE l.id = ?""", (lid,)).fetchone() or abort(404)
    if b.get("create_payment"):
        cp = b["create_payment"]
        if cp.get("month"):
            month_from(cp["month"])
        # Planned as a blank amount, so the lines linked later make up its amount, and undoing them all blanks it again.
        cur = c.execute(
            """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
               paid_source, planned_is_estimate, direction, created_at)
               VALUES (?, ?, ?, ?, ?, ?, (SELECT currency FROM accounts WHERE id = ?), ?, ?, 'bank', 0, ?, ?)""",
            (l["entity_id"], cp.get("month") or l["month"], l["account_id"], cp.get("category", "other"), cp["description"],
             abs(l["amount"]), l["account_id"], l["txn_date"], l["txn_date"], "in" if l["amount"] > 0 else "out", db.now()))
        c.execute("UPDATE statement_lines SET payment_id = ?, status = 'matched' WHERE id = ?", (cur.lastrowid, lid))
        db.log(c, f"Created payment from bank line {l['txn_date']} {l['amount']:,.2f}: {cp['description']}")
    elif "payment_id" in b:
        if b["payment_id"]:
            pid = int(b["payment_id"])
            c.execute("UPDATE statement_lines SET payment_id = ?, status = 'matched' WHERE id = ?", (pid, lid))
            # The latest date of the lines that paid it, as matching gives; it wins over an SQL voucher's, and a date
            # typed in stays.
            paid = statements.paying_dates(c, pid)
            if paid:
                c.execute("""UPDATE payments SET paid_date = ?, paid_source = 'bank'
                             WHERE id = ? AND (paid_date IS NULL OR paid_source IN ('bank', 'sql'))""", (max(paid), pid))
            statements.take_line_total(c, pid)
            if l["payment_id"] != pid:
                desc = c.execute("SELECT description FROM payments WHERE id = ?", (pid,)).fetchone()[0]
                db.log(c, f"Linked bank line {db.short_day(l['txn_date'])} {l['amount']:,.2f} to payment: {desc}")
        else:
            # Remembered (0 for a line undone from 'No documents needed'), so matching again neither links it back nor
            # marks it again; it can still be linked by hand.
            c.execute("""UPDATE statement_lines SET payment_id = NULL, status = 'unmatched', note = NULL,
                         undone_payment_id = COALESCE(?, undone_payment_id, 0) WHERE id = ?""", (l["payment_id"], lid))
            if l["payment_id"]:
                desc = c.execute("SELECT description FROM payments WHERE id = ?", (l["payment_id"],)).fetchone()[0]
                db.log(c, f"Undid bank line {l['txn_date']} {l['amount']:,.2f} from payment: {desc}")
            elif l["status"] == "no_docs":
                db.log(c, f"Undid bank line {db.short_day(l['txn_date'])} {l['amount']:,.2f} as needing no documents")
    elif "status" in b:
        c.execute("UPDATE statement_lines SET status = ?, note = ? WHERE id = ?", (b["status"], b.get("note"), lid))
        if b["status"] == "no_docs" and (l["status"], l["note"]) != ("no_docs", b.get("note")):
            db.log(c, f"Marked bank line {db.short_day(l['txn_date'])} {l['amount']:,.2f} as needing no documents"
                   + (f": {b['note']}" if b.get("note") else ""))
    new = c.execute("SELECT payment_id FROM statement_lines WHERE id = ?", (lid,)).fetchone()[0]
    removed = None
    if l["payment_id"] and l["payment_id"] != new:
        p = c.execute("SELECT * FROM payments WHERE id = ?", (l["payment_id"],)).fetchone()
        if _made_from_lines(c, p, l):
            # Left with no line, it would only be a blank payment past due.
            c.execute("DELETE FROM payments WHERE id = ?", (p["id"],))
            db.log(c, f"Removed the payment made from bank lines, as none is linked to it now: {p['description']} ({p['month']})")
            removed = p["description"]
        else:
            _after_unlink(c, p["id"])
    c.commit()
    return jsonify({"ok": True, "removed": removed})


def _made_from_lines(c, p, l):
    """True when the payment is just what 'Create payment and link' made and no bank line is linked to it now (l: the
    line just taken off): no payee, planned at a blank amount, paid from the bank, due the day of a line it was made
    from, nothing typed in since, and no SQL voucher or document."""
    made = (p["payee_id"] is None and p["planned_is_estimate"] == 0 and p["planned_amount"] is None and p["paid_source"] == "bank"
            and not (p["notes"] or p["bank_ref"] or p["sql_ref"] or p["einvoice_ref"] or p["difference_note"])
            and (p["due_date"] == l["txn_date"] or c.execute(
                "SELECT 1 FROM statement_lines WHERE undone_payment_id = ? AND txn_date = ?", (p["id"], p["due_date"])).fetchone()))
    return made and not any(c.execute(f"SELECT 1 FROM {t} WHERE payment_id = ?", (p["id"],)).fetchone()
                            for t in ("statement_lines", "sql_entries", "documents"))


@app.get("/api/statement-suggestions")
def statement_suggestions():
    """For the lines still to explain: up to 3 open payments each might be (statements.suggest). Nothing is linked."""
    try:
        eid = int(request.args.get("entity", ""))
    except ValueError:
        return err("Say which company (entity) the suggestions are for.")
    return jsonify(statements.suggest(con(), eid))


@app.get("/api/open-payments")
def open_payments():
    """Payments a bank line can be linked to: same account, the statement month or the month before."""
    c = con()
    acct, month = request.args["account"], month_from(request.args.get("month"))
    return jsonify(rows(c.execute(
        """SELECT id, month, description, amount, currency, direction, due_date FROM payments
           WHERE account_id = ? AND month BETWEEN ? AND ?
           ORDER BY due_date""", (acct, db.shift_month(month, -1), month))))


# ---------- SQL Account exports ----------

_pending_sql = {}  # token -> (entity_id, filename, data); one person uses this app, so memory is enough
PASTED = "SQL listing pasted"  # how a pasted listing's file is named
_preview_made = {}  # token -> {payment id: (payee id, month)} for payments the preview set up only for its suggestions


def _parse_sql(token, header_row=None, mapping=None):
    if token not in _pending_sql:
        raise sqlimport.SqlImportError("This upload has expired. Choose the file again.")
    eid, filename, data = _pending_sql[token]
    rows_ = sqlimport.read_rows(filename, data)
    guessed_row, guessed_map = sqlimport.guess_header(rows_) if header_row is None or mapping is None else (None, None)
    header_row = guessed_row if header_row is None else header_row
    mapping = guessed_map if mapping is None else {k: v for k, v in mapping.items() if v is not None}
    return eid, filename, data, rows_, header_row, mapping


@app.post("/api/sql/preview")
def sql_preview():
    c = con()
    pasted = False
    try:
        if request.files.get("file"):
            f = request.files["file"]
            token = secrets.token_hex(8)
            _pending_sql[token] = (int(request.form["entity_id"]), f.filename, f.read())
            hr, mp = None, None
        elif request.get_json().get("text"):
            # Rows copied straight from an SQL Account listing (Ctrl+A, Ctrl+C) and pasted into the app.
            b = request.get_json()
            pasted = True
            if b["text"].count("<DATAPACKET") > 1:
                return err("The box holds more than one SQL listing. Clear it, then paste one listing at a time.")
            token = secrets.token_hex(8)
            ext = "xml" if "<DATAPACKET" in b["text"][:500] else "txt"
            name = f"{PASTED} {datetime.now():%Y%m%d-%H%M}.{ext}"
            _pending_sql[token] = (int(b["entity_id"]), name, b["text"].encode("utf-8"))
            hr, mp = None, None
        else:
            b = request.get_json()
            token, hr, mp = b["token"], b.get("header_row"), b.get("mapping")
            pasted = _pending_sql.get(token, (None, ""))[1].startswith(PASTED)
        picks = (request.get_json(silent=True) or {}).get("picks") or {}
        eid, filename, _, rows_, header_row, mapping = _parse_sql(token, hr, mp)
        recs = sqlimport.records(rows_, header_row, mapping)
    except sqlimport.SqlImportError as ex:
        return err(str(ex))
    except Exception:
        if pasted:
            return err("The pasted rows couldn't be read. Clear the box, copy the listing in SQL again and paste it.")
        return err("This file couldn't be read. Export the SQL report as Excel (.xlsx) and try again.")
    # The months the listing needs are set up for the suggestions (checklist tasks must exist before documents can be
    # linked to them), then undone: only Import keeps anything.
    top = c.execute("SELECT COALESCE(MAX(id), 0) FROM payments").fetchone()[0]
    for m in sqlimport.months_of(recs):
        db.auto_open(c, eid, m)
    sqlimport.propose(c, eid, recs)
    made = _preview_made.get(token, {})
    for r in recs:  # links picked by hand stay with their row when the columns are read again
        if str(r["row"]) in picks and (r["kind"] == "payment" or sqlimport.receipt_invoice(r)):
            r["payment_id"], r["picked"] = _payment_now(c, eid, made, picks[str(r["row"])]), True
    linked = sqlimport.linked_vouchers(c, eid)
    for r in recs:
        r["exists"] = bool(c.execute("SELECT 1 FROM sql_entries WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ?",
                                     (eid, r["doc_no"], r["date"], r["amount"])).fetchone())
        _note_linked(r, linked)
    if header_row >= 0:
        headers = [str(h) if h is not None else "" for h in rows_[header_row]]
    else:  # pasted without headings: label each column by an example value
        sample = next(r for r in rows_ if sum(1 for x in r if str(x or "").strip()) >= 3)
        headers = [f"Column {i + 1}: {str(v)[:25]}" for i, v in enumerate(sample)]
    cands = sqlimport.candidates(c, eid, sqlimport.months_of(recs), [r["payment_id"] for r in recs if r["payment_id"]])
    _preview_made[token] = {r["id"]: (r["payee_id"], r["month"]) for r in c.execute(
        "SELECT id, payee_id, month FROM payments WHERE id > ?", (top,))}
    c.rollback()
    return jsonify({"token": token, "entity_id": eid, "filename": filename, "header_row": header_row, "headers": headers,
                    "mapping": mapping, "fields": list(sqlimport.FIELDS), "records": recs, "candidates": cands})


def _payment_now(c, eid, made, pid):
    """The payment a link picked in a preview means now. One the preview set up only for its suggestions (made: id ->
    payee and month) is found again by payee and month, as setting the month up again may number it differently;
    one removed since is no longer linked."""
    if pid and int(pid) in made:
        hit = c.execute("SELECT id FROM payments WHERE payee_id = ? AND month = ? ORDER BY id", made[int(pid)]).fetchone()
    else:
        hit = c.execute("SELECT id FROM payments WHERE id = ? AND entity_id = ?", (pid, eid)).fetchone() if pid else None
    return hit["id"] if hit else None


def _note_linked(r, linked):
    """Notes the payment that already holds this voucher number with other details: the voucher was changed in SQL."""
    other = linked.get(r["doc_no"].upper())
    if other and not r.get("exists"):
        r["linked_to"], r["linked_amount"] = other["description"], other["amount"]


@app.post("/api/sql/apply")
def sql_apply():
    b = request.get_json()
    c = con()
    try:
        eid, filename, data, rows_, header_row, mapping = _parse_sql(b["token"], b["header_row"], b["mapping"])
        recs = sqlimport.records(rows_, header_row, mapping)
    except sqlimport.SqlImportError as ex:
        return err(str(ex))
    e = entity(c, eid)
    month = max(r["date"] for r in recs)[:7]
    did = store(c, entity=e, month=month, folder="_SQL exports", doc_type="sqlexport", filename=filename, data=data)
    imp = c.execute("INSERT INTO sql_imports (entity_id, filename, document_id, imported_at, entries, linked) VALUES (?, ?, ?, ?, 0, 0)",
                    (eid, filename, did, db.now())).lastrowid
    for m in sqlimport.months_of(recs):
        db.auto_open(c, eid, m)
    made = _preview_made.get(b["token"], {})
    links = {int(k): _payment_now(c, eid, made, v) for k, v in (b.get("links") or {}).items()}
    # A customer invoice links only to money in: the receipt it is for. Its checklist item (task_id) is kept as well.
    money_in = {x[0] for x in c.execute("SELECT id FROM payments WHERE entity_id = ? AND direction = 'in'", (eid,))}
    sqlimport.propose(c, eid, recs)  # for the checklist task of journals and invoices
    added = linked = skipped = 0
    touched = set()
    for r in recs:
        pid = links.get(r["row"]) if r["kind"] == "payment" else None
        if sqlimport.receipt_invoice(r) and links.get(r["row"]) in money_in:
            pid = links[r["row"]]
        status = r["kind"] if r["kind"] != "payment" else ("linked" if pid else "unlinked")
        cur = c.execute(
            """INSERT OR IGNORE INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction,
               einvoice, doc_type, kind, einvoice_status, einvoice_link, task_id, payment_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (imp, eid, r["doc_no"], r["date"], r["description"], r["payee"], r["amount"], r.get("direction"),
             r.get("einvoice") or None, r["doc_type"], r["kind"], r.get("einvoice_status") or None,
             r.get("einvoice_link") or None, r.get("task_id"), pid, status))
        if not cur.rowcount:
            # Already imported from another listing (e.g. the cash book and the PV listing both hold PV2610-001):
            # fill in anything the earlier listing lacked, and an e-Invoice validated since.
            # A document first read without its type (e.g. a customer invoice) is reclassified while still unlinked.
            st = r.get("einvoice_status") or None
            c.execute(
                """UPDATE sql_entries SET einvoice = COALESCE(einvoice, ?),
                   einvoice_status = CASE WHEN ? LIKE 'Validated%' THEN ? ELSE COALESCE(einvoice_status, ?) END,
                   einvoice_link = COALESCE(einvoice_link, ?), task_id = COALESCE(task_id, ?),
                   doc_type = CASE WHEN status = 'unlinked' THEN ? ELSE doc_type END,
                   kind = CASE WHEN status = 'unlinked' THEN ? ELSE kind END,
                   status = CASE WHEN status = 'unlinked' AND ? != 'payment' THEN ? ELSE status END
                   WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ?""",
                (r.get("einvoice") or None, st, st, st, r.get("einvoice_link") or None,
                 r.get("task_id"), r["doc_type"], r["kind"], r["kind"], r["kind"], eid, r["doc_no"], r["date"], r["amount"]))
        if not cur.rowcount and pid and sqlimport.receipt_invoice(r):
            # An invoice imported before, linked to its receipt now (only while it isn't linked to one).
            hit = c.execute("""UPDATE sql_entries SET payment_id = ? WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ?
                               AND payment_id IS NULL""", (pid, eid, r["doc_no"], r["date"], r["amount"]))
            linked += hit.rowcount
            if hit.rowcount:
                db.log(c, f"Linked SQL invoice {r['doc_no']} to receipt: "
                          f"{c.execute('SELECT description FROM payments WHERE id = ?', (pid,)).fetchone()[0]}")
        if not cur.rowcount:
            skipped += 1
            continue
        added += 1
        if pid and r["kind"] == "invoice":
            linked += 1  # the invoice is the receipt's sales invoice; nothing is added to its SQL ref (that is the OR's)
        elif pid:
            _add_sql_ref(c, pid, r["doc_no"], r["amount"], r.get("einvoice"), r["date"], cur.lastrowid)
            linked += 1
            touched.add(int(pid))
    c.execute("UPDATE sql_imports SET entries = ?, linked = ? WHERE id = ?", (added, linked, imp))
    matched = _match_payments(c, eid, touched)
    db.log(c, f"Imported SQL export '{filename}' for {e['code']}: {added} entries, {linked} linked, {skipped} already imported, "
              f"{matched} bank lines matched")
    c.commit()
    _pending_sql.pop(b["token"], None)
    _preview_made.pop(b["token"], None)
    return jsonify({"added": added, "linked": linked, "skipped": skipped, "bank_lines_matched": matched})


# What an SQL voucher's link replaced on a payment, kept (undo_link) so unlinking it can put exactly that back.
LINK_REPLACES = ("amount", "amount_is_estimate", "planned_amount", "planned_is_estimate")


def _add_sql_ref(c, pid, doc_no, amount=None, einvoice=None, doc_date=None, entry_id=None):
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    if doc_date and not p["paid_date"]:
        # A payment or receipt voucher is dated the day the money moved; the bank statement can confirm it later.
        c.execute("UPDATE payments SET paid_date = ?, paid_source = 'sql' WHERE id = ?", (doc_date, pid))
    refs = [x.strip() for x in (p["sql_ref"] or "").split(",") if x.strip()]
    if doc_no.upper() not in sqlimport.refs_of(p["sql_ref"]):  # the number may already be typed in the SQL ref box
        refs.append(doc_no)
    c.execute("UPDATE payments SET sql_ref = ? WHERE id = ?", (", ".join(refs), pid))
    # SQL holds the real figure: a blank or estimated amount becomes the total of the vouchers recording it, and so
    # does any amount paid by several vouchers (SOCSO and SKBBK separately). The figures planned before are kept, so
    # unlinking can put them back, and so is what this voucher replaced, for unlinking it while it is the last voucher
    # to change the amount. An amount that is just the other vouchers' total (one linked before planned figures were
    # kept, unlinked and linked again) isn't a plan, so what was planned stays unknown.
    n, total = _voucher_total(c, pid, p["direction"])
    total = amount if total is None else total
    if amount is not None and (p["amount"] is None or p["amount_is_estimate"] or n > 1) and total > 0:
        undo = json.dumps({"entry": entry_id, **{k: p[k] for k in LINK_REPLACES}})
        others = _voucher_total(c, pid, p["direction"], leave_out=entry_id)[1]
        plan = int(others is None or not db.same_amount(p["amount"], others))
        c.execute(
            """UPDATE payments SET planned_amount = CASE WHEN planned_is_estimate IS NULL AND ? THEN amount ELSE planned_amount END,
               planned_is_estimate = CASE WHEN planned_is_estimate IS NULL AND ? THEN amount_is_estimate ELSE planned_is_estimate END,
               amount = ?, amount_is_estimate = 0, undo_link = ? WHERE id = ?""", (plan, plan, total, undo, pid))
    if einvoice and not p["einvoice_ref"]:
        c.execute("UPDATE payments SET einvoice_ref = ? WHERE id = ?", (einvoice, pid))


def _voucher_total(c, pid, direction, leave_out=None):
    """(how many SQL payment vouchers are linked, what they add up to), leaving out the entry whose id is leave_out. A
    voucher changed in SQL counts once, at its latest figure, and money coming back (a refund receipt) is taken off."""
    n, total = c.execute(
        """SELECT (SELECT COUNT(*) FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') = 'payment' AND id IS NOT ?),
                  SUM(CASE WHEN direction IS NOT NULL AND direction != ? THEN -amount ELSE amount END)
           FROM sql_entries WHERE id IN (SELECT MAX(id) FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') = 'payment'
                                         AND id IS NOT ? GROUP BY doc_no)""", (pid, leave_out, direction, pid, leave_out)).fetchone()
    return n, (None if total is None else round(total, 2))


def _after_unlink(c, pid, entry=None):
    """A bank line, or an SQL voucher (entry, its id), was taken off the payment. When that voucher was the last one to
    change the amount, the amount goes back to exactly what it replaced. Otherwise it goes back to the vouchers still
    linked, or else to the figure planned before links replaced it (when known) and any bank lines left; the same rule
    as linking applies: one voucher alone doesn't replace a firm amount. A paid date that came from the bank or SQL
    stays only while a linked line or voucher still shows it; one typed in stays."""
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    n, total = _voucher_total(c, pid, p["direction"])
    voucher = entry is not None
    undo = json.loads(p["undo_link"] or "{}")
    if voucher:  # what the last voucher replaced no longer holds once any voucher is unlinked
        c.execute("UPDATE payments SET undo_link = NULL WHERE id = ?", (pid,))
    firm = p["planned_is_estimate"] == 0 and p["planned_amount"] is not None  # replaced only because of a 2nd voucher
    if voucher and undo.get("entry") == entry:
        c.execute(f"UPDATE payments SET {', '.join(k + ' = ?' for k in LINK_REPLACES)} WHERE id = ?",
                  (*(undo[k] for k in LINK_REPLACES), pid))
        if not n:
            statements.take_line_total(c, pid)
    elif voucher and (n > 1 or (n == 1 and not firm)) and total and total > 0:
        c.execute("UPDATE payments SET amount = ?, amount_is_estimate = 0 WHERE id = ?", (total, pid))
    elif not n or (voucher and n == 1):
        if p["planned_is_estimate"] is not None:
            c.execute("""UPDATE payments SET amount = planned_amount, amount_is_estimate = planned_is_estimate,
                         planned_amount = NULL, planned_is_estimate = NULL WHERE id = ?""", (pid,))
        statements.take_line_total(c, pid)
    if p["paid_source"] not in ("bank", "sql"):
        return
    lines = statements.paying_dates(c, pid)
    vouchers = [r[0] for r in c.execute(
        "SELECT doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') = 'payment'", (pid,))]
    if p["paid_date"] in (lines if p["paid_source"] == "bank" else vouchers):
        return
    paid, source = (max(lines), "bank") if lines else (min(vouchers), "sql") if vouchers else (None, None)
    c.execute("UPDATE payments SET paid_date = ?, paid_source = ? WHERE id = ?", (paid, source, pid))


OVERSEAS_PROVIDERS = ("ANTHROPIC", "CLAUDE", "GOOGLE", "OPENAI", "CHATGPT", "MICROSOFT", "ADOBE", "ZOOM", "CANVA", "DROPBOX", "HOSTGATOR")


def _guess_category(text):
    t = (text or "").upper()
    for words, cat in ((OVERSEAS_PROVIDERS + ("SUBSCRIPTION",), "claim_overseas"), (("CLAIM",), "claim"), (("SALARY",), "salary"),
                       (("STAMP", "SETEM", "CP204", "CP500", "TAX INSTAL"), "other"),  # LHDN, but not the month's PCB
                       (("KWSP", "PERKESO", "LHDN", "HASIL", "SOCSO"), "statutory"),
                       (("RENTAL",), "rental"), (("TNB", "UNIFI", "TM TECHNOLOGY"), "utility")):
        if any(w in t for w in words):
            return cat
    return "other"


@app.get("/api/sql/entries")
def sql_entries():
    c = con()
    eid = request.args["entity"]
    imports = rows(c.execute("SELECT * FROM sql_imports WHERE entity_id = ? ORDER BY id DESC LIMIT 20", (eid,)))
    unlinked = rows(c.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND status = 'unlinked' ORDER BY doc_date", (eid,)))
    linked, corrections = sqlimport.linked_vouchers(c, eid), sqlimport.corrections(c, eid)
    for u in unlinked:
        _note_linked(u, linked)
        u["correction"] = u["id"] in corrections
    months = sorted({u["doc_date"][:7] for u in unlinked})
    cands = sqlimport.candidates(c, eid, sqlimport.months_of([{"date": m + "-01"} for m in months])) if months else []
    other = _taken_back(c, rows(c.execute(
        """SELECT s.*, t.title AS task_title, t.month AS task_month, p.description AS payment_desc
           FROM sql_entries s LEFT JOIN tasks t ON t.id = s.task_id LEFT JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = ? AND s.kind IN ('journal', 'invoice') ORDER BY s.doc_date DESC LIMIT 200""", (eid,))))
    einv = _taken_back(c, rows(c.execute(
        """SELECT id, entity_id, doc_no, doc_date, description, payee, amount, einvoice, einvoice_status, einvoice_link, kind,
           payment_id FROM sql_entries WHERE entity_id = ? AND (einvoice IS NOT NULL OR einvoice_status IS NOT NULL)
           ORDER BY doc_date DESC LIMIT 200""", (eid,))))
    on_payments = rows(c.execute(
        """SELECT s.*, p.description AS payment_desc, p.month AS payment_month FROM sql_entries s JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = ? ORDER BY s.doc_date DESC, s.id DESC LIMIT 300""", (eid,)))
    ignored = rows(c.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND status = 'ignored' ORDER BY doc_date DESC", (eid,)))
    return jsonify({"imports": imports, "unlinked": unlinked, "candidates": cands, "documents": other, "einvoices": einv,
                    "linked": on_payments, "ignored": ignored})


def _payment_from_entry(c, s, category=None):
    """Adds an SQL voucher that isn't in the tracker (a claim, an advance, a one-off bill) as a paid payment."""
    acct = c.execute("SELECT id, currency FROM accounts WHERE entity_id = ? ORDER BY id LIMIT 1", (s["entity_id"],)).fetchone()
    direction = s["direction"] or "out"
    category = "receipt" if direction == "in" else (category or _guess_category(s["description"]))
    pid = c.execute(
        """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
           paid_source, sql_ref, einvoice_ref, direction, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sql', ?, ?, ?, ?)""",
        (s["entity_id"], s["doc_date"][:7], acct["id"] if acct else None, category,
         s["description"] or s["payee"] or s["doc_no"], s["amount"], acct["currency"] if acct else "MYR",
         s["doc_date"], s["doc_date"], s["doc_no"], s["einvoice"], direction, db.now())).lastrowid
    c.execute("UPDATE sql_entries SET payment_id = ?, status = 'linked' WHERE id = ?", (pid, s["id"]))
    db.log(c, f"Created payment from SQL entry {s['doc_no']}")
    return pid


def _link_entry(c, s, pid):
    if s["kind"] == "invoice":  # a customer invoice stays an invoice; it is the receipt's sales invoice, not a voucher
        c.execute("UPDATE sql_entries SET payment_id = ? WHERE id = ?", (pid, s["id"]))
        return
    c.execute("UPDATE sql_entries SET payment_id = ?, status = 'linked' WHERE id = ?", (pid, s["id"]))
    _add_sql_ref(c, pid, s["doc_no"], s["amount"], s["einvoice"], s["doc_date"] if s["kind"] == "payment" else None, s["id"])


@app.post("/api/sql/entries/create-all")
def sql_create_all():
    c = con()
    eid = request.get_json()["entity_id"]
    # Only real bank vouchers (PV, OR...); anything of unknown type stays for a person to decide.
    unlinked = c.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND status = 'unlinked' AND COALESCE(kind, 'payment') = 'payment'"
                         " AND direction IS NOT NULL", (eid,)).fetchall()
    by_ref, done = sqlimport.payments_by_ref(c, eid), set(sqlimport.linked_vouchers(c, eid))
    corrections = sqlimport.corrections(c, eid)
    created = linked = left = 0
    skipped = []
    for s in unlinked:
        no = s["doc_no"].upper()
        if no in done:
            left += 1  # its number is already linked: changed in SQL since, for a person to check
            continue
        # A voucher already named on a payment (its number typed in the SQL ref box) is linked, not added again.
        if no in by_ref:
            _link_entry(c, s, by_ref[no]["id"])
            linked += 1
        elif s["id"] in corrections:
            skipped.append(s["doc_no"])  # probably a correction (no money moved): for a person to ignore
            continue
        else:
            _payment_from_entry(c, s)
            created += 1
        done.add(no)
    matched = _rematch(c, eid)  # the new payments can now explain bank lines imported earlier
    c.commit()
    return jsonify({"created": created, "linked": linked, "left": left, "corrections": skipped, "bank_lines_matched": matched})


@app.post("/api/sql/entries/ignore")
def sql_ignore_all():
    """Ignores the entries listed (Ignore all, for the probable corrections) that are still not linked."""
    ids = [int(i) for i in request.get_json().get("ids") or []]
    c = con()
    q = ",".join("?" * len(ids))
    nos = [r["doc_no"] for r in c.execute(f"SELECT doc_no FROM sql_entries WHERE status = 'unlinked' AND id IN ({q})", ids)] if ids else []
    if nos:
        c.execute(f"UPDATE sql_entries SET status = 'ignored' WHERE status = 'unlinked' AND id IN ({q})", ids)
        db.log(c, f"Ignored SQL entries: {', '.join(nos)}")
    c.commit()
    return jsonify({"ignored": len(nos)})


def _rematch(c, entity_id, with_counts=False):
    """Matches every statement of the company again, then marks bank charges and own-account transfers."""
    sts = c.execute("SELECT s.id FROM statements s JOIN accounts a ON a.id = s.account_id WHERE a.entity_id = ?",
                    (entity_id,)).fetchall()
    matched = sum(statements.auto_match(c, s["id"]) for s in sts)
    no_docs = sum(statements.classify(c, s["id"]) for s in sts)
    return (matched, no_docs) if with_counts else matched


def _match_payments(c, entity_id, payment_ids):
    """Looks for the bank lines of just these payments, now that SQL has given them an amount or a paid date.
    Other lines waiting to be explained are left alone (one may have been undone by hand)."""
    if not payment_ids:
        return 0
    sts = c.execute("SELECT s.id FROM statements s JOIN accounts a ON a.id = s.account_id WHERE a.entity_id = ?",
                    (entity_id,)).fetchall()
    return sum(statements.auto_match(c, s["id"], set(payment_ids)) for s in sts)


@app.post("/api/statements/rematch")
def statements_rematch():
    c = con()
    matched, no_docs = _rematch(c, request.get_json()["entity_id"], with_counts=True)
    c.commit()
    return jsonify({"matched": matched, "no_docs": no_docs})


@app.post("/api/sql/entries/<int:sid>")
def sql_entry_update(sid):
    b = request.get_json()
    c = con()
    s = c.execute("SELECT * FROM sql_entries WHERE id = ?", (sid,)).fetchone() or abort(404)
    matched = 0
    if b.get("payment_id"):
        if s["kind"] == "invoice" and not c.execute("SELECT 1 FROM payments WHERE id = ? AND entity_id = ? AND direction = 'in'",
                                                    (b["payment_id"], s["entity_id"])).fetchone():
            return err("A customer invoice can only be linked to money received by the same company.")
        if s["payment_id"] and s["payment_id"] != int(b["payment_id"]):
            _unlink_entry(c, s)
        _link_entry(c, s, b["payment_id"])
        desc = c.execute("SELECT description FROM payments WHERE id = ?", (b["payment_id"],)).fetchone()[0]
        db.log(c, f"Linked SQL entry {s['doc_no']} to payment: {desc}")
        matched = _match_payments(c, s["entity_id"], {int(b["payment_id"])})
    elif "create_payment" in b:
        pid = _payment_from_entry(c, s, b["create_payment"].get("category"))
        matched = _match_payments(c, s["entity_id"], {pid})
    elif b.get("status") == "ignored":
        c.execute("UPDATE sql_entries SET status = 'ignored' WHERE id = ?", (sid,))
        db.log(c, f"Ignored SQL entry {s['doc_no']}")
    c.commit()
    return jsonify({"ok": True, "bank_lines_matched": matched})


@app.post("/api/sql/entries/<int:sid>/unlink")
def sql_entry_unlink(sid):
    c = con()
    s = c.execute("SELECT * FROM sql_entries WHERE id = ?", (sid,)).fetchone() or abort(404)
    if not s["payment_id"]:
        return err(f"{s['doc_no']} isn't linked to a payment.")
    desc, removed = _unlink_entry(c, s)
    c.commit()
    return jsonify({"ok": True, "doc_no": s["doc_no"], "payment": desc, "removed": removed})


@app.post("/api/sql/entries/<int:sid>/unignore")
def sql_entry_unignore(sid):
    c = con()
    s = c.execute("SELECT * FROM sql_entries WHERE id = ?", (sid,)).fetchone() or abort(404)
    if s["status"] == "ignored":
        c.execute("UPDATE sql_entries SET status = 'unlinked' WHERE id = ?", (sid,))
        db.log(c, f"SQL entry {s['doc_no']} no longer ignored")
    c.commit()
    return jsonify({"ok": True, "doc_no": s["doc_no"]})


def _unlink_entry(c, s):
    """Takes an SQL voucher off its payment and puts it back under 'not linked'. The payment's SQL ref and e-Invoice
    go back to the vouchers still linked (other numbers typed in the box stay), then its amount and paid date.
    A payment made from this voucher (Create payment) with nothing added since is removed. Returns (the payment's
    description, whether it was removed)."""
    pid = s["payment_id"]
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone()
    if s["kind"] == "invoice":  # only the link goes: the receipt's amount, SQL ref and dates were never taken from it
        c.execute("UPDATE sql_entries SET payment_id = NULL WHERE id = ?", (s["id"],))
        db.log(c, f"Unlinked SQL invoice {s['doc_no']} from receipt: {p['description']}")
        return p["description"], False
    c.execute("UPDATE sql_entries SET payment_id = NULL, status = 'unlinked' WHERE id = ?", (s["id"],))
    if _made_from(c, p, s):
        c.execute("DELETE FROM payments WHERE id = ?", (pid,))
        db.log(c, f"Unlinked SQL entry {s['doc_no']} and removed the payment made from it: {p['description']}")
        return p["description"], True
    left = c.execute("SELECT doc_no, einvoice FROM sql_entries WHERE payment_id = ? ORDER BY id", (pid,)).fetchall()
    ref = p["sql_ref"]
    if s["doc_no"].upper() not in {r["doc_no"].upper() for r in left}:  # the same number may still be linked (changed in SQL)
        ref = re.sub(rf"(?<![\w-]){re.escape(s['doc_no'])}(?![\w-])", "", ref or "", flags=re.I)
        ref = re.sub(r"\s*[,;](\s*[,;])+\s*", ", ", ref).strip(" ,;") or None
    for r in left:
        if r["doc_no"].upper() not in sqlimport.refs_of(ref):
            ref = f"{ref}, {r['doc_no']}" if ref else r["doc_no"]
    einv = p["einvoice_ref"]
    if s["einvoice"] and einv == s["einvoice"]:
        einv = next((r["einvoice"] for r in left if r["einvoice"]), None)
    c.execute("UPDATE payments SET sql_ref = ?, einvoice_ref = ? WHERE id = ?", (ref, einv, pid))
    _after_unlink(c, pid, entry=s["id"])
    db.log(c, f"Unlinked SQL entry {s['doc_no']} from payment: {p['description']}")
    return p["description"], False


def _made_from(c, p, s):
    """True when the payment is just what _payment_from_entry made from this voucher: no payee, the voucher's details,
    nothing typed in since, and no other voucher, bank line or document."""
    made = (p["payee_id"] is None and p["paid_source"] == "sql" and p["description"] == (s["description"] or s["payee"] or s["doc_no"])
            and (p["amount"], p["due_date"], p["einvoice_ref"]) == (s["amount"], s["doc_date"], s["einvoice"])
            and (p["sql_ref"] or "").upper() == s["doc_no"].upper() and not (p["notes"] or p["bank_ref"] or p["difference_note"]))
    return made and not any(c.execute(f"SELECT 1 FROM {t} WHERE payment_id = ?", (p["id"],)).fetchone()
                            for t in ("sql_entries", "statement_lines", "documents"))


# ---------- audit pack, backup, activity ----------

@app.post("/api/audit-pack")
def audit_pack():
    b = request.get_json()
    c = con()
    e = entity(c, int(b["entity_id"]))
    try:
        path = auditpack.build(c, e, month_from(b.get("month")))
    except auditpack.PackError as ex:
        return err(str(ex))
    db.log(c, f"Built audit pack {path.name}")
    c.commit()
    return jsonify({"name": path.name, "url": _pack_url(path)})


def _pack_url(path):
    return f"/api/audit-pack/file?name={path.parent.name}/{path.name}"


@app.get("/api/audit-readiness")
def audit_readiness():
    """Before you print (auditpack.readiness): what a month still needs for a clean audit pack."""
    c = con()
    e = entity(c, int(request.args.get("entity_id") or request.args["entity"]))
    month = month_from(request.args.get("month"))
    r = auditpack.readiness(c, e, month)
    if r["pack"]:
        r["pack"]["url"] = _pack_url(PACKS_DIR / e["code"] / r["pack"]["name"])
    held = c.execute("SELECT COUNT(*) FROM payments WHERE entity_id = ? AND month = ?", (e["id"], month)).fetchone()[0]
    return jsonify({"entity": dict(e), "month": month, "label": db.month_label(month), "set_up": _set_up(c, e["id"], month),
                    "payments": held, "closed_at": db.closed_at(c, e["id"], month), **r})


@app.get("/api/audit-pack/file")
def audit_pack_file():
    p = (PACKS_DIR / request.args["name"]).resolve()
    if PACKS_DIR.resolve() not in p.parents or not p.exists():
        abort(404)
    return send_file(p)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _entity_arg(c):
    return entity(c, id_from(request.args.get("entity_id") or request.args.get("entity") or ""))


@app.get("/api/export/month.xlsx")
def export_month():
    """The month report as an Excel file, built in memory (reports.month_workbook)."""
    c = con()
    e = _entity_arg(c)
    month = month_from(request.args.get("month"))
    data = reports.workbook_bytes(reports.month_workbook(c, e, month))
    return send_file(io.BytesIO(data), mimetype=XLSX, as_attachment=True, download_name=reports.month_report_name(e, month))


@app.get("/api/export/budget.xlsx")
def export_budget():
    """The month's stored budget as an Excel file; the usual error when none is set up."""
    c = con()
    e = _entity_arg(c)
    month = month_from(request.args.get("month"))
    as_at = day_from(request.args["as_at"]) if request.args.get("as_at") else None
    try:
        wb = reports.budget_workbook(c, e, month, as_at)
    except LookupError as ex:
        return err(str(ex), 404)
    return send_file(io.BytesIO(reports.workbook_bytes(wb)), mimetype=XLSX, as_attachment=True,
                     download_name=reports.budget_report_name(e, month))


@app.post("/api/auditor-export")
def auditor_export():
    """Builds a fresh audit pack and a zip for the auditor (reports.auditor_package) and logs it."""
    b = _body()
    c = con()
    e = entity(c, id_from(str(b.get("entity_id"))))
    month = month_from(b.get("month"))
    try:
        path, n, left_out = reports.auditor_package(c, e, month)
    except auditpack.PackError as ex:
        return err(str(ex))
    db.log(c, f"Built auditor package {path.name} ({n} files{f', {left_out} left out' if left_out else ''}), with a fresh audit pack")
    c.commit()
    return jsonify({"name": path.name, "url": f"/api/auditor-export/file?name={path.parent.name}/{path.name}", "files": n,
                    "left_out": left_out})


@app.get("/api/auditor-export/file")
def auditor_export_file():
    p = (EXPORTS_DIR / request.args["name"]).resolve()
    if EXPORTS_DIR.resolve() not in p.parents or p.suffix != ".zip" or not p.exists():
        abort(404)
    return send_file(p, as_attachment=True)


@app.get("/api/audit-packs")
def list_packs():
    """The packs built, newest first: for one company and month (entity, month), else the 30 latest of all."""
    if request.args.get("entity"):
        found = db.packs_of(entity(con(), int(request.args["entity"])), month_from(request.args.get("month")))[::-1]
    else:
        found = sorted(PACKS_DIR.glob("*/*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]
    return jsonify([{"name": p.name, "url": _pack_url(p), "at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}
                    for p in found])


MIN_PASSWORD = 12


def _write_backup(zf, snap):
    zf.write(snap, "records.db")
    for p in (DATA_DIR / "documents").rglob("*"):
        if p.is_file():
            zf.write(p, str(p.relative_to(DATA_DIR)))


def _encrypted_zip(target, snap, password):
    """Writes the backup as an AES-256 zip (7-Zip opens it) under a temporary name, reopens it with the password and
    tests every entry, and only then gives it its name. A file that fails is deleted. The password is passed in bytes
    and not kept."""
    part = target.with_name(target.name + ".part")
    try:
        with pyzipper.AESZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as z:
            z.setpassword(password)
            _write_backup(z, snap)
        with pyzipper.AESZipFile(part) as z:
            z.setpassword(password)
            if z.testzip() is not None or "records.db" not in z.namelist():
                raise ValueError("the finished file did not pass its check")
        os.replace(part, target)
    except Exception:
        part.unlink(missing_ok=True)
        raise


@app.post("/api/backup")
def backup():
    """A backup zip in the backups folder: with {"password": ...} (at least MIN_PASSWORD characters, typed each time,
    never stored or logged) an AES-256 encrypted one, which is also the only kind copied to backup_dir; without, a
    plain one that stays on this PC."""
    b = request.get_json(silent=True)
    password = b.get("password") if isinstance(b, dict) else None
    if password is not None and (not isinstance(password, str) or len(password) < MIN_PASSWORD):
        return err(f"The password needs at least {MIN_PASSWORD} characters.")
    encrypted = password is not None
    pw = password.encode("utf-8") if encrypted else None
    del password, b
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    target = BACKUP_DIR / f"HR-Records backup {stamp}{' (encrypted)' if encrypted else ''}.zip"
    snap = BACKUP_DIR / "records-snapshot.db"
    try:
        src = db.connect()
        dst = sqlite3.connect(snap)
        src.backup(dst)  # consistent copy even while the app is running
        dst.close()
        src.close()
        if encrypted:
            _encrypted_zip(target, snap, pw)
        else:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
                _write_backup(z, snap)
    except Exception as ex:
        if not encrypted:
            target.unlink(missing_ok=True)
        return err(f"The backup was not made: {ex if isinstance(ex, OSError) else 'something went wrong writing the file'}.", 500)
    finally:
        snap.unlink(missing_ok=True)  # the unencrypted snapshot never stays on disk
        pw = None
    copied = failed = not_copied = None
    folder = SETTINGS.get("backup_dir")
    if folder and not encrypted:
        not_copied = f"Saved on this PC only. It was not copied to {folder} because it is not encrypted."
    elif folder:
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
            copied = str(shutil.copy2(target, folder))
        except OSError as ex:
            failed = ex
    c = con()  # logged either way: the backup is made on this PC even when the copy fails (nextup reads this line)
    db.log(c, nextup.BACKED_UP + target.name + (f" (copy to {folder} failed)" if failed else "")
           + (" (not copied: not encrypted)" if not_copied else ""))
    c.commit()
    if failed:
        return jsonify({"file": str(target), "encrypted": encrypted, "warning": f"Backup saved on this PC, but copying to {folder} failed: {failed}"})
    return jsonify({"file": str(target), "encrypted": encrypted, "copied": copied, "not_copied": not_copied})


@app.post("/api/settings/backup-dir")
def set_backup_dir():
    """Where encrypted backups are also copied (empty: nowhere). An absolute Windows path outside the records folder,
    made if it doesn't exist. Saved in settings.json with the other keys kept."""
    b = request.get_json(silent=True)
    path = b.get("backup_dir") if isinstance(b, dict) else None
    path = path.strip().strip('"') if isinstance(path, str) else None
    if path is None:
        return err("Give the folder as text.")
    if path:
        w = PureWindowsPath(path)
        if not (w.drive and w.root):
            return err("Give the full path of the folder, starting with the drive letter, for example D: and then the folders.")
        here, there = os.path.normcase(os.path.realpath(DATA_DIR)), os.path.normcase(os.path.realpath(path))  # junctions followed
        if there == here or there.startswith(here + os.sep):
            return err("Choose a folder outside the records folder, so a backup is not kept beside what it protects.")
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            return err(f"That folder can't be used: {ex}")
    saved = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8")) if config.SETTINGS_FILE.exists() else {}
    saved["backup_dir"] = path
    config.save_settings(saved)
    SETTINGS["backup_dir"] = path
    c = con()
    db.log(c, f"Backup folder set to {path}" if path else "Backup folder cleared")
    c.commit()
    return jsonify({"backup_dir": path})


@app.get("/api/activity")
def activity():
    c = con()
    return jsonify(rows(c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 200")))


@app.get("/api/integrity")
def integrity():
    """Re-checks every stored document against its upload fingerprint."""
    c = con()
    bad = [dict(d) for d in c.execute("SELECT * FROM documents") if not verify(d)]
    return jsonify({"checked": c.execute("SELECT COUNT(*) FROM documents").fetchone()[0], "problems": bad})


def already_running(port):
    """True when another copy of the app holds the port. On Windows two servers can otherwise share a port,
    and an old copy would keep answering some requests with outdated code."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def main():
    if already_running(SETTINGS["port"]):
        print(f"\n  HR Payments is already running at http://127.0.0.1:{SETTINGS['port']}.\n"
              "  Close the other HR Payments window first if you want to restart it.\n")
        return
    db.init()
    print(f"\n  HR Payments is running at http://127.0.0.1:{SETTINGS['port']}\n  Records folder: {DATA_DIR}\n  Close this window to stop it.\n")
    app.run(host="127.0.0.1", port=SETTINGS["port"], debug=False, threaded=False)


if __name__ == "__main__":
    main()
