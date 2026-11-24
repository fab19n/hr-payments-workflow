"""Setup's records and First run (slice 9a), on made-up records only.

1. The Setup menu and its sections as the server gives them: every field of a section is in exactly one group of its record
   dialog, each list section has its sentence and glyph, Recurring payments is a link to its own page (it has one home), the
   Matching words group is the one for companies Kept in SQL Account only, the groups keep their shape, and a company's list
   has the Books column (Kept in SQL Account or Kept here).
2. Where used, and Stop using, Use again and Delete: each asks why (the reason is in the audit trail), a record in use can't be
   deleted (and says what uses it), one the app relies on can't be deleted, an unused one can; a deleted record is gone from its list.
3. Show deleted and Put it back: a deleted record is listed with when, who and why; Put it back is previewed first, needs a
   reason, brings it back as it was, and a record put back is no longer listed; a record whose key was taken since says why it
   can't be put back; one put back already is refused.
4. First run and Move setup count the same way: counts come from the setup file (hrp/setupfile.py), where a stopped record is in
   and a deleted one is out. The preview a new install shows (First run's import and Move setup's) equals what the file holds,
   and once imported, what the install holds (the sentence Move setup says when it refuses another import) is the same figures.

Made-up companies EXA (kept in SQL Account) and EXB (kept here); a third, stopped; a fourth, deleted.

Run: .venv\\Scripts\\python -m synthetic_tests.setup_records_test
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-setup-records-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # part 4's new install: --import <setup.json> <what it holds afterwards>

from hrp import config, db, masters, rulebook, rules, setupfile, sqlfetch  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

if not CHILD:
    (tmp / "seed.json").write_text(json.dumps({"entities": [
        {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}],
         "payees": [{"name": "Test Payee", "category": "salary", "amount": 3000, "due_day": 28, "month_offset": 1}]},
        {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
    ]}), encoding="utf-8")

passed, failed = [], []
from synthetic_tests.flags import KEEP_GOING, keep_going  # noqa: E402  (one place for the flag, so a check of it is about the flag the tests use)


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:600]}" if detail else ""))
        if not KEEP_GOING:
            sys.exit(1)
        failed.append(name)
        return
    passed.append(name)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(c, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def _refused(fn):
    """Whether fn raises Refused with 'too long'."""
    try:
        fn()
    except masters.Refused as x:
        return "too long" in str(x)
    return False


def last_tx():
    return q("SELECT * FROM audit_tx ORDER BY id DESC LIMIT 1")[0]


def write(why, *statements):
    con = db.connect()
    con.arm("user", f"test: {why}")
    try:
        for sql, args in statements:
            con.execute(sql, args)
        con.commit()
    finally:
        con.disarm()
        con.close()


# What a record holding states in a setup file is called in the file's lists (hrp/setupfile.py LISTS) and in what an install holds (HOLDING).
HELD_AS = {"entities": "companies", "accounts": "bank accounts", "payees": "recurring payments", "parties": "customers and suppliers",
           "gl_accounts": "GL accounts", "statutory_accounts": "statutory accounts", "checklist_items": "checklist items", "advances": "salary advances"}


def held(holding):
    """{what: n} of what an install says it holds (setupfile.holding), by the file's names for the lists."""
    name = {}
    for table, one, many in setupfile.HOLDING:
        name[one] = name[many] = HELD_AS.get(table, many)
    return {name[w]: n for w, n in holding}


def counted(preview):
    """{what: n} of a preview's counts, with each list under its plural name (a list of one is counted as the one thing)."""
    one = {v: k for k, v in setupfile.ONE.items()}
    return {one.get(w, w): n for w, n in preview["counts"]}


if CHILD:
    src, dst = Path(sys.argv[2]), Path(sys.argv[3])
    data = json.loads(src.read_text(encoding="utf-8"))
    state = call("get", "/api/setup/import")
    check("[new install] it holds no company data, so it may import", state["empty"] is True and state["holding"] == [])
    pv = call("post", "/api/setup/import", json={"setup": data, "preview": True})
    check("[new install] the preview leaves nothing behind", not q("SELECT id FROM entities"))
    # a code held longer than a new one may be typed is accepted from a file (up to three times that, in capitals); more is refused, naming the row
    def with_code(code):
        d = json.loads(json.dumps(data))
        next(a for a in d["accounts"] if a["label"] == "Legacy")["gl_code"] = code
        return c.post(BASE + "/api/setup/import", headers=H, json={"setup": d, "preview": True})
    edge = {n: with_code("x" * n).status_code for n in (600, 601, 700)}
    bad = with_code("x" * 700).get_json()
    check("[new install] a GL code of 700 characters in the file is refused, naming the row and the field, and 600 is the most that is taken",
          edge == {600: 200, 601: 400, 700: 400} and "Legacy" in bad["error"] and "GL account code" in bad["error"] and "too long" in bad["error"], (edge, bad))
    check("[new install] ...and a refused file imports nothing", not q("SELECT id FROM entities") and not q("SELECT id FROM accounts"))
    call("post", "/api/setup/import", json={"setup": data, "reason": "test: a new install"})
    now = call("get", "/api/setup/import")
    dst.write_text(json.dumps({"preview": counted(pv), "holding": held(now["holding"]), "empty": now["empty"],
                               "codes": [r["code"] for r in q("SELECT code FROM entities ORDER BY id")],
                               "active": {r["code"]: r["active"] for r in q("SELECT code, active FROM entities")},
                               "gl_codes": {r["label"]: r["gl_code"] for r in q("SELECT label, gl_code FROM accounts")}, "refused": bad["error"]}), encoding="utf-8")
    print("child done")
    sys.exit(0)

# ---------- 1. the menu and sections as the server gives them ----------
def flag_in_new_process(value):
    env = {k: v for k, v in os.environ.items() if k != "HRP_KEEP_GOING"}
    if value is not None:
        env["HRP_KEEP_GOING"] = value
    return subprocess.run([sys.executable, "-c", "from synthetic_tests.flags import KEEP_GOING; print(KEEP_GOING)"], cwd=str(Path(__file__).resolve().parents[1]),
                          env=env, capture_output=True, text=True).stdout.strip()


from synthetic_tests import flags  # noqa: E402
check("HRP_KEEP_GOING turns keep-going on only for a value other than empty or 0, read in a new process from the module both tests import (the variable they use)",
      flags.KEEP_GOING is KEEP_GOING and [flag_in_new_process(v) for v in ("1", "yes", "0", "", None)] == ["True", "True", "False", "False", "False"])
T = call("get", "/api/setup/types")
kinds = T["kinds"]
check("the groups keep their shape: [name, [sections]], with Matching words and the settings", dict((g[0], g[1]) for g in T["groups"])["People and payments"] == ["payees", "parties"]
      and dict((g[0], g[1]) for g in T["groups"])["Matching words"] == ["guess_words", "hint_words", "filing_words"], T["groups"])
check("the Matching words group is the one for companies Kept in SQL Account only", T["sql_only"] == ["Matching words"], T.get("sql_only"))
listed = [k for k, v in kinds.items() if not v.get("bespoke") and not v.get("single")]
bad = []
for k in listed:
    fields = [f["key"] for f in kinds[k]["fields"]]
    keys = [x for g in kinds[k]["field_groups"] for x in g[1]]
    if sorted(fields) != sorted(keys):
        bad.append((k, sorted(set(fields) ^ set(keys))))
check("every field of a list section is in exactly one group of its record dialog", not bad and len(listed) == 10, bad)
check("every list section has its sentence under the heading, a glyph and its Stop and Use again notes",
      all(kinds[k].get("intro") and kinds[k].get("glyph") and kinds[k].get("stop_note") and kinds[k].get("use_note") and kinds[k].get("delete_note") for k in listed))
