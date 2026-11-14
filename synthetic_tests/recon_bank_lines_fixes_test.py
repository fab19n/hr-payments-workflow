"""Fixes to the bank reconciliation that counts SQL receipts and payments by their lines on the bank, on made-up records only.

Each case is its own made-up company, so one case's documents and statements can't change another's figures:
- SHR: a voucher listed on two rows for two payments (1,000.00 and 2,000.00), its lines one bank line of 3,000.00. Each
  payment is matched to its own statement line by its amount, never both lines to the first payment.
- FEE: a receipt settled by two documents of 5,000.00 (one not on the statement yet) never takes another customer's
  5,000.00 as a "fee"; a receipt with a fee of 12.50 takes the bank's own charge line, not a supplier's line of 12.50.
- NEW: a voucher edited in SQL and pasted again (3,500.00) after the journal gave its lines (3,000.00) is counted by
  the newer listing, the month says to fetch the journal again, and the SQL check no longer says it agrees.
- JNL: a general journal moving the bank, whose General Journal section was never read, stops the SQL check from
  saying it agrees; once that section is read it agrees.
- GON: a voucher a journal read found SQL no longer has is counted by its listing amount with advice to confirm it as
  deleted in SQL, not to fetch the journal again.
- CHG: a month signed off before the lines rule whose figures changed isn't done on the checklist until confirmed again,
  and the audit pack says the figures changed, with the old and new ones.

Run: .venv\\Scripts\\python -m synthetic_tests.recon_bank_lines_fixes_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-recon-bank-lines-fixes-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import auditpack, config, db, ledger, recon, statements  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

CODES = ("SHR", "FEE", "NEW", "JNL", "GON", "CHG")
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": c, "name": f"Example {c} Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": f"000-{c}"}]}
    for c in CODES]}), encoding="utf-8")


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


BANK = "310-1000"
NOW = db.now()
con = db.connect()
con.arm("user", "test: made-up companies, charts, documents and statements")
E = {}


def company(code, sections=({"label": "Bank Journal", "book": "bank"},)):
    """A made-up company kept in SQL from September 2026: its chart, a listing import, an SQL opening of 10,000.00 on the
    bank on 01/08/2026, a Journal of Transaction read of 01/08 to 31/10 with the sections given, and a book opening."""
    eid = q("SELECT id FROM entities WHERE code = ?", (code,))[0]["id"]
    aid = q("SELECT id FROM accounts WHERE entity_id = ?", (eid,))[0]["id"]
    con.execute("UPDATE entities SET uses_sql = 1, first_month = '2026-09', fy_start = 1 WHERE id = ?", (eid,))
    con.execute("UPDATE accounts SET gl_code = ? WHERE id = ?", (BANK, aid))
    for gl, name, typ, special, grp in [
            ("100-0000", "SHARE CAPITAL", "equity", None, "CP"), ("300-0000", "TRADE DEBTORS", "asset", "debtor_control", "CA"),
            (BANK, "BANK-EXAMPLE 0001", "asset", "bank", "CA"), ("400-0000", "TRADE CREDITORS", "liability", "creditor_control", "CL"),
            ("500-0000", "SALES", "income", None, "SL"), ("530-0000", "DISCOUNT RECEIVED", "income", None, "OI"),
            ("900-B001", "BANK CHARGES", "expense", None, "EP"), ("900-G001", "GENERAL EXPENSES", "expense", None, "EP")]:
        con.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special, sql_type) VALUES (?, ?, ?, ?, ?, ?)",
                    (eid, gl, name, typ, special, grp))
    imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing.xlsx', ?, 0, 0)",
                      (eid, NOW)).lastrowid
    tb = ledger.new_batch(con, eid, origin="sql", report="trial_balance", sql_import_id=imp, file_name="tb.xlsx",
                          period_from="2026-08-01", period_to="2026-08-31")
    ledger.put_openings(con, eid, tb, "2026-08-01", "sql_tb", [{"code": BANK, "dr_sen": S(10000), "cr_sen": 0},
                                                              {"code": "100-0000", "dr_sen": 0, "cr_sen": S(10000)}], True)
    jot = ledger.new_batch(con, eid, origin="sql", report="journal", sql_import_id=imp, file_name="jot.xlsx", period_from="2026-08-01",
                           period_to="2026-10-31", period_source="printed", sections=list(sections))
    con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-09', 10000, ?)", (aid, NOW))
    E[code] = {"eid": eid, "aid": aid, "imp": imp, "jot": jot}
    return E[code]


def pay(e, desc, amount, month, due, direction):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, direction, created_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (e["eid"], month, e["aid"], "receipt" if direction == "in" else "other", desc, amount, due, direction, NOW)).lastrowid


def entry(e, no, day, desc, amount, direction, pid, imp=None, kind="payment", doc_type=None):
    """One listing row (OR in, PV out, or a journal) linked to its payment."""
    return con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
                          payment_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (imp or e["imp"], e["eid"], no, day, desc, desc, amount, direction,
                        doc_type or ("OR" if direction == "in" else "PV"), kind, pid, "linked" if pid else "unlinked")).lastrowid


def doc(e, no, day, lines, batch=None, book="bank"):
    """The document in SQL's Journal of Transaction."""
    ledger.put_document(con, e["eid"], batch or e["jot"], {"doc_no": no, "doc_date": day, "book": book,
                                                           "lines": [{"code": k, "dr_sen": S(dr), "cr_sen": S(cr)} for k, dr, cr in lines]})


