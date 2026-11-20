"""Slice 8: Payments › Budget and Payments › Recurring, on made-up records only.

The server part runs the app on a temporary records folder (Flask's test client): three made-up companies (one with a ringgit
account, one with a ringgit and a US dollar account, one with a US dollar account only), recurring payments of several types,
a month of payments paid before and after the balance date, and a stored budget. It checks the Budget rules of slice 8:
  - with no ringgit balance entered, the funds to request are not worked out (None), never from a blank taken as 0, and the
    Excel says "Not entered" and "Not worked out, bank balance not entered";
  - the balance is read only from the stored budget (a month with none has no balance, and nothing in the page script keeps
    one in the browser);
  - the bank is named from the company's own account in Setup (its label), never written into the app;
  - payments paid on or before the balance date are already out of the balance (counted up to that date);
and the Recurring page's server side: the recurring payments' Excel (every field, the type in Setup's words), Add to month.

The page part runs the page script in Node against a small stand-in for the page (an element per id), with the server's answers:
the Budget page's no-balance sentence, no fund request to print, the print preview's "not worked out" wording, the bank label,
the shortfall and its fund request print, the balance saved on the stored budget; the Recurring page's type filter in Setup's
words with its counts, Show stopped, the table, Add to <month>, Excel, and the form with every field.

Run: .venv\\Scripts\\python -m synthetic_tests.budget_recurring_test
"""
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-budget-recurring-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from openpyxl import load_workbook  # noqa: E402

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

ROOT = Path(__file__).resolve().parent.parent
# Made-up companies and account labels: none of them is a real bank's name.
(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXB", "name": "Example Budget Sdn Bhd", "accounts": [{"label": "Operating account", "bank": "Example Bank", "number": "000-301"}]},
    {"code": "EXR", "name": "Example Recurring Sdn Bhd", "accounts": [
        {"label": "Ringgit current", "bank": "Example Bank", "number": "000-401"},
        {"label": "Dollar float", "bank": "Example Bank", "number": "000-402", "currency": "USD"}]},
    {"code": "EXU", "name": "Example Dollar Trading", "uses_sql": False, "accounts": [{"label": "Dollar only", "bank": "Example Bank", "number": "000-501", "currency": "USD"}]},
]}), encoding="utf-8")

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:600])


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


meta = j("get", "/api/meta")
ids = {e["code"]: e["id"] for e in meta["entities"]}
EXB, EXR, EXU = ids["EXB"], ids["EXR"], ids["EXU"]
acct = {e["code"]: {a["currency"]: a["id"] for a in e["accounts"]} for e in meta["entities"]}
M = db.current_cycle()
day = lambda d: f"{M}-{d:02d}"


def pay(eid, desc, cat, amount, due, paid=None):
    code = next(k for k, v in ids.items() if v == eid)
    return j("post", "/api/payments", json={"entity_id": eid, "month": M, "description": desc, "category": cat, "amount": amount,
                                            "account_id": acct[code]["MYR"], "due_date": day(due), "paid_date": day(paid) if paid else None})["id"]


def budget(eid, as_at=None):
    return j("get", f"/api/budget?entity={eid}&month={M}" + (f"&as_at={as_at}" if as_at else ""))


def sheet(path):
    r = call("get", path)
    assert r.status_code == 200, (path, r.status_code, r.data[:300])
    ws = load_workbook(io.BytesIO(r.data)).worksheets[0]
    return r, [[x for x in row] for row in ws.iter_rows(values_only=True)]


# ---------- the Budget: a month of payments paid before and after the balance date ----------
j("post", "/api/months/open", json={"entity_id": EXB, "month": M})
water = pay(EXB, "Water utility - test", "utility", 200, 5, paid=4)
hall = pay(EXB, "Hall rental - test", "rental", 1500, 20, paid=22)
clean = pay(EXB, "Cleaning contract - test", "other", 300, 25)

# A month with no stored budget: the list worked out from its payments, no balance, so no funds to request.
w = budget(EXB, day(10))
check("a month with no stored budget has no balance (it is kept only with the stored budget)",
      w["stored"] is False and w["balance"] is None and w["saved_as_at"] is None, (w["stored"], w["balance"]))
check("...so the funds to request are not worked out: None, never the total less a blank taken as 0",
      w["funds_to_request"] is None and w["totals"]["MYR"] > 0, (w["funds_to_request"], w["totals"]))
check("payments paid on or before the balance date are already out of it; one paid after it still counts",
      {p["id"] for p in w["paid"]} == {water} and {p["id"] for p in w["to_pay"]} == {hall, clean} and w["totals"]["MYR"] == 1800, w["totals"])
check("the bank is the company's own ringgit account from Setup, by its label",
      w["bank"]["account"] and w["bank"]["account"]["label"] == "Operating account" and w["bank"]["others"] == [], w["bank"])
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXB}&month={M}&as_at={day(10)}")
check("a month with no stored budget still has its Excel: the list worked out from its payments",
      f"EXB {M} budget.xlsx" in r.headers.get("Content-Disposition", "") and {"Water utility - test", "Hall rental - test", "Cleaning contract - test"} <= {x[1] for x in rows}, rows[:8])
