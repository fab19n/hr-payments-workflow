"""The lock's backstop (slice 4): a signed-off month's figures never change, whatever route writes, on made-up records only.

1. The side doors the reviews found are refused, and nothing changes: Setup › Companies switching a company kept here to
   Kept in SQL Account (its signed-off month's book source would flip); a payment created from a bank line in an open
   month whose closing a signed-off month carries on from; a book opening that moves a signed-off month.
2. Their figure-neutral versions go through: a company's name changed; a payment created from a line of a later open
   month; the same book opening saved again; a payment with no amount moved to another account in a signed-off month.
3. Every mutating route the app has (POST, PATCH and DELETE in app.url_map), driven with made-up ids and bodies against
   a company with a signed-off month: afterwards that month's figures (recon.guard_figures: book source, book figures,
   lines and links) are exactly as they were, whether the route refused or changed something else. A new side door
   fails this check.

Made-up company EXG (kept here), account Main (books from October), October open, November signed off and carrying on
from October's closing, December open; account Spare.

Run: .venv\\Scripts\\python -m synthetic_tests.bank_rec_guard_test
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-bank-rec-guard-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, recon  # noqa: E402
from hrp import app as app_module  # noqa: E402
from hrp.app import app  # noqa: E402
from flask import jsonify, request  # noqa: E402


# A throwaway route with no lock check of its own, so only the guard at the commit stands between it and a signed-off
# month (registered before the first request, as Flask asks).
@app.post("/api/test-guard/raw")
def _test_guard_raw():
    b = request.get_json()
    c = app_module.con()
    pid, mode = b["payment_id"], b["mode"]
    if mode == "update":
        c.execute("UPDATE payments SET amount = amount + 1 WHERE id = ?", (pid,))
    elif mode == "cursor":
        c.cursor().execute("UPDATE payments SET amount = amount + 1 WHERE id = ?", (pid,))
    elif mode == "with":
        c.execute("WITH one AS (SELECT 1) UPDATE payments SET amount = amount + 1 WHERE id = ?", (pid,))
    elif mode == "swap":  # two payments of one amount swap paid months: the totals stay, the entries counted change
        da, db_ = (c.execute("SELECT paid_date FROM payments WHERE id = ?", (x,)).fetchone()[0] for x in (pid, b["other_id"]))
        c.execute("UPDATE payments SET paid_date = ? WHERE id = ?", (db_, pid))
        c.execute("UPDATE payments SET paid_date = ? WHERE id = ?", (da, b["other_id"]))
    elif mode == "neutral":
        c.execute("UPDATE payments SET notes = 'Test note, no figure' WHERE id = ?", (pid,))
    elif mode == "unsign":  # taking a sign-off away by hand, not through Reopen month
        c.execute("UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL WHERE id = ?", (b["statement_id"],))
    elif mode == "delstmt":  # an open statement deleted with its lines (one of them counted in signed-off November)
        c.execute("DELETE FROM statement_lines WHERE statement_id = ?", (b["statement_id"],))
        c.execute("DELETE FROM statements WHERE id = ?", (b["statement_id"],))
    elif mode in ("big", "bigmove"):  # one transaction writing well over 2 MB (an import's worth of SQL entries)
        imp = c.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'big.xlsx', ?, 0, 0)",
                        (b["entity_id"], db.now())).lastrowid
        c.executemany("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type,
                         kind, status) VALUES (?, ?, ?, '2026-12-15', ?, 'Test payee', ?, 'out', 'PV', 'payment', 'unlinked')""",
                      [(imp, b["entity_id"], f"PV-{mode.upper()}-{n:05d}", "Test description " + "x" * 400, n + 1) for n in range(6000)])
        c.execute("UPDATE payments SET notes = 'Test big import' WHERE id = ?", (pid,))
        # Figure-neutral, on the signed-off account: the guard has to read the records as last committed to see that.
        c.execute("UPDATE book_openings SET set_at = ? WHERE account_id = ? AND month = '2026-10'", (db.now(), b["account_id"]))
        if mode == "bigmove":
            c.execute("UPDATE payments SET amount = amount + 1 WHERE id = ?", (pid,))
    elif mode == "savepoint":
        c.execute("SAVEPOINT test_guard")
        c.execute("UPDATE payments SET amount = amount + 1 WHERE id = ?", (pid,))
        ok = recon.guard_ok(c)
        c.execute("ROLLBACK TO test_guard")
        c.execute("RELEASE test_guard")
        ok_after = recon.guard_ok(c)
        c.commit()
        return jsonify({"ok_in_savepoint": ok, "ok_after_rollback": ok_after})
    elif mode == "rollback_reuse":
        # The guard reads the trail in a savepoint, the savepoint is rolled back (no guard_reset: nothing tells the guard)
        # and the trail's ids are used again: first a write that moves November (by executemany), then enough notes to
        # bring the newest id back to at least the last one the guard read before.
        c.execute("SAVEPOINT test_reuse")
        for n in range(6):
            c.execute("UPDATE payments SET notes = ? WHERE id = ?", (f"Test before rollback {n}", pid))
        ok = recon.guard_ok(c)
        c.execute("ROLLBACK TO test_reuse")
        c.execute("RELEASE test_reuse")
        c.executemany("UPDATE payments SET amount = amount + 1 WHERE id = ?", [(pid,)])
        c.executemany("UPDATE payments SET notes = ? WHERE id = ?", [(f"Test after rollback {n}", pid) for n in range(8)])
        if not ok:
            return jsonify({"error": "the savepoint's notes alone were refused"}), 500
    elif mode == "reopen_reforge":  # Reopen month, then a sign-off put back by hand in the same transaction
        st = c.execute("SELECT * FROM statements WHERE id = ?", (b["statement_id"],)).fetchone()
        recon.reopen(c, recon._ent(c, b["entity_id"]), st, "Test: reopened to sign by hand")
        c.execute("UPDATE statements SET reconciled_at = '2026-12-01T09:00:00', reconciled_how = 'review' WHERE id = ?", (st["id"],))
    elif mode == "stale_allow":  # a sign-off committed, then on the same connection a later transaction clears it by hand
        st = c.execute("SELECT * FROM statements WHERE id = ?", (b["statement_id"],)).fetchone()
        recon.sign_off_before_tracking(c, recon._ent(c, b["entity_id"]), st, "Test: reconciled before", True)
        c.commit()
        if getattr(c, "_recon_signoffs", None):  # what the sign-off was let through for ends with its own transaction
            return jsonify({"error": "the sign-off's allowance outlived its commit"}), 500
        c.execute("UPDATE statements SET reconciled_at = NULL, reconciled_how = NULL WHERE id = ?", (st["id"],))
    elif mode == "script":
        c.executescript("UPDATE payments SET amount = amount + 1 WHERE id = %d;" % int(pid))
    c.commit()
    return jsonify({"ok": True})

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXG", "name": "Example Guard Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "0000-7171"},
                                                                  {"label": "Spare", "bank": "Example Bank", "number": "0000-7272"}]},
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


