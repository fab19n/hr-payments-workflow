r"""A voucher number typed in a payment's SQL ref box, on made-up records only.

A payment's SQL ref box names a voucher that is not linked yet. The SQL import preview must offer that voucher for that
payment, in the same way for a company that tracks every month and for one that started tracking later (the
before-tracking rule reads the payment's month and dates, so the lookup has to carry them). Before this was fixed the
preview stopped with an error as soon as one payment had a typed ref.

Run: .venv\Scripts\python -m synthetic_tests.sql_typed_ref_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-typed-ref-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXR", "name": "Example Typed Ref Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-777"}]},
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
EID = q("SELECT id FROM entities WHERE code = 'EXR'")[0]["id"]
AID = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]


def listing(*rows):
    """A SQL Account listing in the XML form the preview reads: (doc no, date, description, amount) per voucher."""
    out = ['<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS>'
           '<FIELD attrname="DOCNO" fieldtype="string.uni"/></FIELDS><PARAMS/></METADATA><ROWDATA>']
    for no, d, desc, amt in rows:
        out.append(f'<ROW DOCNO="{no}" DOCTYPE="{no[:2]}" DOCDATE="{d}" DESCRIPTION="{desc}" DOCAMT="{amt:.2f}" '
                   f'CANCELLED="FALSE" DR="0.00" CR="{amt:.2f}"/>')
    return "".join(out) + "</ROWDATA></DATAPACKET>"


def preview(*rows):
    r = c.post(BASE + "/api/sql/preview", headers=H, json={"entity_id": EID, "text": listing(*rows)})
    assert r.status_code == 200, (r.status_code, r.data[:300])
    return {x["doc_no"]: x for x in r.get_json()["records"]}


with sqlite3.connect(config.DB_PATH) as con:
    pid = con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, sql_ref,
                         created_at) VALUES (?, '2026-11', ?, 'other', 'Water bill', 88.40, '2026-11-06', 'PV2611-001', ?)""",
                      (EID, AID, db.now())).lastrowid

recs = preview(("PV2611-001", "20261106", "Some other words entirely", 99.90))
check("the preview opens with a typed ref on a payment", "PV2611-001" in recs)
check("the voucher goes to the payment whose ref box names it", recs["PV2611-001"]["payment_id"] == pid, recs["PV2611-001"])

with db.connect() as con:
    row = sqlimport.payments_by_ref(con, EID)["PV2611-001"]
    check("the lookup carries the payment's month and dates", all(k in row.keys() for k in ("month", "due_date", "paid_date")))

print("all checks passed")
