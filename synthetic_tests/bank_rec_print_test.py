"""The printed bank reconciliation statement (slice 4), on made-up records only.

1. The form code: BR-yymm-<company code>-<last 4 digits of the account number>, the company part from the company record.
2. The keyed check is worked out from the printed figures with a key kept in the records: the same figures give the same
   check, a changed figure another; a check typed back is verified.
3. The key is made once, on the first statement printed, and that is logged; it is never in the audit trail, never in
   a Move setup file (export leaves it out; a file naming it is refused, so load never reads one).
4. The statement prints as a PDF (with the code and check), and the month's Excel export holds its lists.
5. The audit pack's reconciliation page shows the signed statement's code, its sign-off note and the signed copy filed
   on the month's bank reconciliation checklist item.

Made-up company EXZ (kept here) with account Current (number 9900-2468).

Run: .venv\\Scripts\\python -m synthetic_tests.bank_rec_print_test
"""
import base64
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-bank-rec-print-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import auditpack, bankrecpdf, checklistbook, config, db, formcode, setupfile  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXZ", "name": "Example Printing Sdn Bhd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "9900-2468"}]},
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
    return r


EID = q("SELECT id FROM entities WHERE code = 'EXZ'")[0]["id"]
AID = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
NOW = db.now()
con = db.connect()
con.arm("user", "test: a made-up company, a payment and its October statement")
con.execute("UPDATE entities SET uses_sql = 0, first_month = '2026-09' WHERE id = ?", (EID,))
# The starter checklist a company added in Setup gets, with its Bank reconciliation item (shown done by the sign-off).
checklistbook.seed_company(con, dict(con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()), starter=True)
PAY = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                     direction, created_at) VALUES (?, '2026-10', ?, 'other', 'Test Payee Kappa supplies', 320, '2026-10-09', '2026-10-09', 'manual', 'out', ?)""",
                  (EID, AID, NOW)).lastrowid
con.execute("INSERT INTO book_openings (account_id, month, amount, set_at) VALUES (?, '2026-10', 2000, ?)", (AID, NOW))
SID = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, '2026-10', 2000, 1675, ?, 1)",
                  (AID, NOW)).lastrowid
con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
               VALUES (?, 1, '2026-10-09', 'IBG DR TEST PAYEE KAPPA', -320, 1680, ?, 'matched', ?)""", (SID, PAY, NOW))
con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, status, note, confirmed_at)
               VALUES (?, 2, '2026-10-31', 'SERVICE CHARGE', -5, 1675, 'no_docs', 'Bank charge', ?)""", (SID, NOW))
# A refund out and back the same day, never on the bank (a No money moved pair); one description outside Latin-1.
for desc, way in (("Test refund Ţeta out", "out"), ("Test refund Ţeta back", "in")):
    con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                   direction, created_at) VALUES (?, '2026-10', ?, ?, ?, 50, '2026-10-15', '2026-10-15', 'manual', ?, ?)""",
                (EID, AID, "receipt" if way == "in" else "other", desc, way, NOW))
# November: a payment out of 1,800.00 of which only 800.00 is on the statement (matched, but the amounts differ).
PART = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date, paid_source,
                      direction, created_at) VALUES (?, '2026-11', ?, 'other', 'Test Payee Lambda works', 1800, '2026-11-05', '2026-11-05', 'manual', 'out', ?)""",
                   (EID, AID, NOW)).lastrowid
NOV = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, '2026-11', 1675, 875, ?, 1)",
                  (AID, NOW)).lastrowid
con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status, confirmed_at)
               VALUES (?, 1, '2026-11-05', 'IBG DR TEST PAYEE LAMBDA', -800, 875, ?, 'matched', ?)""", (NOV, PART, NOW))
con.commit()
con.close()

# ---------- 1. the code ----------
check("the form code is BR, the month, the company's code and the account's last 4 digits",
      formcode.code("BR", "2026-10", "EXZ", "9900-2468", AID) == "BR-2610-EXZ-2468")