def receipt_lines(gross, fee, customer="300-C001"):
    return [(BANK, gross, 0), ("900-B001", fee, 0), (customer, 0, gross), (BANK, 0, fee)] if fee else [(BANK, gross, 0), (customer, 0, gross)]


def statement(e, month, opening, lines, signed=None):
    closing = round(opening + sum(x[2] for x in lines), 2)
    sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, ?, ?, ?, ?, 1)",
                      (e["aid"], month, opening, closing, NOW)).lastrowid
    bal = opening
    for n, x in enumerate(lines, 1):
        day, desc, amt = x[:3]
        pid, status, conf = (x[3], "matched", NOW) if len(x) > 3 else (None, "unmatched", None)
        bal = round(bal + amt, 2)
        con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status,
                       confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (sid, n, day, desc, amt, bal, pid, status, conf))
    if signed:
        con.execute("UPDATE statements SET reconciled_at = ?, reconciled_how = 'review' WHERE id = ?", (NOW, sid))
    return sid


# SHR: one voucher on two rows, for two payments.
A = company("SHR")
A_P1 = pay(A, "BRENTWICK SUPPLIES", 1000, "2026-09", "2026-09-10", "out")
A_P2 = pay(A, "BRENTWICK SUPPLIES", 2000, "2026-09", "2026-09-10", "out")
entry(A, "PV-M1", "2026-09-10", "BRENTWICK SUPPLIES", 1000, "out", A_P1)
entry(A, "PV-M1", "2026-09-10", "BRENTWICK SUPPLIES", 2000, "out", A_P2)
doc(A, "PV-M1", "2026-09-10", [("400-S001", 3000, 0), (BANK, 0, 3000)])
A_ST = statement(A, "2026-09", 10000, [("2026-09-10", "BRENTWICK SUPPLIES", -1000), ("2026-09-11", "BRENTWICK SUPPLIES", -2000)])

# FEE: a receipt settled by two documents, and a receipt with a fee beside a supplier's line of the same amount.
B = company("FEE")
B_PA = pay(B, "ALPHACO TRADING", 10000, "2026-09", "2026-09-06", "in")
entry(B, "OR-A1", "2026-09-06", "ALPHACO TRADING", 5000, "in", B_PA)
entry(B, "OR-A2", "2026-09-28", "ALPHACO TRADING", 5000, "in", B_PA)
doc(B, "OR-A1", "2026-09-06", receipt_lines(5000, 0))
doc(B, "OR-A2", "2026-09-28", receipt_lines(5000, 0))
B_PG = pay(B, "GAMMALINE LOGISTICS", 10000, "2026-09", "2026-09-12", "in")
entry(B, "OR-G1", "2026-09-12", "GAMMALINE LOGISTICS", 10000, "in", B_PG)
doc(B, "OR-G1", "2026-09-12", receipt_lines(10000, 12.50, "300-C002"))
B_PD = pay(B, "COURIER DELTAWAY", 12.50, "2026-09", "2026-09-13", "out")
entry(B, "PV-D1", "2026-09-13", "COURIER DELTAWAY", 12.50, "out", B_PD)
doc(B, "PV-D1", "2026-09-13", [("400-S009", 12.50, 0), (BANK, 0, 12.50)])
B_ST = statement(B, "2026-09", 10000, [("2026-09-06", "ALPHACO TRADING", 5000), ("2026-09-07", "INWARD TRANSFER BETAMAX SDN BHD", 5000),
                                       ("2026-09-12", "GAMMALINE LOGISTICS", 10000), ("2026-09-13", "COURIER DELTAWAY", -12.50),
                                       ("2026-09-14", "BANK CHARGES", -12.50)])

