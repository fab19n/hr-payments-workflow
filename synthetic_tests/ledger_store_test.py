"""The ledger of SQL documents (update 26): storage, versions, checks and the bank reconciliation, on made-up records only.

Every document SQL's GL Journal of Transaction prints is kept as a header with its account lines (hrp/ledger.py), each
read as a batch that says where it came from. Exported again with the same lines it is only noted as seen; with other
lines it becomes a new version and the old one is kept; missing from a later journal with a printed period it is
marked no longer in SQL. Account lines can't be changed. Journal lines pasted from SQL's grid before update 26 are
copied in by the update itself, and a journal the ledger has counts in the bank reconciliation from its current lines.

Run: .venv\\Scripts\\python -m synthetic_tests.ledger_store_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-ledger-store-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, config, db, ledger, masters, recon, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXB", "name": "Example Branch Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
    {"code": "EXN", "name": "Example Nominees Ltd", "uses_sql": False,
     "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-333"}]},
    {"code": "EXT", "name": "Example Trading Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-444"}]},
    {"code": "EXR", "name": "Example Retail Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-555"}]},
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


def conn(action="test"):
    con = db.connect()
    con.arm("user", action)
    return con


BANK = "310-1000"


def book(eid, month):
    con = db.connect()
    try:
        ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
        mv = recon.movements(con, ent, recon.cash_book_account(con, eid), month)
        return mv["in"], mv["out"]
    finally:
        con.close()


def an_import(con, eid, name="test.xlsx"):
    return con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, 0, 0)",
                       (eid, name, db.now())).lastrowid


def entry(con, imp, eid, no, day, amount, kind, doc_type, direction=None, dockey=None, code=None, desc="EXAMPLE"):
    return con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, direction, doc_type, kind,
                          dockey, code) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (imp, eid, no, day, desc, amount, direction, doc_type, kind, dockey, code)).lastrowid


def pasted(con, imp, eid, key, lines):
    for i, (code, dr, cr) in enumerate(lines, 1):
        con.execute("""INSERT INTO sql_journal_lines (entity_id, dockey, import_id, dtlkey, seq, code, description, project, dr, cr)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (eid, key, imp, f"{key}-{i}", i * 1000, code, f"LINE {i}", "PRJ-1", dr, cr))


def line(code, dr=0, cr=0, desc="EXAMPLE LINE"):
    return {"code": code, "description": desc, "dr_sen": int(round(dr * 100)), "cr_sen": int(round(cr * 100))}


def jot_batch(con, eid, period=None, source=None, books=("general",)):
    return ledger.new_batch(con, eid, origin="sql", report="journal", sql_import_id=an_import(con, eid, "jot.xlsx"),
                            file_name="jot.xlsx", period_from=period[0] if period else None, period_to=period[1] if period else None,
                            period_source=source, sections=[{"label": b.title() + " Journal", "book": b} for b in books])


# ---------- 1. a records.db at update 25 with pasted journal lines, then update 26 ----------
full = db.MIGRATIONS[:]
check("update 26 is the ledger's install", len(full) == 26 and full[25] is ledger.install)
db.MIGRATIONS[:] = full[:25]
db.init()
EID, EXB, EXN, EXT, EXR = (q("SELECT id FROM entities WHERE code = ?", (x,))[0]["id"] for x in ("EXH", "EXB", "EXN", "EXT", "EXR"))
c = conn("test: records before update 26")
c.execute("UPDATE accounts SET gl_code = ? WHERE entity_id = ?", (BANK, EID))
imp1 = an_import(c, EID, "listing.xlsx")
entry(c, imp1, EID, "JV2610-001", "2026-10-05", 1000, "journal", "JV", dockey="K1")
entry(c, imp1, EID, "PV2610-001", "2026-10-06", 500, "payment", "PV", direction="out", dockey="K9")
imp2 = an_import(c, EID, "lines.txt")
pasted(c, imp2, EID, "K1", [(BANK, 1000, 0), ("306-1002", 0, 1000)])
pasted(c, imp2, EID, "K2", [(BANK, 700, 0), ("306-1002", 0, 700)])  # its journal isn't imported yet
# Another company: JV2610-001's lines were pasted under document key K11; the journal was then deleted and entered again
# in SQL under the same number (key K15, 900.00, no bank line), and only that listing was pasted again, not its lines.
c.execute("UPDATE accounts SET gl_code = ? WHERE entity_id = ?", (BANK, EXT))
entry(c, an_import(c, EXT, "listing.xlsx"), EXT, "JV2610-001", "2026-10-05", 1000, "journal", "JV", dockey="K11")
pasted(c, an_import(c, EXT, "lines.txt"), EXT, "K11", [(BANK, 1000, 0), ("306-1002", 0, 1000)])
entry(c, an_import(c, EXT, "listing-again.xlsx"), EXT, "JV2610-001", "2026-10-05", 900, "journal", "JV", dockey="K15")
c.commit()
c.close()
check("the records are at update 25 while they are built", q("PRAGMA user_version")[0]["user_version"] == 25)
before = book(EID, "2026-10")
check("before the update, the pasted journal counts in the bank reconciliation", before == (1000.0, 500.0), before)
before_t = book(EXT, "2026-10")
check("before the update, a re-entered journal's old pasted lines don't count", before_t == (0.0, 0.0), before_t)

