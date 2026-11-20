"""Bank and reconciliation (slice 4), the server, on made-up records only.

1. The link table keeps every link: update 39 copies each bank line's payment into it (run again on records whose table
   was emptied, it puts them back).
2. One statement line can be linked to several payments (a bulk transfer): each stands for its own amount, takes the
   line's date as its paid date when it had none, and the month agrees with the bank. Undone, every payment is freed.
3. The No money moved pairs: an in and an out of one amount on one day that never touched the bank are found; the
   sign-off is refused while a pair is unconfirmed, or not nil (a reversal keyed at another amount in SQL); confirming
   needs a reason, and a pair that isn't nil can't be confirmed.
4. The sign-off keeps the note the app writes as the month stood, the free note and the declared Prepared by.
5. The lock: a signed-off month refuses changes to its lines (link, undo, apply, confirm), to its pairs, to its book
   opening, and to its payments' bank fields through the payment routes (amount, account move, removal, a new payment
   paid in it); a field the bank doesn't hold still changes.
6. Reopen month: the old Undo sign-off route is gone; reopening needs a reason, is logged with the sign-off it undid,
   and the month needs the sign-off again; a month a later signed-off month carries on from can't be reopened alone.

Made-up company EXK (kept here) with account Main (number 0000-4321), and made-up company EXL (kept in SQL Account)
whose cash book holds a bank charge and its reversal.

Run: .venv\\Scripts\\python -m synthetic_tests.bank_rec_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-bank-rec-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, recon  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXK", "name": "Example Kept Here Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "0000-4321"},
                                                                      {"label": "Spare", "bank": "Example Bank", "number": "0000-8765"}]},
    {"code": "EXL", "name": "Example Ledger Sdn Bhd", "accounts": [{"label": "Cash book", "bank": "Example Bank", "number": "0000-5555"}]},
    {"code": "EXN", "name": "Example No Account Sdn Bhd", "accounts": [{"label": "Solo", "bank": "Example Bank", "number": "0000-6161"},
                                                                       {"label": "Other", "bank": "Example Bank", "number": "0000-6262", "currency": "USD"}]},
]}), encoding="utf-8")


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXK'")[0]["id"]
MAIN = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Main'", (EID,))[0]["id"]
SPARE = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Spare'", (EID,))[0]["id"]
NOW = db.now()

con = db.connect()
con.arm("user", "test: a made-up company kept here, its payments and October statement")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (EID,))


def pay(desc, amount, paid, direction="out", acct=MAIN):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                          direction, created_at) VALUES (?, '2026-10', ?, ?, ?, ?, '2026-10-05', ?, ?, ?, ?)""",
                       (EID, acct, "receipt" if direction == "in" else "other", desc, amount, paid, "manual" if paid else None, direction, NOW)).lastrowid


P1 = pay("Test Payee Alpha wages", 1000, "2026-10-05")
P2 = pay("Test Payee Beta wages", 1500, "2026-10-05")
P3 = pay("Test Payee Gamma wages", 500, None)        # no paid date yet: the bulk line gives it one
PX = pay("Test refund out", 200, "2026-10-12")        # a refund out and back the same day, never on the bank
PY = pay("Test refund back", 200, "2026-10-12", "in")
PS = pay("Test Payee Delta single", 75, "2026-10-20")  # an ordinary single link
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 10000, ?)", (MAIN, NOW))
SID = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, '2026-10', 10000, 6915, ?, 1)""",
                  (MAIN, NOW)).lastrowid
L_BULK = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, status)
                        VALUES (?, 1, '2026-10-05', 'PAYROLL BULK 3 ITEMS', -3000, 7000, 'unmatched')""", (SID,)).lastrowid
L_ONE = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status)
                       VALUES (?, 2, '2026-10-20', 'IBG DR TEST PAYEE DELTA', -75, 6925, ?, 'matched')""", (SID, PS)).lastrowid
L_FEE = con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, status, note)
                       VALUES (?, 3, '2026-10-31', 'SERVICE CHARGE', -10, 6915, 'no_docs', 'Bank charge')""", (SID,)).lastrowid
con.commit()
con.close()
links = lambda lid: sorted((r["payment_id"], r["amount"]) for r in q("SELECT payment_id, amount FROM statement_line_payments WHERE line_id = ?", (lid,)))

# ---------- 1. update 39 keeps every link ----------
check("a line linked to a payment is in the link table as soon as it is written", links(L_ONE) == [(PS, None)], links(L_ONE))
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DELETE FROM statement_line_payments")
for t in ("line_link_insert", "line_link_update", "line_link_payment_gone"):
    raw.execute(f"DROP TRIGGER IF EXISTS {t}")
