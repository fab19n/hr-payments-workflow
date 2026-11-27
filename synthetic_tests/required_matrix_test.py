"""The Required documents grid (slice 9c), on made-up records.

Part 1, the server: the view of one payroll month (what each type needs then, the later sets a save from it would replace,
what following every company would give, the companies with their own set), and a save of several types at once: one change
of the audit trail with its one reason and a line for each type, all or nothing (a refusal or a failure on any type keeps
nothing), refused when the records are no longer what the page showed or the month is filed, previewed without keeping
anything, and writing only the types named, each exactly as a save of that type alone writes it.

Run: .venv\\Scripts\\python -m synthetic_tests.required_matrix_test
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-required-matrix-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, masters, rulebook  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.flags import KEEP_GOING  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}]},
    {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed, failed = [], []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:900]}" if detail else ""))
        if not KEEP_GOING:
            sys.exit(1)
        failed.append(name)
        return
    passed.append(name)
    print(f"PASS {name}")


db.init()
client = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def send(method, path, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    return r.status_code, r.get_json(silent=True) or {}


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


EXA, EXB = [r["id"] for r in q("SELECT id FROM entities ORDER BY id")]
RQ = "/api/setup/required"
M0 = db.current_cycle()
M1, M2, M3, MP = db.shift_month(M0, 1), db.shift_month(M0, 2), db.shift_month(M0, 3), db.shift_month(M0, -1)
for e in (EXA, EXB):
    for m in (MP, M0, M1, M2):
        call("post", "/api/months/open", json={"entity_id": e, "month": m})
# a type with no set of its own: it needs what Other needs
call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_water", "label": "Test water", "direction": "out"}})


def payment(entity, category, month, docs=(), paid=True, amount=10):
    """A paid payment with these documents uploaded."""
    pid = call("post", "/api/payments", json={"entity_id": entity, "month": month, "description": f"Test {category} {month}",
                                              "category": category, "amount": amount})["id"]
    for d in docs:
        call("post", "/api/upload", data={"payment_id": str(pid), "doc_type": d, "file": (io.BytesIO(b"%PDF-1.4\n%%EOF\n"), f"{d}.pdf")})
    if paid:
        call("patch", f"/api/payments/{pid}", json={"paid_date": f"{db.shift_month(month, 0)}-05"})
    return pid


def status(entity, month, pid):
    pays = call("get", f"/api/month?entity={entity}&month={month}")["payments"]
    p = next(p for p in pays if p["id"] == pid)
    return p["status"], p["required"]


def view(entity=None, month=None):
    return call("get", f"{RQ}?entity={entity or ''}" + (f"&month={month}" if month else ""))


def typed(v, key):
    return next(t for t in v["types"] if t["key"] == key)


def at(key, entity=None, month=M0):
    return typed(view(entity, month), key)["at"]


def change(key, docs, entity=None, month=M0, was=None):
    return {"payment_type": key, "docs": docs, "was": was if was is not None else at(key, entity, month)}


def batch(changes, entity=None, month=M0, expect=200, reason=None, preview=None, **extra):
    body = {"entity_id": entity, "from_month": month, "changes": changes, **extra}
    if reason is not None:
        body["reason"] = reason
    if preview is not None:
        body["preview"] = preview
    return call("post", RQ, expect, json=body)


def one(key, docs, entity=None, month=M0, expect=200):
    return call("post", RQ, expect, json={"payment_type": key, "entity_id": entity, "docs": docs, "from_month": month})


def sets(key=None):
    return q("SELECT payment_type, entity_id, from_month, to_month, docs FROM required_sets" + (" WHERE payment_type = ?" if key else "")
             + " ORDER BY payment_type, entity_id, from_month", (key,) if key else ())


def last_tx():
    return q("SELECT COALESCE(MAX(id), 0) AS n FROM audit_tx")[0]["n"]


def tx_since(n):
    return q("SELECT * FROM audit_tx WHERE id > ? ORDER BY id", (n,))


def kept():
    """Everything a save of required documents could leave behind."""
    return sets(), last_tx(), q("SELECT COUNT(*) AS n FROM activity")[0]["n"], q("SELECT COUNT(*) AS n FROM audit_row WHERE tbl = 'required_sets'")[0]["n"]


# ---------- 1. the view of one payroll month ----------
v = view()
check("the view is of the month a change is offered from when none is asked: each type's documents then are those it needs now",
      v["month"] == v["default_from"] == M0 and all(t["at"]["docs"] == t["docs"] and t["at"]["later"] == [] and t["own_in"] == [] for t in v["types"]), v["month"])
check("a month that isn't one is refused", call("get", f"{RQ}?entity=&month=2026-13", 400)["error"] == "From which month: months are written like 2026-10."
      and call("get", f"{RQ}?entity=&month=soon", 400)["error"].startswith("From which month"))
w = at("tst_water")
check("a type with no set of its own needs what Other needs, and says so", w["follows_other"] is True and w["since"] is None and w["docs"] == at("other")["docs"], w)
one("utility", ["invoice"], month=M2)
u0, u2 = at("utility", month=M0), at("utility", month=M2)
check("a month before a later set shows what is required then, and names the later set a save from it would replace",
      u0["docs"] == ["invoice", "pv", "bank"] and u0["later"] == [{"from_month": M2, "docs": ["invoice"]}] and u0["since"] == "0000-00"
      and u2["docs"] == ["invoice"] and u2["since"] == M2 and u2["later"] == [], (u0, u2))
check("...while the fields of before still show the latest set, as they did", typed(view(None, M0), "utility")["docs"] == ["invoice"])
one("rental", ["invoice"], entity=EXB, month=M1)
ev = typed(view(None, M0), "rental")["own_in"], typed(view(None, M1), "rental")["own_in"]
check("for every company, a type a company has its own set for names that company: from the month it starts, or in force",
      ev == ([{"entity_id": EXB, "spans": [{"from_month": M1, "to_month": None}]}], [{"entity_id": EXB, "spans": [{"from_month": None, "to_month": None}]}]), ev)
b0, b1 = at("rental", EXB, M0), at("rental", EXB, M1)
every_rental = at("rental", month=M0)["docs"]
check("for a company before its own set starts: it follows every company, and following would end the later set",
      b0["own"] is False and b0["docs"] == every_rental and b0["can_follow"] is True and [x["from_month"] for x in b0["later"]] == [M1]
      and b0["follow"] == every_rental and b0["follow_other"] is False, b0)
check("...and once it is in force: its own, with what following every company would give",
      b1["own"] is True and b1["docs"] == ["invoice"] and b1["follow"] == every_rental and b1["can_follow"] is True, b1)
wb = at("tst_water", EXB, M0)
check("a company's follow of a type with no set for every company would give what Other needs there, and says it is Other's",
      wb["follow"] == at("other", EXB, M0)["docs"] and wb["follow_other"] is True and wb["can_follow"] is False, wb)
check("...and a type a company never set can't be followed again", at("salary", EXB, M0)["can_follow"] is False)

# ---------- 2. a save of several types is one write ----------
p_util = payment(EXA, "utility", M0, docs=["bank", "pv"])          # missing the invoice
p_water = payment(EXA, "tst_water", M0, docs=["invoice", "pv", "bank"])
p_other = payment(EXA, "other", M0, docs=["invoice", "pv", "bank"])
p_before = payment(EXA, "tst_water", MP, docs=["invoice", "pv", "bank"])
check("the payments start as the sets say", [status(EXA, M0, p)[0] for p in (p_util, p_water, p_other)] == ["paid", "complete", "complete"],
      [status(EXA, M0, p) for p in (p_util, p_water, p_other)])
untouched = [s for s in sets() if s["payment_type"] not in ("utility", "statutory")]
n = last_tx()
r = batch([change("utility", ["pv", "bank"]), change("statutory", ["portal", "bank", "payslip"])], reason="HR asked for it")
txs = tx_since(n)
check("a save of two types is one change of the audit trail, with its one reason", len(txs) == 1 and txs[0]["reason"] == "HR asked for it"
      and txs[0]["action"] == "POST /api/setup/required" and txs[0]["source"] == "user", txs)
lines = (txs[0]["summary"] or "").split("\n") if txs else []
check("...with a line for each type", len(lines) == 2 and lines[0].startswith("Required documents: Utility / telco (every company) needs Payment Voucher, Bank receipt")
      and lines[1].startswith("Required documents: Statutory") and all(x.endswith(f"from {db.month_label(M0)}") for x in lines), lines)
entry = call("get", f"/api/audit/tx/{txs[0]['id']}") if txs else {"changes": [], "headline": ""}
by_type = sorted({c["record"] for c in entry["changes"] if c["table"] == "required_sets"})
check("...and the trail's entry holds each type's sets as records of their own", by_type == ["statutory", "utility"] and entry["headline"].endswith("(and 1 more)"), (by_type, entry["headline"]))
check("only the types named are written", [s for s in sets() if s["payment_type"] not in ("utility", "statutory")] == untouched)
check("the new sets start at the month picked; the later set of a type saved is replaced, as a save of that type alone does",
      [(s["from_month"], s["to_month"], json.loads(s["docs"])) for s in sets("utility")]
      == [("0000-00", M0, ["invoice", "pv", "bank"]), (M0, None, ["pv", "bank"])], sets("utility"))
check("it says how many open payments moved", r["affected"] == {"payments": 1, "now_missing": 0, "now_complete": 1} and status(EXA, M0, p_util)[0] == "complete", r)

# Other and a type that follows it, in one save: neither looks changed because the other was written first, and a payment counts once
other_now = at("other")["docs"]
r = batch([change("other", other_now + ["claim"]), change("tst_water", ["invoice", "bank", "einvoice"])])
check("Other and a type that needs what Other needs are saved together", r["ok"] is True, r)
check("...each payment counted once", r["affected"] == {"payments": 2, "now_missing": 2, "now_complete": 0}
      and [status(EXA, M0, p)[0] for p in (p_water, p_other)] == ["paid", "paid"], (r, [status(EXA, M0, p) for p in (p_water, p_other)]))
check("a month before the month picked keeps its rules", status(EXA, MP, p_before)[0] == "complete")
check("...and the type now has a set of its own", at("tst_water")["follows_other"] is False)

# ---------- 3. a preview keeps nothing ----------
before = kept()
r = batch([change("other", other_now), change("salary", ["bank"])], preview=True, reason="Only looking")
check("a preview says what the save would do", r["preview"] is True and r["affected"] == {"payments": 1, "now_missing": 0, "now_complete": 1}, r)
check("...and keeps nothing: no set, no line, no entry of the trail", kept() == before and status(EXA, M0, p_other)[0] == "paid")

# ---------- 4. all or nothing ----------
def refused(name, changes, words, code=400, **kw):
    before = kept()
    s, body = send("post", RQ, json={"entity_id": kw.get("entity"), "from_month": kw.get("month", M0), "changes": changes, "reason": "Try"})
    check(name, s == code and all(x in body.get("error", "") for x in words) and kept() == before, (s, body))


good = change("salary", ["bank"])
refused("one type that changes nothing refuses the whole save, and the type is named", [good, change("claim", at("claim")["docs"])],
        ["Staff claim: Nothing changes"])
refused("...as does a document no payment can need", [good, change("claim", ["bank", "statement"])], ["Staff claim: statement isn't a document type a payment can need."])
refused("...a document chosen twice", [good, change("claim", ["bank", "bank"])], ["Staff claim: Choose each document once."])
refused("...no documents list for every company", [good, change("claim", None)], ["Staff claim: Choose the documents."])
refused("...and a payment type that isn't there", [good, {"payment_type": "tst_gone", "docs": ["bank"], "was": {}}], ["There is no such payment type."], code=404)
old_was = at("claim")
one("claim", ["claim", "bank"])
refused("a type changed since the page read it refuses the whole save, and is named", [good, change("claim", ["bank"], was=old_was)],
        ["What is required from", "for Staff claim", "changed after this page read it."], code=409)
two = at("rental")
one("rental", ["bank"], month=M3)
refused("...a later set added since counts too: it would be replaced unseen", [good, change("rental", ["invoice"], was=two)], ["for Rental", "changed after this page read it."], code=409)
follow_was = at("rental", EXB, M1)
one("rental", ["approval", "bank"], month=M1)
refused("...and for a follow, what following would give", [change("rental", None, entity=EXB, month=M1, was=follow_was)], ["for Rental", "changed after"], code=409, entity=EXB, month=M1)
shape = [("no types", []), ("not a list", {"payment_type": "salary"}),
         ("a change with no docs (it must never read as follow every company)", [{"payment_type": "rental", "was": at("rental", EXB, M1)}]),
         ("a change with nothing of what the page showed", [{"payment_type": "salary", "docs": ["bank"]}]),
         ("a type twice", [good, good])]
for label, changes in shape:
    before = kept()
    s, body = send("post", RQ, json={"entity_id": EXB, "from_month": M1, "changes": changes})
    check(f"a save that can't be read is refused and keeps nothing: {label}", s == 400 and body.get("error") and kept() == before, (s, body))
for label, extra in [("a company sent as text", {"entity_id": str(EXB)}), ("no company said at all", {}), ("true as a company", {"entity_id": True})]:
    before = kept()
    s, body = send("post", RQ, json={"from_month": M0, "changes": [change("claim", ["bank"])], **extra})
    check(f"a save never falls back to every company: {label} is refused", s == 400 and "which company" in body.get("error", "").lower() and kept() == before, (s, body))
before = kept()
s, body = send("post", RQ, json={"entity_id": 999, "from_month": M0, "changes": [change("claim", ["bank"])]})
check("a company that isn't there is refused", s == 404 and kept() == before, (s, body))


# a failure after the first type was written (a check of the records, or anything else) keeps nothing
def breaks(error):
    real, count = masters._required_write, []

    def write(*a):
        count.append(1)
        if len(count) == 2:
            raise error
        return real(*a)
    masters._required_write, app.logger.disabled = write, True  # the failure injected here isn't news
    try:
        s, body = send("post", RQ, json={"entity_id": None, "from_month": M0, "reason": "Try",
                                         "changes": [change("salary", ["bank"]), change("claim", ["bank"])]})
    finally:
        masters._required_write, app.logger.disabled = real, False
    return s, body, len(count)


for label, error, code in [("the records refusing the second type", sqlite3.IntegrityError("CHECK constraint failed"), 409),
                           ("anything else failing at the second type", RuntimeError("disk"), 500)]:
    before = kept()
    s, body, writes = breaks(error)
    check(f"all or nothing: {label} keeps nothing of the first", s == code and writes == 2 and kept() == before, (s, body, writes))
    c2 = db.connect()
    check("...and the rules read afterwards are those kept", rulebook.get(c2).required_docs("salary", 1, M0, EXA) != ["bank"])
    c2.close()

# ---------- 5. a company's own sets, and following again ----------
r = batch([change("salary", ["payslip", "bank"], entity=EXB), change("claim", ["claim"], entity=EXB)], entity=EXB)
check("a company's save gives it its own set for each type changed, and no other company's records move",
      r["ok"] and at("salary", EXB)["own"] and at("claim", EXB)["own"] and not at("salary", EXA)["own"]
      and {s["entity_id"] for s in sets("salary")} == {None, EXB}, sets("salary"))
n = last_tx()
r = batch([change("salary", None, entity=EXB, month=M1), change("claim", ["claim", "bank"], entity=EXB, month=M1)], entity=EXB, month=M1, reason="Back to the usual")
check("a follow and a change go in one write, the follow ending the company's own set from the month",
      len(tx_since(n)) == 1 and at("salary", EXB, M1)["own"] is False and at("salary", EXB, M0)["own"] is True and at("claim", EXB, M1)["docs"] == ["claim", "bank"]
      and "follows every company's documents again" in tx_since(n)[0]["summary"], tx_since(n))
refused("a follow where nothing of its own is left refuses the whole save", [change("claim", ["bank"], entity=EXB, month=M1), change("salary", None, entity=EXB, month=M1)],
        ["Salary: This company already follows the documents set for every company."], entity=EXB, month=M1)

# a company that is to follow every company again from a later month: the view says so, and a save that would undo it unseen is refused
call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_back", "label": "Test back", "direction": "out"}})
one("tst_back", ["bank"], entity=EXB, month=M0)
seen_before = at("tst_back", EXB, M1)
one("tst_back", None, entity=EXB, month=M3)
back = at("tst_back", EXB, M1)
check("a company's own set that is to give way to every company's later says from when; the earlier view, and every company's, name none",
      back["returns"] == [M3] and back["later"] == [] and seen_before["returns"] == [] and at("tst_back", EXB, M3)["returns"] == [] and at("rental", month=M0)["returns"] == [], (back, seen_before))
refused("...a save made from a view without it is refused, so it isn't undone unseen",
        [change("tst_back", ["invoice"], entity=EXB, month=M1, was=seen_before)], ["for Test back", "changed after this page read it."], code=409, entity=EXB, month=M1)
r = batch([change("tst_back", ["invoice"], entity=EXB, month=M1)], entity=EXB, month=M1)
check("...saved having seen it, the company's new set carries on past that month, as a save of the type alone does",
      r["ok"] and at("tst_back", EXB, M3)["own"] is True and at("tst_back", EXB, M3)["docs"] == ["invoice"], at("tst_back", EXB, M3))
one("tst_back", ["bank"], entity=EXB, month=M1)
one("tst_back", None, entity=EXB, month=M2)
one("tst_back", ["approval"], entity=EXB, month=M3)
check("...also when it is to have a set of its own again after that", at("tst_back", EXB, M1)["returns"] == [M2] and [x["from_month"] for x in at("tst_back", EXB, M1)["later"]] == [M3], at("tst_back", EXB, M1))

# the same change by the grid and by one type alone writes the same sets
def shape_of(key):
    return [(s["entity_id"], s["from_month"], s["to_month"], json.loads(s["docs"])) for s in sets(key)]


for key in ("tst_twin_a", "tst_twin_b"):
    call("post", "/api/setup/payment_types", json={"fields": {"key": key, "label": key, "direction": "out"}})
    for month, docs in ((M0, ["bank"]), (M1, ["invoice"]), (M3, ["approval"])):
        one(key, docs, month=month)
one("tst_twin_a", ["pv", "bank"], month=M1)
batch([change("tst_twin_b", ["pv", "bank"], month=M1)], month=M1)
check("from a month before later sets, the grid's save leaves exactly the sets a save of the type alone leaves",
      shape_of("tst_twin_a") == shape_of("tst_twin_b") == [(None, M0, M1, ["bank"]), (None, M1, None, ["pv", "bank"])], (shape_of("tst_twin_a"), shape_of("tst_twin_b")))

# ---------- the months of a company's own sets, as the view for every company gives them ----------
def spans(key, month=M0):
    return [(x["entity_id"], [(s["from_month"], s["to_month"]) for s in x.get("spans", [])]) for x in typed(view(None, month), key)["own_in"]]


def own_steps(key, *steps):
    """A new type with a set for every company, then EXB's changes of it: (month, documents, or None to follow again)."""
    call("post", "/api/setup/payment_types", json={"fields": {"key": key, "label": key, "direction": "out"}})
    one(key, ["bank"], month=M0)
    for month, docs in steps:
        one(key, docs, entity=EXB, month=month)