db.MIGRATIONS[:] = full
trail = db.init()
check("every update has run", q("PRAGMA user_version")[0]["user_version"] == 26)
docs = q("SELECT * FROM ledger_docs")
check("the pasted journal with a header is copied as version 1",
      len(docs) == 1 and docs[0]["doc_no"] == "JV2610-001" and docs[0]["doc_key"] == "JV2610-001" and docs[0]["version"] == 1
      and docs[0]["doc_date"] == "2026-10-05" and docs[0]["book"] == "general" and docs[0]["state"] == "current"
      and (docs[0]["dr_sen"], docs[0]["cr_sen"], docs[0]["line_count"]) == (100000, 100000, 2), docs)
lines = q("SELECT * FROM ledger_lines ORDER BY seq")
check("its lines are copied in order, in sen, with the project",
      [(x["seq"], x["account_code"], x["dr_sen"], x["cr_sen"], x["project"]) for x in lines]
      == [(1, BANK, 100000, 0, "PRJ-1"), (2, "306-1002", 0, 100000, "PRJ-1")], lines)
b = q("SELECT * FROM ledger_batches")
check("in one 'legacy' batch for the import that brought them", len(b) == 1 and b[0]["report"] == "legacy"
      and b[0]["sql_import_id"] == imp2 and b[0]["origin"] == "sql" and b[0]["file_name"] == "lines.txt", b)
check("the journal with no header is left in the pasted lines", len(q("SELECT * FROM sql_journal_lines WHERE dockey = 'K2'")) == 2
      and len(q("SELECT * FROM sql_journal_lines WHERE dockey = 'K1'")) == 2)
after = book(EID, "2026-10")
check("the bank reconciliation gives the same figures after the update", after == before, (before, after))
check("a re-entered journal's old pasted lines are not copied under its number, and its figures don't change",
      book(EXT, "2026-10") == before_t and not q("SELECT * FROM ledger_docs WHERE entity_id = ?", (EXT,))
      and len(q("SELECT * FROM sql_journal_lines WHERE dockey = 'K11'")) == 2, (book(EXT, "2026-10"), q("SELECT * FROM ledger_docs WHERE entity_id = ?", (EXT,))))
ops = q("SELECT tbl, op, COUNT(*) AS n FROM audit_row WHERE tbl LIKE 'ledger_%' GROUP BY tbl, op")
check("the copied rows are in the trail as added by the update, not as a baseline",
      {(o["tbl"], o["op"]) for o in ops} == {("ledger_batches", "insert"), ("ledger_docs", "insert"), ("ledger_lines", "insert")}, ops)
tx = q("""SELECT t.action FROM audit_tx t WHERE t.token IN (SELECT token FROM audit_row WHERE tbl = 'ledger_docs')""")
check("sealed under Update 26", [t["action"] for t in tx] == ["Update 26"], tx)
r = db.connect()
v = audit.verify(r)
r.close()
check("the audit trail checks out", v["ok"], v)
check("start-up repaired no triggers", trail and not trail["triggers_repaired"], trail)
check("the ledger's guard is not one of the trail's triggers",
      q("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name = 'ledger_guard_here'")
      and "ledger_guard_here" not in audit._have(db.connect()))

# ---------- 2. the guards ----------
r = db.connect()
for word, sql in (("UPDATE", "UPDATE ledger_lines SET dr_sen = 1 WHERE id = 1"), ("DELETE", "DELETE FROM ledger_lines WHERE id = 1")):
    try:
        r.execute(sql)
        refused = None
    except sqlite3.DatabaseError as x:
        refused = str(x)
    check(f"account lines refuse {word}", refused and "Account lines can't be changed" in refused, refused)
r.rollback()
r.close()

c = conn("test: guards")
bid = ledger.new_batch(c, EID, origin="here", report="entered")
try:
    c.execute("""INSERT INTO ledger_docs (entity_id, origin, doc_no, doc_key, doc_date, book, dr_sen, cr_sen, line_count, fingerprint, batch_id)
                 VALUES (?, 'here', 'X1', 'X1', '2026-10-01', 'general', 0, 0, 0, 'x', ?)""", (EID, bid))
    refused = None
except sqlite3.DatabaseError as x:
    refused = str(x)
check("ledger_guard_here refuses an entry made here for a company kept in SQL", refused and "kept in SQL Account" in refused, refused)
try:
    ledger.put_document(c, EID, bid, {"origin": "here", "doc_no": "X1", "doc_date": "2026-10-01", "book": "general", "lines": []})
    refused = None
except ledger.LedgerError as x:
    refused = str(x)
check("put_document refuses it too", refused == ledger.REFUSED_HERE, refused)
nb = ledger.new_batch(c, EXN, origin="here", report="entered")
got = ledger.put_document(c, EXN, nb, {"origin": "here", "doc_no": "JE-1", "doc_date": "2026-10-01", "book": "general",
                                       "lines": [line("500-1000", dr=10), line("310-1000", cr=10)]})
check("and allows it for a company not kept in SQL", got["result"] == "new"
      and c.execute("SELECT origin FROM ledger_docs WHERE id = ?", (got["id"],)).fetchone()[0] == "here")
c.rollback()
c.disarm()
c.close()

# ---------- 3. versions ----------
c = conn("test: versions")
DEC = ("2026-12-01", "2026-12-31")
b1 = jot_batch(c, EID, DEC, "printed", books=("general", "sales"))
jv = {"doc_no": "JV2612-001", "doc_date": "2026-12-10", "book": "general", "book_label": "General Journal Journal",
      "lines": [line("500-1000", dr=250), line("306-1002", cr=250)]}
