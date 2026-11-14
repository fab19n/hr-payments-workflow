"""Three fixes to the bank statement review, on made-up records only.

1. A matched line counts as explained: the review's rows carry the payment's id, so the "Explained by" sort and a search
   for "not explained" on the page only treat the lines still to explain as not explained.
2. The "keep the voucher/payment date" tick only shows on a line that still needs it: once a line is confirmed, the
   server says no tick is needed (needs_date_tick), the page shows none, and applying that row again needs none either.
   Undoing and linking the line again takes its confirmation away, so the tick is asked for again. Applying a confirmed
   row as it is changes nothing, not even its payment's paid date when a voucher was linked after it was confirmed.
3. The book opening only takes a well-formed amount: the page refuses "25abc" or "1.2.3" instead of saving 25 or 1.2,
   and the server refuses anything that isn't a number (a string included), whatever the page sends.

The page's own logic (the sort key, the search text, the date tick, reading a typed amount) is run with Node on the
rows the server returns, taken straight from static/app.js.

Run: .venv\\Scripts\\python -m synthetic_tests.recon_review_fixes_test
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-recon-review-fixes-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXR", "name": "Example Review Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

APP_JS = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")


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


def part(pattern, what):
    """A piece of static/app.js, found by a pattern (the test stops when it isn't there)."""
    m = re.search(pattern, APP_JS, re.S | re.M)
    check(f"static/app.js has {what}", m is not None)
    return m.group(0)


def node(script):
    """Runs a piece of JavaScript with Node and returns what it printed as JSON."""
    f = tmp / "page.js"
    f.write_text(script, encoding="utf-8")
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
    check("the page's code runs in Node", out.returncode == 0, out.stderr[-800:])
    return json.loads(out.stdout)


LT_BLOCK = part(r"// LT-BEGIN.*?// LT-END", "the pure helpers (LT)")

EID = q("SELECT id FROM entities WHERE code = 'EXR'")[0]["id"]
AID = q("SELECT id FROM accounts WHERE entity_id = ?", (EID,))[0]["id"]
MONTH = "2026-10"

# ---------- a made-up statement: confirmed and unconfirmed matched lines, a bank charge, an open line ----------
con = db.connect()
con.arm("user", "test: a made-up statement to review")


def pay(desc, amount, paid, direction="out"):
    """A payment with a paid date typed in (so the books have a date of their own for it)."""
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date,
                          direction, created_at) VALUES (?, ?, ?, 'other', ?, ?, ?, ?, ?, ?)""",
                       (EID, MONTH, AID, desc, amount, paid, paid, direction, db.now())).lastrowid


P_RENT = pay("Example office rent", 1000, "2026-10-05")
P_FEES = pay("Example audit fees", 500, "2026-10-10")
P_UTIL = pay("Example utilities", 200, "2026-10-15")
P_SPARE = pay("Example courier", 500, "2026-10-09")
sid = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, ?, 10000, 8595, ?, 1)",
                  (AID, MONTH, db.now())).lastrowid
LINES = [  # line_no, date, description, amount, balance, payment, status, note, confirmed
    (1, "2026-10-08", "EXAMPLE RENT TRANSFER", -1000, 9000, P_RENT, "matched", None, db.now()),
    (2, "2026-10-12", "EXAMPLE AUDIT TRANSFER", -500, 8500, P_FEES, "matched", None, None),
    (3, "2026-10-15", "EXAMPLE UTILITIES", -200, 8300, P_UTIL, "matched", None, None),
    (4, "2026-10-20", "SERVICE CHARGE", -5, 8295, None, "no_docs", "Bank charges", None),
    (5, "2026-10-25", "EXAMPLE CUSTOMER CREDIT", 300, 8595, None, "unmatched", None, None),
]
for no, day, desc, amt, bal, pid, status, note, conf in LINES:
    con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status,
                   note, confirmed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (sid, no, day, desc, amt, bal, pid, status, note, conf))
con.commit()
con.close()
LID = {r["line_no"]: r["id"] for r in q("SELECT id, line_no FROM statement_lines WHERE statement_id = ?", (sid,))}


def review():
    return j("get", f"/api/recon/review?entity_id={EID}&statement_id={sid}")


def rows_by_no(d):
    return {r["line_no"]: r for r in d["lines"]}


# ---------- 1. matched lines count as explained ----------
d = review()
R = rows_by_no(d)
check("a matched row carries the id of its payment", R[1].get("payment_id") == P_RENT and R[2].get("payment_id") == P_FEES
      and R[3].get("payment_id") == P_UTIL, {k: v.get("payment_id") for k, v in R.items()})
check("an explained or open row has no payment id", R[4].get("payment_id", "missing") is None and R[5].get("payment_id", "missing") is None,
      (R[4].get("payment_id", "missing"), R[5].get("payment_id", "missing")))

BANK_TEXT = part(r"^const bankText = .*?;$", "the search text of a bank line (bankText)")
BY_KEY = re.search(r'by: \["text", (.+?)\] \},', part(r"^  bank: \{.*?\n  sql:", "the bank list's sorts")).group(1)
page = node(f"""
const fmtDate = x => x;
{LT_BLOCK}
{BANK_TEXT}
const by = {BY_KEY};
const rows = {json.dumps(d["lines"])};
console.log(JSON.stringify({{
  notExplained: rows.filter(l => LT.match(bankText(l, "MYR"), "not explained")).map(l => l.line_no),
  noDocs: rows.filter(l => LT.match(bankText(l, "MYR"), "no documents needed")).map(l => l.line_no),
  byPayee: rows.filter(l => LT.match(bankText(l, "MYR"), "office rent")).map(l => l.line_no),
  keys: Object.fromEntries(rows.map(l => [l.line_no, by(l)])),
  sorted: LT.sort(rows, by, "text", 1).map(l => l.line_no),
}}));
""")
check("a search for 'not explained' finds only the line still to explain", page["notExplained"] == [5], page)
check("a search for 'no documents needed' finds the bank charge", page["noDocs"] == [4], page)
check("a search for the payment's description finds its matched line", page["byPayee"] == [1], page)
check("the Explained by sort reads the payment for a matched line and the reason for an explained one",
      page["keys"] == {"1": "Example office rent", "2": "Example audit fees", "3": "Example utilities", "4": "No documents needed",
                       "5": "Not explained"}, page["keys"])
check("sorted by Explained by, the open line sits among the others by its words, not with every matched line",
      page["sorted"] == [2, 1, 3, 4, 5], page["sorted"])

# ---------- 2. the date tick only where it is still needed ----------
check("the server says a confirmed line needs no date tick, though its date differs", R[1]["gap_days"] == 3 and R[1].get("needs_date_tick") is False,
      (R[1]["gap_days"], R[1].get("needs_date_tick")))
check("an unconfirmed matched line whose date differs needs the tick", R[2]["gap_days"] == 2 and R[2].get("needs_date_tick") is True,
      (R[2]["gap_days"], R[2].get("needs_date_tick")))
check("a line whose dates agree, a bank charge and an open line need none from the server",
      all(R[n].get("needs_date_tick") is False for n in (3, 4, 5)), {n: R[n].get("needs_date_tick") for n in (3, 4, 5)})

NEEDS_TICK = part(r"^function rvNeedsTick\(l\) \{.*?^\}$", "the date tick a row needs (rvNeedsTick)")


def page_ticks(lines):
    """What the page's rvNeedsTick gives for each row (none of them with a payment chosen in its dropdown)."""
    return node(f"""
const V = {{ choice: {{}}, d: {{ payments: [] }} }}, RV = () => V, rvGap = () => null, rvPay = () => null;
{NEEDS_TICK}
console.log(JSON.stringify(Object.fromEntries({json.dumps(lines)}.map(l => [l.line_no, rvNeedsTick(l)]))));
""")