raw.execute("PRAGMA user_version = 38")
raw.commit()
raw.close()
db.init()
check("update 39, run on records with the links not copied yet, copies every line's payment into the link table",
      links(L_ONE) == [(PS, None)] and q("PRAGMA user_version")[0]["user_version"] >= 41, links(L_ONE))
check("...and the triggers that keep it in step are back", {r["name"] for r in q("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
      >= {"line_link_insert", "line_link_update", "line_link_payment_gone"})

# ---------- 2. one line, several payments ----------
call("post", f"/api/statement-lines/{L_BULK}", json={"payment_ids": [P1, P2, P3]})
check("one bank line is linked to three payments, each for its own amount",
      links(L_BULK) == sorted([(P1, -1000.0), (P2, -1500.0), (P3, -500.0)]), links(L_BULK))
p3 = q("SELECT paid_date, paid_source, amount FROM payments WHERE id = ?", (P3,))[0]
check("a payment with no paid date takes the bulk line's date; amounts stay their own",
      p3 == {"paid_date": "2026-10-05", "paid_source": "bank", "amount": 500.0}, p3)
check("a paid date typed in stays", q("SELECT paid_date, paid_source FROM payments WHERE id = ?", (P1,))[0] == {"paid_date": "2026-10-05", "paid_source": "manual"})
rv = call("get", f"/api/recon/review?entity_id={EID}&statement_id={SID}")
row = next(l for l in rv["lines"] if l["id"] == L_BULK)
check("the review shows the line linked to 3 payments, with each one's part",
      row["group"] and len(row["group"]) == 3 and row["payment_desc"] == "Linked to 3 payments" and not row["short"]
      and sorted(abs(g["part"]) for g in row["group"]) == [500, 1000, 1500], row)
s = rv["summary"]
check("the month agrees with the bank: nothing in the books is missing from it, and nothing differs",
      s["difference"] == 0 and not s["books_only"] and not s["differ"] and not s["bank_only"], (s["difference"], s["books_only"], s["differ"], s["bank_only"]))
check("the review's payments count each one as covered by its part of the line",
      {p["id"]: p["linked"] for p in rv["payments"] if p["id"] in (P1, P2, P3)} == {P1: 1000, P2: 1500, P3: 500})
call("post", f"/api/statement-lines/{L_BULK}", json={"payment_id": None})
check("undone, the line is to explain and every payment is freed", links(L_BULK) == [] and
      q("SELECT payment_id, status FROM statement_lines WHERE id = ?", (L_BULK,))[0] == {"payment_id": None, "status": "unmatched"})
check("...and the paid date the bulk line gave goes with it; a typed one stays",
      q("SELECT paid_date FROM payments WHERE id = ?", (P3,))[0]["paid_date"] is None
      and q("SELECT paid_date FROM payments WHERE id = ?", (P1,))[0]["paid_date"] == "2026-10-05")
call("post", f"/api/statement-lines/{L_BULK}", json={"payment_ids": [P1, P2]})
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={MAIN}&month=2026-10")
check("linked to only two of the three, the line is matched but the amounts differ, and the sign-off waits",
      s["short_lines"] and s["short_lines"][0]["gap"] == -500 and any("matched, but the amounts differ" in w for w in s["why_not"]), s["short_lines"])
call("post", f"/api/statement-lines/{L_BULK}", json={"payment_ids": [P1, P2, P3]})
call("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": SID})
check("Confirm all matched confirms the bulk line (it has no one date to tick)",
      q("SELECT confirmed_at FROM statement_lines WHERE id = ?", (L_BULK,))[0]["confirmed_at"])

# ---------- 3. No money moved ----------
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={MAIN}&month=2026-10")
pr = s["pairs"]
check("the refund out and back the same day is a No money moved pair, net nil, with a reason filled in",
      len(pr) == 1 and pr[0]["nil"] and not pr[0]["confirmed_at"] and "same amount" in pr[0]["reason"]
      and {d["description"] for d in pr[0]["docs"]} == {"Test refund out", "Test refund back"}, pr)
check("its entries aren't listed as in the books, not on the statement", not s["books_only"], s["books_only"])
check("the sign-off waits for the pair", "1 pair under No money moved to confirm" in s["why_not"] and not s["can_sign"], s["why_not"])
r = call("post", "/api/recon/sign-off", 400, json={"entity_id": EID, "statement_id": SID})
check("signing off is refused while a pair is unconfirmed", "pair under No money moved to confirm" in r["error"], r)
KEY = pr[0]["key"]
r = call("post", "/api/recon/pair", 400, json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "key": KEY, "reason": "  "})
check("a pair isn't confirmed without a reason", "Give the pair a reason first" in r["error"], r)
call("post", "/api/recon/pair", json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "key": KEY,
                                      "reason": "Refund sent and returned the same day; no money moved"})
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={MAIN}&month=2026-10")
check("confirmed with its reason, the pair no longer stops the sign-off",
      s["pairs"][0]["confirmed_at"] and s["pairs"][0]["reason"].startswith("Refund sent") and s["can_sign"], (s["pairs"], s["why_not"]))