r1 = ledger.put_document(c, EID, b1, jv)
r1b = ledger.put_document(c, EID, b1, {**jv, "doc_no": " jv2612-002 "})
iv = {"doc_no": "IV2612-001", "doc_date": "2026-12-11", "book": "sales", "lines": [line("300-A0003", dr=90), line("500-2000", cr=90)]}
ledger.put_document(c, EID, b1, iv)
b2 = jot_batch(c, EID, DEC, "printed")
r2 = ledger.put_document(c, EID, b2, {**jv, "lines": list(reversed([line("500-1000", dr=250, desc="OTHER WORDS"), line("306-1002", cr=250)]))})
check("a new document is version 1; the same lines again (other order and words) are only seen",
      r1["result"] == "new" and r1["version"] == 1 and r2["result"] == "same" and r2["id"] == r1["id"]
      and c.execute("SELECT seen_batch_id FROM ledger_docs WHERE id = ?", (r1["id"],)).fetchone()[0] == b2, (r1, r2))
check("the doc no. is its identity, trimmed and upper case", r1b["result"] == "new"
      and c.execute("SELECT doc_no, doc_key FROM ledger_docs WHERE id = ?", (r1b["id"],)).fetchone()[:] == ("jv2612-002", "JV2612-002"))
b3 = jot_batch(c, EID, DEC, "printed")
r3 = ledger.put_document(c, EID, b3, {**jv, "lines": [line("500-1000", dr=260), line("306-1002", cr=260)]})
old = c.execute("SELECT * FROM ledger_docs WHERE id = ?", (r1["id"],)).fetchone()
check("other lines make version 2; version 1 is kept, superseded, with what replaced it",
      r3["result"] == "changed" and r3["version"] == 2 and old["state"] == "superseded" and old["replaced_by"] == r3["id"]
      and old["ended_batch_id"] == b3 and c.execute("SELECT COUNT(*) FROM ledger_lines WHERE doc_id = ?", (r1["id"],)).fetchone()[0] == 2,
      (r3, dict(old)))
r3b = ledger.put_document(c, EID, b3, {**jv, "doc_no": "JV2612-002", "doc_date": "2027-08-01"})
check("a date moved more than 180 days is noted", r3b["result"] == "changed" and r3b["note"] == "number reused?", r3b)
bl = jot_batch(c, EID, DEC, "lines")
check("with no printed period nothing is marked no longer in SQL",
      ledger.mark_gone(c, EID, bl, *DEC, {"general", "sales"}, []) == []
      and c.execute("SELECT state FROM ledger_docs WHERE id = ?", (r3["id"],)).fetchone()[0] == "current")
b4 = jot_batch(c, EID, DEC, "printed")
gone = ledger.mark_gone(c, EID, b4, *DEC, {"general"}, [])
check("with a printed period, only documents of the books the file has are marked no longer in SQL",
      [g["doc_no"] for g in gone] == ["JV2612-001"]
      and c.execute("SELECT state FROM ledger_docs WHERE doc_key = 'IV2612-001'").fetchone()[0] == "current", gone)
r5 = ledger.put_document(c, EID, b4, {**jv, "lines": [line("500-1000", dr=260), line("306-1002", cr=260)]})
check("a document back in SQL with the same lines is current again", r5["result"] == "back" and r5["id"] == r3["id"]
      and c.execute("SELECT state, ended_at FROM ledger_docs WHERE id = ?", (r3["id"],)).fetchone()[:] == ("current", None), r5)
view = ledger.doc_view(c, EID, "jv2612-001")
check("the document view has every version, newest first, with its batch", [x["version"] for x in view["versions"]] == [2, 1]
      and view["versions"][0]["totals"] == {"dr": 260.0, "cr": 260.0} and view["versions"][1]["state"] == "superseded"
      and view["versions"][0]["batch"]["report"] == "journal", view)
c.commit()
c.disarm()
c.close()

# ---------- 4. a pasted grid, then the same journal from the Journal of Transaction ----------
cl = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    resp = getattr(cl, method)(BASE + path, headers=H, **kw)
    assert resp.status_code == expect, (method, path, resp.status_code, resp.data[:500])
    return resp.get_json()


def packet(rows):
    def attrs(r):
        return " ".join('%s="%s"' % (k, v) for k, v in r.items())
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % attrs(r) for r in rows) + "</ROWDATA></DATAPACKET>")


def grid_line(key, dtl, seq, code, dr=0, cr=0):
    return {"DTLKEY": dtl, "DOCKEY": key, "SEQ": seq, "PROJECT": "----", "CODE": code, "DESCRIPTION": "GRID LINE",
            "DR": f"{dr:.2f}", "CR": f"{cr:.2f}", "LOCALDR": f"{dr:.2f}", "LOCALCR": f"{cr:.2f}"}


def paste(text):
    pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": text})
    if "journal_lines" in pre:
        return j("post", "/api/sql/apply", json={"token": pre["token"]})
    return j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})


paste(packet([{"DOCTYPE": "JE", "DOCKEY": "880", "DOCNO": "JV2611-005", "DOCDATE": "20261115", "POSTDATE": "20261115",
               "JOURNAL": "GENERAL", "DESCRIPTION": "EXAMPLE GRID JOURNAL", "TOTALDR": "4000.00", "TOTALCR": "4000.00"}]))
res = paste(packet([grid_line("880", "881", 1000, BANK, cr=4000), grid_line("880", "882", 2000, "520-1000", dr=4000)]))
gd = q("SELECT d.*, b.report FROM ledger_docs d JOIN ledger_batches b ON b.id = d.batch_id WHERE d.doc_key = 'JV2611-005'")
check("a pasted grid is still kept as pasted lines, and as a ledger document from a 'grid' read",
      res.get("journal_lines") == 2 and len(q("SELECT * FROM sql_journal_lines WHERE dockey = '880'")) == 2
      and len(gd) == 1 and gd[0]["report"] == "grid" and gd[0]["version"] == 1 and gd[0]["doc_date"] == "2026-11-15", (res, gd))