own_steps("tst_until", (M0, ["invoice"]), (M2, None))
check("an own set that gives way to every company's later says until when, in force or still to come",
      spans("tst_until") == [(EXB, [(None, M2)])] and spans("tst_until", M2) == [] and spans("tst_until", M3) == [], (spans("tst_until"), spans("tst_until", M2)))
reach = batch([change("tst_until", ["bank", "pv"])], preview=True)
batch([change("tst_until", ["bank", "pv"])])
c2 = db.connect()
seen_by = [rulebook.get(c2).required_docs("tst_until", 1, m, EXB) for m in (M0, M1, M2)]
c2.close()
check("...and a change for every company does reach that company from then", reach["ok"] and seen_by == [["invoice"], ["invoice"], ["bank", "pv"]], seen_by)
own_steps("tst_between", (M1, ["invoice"]), (M2, None))
check("...one to come that ends again says both months", spans("tst_between") == [(EXB, [(M1, M2)])], spans("tst_between"))
own_steps("tst_gap", (M0, ["invoice"]), (M1, None), (M2, ["claim"]))
check("...months between two own sets are left out of them, where a change for every company reaches the company",
      spans("tst_gap") == [(EXB, [(None, M1), (M2, None)])] and spans("tst_gap", M1) == [(EXB, [(M2, None)])], (spans("tst_gap"), spans("tst_gap", M1)))
