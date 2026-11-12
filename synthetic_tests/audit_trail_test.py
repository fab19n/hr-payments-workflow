"""The audit trail, end to end, on made-up records only (so this test can live in git, unlike tests/).

Run: .venv\\Scripts\\python -m synthetic_tests.audit_trail_test

Checks that every change made through the app is captured, attributed and sealed; that refused requests and rollbacks
leave nothing behind; that the append-only guards hold; that changes made outside the app are reported; that tampering is
detected; and that updating a records.db from update 15 changes nothing in the records themselves.
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-audit-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

SEED = {"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}],
     "payees": [{"name": "Staff One", "category": "salary", "amount": 3000, "due_day": 26},
                {"name": "Office Supplier", "category": "bill", "amount": 450, "due_day": 6, "month_offset": 1,
                 "advances": []}]},
    {"code": "AI", "name": "Example International Ltd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}],
     "payees": []},
]}
(tmp / "seed.json").write_text(json.dumps(SEED), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


def business_rows(con):
    """Every row of every table except the audit store, as text, to compare records before and after an update."""
    out = {}
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'audit_%'"):
        out[t] = [tuple(r) for r in con.execute(f'SELECT * FROM "{t}" ORDER BY rowid')]
    return out


# ---------- 1. a records.db at update 15, then updated to 17: the records don't change ----------
full = db.MIGRATIONS[:]
db.MIGRATIONS[:] = full[:15]
db.init()
c = db.connect()
c.execute("""INSERT INTO payments (entity_id, month, category, description, amount, due_date, created_at)
             VALUES (1, '2026-09', 'other', 'Before the trail', 10, '2026-09-26', '2026-09-01')""")
c.commit()
raw = sqlite3.connect(config.DB_PATH)
before = business_rows(raw)
raw.close()
c.close()
db.MIGRATIONS[:] = full
trail = db.init()
raw = sqlite3.connect(config.DB_PATH)
after = business_rows(raw)
# Every original column keeps its value (later updates add columns: compare each row's original part); new rows are listed.
added = {}
for t in after:
    if t == "app_settings":  # update 19's own table
        continue
    old = before.get(t, [])
    if any(new[:len(prev)] != prev for new, prev in zip(after[t], old)) or after[t][len(old):]:
        added[t] = after[t][len(old):] or "changed"
check("updating to 17 changes no record (only the update's own activity line is added)",
      set(added) <= {"activity"} and all("Saved a copy" in r[2] for r in added.get("activity", [])), added)
check("the update reports a clean trail", trail["entries"] >= 1 and trail["outside"] == 0 and not trail["head"]
      and not trail["triggers_repaired"] and trail["late_sealed"] == 0 and not trail["head_behind"], trail)
n_base = raw.execute("SELECT COUNT(*) FROM audit_row WHERE op = 'baseline'").fetchone()[0]
check("baseline covers every record", n_base == sum(len(v) for v in after.values()), (n_base, {t: len(v) for t, v in after.items()}))
raw.close()

# ---------- 2. the app's own requests ----------
client = app.test_client()
BASE = f"http://127.0.0.1:{config.SETTINGS['port']}"
H = {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:300])
    return r.get_json()


def last_tx():
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return r.execute("SELECT * FROM audit_tx ORDER BY id DESC LIMIT 1").fetchone()


def tx_count():
    with sqlite3.connect(config.DB_PATH) as r:
        return r.execute("SELECT COUNT(*) FROM audit_tx").fetchone()[0]


call("post", "/api/months/open", json={"entity_id": 1, "month": "2026-10", "auto": True})
t = last_tx()
check("an automatic month set-up is recorded as automatic, for its company", t["source"] == "auto" and t["entity_id"] == 1
      and t["action"] == "POST /api/months/open" and t["actor"] == audit.who()[0], dict(t))

with sqlite3.connect(config.DB_PATH) as r:
    task_id = r.execute("SELECT id FROM tasks WHERE entity_id = 1 AND month = '2026-10' ORDER BY id LIMIT 1").fetchone()[0]
call("post", f"/api/tasks/{task_id}", json={"note": "Waiting for the bank"})
t = last_tx()
check("a task note (not in the activity log) is captured", json.loads(t["counts"]) == {"tasks": {"update": 1}} and t["summary"] is None, dict(t))
call("post", f"/api/tasks/{task_id}", json={"done": True})
check("ticking a task records the log line with the change", "Ticked task" in (last_tx()["summary"] or ""))

pid = call("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "Printer toner", "amount": 120})["id"]
call("patch", f"/api/payments/{pid}", json={"amount": 135.5, "notes": "Two boxes"})
with sqlite3.connect(config.DB_PATH) as r:
    b, a = r.execute("SELECT before, after FROM audit_row WHERE tbl = 'payments' AND row_key = ? AND op = 'update' ORDER BY id DESC",
                     (str(pid),)).fetchone()
check("a payment edit keeps the values before and after", json.loads(b)["amount"] == 120 and json.loads(a)["amount"] == 135.5
      and json.loads(a)["notes"] == "Two boxes")
call("delete", f"/api/payments/{pid}")
with sqlite3.connect(config.DB_PATH) as r:
    gone = r.execute("SELECT before FROM audit_row WHERE tbl = 'payments' AND row_key = ? AND op = 'delete'", (str(pid),)).fetchone()
check("a removed payment keeps its whole row in the trail", gone and json.loads(gone[0])["description"] == "Printer toner")

n = tx_count()
call("post", "/api/payments", expect=400, json={"entity_id": 1, "month": "2026-10", "description": ""})
check("a refused request leaves no entry", tx_count() == n)

call("post", "/api/payees", json={"entity_id": 2, "name": "Rent from tenant", "category": "receipt", "amount": 2000, "due_day": 1})
check("a recurring payment saved for the second company is recorded against it", last_tx()["entity_id"] in (None, 2) and
      "payees" in json.loads(last_tx()["counts"]), dict(last_tx()))

call("post", "/api/budget/setup", json={"entity_id": 1, "month": "2026-10"})
call("post", "/api/budget/lines", json={"entity_id": 1, "month": "2026-10", "description": "Petty cash", "amount": 300})
check("budget changes are captured", "budget_lines" in json.loads(last_tx()["counts"]))

out = call("post", "/api/backup", json={})
t = last_tx()
with sqlite3.connect(config.DB_PATH) as r:
    ev = r.execute("SELECT after FROM audit_row WHERE tbl = 'backup' AND op = 'event' ORDER BY id DESC").fetchone()
check("a backup is an event with the zip's fingerprint", ev and json.loads(ev[0])["sha256"] == audit.file_sha256(Path(out["file"]))
      and json.loads(ev[0])["encrypted"] is False)

# ---------- 3. nothing unattributed, nothing unsealed, the chain checks out ----------
with db.connect() as r:
    v = audit.verify(r)
    unattributed = r.execute("SELECT COUNT(*) FROM audit_tx WHERE action = 'Unattributed app write'").fetchone()[0]
check("every change the app made was attributed", unattributed == 0)
check("nothing is left unsealed or outside, and the chain verifies", v["ok"] and v["outside"] == 0, v)

# ---------- 4. append-only ----------
raw = sqlite3.connect(config.DB_PATH)
for sql in ("UPDATE audit_row SET op = 'insert'", "DELETE FROM audit_row", "UPDATE audit_tx SET actor = 'x'", "DELETE FROM audit_tx",
            "DELETE FROM activity", "UPDATE activity SET what = 'x'"):
    try:
        raw.execute(sql)
        ok = False
    except sqlite3.DatabaseError as ex:
        ok = "can't be changed" in str(ex)
    check(f"refused: {sql}", ok)
raw.rollback()


# ---------- 5. later update steps, and ways of committing other than commit() ----------
def step_18(con):
    db.add_column(con, "payees", "grade", "TEXT")
    con.execute("UPDATE payees SET grade = 'G1'")                       # a backfill of the new column
    con.execute("CREATE TABLE IF NOT EXISTS step18_notes (id INTEGER PRIMARY KEY, text TEXT)")
    con.execute("INSERT INTO step18_notes (text) VALUES ('made by step 18')")  # filled without refresh(): baselined


n_tx = tx_count()
db.MIGRATIONS.append(step_18)
trail = db.init()
with sqlite3.connect(config.DB_PATH) as r:
    r.row_factory = sqlite3.Row
    txs = r.execute("SELECT action, late FROM audit_tx WHERE id > ? ORDER BY id", (n_tx,)).fetchall()
    grade = r.execute("SELECT COUNT(*) FROM audit_row WHERE tbl = 'payees' AND op = 'update' AND json_extract(after, '$.grade') = 'G1'").fetchone()[0]
    notes = r.execute("SELECT op FROM audit_row WHERE tbl = 'step18_notes'").fetchall()
check("a later update's copy line is sealed as itself, not as a crash", [t["action"] for t in txs][:2] == ["Saved a copy before updating", f"Update {len(db.MIGRATIONS)}"]
      and not any(t["late"] for t in txs) and trail["late_sealed"] == 0, [tuple(t) for t in txs])
check("a later step's backfill of a new column is captured", grade == len(SEED["entities"][0]["payees"]) + 1, grade)
check("a table a later step creates and fills is recorded (as a baseline) and captured from then on",
      [n["op"] for n in notes] == ["baseline"], [tuple(n) for n in notes])
check("start-up after an update repairs nothing", not trail["triggers_repaired"], trail)

with db.connect() as r:
    r.arm("user", "test: executescript")
    r.execute("UPDATE payees SET notes = 'before script' WHERE id = 1")
    r.executescript("UPDATE payees SET notes = 'in script' WHERE id = 1;")
    r.disarm()
    left = r.execute("SELECT COUNT(*) FROM audit_context").fetchone()[0]
    v = audit.verify(r)
check("executescript seals what was pending and never commits the context row", left == 0 and v["ok"], (left, v))
con2 = db.connect()
con2.arm("user", "test: with-block")
with con2:
    con2.execute("UPDATE payees SET notes = 'with block' WHERE id = 1")
con2.disarm()
check("a `with con:` block is sealed like commit()", last_tx()["action"] == "test: with-block" and audit.verify(con2)["ok"])
con2.close()

# ---------- 6. tables and columns with unusual names ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute('CREATE TABLE "payees backup" ("owner\'s note" TEXT, "a""b" INTEGER)')
raw.commit()
raw.close()
trail = db.init()
call("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "After odd table", "amount": 1})
with db.connect() as r:
    r.arm("user", "test: odd names")
    r.execute('INSERT INTO "payees backup" VALUES (\'it\'\'s fine\', 1)')
    r.commit()
    r.disarm()
    odd = r.execute("SELECT after FROM audit_row WHERE tbl = 'payees backup' AND op = 'insert'").fetchone()
check("a table added outside the app with an odd name doesn't stop start-up, and is captured",
      odd and json.loads(odd[0]) == {"owner's note": "it's fine", 'a"b': 1}, odd)

# ---------- 7. the head file ----------
head = audit.read_head()
audit.write_head({**head, "hash": "f" * 64})
with db.connect() as r:
    st = audit.status(r)
check("a head file whose fingerprint differs is reported as a rebuilt trail", st["head_rewritten"], st)
trail = db.init()
with sqlite3.connect(config.DB_PATH) as r:
    ev = r.execute("SELECT after FROM audit_row WHERE tbl = 'audit' AND row_key = 'head' ORDER BY id DESC").fetchone()
check("start-up records it in the trail before moving on", ev and json.loads(ev[0])["kind"] == "rewritten" and trail["head"]["kind"] == "rewritten")
check("and the window says so", any("rebuilt" in w for w in __import__("hrp.app", fromlist=["x"]).audit_warnings(trail)))
import shutil  # noqa: E402
older = tmp / "older.db"
with db.connect() as r:
    r.backup(sqlite3.connect(older))
call("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "After the copy", "amount": 2})
shutil.copy(older, config.DB_PATH)  # a backup restored while the app keeps running
call("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "After the restore", "amount": 3})
with sqlite3.connect(config.DB_PATH) as r:
    ev = r.execute("SELECT after FROM audit_row WHERE tbl = 'audit' AND row_key = 'head' ORDER BY id DESC").fetchone()
check("a records.db restored while the app runs is recorded by the next save, not silently rebased",
      ev and json.loads(ev[0])["kind"] == "behind")

# ---------- 8. accepting outside changes; same-minute backups ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute("UPDATE payees SET notes = 'edited elsewhere' WHERE id = 1")
raw.commit()
raw.close()
upto = client.get(BASE + "/api/audit/outside").get_json()["upto_id"]
call("post", "/api/audit/accept-outside", expect=400, json={"reason": "  ", "upto_id": upto})
call("post", "/api/audit/accept-outside", expect=400, json={"reason": "Note fixed in DB Browser"})  # which ones were checked?
call("post", "/api/audit/accept-outside", json={"reason": "Note fixed in DB Browser", "upto_id": upto})
st = client.get(BASE + "/api/audit/status").get_json()
check("outside changes are accepted only with a reason, then the trail is clean", st["outside"] == 0 and st["check"]["ok"]
      and last_tx()["reason"] == "Note fixed in DB Browser", st)
a = call("post", "/api/backup", json={})["file"]
b = call("post", "/api/backup", json={})["file"]
check("two backups in one minute are two files", a != b and Path(a).exists() and Path(b).exists(), (a, b))

# ---------- 9. a capture trigger dropped outside the app ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DROP TRIGGER audit_payees_u")
raw.execute("UPDATE payees SET amount = 1 WHERE id = 1")  # not recorded: the trigger is gone
raw.commit()
raw.close()
trail = db.init()
check("a missing capture trigger is put back, and the window warns that changes may be missing",
      "audit_payees_u" in trail["triggers_repaired"] and any("put back" in w for w in __import__("hrp.app", fromlist=["x"]).audit_warnings(trail)))

# ---------- 10. outside changes and tampering ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute("UPDATE payees SET amount = 3100 WHERE name = 'Staff One'")
raw.commit()
raw.close()
with db.connect() as r:
    check("a change made by another program is reported", audit.outside_rows(r) == 1)
    r.arm("user", "test: accept")
    audit.accept_outside(r, "Corrected the salary in DB Browser")
    r.commit()
    r.disarm()
    check("accepting it seals it, with the reason", audit.outside_rows(r) == 0 and audit.verify(r)["ok"])
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DROP TRIGGER audit_guard_audit_row_u")
raw.execute("UPDATE audit_row SET after = json_set(after, '$.amount', 1) WHERE tbl = 'payments' AND op = 'update'")
raw.commit()
raw.close()
with db.connect() as r:
    v = audit.verify(r)
check("an edited entry and a removed guard are both reported", not v["ok"] and len(v["problems"]) == 2, v["problems"])
db.init()
with db.connect() as r:
    v = audit.verify(r)
check("start-up puts the guard back and records that; the edited entry stays reported",
      v["problems"] and all("changed since" in p for p in v["problems"]), v["problems"])

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