c = conn("test: JoT after a grid")
bj = jot_batch(c, EID, ("2026-11-01", "2026-11-30"), "printed")
same = ledger.put_document(c, EID, bj, {"doc_no": "JV2611-005", "doc_date": "2026-11-15", "book": "general",
                                        "book_label": "General Journal Journal",
                                        "lines": [line("520-1000", dr=4000, desc="JOT WORDS"), line(BANK, cr=4000, desc="JOT WORDS")]})
check("the same journal from the Journal of Transaction makes no new version", same["result"] == "same"
      and c.execute("SELECT COUNT(*) FROM ledger_docs WHERE doc_key = 'JV2611-005'").fetchone()[0] == 1, same)
c.commit()
c.disarm()
c.close()
res = paste(packet([grid_line("880", "883", 1000, BANK, cr=4000), grid_line("880", "884", 2000, "520-1000", dr=4000)]))
check("pasting the same lines again adds no version either", q("SELECT COUNT(*) AS n FROM ledger_docs WHERE doc_key = 'JV2611-005'")[0]["n"] == 1)

# ---------- 5. checks: totals, payments, sub-ledgers ----------
c = conn("test: chart")
for code, name, typ, special in (("300-0000", "TRADE DEBTORS", "asset", "debtor_control"), ("305-0000", "OTHER DEBTORS", "asset", None),
                                 ("400-0000", "TRADE CREDITORS", "liability", "creditor_control"), (BANK, "BANK-EXAMPLE", "asset", "bank"),
                                 ("500-1000", "EXAMPLE EXPENSE", "expense", None), ("500-2000", "EXAMPLE SALES", "income", None),
                                 ("520-1000", "EXAMPLE FEES", "expense", None), ("306-1002", "EXAMPLE ACCRUAL", "liability", None)):
    c.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EID, code, name, typ, special))
c.execute("INSERT INTO parties (entity_id, kind, name, sql_code, gl_code) VALUES (?, 'customer', 'Example Customer Ltd', '300-A0003', '305-0000')", (EID,))
c.execute("INSERT INTO parties (entity_id, kind, name, sql_code) VALUES (?, 'supplier', 'Example Print Sdn Bhd', '400-S0001')", (EID,))
c.commit()
check("a customer's code maps to the party's control account (its GL code)", ledger.control_of(c, EID, "300-a0003") == "305-0000")
check("a supplier's code with no GL code maps by prefix to the creditor control", ledger.control_of(c, EID, "400-S0001") == "400-0000")
check("a code by prefix only maps to the debtor control", ledger.control_of(c, EID, "300-Z9999") == "300-0000")
check("a chart code maps to itself, an unknown one to nothing", ledger.control_of(c, EID, "500-1000") == "500-1000"
      and ledger.control_of(c, EID, "999-X001") is None)
check("a ledger footer's Add Code counts as a control", ledger.control_of(c, EXB, "300-A0001", footer_codes=["300-0000"]) == "300-0000")
names = ledger.account_names(c, EID, ["300-A0003", "500-1000", "777-0001"], printed={"777-0001": "PRINTED NAME"})
check("account names come from the chart, then the parties, then the printed name",
      names["500-1000"] == {"name": "EXAMPLE EXPENSE", "name_from": "chart", "control": "500-1000"}
      and names["300-A0003"]["name"] == "Example Customer Ltd · sub-ledger of 305-0000" and names["300-A0003"]["name_from"] == "party"
      and names["777-0001"]["name_from"] == "printed", names)
check("bank codes come from the bank account and the chart", ledger.bank_codes(c, EID) == {BANK}, ledger.bank_codes(c, EID))

imp = an_import(c, EID, "nov.xlsx")
entry(c, imp, EID, "PV2611-001", "2026-11-03", 300, "payment", "PV", direction="out")
entry(c, imp, EID, "PV2611-001", "2026-11-03", 200, "payment", "PV", direction="out", desc="EXAMPLE SECOND ROW")
entry(c, imp, EID, "IV2611-001", "2026-11-04", 1000, "invoice", "IV", code="300-A0003")
entry(c, imp, EID, "PV2611-002", "2026-11-05", 800, "payment", "PV", direction="out")
imp_b = an_import(c, EID, "nov-again.xlsx")
entry(c, imp_b, EID, "PV2611-002", "2026-11-05", 900, "payment", "PV", direction="out")
entry(c, imp, EID, "PV2611-009", "2026-11-20", 50, "payment", "PV", direction="out")  # not in the journal
bn = jot_batch(c, EID, ("2026-11-01", "2026-11-30"), "printed", books=("bank", "general", "sales"))
for doc in ({"doc_no": "PV2611-001", "doc_date": "2026-11-03", "book": "bank", "lines": [line("400-S0001", dr=500), line(BANK, cr=500)]},
            {"doc_no": "IV2611-001", "doc_date": "2026-11-04", "book": "sales", "lines": [line("300-A0003", dr=1000), line("500-2000", cr=1000)]},
            {"doc_no": "PV2611-002", "doc_date": "2026-11-05", "book": "bank", "lines": [line("520-1000", dr=800), line(BANK, cr=800)]},
            {"doc_no": "PV2611-003", "doc_date": "2026-11-06", "book": "bank", "lines": [line("999-X001", dr=10), line(BANK, cr=11)]}):
    ledger.put_document(c, EID, bn, doc)
c.commit()
chk = ledger.doc_checks(c, EID, ["PV2611-001", "IV2611-001", "PV2611-002", "PV2611-003"])
check("a voucher listed on two rows: the total check sums them", chk["PV2611-001"]["total_ok"] is True
      and chk["PV2611-001"]["rule"] == "bank" and chk["PV2611-001"]["warnings"] == [], chk["PV2611-001"])
