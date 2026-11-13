"""Setup › Monthly work: each company's monthly checklist and the joiner and leaver reminders (checklistbook holds them).

Every change takes effect from a payroll month the user chooses (owner decision, 12 Nov 2026), by default the earliest
month not filed, and never reaches a filed month: a change that would add, change or remove a checklist item in one is
refused. From that month on, the months already set up and not filed are brought into line: un-ticked items get the new
wording, due date and documents; a new item is added; a stopped one is removed where nothing is filed on it. Ticked
items stay as they are. Months not set up yet take the change when they are. How an item is shown done is looked up by
its own month, so a rule changed from a month on never alters the months before it.

A reminder is picked by the month of the person's start date or last day; a change brings the reminders of the people
it reaches into line through db.sync_reminders.

Stop using, Use again and Delete take a reason (the request carries it into the audit trail); an item or reminder can be
deleted only while nothing uses it and the app didn't bring it."""
import json
import re

from . import checklistbook, db, masters, rulebook
from .masters import MONTH, KEY, Refused, INTERNAL_DOCS

TITLE_MAX, DETAIL_MAX = 200, 2000
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ]{0,39}")
SUBMIT_MAX = 30


# ---------- shared ----------

def _int(v, label, lo, hi):
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise Refused(f"{label}: give a whole number from {lo} to {hi}.")
    return v


def _text(v, label, required=True, limit=TITLE_MAX):
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise Refused(f"{label}: this can't be empty.")
        return ""
    if not isinstance(v, str):
        raise Refused(f"{label}: give it as text.")
    v = v.strip()
    if len(v) > limit:
        raise Refused(f"{label}: that is too long.")
    return v


def _docs(con, v, keep=(), label="Documents"):
    """A list of document types a checklist item or reminder may ask for: in use (or already asked for), not the app's own."""
    R = rulebook.get(con)
    if v is None:
        return []
    if not isinstance(v, list) or len(set(map(str, v))) != len(v):
        raise Refused(f"{label}: choose each document once.")
    for d in v:
        if not isinstance(d, str) or d not in R.docs or d in INTERNAL_DOCS or not (R.docs[d]["active"] or d in keep):
            raise Refused(f"{label}: {d} isn't a document type in use.")
    return list(v)


def _from(con, b, entity_id):
    m = b.get("from_month")
    if not isinstance(m, str) or not MONTH.fullmatch(m):
        raise Refused("From which month: months are written like 2026-10.")
    last = masters._last_filed(con, entity_id)
    if last and m <= last:
        raise Refused(f"{db.month_label(last)} is filed, and filed months never change. Choose {db.month_label(db.shift_month(last, 1))} or later.")
    return m


def _filed_tasks(con, entity_id=None):
    sql = """SELECT t.id, t.entity_id, t.month, t.code, t.title, t.detail, t.due_date, t.required_docs, t.done_at, t.sort
             FROM tasks t JOIN months m ON m.entity_id = t.entity_id AND m.month = t.month WHERE m.closed_at IS NOT NULL"""
    rows = con.execute(sql + (" AND t.entity_id = ?" if entity_id is not None else ""),
                       (entity_id,) if entity_id is not None else ()).fetchall()
    return {r["id"]: tuple(r) for r in rows}


def _keep_filed(con, before, entity_id=None):
    """Refuses (so the whole change is undone) when a checklist item in a filed month was added, changed or removed."""
    after = _filed_tasks(con, entity_id)
    if after == before:
        return
    tid = next(iter(sorted(set(before) ^ set(after)) or [k for k in after if after[k] != before[k]]))
    row = after.get(tid) or before[tid]
    month, title = row[2], row[4]
    raise Refused(f"This would change {title} in {db.month_label(month)}, which is marked as filed. Choose a month after "
                  f"it, or reopen {db.month_label(month)} first.")