check("...whose balance reads Not entered and whose funds to request are not worked out",
      rows[1][:2] == ["Bank balance", "Not entered"] and rows[3][:2] == ["Funds to request", "Not worked out, bank balance not entered"]
      and rows[1][3:5] == ["Bank account", "Operating account"], rows[:4])
worked_route = budget(EXB)

# The stored budget: the balance kept with it, and payments counted up to its date.
j("post", "/api/budget/setup", json={"entity_id": EXB, "month": M})
b = budget(EXB)
check("set up: a line for each payment out, no balance yet, so no funds to request",
      b["stored"] and len(b["lines"]) == 3 and b["balance"] is None and b["funds_to_request"] is None, (len(b["lines"]), b["balance"]))
no_bal_route = b
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXB}&month={M}")
check("the stored budget's Excel with no balance: Not entered, and the funds not worked out",
      rows[1][:2] == ["Bank balance", "Not entered"] and rows[3][:2] == ["Funds to request", "Not worked out, bank balance not entered"]
      and rows[4][:2] == ["No.", "Description"], rows[:5])
j("post", "/api/budget/header", json={"entity_id": EXB, "month": M, "balance": 1000, "as_at": day(10)})
b = budget(EXB)
lines = {x["payment_id"]: x for x in b["lines"]}
check("the balance and its date are read from the stored budget",
      (b["balance"], b["saved_as_at"], b["as_at"]) == (1000, day(10), day(10)), (b["balance"], b["saved_as_at"], b["as_at"]))
check("payments counted up to the balance date: paid by then is in the balance, paid after it is still to pay",
      lines[water]["in_balance"] and lines[water]["to_pay"] == 0 and not lines[hall]["in_balance"] and lines[hall]["to_pay"] == 1500
      and lines[clean]["to_pay"] == 300 and b["totals"] == {"MYR": 1800}, {k: (v["to_pay"], v["in_balance"]) for k, v in lines.items()})
check("the funds to request are what is still to pay less the balance", b["funds_to_request"] == 800, b["funds_to_request"])
check("Budget vs paid: paid against the budget counts only what was paid by the balance date",
      b["sums"]["MYR"]["paid_by"] == 200 and b["sums"]["MYR"]["paid"] == 1700, b["sums"])
short_route = b
later = budget(EXB, day(25))
check("as at a later date the payment paid in between is out of the balance too",
      later["totals"] == {"MYR": 300}, later["totals"])
check("...but the balance kept is for its own date, so it is never set against what is still to pay at another one",
      later["balance"] == 1000 and later["saved_as_at"] == day(10) and later["funds_to_request"] is None, (later["saved_as_at"], later["funds_to_request"]))
other_route = later
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXB}&month={M}&as_at={day(25)}")
check("...and its Excel as at that other date says which date the balance is for, and works out no funds",
      str(rows[1][1]).startswith("Not entered for this date: the balance kept is as at ")
      and str(rows[3][1]).startswith("Not worked out: the balance is for ") and "open the budget as at that date" in str(rows[3][1]), rows[:4])
j("post", "/api/budget/header", json={"entity_id": EXB, "month": M, "as_at": day(25)})
check("with the balance's date moved to that day, the balance covers what is left", budget(EXB)["funds_to_request"] == 0)
j("post", "/api/budget/header", json={"entity_id": EXB, "month": M, "as_at": day(10)})
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXB}&month={M}")
check("the stored budget's Excel with a balance: the balance and the funds to request, the bank account named",
      rows[1][:2] == ["Bank balance", 1000] and rows[3][:2] == ["Funds to request", 800] and rows[1][3:5] == ["Bank account", "Operating account"], rows[:4])
j("post", "/api/budget/header", json={"entity_id": EXB, "month": M, "balance": ""})
b = budget(EXB)
check("a balance cleared is not entered (None), not 0, and the funds are not worked out again",
      b["balance"] is None and b["funds_to_request"] is None, (b["balance"], b["funds_to_request"]))
j("post", "/api/budget/header", json={"entity_id": EXB, "month": M, "balance": 1000, "as_at": day(10)})
j("post", "/api/budget/header", 400, json={"entity_id": EXR, "month": M, "balance": 5})  # no stored budget: nowhere to keep it

# The bank label of the other companies: a ringgit account beside a dollar one; only a dollar account.
rb = budget(EXR)["bank"]
check("with a ringgit and a dollar account, the balance is the ringgit one's; the dollar one is listed apart",
      rb["account"]["label"] == "Ringgit current" and [o["label"] for o in rb["others"]] == ["Dollar float"], rb)