check("an invoice is checked on the customer's line", chk["IV2611-001"]["total_ok"] is True and chk["IV2611-001"]["rule"] == "party"
      and not chk["IV2611-001"]["unknown"], chk["IV2611-001"])
w = " ".join(chk["PV2611-002"]["warnings"])
check("lines that match an earlier listing say so", chk["PV2611-002"]["total_ok"] is False and "earlier listing" in w, w)
check("unbalanced lines and unknown codes are warned of", chk["PV2611-003"]["balanced"] is False
      and chk["PV2611-003"]["unknown"] == ["999-X001"] and chk["PV2611-003"]["total_ok"] is None
      and any("don't balance" in x for x in chk["PV2611-003"]["warnings"]), chk["PV2611-003"])
orph = ledger.orphans(c, EID)
check("orphans: in the journal with no listing, and listed but missing from the journal",
      "PV2611-003" in [x["doc_no"] for x in orph["no_listing"]] and [x["doc_no"] for x in orph["not_in_journal"]] == ["PV2611-009"], orph)

ib = an_import(c, EXB, "exb.xlsx")
entry(c, ib, EXB, "PV2611-101", "2026-11-03", 75, "payment", "PV", direction="out")
bb = jot_batch(c, EXB, ("2026-11-01", "2026-11-30"), "printed", books=("bank",))
ledger.put_document(c, EXB, bb, {"doc_no": "PV2611-101", "doc_date": "2026-11-03", "book": "bank",
                                 "lines": [line("520-1000", dr=75), line("310-9000", cr=75)]})
cb = ledger.doc_checks(c, EXB, ["PV2611-101"])["PV2611-101"]
check("a payment with no bank GL code can't be told, and says what to set", cb["total_ok"] is None
      and any("set the bank account's GL code in Setup" in x for x in cb["warnings"])
      and any("chart of accounts in Setup" in x for x in cb["warnings"]), cb)
c.execute("UPDATE accounts SET gl_code = '310-9000' WHERE entity_id = ?", (EXB,))
cb = ledger.doc_checks(c, EXB, ["PV2611-101"])["PV2611-101"]
check("with the bank GL code set, the same payment checks out", cb["total_ok"] is True, cb)
c.commit()
check("the chart's usage counts the account lines on a code",
      ["SQL account lines", 2] in masters.usage(c, "gl_accounts", c.execute("SELECT id FROM gl_accounts WHERE code = '500-2000'").fetchone()[0]))
c.disarm()
c.close()

# ---------- 6. the bank reconciliation ----------
c = conn("test: headerless grid gets its journal")
entry(c, an_import(c, EID), EID, "JV2610-002", "2026-10-07", 700, "journal", "JV", dockey="K2")
c.commit()
check("a headerless pasted grid counts by document key once its journal is listed", book(EID, "2026-10") == (1700.0, 500.0), book(EID, "2026-10"))
check("copy_pasted copies it then, once", ledger.copy_pasted(c, EID) == 1 and ledger.copy_pasted(c, EID) == 0)
c.commit()
check("and it still counts the same from the ledger", book(EID, "2026-10") == (1700.0, 500.0), book(EID, "2026-10"))
entry(c, an_import(c, EID), EID, "JV2610-003", "2026-10-09", 250, "journal", "JV")
bo = jot_batch(c, EID, ("2026-10-01", "2026-10-31"), "printed")
ledger.put_document(c, EID, bo, {"doc_no": "JV2610-003", "doc_date": "2026-10-09", "book": "general",
                                 "lines": [line("520-1000", dr=250), line(BANK, cr=250)]})
c.commit()
check("a journal from the Journal of Transaction with lines on the bank code counts, with nothing pasted",
      book(EID, "2026-10") == (1700.0, 750.0), book(EID, "2026-10"))
move = recon.journal_move(c, EID, "jv2610-003")
check("journal_move finds it by doc no.", move == -250.0, move)
gone = ledger.mark_gone(c, EID, bo, "2026-10-01", "2026-10-31", {"general"}, ["JV2610-002", "JV2610-003"])
c.commit()
check("a journal no longer in SQL stops counting, and isn't read from its pasted lines again",
      [g["doc_no"] for g in gone] == ["JV2610-001"] and book(EID, "2026-10") == (700.0, 750.0)
      and len(q("SELECT * FROM sql_journal_lines WHERE dockey = 'K1'")) == 2, (gone, book(EID, "2026-10")))
ent = c.execute("SELECT * FROM entities WHERE id = ?", (EID,)).fetchone()
acct = recon.cash_book_account(c, EID)
c.execute("INSERT INTO statements (account_id, month, imported_at, reconciled_at, reconciled_how) VALUES (?, '2026-10', ?, ?, 'review')",
          (acct["id"], db.now(), db.now()))
snap = ledger.recon_snapshot(c, ent, ["2026-10", "2026-11"])
back = ledger.put_document(c, EID, jot_batch(c, EID), {"doc_no": "JV2610-001", "doc_date": "2026-10-05", "book": "general",
                                                       "lines": [line(BANK, dr=1000), line("306-1002", cr=1000)]})
moved = ledger.recon_changed(snap, ledger.recon_snapshot(c, ent, ["2026-10", "2026-11"]))
check("back in SQL, it counts again, and the signed-off month it changed is reported", back["result"] == "back"
      and moved == [{"month": "2026-10", "before": {"in": 700.0, "out": 750.0}, "after": {"in": 1700.0, "out": 750.0}}], (back, moved))
c.commit()

