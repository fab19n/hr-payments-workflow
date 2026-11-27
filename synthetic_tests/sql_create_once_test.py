"""One SQL entry makes one payment, on made-up records only.

Create payment on the SQL page can be sent twice (a second click while the list is being read again), so the server
refuses it for an entry already linked to a payment, and the refusal changes nothing. The link is what counts, not the
status: a journal keeps its status when linked, as a customer invoice does. After the entry is unlinked, or its payment
removed, Create payment works again.

Run: .venv\\Scripts\\python -m synthetic_tests.sql_create_once_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-create-once-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
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


def post(path, body):
    return c.post(BASE + path, headers=H, json=body)


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


EID = q("SELECT id FROM entities WHERE code = 'EXH'")[0]["id"]
BANK_NAME, BANK_CODE, MONTH = "BANK-EXAMPLE 0001 0002 0003", "310-1000", "2026-10"


def packet(rows):
    """A DATAPACKET as SQL Account copies a grid: one ROW per dictionary."""
    def attrs(r):
        return " ".join('%s="%s"' % (k, v) for k, v in r.items())
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % attrs(r) for r in rows) + "</ROWDATA></DATAPACKET>")


def voucher(no, key, amount, kind="PV", desc="EXAMPLE SUPPLIER LTD"):
    money_in = kind == "OR"
    return {"DOCKEY": key, "DOCNO": no, "DOCTYPE": kind, "DOCDATE": "20261006", "DESCRIPTION": desc, "DOCAMT": f"{amount:.2f}",
            "CANCELLED": "FALSE", "PAYMENTMETHODDESC": BANK_NAME, "DR": f"{amount if money_in else 0:.2f}",
            "CR": f"{0 if money_in else amount:.2f}"}


def line(key, dtl, seq, code, dr=0, cr=0):
    return {"DTLKEY": dtl, "DOCKEY": key, "SEQ": seq, "AREA": "----", "AGENT": "----", "PROJECT": "PV-0000-001", "CODE": code,
            "DESCRIPTION": "EXAMPLE LINE", "TAX": "", "LOCALTAXAMT": "0.00", "TAXINCLUSIVE": "FALSE", "DR": f"{dr:.2f}",
            "CR": f"{cr:.2f}", "LOCALDR": f"{dr:.2f}", "LOCALCR": f"{cr:.2f}", "CHANGED": "FALSE"}


def paste(text):
    """Pastes the text on the SQL page and imports it."""
    pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": text})
    if "journal_lines" in pre:
        return j("post", "/api/sql/apply", json={"token": pre["token"]})
    return j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"],
                                             "links": {}})


def row(no):
    return q("SELECT * FROM sql_entries WHERE doc_no = ?", (no,))[0]


def eid_of(no):
    return row(no)["id"]


def records():
    """Everything a refused Create payment must leave alone."""
    return {t: q(f"SELECT * FROM {t} ORDER BY 1") for t in ("payments", "sql_entries", "activity", "statement_lines")}


def create(no, body=None):
    return post(f"/api/sql/entries/{eid_of(no)}", {"create_payment": body or {}})


def refused_again(what, no, body=None):
    """Create payment on an entry already linked is refused, says why, and changes nothing."""
    before, linked = records(), row(no)["payment_id"]
    r = create(no, body)
    said = (r.get_json() or {}).get("error", "")
    after = records()
    check(f"{what}: a second Create payment is refused", r.status_code == 400, (r.status_code, r.data[:300]))
    check(f"{what}: it says the entry is linked already, and to unlink it first",
          said.startswith(f"{no} is already linked to a payment") and "unlink it first" in said.lower(), said)
    check(f"{what}: nothing changed", after == before and row(no)["payment_id"] == linked,
          {t: (before[t], after[t]) for t in before if before[t] != after[t]})


def made_for(no):
    return q("SELECT * FROM payments WHERE sql_ref = ?", (no,))


con = db.connect()
con.arm("user", "test: the chart of accounts")
con.execute("INSERT INTO gl_accounts (entity_id, code, name) VALUES (?, ?, ?)", (EID, BANK_CODE, BANK_NAME))
con.commit()
con.close()

paste(packet([
    voucher("PV2610-001", "301", 120),
    voucher("OR2610-001", "302", 450, kind="OR", desc="EXAMPLE CUSTOMER LTD"),
    voucher("PV2610-002", "303", 80, desc="EXAMPLE CLEANER"),
    voucher("PV2610-003", "304", 60, desc="EXAMPLE COURIER"),
    {"DOCTYPE": "JE", "DOCKEY": "334", "DOCNO": "JV2610-001", "DOCDATE": "20261026", "POSTDATE": "20261026",
     "JOURNAL": "GENERAL", "DESCRIPTION": "EXAMPLE JOURNAL", "TOTALDR": "900.00", "TOTALCR": "900.00"},
]))
paste(packet([line("334", "335", 1000, BANK_CODE, cr=900), line("334", "336", 2000, "610-1000", dr=900)]))

# ---------- a voucher, money out and money in ----------
check("a voucher's first Create payment is saved", create("PV2610-001").status_code == 200)
check("it made one payment and linked the voucher to it", len(made_for("PV2610-001")) == 1
      and (row("PV2610-001")["status"], row("PV2610-001")["payment_id"]) == ("linked", made_for("PV2610-001")[0]["id"]),
      (made_for("PV2610-001"), row("PV2610-001")))
refused_again("a payment voucher", "PV2610-001")
refused_again("a payment voucher sent with another type", "PV2610-001", {"category": "utilities"})
check("a receipt's first Create payment is saved", create("OR2610-001").status_code == 200)
refused_again("a receipt", "OR2610-001")

# ---------- a journal, which keeps its status when linked ----------
check("a bank-moving journal's first Create payment is saved", create("JV2610-001").status_code == 200)
check("the journal stays a journal, linked", (row("JV2610-001")["status"], bool(row("JV2610-001")["payment_id"])) == ("journal", True),
      row("JV2610-001"))
refused_again("a journal", "JV2610-001")

# ---------- linked in other ways: by hand, and by Create payments for all ----------
j("post", "/api/payments", json={"entity_id": EID, "month": MONTH, "description": "Example cleaning bill", "category": "other",
                                 "amount": 80, "due_date": "2026-10-06"})
by_hand = q("SELECT id FROM payments WHERE description = 'Example cleaning bill'")[0]["id"]
j("post", f"/api/sql/entries/{eid_of('PV2610-002')}", json={"payment_id": by_hand})
refused_again("a voucher linked by hand", "PV2610-002")
res = j("post", "/api/sql/entries/create-all", json={"entity_id": EID})
check("Create payments for all adds the one voucher left", res["created"] == 1 and len(made_for("PV2610-003")) == 1, res)
refused_again("a voucher added by Create payments for all", "PV2610-003")
res = j("post", "/api/sql/entries/create-all", json={"entity_id": EID})
check("and pressed again, it adds nothing", res["created"] == 0 and res["linked"] == 0 and len(made_for("PV2610-003")) == 1, res)

# ---------- a customer invoice linked to its receipt ----------
receipt = made_for("OR2610-001")[0]["id"]
with sqlite3.connect(config.DB_PATH) as raw:
    raw.execute("INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, direction, doc_type, kind, status) "
                "SELECT MAX(id), ?, 'IV2610-001', '2026-10-02', 'EXAMPLE CUSTOMER LTD', 450, 'in', 'IV', 'invoice', 'invoice' "
                "FROM sql_imports", (EID,))
j("post", f"/api/sql/entries/{eid_of('IV2610-001')}", json={"payment_id": receipt})
refused_again("a customer invoice linked to its receipt", "IV2610-001")
check("the invoice stays an invoice", row("IV2610-001")["status"] == "invoice", row("IV2610-001"))

# ---------- unlinked, Create payment works again ----------
for no, free in (("PV2610-001", "unlinked"), ("JV2610-001", "journal")):
    first = row(no)["payment_id"]
    u = j("post", f"/api/sql/entries/{eid_of(no)}/unlink", json={})
    check(f"{no} unlinked: the payment made from it is removed", u["removed"] and not q("SELECT 1 FROM payments WHERE id = ?", (first,))
          and (row(no)["status"], row(no)["payment_id"]) == (free, None), (u, row(no)))
    check(f"{no} unlinked: Create payment works again", create(no).status_code == 200 and len(made_for(no)) == 1
          and row(no)["payment_id"] == made_for(no)[0]["id"], (made_for(no), row(no)))
    refused_again(f"{no} created again", no)

# A payment with something typed on it stays when unlinked; the voucher is free, so Create payment makes another.
kept = row("PV2610-001")["payment_id"]
j("patch", f"/api/payments/{kept}", json={"notes": "Example note"})
u = j("post", f"/api/sql/entries/{eid_of('PV2610-001')}/unlink", json={})
check("unlinked from a payment that stays, Create payment works again", not u["removed"] and create("PV2610-001").status_code == 200
      and row("PV2610-001")["payment_id"] not in (None, kept) and q("SELECT 1 FROM payments WHERE id = ?", (kept,)), (u, row("PV2610-001")))

# ---------- the linked payment removed, Create payment works again ----------
for no in ("OR2610-001", "JV2610-001", "PV2610-003"):
    first = row(no)["payment_id"]
    j("delete", f"/api/payments/{first}")
    check(f"{no}'s payment removed: the entry is free", row(no)["payment_id"] is None, row(no))
    check(f"{no}'s payment removed: Create payment works again", create(no).status_code == 200 and row(no)["payment_id"] is not None
          and len(q("SELECT 1 FROM payments WHERE id = ?", (row(no)["payment_id"],))) == 1, row(no))
    refused_again(f"{no} after its payment was removed and made again", no)

# A link to a payment that isn't there (the app's own connections can't leave one; a file edited by hand could) doesn't
# stop Create payment.
with sqlite3.connect(config.DB_PATH) as raw:
    raw.execute("UPDATE sql_entries SET payment_id = 999999 WHERE id = ?", (eid_of("PV2610-002"),))
r = create("PV2610-002")
now_on = q("SELECT id FROM payments WHERE id = ?", (row("PV2610-002")["payment_id"],))
check("a link to a payment that isn't there doesn't stop Create payment", r.status_code == 200
      and len(now_on) == 1 and now_on[0]["id"] != by_hand, (r.status_code, r.data[:300], row("PV2610-002")))

print("all passed")