# NEW: a voucher kept at 3,000.00, then edited in SQL and pasted again at 3,500.00 (the journal not fetched again).
C = company("NEW")
C_PX = pay(C, "HOLLOWAY PRINTING", 3500, "2026-09", "2026-09-15", "out")
entry(C, "PV-X1", "2026-09-15", "HOLLOWAY PRINTING", 3000, "out", C_PX)
doc(C, "PV-X1", "2026-09-15", [("400-S002", 3000, 0), (BANK, 0, 3000)])
C_IMP2 = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing-2.xlsx', ?, 0, 0)",
                     (C["eid"], NOW)).lastrowid
entry(C, "PV-X1", "2026-09-15", "HOLLOWAY PRINTING", 3500, "out", C_PX, imp=C_IMP2)

# JNL: a general journal of 200.00 out of the bank whose section was never read, and a voucher of 50.00 with lines.
D = company("JNL")
entry(D, "JV-0001", "2026-09-10", "TRANSFER TO PETTY CASH", 200, None, None, kind="journal", doc_type="JV")
D_PY = pay(D, "QUILLON STATIONERS", 50, "2026-09", "2026-09-05", "out")
entry(D, "PV-Y1", "2026-09-05", "QUILLON STATIONERS", 50, "out", D_PY)
doc(D, "PV-Y1", "2026-09-05", [("400-S003", 50, 0), (BANK, 0, 50)])

# GON: a voucher with lines kept that a later journal read of September no longer holds.
G = company("GON")
G_PG = pay(G, "MERIDALE TRAVEL", 3000, "2026-09", "2026-09-18", "out")
entry(G, "PV-G1", "2026-09-18", "MERIDALE TRAVEL", 3000, "out", G_PG)
doc(G, "PV-G1", "2026-09-18", [("400-S004", 3000, 0), (BANK, 0, 3000)])
G_JOT2 = ledger.new_batch(con, G["eid"], origin="sql", report="journal", sql_import_id=G["imp"], file_name="jot-sep.xlsx",
                          period_from="2026-09-01", period_to="2026-09-30", period_source="printed",
                          sections=[{"label": "Bank Journal", "book": "bank"}])
ledger.mark_gone(con, G["eid"], G_JOT2, "2026-09-01", "2026-09-30", {"bank"}, [])

# CHG: September signed off under listing amounts with the same closing by lines; October signed off with a fee the
# statement doesn't show, so by lines the books differ from the bank by 10.00.
H_ = company("CHG")
H_SR = pay(H_, "QUORVEX TRADING", 2000, "2026-09", "2026-09-10", "in")
H_SP = pay(H_, "BRENTWICK SUPPLIES", 520, "2026-09", "2026-09-15", "out")
entry(H_, "OR2609-001", "2026-09-10", "QUORVEX TRADING", 2000, "in", H_SR)
doc(H_, "OR2609-001", "2026-09-10", receipt_lines(2000, 20))
entry(H_, "PV2609-001", "2026-09-15", "BRENTWICK SUPPLIES", 520, "out", H_SP)
doc(H_, "PV2609-001", "2026-09-15", [("400-S001", 520, 0), (BANK, 0, 500), ("530-0000", 0, 20)])
H_SEP = statement(H_, "2026-09", 10000, [("2026-09-10", "QUORVEX TRADING", 1980, H_SR), ("2026-09-15", "BRENTWICK SUPPLIES", -500, H_SP)],
                  signed=True)
H_OR = pay(H_, "ZEPHYRA HOLDINGS", 4000, "2026-10", "2026-10-03", "in")
entry(H_, "OR2610-001", "2026-10-03", "ZEPHYRA HOLDINGS", 4000, "in", H_OR)
doc(H_, "OR2610-001", "2026-10-03", receipt_lines(4000, 10))
H_OCT = statement(H_, "2026-10", 11480, [("2026-10-03", "ZEPHYRA HOLDINGS", 4000, H_OR)], signed=True)
con.commit()
con.disarm()
con.close()


