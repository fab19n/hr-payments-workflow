r"""Slice 6: how Accounting › e-Invoices groups a company's e-Invoices and SQL documents (hrp/einvoicebook.lists), checked
on many generated, made-up companies.

Each company is built from a seeded random choice of small cases, and each case declares, on its own, what the page
must show: every group, its tab (Issued, Self-billed, Received or Other), its SQL document (or none) and the MyInvois
rows it accounts for. The cases: a customer invoice with its e-Invoice (and a cancelled attempt, linked or not); one
found only by the UUID on it, with a cancelled attempt of another total; a customer invoice with none; a number reused
in another year; a payment voucher and a receipt with the same number on the same day; an invoice whose date SQL
changed (two live rows, one e-Invoice); a voucher replaced twice (a chain A -> B -> C, the e-Invoice linked to A); a
customer invoice that MyInvois links a self-billed e-Invoice to; a refund and a cash sale with their own e-Invoice; an
e-Invoice for neither side; a received one paid by a voucher, and one in no SQL document; e-Invoices with no SQL
document, cancelled and issued again with the same total (one document) or a corrected one (two).

For every company the test checks the declared groups exactly, then the invariants: every MyInvois row is accounted
for exactly once; every SQL document shown is shown once; no two rows shown carry the same SQL e-Invoice UUID; and the
Excel file has one row per group on each sheet.

Run: .venv\Scripts\python -m synthetic_tests.einvoices_groups_test
"""
import io
import json
import os
import random
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-einvoices-groups-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, einvoicebook  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file
from openpyxl import load_workbook  # noqa: E402

(tmp / "seed.json").write_text(json.dumps({"entities": [{"code": "EXG", "name": "Example Groups Sdn Bhd",
                                                         "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-801"}]}]}),
                               encoding="utf-8")
db.init()
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:1200])


TABS = ("issued", "self_billed", "received", "other")
ME, ME_TIN = "EXAMPLE GENERATED SDN BHD", "C00000000810"