j("post", "/api/months/open", json={"entity_id": EXU, "month": M})
ub = budget(EXU)
check("a company with no ringgit account has no account for the balance, and its dollar account is named",
      ub["bank"]["account"] is None and [o["currency"] for o in ub["bank"]["others"]] == ["USD"] and ub["funds_to_request"] is None, ub["bank"])
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXU}&month={M}")
check("...and its Excel says no ringgit account is set up", rows[1][3:5] == ["Bank account", "No ringgit account set up"], rows[:3])

# ---------- Recurring: payment types in Setup's words, Excel, Add to month ----------
pt = {x["key"]: x for x in j("get", "/api/setup/payment_types")["rows"]}
j("patch", f"/api/setup/payment_types/{pt['utility']['id']}", json={"fields": {"label": "Utilities and phone (test)"}})
labels = j("get", "/api/meta")["categories"]
check("a payment type renamed in Setup is named so everywhere", labels["utility"] == "Utilities and phone (test)")
mk = lambda **b: j("post", "/api/payees", json={"entity_id": EXR, **b})["id"]
p_sal = mk(name="Staff salaries - test", category="salary", amount=8000, due_day=25, month_offset=0, account_id=acct["EXR"]["MYR"])
p_util = mk(name="Electricity - test", category="utility", amount=320, amount_varies=1, due_day=7, month_offset=1, account_id=acct["EXR"]["MYR"],
            bank_details="Example utility account 000111229876", reference="UT-0001", match_words="ELECTRIC TEST", notes="Estimated each month")
p_in = mk(name="Tenant rent - test", category="receipt", direction="in", amount=900, due_day=5, account_id=acct["EXR"]["MYR"])
p_old = mk(name="Old storage - test", category="rental", amount=150, due_day=1, account_id=acct["EXR"]["MYR"])
j("post", f"/api/payees/{p_old}/stop", json={"reason": "No longer used (test)"})
j("post", f"/api/payees/{p_sal}/advances", json={"monthly_deduction": 100, "start_month": M, "end_month": db.shift_month(M, 2), "note": "Test advance"})
j("post", "/api/months/open", json={"entity_id": EXR, "month": M})
p_new = mk(name="Courier - test", category="other", amount=60, due_day=12, account_id=acct["EXR"]["MYR"])  # after the month was set up
with db.connect() as con:  # its payment taken out of the month again, as if it had been added after the month was done with
    con.arm("user", "test: a recurring payment not in the month")
    con.execute("DELETE FROM payments WHERE payee_id = ? AND month = ?", (p_new, M))
    con.commit()
    con.disarm()
listed = {p["id"]: p for p in j("get", f"/api/payees?entity={EXR}&month={M}")}
check("a recurring payment added after the month was set up is not in it yet", listed[p_new]["in_month"] is False and listed[p_util]["in_month"] is True)
recurring_route = list(listed.values())
r, rows = sheet(f"/api/export/recurring.xlsx?entity_id={EXR}")
head = rows[2]
by_name = {x[0]: dict(zip(head, x)) for x in rows[3:] if x and x[0]}
check("the recurring payments have their Excel, named for the company",
      r.status_code == 200 and "EXR recurring payments.xlsx" in r.headers.get("Content-Disposition", ""), r.headers.get("Content-Disposition"))
check("...with every field of the form as a column",
      {"Payee", "Money", "Type", "Description each month", "Paid in", "Day of month", "Usual amount", "Currency", "Amount changes monthly",
       "Pay from / paid into", "Bank details", "Account / ref no.", "Words on the bank statement", "Supplier or customer", "Start date",
       "Last day", "Status", "Notes", "Salary advances"} <= set(head), head)
u = by_name.get("Electricity - test", {})
check("...each row as kept, its type in Setup's words",
      set(by_name) >= {"Staff salaries - test", "Electricity - test", "Tenant rent - test", "Old storage - test", "Courier - test"}
      and u.get("Type") == "Utilities and phone (test)" and u.get("Paid in") == "The following month" and u.get("Amount changes monthly") == "Yes, estimate"
      and u.get("Pay from / paid into") == "Ringgit current" and u.get("Words on the bank statement") == "ELECTRIC TEST"
      and by_name["Tenant rent - test"]["Money"] == "Money in" and by_name["Old storage - test"]["Status"] == "Stopped"
      and "100.00 a month" in by_name["Staff salaries - test"]["Salary advances"], u)
check("...its bank details masked to the last 4, as the audit trail's export has them",
      u.get("Bank details") == "••••9876" and "000111229876" not in str(rows) and "masked to the last 4" in str(rows[1][0]), (u.get("Bank details"), rows[1]))
j("post", f"/api/payees/{p_new}/add-to-month", json={"month": M})
check("Add to month adds its payment to the month", j("get", f"/api/payees?entity={EXR}&month={M}") and
      next(p for p in j("get", f"/api/payees?entity={EXR}&month={M}") if p["id"] == p_new)["in_month"] is True)
check("...and only once", "already has a payment" in j("post", f"/api/payees/{p_new}/add-to-month", 400, json={"month": M})["error"])