def _dated(con, table, key_col, key, values, m, in_use, cols, spread=False):
    """A change from month m: the term in force at m ends there and the new one runs from m until the next term planned
    after it, which stays as it was. spread (Stop using, Use again): the terms planned later are stopped, or used,
    too. Returns lines naming those later terms."""
    later = [r[0] for r in con.execute(f"SELECT from_month FROM {table} WHERE {key_col} = ? AND from_month > ? ORDER BY from_month",
                                       (key, m))]
    con.execute(f"UPDATE {table} SET to_month = ? WHERE {key_col} = ? AND from_month < ? AND (to_month IS NULL OR to_month > ?)",
                (m, key, m, m))
    con.execute(f"DELETE FROM {table} WHERE {key_col} = ? AND from_month = ?", (key, m))
    con.execute(f"INSERT INTO {table} ({key_col}, from_month, to_month, in_use, set_at, {', '.join(cols)}) "
                f"VALUES (?, ?, ?, ?, ?, {', '.join('?' * len(cols))})",
                (key, m, later[0] if later else None, in_use, db.now(), *[values[c] for c in cols]))
    if spread and later:
        con.execute(f"UPDATE {table} SET in_use = ? WHERE {key_col} = ? AND from_month > ?", (in_use, key, m))
    what = ("stopped too" if not in_use else "in use too") if spread else "kept as planned"
    return [f"The change planned from {db.month_label(x)}: {what}" for x in later]


def _live_at(terms, m):
    """(the term in force in month m or None, the first one planned after m or None)."""
    return (next((t for t in terms if checklistbook._live(t, m)), None),
            next((t for t in terms if t["from_month"] > m), None))


def _term_out(t):
    return {k: t[k] for k in t if k not in ("id", "item_id", "people_task_id", "set_at")} if t else None


# ---------- the monthly checklist ----------

TERM_COLS = ("due_offset", "due_day", "title", "detail", "docs", "deadline", "submit_as", "rule", "sort")


def _ent(con, entity_id):
    if isinstance(entity_id, bool) or not isinstance(entity_id, int):
        raise Refused("Choose a company.")
    e = con.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not e:
        raise Refused("There is no such company.", 404)
    return dict(e)


def _used(con, entity_id, code):
    return con.execute("SELECT COUNT(*) FROM tasks WHERE entity_id = ? AND code = ?", (entity_id, code)).fetchone()[0]


def _starter_norm(t):
    """A term's wording, due date, documents and rule, as comparable with a starter item's as given."""
    return (t.get("due_offset"), t.get("due_day"), t.get("title"), t.get("detail") or "", list(t.get("docs") or []),
            int(bool(t.get("deadline"))), t.get("submit_as") or None, _norm_rule(t.get("rule")), t.get("sort"))


def _replaceable(con, B, entity_id):
    """Whether a company's checklist may be replaced by a copy of another's: it is still, untouched, the starter list a
    company added in Setup was given (checklistbook.starter_items: the same items in the same order, each with one term,
    in use, worded as given; nothing built in), and no month has been set up with it yet. Any other checklist is kept:
    the copy adds to it, or is refused, as before."""
    mine = [it for (eid, _), it in B.items.items() if eid == entity_id]
    if not mine or any(it["system"] for it in mine) or con.execute("SELECT 1 FROM tasks WHERE entity_id = ?", (entity_id,)).fetchone():
        return False
    for it in mine:
        ts = B.terms.get(it["id"], [])
        if len(ts) != 1 or not ts[0]["in_use"] or ts[0]["to_month"] is not None:
            return False
    have = {it["code"]: (it["completion"], _starter_norm(B.terms[it["id"]][0])) for it in mine}
    uses_sql = con.execute("SELECT uses_sql FROM entities WHERE id = ?", (entity_id,)).fetchone()[0]
    # the list it was given went by whether it was kept in SQL Account then, which may have been changed since
    return any(have == {code: (kind, _starter_norm(term)) for code, kind, term in checklistbook.starter_items(con, u)}
               for u in dict.fromkeys((uses_sql, 1 - uses_sql)))


def _latest(B, it):
    ts = B.terms.get(it["id"], [])
    return ts[-1] if ts else None


