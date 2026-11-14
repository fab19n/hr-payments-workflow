"""Received e-Invoices matched by amount, on made-up records only.

A supplier's e-Invoice carries the supplier's number, while the company pays it by its own voucher, often inside a staff
claim paying several receipts, or one voucher paying two of a supplier's invoices. On real books most received
e-Invoices were therefore 'not found' though booked. hrp/myinvois._by_amount, the last resort after the supplier's
number and its TIN, takes: one voucher of the same amount dated near it ('amount'); else the one document with a line
of that amount ('line'); else several e-Invoices of one supplier paid together by one voucher ('sum'), the group of
one billing period (closest together) winning when a monthly bill of the same amount makes another group fit too.

Run: .venv\\Scripts\\python -m synthetic_tests.myinvois_amount_test
"""
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-myinvois-amount-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger, myinvois  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Ltd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]}]}),
    encoding="utf-8")


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    print(f"PASS {name}")


db.init()
con = db.connect()
con.arm("user", "test: made-up books")
EID = con.execute("SELECT id FROM entities WHERE code = 'EXH'").fetchone()[0]
con.execute("UPDATE accounts SET gl_code = '310-1000' WHERE entity_id = ?", (EID,))
IMP = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'x.xlsx', ?, 0, 0)",
                  (EID, db.now())).lastrowid
JB = ledger.new_batch(con, EID, origin="sql", report="journal", sql_import_id=IMP, file_name="jot.xlsx",
                      period_from="2026-09-01", period_to="2026-12-31", period_source="printed",
                      sections=[{"label": "Bank Journal", "book": "bank"}])
ids = {}


def voucher(no, day, amount, lines=None):
    """A payment voucher in the listing, and its lines in the journal (by default one expense line and the bank)."""
    ids[no] = con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, amount, direction,
                             doc_type, kind, status) VALUES (?, ?, ?, ?, 'MADE UP', ?, 'out', 'PV', 'payment', 'unlinked')""",
                          (IMP, EID, no, day, amount)).lastrowid
    lines = lines or [("900-P001", amount)]
    total = round(sum(a for _, a in lines), 2)
    ledger.put_document(con, EID, JB, {"doc_no": no, "doc_date": day, "book": "bank", "lines":
                        [{"code": c, "dr_sen": round(a * 100), "cr_sen": 0} for c, a in lines]
                        + [{"code": "310-1000", "dr_sen": 0, "cr_sen": round(total * 100)}]})


def received(n, no, day, amount, tin="C00000000020"):
    return {"id": n, "doc_no": no, "issued_at": f"{day} 10:00:00", "received_at": f"{day} 10:00:00", "total_sen": round(amount * 100),
            "currency": "MYR", "type": "Invoice", "supplier_tin": tin}


voucher("PV2611-001", "2026-11-05", 709.20)                                   # an electricity bill, paid in November
voucher("PV2610-021", "2026-10-19", 9200.00, [("613-0000", 4960.00), ("200-C021", 3099.00), ("900-S004", 1141.00)])  # a claim
voucher("PV2610-004", "2026-10-06", 136.09)                                   # September's two copier invoices
voucher("PV2611-003", "2026-11-05", 180.16)                                   # October's two copier invoices
voucher("PV2611-007", "2026-11-06", 50.00)
voucher("PV2611-008", "2026-11-07", 50.00)                                    # two vouchers of the same amount
con.commit()

purchases = [dict(r) for r in con.execute("SELECT * FROM sql_entries WHERE entity_id = ?", (EID,))]
rest = [received(1, "ELEC-1", "2026-10-15", 709.20, "C00000000030"),
        received(2, "LAPTOP-1", "2026-10-07", 3099.00, "C00000000040"),
        received(3, "TCG-0924", "2026-09-24", 93.28), received(4, "TCG-0930", "2026-09-30", 42.81),
        received(5, "TCG-1027", "2026-10-27", 93.28), received(6, "TCG-1029", "2026-10-29", 86.88),
        received(7, "TWO-50", "2026-11-04", 50.00, "C00000000050"),
        received(8, "NOWHERE", "2026-10-06", 1220.00, "C00000000060")]
got = {}
myinvois._by_amount(con, EID, rest, purchases, set(), lambda d, e, how: got.__setitem__(d["doc_no"], (e, how)))
name = {v: k for k, v in ids.items()}
seen = {k: (name.get(e), how) for k, (e, how) in got.items()}
check("a bill paid by the company's own voucher of the same amount, dated after it, is matched by amount",
      seen["ELEC-1"] == ("PV2611-001", "amount"), str(seen))
check("a receipt paid inside a staff claim is matched by the claim's line of that amount",
      seen["LAPTOP-1"] == ("PV2610-021", "line"), str(seen))
check("two invoices of one supplier paid by one voucher are matched together, each billing period to its own voucher",
      seen["TCG-0924"] == seen["TCG-0930"] == ("PV2610-004", "sum") and seen["TCG-1027"] == seen["TCG-1029"] == ("PV2611-003", "sum"),
      str(seen))
check("two vouchers of the same amount: neither is guessed", seen["TWO-50"] == (None, None), str(seen))
check("an e-Invoice no voucher or line fits stays unmatched, for the owner to check", seen["NOWHERE"] == (None, None), str(seen))

# A tie between two groups of the same billing period's closeness leaves the voucher unmatched.
rest2 = [received(11, "A-1", "2026-10-01", 10.00, "C00000000070"), received(12, "A-2", "2026-10-11", 20.00, "C00000000070"),
         received(13, "A-3", "2026-10-21", 10.00, "C00000000070")]
voucher("PV2610-090", "2026-10-25", 30.00)
con.commit()
purchases = [dict(r) for r in con.execute("SELECT * FROM sql_entries WHERE entity_id = ?", (EID,))]
got2 = {}
myinvois._by_amount(con, EID, rest2, purchases, set(), lambda d, e, how: got2.__setitem__(d["doc_no"], (e, how)))
check("two equally close groups for one voucher: neither is taken", all(v == (None, None) for v in got2.values()), str(got2))
# A voucher whose supplier is known to have another TIN never takes the e-Invoice by its amount.
voucher("PV2612-001", "2026-12-03", 77.00)
con.commit()
purchases = [dict(r) for r in con.execute("SELECT * FROM sql_entries WHERE entity_id = ?", (EID,))]
other = lambda s: "C00000000999" if s["doc_no"] == "PV2612-001" else None
got3 = {}
myinvois._by_amount(con, EID, [received(21, "B-1", "2026-12-01", 77.00, "C00000000080")], purchases, set(),
                    lambda d, e, how: got3.__setitem__(d["doc_no"], (e, how)), other)
check("a voucher whose supplier has another TIN is never matched by amount", got3["B-1"] == (None, None), str(got3))
con.disarm()
con.close()
print("All MyInvois amount checks passed.")