t = page_ticks(d["lines"])
check("the page shows no tick on the confirmed line", t["1"] is None, t)
check("the page shows the tick on the unconfirmed line whose date differs", t["2"] and t["2"]["days"] == 2 and t["2"]["kind"] == "payment"
      and t["2"]["date"] == "2026-10-10", t)
check("and none on the others", all(t[n] is None for n in ("3", "4", "5")), t)

body = {"entity_id": EID, "statement_id": sid, "checked": True}
j("post", "/api/recon/apply", json={**body, "rows": [{"line_id": LID[1]}]})
check("applying the confirmed line again asks for no tick, and changes nothing", q("SELECT confirmed_at FROM statement_lines WHERE id = ?", (LID[1],))[0]["confirmed_at"])
r = j("post", "/api/recon/apply", expect=400, json={**body, "rows": [{"line_id": LID[2]}]})
check("an unconfirmed line whose date differs still needs its tick to be applied", "keep the payment date" in r["error"], r)

r = j("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": sid})
check("Confirm all matched confirms what it can and counts only the unconfirmed line left for a tick",
      r["confirmed"] == 2 and r["needs_date_tick"] == 1, r)
R = rows_by_no(review())
check("after it, only that line still needs the tick", [n for n, x in R.items() if x["needs_date_tick"]] == [2], R)
r = j("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": sid})
check("asked again, nothing is confirmed and the same one line is left", r["confirmed"] == 0 and r["needs_date_tick"] == 1, r)

