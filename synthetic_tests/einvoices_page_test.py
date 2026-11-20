r"""Slice 6: Accounting › e-Invoices, built to MyInvois.dc.html (and the print notes InvoicePdf.dc.html draws), on made-up
records only.

The server part runs the app on a temporary records folder (Flask's test client). A company Kept in SQL Account has SQL
documents fetched (customer invoices in September, October and November, a credit note whose account lines were never
fetched, a supplier's invoice, a payment voucher with a self-billed e-Invoice in US dollars, a voucher that pays a
supplier's e-Invoice) and a copy of SQL's MyInvois Transaction screen read (issued, self-billed and received
e-Invoices, one issued with no SQL document, one received that SQL's books don't have). GET /api/einvoices puts them in
the page's three lists, and GET /api/export/einvoices.xlsx gives the same lists as an Excel file (both new in slice 6:
the route answers 404 on the code before it). A company kept here, and one with nothing fetched, are there too.

The page part runs the page script in Node against a small stand-in for the page (an element per id), with the server's
answers above, and checks the board's states and wording: the head and its intro; where the e-Invoices come from (the
copy read, in one line, with its times written "1 Oct 2026, 11:19"; and no copy read yet); the Issued, Received and
Self-billed tabs with their counts, the arrow keys, Home and End, and the address that follows the tab; the month the
page opens on (the month being worked, not the newest); the Print column with each document's print note beside its
PDF (opened, and closed with Escape; a document that can't be printed says why); All of the month (the zip made, saved,
or refused in place; no button for all months or an empty month); the print settings still missing; the e-Invoices
received but not found in SQL's books; Excel; many rows (Showing 25 of 30, Show 5 more); No e-Invoices yet; the error
state; the Kept here company ("Submission method not decided yet"); and that the SQL import page no longer carries the
e-Invoices card or its print bar.

Run: .venv\Scripts\python -m synthetic_tests.einvoices_page_test
"""
import copy
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-einvoices-page-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, ledger  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

from openpyxl import load_workbook  # noqa: E402

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXV", "name": "Example Vale Sdn Bhd", "accounts": [{"label": "Operating account", "bank": "Example Bank", "number": "000-711"}]},
    {"code": "EXK", "name": "Example Kept Ltd", "uses_sql": False, "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-712"}]},
    {"code": "EXN", "name": "Example New Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-713"}]},
]}), encoding="utf-8")

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:900])


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


