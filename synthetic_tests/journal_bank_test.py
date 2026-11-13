"""A journal that moves the bank counts in the bank reconciliation, on made-up records only.

SQL Account's journal header carries one total (TOTALDR = TOTALCR), so which side of the bank a journal moved can't be
told from the listing. Its detail grid, pasted as a DATAPACKET of its own (rows with a DTLKEY and the journal's DOCKEY,
no DOCNO), gives the lines. Once a journal's lines are kept (sql_journal_lines) and some are on the bank account's GL code
(accounts.gl_code, else the chart entry named like the payment method most cash vouchers carry), the journal counts as
a bank movement of the net of those lines: in the month's book, in left_out, in Create payment and Link. A journal with
no lines, or none on the bank, stays out as before; lines pasted again replace the earlier ones; lines may be pasted
before the journal itself.

Run: .venv\\Scripts\\python -m synthetic_tests.journal_bank_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-journal-bank-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, recon, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
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


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
BANK_NAME, BANK_CODE, MONTH = "BANK-EXAMPLE 0001 0002 0003", "310-1000", "2026-10"


def book():
    """The month's books as recon counts them, and the bank's GL code it found, on a fresh connection."""
    con = db.connect()
    try:
        ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
        acct = recon.cash_book_account(con, EID)
        return recon.movements(con, ent, acct, MONTH), recon.bank_gl_code(con, acct)
    finally:
        con.close()


def packet(rows):
    """A DATAPACKET as SQL Account copies a grid: one ROW per dictionary."""
    def attrs(r):
        return " ".join('%s="%s"' % (k, v) for k, v in r.items())
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % attrs(r) for r in rows) + "</ROWDATA></DATAPACKET>")


def head(no, key, total, day="20261026", desc="EXAMPLE JOURNAL"):
    return {"DOCTYPE": "JE", "DOCKEY": key, "DOCNO": no, "DOCDATE": day, "POSTDATE": day, "JOURNAL": "GENERAL",
            "DESCRIPTION": desc, "TOTALDR": f"{total:.2f}", "TOTALCR": f"{total:.2f}"}


def line(key, dtl, seq, code, dr=0, cr=0):
    return {"DTLKEY": dtl, "DOCKEY": key, "SEQ": seq, "AREA": "----", "AGENT": "----", "PROJECT": "PV-0000-001", "CODE": code,
            "DESCRIPTION": "EXAMPLE LINE", "TAX": "", "LOCALTAXAMT": "0.00", "TAXINCLUSIVE": "FALSE", "DR": f"{dr:.2f}",
            "CR": f"{cr:.2f}", "LOCALDR": f"{dr:.2f}", "LOCALCR": f"{cr:.2f}", "CHANGED": "FALSE"}


def paste(text, apply=True):
    """Pastes the text on the SQL page: the preview, and (apply) the Import button; returns (preview, result)."""
    pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": text})
    if not apply:
        return pre
    if "journal_lines" in pre:
        res = j("post", "/api/sql/apply", json={"token": pre["token"]})
    else:
        links = {r["row"]: r["payment_id"] for r in pre["records"] if r["payment_id"]}
        res = j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": links})
    return pre, res


def entry(no):
    return next(x for x in j("get", f"/api/sql/entries?entity={EID}")["documents"] if x["doc_no"] == no)


# ---------- the listing: an OR, a PV and two journals ----------
listing = packet([
    {"DOCKEY": "301", "DOCNO": "OR2610-001", "DOCTYPE": "OR", "DOCDATE": "20261005", "DESCRIPTION": "EXAMPLE CUSTOMER LTD",
     "DOCAMT": "12345.00", "CANCELLED": "FALSE", "PAYMENTMETHODDESC": BANK_NAME, "DR": "12345.00", "CR": "0.00"},
    {"DOCKEY": "302", "DOCNO": "PV2610-001", "DOCTYPE": "PV", "DOCDATE": "20261006", "DESCRIPTION": "EXAMPLE SUPPLIER LTD",
     "DOCAMT": "2345.00", "CANCELLED": "FALSE", "PAYMENTMETHODDESC": BANK_NAME, "DR": "0.00", "CR": "2345.00"},
    head("JV2610-001", "334", 50000),
    head("JV2610-002", "340", 7000, desc="EXAMPLE RECLASS"),
])
check("a normal listing is not read as journal lines", sqlimport.journal_lines(listing) is None
      and sqlimport.journal_lines("not xml at all") is None and sqlimport.journal_lines(b"<DATAPACKET><ROW DOCNO='X'/></DATAPACKET>") is None)
pre, res = paste(listing)
check("a listing paste reads as before (4 records, no journal_lines)", "journal_lines" not in pre and len(pre["records"]) == 4
      and res == {"added": 4, "linked": 0, "skipped": 0, "bank_lines_matched": 0}, (pre.get("records"), res))
mv, code = book()
check("without lines or a bank code, journals stay out of the books", (mv["in"], mv["out"]) == (12345.0, 2345.0)
      and mv["left_out"]["journals"] == 2 and code is None, (mv, code))

# ---------- the lines, with no bank code to be found ----------
bank_line = packet([line("334", "335", 1000, BANK_CODE, dr=50000), line("334", "336", 2000, "306-1002", cr=50000)])
reclass = packet([line("340", "341", 1000, "520-1000", dr=7000), line("340", "342", 2000, "306-1002", cr=7000)])
pre = paste(bank_line, apply=False)
check("lines are recognised and the preview asks for the GL code",
      pre["journal_lines"]["lines"] == 2 and "Set the bank account's GL code in Setup" in pre["journal_lines"]["notes"][0]["text"]
      and "JV2610-001" in pre["journal_lines"]["notes"][0]["text"], pre["journal_lines"])
pre, res = paste(bank_line)
check("they are stored anyway, as a document and an import, and logged",
      res["journal_lines"] == 2 and len(q("SELECT * FROM sql_journal_lines WHERE dockey = '334'")) == 2
      and q("SELECT document_id FROM sql_imports ORDER BY id DESC LIMIT 1")[0]["document_id"]
      and "Imported SQL journal lines" in q("SELECT what FROM activity ORDER BY id DESC LIMIT 1")[0]["what"], res)
mv, _ = book()
check("without a bank code they still don't count", mv["in"] == 12345.0 and mv["left_out"]["journals"] == 2, mv)

# ---------- the bank code from the payment method ----------
con = db.connect()
con.arm("user", "test: the chart of accounts")
con.execute("INSERT INTO gl_accounts (entity_id, code, name) VALUES (?, ?, ?)", (EID, BANK_CODE, BANK_NAME))
con.execute("INSERT INTO gl_accounts (entity_id, code, name) VALUES (?, '306-1002', 'EXAMPLE OTHER ACCOUNT')", (EID,))
con.commit()
con.close()
mv, code = book()
check("the bank's GL code is found from the payment method most vouchers carry", code == BANK_CODE, code)
check("the journal now counts as money in, and leaves left_out", mv["in"] == 62345.0 and mv["out"] == 2345.0
      and mv["left_out"]["journals"] == 1, mv)
item = next(i for i in mv["items"] if i["ref"] == "JV2610-001")
check("it has the shape of a voucher in the books", item["kind"] == "sql" and item["amount"] == 50000.0 and item["payment_id"] is None
      and item["doc_type"] == "JE" and item["date"] == "2026-10-26" and item["status"] == "journal", item)

con = db.connect()
con.arm("user", "test: a GL code set in Setup")
con.execute("UPDATE accounts SET gl_code = '999-9999' WHERE entity_id = ?", (EID,))
con.commit()
con.close()
mv, code = book()
check("a GL code set on the account comes before the payment method's", code == "999-9999" and mv["in"] == 12345.0, (code, mv))
con = db.connect()
con.arm("user", "test: the GL code cleared again")
con.execute("UPDATE accounts SET gl_code = '' WHERE entity_id = ?", (EID,))
con.commit()
con.close()
check("an empty GL code falls back again", book()[1] == BANK_CODE)

con = db.connect()
con.arm("user", "test: the account's own SQL payment method")
con.execute("UPDATE accounts SET sql_payment_method = 'EXAMPLE OTHER ACCOUNT' WHERE entity_id = ?", (EID,))
con.commit()
con.close()
check("the account's own SQL payment method comes before the most used one", book()[1] == "306-1002", book()[1])
con = db.connect()
con.arm("user", "test: the SQL payment method cleared again")
con.execute("UPDATE accounts SET sql_payment_method = '' WHERE entity_id = ?", (EID,))
con.commit()
con.close()
check("and cleared, the most used one is used again", book()[1] == BANK_CODE)

# ---------- previews and repeats ----------
pre = paste(bank_line, apply=False)
check("the preview says what the journal moves", pre["journal_lines"]["notes"][0]["text"] ==
      "Journal lines for JV2610-001: bank account 310-1000 +50,000.00 (money in). Counts in the bank reconciliation once applied.",
      pre["journal_lines"]["notes"][0]["text"])
paste(bank_line)
mv, _ = book()
check("the same lines pasted again replace the earlier ones, they don't double",
      len(q("SELECT * FROM sql_journal_lines WHERE dockey = '334'")) == 2 and mv["in"] == 62345.0, mv)
paste(packet([line("334", "335", 1000, BANK_CODE, dr=40000), line("334", "336", 2000, "306-1002", cr=40000)]))
mv, _ = book()
check("lines changed in SQL and pasted again take the new figure", mv["in"] == 52345.0
      and len(q("SELECT * FROM sql_journal_lines WHERE dockey = '334'")) == 2, mv)
paste(bank_line)
paste(reclass)
mv, _ = book()
check("a reclass journal with no bank line stays out", mv["in"] == 62345.0 and mv["left_out"]["journals"] == 1
      and not any(i["ref"] == "JV2610-002" for i in mv["items"]), mv)
pre = paste(reclass, apply=False)
check("and the preview says it moves no money", "none of the 2 lines is on the bank account 310-1000" in pre["journal_lines"]["notes"][0]["text"],
      pre["journal_lines"]["notes"][0]["text"])

# ---------- lines before their journal ----------
early = packet([line("350", "351", 1000, BANK_CODE, cr=3000), line("350", "352", 2000, "610-1000", dr=3000)])
text = paste(early, apply=False)["journal_lines"]["notes"][0]["text"]
check("lines pasted before their journal are kept, with a note", "journal key 350" in text
      and "will count once the journal is pasted" in text and "-3,000.00 (money out)" in text, text)
paste(early)
mv, _ = book()
check("kept lines change nothing until the journal is there", mv["in"] == 62345.0 and mv["out"] == 2345.0, mv)
paste(packet([head("JV2610-003", "350", 3000, day="20261028")]))
mv, _ = book()
check("then it counts, as money out", mv["out"] == 5345.0 and mv["in"] == 62345.0 and mv["left_out"]["journals"] == 1
      and next(i for i in mv["items"] if i["ref"] == "JV2610-003")["amount"] == -3000.0, mv)

# ---------- Create payment and Link ----------
x = entry("JV2610-001")
check("the SQL page offers a bank-moving journal for linking, with what it moves", x["bank_move"] == 50000.0 and x["payment_id"] is None
      and entry("JV2610-002")["bank_move"] is None, (x["bank_move"], entry("JV2610-002")["bank_move"]))
r = j("post", f"/api/sql/entries/{entry('JV2610-002')['id']}", expect=400, json={"create_payment": {}})
check("a journal that moves no money can't make a payment", "no lines on the bank account" in r["error"], r)
j("post", f"/api/sql/entries/{x['id']}", json={"create_payment": {}})
pay = q("SELECT * FROM payments WHERE sql_ref = 'JV2610-001'")[0]
check("Create payment takes the bank amount and the direction from the sign",
      pay["amount"] == 50000.0 and pay["direction"] == "in" and pay["paid_date"] == "2026-10-26" and pay["category"] == "receipt", pay)
check("the journal stays a journal, linked", q("SELECT kind, status, payment_id FROM sql_entries WHERE doc_no = 'JV2610-001'")[0]
      == {"kind": "journal", "status": "journal", "payment_id": pay["id"]})
mv, _ = book()
check("the books now name the payment", next(i for i in mv["items"] if i["ref"] == "JV2610-001")["payment_id"] == pay["id"])

con = db.connect()
ent = con.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
acct = recon.cash_book_account(con, EID)
con.arm("user", "test: a bank statement")
sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at) VALUES (?, ?, 0, 0, ?)",
                  (acct["id"], MONTH, db.now())).lastrowid
con.execute("INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id) "
            "VALUES (?, 1, '2026-10-26', 'EXAMPLE CREDIT', 50000, 50000, ?)", (sid, pay["id"]))
con.commit()
st = con.execute("SELECT * FROM statements WHERE id = ?", (sid,)).fetchone()
books_only, bank_only, differ = recon._lists(con, ent, acct, MONTH, st, recon.movements(con, ent, acct, MONTH))
con.close()
check("once its payment's bank line is linked, nothing is left for the journal", not any(b["ref"] == "JV2610-001" for b in books_only)
      and not any(d["ref"] == "JV2610-001" for d in differ) and any(b["ref"] == "JV2610-003" for b in books_only), (books_only, differ))

# a money-out journal linked to a payment that exists
made = j("post", "/api/payments", json={"entity_id": EID, "month": MONTH, "description": "Example supplier bill", "category": "other",
                                         "amount": 3000, "due_date": "2026-10-28"})
pid = q("SELECT id FROM payments WHERE description = 'Example supplier bill'")[0]["id"]
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}", json={"payment_id": pid})
p = q("SELECT * FROM payments WHERE id = ?", (pid,))[0]
check("linking a journal to a payment adds its number and date", "JV2610-003" in p["sql_ref"] and p["paid_date"] == "2026-10-28", p)
check("the linked list shows the bank amount, not the journal total",
      next(x for x in j("get", f"/api/sql/entries?entity={EID}")["linked"] if x["doc_no"] == "JV2610-003")["amount"] == 3000.0)
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}/unlink", json={})
check("unlinking leaves it a journal, not linked", q("SELECT status, payment_id FROM sql_entries WHERE doc_no = 'JV2610-003'")[0]
      == {"status": "journal", "payment_id": None})
j("post", f"/api/sql/entries/{entry('JV2610-001')['id']}/unlink", json={})
check("a payment made from the journal stays while a bank line is linked to it", q("SELECT id FROM payments WHERE id = ?", (pay["id"],)))
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}", json={"create_payment": {}})
made = q("SELECT * FROM payments WHERE sql_ref = 'JV2610-003'")[0]
check("a money-out journal makes a payment out, for the bank amount", made["direction"] == "out" and made["amount"] == 3000.0, made)
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}/unlink", json={})
check("unlinked with nothing else on it, the payment made from the journal is removed", not q("SELECT id FROM payments WHERE id = ?", (made["id"],)))
mv, _ = book()
check("and the books still count both journals", mv["in"] == 62345.0 and mv["out"] == 5345.0 and mv["left_out"]["journals"] == 1, mv)

# a payment going the other way can't be linked; lines revised after Create payment don't strand the payment on unlink
r = j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}", expect=400, json={"payment_id": pay["id"]})
check("a money-out journal can't be linked to a money-in payment", "other way" in r["error"], r)
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}", json={"create_payment": {}})
paste(packet([line("350", "351", 1000, BANK_CODE, cr=2000), line("350", "352", 2000, "610-1000", dr=2000)]))
j("post", f"/api/sql/entries/{entry('JV2610-003')['id']}/unlink", json={})
check("lines revised after Create payment: unlinking still removes the payment made from it", not q("SELECT id FROM payments WHERE sql_ref = 'JV2610-003'"))
paste(early)
net0 = packet([line("340", "341", 1000, BANK_CODE, dr=800), line("340", "342", 2000, BANK_CODE, cr=800)])
t = paste(net0, apply=False)["journal_lines"]["notes"][0]["text"]
check("lines on the bank that net to nothing are described as that", "net to nothing" in t and "none of" not in t, t)
mv, _ = book()
check("the books are as before this block", mv["out"] == 5345.0 and mv["in"] == 62345.0, mv)

# ---------- a normal listing is unchanged ----------
more = packet([{"DOCKEY": "303", "DOCNO": "PV2610-002", "DOCTYPE": "PV", "DOCDATE": "20261008", "DESCRIPTION": "ANOTHER EXAMPLE SUPPLIER",
                "DOCAMT": "100.00", "CANCELLED": "FALSE", "PAYMENTMETHODDESC": BANK_NAME, "DR": "0.00", "CR": "100.00"}])
pre, res = paste(more)
mv, _ = book()
check("a later listing paste still counts its vouchers as it did", res["added"] == 1 and mv["out"] == 5445.0 and len(pre["records"]) == 1, (res, mv))

# ---------- lines copied as plain text: no document key, so the journal is chosen ----------
HEADING = "\t".join(["Account", "Description", "Ref", "Project", "Local DR", "Local CR", "Tax", "Tax Rate", "Tax Inclusive",
                     "Local Tax Amt", "Local DR (Tax)", "Local CR (Tax)"])


def text_lines(rows, heading=HEADING):
    """Lines as SQL Account copies an expanded journal: tab-separated, amounts with thousands commas."""
    def f(x):
        return f"{x:,.2f}"
    return heading + "\n" + "\n".join("\t".join([code, "EXAMPLE TEXT LINE", "", "PV-0000-002", f(dr), f(cr), "", "", "False", "0.00", f(dr), f(cr)])
                                       for code, dr, cr in rows) + "\n"


def apply_text(pre, journal_id, expect=200):
    return j("post", "/api/sql/apply", expect=expect, json={"token": pre["token"], "journal_id": journal_id})


paste(packet([head("JV2610-004", "360", 8000, day="20261015"), head("JV2610-005", "361", 9000, day="20261016"),
              {k: v for k, v in head("JV2610-006", "0", 8000, day="20261017").items() if k != "DOCKEY"}]))
other = q("SELECT MAX(import_id) AS i FROM sql_entries")[0]["i"]
with sqlite3.connect(config.DB_PATH) as raw:  # a journal of another company, with a key and the same total
    raw.execute("INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, amount, kind, dockey, status) "
                "VALUES (?, ?, 'JV2610-007', '2026-10-18', 8000, 'journal', '370', 'journal')", (other, EID + 99))
tl = text_lines([(BANK_CODE, 8000, 0), ("306-1002", 0, 8000)])
check("a text paste of journal lines is recognised", sqlimport.text_journal_lines(tl) and len(sqlimport.text_journal_lines(tl)) == 2
      and sqlimport.text_journal_lines(tl)[0]["dr"] == 8000.0 and sqlimport.text_journal_lines(tl)[1]["cr"] == 8000.0
      and sqlimport.text_journal_lines(tl)[0]["code"] == BANK_CODE and sqlimport.text_journal_lines(tl)[0]["project"] == "PV-0000-002")
check("other headings work too (Code, DR, CR) and blank rows are skipped",
      len(sqlimport.text_journal_lines("Code\tDR\tCR\n" + BANK_CODE + "\t1,000.00\t0.00\n\t\t\n306-1002\t0.00\t1,000.00\n")) == 2)
_q = sqlimport.text_journal_lines("Code\tDescription\tDR\tCR\n310-1000\tx\t50,000.00\t0.00\n306-1002\t\"ABC LEGAL\t0.00\t50,000.00\n310-1000\ty\t1.00\t0.00\n")
check("a description starting with a quote mark does not swallow the next rows",
      _q is not None and len(_q) == 3 and _q[1]["description"] == '"ABC LEGAL' and _q[1]["cr"] == 50000.0 and _q[2]["dr"] == 1.0)
check("a listing with a Doc No column is not read as lines",
      sqlimport.text_journal_lines("Doc No\tCode\tDR\tCR\nJV1\t310-1000\t1.00\t0.00\n") is None)
pre = paste(tl, apply=False)
jl = pre["journal_lines"]
by_no = {o["doc_no"]: o for o in jl["options"]}
check("the preview offers the company's journals with a key, not the keyless one or another company's",
      jl["text_form"] and jl["balanced"] and "JV2610-006" not in by_no and "JV2610-007" not in by_no and {"JV2610-004", "JV2610-005"} <= by_no.keys(), jl["options"])
check("the one journal with the same total is preselected, and the note is for it", jl["chosen"] == by_no["JV2610-004"]["id"]
      and jl["notes"][0]["text"] == "Journal lines for JV2610-004: bank account 310-1000 +8,000.00 (money in). Counts in the bank reconciliation once applied."
      and "Only JV2610-004" in jl["message"], jl)
pre2 = j("post", "/api/sql/preview", json={"token": pre["token"], "journal_id": by_no["JV2610-005"]["id"]})["journal_lines"]
check("choosing another journal changes the note and warns about the total", pre2["chosen"] == by_no["JV2610-005"]["id"]
      and "JV2610-005" in pre2["notes"][0]["text"] and "is 9,000.00: choose the journal they come from" in pre2["notes"][0]["text"], pre2)
mv0, _ = book()
res = apply_text(pre, jl["chosen"])
mv, _ = book()
check("applying with the choice counts in the books as the XML path does", res["journal_lines"] == 2 and mv["in"] == mv0["in"] + 8000.0
      and len(q("SELECT * FROM sql_journal_lines WHERE dockey = '360'")) == 2
      and q("SELECT seq, dtlkey FROM sql_journal_lines WHERE dockey = '360' ORDER BY seq") == [{"seq": 1, "dtlkey": None}, {"seq": 2, "dtlkey": None}]
      and "JV2610-004" in q("SELECT what FROM activity ORDER BY id DESC LIMIT 1")[0]["what"], (mv0, mv))
pre = paste(tl, apply=False)
apply_text(pre, pre["journal_lines"]["chosen"])
mv2, _ = book()
check("pasting the text again replaces the lines, it doesn't double", len(q("SELECT * FROM sql_journal_lines WHERE dockey = '360'")) == 2
      and mv2["in"] == mv["in"], mv2)

pre = paste(tl, apply=False)
r = apply_text(pre, None, expect=400)
check("no journal chosen is refused", "Choose the journal" in r["error"], r)
r = apply_text(pre, by_no["JV2610-005"]["id"], expect=400)
check("a journal with another total is refused", r["error"] == "These lines add up to 8,000.00, but JV2610-005 is 9,000.00: choose the journal they come from.", r)
nokey = q("SELECT id FROM sql_entries WHERE doc_no = 'JV2610-006'")[0]["id"]
r = apply_text(pre, nokey, expect=400)
check("a journal with no document key is refused", r["error"].startswith("Paste the journal list again so its document key is recorded"), r)
foreign = q("SELECT id FROM sql_entries WHERE doc_no = 'JV2610-007'")[0]["id"]
r = apply_text(pre, foreign, expect=400)
check("another company's journal is refused", "isn't one of this company's journals" in r["error"], r)
check("nothing was stored by the refusals", len(q("SELECT * FROM sql_journal_lines WHERE dockey IN ('361', '0', '370')")) == 0)

bad = text_lines([(BANK_CODE, 8000, 0), ("306-1002", 0, 7500)])
pre = paste(bad, apply=False)
check("unbalanced lines are said so and offer no journal", pre["journal_lines"]["balanced"] is False and "don't balance" in pre["journal_lines"]["message"]
      and pre["journal_lines"]["options"] == [] and pre["journal_lines"]["chosen"] is None, pre["journal_lines"])
r = apply_text(pre, by_no["JV2610-004"]["id"], expect=400)
check("and they are refused on apply", "don't balance" in r["error"], r)

none = text_lines([("520-1000", 1234, 0), ("306-1002", 0, 1234)])
pre = paste(none, apply=False)
check("with no journal of that total nothing is preselected", pre["journal_lines"]["chosen"] is None and pre["journal_lines"]["notes"] == []
      and "No imported journal has a total of 1,234.00" in pre["journal_lines"]["message"], pre["journal_lines"])

pre = paste("Doc No\tDoc Type\tDoc Date\tDescription\tCode\tDR\tCR\tAmount\tDoc key\n"
            "PV2610-009\tPV\t20261009\tEXAMPLE TEXT SUPPLIER\t310-1000\t0.00\t55.00\t55.00\t380\n", apply=False)
check("an ordinary text listing with a Doc No column goes the normal way", "journal_lines" not in pre and len(pre["records"]) == 1
      and pre["records"][0]["doc_no"] == "PV2610-009", pre)

# An Excel listing (a zip, whatever bytes it holds, tabs and NULs included) is never read as pasted journal lines
check("binary data is never pasted journal lines", sqlimport.text_journal_lines(b"PK\x03\x04\x00\x00\tAccount\tDR\tCR\n") is None
      and sqlimport.text_journal_lines(b"Account\tDR\tCR\n310-000\t\x00\t5\n") is None)
import io  # noqa: E402
from openpyxl import Workbook  # noqa: E402
wb = Workbook()
ws = wb.active
ws.append(["Doc No", "Doc Type", "Date", "Description", "Code", "Amount"])
ws.append(["PV2610-010", "PV", "2026-10-12", "EXAMPLE XLSX SUPPLIER\twith a tab", "310-1000", 75.0])
buf = io.BytesIO()
wb.save(buf)
r = c.post(BASE + "/api/sql/preview", headers=H, content_type="multipart/form-data",
           data={"entity_id": str(EID), "file": (io.BytesIO(buf.getvalue()), "PV listing.xlsx")})
check("an Excel listing still previews as a listing", r.status_code == 200 and "journal_lines" not in r.get_json()
      and len(r.get_json()["records"]) == 1, (r.status_code, r.data[:300]))

print("all passed")
