r"""Slice 5: what each SQL document is called on the SQL import page, on made-up records only.

Before slice 5 every invoice the SQL page showed was a "Customer invoice": sqlimport filed supplier invoices, debit notes
and credit notes (PI, SD, SC) under the same kind as a customer's, and the page named the kind, not the document. Now the
server names each document by its type (sqlimport.doc_label) and sends that name with the preview's rows and with
Journals and invoices, so a supplier's invoice is never shown as a customer's. This test fails on the code before slice 5
(there is no doc_label, and neither list carries a label).

Run: .venv\Scripts\python -m synthetic_tests.sql_doc_labels_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-sql-doc-labels-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_source  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXL", "name": "Example Labels Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-931"}]},
]}), encoding="utf-8")

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:600])


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


EID = q("SELECT id FROM entities WHERE code = 'EXL'")[0]["id"]

# ---------- the names, by document type ----------
want = {"PI": "Supplier invoice", "SD": "Supplier debit note", "SC": "Supplier credit note", "IV": "Customer invoice",
        "DN": "Customer debit note", "CN": "Customer credit note", "JV": "Journal"}
got = {t: getattr(sqlimport, "doc_label", lambda *a: None)(t, "journal" if t == "JV" else "invoice") for t in want}
check("each document type has its own name: a supplier's documents are named as a supplier's", got == want, got)
label = getattr(sqlimport, "doc_label", None)
check("a voucher has no document name (the page shows its payment instead), and a type not listed is named by its kind",
      label is not None and label("PV", "payment") == "" and label("XX", "invoice") == "Invoice" and label("", "journal") == "Journal"
      and label("pi", "invoice") == "Supplier invoice")


# ---------- the preview of a pasted listing ----------
def packet(rows):
    return ('<?xml version="1.0" standalone="yes"?><DATAPACKET Version="2.0"><METADATA><FIELDS/><PARAMS/></METADATA><ROWDATA>'
            + "".join("<ROW %s/>" % " ".join('%s="%s"' % kv for kv in r.items()) for r in rows) + "</ROWDATA></DATAPACKET>")


def doc(no, kind, amount, desc, code):
    return {"DOCNO": no, "DOCTYPE": kind, "DOCDATE": "20261020", "DESCRIPTION": desc, "CODE": code, "DOCAMT": f"{amount:.2f}", "CANCELLED": "FALSE"}


ROWS = [doc("PI2610-101", "PI", 1200.00, "EXAMPLE SUPPLIER - CLEANING OCTOBER", "400-X001"),
        doc("SD2610-102", "SD", 60.00, "EXAMPLE SUPPLIER - EXTRA VISIT", "400-X001"),
        doc("SC2610-103", "SC", 25.00, "EXAMPLE SUPPLIER - DISCOUNT", "400-X001"),
        doc("IV2610-104", "IV", 900.00, "EXAMPLE TENANT - RENT OCTOBER", "300-X002"),
        {**doc("JV2610-105", "JV", 300.00, "EXAMPLE ACCRUAL OCTOBER", ""), "CODE": ""},
        {**doc("PV2610-106", "PV", 84.30, "EXAMPLE WATER - OCTOBER", "400-X003"), "DR": "0.00", "CR": "84.30"}]
pre = j("post", "/api/sql/preview", json={"entity_id": EID, "text": packet(ROWS)})
recs = {r["doc_no"]: r for r in pre["records"]}
check("the preview reads every document", set(recs) == {r["DOCNO"] for r in ROWS}, sorted(recs))
check("the preview names each document by its type, so a supplier invoice is not a customer invoice",
      {n: r.get("label") for n, r in recs.items()} == {"PI2610-101": "Supplier invoice", "SD2610-102": "Supplier debit note",
                                                       "SC2610-103": "Supplier credit note", "IV2610-104": "Customer invoice",
                                                       "JV2610-105": "Journal", "PV2610-106": ""},
      {n: r.get("label") for n, r in recs.items()})
check("...and the supplier's documents are still kept as invoices (only their name changed)",
      {recs[n]["kind"] for n in ("PI2610-101", "SD2610-102", "SC2610-103")} == {"invoice"})

# ---------- Journals and invoices, after the import ----------
res = j("post", "/api/sql/apply", json={"token": pre["token"], "header_row": pre["header_row"], "mapping": pre["mapping"], "links": {}})
check("the import keeps all six", res["added"] == 6, res)
d = j("get", f"/api/sql/entries?entity={EID}")
docs = {x["doc_no"]: x for x in d["documents"]}
check("Journals and invoices lists the invoices and the journal, each with its name",
      {n: x.get("label") for n, x in docs.items()} == {"PI2610-101": "Supplier invoice", "SD2610-102": "Supplier debit note",
                                                      "SC2610-103": "Supplier credit note", "IV2610-104": "Customer invoice", "JV2610-105": "Journal"},
      {n: x.get("label") for n, x in docs.items()})
check("no supplier document is called a customer invoice anywhere on the page's data",
      not [n for n, x in docs.items() if x["doc_type"] in sqlimport.PURCHASE_DOCS and "Customer" in (x.get("label") or "")])

# ---------- the page uses the server's name ----------
js = app_source()
check("the preview's 'kept on file' pill takes the document's name from the server, not one name for every invoice",
      'kinds = { journal: "Journal", invoice: "Customer invoice" }' not in js and '${esc(r.label || (r.kind === "journal" ? "Journal" : "Invoice"))}, kept on file' in js)
check("Journals and invoices shows a supplier's document's name under its description", 'x.kind === "invoice" && x.doc_type !== "IV" ? x.label' in js)

if failures:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    sys.exit(1)
print("\nsql_doc_labels_test: all passed")