def ent_of(e, cn):
    return cn.execute("SELECT * FROM entities WHERE id = ?", (e["eid"],)).fetchone()


def summary(e, month):
    return j("get", f"/api/recon/month?entity_id={e['eid']}&account_id={e['aid']}&month={month}")


def moves(e, month):
    cn = db.connect()
    try:
        return recon.movements(cn, ent_of(e, cn), recon.cash_book_account(cn, e["eid"]), month)
    finally:
        cn.close()


def lines(sid):
    return {r["line_no"]: r for r in q("SELECT * FROM statement_lines WHERE statement_id = ? ORDER BY line_no", (sid,))}


def match(e, sid):
    cn = db.connect()
    cn.arm("user", "test: match the statement")
    statements.classify(cn, sid)
    n = statements.auto_match(cn, sid)
    cn.commit()
    cn.disarm()
    cn.close()
    return n


def total(pid):
    cn = db.connect()
    try:
        return db.linked_total(cn, cn.execute("SELECT * FROM payments WHERE id = ?", (pid,)).fetchone())
    finally:
        cn.close()


def parts(e, ids):
    cn = db.connect()
    try:
        return recon.bank_parts(cn, e["eid"], ids)
    finally:
        cn.close()


# ---------- 1. a voucher listed on two rows for two payments ----------
check("a voucher listed for two payments gives neither of them its bank lines", parts(A, [A_P1, A_P2]) == {}, parts(A, [A_P1, A_P2]))
match(A, A_ST)
L = lines(A_ST)
check("each payment is matched to its own line by its amount", L[1]["payment_id"] == A_P1 and L[2]["payment_id"] == A_P2, L)
check("each is fully paid, not one paid three times over", total(A_P1) == 1000 and total(A_P2) == 2000, (total(A_P1), total(A_P2)))
mv = moves(A, "2026-09")
check("the month still counts what the voucher posted to the bank, one item per payment",
      sorted((i["payment_id"], i["amount"]) for i in mv["items"]) == sorted([(A_P1, -1000), (A_P2, -2000)]) and mv["out"] == 3000, mv["items"])
s = summary(A, "2026-09")
check("nothing differs and nothing is left on either side", s["difference"] == 0 and not s["differ"] and not s["books_only"]
      and not s["bank_only"], (s["difference"], s["differ"], s["books_only"], s["bank_only"]))

# ---------- 2. what can be taken as a fee ----------
match(B, B_ST)
L = lines(B_ST)
check("another customer's receipt of the same amount is never taken as a fee", L[2]["payment_id"] is None, L[2])
check("a receipt settled by two documents isn't matched by its merged lines", L[1]["payment_id"] in (None,), L[1])
check("a receipt with a fee takes its own line and the bank's charge line", L[3]["payment_id"] == B_PG and L[5]["payment_id"] == B_PG, (L[3], L[5]))
check("a supplier's own line of the same amount stays with its own payment", L[4]["payment_id"] == B_PD, L[4])

# ---------- 3. a listing pasted after the journal gave the lines ----------
mv = moves(C, "2026-09")
x = mv["items"][0]
check("a voucher pasted again after its lines were read counts by the newer listing", len(mv["items"]) == 1 and x["amount"] == -3500
      and x["basis"] == "listing" and mv["listing_docs"] == 1 and mv["newer_docs"] == 1, mv)
s = summary(C, "2026-09")
check("the month says to fetch the journal again, the lines kept being out of date",
      "fetch SQL's GL Journal of Transaction" in s["listing_note"] and "pasted again after the journal was read" in s["listing_note"], s["listing_note"])
check("the SQL check no longer says it agrees", s["sql_check"]["state"] == "differs" and s["sql_check"]["difference"] == -500, s["sql_check"])
check("its payment isn't matched by the out-of-date lines", parts(C, [C_PX]) == {}, parts(C, [C_PX]))

# ---------- 4. a journal whose section was never read ----------
s = summary(D, "2026-09")
check("the book side leaves the journal out", s["left_out"]["journals"] == 1, s["left_out"])
check("the SQL check is skipped, naming the section and the journal, instead of saying it agrees",
      s["sql_check"]["state"] == "skipped" and "General Journal" in s["sql_check"]["text"] and "JV-0001" in s["sql_check"]["text"]
      and "all its sections" in s["sql_check"]["text"], s["sql_check"])