check("...from whatever company code the record holds, and the account id when the number is short",
      formcode.code("BR", "2027-01", "ab c", "12", 7) == "BR-2701-ABC-0007")

# ---------- 2 and 3. the key, made on the first statement printed ----------
check("no key is kept before anything is printed", not q("SELECT * FROM form_keys"))
r = call("get", f"/api/recon/statement.pdf?entity_id={EID}&account_id={AID}&month=2026-10", 409)
check("the PDF can't be drawn before the statement is printed once (the key is made by printing)", "Print the reconciliation statement" in r.get_json()["error"])
p1 = call("post", "/api/recon/print", json={"entity_id": EID, "account_id": AID, "month": "2026-10", "printed_by": "Test Printer"}).get_json()
keys = q("SELECT * FROM form_keys")
made = [r["what"] for r in q("SELECT what FROM activity WHERE what LIKE 'Made the key%'")]
check("printing the first statement makes the key, once, and logs it", len(keys) == 1 and len(made) == 1, (keys, made))
check("the print preview carries the code and a check of the form XXX-XXXX",
      p1["preview"]["code"] == "BR-2610-EXZ-2468" and re.fullmatch(r"[A-Z2-9]{3}-[A-Z2-9]{4}", p1["preview"]["check"]), p1["preview"])
check("...and the printing is logged with them", q("SELECT 1 FROM activity WHERE what LIKE ? AND what LIKE ?",
                                                 ("Printed the bank reconciliation statement BR-2610-EXZ-2468%", f"%check {p1['preview']['check']}%")))
p2 = call("post", "/api/recon/print", json={"entity_id": EID, "account_id": AID, "month": "2026-10", "printed_by": "Test Printer"}).get_json()
check("printed again with the same figures: the same check, and no second key",
      p2["preview"]["check"] == p1["preview"]["check"] and len(q("SELECT * FROM form_keys")) == 1
      and len(q("SELECT 1 FROM activity WHERE what LIKE 'Made the key%'")) == 1)
secret = keys[0]["secret"]
trail = q("SELECT tbl, before, after FROM audit_row")
check("the key is never copied into the audit trail", not any(r["tbl"] == "form_keys" for r in trail)
      and not any(secret in (r["before"] or "") or secret in (r["after"] or "") for r in trail))

con = db.connect()
con.arm("user", "test: reading the statement")
ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
acct = con.execute("SELECT * FROM accounts WHERE id = ?", (AID,)).fetchone()
data = bankrecpdf.statement(con, ent, acct, "2026-10")
check("the check is worked out from the figures printed", formcode.verify(con, data["code"], data["figures"], data["check"])
      and data["check"] == p1["preview"]["check"])
figs = [data["figures"][0].replace("1675.0", "1675.01")]
check("a figure changed by one sen gives another check", figs != data["figures"] and formcode.check(con, data["code"], figs) != data["check"]
      and not formcode.verify(con, data["code"], figs, data["check"]))
check("...another code too", formcode.check(con, "BR-2610-EXZ-9999", data["figures"]) != data["check"])
check("a check typed back in lower case or without its dash still verifies",
      formcode.verify(con, data["code"], data["figures"], data["check"].lower().replace("-", "")))
# Everything printed counts, dates and reasons too, not only the amounts.
con.execute("UPDATE payments SET paid_date = '2026-10-16' WHERE description LIKE 'Test refund %'")
moved = bankrecpdf.statement(con, ent, acct, "2026-10")
con.rollback()
check("the dates printed changed (the pair's entries a day later, the same amounts) give another check",
      moved["check"] != data["check"] and moved["totals"] == data["totals"])