# ---------- Budget vs paid for a payment paid in two parts across the balance date ----------
two = j("post", "/api/payments", json={"entity_id": EXR, "month": M, "description": "Two-part supply - test", "category": "other", "amount": 1000,
                                       "account_id": acct["EXR"]["MYR"], "due_date": day(18), "paid_date": None})["id"]
with db.connect() as con:
    con.arm("user", "test: a payment paid in two parts")
    st = con.execute("INSERT INTO statements (account_id, month, statement_date, imported_at, check_ok) VALUES (?, ?, ?, ?, 1)",
                     (acct["EXR"]["MYR"], M, day(28), db.now())).lastrowid
    for n, (d_, amt) in enumerate(((8, -400), (15, -600)), 1):
        con.execute("INSERT INTO statement_lines (statement_id, line_no, txn_date, description, amount, balance, payment_id, status) "
                    "VALUES (?, ?, ?, 'TRANSFER TEST', ?, 0, ?, 'matched')", (st, n, day(d_), amt, two))
    con.commit()
    con.disarm()
j("post", "/api/budget/setup", json={"entity_id": EXR, "month": M})
rv = budget(EXR, day(10))
tl = next(x for x in rv["lines"] if x["payment_id"] == two)
others_paid = sum(x["paid"] or 0 for x in rv["lines"] if x["payment_id"] != two and x["paid_date"] and x["paid_date"] <= day(10))
check("a payment paid in two parts across the balance date: paid against the budget counts only the part paid by then",
      tl["to_pay"] == 600 and round(rv["sums"]["MYR"]["paid_by"] - others_paid, 2) == 400, (tl["to_pay"], rv["sums"]["MYR"]))
check("...so paid by the date and still to pay add up to the line's budget", tl["amount"] - 400 == tl["to_pay"])
check("...and as at a date after both parts, all of it", next(x for x in budget(EXR, day(20))["lines"] if x["payment_id"] == two)["to_pay"] == 0)

# ---------- a stopped ringgit account is told apart from none ----------
racct = acct["EXR"]["MYR"]
def _acct_active(v):  # a cash book account can't be stopped in Setup, so the test marks it stopped in the records
    with db.connect() as con:
        con.arm("user", "test: a stopped ringgit account")
        con.execute("UPDATE accounts SET active = ? WHERE id = ?", (v, racct))
        con.commit()
        con.disarm()


_acct_active(0)
sb = budget(EXR)["bank"]
check("a company whose ringgit account is stopped: no account for the balance, and the stopped one named",
      sb["account"] is None and sb["stopped"] and sb["stopped"]["label"] == "Ringgit current", sb)
r, rows = sheet(f"/api/export/budget.xlsx?entity_id={EXR}&month={M}")
check("...and the Excel says it is stopped", rows[1][3:5] == ["Bank account", "Ringgit current (stopped)"], rows[:3])
stopped_bank_route = budget(EXR)
_acct_active(1)

# ---------- nothing about a bank or a company is written into the code ----------
budget_js = (ROOT / "static" / "js" / "pages" / "budget.js").read_text(encoding="utf-8")
recurring_js = (ROOT / "static" / "js" / "pages" / "recurring.js").read_text(encoding="utf-8")
server = (ROOT / "hrp" / "budget.py").read_text(encoding="utf-8") + (ROOT / "hrp" / "reports.py").read_text(encoding="utf-8")
check("the Budget page keeps nothing in the browser: no localStorage left in budget.js", "localStorage" not in budget_js)
check("...and the Overview no longer sends a balance date of its own", "as_at_${" not in (ROOT / "static" / "js" / "pages" / "overview.js").read_text(encoding="utf-8"))
banks = ("Maybank", "CIMB", "Public Bank", "RHB", "Hong Leong", "AmBank", "Bank Islam", "UOB", "OCBC", "HSBC")
check("no bank's name is written into the Budget or Recurring code", not [b_ for b_ in banks if b_ in budget_js + recurring_js + server])
check("no company code is written into them either", not re.search(r'"(AISB|AIL|AIP|AI)"', budget_js + recurring_js))

# ---------- the pages, in Node ----------
# Many lines (made up from the stored budget's): 30 in ringgit, 3 in dollars, for Show more and Select all.
import copy  # noqa: E402
many_route = copy.deepcopy(short_route)
base = many_route["lines"][0]
many_route["lines"] = [dict(base, id=90000 + i, description=f"Bulk line {i} - test", payment_id=None) for i in range(30)] + \
    [dict(base, id=91000 + i, description=f"Dollar line {i} - test", currency="USD", payment_id=None) for i in range(3)]