# ---------- 7. report checks ----------
oct_lines = q("""SELECT l.account_code AS code, SUM(l.dr_sen) AS dr, SUM(l.cr_sen) AS cr FROM ledger_lines l JOIN ledger_docs d ON d.id = l.doc_id
                 WHERE d.entity_id = ? AND d.state = 'current' AND d.doc_date BETWEEN '2026-10-01' AND '2026-10-31' GROUP BY l.account_code""", (EID,))
led = {"period": ["2026-10-01", "2026-10-31"], "footer": [], "accounts": [
    {"code": x["code"], "name": "", "bf_sen": 0, "virtual": [{"date": "2026-10-31", "doc_no": None, "dr_sen": 99, "cr_sen": 0, "bal_sen": None}],
     "rows": [{"date": "2026-10-15", "doc_no": "X", "dr_sen": x["dr"], "cr_sen": x["cr"], "bal_sen": x["dr"] - x["cr"]}]} for x in oct_lines]}
res = ledger.report_checks(c, EID, None, led, "gl_ledger")
check("a ledger that agrees with the lines gives no warning (PROFIT/(LOSS) and B/F left out)",
      not [x for x in res if x["outcome"] == "warn"] and res[-1]["outcome"] == "ok", res)
led["accounts"][0]["rows"][0]["dr_sen"] += 100
res = ledger.report_checks(c, EID, None, led, "gl_ledger")
check("one that doesn't names the account", [x["subject"] for x in res if x["outcome"] == "warn"] == [led["accounts"][0]["code"]], res)
# The year's first month: Month To Date of a profit and loss account also holds SQL's closing of last year's 1,000.00,
# while Year To Date started again and equals the lines.
closing = {"520-1000": 100000}
tb = {"period": ["2026-10-01", "2026-10-31"], "accounts": [
    {"code": x["code"], "name": "", "open": (closing.get(x["code"], 0), 0), "ptd": (x["dr"], x["cr"] + closing.get(x["code"], 0)),
     "mtd": (x["dr"], x["cr"] + closing.get(x["code"], 0)), "ytd": (x["dr"], x["cr"])} for x in oct_lines]}
res = ledger.report_checks(c, EID, None, tb, "trial_balance", ledger_rep=None)
check("a trial balance in what may be the year's first month skips P&L, and the balance check says why",
      not [x for x in res if x["outcome"] == "warn"] and any(x["outcome"] == "skipped" and "year-end closing" in x["text"] for x in res)
      and any(x["rule"] == "tb_balance" and x["outcome"] == "skipped" for x in res), res)
c.disarm()
c.close()

# ---------- 8. report and listing checks of another company ----------
c = conn("test: another company's chart and lines")
c.execute("UPDATE accounts SET gl_code = ? WHERE entity_id = ?", (BANK, EXR))
for code, name, typ, special in (("300-0000", "TRADE DEBTORS", "asset", "debtor_control"), (BANK, "BANK-EXAMPLE", "asset", "bank"),
                                 ("310-2000", "BANK-EXAMPLE TWO", "asset", "bank"), ("500-2000", "EXAMPLE SALES", "income", None),
                                 ("9S0-T002", "SALARY - EXAMPLE", "expense", None)):
    c.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, ?, ?, ?, ?)", (EXR, code, name, typ, special))
br = jot_batch(c, EXR, ("2026-10-01", "2026-11-30"), "printed", books=("bank", "general", "sales"))
for doc in ({"doc_no": "IV2610-001", "doc_date": "2026-10-08", "book": "sales", "lines": [line("300-A0003", dr=3000), line("500-2000", cr=3000)]},
            {"doc_no": "PV2610-005", "doc_date": "2026-10-05", "book": "bank", "lines": [line("9S0-T002", dr=500), line(BANK, cr=500)]},
            {"doc_no": "PV2611-005", "doc_date": "2026-11-03", "book": "bank", "lines": [line("9S0-T002", dr=600), line(BANK, cr=600)]},
            {"doc_no": "PV2610-050", "doc_date": "2026-10-12", "book": "bank", "lines": [line("310-2000", dr=1000), line(BANK, cr=1000)]},
            {"doc_no": "PV2610-060", "doc_date": "2026-10-15", "book": "bank", "lines": [line("9S0-T002", dr=350), line(BANK, cr=350)]}):
    ledger.put_document(c, EXR, br, doc)
ia = an_import(c, EXR, "pv-a.xlsx")
entry(c, ia, EXR, "PV2610-050", "2026-10-12", 1000, "payment", "PV", direction="out")
entry(c, ia, EXR, "PV2610-060", "2026-10-15", 100, "payment", "PV", direction="out")
entry(c, ia, EXR, "PV2610-060", "2026-10-15", 200, "payment", "PV", direction="out", desc="EXAMPLE SECOND ROW")
entry(c, ia, EXR, "PV2610-070", "2026-10-16", 360, "payment", "PV", direction="out")  # listed on two rows, not in the journal
entry(c, ia, EXR, "PV2610-070", "2026-10-16", 40, "payment", "PV", direction="out", desc="EXAMPLE SECOND ROW")
jv71 = entry(c, ia, EXR, "JV2610-071", "2026-10-17", 75, "journal", "JV")  # a journal SQL's journal lacks
c.execute("UPDATE sql_entries SET status = 'journal' WHERE id = ?", (jv71,))
# The second row of PV2610-060 edited in SQL to 250.00 and fetched again: the unchanged 100.00 row is already
# imported, so it stays with the first import and only the 250.00 row is in the second.
entry(c, an_import(c, EXR, "pv-b.xlsx"), EXR, "PV2610-060", "2026-10-15", 250, "payment", "PV", direction="out", desc="EXAMPLE SECOND ROW")
c.commit()
ck = ledger.doc_checks(c, EXR, ["PV2610-050", "PV2610-060"])
check("a voucher moving money between two of the company's own bank accounts agrees with its listing",
      ck["PV2610-050"]["total_ok"] is True and ck["PV2610-050"]["warnings"] == [], ck["PV2610-050"])