key = bankrecpdf.recon.month_summary(con, ent, acct, "2026-10")["pairs"][0]["key"]
con.close()
call("post", "/api/recon/pair", json={"entity_id": EID, "account_id": AID, "month": "2026-10", "key": key, "reason": "Refund, first reason"})
con = db.connect()
first = bankrecpdf.statement(con, ent, acct, "2026-10")["check"]
con.close()
call("post", "/api/recon/pair", json={"entity_id": EID, "account_id": AID, "month": "2026-10", "key": key, "reason": "Refund, another reason"})
con = db.connect()
second = bankrecpdf.statement(con, ent, acct, "2026-10")
check("a pair's reason changed (the same amounts) gives another check", first != second["check"] and first != data["check"])
check("printing again later (another day, another person) keeps the check", bankrecpdf.statement(
    con, ent, acct, "2026-10", printed_by="Someone Else", today=__import__("datetime").date(2027, 1, 1))["check"] == second["check"])
# Two first prints at once: the one that comes second uses the key the first made, and makes no second one.
kept = q("SELECT secret FROM form_keys")[0]["secret"]
check("a second key isn't made when one is there already (two first prints at once)",
      base64.b64encode(formcode._create(con)).decode() == kept and len(q("SELECT * FROM form_keys")) == 1)
con.rollback()
check("...and no second 'Made the key' line is logged", len(q("SELECT 1 FROM activity WHERE what LIKE 'Made the key%'")) == 1)
con.close()

# November: a payment partly on the statement. The reconciliation and its totals check both account for it.
con = db.connect()
nov = bankrecpdf.statement(con, ent, acct, "2026-11")
con.close()
check("a month whose only item is a payment matched for another amount reconciles on paper, and its totals tally",
      nov["tot_line"].startswith("The debit and credit totals tally with the statement") and "make up the difference" in nov["rec_line"], (nov["tot_line"], nov["rec_line"]))
row = next(t for t in nov["totals"] if t["label"].startswith("Add or less: matched"))
check("...the difference is taken off the money out, where the payment is", row["in"] == 0 and row["out"] == -1000, row)

# The month's figures change (a line's note changes nothing; the sign-off does): the statement's check changes with them.
call("post", "/api/recon/sign-off", json={"entity_id": EID, "statement_id": SID, "note": "Test sign-off", "prepared_by": "Test Preparer"})
p3 = call("post", "/api/recon/print", json={"entity_id": EID, "account_id": AID, "month": "2026-10"}).get_json()
check("signed off, the statement prints otherwise, so its check is another", p3["preview"]["check"] != p1["preview"]["check"]
      and p3["preview"]["signed"] and "Signed off on" in p3["preview"]["sign_line"] and "Test Preparer" in p3["preview"]["sign_line"], p3["preview"])
check("...its sign-off note is the one the app wrote, with the free note", any("Explained without documents" in t for t in p3["preview"]["note"])
      and "Note: Test sign-off" in p3["preview"]["note"], p3["preview"]["note"])
check("...and Prepared by is filled in from the sign-off; Reviewed by is left for an approver of the company",
      p3["preview"]["signers"][0]["name"] == "Test Preparer" and p3["preview"]["signers"][1]["note"] == "An approver of EXZ", p3["preview"]["signers"])

# ---------- 3. never in a Move setup file ----------
con = db.connect()
exp = setupfile.export(con, "full", payees=True)
text = json.dumps(exp)
check("a Move setup file (everything) leaves the key out", secret not in text and "form_keys" not in text and "form_key" not in text)
tmpl = json.dumps(setupfile.export(con, "template", entity_id=EID))
check("...and so does a template", secret not in tmpl and "form_keys" not in tmpl)
bad = dict(exp, form_keys=[{"secret": base64.b64encode(b"0" * 32).decode(), "created_at": NOW}])
try:
    setupfile.load(con, bad, preview=True)
    refused = None
except setupfile.Refused as ex:
    refused = str(ex)
con.rollback()
check("a setup file naming a key is refused before anything is read from it, so load never takes one",
      refused and "form_keys" in refused and q("SELECT secret FROM form_keys")[0]["secret"] == secret, refused)