# ---------- 4. sign-off with its note ----------
call("post", "/api/recon/sign-off", json={"entity_id": EID, "statement_id": SID, "note": "Checked against the payroll run",
                                          "prepared_by": "Test Preparer"})
st = q("SELECT * FROM statements WHERE id = ?", (SID,))[0]
note = json.loads(st["sign_note"])
check("the sign-off keeps the free note and the declared Prepared by",
      st["reconciled_at"] and st["reconciled_note"] == "Checked against the payroll run" and st["prepared_by"] == "Test Preparer", st)
check("...and the note the app writes as the month stands: the pair with its reason, the line explained without documents",
      note[0].startswith("No money moved: ") and "net nil. Reason: Refund sent" in note[0]
      and note[1].startswith("Explained without documents: ") and "SERVICE CHARGE" in note[1] and "Bank charge" in note[1]
      and note[2] == "Reconciling items left: none.", note)
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={MAIN}&month=2026-10")
check("the month is reconciled and locked", s["status"] == "reconciled" and s["locked"] and s["sign_note"] == note
      and s["prepared_by"] == "Test Preparer" and s["free_note"] == "Checked against the payroll run", s)
y = {r["month"]: r for r in call("get", f"/api/recon/year?entity_id={EID}&account_id={MAIN}&year=2026")["rows"]}
check("the year table says it is locked", y["2026-10"]["locked"] and y["2026-10"]["status"] == "reconciled", y["2026-10"])

# ---------- 5. the lock ----------
def refused(r, what):
    check(what, "is marked reconciled and locked" in (r.get("error") or ""), r)


refused(call("post", f"/api/statement-lines/{L_FEE}", 400, json={"payment_id": None}), "a line of a locked month can't be undone")
refused(call("post", f"/api/statement-lines/{L_FEE}", 400, json={"payment_id": PX}), "...nor linked")
refused(call("post", f"/api/statement-lines/{L_BULK}", 400, json={"payment_ids": [P1, P2]}), "...nor linked to other payments")
refused(call("post", "/api/recon/apply", 400, json={"entity_id": EID, "statement_id": SID, "checked": True, "rows": [{"line_id": L_FEE}]}),
        "...nor applied on the review")
refused(call("post", "/api/recon/confirm-matched", 400, json={"entity_id": EID, "statement_id": SID}), "...nor confirmed")
refused(call("post", "/api/recon/pair", 400, json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "key": KEY, "confirmed": False}),
        "its No money moved pair can't be unconfirmed")
r = call("post", "/api/recon/book-opening", 400, json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "amount": 9000})
check("a book opening that changes a locked month is refused, nothing saved",
      "October 2026 is marked reconciled and locked, so a book opening that changes it can't be saved" in r["error"]
      and q("SELECT amount FROM book_openings WHERE account_id = ? AND month = '2026-10'", (MAIN,))[0]["amount"] == 10000, r)
refused(call("patch", f"/api/payments/{P1}", 400, json={"amount": 999}), "the amount of a payment on a locked line can't change (the payment PATCH)")
refused(call("patch", f"/api/payments/{P1}", 400, json={"account_id": SPARE}), "...nor can it move to another account")
refused(call("patch", f"/api/payments/{P1}", 400, json={"account_id": 0}), "...nor be taken off its account")
refused(call("patch", f"/api/payments/{PX}", 400, json={"paid_date": "2026-11-02"}),
        "the paid date of a payment the locked month's books count can't change (no bank line needed)")
refused(call("delete", f"/api/payments/{PX}", 400, json={}), "...nor can it be removed")
refused(call("post", "/api/payments", 400, json={"entity_id": EID, "month": "2026-10", "account_id": MAIN, "description": "Test late entry",
                                                 "category": "other", "amount": 5, "paid_date": "2026-10-15"}),
        "a new payment paid in a locked month of an account kept here is refused")
call("post", "/api/payments", json={"entity_id": EID, "month": "2026-10", "account_id": MAIN, "description": "Test next month entry",
                                    "category": "other", "amount": 5, "paid_date": "2026-11-15"})