def checklist_view(con, entity_id):
    e = _ent(con, entity_id)
    B, R = checklistbook.get(con), rulebook.get(con)
    if not B.from_tables:
        raise Refused("The checklist can be edited once the records are updated.", 409)
    items = []
    for (eid, code), it in B.items.items():
        if eid != entity_id:
            continue
        ts = B.terms.get(it["id"], [])
        now = ts[-1] if ts else None
        used = _used(con, eid, code)
        items.append({"id": it["id"], "code": code, "completion": it["completion"], "system": it["system"],
                      "in_use": bool(now and now["in_use"] and now["to_month"] is None), "used": used,
                      "can_delete": not used and not it["system"], "now": _term_out(now),
                      "history": [_term_out(t) for t in reversed(ts)]})
    items.sort(key=lambda x: ((x["now"] or {}).get("sort", 1 << 30), x["id"]))
    last = masters._last_filed(con, entity_id)
    others = []
    for o in con.execute("SELECT id, code, name FROM entities WHERE id != ? ORDER BY id", (entity_id,)):
        n = len(B.checklist(o, masters._first_open(con, o["id"])))
        if n:
            others.append({"id": o["id"], "code": o["code"], "name": o["name"], "items": n})
    docs = sorted(((k, d) for k, d in R.docs.items() if k not in INTERNAL_DOCS), key=lambda kv: (R.order(kv[0], 999), kv[1]["sort"]))
    return {"entity_id": entity_id, "code": e["code"], "name": e["name"],
            "default_from": masters._first_open(con, entity_id), "first_allowed": db.shift_month(last, 1) if last else None,
            "items": items,
            "completions": [{"key": k, "label": label, "code": code} for k, label, code in checklistbook.COMPLETIONS],
            "doc_types": [{"key": k, "label": d["label"], "active": d["active"]} for k, d in docs],
            "payment_types": [{"key": k, "label": t["label"], "active": t["active"], "direction": t["direction"]} for k, t in R.types.items()],
            "others": others, "replaceable": _replaceable(con, B, entity_id)}


def _rule(con, v, keep):
    """A payments rule from the page, checked; keep: the rule it replaces (its stopped types and documents may stay)."""
    if not isinstance(v, dict):
        raise Refused("Say which payments show the item done.")
    R = rulebook.get(con)
    keep = keep or {}
    cats = v.get("categories") or []
    if not isinstance(cats, list) or any(not isinstance(c, str) or c not in R.types or not (R.types[c]["active"] or c in keep.get("categories", ()))
                                         for c in cats):
        raise Refused("Payment types: choose ones in use.")
    direction = v.get("direction") or None
    if direction not in (None, "in", "out"):
        raise Refused("Money: choose in, out or either.")
    words = v.get("words") or []
    if not isinstance(words, list) or any(not isinstance(w, str) or not WORD.fullmatch(w.strip()) for w in words):
        raise Refused("Words: letters, digits and spaces only, up to 40 characters each.")
    words = list(dict.fromkeys(w.strip().upper() for w in words))
    docs = _docs(con, v.get("docs"), tuple(keep.get("docs", ())) + tuple(keep.get("on_item", ())), "Documents each payment needs")
    if not docs:
        raise Refused("Documents each payment needs: choose at least one.")
    on_item = v.get("on_item") or []
    if not isinstance(on_item, list) or any(d not in docs for d in on_item):
        raise Refused("Documents that may be filed on the item instead: choose among the documents each payment needs.")
    name = v.get("name")
    if not isinstance(name, list) or len(name) != 2 or not all(isinstance(n, str) and n.strip() for n in name):
        raise Refused("Say what one such payment is called, and several.")
    name = [_text(n, "What they are called") for n in name]
    if len(words) > 50 or len(set(cats)) > 100:
        raise Refused("Words: at most 50.")
    cats = list(dict.fromkeys(cats))
    none = v.get("none")
    none = _text(none, "With no such payment", required=False) or None
    out = {"categories": cats, "direction": direction, "words": words, "docs": docs, "on_item": list(dict.fromkeys(on_item)),
           "paid": bool(v.get("paid")), "none": none, "name": [name[0].strip(), name[1].strip()]}
    return out


def _norm_rule(r):
    if not r:
        return None
    return {"categories": list(r.get("categories") or []), "direction": r.get("direction") or None,
            "words": [w.upper() for w in r.get("words") or []], "docs": list(r.get("docs") or []),
            "on_item": list(r.get("on_item") or []), "paid": bool(r.get("paid")), "none": r.get("none") or None,
            "name": list(r.get("name") or [])}


