"""Setup phase 4 on made-up records only: payment types, document types and required documents kept in the records
(update 20), dated by payroll month, per company; the frozen rules below update 20; and what the app does with them.

Run: .venv\\Scripts\\python -m synthetic_tests.types_test
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-types-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, rulebook, rules  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}],
     "payees": [{"name": "Staff One", "category": "salary", "amount": 3000, "due_day": 28, "month_offset": 1},
                {"name": "Office Supplier", "category": "utility", "amount": 450, "due_day": 28, "month_offset": 1}]},
    {"code": "AI", "name": "Example International Ltd", "uses_sql": False,
     "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}],
     "payees": [{"name": "Landlord", "category": "rental", "amount": 2000, "due_day": 28, "month_offset": 1}]},
]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


# ---------- 1. below update 20 the rules are rules.py's, frozen; update 20 writes them and they read back the same ----------
full = db.MIGRATIONS[:]
db.MIGRATIONS[:] = full[:19]
db.init()
with db.connect() as c:
    R = rulebook.get(c)
    check("below update 20 the rules are the frozen ones from rules.py", R is rulebook.FROZEN and not R.from_tables)
db.MIGRATIONS[:] = full
db.init()
with db.connect() as c:
    R = rulebook.get(c)
    check("from update 20 they come from the tables", R.from_tables)
    check("and read exactly as rules.py had them", R.categories == rules.CATEGORIES and list(R.categories) == list(rules.CATEGORIES)
          and R.doc_types == rules.DOC_TYPES and R.sql_only == rules.SQL_ONLY
          and all(R.required_docs(k, u) == rules.required_docs(k, u) for k in list(rules.CATEGORIES) + ["unknown"] for u in (0, 1)))
    seeded = c.execute("SELECT COUNT(*) FROM audit_row WHERE tbl IN ('payment_types', 'doc_types', 'required_sets') AND op = 'insert'").fetchone()[0]
    check("update 20's rows are in the audit trail as added", seeded == len(rules.CATEGORIES) + len(rules.DOC_TYPES) + len(rules.REQUIRED_DOCS), seeded)

c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:400])
    return r.get_json()


CYC = db.current_cycle()
M1, M2, M3 = CYC, db.shift_month(CYC, 1), db.shift_month(CYC, 2)
for e in (1, 2):
    for m in (M1, M2, M3):
        j("post", "/api/months/open", json={"entity_id": e, "month": m})


def salary_required(month, eid=1):
    pays = j("get", f"/api/month?entity={eid}&month={month}")["payments"]
    p = next(p for p in pays if p["description"].startswith("Staff One" if eid == 1 else "Landlord"))
    return p["required"], p["status"]


# ---------- 2. meta and the registry ----------
m = j("get", "/api/meta")
check("meta keeps its shapes and adds what the page needs", m["categories"] == rules.CATEGORIES and m["doc_types"] == rules.DOC_TYPES
      and m["category_info"]["receipt"]["direction"] == "in" and m["doc_info"]["pv"]["from_sql"] == 1)
t = j("get", "/api/setup/types")
check("Setup lists payment types, document types and required documents", {"payment_types", "doc_types", "required"} <= set(t["kinds"]))

# ---------- 3. payment types ----------
j("post", "/api/setup/payment_types", 400, json={"fields": {"key": "Bad Key!", "label": "X", "direction": "out"}})
j("post", "/api/setup/payment_types", 400, json={"fields": {"key": "salary", "label": "Copy", "direction": "out"}})
j("post", "/api/setup/payment_types", 400, json={"fields": {"key": "levy", "label": "Levy", "direction": "out", "legal_due_day": 15}})
grant = j("post", "/api/setup/payment_types", json={"fields": {"key": "grant", "label": "Grant received", "direction": "in"}})
levy = j("post", "/api/setup/payment_types", json={"fields": {"key": "levy", "label": "HRD levy", "direction": "out",
                                                               "legal_due_offset": "1", "legal_due_day": 15}})
check("payment types are added, a legal deadline with both its parts", levy["record"]["legal_due_day"] == 15 and levy["record"]["legal_due_offset"] == 1)
check("a new type's key is locked, with the reason", "key" in grant["locked"])
pt = {r["key"]: r for r in j("get", "/api/setup/payment_types")["rows"]}
stat = j("get", f"/api/setup/payment_types/{pt['statutory']['id']}")
check("a type the app relies on can't be stopped or deleted, and its direction is locked",
      stat["can_stop"] is False and stat["can_delete"] is False and "direction" in stat["locked"])
j("post", f"/api/setup/payment_types/{pt['statutory']['id']}/stop", 400, json={"reason": "x"})
j("patch", f"/api/setup/payment_types/{pt['statutory']['id']}", 400, json={"fields": {"legal_due_day": None, "legal_due_offset": None}})
j("patch", f"/api/setup/payment_types/{pt['utility']['id']}", json={"fields": {"label": "Utilities and telco"}})
check("a type's name changes everywhere it is shown", j("get", "/api/meta")["categories"]["utility"] == "Utilities and telco")
j("post", f"/api/setup/payment_types/{pt['rental']['id']}/stop", json={"reason": "No longer renting"})
e = j("post", "/api/payees", 400, json={"entity_id": 2, "name": "New landlord", "category": "rental"})["error"]
check("a stopped type isn't taken for a new recurring payment", "payment types" in e, e)
j("post", "/api/payees", json={"id": 3, "name": "Landlord", "category": "rental"})
check("but a recurring payment that already has it keeps it", True)
j("post", "/api/payments", 400, json={"entity_id": 1, "month": M1, "description": "x", "category": "rental"})
j("post", f"/api/setup/payment_types/{pt['rental']['id']}/use", json={"reason": "Renting again"})
r = j("post", "/api/payees", json={"entity_id": 1, "name": "Research grant", "category": "grant", "direction": "in", "amount": 10000})
with sqlite3.connect(config.DB_PATH) as raw:
    g = raw.execute("SELECT category, direction FROM payees WHERE name = 'Research grant'").fetchone()
check("a new money-in type is kept, not turned into Money received", g == ("grant", "in"), g)
j("delete", f"/api/setup/payment_types/{levy['id']}", json={"reason": "Added by mistake"})
check("an unused type of our own is deleted", "levy" not in j("get", "/api/meta")["categories"])
check("one in use is not", "Stop using it instead" in j("delete", f"/api/setup/payment_types/{grant['id']}", 409, json={"reason": "x"})["error"])

# ---------- 4. document types ----------
tf = j("post", "/api/setup/doc_types", json={"fields": {"key": "tax_form", "label": "Tax form", "singular": "tax form", "plural": "tax forms",
                                                        "pack_order": 5}})
dt = {r["key"]: r for r in j("get", "/api/setup/doc_types")["rows"]}
check("a document type is added", "tax_form" in dt and dt["tax_form"]["system"] == 0)
check("a seeded one can't be deleted", j("get", f"/api/setup/doc_types/{dt['pv']['id']}")["can_delete"] is False)
j("post", f"/api/setup/doc_types/{dt['pv']['id']}/stop", 400, json={"reason": "x"})
e = j("post", f"/api/setup/doc_types/{dt['payslip']['id']}/stop", 400, json={"reason": "x"})["error"]
check("a document type still required can't be stopped; the message says where", "Salary" in e, e)
pay = j("get", f"/api/month?entity=1&month={M1}")["payments"][0]
up = c.post(BASE + "/api/upload", headers=H, data={"payment_id": str(pay["id"]), "doc_type": "tax_form",
                                                  "file": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "form.pdf")})
check("a new document type can be uploaded", up.status_code == 200, up.data[:200])
j("post", f"/api/setup/doc_types/{tf['id']}/stop", json={"reason": "Replaced"})
up = c.post(BASE + "/api/upload", headers=H, data={"payment_id": str(pay["id"]), "doc_type": "tax_form",
                                                  "file": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "form2.pdf")})
check("a stopped one can't", up.status_code == 400 and "no longer in use" in up.get_json()["error"])
j("post", f"/api/setup/doc_types/{tf['id']}/use", json={"reason": "Back"})

# ---------- 5. required documents, dated ----------
v = j("get", "/api/setup/required")
sal = next(x for x in v["types"] if x["key"] == "salary")
check("the view shows each type's documents now", sal["docs"] == ["pv", "payslip", "bank"] and v["default_from"] == M1)
j("post", "/api/setup/required", 400, json={"payment_type": "salary", "entity_id": None, "docs": ["pv", "payslip", "bank"], "from_month": M2})
j("post", "/api/setup/required", 400, json={"payment_type": "salary", "entity_id": None, "docs": ["pv", "nope"], "from_month": M2})
before = [salary_required(x) for x in (M1, M2, M3)]
r = j("post", "/api/setup/required", json={"payment_type": "salary", "entity_id": None, "docs": ["pv", "payslip", "bank", "tax_form"],
                                            "from_month": M2, "reason": "New rule from HR"})
after = [salary_required(x) for x in (M1, M2, M3)]
check("a change from a month on applies from that month, not before", after[0][0] == before[0][0] and "tax_form" in after[1][0]
      and "tax_form" in after[2][0], (before, after))
check("and says how many open payments it moved", r["affected"]["payments"] >= 0 and "now_missing" in r["affected"])
h = next(x for x in j("get", "/api/setup/required")["types"] if x["key"] == "salary")["history"]
check("the earlier set is kept and closed at that month", [(x["from_month"], x["to_month"]) for x in h] == [(M2, None), ("0000-00", M2)], h)
# a company's own set
j("post", "/api/setup/required", json={"payment_type": "rental", "entity_id": 2, "docs": ["invoice"], "from_month": M2})
check("a company's own set wins for it", salary_required(M2, 2)[0] == ["invoice"] and salary_required(M1, 2)[0] == ["invoice", "bank"])
j("post", "/api/setup/required", json={"payment_type": "rental", "entity_id": 2, "docs": None, "from_month": M3})
check("and from a later month it can follow every company again", salary_required(M3, 2)[0] == ["invoice", "bank"] and salary_required(M2, 2)[0] == ["invoice"])
check("a company not in SQL isn't asked for SQL documents", "pv" not in salary_required(M1, 2)[0])
# filed months never change
j("post", "/api/months/close", json={"entity_id": 1, "month": M2, "closed": True})
e = j("post", "/api/setup/required", 400, json={"payment_type": "salary", "entity_id": None, "docs": ["pv", "bank"], "from_month": M2})["error"]
check("a change can't start in a filed month", "filed" in e, e)
check("the earliest month offered is after the filed one", j("get", "/api/setup/required")["default_from"] == M3)
check("and the page may go back no further than the month after it", j("get", "/api/setup/required")["first_allowed"] == M3)

# ---------- 5b. what can't be stopped or changed while open or filed months rely on it ----------
M4 = db.shift_month(M3, 1)
memo = j("post", "/api/setup/doc_types", json={"fields": {"key": "memo", "label": "Memo", "singular": "memo", "plural": "memos"}})
j("post", "/api/setup/required", json={"payment_type": "rental", "entity_id": None, "docs": ["memo", "bank"], "from_month": M3})
j("post", "/api/setup/required", json={"payment_type": "rental", "entity_id": None, "docs": ["bank"], "from_month": M4})
e = j("post", f"/api/setup/doc_types/{memo['id']}/stop", 400, json={"reason": "x"})["error"]
check("a document type an open month still needs (a set that has ended) can't be stopped", "Rental" in e or "rental" in e, e)
dt = {r["key"]: r for r in j("get", "/api/setup/doc_types")["rows"]}
for k in ("approval", "portal", "payroll"):
    rec = j("get", f"/api/setup/doc_types/{dt[k]['id']}")
    e = j("post", f"/api/setup/doc_types/{dt[k]['id']}/stop", 400, json={"reason": "x"})["error"]
    check(f"the monthly checklist's {k} can't be stopped while the checklist or reminders ask for it", "monthly checklist" in e, e)
pt = {r["key"]: r for r in j("get", "/api/setup/payment_types")["rows"]}
e = j("post", f"/api/setup/payment_types/{pt['utility']['id']}/stop", 400, json={"reason": "x"})["error"]
check("the type new recurring payments start on can't be stopped", "General settings" in e, e)
sal = j("get", f"/api/setup/payment_types/{pt['salary']['id']}")
check("a type with payments in a filed month has its legal deadline locked", "legal_due_day" in sal["locked"], sal["locked"])
j("patch", f"/api/setup/payment_types/{pt['salary']['id']}", 400, json={"fields": {"legal_due_offset": "1", "legal_due_day": 7}})
pid = j("post", "/api/payments", json={"entity_id": 1, "month": M3, "description": "Refund", "category": "receipt",
                                       "amount": 10})["id"]
with sqlite3.connect(config.DB_PATH) as raw:
    d = raw.execute("SELECT direction FROM payments WHERE id = ?", (pid,)).fetchone()[0]
check("a payment added by hand with no direction goes the way its type does", d == "in", d)
out = next(p for p in j("get", f"/api/month?entity=1&month={M3}")["payments"] if p["description"].startswith("Office Supplier"))
e = j("patch", f"/api/payments/{out['id']}", 400, json={"category": "receipt"})["error"]
check("a payment can't change to a type going the other way", "money out" in e, e)
from hrp.app import valid_cat  # noqa: E402
with db.connect() as cc:
    got = [valid_cat(cc, "rental", "out"), valid_cat(cc, "rental", "in"), valid_cat(cc, "levy", "out"), valid_cat(cc, None, "in")]
check("payments made from bank lines and SQL vouchers keep only a type in use going their way", got == ["rental", "receipt", "other", "receipt"], got)

# ---------- 6. the trail ----------
from hrp import audit  # noqa: E402
with db.connect() as cc:
    v = audit.verify(cc)
    un = cc.execute("SELECT COUNT(*) FROM audit_tx WHERE action = 'Unattributed app write'").fetchone()[0]
check("every change was attributed and the trail checks out", v["ok"] and un == 0, v)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