check("...one paid in an open month is added", q("SELECT 1 FROM payments WHERE description = 'Test next month entry'"))
call("patch", f"/api/payments/{P1}", json={"notes": "notes are not a bank field"})
check("a field the bank doesn't hold still changes", q("SELECT notes FROM payments WHERE id = ?", (P1,))[0]["notes"] == "notes are not a bank field")
check("nothing in the locked month changed", links(L_BULK) == sorted([(P1, -1000.0), (P2, -1500.0), (P3, -500.0)])
      and q("SELECT amount, account_id FROM payments WHERE id = ?", (P1,))[0] == {"amount": 1000.0, "account_id": MAIN}
      and q("SELECT payment_id, status, confirmed_at IS NOT NULL AS c FROM statement_lines WHERE id = ?", (L_FEE,))[0] == {"payment_id": None, "status": "no_docs", "c": 1})
r = call("post", "/api/recon/sign-off", 400, json={"entity_id": EID, "statement_id": SID})
check("a signed-off month isn't signed off twice", "already marked reconciled" in r["error"], r)

# ---------- 6. Reopen month ----------
r = c.post(BASE + "/api/recon/undo-sign-off", headers=H, json={"entity_id": EID, "statement_id": SID})
check("the old Undo sign-off route is gone", r.status_code in (404, 405) and q("SELECT reconciled_at FROM statements WHERE id = ?", (SID,))[0]["reconciled_at"],
      r.status_code)
r = call("post", "/api/recon/reopen", 400, json={"entity_id": EID, "statement_id": SID, "reason": "   "})
check("reopening needs a reason", r["error"] == "Say why you're reopening this month.", r)
r = call("post", "/api/recon/reopen", 400, json={"entity_id": EID, "statement_id": SID})
check("...also when none is sent", r["error"] == "Say why you're reopening this month.", r)
call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": SID, "reason": "Test: the service charge is to be checked"})
st = q("SELECT * FROM statements WHERE id = ?", (SID,))[0]
check("reopened, the month is open again with no sign-off, note or Prepared by",
      not st["reconciled_at"] and not st["sign_note"] and not st["prepared_by"] and not st["reconciled_note"], st)
ro = q("SELECT * FROM recon_reopens WHERE statement_id = ?", (SID,))
check("the reopening is kept with its reason and the sign-off it undid, its note included",
      len(ro) == 1 and ro[0]["reason"] == "Test: the service charge is to be checked" and ro[0]["was_how"] == "review"
      and json.loads(ro[0]["was_sign_note"]) == note and ro[0]["was_prepared_by"] == "Test Preparer" and ro[0]["was_note"] == "Checked against the payroll run", ro)
log = q("SELECT what FROM activity WHERE what LIKE 'Reopened %' ORDER BY id DESC LIMIT 1")
check("...and logged with the reason and the old sign-off note", log and "Test: the service charge is to be checked" in log[0]["what"]
      and "Refund sent and returned" in log[0]["what"] and "needs the sign-off again" in log[0]["what"], log)
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={MAIN}&month=2026-10")
check("the month says when and why it was reopened, and can be signed off again",
      not s["locked"] and s["reopens"][0]["reason"] == "Test: the service charge is to be checked" and s["can_sign"] and s["status"] == "to_review", s)
call("post", f"/api/statement-lines/{L_FEE}", json={"status": "no_docs", "note": "Bank charge, checked"})
check("reopened, its lines can change again", q("SELECT note FROM statement_lines WHERE id = ?", (L_FEE,))[0]["note"] == "Bank charge, checked")
r = call("post", "/api/recon/reopen", 400, json={"entity_id": EID, "statement_id": SID, "reason": "again"})
check("a month not signed off has nothing to reopen", "isn't marked as reconciled" in r["error"], r)

