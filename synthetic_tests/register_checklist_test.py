"""Slice 2: the company month page split into Payments › Payments register and Payments › Monthly checklist, on made-up records only.

The server part runs the app on a temporary records folder (Flask's test client): two made-up companies, one Kept in SQL Account and
one Kept here, a month of payments (paid and complete, not paid, paid with documents missing and not in SQL, a salary, money in), a
checklist with items that ask for documents, two payroll workbook checks (the second replacing the first's workbook) and a filed
month. It checks what /api/month now gives for the pages (the latest payroll check, the workbook the check filed and the one it
replaced) and the register's Excel (the month report: every payment of the month on its Payments sheet).

The page part runs the page script in Node against a small stand-in for the page (an element per id), with the server's answers:
the register's tabs and their counts (no Not in SQL tab for a company kept here), money in counted apart from payments out, the
search (narrows the list and the counts, never in the address), a tab in the address, the link to the company's to-dos on the
Overview in place of the Next up card, a salary row's payroll check link, Excel, a filed month read only (no Add, no picking, the
payment read only); the checklist's "N of M done", its Missing documents filter listing exactly the items whose documents are
missing (and in the address), the payroll workbook item ("Uploaded on HR › Payroll › Workbook check", the earlier workbook it
replaced); Next up and count links landing on the right page and filter.

Run: .venv\\Scripts\\python -m synthetic_tests.register_checklist_test
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-register-checklist-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from openpyxl import load_workbook  # noqa: E402

from hrp import config, db, payrollcheck  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_bundle  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-101"}]},
    {"code": "EXH", "name": "Example Here Trading", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-202"}]},
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
EXA, EXH = ids["EXA"], ids["EXH"]
acct = {e["code"]: e["accounts"][0]["id"] for e in meta["entities"]}
M = db.current_cycle()
for e in (EXA, EXH):
    j("post", "/api/months/open", json={"entity_id": e, "month": M})

# ---------- the checklist: items that ask for documents, and one that doesn't ----------
for title, docs in (("Collect the timesheets", []), ("Payroll worked out", ["payroll"]), ("File the portal receipt", ["portal"])):
    j("post", "/api/setup/checklist", json={"action": "add", "entity_id": EXA, "from_month": M,
                                             "fields": {"completion": "hand", "title": title, "detail": "", "due_offset": 0, "due_day": 20, "docs": docs}})

PDF = b"%PDF-1.4\n% made-up test file\n"


def upload(field, ident, doc_type, name="test file.pdf"):
    return j("post", "/api/upload", data={"file": (io.BytesIO(PDF), name), field: str(ident), "doc_type": doc_type},
             content_type="multipart/form-data")


def pay(eid, desc, cat, amount, due, paid=None, direction=None, sql_ref=None):
    body = {"entity_id": eid, "month": M, "description": desc, "category": cat, "amount": amount, "account_id": acct["EXA" if eid == EXA else "EXH"],
            "due_date": f"{M}-{due:02d}", "paid_date": f"{M}-{paid:02d}" if paid else None}
    if direction:
        body["direction"] = direction
    pid = j("post", "/api/payments", json=body)["id"]
    if sql_ref:
        j("patch", f"/api/payments/{pid}", json={"sql_ref": sql_ref})
    return pid


done_pay = pay(EXA, "Office lease - test", "other", 1200, 3, paid=3, sql_ref="PV-TEST-001")
unpaid_pay = pay(EXA, "Cleaning service - test", "other", 300, 10)
nosql_pay = pay(EXA, "Courier charges - test", "other", 85.5, 10, paid=9)
salary_pay = pay(EXA, "Salaries - test", "salary", 9000, 25)
money_in = pay(EXA, "Rent received - test", "receipt", 700, 10, paid=8, direction="in", sql_ref="OR-TEST-001")
here_pay = pay(EXH, "Water bill - test", "utility", 45, 6, paid=6)
month = j("get", f"/api/month?entity={EXA}&month={M}")
lease = next(p for p in month["payments"] if p["id"] == done_pay)
for dt in lease["missing"]:
    upload("payment_id", done_pay, dt)

# ---------- two payroll workbook checks: the second replaces the workbook the first filed ----------
with db.connect() as con:
    con.arm("user", "test: payroll workbook checks")
    e = dict(con.execute("SELECT * FROM entities WHERE id = ?", (EXA,)).fetchone())
    for name, fix, chk in (("Payroll test v1.xlsx", 3, 1), ("Payroll test v2.xlsx", 2, 0)):
        report = {"counts": {"fix": fix, "check": chk, "note": 4}, "workbook_month": M, "pay": {"totals": {"to_pay": 900000}},
                  "headline": f"{fix} things to fix before paying"}
        payrollcheck.save(con, e, M, name, b"PK made-up workbook", report)
    con.commit()
    con.disarm()

month = j("get", f"/api/month?entity={EXA}&month={M}")
here = j("get", f"/api/month?entity={EXH}&month={M}")
by_title = {t["title"]: t for t in month["tasks"]}
wb_task = by_title["Payroll worked out"]
wb_docs = [d for d in wb_task["documents"] if d["doc_type"] == "payroll"]
check("the month gives the latest payroll check, counts only (no report, no names)",
      month["payroll_check"] and month["payroll_check"]["to_fix"] == 2 and month["payroll_check"]["to_check"] == 0
      and set(month["payroll_check"]) == {"id", "checked_at", "to_fix", "to_check", "notes"}, month["payroll_check"])
check("the workbook the check filed is on the item asking for it, marked as filed by the check",
      len(wb_docs) == 1 and wb_docs[0]["original_name"] == "Payroll test v2.xlsx" and wb_docs[0]["from_check"] is True, wb_docs)
check("...with the earlier workbook it replaced and what that check found",
      len(wb_docs[0]["earlier"]) == 1 and wb_docs[0]["earlier"][0]["name"] == "Payroll test v1.xlsx"
      and wb_docs[0]["earlier"][0]["check"]["to_fix"] == 3 and wb_docs[0]["earlier"][0]["replaced_at"] == wb_docs[0]["uploaded_at"], wb_docs[0]["earlier"])
up = upload("task_id", by_title["File the portal receipt"]["id"], "other")
plain = [d for d in j("get", f"/api/month?entity={EXA}&month={M}")["tasks"] if d["title"] == "File the portal receipt"][0]["documents"]
check("a document uploaded by hand is not marked as the check's and has no earlier ones",
      plain and all(d["from_check"] is False and d["earlier"] == [] for d in plain), plain)
check("a company with no check gives none", here["payroll_check"] is None)

# ---------- the register's Excel: the month report, every payment on its Payments sheet ----------
r = call("get", f"/api/export/month.xlsx?entity_id={EXA}&month={M}")
wb = load_workbook(io.BytesIO(r.data)) if r.status_code == 200 else None
rows = [row for row in wb["Payments"].iter_rows(min_row=2, values_only=True) if row[1]] if wb else []
descs = {p["description"] for p in month["payments"]}
check("the register's Excel is the month report, named for the company and month",
      r.status_code == 200 and r.mimetype.endswith("spreadsheetml.sheet") and f"EXA {M}" in r.headers.get("Content-Disposition", ""), r.status_code)
check("...with every payment of the month on its Payments sheet, money in included, and its status words",
      {x[1] for x in rows if x[1] in descs} == descs and any(x[3] == "Money in" for x in rows) and all(x[6] for x in rows if x[1] in descs), rows[:3])

# ---------- a filed month ----------
j("post", "/api/months/close", json={"entity_id": EXH, "month": M, "closed": True})
here = j("get", f"/api/month?entity={EXH}&month={M}")
check("the Kept here company's month is filed", bool(here["closed_at"]))

month = j("get", f"/api/month?entity={EXA}&month={M}")
fixture = {"exa": EXA, "exh": EXH, "month": M, "routes": {
    "/api/meta": j("get", "/api/meta"), f"/api/month?entity={EXA}&month={M}": month, f"/api/month?entity={EXH}&month={M}": here,
    f"/api/next?entity_id={EXA}": j("get", f"/api/next?entity_id={EXA}"), f"/api/next?entity_id={EXH}": j("get", f"/api/next?entity_id={EXH}"),
    "/api/next": j("get", "/api/next"), f"/api/overview?month={M}": j("get", f"/api/overview?month={M}"),
    # the Overview's cards (slice 1), each on its own route, for EXA's Overview
    **{f"/api/overview/{k}?month={M}&entity_id={EXA}": j("get", f"/api/overview/{k}?month={M}&entity_id={EXA}")
       for k in ("attention", "checklist", "due", "funds", "bank", "pl", "customers", "suppliers", "leave", "dates", "headcount", "requests", "rollover", "activity")}},
    "wb_doc": wb_docs[0]["id"], "salary": salary_pay, "unpaid": unpaid_pay, "nosql": nosql_pay, "here_pay": here_pay}
fx = tmp / "fixture.json"
fx.write_text(json.dumps(fixture), encoding="utf-8")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [appPath, fxPath] = process.argv.slice(2);
const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, posts = [], refuse = new Set();
const el = id => els[id] ||= { id, innerHTML: "", value: "", checked: false, hidden: id === "drawer", textContent: "", dataset: {}, classList: { add() {}, remove() {} } };
const document = { querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, addEventListener() {} };
async function fetch(path, init = {}) {
  if (init.method && init.method !== "GET") {
    posts.push([init.method, path, init.body && typeof init.body === "string" ? JSON.parse(init.body) : null]);
    if (refuse.has(path)) return { ok: false, status: 400, json: async () => ({ error: "Refused for the test" }) };
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  }
  const r = fx.routes[path] ?? (path.startsWith("/api/overview?") ? fx.routes[`/api/overview?month=${fx.month}`] : path.startsWith("/api/audit/status") ? { ok: true } : undefined);
  if (r === undefined) return { ok: false, status: 404, json: async () => ({ error: "not stubbed: " + path }) };
  return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(r)) };
}
const ctx = vm.createContext({ document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams,
  localStorage: { getItem: () => null, setItem() {} }, window: {} });
const run = code => vm.runInContext(code, ctx);
const pause = () => new Promise(r => setTimeout(r, 30));
const out = {};
(async () => {
  run(fs.readFileSync(appPath, "utf8"));
  await pause();
  const show = async (view, entity, params) => { run(`state.view = "${view}"; state.entity = ${entity}; state.month = "${fx.month}"; state.day = dayKey(); state.addr = { all: false, id: null, params: ${JSON.stringify(params || {})} }; state.reg = null; state.cl = null`);
    await run("render()"); return el("main").innerHTML; };
  out.reg = await show("entity", fx.exa);
  out.reg_addr = run("currentAddr()");
  run(`regSearch("courier")`); out.search = { panel: el("regPanel").innerHTML, tabs: el("regTabs").innerHTML, addr: run("currentAddr()"), say: el("regQSay").textContent };
  run(`regSearch("")`);
  run(`regPick("unpaid")`); out.unpaid = { panel: el("regPanel").innerHTML, tabs: el("regTabs").innerHTML, addr: run("currentAddr()"), note: el("regNote").textContent };
  run(`regPick("all")`); out.all_addr = run("currentAddr()");
  out.reg_nosql = await show("entity", fx.exa, { tab: "nosql" });
  // the bulk bar: a paid date only on payments not paid yet; a refused one stays picked and is named
  await show("entity", fx.exa);
  for (const id of [fx.unpaid, fx.salary, fx.nosql]) run(`regPickOne(${id}, true)`);
  refuse.add(`/api/payments/${fx.salary}`); posts.length = 0; el("regBulkDate").value = "2026-01-15";
  await run(`regBulk("date")`);
  out.bulk = { posts: posts.filter(x => x[0] === "PATCH"), picked: run("state.reg.picked"), toast: el("toast").textContent };
  refuse.clear();
  // a new tab or search starts a new selection; the same search again keeps it
  run(`state.reg.picked = []; regPickOne(${fx.unpaid}, true)`); run(`regPick("unpaid")`); out.pick_tab = run("state.reg.picked.length");
  run(`regPickOne(${fx.unpaid}, true)`); run(`regSearch("")`); out.pick_same = run("state.reg.picked.length");
  run(`regSearch("clean")`); out.pick_search = run("state.reg.picked.length");
  run(`regSearch("")`); run(`regPick("all")`);
  out.here_nosql = await show("entity", fx.exh, { tab: "nosql" }); out.here_nosql_addr = run("currentAddr()");
  out.old_task = run(`JSON.stringify(parseAddr("#/EXA/${fx.month}/payments/register?task=7"))`);
  out.old_task_pay = run(`JSON.stringify(parseAddr("#/EXA/${fx.month}/payments/register/21"))`);
  out.here = await show("entity", fx.exh);
  run(`openPayment(${fx.here_pay})`); out.here_drawer = el("drawer").innerHTML;
  run(`closeDrawer(true)`);
  out.cl = await show("checklist", fx.exa);
  out.cl_addr0 = run("currentAddr()");
  run(`clPick("missing")`); out.missing = { panel: el("clPanel").innerHTML, addr: run("currentAddr()"), tabs: el("clTabs").innerHTML };
  out.cl_missing = await show("checklist", fx.exa, { tab: "missing" });
  run(`clPick("all")`); run(`clHist(${fx.wb_doc})`); out.hist = el("clPanel").innerHTML;
  out.cl_here = await show("checklist", fx.exh);
  // links: what Next up rows and the Overview's counts say (view "entity", as the server words them) land on the right page and filter
  const g = { entity_id: fx.exa, month: fx.month };
  out.links = {
    task: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "entity", task_id: 7 })}))`),
    tasks: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "entity", task_id: 7, task_ids: [7, 8] })}))`),
    overdue: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "entity", filter: "overdue_tasks" })}))`),
    payment: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "entity", payment_id: 21 })}))`),
    payments: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "entity", payment_ids: [21, 22] })}))`),
    bank: run(`addrOf(linkPlace(${JSON.stringify({ ...g, view: "bank", account_id: 5, filter: "to_explain" })}))`),
    next: run(`(${JSON.stringify(fx.routes["/api/next"].items)}).map(r => [r.go, addrOf(linkPlace(r.go))])`) };
  out.pills = {};
  for (const kind of ["docs_missing", "not_in_sql", "part_paid", "overdue_tasks", "not_on_statement"]) {
    run(`state.view = "overview"; state.month = "${fx.month}"`);
    await run(`pillGo(${JSON.stringify(kind)}, ${fx.exa})`); await pause();
    out.pills[kind] = { view: run("state.view"), params: run("JSON.stringify(state.addr.params)"), addr: run("currentAddr()") };
  }
  await show("overview", fx.exa); await run("OV.done");
  out.overview = ["attention", "checklist"].map(k => el("ov-c-" + k).innerHTML).join("");
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
node = shutil.which("node")
res = subprocess.run([node, str(probe), app_bundle(tmp / "app.js"), str(fx)], capture_output=True, text=True, encoding="utf-8", timeout=120)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the page script ran", o is not None, res.stderr[-800:])
if o is None:
    print("\n%d failed: %s" % (len(failures), "; ".join(failures)))
    raise SystemExit(1)


def tab_counts(html, attr):
    return {k: int(n) for k, n in re.findall(rf'{attr}="(\w+)"[^>]*>[^<]*<span class="tab-n">(\d+)</span>', html)}


def rows_in(html):
    return sorted({int(x) for x in re.findall(r'<tr class="click[^"]*" id="pay-(\d+)"', html)})


def kind(p):
    return "unpaid" if p["status"] == "planned" else "complete" if p["status"] == "complete" else "attention"


P = month["payments"]
want = {"all": len(P), "unpaid": sum(kind(p) == "unpaid" for p in P), "attention": sum(kind(p) == "attention" for p in P),
        "nosql": sum(bool(p["not_in_sql"]) for p in P), "complete": sum(kind(p) == "complete" for p in P)}
got = tab_counts(o["reg"], "data-reg-tab")
check("the register's tabs are All, Not paid, Needs attention, Not in SQL, Complete, in that order",
      list(got) == ["all", "unpaid", "attention", "nosql", "complete"], list(got))
check("...each counting its payments", got == want and want["unpaid"] >= 2 and want["nosql"] >= 1 and want["complete"] >= 1, (got, want))
check("the tabs follow the keyboard rules: role=tab, aria-selected, one tab in the Tab order, a labelled tablist and panel",
      'role="tablist" class="segtabs" id="regTabs" aria-label="Filter payments"' in o["reg"] and o["reg"].count('role="tab"') == 5
      and o["reg"].count('tabindex="0">') == 1 and 'id="reg-tab-all" data-reg-tab="all" aria-selected="true"' in o["reg"]
      and 'id="regPanel" role="tabpanel" tabindex="0" aria-labelledby="reg-tab-all"' in o["reg"])
gh = tab_counts(o["here"], "data-reg-tab")
check("a company kept here has no Not in SQL tab (nor figure)", list(gh) == ["all", "unpaid", "attention", "complete"] and 'data-reg-tab="nosql"' not in o["here"], list(gh))
out_p, in_p = [p for p in P if p["direction"] != "in"], [p for p in P if p["direction"] == "in"]
check("money in is counted apart: payments out fully documented counts only money out",
      f"<b>{sum(kind(p) == 'complete' for p in out_p)} / {len(out_p)}</b><span>Payments out fully documented</span>" in o["reg"], o["reg"][:300])
check("...with money in a figure of its own", f"<b>{sum(kind(p) == 'complete' for p in in_p)} / {len(in_p)}</b><span>Money in fully documented</span>" in o["reg"])
rin = next(p for p in P if p["id"] == money_in)
grp = o["reg"].split(f"Due {int(rin['due_date'][8:])} ")[1].split("</tr>")[0]
check("...and in its due date's total, apart from money out (green, with a +)", '<span class="recv">+RM 700.00</span>' in grp and "RM 385.50" in grp, grp)
check("every payment of the month is a row, grouped by due date", rows_in(o["reg"]) == sorted(p["id"] for p in P) and '<tr class="group">' in o["reg"])
check("the columns are Payment, Type, Paid / received, Amount, Documents, Status",
      re.sub(r"<[^>]+>", "|", o["reg"].split("<thead>")[1].split("</thead>")[0]).replace("|", " ").split() ==
      ["Payment", "Type", "Paid", "/", "received", "Amount", "Documents", "Status"])
s = o["search"]
check("search narrows the list", rows_in(s["panel"]) == [nosql_pay], rows_in(s["panel"]))
check("...and the tab counts", tab_counts(s["tabs"], "data-reg-tab") == {"all": 1, "unpaid": 0, "attention": 1, "nosql": 1, "complete": 0}, s["tabs"])
check("...says how many match, and stays out of the address", s["say"] == "1 payment matches" and "courier" not in s["addr"].lower() and "?" not in s["addr"], s)
u = o["unpaid"]
check("a tab is written in the address", u["addr"] == f"#/EXA/{M}/payments/register?tab=unpaid" and o["all_addr"] == f"#/EXA/{M}/payments/register", (u["addr"], o["all_addr"]))
check("...and shows only its payments, with its note", rows_in(u["panel"]) == sorted(p["id"] for p in P if kind(p) == "unpaid") and u["note"].startswith("Not paid:"), u["note"])
check("an address with a tab opens on it", rows_in(o["reg_nosql"]) == sorted(p["id"] for p in P if p["not_in_sql"]) and 'data-reg-tab="nosql" aria-selected="true"' in o["reg_nosql"])
nx = fixture["routes"][f"/api/next?entity_id={EXA}"]["items"]
n, over = len(nx), sum(r["state"] == "overdue" for r in nx)
todo = (f"{n} to-do{'' if n == 1 else 's'} for EXA on the Overview" + (f", {over} overdue" if over else "")) if n else "Nothing to do for EXA on the Overview"
check("the link to the company's to-dos on the Overview stands where the Next up card was", f'href="#/EXA/{M}/overview" id="todoLink"' in o["reg"]
      and f"{todo}</a>" in o["reg"] and 'id="nextUp"' not in o["reg"] and 'class="next-row"' not in o["reg"], todo)
sal = o["reg"].split(f'id="pay-{salary_pay}"')[1].split("</tr>")[0]
check("a salary row says what the payroll check found, with a link to HR > Payroll > Workbook check",
      f'href="#/EXA/{M}/hr/payroll/workbook"' in sal and "The payroll check found 2 things to fix" in sal, sal[:400])
check("...and other rows don't", "payroll check" not in o["reg"].split(f'id="pay-{nosql_pay}"')[1].split("</tr>")[0].lower())
check("Excel and Add a payment, and the link to the Monthly checklist", f'href="/api/export/month.xlsx?entity_id={EXA}&month={M}" download>' in o["reg"]
      and 'id="addPayment"' in o["reg"] and f'href="#/EXA/{M}/payments/checklist"' in o["reg"])
check("rows can be picked for the bulk bar in an open month", f'data-reg-pick="{unpaid_pay}"' in o["reg"] and "data-reg-pick-all" in o["reg"])
B = o["bulk"]
check("Set paid date sets the date only on picked payments not paid yet (a paid one keeps its own date)",
      sorted(int(x[1].rsplit("/", 1)[1]) for x in B["posts"]) == sorted([unpaid_pay, salary_pay]) and all(x[2] == {"paid_date": "2026-01-15"} for x in B["posts"]), B["posts"])
check("...a refused one stays picked and is named, with how many were set and how many kept their date",
      B["picked"] == [salary_pay] and "set on 1 of 2" in B["toast"] and "1 payment already paid kept its own date" in B["toast"]
      and "not set on: Salaries - test (Refused for the test)" in B["toast"], B)
check("a new tab or a new search clears the selection (the bulk bar never acts on payments not listed); the same search keeps it",
      o["pick_tab"] == 0 and o["pick_same"] == 1 and o["pick_search"] == 0, (o["pick_tab"], o["pick_same"], o["pick_search"]))
check("a tab the company doesn't have is dropped from the address", o["here_nosql_addr"] == f"#/EXH/{M}/payments/register" and 'data-reg-tab="all" aria-selected="true"' in o["here_nosql"], o["here_nosql_addr"])
ot, op = json.loads(o["old_task"]), json.loads(o["old_task_pay"])
check("an old register address naming checklist items opens them on the Monthly checklist, marked",
      ot["view"] == "checklist" and ot["params"] == {"task": "7"} and op["view"] == "entity" and op["id"] == "21", (ot, op))
h, hd = o["here"], o["here_drawer"]
check("a filed month says so and sends Reopen to the Monthly checklist", "was filed on" in h and "Reopen on the Monthly checklist" in h and f'href="#/EXH/{M}/payments/checklist"' in h)
check("a filed month is read only: no Add a payment, no picking", 'id="addPayment"' not in h and "data-reg-pick" not in h)
check("...and its payment opens read only: fields disabled, no upload, replace, remove, save or delete",
      re.search(r'<input id="pf-amount" type="number" step="0\.01"[^>]* value="45" disabled>', hd) and "data-upload" not in hd and "data-remove-doc" not in hd
      and "data-pd-menu" not in hd and "Save details" not in hd and "deletePayment" not in hd and "so this payment is read only" in hd
      and "Read only: the month is filed" in hd, hd[:500])

# ---------- the checklist ----------
T = [t for t in month["tasks"] if not t["waiting"]]
cl = o["cl"]
check("the checklist says how many items are done, as 'N of M done'", f'<b class="cl-count">{sum(t["done"] for t in T)} of {len(T)} done</b>' in cl
      and 'role="progressbar"' in cl, re.findall(r'cl-count">[^<]*', cl))
ct = tab_counts(cl, "data-cl-tab")
missing = sorted(t["id"] for t in T if t["missing"])
check("its filters are All items, Not done, Done, Missing documents, each counted",
      list(ct) == ["all", "open", "done", "missing"] and ct == {"all": len(T), "open": sum(not t["done"] for t in T), "done": sum(t["done"] for t in T), "missing": len(missing)}, ct)


def items_in(html):
    return sorted({int(x) for x in re.findall(r'<div class="task [^"]*" id="task-(\d+)"', html)})


m = o["missing"]
check("the Missing documents filter lists exactly the items whose documents are missing",
      items_in(m["panel"]) == missing and by_title["File the portal receipt"]["id"] in missing and by_title["Collect the timesheets"]["id"] not in missing
      and wb_task["id"] not in missing, (items_in(m["panel"]), missing))
check("...is written in the address, and an address with it opens on it",
      m["addr"] == f"#/EXA/{M}/payments/checklist?tab=missing" and o["cl_addr0"] == f"#/EXA/{M}/payments/checklist" and items_in(o["cl_missing"]) == missing, m["addr"])
wb = cl.split(f'id="task-{wb_task["id"]}"')[1].split('<div class="task ')[0]
check("the payroll workbook item: the workbook, 'Uploaded on HR > Payroll > Workbook check', and the way to the check",
      "Payroll test v2.xlsx" in wb and "Uploaded on HR › Payroll › Workbook check" in wb and f'href="#/EXA/{M}/hr/payroll/workbook">Open the workbook check' in wb, wb[:600])
check("...replaced through the check (no Replace on it), still removable", f'data-replaces="{fixture["wb_doc"]}"' not in wb and f'data-remove-doc="{fixture["wb_doc"]}"' in wb)
check("...with its replaced history, closed until asked for", "Show the earlier workbook (1 replaced)" in wb and "Payroll test v1.xlsx" not in wb)
hist = o["hist"].split(f'id="task-{wb_task["id"]}"')[1].split('<div class="task ')[0]
check("...and open: the earlier workbook, what its check found, when it was replaced",
      "Hide the earlier workbook (1 replaced)" in hist and "<s>Payroll test v1.xlsx</s>" in hist and "3 things to fix before paying, 1 to check; 4 notes" in hist
      and "Replaced " in hist and 'aria-expanded="true"' in hist, hist[-700:])
check("Mark month as filed on an open month, Reopen on a filed one", 'data-close-month="1"' in cl and "data-reopen-month" not in cl
      and 'data-reopen-month="1">Reopen</button>' in o["cl_here"] and 'data-close-month' not in o["cl_here"])
check("the checklist links to the to-dos on the Overview and the month's register", 'id="todoLink"' in cl and f'href="#/EXA/{M}/payments/register"' in cl)

# ---------- links ----------
L = o["links"]
check("a Next up row about a checklist item lands on the Monthly checklist with the item marked",
      L["task"] == f"#/EXA/{M}/payments/checklist?task=7" and L["tasks"] == f"#/EXA/{M}/payments/checklist?task=7,8" and L["overdue"] == f"#/EXA/{M}/payments/checklist?mark=overdue_tasks", L)
check("one about payments lands on the Payments register", L["payment"] == f"#/EXA/{M}/payments/register/21" and L["payments"] == f"#/EXA/{M}/payments/register?pay=21,22", L)
check("other rows are unchanged", L["bank"] == f"#/EXA/{M}/accounting/bank?filter=to_explain&account=5")
check("every Next up row of the made-up month has an address on the right page",
      all(a and ("/payments/checklist" in a) == bool(g.get("task_id")) for g, a in L["next"] if g["view"] == "entity"), L["next"])
P_ = o["pills"]
check("the Overview's Documents missing count opens the checklist's Missing documents filter",
      P_["docs_missing"]["view"] == "checklist" and P_["docs_missing"]["addr"] == f"#/EXA/{M}/payments/checklist?tab=missing", P_["docs_missing"])
check("...Not in SQL the register's Not in SQL tab", P_["not_in_sql"]["view"] == "entity" and P_["not_in_sql"]["addr"] == f"#/EXA/{M}/payments/register?tab=nosql", P_["not_in_sql"])
check("...Part paid the Needs attention tab with them marked", P_["part_paid"]["addr"] == f"#/EXA/{M}/payments/register?mark=part_paid&tab=attention", P_["part_paid"])
check("...overdue checklist items the Monthly checklist, marked", P_["overdue_tasks"]["view"] == "checklist" and P_["overdue_tasks"]["addr"] == f"#/EXA/{M}/payments/checklist?mark=overdue_tasks", P_["overdue_tasks"])
check("...a past due word the register, marked", P_["not_on_statement"]["addr"] == f"#/EXA/{M}/payments/register?mark=not_on_statement", P_["not_on_statement"])
check("the Overview's Checklist card opens the Monthly checklist, its Needs attention counters the register's tabs and the checklist's filter",
      f'href="#/EXA/{M}/payments/checklist"' in o["overview"] and f'href="#/EXA/{M}/payments/register?tab=nosql"' in o["overview"]
      and f'href="#/EXA/{M}/payments/checklist?tab=missing"' in o["overview"], o["overview"][:600])

# ---------- one document can retire several (every branch is listed, newest first) ----------
extra = upload("task_id", wb_task["id"], "payroll", "Payroll test by hand.xlsx")["id"]
with db.connect() as con:
    con.arm("user", "test: a second workbook retired by the same check")
    con.execute("UPDATE documents SET replaced_by = ? WHERE id = ?", (fixture["wb_doc"], extra))
    con.commit()
    con.disarm()
doc = next(d for t in j("get", f"/api/month?entity={EXA}&month={M}")["tasks"] for d in t["documents"] if d["id"] == fixture["wb_doc"])
check("a document that retired several lists every one, newest first",
      [x["name"] for x in doc["earlier"]] == ["Payroll test by hand.xlsx", "Payroll test v1.xlsx"], doc["earlier"])

readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "register_checklist_test" in readme)

shutil.rmtree(tmp, ignore_errors=True)
print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