def write(why, fn):
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        out = fn(con)
        con.commit()
        return out
    finally:
        con.disarm()
        con.close()


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def j(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


meta = j("get", "/api/meta")
ids = {e["code"]: e["id"] for e in meta["entities"]}
EXV, EXK, EXN = ids["EXV"], ids["EXK"], ids["EXN"]
TIN = "C00000000710"
j("patch", f"/api/setup/entities/{EXV}", json={"fields": {"tin": TIN, "reg_no": "202001000071", "address": "1, Jalan Contoh,\n50000 Kuala Lumpur"}})

ROWS = {}
U = lambda ch: (ch * 4 + "Q5JKA274M3RP29RZR97M10")[:26]
LONG = lambda ch: (ch * 6 + "LONGIDEXAMPLE0123456789")[:26]


def setup_docs(con):
    con.execute("UPDATE entities SET first_month = '2026-09' WHERE id = ?", (EXV,))
    imp = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'listing.xlsx', '2026-11-18T10:42:00', 0, 0)",
                      (EXV,)).lastrowid
    batch = ledger.new_batch(con, EXV, report="journal", sql_import_id=imp, file_name="GL Journal of Transaction.xlsx",
                             period_from="2026-09-01", period_to="2026-11-30")

    def entry(no, day, amount, kind, doc_type, code, desc, direction=None, payee=None, einvoice=None, status_=None):
        ROWS[no] = con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction,
                                  doc_type, kind, code, status, einvoice, einvoice_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (imp, EXV, no, day, desc, payee, amount, direction, doc_type, kind, code,
                                "invoice" if kind == "invoice" else "unlinked", einvoice, status_)).lastrowid

    def lines(no, day, book, ls):
        ledger.put_document(con, EXV, batch, {"doc_no": no, "doc_date": day, "book": book,
                                              "lines": [{"code": a, "description": d, "dr_sen": dr, "cr_sen": cr} for a, d, dr, cr in ls]})

    TENANT = "EXAMPLE RIVER TENANT"
    entry("IV2609-301", "2026-09-30", 900.0, "invoice", "IV", "300-V0001", "EXAMPLE RENT SEPTEMBER", "in", TENANT)
    lines("IV2609-301", "2026-09-30", "sales", [("300-V0001", "EXAMPLE RENT SEPTEMBER", 90000, 0), ("500-1000", "EXAMPLE RENT SEPTEMBER", 0, 90000)])
    entry("IV2610-302", "2026-10-01", 1250.0, "invoice", "IV", "300-V0001", "EXAMPLE RENT OCTOBER", "in", TENANT, U("A"), "Validated")
    lines("IV2610-302", "2026-10-01", "sales", [("300-V0001", "EXAMPLE RENT OCTOBER", 125000, 0), ("500-1000", "EXAMPLE RENT OCTOBER", 0, 125000)])
    entry("CN2610-303", "2026-10-20", 50.0, "invoice", "CN", "300-V0001", "EXAMPLE RENT REBATE", None, TENANT)  # its lines never fetched
    entry("IV2611-304", "2026-11-02", 1250.0, "invoice", "IV", "300-V0001", "EXAMPLE RENT NOVEMBER", "in", TENANT)
    lines("IV2611-304", "2026-11-02", "sales", [("300-V0001", "EXAMPLE RENT NOVEMBER", 125000, 0), ("500-1000", "EXAMPLE RENT NOVEMBER", 0, 125000)])
    # SQL restarts its numbers each year: the same number on two invoices of different years (and amounts)
    entry("IV-0007", "2025-09-10", 300.0, "invoice", "IV", "300-V0001", "EXAMPLE STORAGE 2025", "in", TENANT)
    entry("IV-0007#", "2025-10-10", 450.0, "invoice", "IV", "300-V0001", "EXAMPLE STORAGE 2025 AGAIN", "in", TENANT)
    entry("PI2610-305", "2026-10-12", 80.0, "invoice", "PI", "400-V0002", "EXAMPLE PEST CONTROL")  # a supplier's invoice: not issued
    SUP = "EXAMPLE FARAWAY SOFTWARE INC"
    entry("PV2610-306", "2026-10-15", 470.0, "payment", "PV", "400-V0003", "EXAMPLE SOFTWARE OCTOBER", "out", SUP, U("S"))
    lines("PV2610-306", "2026-10-15", "bank", [("900-V001", "EXAMPLE SOFTWARE", 47000, 0), ("310-000", "EXAMPLE SOFTWARE OCTOBER", 0, 47000)])
    con.execute("INSERT INTO gl_accounts (entity_id, code, name, type, special) VALUES (?, '310-000', 'BANK-EXAMPLE', 'asset', 'bank')", (EXV,))
    entry("PV2610-307", "2026-10-05", 84.3, "payment", "PV", "400-V0004", "EXAMPLE WATER OCTOBER", "out", "EXAMPLE WATER WORKS")
    # September: a self-billed voucher a refund takes back; SQL documents with an e-Invoice no copy of MyInvois has
    entry("PV2609-308", "2026-09-20", 212.0, "payment", "PV", "400-V0005", "EXAMPLE DESIGN SEPTEMBER", "out", "EXAMPLE DISTANT STUDIO", U("T"))
    entry("OR2609-309", "2026-09-25", 212.0, "payment", "OR", "400-V0005", "REFUND CANCELS PV2609-308", "in", "EXAMPLE DISTANT STUDIO", U("Q"), "Validated")
    # a cash sale with its own issued e-Invoice, found by its UUID (MyInvois links it to no document)
    entry("CS2609-314", "2026-09-05", 33.0, "payment", "CS", "300-V0009", "EXAMPLE COUNTER SALE", "in", "EXAMPLE WALK-IN BUYER", U("H"), "Validated")
    # a customer invoice SQL changed: read again with a new amount, same number and date (the later read is the one)
    entry("IV2611-312", "2026-11-03", 100.0, "invoice", "IV", "300-V0001", "EXAMPLE PARKING NOVEMBER", "in", TENANT)
    entry("IV2611-312#", "2026-11-03", 120.0, "invoice", "IV", "300-V0001", "EXAMPLE PARKING NOVEMBER", "in", TENANT)
    entry("PI2609-310", "2026-09-12", 64.5, "invoice", "PI", "400-V0006", "EXAMPLE LAMPS SEPTEMBER", None, "EXAMPLE LAMP SHOP", U("P"), "Validated")
    entry("PV2609-311", "2026-09-14", 99.0, "payment", "PV", "400-V0007", "EXAMPLE PARTS SEPTEMBER", "out", "EXAMPLE PARTS HOUSE", None, "Validated")
    doc = con.execute("""INSERT INTO documents (entity_id, month, doc_type, original_name, stored_path, sha256, size, uploaded_at)
                         VALUES (?, '2026-11', 'sql', 'example-myinvois-copy.xlsx', 'x', 'y', 1, '2026-11-18T10:42:05')""", (EXV,)).lastrowid

    def mi(uuid, no, typ, cur, sup, sup_tin, buyer, buyer_tin, validated, issued, status, total, way, entry_no=None, long_id=None, matched=None):
        con.execute("""INSERT INTO myinvois_docs (entity_id, uuid, doc_no, type, currency, supplier_name, supplier_tin, buyer_name, buyer_tin,
                       validated_at, issued_at, status, total_sen, direction, as_at, last_document_id, entry_id, long_id, matched_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-11-17T16:05:00', ?, ?, ?, ?)""",
                    (EXV, uuid, no, typ, cur, sup, sup_tin, buyer, buyer_tin, validated, issued, status, total, way, doc,
                     ROWS.get(entry_no), long_id, matched))

    ME = "EXAMPLE VALE SDN BHD"
    mi(U("A"), "IV2610-302", "Invoice", "MYR", ME, TIN, TENANT, "C00000000720", "2026-10-01 11:19:44", "2026-10-01 11:00:00", "Valid", 125000, "issued", "IV2610-302", LONG("A"))
    # the same invoice's first e-Invoice, cancelled and issued again (MyInvois links every one of the group to the document)
    mi(U("C"), "IV2610-302", "Invoice", "MYR", ME, TIN, TENANT, "C00000000720", "2026-10-01 08:10:00", "2026-10-01 08:00:00", "Cancelled", 125000, "issued", "IV2610-302")
    # its first attempt, cancelled (no SQL document either): folded into the one row of IV2610-399
    mi(U("G"), "IV2610-399", "Invoice", "USD", ME, TIN, "EXAMPLE OTHER BUYER", "C00000000730", None, "2026-10-27 09:00:00", "Cancelled", 30000, "issued")
    mi(U("B"), "IV2610-399", "Invoice", "USD", ME, TIN, "EXAMPLE OTHER BUYER", "C00000000730", None, "2026-10-28 09:00:00", "Submitted", 30000, "issued")
    mi(U("S"), "PV2610-306", "Self-billed Invoice", "USD", SUP, "EI00000000010", ME, TIN, "2026-10-16 14:19:44", "2026-10-16 14:00:00", "Valid", 10000, "self_billed", "PV2610-306", LONG("S"))
    mi(U("D"), "PV2610-306", "Self-billed Invoice", "USD", SUP, "EI00000000010", ME, TIN, "2026-10-15 10:00:00", "2026-10-15 09:00:00", "Cancelled", 10000, "self_billed", "PV2610-306")
    mi(U("T"), "PV2609-308", "Self-billed Invoice", "MYR", "EXAMPLE DISTANT STUDIO", "EI00000000020", ME, TIN, "2026-09-20 15:00:00", "2026-09-20 14:00:00", "Valid", 21200, "self_billed", "PV2609-308", LONG("T"))
    mi(U("Q"), "OR2609-309", "Invoice", "MYR", ME, TIN, "EXAMPLE DISTANT STUDIO", "C00000000780", "2026-09-25 12:00:00", "2026-09-25 11:00:00", "Valid", 21200, "issued", "OR2609-309", LONG("Q"))
    mi(U("H"), "CS2609-314", "Invoice", "MYR", ME, TIN, "EXAMPLE WALK-IN BUYER", "EI00000000030", "2026-09-05 12:00:00", "2026-09-05 11:00:00", "Valid", 3300, "issued")
    # one number used on two e-Invoices of different years, neither in SQL's documents: two documents
    mi(U("E"), "IV-0050", "Invoice", "MYR", ME, TIN, "EXAMPLE OLD BUYER", "C00000000790", "2025-03-01 10:00:00", "2025-03-01 09:00:00", "Valid", 10000, "issued")
    mi(U("F"), "IV-0050", "Invoice", "MYR", ME, TIN, "EXAMPLE OLD BUYER", "C00000000790", "2026-03-01 10:00:00", "2026-03-01 09:00:00", "Valid", 10000, "issued")
    mi(U("R"), "WW-0042", "Invoice", "MYR", "EXAMPLE WATER WORKS", "C00000000740", ME, TIN, "2026-10-03 09:30:12", "2026-10-03 09:00:00", "Valid", 8430, "received", "PV2610-307", LONG("R"), "amount")
    # neither the company's nor sent to it: another company's TIN on both sides
    mi(U("O"), "XX-0099", "Invoice", "MYR", "EXAMPLE THIRD PARTY", "C00000000760", "EXAMPLE FOURTH PARTY", "C00000000770", "2026-10-09 10:00:00", "2026-10-09 09:00:00", "Valid", 12000, "other")
    mi(U("N"), "PC/2610/77", "Invoice", "MYR", "EXAMPLE PEST CARE", "C00000000750", ME, TIN, "2026-10-12 13:40:02", "2026-10-12 13:00:00", "Valid", 25000, "received")