# A later month that carries on from this one's closing, signed off, stops this one being reopened on its own.
call("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": SID})
call("post", "/api/recon/sign-off", json={"entity_id": EID, "statement_id": SID})
con = db.connect()
con.arm("user", "test: a made-up November statement, signed off")
NOV = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                     VALUES (?, '2026-11', 6915, 6915, ?, 1, ?, 'review')""", (MAIN, NOW, NOW)).lastrowid
con.commit()
con.close()
r = call("post", "/api/recon/reopen", 400, json={"entity_id": EID, "statement_id": SID, "reason": "Test: a later look"})
check("October can't be reopened while November, which carries on from its closing, is signed off",
      r["error"] == "November 2026 is marked reconciled and carries on from October's closing balance, so this month can't be reopened on its own. "
                    "Reopen November 2026 first.", r)
call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": NOV, "reason": "Test: November first"})
call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": SID, "reason": "Test: then October"})
check("...November reopened first, October can be", len(q("SELECT 1 FROM recon_reopens WHERE statement_id = ?", (SID,))) == 2)

# ---------- 3b. a pair that isn't nil (EXL, kept in SQL Account: a reversal keyed in SQL at another amount) ----------
LID = q("SELECT id FROM entities WHERE code = 'EXL'")[0]["id"]
CB = q("SELECT id FROM accounts WHERE entity_id = ?", (LID,))[0]["id"]
con = db.connect()
con.arm("user", "test: a made-up SQL cash book with a charge and its reversal")
con.execute("UPDATE entities SET uses_sql = 1, first_month = '2026-09' WHERE id = ?", (LID,))
IMP = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing.xlsx', ?, 0, 0)", (LID, NOW)).lastrowid
for no, desc, amt, way in [("CB2610-901", "BANK CHARGES TEST", 48, "out"), ("CB2610-902", "REVERSAL OF CB2610-901", 45, "in")]:
    con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind, status)
                   VALUES (?, ?, ?, '2026-10-31', ?, ?, ?, ?, 'CB', 'payment', 'unlinked')""", (IMP, LID, no, desc, desc, amt, way))
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 500, ?)", (CB, NOW))
S_CB = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, '2026-10', 500, 497, ?, 1)",
                   (CB, NOW)).lastrowid
con.commit()
con.close()
s = call("get", f"/api/recon/month?entity_id={LID}&account_id={CB}&month=2026-10")
pr = s["pairs"]
check("a reversal naming the charge it reverses is a pair, though keyed at another amount: net 3.00, not nil",
      len(pr) == 1 and not pr[0]["nil"] and abs(pr[0]["net"] + 3) < 0.005 and pr[0]["reason"].startswith("Reversal: CB2610-902 reverses CB2610-901"), pr)
check("the sign-off is refused while the pair isn't nil", any("isn't nil (RM 3.00 left)" in w for w in s["why_not"]) and not s["can_sign"], s["why_not"])
r = call("post", "/api/recon/pair", 400, json={"entity_id": LID, "account_id": CB, "month": "2026-10", "key": pr[0]["key"], "reason": "Reversal"})
check("a pair that isn't nil can't be confirmed", "don't cancel: RM 3.00 is left" in r["error"], r)
r = call("post", "/api/recon/sign-off", 400, json={"entity_id": LID, "statement_id": S_CB})
check("signing off is refused with why", "isn't nil" in r["error"], r)

# ---------- 7. review fixes: the lock reaches every path that rewrites a payment, and carries forward ----------
con = db.connect()
con.arm("user", "test: made-up statements on Spare (August open, September signed off, October open)")
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-08', 0, ?)", (SPARE, NOW))


