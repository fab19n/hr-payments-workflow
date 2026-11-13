"""Local web app. Listens on 127.0.0.1 only, so nothing outside this PC can reach it."""
import functools
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

from . import (appsettings, audit, auditpack, auditread, checklistbook, config, budget as stored, db, masters, nextup, recon, reports,
               monthly, partybook, rulebook, rules, sqlimport, statements)
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


def audited_read(kind):
    """Marks a GET route that hands over a file (a document, an audit pack, an export): when it succeeds, an 'opened'
    event goes into the audit trail. Only for requests the browser says come from this app itself (Sec-Fetch-Site
    same-origin, or none for a link typed or opened from a bookmark), so another website can't fill the trail."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            g.read_kind = kind
            return fn(*a, **kw)
        wrapper.audited_read = kind
        return wrapper
    return deco


@app.after_request
def log_read(resp):
    kind = g.pop("read_kind", None)
    if kind and 200 <= resp.status_code < 300 and request.headers.get("Sec-Fetch-Site", "none") in ("same-origin", "none"):
        try:
            c = db.connect()
            try:
                eid = request.args.get("entity_id", type=int)
                c.arm("user", f"Opened {kind}", route=request.url_rule.rule if request.url_rule else None, entity_id=eid)
                name = resp.headers.get("Content-Disposition", "")
                audit.event(c, "read", kind, {"path": request.full_path.rstrip("?"), "file": name.split("filename=")[-1].strip('"') if "filename=" in name else None},
                            entity_id=eid)
                c.commit()
            finally:
                c.close()
        except sqlite3.Error:
            pass  # a busy records.db never stops a download; the read just isn't noted
    return resp


def con():
    # One connection per request, closed afterwards; an open connection keeps records.db locked on Windows.
    if "con" not in g:
        g.con = db.connect()
        if request.method in ("GET", "HEAD"):
            # Looking at a page never changes the records, so another website can't make it do so through a link.
            g.con.execute("PRAGMA query_only = ON")
        else:
            g.con.arm(**_trail_context())
    return g.con


IMPORTS = ("/api/statements", "/api/sql/apply")  # requests whose changes the trail shows as an import


def _trail_context():
    """Who, how and why for the audit trail, for a request that may change the records: the Windows user (audit.who),
    the source (an automatic set-up the page asks for, an import, else the user), the route, the company and the reason
    the page sent. Only those keys are read from the body (a backup's password is never touched)."""
    b = request.get_json(silent=True) if request.is_json else None
    b = b if isinstance(b, dict) else {}
    source = "import" if request.path in IMPORTS else "auto" if b.get("auto") is True else "user"
    try:
        eid = int(b.get("entity_id") if b.get("entity_id") is not None else request.form.get("entity_id"))
    except (TypeError, ValueError):
        eid = None
    reason = b.get("reason") if isinstance(b.get("reason"), str) and b.get("reason").strip() else None
    return {"source": source, "action": f"{request.method} {request.path}",
            "route": request.url_rule.rule if request.url_rule else None, "entity_id": eid,
            "reason": reason.strip()[:500] if reason else None}


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
    ents = rows(c.execute("SELECT * FROM entities ORDER BY sort, id"))
    R = rulebook.get(c)
    for e in ents:
        e["accounts"] = rows(c.execute("SELECT * FROM accounts WHERE entity_id = ? ORDER BY sort, id", (e["id"],)))
    return jsonify({
        "entities": ents, "doc_types": R.doc_types, "categories": R.categories,
        "category_info": {k: {"active": t["active"], "direction": t["direction"], "system": t["system"]} for k, t in R.types.items()},
        "doc_info": {k: {"active": d["active"], "from_sql": d["from_sql"], "system": d["system"]} for k, d in R.docs.items()},
        "required": {k: (R.set_for(k) or R.set_for("other") or {"docs": []})["docs"] for k in R.types}, "sql_only": sorted(R.sql_only),
        "data_dir": str(DATA_DIR), "backup_dir": SETTINGS.get("backup_dir") or "", "settings": appsettings.values(),
        **_meta_monthly(c),
        "parties": rows(c.execute("""SELECT id, entity_id, kind, name, short_name, sql_code, active FROM parties
                                     ORDER BY name COLLATE NOCASE, id""")) if partybook.ready(c) else [],
    })


def _meta_monthly(c):
    """The joiner and leaver reminders (for the recurring payment drawer's note) and every checklist code in use with
    its latest title and companies (for Setup's filing words)."""
    B = checklistbook.get(c)
    people = []
    for p in B.people():
        t = B.people_term(p["key"], "9999-12")
        people.append({"key": p["key"], "kind": p["kind"], "short_name": p.get("short_name"),
                       "title": t["title"] if t else None, "active": bool(t)})
    codes = {}
    if B.from_tables:
        names = {r["id"]: r["code"] for r in c.execute("SELECT id, code FROM entities")}
        for (eid, code), it in sorted(B.items.items(), key=lambda kv: kv[1]["id"]):
            codes.setdefault(code, [it["name"] or code, []])[1].append(names.get(eid, "?"))
    return {"people_tasks": people, "checklist_codes": {k: f"{n} ({', '.join(cs)})" for k, (n, cs) in codes.items()}}


def docs_for(c, field, ident):
    out = rows(c.execute(f"""SELECT * FROM documents WHERE {field} = ? AND replaced_by IS NULL AND removed_at IS NULL
                             ORDER BY uploaded_at""", (ident,)))
    for d in out:
        d["label"] = rulebook.get(c).doc_label(d["doc_type"])
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
        p["required"] = rulebook.get(c).required_docs(p["category"], e["uses_sql"], p["month"], p["entity_id"])
        p["bank_lines"] = rows(c.execute("SELECT id, txn_date, amount, description FROM statement_lines WHERE payment_id = ?", (p["id"],)))
        p["bank_total"] = db.linked_total(c, p)
        p["sql_entries"] = rows(c.execute(
            "SELECT id, doc_no, doc_date, amount, direction, kind FROM sql_entries WHERE payment_id = ? ORDER BY doc_date, id", (p["id"],)))
        journals = [x for x in p["sql_entries"] if x["kind"] == "journal"] if partybook.ready(c) else []
        for x in journals:  # a journal is shown for what it moves on the bank, as a voucher for its amount
            x["dockey"] = c.execute("SELECT dockey FROM sql_entries WHERE id = ?", (x["id"],)).fetchone()[0]
        _journal_moves(c, p["entity_id"], journals, as_amount=True)
        for x in journals:
            del x["dockey"]
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
    for e in c.execute("SELECT * FROM entities WHERE active = 1 ORDER BY sort, id").fetchall():
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
    filed = "AND month NOT IN (SELECT month FROM months m WHERE m.entity_id = ? AND m.closed_at IS NOT NULL)"  # never a filed month
    pays = [p["id"] for p in c.execute(f"SELECT * FROM payments WHERE entity_id = ? AND month < ? {filed}", (e["id"], e["first_month"], e["id"]))
            if not db.recorded(c, p)]
    tasks = [t["id"] for t in c.execute(
        f"""SELECT id FROM tasks t WHERE entity_id = ? AND month < ? AND done_at IS NULL {filed}
           AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.task_id = t.id)
           AND NOT EXISTS (SELECT 1 FROM sql_entries s WHERE s.task_id = t.id)""", (e["id"], e["first_month"], e["id"]))]
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
    b = _body()
    if not isinstance(b.get("reason"), str) or not b["reason"].strip():
        return err("Say why you're making this change.")
    c = con()
    e = entity(c, id_from(str(b.get("entity_id"))))
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


def valid_cat(c, cat, direction):
    """The payment type to store for a payment made from a bank line or an SQL voucher: the one chosen when it is in
    use and of the payment's direction, else Money received (money in) or Other payment (money out)."""
    R = rulebook.get(c)
    if cat and R.active_type(cat) and R.direction(cat) == direction:
        return cat
    return "receipt" if direction == "in" else "other"


@app.post("/api/payments")
def create_payment():
    b = request.get_json()
    c = con()
    e = entity(c, int(b["entity_id"]))
    month = month_from(b.get("month"))
    acct = own_account(c, e, b.get("account_id"))
    if not b.get("description"):
        return err("Give the payment a description.")
    cat = b.get("category", "other")
    if not rulebook.get(c).active_type(cat):
        return err("Choose one of the payment types in use.")
    # Money in or out as posted (the page sends its type's, older callers may pair them freely); else the type's.
    way = b.get("direction") if b.get("direction") in ("in", "out") else rulebook.get(c).direction(cat)
    cur = c.execute(
        """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
           paid_source, direction, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (e["id"], month, acct["id"] if acct else None, cat, b["description"],
         b.get("amount"), acct["currency"] if acct else "MYR", b.get("due_date") or b.get("paid_date") or date.today().isoformat(),
         b.get("paid_date"), "manual" if b.get("paid_date") else None, way, b.get("notes"), db.now()))
    db.log(c, f"Added payment: {b['description']} ({month})")
    c.commit()
    return jsonify({"id": cur.lastrowid})


@app.patch("/api/payments/<int:pid>")
def update_payment(pid):
    b = request.get_json()
    c = con()
    p = c.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone() or abort(404)
    sets = {k: (v if v != "" else None) for k, v in b.items() if k in PAY_FIELDS}
    if "category" in sets and sets["category"] != p["category"]:
        if not rulebook.get(c).active_type(sets["category"]):
            return err("Choose one of the payment types in use.")
        if rulebook.get(c).direction(sets["category"]) != p["direction"]:
            return err(f"This payment is money {p['direction']}, so choose a payment type for money {p['direction']}.")
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
        freed = [r["id"] for r in c.execute("SELECT id FROM statement_lines WHERE payment_id = ?", (pid,))]
        lines = c.execute("UPDATE statement_lines SET payment_id = NULL, status = 'unmatched', undone_payment_id = ? "
                          "WHERE payment_id = ?", (pid, pid)).rowcount
        recon.line_changed(c, freed)
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
    c = con()
    R = rulebook.get(c)
    if doc_type not in R.docs:
        return err("Unknown document type.")
    if not R.docs[doc_type]["active"]:
        return err(f"{R.doc_label(doc_type)} is a document type no longer in use. Choose another.")
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
    db.log(c, f"Uploaded {R.doc_label(doc_type)} '{f.filename}' to {folder}")
    c.commit()
    return jsonify({"id": did})


@app.get("/api/documents/<int:did>/file")
@audited_read("document")
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
    db.log(c, f"Removed {rulebook.get(c).doc_label(d['doc_type'])} '{d['original_name']}' from {owner['name']} "
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
                "reference", "match_words", "active", "notes", "account_id", "start_date", "end_date", "direction", "party_id")


@app.post("/api/payees")
def save_payee():
    """Saves a recurring payment, and brings the change into the months already set up (db.sync_payee). Every field is
    checked (masters.payee_check). Stopping and using again have routes of their own that ask why; active is still
    taken here for older callers."""
    b = _body()
    c = con()
    vals = {k: b.get(k) for k in PAYEE_FIELDS if k in b and (k != "party_id" or partybook.ready(c))}
    if not isinstance(vals.get("name"), str) or not vals["name"].strip():
        return err("Give the payee a name.")
    vals.setdefault("desc_template", vals["name"].strip() + " - {M}")
    if not vals.get("desc_template"):
        vals["desc_template"] = vals["name"].strip() + " - {M}"
    # Money in takes a money-in payment type (Money received unless another is chosen) and a money-in type is money
    # in; money out takes a money-out type (Other payment instead of a money-in one).
    R = rulebook.get(c)
    is_in = lambda cat: cat in R.categories and R.direction(cat) == "in"
    way = vals.get("direction") or ("in" if is_in(vals.get("category")) else None)
    if way not in (None, "in", "out"):
        return err("Choose Money in or Money out.")
    if way == "in":
        vals["direction"] = "in"
        if not is_in(vals.get("category")):
            vals["category"] = "receipt"
    elif way == "out":
        vals["direction"] = "out"
        if is_in(vals.get("category")):
            vals["category"] = "other"
    old = c.execute("SELECT * FROM payees WHERE id = ?", (b["id"],)).fetchone() if b.get("id") else None
    if b.get("id") and not old:
        return err("This recurring payment has been removed.", 404)
    e = entity(c, old["entity_id"] if old else id_from(str(b.get("entity_id"))))
    if not old:
        d = appsettings.values()
        vals.setdefault("category", "receipt" if vals.get("direction") == "in" else valid_cat(c, d["payee_default_category"], "out"))
        vals.setdefault("due_day", d["payee_default_due_day"])
        vals.setdefault("month_offset", d["payee_default_month_offset"])
        if not vals.get("account_id"):
            acct = masters.first_active_account(c, e["id"])
            vals["account_id"] = acct["id"] if acct else None
    try:
        vals = masters.payee_check(c, e, vals, old)
    except masters.Refused as x:
        return err(str(x), x.status)
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
    return jsonify({"ok": True, "id": pid, "changes": changes, "kept": kept})


def _payee(c, pid):
    p = c.execute("SELECT * FROM payees WHERE id = ?", (pid,)).fetchone()
    if not p:
        abort(make_response(*err("This recurring payment has been removed.", 404)))
    return p


def _reason():
    r = _body().get("reason")
    if not isinstance(r, str) or not r.strip():
        abort(make_response(*err("Say why you're making this change.")))
    return r.strip()


@app.get("/api/payees/<int:pid>/usage")
def payee_usage(pid):
    c = con()
    _payee(c, pid)
    used = masters.payee_usage(c, pid)
    return jsonify({"used_by": used, "used_total": sum(n for _, n in used), "can_delete": not used})


def _payee_active(pid, active):
    _reason()
    c = con()
    old = _payee(c, pid)
    if bool(old["active"]) == active:
        return jsonify({"changes": [], "kept": []})
    c.execute("UPDATE payees SET active = ? WHERE id = ?", (int(active), pid))
    db.log(c, f"{'Using again' if active else 'Stopped'} recurring payment: {old['name']}")
    new = _payee(c, pid)
    changes, kept = db.sync_payee(c, old, new)
    changes += db.sync_reminders(c, new)
    c.commit()
    return jsonify({"changes": changes, "kept": kept})


@app.post("/api/payees/<int:pid>/stop")
def payee_stop(pid):
    """Stops a recurring payment (with the reason given): new months don't add it, and the months already set up lose
    its payments nobody has touched, from the current cycle on."""
    return _payee_active(pid, False)


@app.post("/api/payees/<int:pid>/use")
def payee_use(pid):
    return _payee_active(pid, True)


@app.delete("/api/payees/<int:pid>")
def payee_delete(pid):
    """Deletes a recurring payment nothing uses yet (no payments, salary advances, budget lines or reminders); one in
    use is stopped instead. The whole row stays in the audit trail."""
    _reason()
    c = con()
    p = _payee(c, pid)
    used = masters.payee_usage(c, pid)
    if used:
        return err(f"Used by {masters._words(used)}, so it can't be deleted. Stop using it instead.", 409)
    c.execute("DELETE FROM payees WHERE id = ?", (pid,))
    db.log(c, f"Deleted recurring payment: {p['name']}")
    c.commit()
    return jsonify({"ok": True})


def _advance_change(pid, write):
    """Runs a change to a payee's salary advances and brings it into the months already set up. The plans are taken
    before the change (db.plans), as the payee's own row doesn't show its advances (the bug the review found: taken
    after, they already held the change, and nothing was updated)."""
    c = con()
    p = _payee(c, pid)
    was = db.plans(c, p)
    try:
        out = write(c, p)
    except masters.Refused as x:
        return err(str(x), x.status)
    changes, kept = db.sync_payee(c, p, p, was_plans=was)
    changes += db.sync_reminders(c, p)
    c.commit()
    return jsonify({**(out or {}), "changes": changes, "kept": kept})


def _advance_text(a):
    return f"{a['monthly_deduction']:,.2f} a month, {a['start_month']} to {a['end_month']}"


@app.post("/api/payees/<int:pid>/advances")
def advance_add(pid):
    b = _body()

    def write(c, p):
        if p["category"] not in ("salary", "director"):
            raise masters.Refused("Salary advances are recovered from a salary or director's fee only.")
        v = masters.advance_check(c, b)
        aid = c.execute("INSERT INTO advances (payee_id, monthly_deduction, start_month, end_month, note) VALUES (?, ?, ?, ?, ?)",
                        (pid, v["monthly_deduction"], v["start_month"], v["end_month"], v.get("note"))).lastrowid
        db.log(c, f"Added a salary advance recovery for {p['name']}: {_advance_text(v)}")
        return {"advance": dict(c.execute("SELECT * FROM advances WHERE id = ?", (aid,)).fetchone())}
    return _advance_change(pid, write)


def _advance(c, aid):
    a = c.execute("SELECT * FROM advances WHERE id = ?", (aid,)).fetchone()
    if not a:
        abort(make_response(*err("This salary advance has been removed.", 404)))
    return a


@app.patch("/api/advances/<int:aid>")
def advance_update(aid):
    b = _body()
    c0 = con()
    a = _advance(c0, aid)

    def write(c, p):
        v = masters.advance_check(c, {k: b[k] for k in ("monthly_deduction", "start_month", "end_month", "note") if k in b}, old=a)
        if v:
            c.execute(f"UPDATE advances SET {', '.join(k + ' = ?' for k in v)} WHERE id = ?", (*v.values(), aid))
            db.log(c, f"Changed the salary advance recovery for {p['name']}: {_advance_text({**dict(a), **v})}")
        return {"advance": dict(c.execute("SELECT * FROM advances WHERE id = ?", (aid,)).fetchone())}
    return _advance_change(a["payee_id"], write)


@app.delete("/api/advances/<int:aid>")
def advance_delete(aid):
    _reason()
    c0 = con()
    a = _advance(c0, aid)

    def write(c, p):
        c.execute("DELETE FROM advances WHERE id = ?", (aid,))
        db.log(c, f"Removed the salary advance recovery for {p['name']}: {_advance_text(a)}")
    return _advance_change(a["payee_id"], write)


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
    removed = change_line(c, l, b)
    c.commit()
    return jsonify({"ok": True, "removed": removed})


def change_line(c, l, b):
    """Link a bank line to a payment, create a payment for it, undo it, or mark it as needing no documents (what the
    body b says), logging it. A change to the line's link or explanation clears its confirmation and its statement's
    sign-off. Returns the description of a payment removed because nothing is linked to it now, else None. The caller
    commits."""
    lid = l["id"]
    if b.get("create_payment"):
        cp = b["create_payment"]
        if cp.get("month"):
            month_from(cp["month"])
        # Planned as a blank amount, so the lines linked later make up its amount, and undoing them all blanks it again.
        cur = c.execute(
            """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
               paid_source, planned_is_estimate, direction, created_at)
               VALUES (?, ?, ?, ?, ?, ?, (SELECT currency FROM accounts WHERE id = ?), ?, ?, 'bank', 0, ?, ?)""",
            (l["entity_id"], cp.get("month") or l["month"], l["account_id"],
             valid_cat(c, cp.get("category", "other"), "in" if l["amount"] > 0 else "out"), cp["description"],
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
    now_ = c.execute("SELECT payment_id, status FROM statement_lines WHERE id = ?", (lid,)).fetchone()
    new = now_["payment_id"]
    if (now_["payment_id"], now_["status"]) != (l["payment_id"], l["status"]):
        recon.line_changed(c, [lid])
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
    return removed


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


# ---------- bank reconciliation (hrp/recon.py) ----------

def _recon_account():
    """The company and account a reconciliation request is for, from entity and account in the query (or JSON body):
    the account must belong to the company."""
    src = request.args if request.method == "GET" else (request.get_json(silent=True) or {})
    try:
        eid, aid = int(src.get("entity_id", src.get("entity", ""))), int(src.get("account_id", src.get("account", "")))
    except (TypeError, ValueError):
        abort(make_response(*err("Say which company and account.")))
    c = con()
    e = c.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone() or abort(404)
    a = c.execute("SELECT * FROM accounts WHERE id = ? AND entity_id = ?", (aid, eid)).fetchone() or abort(404)
    return e, a


def _recon_statement():
    """The company and statement a request is for (statement_id and entity_id): the statement must be one of the company's."""
    src = request.args if request.method == "GET" else (request.get_json(silent=True) or {})
    try:
        eid, sid = int(src.get("entity_id", src.get("entity", ""))), int(src.get("statement_id", src.get("statement", "")))
    except (TypeError, ValueError):
        abort(make_response(*err("Say which company and statement.")))
    c = con()
    e = c.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone() or abort(404)
    st = c.execute("SELECT s.* FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = ? AND a.entity_id = ?",
                   (sid, eid)).fetchone() or abort(404)
    return e, st


def _recon_do(action):
    """Runs a reconciliation action as one change: nothing is kept if it stops with an error."""
    c = con()
    try:
        out = action(c)
        c.commit()
        return jsonify(dict(out or {}, ok=True))
    except recon.ReconError as ex:
        c.rollback()
        return err(str(ex))
    except sqlite3.Error:
        c.rollback()
        return err("That couldn't be saved, so nothing was changed. Try again.")


@app.get("/api/recon/year")
def recon_year():
    e, a = _recon_account()
    try:
        year = int(request.args.get("year") or 0) or None
    except ValueError:
        return err("Say which year.")
    return jsonify(recon.year_view(con(), e, a, year))


@app.get("/api/recon/month")
def recon_month():
    e, a = _recon_account()
    return jsonify(recon.month_summary(con(), e, a, month_from(request.args.get("month"))))


@app.get("/api/recon/review")
def recon_review():
    e, st = _recon_statement()
    return jsonify(recon.review(con(), e, st))


@app.post("/api/recon/book-opening")
def recon_book_opening():
    e, a = _recon_account()
    b = request.get_json()
    month = month_from(b.get("month"))
    return _recon_do(lambda c: recon.set_book_opening(c, e, a, month, b.get("amount")))


@app.post("/api/recon/confirm")
def recon_confirm():
    e, st = _recon_statement()
    b = request.get_json()
    return _recon_do(lambda c: {"confirmed": recon.confirm_lines(c, st, b.get("line_ids") or [])})


@app.post("/api/recon/confirm-matched")
def recon_confirm_matched():
    e, st = _recon_statement()

    def go(c):
        done, skipped = recon.confirm_matched(c, st)
        return {"confirmed": done, "needs_date_tick": skipped}
    return _recon_do(go)


@app.post("/api/recon/apply")
def recon_apply():
    e, st = _recon_statement()
    b = request.get_json()

    def change(c, line, body):
        joined = c.execute(
            """SELECT l.*, s.month, s.account_id, a.entity_id FROM statement_lines l JOIN statements s ON s.id = l.statement_id
               JOIN accounts a ON a.id = s.account_id WHERE l.id = ?""", (line["id"],)).fetchone()
        change_line(c, joined, body)
    return _recon_do(lambda c: recon.apply_rows(c, e, st, b.get("rows"), b.get("checked") is True, change))


@app.post("/api/recon/sign-off")
def recon_sign_off():
    e, st = _recon_statement()
    return _recon_do(lambda c: recon.sign_off(c, e, st))


@app.post("/api/recon/undo-sign-off")
def recon_undo_sign_off():
    e, st = _recon_statement()
    return _recon_do(lambda c: recon.undo_sign_off(c, st))


@app.post("/api/recon/before-tracking")
def recon_before_tracking():
    e, st = _recon_statement()
    b = request.get_json()
    return _recon_do(lambda c: recon.sign_off_before_tracking(c, e, st, b.get("note"), b.get("checked") is True))


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
        lines = sqlimport.journal_lines(_pending_sql[token][2]) if token in _pending_sql else None
        text_lines = None if lines or token not in _pending_sql else sqlimport.text_journal_lines(_pending_sql[token][2])
        if text_lines:  # the lines as plain text have no document key: the person says which journal they belong to
            eid, filename = _pending_sql[token][:2]
            chosen = (request.get_json(silent=True) or {}).get("journal_id")
            return jsonify({"token": token, "entity_id": eid, "filename": filename, "records": [],
                            "journal_lines": _text_lines_preview(c, eid, text_lines, chosen)})
        if lines:  # the detail grid of a journal, not a listing: its lines are kept, not matched to payments
            eid, filename = _pending_sql[token][:2]
            return jsonify({"token": token, "entity_id": eid, "filename": filename, "records": [],
                            "journal_lines": _journal_notes(c, eid, lines)})
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
                    "mapping": mapping, "fields": sqlimport.ALL_FIELDS, "records": recs, "candidates": cands})