write("SQL documents, their lines and e-Invoices, as fetched", setup_docs)
# The second IV-0007 is the same number as the first (the "#" only kept the two apart in ROWS).
write("the number used again", lambda con: con.execute("UPDATE sql_entries SET doc_no = 'IV-0007' WHERE id = ?", (ROWS["IV-0007#"],)))
lamp_pay = j("post", "/api/payments", json={"entity_id": EXV, "month": "2026-09", "description": "Example lamps - test", "category": "utility",
                                            "amount": 64.5, "account_id": meta["entities"][0]["accounts"][0]["id"], "due_date": "2026-09-20"})["id"]
write("the supplier's invoice linked to its payment", lambda con: con.execute("UPDATE sql_entries SET payment_id = ? WHERE id = ?", (lamp_pay, ROWS["PI2609-310"])))
write("the changed invoice keeps its number", lambda con: con.execute("UPDATE sql_entries SET doc_no = 'IV2611-312' WHERE id = ?", (ROWS["IV2611-312#"],)))
water_pay = j("post", "/api/payments", json={"entity_id": EXV, "month": "2026-10", "description": "Example water - test", "category": "utility",
                                             "amount": 84.3, "account_id": meta["entities"][0]["accounts"][0]["id"], "due_date": "2026-10-20"})["id"]
write("the water voucher linked to its payment", lambda con: con.execute("UPDATE sql_entries SET payment_id = ? WHERE id = ?", (water_pay, ROWS["PV2610-307"])))

# ---------- the server: the three lists ----------
d = j("get", f"/api/einvoices?entity={EXV}")
iss = {x["doc_no"]: x for x in d["issued"]}
nos = lambda k: [x.get("doc_no") or x.get("in_sql") for x in d[k]]  # rows per number counted with lists, never a dict

# ---------- the invariant: every e-Invoice and every document with one, exactly once ----------
TABS = ("issued", "self_billed", "received", "other")
all_mi = sorted(r["id"] for r in q("SELECT id FROM myinvois_docs WHERE entity_id = ?", (EXV,)))
accounted = sorted(i for k in TABS for x in d[k] for i in x["mi_ids"])
check("invariant (a): every MyInvois row is accounted for exactly once (shown, or folded into one shown group)",
      accounted == all_mi, (len(accounted), len(all_mi), sorted(set(accounted) ^ set(all_mi)), [i for i in accounted if accounted.count(i) > 1]))
# Declared here, independently of the code: every group the page must show, by tab, with its SQL document (a key of
# ROWS) or none, and the e-Invoices it accounts for (by the letter their made-up UUIDs start with).
EXPECT = [
    ("issued", "IV-0007", ""), ("issued", "IV-0007#", ""), ("issued", "IV2609-301", ""), ("issued", "IV2610-302", "AC"),
    ("issued", "CN2610-303", ""), ("issued", "IV2611-304", ""), ("issued", "IV2611-312#", ""), ("issued", "OR2609-309", "Q"),
    ("issued", "CS2609-314", "H"), ("issued", None, "BG"), ("issued", None, "E"), ("issued", None, "F"),
    ("self_billed", "PV2610-306", "DS"), ("self_billed", "PV2609-308", "T"), ("self_billed", "PV2609-311", ""),
    ("received", "PV2610-307", "R"), ("received", "PI2609-310", ""), ("received", None, "N"),
    ("other", None, "O"),
]
letter = {r["id"]: r["uuid"][0] for r in q("SELECT id, uuid FROM myinvois_docs WHERE entity_id = ?", (EXV,))}
shown_groups = sorted((k, x.get("id") or 0, "".join(sorted(letter[i] for i in x["mi_ids"]))) for k in TABS for x in d[k])
declared = sorted((k, ROWS[doc] if doc else 0, uu) for k, doc, uu in EXPECT)
check("invariant (b): the page shows exactly the declared groups: each document once, on its declared tab, with its declared e-Invoices",
      shown_groups == declared, [g for g in shown_groups if g not in declared] + ["<- shown | declared ->"] + [g for g in declared if g not in shown_groups])
check("invariant (c): distinct documents stay apart: a number reused in another year, with or without SQL documents, is two rows",
      nos("issued").count("IV-0050") == 2 and nos("issued").count("IV-0007") == 2
      and sorted(x["date"] for x in d["issued"] if x["doc_no"] == "IV-0050") == ["2025-03-01", "2026-03-01"], nos("issued"))
check("an e-Invoice with no SQL document, cancelled and issued again: one row, the later attempt, the cancelled one folded into it",
      nos("issued").count("IV2610-399") == 1 and iss["IV2610-399"]["myinvois"]["uuid"] == U("B") and len(iss["IV2610-399"]["mi_ids"]) == 2)
check("a refund and a cash sale with their own issued e-Invoice: one Issued row each, with what the copy says",
      nos("issued").count("OR2609-309") == 1 and nos("issued").count("CS2609-314") == 1
      and iss["OR2609-309"]["myinvois"]["uuid"] == U("Q") and iss["CS2609-314"]["myinvois"]["uuid"] == U("H")
      and iss["CS2609-314"]["id"] == ROWS["CS2609-314"], [(x["doc_no"], x["id"]) for x in d["issued"]])
check("an invoice SQL changed (read twice, same number and date): one row, the later read's amount",
      nos("issued").count("IV2611-312") == 1 and iss["IV2611-312"]["amount"] == 120.0 and iss["IV2611-312"]["id"] == ROWS["IV2611-312#"])
check("...and November's zip counts it once, as the zip itself does",
      d["print"]["counts"]["customer"]["2026-11"] == 2 and d["print"]["counts"]["customer"]["2026-10"] == 2, d["print"]["counts"])
ww = [x for x in d["received"] if x["their"] == "WW-0042"]
check("a received e-Invoice matched to a voucher linked to a payment keeps Unlink (the voucher's id and payment)",
      len(ww) == 1 and ww[0]["id"] == ROWS["PV2610-307"] and ww[0]["payment_id"] == water_pay, ww)
check("Issued: the customer documents, the refund and cash sale, and the e-Invoices issued with no SQL document, by date; not the supplier's invoice",
      nos("issued") == ["IV-0050", "IV-0007", "IV-0007", "IV-0050", "CS2609-314", "OR2609-309", "IV2609-301", "IV2610-302", "CN2610-303",
                        "IV2610-399", "IV2611-304", "IV2611-312"], nos("issued"))
check("...each SQL document with what its MyInvois copy says, its buyer and its share link",
      iss["IV2610-302"]["myinvois"] == {"uuid": U("A"), "type": "Invoice", "status": "Valid", "validated_at": "2026-10-01 11:19:44",
                                         "link": f"https://myinvois.hasil.gov.my/{U('A')}/share/{LONG('A')}"}
      and iss["IV2610-302"]["party"] == {"label": "Buyer", "name": "EXAMPLE RIVER TENANT", "tin": "C00000000720"}
      and iss["IV2610-302"]["status"] == "Validated" and iss["IV2610-302"]["print_kind"] == "customer", iss["IV2610-302"])