own_steps("tst_joined", (M0, ["invoice"]), (M1, ["claim"]), (M3, ["approval"]))
check("...and own sets that follow on from one another are one span", spans("tst_joined") == [(EXB, [(None, None)])], spans("tst_joined"))

# ---------- a company's new set stands over every company's later ones ----------
call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_over", "label": "Test over", "direction": "out"}})
one("tst_over", ["bank"], month=M0)
stale_view = at("tst_over", EXB, M0)
one("tst_over", ["invoice"], month=M2)
now_view = at("tst_over", EXB, M0)
check("the view for a company that would get a set of its own names the later months every company's set changes; the view for every company names none",
      stale_view.get("every_later") == [] and now_view.get("every_later") == [M2] and at("tst_over", month=M0).get("every_later") == [] and at("tst_over", EXB, M2).get("every_later") == [],
      (stale_view, now_view))
refused("a company's save made before every company's later set was added is refused, so it doesn't stand over it unseen",
        [change("tst_over", ["claim"], entity=EXB, was=stale_view)], ["for Test over", "changed after this page read it."], code=409, entity=EXB)
r = batch([change("tst_over", ["claim"], entity=EXB)], entity=EXB)
check("...saved having seen it, it is kept", r["ok"] and at("tst_over", EXB, M2)["docs"] == ["claim"], r)
mine = at("tst_over", EXB, M0)
one("tst_over", ["pv"], month=M3)
r = batch([change("tst_over", ["claim", "bank"], entity=EXB, was=mine)], entity=EXB)
check("a company that has its own set in force already isn't refused for a later set of every company: it stood over it before", r["ok"] and mine.get("every_later") == [], (r, mine))
seen_follow = at("tst_over", EXB, M1)
one("tst_over", ["approval"], month=M2)
r = batch([change("tst_over", None, entity=EXB, month=M1, was=seen_follow)], entity=EXB, month=M1)
check("...nor is Follow all companies again, which takes every company's later sets", r["ok"] is True, r)

