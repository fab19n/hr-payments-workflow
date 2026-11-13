"""Setup phase 7, part 3 on made-up records only: putting back a deleted Setup record (hrp/restore.py, owner decision 2).

Each kind of Setup record is deleted through the app and put back: with the same id when it is free, else a new one;
refused with a plain reason when its key or code is taken now, its company or another record it names is gone, it was
put back already, or the delete was made outside the app. The rows deleted with it come back with it (a payment type's
required documents, a checklist item's and reminder's wordings, a company's own checklist and sets); a cash book that
another account took over comes back as not the cash book, and says so; a recurring payment, checklist item or reminder
put back is brought into the months set up (never a filed one). A preview leaves nothing. The trail shows each put back
with its reason and an event naming the delete; the record's History and the delete's entry show the link. Deleting a
company that has its own checklist and required documents works (it gave a 500 before).

Run: .venv\\Scripts\\python -m synthetic_tests.restore_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-restore-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

import hrp  # noqa: E402
from hrp import audit, auditread, config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXI", "name": "Example International Ltd", "uses_sql": False,
     "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


def n_tx():
    return q("SELECT COUNT(*) AS n FROM audit_tx")[0]["n"]


def last_delete(tbl, key):
    return q("SELECT id FROM audit_row WHERE tbl = ? AND row_key = ? AND op = 'delete' ORDER BY id DESC LIMIT 1", (tbl, str(key)))[0]["id"]


def put(row, why="test: put it back", expect=200):
    return j("post", f"/api/setup/restore/{row}", expect=expect, json={"reason": why})


def refused(row):
    r = call("post", f"/api/setup/restore/{row}", json={"reason": "test: refused"})
    return r.status_code, (r.get_json() or {}).get("error", "")


def listed(kind, entity=None):
    return j("get", f"/api/setup/restore?kind={kind}" + (f"&entity={entity}" if entity else ""))["rows"]


def table(tbl):
    return q(f"SELECT * FROM {tbl} ORDER BY id")


EXH, EXI = (q("SELECT id FROM entities WHERE code = ?", (code,))[0]["id"] for code in ("EXH", "EXI"))
CUR = db.current_cycle()
NEXT = db.shift_month(CUR, 1)
DOC = q("SELECT key FROM doc_types WHERE active = 1 AND key NOT IN ('statement', 'recon', 'sqlexport') ORDER BY id LIMIT 1")[0]["key"]

# ---------- a payment type, with its required documents; preview; reason; the trail's link ----------
pt = j("post", "/api/setup/payment_types", json={"fields": {"key": "water_bill", "label": "Water bill", "direction": "out"}})["id"]
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": None, "docs": [DOC], "from_month": CUR})
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": EXI, "docs": [], "from_month": CUR})
sets = q("SELECT * FROM required_sets WHERE payment_type = 'water_bill' ORDER BY id")
check("a payment type with two sets of required documents (one a company's own)", len(sets) == 2, sets)
j("delete", f"/api/setup/payment_types/{pt}", json={"reason": "test: delete the type"})
row = last_delete("payment_types", pt)
check("deleting it takes its sets with it", not q("SELECT 1 FROM required_sets WHERE payment_type = 'water_bill'"))
rows = listed("payment_types")
check("Show deleted lists it, with the delete's reason, and nothing in the way",
      [(r["row_id"], r["name"], r["reason"], r["problem"]) for r in rows] == [(row, "Water bill", "test: delete the type", None)], rows)
d = j("get", f"/api/audit/tx/{q('SELECT t.id FROM audit_tx t JOIN audit_row r ON r.token = t.token WHERE r.id = ?', (row,))[0]['id']}")
ch = next(x for x in d["changes"] if x["id"] == row)
check("the delete's entry in the trail offers Put it back", ch.get("put_back") is True and not ch.get("put_back_in"), ch)
tx = n_tx()
pv = j("post", f"/api/setup/restore/{row}", json={"preview": True})
check("a preview says what it would do", pv["preview"] is True and pv["same_id"] is True and pv["kind"] == "payment_types", pv)
check("a preview leaves nothing: no type, no sets, no trail entry",
      n_tx() == tx and not q("SELECT 1 FROM payment_types WHERE key = 'water_bill'") and not q("SELECT 1 FROM required_sets WHERE payment_type = 'water_bill'"))
r = call("post", f"/api/setup/restore/{row}", json={})
check("putting back asks why", r.status_code == 400 and "why" in r.get_json()["error"], r.get_json())
out = put(row, "test: deleted by mistake")
back = q("SELECT * FROM payment_types WHERE key = 'water_bill'")
check("put back with the same id", out["same_id"] and out["id"] == pt and back and back[0]["id"] == pt and back[0]["label"] == "Water bill", (out, back))
check("its required documents come back with it, as they were",
      [{k: v for k, v in s.items() if k != "id"} for s in q("SELECT * FROM required_sets WHERE payment_type = 'water_bill' ORDER BY id")]
      == [{k: v for k, v in s.items() if k != "id"} for s in sets])
t = q("SELECT * FROM audit_tx WHERE id = (SELECT MAX(id) FROM audit_tx)")[0]
ev = q("SELECT * FROM audit_row WHERE token = ? AND tbl = 'restore'", (t["token"],))
del_tx = q("SELECT t.id FROM audit_tx t JOIN audit_row r ON r.token = t.token WHERE r.id = ?", (row,))[0]["id"]
check("the trail shows the put back as one entry, with its reason and an event naming the delete",
      n_tx() == tx + 1 and t["source"] == "user" and t["reason"] == "test: deleted by mistake" and "Put back payment type Water bill" in t["summary"]
      and len(ev) == 1 and json.loads(ev[0]["after"])["from_row"] == row and json.loads(ev[0]["after"])["from_entry"] == del_tx, (dict(t), ev))
h = j("get", f"/api/audit/record/payment_types/{pt}")
evs = [x for x in h["changes"] if x["table"] == "restore"]
dl = [x for x in h["changes"] if x["op"] == "delete"]
check("its History shows the put back from the delete's entry, and the delete as put back",
      len(evs) == 1 and any(f["name"] == "from_entry" and f["after"] == del_tx for f in evs[0]["fields"])
      and dl and dl[0].get("put_back_in") == t["id"], h["changes"][:3])
code, msg = refused(row)
check("the same delete can't be put back twice", code == 409 and "put back already" in msg, (code, msg))
check("and it leaves the deleted list", not listed("payment_types"))
d = j("get", f"/api/audit/tx/{del_tx}")
ch = next(x for x in d["changes"] if x["id"] == row)
check("the delete's entry now says which entry put it back", ch.get("put_back_in") == t["id"] and not ch.get("put_back"), ch)

# ---------- a document type: id taken since -> a new id; key taken since -> refused ----------
d1 = j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_form", "label": "Example form"}})["id"]
j("delete", f"/api/setup/doc_types/{d1}", json={"reason": "test"})
r1 = last_delete("doc_types", d1)
d2 = j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_other", "label": "Example other form"}})["id"]
check("ids are reused: a type added since takes the deleted one's id", d2 == d1, (d1, d2))
out = put(r1)
check("put back with a new id when its own is taken, and a note says so",
      not out["same_id"] and out["id"] != d1 and q("SELECT key FROM doc_types WHERE id = ?", (out["id"],))[0]["key"] == "ex_form"
      and q("SELECT key FROM doc_types WHERE id = ?", (d1,))[0]["key"] == "ex_other" and any("new" in n for n in out["notes"]), out)
h = j("get", f"/api/audit/record/doc_types/{out['id']}")
check("the new id's History links back to the delete under the old id",
      any(x["table"] == "restore" and any(f["name"] == "key" and f["after"] == str(d1) for f in x["fields"]) for x in h["changes"]), h["changes"])
d3 = j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_dup", "label": "Example duplicate"}})["id"]
j("delete", f"/api/setup/doc_types/{d3}", json={"reason": "test"})
r3 = last_delete("doc_types", d3)
j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_dup", "label": "Example duplicate, added again"}})
tx = n_tx()
code, msg = refused(r3)
check("refused when its key is taken now, leaving nothing", code == 409 and "ex_dup" in msg and n_tx() == tx, (code, msg))
rows = listed("doc_types")
check("Show deleted says why it can't be put back", any(x["row_id"] == r3 and x["problem"] and "ex_dup" in x["problem"] for x in rows), rows)

# ---------- matching words: their payment type gone -> refused ----------
gas = j("post", "/api/setup/payment_types", json={"fields": {"key": "gas_bill", "label": "Gas bill", "direction": "out"}})["id"]
g = j("post", "/api/setup/guess_words", json={"fields": {"label": "Gas", "words": "EXAMPLE GAS", "payment_type": "gas_bill"}})["id"]
j("delete", f"/api/setup/guess_words/{g}", json={"reason": "test"})
rg = last_delete("guess_words", g)
j("delete", f"/api/setup/payment_types/{gas}", json={"reason": "test"})
code, msg = refused(rg)
check("refused while the payment type it names is gone", code == 409 and "gas_bill" in msg and "deleted since" in msg, (code, msg))
put(last_delete("payment_types", gas))
out = put(rg)
check("put back once its payment type is back", out["same_id"] and json.loads(q("SELECT words FROM guess_words WHERE id = ?", (g,))[0]["words"]) == ["EXAMPLE GAS"])

# ---------- customers and suppliers: code taken since -> refused ----------
p1 = j("post", "/api/setup/parties", json={"fields": {"name": "Acme Paper Trading", "kind": "supplier", "entity_id": EXH, "sql_code": "400-A001"}})["id"]
j("delete", f"/api/setup/parties/{p1}", json={"reason": "test"})
rp = last_delete("parties", p1)
j("post", "/api/setup/parties", json={"fields": {"name": "Beta Stationery", "kind": "supplier", "entity_id": EXH, "sql_code": "400-A001"}})
code, msg = refused(rp)
check("refused when another supplier the company sees has its SQL code now", code == 409 and "400-A001" in msg, (code, msg))
check("Show deleted lists a company's customers and suppliers", [x["row_id"] for x in listed("parties", EXH)] == [rp])

# ---------- a company with its own checklist and required documents; its GL account ----------
exc = j("post", "/api/setup/entities", json={"fields": {"code": "EXC", "name": "Example Consulting Sdn Bhd"}})["id"]
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": exc, "docs": [DOC], "from_month": CUR})
items = q("SELECT * FROM checklist_items WHERE entity_id = ? ORDER BY id", (exc,))
terms = q("SELECT * FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?) ORDER BY id", (exc,))
gl = j("post", "/api/setup/gl_accounts", json={"fields": {"code": "310-000", "name": "Example bank", "type": "asset"}, "entity_id": exc})["id"]
j("delete", f"/api/setup/gl_accounts/{gl}", json={"reason": "test"})
rgl = last_delete("gl_accounts", gl)
r = call("delete", f"{'/api/setup/entities/'}{exc}", json={"reason": "test: delete the company"})
check("a company with its own checklist and required documents can be deleted (no error)",
      r.status_code == 200 and items and terms and not q("SELECT 1 FROM checklist_items WHERE entity_id = ?", (exc,))
      and not q("SELECT 1 FROM required_sets WHERE entity_id = ?", (exc,)), (r.status_code, r.data[:300]))
rc = last_delete("entities", exc)
code, msg = refused(rgl)
check("a GL account whose company is gone is refused", code == 409 and "company" in msg and "deleted since" in msg, (code, msg))
item_row = q("SELECT id FROM audit_row WHERE tbl = 'checklist_items' AND op = 'delete' AND row_key = ?", (str(items[0]["id"]),))[-1]["id"]
code, msg = refused(item_row)
check("a checklist item deleted with its company comes back only with the company", code == 409 and "with its company" in msg, (code, msg))
check("so the checklist's deleted list doesn't offer it", all(x["row_id"] != item_row for x in listed("checklist", EXH)))
out = put(rc)
check("the company is put back with the same id, its checklist and its own required documents",
      out["same_id"] and q("SELECT code FROM entities WHERE id = ?", (exc,))[0]["code"] == "EXC"
      and q("SELECT * FROM checklist_items WHERE entity_id = ? ORDER BY id", (exc,)) == items
      and q("SELECT * FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?) ORDER BY id", (exc,)) == terms
      and len(q("SELECT 1 FROM required_sets WHERE entity_id = ?", (exc,))) == 1, out)
out = put(rgl)
check("its GL account can be put back once the company is back", out["same_id"] and q("SELECT code FROM gl_accounts WHERE id = ?", (gl,)))

# ---------- a cash book account: another took over ----------
second = j("post", "/api/setup/accounts", json={"fields": {"label": "Second", "currency": "MYR"}, "entity_id": EXH})["id"]
main = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Main'", (EXH,))[0]["id"]
check("the first account is the cash book", q("SELECT cash_book FROM accounts WHERE id = ?", (main,))[0]["cash_book"] == 1)
j("delete", f"/api/setup/accounts/{main}", json={"reason": "test"})
check("deleting it hands the cash book to the other account", q("SELECT cash_book FROM accounts WHERE id = ?", (second,))[0]["cash_book"] == 1)
out = put(last_delete("accounts", main))
books = q("SELECT id FROM accounts WHERE entity_id = ? AND cash_book = 1", (EXH,))
check("a cash book put back comes back as not the cash book, and says so",
      out["same_id"] and [b["id"] for b in books] == [second] and any("cash book" in n for n in out["notes"]), (out, books))

# ---------- a checklist item: brought into the open months, never a filed one ----------
added = j("post", "/api/setup/checklist", json={"action": "add", "entity_id": EXH, "from_month": "2020-01",
                                                "fields": {"completion": "hand", "title": "Example filing", "due_day": 15, "docs": []}})
iid = added["item_id"]
j("post", "/api/setup/checklist", json={"action": "delete", "entity_id": EXH, "item_id": iid, "reason": "test"})
ri = last_delete("checklist_items", iid)
for m in (CUR, NEXT):
    j("post", "/api/months/open", json={"entity_id": EXH, "month": m})
j("post", "/api/months/close", json={"entity_id": EXH, "month": CUR, "closed": True})
filed = q("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY id", (EXH, CUR))
rows = listed("checklist", EXH)
check("the checklist's deleted list offers the item", [x["row_id"] for x in rows] == [ri] and rows[0]["problem"] is None, rows)
tx = n_tx()
pv = j("post", f"/api/setup/restore/{ri}", json={"preview": True})
check("a preview of a checklist item says it is added to the open month only",
      pv["affected"]["tasks"] == 1 and any("Example filing" in x for x in pv["lines"]) and n_tx() == tx
      and not q("SELECT 1 FROM tasks WHERE code LIKE 'example-filing%'") and not q("SELECT 1 FROM checklist_items WHERE id = ?", (iid,)), pv)
out = put(ri)
got = q("SELECT month FROM tasks WHERE entity_id = ? AND code = ?", (EXH, q("SELECT code FROM checklist_items WHERE id = ?", (iid,))[0]["code"]))
check("put back: in the open month, not the filed one, which is as it was",
      out["same_id"] and [g["month"] for g in got] == [NEXT] and q("SELECT * FROM tasks WHERE entity_id = ? AND month = ? ORDER BY id", (EXH, CUR)) == filed
      and q("SELECT COUNT(*) AS n FROM checklist_terms WHERE item_id = ?", (iid,))[0]["n"] == 1, (out, got))
h = j("get", f"/api/audit/record/checklist_items/{iid}")
check("the item's History shows it put back", any(x["table"] == "restore" for x in h["changes"]))

# ---------- a reminder: brought to the people it reaches ----------
j("post", "/api/setup/reminders", json={"action": "add", "key": "exwelcome", "kind": "joiner", "from_month": NEXT,
                                        "fields": {"days": 3, "title": "Welcome pack for {name}", "detail": "Hand it over by {date}.", "docs": []}})
rem = q("SELECT id FROM people_tasks WHERE key = 'exwelcome'")[0]["id"]
nterms = q("SELECT COUNT(*) AS n FROM people_task_terms WHERE people_task_id = ?", (rem,))[0]["n"]
j("post", "/api/setup/reminders", json={"action": "delete", "id": rem, "reason": "test"})
rr = last_delete("people_tasks", rem)
# reminders are for a company that runs payroll: one with a statutory recurring payment
j("post", "/api/payees", json={"entity_id": EXH, "name": "Example KWSP", "category": "statutory", "amount": 500, "due_day": 15,
                               "month_offset": 1})
hire = j("post", "/api/payees", json={"entity_id": EXH, "name": "Example New Hire", "category": "salary", "amount": 3000,
                                      "start_date": f"{NEXT}-15", "due_day": 26, "month_offset": 0})["id"]
code_ = f"joiner-exwelcome-{hire}"
check("a joiner starting while the reminder is deleted doesn't get it", not q("SELECT 1 FROM tasks WHERE code = ?", (code_,)))
check("the reminders' deleted list offers it", [x["row_id"] for x in listed("reminders")] == [rr])
out = put(rr)
check("a reminder put back comes with its wordings and reaches the joiner",
      out["same_id"] and q("SELECT COUNT(*) AS n FROM people_task_terms WHERE people_task_id = ?", (rem,))[0]["n"] == nterms
      and [x["month"] for x in q("SELECT month FROM tasks WHERE code = ?", (code_,))] == [NEXT] and out["affected"]["tasks"] == 1, out)

# ---------- a recurring payment: brought into the months set up, as one added is ----------
pay = j("post", "/api/payees", json={"entity_id": EXI, "name": "Example Office Rent", "category": "other", "amount": 1200,
                                     "due_day": 28, "month_offset": 1})["id"]
j("delete", f"/api/payees/{pay}", json={"reason": "test: delete the payee"})
rpay = last_delete("payees", pay)
for m in (CUR, NEXT):
    j("post", "/api/months/open", json={"entity_id": EXI, "month": m})
check("the months set up meanwhile have no payment for it", not q("SELECT 1 FROM payments WHERE payee_id = ?", (pay,)))
tx = n_tx()
pv = j("post", f"/api/setup/restore/{rpay}", json={"preview": True})
check("a preview of a recurring payment shows its payments, and leaves nothing",
      pv["affected"]["payments"] >= 1 and pv["lines"] and n_tx() == tx and not q("SELECT 1 FROM payees WHERE id = ?", (pay,))
      and not q("SELECT 1 FROM payments WHERE payee_id = ?", (pay,)), pv)
out = put(rpay)
pays = q("SELECT month, amount FROM payments WHERE payee_id = ? ORDER BY month", (pay,))
check("put back, it fans out into the months set up as one added does",
      out["same_id"] and pays and all(p["amount"] == 1200 for p in pays) and out["affected"]["payments"] == len(pays), (out, pays))

# ---------- a delete made outside the app can't be put back ----------
hw = j("post", "/api/setup/hint_words", json={"fields": {"label": "Example pay", "words": "EXPAY", "payment_type": "salary"}})["id"]
with sqlite3.connect(config.DB_PATH) as raw:
    raw.execute("DELETE FROM hint_words WHERE id = ?", (hw,))
ro = last_delete("hint_words", hw)
code, msg = refused(ro)
check("a delete made outside the app can't be put back", code == 409 and "outside" in msg, (code, msg))
upto = j("get", "/api/audit/outside")["upto_id"]
j("post", "/api/audit/accept-outside", json={"reason": "test: accept", "upto_id": upto})
code, msg = refused(ro)
check("not even once it is accepted", code == 409 and "outside" in msg and not listed("hint_words"), (code, msg))

# ---------- ids are reused: a company added since with a deleted company's id is another company ----------
exe = j("post", "/api/setup/entities", json={"fields": {"code": "EXE", "name": "Example Engineering Sdn Bhd"}})["id"]
acc = j("post", "/api/setup/accounts", json={"fields": {"label": "Consulting current", "currency": "MYR"}, "entity_id": exe})["id"]
gle = j("post", "/api/setup/gl_accounts", json={"fields": {"code": "320-000", "name": "Example tools", "type": "asset"}, "entity_id": exe})["id"]
sup = j("post", "/api/setup/parties", json={"fields": {"name": "Acme Tools Trading", "kind": "supplier", "entity_id": exe, "sql_code": "400-E001"}})["id"]
fee = j("post", "/api/setup/payment_types", json={"fields": {"key": "ex_fee", "label": "Example fee", "direction": "out"}})["id"]
j("post", "/api/setup/required", json={"payment_type": "ex_fee", "entity_id": exe, "docs": [DOC], "from_month": CUR})
j("delete", f"/api/setup/payment_types/{fee}", json={"reason": "test"})
rfee = last_delete("payment_types", fee)
for kind, rid in (("accounts", acc), ("gl_accounts", gle), ("parties", sup), ("entities", exe)):
    j("delete", f"/api/setup/{kind}/{rid}", json={"reason": "test: set up by mistake"})
racc, rgle, rsup, rexe = (last_delete(t, k) for t, k in (("accounts", acc), ("gl_accounts", gle), ("parties", sup), ("entities", exe)))
exf = j("post", "/api/setup/entities", json={"fields": {"code": "EXF", "name": "Example Foods Sdn Bhd"}})["id"]
check("ids are reused: a company added since takes the deleted company's id", exf == exe, (exe, exf))
shown = {k: [x["row_id"] for x in listed(k, exf)] for k in ("accounts", "gl_accounts", "parties")}
check("the new company's Show deleted doesn't offer the deleted company's records",
      racc not in shown["accounts"] and rgle not in shown["gl_accounts"] and rsup not in shown["parties"], shown)
tx = n_tx()
for what, rid in (("bank account", racc), ("GL account", rgle), ("supplier", rsup)):
    code, msg = refused(rid)
    check(f"a {what} of a deleted company is refused, though another company has its id now",
          code == 409 and "company" in msg and "deleted since" in msg, (code, msg))
check("and nothing lands in the company that took the id", n_tx() == tx and not q("SELECT 1 FROM accounts WHERE entity_id = ?", (exf,))
      and not q("SELECT 1 FROM gl_accounts WHERE entity_id = ?", (exf,)) and not q("SELECT 1 FROM parties WHERE entity_id = ?", (exf,)))
out = put(rfee)
check("a payment type put back leaves out the deleted company's own required documents, and says so",
      not q("SELECT 1 FROM required_sets WHERE payment_type = 'ex_fee' AND entity_id = ?", (exf,))
      and any("company has been deleted since" in n for n in out["notes"]), out)
j("delete", f"/api/setup/entities/{exf}", json={"reason": "test: the wrong company"})
out = put(rexe)
check("the deleted company put back takes its own id again", out["same_id"] and out["id"] == exe, out)
check("so its Show deleted offers its records again, with nothing in the way",
      [(x["row_id"], x["problem"]) for x in listed("accounts", exe)] == [(racc, None)], listed("accounts", exe))
out = put(racc)
check("and its bank account comes back into it",
      out["same_id"] and q("SELECT entity_id, label FROM accounts WHERE id = ?", (acc,)) == [{"entity_id": exe, "label": "Consulting current"}], out)

# ---------- a recurring payment's bank account deleted, its id taken by another account since ----------
sav = j("post", "/api/setup/accounts", json={"fields": {"label": "Savings", "currency": "MYR"}, "entity_id": exe})["id"]
cl = j("post", "/api/payees", json={"entity_id": exe, "name": "Example Cleaner", "category": "other", "amount": 100, "due_day": 5,
                                    "month_offset": 0, "account_id": sav})["id"]
j("delete", f"/api/payees/{cl}", json={"reason": "test"})
rcl = last_delete("payees", cl)
j("delete", f"/api/setup/accounts/{sav}", json={"reason": "test"})
usd = j("post", "/api/setup/accounts", json={"fields": {"label": "Payroll USD", "currency": "USD"}, "entity_id": exe})["id"]
check("an account added since takes the deleted account's id", usd == sav, (sav, usd))
code, msg = refused(rcl)
check("a recurring payment whose account was deleted since is refused, though another account has its id",
      code == 409 and "bank account" in msg and "deleted since" in msg and not q("SELECT 1 FROM payees WHERE name = 'Example Cleaner'"), (code, msg))

# ---------- a recurring payment's supplier deleted, its id taken by another since ----------
ps = j("post", "/api/setup/parties", json={"fields": {"name": "Acme Paper Supplies", "kind": "supplier", "entity_id": exe, "sql_code": "400-E002"}})["id"]
pp = j("post", "/api/payees", json={"entity_id": exe, "name": "Example Paper", "category": "other", "amount": 50, "due_day": 5,
                                    "month_offset": 0, "account_id": acc, "party_id": ps})["id"]
j("delete", f"/api/payees/{pp}", json={"reason": "test"})
rpp = last_delete("payees", pp)
j("delete", f"/api/setup/parties/{ps}", json={"reason": "test"})
ps2 = j("post", "/api/setup/parties", json={"fields": {"name": "Beta Office Supply", "kind": "supplier", "entity_id": None, "sql_code": "400-B009"}})["id"]
check("a supplier added since takes the deleted supplier's id", ps2 == ps, (ps, ps2))
code, msg = refused(rpp)
check("a recurring payment whose supplier was deleted since is refused, though another supplier has its id",
      code == 409 and "supplier or customer" in msg and "deleted since" in msg and not q("SELECT 1 FROM payees WHERE name = 'Example Paper'"), (code, msg))

# ---------- a filing word's supplier deleted (another took its id) or stopped ----------
fcode = q("SELECT code FROM checklist_items WHERE id = ?", (iid,))[0]["code"]
gs = j("post", "/api/setup/parties", json={"fields": {"name": "Gamma Copier Rental", "kind": "supplier", "entity_id": EXH, "sql_code": "400-G001"}})["id"]
fw = j("post", "/api/setup/filing_words", json={"fields": {"label": "Copier", "doc_kind": "invoice", "words": "EXAMPLE COPIER",
                                                         "checklist_code": fcode, "party_id": gs}})["id"]
j("delete", f"/api/setup/filing_words/{fw}", json={"reason": "test"})
rfw = last_delete("filing_words", fw)
j("delete", f"/api/setup/parties/{gs}", json={"reason": "test"})
dc = j("post", "/api/setup/parties", json={"fields": {"name": "Delta Customer", "kind": "customer", "entity_id": EXI, "sql_code": "300-D001"}})["id"]
check("a customer of another company added since takes the deleted supplier's id", dc == gs, (gs, dc))
code, msg = refused(rfw)
check("a filing word whose supplier was deleted since is refused, though another company's customer has its id",
      code == 409 and "customer or supplier" in msg and "deleted since" in msg and not q("SELECT 1 FROM filing_words WHERE label = 'Copier'"), (code, msg))
es = j("post", "/api/setup/parties", json={"fields": {"name": "Epsilon Copier Service", "kind": "supplier", "entity_id": EXH, "sql_code": "400-G002"}})["id"]
fw2 = j("post", "/api/setup/filing_words", json={"fields": {"label": "Copier service", "doc_kind": "invoice", "words": "EXAMPLE SERVICE",
                                                          "checklist_code": fcode, "party_id": es}})["id"]
j("delete", f"/api/setup/filing_words/{fw2}", json={"reason": "test"})
rfw2 = last_delete("filing_words", fw2)
j("post", f"/api/setup/parties/{es}/stop", json={"reason": "test"})
code, msg = refused(rfw2)
check("a filing word naming a supplier stopped since is refused", code == 409 and "stopped" in msg, (code, msg))
j("post", f"/api/setup/parties/{es}/use", json={"reason": "test"})
out = put(rfw2)
check("and put back once the supplier is in use again", out["same_id"] and q("SELECT party_id FROM filing_words WHERE id = ?", (fw2,)) == [{"party_id": es}], out)

# ---------- a recurring payment in use put back onto an account stopped since ----------
res = j("post", "/api/setup/accounts", json={"fields": {"label": "Reserve", "currency": "MYR"}, "entity_id": exe})["id"]
gd = j("post", "/api/payees", json={"entity_id": exe, "name": "Example Guard", "category": "other", "amount": 80, "due_day": 5,
                                    "month_offset": 0, "account_id": res})["id"]
j("post", f"/api/setup/accounts/{res}/stop", 400, json={"reason": "test"})
j("delete", f"/api/payees/{gd}", json={"reason": "test"})
rgd = last_delete("payees", gd)
j("post", f"/api/setup/accounts/{res}/stop", json={"reason": "test"})
code, msg = refused(rgd)
check("a recurring payment in use is refused onto a bank account stopped since", code == 409 and "stopped" in msg
      and not q("SELECT 1 FROM payees WHERE name = 'Example Guard'"), (code, msg))
j("post", f"/api/setup/accounts/{res}/use", json={"reason": "test"})
out = put(rgd)
check("and put back once the account is in use again", out["same_id"] and q("SELECT account_id, active FROM payees WHERE id = ?", (gd,))
      == [{"account_id": res, "active": 1}], out)

# ---------- a checklist item, reminder or required documents asking for a document type stopped since ----------
cert = j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_cert", "label": "Example certificate"}})["id"]
ci = j("post", "/api/setup/checklist", json={"action": "add", "entity_id": exe, "from_month": CUR,
                                             "fields": {"completion": "hand", "title": "Example certificate check", "due_day": 10, "docs": ["ex_cert"]}})["item_id"]
j("post", "/api/setup/reminders", json={"action": "add", "key": "excert", "kind": "leaver", "from_month": NEXT,
                                        "fields": {"days": 3, "title": "Certificate for {name}", "detail": "By {date}.", "docs": ["ex_cert"]}})
rmc = q("SELECT id FROM people_tasks WHERE key = 'excert'")[0]["id"]
j("post", f"/api/setup/doc_types/{cert}/stop", 400, json={"reason": "test"})
j("post", "/api/setup/checklist", json={"action": "delete", "entity_id": exe, "item_id": ci, "reason": "test"})
j("post", "/api/setup/reminders", json={"action": "delete", "id": rmc, "reason": "test"})
rci, rrmc = last_delete("checklist_items", ci), last_delete("people_tasks", rmc)
j("post", f"/api/setup/doc_types/{cert}/stop", json={"reason": "test"})
for what, rid in (("checklist item", rci), ("reminder", rrmc)):
    code, msg = refused(rid)
    check(f"a {what} asking for a document type stopped since is refused", code == 409 and "ex_cert" in msg and "stopped since" in msg, (code, msg))
j("post", f"/api/setup/doc_types/{cert}/use", json={"reason": "test"})
check("both put back once the document type is in use again", put(rci)["same_id"] and put(rrmc)["same_id"])
slip = j("post", "/api/setup/doc_types", json={"fields": {"key": "ex_slip", "label": "Example slip"}})["id"]
levy = j("post", "/api/setup/payment_types", json={"fields": {"key": "ex_levy", "label": "Example levy", "direction": "out"}})["id"]
j("post", "/api/setup/required", json={"payment_type": "ex_levy", "entity_id": None, "docs": ["ex_slip"], "from_month": NEXT})
j("post", f"/api/setup/doc_types/{slip}/stop", 400, json={"reason": "test"})
j("delete", f"/api/setup/payment_types/{levy}", json={"reason": "test"})
j("post", f"/api/setup/doc_types/{slip}/stop", json={"reason": "test"})
out = put(last_delete("payment_types", levy))
check("a payment type put back leaves out required documents naming a document type stopped since, and says so",
      not q("SELECT 1 FROM required_sets WHERE payment_type = 'ex_levy'") and any("ex_slip" in n and "stopped since" in n for n in out["notes"]), out)

# ---------- a record's parent put back under a new id: refused, saying where the parent went ----------
exm = j("post", "/api/setup/entities", json={"fields": {"code": "EXM", "name": "Example Marine Sdn Bhd"}})["id"]
mac = j("post", "/api/setup/accounts", json={"fields": {"label": "Marine current", "currency": "MYR"}, "entity_id": exm})["id"]
j("delete", f"/api/setup/accounts/{mac}", json={"reason": "test"})
rmac = last_delete("accounts", mac)
j("delete", f"/api/setup/entities/{exm}", json={"reason": "test"})
rexm = last_delete("entities", exm)
exn = j("post", "/api/setup/entities", json={"fields": {"code": "EXN", "name": "Example Nautical Ltd"}})["id"]
check("a company added since takes the deleted company's id", exn == exm, (exm, exn))
out = put(rexm)
check("the deleted company comes back under a new id", not out["same_id"] and out["id"] != exm, out)
code, msg = refused(rmac)
check("its bank account is refused, saying the company was put back as a new record (not 'put it back first')",
      code == 409 and f"put back as a new record (#{out['id']})" in msg and "can't follow it" in msg and "first" not in msg
      and not q("SELECT 1 FROM accounts WHERE label = 'Marine current'"), (code, msg))
moved = out["id"]
j("delete", f"/api/setup/entities/{moved}", json={"reason": "test: moved, then deleted again"})
code, msg = refused(rmac)
check("once the moved company is deleted again, its bank account still says where the company moved to (no circle)",
      code == 409 and f"put back as a new record (#{moved})" in msg and "first" not in msg, (code, msg))
put(last_delete("entities", moved))
for what, rid, tbl, key in (("bank account", rcl, "accounts", sav), ("supplier", rpp, "parties", ps)):
    out = put(last_delete(tbl, key))
    check(f"a recurring payment's {what} put back under a new id", not out["same_id"] and out["id"] != key, out)
    code, msg = refused(rid)
    check(f"so the recurring payment is refused, saying its {what} was put back as a new record",
          code == 409 and f"put back as a new record (#{out['id']})" in msg and "recurring payment can't follow it" in msg
          and "first" not in msg, (code, msg))
out = put(last_delete("parties", gs))
code, msg = refused(rfw)
check("a filing word whose supplier was put back under a new id is refused, saying so",
      not out["same_id"] and code == 409 and f"put back as a new record (#{out['id']})" in msg and "words can't follow it" in msg
      and "first" not in msg, (out, code, msg))

# ---------- many delete/put back cycles of one company: no recursion, still listed ----------
from hrp import restore  # noqa: E402
exp = j("post", "/api/setup/entities", json={"fields": {"code": "EXP", "name": "Example Plantation Sdn Bhd"}})["id"]
pac = j("post", "/api/setup/accounts", json={"fields": {"label": "Plantation current", "currency": "MYR"}, "entity_id": exp})["id"]
j("delete", f"/api/setup/accounts/{pac}", json={"reason": "test"})
rpac = last_delete("accounts", pac)
CYCLES = 50
for _ in range(CYCLES):
    j("delete", f"/api/setup/entities/{exp}", json={"reason": "test: cycle"})
    assert put(last_delete("entities", exp), why="test: cycle")["same_id"]
depth = 0
while True:
    try:
        sys._getframe(depth)
        depth += 1
    except ValueError:
        break
limit = sys.getrecursionlimit()
with db.connect() as r:
    sys.setrecursionlimit(depth + 25)  # far fewer frames than the 50 a recursive walk of the chain needs
    try:
        same = restore._same(r, "entities", exp, rpac)
        err = None
    except RecursionError as x:
        same, err = None, x
    finally:
        sys.setrecursionlimit(limit)
check(f"after {CYCLES} deletes and put backs of its company, the company is still the account's own, without recursion",
      same is True and err is None, err)
rows = listed("accounts", exp)
check("its Show deleted still offers the account, with nothing in the way", [(x["row_id"], x["problem"]) for x in rows] == [(rpac, None)], rows)
out = put(rpac)
check("and it is put back into the company", out["same_id"] and q("SELECT entity_id FROM accounts WHERE id = ?", (pac,)) == [{"entity_id": exp}], out)

# ---------- a delete row that isn't a Setup record's ----------
code, msg = refused(q("SELECT id FROM audit_row WHERE op = 'insert' ORDER BY id DESC LIMIT 1")[0]["id"])
check("only a delete of a Setup record can be put back", code == 404, (code, msg))

with db.connect() as r:
    v = audit.verify(r)
    rp = auditread.replay(r)
check("the trail checks out, and every record matches it", v["ok"] and rp["count"] == 0, (v["problems"], rp["problems"]))
print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