check("a number SQL used again in another year: both invoices are listed, each by its own date and amount (not the newer alone)",
      sorted((x["date"], x["amount"]) for x in d["issued"] if x["doc_no"] == "IV-0007") == [("2025-09-10", 300.0), ("2025-10-10", 450.0)]
      and {x["id"] for x in d["issued"] if x["doc_no"] == "IV-0007"} == {ROWS["IV-0007"], ROWS["IV-0007#"]}, [x["doc_no"] for x in d["issued"]])
check("...a credit note is named as one and prints; the e-Invoice with no SQL document has nothing to print",
      iss["CN2610-303"]["what"] == "credit note" and iss["CN2610-303"]["print_kind"] == "customer"
      and iss["IV2610-399"]["id"] is None and iss["IV2610-399"]["print_kind"] is None and iss["IV2610-399"]["status"] == "Submitted, not validated")
sb = d["self_billed"]
check("Self-billed: the voucher's number, the supplier, USD with what was paid in ringgit, printable",
      len(sb) == 3 and sb[2]["doc_no"] == "PV2610-306" and sb[2]["currency"] == "USD" and sb[2]["amount"] == 100.0
      and sb[2]["paid_as"] == {"amount": 470.0, "by": "PV2610-306"} and sb[2]["print_kind"] == "self_billed"
      and sb[2]["party"]["name"] == "EXAMPLE FARAWAY SOFTWARE INC", sb)
rc = {x["their"]: x for x in d["received"]}
check("Received: each with the SQL document it is in, how it was matched, and its SQL code; or Not found",
      rc["WW-0042"]["in_sql"] == "PV2610-307" and rc["WW-0042"]["matched_by"] == "By amount" and rc["WW-0042"]["code"] == "400-V0004"
      and rc["PC/2610/77"]["in_sql"] == "", rc)
check("...and the valid one received that SQL's books don't have, from the first month tracked",
      [x["doc_no"] for x in d["unmatched"]] == ["PC/2610/77"] and d["since"] == "2026-09", d["unmatched"])
check("an invoice whose e-Invoice was cancelled and issued again is listed once, with the valid one (myinvois._best)",
      [x["doc_no"] for x in d["issued"]].count("IV2610-302") == 1 and iss["IV2610-302"]["myinvois"]["uuid"] == U("A"),
      [(x["doc_no"], x["what"]) for x in d["issued"]])
sbs = {x["doc_no"]: x for x in d["self_billed"]}
check("a voucher with a cancelled and a valid self-billed e-Invoice is one row, with the valid one",
      [x["doc_no"] for x in d["self_billed"]].count("PV2610-306") == 1 and sbs["PV2610-306"]["myinvois"]["uuid"] == U("S"), list(sbs))
check("a self-billed e-Invoice a refund takes back says so (not Validated)", sbs["PV2609-308"]["taken_back_by"] == "OR2609-309", sbs["PV2609-308"])
rcs = {x["in_sql"]: x for x in d["received"]}
check("SQL documents with an e-Invoice no copy has are on their side's tab with SQL's status: the supplier's invoice on Received (with its payment), the voucher on Self-billed",
      rcs.get("PI2609-310", {}).get("sql_only") and rcs["PI2609-310"]["status"] == "Validated" and rcs["PI2609-310"]["payment_id"] == lamp_pay
      and rcs["PI2609-310"]["id"] == ROWS["PI2609-310"] and sbs.get("PV2609-311", {}).get("sql_only") and sbs["PV2609-311"]["status"] == "Validated",
      (list(rcs), list(sbs)))
check("the e-Invoices in the copy that are neither the company's nor sent to it are listed apart",
      [(x["doc_no"], x["supplier"], x["buyer"], x["amount"]) for x in d["other"]] == [("XX-0099", "EXAMPLE THIRD PARTY", "EXAMPLE FOURTH PARTY", 120.0)]
      and d["counts"]["other"] == 1, d["other"])
check("the copy read and the days it covers, and what printing lacks",
      d["copy"] and d["sources"][0]["name"] == "example-myinvois-copy.xlsx" and d["span"] == ["2025-03-01", "2026-10-28"]
      and d["print"] and any("signature" in m for m in d["print"]["missing"]) and "2026-11" in d["print"]["months"]["customer"], (d["sources"], d["span"], d["print"]))
d_new = j("get", f"/api/einvoices?entity={EXN}")
check("a company with nothing fetched: empty lists and no copy", not (d_new["issued"] or d_new["received"] or d_new["self_billed"] or d_new["copy"]))

# ---------- the server: Excel ----------
r = c.get(BASE + f"/api/export/einvoices.xlsx?entity_id={EXV}&month=2026-10", headers=H)
check("Excel: the month's lists as a workbook, named by the company and month",
      r.status_code == 200 and "EXV e-Invoices 2026-10.xlsx" in r.headers.get("Content-Disposition", ""), (r.status_code, r.headers.get("Content-Disposition")))
wb = load_workbook(io.BytesIO(r.data))
col = lambda ws, n: [ws.cell(row=i, column=n).value for i in range(4, ws.max_row + 1)]
check("...one sheet per tab and one for those not found in SQL's books",
      wb.sheetnames == ["Issued", "Received", "Self-billed", "Not found in SQL", "Other"], wb.sheetnames)
heads = lambda ws: [ws.cell(row=3, column=i).value for i in range(1, ws.max_column + 1)]
check("...Issued has a Currency column and an Amount heading without RM, as an issued e-Invoice may be in USD",
      heads(wb["Issued"])[6:8] == ["Currency", "Amount"] and "Amount (RM)" not in heads(wb["Issued"])
      and [(r[0].value, r[6].value, r[7].value) for r in wb["Issued"].iter_rows(min_row=4) if r[0].value == "IV2610-399"] == [("IV2610-399", "USD", 300.0)], heads(wb["Issued"]))
check("...and the Other sheet lists those neither issued nor received", col(wb["Other"], 1) == ["XX-0099"] and col(wb["Other"], 6) == ["EXAMPLE FOURTH PARTY"])
check("...Issued holds October's documents only, with their status and MyInvois UUID",
      col(wb["Issued"], 1) == ["IV2610-302", "CN2610-303", "IV2610-399"] and wb["Issued"].cell(row=4, column=10).value == U("A")
      and wb["Issued"].cell(row=4, column=9).value == "Validated", col(wb["Issued"], 1))
check("...Received and Self-billed for October, and the one not found in SQL",
      col(wb["Received"], 5) == ["WW-0042", "PC/2610/77"] and col(wb["Received"], 12) == ["PV2610-307", "Not found"]
      and col(wb["Self-billed"], 1) == ["PV2610-306"] and col(wb["Not found in SQL"], 1) == ["PC/2610/77"])