# ---------- "Changes from" under In force: the first later month another set is in force ----------
def new_type(key):
    call("post", "/api/setup/payment_types", json={"fields": {"key": key, "label": key, "direction": "out"}})


def changes(key, entity=None, month=M0):
    a = at(key, entity, month)
    return a.get("changes_from", "missing"), a.get("follow_changes_from", "missing")


new_type("tst_chg")
one("tst_chg", ["bank"], month=M0)
one("tst_chg", ["invoice"], month=M2)
check("a type's later set for every company is the next change, for every company and for a company that follows them; from that month on there is none",
      changes("tst_chg") == (M2, None) and changes("tst_chg", EXA) == (M2, M2) and changes("tst_chg", EXA, M2) == (None, None), (changes("tst_chg"), changes("tst_chg", EXA)))
one("tst_chg", ["claim"], entity=EXB, month=M3)
check("...also before a company's own set that starts later still: every company's comes first",
      changes("tst_chg", EXB)[0] == M2 and at("tst_chg", EXB, M0)["later"][0]["from_month"] == M3 and changes("tst_chg", EXB, M2)[0] == M3, changes("tst_chg", EXB))
new_type("tst_chg_own")
one("tst_chg_own", ["bank"], month=M0)
one("tst_chg_own", ["claim"], entity=EXB, month=M0)
one("tst_chg_own", ["invoice"], month=M2)
check("a company's own set in force isn't changed by every company's later one; once it follows them again, it is",
      changes("tst_chg_own", EXB) == (None, M2), changes("tst_chg_own", EXB))
