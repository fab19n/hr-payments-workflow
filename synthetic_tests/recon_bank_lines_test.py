"""The bank reconciliation counts SQL vouchers and receipts by their lines on the bank account, on made-up records only.

The book side of a bank reconciliation is the cash book: what each document actually posted to the bank account in
SQL, not its headline amount. A receipt of 58,585.50 on which the bank took a fee of 36.25 is posted in SQL as bank DR
58,585.50 and bank CR 36.25, a net 58,549.25 on the bank. The statement may show one net line, or the full amount and a
separate fee line; either is matched, never both, and a fee line is never matched on its own. A document with no lines
kept yet is still counted by its listing amount, and the month says so. Each month's book closing is checked against
SQL's balance on the bank account at month end. A month signed off before this rule changed its figures keeps its
sign-off but asks to be confirmed again; months before tracking keep their state.

Made-up company EXB, chart, SQL openings, documents with lines and bank statements:
- August 2026 (before tracking, signed off then): a receipt of 1,000.00 with a fee of 10.00, counted by its listing.
- September (tracked, signed off before the rule): a receipt of 2,000.00 net of a 20.00 fee, and a payment listed at
  520.00 of which 500.00 left the bank (20.00 settlement discount). The closing stays the same, the in and out change.
- October: the receipt of 58,585.50 with a fee of 36.25 (one net line), a receipt of 10,000.00 with a fee of 12.50 (the
  gross line and a fee line), a payment of 3,000.00 with a charge of 5.00 (two lines), and a payment of 700.00 with no
  lines kept (counted by its listing amount).
- November: a receipt of 5,000.00 with a fee of 7.50 matched by hand in the review, and a fee line of 4.00 whose
  receipt isn't on the statement (never matched or suggested on its own).

Run: .venv\\Scripts\\python -m synthetic_tests.recon_bank_lines_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-recon-bank-lines-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, recon, statements  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXB", "name": "Example Bank Lines Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-555"}]},
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


def S(rm):
    return int(round(rm * 100))


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXB'")[0]["id"]
AID = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
BANK = "310-1000"

con = db.connect()
con.arm("user", "test: a made-up company, chart, documents and statements")
con.execute("UPDATE entities SET uses_sql = 1, first_month = '2026-09', fy_start = 1 WHERE id = ?", (EID,))
con.execute("UPDATE accounts SET gl_code = ? WHERE id = ?", (BANK, AID))
for code, name, typ, special, grp in [
        ("100-0000", "SHARE CAPITAL", "equity", None, "CP"), ("150-0000", "RETAINED EARNINGS", "equity", None, "RE"),
        ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA"), (BANK, "BANK-EXAMPLE 0001", "asset", "bank", "CA"),
        ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL"), ("500-0000", "SALES", "income", None, "SL"),
        ("530-0000", "DISCOUNT RECEIVED", "income", None, "OI"), ("900-B001", "BANK CHARGES", "expense", None, "EP")]:
    con.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)",
                (EID, code, name, typ, special, grp))
IMP = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing.xlsx', ?, 0, 0)",
                  (EID, db.now())).lastrowid
TB = ledger.new_batch(con, EID, origin="sql", report="trial_balance", sql_import_id=IMP, file_name="tb.xlsx",
                      period_from="2026-08-01", period_to="2026-08-31")
ledger.put_openings(con, EID, TB, "2026-08-01", "sql_tb", [{"code": BANK, "dr_sen": S(10000), "cr_sen": 0},
                                                          {"code": "100-0000", "dr_sen": 0, "cr_sen": S(10000)}], True)
JOT = ledger.new_batch(con, EID, origin="sql", report="journal", sql_import_id=IMP, file_name="jot.xlsx", period_from="2026-08-01",
                       period_to="2026-10-31", period_source="printed", sections=[{"label": "Bank Journal", "book": "bank"}])
JOT_NOV = ledger.new_batch(con, EID, origin="sql", report="journal", sql_import_id=IMP, file_name="jot-nov.xlsx", period_from="2026-11-01",
                           period_to="2026-11-15", period_source="printed", sections=[{"label": "Bank Journal", "book": "bank"}])


def pay(desc, amount, month, due, direction):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, direction, created_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (EID, month, AID, "receipt" if direction == "in" else "other", desc, amount, due, direction, db.now())).lastrowid


def voucher(no, day, desc, amount, direction, pid, lines=None, batch=None):
    """A listing entry (OR in, PV out) linked to its payment, and (lines) its document in SQL's Journal of Transaction."""
    con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
                   payment_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'payment', ?, 'linked')""",
                (IMP, EID, no, day, desc, desc, amount, direction, "OR" if direction == "in" else "PV", pid))
    if lines:
        ledger.put_document(con, EID, batch or JOT, {"doc_no": no, "doc_date": day, "book": "bank",
                                                     "lines": [{"code": k, "dr_sen": S(dr), "cr_sen": S(cr)} for k, dr, cr in lines]})


def receipt_lines(gross, fee, customer="300-C001"):
    return [(BANK, gross, 0), ("900-B001", fee, 0), (customer, 0, gross), (BANK, 0, fee)]


def statement(month, opening, lines, signed=None):
    closing = round(opening + sum(x[2] for x in lines), 2)
    sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, ?, ?, ?, ?, 1)",
                      (AID, month, opening, closing, db.now())).lastrowid
    bal = opening
    for n, (day, desc, amt, pid, status, note, conf) in enumerate(lines, 1):
        bal = round(bal + amt, 2)
        con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, note,
                       confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (sid, n, day, desc, amt, bal, pid, status, note, conf))
    if signed:
        con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = ?, reconciled_note = ? WHERE id = ?",
                    (db.now(), signed[0], signed[1], sid))
    return sid


NOW = db.now()
# August, before tracking: the receipt is counted by its listing (1,000.00), as it always was; signed off before tracking.
P_AUG = pay("QUORVEX TRADING receipt", 1000, "2026-08", "2026-08-05", "in")
voucher("OR2608-001", "2026-08-05", "QUORVEX TRADING", 1000, "in", P_AUG, receipt_lines(1000, 10))
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-08', 10000, ?)", (AID, NOW))
S_AUG = statement("2026-08", 10000, [("2026-08-05", "QUORVEX TRADING", 1000, P_AUG, "matched", None, NOW),
                                     ("2026-08-05", "BANK CHARGES", -10, None, "no_docs", "Bank charge", NOW)],
                  signed=("before tracking", "reconciled in SQL Account"))
# September, tracked, signed off by review under the listing amounts (2,000.00 in, 520.00 out).
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-09', 10990, ?)", (AID, NOW))
P_SEP_R = pay("QUORVEX TRADING receipt", 2000, "2026-09", "2026-09-10", "in")
P_SEP_P = pay("BRENTWICK SUPPLIES", 520, "2026-09", "2026-09-15", "out")
voucher("OR2609-001", "2026-09-10", "QUORVEX TRADING", 2000, "in", P_SEP_R, receipt_lines(2000, 20))
voucher("PV2609-001", "2026-09-15", "BRENTWICK SUPPLIES", 520, "out", P_SEP_P,
        [("400-S001", 520, 0), (BANK, 0, 500), ("530-0000", 0, 20)])
S_SEP = statement("2026-09", 10990, [("2026-09-10", "QUORVEX TRADING", 1980, P_SEP_R, "matched", None, NOW),
                                     ("2026-09-15", "BRENTWICK SUPPLIES", -500, P_SEP_P, "matched", None, NOW)],
                  signed=("review", None))
# October: the cases to match, nothing linked yet.
P_OCT_A = pay("ZEPHYRA HOLDINGS receipt", 58585.50, "2026-10", "2026-10-06", "in")
P_OCT_B = pay("MALLORIN EXPORTS receipt", 10000, "2026-10", "2026-10-12", "in")
P_OCT_C = pay("BRENTWICK SUPPLIES", 3000, "2026-10", "2026-10-20", "out")
P_OCT_D = pay("TALVERA CLEANING", 700, "2026-10", "2026-10-25", "out")
voucher("OR2610-001", "2026-10-06", "ZEPHYRA HOLDINGS", 58585.50, "in", P_OCT_A, receipt_lines(58585.50, 36.25))
voucher("OR2610-002", "2026-10-12", "MALLORIN EXPORTS", 10000, "in", P_OCT_B, receipt_lines(10000, 12.50, "300-C002"))
voucher("PV2610-001", "2026-10-20", "BRENTWICK SUPPLIES", 3000, "out", P_OCT_C, [("400-S001", 3000, 0), ("900-B001", 5, 0), (BANK, 0, 3005)])
voucher("PV2610-002", "2026-10-25", "TALVERA CLEANING", 700, "out", P_OCT_D)  # no lines kept: the listing only
S_OCT = statement("2026-10", 12470, [("2026-10-07", "ZEPHYRA HOLDINGS", 58549.25, None, "unmatched", None, None),
                                     ("2026-10-12", "MALLORIN EXPORTS", 10000, None, "unmatched", None, None),
                                     ("2026-10-13", "BANK CHARGES", -12.50, None, "unmatched", None, None),
                                     ("2026-10-20", "BRENTWICK SUPPLIES", -3000, None, "unmatched", None, None),
                                     ("2026-10-20", "TT CHARGES", -5, None, "unmatched", None, None),
                                     ("2026-10-25", "TALVERA CLEANING", -700, None, "unmatched", None, None)])
# November: a receipt matched by hand, and a fee line whose receipt isn't on this statement.
P_NOV_A = pay("ORVANTE MEDIA receipt", 5000, "2026-11", "2026-11-04", "in")
P_NOV_B = pay("KESTRALYN FOODS receipt", 3000, "2026-11", "2026-11-28", "in")
voucher("OR2611-001", "2026-11-04", "ORVANTE MEDIA", 5000, "in", P_NOV_A, receipt_lines(5000, 7.50), JOT_NOV)
voucher("OR2611-002", "2026-11-12", "KESTRALYN FOODS", 3000, "in", P_NOV_B, receipt_lines(3000, 4), JOT_NOV)
S_NOV = statement("2026-11", 77301.75, [("2026-11-04", "INWARD TRANSFER REF 88231", 5000, None, "unmatched", None, None),
                                        ("2026-11-04", "COMMISSION", -7.50, None, "unmatched", None, None),
                                        ("2026-11-12", "COMMISSION", -4, None, "unmatched", None, None)])
# December, signed off by review under the listing amount: the fee isn't on this statement, so by its bank lines the
# books no longer agree with the bank, and the sign-off can't simply be confirmed again.
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-12', 50000, ?)", (AID, NOW))
P_DEC = pay("ZEPHYRA HOLDINGS receipt", 4000, "2026-12", "2026-12-03", "in")
voucher("OR2612-001", "2026-12-03", "ZEPHYRA HOLDINGS", 4000, "in", P_DEC, receipt_lines(4000, 10))
S_DEC = statement("2026-12", 50000, [("2026-12-03", "ZEPHYRA HOLDINGS", 4000, P_DEC, "matched", None, NOW)], signed=("review", None))
con.commit()
con.disarm()
con.close()


def summary(month):
    return j("get", f"/api/recon/month?entity_id={EID}&account_id={AID}&month={month}")


def year():
    return {r["month"]: r for r in j("get", f"/api/recon/year?entity_id={EID}&account_id={AID}&year=2026")["rows"]}


def moves(month):
    cn = db.connect()
    try:
        ent = cn.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
        return recon.movements(cn, ent, recon.cash_book_account(cn, EID), month)
    finally:
        cn.close()


def lines(sid):
    return {r["line_no"]: r for r in q("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (sid,))}


# ---------- 1. the book side from the lines ----------
oct_mv = moves("2026-10")
by = {i["ref"]: i for i in oct_mv["items"]}
check("a receipt with a fee counts as its net movement on the bank, its bank lines kept for matching",
      by["OR2610-001"]["amount"] == 58549.25 and by["OR2610-001"]["bank_lines"] == [58585.50, -36.25]
      and by["OR2610-001"]["basis"] == "lines", by["OR2610-001"])
check("a payment with a charge counts as what left the bank", by["PV2610-001"]["amount"] == -3005 and by["PV2610-001"]["bank_lines"] == [-3005], by["PV2610-001"])
check("a document with no lines kept is still counted by its listing amount", by["PV2610-002"]["amount"] == -700
      and by["PV2610-002"]["basis"] == "listing" and oct_mv["listing_docs"] == 1, (by["PV2610-002"], oct_mv.get("listing_docs")))
check("the month's in and out are the bank lines' figures", (oct_mv["in"], oct_mv["out"]) == (68536.75, 3705.0), (oct_mv["in"], oct_mv["out"]))
aug_mv = moves("2026-08")
check("a month before tracking keeps the listing amounts", (aug_mv["in"], aug_mv["out"]) == (1000.0, 0.0)
      and aug_mv["items"][0]["basis"] == "listing" and aug_mv["listing_docs"] == 0, aug_mv)
s = summary("2026-10")
check("the month summary says how many documents still rely on listing amounts",
      s["listing_docs"] == 1 and "fetch SQL's GL Journal of Transaction to count them by their bank lines" in s["listing_note"], s.get("listing_note"))
check("the year view says how many months do", year()["2026-10"]["listing_docs"] == 1
      and j("get", f"/api/recon/year?entity_id={EID}&account_id={AID}&year=2026")["listing_months"] == 1)

# ---------- 2. matching both ways ----------
cn = db.connect()
cn.arm("user", "test: match the statements")
statements.classify(cn, S_OCT)  # the fee lines are marked as bank charges first, as on a real import
n_oct = statements.auto_match(cn, S_OCT)
n_nov = statements.auto_match(cn, S_NOV)
cn.commit()
cn.disarm()
cn.close()
L = lines(S_OCT)
check("the net receipt line is matched to its receipt (one line equal to the net movement)", L[1]["payment_id"] == P_OCT_A, L[1])
check("the gross line and the fee line are both matched to their receipt", L[2]["payment_id"] == P_OCT_B and L[3]["payment_id"] == P_OCT_B
      and L[3]["status"] == "matched", (L[2], L[3]))
check("a payment and its charge line are both matched to it", L[4]["payment_id"] == P_OCT_C and L[5]["payment_id"] == P_OCT_C, (L[4], L[5]))
check("a payment with no lines is matched as before, by its amount", L[6]["payment_id"] == P_OCT_D and n_oct == 6, (L[6], n_oct))
s = summary("2026-10")
check("October agrees with the bank, nothing left on either side", s["difference"] == 0 and not s["books_only"] and not s["bank_only"]
      and not s["differ"], (s["difference"], s["books_only"], s["bank_only"], s["differ"]))
NL = lines(S_NOV)
check("a fee line is never matched on its own, nor the gross line without the payee's name", n_nov == 0
      and all(x["payment_id"] is None for x in NL.values()), NL)
cn = db.connect()
pa = cn.execute("SELECT * FROM payments WHERE id = ?", (P_OCT_A,)).fetchone()
check("a receipt matched to its net line isn't part paid: the fee SQL booked is counted back",
      db.linked_total(cn, pa) == 58585.50 and not db.part_paid(pa, db.linked_total(cn, pa)), db.linked_total(cn, pa))
pb = cn.execute("SELECT * FROM payments WHERE id = ?", (P_OCT_B,)).fetchone()
check("nor one matched to its gross line and fee line", db.linked_total(cn, pb) == 10000, db.linked_total(cn, pb))
cn.close()

# November by hand: link the gross line in the review; the fee line is then suggested and linked to the same receipt.
rv = j("get", f"/api/recon/review?entity_id={EID}&statement_id={S_NOV}")
sugg = {l["line_no"]: l["suggestions"] for l in rv["lines"]}
check("a fee line alone isn't suggested for a receipt whose other line isn't matched",
      not any(x["payment_id"] in (P_NOV_A, P_NOV_B) for x in sugg[2] + sugg[3]), sugg)
pays = {p["id"]: p for p in rv["payments"]}
check("the review's payments carry their bank lines and what is still open",
      pays[P_NOV_A]["bank_lines"] == [5000, -7.5] and pays[P_NOV_A]["open_lines"] == [5000, -7.5], pays[P_NOV_A])
r = j("post", "/api/recon/apply", json={"entity_id": EID, "statement_id": S_NOV, "checked": True,
                                         "rows": [{"line_id": NL[1]["id"], "payment_id": P_NOV_A}]})
check("the gross line is linked by hand", r["linked"] == 1, r)
rv = j("get", f"/api/recon/review?entity_id={EID}&statement_id={S_NOV}")
sugg = {l["line_no"]: l["suggestions"] for l in rv["lines"]}
pays = {p["id"]: p for p in rv["payments"]}
check("then its fee line is suggested for the same receipt, and only that one",
      [x["payment_id"] for x in sugg[2]][:1] == [P_NOV_A] and not any(x["payment_id"] == P_NOV_A for x in sugg[3])
      and pays[P_NOV_A]["open_lines"] == [-7.5], (sugg, pays[P_NOV_A]))
r = j("post", "/api/recon/apply", json={"entity_id": EID, "statement_id": S_NOV, "checked": True,
                                         "rows": [{"line_id": NL[2]["id"], "payment_id": P_NOV_A}]})
NL = lines(S_NOV)
check("a manual match links the fee line to the same receipt", NL[2]["payment_id"] == P_NOV_A and r["linked"] == 1, NL[2])
s = summary("2026-11")
check("nothing about the receipt differs any more", not s["differ"] and not any(x.get("ref") == "OR2611-001" for x in s["books_only"]), s["differ"])
cn = db.connect()
cn.arm("user", "test: match again")
check("matching again leaves the lone fee line alone", statements.auto_match(cn, S_NOV) == 0 and lines(S_NOV)[3]["payment_id"] is None)
cn.rollback()
cn.disarm()
cn.close()

# ---------- 3. the month-end check against SQL's bank account ----------
s = summary("2026-10")
check("a book closing that differs from SQL's bank account says by how much",
      s["sql_check"]["state"] == "differs" and s["sql_check"]["difference"] == -700 and "310-1000" in s["sql_check"]["text"]
      and "700.00" in s["sql_check"]["text"], s["sql_check"])
cn = db.connect()
cn.arm("user", "test: the payment's lines arrive")
ledger.put_document(cn, EID, JOT, {"doc_no": "PV2610-002", "doc_date": "2026-10-25", "book": "bank",
                                   "lines": [{"code": "400-S002", "dr_sen": S(700), "cr_sen": 0}, {"code": BANK, "dr_sen": 0, "cr_sen": S(700)}]})
cn.commit()
cn.disarm()
cn.close()
s = summary("2026-10")
check("once every document's lines are kept, it agrees with SQL's bank account",
      s["sql_check"]["state"] == "agrees" and s["sql_check"]["text"] == "Agrees with SQL's bank account 310-1000"
      and s["listing_docs"] == 0, s["sql_check"])
rv = j("get", f"/api/recon/review?entity_id={EID}&statement_id={S_OCT}")
check("the review screen shows the same check", rv["summary"]["sql_check"]["state"] == "agrees")
s = summary("2026-11")
check("a month SQL's Journal of Transaction doesn't cover is skipped with the reason",
      s["sql_check"]["state"] == "skipped" and "Journal of Transaction" in s["sql_check"]["text"], s["sql_check"])
s = summary("2026-08")
check("a month before tracking isn't checked", s["sql_check"]["state"] == "skipped" and "before tracking" in s["sql_check"]["text"], s["sql_check"])

# ---------- 4. a signed-off month whose figures change ----------
y = year()
check("September keeps its sign-off, and says its book figures changed",
      y["2026-09"]["status"] == "reconciled" and y["2026-09"]["book_changed"]
      and y["2026-09"]["book_changed"]["old"] == {"in": 2000.0, "out": 520.0, "closing": 12470.0}
      and y["2026-09"]["book_changed"]["new"] == {"in": 1980.0, "out": 500.0, "closing": 12470.0}
      and y["2026-09"]["book_changed"]["text"] == "Book figures changed since sign-off: confirm again", y["2026-09"])
check("it isn't un-signed in the records", q("SELECT reconciled_at FROM statements WHERE id = ?", (S_SEP,))[0]["reconciled_at"])
s = summary("2026-09")
check("its month summary asks to confirm again", s["book_changed"]["text"] == "Book figures changed since sign-off: confirm again"
      and s["status"] == "reconciled" and s["can_reconfirm"], s.get("book_changed"))
check("August, before tracking, is untouched", y["2026-08"]["status"] == "reconciled" and not y["2026-08"]["book_changed"]
      and y["2026-08"]["book_closing"] == 11000, y["2026-08"])
err = j("post", "/api/recon/confirm-book", expect=400, json={"entity_id": EID, "statement_id": S_OCT})
check("a month not signed off has nothing to confirm again", "isn't marked as reconciled" in err["error"], err)
err = j("post", "/api/recon/confirm-book", expect=400, json={"entity_id": EID, "statement_id": S_AUG})
check("nor one whose figures didn't change (before tracking)", err["error"].startswith("Nothing to confirm"), err)
s = summary("2026-12")
check("a signed-off month whose new figures differ from the bank keeps its sign-off, but can't be confirmed as it is",
      s["status"] == "reconciled" and s["book_changed"]["new"]["closing"] == 53990 and not s["can_reconfirm"]
      and "undo the sign-off and review the month" in s["reconfirm_why"], (s["status"], s["book_changed"], s["reconfirm_why"]))
err = j("post", "/api/recon/confirm-book", expect=400, json={"entity_id": EID, "statement_id": S_DEC})
check("confirming it is refused with the reason", "differs from the bank by" in err["error"]
      and q("SELECT book_rule_at FROM statements WHERE id = ?", (S_DEC,))[0]["book_rule_at"] is None, err)
r = j("post", "/api/recon/confirm-book", json={"entity_id": EID, "statement_id": S_SEP})
y = year()
check("confirming again keeps the sign-off and clears the question", r["ok"] and y["2026-09"]["status"] == "reconciled"
      and not y["2026-09"]["book_changed"], y["2026-09"])
log = q("SELECT what FROM activity ORDER BY id DESC LIMIT 1")[0]["what"]
check("the confirmation is logged with the old and new figures", "Confirmed again" in log and "2,000.00" in log and "1,980.00" in log, log)
check("signing a month off now records it under the new rule",
      "book_rule_at" in q("SELECT * FROM statements WHERE id = ?", (S_SEP,))[0] and q("SELECT book_rule_at FROM statements WHERE id = ?", (S_SEP,))[0]["book_rule_at"])

print("\nAll checks passed.")