def spare_pay(desc, amount, month, paid=None, source=None):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                          direction, created_at) VALUES (?, ?, ?, 'other', ?, ?, ?, ?, ?, 'out', ?)""",
                       (EID, month, SPARE, desc, amount, (paid or month + "-10"), paid, source, NOW)).lastrowid


def spare_stmt(month, lines, signed=False):
    sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how) "
                      "VALUES (?, ?, 0, ?, ?, 1, ?, ?)", (SPARE, month, round(sum(x[2] for x in lines), 2), NOW,
                                                          NOW if signed else None, "review" if signed else None)).lastrowid
    out, bal = [], 0
    for n, (day, desc, amt, pid) in enumerate(lines, 1):
        bal = round(bal + amt, 2)
        out.append(con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (sid, n, day, desc, amt, bal, pid, "matched" if pid else "unmatched")).lastrowid)
    return sid, out


Q = spare_pay("Test Payee Sigma deposit", 400, "2026-09", "2026-09-28", "bank")
R = spare_pay("Test Payee Omicron rent", 250, "2026-09", "2026-09-20", "sql")
X1, X2 = spare_pay("Test Payee Tau fees", 1000, "2026-10"), spare_pay("Test Payee Upsilon fees", 2000, "2026-10")
Y1, Y2 = spare_pay("Test Payee Phi fees", 100, "2026-10"), spare_pay("Test Payee Chi fees", 200, "2026-10")
S_AUG, (L_AUG_FEE,) = spare_stmt("2026-08", [("2026-08-31", "SERVICE CHARGE", -10, None)])  # August stays open
S_SEP, _ = spare_stmt("2026-09", [("2026-09-28", "IBG DR SIGMA DEPOSIT", -400, Q)], signed=True)
S_SOCT, (L_Q, L_R, L_X, L_Y) = spare_stmt("2026-10", [("2026-10-03", "IBG DR SIGMA DEPOSIT TOP UP", -600, None),
                                                       ("2026-10-02", "IBG DR OMICRON RENT", -250, None),
                                                       ("2026-10-06", "BULK 2 ITEMS", -3000, None),
                                                       ("2026-10-07", "BULK 2 MORE", -300, None)])
con.commit()
con.close()
pq = lambda pid: q("SELECT paid_date, paid_source, amount FROM payments WHERE id = ?", (pid,))[0]
was_q = pq(Q)
refused(call("post", f"/api/statement-lines/{L_Q}", 400, json={"payment_id": Q}),
        "linking an open month's line to a payment counted in a signed-off month (its paid date would move) is refused")
check("...nothing changed: the payment keeps its paid date and amount, the line is still to explain",
      pq(Q) == was_q and q("SELECT payment_id FROM statement_lines WHERE id = ?", (L_Q,))[0]["payment_id"] is None, pq(Q))
refused(call("post", f"/api/statement-lines/{L_Q}", 400, json={"payment_ids": [Q, X1]}), "...also as one of several payments")
refused(call("post", "/api/recon/apply", 400, json={"entity_id": EID, "statement_id": S_SOCT, "checked": True,
                                                    "rows": [{"line_id": L_Q, "payment_id": Q}]}), "...also through Apply on the review")
was_r = pq(R)
call("post", "/api/statements/rematch", json={"entity_id": EID})
check("matching again leaves a payment alone when the match would move it out of a signed-off month's books",
      pq(R) == was_r and q("SELECT payment_id FROM statement_lines WHERE id = ?", (L_R,))[0]["payment_id"] is None, (pq(R), was_r))
check("...and leaves an open August's bank charge to explain: marked, it would change signed-off September's opening",
      q("SELECT status FROM statement_lines WHERE id = ?", (L_AUG_FEE,))[0]["status"] == "unmatched")
refused(call("post", "/api/payments", 400, json={"entity_id": EID, "month": "2026-08", "account_id": SPARE, "description": "Test August entry",
                                                 "category": "other", "amount": 5, "paid_date": "2026-08-20"}),
        "a payment paid in an open month whose closing a signed-off later month carries on from is refused")
r = call("post", "/api/payments", 400, json={"entity_id": EID, "month": "2026-08", "account_id": SPARE, "description": "Test August entry",
                                             "category": "other", "amount": 5, "paid_date": "2026-08-20"})
check("...naming the later month that is locked", r["error"].startswith("Spare September 2026 is marked reconciled and locked"), r)

# A line left with one payment's part when the other is moved off it shows as short, not as fully matched.
call("post", f"/api/statement-lines/{L_X}", json={"payment_ids": [X1, X2]})
call("patch", f"/api/payments/{X2}", json={"account_id": MAIN})
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={SPARE}&month=2026-10")
sl = [x for x in s["short_lines"] if x["line_id"] == L_X]
check("a bulk line left with one payment's part (another moved off it) is still matched, but the amounts differ",
      sl and sl[0]["gap"] == -2000 and any("matched, but the amounts differ" in w for w in s["why_not"]), s["short_lines"])
rv = call("get", f"/api/recon/review?entity_id={EID}&statement_id={S_SOCT}")
row = next(x for x in rv["lines"] if x["id"] == L_X)
check("...and the review shows its part and the gap", row["group"] and len(row["group"]) == 1 and row["short"] and row["payment_desc"] == "Linked to 1 payment", row)

# A line paying several payments isn't explained another way until it is undone.
call("post", f"/api/statement-lines/{L_Y}", json={"payment_ids": [Y1, Y2]})
for body in ({"create_payment": {"description": "Test new one"}}, {"status": "no_docs", "note": "Bank charge"}):
    r = call("post", f"/api/statement-lines/{L_Y}", 400, json=body)
    check(f"a line linked to several payments can't be {'given a new payment' if 'create_payment' in body else 'marked as needing no documents'}",
          "is linked to 2 payments: undo that first" in r["error"] and len(links(L_Y)) == 2, r)

# The audit pack sees a pair confirmed after it was built (the pack check reads the new tables).
from hrp import packcheck  # noqa: E402
c2 = db.connect()
after_id = c2.execute("SELECT MAX(id) FROM audit_row").fetchone()[0]
c2.close()
call("post", "/api/recon/reopen", json={"entity_id": EID, "statement_id": SID, "reason": "Test: the pair again"}) if \
    q("SELECT reconciled_at FROM statements WHERE id = ?", (SID,))[0]["reconciled_at"] else None
call("post", "/api/recon/pair", json={"entity_id": EID, "account_id": MAIN, "month": "2026-10", "key": KEY, "reason": "Refund, checked again"})
c2 = db.connect()
ch = packcheck._changes(c2, c2.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone(), "2026-10", after_id, "no token")
c2.close()
check("a No money moved pair confirmed after the pack is a change to the month's pack", any(r["tbl"] == "recon_pairs" for r in ch["statements"]),
      [r["tbl"] for r in ch["statements"]])

refused(call("post", f"/api/statement-lines/{L_AUG_FEE}", 400, json={"status": "no_docs", "note": "Bank charge"}),
        "marking that August line as needing no documents by hand is refused too")

# ---------- 8. second review: the SQL routes, Setup, reopen without books, changes that move nothing ----------
con = db.connect()
con.arm("user", "test: made-up SQL listings for payments of an account kept here")
IMP_K = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'k.xlsx', ?, 0, 0)", (EID, NOW)).lastrowid


def entry(no, day, amount, pid=None):
    return con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
                          payment_id, status) VALUES (?, ?, ?, ?, 'Test voucher', 'Test voucher', ?, 'out', 'PV', 'payment', ?, ?)""",
                       (IMP_K, EID, no, day, amount, pid, "linked" if pid else "unlinked")).lastrowid