r = c.get(BASE + f"/api/export/einvoices.xlsx?entity_id={EXV}", headers=H)
check("...with no month, every month", r.status_code == 200 and "EXV e-Invoices all months.xlsx" in r.headers.get("Content-Disposition", "")
      and len(col(load_workbook(io.BytesIO(r.data))["Issued"], 1)) == 12)
xl_all = load_workbook(io.BytesIO(r.data))
check("...the Excel's sheets hold the declared groups too, one row each",
      [len(col(xl_all[s], 1)) for s in ("Issued", "Self-billed", "Received", "Other")]
      == [sum(1 for k, *_ in EXPECT if k == t) for t in ("issued", "self_billed", "received", "other")])
wb_all = load_workbook(io.BytesIO(r.data))
check("...the Self-billed sheet says Cancelled by the refund, as the page does",
      [(x[0].value, x[8].value) for x in wb_all["Self-billed"].iter_rows(min_row=4) if x[0].value == "PV2609-308"] == [("PV2609-308", "Cancelled by OR2609-309")])
check("...a month that isn't one is refused", c.get(BASE + f"/api/export/einvoices.xlsx?entity_id={EXV}&month=2026-13", headers=H).status_code == 400)
check("...and opening it is in the audit trail",
      len(q("SELECT 1 FROM audit_row WHERE tbl = 'read' AND op = 'event' AND row_key = 'e-Invoices export'")) == 2)

# ---------- the print check of each document, as the page reads it ----------
chk = {}
for no in ("IV2610-302", "CN2610-303", "IV2611-304", "IV2609-301", "PV2610-306"):
    rr = c.get(BASE + f"/api/invoices/{ROWS[no]}/check", headers=H)
    chk[no] = (rr.status_code, rr.get_json())
check("the print check: the credit note with no lines can't be printed, and says why",
      chk["CN2610-303"][0] >= 400 and "haven't been fetched" in chk["CN2610-303"][1]["error"], chk["CN2610-303"])
check("...the invoices print", chk["IV2610-302"][0] == 200 and chk["IV2611-304"][0] == 200, chk["IV2610-302"])

# ---------- the page ----------
sql_entries = j("get", f"/api/sql/entries?entity={EXV}")
routes = {"/api/meta": j("get", "/api/meta"), f"/api/einvoices?entity={EXV}": d, f"/api/einvoices?entity={EXN}": d_new,
          f"/api/sql/entries?entity={EXV}": sql_entries}
for no, (st, body) in chk.items():
    routes[f"/api/invoices/{ROWS[no]}/check"] = body if st == 200 else {"__status": st, **body}
# The print check of the self-billed voucher, with a note (the shape the server sends), to show a marker with notes.
routes[f"/api/invoices/{ROWS['PV2610-306']}/check"] = {**chk["PV2610-306"][1], "notes": ["The e-Invoice is in USD: its lines print SQL's ringgit lines at the voucher's rate."]}
# Many rows: thirty issued documents in October (state-only, as the board's many-rows sample).
many = copy.deepcopy(d)
base_row = next(x for x in many["issued"] if x["doc_no"] == "IV2609-301")
many["issued"] = [dict(base_row, id=None, print_kind=None, doc_no=f"IV2610-{400 + i}", date=f"2026-10-{1 + i % 28:02d}") for i in range(30)]
fixture = {"exv": EXV, "exk": EXK, "exn": EXN, "rows": ROWS, "routes": routes, "many": many,
           "zip_oct": f"/api/invoices/month.zip?entity={EXV}&entity_id={EXV}&month=2026-10&kind=customer",
           "zip_sb": f"/api/invoices/month.zip?entity={EXV}&entity_id={EXV}&month=2026-10&kind=self_billed"}
fx = tmp / "fixture.json"
fx.write_text(json.dumps(fixture), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, docListeners = {}, fetched = [], zips = {};
const holds = [], release = () => holds.splice(0).forEach(r => r());  // every zip held is let go
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, listeners: {}, files: [],
  classList: { add() {}, remove() {}, contains() { return false; }, toggle() {} }, addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
  querySelectorAll() { return []; }, querySelector() { return null; }, setAttribute(k, v) { this["@" + k] = v; }, getAttribute(k) { return this["@" + k] ?? null; },
  removeAttribute(k) { delete this["@" + k]; }, focus() { focused = id; }, remove() {}, scrollIntoView() {} };
let focused = null;
const document = { querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, querySelectorAll: () => [], getElementById: id => els[id] || null,
  addEventListener(t, f) { (docListeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  fetched.push(path);
  if (zips[path]) { const z = zips[path]; if (z.hold) await new Promise(r => holds.push(r)); return z.ok ? { ok: true, status: 200, blob: async () => ({ size: 10 }) } : { ok: false, status: 404, text: async () => z.html }; }
  let r = fx.routes[path];
  if (r === undefined && path.startsWith("/api/audit/status")) r = { ok: true };
  if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: "The records folder can't be reached (not stubbed: " + path + ")." }) };
  if (r.__status) return { ok: false, status: r.__status, json: async () => JSON.parse(JSON.stringify(r)) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
const ctx = vm.createContext({ document, fetch, FormData: class { append() {} }, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, window: { print() {} } });
const run = code => vm.runInContext(code, ctx);
const pause = () => new Promise(r => setTimeout(r, 30));
const target = (dataset = {}, id = "", more = {}) => ({ id, dataset, closest() { return this; }, getAttribute(k) { return this["@" + k] ?? null; }, setAttribute(k, v) { this["@" + k] = v; },
  removeAttribute(k) { delete this["@" + k]; }, classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } }, querySelector() { return null; }, querySelectorAll() { return []; }, ...more });
