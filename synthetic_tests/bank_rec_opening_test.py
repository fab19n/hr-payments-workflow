"""A book opening and the lock (slice 4), on made-up records only: a company kept here and one kept in SQL Account.

For each, account Main has books from August 2026 (opening 1,000), August open, September signed off (carrying on from
August's closing), October open:
1. a book opening typed into signed-off September is refused with the lock message ("Main September 2026 is marked
   reconciled and locked") and nothing changes;
2. a book opening for open August that moves September's opening is refused the same way, and nothing changes;
3. a book opening for open October (after the signed-off month) is saved.
The SQL cash book's figures are left out of the central guard (they move with SQL), so for that company only the book
opening's own check stands in the way: it must compare the book side whatever the book source.

Run: .venv\\Scripts\\python -m synthetic_tests.bank_rec_opening_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-bank-rec-opening-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, recon  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Here Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "0000-8181"}]},
    {"code": "EXQ", "name": "Example Sql Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "0000-8282"}]},
]}), encoding="utf-8")


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:800]}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}
NOW = db.now()
con = db.connect()
con.arm("user", "test: two made-up companies with August open, September signed off, October open")
CO = {}
for code, uses_sql in (("EXH", 0), ("EXQ", 1)):
    eid = q("SELECT id FROM entities WHERE code = ?", (code,))[0]["id"]
    aid = q("SELECT id FROM accounts WHERE entity_id = ?", (eid,))[0]["id"]
    CO[code] = (eid, aid)
    con.execute("UPDATE entities SET uses_sql = ?, first_month = '2026-08' WHERE id = ?", (uses_sql, eid))
    con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-08', 1000, ?)", (aid, NOW))
    if uses_sql:
        imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'test.xlsx', ?, 3, 0)",
                          (eid, NOW)).lastrowid
        for n, (day, amt) in enumerate((("2026-08-10", 100), ("2026-09-10", 50), ("2026-10-10", 20)), 1):
            con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type,
                           kind, status) VALUES (?, ?, ?, ?, 'Test rent', 'Test Payee Chi', ?, 'out', 'PV', 'payment', 'unlinked')""",
                        (imp, eid, f"PV-OPEN-{n:03d}", day, amt))
    else:
        for day, amt in (("2026-08-10", 100), ("2026-09-10", 50), ("2026-10-10", 20)):
            con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                           direction, created_at) VALUES (?, ?, ?, 'other', 'Test Payee Psi rent', ?, ?, ?, 'manual', 'out', ?)""",
                        (eid, day[:7], aid, amt, day, day, NOW))
    for month, opening, closing, signed in (("2026-08", 1000, 900, False), ("2026-09", 900, 850, True), ("2026-10", 850, 830, False)):
        con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?, ?)", (aid, month, opening, closing, NOW, NOW if signed else None, "review" if signed else None))
con.commit()
con.close()


def book(aid):
    with db.connect() as r:
        return recon.signed_figures(r, {aid: "2026-08"})


def opening(aid, month):
    rows = q("SELECT amount FROM book_openings WHERE account_id = ? AND month = ?", (aid, month))
    return rows[0]["amount"] if rows else None


for code, kind in (("EXH", "kept here"), ("EXQ", "kept in SQL Account")):
    eid, aid = CO[code]
    was = book(aid)
    sep = [v for v in was.values()]
    check(f"({kind}) signed-off September's books run from August's opening (opening 900)",
          len(sep) == 1 and sep[0][2] == "ok" and abs(sep[0][3] - 900) < 0.005, was)
    r = c.post(BASE + "/api/recon/book-opening", headers=H, json={"entity_id": eid, "account_id": aid, "month": "2026-09", "amount": 9999})
    check(f"({kind}) a book opening typed into signed-off September is refused with the lock message",
          r.status_code == 400 and "Main September 2026 is marked reconciled and locked" in (r.get_json() or {}).get("error", ""),
          (r.status_code, r.data[:300]))
    check(f"({kind}) ...and nothing changes", opening(aid, "2026-09") is None and book(aid) == was)
    r = c.post(BASE + "/api/recon/book-opening", headers=H, json={"entity_id": eid, "account_id": aid, "month": "2026-08", "amount": 700})
    check(f"({kind}) a book opening for open August that moves September's opening is refused with the lock message",
          r.status_code == 400 and "Main September 2026 is marked reconciled and locked" in (r.get_json() or {}).get("error", ""),
          (r.status_code, r.data[:300]))
    check(f"({kind}) ...and nothing changes", opening(aid, "2026-08") == 1000 and book(aid) == was)
    r = c.post(BASE + "/api/recon/book-opening", headers=H, json={"entity_id": eid, "account_id": aid, "month": "2026-10", "amount": 5000})
    check(f"({kind}) a book opening for open October (after the signed-off month) is saved",
          r.status_code == 200 and opening(aid, "2026-10") == 5000 and book(aid) == was, (r.status_code, r.data[:300]))

print("\nAll book opening lock checks passed.")