check("Recurring payments is a link to its page, with its note, and the others are not links",
      kinds["payees"].get("link_note") == "Opens Payments › Recurring" and not any(kinds[k].get("link_note") for k in kinds if k != "payees"), kinds["payees"])
check("every section has a glyph, for the menu", all(v.get("glyph") for v in kinds.values()))
check("a company's list has the Books column (Kept in SQL Account or Kept here)", [x["key"] for x in kinds["entities"]["columns"]][-1] == "uses_sql")
check("the types are listed by name first, as the boards have them", kinds["payment_types"]["columns"][0]["key"] == "label" and kinds["doc_types"]["columns"][0]["key"] == "label")
check("a company is Kept in SQL Account by default, and the field says what each answer means",
      next(f for f in kinds["entities"]["fields"] if f["key"] == "uses_sql")["default"] == 1
      and "Kept here" in next(f for f in kinds["entities"]["fields"] if f["key"] == "uses_sql")["hint"])

# ---------- 2. Where used; Stop using, Use again and Delete ask why ----------
EXA, EXB = [r["id"] for r in q("SELECT id FROM entities ORDER BY id")]
lev = call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_levy", "label": "Test levy", "direction": "out"}})
rec = call("get", f"/api/setup/payment_types/{lev['id']}")
check("Where used: a new type is used nowhere, and can be deleted", rec["used_by"] == [] and rec["used_total"] == 0 and rec["can_delete"] is True)
sal = {r["key"]: r for r in call("get", "/api/setup/payment_types")["rows"]}["salary"]
sr = call("get", f"/api/setup/payment_types/{sal['id']}")
check("Where used: a type in use says what uses it, and can't be deleted", sr["used_total"] >= 1 and sr["can_delete"] is False and sr["used_by"], sr["used_by"])
r = c.delete(BASE + f"/api/setup/payment_types/{sal['id']}", headers=H, json={"reason": "test"})
check("...the refusal says what uses it and to stop using it instead", r.status_code in (400, 409) and "Stop using it instead" in r.get_json()["error"], r.get_json())
call("post", f"/api/setup/payment_types/{lev['id']}/stop", 400, json={})
check("Stop using asks why", q("SELECT active FROM payment_types WHERE id = ?", (lev["id"],))[0]["active"] == 1)
call("post", f"/api/setup/payment_types/{lev['id']}/stop", json={"reason": "Not needed this year"})
check("...and with a reason stops it, the reason in the audit trail", q("SELECT active FROM payment_types WHERE id = ?", (lev["id"],))[0]["active"] == 0
      and last_tx()["reason"] == "Not needed this year")
rows = {r["key"]: r for r in call("get", "/api/setup/payment_types")["rows"]}
check("a stopped type stays in its list, as stopped", rows["tst_levy"]["status"] == "stopped")
call("post", f"/api/setup/payment_types/{lev['id']}/use", 400, json={})
call("post", f"/api/setup/payment_types/{lev['id']}/use", json={"reason": "Needed again"})
check("Use again asks why, and with a reason puts it back in use", q("SELECT active FROM payment_types WHERE id = ?", (lev["id"],))[0]["active"] == 1
      and last_tx()["reason"] == "Needed again")
call("delete", f"/api/setup/payment_types/{lev['id']}", 400, json={})
check("Delete asks why", q("SELECT id FROM payment_types WHERE id = ?", (lev["id"],)) != [])
call("delete", f"/api/setup/payment_types/{lev['id']}", json={"reason": "Opened by mistake"})
check("...and with a reason deletes it, the reason in the audit trail", not q("SELECT id FROM payment_types WHERE id = ?", (lev["id"],))
      and last_tx()["reason"] == "Opened by mistake")
check("a deleted record is gone from its list", "tst_levy" not in {r["key"] for r in call("get", "/api/setup/payment_types")["rows"]})

# a bank account of one company: Where used there, and the cash book can't be stopped
acct = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Spare", "bank": "Example Bank", "currency": "MYR"}})
ar = call("get", f"/api/setup/accounts/{acct['id']}")
check("Where used for a bank account: nowhere yet, can be deleted", ar["used_total"] == 0 and ar["can_delete"] is True)
main = [r for r in call("get", f"/api/setup/accounts?entity={EXA}")["rows"] if r["label"] == "Main"][0]
r = c.post(BASE + f"/api/setup/accounts/{main['id']}/stop", headers=H, json={"reason": "test"})
check("the company's cash book account can't be stopped, and says why", r.status_code == 400 and "cash book" in r.get_json()["error"], r.get_json())

# ---------- 3. Show deleted and Put it back ----------
call("delete", f"/api/setup/accounts/{acct['id']}", json={"reason": "Opened by mistake"})
gone = call("get", f"/api/setup/restore?kind=accounts&entity={EXA}")
row = next((x for x in gone["rows"] if x["name"] == "Spare"), None)
check("Show deleted lists the account with when, by whom and why, newest first", row is not None and row["reason"] == "Opened by mistake" and row["actor"]
      and row["at"] and row["entry"] and not row.get("problem"), gone)
check("...in the section's own list: another company lists none", all(x["name"] != "Spare" for x in call("get", f"/api/setup/restore?kind=accounts&entity={EXB}")["rows"]))
pv = call("post", f"/api/setup/restore/{row['row_id']}", json={"preview": True})
check("Put it back is previewed first: what was deleted, and that it comes back with the same number",
      pv["same_id"] is True and pv["deleted"]["reason"] == "Opened by mistake" and q("SELECT id FROM accounts WHERE label = 'Spare'") == [], pv)
call("post", f"/api/setup/restore/{row['row_id']}", 400, json={})
check("...and then asks why", q("SELECT id FROM accounts WHERE label = 'Spare'") == [])
back = call("post", f"/api/setup/restore/{row['row_id']}", json={"reason": "It is the new account after all"})
check("with a reason it is put back, as it was, and the reason is in the audit trail",
      back["same_id"] is True and q("SELECT label, currency FROM accounts WHERE id = ?", (acct["id"],)) == [{"label": "Spare", "currency": "MYR"}]
      and last_tx()["reason"] == "It is the new account after all")
check("a record put back is no longer listed as deleted", all(x["name"] != "Spare" for x in call("get", f"/api/setup/restore?kind=accounts&entity={EXA}")["rows"]))
r = c.post(BASE + f"/api/setup/restore/{row['row_id']}", headers=H, json={"reason": "again"})
check("one put back already is refused, with the reason", r.status_code in (400, 409) and "put back" in r.get_json()["error"].lower(), r.get_json())
# a key taken since
a1 = call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form"}})
call("delete", f"/api/setup/doc_types/{a1['id']}", json={"reason": "Wrong name"})
call("post", "/api/setup/doc_types", json={"fields": {"key": "tst_form", "label": "Test form again"}})
dl = call("get", "/api/setup/restore?kind=doc_types")
row2 = next(x for x in dl["rows"] if x["name"] == "Test form")
check("a deleted type whose key was taken since says why it can't be put back", row2.get("problem") and "tst_form" in row2["problem"], row2)
r = c.post(BASE + f"/api/setup/restore/{row2['row_id']}", headers=H, json={"preview": True})
check("...and its preview is refused with the same reason, nothing changed", r.status_code in (400, 409) and "tst_form" in r.get_json()["error"], r.get_json())

# ---------- 4. First run and Move setup count the same way ----------
cx = call("post", "/api/setup/entities", json={"fields": {"code": "EXC", "name": "Example Gamma Ltd", "uses_sql": False}})
call("post", f"/api/setup/entities/{cx['id']}/stop", json={"reason": "Not trading yet"})
cd = call("post", "/api/setup/entities", json={"fields": {"code": "EXD", "name": "Example Delta Ltd"}})
call("delete", f"/api/setup/entities/{cd['id']}", json={"reason": "Added by mistake"})
for code, name in (("420-1001", "EPF payable"), ("900-E001", "EPF employer expense"), ("310-000", "Maybank current")):
    call("post", "/api/setup/gl_accounts", json={"entity_id": EXA, "fields": {"code": code, "name": name}})
