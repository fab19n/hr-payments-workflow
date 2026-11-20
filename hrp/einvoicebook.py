"""Accounting › e-Invoices (slice 6): a company's e-Invoices in the lists the page shows, and the same lists as an Excel
file. Read-only: everything comes from SQL's documents fetched (sql_entries) and the copies of SQL's MyInvois
Transaction screen read by Fetch (myinvois_docs).

- Issued: SQL's customer invoices, debit notes and credit notes (as invoicepdf prints them) and any other document of
  the company's with its own e-Invoice (a refund, a cash sale), each with what its MyInvois copy says, then the
  e-Invoices issued that no SQL document has.
- Self-billed: the self-billed e-Invoices the company made, one row per payment voucher.
- Received: the e-Invoices other companies sent it, each with the SQL document it is in (or Not found), and apart the
  valid ones received that none of SQL's documents has (myinvois.view's unmatched).
- Other: those in the copies that are neither the company's nor sent to it.
An SQL document with an e-Invoice that no copy of MyInvois has yet is listed on its side's tab with SQL's own status.
lists() says how the rows are formed so that each e-Invoice and each document is shown exactly once.

Each row carries its date (YYYY-MM-DD), so the page and the export choose a month the same way: by the document's date
in SQL, or for an e-Invoice with no SQL document, the day it was issued. Nothing here names a company."""
from openpyxl import Workbook

from . import db, invoicepdf, myinvois
from .reports import DAY, MONEY, _day, _put, _table

# What each MyInvois status puts on a document, in the words SQL uses (myinvois.STATUS_WORDS).
WORDS = myinvois.STATUS_WORDS
# How a received e-Invoice was matched to an SQL document, when not by its number or its supplier's TIN and amount.
MATCHED = {"amount": "By amount", "line": "By a line's amount", "sum": "Paid together"}
# A supplier's invoice, debit note or credit note in SQL (sqlimport.doc_label).
SUPPLIER_DOCS = ("PI", "SD", "SC")