def _journal_header(c, eid, dockey):
    """The journal (its latest pasted row) that has this SQL document key, or None while its header isn't imported."""
    return c.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND kind = 'journal' AND dockey = ? ORDER BY import_id DESC, id DESC LIMIT 1",
                     (eid, dockey)).fetchone()


def _journal_text(c, mine, name, head, acct):
    """One sentence on what these lines of a journal do, in words for the person pasting: what they move on the bank
    account, and whether that counts in the bank reconciliation now or once the journal itself is pasted."""
    code = recon.bank_gl_code(c, acct) if acct else None
    net = round(sum(l["dr"] - l["cr"] for l in mine if code and l["code"] == code.strip().upper()), 2)
    if not code:
        text = f"Journal lines for {name}: Set the bank account's GL code in Setup. The lines are kept, and count once it is set."
    elif abs(net) < recon.TOL:
        on = sum(1 for l in mine if l["code"] == code.strip().upper())
        text = (f"Journal lines for {name}: none of the {len(mine)} lines is on the bank account {code}, so it moves no money. The lines are kept."
                if not on else f"Journal lines for {name}: its {on} lines on the bank account {code} net to nothing, so it moves no money. The lines are kept.")
    else:
        text = (f"Journal lines for {name}: bank account {code} {'+' if net > 0 else '-'}{abs(net):,.2f} "
                f"({'money in' if net > 0 else 'money out'}). "
                + ("Counts in the bank reconciliation once applied." if head
                   else "The journal itself isn't imported yet: the lines are kept and will count once the journal is pasted."))
    if head and head["payment_id"]:
        text += " It is linked to a payment, which keeps the amount it has: check that payment."
    return text