one("tst_chg_own", None, entity=EXB, month=M3)
check("...with a month it is to follow them again from, that is the change as the records are, and every company's own as a follow now would be",
      changes("tst_chg_own", EXB) == (M3, M2), changes("tst_chg_own", EXB))
new_type("tst_via")
other_was = at("other")["docs"]
one("other", ["bank", "claim"], entity=EXB, month=M2)
check("a type that needs what Other needs changes when Other does: a company's own Other, for that company alone",
      changes("tst_via", EXB)[0] == M2 and at("tst_via", EXB, M0)["follows_other"] is True and at("tst_via", EXB, M0)["later"] == [] and changes("tst_via")[0] != M2, (changes("tst_via", EXB), changes("tst_via")))
one("other", [d for d in other_was if d != "bank"] or ["bank"], month=M3)
check("...and every company's Other, in every company's view and for a company that follows it", changes("tst_via")[0] == M3 and changes("tst_via", EXA)[0] == M3, (changes("tst_via"), changes("tst_via", EXA)))
one("tst_via", ["approval"], month=M1)
check("...until it is to have a set of its own, which Other's later ones don't change", changes("tst_via")[0] == M1 and changes("tst_via", month=M1)[0] is None, (changes("tst_via"), changes("tst_via", month=M1)))