class Company:
    """One generated company: its SQL documents and MyInvois rows, and what the page must show for them."""

    def __init__(self, con, seed):
        self.con, self.rng, self.k = con, random.Random(seed), 0
        self.eid = con.execute("INSERT INTO entities (code, name, uses_sql) VALUES (?, ?, 1)", (f"G{seed:03d}", ME)).lastrowid
        if "tin" in {r[1] for r in con.execute("PRAGMA table_info(entities)")}:
            con.execute("UPDATE entities SET tin = ? WHERE id = ?", (ME_TIN, self.eid))
        imp = lambda name, at: con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, ?, ?, 0, 0)",
                                           (self.eid, name, at)).lastrowid
        self.imp, self.imp2 = imp("g.xlsx", "2026-11-18T10:00:00"), imp("g2.xlsx", "2026-11-19T10:00:00")  # a later fetch
        self.expect = []  # (tab, SQL row id or 0, sorted MyInvois row ids, sorted ids of the documents also shown on the row)
        self.unmatched = []  # the MyInvois rows that must be listed as received but not found in SQL's books
        self.seed = seed
        self.foreign = []  # (SQL row id, currency, amount) the Issued row must show

    def n(self):
        self.k += 1
        return self.k

    def uuid(self):
        return f"G{self.seed:03d}X{self.n():04d}QJKA274M3RP29RZR97"[:26]

    def day(self, year=None):
        return f"{year or self.rng.choice((2025, 2026))}-{self.rng.randint(1, 12):02d}-{self.rng.randint(1, 28):02d}"

    def entry(self, no, day, amount, kind, doc_type, direction=None, einvoice=None, status=None, row_status=None, later=False):
        return self.con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, description, payee, amount, direction, doc_type, kind,
                                   status, einvoice, einvoice_status) VALUES (?, ?, ?, ?, ?, 'EXAMPLE PARTY', ?, ?, ?, ?, ?, ?, ?)""",
                                (self.imp2 if later else self.imp, self.eid, no, day, f"EXAMPLE {no}", amount, direction, doc_type, kind,
                                 row_status or ("invoice" if kind == "invoice" else "unlinked"), einvoice, status)).lastrowid

    def mi(self, no, direction, day, status="Valid", total=10000, entry=None, uuid=None, currency="MYR", supplier_tin=None):
        sup, sup_tin, buy, buy_tin = {"issued": (ME, ME_TIN, "EXAMPLE BUYER", "C00000000820"),
                                      "self_billed": ("EXAMPLE OVERSEAS", "EI00000000080", ME, ME_TIN),
                                      "received": ("EXAMPLE SUPPLIER", "C00000000830", ME, ME_TIN),
                                      "other": ("EXAMPLE THIRD", "C00000000840", "EXAMPLE FOURTH", "C00000000850")}[direction]
        typ = "Self-billed Invoice" if direction == "self_billed" else "Invoice"
        return self.con.execute("""INSERT INTO myinvois_docs (entity_id, uuid, doc_no, type, currency, supplier_name, supplier_tin, buyer_name, buyer_tin,
                                   issued_at, status, total_sen, direction, as_at, entry_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-11-17T16:00:00', ?)""",
                                (self.eid, uuid or self.uuid(), no, typ, currency, sup, supplier_tin or sup_tin, buy, buy_tin, day + " 10:00:00", status, total,
                                 direction, entry)).lastrowid

    def want(self, tab, doc, mis, also=()):
        self.expect.append((tab, doc or 0, tuple(sorted(mis)), tuple(sorted(also))))

    # ---- the cases ----
    def linked_invoice(self):
        no, day, u = f"IV-{self.n():05d}", self.day(), self.uuid()
        doc = self.entry(no, day, 100.0, "invoice", "IV", "in", u, "Validated")
        mis = [self.mi(no, "issued", day, entry=doc, uuid=u)]
        how = self.rng.choice(("none", "linked", "unlinked"))
        if how != "none":  # an earlier attempt, cancelled: linked to it by MyInvois, or not
            mis.append(self.mi(no, "issued", day[:4] + "-01-01", "Cancelled", entry=doc if how == "linked" else None))
        self.want("issued", doc, mis)

    def uuid_only_invoice(self):
        no, day, u = f"IV-{self.n():05d}", self.day(), self.uuid()
        doc = self.entry(no, day, 120.0, "invoice", "IV", "in", u, "Validated")
        mis = [self.mi(no, "issued", day, uuid=u), self.mi(no, "issued", day[:4] + "-01-02", "Cancelled", total=11000)]  # neither linked
        self.want("issued", doc, mis)

    def plain_invoice(self):
        no = f"IV-{self.n():05d}"
        self.want("issued", self.entry(no, self.day(), 80.0, "invoice", "IV", "in"), [])

    def reused_number(self):
        no = f"IV-{self.n():05d}"
        for year in (2025, 2026):
            day, u = self.day(year), self.uuid()
            doc = self.entry(no, day, 50.0 + year % 10, "invoice", "IV", "in", u, "Validated")
            self.want("issued", doc, [self.mi(no, "issued", day, entry=doc, uuid=u)])

    def same_day_types(self):
        no, day = f"{self.n():05d}", self.day()
        self.want("self_billed", self.entry(no, day, 30.0, "payment", "PV", "out", None, "Validated"), [])
        self.want("issued", self.entry(no, day, 31.0, "payment", "OR", "in", None, "Validated"), [])

    def date_edited(self):
        no, u, year = f"IV-{self.n():05d}", self.uuid(), self.rng.choice((2025, 2026))
        first = self.entry(no, f"{year}-03-10", 90.0, "invoice", "IV", "in", u, "Validated")
        last = self.entry(no, f"{year}-03-12", 90.0, "invoice", "IV", "in", u, "Validated")  # read again after SQL changed its date
        self.want("issued", last, [self.mi(no, "issued", f"{year}-03-10", entry=first, uuid=u)])

    def chain(self):
        no = f"PV-{self.n():05d}"
        a = self.entry(no, "2026-05-01", 40.0, "payment", "PV", "out", self.uuid(), "Validated", "superseded")
        b = self.entry(no, "2026-05-02", 41.0, "payment", "PV", "out", None, None, "superseded")
        c = self.entry(no, "2026-05-03", 42.0, "payment", "PV", "out")
        self.con.execute("UPDATE sql_entries SET superseded_by = ? WHERE id = ?", (b, a))
        self.con.execute("UPDATE sql_entries SET superseded_by = ? WHERE id = ?", (c, b))
        self.want("self_billed", c, [self.mi(no, "self_billed", "2026-05-01", entry=a)])

    def customer_self_billed(self):
        no, day = f"IV-{self.n():05d}", self.day()
        doc = self.entry(no, day, 60.0, "invoice", "IV", "in")
        self.want("issued", doc, [])
        self.want("self_billed", 0, [self.mi(no, "self_billed", day, entry=doc)])

    def refund(self):
        no, day, u = f"OR-{self.n():05d}", self.day(), self.uuid()
        doc = self.entry(no, day, 25.0, "payment", "OR", "in", u, "Validated")
        self.want("issued", doc, [self.mi(no, "issued", day, entry=doc, uuid=u)])

    def cash_sale(self):
        no, day, u = f"CS-{self.n():05d}", self.day(), self.uuid()
        doc = self.entry(no, day, 15.0, "payment", "CS", "in", u, "Validated")
        self.want("issued", doc, [self.mi(no, "issued", day, uuid=u)])

    def other(self):
        self.want("other", 0, [self.mi(f"XX-{self.n():05d}", "other", self.day())])

    def received(self):
        no, day = f"PV-{self.n():05d}", self.day()
        doc = self.entry(no, day, 70.0, "payment", "PV", "out")
        self.want("received", doc, [self.mi(f"SUP-{self.n():05d}", "received", day, total=7000, entry=doc)])
        orphan = self.mi(f"SUP-{self.n():05d}", "received", day)
        self.want("received", 0, [orphan])
        self.unmatched.append(orphan)

    def orphan_reissued(self):
        no, year = f"IV-{self.n():05d}", self.rng.choice((2025, 2026))
        first = self.mi(no, "issued", f"{year}-06-01", "Cancelled")
        if self.rng.random() < 0.5:  # issued again with the same total: one document
            self.want("issued", 0, [first, self.mi(no, "issued", f"{year}-06-02")])
        else:  # a corrected total: two documents
            self.want("issued", 0, [first])
            self.want("issued", 0, [self.mi(no, "issued", f"{year}-06-02", total=12345)])

    def amount_change(self):  # read again after SQL changed its amount: the row read last
        no, day = f"IV-{self.n():05d}", self.day()
        first = self.entry(no, day, 100.0, "invoice", "IV", "in")
        last = self.entry(no, day, 110.0, "invoice", "IV", "in", later=True)
        self.want("issued", last, [self.mi(no, "issued", day, entry=first)])

    def attempt_other_year(self):  # an unlinked attempt of another year is not the document's
        no = f"IV-{self.n():05d}"
        doc = self.entry(no, "2026-02-10", 100.0, "invoice", "IV", "in")
        self.want("issued", doc, [self.mi(no, "issued", "2026-02-10", entry=doc)])
        self.want("issued", 0, [self.mi(no, "issued", "2025-12-20", "Cancelled")])

    def loose_two_years(self):  # no SQL document, the same number and total in two years: two documents
        no = f"IV-{self.n():05d}"
        for year in (2025, 2026):
            self.want("issued", 0, [self.mi(no, "issued", f"{year}-04-04")])

    def reused_no_uuid(self):  # the same number in two years, no e-Invoice, read in two fetches: two documents
        no = f"IV-{self.n():05d}"
        self.want("issued", self.entry(no, "2025-07-07", 70.0, "invoice", "IV", "in"), [])
        self.want("issued", self.entry(no, "2026-07-07", 70.0, "invoice", "IV", "in", later=True), [])

    def one_import_no_uuid(self):  # one listing holding a number twice in a year can't be told from two documents: kept apart
        no, year = f"IV-{self.n():05d}", self.rng.choice((2025, 2026))
        self.want("issued", self.entry(no, f"{year}-08-01", 80.0, "invoice", "IV", "in"), [])
        self.want("issued", self.entry(no, f"{year}-08-09", 81.0, "invoice", "IV", "in"), [])

    def edit_no_uuid(self):  # a date SQL changed, read in a later fetch, neither row with an e-Invoice: one document
        no, year = f"IV-{self.n():05d}", self.rng.choice((2025, 2026))
        self.entry(no, f"{year}-09-01", 90.0, "invoice", "IV", "in")
        self.want("issued", self.entry(no, f"{year}-09-03", 90.0, "invoice", "IV", "in", later=True), [])

    def edit_later_uuid(self):  # only the later row carries the e-Invoice, MyInvois links it to the earlier: one document
        no, year, u = f"IV-{self.n():05d}", self.rng.choice((2025, 2026)), self.uuid()
        first = self.entry(no, f"{year}-10-01", 95.0, "invoice", "IV", "in")
        last = self.entry(no, f"{year}-10-04", 95.0, "invoice", "IV", "in", u, "Validated", later=True)
        self.want("issued", last, [self.mi(no, "issued", f"{year}-10-01", entry=first, uuid=u)])

    def edit_across_year(self):  # a date moved across a year end, the same e-Invoice on both rows: one document
        no, u = f"IV-{self.n():05d}", self.uuid()
        first = self.entry(no, "2025-12-31", 99.0, "invoice", "IV", "in", u, "Validated")
        last = self.entry(no, "2026-01-02", 99.0, "invoice", "IV", "in", u, "Validated", later=True)
        self.want("issued", last, [self.mi(no, "issued", "2025-12-31", entry=first, uuid=u)])

    def two_suppliers_same_number(self):  # a voucher paying two suppliers' e-Invoices that share a number: two rows
        no, day, their = f"PV-{self.n():05d}", self.day(), f"INV-{self.n():05d}"
        doc = self.entry(no, day, 150.0, "payment", "PV", "out")
        self.want("received", doc, [self.mi(their, "received", day, entry=doc, supplier_tin="C00000000831")])
        self.want("received", 0, [self.mi(their, "received", day, entry=doc, supplier_tin="C00000000832")])

    def deleted_in_sql(self):  # a document deleted in SQL is not shown; its e-Invoice is, on its own
        no, day, u = f"IV-{self.n():05d}", self.day(), self.uuid()
        doc = self.entry(no, day, 45.0, "invoice", "IV", "in", u, "Validated")
        self.con.execute("UPDATE sql_entries SET deleted_in_sql = '2026-11-18T09:00:00' WHERE id = ?", (doc,))
        self.want("issued", 0, [self.mi(no, "issued", day, entry=doc, uuid=u)])

    def superseded_uuid(self):  # the UUID is on a replaced row, MyInvois links nothing: the live end of the chain
        no, u = f"PV-{self.n():05d}", self.uuid()
        a = self.entry(no, "2026-06-01", 40.0, "payment", "PV", "out", u, "Validated", "superseded")
        c = self.entry(no, "2026-06-03", 42.0, "payment", "PV", "out", later=True)
        self.con.execute("UPDATE sql_entries SET superseded_by = ? WHERE id = ?", (c, a))
        self.want("self_billed", c, [self.mi(no, "self_billed", "2026-06-01", uuid=u)])

    def pi_carries_paid_by_pv(self):  # the PI carries the UUID, MyInvois links the e-Invoice to the PV: one row, both documents
        day, u = self.day(), self.uuid()
        pi = self.entry(f"PI-{self.n():05d}", day, 66.0, "invoice", "PI", None, u, "Validated")
        pv = self.entry(f"PV-{self.n():05d}", day, 66.0, "payment", "PV", "out")
        self.want("received", pv, [self.mi(f"SUP-{self.n():05d}", "received", day, total=6600, entry=pv, uuid=u)], [pi])

    def pi_carries_unlinked(self):  # the PI carries the UUID, MyInvois links nothing: in SQL, so never "not found"
        day, u = self.day(), self.uuid()
        pi = self.entry(f"PI-{self.n():05d}", day, 67.0, "invoice", "PI", None, u, "Validated")
        self.want("received", pi, [self.mi(f"SUP-{self.n():05d}", "received", day, total=6700, uuid=u)])

    def foreign_invoice(self):  # an invoice in US dollars: the row says USD and the e-Invoice's total
        no, day = f"IV-{self.n():05d}", self.day()
        doc = self.entry(no, day, 470.0, "invoice", "IV", "in")
        self.want("issued", doc, [self.mi(no, "issued", day, entry=doc, currency="USD", total=10000)])
        self.foreign.append((doc, "USD", 100.0))

    def pv_own_and_received(self):  # a voucher with its own self-billed UUID (no copy has it yet) that also pays a received one
        no, day = f"PV-{self.n():05d}", self.day()
        pv = self.entry(no, day, 77.0, "payment", "PV", "out", self.uuid(), "Validated")
        self.want("self_billed", pv, [])
        self.want("received", 0, [self.mi(f"SUP-{self.n():05d}", "received", day, total=7700, entry=pv)])

    CASES = ("linked_invoice", "uuid_only_invoice", "plain_invoice", "reused_number", "same_day_types", "date_edited", "chain",
             "customer_self_billed", "refund", "cash_sale", "other", "received", "orphan_reissued", "amount_change", "attempt_other_year",
             "loose_two_years", "reused_no_uuid", "one_import_no_uuid", "edit_no_uuid", "edit_later_uuid", "edit_across_year",
             "two_suppliers_same_number", "deleted_in_sql", "superseded_uuid", "pi_carries_paid_by_pv", "pi_carries_unlinked",
             "foreign_invoice", "pv_own_and_received")