many_route["sums"]["USD"] = {"budget": 30, "paid": 0, "diff": 0, "paid_by": 0}
fixture = {"exb": EXB, "exr": EXR, "exu": EXU, "month": M, "p_new": p_new, "p_sal": p_sal, "p_util": p_util, "routes": {
    "/api/meta": j("get", "/api/meta"),
    f"/api/budget?entity={EXU}&month={M}": budget(EXU),
    f"/api/payees?entity={EXR}&month={M}": recurring_route,
    f"/api/month?entity={EXR}&month={M}": j("get", f"/api/month?entity={EXR}&month={M}"),
    f"/api/payees/{p_sal}/usage": j("get", f"/api/payees/{p_sal}/usage"),
    f"/api/payees/{p_util}/usage": j("get", f"/api/payees/{p_util}/usage"),
}, "budgets": {"worked": worked_route, "nobal": no_bal_route, "short": short_route, "other": other_route, "many": many_route,
               "stopped": stopped_bank_route}}
fx = tmp / "fixture.json"
fx.write_text(json.dumps(fixture), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, posts = [], kept = [], docListeners = {}, store = {}, refuse = new Set();
let budgetNow = null;
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, listeners: {},
  classList: { add() {}, remove() {}, contains() { return false; } }, addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
  querySelectorAll() { return []; }, querySelector() { return null; }, setAttribute() {}, removeAttribute() {}, focus() {}, remove() {} };
const document = { querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, querySelectorAll: () => [], getElementById: () => null,
  addEventListener(t, f) { (docListeners[t] ||= []).push(f); } };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") {
    posts.push([init.method, path, init.body && typeof init.body === "string" ? JSON.parse(init.body) : null]);
    if (refuse.has(path)) { refuse.delete(path); return { ok: false, status: 400, json: async () => ({ error: "Refused for the test" }) }; }
    return { ok: true, status: 200, json: async () => ({ ok: true, result: 1, changes: [], kept: [] }) };
  }
  let r = fx.routes[path];
  if (r === undefined && path.startsWith("/api/budget?") && budgetNow) r = budgetNow;
  if (r === undefined && path.startsWith("/api/audit/status")) r = { ok: true };
  if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: "not stubbed: " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