# ---------- changes through Other that a set of the type's own does away with ----------
def via(key, entity=None, month=M0):
    return at(key, entity, month).get("other_later", "missing")


def needs(key, entity, month):
    c = db.connect()
    out = rulebook.get(c).required_docs(key, 1, month, entity)
    c.close()
    return out


new_type("tst_path")
base_other = at("other")["docs"]
check("from the month of Other's last planned change on, no month is named for a type that needs what Other needs", via("tst_path", month=M3) == [] and via("tst_path", EXA, M3) == [],
      (via("tst_path", month=M3), via("tst_path", EXA, M3)))
path_was = at("tst_path", EXA, M0)
one("other", [d for d in base_other if d != "einvoice"] + ["einvoice", "portal"], month=M2)  # this replaces the one planned for the month after
check("a later change to every company's Other is named for the type, for every company and for a company; from that month on none is",
      via("tst_path") == [M2] and via("tst_path", EXA) == [M2] and via("tst_path", EXA, M2) == [] and via("other", EXA) == [] and at("tst_path", EXA)["every_later"] == [], (via("tst_path"), via("tst_path", EXA)))
refused("a company's save made before that change to Other was added is refused, so it doesn't do away with it unseen",
        [change("tst_path", ["bank", "approval"], entity=EXA, was=path_was)], ["for tst_path", "changed after this page read it."], code=409, entity=EXA)