L60 = ledger.listing_of(c, EXR, ["PV2610-060"])["PV2610-060"]
check("a voucher with one of its rows edited in SQL can't be told, rather than totalled from the edited row alone",
      L60["total"] is None and L60["partial"] is True and ck["PV2610-060"]["total_ok"] is None
      and any("only some of this document's rows" in x for x in ck["PV2610-060"]["warnings"]), (L60, ck["PV2610-060"]))
orph = {x["doc_no"]: x for x in ledger.orphans(c, EXR)["not_in_journal"]}
check("a listing entry missing from the journal has all its rows, and only an unlinked voucher can be ignored",
      len(orph["PV2610-070"]["ids"]) == 2 and orph["PV2610-070"]["can_ignore"] is True and orph["JV2610-071"]["can_ignore"] is False, orph)
c.disarm()
c.close()
e = j("post", f"/api/sql/entries/{jv71}", 400, json={"status": "ignored"})
check("ignoring a journal is refused in words", "can't be ignored" in e["error"]
      and q("SELECT status FROM sql_entries WHERE id = ?", (jv71,))[0]["status"] == "journal", e)
got = j("post", "/api/sql/entries/ignore", json={"ids": orph["PV2610-070"]["ids"]})
r = db.connect()
left = [x["doc_no"] for x in ledger.orphans(r, EXR)["not_in_journal"]]
r.close()
check("ignoring every row of an entry listed on two rows takes it off the list", got["ignored"] == 2 and "PV2610-070" not in left, (got, left))
c = conn("test: an ignored journal")
c.execute("UPDATE sql_entries SET status = 'ignored' WHERE id = ?", (jv71,))
c.commit()
c.disarm()
c.close()
j("post", f"/api/sql/entries/{jv71}/unignore")
check("un-ignoring a journal gives it back its own status, not 'unlinked'",
      q("SELECT status FROM sql_entries WHERE id = ?", (jv71,))[0]["status"] == "journal")

c = conn("test: report checks of another company")
# The Level 1 ledger prints a debtor control account with its B/F only: its movements are in the footer (Add Code).
led_ctl = {"period": ["2026-10-01", "2026-10-31"], "footer": [{"op": "add", "code": "300-0000", "dr_sen": 300000, "cr_sen": 0}],
           "accounts": [{"code": "300-0000", "name": "TRADE DEBTORS", "bf_sen": 1000000, "rows": [], "virtual": [], "closing_sen": 1000000}]}
for as_at in ("2026-10-31", "2026-10-14"):
    tb = {"period": ["2026-10-01", as_at], "accounts": [{"code": "300-0000", "name": "TRADE DEBTORS", "open": (1000000, 0),
                                                          "ptd": (300000, 0), "mtd": (300000, 0), "ytd": (1300000, 0)}]}
    res = [x for x in ledger.report_checks(c, EXR, None, tb, "trial_balance", ledger_rep=led_ctl) if x["rule"] == "tb_balance"]
    if as_at == "2026-10-31":
        check("a control account with no ledger rows is compared with its B/F plus the footer on the ledger's last day",
              not [x for x in res if x["outcome"] == "warn"]
              and any(x["outcome"] == "ok" and x["text"].startswith("1 balance-sheet account agrees") for x in res), res)
    else:
        check("and is skipped, saying why, on a day inside the ledger's period", not [x for x in res if x["outcome"] == "warn"]
              and any(x["outcome"] == "skipped" and x["subject"] == "300-0000" and "control account" in x["text"] for x in res), res)

# A financial year starting in October, the trial balance printed over two months: October's Month To Date holds the
# year-end closing of last year's 49,500.00 salary, its Year To Date only October's 500.00.
tb_oct = {"period": ["2026-09-01", "2026-10-14"], "accounts": [
    {"code": "9S0-T002", "name": "SALARY - EXAMPLE", "open": (4950000, 0), "ptd": (50000, 4950000), "mtd": (50000, 4950000), "ytd": (50000, 0)}]}
res = [x for x in ledger.report_checks(c, EXR, None, tb_oct, "trial_balance") if x["rule"] == "tb_mtd"]
check("a closing month printed over two months skips profit and loss Month To Date instead of warning",
      not any(x["subject"] == "9S0-T002" for x in res) and any(x["outcome"] == "skipped" and "year-end closing" in x["text"] for x in res), res)
# November printed for the month alone: Month To Date equals Period To Date, Year To Date holds October too.
tb_nov = {"period": ["2026-11-01", "2026-11-14"], "accounts": [
    {"code": "9S0-T002", "name": "SALARY - EXAMPLE", "open": (50000, 0), "ptd": (60000, 0), "mtd": (60000, 0), "ytd": (110000, 0)}]}
res = [x for x in ledger.report_checks(c, EXR, None, tb_nov, "trial_balance") if x["rule"] == "tb_mtd"]
check("a later month printed for one month compares profit and loss Month To Date",
      not any(x["outcome"] == "skipped" for x in res) and not any(x["subject"] == "9S0-T002" for x in res)
      and any(x["outcome"] == "ok" for x in res), res)