j("post", "/api/recon/apply", json={**body, "rows": [{"line_id": LID[2], "keep_date": True}]})
d = review()
R = rows_by_no(d)
check("once ticked and confirmed, no line needs the tick", R[2]["confirmed_at"] and not any(x["needs_date_tick"] for x in d["lines"]), R[2])
check("and the page shows none", all(v is None for v in page_ticks(d["lines"]).values()))
r = j("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": sid})
check("Confirm all matched has nothing left for a tick", r["confirmed"] == 0 and r["needs_date_tick"] == 0, r)

# Undo the confirmed line and link it to another payment: its confirmation goes, so the tick is asked for again.
j("post", f"/api/statement-lines/{LID[2]}", json={"payment_id": None})
R = rows_by_no(review())
check("undone, the line is open with no payment, no confirmation and no tick", R[2]["state"] == "open" and R[2]["payment_id"] is None
      and not R[2]["confirmed_at"] and R[2]["needs_date_tick"] is False, R[2])
j("post", f"/api/statement-lines/{LID[2]}", json={"payment_id": P_SPARE})
d = review()
R = rows_by_no(d)
check("linked again to a payment dated otherwise, it is unconfirmed and needs the tick again",
      R[2]["payment_id"] == P_SPARE and not R[2]["confirmed_at"] and R[2]["gap_days"] == 3 and R[2]["needs_date_tick"] is True, R[2])
check("and the page shows it again", (page_ticks(d["lines"])["2"] or {}).get("days") == 3)
r = j("post", "/api/recon/confirm-matched", json={"entity_id": EID, "statement_id": sid})
check("Confirm all matched counts it as left for a tick", r["confirmed"] == 0 and r["needs_date_tick"] == 1, r)
r = j("post", "/api/recon/confirm", expect=400, json={"entity_id": EID, "statement_id": sid, "line_ids": [LID[2]]})
check("and confirming it on its own still asks for the tick", "keep the payment date" in r["error"], r)

# A confirmed line that gets an SQL voucher linked to its payment afterwards: applying that row as it is changes nothing,
# the payment's paid date included. Only the tick, when a person gives it, moves the paid date to the voucher's.
M2 = "2026-11"
con = db.connect()
con.arm("user", "test: confirmed lines that get a voucher afterwards")


def pay2(desc, paid, source):
    return con.execute("""INSERT INTO payments (entity_id, month, account_id, category, description, amount, due_date, paid_date,
                          paid_source, direction, created_at) VALUES (?, ?, ?, 'other', ?, 100, ?, ?, ?, 'out', ?)""",
                       (EID, M2, AID, desc, paid, paid, source, db.now())).lastrowid


P_TYPED = pay2("Example cleaning", "2026-11-05", None)  # paid date typed in, its first voucher on the same day
P_BANK = pay2("Example parking", "2026-11-08", "bank")  # paid date taken from the bank line
P_TICK = pay2("Example stationery", "2026-11-18", "bank")  # the same, and this one's row will be ticked
sid2 = con.execute("INSERT INTO statements (account_id, month, opening, closing, imported_at, check_ok) VALUES (?, ?, 1000, 700, ?, 1)",
                   (AID, M2, db.now())).lastrowid
for no, day, pid, bal in [(1, "2026-11-08", P_TYPED, 900), (2, "2026-11-08", P_BANK, 800), (3, "2026-11-18", P_TICK, 700)]:
    con.execute("""INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status,
                   confirmed_at) VALUES (?, ?, ?, 'EXAMPLE TRANSFER', -100, ?, ?, 'matched', ?)""", (sid2, no, day, bal, pid, db.now()))
iid = con.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'example.csv', ?, 4, 4)",
                  (EID, db.now())).lastrowid