one("other", ["claim", "bank"], entity=EXA, month=M1)
check("a company with its own Other is changed by its own Other's changes, not by every company's", via("tst_path", EXA) == [M1] and via("tst_path") == [M2], (via("tst_path", EXA), via("tst_path")))
one("other", None, entity=EXA, month=M3)
check("...until it is to follow every company's Other again", via("tst_path", EXA) == [M1, M3], via("tst_path", EXA))
one("tst_path", ["invoice"], month=M3)
check("a month from which the type has a set of its own is no change through Other, and a type with a set in force has none",
      via("tst_path", EXA) == [M1] and via("tst_path") == [M2] and via("tst_path", month=M3) == [] and via("tst_path", EXA, M3) == [], (via("tst_path", EXA), via("tst_path")))
ahead = needs("tst_path", EXA, M1)
r = batch([change("tst_path", ["pv"], entity=EXA)], entity=EXA)
check("...saved having seen it, it is kept, and the company's type no longer follows Other's change", r["ok"] and ahead == ["claim", "bank"] and needs("tst_path", EXA, M1) == ["pv"], (r, ahead))


def other_own(key, month=M0):
    return [(x["entity_id"], [(s["from_month"], s["to_month"]) for s in x["spans"]]) for x in typed(view(None, month), key).get("other_own_in", [])]