def _term_fields(con, f, completion, keep=None):
    if not isinstance(f, dict):
        raise Refused("Nothing to save.")
    keep = keep or {}
    t = {"title": _text(f.get("title"), "Title"),
         "detail": _text(f.get("detail"), "Detail", required=False, limit=DETAIL_MAX),
         "due_offset": _int(f.get("due_offset", 0), "Due in", 0, 1),
         "due_day": _int(f.get("due_day"), "Due day", 1, 31),
         "docs": _docs(con, f.get("docs") or [], tuple(keep.get("docs", ())), "Documents the item asks for"),
         "deadline": 1 if f.get("deadline") in (True, 1, "1") else 0}
    if completion in checklistbook.STATEMENTS_ARG or completion == "pack":
        t["deadline"] = 0  # Next up shows these through its own rows (import, reconcile, the audit pack)
    t["submit_as"] = (_text(f.get("submit_as"), "Submitted as", required=False, limit=SUBMIT_MAX) or None) if t["deadline"] else None
    t["rule"] = _rule(con, f.get("rule"), keep.get("rule")) if completion == "payments" else None
    return t


def _slug(title, taken):
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30].strip("-") or "item"
    if not base[0].isalpha():
        base = "item-" + base
    if base.startswith(checklistbook.REMINDER_PREFIXES) or base in checklistbook.BUILT_IN:
        base = "item-" + base
    code, n = base, 2
    while code in taken:
        code, n = f"{base[:27]}-{n}", n + 1
    return code


def _in_use_spans(B, ent, skip=()):
    """{code: [(title, from, until)]}: the spans in which each of the company's items (but those in skip) is in use."""
    out = {}
    for (eid, c), it in B.items.items():
        if eid == ent["id"] and c not in skip:
            out[c] = [(t["title"], t["from_month"], t["to_month"]) for t in B.terms.get(it["id"], []) if t["in_use"]]
    return out


def _clash(spans, others):
    """Refuses when a title in spans ([(title, from, until)], an until of None runs on) is one in others has in an
    overlapping span: the lower-cased titles are compared, the same rule as the setup file's import
    (setupfile._same_title)."""
    for title, f, to in spans:
        low = title.strip().lower()
        if any(t2.strip().lower() == low and (to is None or to > f2) and (to2 is None or to2 > f) for t2, f2, to2 in others):
            raise Refused(f"Another item in use is called {title}. Give this one another title.")


def _same_title(B, ent, spans, code):
    """Refuses when a title this item will have in use after the write (spans: [(title, from, until)]) is one another of
    the company's items has in use in an overlapping span, so no two items in use ever share a title."""
    _clash(spans, [s for c, ss in _in_use_spans(B, ent, {code}).items() for s in ss])