for doc, day, pid in [("PV-901", "2026-11-05", P_TYPED), ("PV-902", "2026-11-07", P_TYPED), ("PV-903", "2026-11-05", P_BANK),
                      ("PV-904", "2026-11-16", P_TICK)]:
    con.execute("""INSERT INTO sql_entries (import_id, entity_id, doc_no, doc_date, amount, direction, kind, payment_id, status)
                   VALUES (?, ?, ?, ?, 100, 'out', 'payment', ?, 'linked')""", (iid, EID, doc, day, pid))
con.commit()
con.close()
LID2 = {r["line_no"]: r["id"] for r in q("SELECT id, line_no FROM statement_lines WHERE statement_id = ?", (sid2,))}
R2 = rows_by_no(j("get", f"/api/recon/review?entity_id={EID}&statement_id={sid2}"))
check("a confirmed line whose payment got a voucher afterwards shows a voucher gap but no tick",
      [(R2[n]["gap_days"], R2[n].get("book_date_kind"), R2[n]["needs_date_tick"]) for n in (1, 2, 3)]
      == [(1, "voucher", False), (3, "voucher", False), (2, "voucher", False)], R2)


def paid(pid):
    p = q("SELECT paid_date, paid_source FROM payments WHERE id = ?", (pid,))[0]
    return p["paid_date"], p["paid_source"]


body2 = {"entity_id": EID, "statement_id": sid2, "checked": True}
r = j("post", "/api/recon/apply", json={**body2, "rows": [{"line_id": LID2[1]}, {"line_id": LID2[2]}]})
check("applying those confirmed rows as they are counts nothing", {k: r[k] for k in ("linked", "created", "explained", "confirmed")} == {"linked": 0, "created": 0, "explained": 0, "confirmed": 0}, r)
check("and leaves a typed paid date where it was, though a later voucher is nearer the bank's date",
      paid(P_TYPED) == ("2026-11-05", None), paid(P_TYPED))
check("and leaves a paid date taken from the bank where it was, though the voucher is dated otherwise",
      paid(P_BANK) == ("2026-11-08", "bank"), paid(P_BANK))
j("post", "/api/recon/apply", json={**body2, "rows": [{"line_id": LID2[3], "keep_date": True}]})
check("ticking \"keep the voucher date\" on such a row still gives the payment the voucher's date",
      paid(P_TICK) == ("2026-11-16", "sql"), paid(P_TICK))

# ---------- 3. the book opening takes only a well-formed amount ----------
OB = {"entity_id": EID, "account_id": AID, "month": MONTH}
for bad in ["25abc", "25", "1.2.3", "", True, None, [25], {"amount": 25}]:
    r = j("post", "/api/recon/book-opening", expect=400, json={**OB, "amount": bad})
    check(f"the server refuses the book opening {bad!r}", r["error"] == "Type the book balance as a number.", r)
check("and keeps none of them", not q("SELECT * FROM book_openings WHERE account_id = ?", (AID,)))
for good, kept in [(25367.58, 25367.58), (-1200, -1200.0), (0, 0.0)]:
    j("post", "/api/recon/book-opening", json={**OB, "amount": good})
    got = q("SELECT amount FROM book_openings WHERE account_id = ? AND month = ?", (AID, MONTH))[0]["amount"]
    check(f"the server keeps the number {good!r}", got == kept, got)

handler = part(r'if \(ev\.target\.id === "openingForm"\) \{.*?\n  \}', "the book opening form's handler")
check("the opening form reads the amount with the page's amount reader, not parseFloat",
      "LT.typedAmount(" in handler and "parseFloat" not in handler, handler)
typed = ["25,367.58", "25367.58", "  1,000  ", "-1,200.50", "(1,200.50)", "( 300 )", "0", "0.5", "7.", "25abc", "1.2.3", "1,23",
         "12,3456", "1.234", "", "  ", "-", "()", "(5", "5)", "--5", "-(5)", "abc", "1e3", "0x10", "Infinity", ",100", "RM 100"]
got = node(f"""
{LT_BLOCK}
console.log(JSON.stringify({json.dumps(typed)}.map(s => LT.typedAmount(s))));
""")
want = [25367.58, 25367.58, 1000, -1200.5, -1200.5, -300, 0, 0.5, None, None, None, None,
        None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None]
for s, g, w in zip(typed, got, want):
    check(f"the page reads {s!r} as {w!r}", g == w, g)

print("All recon review fixes checks passed.")