SEEDS = range(1, 41)
companies = []
con = db.connect()
con.arm("user", "test: generated companies")
try:
    for seed in SEEDS:
        co = Company(con, seed)
        picks = [co.rng.choice(Company.CASES) for _ in range(co.rng.randint(4, 9))]
        if seed <= len(Company.CASES):
            picks.append(Company.CASES[seed - 1])  # every case at least once
        for case in picks:
            getattr(co, case)()
        companies.append((co.eid, co.expect, picks, co.unmatched, co.foreign))
    con.commit()
finally:
    con.disarm()

seen_cases = set()
for eid, expect, picks, unmatched, foreign in companies:
    ent = con.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
    L = einvoicebook.lists(con, ent)
    tag = f"company {ent['code']} ({', '.join(picks)})"
    shown = sorted((k, x.get("id") or 0, tuple(sorted(x["mi_ids"])), tuple(sorted(a["id"] for a in x.get("also", [])))) for k in TABS for x in L[k])
    ok = shown == sorted(expect)
    check(f"{tag}: the declared groups, exactly", ok,
          {"shown, not declared": [g for g in shown if g not in expect], "declared, not shown": [g for g in sorted(expect) if g not in shown]})
    if ok:
        seen_cases.update(picks)
    all_mi = sorted(r[0] for r in con.execute("SELECT id FROM myinvois_docs WHERE entity_id = ?", (eid,)))
    check(f"{tag}: every MyInvois row is accounted for exactly once", sorted(i for k in TABS for x in L[k] for i in x["mi_ids"]) == all_mi)
    owners = [x["id"] for k in TABS[:3] for x in L[k] if x.get("id")] + [a["id"] for k in TABS[:3] for x in L[k] for a in x.get("also", [])]
    check(f"{tag}: every SQL document shown is shown once", len(owners) == len(set(owners)), owners)
    sql_uuid = lambda i: con.execute("SELECT einvoice FROM sql_entries WHERE id = ?", (i,)).fetchone()[0]
    mi_uuid = {r[0]: r[1] for r in con.execute("SELECT id, uuid FROM myinvois_docs WHERE entity_id = ?", (eid,))}
    per_row = []  # every UUID a row stands for: its e-Invoices', its document's and the documents also shown on it
    for k in TABS:
        for x in L[k]:
            us = {mi_uuid[i] for i in x["mi_ids"]} | {sql_uuid(i) for i in [x.get("id")] + [a["id"] for a in x.get("also", [])] if i}
            per_row += sorted(u for u in us if u)
    check(f"{tag}: no two rows shown carry the same e-Invoice UUID (SQL's or MyInvois's)", len(per_row) == len(set(per_row)),
          [u for u in per_row if per_row.count(u) > 1])
    got = sorted(u["uuid"] for u in L["unmatched"])
    check(f"{tag}: received but not found in SQL's books: exactly the declared ones", got == sorted(mi_uuid[i] for i in unmatched),
          (got, sorted(mi_uuid[i] for i in unmatched)))
    rows_by_id = {x["id"]: x for x in L["issued"] if x.get("id")}
    check(f"{tag}: an invoice in another currency shows the e-Invoice's currency and total",
          all((rows_by_id[i]["currency"], rows_by_id[i]["amount"]) == (cur, amt) for i, cur, amt in foreign), foreign)
    wb = load_workbook(io.BytesIO(__import__("hrp.reports", fromlist=["workbook_bytes"]).workbook_bytes(einvoicebook.workbook(con, ent))))
    counts = [max(0, wb[s].max_row - 3) for s in ("Issued", "Self-billed", "Received", "Other")]
    check(f"{tag}: the Excel file has one row per declared group on each sheet",
          counts == [sum(1 for k, *_ in expect if k == t) for t in TABS], counts)
check("every case was generated and passed at least once", seen_cases == set(Company.CASES), sorted(set(Company.CASES) - seen_cases))
con.close()

if failures:
    print("\n%d failed" % len(failures))
    raise SystemExit(1)
print(f"\nAll passed ({len(companies)} generated companies).")