new_type("tst_fall")
# EXA has its own Other from M1 until it follows every company's again from M3; EXB its own from M2 on
check("for every company, a type with no set names the companies that need their own Other for it, with the months: from the one it starts in, until it follows every company again",
      other_own("tst_fall") == [(EXA, [(M1, M3)]), (EXB, [(M2, None)])], other_own("tst_fall"))
check("...one that needs it in the month shown has no starting month; one company's view, and Other itself, name none",
      other_own("tst_fall", M2) == [(EXA, [(None, M3)]), (EXB, [(None, None)])] and typed(view(EXA, M1), "tst_fall").get("other_own_in") == []
      and typed(view(None, M0), "other").get("other_own_in") == [], other_own("tst_fall", M2))
one("tst_fall", ["approval"], entity=EXB, month=M3)
check("...but not in the months the company has its own set for the type", other_own("tst_fall") == [(EXA, [(M1, M3)]), (EXB, [(M2, M3)])], other_own("tst_fall"))
one("tst_fall", ["bank"], month=M2)
check("...nor once every company has a set of the type, which stands over a company's own Other",
      other_own("tst_fall") == [(EXA, [(M1, M2)])] and other_own("tst_fall", M2) == [] and needs("tst_fall", EXA, M1) == ["claim", "bank"] and needs("tst_fall", EXA, M2) == ["bank"],
      (other_own("tst_fall"), other_own("tst_fall", M2)))

# ---------- 6. filed months never change ----------
filed_was = at("salary", month=MP)
call("post", "/api/months/close", json={"entity_id": EXA, "month": M0, "closed": True})
v = view()
check("with a month filed, the view offers the month after it, and nothing at or before it", v["first_allowed"] == M1 and v["default_from"] == M1 and v["month"] == M1, v["first_allowed"])
refused("a save of several types never reaches a filed month, for every company", [change("salary", ["bank"], month=M0), change("claim", ["approval"], month=M0)],
        [f"{db.month_label(M0)} is filed, and filed months never change. Choose {db.month_label(M1)} or later."])
refused("...nor a month before it", [change("salary", ["bank"], month=MP, was=filed_was)], ["is filed, and filed months never change."], month=MP)
refused("...nor for the company that filed it", [change("salary", ["approval"], entity=EXA, month=M0)], ["is filed, and filed months never change."], entity=EXA)
r = batch([change("salary", ["approval"], entity=EXB, month=M0)], entity=EXB, month=M0)
check("a company with nothing filed saves from that month", r["ok"] is True, r)
s, body = send("post", RQ, json={"entity_id": None, "from_month": M0, "preview": True, "changes": [change("salary", ["bank"], month=M0)]})
check("a preview of a filed month is refused too", s == 400 and "is filed" in body.get("error", ""), (s, body))

if failed:
    print(f"\n{len(failed)} FAILED, {len(passed)} passed")
    sys.exit(1)
print(f"\nrequired_matrix_test: all {len(passed)} checks passed")
