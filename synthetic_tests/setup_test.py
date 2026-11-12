"""Setup (phase 3) on made-up records only: update 19, companies, bank accounts and the cash book, general settings,
recurring payments (checks, stop, use again, delete) and salary advances (the old-plan fix), each change in the audit
trail with its reason.

Run: .venv\\Scripts\\python -m synthetic_tests.setup_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-setup-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import appsettings, audit, config, db, nextup  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"},
                                                                       {"label": "FCA", "bank": "Example Bank", "number": "000-333", "currency": "USD"}],
     "payees": [{"name": "Staff One", "category": "salary", "amount": 3000, "due_day": 28, "month_offset": 1},
                {"name": "Statutory", "category": "statutory", "amount": 500, "due_day": 15, "month_offset": 1}]},
    {"code": "AI", "name": "Example International Ltd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


# The columns each table had the first time it was read (before the remaining updates): a later update may add columns,
# which are compared apart: they must still be empty.
_COLS = {}


def _known(r, t):
    have = [c[1] for c in r.execute(f'PRAGMA table_info("{t}")')]
    cols = _COLS.setdefault(t, have)
    rows = [tuple(x) for x in r.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in cols)} FROM "{t}" ORDER BY rowid')]
    new = [c for c in have if c not in cols]
    filled = bool(new) and r.execute(f'SELECT 1 FROM "{t}" WHERE {" OR ".join(chr(34) + c + chr(34) + " IS NOT NULL" for c in new)}').fetchone()
    return rows, filled


def rows_of(con, table):
    rows, filled = _known(con, table)
    return rows + (["columns a later update added are not empty"] if filled else [])


# ---------- 1. update 19 on records already in use ----------
full = db.MIGRATIONS[:]
db.MIGRATIONS[:] = full[:18]
db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}
CYC = db.current_cycle()
c.post(BASE + "/api/months/open", headers=H, json={"entity_id": 1, "month": CYC})
raw = sqlite3.connect(config.DB_PATH)
before = {t: rows_of(raw, t) for t in ("payments", "tasks", "payees", "months")}
raw.close()
db.MIGRATIONS[:] = full
trail = db.init()
raw = sqlite3.connect(config.DB_PATH)
raw.row_factory = sqlite3.Row
check("update 19 reaches the last update", raw.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS))
check("payments, checklist items, recurring payments and months are unchanged by it",
      all(rows_of(raw, t) == before[t] for t in before))
check("each company's first account becomes its cash book", [tuple(r) for r in raw.execute(
    "SELECT entity_id, label FROM accounts WHERE cash_book = 1 ORDER BY entity_id")] == [(1, "Main"), (2, "Current")])
check("the sidebar keeps the organisation name it showed", appsettings.get("organisation_name") == "Agrinexus · HR & Finance")
raw.close()
with db.connect() as r:
    check("the trail still checks out after the update", audit.verify(r)["ok"] and trail["outside"] == 0)


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:400])
    return r.get_json()


def last_tx():
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return dict(r.execute("SELECT * FROM audit_tx ORDER BY id DESC LIMIT 1").fetchone())


# ---------- 2. registry and meta ----------
t = j("get", "/api/setup/types")
check("the registry lists companies, bank accounts, recurring payments and general settings",
      {"entities", "accounts", "payees", "settings"} <= set(t["kinds"]) and t["kinds"]["entities"]["fields"][0]["key"] == "code")
m = j("get", "/api/meta")
check("meta carries the general settings", m["settings"]["cycle_rollover_day"] == 10 and m["settings"]["payee_default_due_day"] == 6)

# ---------- 3. companies ----------
j("post", "/api/setup/entities", 400, json={"fields": {"code": "bad code!", "name": "X"}})
j("post", "/api/setup/entities", 400, json={"fields": {"code": "AISB", "name": "Copy"}})
new = j("post", "/api/setup/entities", json={"fields": {"code": "test-co", "name": "Test Company Sdn Bhd", "uses_sql": False}})
check("a company is added, its code tidied to capitals", new["record"]["code"] == "TEST-CO" and new["record"]["uses_sql"] == 0)
check("a company without a checklist says so", any("no monthly checklist" in n for n in new["notes"]))
rec = j("get", "/api/setup/entities/1")
check("a company with records has its code locked, with the reason", "code" in rec["locked"] and "can't change" in rec["locked"]["code"])
j("patch", "/api/setup/entities/1", 400, json={"fields": {"code": "NEW"}})
j("patch", "/api/setup/entities/1", json={"fields": {"short_name": "Example", "tin": "C1234567890"}})
check("a company's details change, and the change is in the trail", last_tx()["summary"].startswith("Changed company Example Holdings"))
j("post", f"/api/setup/entities/{new['id']}/stop", 400, json={})
j("post", f"/api/setup/entities/{new['id']}/stop", json={"reason": "Not trading yet"})
check("stopping asks why, and the reason goes into the trail", last_tx()["reason"] == "Not trading yet")
ov = j("get", f"/api/overview?month={CYC}")
check("a stopped company is left out of the Overview", all(e.get("code") != "TEST-CO" for e in (ov.get("entities") or ov.get("companies") or [])) and "TEST-CO" not in json.dumps(ov))
nx = j("get", "/api/next")
check("and out of Next up", "TEST-CO" not in json.dumps(nx))
used = j("delete", "/api/setup/entities/1", 409, json={"reason": "test"})
check("a company in use can't be deleted; the message says what uses it", "Used by" in used["error"] and "Stop using it instead" in used["error"])
j("delete", f"/api/setup/entities/{new['id']}", json={"reason": "Added by mistake"})
check("an unused company is deleted, with its reason", last_tx()["reason"] == "Added by mistake")
with db.connect() as r:
    r.arm("user", "test: file a month")
    r.execute("UPDATE months SET closed_at = '2026-11-01T00:00:00' WHERE entity_id = 2")
    r.execute("INSERT INTO months (entity_id, month, generated_at, closed_at) VALUES (2, '2026-01', 'x', '2026-02-10')")
    r.commit()
check("SQL Account use is locked once a month is filed", "uses_sql" in j("get", "/api/setup/entities/2")["locked"])

# ---------- 4. bank accounts and the cash book ----------
lst = j("get", "/api/setup/accounts?entity=1")["rows"]
main, fca = (next(a for a in lst if a["label"] == n) for n in ("Main", "FCA"))
check("accounts list with what uses them", main["cash_book"] == 1 and "used_by" in main)
j("patch", f"/api/setup/accounts/{main['id']}", 400, json={"fields": {"cash_book": 0}})
reserve = j("post", "/api/setup/accounts", json={"entity_id": 1, "fields": {"label": "Reserve", "currency": "MYR"}})["id"]
j("patch", f"/api/setup/accounts/{reserve}", json={"fields": {"cash_book": 1}})
lst = {a["label"]: a for a in j("get", "/api/setup/accounts?entity=1")["rows"]}
check("making another account the cash book moves it (one per company)", lst["Reserve"]["cash_book"] == 1 and lst["Main"]["cash_book"] == 0)
j("post", f"/api/setup/accounts/{reserve}/stop", 400, json={"reason": "Closed"})
j("patch", f"/api/setup/accounts/{main['id']}", json={"fields": {"cash_book": 1}})
j("post", f"/api/setup/accounts/{reserve}/stop", json={"reason": "Not needed"})
j("post", f"/api/setup/accounts/{fca['id']}/stop", json={"reason": "Account closed at the bank"})
with db.connect() as r:
    sts = db.month_statements(r, r.execute("SELECT * FROM entities WHERE id = 1").fetchone(), CYC)
check("a stopped account no longer asks for a statement", [s["label"] for s in sts] == ["Main"], sts)
acc = j("post", "/api/setup/accounts", json={"entity_id": 1, "fields": {"label": "Payroll", "currency": "myr"}})
check("a new account is added (currency tidied), not the cash book while another is", acc["record"]["currency"] == "MYR" and acc["record"]["cash_book"] == 0)
pay = j("post", "/api/payments", json={"entity_id": 1, "month": CYC, "account_id": acc["id"], "description": "Test", "amount": 1})
check("an account's currency locks once it has a payment", "currency" in j("get", f"/api/setup/accounts/{acc['id']}")["locked"])
check("an account in use can't be deleted", "Stop using it instead" in j("delete", f"/api/setup/accounts/{acc['id']}", 409, json={"reason": "x"})["error"])

# ---------- 5. general settings ----------
j("patch", "/api/setup/settings", 400, json={"values": {"cycle_rollover_day": 31}})
j("patch", "/api/setup/settings", 400, json={"values": {"payee_default_category": "nonsense"}})
j("patch", "/api/setup/settings", json={"values": {"cycle_rollover_day": 5, "soon_days": 2, "organisation_name": "Example Group"}})
check("the payroll month follows the rollover day", db.current_cycle(date(2026, 11, 6)) == "2026-11" and db.current_cycle(date(2026, 11, 5)) == "2026-10")
check("meta and Next up read the new values", j("get", "/api/meta")["settings"]["organisation_name"] == "Example Group" and nextup._soon() == 2)
j("patch", "/api/setup/settings", json={"values": {"cycle_rollover_day": 10}})
check("settings changes are in the trail", "General setting" in json.dumps(j("get", "/api/audit?tbl=app_settings")) or
      j("get", "/api/audit?tbl=app_settings")["entries"])

# ---------- 6. recurring payments: checks, defaults, stop, use again, delete ----------
for bad, word in (({"category": "nonsense"}, "payment types"), ({"due_day": 0}, "1 to 31"), ({"month_offset": 3}, "next month"),
                  ({"start_date": "2026-10-10", "end_date": "2026-10-01"}, "before the start"), ({"amount": "lots"}, "number"),
                  ({"account_id": fca["id"]}, "stopped")):
    e = j("post", "/api/payees", 400, json={"entity_id": 1, "name": "Bad", **bad})["error"]
    check(f"a recurring payment is refused: {word}", word in e, e)
j("post", "/api/payees", json={"entity_id": 1, "name": "Water bill"})
with sqlite3.connect(config.DB_PATH) as r:
    r.row_factory = sqlite3.Row
    w = dict(r.execute("SELECT * FROM payees WHERE name = 'Water bill'").fetchone())
check("a new recurring payment takes the defaults from general settings and the cash book account",
      (w["category"], w["due_day"], w["month_offset"], w["account_id"]) == ("utility", 6, 1, main["id"]), w)
use = j("get", f"/api/payees/{w['id']}/usage")
j("post", f"/api/payees/{w['id']}/stop", 400, json={})
j("post", f"/api/payees/{w['id']}/stop", json={"reason": "Moved to the landlord"})
check("stopping a recurring payment asks why", last_tx()["reason"] == "Moved to the landlord")
j("post", f"/api/payees/{w['id']}/use", json={"reason": "Back on our account"})
if use["can_delete"]:
    j("delete", f"/api/payees/{w['id']}", json={"reason": "Added by mistake"})
    check("an unused recurring payment is deleted", not sqlite3.connect(config.DB_PATH).execute("SELECT 1 FROM payees WHERE id = ?", (w["id"],)).fetchone())
check("a recurring payment in use can't be deleted", "Stop using it instead" in j("delete", "/api/payees/1", 409, json={"reason": "x"})["error"])

# ---------- 7. salary advances: the old-plan fix ----------
NXT = db.shift_month(CYC, 1)
j("post", "/api/months/open", json={"entity_id": 1, "month": NXT})


def salary(month):
    with sqlite3.connect(config.DB_PATH) as r:
        return r.execute("SELECT amount, notes FROM payments WHERE payee_id = 1 AND month = ?", (month,)).fetchone()


start = salary(NXT)
r = j("post", "/api/payees/1/advances", json={"monthly_deduction": 250, "start_month": NXT, "end_month": NXT, "note": "Laptop"})
after = salary(NXT)
check("adding an advance brings the deduction into the month already set up", start[0] == 3000 and after[0] == 2750
      and r["changes"] and "Laptop" in (after[1] or ""), (start, after, r))
aid = r["advance"]["id"]
r = j("patch", f"/api/advances/{aid}", json={"monthly_deduction": 300})
check("changing it changes the month's salary again", salary(NXT)[0] == 2700, (salary(NXT), r))
j("delete", f"/api/advances/{aid}", 400, json={})
r = j("delete", f"/api/advances/{aid}", json={"reason": "Repaid in full"})
check("removing it puts the salary back", salary(NXT)[0] == 3000 and r["changes"], (salary(NXT), r))
for bad in ({"monthly_deduction": 0, "start_month": NXT, "end_month": NXT}, {"monthly_deduction": 5, "start_month": NXT, "end_month": CYC}):
    j("post", "/api/payees/1/advances", 400, json=bad)
check("advances are refused for a payment that isn't a salary", "salary" in j("post", "/api/payees/2/advances", 400,
      json={"monthly_deduction": 5, "start_month": NXT, "end_month": NXT})["error"])
h = j("get", "/api/audit/record/payees/1")
check("a recurring payment's history includes its salary advances", any(ch["table"] == "advances" for ch in h["changes"]))

# ---------- 8. Tidy asks why ----------
j("post", "/api/entities/1/first-month", json={"month": CYC})
check("Tidy up refuses without a reason", "why" in j("post", "/api/months/tidy", 400, json={"entity_id": 1})["error"])
j("post", "/api/months/tidy", json={"entity_id": 1, "reason": "Months before tracking"})

# ---------- 9. filed months never change (review findings) ----------
j("post", "/api/months/close", json={"entity_id": 1, "month": NXT, "closed": True})
r = j("post", "/api/payees/1/advances", json={"monthly_deduction": 100, "start_month": NXT, "end_month": NXT})
check("an advance doesn't reach a filed month, and says so", salary(NXT)[0] == 3000 and any("marked as filed" in k for k in r["kept"]), (salary(NXT), r))
r = j("post", "/api/payees/2/stop", json={"reason": "Test"})
with sqlite3.connect(config.DB_PATH) as rr:
    left = rr.execute("SELECT COUNT(*) FROM payments WHERE payee_id = 2 AND month = ?", (NXT,)).fetchone()[0]
check("stopping a recurring payment leaves its payments in a filed month", left == 1, r)
j("post", "/api/payees/2/use", json={"reason": "Test"})
j("post", "/api/entities/1/first-month", json={"month": db.shift_month(NXT, 1)})
n = j("get", "/api/months/tidy?entity=1")
j("post", "/api/months/tidy", json={"entity_id": 1, "reason": "Before tracking"})
with sqlite3.connect(config.DB_PATH) as rr:
    kept_filed = rr.execute("SELECT COUNT(*) FROM payments WHERE entity_id = 1 AND month = ?", (NXT,)).fetchone()[0]
check("Tidy up never removes anything from a filed month", kept_filed > 0, n)
j("post", "/api/entities/1/first-month", json={"month": CYC})

# ---------- 10. the cash book and stopped accounts (review findings) ----------
check("the cash book is locked once a month is filed", "cash_book" in j("get", f"/api/setup/accounts/{main['id']}")["locked"])
spare = j("post", "/api/setup/accounts", json={"entity_id": 2, "fields": {"label": "Spare", "currency": "MYR"}})["id"]
j("post", f"/api/setup/accounts/{spare}/stop", json={"reason": "Not used"})
j("post", f"/api/setup/accounts/{spare}/use", json={"reason": "Used again"})
with sqlite3.connect(config.DB_PATH) as rr:
    books = rr.execute("SELECT COUNT(*) FROM accounts WHERE entity_id = 2 AND active = 1 AND cash_book = 1").fetchone()[0]
check("stopping and using an account again never makes a second cash book", books == 1, books)
check("a USD account can't be the cash book", "MYR" in j("post", "/api/setup/accounts", 400,
      json={"entity_id": 2, "fields": {"label": "USD2", "currency": "USD", "cash_book": True}})["error"])
pr = j("post", "/api/setup/accounts", json={"entity_id": 2, "fields": {"label": "Payroll", "currency": "MYR"}})["id"]
j("post", "/api/payees", json={"entity_id": 2, "name": "Contractor", "category": "consultant", "amount": 900, "account_id": pr})
check("an account recurring payments are paid from can't be stopped; the message names them",
      "Contractor" in j("post", f"/api/setup/accounts/{pr}/stop", 400, json={"reason": "x"})["error"])
check("an empty account on a recurring payment is no account, not an error",
      j("post", "/api/payees", json={"id": 1, "name": "Staff One", "account_id": 0})["ok"])
check("'Money received' isn't offered as the default type", "receipt" not in json.dumps(j("get", "/api/setup/settings")["fields"][2]["options"])
      and j("patch", "/api/setup/settings", 400, json={"values": {"payee_default_category": "receipt"}}))
check("a new company defaults to being kept in SQL Account", next(f for f in t["kinds"]["entities"]["fields"] if f["key"] == "uses_sql")["default"] == 1)

# ---------- 11. the trail ----------
with db.connect() as r:
    v = audit.verify(r)
    un = r.execute("SELECT COUNT(*) FROM audit_tx WHERE action = 'Unattributed app write'").fetchone()[0]
check("every Setup change was attributed and the trail checks out", v["ok"] and un == 0, v)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