const fire = async (type, ev) => { for (const f of docListeners[type] || []) await f({ preventDefault() {}, stopPropagation() {}, ...ev }); await pause(); await pause(); };
const click = (dataset, id, more) => fire("click", { target: target(dataset, id, more) });
const key = (k, dataset) => fire("keydown", { key: k, target: target(dataset) });
const out = {};
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  await pause();
  const show = async (view, entity, params = {}) => {
    run(`state.view = ${JSON.stringify(view)}; state.entity = ${entity}; render.company = ${entity}; state.month = "2026-10"; state.day = dayKey(); state.addr = { all: false, id: null, params: ${JSON.stringify(params)} }; state.ei = null;`);
    await run("render()"); await pause(); await pause(); return el("main").innerHTML; };
  out.page = await show("einvoices", fx.exv);
  out.month = run("state.ei.month");
  const R = fx.rows;
  out.noteIv = el(`ei-pn-${R["IV2610-302"]}`).innerHTML; out.noteCn = el(`ei-pn-${R["CN2610-303"]}`).innerHTML;
  out.checked = fetched.filter(p => /\/check$/.test(p));
  // A print note opened, then closed with Escape (the focus stays on its marker)
  await click({ eiNote: String(R["CN2610-303"]) }); out.noteOpen = el(`ei-pn-${R["CN2610-303"]}`).innerHTML;
  await key("Escape", { eiNote: String(R["CN2610-303"]) }); out.noteShut = el(`ei-pn-${R["CN2610-303"]}`).innerHTML; out.noteFocus = focused;
  // All of the month: made and saved; then refused in place
  zips[fx.zip_oct] = { ok: true };
  await click({ eiZip: "1" }, "ei-zip"); out.zipDone = el("ei-print").innerHTML; out.zipFocus = focused; out.zipSay = el("ei-say").textContent;
  zips[fx.zip_oct] = { ok: false, html: "<!doctype html><meta charset='utf-8'><title>Not printed</title><body><p>EXV has no customer invoices, debit notes or credit notes in October 2026 in the SQL documents fetched.</p></body>" };
  await click({ eiZip: "1" }, "ei-zip"); out.zipBad = el("ei-print").innerHTML;
  // A zip still being made while the tab changes: it can't be asked for twice, and its answer lands only on its own tab
  zips[fx.zip_oct] = { ok: true, hold: true };
  const n0 = fetched.filter(p => p === fx.zip_oct).length;
  const held = fire("click", { target: target({ eiZip: "1" }, "ei-zip") }); await pause();
  out.raceBusy = el("ei-print").innerHTML;
  // (the clicks are not awaited: a zip asked for again would wait on the held answer)
  await key("ArrowLeft", { eiTab: "issued" }); out.raceSbBusy = el("ei-panel").innerHTML;
  const again1 = click({ eiZip: "1" }, "ei-zip"); await pause();
  await key("ArrowRight", { eiTab: "self-billed" }); out.raceBack = el("ei-panel").innerHTML;
  const again2 = click({ eiZip: "1" }, "ei-zip"); await pause();
  await key("ArrowLeft", { eiTab: "issued" });
  release(); await Promise.all([held, again1, again2]); await pause();
  out.raceSb = el("ei-print").innerHTML; out.raceFetches = fetched.filter(p => p === fx.zip_oct).length - n0;
  await key("ArrowRight", { eiTab: "self-billed" }); out.raceIssued = el("ei-panel").innerHTML;
  zips[fx.zip_oct] = { ok: true };
  // A zip still being made while the month being worked changes: still one at a time, and its answer isn't said on September
  zips[fx.zip_oct] = { ok: true, hold: true };
  const z0 = fetched.filter(p => p.startsWith("/api/invoices/month.zip")).length;
  const heldM = fire("click", { target: target({ eiZip: "1" }, "ei-zip") }); await pause();
  run('state.month = "2026-09"'); await run("render()"); await pause();
  out.monthBusy = el("main").innerHTML;
  const againM = click({ eiZip: "1" }, "ei-zip"); await pause();
  release(); await Promise.all([heldM, againM]); await pause();
  out.monthFetches = fetched.filter(p => p.startsWith("/api/invoices/month.zip")).length - z0;
  out.monthAfter = el("ei-print").innerHTML + el("main").innerHTML;
  run('state.month = "2026-10"'); await run("render()"); await pause();
  zips[fx.zip_oct] = { ok: true };
  // The other e-Invoices, folded under the source line (the stand-in has no .ei-source, so it is drawn here as the page does)
  await click({ eiOther: "1" }, "ei-other-b"); out.otherOpen = run("eiSource(ent(), state.eiData)"); out.otherFocus = focused;
  // The tabs: a click, the arrow keys, Home and End; the address follows
  await key("ArrowRight", { eiTab: "issued" }); out.recv = el("ei-panel").innerHTML; out.recvTabs = el("ei-tabs").innerHTML; out.recvFocus = focused; out.recvAddr = run("currentAddr()");
  out.recvSay = el("ei-say").textContent;
  await key("ArrowRight", { eiTab: "received" }); out.sb = el("ei-panel").innerHTML; out.sbFocus = focused;
  await new Promise(r => setTimeout(r, 120)); out.noteSb = el(`ei-pn-${R["PV2610-306"]}`).innerHTML;
  await key("ArrowRight", { eiTab: "self-billed" }); out.wrapFocus = focused;
  await key("End", { eiTab: "issued" }); out.endFocus = focused;
  await key("Home", { eiTab: "self-billed" }); out.homeFocus = focused; out.homeAddr = run("currentAddr()");
  await click({ eiTab: "received" }); out.clickTab = run("eiTab()"); out.clickFocus = focused;
  // The month: all months, then an empty one
  await fire("change", { target: target({ eiMonth: "1" }, "ei-month", { value: "all" }) });
  await click({ eiTab: "issued" }); out.allPanel = el("ei-panel").innerHTML; out.allXl = el("ei-xl")["@href"]; out.allHead = el("ei-list-h").textContent;
  await fire("change", { target: target({ eiMonth: "1" }, "ei-month", { value: "2026-11" }) }); out.novPanel = el("ei-panel").innerHTML;
  await click({ eiTab: "self-billed" }); out.novSb = el("ei-panel").innerHTML;
  // September: the refund on Issued, the voucher it takes back, the supplier's invoice from SQL with Unlink
  await fire("change", { target: target({ eiMonth: "1" }, "ei-month", { value: "2026-09" }) }); out.sepSb = el("ei-panel").innerHTML;
  await click({ eiTab: "received" }); out.sepRecv = el("ei-panel").innerHTML;
  await click({ eiTab: "issued" }); out.sepIss = el("ei-panel").innerHTML;
  // An address that names a tab opens it
  out.byAddr = await show("einvoices", fx.exv, { tab: "received" }); out.byAddrTab = run("eiTab()");
  // Many rows
  fx.routes[`/api/einvoices?entity=${fx.exv}`] = fx.many;
  out.many = await show("einvoices", fx.exv);
  await click({ eiMore: "1" }); out.more = el("ei-panel").innerHTML; out.moreFocus = focused;
  // No e-Invoices yet; couldn't load; kept here
  out.empty = await show("einvoices", fx.exn);
  delete fx.routes[`/api/einvoices?entity=${fx.exn}`];
  out.error = await show("einvoices", fx.exn);
  out.here = await show("einvoices", fx.exk);
  // The SQL import page
  out.sql = await show("sql", fx.exv);
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
node = shutil.which("node")
if not node:
    print("SKIPPED the page checks: Node.js isn't installed")
    o = None
