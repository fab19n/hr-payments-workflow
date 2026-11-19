"""The menu's data: /api/meta gives each company its kind, kind_label and pages (hrp/pages.py), and every Next up row
says which menu area it belongs to (nextup.AREA), on made-up records.

1. A company kept in SQL Account and one kept here: kind, kind_label and pages; the sets differ exactly by the SQL
   import and the four Kept here placeholders; every key is in the universe; the old fields stay.
2. hrp/pages.py names no company (a source check).
3. Every rule 1-15 has an area in the allowed set, every _row call in nextup.py is for a rule with one, and the rows a
   fixture produces (the checklist, a payment due soon, the backup) each carry one.

Run: .venv\\Scripts\\python -m synthetic_tests.meta_pages_test
"""
import json
import os
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-meta-pages-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db, nextup, pages  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

passed = []


def check(name, ok, detail=""):
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    passed.append(name)
    print("PASS", name)


(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "uses_sql": True,
     "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False,
     "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")
db.init()
c0 = app.test_client()
B, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


class _C:
    def get(self, p):
        return c0.get(B + p)

    def post(self, p, **kw):
        return c0.post(B + p, **kw)


c = _C()

# 1. meta
meta = c.get("/api/meta").get_json()
by = {e["code"]: e for e in meta["entities"]}
sql, here = by["EXA"], by["EXB"]
check("meta kinds", (sql["kind"], here["kind"]) == ("sql", "here"), (sql["kind"], here["kind"]))
check("meta labels", (sql["kind_label"], here["kind_label"]) == ("Kept in SQL Account", "Kept here"))
check("old fields kept", sql["uses_sql"] == 1 and here["uses_sql"] == 0 and sql["accounts"] and sql["name"])
check("every key in the universe", all(set(e["pages"]) <= set(pages.ALL) for e in (sql, here)))
check("no repeats", all(len(e["pages"]) == len(set(e["pages"])) for e in (sql, here)))
check("sets differ exactly as designed",
      set(sql["pages"]) - set(here["pages"]) == {"accounting/sql"}
      and set(here["pages"]) - set(sql["pages"]) == {"accounting/sales", "accounting/purchases", "accounting/journals",
                                                      "accounting/period-close"})
common = set(sql["pages"]) & set(here["pages"])
check("shared pages", {"overview", "hr/payroll", "payments/to-pay", "accounting/einvoices", "accounting/parties",
                       "accounting/statutory", "admin/backup"} <= common)
check("no sign-in page yet", not any("users" in p for p in pages.ALL))

# 2. no company codes in hrp/pages.py
text = Path(pages.__file__).read_text(encoding="utf-8")
codes = [r["code"] for r in db.connect().execute("SELECT code FROM entities")] + ["AISB", "AIL", "AIP"]
check("pages.py names no company", not any(re.search(rf"\b{k}\b", text) for k in codes))

# 3. areas
check("every rule has an area", set(nextup.AREA) == set(range(1, 16)) and set(nextup.AREA.values()) <= set(nextup.AREAS))
src = Path(nextup.__file__).read_text(encoding="utf-8")
used = {int(n) for n in re.findall(r"_row\((\d+),", src)}
check("every _row call is for a rule with an area", used and used <= set(nextup.AREA), used)

con = db.connect()
today = date.today()
cycle = db.current_cycle(today)
for e in con.execute("SELECT id FROM entities").fetchall():
    c.post("/api/months/open", headers=H, json={"entity_id": e["id"], "month": cycle})
    c.post("/api/payments", headers=H, json={"entity_id": e["id"], "month": cycle, "description": "Example hosting",
                                              "category": "other", "amount": 120, "due_date": (today + timedelta(days=1)).isoformat()})
    c.post("/api/payments", headers=H, json={"entity_id": e["id"], "month": cycle, "description": "Example rent",
                                              "category": "other", "amount": 80, "due_date": (today - timedelta(days=9)).isoformat()})
rows = nextup.items(db.connect(), today)
seen = {r["rule"] for r in rows}
check("fixture gives rows", {5, 13} <= seen, seen)
check("every row has an allowed area", all(r.get("area") in nextup.AREAS for r in rows), [(r["rule"], r.get("area")) for r in rows])
check("area follows the rule", all(r["area"] == nextup.AREA[r["rule"]] for r in rows))
api = c.get("/api/next").get_json()
check("the API rows carry it", api["items"] and all(r["area"] in nextup.AREAS for r in api["items"]))
check("every rule has a page that exists, in its area", set(nextup.PAGE) == set(range(1, 16)) and all(p in pages.ALL and nextup.AREA[r] == p.split("/")[0] for r, p in nextup.PAGE.items()))
check("joiner and leaver filings count on the monthly checklist", nextup.PAGE[2] == "payments/checklist" and nextup.AREA[2] == "payments")
check("every row has its rule's page", all(r.get("page") == nextup.PAGE[r["rule"]] for r in rows) and all(r["page"] in pages.ALL for r in api["items"]))
check("go objects unchanged", all("view" in r["go"] and "area" not in r["go"] and "page" not in r["go"] for r in rows))
print(f"{len(passed)} checks passed")