call("post", "/api/setup/statutory_accounts", json={"entity_id": EXA, "fields": {"kind": "epf", "label": "EPF (KWSP)", "payable_code": "420-1001", "employer_code": "900-E001"}})
call("post", "/api/setup/parties", json={"entity_id": EXA, "fields": {"name": "Test Supplier", "kind": "supplier", "sql_code": "400-T001"}})
# the page posts every field of the dialog, a words box left empty as an empty list: that is no words, not a refusal
r = c.post(BASE + "/api/setup/parties", headers=H, json={"entity_id": EXA, "fields": {"name": "Test Customer", "kind": "customer", "sql_code": "300-T001", "match_words": []}})
check("Add customer or supplier with the words box left empty (as the page posts it) is not refused", r.status_code == 200, r.get_json())
if r.status_code != 200:  # (to see what else a change fixes, with HRP_KEEP_GOING: the customer is added without the box)
    call("post", "/api/setup/parties", json={"entity_id": EXA, "fields": {"name": "Test Customer", "kind": "customer", "sql_code": "300-T001"}})
# bank accounts that hold a GL code as an older version let it be typed: any text (here 17 and 30 characters, not in SQL's code format)
OLD_A, OLD_B = "Example Bank CA 1", "Example Bank Current Acct 0001"
assert len(OLD_B) == 30
write("old free-text GL codes", ("UPDATE accounts SET gl_code = ? WHERE id = ?", (OLD_A, main["id"])),
      ("UPDATE accounts SET gl_code = ? WHERE entity_id = ? AND label = 'Current'", (OLD_B, EXB)))
# 100 letters that grow in capitals (the German sharp s) are 200 capitals: the longest a GL code can be
call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Sharp", "bank": "Example Bank", "currency": "SGD", "gl_code": "\u00df" * 100}})
# a code an older version kept as typed (150 letters that grow in capitals: 300 capitals, over the 200 a new one may be)
call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Legacy", "bank": "Example Bank", "currency": "SGD"}})
write("a GL code kept as typed by an older version", ("UPDATE accounts SET gl_code = ? WHERE label = 'Legacy'", ("\u00df" * 150,)))
full = call("get", "/api/setup/export?what=full&payees=1")
check("the file holds the stopped company and not the deleted one", [e["code"] for e in full["entities"]] == ["EXA", "EXB", "EXC"]
      and [e["active"] for e in full["entities"]] == [1, 1, 0], [(e["code"], e["active"]) for e in full["entities"]])
mine = held(call("get", "/api/setup/import")["holding"])
check("what this install holds (Move setup's sentence) counts the stopped company and not the deleted one",
      mine["companies"] == 3 and mine["bank accounts"] == 5 and mine["statutory accounts"] == 1 and mine["customers and suppliers"] == 2
      and mine["GL accounts"] == 3 and mine["recurring payments"] == 1, mine)
fileholds = {w: len(full[k]) for k, w in (("entities", "companies"), ("accounts", "bank accounts"), ("gl_accounts", "GL accounts"),
                                                              ("statutory_accounts", "statutory accounts"), ("parties", "customers and suppliers"),
                                                              ("checklist", "checklist items"), ("payees", "recurring payments"))}
check("the file's own rows are the figures the install holds", all(mine[w] == n for w, n in fileholds.items()), (mine, fileholds))
src_file, out_file = tmp / "setup full.json", tmp / "child out.json"
filed = json.loads(json.dumps(full))
next(a for a in filed["accounts"] if a["label"] == "Spare")["gl_code"] = " bk-310 "   # a file made by hand, or by an older version
src_file.write_text(json.dumps(filed), encoding="utf-8")
run = subprocess.run([sys.executable, "-m", "synthetic_tests.setup_records_test", "--import", str(src_file), str(out_file)],
                     cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=600)
print("\n".join("  " + line for line in run.stdout.splitlines()))
check("the new install's checks pass", run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:])


class Missing(dict):
    """What the new install didn't say, when it stopped (listing every failure with HRP_KEEP_GOING): any key is nothing, so each check that needed it fails."""
    def __missing__(self, k):
        return Missing()


got = Missing(json.loads(out_file.read_text(encoding="utf-8"))) if out_file.exists() else Missing()
check("First run's preview of the file counts the stopped company, not the deleted one", got["preview"]["companies"] == 3, got["preview"])
check("First run's counts are Move setup's: the preview of the file equals what the install holds once it is imported, figure by figure",
      all(got["holding"][w] == got["preview"][w] for w in got["holding"]) and set(got["holding"]) >= {"companies", "bank accounts", "GL accounts", "statutory accounts",
                                                                                                      "customers and suppliers", "checklist items", "recurring payments"},
      (got["preview"], got["holding"]))
# A company with no checklist of its own in the file starts with the starter checklist, so the new install holds those rows too (and the
# preview counts them, above): the first install keeps none of its own for the two companies it never opened a checklist for.
check("...and, but for the starter checklists the import gives, both are what the first install holds",
      all(got["holding"][w] == mine[w] for w in mine if w != "checklist items") and got["holding"]["checklist items"] > mine["checklist items"], (got["holding"], mine))
check("the export of an install holding free-text GL codes holds them as they are", {a["label"]: a["gl_code"] for a in full["accounts"]}.get("Main") == OLD_A
      and {a["label"]: a["gl_code"] for a in full["accounts"]}.get("Current") == OLD_B, [(a["label"], a["gl_code"]) for a in full["accounts"]])
check("...and imports into a fresh install, which is not refused for their shape: they come in tidied (capitals, no spaces round them), the 30-character one whole, and a hand-made ' bk-310 ' as BK-310",
      got["gl_codes"] == {"Main": OLD_A.upper(), "Current": OLD_B.upper(), "Spare": "BK-310", "Sharp": "SS" * 100, "Legacy": "SS" * 150}, got.get("gl_codes"))
check("...a code an older version kept as typed, 150 letters that are 300 capitals (over the 200 a new one may be), goes out in the export as it is kept and comes back in whole into a fresh install",
      {a["label"]: a["gl_code"] for a in full["accounts"]}.get("Legacy") == "\u00df" * 150 and got["gl_codes"]["Legacy"] == "SS" * 150, (len({a["label"]: a["gl_code"] for a in full["accounts"]}.get("Legacy") or ""), got["gl_codes"]["Legacy"]))
check("...and a code of 700 characters in a file is refused naming the bank account and the field (600 characters is the most a file may hold, tried in the new install)",
      "Legacy" in got["refused"] and "GL account code" in got["refused"] and "too long" in got["refused"], got["refused"])
check("...and a GL code of 200 capitals made of 100 letters that grow in capitals goes out in the export and comes back in whole: what is kept is accepted again",
      {a["label"]: a["gl_code"] for a in full["accounts"]}.get("Sharp") == "SS" * 100 and got["gl_codes"]["Sharp"] == "SS" * 100)
check("the stopped company comes across as stopped, and nothing is left of the deleted one",
      got["codes"] == ["EXA", "EXB", "EXC"] and got["active"] == {"EXA": 1, "EXB": 1, "EXC": 0} and got["empty"] is False, got)


# ---------- 5. review fixes ----------