# A ledger from September, with the journals read covering October on: its footer's Add Code holds September too.
led_wide = {"period": ["2026-09-01", "2026-10-31"], "footer": [{"op": "add", "code": "300-0000", "dr_sen": 350000, "cr_sen": 0}],
            "accounts": [{"code": "300-0000", "name": "TRADE DEBTORS", "bf_sen": 0, "rows": [], "virtual": []},
                         {"code": "500-2000", "name": "EXAMPLE SALES", "bf_sen": 0, "virtual": [], "rows": [
                             {"date": "2026-09-10", "doc_no": "IV2609-001", "dr_sen": 0, "cr_sen": 50000, "bal_sen": -50000},
                             {"date": "2026-10-08", "doc_no": "IV2610-001", "dr_sen": 0, "cr_sen": 300000, "bal_sen": -350000}]}]}
res = ledger.report_checks(c, EXR, None, led_wide, "gl_ledger")
check("a ledger wider than the journals read doesn't compare the footer's control accounts, and says why",
      not [x for x in res if x["outcome"] == "warn" and x["subject"] in ("300-0000", "500-2000")]
      and any(x["outcome"] == "skipped" and x["subject"] == "300-0000" for x in res) and any(x["outcome"] == "info" for x in res), res)
c.disarm()
c.close()

# ---------- 9. the signed-off months a fetch changes, by the listing's date ----------
c = conn("test: a signed-off October")
ent_t = c.execute("SELECT * FROM entities WHERE id = ?", (EXT,)).fetchone()
c.execute("INSERT INTO statements (account_id, month, imported_at, reconciled_at, reconciled_how) VALUES (?, '2026-10', ?, ?, 'review')",
          (recon.cash_book_account(c, EXT)["id"], db.now(), db.now()))
li = an_import(c, EXT, "jv-listing.xlsx")
entry(c, li, EXT, "JV2610-009", "2026-10-31", 300, "journal", "JV")
entry(c, li, EXT, "JV2610-010", "2026-10-20", 500, "journal", "JV")
c.commit()
c.disarm()
c.close()


def fetched(name, period, docs):
    return {"kind": "journal", "name": name, "month": period[0][:7], "saved": name, "data": f"made-up {name}".encode(),
            "rep": {"title": "GL Journal of Transaction", "period": list(period), "period_source": "printed",
                    "sections": [{"label": "General Journal Journal", "book": "general"}],
                    "docs": [{"doc_no": n, "date": d, "book": "general", "book_label": "General Journal Journal", "lines": ls}
                             for n, d, ls in docs]}}


def fetch(gl):
    con = conn("test: a fetch")
    try:
        pre = ledger.preview(con, EXT, gl)
        got = ledger.apply_fetch(con, ent_t, an_import(con, EXT, "fetch.xlsx"), gl)
        con.commit()
        return pre, got
    finally:
        con.disarm()
        con.close()


JV10 = ("JV2610-010", "2026-10-20", [line(BANK, dr=500), line("306-1002", cr=500)])
JV9 = ("JV2610-009", "2026-11-02", [line(BANK, dr=300), line("306-1002", cr=300)])  # re-dated in SQL to 02/11
pre, got = fetch([fetched("jot-oct.xlsx", ("2026-10-01", "2026-10-31"), [JV10])])
check("a journal starting to count in signed-off October is reported", book(EXT, "2026-10") == (500.0, 0.0)
      and [x["month"] for x in got["recon_changed"]] == ["2026-10"], (book(EXT, "2026-10"), got["recon_changed"]))
pre, got = fetch([fetched("jot-nov.xlsx", ("2026-11-01", "2026-11-30"), [JV9])])
cnt = {x["doc_no"]: x for x in pre["counting"]["journals"]}
check("a journal SQL re-dated into November changes signed-off October, where its listing row is, and that is reported",
      book(EXT, "2026-10") == (800.0, 0.0) and [x["month"] for x in got["recon_changed"]] == ["2026-10"],
      (book(EXT, "2026-10"), got["recon_changed"]))
check("the preview names October, its listing's month, as signed off", cnt["JV2610-009"]["month"] == "2026-10"
      and cnt["JV2610-009"]["signed_off"] is True and pre["counting"]["signed_off"] == ["2026-10"], pre["counting"])
pre, got = fetch([fetched("jot-both.xlsx", ("2026-10-01", "2026-11-30"), [JV9])])
gone = {x["doc_no"]: x for x in pre["gone"]}
check("a journal deleted in SQL stops counting in signed-off October, and that is reported",
      book(EXT, "2026-10") == (300.0, 0.0) and [x["month"] for x in got["recon_changed"]] == ["2026-10"],
      (book(EXT, "2026-10"), got["recon_changed"]))
check("the preview flags the deleted journal's signed-off month", gone["JV2610-010"]["signed_off"] is True
      and gone["JV2610-010"]["month"] == "2026-10" and pre["counting"]["signed_off"] == ["2026-10"], (pre["gone"], pre["counting"]))

# ---------- 10. the ledger's guard put back at start-up ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DROP TRIGGER ledger_guard_here")
raw.commit()
raw.close()
r = db.connect()
v = audit.verify(r)
r.close()
check("the audit check notices the ledger's guard is missing", not v["ok"] and any("kept in SQL" in p for p in v["problems"]), v)
trail = db.init()
check("start-up puts it back and records it", trail and "ledger_guard_here" in trail["triggers_repaired"]
      and q("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name = 'ledger_guard_here'"), trail)
trail = db.init()
check("and finds nothing to put back the next time", trail and "ledger_guard_here" not in trail["triggers_repaired"], trail)

r = db.connect()
v = audit.verify(r)
r.close()
check("the audit trail still checks out at the end", v["ok"], v)
print("\nAll checks passed. Records folder used:", tmp)