def call(method, path, expect=None, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert expect is None or r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r


EID = q("SELECT id FROM entities WHERE code = 'EXG'")[0]["id"]
MAIN = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Main'", (EID,))[0]["id"]
SPARE = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Spare'", (EID,))[0]["id"]
NOW = db.now()
con = db.connect()
con.arm("user", "test: a made-up company kept here with October open, November signed off, December open")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (EID,))
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 1000, ?)", (MAIN, NOW))


def pay(desc, amount, month, paid, acct=MAIN):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                          direction, created_at) VALUES (?, ?, ?, 'other', ?, ?, ?, ?, ?, 'out', ?)""",
                       (EID, month, acct, desc, amount, paid or month + "-10", paid, "manual" if paid else None, NOW)).lastrowid


def stmt(month, opening, lines, signed=False):
    sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how) "
                      "VALUES (?, ?, ?, ?, ?, 1, ?, ?)", (MAIN, month, opening, round(opening + sum(x[2] for x in lines), 2), NOW,
                                                          NOW if signed else None, "review" if signed else None)).lastrowid
    out, bal = [], opening
    for n, (day, desc, amt, pid, status, note) in enumerate(lines, 1):
        bal = round(bal + amt, 2)
        out.append(con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status,
                                  note, confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (sid, n, day, desc, amt, bal, pid, status, note, NOW if pid or status == "no_docs" else None)).lastrowid)
    return sid, out


P_NOV = pay("Test Payee Rho rent", 200, "2026-11", "2026-11-05")
P_NOV2 = pay("Test Payee Sigma rates", 50, "2026-11", "2026-11-07")
P_OCT = pay("Test Payee Tau fees", 300, "2026-10", None)
P_NOAMT = pay("Test Payee Upsilon estimate", None, "2026-11", "2026-11-20")
P_DEC50 = pay("Test Payee Phi rates", 50, "2026-12", "2026-12-03")  # the same amount as P_NOV2, paid in December
S_OCT, (L_OCT, L_OCT2) = stmt("2026-10", 1000, [("2026-10-12", "IBG DR WEB HOSTING", -100, None, "unmatched", None),
                                                ("2026-10-14", "IBG DR TEST PAYEE TAU", -300, None, "unmatched", None)])
S_NOV, (L_NOV1, L_NOV2, L_NOV3) = stmt("2026-11", 600, [("2026-11-05", "IBG DR TEST PAYEE RHO", -200, P_NOV, "matched", None),
                                                        ("2026-11-07", "IBG DR TEST PAYEE SIGMA", -50, P_NOV2, "matched", None),
                                                        ("2026-11-30", "SERVICE CHARGE", -5, None, "no_docs", "Bank charge")], signed=True)
S_DEC, (L_DEC,) = stmt("2026-12", 345, [("2026-12-03", "IBG DR DOMAIN RENEWAL", -20, None, "unmatched", None)])
S_AUG, _ = stmt("2026-08", 0, [])  # before tracking began: signed off the before-tracking way below
# An open January statement whose bank charge is dated in November: November's books count it (by its date).
S_JAN, _ = stmt("2027-01", 325, [("2026-11-28", "SERVICE CHARGE LATE", -3, None, "no_docs", "Bank charge")])
con.commit()
con.close()


def figures():
    with db.connect() as r:  # November of Main, from November on (the months the checks below are about)
        return recon.guard_figures(r, {MAIN: "2026-11"})


before = figures()
check("November is held by the guard with its book figures (opening carried on from October's closing)",
      S_NOV in before and before[S_NOV][1][0] == "payments" and before[S_NOV][1][2] == "ok", before.get(S_NOV))


def same_nov(what):
    now = figures()
    check(what, now.get(S_NOV) == before[S_NOV], (now.get(S_NOV), before[S_NOV]))


# ---------- 1. the side doors are refused ----------
r = call("patch", f"/api/setup/entities/{EID}", json={"fields": {"uses_sql": True}})
check("Setup › Companies: switching the company to Kept in SQL Account (November's book source would flip) is refused",
      r.status_code in (400, 409) and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and q("SELECT uses_sql FROM entities WHERE id = ?", (EID,))[0]["uses_sql"] == 0, r.get_json())
same_nov("...November unchanged")
r = call("post", f"/api/statement-lines/{L_OCT}", json={"create_payment": {"description": "Test web hosting"}})
check("creating a payment from an open October line (November carries on from October's closing) is refused",
      r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and not q("SELECT 1 FROM payments WHERE description = 'Test web hosting'")
      and q("SELECT payment_id FROM statement_lines WHERE id = ?", (L_OCT,))[0]["payment_id"] is None, r.get_json())
r = call("post", "/api/recon/apply", json={"entity_id": EID, "statement_id": S_OCT, "checked": True,
                                           "rows": [{"line_id": L_OCT, "create_payment": {"description": "Test web hosting"}}]})
check("...also through Apply on the review", r.status_code == 400 and "locked" in r.get_json()["error"]
      and not q("SELECT 1 FROM payments WHERE description = 'Test web hosting'"), r.get_json())
r = call("post", "/api/recon/book-opening", json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "amount": 900})
check("a book opening for October that moves November is refused", r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and q("SELECT amount FROM book_openings WHERE account_id = ? AND month = '2026-10'", (MAIN,))[0]["amount"] == 1000, r.get_json())
same_nov("...November unchanged after all three")

# ---------- 2. their figure-neutral versions go through ----------
r = call("patch", f"/api/setup/entities/{EID}", json={"fields": {"name": "Example Guard Renamed Sdn Bhd"}})
check("the company's name changed (no figure moves) is saved", r.status_code == 200
      and q("SELECT name FROM entities WHERE id = ?", (EID,))[0]["name"] == "Example Guard Renamed Sdn Bhd", r.get_json())
r = call("post", f"/api/statement-lines/{L_DEC}", json={"create_payment": {"description": "Test domain renewal"}})
check("a payment created from a line of open December (after the signed-off month) is saved", r.status_code == 200
      and q("SELECT 1 FROM payments WHERE description = 'Test domain renewal'"), r.get_json())
r = call("post", "/api/recon/book-opening", json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "amount": 1000})
check("the same book opening saved again (no figure moves) is saved", r.status_code == 200, r.get_json())
r = call("patch", f"/api/payments/{P_NOAMT}", json={"account_id": SPARE})
check("a payment with no amount (in no book) moved to another account in signed-off November is saved", r.status_code == 200
      and q("SELECT account_id FROM payments WHERE id = ?", (P_NOAMT,))[0]["account_id"] == SPARE, r.get_json())
same_nov("...November unchanged after all four")

# ---------- 2b. the guard itself, on a route with no lock check of its own ----------
amount = lambda pid: q("SELECT amount FROM payments WHERE id = ?", (pid,))[0]["amount"]
for mode in ("update", "cursor", "with"):
    r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": mode})
    check(f"a write that moves signed-off November's figures with no check of its own ({mode}) is refused at the commit",
          r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"] and amount(P_NOV) == 200, (r.status_code, r.data[:300]))
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV2, "other_id": P_DEC50, "mode": "swap"})
check("two payments of one amount swapping paid months (November's totals the same, its entries not) is refused",
      r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and q("SELECT paid_date FROM payments WHERE id = ?", (P_NOV2,))[0]["paid_date"] == "2026-11-07", (r.status_code, r.data[:300]))
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "script"})
check("a script (which would commit by itself, past the guard) isn't run on a guarded connection", r.status_code >= 400 and amount(P_NOV) == 200, r.status_code)
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "neutral"})
check("a figure-neutral write in the same style (a note) is saved", r.status_code == 200
      and q("SELECT notes FROM payments WHERE id = ?", (P_NOV,))[0]["notes"] == "Test note, no figure")
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "savepoint"}).get_json()
check("in a savepoint, guard_ok is False after such a write and True again once it is rolled back",
      r == {"ok_in_savepoint": False, "ok_after_rollback": True} and amount(P_NOV) == 200, r)
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "rollback_reuse"})
check("after a rollback to a savepoint the guard had read in, a write moving November on the trail's reused ids "
      "(executemany) is still refused", r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and amount(P_NOV) == 200 and not q("SELECT 1 FROM payments WHERE notes LIKE 'Test after rollback%'"), (r.status_code, r.data[:300]))
r = call("post", "/api/recon/before-tracking", json={"entity_id": EID, "statement_id": S_AUG, "checked": True, "note": "Test: reconciled before"})
check("a sign-off (the month's own sign-off changes, the app's own way) passes the guard", r.status_code == 200
      and q("SELECT reconciled_at FROM statements WHERE id = ?", (S_AUG,))[0]["reconciled_at"], r.get_json())
r = call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": S_AUG, "reason": "Test: reopened again"})
check("...and so does a reopen", r.status_code == 200 and not q("SELECT reconciled_at FROM statements WHERE id = ?", (S_AUG,))[0]["reconciled_at"])
NOV_AT = q("SELECT reconciled_at FROM statements WHERE id = ?", (S_NOV,))[0]["reconciled_at"]
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "reopen_reforge", "statement_id": S_NOV, "entity_id": EID})
check("Reopen month followed, in the same transaction, by a sign-off put back by hand is refused (the reopen lets only "
      "its own change through)", r.status_code == 400 and q("SELECT reconciled_at FROM statements WHERE id = ?", (S_NOV,))[0]["reconciled_at"] == NOV_AT
      and not q("SELECT 1 FROM recon_reopens WHERE reason = 'Test: reopened to sign by hand'"), (r.status_code, r.data[:300]))
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "stale_allow", "statement_id": S_AUG, "entity_id": EID})
check("a sign-off saved, then on the same connection a later transaction clearing it by hand is refused (the sign-off's "
      "allowance ended with its own commit)", r.status_code == 400 and "locked" in (r.get_json() or {}).get("error", "")
      and q("SELECT reconciled_at FROM statements WHERE id = ?", (S_AUG,))[0]["reconciled_at"], (r.status_code, r.data[:300]))
r = call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": S_AUG, "reason": "Test: reopened once more"})
check("...and Reopen month still takes it back the app's own way", r.status_code == 200
      and not q("SELECT reconciled_at FROM statements WHERE id = ?", (S_AUG,))[0]["reconciled_at"], r.get_json())
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "unsign", "statement_id": S_NOV})
check("taking November's sign-off away by hand (not through Reopen month) is refused",
      r.status_code == 400 and q("SELECT reconciled_at FROM statements WHERE id = ?", (S_NOV,))[0]["reconciled_at"], (r.status_code, r.data[:200]))
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "delstmt", "statement_id": S_JAN})
check("deleting an open statement whose bank charge is dated in signed-off November is refused (the line's month, from its before image)",
      r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"]
      and q("SELECT 1 FROM statements WHERE id = ?", (S_JAN,)), (r.status_code, r.data[:200]))
_reads, _committed = [], recon._committed
recon._committed = lambda: (_reads.append(1), _committed())[1]  # counts the guard's reads of the records as last committed
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "big", "entity_id": EID, "account_id": MAIN})
recon._committed = _committed
check("one request writing well over 2 MB (6,000 SQL entries, and a figure-neutral change on signed-off Main) is saved with the guard on",
      r.status_code == 200 and q("SELECT COUNT(*) AS n FROM sql_entries WHERE doc_no LIKE 'PV-BIG-%'")[0]["n"] == 6000, (r.status_code, r.data[:300]))
check("...and the guard's final check read the records as last committed itself (it read them; no fall-back logged)",
      _reads and not q("SELECT 1 FROM activity WHERE what LIKE 'The bank reconciliation lock''s final check couldn''t read%'"), _reads)
r = call("post", "/api/test-guard/raw", json={"payment_id": P_NOV, "mode": "bigmove", "entity_id": EID, "account_id": MAIN})
check("...while the same large transaction with a write that moves November is refused, all of it undone",
      r.status_code == 400 and "November 2026 is marked reconciled and locked" in r.get_json()["error"] and amount(P_NOV) == 200
      and q("SELECT COUNT(*) AS n FROM sql_entries WHERE doc_no LIKE 'PV-BIG-%'")[0]["n"] == 6000, (r.status_code, r.data[:300]))
same_nov("...November unchanged after the guard's own checks")
with db.connect() as cx:  # the big made-up entries go, so the route sweep below isn't creating 6,000 payments from them
    cx.arm("user", "test: the large made-up import taken out again")
    cx.execute("DELETE FROM sql_entries WHERE doc_no LIKE 'PV-BIG-%'")

# ---------- 2c. the guard's cost: a made-up company with two accounts of 36 signed-off months ----------
# Big enough that a guard working out every signed-off month (or every month of the account touched) is clearly
# slower; the right one works out only the months a change can reach, so it costs next to nothing here.
import time  # noqa: E402
con = db.connect()
con.arm("user", "test: a made-up company with three years signed off on two accounts")
con.execute("INSERT INTO entities (code, name, uses_sql, first_month) VALUES ('EXT', 'Example Timing Sdn Bhd', 0, '2024-01')")
TE = con.execute("SELECT id FROM entities WHERE code = 'EXT'").fetchone()[0]
months = [db.shift_month("2024-01", i) for i in range(37)]
keep, TA = None, None
for k, label in enumerate(("Timing", "Timing two")):
    acct = con.execute("INSERT INTO accounts (entity_id, label, bank, number, currency) VALUES (?, ?, 'Example Bank', ?, ?)",
                       (TE, label, f"0000-90{k}0", "MYR" if k == 0 else "USD")).lastrowid
    TA = TA or acct
    con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2024-01', 100000, ?)", (acct, NOW))
    bal = 100000.0
    for i, m in enumerate(months):
        signed = i < 36 or k == 1
        sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how) "
                          "VALUES (?, ?, ?, ?, ?, 1, ?, ?)", (acct, m, bal, bal - 30 * 10, NOW, NOW if signed else None, "review" if signed else None)).lastrowid
        for n in range(30):
            day = f"{m}-{n % 28 + 1:02d}"
            pid = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date,
                                 paid_source, direction, created_at) VALUES (?, ?, ?, 'other', ?, 10, ?, ?, ?, 'manual', 'out', ?)""",
                              (TE, m, acct, f"Test Payee Timing {k}-{n}", "MYR" if k == 0 else "USD", day, day if signed else None, NOW)).lastrowid
            bal = round(bal - 10, 2)
            con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
                           VALUES (?, ?, ?, ?, -10, ?, ?, ?, ?)""", (sid, n + 1, day, f"IBG DR TEST PAYEE TIMING {k}-{n}", bal,
                                                                      pid if signed else None, "matched" if signed else "unmatched", NOW if signed else None))
            keep = keep or pid
con.commit()
con.close()


def undo_rematch():
    with db.connect() as r:
        r.arm("user", "test: the open month's lines back to explain, for the next timing")
        r.execute("""UPDATE statement_lines SET payment_id = NULL, status = 'unmatched', confirmed_at = NULL
                     WHERE statement_id = (SELECT id FROM statements WHERE account_id = ? AND month = ?)""", (TA, months[-1]))
        r.execute("UPDATE payments SET paid_date = NULL, paid_source = NULL WHERE account_id = ? AND month = ?", (TA, months[-1]))


def once(run, setup=None):
    if setup:
        setup()
    t0 = time.perf_counter()
    run()
    return time.perf_counter() - t0


patch = lambda: call("patch", f"/api/payments/{keep}", 200, json={"notes": f"Test note {time.perf_counter()}"})
matched = []
rematch = lambda: matched.append(call("post", "/api/statements/rematch", 200, json={"entity_id": TE}).get_json()["matched"])
best = {"patch": [9e9, 9e9], "rematch": [9e9, 9e9]}  # the fastest of each, guard on and off, taken in turns
for _ in range(7):
    for side in (0, 1):
        if side:  # the same operation with the guard off: no check at the commit, none in a bulk step
            recon.GUARD.check, keep_ok, recon.guard_ok = (lambda con: None), recon.guard_ok, (lambda con: True)
        best["patch"][side] = min(best["patch"][side], once(patch))
        best["rematch"][side] = min(best["rematch"][side], once(rematch, undo_rematch))
        if side:
            del recon.GUARD.check
            recon.guard_ok = keep_ok
ratios = (best["patch"][0] / best["patch"][1], best["rematch"][0] / best["rematch"][1])
print(f"     (notes-only PATCH {best['patch'][0] * 1000:.1f} ms with the guard, {best['patch'][1] * 1000:.1f} ms without: x{ratios[0]:.2f}; "
      f"rematch {best['rematch'][0] * 1000:.0f} ms with, {best['rematch'][1] * 1000:.0f} ms without: x{ratios[1]:.2f})")
check("the rematch timed does real work: it matches the open month's 30 lines each time", matched and min(matched) == 30, matched)
check("with two accounts of 36 signed-off months, a notes-only payment change and a rematch of the open month cost at most "
      "twice as much with the guard as without (the fastest of 7 each; a guard not scoped to the accounts and months touched "
      "costs 15 to 50 times as much here)", all(x <= 2.0 for x in ratios), ratios)
# ---------- 3. every mutating route, against signed-off November ----------
SKIP = re.compile(r"^/api/(backup|settings/|audit-pack|auditor-export|setup/import|test-guard/)")  # files outside the records' tables, new records only, this test's own route
ids = {"aid": [1], "did": [1], "eid": [EID], "lid": [L_NOV1, L_NOV3, L_OCT], "pid": [P_NOV, P_NOV2], "sid": [1, S_NOV], "tid": [1],
       "rid": [MAIN, EID], "row_id": [1], "nid": [1]}
words = {"kind": ["accounts", "entities"], "act": ["stop", "use"], "which": ["logo"]}
bodies = [{}, {"amount": 1, "paid_date": "2026-11-25", "account_id": SPARE, "direction": "in", "description": "Test probe", "category": "other",
               "entity_id": EID, "month": "2026-11", "reason": "Test probe"},
          {"payment_id": P_NOV2, "payment_ids": [P_NOV, P_NOV2], "status": "unmatched", "note": "Test probe", "entity_id": EID},
          {"create_payment": {"description": "Test probe payment"}, "entity_id": EID, "statement_id": S_NOV, "account_id": MAIN},
          {"entity_id": EID, "account_id": MAIN, "statement_id": S_NOV, "month": "2026-11", "amount": 5, "checked": True, "key": "x",
           "rows": [{"line_id": L_NOV1, "payment_id": P_NOV2}], "line_ids": [L_NOV1], "note": "Test probe"},
          {"entity_id": EID, "account_id": MAIN, "month": "2026-10", "amount": 700, "checked": True, "rows": [{"line_id": L_OCT, "no_docs": True}]},
          {"fields": {"uses_sql": True, "first_month": "2026-12", "currency": "USD", "cash_book": True, "label": "Test probe", "name": "Test probe"},
           "entity_id": EID, "reason": "Test probe"},
          {"amount": None, "account_id": 0, "paid_date": "", "reason": "Test probe"}]
rules = sorted(((str(r), m) for r in app.url_map.iter_rules() for m in r.methods & {"POST", "PATCH", "DELETE"}), key=str)
tried = passed = 0
for rule, method in rules:
    if not rule.startswith("/api/") or SKIP.match(rule):
        continue
    names = re.findall(r"<(?:\w+:)?(\w+)>", rule)
    variants = [{}]
    for n in names:
        variants = [dict(v, **{n: x}) for v in variants for x in (words.get(n) or ids.get(n) or [1])]
    for v in variants:
        path = re.sub(r"<(?:\w+:)?(\w+)>", lambda m: str(v[m.group(1)]), rule)
        for b in bodies:
            if path == "/api/recon/reopen" and b.get("reason"):
                continue  # reopening with a reason is the one way to change a signed-off month; it is checked on its own
            try:
                resp = getattr(c, method.lower())(BASE + path, headers=H, json=b)
                passed += 200 <= resp.status_code < 300
            except Exception as ex:  # a crash on a made-up body is not this test's concern; what it wrote is undone
                print(f"     ({method} {path} raised {type(ex).__name__})")
            tried += 1
            now = figures()
            if now.get(S_NOV) != before[S_NOV]:
                check(f"{method} {path} with {json.dumps(b)[:120]} leaves signed-off November as it was", False, (now.get(S_NOV), before[S_NOV]))
check(f"every mutating route ({len(rules)} route-methods, {tried} requests with made-up ids and bodies) leaves signed-off November's "
      "figures, lines and links exactly as they were", tried > 300 and figures().get(S_NOV) == before[S_NOV], tried)
print(f"     ({passed} of the {tried} requests got past validation and were saved)")
check("...and the sweep reaches the writing code: at least 60 of its requests were accepted (2xx), not only refused", passed >= 60, passed)
r = call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": S_NOV, "reason": "Test: reopened on purpose"})
check("...and reopening with a reason (the one way in) still works", r.status_code == 200 and not q("SELECT reconciled_at FROM statements WHERE id = ?", (S_NOV,))[0]["reconciled_at"])

print("\nAll lock backstop checks passed.")