cn = db.connect()
cn.arm("user", "test: the General Journal is read")
jot2 = ledger.new_batch(cn, D["eid"], origin="sql", report="journal", sql_import_id=D["imp"], file_name="jot-gj.xlsx", period_from="2026-09-01",
                        period_to="2026-09-30", period_source="printed",
                        sections=[{"label": "Bank Journal", "book": "bank"}, {"label": "General Journal", "book": "general"}])
for no, day, ls, book in [("PV-Y1", "2026-09-05", [("400-S003", 50, 0), (BANK, 0, 50)], "bank"),
                          ("JV-0001", "2026-09-10", [("900-G001", 200, 0), (BANK, 0, 200)], "general")]:
    ledger.put_document(cn, D["eid"], jot2, {"doc_no": no, "doc_date": day, "book": book,
                                             "lines": [{"code": k, "dr_sen": S(dr), "cr_sen": S(cr)} for k, dr, cr in ls]})
cn.commit()
cn.disarm()
cn.close()
s = summary(D, "2026-09")
check("once the section is read, the journal counts and the check agrees", s["left_out"]["journals"] == 0 and s["book"]["closing"] == 9750
      and s["sql_check"]["state"] == "agrees", (s["left_out"], s["book"], s["sql_check"]))

# ---------- 5. a voucher SQL no longer has ----------
mv = moves(G, "2026-09")
check("a voucher SQL no longer has counts by its listing amount, apart from those with no lines kept",
      mv["items"][0]["amount"] == -3000 and mv["items"][0]["basis"] == "listing" and mv["listing_docs"] == 0 and mv["gone_docs"] == 1, mv)
s = summary(G, "2026-09")
check("the month points to confirming it as deleted in SQL, not to fetching the journal again",
      "Deleted in SQL" in s["listing_note"] and "count them by their bank lines" not in s["listing_note"] and s["gone_docs"] == 1, s["listing_note"])

# ---------- 6. a signed-off month whose figures changed, on the checklist and in the audit pack ----------
cn = db.connect()
ent = ent_of(H_, cn)
acct = recon.cash_book_account(cn, H_["eid"])
check("September waits on the checklist until it is confirmed again",
      recon.not_reconciled(cn, ent, H_["aid"], "2026-09") == "book figures changed since sign-off: confirm again",
      recon.not_reconciled(cn, ent, H_["aid"], "2026-09"))
check("October, whose new figures differ from the bank, says so on the checklist",
      (recon.not_reconciled(cn, ent, H_["aid"], "2026-10") or "").startswith("book figures changed since sign-off and now differ from the bank by")
      and "10.00" in recon.not_reconciled(cn, ent, H_["aid"], "2026-10"), recon.not_reconciled(cn, ent, H_["aid"], "2026-10"))
said = []
auditpack._reconciled(recon.month_summary(cn, ent, acct, "2026-10"), said.append, lambda *a: None, lambda *a: None, "MYR")
text = " ".join(said)
check("the audit pack says the book figures changed since sign-off, with the old and new figures",
      "Book figures changed since sign-off: confirm again" in text and "closing RM 15,480.00" in text and "closing RM 15,470.00" in text
      and "needs reviewing again" in text, text)
said = []
auditpack._reconciled(recon.month_summary(cn, ent, acct, "2026-09"), said.append, lambda *a: None, lambda *a: None, "MYR")
check("and for September, whose new figures still agree, without asking to review it", "Book figures changed" in " ".join(said)
      and "needs reviewing again" not in " ".join(said), said)
cn.close()
r = j("post", "/api/recon/confirm-book", json={"entity_id": H_["eid"], "statement_id": H_SEP})
cn = db.connect()
check("once confirmed again, September is done on the checklist", r["ok"] and recon.not_reconciled(cn, ent_of(H_, cn), H_["aid"], "2026-09") is None,
      recon.not_reconciled(cn, ent_of(H_, cn), H_["aid"], "2026-09"))
said = []
auditpack._reconciled(recon.month_summary(cn, ent_of(H_, cn), acct, "2026-09"), said.append, lambda *a: None, lambda *a: None, "MYR")
check("and the audit pack no longer says its figures changed", "Book figures changed" not in " ".join(said), said)
cn.close()

print("\nAll checks passed.")