class section:
    """A part of the review fixes. With HRP_KEEP_GOING one that fails (or stops) is listed and the next still runs."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et and KEEP_GOING and et is not SystemExit:
            print(f"FAIL part: {self.name} -> {et.__name__}: {str(ev)[:300]}")
            failed.append(self.name)
            return True
        return False


# 1. Words in SQL descriptions is optional: left empty it is no words, on add and on edit; a matching-word rule still needs its words
with section('1. Words in SQL descriptions is optional: left empty it is no words, o'):
    for empty in ([], [" ", ""], ""):
        tp = call("post", "/api/setup/parties", json={"entity_id": EXA, "fields": {"name": f"Words {len(passed)}", "kind": "supplier", "match_words": empty}})
        check(f"a supplier added with its words box empty ({empty!r}) is added, with no words", q("SELECT match_words FROM parties WHERE id = ?", (tp["id"],))[0]["match_words"] is None
              and call("get", f"/api/setup/parties/{tp['id']}")["record"]["match_words"] is None)
    tw = call("post", "/api/setup/parties", json={"entity_id": EXA, "fields": {"name": "Words Test", "kind": "supplier", "match_words": ["tnb", "electric"]}})
    check("words are kept as capitals", call("get", f"/api/setup/parties/{tw['id']}")["record"]["match_words"] == ["TNB", "ELECTRIC"])
    call("patch", f"/api/setup/parties/{tw['id']}", json={"fields": {"match_words": []}})
    check("clearing the box of a party that has words stores no words", q("SELECT match_words FROM parties WHERE id = ?", (tw["id"],))[0]["match_words"] is None
          and call("get", f"/api/setup/parties/{tw['id']}")["record"]["match_words"] is None)
    check("...and the list, the export and a record with no words all read as none",
          all(r["match_words"] is None for r in call("get", f"/api/setup/parties?entity={EXA}")["rows"] if r["name"] in ("Words Test", "Test Customer"))
          and all(p["match_words"] is None for p in call("get", "/api/setup/export?what=full")["parties"] if p["name"] in ("Words Test", "Test Customer")))
    r = c.post(BASE + "/api/setup/guess_words", headers=H, json={"fields": {"label": "Empty", "words": [], "payment_type": "other"}})
    check("a matching-word rule still needs words: an empty list is refused", r.status_code == 400 and "at least one word" in r.get_json()["error"], r.get_json())
    rule = call("post", "/api/setup/guess_words", json={"fields": {"label": "Test rule", "words": ["levy"], "payment_type": "other"}})
    r = c.patch(BASE + f"/api/setup/guess_words/{rule['id']}", headers=H, json={"fields": {"words": []}})
    check("...and so is clearing the words of one", r.status_code == 400 and "at least one word" in r.get_json()["error"]
          and call("get", f"/api/setup/guess_words/{rule['id']}")["record"]["words"] == ["LEVY"], r.get_json())
    item = q("SELECT code FROM checklist_items ORDER BY id LIMIT 1")[0]["code"]
    for kind, fields in (("hint_words", {"label": "Test hint", "payment_type": "salary"}),
                         ("filing_words", {"label": "Test filing", "doc_kind": "invoice", "checklist_code": item})):
        r = c.post(BASE + f"/api/setup/{kind}", headers=H, json={"fields": {**fields, "words": []}})
        check(f"{kind}: an empty list of words is refused on add, as for payment type guesses", r.status_code == 400 and "at least one word" in r.get_json()["error"], r.get_json())
        r = c.post(BASE + f"/api/setup/{kind}", headers=H, json={"fields": {**fields, "words": [" ", ""]}})
        check(f"{kind}: ...and a list of blanks", r.status_code == 400 and "at least one word" in r.get_json()["error"], r.get_json())
        made = call("post", f"/api/setup/{kind}", json={"fields": {**fields, "words": ["levy"]}})
        r = c.patch(BASE + f"/api/setup/{kind}/{made['id']}", headers=H, json={"fields": {"words": []}})
        check(f"{kind}: ...and clearing the words of one, which keeps its words", r.status_code == 400 and "at least one word" in r.get_json()["error"]
              and call("get", f"/api/setup/{kind}/{made['id']}")["record"]["words"] == ["LEVY"], r.get_json())

# 2. Where used lists every record that refers to a company or a GL account, so Delete is not offered and then refused by the records
with section('2. Where used lists every record that refers to a company or a GL acco'):
    fk = {}
    with sqlite3.connect(config.DB_PATH) as r:
        for (t,) in r.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for row in r.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
                if row[2] == "entities":
                    fk.setdefault(t, row[3])
    listed = " ".join(u[2] for u in masters.USES["entities"])
    GONE_WITH_IT = {"checklist_items", "required_sets"}  # deleted with the company, as no month was set up with them
    check("every table with a foreign key to companies is in Where used for a company (or goes with it)", all(t in listed or t in GONE_WITH_IT for t in fk),
          [t for t in fk if t not in listed and t not in GONE_WITH_IT])
    NOW = "2026-11-21T10:00:00"
    ROWS = {
        "printed company name": ("sql_company_names", "(entity_id, name_key, name, confirmed_at) VALUES (?, 'k', 'EXAMPLE NAME (1)', ?)", (NOW,)),
        "opening balance": ("ledger_openings", "(entity_id, account_code, as_of, source, set_at) VALUES (?, '100-000', '2026-01-01', 'here', ?)", (NOW,)),
        "payroll workbook check": ("payroll_checks", "(entity_id, month, filename, checked_at, to_fix, to_check, notes, report) VALUES (?, '2026-10', 'x.xlsx', ?, 0, 0, 0, '{}')", (NOW,)),
        "MyInvois document": ("myinvois_docs", "(entity_id, uuid, doc_no, status, total_sen, direction, as_at) VALUES (?, 'u1', 'D1', 'valid', 0, 'issued', ?)", (NOW,)),
        "SQL account fetch": ("ledger_batches", "(entity_id, origin, report, read_at) VALUES (?, 'here', 'entered', ?)", (NOW,)),
    }
    for i, (what, (table, cols, extra)) in enumerate(ROWS.items()):
        co = call("post", "/api/setup/entities", json={"fields": {"code": f"FK{i}", "name": f"Example Referenced {i} Ltd", "uses_sql": False}})
        write(f"a {what} of FK{i}", (f"INSERT INTO {table} {cols}", (co["id"], *extra)))
        rec = call("get", f"/api/setup/entities/{co['id']}")
        check(f"Where used says a company has a {what}, and Delete is not offered", any(w == what for w, n in rec["used_by"]) and rec["can_delete"] is False, rec["used_by"])
        r = c.delete(BASE + f"/api/setup/entities/{co['id']}", headers=H, json={"reason": "test"})
        err = r.get_json()["error"]
        check(f"...deleting it says what uses it, in the records' words, and deletes nothing", r.status_code == 409 and f"1 {what}" in err and "FOREIGN KEY" not in err.upper()
              and q("SELECT id FROM entities WHERE id = ?", (co["id"],)) != [], err)
    # a reference the list does not know of: the refusal is plain, and the delete leaves everything as it was
    co = call("post", "/api/setup/entities", json={"fields": {"code": "FKX", "name": "Example Unlisted Ltd", "uses_sql": False}})
    items = q("SELECT COUNT(*) AS n FROM checklist_items WHERE entity_id = ?", (co["id"],))[0]["n"]
    with sqlite3.connect(config.DB_PATH) as raw:
        raw.execute("CREATE TABLE tst_unlisted (entity_id INTEGER REFERENCES entities(id))")
        raw.execute("INSERT INTO tst_unlisted VALUES (?)", (co["id"],))
    r = c.delete(BASE + f"/api/setup/entities/{co['id']}", headers=H, json={"reason": "test"})
    check("a delete that still meets a reference Where used lacks is refused in plain words, never as the records' own text",
          r.status_code == 409 and r.get_json()["error"] == "It is still used by other records, so nothing was deleted. Stop using it instead.", r.get_json())
    check("...and nothing was deleted: the company and its checklist are as they were",
          q("SELECT id FROM entities WHERE id = ?", (co["id"],)) != [] and q("SELECT COUNT(*) AS n FROM checklist_items WHERE entity_id = ?", (co["id"],))[0]["n"] == items and items > 0)
    with sqlite3.connect(config.DB_PATH) as raw:
        raw.execute("DROP TABLE tst_unlisted")
    # a bank account's confirmed pair of bank lines, and a GL account a statutory account names
    ac = call("post", "/api/setup/accounts", json={"entity_id": EXB, "fields": {"label": "Paired", "bank": "Example Bank", "currency": "MYR"}})
    write("a confirmed pair", ("INSERT INTO recon_pairs (account_id, month, pair_key) VALUES (?, '2026-10', 'k1')", (ac["id"],)))
    ar = call("get", f"/api/setup/accounts/{ac['id']}")
    check("Where used says a bank account has a confirmed pair of bank lines, and Delete is not offered",
          any(w == "confirmed pair of bank lines" for w, n in ar["used_by"]) and ar["can_delete"] is False, ar["used_by"])
    gl = {r["code"]: r for r in call("get", f"/api/setup/gl_accounts?entity={EXA}")["rows"]}
    for code in ("420-1001", "900-E001"):
        g = call("get", f"/api/setup/gl_accounts/{gl[code]['id']}")
        check(f"Where used says a GL account a statutory account names ({code}) is used by it, and Delete is not offered",
              any(w == "statutory account" for w, n in g["used_by"]) and g["can_delete"] is False and "code" in g["locked"], g["used_by"])
        r = c.delete(BASE + f"/api/setup/gl_accounts/{gl[code]['id']}", headers=H, json={"reason": "test"})
        check(f"...and deleting {code} is refused, naming it, so no statutory account is left pointing at nothing",
              r.status_code == 409 and "1 statutory account" in r.get_json()["error"] and q("SELECT id FROM gl_accounts WHERE code = ?", (code,)) != []
              and q("SELECT payable_code FROM statutory_accounts")[0]["payable_code"] == "420-1001", r.get_json())
    check("a GL account no statutory account names can still be deleted", call("get", f"/api/setup/gl_accounts/{gl['310-000']['id']}")["can_delete"] is True)
    # a chart account named only by an opening balance, or by a line of a journal read from SQL
    for what, code in (("opening balance", "770-0001"), ("SQL journal line", "770-0002")):
        ga = call("post", "/api/setup/gl_accounts", json={"entity_id": EXB, "fields": {"code": code, "name": f"Named only by a {what}"}})
        if what == "opening balance":
            write(f"a {what} of {code}", ("INSERT INTO ledger_openings (entity_id, account_code, as_of, source, set_at) VALUES (?, ?, '2026-01-01', 'here', ?)", (EXB, code, NOW)))
        else:
            write(f"a {what} of {code}", ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'journal.xlsx', ?, 0, 0)", (EXB, NOW)),
                  ("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, 'J1', (SELECT MAX(id) FROM sql_imports), ?, 10, 0)", (EXB, code)))
        rec = call("get", f"/api/setup/gl_accounts/{ga['id']}")
        check(f"Where used says a chart account named only by a {what} is used by it, its code can't change, and Delete is not offered",
              any(w == what for w, n in rec["used_by"]) and rec["can_delete"] is False and "code" in rec["locked"], rec["used_by"])
        r = c.delete(BASE + f"/api/setup/gl_accounts/{ga['id']}", headers=H, json={"reason": "test"})
        check(f"...and deleting it is refused, naming it, and deletes nothing", r.status_code == 409 and f"1 {what}" in r.get_json()["error"]
              and q("SELECT id FROM gl_accounts WHERE id = ?", (ga["id"],)) != [], r.get_json())

# 3. a company switched to Kept here keeps the printed company names confirmed while it was Kept in SQL Account: they can be removed
with section('3. a company switched to Kept here keeps the printed company names con'):
    ko = call("post", "/api/setup/entities", json={"fields": {"code": "KEPT", "name": "Example Switched Ltd", "uses_sql": True}})
    write("a confirmed printed company name", ("INSERT INTO sql_company_names (entity_id, name_key, name, confirmed_at) VALUES (?, ?, 'EXAMPLE PRINTED NAME BHD (2026)', ?)",
                                                (ko["id"], sqlfetch._key("EXAMPLE PRINTED NAME BHD (2026)"), NOW)))
    call("patch", f"/api/setup/entities/{ko['id']}", json={"fields": {"uses_sql": False}})
    left = call("get", "/api/setup/export?what=full").get("left_out", [])
    check("the export says a name of a company now Kept here stays out, and where to remove it",
          any("EXAMPLE PRINTED NAME BHD" in x and "no longer kept in SQL Account" in x and "Remove the name in Setup › Companies" in x for x in left), left)
    nm = call("get", f"/api/setup/entities/{ko['id']}/sql-names")
    check("the company's names are still listed for a company Kept here, and can be removed there", nm["ready"] and [n["name"] for n in nm["names"]] == ["EXAMPLE PRINTED NAME BHD (2026)"])
    r = c.post(BASE + "/api/sql/take-company", headers=H, json={"entity_id": EXA, "company": "Example Printed Name Bhd (2026)"})
    check("while a company Kept here still holds a confirmed name no other company can take it (what the dialog's sentence says)",
          r.status_code == 400 and "was taken for KEPT before" in r.get_json()["error"] and sqlfetch.confirmed_names(db.connect()).get(sqlfetch._key("EXAMPLE PRINTED NAME BHD (2026)")) == ko["id"], r.get_json())
    call("delete", f"/api/setup/entities/{ko['id']}/sql-names/{nm['names'][0]['id']}", json={})
    got_it = call("post", "/api/sql/take-company", json={"entity_id": EXA, "company": "Example Printed Name Bhd (2026)"})
    check("...and once it is removed another company can", got_it["added"] is True)
    call("delete", f"/api/setup/entities/{EXA}/sql-names/{call('get', f'/api/setup/entities/{EXA}/sql-names')['names'][0]['id']}", json={})
    check("...removing it leaves none, and the export no longer says it is left out",
          call("get", f"/api/setup/entities/{ko['id']}/sql-names")["names"] == [] and not any("EXAMPLE PRINTED NAME BHD" in x for x in call("get", "/api/setup/export?what=full").get("left_out", [])))

# 4. the stopped note is said once in a record's own answer (the page adds the section's note only when the server has not)
with section("4. the stopped note is said once in a record's own answer (the page ad"):
    ss = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Stop me", "bank": "Example Bank", "currency": "USD"}})
    call("post", f"/api/setup/accounts/{ss['id']}/stop", json={"reason": "Not needed"})
    sn = call("get", f"/api/setup/accounts/{ss['id']}")["notes"]
    check("a stopped record's notes hold the section's stopped note once, and it is the same words the section carries",
          sn.count(masters.STOPPED_NOTE["accounts"]) == 1 and call("get", "/api/setup/types")["kinds"]["accounts"]["stop_note"] == masters.STOPPED_NOTE["accounts"], sn)

# 13. what a company Kept here is not asked for is what the server leaves out of its payments' documents
with section('13. what a company Kept here is not asked for is what the server leave'):
    R = rulebook.get(db.connect())
    sqlish = sorted(d["key"] for d in call("get", "/api/setup/required?entity=")["doc_types"] if d["from_sql"])
    check("the documents Setup says SQL Account issues are the ones the server does not ask a company Kept here for",
          sqlish == sorted(rules.SQL_ONLY) and "pv" not in R.required_docs("salary", False) and "pv" in R.required_docs("salary", True)
          and all(d in R.required_docs("salary", False) for d in R.required_docs("salary", True) if d not in sqlish), (sqlish, R.required_docs("salary", False), R.required_docs("salary", True)))

# 14. wording that had gone stale
with section('14. wording that had gone stale'):
    check("a stopped company is hidden from the company switcher, not the sidebar", "company switcher" in masters.STOPPED_NOTE["entities"] and "sidebar" not in masters.STOPPED_NOTE["entities"])
    check("a stopped bank account says everything recorded stays, as the board does", masters.STOPPED_NOTE["accounts"].endswith("Everything recorded stays."))
    check("Statutory accounts says where it is checked by the menu's own name", "Accounting › Statutory payables" in masters.KINDS["statutory_accounts"]["help"]
          and "Books › Statutory" not in masters.KINDS["statutory_accounts"]["help"])

# 16. Show deleted names a company by its code and name, a chart account with its code beside it, and each section by its own words
with section('16. Show deleted names a company by its code and name, a chart account'):
    dc = call("get", "/api/setup/restore?kind=entities")["rows"]
    check("a deleted company is listed as CODE · Name, as its list shows it", [x["name"] for x in dc if x["name"].startswith("EXD")] == ["EXD · Example Delta Ltd"], [x["name"] for x in dc])
    pvw = call("post", f"/api/setup/restore/{next(x['row_id'] for x in dc if x['name'].startswith('EXD'))}", json={"preview": True})
    check("...and the Put it back preview names it so too", pvw["name"] == "EXD · Example Delta Ltd", pvw.get("name"))
    spare = call("post", "/api/setup/gl_accounts", json={"entity_id": EXA, "fields": {"code": "999-001", "name": "Spare account"}})["id"]
    call("delete", f"/api/setup/gl_accounts/{spare}", json={"reason": "Not needed"})
    gd = call("get", f"/api/setup/restore?kind=gl_accounts&entity={EXA}")["rows"]
    check("a deleted chart account is listed by its name, with its code", [(x["name"], x["code"]) for x in gd] == [("Spare account", "999-001")], gd)
    kk = call("get", "/api/setup/types")["kinds"]
    check("each section says its own words for what was deleted: Filing words, bank accounts, accounts for the chart",
          kk["filing_words"]["deleted_plural"] == "filing words" and kk["accounts"]["deleted_plural"] == "bank accounts" and kk["gl_accounts"]["deleted_plural"] == "accounts"
    )

# 17. a chart account's uses are read in one pass for the whole chart: per company, whatever case or padding a stored code has
with section("17. a chart account's uses are counted per company, as capitals without padding"):
    def chart(eid, code, name="Chart test"):
        return call("post", "/api/setup/gl_accounts", json={"entity_id": eid, "fields": {"code": code, "name": f"{name} {code}"}})["id"]
    SAME_A, SAME_B = chart(EXA, "880-0001"), chart(EXB, "880-0001")      # the same code in two companies
    PAD_OPEN, LOW_JNL, PAD_BANK, API_BANK = chart(EXB, "880-0002"), chart(EXB, "880-A003"), chart(EXA, "880-A004"), chart(EXA, "880-A006")
    write("rows naming chart codes",
          ("INSERT INTO ledger_openings (entity_id, account_code, as_of, source, set_at) VALUES (?, '880-0001', '2026-01-01', 'here', ?)", (EXB, NOW)),
          ("INSERT INTO ledger_openings (entity_id, account_code, as_of, source, set_at) VALUES (?, '  880-0002 ', '2026-01-01', 'here', ?)", (EXB, NOW)),
          ("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'journal.xlsx', ?, 0, 0)", (EXB, NOW)),
          ("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, 'J1', (SELECT MAX(id) FROM sql_imports), '880-0001', 5, 0)", (EXB,)),
          ("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, 'J1', (SELECT MAX(id) FROM sql_imports), '880-0001', 0, 5)", (EXB,)),
          ("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, 'J2', (SELECT MAX(id) FROM sql_imports), '880-a003', 7, 0)", (EXB,)),
          ("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, 'J2', (SELECT MAX(id) FROM sql_imports), ' 880-A003 ', 0, 7)", (EXB,)))
    pa = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Padded GL", "bank": "Example Bank", "currency": "USD"}})
    write("a bank account naming a chart code padded and in lower case, as an older record may hold it", ("UPDATE accounts SET gl_code = ' 880-a004 ' WHERE id = ?", (pa["id"],)))
    uses = lambda kind_eid, gid: next(x for x in call("get", f"/api/setup/gl_accounts?entity={kind_eid}")["rows"] if x["id"] == gid)
    check("a second company's rows with the same code are not this company's: its account of that code is used by nothing, the other's by its opening and its journal lines",
          uses(EXA, SAME_A)["used_by"] == [] and call("get", f"/api/setup/gl_accounts/{SAME_A}")["can_delete"] is True
          and uses(EXB, SAME_B)["used_by"] == [["opening balance", 1], ["SQL journal lines", 2]] and call("get", f"/api/setup/gl_accounts/{SAME_B}")["used_by"] == [["opening balance", 1], ["SQL journal lines", 2]],
          (uses(EXA, SAME_A)["used_by"], uses(EXB, SAME_B)["used_by"]))
    check("a stored code padded or in lower case still names its account: an opening balance, journal lines of both kinds, a bank account, in the list and in the record",
          uses(EXB, PAD_OPEN)["used_by"] == [["opening balance", 1]] and uses(EXB, LOW_JNL)["used_by"] == [["SQL journal lines", 2]] and uses(EXA, PAD_BANK)["used_by"] == [["bank account", 1]]
          and call("get", f"/api/setup/gl_accounts/{PAD_OPEN}")["used_by"] == [["opening balance", 1]] and call("get", f"/api/setup/gl_accounts/{PAD_BANK}")["used_by"] == [["bank account", 1]],
          [uses(EXB, PAD_OPEN)["used_by"], uses(EXB, LOW_JNL)["used_by"], uses(EXA, PAD_BANK)["used_by"]])
    for gid, why in ((PAD_OPEN, "a padded opening balance"), (LOW_JNL, "lower-case journal lines"), (PAD_BANK, "a bank account's padded lower-case code")):
        rc = call("get", f"/api/setup/gl_accounts/{gid}")
        r = c.delete(BASE + f"/api/setup/gl_accounts/{gid}", headers=H, json={"reason": "test"})
        r2 = c.patch(BASE + f"/api/setup/gl_accounts/{gid}", headers=H, json={"fields": {"code": "880-9999"}})
        check(f"{why} locks the chart account's code and Delete is not offered or allowed", rc["can_delete"] is False and "code" in rc["locked"] and r.status_code == 409
              and r2.status_code == 400 and "can't change once used" in r2.get_json()["error"], (rc["used_by"], r.get_json(), r2.get_json()))
    # a bank account's GL code is kept as the chart keeps its codes
    call("patch", f"/api/setup/accounts/{pa['id']}", json={"fields": {"label": "Padded GL two", "gl_code": "  880-a006 "}})
    check("a bank account's GL code is stored in capitals without the spaces round it, so it names its chart account as typed",
          q("SELECT gl_code FROM accounts WHERE id = ?", (pa["id"],))[0]["gl_code"] == "880-A006" and uses(EXA, API_BANK)["used_by"] == [["bank account", 1]]
          and call("get", f"/api/setup/accounts/{pa['id']}")["record"]["gl_code"] == "880-A006")
    mk = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "New with a code", "bank": "Example Bank", "currency": "SGD", "gl_code": "bk-7 "}})
    check("...also when the account is added", q("SELECT gl_code FROM accounts WHERE id = ?", (mk["id"],))[0]["gl_code"] == "BK-7")
    # ...but never refused for its shape: an older install holds any text there, and must keep saving it
    mo = call("post", "/api/setup/accounts", json={"entity_id": EXA, "fields": {"label": "Old text", "bank": "Example Bank", "currency": "SGD"}})
    write("an old free-text GL code", ("UPDATE accounts SET gl_code = ? WHERE id = ?", (OLD_A, mo["id"])))
    r = c.patch(BASE + f"/api/setup/accounts/{mo['id']}", headers=H, json={"fields": {"gl_code": OLD_A, "bank": "Example Bank Two"}})
    check("a PATCH that posts the old value unchanged with another field is not refused, and tidies it", r.status_code == 200
          and q("SELECT gl_code, bank FROM accounts WHERE id = ?", (mo["id"],)) == [{"gl_code": OLD_A.upper(), "bank": "Example Bank Two"}], r.get_json())
    r = c.patch(BASE + f"/api/setup/accounts/{mo['id']}", headers=H, json={"fields": {"gl_code": OLD_B}})
    check("...a 30-character value (over a chart code's 20) is kept whole", r.status_code == 200 and q("SELECT gl_code FROM accounts WHERE id = ?", (mo["id"],))[0]["gl_code"] == OLD_B.upper(), r.get_json())
    sharp = q("SELECT id, gl_code FROM accounts WHERE label = 'Sharp'")[0]
    r = c.patch(BASE + f"/api/setup/accounts/{sharp['id']}", headers=H, json={"fields": {"gl_code": sharp["gl_code"], "bank": "Example Bank Three"}})
    check("...the rule is one for every caller, capitals first and then the length of what is kept: the stored 200 capitals are accepted again by a PATCH (with another field), as an import accepts them",
          sharp["gl_code"] == "SS" * 100 and r.status_code == 200 and q("SELECT bank FROM accounts WHERE id = ?", (sharp["id"],))[0]["bank"] == "Example Bank Three", r.get_json())
    long = "\u00df" * 101   # 202 capitals
    r1 = c.patch(BASE + f"/api/setup/accounts/{sharp['id']}", headers=H, json={"fields": {"gl_code": long}})
    r2 = c.post(BASE + "/api/setup/accounts", headers=H, json={"entity_id": EXA, "fields": {"label": "Too long", "bank": "Example Bank", "currency": "SGD", "gl_code": long}})
    r3 = c.patch(BASE + f"/api/setup/accounts/{sharp['id']}", headers=H, json={"fields": {"gl_code": "x" * 201}})
    try:
        masters._checked("accounts", {"gl_code": long})   # what an import and a paste check a row with
        refused = None
    except masters.Refused as x:
        refused = str(x)
    check("...and 101 of them (202 capitals), or 201 characters, are refused as too long when typed as a new value: by the page's path, the API (added or changed) and the strict check a paste uses (a setup file's own check takes up to 600, below)",
          r1.status_code == 400 and r2.status_code == 400 and r3.status_code == 400 and all("too long" in r.get_json()["error"] for r in (r1, r2, r3))
          and refused is not None and "too long" in refused and masters._checked("accounts", {"gl_code": "\u00df" * 100})["gl_code"] == "SS" * 100
          and q("SELECT gl_code FROM accounts WHERE id = ?", (sharp["id"],))[0]["gl_code"] == "SS" * 100, (r1.get_json(), r2.get_json(), r3.get_json(), refused))
    # a code an older version kept as typed (300 capitals): the same value posted again with another field is the record's own, and is accepted; a new or changed one is not
    leg = q("SELECT id, gl_code FROM accounts WHERE label = 'Legacy'")[0]
    ra = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": leg["gl_code"], "bank": "Example Bank Legacy"}})
    now = q("SELECT gl_code, bank FROM accounts WHERE id = ?", (leg["id"],))[0]
    check("a PATCH that posts a stored code of 300 capitals again unchanged (as the page does) with another field is accepted, and the code is kept as capitals",
          leg["gl_code"] == "\u00df" * 150 and ra.status_code == 200 and now == {"gl_code": "SS" * 150, "bank": "Example Bank Legacy"}, (ra.get_json(), now))
    rb = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": "  " + "ss" * 150 + " ", "bank": "Example Bank Legacy Two"}})
    check("...also written in lower case with spaces round it (the same code), and it is still the record's own",
          rb.status_code == 200 and q("SELECT gl_code, bank FROM accounts WHERE id = ?", (leg["id"],)) == [{"gl_code": "SS" * 150, "bank": "Example Bank Legacy Two"}], rb.get_json())
    rc_ = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": "BK-1"}})
    rd = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": "\u00df" * 150}})
    check("...but once another code has been stored, the same long value is a new one: refused as too long, as it is when added",
          rc_.status_code == 200 and rd.status_code == 400 and "too long" in rd.get_json()["error"] and q("SELECT gl_code FROM accounts WHERE id = ?", (leg["id"],))[0]["gl_code"] == "BK-1", (rc_.get_json(), rd.get_json()))
    re_ = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": "\u00df" * 100}})
    rf = c.patch(BASE + f"/api/setup/accounts/{leg['id']}", headers=H, json={"fields": {"gl_code": "\u00df" * 101}})
    check("...100 letters (200 capitals) are accepted as a new value and 101 refused; and nothing is taken at three times the length by a PATCH unless it is the record's own",
          re_.status_code == 200 and q("SELECT gl_code FROM accounts WHERE id = ?", (leg["id"],))[0]["gl_code"] == "SS" * 100 and rf.status_code == 400 and "too long" in rf.get_json()["error"], (re_.get_json(), rf.get_json()))
    check("a file's own check takes three times the length (600 capitals) and no more, as a hard cap; Setup's own check of a typed value is unchanged (200)",
          masters._checked("accounts", {"gl_code": "x" * 600}, lenient=True)["gl_code"] == "X" * 600 and masters._checked("accounts", {"gl_code": "x" * 200})["gl_code"] == "X" * 200
          and all(_refused(lambda n=n, k=k: masters._checked("accounts", {"gl_code": "x" * n}, lenient=k)) for n, k in ((601, True), (201, False))), None)
    r = c.post(BASE + "/api/setup/accounts", headers=H, json={"entity_id": EXA, "fields": {"label": "Odd code", "bank": "Example Bank", "currency": "SGD", "gl_code": " no good! "}})
    check("...and so is one SQL Account would not write: kept as typed apart from the capitals and the spaces round it", r.status_code == 200
          and q("SELECT gl_code FROM accounts WHERE id = ?", (r.get_json()["id"],))[0]["gl_code"] == "NO GOOD!", r.get_json())

# 18. a big company's chart: 500 accounts, 3 openings each and 50,000 journal lines read from SQL. Counting each account's uses by a scan of the
# journal lines for each took 9 to 16 seconds for the list and the same for pasting the chart; it is one pass over each table, whatever the chart.
with section("18. a big chart of accounts is listed, pasted and edited in a moment"):
    big = call("post", "/api/setup/entities", json={"fields": {"code": "BIG", "name": "Example Big Sdn Bhd", "uses_sql": True}})["id"]
    codes = [f"{300 + i // 100}-{i % 100:04d}" for i in range(500)]
    bc = db.connect()
    bc.arm("user", "test: a big chart")
    bc.executemany("INSERT INTO gl_accounts (entity_id, code, name) VALUES (?, ?, ?)", [(big, k, f"Account {k}") for k in codes])
    bc.execute("INSERT INTO sql_imports (entity_id, filename, imported_at, entries, linked) VALUES (?, 'big.xlsx', ?, 0, 0)", (big, NOW))
    imp = bc.execute("SELECT MAX(id) FROM sql_imports").fetchone()[0]
    bc.execute("INSERT INTO ledger_batches (entity_id, origin, report, read_at, sql_import_id) VALUES (?, 'sql', 'trial_balance', ?, ?)", (big, NOW, imp))
    batch = bc.execute("SELECT MAX(id) FROM ledger_batches").fetchone()[0]
    bc.executemany("INSERT INTO ledger_openings (entity_id, account_code, as_of, source, batch_id, set_at) VALUES (?, ?, ?, 'sql_tb', ?, ?)",
                   [(big, k, d, batch, NOW) for k in codes for d in ("2024-01-01", "2025-01-01", "2026-01-01")])
    bc.executemany("INSERT INTO sql_journal_lines (entity_id, dockey, import_id, code, dr, cr) VALUES (?, ?, ?, ?, 1, 0)", [(big, f"J{i // 4}", imp, codes[i % 500]) for i in range(50000)])
    bc.commit()
    bc.disarm()
    bc.close()

    def timed(fn):
        t0 = time.perf_counter()
        r = fn()
        return r, time.perf_counter() - t0
    r, t_list = timed(lambda: c.get(BASE + f"/api/setup/gl_accounts?entity={big}", headers=H))
    rows = r.get_json()["rows"]
    check(f"the chart of 500 accounts, each with 3 openings and 100 journal lines, is listed with what uses each in {t_list:.2f} s (a budget of 1 s; it took 9 to 16 s when each account scanned the journal lines)",
          r.status_code == 200 and len(rows) == 500 and t_list < 1.0 and rows[0]["used_by"] == [["opening balances", 3], ["SQL journal lines", 100]], (r.status_code, len(rows), t_list, rows[0]["used_by"] if rows else None))
    text = "Code\tName\n" + "\n".join(f"{k}\tRenamed {k}" for k in codes)
    r, t_prev = timed(lambda: c.post(BASE + "/api/setup/gl_accounts/paste", headers=H, json={"entity_id": big, "text": text, "preview": True}))
    r2, t_apply = timed(lambda: c.post(BASE + "/api/setup/gl_accounts/paste", headers=H, json={"entity_id": big, "text": text}))
    check(f"pasting the chart with all 500 names changed takes {t_prev:.2f} s to preview and {t_apply:.2f} s to save (a budget of 3 s each; 15 s before), and changes them",
          r.status_code == 200 and r.get_json()["counts"]["update"] == 500 and r2.status_code == 200 and r2.get_json()["counts"]["update"] == 500 and t_prev < 3 and t_apply < 3
          and q("SELECT name FROM gl_accounts WHERE entity_id = ? AND code = ?", (big, codes[0]))[0]["name"] == f"Renamed {codes[0]}", (r.status_code, t_prev, t_apply))
    gid = q("SELECT id FROM gl_accounts WHERE entity_id = ? AND code = ?", (big, codes[7]))[0]["id"]
    r, t_edit = timed(lambda: c.patch(BASE + f"/api/setup/gl_accounts/{gid}", headers=H, json={"fields": {"name": "Edited once", "notes": "and a note"}}))
    check(f"editing one account takes {t_edit:.2f} s (a budget of 0.5 s)", r.status_code == 200 and t_edit < 0.5, (r.status_code, t_edit))
    r = c.patch(BASE + f"/api/setup/gl_accounts/{gid}", headers=H, json={"fields": {"code": "999-9999"}})
    check("...and its code, which its openings and journal lines name, still can't be changed", r.status_code == 400 and "can't change once used" in r.get_json()["error"], r.get_json())

    # the speed above is a time; this is the work: the lists of a chart read each table once, not once per account, and an edit asks only when it must
    def statements(fn, has):
        """(how many statements of the call have the words in has, what it was refused with, or None)."""
        rc = db.connect()
        seen, refused = [], None
        rc.set_trace_callback(lambda s: seen.append(s) if all(w in s for w in has) else None)
        try:
            fn(rc)
        except masters.Refused as x:
            refused = str(x)
        finally:
            rc.set_trace_callback(None)
            rc.close()
        return len(seen), refused
    GROUPED, EXISTS, SOURCES = ("UPPER(TRIM(", "GROUP BY"), ("UPPER(TRIM(", "LIMIT 1"), len(masters.GL_USES)
    check("listing a chart of 500 accounts reads each of the tables that name an account once, not once per account", statements(lambda rc: masters.listing(rc, "gl_accounts", big), GROUPED)[0] == SOURCES)
    check("one account's record reads each of them once (its Where used and what it locks come from the same reading)", statements(lambda rc: masters.record(rc, "gl_accounts", gid), GROUPED)[0] == SOURCES
          and statements(lambda rc: masters.record(rc, "gl_accounts", gid), EXISTS)[0] == 0)

    def edit(rc, fields, rid=None):
        rc.arm("user", "test: one edit")
        try:
            masters.update(rc, "gl_accounts", rid or gid, fields, quiet=True)
        finally:
            rc.rollback()
            rc.disarm()
    check("an edit of an account's name, type and notes doesn't look for what uses it at all (only its code depends on that)",
          statements(lambda rc: edit(rc, {"name": "Edited twice", "notes": "another note", "type": "asset", "special": "bank"}), ("UPPER(TRIM(",))[0] == 0)
    n, why = statements(lambda rc: edit(rc, {"name": "x", "notes": "y", "code": "999-9998"}), EXISTS)
    check("an edit of the name, the notes and then the code of an account that is used is refused, having asked what uses it once at most (each table once), not once for each field",
          why is not None and "can't change once used" in why and 1 <= n <= SOURCES, (n, why))
    free = call("post", "/api/setup/gl_accounts", json={"entity_id": big, "fields": {"code": "999-0001", "name": "Used by nothing"}})["id"]
    n, why = statements(lambda rc: edit(rc, {"name": "x", "notes": "y", "code": "999-0002"}, free), EXISTS)
    check("...and one that nothing uses is changed (not refused), having asked each table once", why is None and n == SOURCES, (n, why))

# 19. the company switcher's names come from the records' overview: a company's short name travels in it, as Setup keeps it
with section("19. the records' overview (/api/meta) carries each company's short name"):
    names = {e["code"]: e for e in call("get", "/api/meta")["entities"]}
    check("/api/meta lists every company with its short_name key (empty when none is set), which the company switcher reads", all("short_name" in e for e in names.values()) and names["EXA"]["short_name"] in (None, ""), names["EXA"])
    call("patch", f"/api/setup/entities/{EXA}", json={"fields": {"short_name": "Alpha"}})
    check("...and the one set in Setup is there at once", {e["code"]: e["short_name"] for e in call("get", "/api/meta")["entities"]}["EXA"] == "Alpha")

# 20. the longer limit of a setup file's own check (three times) is for the fields kept in capitals; every other field keeps its limit there
with section("20. a setup file's longer limit reaches only the fields kept in capitals"):
    every = [(k, f) for k, spec in masters.KINDS.items() for f in spec["fields"]]
    kept_upper = [(k, f["key"]) for k, f in every if f.get("upper")]
    check("only the bank account's GL code is kept in capitals, so it is the one field the longer limit of a file's check can reach", kept_upper == [("accounts", "gl_code")], kept_upper)
    strict, off = [(k, f) for k, f in every if f["type"] in ("text", "textarea") and not f.get("upper")], []
    for k, f in strict:
        limit = 2000 if f["type"] == "textarea" else f.get("max", 200)
        for n, taken in ((limit, True), (limit + 1, False)):
            try:
                masters.check_value(f, "x" * n, lenient=True)
                got = True
            except masters.Refused:
                got = False
            if got != taken:
                off.append((k, f["key"], n))
    check(f"every other text field of every kind ({len(strict)} of them) keeps its own limit in a file's check: its limit is taken, one more is refused", len(strict) > 20 and not off, off[:5])
    check("...and the GL code is the one that takes three times (600) and refuses one more, in a file's check, while a typed value is held to 200",
          masters.check_value(next(f for k, f in every if f.get("upper")), "x" * 600, lenient=True) == "X" * 600
          and _refused(lambda: masters.check_value(next(f for k, f in every if f.get("upper")), "x" * 601, lenient=True))
          and _refused(lambda: masters.check_value(next(f for k, f in every if f.get("upper")), "x" * 201)))

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