con.close()

# ---------- 4. the PDF and the Excel export ----------
r = call("get", f"/api/recon/statement.pdf?entity_id={EID}&account_id={AID}&month=2026-10")
check("the statement is a PDF", r.data[:5] == b"%PDF-" and r.mimetype == "application/pdf")
from pypdf import PdfReader  # noqa: E402
pdf_text = " ".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(r.data)).pages)
check("...that prints the code, the check and its parts", "BR-2610-EXZ-2468" in pdf_text and p3["preview"]["check"] in pdf_text
      and "Reconciliation at" in pdf_text and "Totals check" in pdf_text and "Prepared by and Reviewed by" in pdf_text, pdf_text[:400])
uni = "Test refund Ţeta out" in pdf_text
check("a name outside Latin-1 prints as written in the invoices' font, or the statement says why it shows as '?'",
      uni or ("show as '?' or are left out here" in " ".join(pdf_text.split()) and "Test refund ?eta out" in pdf_text), pdf_text[-500:])
print(f"     (the statement was printed {'in a Unicode font' if uni else 'in Helvetica, with the note'})")
check("...and a name the font has no glyph for (a Chinese character) is said at the foot, not left out silently",
      "show as '?' or are left out here" in " ".join(" ".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(
          bankrecpdf.render(dict(p3["preview"], company=p3["preview"]["company"] + " 测", rec=[], pairs=[], totals=[])))).pages).split()))
check("...named for the form", "BR-2610-EXZ-2468 Bank reconciliation Current October 2026.pdf" in r.headers.get("Content-Disposition", ""),
      r.headers.get("Content-Disposition"))
r = call("get", f"/api/export/recon.xlsx?entity_id={EID}&account_id={AID}&month=2026-10")
from openpyxl import load_workbook  # noqa: E402
wb = load_workbook(io.BytesIO(r.data))
check("the month's Excel holds the lines, the No money moved pairs and the outstanding lists",
      {"Summary", "Lines", "No money moved", "Reopened"} <= set(wb.sheetnames) and wb["Lines"].max_row == 3, wb.sheetnames)

# ---------- 5. the signed copy filed on the checklist item, and the audit pack's page ----------
call("post", "/api/months/open", json={"entity_id": EID, "month": "2026-10"})
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={AID}&month=2026-10").get_json()
task = s["recon_task"]
check("the month names its bank reconciliation checklist item to file the signed statement on", task and task["documents"] == [], s["recon_task"])
for name in ("BR-2610-EXZ-9999 signed another account.pdf", "BR-2610-EXZ-2468 signed statement.pdf"):
    call("post", "/api/upload", data={"task_id": str(task["id"]), "doc_type": "recon", "file": (io.BytesIO(b"%PDF-1.4\n% made-up signed copy\n"), name)},
         content_type="multipart/form-data")
s = call("get", f"/api/recon/month?entity_id={EID}&account_id={AID}&month=2026-10").get_json()
check("the signed statement is filed on it as an ordinary document, and only this statement's copy counts for this account",
      [d["original_name"] for d in s["recon_task"]["documents"]] == ["BR-2610-EXZ-2468 signed statement.pdf"], s["recon_task"])
con = db.connect()
pages = auditpack._reconciliation(con, con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone(), "2026-10")
con.close()
pack_text = " ".join(" ".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(pages)).pages).split())
check("the audit pack's reconciliation page shows the statement's code, the signed copy and the sign-off note",
      "BR-2610-EXZ-2468" in pack_text and "BR-2610-EXZ-2468 signed statement.pdf" in pack_text and "another account" not in pack_text
      and "Sign-off note" in pack_text
      and "Explained without documents" in pack_text and "Test sign-off" in pack_text and "Test Preparer" in pack_text, pack_text[:600])

print("\nAll printed reconciliation statement checks passed.")