def _journal_notes(c, eid, lines):
    """What pasting these journal lines does, one sentence per journal."""
    acct = recon.cash_book_account(c, eid)
    notes = []
    for key in dict.fromkeys(l["dockey"] for l in lines):
        mine = [l for l in lines if l["dockey"] == key]
        head = _journal_header(c, eid, key)
        name = head["doc_no"] if head else f"journal key {key}"
        notes.append({"dockey": key, "doc_no": head["doc_no"] if head else None, "lines": len(mine),
                      "text": _journal_text(c, mine, name, head, acct)})
    return {"lines": len(lines), "notes": notes}


def _text_totals(lines):
    dr, cr = round(sum(l["dr"] for l in lines), 2), round(sum(l["cr"] for l in lines), 2)
    return dr, cr, abs(dr - cr) < 0.005


def _text_lines_preview(c, eid, lines, chosen):
    """The preview of journal lines pasted as plain text, which carry no document key. It offers the journals they could
    belong to (the latest paste of each journal that has a document key, those with the lines' total first), preselects
    the one journal with that total when there is only one, and gives the note for the journal chosen."""
    dr, cr, balanced = _text_totals(lines)
    out = {"lines": len(lines), "text_form": True, "total": dr, "balanced": balanced, "options": [], "chosen": None,
           "notes": [], "message": ""}
    if not balanced:
        out["message"] = f"These lines don't balance: debits add up to {dr:,.2f} and credits to {cr:,.2f}. They can't be kept."
        return out
    js = rows(c.execute("""SELECT id, doc_no, doc_date, amount FROM sql_entries s WHERE entity_id = ? AND kind = 'journal'
                           AND dockey IS NOT NULL AND dockey <> '' AND NOT EXISTS (SELECT 1 FROM sql_entries t
                           WHERE t.entity_id = s.entity_id AND t.kind = 'journal' AND t.doc_no = s.doc_no
                           AND (t.import_id > s.import_id OR (t.import_id = s.import_id AND t.id > s.id)))
                           ORDER BY doc_date DESC, id DESC LIMIT 300""", (eid,)))
    for j in js:
        j["match"] = abs(j["amount"] - dr) < 0.005
    out["options"] = sorted(js, key=lambda j: not j["match"])
    hits = [j for j in js if j["match"]]
    try:
        chosen = int(chosen) if chosen not in (None, "") else None
    except (TypeError, ValueError):
        chosen = None
    if chosen is None and len(hits) == 1:
        chosen = hits[0]["id"]
        out["message"] = f"Only {hits[0]['doc_no']} has a total of {dr:,.2f}, so it is chosen. Change it if these lines are from another journal."
    elif chosen is None:
        out["message"] = (f"{len(hits)} journals have a total of {dr:,.2f}: choose the one these lines are from." if hits
                          else f"No imported journal has a total of {dr:,.2f}: choose the journal these lines are from.")
    head = c.execute("SELECT * FROM sql_entries WHERE id = ? AND entity_id = ?", (chosen, eid)).fetchone() if chosen else None
    if head:
        out["chosen"] = head["id"]
        text = _journal_text(c, lines, head["doc_no"], head, recon.cash_book_account(c, eid))
        if abs(head["amount"] - dr) >= 0.005:
            text += f" These lines add up to {dr:,.2f}, but {head['doc_no']} is {head['amount']:,.2f}: choose the journal they come from."
        out["notes"] = [{"dockey": head["dockey"], "doc_no": head["doc_no"], "lines": len(lines), "text": text}]
    return out


