"""Setup phase 5 on made-up records only: the monthly checklist, the joiner and leaver reminders and the matching words
kept in the records (update 21), dated by payroll month, and what the app does with them.

Run: .venv\\Scripts\\python -m synthetic_tests.checklist_test
"""
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-checklist-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import checklistbook, config, db, rules  # noqa: E402
from hrp.app import _guess_category, app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}],
     "payees": [{"name": "Staff One (One)", "category": "salary", "amount": 3500, "due_day": 28, "start_date": "2026-11-20"},
                {"name": "Staff Two (Two)", "category": "salary", "amount": 2800, "due_day": 28, "end_date": "2027-01-05"},
                {"name": "KWSP", "category": "statutory", "amount": 900, "due_day": 15, "month_offset": 1}]},
    {"code": "AI", "name": "Example International Ltd", "uses_sql": False,
     "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "XCO", "name": "Example Other Co", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


# ---------- 1. below update 21 the code's values, frozen; from 21 the tables, reading back the same ----------
full = db.MIGRATIONS[:]
db.MIGRATIONS[:] = full[:20]
db.init()
with db.connect() as c:
    check("below update 21 the checklist, reminders and words are the code's own", checklistbook.get(c) is checklistbook.FROZEN)
    ent = c.execute("SELECT * FROM entities WHERE code = 'AISB'").fetchone()
    frozen_list = checklistbook.get(c).checklist(ent, "2026-11")
db.MIGRATIONS[:] = full
db.init()
with db.connect() as c:
    B = checklistbook.get(c)
    check("from update 21 they come from the tables", B.from_tables and c.execute("PRAGMA user_version").fetchone()[0] >= 21)
    ent = c.execute("SELECT * FROM entities WHERE code = 'AISB'").fetchone()
    check("and AISB's checklist reads as the code had it",
          [{k: t[k] for k in frozen_list[0]} for t in B.checklist(ent, "2026-11")] == frozen_list)
    check("the guesses, salary words and filing words read as the code had them",
          B.guess == checklistbook.FROZEN.guess and B.hints == checklistbook.FROZEN.hints)
    seeded = c.execute("""SELECT COUNT(*) FROM audit_row WHERE op = 'insert' AND tbl IN ('checklist_items', 'checklist_terms',
                          'people_tasks', 'people_task_terms', 'guess_words', 'hint_words', 'filing_words')""").fetchone()[0]
    check("update 21's rows are in the audit trail as added", seeded > 50, seeded)

c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


CYC = db.current_cycle()
M1, M2, M3 = CYC, db.shift_month(CYC, 1), db.shift_month(CYC, 2)
M4 = db.shift_month(M3, 1)
for e in (1, 2, 3):
    for m in (M1, M2, M3):
        j("post", "/api/months/open", json={"entity_id": e, "month": m})


def tasks(eid, month):
    return j("get", f"/api/month?entity={eid}&month={month}")["tasks"]


def task(eid, month, code):
    return next((t for t in tasks(eid, month) if t["code"] == code), None)


def save(body, expect=200):
    return j("post", "/api/setup/checklist", expect, json=body)


# ---------- 2. Setup lists the new sections ----------
types = j("get", "/api/setup/types")
groups = dict((g[0], g[1]) for g in types["groups"])
check("Setup has Monthly work and Matching words", groups.get("Monthly work") == ["checklist", "reminders"]
      and groups.get("Matching words") == ["guess_words", "hint_words", "filing_words"])
meta = j("get", "/api/meta")
check("/api/meta gives the reminders and the checklist codes",
      [p["key"] for p in meta["people_tasks"]] == ["ecp22", "perkeso", "kwsp", "stamp", "cp22a"] and "kwsp" in meta["checklist_codes"])
v = j("get", "/api/setup/checklist?entity=1")
items = {x["code"]: x for x in v["items"]}
check("the checklist view lists AISB's 15 items, built in and in use", len(items) == 15 and all(x["system"] and x["in_use"] for x in items.values()))
check("and how each is shown done", items["statement"]["completion"] == "statements" and items["kwsp"]["completion"] == "payments"
      and items["kwsp"]["now"]["rule"]["docs"] == ["portal"] and items["kwsp"]["now"]["submit_as"] == "KWSP")
check("a change may start from the month being worked on", v["default_from"] == M1 and v["first_allowed"] is None)
xco = j("get", "/api/setup/entities/3")
check("a company without a checklist says so", any("no monthly checklist" in n for n in xco["notes"]))

# ---------- 3. a change from a month on, previewed first ----------
inputs = items["inputs"]
fields = {**inputs["now"], "title": "Collect payroll changes and leave"}
p = save({"action": "change", "entity_id": 1, "item_id": inputs["id"], "from_month": M2, "fields": fields, "preview": True})
check("a preview says what would change", p["preview"] is True and any(M2[:4] in x for x in p["lines"]) and p["affected"]["tasks"] == 2, p)
check("and changes nothing", task(1, M2, "inputs")["title"] == "Collect payroll changes")
r = save({"action": "change", "entity_id": 1, "item_id": inputs["id"], "from_month": M2, "fields": fields, "reason": "Leave too"})
check("a change applies from that month on, not before", task(1, M1, "inputs")["title"] == "Collect payroll changes"
      and task(1, M2, "inputs")["title"] == fields["title"] and task(1, M3, "inputs")["title"] == fields["title"], r)
save({"action": "change", "entity_id": 1, "item_id": inputs["id"], "from_month": M2, "fields": fields}, 400)
h = next(x for x in j("get", "/api/setup/checklist?entity=1")["items"] if x["code"] == "inputs")["history"]
check("the earlier wording is kept, ended at that month", [(x["from_month"], x["to_month"]) for x in h] == [(M2, None), ("0000-00", M2)], h)
t3 = task(1, M3, "inputs")
j("post", f"/api/tasks/{t3['id']}", json={"done": True})
r = save({"action": "change", "entity_id": 1, "item_id": inputs["id"], "from_month": M3,
          "fields": {**fields, "due_day": 19, "detail": "Joiners and leavers."}})
check("a ticked item is kept as it was, and says so", task(1, M3, "inputs")["detail"] != "Joiners and leavers."
      and any("ticked" in x for x in r["lines"]), r["lines"])
check("an un-ticked one gets the new due date", task(1, M2, "inputs")["due_date"].endswith("-18"))

# ---------- 4. add, stop, use again, delete ----------
r = save({"action": "add", "entity_id": 1, "from_month": M2, "fields": {"completion": "hand", "title": "Send payslips", "detail": "",
                                                                        "due_offset": 1, "due_day": 1, "docs": ["payslip"]}})
check("a new item is added to the open months from then on", task(1, M1, "send-payslips") is None
      and task(1, M2, "send-payslips") and task(1, M3, "send-payslips") and r["item_id"])
new_id = r["item_id"]
save({"action": "add", "entity_id": 1, "from_month": M2, "fields": {"completion": "statements", "title": "Statements again",
                                                                   "due_offset": 1, "due_day": 5}}, 400)
check("a built-in item can't be added twice", True)
save({"action": "add", "entity_id": 1, "from_month": M2, "fields": {"completion": "hand", "title": "Send payslips", "due_offset": 1, "due_day": 2}}, 400)
check("two items in use can't share a title", True)
save({"action": "stop", "entity_id": 1, "item_id": new_id, "from_month": M3, "reason": "Not needed"})
check("a stopped item leaves the months from then on", task(1, M2, "send-payslips") and task(1, M3, "send-payslips") is None)
save({"action": "use", "entity_id": 1, "item_id": new_id, "from_month": M3, "reason": "Needed after all"})
check("and comes back when used again", task(1, M3, "send-payslips") is not None)
e = save({"action": "delete", "entity_id": 1, "item_id": new_id, "reason": "x"}, 409)["error"]
check("an item months use can't be deleted", "Stop using it instead" in e, e)
r = save({"action": "add", "entity_id": 1, "from_month": M4, "fields": {"completion": "hand", "title": "Later item", "due_offset": 0, "due_day": 9}})
save({"action": "delete", "entity_id": 1, "item_id": r["item_id"], "reason": "Added by mistake"})
check("one no month uses can be deleted", all(x["title"] if False else x["code"] != "later-item" for x in j("get", "/api/setup/checklist?entity=1")["items"]))

# ---------- 5. how an item is shown done, dated ----------
jv = items["payroll-jv"]
before_m1 = task(1, M1, "payroll-jv")["why"]
rule = {**jv["now"]["rule"], "categories": ["director"], "name": ["director payment", "director payments"]}
save({"action": "change", "entity_id": 1, "item_id": jv["id"], "from_month": M2, "fields": {**jv["now"], "rule": rule}})
check("a payments rule changed from a month on leaves the months before it as they were",
      task(1, M1, "payroll-jv")["why"] == before_m1 and task(1, M2, "payroll-jv")["why"] == "No director payment this month yet",
      (before_m1, task(1, M2, "payroll-jv")["why"]))
bad = {**rule, "docs": []}
save({"action": "change", "entity_id": 1, "item_id": jv["id"], "from_month": M3, "fields": {**jv["now"], "rule": bad}}, 400)
check("a payments rule needs documents", True)

# ---------- 6. Next up takes the deadlines and due dates from the checklist ----------
recon = items["recon"]
save({"action": "change", "entity_id": 1, "item_id": recon["id"], "from_month": M3, "fields": {**recon["now"], "due_day": 25}})
check("a checklist item due after the cycle's rollover day still belongs to its month", task(1, M3, "recon")["waiting"] is None)
with db.connect() as cc:
    BB = checklistbook.get(cc)
    check("the statement's due date comes from the company's item, else the old one",
          BB.due_of(1, "statement", M2, (9, 9)) == (1, 5) and BB.due_of(3, "statement", M2, (1, 5)) == (1, 5))
    check("deadlines and submitted names come from the items", BB.deadline(1, "kwsp", M2) and BB.submit_as(1, "epcb", M2) == "e-PCB"
          and not BB.deadline(1, "inputs", M2))

# ---------- 7. copy another company's checklist ----------
r = save({"action": "copy", "entity_id": 3, "from_month": M2, "copy_from": 2, "reason": "Same as AI"})
check("a company without a checklist can copy another's from a month", task(3, M1, "statement") is None
      and {t["code"] for t in tasks(3, M2)} >= {"budget", "invoices", "statement", "records", "file"}, r)
xco = j("get", "/api/setup/entities/3")
check("and then has one", not any("no monthly checklist" in n for n in xco["notes"]))
save({"action": "copy", "entity_id": 3, "from_month": M2, "copy_from": 1}, 400)
check("copying is refused once it has a checklist", True)

# ---------- 9. joiner and leaver reminders ----------
rv = j("get", "/api/setup/reminders")
rules_ = {x["key"]: x for x in rv["rules"]}
check("the reminders view lists the five", list(rules_) == ["ecp22", "perkeso", "kwsp", "stamp", "cp22a"] and rules_["stamp"]["now"]["salary_over"] == 3000)
before = [t for m in (M1, M2, M3) for t in tasks(1, m) if t["code"].startswith("joiner-")]
check("Staff One has their joiner reminders", {t["code"].split("-")[1] for t in before} == {"ecp22", "perkeso", "kwsp", "stamp"},
      [t["code"] for t in before])
st = rules_["stamp"]
r = j("post", "/api/setup/reminders", json={"action": "stop", "id": st["id"], "from_month": M1, "reason": "Done by HR", "preview": True})
check("stopping a reminder is previewed with what it removes", r["preview"] and any("removed" in x for x in r["lines"]), r)
j("post", "/api/setup/reminders", json={"action": "stop", "id": st["id"], "from_month": M1, "reason": "Done by HR"})
after = [t["code"] for m in (M1, M2, M3) for t in tasks(1, m) if t["code"].startswith("joiner-stamp")]
check("and then removes it for people starting from then", after == [], after)
ec = rules_["ecp22"]
r = j("post", "/api/setup/reminders", json={"action": "change", "id": ec["id"], "from_month": M1,
                                            "fields": {**ec["now"], "days": 14}})
due = next(t for m in (M1, M2, M3) for t in tasks(1, m) if t["code"].startswith("joiner-ecp22"))["due_date"]
check("a change of days moves the reminder's due date", due == "2026-12-04", (due, r))
j("post", "/api/setup/reminders", 400, json={"action": "change", "id": ec["id"], "from_month": M2,
                                             "fields": {**ec["now"], "title": "e-CP22 for {person}"}})
check("a title may only use {name}", True)
r = j("post", "/api/setup/reminders", json={"action": "add", "key": "medical", "kind": "joiner", "short_name": "medical check",
                                            "from_month": M1, "fields": {"days": 10, "salary_over": None, "title": "Medical check for {name}",
                                                                         "detail": "Book it before {date}.", "docs": []}})
check("a new reminder reaches the people it covers", any(t["code"].startswith("joiner-medical") for m in (M1, M2, M3) for t in tasks(1, m)), r)
j("post", "/api/setup/reminders", 409, json={"action": "delete", "id": r["id"], "reason": "x"})
check("a reminder in use can't be deleted", True)
pu = j("get", "/api/payees/1/usage")
check("the recurring payment counts its reminders", any("reminder" in u[0] for u in pu.get("used_by", pu.get("usage", []))), pu)

# ---------- 8. filed months never change ----------
j("post", "/api/months/close", json={"entity_id": 1, "month": M1, "closed": True})
e = save({"action": "change", "entity_id": 1, "item_id": inputs["id"], "from_month": M1, "fields": fields}, 400)["error"]
check("a change can't start in a filed month", "filed" in e, e)
check("the earliest month offered is after the filed one", j("get", "/api/setup/checklist?entity=1")["first_allowed"] == M2)

cp = next(t for t in tasks(1, M1) if t["code"].startswith("leaver-cp22a"))
check("a leaver's CP22A sits in the month before the last day's month", cp["due_date"] == "2026-12-06", cp["due_date"])
cr = rules_["cp22a"]
e = j("post", "/api/setup/reminders", 400, json={"action": "change", "id": cr["id"], "from_month": M3,
                                                 "fields": {**cr["now"], "days": -20}})["error"]
check("a reminder change that would move one out of a filed month is refused", "filed" in e and "CP22A" in e, e)
# ---------- 10. matching words ----------
gw = j("get", "/api/setup/guess_words")["rows"]
check("the guesses list in order, words as lists", [g["payment_type"] for g in gw][:3] == ["claim_overseas", "claim", "salary"]
      and gw[1]["words"] == ["CLAIM"])
ins = j("post", "/api/setup/guess_words", json={"fields": {"label": "Insurance", "words": "insurance, takaful", "payment_type": "utility"}})
j("post", "/api/setup/guess_words", 400, json={"fields": {"label": "Money in", "words": "REFUND", "payment_type": "receipt"}})
check("a guess must give a money-out type", True)
claims = next(g for g in gw if g["payment_type"] == "claim")
j("post", f"/api/setup/guess_words/{claims['id']}/stop", json={"reason": "Not wanted"})
with db.connect() as cc:
    check("the guesses Setup keeps are used", _guess_category("TAKAFUL PREMIUM", cc) == "utility"
          and _guess_category("SALARY CLAIM", cc) == "salary")
check("without a connection the code's own guesses stay", _guess_category("SALARY CLAIM") == "claim")
j("post", "/api/setup/filing_words", 400, json={"fields": {"label": "x", "doc_kind": "journal", "words": "BONUS", "checklist_code": "nope"}})
fw = j("post", "/api/setup/filing_words", json={"fields": {"label": "Bonus journals", "doc_kind": "journal", "words": "BONUS",
                                                         "checklist_code": "payroll-jv"}})
with db.connect() as cc:
    check("filing words Setup adds are used", any(code == "payroll-jv" and "BONUS" in w for _, _, w, code in checklistbook.get(cc).filing))

# ---------- 11. document types the checklist asks for ----------
dt = {r["key"]: r for r in j("get", "/api/setup/doc_types")["rows"]}
rec = j("get", f"/api/setup/doc_types/{dt['approval']['id']}")
check("a document type counts the checklist templates asking for it", any("checklist template" in u[0] for u in rec["used_by"]), rec["used_by"])
e = j("post", f"/api/setup/doc_types/{dt['payslip']['id']}/stop", 400, json={"reason": "x"})["error"]
check("one an open month's checklist asks for can't be stopped", "monthly checklist" in e, e)

# ---------- 12. the trail ----------
# ---------- 11b. review fixes: later plans kept, reasons asked, the app's own reminders, limits ----------
pay = items["payroll-approve"]
save({"action": "stop", "entity_id": 1, "item_id": pay["id"], "from_month": M4, "reason": "Approved elsewhere"})
r = save({"action": "change", "entity_id": 1, "item_id": pay["id"], "from_month": M3, "fields": {**pay["now"], "title": "Payroll approved by HR"}})
h = next(x for x in j("get", "/api/setup/checklist?entity=1")["items"] if x["code"] == "payroll-approve")["history"]
check("a change from a month keeps a stop planned for a later month", [(x["from_month"], x["to_month"], x["in_use"]) for x in h][:2]
      == [(M4, None, 0), (M3, M4, 1)] and any("kept as planned" in x for x in r["lines"]), (h, r["lines"]))
r = save({"action": "stop", "entity_id": 1, "item_id": pay["id"], "from_month": M3, "reason": "Not needed"})
h = next(x for x in j("get", "/api/setup/checklist?entity=1")["items"] if x["code"] == "payroll-approve")["history"]
check("stopping from a month stops the wording planned later too", all(not x["in_use"] for x in h if x["from_month"] >= M3), h)
save({"action": "stop", "entity_id": 1, "item_id": pay["id"], "from_month": M3}, 400)
check("stop, use again and delete ask why", True)
late = save({"action": "add", "entity_id": 1, "from_month": M4, "fields": {"completion": "hand", "title": "Planned item", "due_offset": 0, "due_day": 9}})
save({"action": "use", "entity_id": 1, "item_id": late["item_id"], "from_month": M3, "reason": "Sooner"})
h = next(x for x in j("get", "/api/setup/checklist?entity=1")["items"] if x["id"] == late["item_id"])["history"]
check("an item can be used from a month before the one it was added from", [(x["from_month"], x["to_month"]) for x in h] == [(M4, None), (M3, M4)], h)
e = save({"action": "add", "entity_id": 1, "from_month": M4, "fields": {"completion": "statements", "title": "x", "due_offset": 1, "due_day": 5}}, 400)
r = save({"action": "add", "entity_id": 3, "from_month": M4, "fields": {"completion": "hand", "title": "SST return", "due_offset": 0,
                                                                       "due_day": 28, "deadline": True, "submit_as": "SST"}})
from hrp import nextup  # noqa: E402
with db.connect() as cc:
    e3 = dict(cc.execute("SELECT * FROM entities WHERE id = 3").fetchone())
    from datetime import date as _d
    rows_ = nextup._deadlines(e3, [{"code": t["code"], "month": M4, "due_date": db.due(M4, 0, 28), "title": "SST return", "id": 1}
                                   for t in [{"code": next(x["code"] for x in j("get", "/api/setup/checklist?entity=3")["items"] if x["now"]["title"] == "SST return")}]],
                              _d.fromisoformat(db.due(M4, 0, 26)), __import__("hrp").rulebook.get(cc), checklistbook.get(cc))
check("a company's own submitted item has no statutory legal deadline", rows_ and rows_[0]["text"] == f"Submit {db.month_label(M4, short=True).split()[0]} SST", rows_)
rv = j("get", "/api/setup/reminders")
cp = next(x for x in rv["rules"] if x["key"] == "cp22a")
check("the app's own reminders can't be deleted", cp["system"] == 1 and cp["can_delete"] is False)
gw = j("get", "/api/setup/guess_words")["rows"][0]
j("patch", f"/api/setup/guess_words/{gw['id']}", json={"fields": {"sort": None}})
check("emptying a guess's order puts it after the others", j("get", f"/api/setup/guess_words/{gw['id']}")["record"]["sort"] > 5)
memo = j("post", "/api/setup/doc_types", json={"fields": {"key": "memo", "label": "Memo", "singular": "memo", "plural": "memos"}})
mi = save({"action": "add", "entity_id": 3, "from_month": M4, "fields": {"completion": "hand", "title": "Memo check", "due_offset": 0,
                                                                        "due_day": 9, "docs": ["memo"]}})
j("post", f"/api/setup/doc_types/{memo['id']}/stop", 400, json={"reason": "x"})
save({"action": "stop", "entity_id": 3, "item_id": mi["item_id"], "from_month": M4, "reason": "Not needed"})
j("post", f"/api/setup/doc_types/{memo['id']}/stop", json={"reason": "No longer asked for"})
check("a document type can be stopped once the item asking for it is stopped", True)
j("post", "/api/setup/checklist", 400, json={"action": "change", "entity_id": 1, "item_id": items["kwsp"]["id"], "from_month": M4,
                                             "fields": {**items["kwsp"]["now"], "rule": {**items["kwsp"]["now"]["rule"], "name": ["x" * 300, "y"]}}})
check("a payments rule's names have a length limit", True)

# ---------- 12. the trail ----------
hist = j("get", f"/api/audit/record/checklist_items/{inputs['id']}")
check("a checklist item's history shows its wordings over time", any(c.get("table") == "checklist_terms" or "wording" in str(c).lower()
                                                                     for c in hist["changes"]), str(hist)[:400])
from hrp import audit  # noqa: E402
with db.connect() as cc:
    vr = audit.verify(cc)
    un = cc.execute("SELECT COUNT(*) FROM audit_tx WHERE action = 'Unattributed app write'").fetchone()[0]
check("every change was attributed and the trail checks out", vr["ok"] and un == 0, vr)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