const ctx = vm.createContext({ document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: k => store[k] ?? null, setItem(k, v) { kept.push(k); store[k] = String(v); }, removeItem(k) { delete store[k]; } }, window: { print() { posts.push(["PRINT"]); } }, askStub: async () => true });
const run = code => vm.runInContext(code, ctx);
const pause = () => new Promise(r => setTimeout(r, 30));
const fire = async (id, type, target) => { for (const f of el(id).listeners[type] || []) await f({ target, preventDefault() {} }); await pause(); };
const click = async (dataset, id = "") => { for (const f of docListeners.click || []) await f({ target: { id, dataset, closest() { return this; } } }); await pause(); };
const btn = (dataset, id = "") => ({ id, dataset, closest() { return this; } });
const out = {};
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  run("ask = askStub");
  await pause();
  // A page drawn again gets a new box in a browser, so the stand-in's box starts with no listeners each time.
  const show = async (view, entity) => { run(`state.view = "${view}"; state.entity = ${entity}; state.month = "${fx.month}"; state.day = dayKey(); state.addr = { all: false, id: null, params: {} }; state.asAt = null`);
    el("bud").listeners = {}; el("bud").innerHTML = "";
    await run("render()"); await pause(); return view === "budget" ? el("bud").innerHTML : el("main").innerHTML; };
  // A balance this browser kept before slice 8: a month with no stored budget keeps it; its stored budget takes it once.
  const bk = `bal-${fx.exb}-${fx.month}`, dk = `asat-${fx.exb}-${fx.month}`;
  store[bk] = "2500.75"; store[dk] = `${fx.month}-09`;
  // Budget: worked out (no stored budget), stored with no balance, stored with a shortfall, a company with no ringgit account
  posts.length = 0;
  budgetNow = fx.budgets.worked; out.worked = await show("budget", fx.exb);
  out.carry_worked = { posts: posts.length, keys: [bk, dk].filter(k => k in store).length };
  await fire("bud", "click", btn({ budPrint: "budget" }, "bud-print")); out.worked_print = el("bud").innerHTML;
  await fire("bud", "click", btn({}, "bud-print-back"));
  posts.length = 0;
  budgetNow = fx.budgets.nobal; out.nobal = await show("budget", fx.exb);
  out.carry = { posts: posts.slice(), keys: [bk, dk].filter(k => k in store).length };
  store[bk] = "300"; posts.length = 0; await show("budget", fx.exb);  // a balance kept with no date: no date made up
  out.carry_nodate = { posts: posts.slice(), keys: [bk, dk].filter(k => k in store).length };
  posts.length = 0; await show("budget", fx.exb); out.carry_again = posts.length;  // once only
  await fire("bud", "click", btn({ budPrint: "budget" }, "bud-print")); out.nobal_print = el("bud").innerHTML;
  await fire("bud", "click", btn({}, "bud-print-go")); out.printed = posts.some(p => p[0] === "PRINT");
  await fire("bud", "click", btn({}, "bud-print-back"));
  // the balance typed in is saved on the stored budget; with no date entered none is made up; a refused save shows no Saved
  const balBox = Object.assign(el("bud-bal"), { closest() { return null; } });
  posts.length = 0; balBox.value = "1,234.50"; el("bud-date").value = "";
  refuse.add("/api/budget/header");
  await fire("bud", "change", balBox);
  out.refused = { posts: posts.filter(p => p[1] === "/api/budget/header").length, tick: el("bud").innerHTML.includes('id="bud-tick-bal"') };
  posts.length = 0; await fire("bud", "change", balBox);
  out.saved = posts.filter(p => p[1] === "/api/budget/header"); out.saved_tick = el("bud").innerHTML.includes('id="bud-tick-bal"');
  posts.length = 0; balBox.value = "1,500"; el("bud-date").value = `${fx.month}-12`;
  await fire("bud", "change", balBox); out.saved_dated = posts.filter(p => p[1] === "/api/budget/header");
  // Enter, then the box's change: one save
  posts.length = 0; balBox.value = "1,600";
  await Promise.all([fire("bud", "keydown", Object.assign(balBox, { key: "Enter" })), fire("bud", "change", balBox)]);
  out.once = posts.filter(p => p[1] === "/api/budget/header").length;
  budgetNow = fx.budgets.short; out.short = await show("budget", fx.exb);
  await fire("bud", "click", btn({ budPrint: "fund" }, "bud-fund")); out.fund_print = el("bud").innerHTML;
  await fire("bud", "click", btn({}, "bud-print-back"));
  // the balance kept is for another date than the page's
  budgetNow = fx.budgets.other; out.other = await show("budget", fx.exb);
  await fire("bud", "click", btn({ budPrint: "budget" }, "bud-print")); out.other_print = el("bud").innerHTML;
  // many lines: each currency pages on its own; Select all and Delete selected take the lines shown only
  budgetNow = fx.budgets.many; out.many = await show("budget", fx.exb);
  await fire("bud", "change", { id: "bud-all", checked: true, dataset: {}, closest() { return null; } });
  out.many_sel = el("bud").innerHTML;
  posts.length = 0; await fire("bud", "click", btn({}, "bud-delsel")); await pause();
  out.many_del = posts.filter(p => p[1] === "/api/budget/lines/delete");
  budgetNow = fx.budgets.stopped; out.stopped = await show("budget", fx.exr);
  budgetNow = null; out.usd = await show("budget", fx.exu);
  out.kept = kept.filter(k => /bal|asat|budget/i.test(k));
  // Recurring
  out.rc = await show("payees", fx.exr);
  await click({ rcType: "utility" }); out.rc_util = el("payeeTable").innerHTML; out.chips_util = el("rcChips").innerHTML;
  await click({ rcType: "all" });
  for (const f of docListeners.change || []) await f({ target: { id: "rc-stopped", checked: false, dataset: {}, matches() { return false; }, closest() { return null; } } });
  await pause(); out.rc_nostopped = el("payeeTable").innerHTML;
  posts.length = 0; await click({ addMonth: String(fx.p_new) }); out.add = posts.slice(); out.add_toast = el("toast").innerHTML || el("toast").textContent;
  await run(`editPayee(${fx.p_util})`); await pause(); out.form = el("drawer").innerHTML;
  await run(`editPayee(${fx.p_sal})`); await pause(); out.form_sal = el("drawer").innerHTML;
  await run(`editPayee("new")`); await pause(); out.form_new = el("drawer").innerHTML;
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
    res = subprocess.run([node, str(probe), app_bundle(tmp / "app.js"), str(fx)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
    check("the page script ran", o is not None, res.stderr[-800:])

if o:
    NOBAL = "Enter the bank balance to see funds to request"
    check("Budget, not set up: the no-balance sentence, and no fund request to print",
          NOBAL in o["worked"] and 'data-bud-print="fund"' not in o["worked"], o["worked"][:400])
    check("...the balance box can't be filled until the budget is set up (it is kept with the budget), and says so",
          re.search(r'id="bud-bal"[^>]*disabled', o["worked"]) is not None and "Set up the budget to enter the balance" in o["worked"])
    check("...the read-only list still to pay after the balance date, and Set up budget",
          "Still to pay after" in o["worked"] and "Hall rental - test" in o["worked"] and 'id="bud-setup"' in o["worked"])
    check("...the head names the company and its own bank account; Excel and Print budget are there",
          "EXB · Operating account" in o["worked"] and "/api/export/budget.xlsx?entity_id=" in o["worked"] and 'data-bud-print="budget"' in o["worked"])
    check("...its print says the funds were not worked out, bank balance not entered",
          "Funds to request: <b>not worked out, bank balance not entered</b>" in o["worked_print"] and "Bank balance (Operating account): <b>not entered</b>" in o["worked_print"],
          o["worked_print"][:600])
    check("Budget, stored with no balance: the same sentence, no fund request, the print not worked out",
          NOBAL in o["nobal"] and 'data-bud-print="fund"' not in o["nobal"] and "not worked out, bank balance not entered" in o["nobal_print"]
          and "Budget lines" in o["nobal"] and re.search(r'id="bud-bal"[^>]*disabled', o["nobal"]) is None)
    check("...Print sends the preview to the printer", o["printed"])
    check("...a refused save shows no Saved", o["refused"]["posts"] == 1 and not o["refused"]["tick"], o["refused"])
    check("...a balance typed in is saved on the stored budget (commas allowed), and Saved shows once the server took it",
          len(o["saved"]) == 1 and o["saved"][0][2]["balance"] == 1234.5 and o["saved"][0][2]["entity_id"] == EXB and o["saved_tick"], o["saved"])
    check("...with no date entered, none is made up (the 'Enter the date' note stays)", "as_at" not in o["saved"][0][2], o["saved"])
    check("...with a date entered, that date goes with it", len(o["saved_dated"]) == 1 and o["saved_dated"][0][2] == {"entity_id": EXB, "month": M, "balance": 1500, "as_at": day(12)}, o["saved_dated"])
    check("...Enter and the box's change save it once", o["once"] == 1, o["once"])
    check("a balance this browser kept before slice 8 stays while the month has no stored budget",
          o["carry_worked"] == {"posts": 0, "keys": 2}, o["carry_worked"])
    check("...and goes across to the stored budget once, with the date as kept, then leaves the browser",
          [p_[1] for p_ in o["carry"]["posts"]] == ["/api/budget/header"] and o["carry"]["posts"][0][2] == {"entity_id": EXB, "month": M, "balance": 2500.75, "as_at": day(9)}
          and o["carry"]["keys"] == 0 and o["carry_again"] == 0, o["carry"])
    check("...a browser balance kept with no date goes across with no date made up",
          len(o["carry_nodate"]["posts"]) == 1 and o["carry_nodate"]["posts"][0][2] == {"entity_id": EXB, "month": M, "balance": 300} and o["carry_nodate"]["keys"] == 0, o["carry_nodate"])
    check("...and nothing about the budget is kept in the browser", o["kept"] == [], o["kept"])
    check("Budget with a shortfall: the figure, Fund requisition needed, and Print fund request",
          NOBAL not in o["short"] and "Shortfall to request" in o["short"] and "RM 800.00" in o["short"] and 'data-bud-print="fund"' in o["short"], o["short"][:300])
    check("...the balance shown is the one kept with the stored budget, with its date",
          re.search(r'id="bud-bal"[^>]*value="1,000.00"', o["short"]) is not None and re.search(rf'id="bud-date"[^>]*value="{day(10)}"', o["short"]) is not None)
    check("...the fund request print lists only what is still to pay, and its total is the Still to pay figure",
          "Water utility - test" not in o["fund_print"] and "Hall rental - test" in o["fund_print"] and "Cleaning contract - test" in o["fund_print"]
          and '<td>TOTAL</td><td></td><td class="num">1,800.00</td>' in o["fund_print"] and "Still to pay: <b>RM 1,800.00</b>" in o["fund_print"], o["fund_print"][:800])
    check("...while the budget print lists every line at its budget",
          "Water utility - test" in o["nobal_print"] and "RM budget" in o["nobal_print"])
    check("Budget at another date than the balance kept: no funds worked out, it says which date the balance is for",
          NOBAL not in o["other"] and "Not worked out for " in o["other"] and f"The balance is for {int(day(10)[8:])} " in o["other"] and "open the budget as at that date to see funds to request" in o["other"]
          and 'data-bud-print="fund"' not in o["other"] and re.search(r'id="bud-bal"[^>]*value=""', o["other"]) is not None, o["other"][:600])
    check("...and its print the same: the balance not entered for this date, the funds not worked out",
          "not entered for " in o["other_print"] and "not worked out: the balance is for " in o["other_print"] and "RM 1,000.00" not in o["other_print"], o["other_print"][:800])
    check("many lines: each currency's table pages on its own (25 ringgit lines, every dollar line shown)",
          o["many"].count('data-sel="900') == 25 and o["many"].count('data-sel="910') == 3 and "No lines." not in o["many"]
          and "Showing 25 of 30 lines" in o["many"], re.findall(r"Showing [^<]*", o["many"]))
    check("...Select all picks the lines shown only, and Delete selected deletes those",
          "Delete selected (28)" in o["many_sel"] and len(o["many_del"]) == 1 and len(o["many_del"][0][2]["ids"]) == 28
          and not set(o["many_del"][0][2]["ids"]) & {90000 + i for i in range(25, 30)}, (re.findall(r"Delete selected[^<]*", o["many_sel"]), o["many_del"][:1]))
    check("...the payment picker shows each payment's amount beside its name and date",
          re.search(r'<option value="\d+"[^>]*>Hall rental - test · 1,500\.00 · paid ', o["short"]) is not None)
    check("a stopped ringgit account is named as stopped, not as none",
          "Ringgit current is stopped" in o["stopped"], o["stopped"][:500])
    check("...the fund request print: its title, the shortfall and the bank by its label",
          "Fund request for" in o["fund_print"] and "Shortfall = fund requisition needed: <b>RM 800.00</b>" in o["fund_print"]
          and "Bank balance (Operating account): <b>RM 1,000.00</b>" in o["fund_print"], o["fund_print"][:600])
    check("...Budget vs paid and Paid but not in the budget are there", "Budget vs paid" in o["short"] and "Paid against the budget" in o["short"]
          and "Paid but not in the budget" in o["short"])
    check("...the wide table carries the 'best done on a computer' note (shown at narrow widths only)", "Best done on a computer" in o["short"])
    check("a company with only a dollar account: the page says no ringgit balance is entered, naming its account",
          "only account is Dollar only (USD), so no RM balance is entered" in o["usd"] and NOBAL in o["usd"], o["usd"][:500])
    cat = fixture["routes"]["/api/meta"]["categories"]
    check("Recurring: the head, Excel and Add recurring payment",
          "<h1" in o["rc"] and "Recurring payments" in o["rc"] and f"/api/export/recurring.xlsx?entity_id={EXR}" in o["rc"] and 'data-edit-payee="new"' in o["rc"])
    chips = dict(re.findall(r'data-rc-type="(\w+)" aria-pressed="(?:true|false)">([^<]*) <span', o["rc"]))
    check("...the type filter: All, then the types in use, in Setup's words",
          list(chips)[0] == "all" and chips.get("utility") == "Utilities and phone (test)" and chips.get("salary") == cat["salary"]
          and chips.get("receipt") == cat["receipt"] and "consultant" not in chips, chips)
    counts = dict(re.findall(r'data-rc-type="(\w+)"[^>]*>[^<]*<span class="tab-n">(\d+)</span>', o["rc"]))
    check("...each with how many", counts.get("all") == str(len(recurring_route)) and counts.get("utility") == "1", counts)
    check("...picking a type shows only its rows, and marks it", "Electricity - test" in o["rc_util"] and "Staff salaries - test" not in o["rc_util"]
          and 'data-rc-type="utility" aria-pressed="true"' in o["chips_util"])
    check("...Show stopped off hides the stopped one", "Old storage - test" in o["rc"] and "Old storage - test" not in o["rc_nostopped"])
    check("...the table's columns and a type in Setup's words on its row",
          all(h in o["rc"] for h in ("Payee", "Type", "Paid / received", "Usual amount", "Bank / ref", "Status")) and "Utilities and phone (test)" in o["rc"])
    mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(M[5:]) - 1]
    check("...Add to <month> on each row not in the month yet, a stopped one too (its last payment), under its Stopped pill",
          sorted(re.findall(r'data-add-month="(\d+)"', o["rc"])) == sorted([str(p_new), str(p_old)]) and f"Add to {mon}" in o["rc"] and f"In {mon}" in o["rc"]
          and re.search(rf'Stopped</span><button type="button" class="ghost small" data-add-month="{p_old}"', o["rc"]) is not None, re.findall(r'data-add-month="(\d+)"', o["rc"]))
    check("...and Add to <month> asks the server to add it to the month on the page",
          [p[1] for p in o["add"]] == [f"/api/payees/{p_new}/add-to-month"] and o["add"][0][2] == {"month": M}, o["add"])
    fields = ["py-dir", "py-cat", "py-name", "py-desc", "py-party", "py-acct", "py-amt", "py-var", "py-off", "py-day", "py-bank", "py-ref",
              "py-match", "py-start", "py-end", "py-notes"]
    check("the form has every field, in the board's order", all(f'id="{f}"' in o["form"] for f in fields)
          and [o["form"].index(f'id="{f}"') for f in fields] == sorted(o["form"].index(f'id="{f}"') for f in fields), [f for f in fields if f'id="{f}"' not in o["form"]])
    check("...its types are Setup's, by their labels", f'>{cat["salary"]}</option>' in o["form"] and ">Utilities and phone (test)</option>" in o["form"])
    check("...Money in or out, Required on Payee and Day of month, the hints of the board",
          "Money in (received)" in o["form"] and o["form"].count('class="req">Required') == 2 and "Leave it empty if it changes every month." in o["form"]
          and "A month with fewer days uses its last day." in o["form"])
    check("...Where used, Stop using and History on a saved one; Save changes", "Where used" in o["form"] and 'data-payee-act="stop"' in o["form"]
          and 'data-hist="payees:' in o["form"] and "Save changes" in o["form"])
    check("...salary advances stay on the salary's form until HR › Claims and advances", "Salary advances" in o["form_sal"] and 'data-adv-add="' in o["form_sal"])
    check("...a new one: Add recurring payment, no Where used", "Add recurring payment" in o["form_new"] and "Where used" not in o["form_new"])

shutil.rmtree(tmp, ignore_errors=True)
if failures:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    raise SystemExit(1)
print("\nbudget_recurring_test: all passed")