def _apply_journal_lines(c, eid, filename, data, lines):
    """Keeps the pasted journal lines: the file as a document, as a listing is, and the lines by the journal's document
    key. Lines pasted again for a journal replace its earlier ones. The import's entries are the lines kept."""
    e = entity(c, eid)
    head = next(filter(None, (_journal_header(c, eid, l["dockey"]) for l in lines)), None)
    did = store(c, entity=e, month=head["doc_date"][:7] if head else f"{datetime.now():%Y-%m}", folder="_SQL exports",
                doc_type="sqlexport", filename=filename, data=data)
    imp = c.execute("INSERT INTO sql_imports (entity_id, filename, document_id, imported_at, entries, linked) VALUES (?, ?, ?, ?, ?, 0)",
                    (eid, filename, did, db.now(), len(lines))).lastrowid
    keys = list(dict.fromkeys(l["dockey"] for l in lines))
    for key in keys:
        c.execute("DELETE FROM sql_journal_lines WHERE entity_id = ? AND dockey = ?", (eid, key))
    for l in lines:
        c.execute("""INSERT INTO sql_journal_lines (entity_id, dockey, import_id, dtlkey, seq, code, description, project, dr, cr)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (eid, l["dockey"], imp, l["dtlkey"], l["seq"], l["code"], l["description"], l["project"], l["dr"], l["cr"]))
    names = ", ".join((_journal_header(c, eid, k) or {"doc_no": f"key {k}"})["doc_no"] for k in keys)
    db.log(c, f"Imported SQL journal lines '{filename}' for {e['code']}: {len(lines)} lines kept for {names}")
    c.commit()
    return len(lines)


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
    pending = _pending_sql.get(b["token"])
    lines = sqlimport.journal_lines(pending[2]) if pending else None
    text_lines = None if lines or not pending else sqlimport.text_journal_lines(pending[2])
    if text_lines:
        dr, cr, balanced = _text_totals(text_lines)
        if not balanced:
            return err(f"These lines don't balance: debits add up to {dr:,.2f} and credits to {cr:,.2f}. They can't be kept.")
        try:
            jid = int(b.get("journal_id"))
        except (TypeError, ValueError):
            return err("Choose the journal these lines are from.")
        head = c.execute("SELECT * FROM sql_entries WHERE id = ? AND kind = 'journal'", (jid,)).fetchone()
        if not head or head["entity_id"] != pending[0]:
            return err("That isn't one of this company's journals. Choose the journal these lines are from.")
        if not head["dockey"]:
            return err("Paste the journal list again so its document key is recorded, then paste the lines.")
        if abs(head["amount"] - dr) >= 0.005:
            return err(f"These lines add up to {dr:,.2f}, but {head['doc_no']} is {head['amount']:,.2f}: choose the journal they come from.")
        kept = _apply_journal_lines(c, pending[0], pending[1], pending[2], [{**l, "dockey": head["dockey"]} for l in text_lines])
        _pending_sql.pop(b["token"], None)
        return jsonify({"added": kept, "linked": 0, "skipped": 0, "bank_lines_matched": 0, "journal_lines": kept})
    if lines:
        kept = _apply_journal_lines(c, pending[0], pending[1], pending[2], lines)
        _pending_sql.pop(b["token"], None)
        return jsonify({"added": kept, "linked": 0, "skipped": 0, "bank_lines_matched": 0, "journal_lines": kept})
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
        extra = {f: r.get(f) or None for f in partybook.SQL_EXTRA}
        if any(extra.values()) and partybook.ready(c):  # kept from update 22; a later listing fills what an earlier lacked
            c.execute(f"""UPDATE sql_entries SET {', '.join(f'{f} = COALESCE({f}, ?)' for f in extra)}
                          WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ?""",
                      (*extra.values(), eid, r["doc_no"], r["date"], r["amount"]))
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
        "SELECT doc_date FROM sql_entries WHERE payment_id = ? AND COALESCE(kind, 'payment') IN ('payment', 'journal')", (pid,))]
    if p["paid_date"] in (lines if p["paid_source"] == "bank" else vouchers):
        return
    paid, source = (max(lines), "bank") if lines else (min(vouchers), "sql") if vouchers else (None, None)
    c.execute("UPDATE payments SET paid_date = ?, paid_source = ? WHERE id = ?", (paid, source, pid))


def _guess_category(text, c=None):
    """The payment type an SQL voucher's description suggests: the first of Setup's guesses (checklistbook; the code's
    own without a connection) with a word anywhere in it, in capitals; else other."""
    t = (text or "").upper()
    for words, cat in (checklistbook.get(c) if c is not None else checklistbook.FROZEN).guess:
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
    other = _taken_back(c, rows(c.execute(
        """SELECT s.*, t.title AS task_title, t.month AS task_month, p.description AS payment_desc
           FROM sql_entries s LEFT JOIN tasks t ON t.id = s.task_id LEFT JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = ? AND s.kind IN ('journal', 'invoice') ORDER BY s.doc_date DESC LIMIT 200""", (eid,))))
    on_payments = rows(c.execute(
        """SELECT s.*, p.description AS payment_desc, p.month AS payment_month FROM sql_entries s JOIN payments p ON p.id = s.payment_id
           WHERE s.entity_id = ? ORDER BY s.doc_date DESC, s.id DESC LIMIT 300""", (eid,)))
    for x in other:  # a journal pasted again after a change in SQL is a new row: say when its number is already linked
        if x["kind"] == "journal" and not x["payment_id"]:
            _note_linked(x, linked)
    _journal_moves(c, eid, other)
    _journal_moves(c, eid, on_payments, as_amount=True)
    # A journal that moves the bank is linked like a voucher, so the months of its payments are offered as well.
    months = sorted({u["doc_date"][:7] for u in unlinked} | {x["doc_date"][:7] for x in other
                                                            if x["kind"] == "journal" and x["bank_move"] and not x["payment_id"]})
    cands = sqlimport.candidates(c, eid, sqlimport.months_of([{"date": m + "-01"} for m in months])) if months else []
    einv = _taken_back(c, rows(c.execute(
        """SELECT id, entity_id, doc_no, doc_date, description, payee, amount, einvoice, einvoice_status, einvoice_link, kind,
           payment_id FROM sql_entries WHERE entity_id = ? AND (einvoice IS NOT NULL OR einvoice_status IS NOT NULL)
           ORDER BY doc_date DESC LIMIT 200""", (eid,))))
    ignored = rows(c.execute("SELECT * FROM sql_entries WHERE entity_id = ? AND status = 'ignored' ORDER BY doc_date DESC", (eid,)))
    return jsonify({"imports": imports, "unlinked": unlinked, "candidates": cands, "documents": other, "einvoices": einv,
                    "linked": on_payments, "ignored": ignored})


def _journal_moves(c, eid, entries, as_amount=False):
    """Gives each journal in the rows bank_move: what its pasted lines move on the bank account (money in above 0), or None
    when it moves nothing there. With as_amount (the rows are linked ones), a journal shows that as its amount and direction, as a voucher does."""
    if not any(x["kind"] == "journal" for x in entries):
        return
    acct = recon.cash_book_account(c, eid)
    moves = recon.journal_moves(c, eid, [x.get("dockey") for x in entries if x["kind"] == "journal"],
                                recon.bank_gl_code(c, acct) if acct else None)
    for x in entries:
        if x["kind"] == "journal":
            x["bank_move"] = moves.get(x.get("dockey"))
            if as_amount and x["bank_move"] is not None:
                x["amount"], x["direction"] = abs(x["bank_move"]), "in" if x["bank_move"] > 0 else "out"


def _payment_from_entry(c, s, category=None):
    """Adds an SQL voucher that isn't in the tracker (a claim, an advance, a one-off bill) as a paid payment."""
    acct = masters.first_active_account(c, s["entity_id"])  # the cash book account, as SQL's cash book listing is for it
    direction = s["direction"] or "out"
    category = "receipt" if direction == "in" else valid_cat(c, category or _guess_category(s["description"], c), "out")
    pid = c.execute(
        """INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
           paid_source, sql_ref, einvoice_ref, direction, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sql', ?, ?, ?, ?)""",
        (s["entity_id"], s["doc_date"][:7], acct["id"] if acct else None, category,
         s["description"] or s["payee"] or s["doc_no"], s["amount"], acct["currency"] if acct else "MYR",
         s["doc_date"], s["doc_date"], s["doc_no"], s["einvoice"], direction, db.now())).lastrowid
    # (a journal keeps its status, as an invoice does: it is still a journal, only linked)
    c.execute("UPDATE sql_entries SET payment_id = ?, status = CASE WHEN kind = 'journal' THEN status ELSE 'linked' END WHERE id = ?",
              (pid, s["id"]))
    db.log(c, f"Created payment from SQL entry {s['doc_no']}")
    return pid


def _as_voucher(c, s, strict=True):
    """The SQL entry as the payment it records: a voucher as it is; a journal that moves the bank (its pasted lines on the
    bank account's GL code) as a voucher for what it moves there, in the direction of its sign, not for its total. A
    journal that moves nothing there is refused (strict), or taken as it is."""
    if s["kind"] != "journal":
        return s
    move = recon.journal_move(c, s["entity_id"], s["dockey"]) if s["dockey"] else None
    if move is None:
        if strict:
            raise sqlimport.SqlImportError(f"{s['doc_no']} has no lines on the bank account, so it moves no money and can't be linked to a "
                                           "payment. Paste its lines from SQL first (and set the bank account's GL code in Setup).")
        return s
    return {**dict(s), "amount": round(abs(move), 2), "direction": "in" if move > 0 else "out"}


def _link_entry(c, s, pid):
    if s["kind"] == "invoice":  # a customer invoice stays an invoice; it is the receipt's sales invoice, not a voucher
        c.execute("UPDATE sql_entries SET payment_id = ? WHERE id = ?", (pid, s["id"]))
        return
    if s["kind"] == "journal":  # a journal that moves the bank is linked like a voucher, for what it moves there
        v = _as_voucher(c, s)
        c.execute("UPDATE sql_entries SET payment_id = ? WHERE id = ?", (pid, s["id"]))
        _add_sql_ref(c, pid, s["doc_no"], v["amount"], None, s["doc_date"], s["id"])
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
    if s["kind"] == "journal" and (b.get("payment_id") or "create_payment" in b):
        try:
            _as_voucher(c, s)
        except sqlimport.SqlImportError as ex:
            return err(str(ex))
    if b.get("payment_id"):
        if s["kind"] == "journal":
            v = _as_voucher(c, s)
            pay = c.execute("SELECT direction FROM payments WHERE id = ? AND entity_id = ?", (b["payment_id"], s["entity_id"])).fetchone()
            if pay and (pay["direction"] or "out") != v["direction"]:
                return err(f"{s['doc_no']} moves money {'in' if v['direction'] == 'in' else 'out'} on the bank account, "
                           "so it can't be linked to a payment going the other way.")
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
        pid = _payment_from_entry(c, _as_voucher(c, s), b["create_payment"].get("category"))
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
    return jsonify({"ok": True, "doc_no": s["doc_no"], "kind": s["kind"], "payment": desc, "removed": removed})


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
    c.execute("UPDATE sql_entries SET payment_id = NULL, status = CASE WHEN kind = 'journal' THEN status ELSE 'unlinked' END WHERE id = ?",
              (s["id"],))
    v = _as_voucher(c, s, strict=False)
    if s["kind"] == "journal":  # its lines may have been pasted again since: the payment keeps the amount it was made with
        v = {**dict(v), "amount": p["amount"]}
    if _made_from(c, p, v):
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
    audit.event(c, "pack", path.name, {"company": e["code"], "month": b.get("month"), "file": path.name,
                                       "sha256": audit.file_sha256(path), "size": path.stat().st_size}, entity_id=e["id"])
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
@audited_read("audit pack")
def audit_pack_file():
    p = (PACKS_DIR / request.args["name"]).resolve()
    if PACKS_DIR.resolve() not in p.parents or not p.exists():
        abort(404)
    return send_file(p)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _entity_arg(c):
    return entity(c, id_from(request.args.get("entity_id") or request.args.get("entity") or ""))


@app.get("/api/export/month.xlsx")
@audited_read("month export")
def export_month():
    """The month report as an Excel file, built in memory (reports.month_workbook)."""
    c = con()
    e = _entity_arg(c)
    month = month_from(request.args.get("month"))
    data = reports.workbook_bytes(reports.month_workbook(c, e, month))
    return send_file(io.BytesIO(data), mimetype=XLSX, as_attachment=True, download_name=reports.month_report_name(e, month))


@app.get("/api/export/budget.xlsx")
@audited_read("budget export")
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
    pack = db.packs_of(e, month)[-1]  # the fresh audit pack the package was built with, also kept in audit-packs
    audit.event(c, "pack", pack.name, {"company": e["code"], "month": month, "file": pack.name, "via": "auditor package",
                                       "sha256": audit.file_sha256(pack), "size": pack.stat().st_size}, entity_id=e["id"])
    audit.event(c, "export", path.name, {"kind": "auditor package", "company": e["code"], "month": month, "file": path.name,
                                         "files": n, "left_out": left_out, "sha256": audit.file_sha256(path),
                                         "size": path.stat().st_size}, entity_id=e["id"])
    c.commit()
    return jsonify({"name": path.name, "url": f"/api/auditor-export/file?name={path.parent.name}/{path.name}", "files": n,
                    "left_out": left_out})


@app.get("/api/auditor-export/file")
@audited_read("auditor package")
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
    # manifest.json: the audit trail's last entry and the snapshot's fingerprint, so a records.db or a trail rebuilt
    # later can be checked against what this backup holds.
    s = sqlite3.connect(snap)
    try:
        last = s.execute("SELECT id, hash, at FROM audit_tx ORDER BY id DESC LIMIT 1").fetchone() if audit.present(s) else None
    finally:
        s.close()
    zf.writestr("manifest.json", json.dumps({"made": datetime.now().isoformat(timespec="seconds"), "records_sha256": audit.file_sha256(snap),
                                             "audit_trail": {"last_entry": last[0], "hash": last[1], "at": last[2]} if last else None}, indent=2))
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
    n = 1  # a second backup in the same minute keeps the first (the trail records each by fingerprint)
    while target.exists():
        n += 1
        target = BACKUP_DIR / f"HR-Records backup {datetime.now():%Y%m%d-%H%M%S}{f'-{n}' if n > 2 else ''}{' (encrypted)' if encrypted else ''}.zip"
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
    audit.event(c, "backup", target.name, {"file": target.name, "encrypted": encrypted, "sha256": audit.file_sha256(target),
                                           "size": target.stat().st_size, "copied_to": folder if copied else None,
                                           "copy_failed": str(failed) if failed else None})
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
    before = SETTINGS.get("backup_dir") or ""
    saved["backup_dir"] = path
    config.save_settings(saved)
    SETTINGS["backup_dir"] = path
    c = con()
    db.log(c, f"Backup folder set to {path}" if path else "Backup folder cleared")
    audit.event(c, "settings", "backup_dir", {"before": before, "after": path})
    c.commit()
    return jsonify({"backup_dir": path})


def _setup_call(fn, preview=None):
    """Runs a Setup change; a refusal comes back as its plain sentence. preview: the change is made, what it did is
    returned, and it is all undone."""
    c = con()
    try:
        out = fn(c)
    except masters.Refused as x:
        c.rollback()
        rulebook.forget(c)
        checklistbook.forget(c)
        return err(str(x), x.status)
    if preview:
        c.rollback()
        rulebook.forget(c)
        checklistbook.forget(c)
        return jsonify({**out, "preview": True})
    c.commit()
    return jsonify(out if preview is None else {**out, "preview": False})


def _out_types(c):
    """The money-out payment types in use: what a new recurring payment may default to."""
    R = rulebook.get(c)
    return {k: t["label"] for k, t in R.types.items() if t["active"] and t["direction"] == "out"}


@app.get("/api/setup/required")
def setup_required():
    eid = request.args.get("entity", type=int)
    return _setup_call(lambda c: masters.required_view(c, eid))


@app.post("/api/setup/required")
def setup_required_save():
    b = _body()
    eid = b.get("entity_id") if isinstance(b.get("entity_id"), int) and not isinstance(b.get("entity_id"), bool) else None
    return _setup_call(lambda c: {"ok": True, "affected": masters.required_save(
        c, b.get("payment_type"), eid, b.get("docs"), b.get("from_month"))})


@app.get("/api/setup/checklist")
def setup_checklist():
    eid = request.args.get("entity", type=int)
    return _setup_call(lambda c: monthly.checklist_view(c, eid))


@app.post("/api/setup/checklist")
def setup_checklist_save():
    b = _body()
    if b.get("action") in ("stop", "use", "delete"):
        _reason()
    return _setup_call(lambda c: monthly.checklist_save(c, b), preview=b.get("preview") is True)


@app.get("/api/setup/reminders")
def setup_reminders():
    return _setup_call(monthly.reminders_view)


@app.post("/api/setup/reminders")
def setup_reminders_save():
    b = _body()
    if b.get("action") in ("stop", "use", "delete"):
        _reason()
    return _setup_call(lambda c: monthly.reminders_save(c, b), preview=b.get("preview") is True)


@app.post("/api/setup/<kind>/paste")
def setup_paste(kind):
    b = _body()
    return _setup_call(lambda c: partybook.paste(c, kind, b), preview=b.get("preview") is True)


@app.get("/api/setup/types")
def setup_types():
    return jsonify(masters.types())


@app.get("/api/setup/settings")
def setup_settings():
    return jsonify({"values": appsettings.values(), "fields": appsettings.fields(_out_types(con()))})


@app.patch("/api/setup/settings")
def setup_settings_save():
    b = _body()

    def run(c):
        try:
            v = appsettings.check(b.get("values") if isinstance(b.get("values"), dict) else {}, _out_types(c))
        except ValueError as x:
            raise masters.Refused(str(x))
        v = {k: x for k, x in v.items() if x != appsettings.get(k)}
        if v:
            appsettings.save(c, v)
            db.log(c, "Changed general settings: " + ", ".join(appsettings.SPEC[k][1].lower() for k in v))
        return {"values": appsettings.values()}
    return _setup_call(run)  # values are checked before anything is saved


@app.get("/api/setup/<kind>")
def setup_list(kind):
    eid = request.args.get("entity", type=int)
    return _setup_call(lambda c: masters.listing(c, kind, eid))


@app.get("/api/setup/<kind>/<int:rid>")
def setup_record(kind, rid):
    return _setup_call(lambda c: masters.record(c, kind, rid))


@app.post("/api/setup/<kind>")
def setup_create(kind):
    b = _body()

    def run(c):
        rid = masters.create(c, kind, b.get("fields"), entity_id=b.get("entity_id") if isinstance(b.get("entity_id"), int) else None)
        return {"id": rid, **masters.record(c, kind, rid)}
    return _setup_call(run)


@app.patch("/api/setup/<kind>/<int:rid>")
def setup_update(kind, rid):
    b = _body()

    def run(c):
        notes = masters.update(c, kind, rid, b.get("fields"))
        return {**masters.record(c, kind, rid), "notes": notes}
    return _setup_call(run)


@app.post("/api/setup/<kind>/<int:rid>/<act>")
def setup_active(kind, rid, act):
    if act not in ("stop", "use"):
        return err("There is no such action.", 404)
    _reason()
    return _setup_call(lambda c: (masters.set_active(c, kind, rid, act == "use"), masters.record(c, kind, rid))[1])


@app.delete("/api/setup/<kind>/<int:rid>")
def setup_delete(kind, rid):
    _reason()
    return _setup_call(lambda c: (masters.delete(c, kind, rid), {"ok": True})[1])


@app.get("/api/audit/status")
def audit_status():
    """The audit trail's state: entries, changes made outside the app waiting to be accepted and the head-file check;
    with ?quick=1 (the Overview) only those, else also a check of the last 200 entries."""
    c = con()
    st = audit.status(c)
    if request.args.get("quick"):
        return jsonify(st)
    last = c.execute("SELECT after FROM audit_row WHERE tbl = 'audit' AND row_key = 'check' ORDER BY id DESC LIMIT 1").fetchone()
    return jsonify({**st, "check": audit.verify(c, last=200), "last_full_check": json.loads(last[0]) if last else None})


def _trail_filters():
    a = request.args
    f = {"q": (a.get("q") or "").strip()[:200], "source": a.get("source") or None, "tbl": a.get("tbl") or None,
         "before_id": a.get("before_id", type=int)}
    for k in ("from", "to"):
        f[k] = iso_day(a.get(k)) if a.get(k) else None
    eid = a.get("entity_id", type=int)
    f["entity_id"] = eid
    if f["source"] and f["source"] not in auditread.SOURCES:
        abort(make_response(*err("That isn't a source of changes.")))
    if f["tbl"] and f["tbl"] not in auditread.TABLE_LABELS:
        abort(make_response(*err("That isn't a kind of record.")))
    return f


@app.get("/api/audit")
def audit_entries():
    """Audit trail entries, newest first: filters from, to, entity_id, tbl, source, q; before_id for the next page."""
    labels = {"tables": {k: v[0] for k, v in auditread.TABLE_LABELS.items()}, "sources": auditread.SOURCES}
    return jsonify({**auditread.entries(con(), _trail_filters()), "labels": labels})


@app.get("/api/audit/tx/<int:tid>")
def audit_entry(tid):
    out = auditread.entry(con(), tid, show=bool(request.args.get("show")))
    return jsonify(out) if out else err("There is no such entry.", 404)


@app.get("/api/audit/record/<tbl>/<key>")
def audit_record(tbl, key):
    """One record's history (a payment, a recurring payment, a budget line...)."""
    if tbl not in auditread.TABLE_LABELS or len(key) > 100:
        return err("That isn't a record.", 404)
    return jsonify(auditread.history(con(), tbl, key, show=bool(request.args.get("show"))))


@app.get("/api/audit/outside")
def audit_outside():
    return jsonify(auditread.outside(con(), show=bool(request.args.get("show"))))


@app.post("/api/audit/check")
def audit_check():
    """The full check: every entry's fingerprint, the triggers, the head file, and each record against the trail.
    Recorded in the trail."""
    c = con()
    out = auditread.check(c)
    db.log(c, "Checked the audit trail: " + ("every entry checks out and every record matches it" if out["ok"] else
           f"{len(out['problems']) + out['replay']['count']} problem(s) found"))
    c.commit()
    return jsonify(out)


@app.get("/api/audit/export.xlsx")
@audited_read("audit trail export")
def audit_export():
    """The entries the filters find, as an Excel file: one row per field changed. Bank details and account numbers are
    left masked unless show=1."""
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font
    c = con()
    rows, cut = auditread.export_rows(c, _trail_filters(), show=bool(request.args.get("show")))
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit trail"
    ws.append(auditread.EXPORT_HEAD)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append([ILLEGAL_CHARACTERS_RE.sub("�", v) if isinstance(v, str) else v for v in r])  # control characters
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str) and cell.value[:1] in ("=", "+", "-", "@"):
                cell.data_type = "s"  # text as it is, never a formula (as the month report does)
    if cut:
        ws.append(["Only the newest 5,000 entries are in this file. Choose earlier dates to export the rest."])
    ws.freeze_panes = "A2"
    for col, width in zip("ABCDEFGHIJKLMN", (19, 14, 12, 9, 50, 30, 7, 10, 18, 30, 10, 22, 24, 24)):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"Audit trail {date.today():%Y-%m-%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/audit/accept-outside")