def _cols(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _mi(r):
    """What a MyInvois copy says of an e-Invoice, for a row of the page."""
    return {"uuid": r["uuid"], "type": r["type"] or "", "status": r["status"], "validated_at": r["validated_at"] or "",
            "link": myinvois.link_of(r)}


def _amount(sen):
    return None if sen is None else sen / 100


def _issued_day(r):
    return (r["issued_at"] or r["received_at"] or "")[:10]


def lists(con, ent):
    """{issued, self_billed, received, other, unmatched, sources, counts, copy, span, printing}: the rows of each list in date
    order, the copies of MyInvois read (newest first), how many e-Invoices each way, whether a copy was read at all, and
    the first and last day the copies cover.

    Built in one pass around one rule: every e-Invoice read from MyInvois is in exactly one group, every live SQL document
    with an e-Invoice (or that MyInvois links to) is in exactly one group, and no two documents share a group.
    1. The SQL documents: the live rows (not ignored, replaced by a later version or deleted in SQL), one per document as
       the import tells them apart (its number, date, kind and type: a PV and an OR may share a number and a day; when SQL
       changed its amount, the row read last, as invoicepdf.month_documents prints it). A row whose date SQL changed
       (same number, year and e-Invoice) is the same document; a replaced row stands for the live end of its chain. SQL
       restarts its numbers each year, so a number alone may be two documents.
    2. Each e-Invoice is claimed by the SQL document MyInvois links it to (entry_id), else by the document carrying its
       UUID, and the unlinked attempts at a claimed document (same way, number and year) go with it. Those no document
       claims are grouped by way, number, year issued and total: only attempts at the same document (one cancelled and
       issued again) share a group. The 'other' ones (neither the company's nor sent to it) are never claimed.
    3. Each group goes to one tab: an SQL document's issued e-Invoices to Issued, its self-billed ones to Self-billed, its
       received ones to Received (one row per supplier document it pays); a document with none, by its kind (a customer
       document to Issued, a supplier's to Received, a payment voucher to Self-billed, anything else to Issued).
    4. Each group is one row, showing the e-Invoice that speaks for it (myinvois._best); the others of the group are
       folded into it. mi_ids on every row lists the MyInvois rows it accounts for."""
    eid = ent["id"]
    mi = myinvois.view(con, ent) or {"rows": [], "unmatched": [], "sources": [], "counts": dict.fromkeys(myinvois.DIRECTIONS, 0)}
    rows = mi["rows"]
    printing = invoicepdf.ready(con)
    cols = _cols(con, "sql_entries")
    gone = "AND deleted_in_sql IS NULL" if "deleted_in_sql" in cols else ""
    # 1. the live documents, and the one each row of sql_entries stands for (canon: row id -> live document id, or none)
    every = {r["id"]: dict(r) for r in con.execute(f"SELECT * FROM sql_entries WHERE entity_id = ? AND status <> 'ignored' {gone}", (eid,))}
    num = lambda s: str(s["doc_no"] or "").strip().upper()
    key_of = lambda s: (num(s), s["doc_date"], s["kind"] or "payment", str(s["doc_type"] or "").strip().upper())
    newest = {}
    for i, s in every.items():
        if s["status"] != "superseded":
            k = key_of(s)
            newest[k] = max(newest.get(k, i), i)  # the same document read again (SQL changed its amount): the row read last
    canon = {i: newest[key_of(s)] for i, s in every.items() if s["status"] != "superseded"}
    # A document whose date SQL changed comes back as a second live row of its number and type (invoices are never
    # marked replaced). Two such rows are one document, the row read last (as invoicepdf.month_documents prints it), when
    # they carry the same e-Invoice (whatever the year: a date moved across a year end), or when they are of the same
    # year and came in different imports without carrying two different e-Invoices (sqlimport.edited's sign of an edit:
    # SQL lists one document once). Two rows of one import with one number and year can't be told from two documents,
    # and rows of different years without a shared e-Invoice are a number SQL used again: those stay apart.
    parent = {i: i for i in set(canon.values())}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    by_number = {}
    for i in sorted(parent):
        s = every[i]
        by_number.setdefault((num(s), s["kind"] or "payment", str(s["doc_type"] or "").strip().upper()), []).append(i)
    for ids in by_number.values():
        for x, i in enumerate(ids):
            for j in ids[x + 1:]:
                a, c = every[i], every[j]
                if a["einvoice"] and a["einvoice"] == c["einvoice"]:
                    one = True
                else:
                    one = (str(a["doc_date"])[:4] == str(c["doc_date"])[:4] and a["import_id"] != c["import_id"]
                           and not (a["einvoice"] and c["einvoice"]))
                if one:
                    parent[root(i)] = root(j)
    clusters = {}
    for i in parent:
        clusters.setdefault(root(i), []).append(i)
    merged = {i: max(ids) for ids in clusters.values() for i in ids}
    canon = {j: merged.get(c, c) for j, c in canon.items()}
    # A row replaced by a later version stands for the live end of its chain (A -> B -> C), however the rows are ordered.
    for i, s in every.items():
        if s["status"] == "superseded":
            seen, at = set(), i
            while at in every and every[at]["status"] == "superseded" and at not in seen:
                seen.add(at)
                at = every[at].get("superseded_by")
            canon[i] = canon.get(at)
    entries = {i: every[i] for i in set(canon.values()) if i is not None}
    # The UUID an SQL row carries, for the live document it stands for (a live row first, then an earlier version or a
    # replaced row of the chain).
    by_uuid = {}
    for s in sorted(every.values(), key=lambda s: (s["id"] not in entries, s["doc_date"], s["doc_no"], s["id"])):
        if s["einvoice"] and canon.get(s["id"]):
            by_uuid.setdefault(s["einvoice"], canon[s["id"]])

    # 2. who claims each e-Invoice: the document MyInvois links it to, else the document carrying its UUID; then the
    # unlinked attempts at a claimed document (the same way, number and year: one cancelled and issued again) go with it.
    owner_of, attempt = {}, lambda r: (r["direction"], myinvois.doc_key(r["doc_no"]), _issued_day(r)[:4])
    for r in rows:
        if r["direction"] != "other":
            owner_of[r["id"]] = (canon.get(r["entry_id"]) if r["entry_id"] else None) or by_uuid.get(r["uuid"])
    claims = {}
    for r in rows:
        if r["direction"] in ("issued", "self_billed") and owner_of.get(r["id"]):
            claims.setdefault(attempt(r), set()).add(owner_of[r["id"]])
    for r in rows:
        if r["direction"] in ("issued", "self_billed") and not owner_of.get(r["id"]) and len(claims.get(attempt(r), ())) == 1:
            owner_of[r["id"]] = next(iter(claims[attempt(r)]))
    owned, loose = {}, {}
    for r in rows:
        owner = owner_of.get(r["id"])
        if r["direction"] == "other":
            loose.setdefault(("other", r["id"]), []).append(r)
        elif owner:
            sub = myinvois.doc_key(r["doc_no"]) + "|" + (r["supplier_tin"] or "") if r["direction"] == "received" else ""
            owned.setdefault(owner, {}).setdefault((r["direction"], sub), []).append(r)
        else:
            loose.setdefault((r["direction"], myinvois.doc_key(r["doc_no"]), _issued_day(r)[:4], r["total_sen"],
                              r["supplier_tin"] if r["direction"] == "received" else ""), []).append(r)

    def sql_row(s, g, what, party, print_kind, status=None, amount=None, currency="MYR", paid_as=None):
        m = myinvois._best(g) if g else None
        return {"id": s["id"], "doc_no": s["doc_no"], "date": s["doc_date"], "description": s["description"] or "",
                "doc_type": (s["doc_type"] or "").upper(), "what": what, "party": party, "amount": s["amount"] if amount is None else amount,
                "currency": currency, "paid_as": paid_as,
                "status": status or s["einvoice_status"] or ("Has UUID" if s["einvoice"] else None), "taken_back_by": db.taken_back_by(con, s),
                "link": s["einvoice_link"] or (m and myinvois.link_of(m)), "myinvois": _mi(m) if m else None,
                "print_kind": print_kind, "payment_id": s["payment_id"], "sql_only": m is None, "mi_ids": [r["id"] for r in g]}

    def mi_row(g, what, label, name, tin):
        m = myinvois._best(g)
        return {"id": None, "doc_no": m["doc_no"], "date": _issued_day(m), "description": m["type"] or "", "doc_type": "",
                "what": what, "party": {"label": label, "name": name(m) or "", "tin": tin(m) or ""},
                "amount": _amount(m["total_sen"]), "currency": m["currency"] or "MYR", "paid_as": None,
                "status": WORDS.get(m["status"], m["status"]), "taken_back_by": None, "link": myinvois.link_of(m),
                "myinvois": _mi(m), "print_kind": None, "payment_id": None, "sql_only": False, "mi_ids": [r["id"] for r in g]}

    def recv_row(g, s=None, owner=True):
        m = myinvois._best(g)
        return {"uuid": m["uuid"], "date": _issued_day(m), "issued_at": m["issued_at"] or m["received_at"] or "",
                "validated_at": m["validated_at"] or "", "party": m["supplier_name"] or "", "tin": m["supplier_tin"] or "",
                "code": (s or {}).get("code") or "", "their": m["doc_no"] or "", "amount": _amount(m["total_sen"]),
                "currency": m["currency"] or "MYR", "status": m["status"], "link": myinvois.link_of(m),
                "in_sql": s["doc_no"] if s else "", "matched_by": MATCHED.get(m["matched_by"] or "", ""), "taken_back_by": None,
                "id": s["id"] if s and owner else None, "payment_id": s["payment_id"] if s and owner else None, "sql_only": False,
                "mi_ids": [r["id"] for r in g]}

    issued, self_billed, received = [], [], []
    buyer = {"label": "Buyer"}
    # An e-Invoice claimed by one document may also be carried (by its UUID) by another document that has no e-Invoice of
    # its own here (the supplier's invoice that a voucher pays): that document is shown on the claimed row, never again.
    uuid_owner = {r["uuid"]: o for o, groups in owned.items() for g in groups.values() for r in g}
    also = {}
    # 1 and 3: every live SQL document that is a customer document, carries an e-Invoice, or is claimed by one
    for sid in sorted((i for i, s in entries.items() if i in owned or s["einvoice"] or s["einvoice_status"]
                       or (s["kind"] == "invoice" and invoicepdf.kind_of(con, s) == "customer")),
                      key=lambda i: (entries[i]["doc_date"], entries[i]["doc_no"], i)):
        s, groups = entries[sid], owned.get(sid, {})
        if not groups and s["einvoice"] and uuid_owner.get(s["einvoice"], sid) != sid:
            also.setdefault(s["einvoice"], []).append(s)
            continue
        iss, sb = groups.get(("issued", ""), []), groups.get(("self_billed", ""), [])
        recv = [g for (way, _), g in sorted(groups.items(), key=lambda kv: kv[0]) if way == "received"]
        doc_type = (s["doc_type"] or "").upper()
        customer = s["kind"] == "invoice" and invoicepdf.kind_of(con, s) == "customer"
        shown = True
        own_apart = bool(s["einvoice"]) and s["einvoice"] not in {r["uuid"] for g in recv for r in g}  # its own e-Invoice, not one it pays
        if iss or customer:
            m = myinvois._best(iss) if iss else None
            cur = (m and m["currency"]) or "MYR"  # an invoice in another currency: the e-Invoice's currency and total
            issued.append(sql_row(s, iss, invoicepdf._printed_name(s, "customer") if customer else "document",
                                  {**buyer, "name": (m and m["buyer_name"]) or s["payee"] or "", "tin": (m and m["buyer_tin"]) or ""},
                                  "customer" if customer and printing else None,
                                  amount=_amount(m["total_sen"]) if cur != "MYR" else None, currency=cur))
        elif sb:
            m = myinvois._best(sb)
            cur = m["currency"] or "MYR"
            self_billed.append(sql_row(s, sb, "self-billed invoice", {"label": "Supplier", "name": m["supplier_name"] or "", "tin": m["supplier_tin"] or ""},
                                       "self_billed" if printing and invoicepdf.kind_of(con, s) == "self_billed" else None,
                                       status=WORDS.get(m["status"], m["status"]), amount=_amount(m["total_sen"]), currency=cur,
                                       paid_as={"amount": s["amount"], "by": s["doc_no"]} if cur != "MYR" else None))
        elif recv and not own_apart:
            shown = False
        elif s["kind"] == "invoice" and doc_type in SUPPLIER_DOCS:
            received.append({"uuid": s["einvoice"] or "", "date": s["doc_date"], "issued_at": "", "validated_at": "", "party": s["payee"] or "",
                             "tin": "", "code": s["code"] or "", "their": "", "amount": s["amount"], "currency": "MYR",
                             "status": s["einvoice_status"] or "Has UUID", "link": s["einvoice_link"], "in_sql": s["doc_no"], "matched_by": "",
                             "taken_back_by": db.taken_back_by(con, s), "id": s["id"], "payment_id": s["payment_id"], "sql_only": True, "mi_ids": []})
        elif (s["kind"] or "payment") == "payment" and s["direction"] != "in":
            self_billed.append(sql_row(s, [], "payment voucher", {"label": "Paid to", "name": s["payee"] or "", "tin": ""}, None))
        else:
            issued.append(sql_row(s, [], "document", {"label": "Party", "name": s["payee"] or "", "tin": ""}, None))
        # the supplier documents it pays: one row each; the document itself is the row's own (Unlink) only once
        for k, g in enumerate(recv):
            received.append(recv_row(g, s, owner=not shown and k == 0))
        # a self-billed e-Invoice on a document shown on Issued (a customer document) is kept apart on Self-billed
        if sb and (iss or customer):
            self_billed.append(mi_row(sb, "self-billed invoice", "Supplier", lambda m: m["supplier_name"], lambda m: m["supplier_tin"]))
    # 2. then the e-Invoices no SQL document claimed (after every document has claimed its own)
    other = []
    for (way, *_), g in loose.items():
        if way == "issued":
            issued.append(mi_row(g, "e-Invoice", "Buyer", lambda m: m["buyer_name"], lambda m: m["buyer_tin"]))
        elif way == "self_billed":
            self_billed.append(mi_row(g, "self-billed invoice", "Supplier", lambda m: m["supplier_name"], lambda m: m["supplier_tin"]))
        elif way == "received":
            received.append(recv_row(g))
        else:
            r = g[0]
            other.append({"uuid": r["uuid"], "doc_no": r["doc_no"] or "", "type": r["type"] or "", "date": _issued_day(r), "status": r["status"],
                          "supplier": r["supplier_name"] or "", "supplier_tin": r["supplier_tin"] or "", "buyer": r["buyer_name"] or "",
                          "buyer_tin": r["buyer_tin"] or "", "amount": _amount(r["total_sen"]), "currency": r["currency"] or "MYR",
                          "link": myinvois.link_of(r), "mi_ids": [r["id"]]})
    # The documents shown on another's row: on the row holding the e-Invoice they carry.
    uuid_of = {r["id"]: r["uuid"] for r in rows}
    holder = {uuid_of[i]: x for x in issued + self_billed + received for i in x["mi_ids"]}
    for u, docs in also.items():
        x = holder[u]
        x.setdefault("also", []).extend({"id": s["id"], "doc_no": s["doc_no"], "payment_id": s["payment_id"]} for s in docs)
    for x in issued + self_billed + received:
        x.setdefault("also", [])
    order = lambda x: (x["date"] or "", x.get("doc_no") or x.get("their") or x.get("in_sql") or "")
    days = sorted(d for d in (_issued_day(r) for r in rows) if d)
    # Received but in none of SQL's documents: the received rows no document claims (nor carries by UUID), valid, issued
    # from the first month tracked.
    since = f"{ent['first_month']}-01" if ent["first_month"] else ""
    by_id = {r["id"]: r for r in rows}
    unmatched = []
    for x in received:
        m = myinvois._best([by_id[i] for i in x["mi_ids"]]) if x["mi_ids"] else None
        if m and not x["in_sql"] and not x["also"] and m["status"] == "Valid" and _issued_day(m) >= since:
            unmatched.append({"doc_no": m["doc_no"], "uuid": m["uuid"], "supplier": m["supplier_name"] or "", "tin": m["supplier_tin"] or "",
                              "date": _issued_day(m), "amount": _amount(m["total_sen"]), "currency": m["currency"] or "MYR"})
    return {"issued": sorted(issued, key=order), "self_billed": sorted(self_billed, key=order), "received": sorted(received, key=order),
            "other": sorted(other, key=order),
            "unmatched": sorted(unmatched, key=lambda x: (x["date"], x["doc_no"])), "since": ent["first_month"],
            "sources": mi["sources"], "counts": mi["counts"], "copy": bool(rows), "span": [days[0], days[-1]] if days else None,
            "printing": printing}


def in_month(rows, month):
    return [x for x in rows if not month or (x["date"] or "")[:7] == month]


def workbook(con, ent, month=None):
    """The three lists of the page (and the e-Invoices received but not found in SQL's books, and those that are neither
    the company's nor sent to it) as a workbook, for one month (YYYY-MM) or every month (None): one sheet each."""
    L = lists(con, ent)
    label = db.month_label(month) if month else "all months"
    wb = Workbook()
    status = lambda x: (f"Cancelled by {x['taken_back_by']}" if x["taken_back_by"] else x["status"] or "")
    mi = lambda x, k: (x["myinvois"] or {}).get(k) or ""
    sheets = [
        ("Issued", ["Doc no.", "Date", "Document", "Description", "Buyer", "Buyer TIN", "Currency", "Amount", "e-Invoice status", "UUID",
                    "MyInvois status", "Validated", "MyInvois page"],
         [(x["doc_no"], _day(x["date"]), x["what"].capitalize(), x["description"], x["party"]["name"], x["party"]["tin"], x["currency"], x["amount"],
           status(x), mi(x, "uuid"), mi(x, "status"), mi(x, "validated_at"), x["link"] or "") for x in in_month(L["issued"], month)],
         [14, 11, 14, 34, 28, 16, 9, 13, 24, 30, 12, 18, 40], {2: DAY, 8: MONEY}),
        ("Received", ["Issued", "From", "SQL code", "Supplier TIN", "Their number", "Currency", "Amount", "Status", "Validated", "UUID",
                      "MyInvois page", "In SQL", "Matched"],
         [(_day(x["date"]), x["party"], x["code"], x["tin"], x["their"], x["currency"], x["amount"], status(x), x["validated_at"], x["uuid"],
           x["link"] or "", ", ".join(filter(None, [x["in_sql"]] + [a["doc_no"] for a in x["also"]])) or "Not found", x["matched_by"]) for x in in_month(L["received"], month)],
         [11, 28, 12, 16, 18, 9, 13, 11, 18, 30, 40, 14, 16], {1: DAY, 7: MONEY}),
        ("Self-billed", ["Doc no.", "Date", "Description", "Supplier", "Supplier TIN", "Currency", "Amount", "Paid as (MYR)", "Status", "UUID",
                         "Validated", "MyInvois page"],
         [(x["doc_no"], _day(x["date"]), x["description"], x["party"]["name"], x["party"]["tin"], x["currency"], x["amount"],
           (x["paid_as"] or {}).get("amount"), status(x), mi(x, "uuid"), mi(x, "validated_at"), x["link"] or "")
          for x in in_month(L["self_billed"], month)],
         [14, 11, 34, 28, 16, 9, 13, 13, 12, 30, 18, 40], {2: DAY, 7: MONEY, 8: MONEY}),
        ("Not found in SQL", ["Doc no.", "Supplier", "Supplier TIN", "Issued", "Currency", "Total"],
         [(x["doc_no"], x["supplier"], x["tin"], _day(x["date"]), x["currency"], x["amount"]) for x in L["unmatched"]],
         [18, 28, 16, 11, 9, 13], {4: DAY, 6: MONEY}),
        ("Other", ["Doc no.", "Type", "Issued", "Supplier", "Supplier TIN", "Buyer", "Buyer TIN", "Currency", "Amount", "Status", "UUID", "MyInvois page"],
         [(x["doc_no"], x["type"], _day(x["date"]), x["supplier"], x["supplier_tin"], x["buyer"], x["buyer_tin"], x["currency"], x["amount"],
           x["status"], x["uuid"], x["link"] or "") for x in in_month(L["other"], month)],
         [18, 18, 11, 28, 16, 28, 16, 9, 13, 11, 30, 40], {3: DAY, 9: MONEY}),
    ]
    for i, (title, heads, rows, widths, fmts) in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = title
        what = ("Valid e-Invoices received that no supplier invoice or payment voucher in SQL has, whatever month is chosen"
                if title == "Not found in SQL" else f"e-Invoices in the MyInvois copies that {ent['code']} neither issued nor received, {label}"
                if title == "Other" else f"{title} e-Invoices, {label}")
        _put(ws, 1, 1, f"{ent['name']} - {what}", bold=True)
        _put(ws, 2, 1, "From SQL's documents fetched and the copies of SQL's MyInvois Transaction screen read. Read-only: it follows SQL.")
        _table(ws, 3, heads, rows, widths, fmts)
    return wb


def report_name(ent, month=None):
    return f"{ent['code']} e-Invoices {month or 'all months'}.xlsx"
