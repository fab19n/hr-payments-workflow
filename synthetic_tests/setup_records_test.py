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
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-setup-records-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # part 4's new install: --import <setup.json> <what it holds afterwards>

from hrp import config, db, masters, rulebook, rules, setupfile  # noqa: E402
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
KEEP_GOING = bool(os.environ.get("HRP_KEEP_GOING"))  # list every check that fails, not only the first (to see what a change fixes)


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


def last_tx():
    return q("SELECT * FROM audit_tx ORDER BY id DESC LIMIT 1")[0]


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
    call("post", "/api/setup/import", json={"setup": data, "reason": "test: a new install"})
    now = call("get", "/api/setup/import")
    dst.write_text(json.dumps({"preview": counted(pv), "holding": held(now["holding"]), "empty": now["empty"],
                               "codes": [r["code"] for r in q("SELECT code FROM entities ORDER BY id")],
                               "active": {r["code"]: r["active"] for r in q("SELECT code, active FROM entities")}}), encoding="utf-8")
    print("child done")
    sys.exit(0)

# ---------- 1. the menu and sections as the server gives them ----------
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
full = call("get", "/api/setup/export?what=full&payees=1")
check("the file holds the stopped company and not the deleted one", [e["code"] for e in full["entities"]] == ["EXA", "EXB", "EXC"]
      and [e["active"] for e in full["entities"]] == [1, 1, 0], [(e["code"], e["active"]) for e in full["entities"]])
mine = held(call("get", "/api/setup/import")["holding"])
check("what this install holds (Move setup's sentence) counts the stopped company and not the deleted one",
      mine["companies"] == 3 and mine["bank accounts"] == 3 and mine["statutory accounts"] == 1 and mine["customers and suppliers"] == 2
      and mine["GL accounts"] == 3 and mine["recurring payments"] == 1, mine)
fileholds = {w: len(full[k]) for k, w in (("entities", "companies"), ("accounts", "bank accounts"), ("gl_accounts", "GL accounts"),
                                                              ("statutory_accounts", "statutory accounts"), ("parties", "customers and suppliers"),
                                                              ("checklist", "checklist items"), ("payees", "recurring payments"))}
check("the file's own rows are the figures the install holds", all(mine[w] == n for w, n in fileholds.items()), (mine, fileholds))
src_file, out_file = tmp / "setup full.json", tmp / "child out.json"
src_file.write_text(json.dumps(full), encoding="utf-8")
run = subprocess.run([sys.executable, "-m", "synthetic_tests.setup_records_test", "--import", str(src_file), str(out_file)],
                     cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=600)
print("\n".join("  " + line for line in run.stdout.splitlines()))
check("the new install's checks pass", run.returncode == 0, run.stdout[-1500:] + run.stderr[-1500:])
got = json.loads(out_file.read_text(encoding="utf-8"))
check("First run's preview of the file counts the stopped company, not the deleted one", got["preview"]["companies"] == 3, got["preview"])
check("First run's counts are Move setup's: the preview of the file equals what the install holds once it is imported, figure by figure",
      all(got["holding"][w] == got["preview"][w] for w in got["holding"]) and set(got["holding"]) >= {"companies", "bank accounts", "GL accounts", "statutory accounts",
                                                                                                      "customers and suppliers", "checklist items", "recurring payments"},
      (got["preview"], got["holding"]))
# A company with no checklist of its own in the file starts with the starter checklist, so the new install holds those rows too (and the
# preview counts them, above): the first install keeps none of its own for the two companies it never opened a checklist for.
check("...and, but for the starter checklists the import gives, both are what the first install holds",
      all(got["holding"][w] == mine[w] for w in mine if w != "checklist items") and got["holding"]["checklist items"] > mine["checklist items"], (got["holding"], mine))
check("the stopped company comes across as stopped, and nothing is left of the deleted one",
      got["codes"] == ["EXA", "EXB", "EXC"] and got["active"] == {"EXA": 1, "EXB": 1, "EXC": 0} and got["empty"] is False, got)


# ---------- 5. review fixes ----------
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
    write("a confirmed printed company name", ("INSERT INTO sql_company_names (entity_id, name_key, name, confirmed_at) VALUES (?, 'kn', 'EXAMPLE SWITCHED LTD (2026)', ?)", (ko["id"], NOW)))
    call("patch", f"/api/setup/entities/{ko['id']}", json={"fields": {"uses_sql": False}})
    left = call("get", "/api/setup/export?what=full").get("left_out", [])
    check("the export says a name of a company now Kept here stays out, and where to remove it",
          any("EXAMPLE SWITCHED LTD" in x and "no longer kept in SQL Account" in x and "Remove the name in Setup › Companies" in x for x in left), left)
    nm = call("get", f"/api/setup/entities/{ko['id']}/sql-names")
    check("the company's names are still listed for a company Kept here, and can be removed there", nm["ready"] and [n["name"] for n in nm["names"]] == ["EXAMPLE SWITCHED LTD (2026)"])
    call("delete", f"/api/setup/entities/{ko['id']}/sql-names/{nm['names'][0]['id']}", json={})
    check("...removing it leaves none, and the export no longer says it is left out",
          call("get", f"/api/setup/entities/{ko['id']}/sql-names")["names"] == [] and not any("EXAMPLE SWITCHED LTD" in x for x in call("get", "/api/setup/export?what=full").get("left_out", [])))

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

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