Z1 = spare_pay("Test Payee Kappa supplies", 300, "2026-09")                    # no paid date yet
Z2 = spare_pay("Test Payee Lambda supplies", 120, "2026-09", "2026-09-15", "sql")  # paid by its linked voucher
con.execute("UPDATE payments SET sql_ref = 'PV2609-902' WHERE id = ?", (Z2,))
Z3 = spare_pay("Test Payee Mu supplies", 80, "2026-09")
con.execute("UPDATE payments SET sql_ref = 'PV2609-903' WHERE id = ?", (Z3,))
E1, E2, E3 = entry("PV2609-901", "2026-09-15", 300), entry("PV2609-902", "2026-09-15", 120, Z2), entry("PV2609-903", "2026-09-16", 80)
con.commit()
con.close()
was = {p: pq(p) for p in (Z1, Z2, Z3)}
refused(call("post", f"/api/sql/entries/{E1}", 400, json={"payment_id": Z1}),
        "linking an SQL voucher that would date a payment in a signed-off month (books kept here) is refused")
check("...nothing changed: the payment has no paid date, the voucher is still not linked",
      pq(Z1) == was[Z1] and q("SELECT payment_id, status FROM sql_entries WHERE id = ?", (E1,))[0] == {"payment_id": None, "status": "unlinked"})
refused(call("post", f"/api/sql/entries/{E2}/unlink", 400, json={}), "unlinking the voucher that dates a payment in a signed-off month is refused")
check("...nothing changed", pq(Z2) == was[Z2] and q("SELECT payment_id FROM sql_entries WHERE id = ?", (E2,))[0]["payment_id"] == Z2)
r = call("post", "/api/sql/entries/create-all", json={"entity_id": EID})
check("Link or create all leaves a voucher whose link the lock refuses, and says so",
      any(h["doc_no"] == "PV2609-903" and "is marked reconciled and locked" in h["why"] for h in r.get("held", []))
      and pq(Z3) == was[Z3] and q("SELECT payment_id FROM sql_entries WHERE id = ?", (E3,))[0]["payment_id"] is None, r)

NID = q("SELECT id FROM entities WHERE code = 'EXN'")[0]["id"]
SOLO = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Solo'", (NID,))[0]["id"]
OTHER = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Other'", (NID,))[0]["id"]
con = db.connect()
con.arm("user", "test: a made-up company whose one ringgit account counts the payments with no account")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (NID,))
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 1000, ?)", (SOLO, NOW))
NA = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date, paid_source,
                    direction, created_at) VALUES (?, '2026-10', NULL, 'other', 'Test Payee Nu rates', 300, 'MYR', '2026-10-05', '2026-10-05', 'manual', 'out', ?)""",
                 (NID, NOW)).lastrowid
NB = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, direction, created_at)
                    VALUES (?, '2026-10', ?, 'other', 'Test Payee Xi estimate', NULL, '2026-10-20', 'out', ?)""", (NID, SOLO, NOW)).lastrowid