def audit_accept_outside():
    """Seals the changes made to records.db outside this app into the trail, with the reason typed (required)."""
    b = _body()
    reason, upto = b.get("reason"), b.get("upto_id")
    if not isinstance(reason, str) or not reason.strip():
        return err("Say why these changes were made outside the app.")
    if not isinstance(upto, int) or isinstance(upto, bool):
        return err("Say which changes were checked: open the audit trail again and accept from there.")
    c = con()
    n = audit.accept_outside(c, reason.strip()[:500], upto=upto)
    c.commit()
    return jsonify({"accepted": n})


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


def audit_warnings(trail):
    """What start-up found in the audit trail that the user should know, in plain words (printed in the app window).
    Each is also recorded in the trail itself."""
    if not trail:
        return []
    out = []
    if trail["outside"]:
        out.append(f"{trail['outside']} change(s) to records.db were made outside this app. Accept them with a reason:\n"
                   '  .venv\\Scripts\\python -m hrp.trail accept "why they were made"')
    head = trail.get("head") or {}
    if head.get("kind") == "behind":
        out.append("records.db is older than the last entry recorded beside it. That is expected after restoring a backup;\n"
                   "  otherwise entries may have been removed.")
    if head.get("kind") == "rewritten":
        out.append("the last entry recorded beside records.db has a different fingerprint inside it: the trail may have been rebuilt.")
    if trail.get("triggers_repaired"):
        out.append(f"{len(trail['triggers_repaired'])} audit trigger(s) were missing or changed and have been put back. Unless the app\n"
                   "  was just updated, records.db was edited outside the app, and changes made meanwhile were not recorded.")
    if trail.get("late_sealed"):
        out.append(f"{trail['late_sealed']} change(s) left unsealed by an unexpected stop were sealed now.")
    return out


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
    trail = db.init()
    for line in audit_warnings(trail):
        print("\n  Audit trail: " + line)
    print(f"\n  HR Payments is running at http://127.0.0.1:{SETTINGS['port']}\n  Records folder: {DATA_DIR}\n  Close this window to stop it.\n")
    app.run(host="127.0.0.1", port=SETTINGS["port"], debug=False, threaded=False)


if __name__ == "__main__":
    main()