else:
    run_ = subprocess.run([node, str(probe), app_bundle(tmp / "app.js"), str(fx)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    o = json.loads(run_.stdout) if run_.returncode == 0 and run_.stdout.strip() else None
    check("the page script ran", o is not None, run_.stderr[-1500:])

if o:
    P, IV, CN, SB = o["page"], ROWS["IV2610-302"], ROWS["CN2610-303"], ROWS["PV2610-306"]
    check("the head: the company and its kind, e-Invoices, the board's intro",
          "EXV · Kept in SQL Account" in P and ">e-Invoices</h1>" in P and "EXV&#39;s MyInvois e-Invoices: those it issued to customers" in P
          and "Nothing here can be edited: it follows SQL." in P)
    check("where they come from, in one line, its times as \"18 Nov 2026, 10:42\" (not raw ISO)",
          "From <b>example-myinvois-copy.xlsx</b>, saved 17 Nov 2026, 16:05, read 18 Nov 2026, 10:42 by Fetch on SQL import: 14 e-Invoices (8 issued, 2 received, 3 self-billed, 1 other)." in P
          and 'data-menu="accounting/sql">Open SQL import' in P and "2026-11-17T16:05" not in P, P[:3000])
    check("the month the page opens on is the month being worked (October), not the newest (November)",
          o["month"] == "2026-10" and '<option value="2026-10" selected>October 2026</option>' in P and '<option value="2026-11">November 2026</option>' in P)
    check("...and the all-months choice names the days the copy covers", "All months in the copy (1 Mar to 28 Oct)" in P)
    check("the tabs: Issued chosen, each with its count for the month, roving focus",
          'id="ei-tab-issued" data-ei-tab="issued" aria-selected="true" aria-controls="ei-panel" aria-label="Issued, 3" tabindex="0"' in P
          and 'aria-label="Received, 2" tabindex="-1"' in P and 'aria-label="Self-billed, 1" tabindex="-1"' in P and 'role="tablist"' in P)
    check("Excel for the month chosen", f'href="/api/export/einvoices.xlsx?entity_id={EXV}&amp;month=2026-10" download' in P)
    Q = P  # the panel as first drawn, inside the page
    check("Issued: the board's columns, with the Print column",
          all(f'<th scope="col"{x}>{h}</th>' in Q for x, h in (("", "Doc no."), ("", "Date"), ("", "Description"), (' class="num"', "Amount (RM)"), ("", "Status"), ("", "MyInvois"), ("", "Print"))))
    check("...a validated invoice: its pill, its MyInvois page, its UUID and when it was validated, written \"1 Oct 2026, 11:19\"",
          "Validated</span>" in Q and "Open IV2610-302 on MyInvois, opens in a new tab" in Q and U("A") in Q
          and "Invoice · Valid · validated 1 Oct 2026, 11:19" in Q and "2026-10-01 11:19:44" not in Q, Q[:4000])
    check("...the buyer under the description", "Buyer: EXAMPLE RIVER TENANT (C00000000720)" in Q)
    check("...the PDF buttons say what they print, and open in a new tab",
          f'href="/api/invoices/{IV}.pdf?entity_id={EXV}" target="_blank"' in Q and "Invoice PDF of IV2610-302, opens in a new tab" in Q
          and "Credit note PDF of CN2610-303" in Q and "The credit note, laid out as SQL Account prints it" in Q)
    check("...the e-Invoice with no SQL document has no PDF, and its status is MyInvois's",
          "IV2610-399" in Q and "Submitted, not validated" in Q)
    check("...each printable document of the month shown is checked once", sorted(o["checked"]) == sorted([f"/api/invoices/{IV}/check", f"/api/invoices/{CN}/check"]), o["checked"])
    check("the print note beside the PDF: none for a document that prints cleanly; Not printed, with why, for one that can't",
          o["noteIv"] == "" and f'data-ei-note="{CN}" aria-expanded="false"' in o["noteCn"] and "Not printed" in o["noteCn"]
          and "haven&#39;t been fetched" in o["noteCn"], o["noteCn"])
    check("...opened, it lists the note; Escape closes it and the focus stays on its marker",
          'aria-expanded="true"' in o["noteOpen"] and '<ul class="ei-pn-list"' in o["noteOpen"] and "<ul" not in o["noteShut"]
          and o["noteFocus"] == f"ei-pn-b-{CN}", (o["noteOpen"], o["noteShut"], o["noteFocus"]))
    check("Print: All of the month says what goes in the zip",
          "All of the month</button>" in Q and "EXV Invoices 2026-10.zip: the 2 invoices, debit and credit notes of October 2026, one PDF each" in Q)
    check("...the print settings still missing, with the way to Setup",
          "<b>Print settings:</b> invoices print without what is missing." in Q and "No signature: upload it under Printed invoices in Setup › Companies › EXV." in Q
          and 'data-inv-setup="1">Open Setup › Companies</button>' in Q)
    check("...the zip made: saved, said, the focus on the button", "Saved EXV Invoices 2026-10.zip" in o["zipDone"] and o["zipFocus"] == "ei-zip"
          and o["zipSay"] == "Saved EXV Invoices 2026-10.zip.", o["zipDone"])
    check("...a zip the server refuses says why in place", 'role="alert">EXV has no customer invoices, debit notes or credit notes in October 2026' in o["zipBad"], o["zipBad"])
    check("a zip still being made: busy, not asked for twice (not even from another tab and back), and its answer lands only on its own tab",
          "Making the zip…" in o["raceBusy"] and "Making the zip…" in o["raceBack"] and o["raceFetches"] == 1
          and "Another zip is being made." in o["raceSbBusy"] and "Saved EXV Invoices 2026-10.zip" not in o["raceSb"]
          and "Saved EXV Invoices 2026-10.zip" in o["raceIssued"], (o["raceFetches"], "Making" in o["raceBusy"], "Making" in o["raceBack"], "Another" in o["raceSbBusy"], "Saved" in o["raceSb"], o["raceIssued"][-500:]))
    check("the other e-Invoices the source line counts can be opened under it",
          'id="ei-other-b" data-ei-other="1" aria-expanded="false"' in P and "1 other e-Invoice in the copy, neither issued by EXV nor sent to it" in P
          and "XX-0099" in o["otherOpen"] and "EXAMPLE FOURTH PARTY" in o["otherOpen"] and o["otherFocus"] == "ei-other-b", o["otherOpen"][:800])
    check("a zip still being made while the month being worked changes: not asked for again, and not said Saved on the other month",
          o["monthFetches"] == 1 and "Another zip is being made." in o["monthBusy"] and "Saved EXV Invoices 2026-10.zip" not in o["monthAfter"],
          (o["monthFetches"], "Another" in o["monthBusy"]))
    check("a tab clicked keeps the focus on it (Enter and Space click it)", o["clickFocus"] == "ei-tab-received", o["clickFocus"])
    check("September, Self-billed: the voucher a refund takes back says Cancelled by it; the voucher with SQL's e-Invoice alone is listed",
          "Cancelled by OR2609-309" in o["sepSb"] and "PV2609-311" in o["sepSb"], o["sepSb"][:1500])
    check("September, Received: the supplier's invoice from SQL, with SQL's status and Unlink, as the SQL page's card had",
          "PI2609-310</b>" in o["sepRecv"] and "From SQL: no copy of MyInvois has it yet" in o["sepRecv"]
          and f'data-sql-unlink="{ROWS["PI2609-310"]}" aria-label="Unlink PI2609-310 from its payment">Unlink</button>' in o["sepRecv"]
          and "Validated</span>" in o["sepRecv"], o["sepRecv"][:2000])
    check("September, Issued: the refund with its e-Invoice, from SQL", "OR2609-309" in o["sepIss"] and "REFUND CANCELS PV2609-308" in o["sepIss"])
    check("October, Received: the voucher a received e-Invoice is in keeps its Unlink",
          f'data-sql-unlink="{ROWS["PV2610-307"]}" aria-label="Unlink PV2610-307 from its payment">Unlink</button>' in o["recv"], o["recv"][:1500])
    Rv = o["recv"]
    check("the arrow keys: Right picks Received, the focus follows, the address names the tab, it is said",
          o["recvFocus"] == "ei-tab-received" and 'id="ei-tab-received" data-ei-tab="received" aria-selected="true"' in o["recvTabs"]
          and o["recvAddr"] == "#/EXV/2026-10/accounting/einvoices?tab=received" and o["recvSay"] == "Received e-Invoices shown.", (o["recvAddr"], o["recvFocus"]))
    check("Received: the board's columns, matched by amount as a likely match, Not found, validated \"3 Oct 2026, 09:30\"",
          all(f'<th scope="col"{x}>{h}</th>' in Rv for x, h in (("", "Issued"), ("", "From"), ("", "Their number"), ("", "In SQL")))
          and "PV2610-307</b>" in Rv and 'title="A likely match, by amount only: check it">By amount' in Rv and "Not found</span>" in Rv
          and "Validated 3 Oct 2026, 09:30" in Rv and "Code 400-V0004" in Rv and "All of the month" not in Rv, Rv[:3000])
    check("...the e-Invoices received but not found in SQL's books, whatever month is chosen",
          "e-Invoices received but not found in SQL's books (1)</h3>" in Rv and "from September 2026" in Rv and "Listed whatever month is chosen." in Rv
          and "PC/2610/77" in Rv)
    S = o["sb"]
    check("Self-billed: the supplier, USD, what was paid in ringgit, Invoice PDF, and its own zip",
          o["sbFocus"] == "ei-tab-sb" and "Supplier: EXAMPLE FARAWAY SOFTWARE INC (EI00000000010)" in S and "USD 100.00" in S
          and "Paid as RM 470.00 by PV2610-306" in S and "Invoice PDF of PV2610-306" in S
          and "EXV Self-billed invoices 2026-10.zip: the 1 self-billed invoice of October 2026, one PDF each" in S, S[:3000])
    check("...its print note beside the PDF, with the note on hover", f'data-ei-note="{SB}"' in o["noteSb"] and "1 print note" in o["noteSb"]
          and "title=\"The e-Invoice is in USD" in o["noteSb"], o["noteSb"])
    check("the arrow keys wrap, End and Home go to the last and the first, the address drops the tab for Issued",
          o["wrapFocus"] == "ei-tab-issued" and o["endFocus"] == "ei-tab-sb" and o["homeFocus"] == "ei-tab-issued"
          and o["homeAddr"] == "#/EXV/2026-10/accounting/einvoices" and o["clickTab"] == "received", (o["wrapFocus"], o["endFocus"], o["homeFocus"], o["homeAddr"]))
    check("all months: every document, no zip (choose a month), Excel for every month",
          "IV2609-301" in o["allPanel"] and "IV2611-304" in o["allPanel"] and "Choose a month to print all of it as one zip." in o["allPanel"]
          and 'id="ei-zip"' not in o["allPanel"] and o["allXl"] == f"/api/export/einvoices.xlsx?entity_id={EXV}" and o["allHead"] == "Issued e-Invoices, all months")
    check("a month with nothing on the tab: the board's empty sentence, and no zip",
          "No self-billed e-Invoice in November 2026. They are made for overseas suppliers and claims paid abroad." in o["novSb"]
          and "Nothing to print for November 2026." in o["novSb"] and "IV2611-304" in o["novPanel"]
          and "EXV Invoices 2026-11.zip: the 2 invoices, debit and credit notes of November 2026" in o["novPanel"] and o["novPanel"].count(">IV2611-312</td>") == 1, o["novPanel"][:1500])
    check("an address that names a tab opens it", o["byAddrTab"] == "received" and 'id="ei-tab-received" data-ei-tab="received" aria-selected="true"' in o["byAddr"])
    check("many rows: 25 shown, Showing 25 of 30, Show 5 more; then all, the focus on the first new row",
          "Showing 25 of 30 e-Invoices" in o["many"] and "Show 5 more</button>" in o["many"] and 'id="ei-row-24"' in o["many"] and 'id="ei-row-25"' not in o["many"]
          and 'id="ei-row-29"' in o["more"] and "Show 5 more" not in o["more"] and o["moreFocus"] == "ei-row-25", o["moreFocus"])
    check("No e-Invoices yet, with the way to SQL import",
          "No e-Invoices yet</h2>" in o["empty"] and "Nothing has been fetched from SQL Account for EXN yet." in o["empty"]
          and 'data-menu="accounting/sql">' in o["empty"] and "Open SQL import" in o["empty"] and 'role="tablist"' not in o["empty"])
    check("couldn't load: the board's title, the reason, Try again and Copy details",
          "Couldn&#39;t load the e-Invoices</h2>" in o["error"] and "The records folder can&#39;t be reached" in o["error"] and 'data-retry="1"' in o["error"]
          and "Copy details" in o["error"], o["error"][-800:])
    Hh = o["here"]
    check("a company kept here: its intro, Submission method not decided yet, Open Sales",
          "EXK · Kept here" in Hh and "EXK is kept here, so they will come from its own documents, not from SQL Account." in Hh
          and "Submission method not decided yet</h2>" in Hh and "Example Kept Ltd is kept here, so its e-Invoices don't come from SQL Account." in Hh
          and 'data-menu="accounting/sales">Open Sales' in Hh, Hh[:2500])
    check("...its tabs are there, empty in the board's words, with no print bar and no source line",
          'role="tablist"' in Hh and "No e-Invoices for EXK yet. Its invoices and notes will be listed here once Sales holds them." in Hh
          and 'id="ei-print"' not in Hh and "Where these e-Invoices come from" not in Hh and "/api/einvoices" not in "".join(o.get("checked", [])))
    Sq = o["sql"]
    check("the SQL import page no longer carries the e-Invoices card or its print bar, and its lede says they have their own page",
          ">SQL import</h1>" in Sq and 'id="sqlEinvoices"' not in Sq and 'id="invPrint"' not in Sq and "From MyInvois" not in Sq
          and "All invoices, debit and credit notes of" not in Sq
          and 'The e-Invoices this fetch reads, and the printed invoices, have their own page: <a href="#/EXV/2026-10/accounting/einvoices" data-menu="accounting/einvoices">e-Invoices</a>.' in Sq, Sq[:2500])

if failures:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    raise SystemExit(1)
print("\nAll passed.")