S_SOLO = con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how)
                        VALUES (?, '2026-10', 1000, 700, ?, 1, ?, 'review')""", (SOLO, NOW, NOW)).lastrowid
for m in ("2026-08", "2026-09"):  # the dollar account: two months signed off, no book opening (no books run through them)
    con.execute("""INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok, reconciled_at, reconciled_how, reconciled_note)
                   VALUES (?, ?, 0, 0, ?, 1, ?, 'before tracking', 'Reconciled in the old books')""", (OTHER, m, NOW, NOW))
con.commit()
con.close()
book = lambda: call("get", f"/api/recon/month?entity_id={NID}&account_id={SOLO}&month=2026-10")["book"]["closing"]
closing = book()
call("post", "/api/setup/accounts", json={"entity_id": NID, "fields": {"label": "Second", "bank": "Example Bank", "number": "0000-6363", "currency": "MYR"}})
check("a second ringgit account is added while October is signed off, and October's book figures stay as they were",
      q("SELECT 1 FROM accounts WHERE entity_id = ? AND label = 'Second'", (NID,)) and book() == closing
      and call("get", f"/api/recon/month?entity_id={NID}&account_id={SOLO}&month=2026-10")["status"] == "reconciled")
check("...the payment with no account is now on Solo, the account its books already counted it in",
      q("SELECT account_id FROM payments WHERE id = ?", (NA,))[0]["account_id"] == SOLO)
check("...and the activity log says so", q("SELECT 1 FROM activity WHERE what = ?",
                                           ("1 payment with no bank account was set to Solo, the account their books already counted them in, "
                                            "before Second was added",)), [r["what"] for r in q("SELECT what FROM activity ORDER BY id DESC LIMIT 3")])
call("post", "/api/setup/accounts", json={"entity_id": NID, "fields": {"label": "Euro", "bank": "Example Bank", "number": "0000-6464", "currency": "EUR"}})
check("...an account in another currency changes no book, so it is added", q("SELECT 1 FROM accounts WHERE entity_id = ? AND label = 'Euro'", (NID,)))
con = db.connect()
con.arm("user", "test: another payment with no account, on a company with one dollar account")
NC = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, currency, due_date, paid_date, paid_source,
                    direction, created_at) VALUES (?, '2026-08', NULL, 'other', 'Test Payee Pi fees', 40, 'USD', '2026-08-05', '2026-08-05', 'manual', 'out', ?)""",
                 (NID, NOW)).lastrowid
con.commit()
con.close()
call("patch", f"/api/payments/{NC}", json={"account_id": OTHER})
check("a payment with no account put on the one account that already counts it changes no book: accepted in a signed-off month",
      q("SELECT account_id FROM payments WHERE id = ?", (NC,))[0]["account_id"] == OTHER)
call("patch", f"/api/payments/{NB}", json={"paid_date": "2026-10-21"})
check("a paid date on a payment with no amount (in no book) is accepted in a signed-off month",
      q("SELECT paid_date FROM payments WHERE id = ?", (NB,))[0]["paid_date"] == "2026-10-21")
OTHER_AUG = q("SELECT id FROM statements WHERE account_id = ? AND month = '2026-08'", (OTHER,))[0]["id"]
call("post", "/api/recon/reopen", json={"entity_id": NID, "statement_id": OTHER_AUG, "reason": "Test: no books run through August"})
check("a month whose account has no books through it can be reopened though a later month is signed off",
      not q("SELECT reconciled_at FROM statements WHERE id = ?", (OTHER_AUG,))[0]["reconciled_at"])
con = db.connect()
con.arm("user", "test: EXL's October signed off")
con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id = ?", (NOW, S_CB))
con.commit()
con.close()
r = call("post", f"/api/entities/{LID}/first-month", 400, json={"month": "2026-11"})
check("moving the first month tracked past a signed-off month of an SQL cash book (it would count by listings) is refused",
      "Cash book October 2026 is marked reconciled and locked" in r["error"]
      and q("SELECT first_month FROM entities WHERE id = ?", (LID,))[0]["first_month"] == "2026-09", r)
call("post", f"/api/entities/{LID}/first-month", json={"month": "2026-08"})
check("...moving it to a month before changes no signed-off month: accepted", q("SELECT first_month FROM entities WHERE id = ?", (LID,))[0]["first_month"] == "2026-08")
new_cb = call("post", "/api/setup/accounts", json={"entity_id": LID, "fields": {"label": "Spare cash", "bank": "Example Bank", "number": "0000-5656",
                                                                              "currency": "MYR"}})["id"]
r = call("patch", f"/api/setup/accounts/{new_cb}", 409, json={"fields": {"cash_book": True}})
check("making another account the cash book, which would change a signed-off month's books, can't be pinned and is refused",
      "Cash book October 2026 is marked reconciled and locked" in r["error"]
      and q("SELECT cash_book FROM accounts WHERE id = ?", (new_cb,))[0]["cash_book"] == 0, r)

print("\nAll bank and reconciliation checks passed.")