def _bring_into_line(con, ent, code, m):
    """The months already set up from m on, not filed (nor before the first month tracked), brought into line with the
    item's terms. Returns (lines, how many items changed)."""
    checklistbook.forget(con)
    B = checklistbook.get(con)
    lines, n = [], 0
    for r in con.execute("SELECT month FROM months WHERE entity_id = ? AND month >= ? AND closed_at IS NULL ORDER BY month",
                         (ent["id"], m)).fetchall():
        month = r["month"]
        if db.before_tracking(ent, month):
            continue
        t = next((t for t in B.checklist(ent, month) if t["code"] == code), None)
        have = con.execute("SELECT * FROM tasks WHERE entity_id = ? AND month = ? AND code = ?", (ent["id"], month, code)).fetchone()
        label = db.month_label(month)
        if t:
            want = {"title": t["title"], "detail": t["detail"], "due_date": db.due(month, t["due_offset"], t["due_day"]),
                    "required_docs": json.dumps(t["docs"]), "sort": t["sort"]}
            if not have:
                con.execute("""INSERT INTO tasks (entity_id, month, code, title, detail, due_date, required_docs, sort)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (ent["id"], month, code, *want.values()))
                lines.append(f"{label}: added {t['title']}, due {db.day_label(want['due_date'])}")
                n += 1
                continue
            diff = {k: v for k, v in want.items() if have[k] != v}
            if not diff:
                continue
            if have["done_at"]:
                if set(diff) - {"sort"}:
                    lines.append(f"{label}: kept {have['title']} as it was, as it is ticked")
                continue
            con.execute(f"UPDATE tasks SET {', '.join(k + ' = ?' for k in diff)} WHERE id = ?", (*diff.values(), have["id"]))
            what = (f"now due {db.day_label(want['due_date'])}" if "due_date" in diff
                    else "updated" if set(diff) - {"sort"} else None)
            if what:
                lines.append(f"{label}: {t['title']} {what}")
            n += 1
        elif have:
            if have["done_at"]:
                lines.append(f"{label}: kept {have['title']}, as it is ticked")
            elif db.held(con, have["id"]):
                lines.append(f"{label}: kept {have['title']}, as a document is filed on it: tick it once it's done")
            else:
                con.execute("DELETE FROM tasks WHERE id = ?", (have["id"],))
                lines.append(f"{label}: removed {have['title']}")
                n += 1
    return lines, n


def checklist_save(con, b):
    """Adds, changes, stops, uses again, deletes or copies checklist items (see the module's notes). Returns
    {lines, affected, item_id}."""
    if not isinstance(b, dict):
        raise Refused("Nothing to save.")
    action = b.get("action")
    ent = _ent(con, b.get("entity_id"))
    eid = ent["id"]
    B = checklistbook.get(con)
    if not B.from_tables:
        raise Refused("The checklist can be edited once the records are updated.", 409)
    it = None
    if action in ("change", "stop", "use", "delete"):
        iid = b.get("item_id")
        it = next((x for x in B.items.values() if x["id"] == iid and x["entity_id"] == eid), None) if isinstance(iid, int) else None
        if not it:
            raise Refused("This checklist item has been removed.", 404)
    elif action not in ("add", "copy"):
        raise Refused("Choose what to do.")
    if action == "delete":
        used = _used(con, eid, it["code"])
        if it["system"]:
            raise Refused("The app brought this item, so it can't be deleted. Stop using it instead.", 409)
        if used:
            raise Refused(f"Used by {used} checklist item{'s' if used != 1 else ''} in months set up, so it can't be deleted. "
                          "Stop using it instead.", 409)
        con.execute("DELETE FROM checklist_terms WHERE item_id = ?", (it["id"],))
        con.execute("DELETE FROM checklist_items WHERE id = ?", (it["id"],))
        db.log(con, f"Checklist {ent['code']}: deleted {it['name']}")
        checklistbook.forget(con)
        return {"lines": [], "affected": {"tasks": 0, "payments": 0, "now_missing": 0, "now_complete": 0}, "item_id": None}
    m = _from(con, b, eid)
    before_filed = _filed_tasks(con, eid)
    before = masters._statuses(con, eid, m)
    lines, n, done = [], 0, []
    if action == "copy":
        src_id = b.get("copy_from")
        src = _ent(con, src_id) if src_id != eid else None
        if not src:
            raise Refused("Choose another company to copy from.")
        replace = _replaceable(con, B, eid)
        if B.checklist(ent, m) and not replace:
            raise Refused(f"{ent['code']} already has a checklist from {db.month_label(m)}. Change its items instead.")
        terms = B.checklist(src, m)
        if not terms:
            raise Refused(f"{src['code']} has no checklist in {db.month_label(m)}.")
        # each copied item is in use from m until the next change planned for the company's own item of that code, if
        # any; its titles then may not be another item's in use over the same months (the items replaced don't count)
        new = {}
        for t in terms:
            mine = None if replace else B.items.get((eid, t["code"]))
            nxt = mine and _live_at(B.terms.get(mine["id"], []), m)[1]
            new[t["code"]] = (t["title"], m, nxt["from_month"] if nxt else None)
        kept = {} if replace else _in_use_spans(B, ent)
        for c in new:
            if c in kept:  # what this copy writes over goes from m: its terms planned later stay
                kept[c] = [s for s in kept[c] if s[1] > m]
        for c, span in new.items():
            _clash([span], [s for c2, ss in kept.items() if c2 != c for s in ss] + [s for c2, s in new.items() if c2 != c])
        if replace:  # the starter list goes: the copy takes its place
            con.execute("DELETE FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?)", (eid,))
            con.execute("DELETE FROM checklist_items WHERE entity_id = ?", (eid,))
            db.log(con, f"Checklist {ent['code']}: the starter checklist removed, to be replaced by {src['code']}'s")
        for t in terms:
            sit = B.items[(src["id"], t["code"])]
            vals = {k: t[k] for k in TERM_COLS}
            vals["docs"] = list(t["docs"])
            mine = None if replace else B.items.get((eid, t["code"]))
            if mine:
                if mine["completion"] != sit["completion"]:
                    raise Refused(f"{ent['code']} already has an item {t['code']} shown done another way.")
                _write_term(con, mine["id"], vals, m, 1)
            else:
                checklistbook.add_item(con, eid, t["code"], sit["completion"], 0, {**vals, "rule": vals["rule"]}, m, 1)
            done.append(t["code"])
        db.log(con, f"Checklist {ent['code']}: copied {len(terms)} items from {src['code']}, from {db.month_label(m)}")
        item_id = None
    else:
        if action == "add":
            f = b.get("fields") or {}
            completion = f.get("completion") if isinstance(f, dict) else None
            if completion not in [k for k, _, _ in checklistbook.COMPLETIONS]:
                raise Refused("Say how the item is shown done.")
            vals = _term_fields(con, f, completion)
            _same_title(B, ent, [(vals["title"], m, None)], None)
            taken = {code for (e2, code) in B.items if e2 == eid}
            code = next((c for c, k in checklistbook.BUILT_IN.items() if k == completion), None)
            if code and code in taken:
                raise Refused(f"{ent['code']} already has this built-in item. Use it again instead.")
            code = code or _slug(vals["title"], taken)
            vals["sort"] = 1 + max([t["sort"] for x in B.items.values() if x["entity_id"] == eid for t in B.terms.get(x["id"], [])] or [-1])
            item_id = checklistbook.add_item(con, eid, code, completion, 0, vals, m, 1)
            db.log(con, f"Checklist {ent['code']}: added {vals['title']}, from {db.month_label(m)}")
        else:
            ts = B.terms.get(it["id"], [])
            cur, nxt = _live_at(ts, m)
            base = cur or nxt or ts[-1]
            if action == "change":
                vals = _term_fields(con, b.get("fields"), it["completion"], base)
                vals["sort"] = base["sort"]
                in_use = base["in_use"]
                same = cur and all((_norm_rule(vals[k]) == _norm_rule(cur[k])) if k == "rule" else vals[k] == cur[k] for k in TERM_COLS)
                if same:
                    raise Refused("Nothing changes: this is what the item is from that month already.")
                if in_use:  # the new wording runs from m until the next change planned, which stays as it was
                    _same_title(B, ent, [(vals["title"], m, nxt["from_month"] if nxt else None)], it["code"])
                what = "changed"
            else:
                in_use = 1 if action == "use" else 0
                if not in_use and not (cur and cur["in_use"]):
                    raise Refused("It is already stopped from then." if cur else "It isn't in use then.")
                if in_use and cur and cur["in_use"]:
                    raise Refused("It is already in use from then.")
                vals = {k: base[k] for k in TERM_COLS}
                if in_use:  # the changes planned later are put in use too: each title checked over its own months
                    _same_title(B, ent, [(vals["title"], m, nxt["from_month"] if nxt else None)]
                                + [(t["title"], t["from_month"], t["to_month"]) for t in ts if t["from_month"] > m], it["code"])
                what = "in use again" if in_use else "stopped"
            lines += _write_term(con, it["id"], vals, m, in_use, spread=action in ("stop", "use"))
            db.log(con, f"Checklist {ent['code']}: {vals['title']} {what}, from {db.month_label(m)}")
            item_id, code = it["id"], it["code"]
        done.append(code)
    for code in done:
        more, k = _bring_into_line(con, ent, code, m)
        lines += more
        n += k
    for x in lines:
        db.log(con, f"Checklist {ent['code']} in {x}")
    _keep_filed(con, before_filed, eid)
    checklistbook.forget(con)
    after = masters._statuses(con, eid, m)
    moved = [pid for pid in after if after[pid] != before.get(pid)]
    return {"lines": lines, "item_id": item_id,
            "affected": {"tasks": n, "payments": len(moved), "now_missing": sum(before.get(p) == "complete" for p in moved),
                         "now_complete": sum(after[p] == "complete" for p in moved)}}


def _write_term(con, item_id, vals, m, in_use, spread=False):
    v = dict(vals)
    v["docs"] = json.dumps(v["docs"])
    v["rule"] = json.dumps(v["rule"]) if v.get("rule") else None
    v["detail"] = v.get("detail") or ""
    out = _dated(con, "checklist_terms", "item_id", item_id, v, m, in_use, TERM_COLS, spread)
    con.execute("UPDATE checklist_items SET name = ? WHERE id = ?", (vals["title"], item_id))
    checklistbook.forget(con)
    return out


# ---------- joiner and leaver reminders ----------

PEOPLE_COLS = ("days", "salary_over", "title", "detail", "docs")


def reminders_view(con):
    B, R = checklistbook.get(con), rulebook.get(con)
    if not B.from_tables:
        raise Refused("The reminders can be edited once the records are updated.", 409)
    out = []
    for p in con.execute("SELECT * FROM people_tasks ORDER BY sort, id").fetchall():
        ts = B._pterms.get(p["key"], [])
        now = ts[-1] if ts else None
        used = _reminder_used(con, p["kind"], p["key"])
        out.append({"id": p["id"], "key": p["key"], "kind": p["kind"], "short_name": p["short_name"], "system": p["system"],
                    "in_use": bool(now and now["in_use"] and now["to_month"] is None), "used": used,
                    "can_delete": not used and not p["system"], "now": _term_out(now),
                    "history": [_term_out(t) for t in reversed(ts)]})
    last = masters._last_filed(con, None)
    docs = sorted(((k, d) for k, d in R.docs.items() if k not in INTERNAL_DOCS), key=lambda kv: (R.order(kv[0], 999), kv[1]["sort"]))
    return {"default_from": masters._first_open(con, None), "first_allowed": db.shift_month(last, 1) if last else None,
            "rules": out, "doc_types": [{"key": k, "label": d["label"], "active": d["active"]} for k, d in docs]}


def _reminder_used(con, kind, key):
    return con.execute("SELECT COUNT(*) FROM tasks WHERE code GLOB ?", (f"{kind}-{key}-[0-9]*",)).fetchone()[0]


def _template(v, label, allowed, limit):
    v = _text(v, label, limit=limit)
    if "{" in v.replace("{" + allowed + "}", "") or "}" in v.replace("{" + allowed + "}", ""):
        raise Refused(f"{label}: only {{{allowed}}} may be written in braces.")
    return v


def _people_fields(con, f, keep=None):
    if not isinstance(f, dict):
        raise Refused("Nothing to save.")
    over = f.get("salary_over")
    if over in (None, ""):
        over = None
    elif isinstance(over, bool) or not isinstance(over, (int, float)) or not 0 <= over < 1e9:
        raise Refused("Salary over: give an amount, or leave it empty for any salary.")
    return {"days": _int(f.get("days"), "Days", -366, 366), "salary_over": over,
            "title": _template(f.get("title"), "Title", "name", TITLE_MAX),
            "detail": _template(f.get("detail"), "Detail", "date", DETAIL_MAX),
            "docs": _docs(con, f.get("docs") or [], tuple((keep or {}).get("docs", ())), "Documents")}


def _short_name(v):
    return _text(v, "Short name", required=False, limit=80) or None


def reminders_save(con, b):
    if not isinstance(b, dict):
        raise Refused("Nothing to save.")
    B = checklistbook.get(con)
    if not B.from_tables:
        raise Refused("The reminders can be edited once the records are updated.", 409)
    action = b.get("action")
    p = None
    if action in ("change", "stop", "use", "delete"):
        p = con.execute("SELECT * FROM people_tasks WHERE id = ?", (b.get("id"),)).fetchone() if isinstance(b.get("id"), int) else None
        if not p:
            raise Refused("This reminder has been removed.", 404)
        p = dict(p)
    elif action != "add":
        raise Refused("Choose what to do.")
    if action == "delete":
        used = _reminder_used(con, p["kind"], p["key"])
        if p["system"]:
            raise Refused("The app brought this reminder, so it can't be deleted. Stop using it instead.", 409)
        if used:
            raise Refused(f"Used by {used} reminder{'s' if used != 1 else ''} in months set up, so it can't be deleted. Stop using it instead.", 409)
        con.execute("DELETE FROM people_task_terms WHERE people_task_id = ?", (p["id"],))
        con.execute("DELETE FROM people_tasks WHERE id = ?", (p["id"],))
        db.log(con, f"Joiner and leaver reminders: deleted {p['key']}")
        checklistbook.forget(con)
        return {"lines": [], "affected": {"tasks": 0}, "id": None}
    m = _from(con, b, None)
    before_filed = _filed_tasks(con)
    if action == "add":
        key = b.get("key")
        if not isinstance(key, str) or not KEY.fullmatch(key.strip().lower()):
            raise Refused("Key: lower-case letters, digits and _ only, 2 to 20 characters, starting with a letter.")
        key = key.strip().lower()
        if con.execute("SELECT 1 FROM people_tasks WHERE key = ?", (key,)).fetchone():
            raise Refused(f"There is already a reminder with the key {key}.")
        kind = b.get("kind")
        if kind not in ("joiner", "leaver"):
            raise Refused("Say whether it is for joiners or leavers.")
        vals = _people_fields(con, b.get("fields"))
        sort = con.execute("SELECT COALESCE(MAX(sort), -1) + 1 FROM people_tasks").fetchone()[0]
        pid = con.execute("INSERT INTO people_tasks (key, kind, short_name, system, sort) VALUES (?, ?, ?, 0, ?)",
                          (key, kind, _short_name(b.get("short_name")), sort)).lastrowid
        p = {"id": pid, "key": key, "kind": kind}
        in_use, what = 1, "added"
    else:
        ts = B._pterms.get(p["key"], [])
        cur, nxt = _live_at(ts, m)
        base = cur or nxt or (ts[-1] if ts else None)
        if action == "change":
            vals = _people_fields(con, b.get("fields"), base)
            in_use = base["in_use"] if base else 1
            name = _short_name(b.get("short_name")) if "short_name" in b else p["short_name"]
            same = cur and all(vals[k] == cur[k] for k in PEOPLE_COLS)
            if same and name == p["short_name"]:
                raise Refused("Nothing changes: this is what the reminder is from that month already.")
            if name != p["short_name"]:
                con.execute("UPDATE people_tasks SET short_name = ? WHERE id = ?", (name, p["id"]))
            what = "changed"
            if same:
                db.log(con, f"Joiner and leaver reminders: {p['key']} now called {name or 'by its title'}")
                checklistbook.forget(con)
                return {"lines": [], "affected": {"tasks": 0}, "id": p["id"]}
        else:
            in_use = 1 if action == "use" else 0
            if not base:
                raise Refused("This reminder has nothing to use from then.")
            if not in_use and not (cur and cur["in_use"]):
                raise Refused("It is already stopped from then." if cur else "It isn't in use then.")
            if in_use and cur and cur["in_use"]:
                raise Refused("It is already in use from then.")
            vals = {k: base[k] for k in PEOPLE_COLS}
            what = "in use again" if in_use else "stopped"
    v = dict(vals)
    v["docs"] = json.dumps(v["docs"])
    planned = _dated(con, "people_task_terms", "people_task_id", p["id"], v, m, in_use, PEOPLE_COLS,
                     spread=action in ("stop", "use")) if action != "add" else []
    if action == "add":
        _dated(con, "people_task_terms", "people_task_id", p["id"], v, m, in_use, PEOPLE_COLS)
    checklistbook.forget(con)
    db.log(con, f"Joiner and leaver reminders: {p['key']} {what}, for people {'starting' if p['kind'] == 'joiner' else 'leaving'} "
                f"from {db.month_label(m)}")
    col = "start_date" if p["kind"] == "joiner" else "end_date"
    lines, n = list(planned), 0
    for payee in con.execute(f"SELECT * FROM payees WHERE {col} IS NOT NULL AND substr({col}, 1, 7) >= ? ORDER BY entity_id, sort, id",
                             (m,)).fetchall():
        for x in db.sync_reminders(con, payee):
            lines.append(f"{payee['name']}: {x}")
            n += 1
    _keep_filed(con, before_filed)
    return {"lines": lines, "affected": {"tasks": n}, "id": p["id"]}
