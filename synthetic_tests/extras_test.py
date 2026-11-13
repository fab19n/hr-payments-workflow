"""Setup phase 7 on made-up records only. Part 1: no organisation's names in what a new install is given, and the
starter checklist a company added in Setup gets (rules.STARTER), in the same audited change.

A new install's matching words must be the neutral ones defined here (the utility guess words, and SQL filing words
only for payroll journals: the related company's and the tenant's rules belong to the codes of rules.CHECKLIST and come
only with a company that has them); its organisation name and the page's sidebar line start empty. A company added in
Setup starts with the starter checklist, its own to change (nothing built in); one not kept in SQL Account without the
item asking for SQL vouchers; months set up use it; until a month is set up another company's checklist may be copied
in its place; an unused company is deleted with it.

Part 2: Setup › Move setup. The records above get more made-up setup, then a template and everything are exported
(setup.json) and each is imported into a new install of its own (this file run again with --import, in a fresh records
folder), which exports what it then holds: the two must agree (ids aside). A preview leaves nothing; an import into
records with a company, a file from a newer version, a bad reference, a key twice or a refusal late in the import
leaves nothing either; the trail shows the import as one, with its reason; a template's starter checklist is kept for
companies added later. What Setup reaches imports as it is (--probe): a company added with a code that has a list in the
code keeps its own checklist and one from seed.json its built-in list; document types stopped after a wording or set of
required documents that asked for them ended at a filed month. Setup refuses a title another item takes in a later month.
A copy replaces only an untouched starter checklist; Setup's change, Use again and copy check each title over the months
it will be in use.

Run: .venv\\Scripts\\python -m synthetic_tests.extras_test
"""
import copy
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-extras-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
CHILD = sys.argv[1:2] == ["--import"]  # part 2's new install: --import <setup.json> <what it exports afterwards>
AS_IS = sys.argv[1:2] == ["--as-is"]  # a new install that only imports <setup.json>, as it is
PROBE = sys.argv[1:2] == ["--probe"]  # a new install that imports <setup.json> and writes what it holds to <out.json>
CHILD = CHILD or AS_IS or PROBE

import hrp  # noqa: E402
from hrp import audit, checklistbook, config, db, monthly, partybook, rules, setupfile, sqlimport  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

if not CHILD:
    (tmp / "seed.json").write_text(json.dumps({"entities": [
        {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
        {"code": "EXI", "name": "Example International Ltd", "uses_sql": False,
         "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
    ]}), encoding="utf-8")

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


db.init()
c = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, **kw):
    return getattr(c, method)(BASE + path, headers=H, **kw)


def j(method, path, expect=200, **kw):
    r = call(method, path, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:500])
    return r.get_json()


def n_tx():
    return q("SELECT COUNT(*) AS n FROM audit_tx")[0]["n"]


def import_child(src, dst):
    """Part 2's new install (no seed.json): previews, refusals, then the import of src; writes what it exports then."""
    data = json.loads(src.read_text(encoding="utf-8"))
    what, full = data["what"], data["what"] == "full"
    tag = f"[{what}] "
    st = j("get", "/api/setup/import")
    check(tag + "a new install holds no company data, so it may import", st["empty"] is True and st["holding"] == [], st)
    tx, settings = n_tx(), j("get", "/api/setup/settings")["values"]
    types = q("SELECT key, label FROM payment_types ORDER BY id")
    pv = j("post", "/api/setup/import", json={"setup": data, "preview": True})
    counts = dict(pv["counts"])
    check(tag + "the preview counts what the file adds", pv["preview"] is True and counts["payment types"] == len(data["payment_types"])
          and counts.get("companies", 0) == len(data.get("entities", [])), pv)
    check(tag + "a preview leaves nothing: no company, no trail entry, settings and types as they were",
          j("get", "/api/setup/import")["empty"] and n_tx() == tx and j("get", "/api/setup/settings")["values"] == settings
          and q("SELECT key, label FROM payment_types ORDER BY id") == types and not q("SELECT 1 FROM app_settings WHERE key = ?",
                                                                                         (checklistbook.STARTER_KEY,)))

    def refused(name, change, says, status=400):
        d = copy.deepcopy(data)
        change(d)
        r = call("post", "/api/setup/import", json={"setup": d, "reason": "test: refused"})
        err = (r.get_json() or {}).get("error", "")
        check(tag + f"refused: {name}, leaving nothing", r.status_code == status and says in err and n_tx() == tx
              and j("get", "/api/setup/import")["empty"] and j("get", "/api/setup/settings")["values"] == settings, (r.status_code, err))

    refused("a file from a newer version of the app", lambda d: d.update(records_version=len(db.MIGRATIONS) + 1), "newer version")
    refused("a file in a newer form", lambda d: d.update(format_version=2), "newer form")
    refused("not a setup file", lambda d: d.update(format="something else"), "isn't a setup file")
    refused("a payment type twice", lambda d: d["payment_types"].append(dict(d["payment_types"][-1])), "twice")
    refused("a guess naming no payment type", lambda d: d["guess_words"][0].update(payment_type="no_such_type"), "Payment type")
    refused("a filing word on no checklist item", lambda d: d["filing_words"][0].update(checklist_code="no-such-item"), "no-such-item")
    refused("a setting out of range, found last of all", lambda d: d["settings"].update(soon_days=99), "General settings")
    refused("a header whose holds isn't a list of notes", lambda d: (d.update(holds=5), d["settings"].update(soon_days=9)),
            "can't be read")
    refused("a header whose holds is one piece of text", lambda d: d.update(holds="abc"), "can't be read")
    refused("a header whose made isn't a date and time", lambda d: d.update(made=5), "can't be read")
    refused("a default payment type that isn't a key", lambda d: d["settings"].update(payee_default_category=[]),
            "choose one of the payment types")
    refused("a default month given as yes or no", lambda d: d["settings"].update(payee_default_month_offset=True),
            "the same month or the next month")
    r = call("patch", "/api/setup/settings", json={"values": {"payee_default_category": {"a": 1}}})
    check(tag + "Setup's settings refuse a default payment type that isn't a key", r.status_code == 400
          and "payment types" in r.get_json()["error"] and j("get", "/api/setup/settings")["values"] == settings, r.data[:300])
    load = setupfile.load

    def fails_late(con, d):  # a failure no check foresaw, after the import saved its settings
        load(con, d)
        raise RuntimeError("test: a failure after the settings were saved")
    setupfile.load = fails_late
    try:
        d = copy.deepcopy(data)
        d["settings"]["soon_days"] = 9
        try:
            r = call("post", "/api/setup/import", json={"setup": d, "reason": "test: fails late"})
            status = r.status_code
        except RuntimeError:
            status = 500
    finally:
        setupfile.load = load
    check(tag + "a failure late in an import undoes it, and the settings in use are the kept ones",
          status == 500 and n_tx() == tx and j("get", "/api/setup/import")["empty"]
          and j("get", "/api/setup/settings")["values"] == settings, status)
    if full:
        refused("a recurring payment starting on a day not on the calendar",
                lambda d: d["payees"][0].update(start_date="2026-11-31"), "dates are written like 2026-10-20")
        refused("a recurring payment ending on a month not on the calendar",
                lambda d: d["payees"][0].update(end_date="2026-13-45"), "dates are written like 2026-10-20")
        refused("recurring payments in use paid from a stopped bank account",
                lambda d: next(a for a in d["accounts"] if a["ref"] == d["payees"][0]["account"]).update(active=0),
                "Recurring payments are paid from this account")
        refused("a document type stopped while the checklist asks for it",
                lambda d: next(t for t in d["doc_types"] if t["key"] == "tax_form").update(active=0),
                "The monthly checklist asks for this document type")

        def same_title(d):
            x = copy.deepcopy(next(x for x in d["checklist"] if x["code"] == "water-bills-paid"))
            x["code"] = "zzz-copy"
            for t in x["terms"]:
                t["title"] = t["title"].lower()
            d["checklist"].append(x)
        refused("two checklist items in use in one company with the same title", same_title, "Another item in use is called")
        refused("a company twice", lambda d: d["entities"].append(dict(d["entities"][0])), "twice")
        refused("a set of documents for a company not in the file",
                lambda d: d["required_sets"].append({"payment_type": "other", "company": "NOPE", "from_month": "2026-01", "docs": []}),
                "no company NOPE")
        refused("a recurring payment from a bank account not in the file", lambda d: d["payees"][0].update(account="a99"),
                "no bank account a99")
        refused("an account under a parent not in the chart", lambda d: d["gl_accounts"][-1].update(parent_code="999-999"),
                "no account 999-999")
    else:
        refused("a template holding a company", lambda d: d.update(entities=[{"code": "EXZ", "name": "Example Z Ltd"}]), "rules only")
        mine = next(x for x in data["starter_checklist"] if x["code"] not in checklistbook.BUILT_IN)
        refused("two starter checklist items with the same title",
                lambda d: d["starter_checklist"].append({**mine, "code": "zzz-copy", "title": mine["title"].upper()}),
                "Another item in use is called")
        refused("a document type stopped while a set of required documents asks for it",
                lambda d: next(t for t in d["doc_types"] if t["key"] == "tax_form").update(active=0), "It is still required for")
    r = call("post", "/api/setup/import", json={"setup": data})
    check(tag + "an import asks why", r.status_code == 400 and "why" in r.get_json()["error"])
    out = j("post", "/api/setup/import", json={"setup": data, "reason": f"test: start from the {what}"})
    t = q("SELECT * FROM audit_tx WHERE id = (SELECT MAX(id) FROM audit_tx)")[0]
    check(tag + "the trail shows it as an import, with its reason, in one entry",
          out["preview"] is False and t["source"] == "import" and t["reason"] == f"test: start from the {what}"
          and n_tx() == tx + 1 and "Imported a setup" in (t["summary"] or ""), dict(t))
    again = call("get", f"/api/setup/export?what={what}" + ("&payees=1" if "payees" in data else ""))
    dst.write_bytes(again.data)  # before a company is added below
    if full:
        empty = [e["code"] for e in data["entities"] if not any(x["company"] == e["code"] for x in data["checklist"])]
        got = {e: [r["code"] for r in q("SELECT i.code FROM checklist_items i JOIN entities e ON e.id = i.entity_id WHERE e.code = ? "
                                         "ORDER BY i.id", (e,))] for e in empty}
        check(tag + "a company with no checklist in the file starts with the starter checklist",
              empty and all(got[e] == [x[0] for x in rules.STARTER if next(y for y in data["entities"] if y["code"] == e)
                                       .get("uses_sql", 1) or x[0] not in rules.STARTER_SQL_ONLY] for e in empty), got)
        r = call("post", "/api/setup/import", json={"setup": data, "reason": "test: again"})
        check(tag + "records holding companies refuse another import", r.status_code == 409 and "new records" in r.get_json()["error"])
    else:
        new = j("post", "/api/setup/entities", json={"fields": {"code": "EXL", "name": "Example Later Sdn Bhd"}, "reason": "test"})
        codes = [i["code"] for i in j("get", f"/api/setup/checklist?entity={new['id']}")["items"]]
        check(tag + "a company added later starts with the template's starter checklist",
              codes == [x["code"] for x in data["starter_checklist"]], codes)
    with db.connect() as r:
        check(tag + "the trail checks out", audit.verify(r)["ok"])
    print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")


def import_as_is(src):
    """A new install that imports src as it is: a full export with EXH's cash book stopped and FCA USD in use."""
    data = json.loads(src.read_text(encoding="utf-8"))
    pv = j("post", "/api/setup/import", json={"setup": data, "preview": True})
    j("post", "/api/setup/import", json={"setup": data, "reason": "test: a stopped cash book"})
    got = [(r["label"], r["active"], r["cash_book"]) for r in q(
        "SELECT a.label, a.active, a.cash_book FROM accounts a JOIN entities e ON e.id = a.entity_id WHERE e.code = 'EXH' ORDER BY a.id")]
    check("[as is] a stopped cash book with another account in use, as Setup reaches it, imports as it is",
          pv["preview"] is True and got == [("Main", 0, 1), ("FCA USD", 1, 0)], got)


def import_probe(src, out):
    """A new install that previews, then imports, src as it is, and writes what it then holds to out: the answers, each
    company's checklist (code, built in, can be deleted) and whether it can be replaced, and the document types in use."""
    data = json.loads(src.read_text(encoding="utf-8"))
    got = {}
    for name, pv in (("preview", True), ("import", False)):
        r = call("post", "/api/setup/import", json={"setup": data, "preview": pv, "reason": "test: as Setup left it"})
        got[name] = [r.status_code, (r.get_json(silent=True) or {}).get("error")]
    got["companies"] = {}
    for e in q("SELECT id, code FROM entities ORDER BY id"):
        v = j("get", f"/api/setup/checklist?entity={e['id']}")
        got["companies"][e["code"]] = {"items": [[i["code"], i["system"], i["can_delete"]] for i in v["items"]],
                                       "replaceable": v["replaceable"]}
    got["doc_types"] = {r["key"]: r["active"] for r in q("SELECT key, active FROM doc_types")}
    with db.connect() as r:
        got["trail_ok"] = audit.verify(r)["ok"]
    out.write_text(json.dumps(got), encoding="utf-8")


if PROBE:
    import_probe(Path(sys.argv[2]), Path(sys.argv[3]))
    sys.exit(0)

if CHILD:
    if AS_IS:
        import_as_is(Path(sys.argv[2]))
    else:
        import_child(Path(sys.argv[2]), Path(sys.argv[3]))
    sys.exit(0)


# ---------- 1. what a new install is given ----------
check("a new install runs every update", q("PRAGMA user_version")[0]["user_version"] == len(db.MIGRATIONS))
check("companies from seed.json whose code has no list in the code get no checklist, as before",
      q("SELECT COUNT(*) AS n FROM checklist_items")[0]["n"] == 0)
UTILITY_WORDS = ["ELECTRIC", "WATER", "INTERNET", "BROADBAND", "TELCO", "TELEPHONE"]
guess = [(r["label"], json.loads(r["words"]), r["payment_type"]) for r in q("SELECT * FROM guess_words ORDER BY sort, id")]
check("the guess words are the code's own, the utility ones neutral",
      guess == [(label, list(words), cat) for label, words, cat in checklistbook.GUESS]
      and ("Utilities and telco", UTILITY_WORDS, "utility") in guess, guess)
filing = [(r["label"], json.loads(r["words"]), r["doc_kind"], r["direction"], r["checklist_code"])
          for r in q("SELECT * FROM filing_words ORDER BY sort, id")]
check("a new install's SQL filing words are only the payroll journals' (no company's names)",
      filing == [("Payroll journals", ["PAYROLL", "SALARY", "SALARIES", "WAGES", "GAJI"], "journal", None, "payroll-jv")], filing)
check("the organisation name starts empty", j("get", "/api/meta")["settings"]["organisation_name"] == "")
page = (Path(hrp.__file__).parent.parent / "static" / "index.html").read_text(encoding="utf-8")
check("the page's sidebar line starts empty and hidden", re.search(r'<div class="eyebrow" id="orgName" hidden></div>', page))
check("update 13 reads no company's checklist (the self-billed due date is frozen)",
      db.SELFBILLED_DUE == (1, 7) == next(d for code, d, *_ in rules.STARTER if code == "einv-selfbilled"))

# A company whose code has a list in the code (an older seed.json) gets it, built in, and the SQL filing words of its
# codes; nothing is kept (the change is rolled back).
code = next(iter(rules.CHECKLIST))
con = db.connect()
try:
    con.arm("user", "test: a company with a list in the code")
    eid = con.execute("INSERT INTO entities (code, name, uses_sql) VALUES (?, 'Example Frozen Sdn Bhd', 1)", (code,)).lastrowid
    checklistbook.seed_company(con, {"id": eid, "code": code})
    checklistbook.seed_filing(con, {r[0] for r in con.execute("SELECT code FROM checklist_items WHERE entity_id = ?", (eid,))})
    items = con.execute("SELECT code, system FROM checklist_items WHERE entity_id = ? ORDER BY id", (eid,)).fetchall()
    codes = {r[0] for r in con.execute("SELECT DISTINCT checklist_code FROM filing_words")}
    check("a code with a list in the code gets that list, built in, and the filing words for its codes",
          [r[0] for r in items] == [x[0] for x in rules.CHECKLIST[code]] and all(r[1] == 1 for r in items)
          and codes == {x[3] for x in sqlimport.TASK_RULES} & {x[0] for x in rules.CHECKLIST[code]}, (items, codes))
    # seed.json's "names" put real names in place of the placeholders, here made-up ones, in the same case
    for other in rules.CHECKLIST:
        if other != code:
            oid = con.execute("INSERT INTO entities (code, name, uses_sql) VALUES (?, 'Example Other Sdn Bhd', 1)", (other,)).lastrowid
            checklistbook.seed_company(con, {"id": oid, "code": other})
    checklistbook.seed_filing(con, {r[0] for r in con.execute("SELECT DISTINCT code FROM checklist_items")})
    held = lambda: " ".join(str(v) for t, c, _ in checklistbook.NAME_COLUMNS for (v,) in con.execute(f"SELECT {c} FROM {t}"))
    check("the built-in lists and filing words hold the placeholders",
          all(p in held() and p.upper() in held() for p in rules.PLACEHOLDERS[:1]) and rules.PLACEHOLDERS[1].upper() in held())
    checklistbook.fill_names(con, {rules.PLACEHOLDERS[0]: "Example Sister Bhd", rules.PLACEHOLDERS[1]: "Example Tenant"})
    text = held()
    check("seed.json's names take the placeholders' place, in capitals where they were in capitals",
          not any(p.lower() in text.lower() for p in rules.PLACEHOLDERS) and "Example Sister Bhd" in text
          and "EXAMPLE SISTER BHD" in text and "EXAMPLE TENANT" in text)
    # A name holding another placeholder's words (or its own) is written as given, not changed again
    fid = con.execute("INSERT INTO filing_words (label, words, doc_kind, checklist_code, sort) VALUES ('test', ?, 'invoice', "
                      "'fund-received', 99)", (json.dumps([p.upper() for p in rules.PLACEHOLDERS]),)).lastrowid
    checklistbook.fill_names(con, {rules.PLACEHOLDERS[0]: rules.PLACEHOLDERS[1] + " Holdings",
                                   rules.PLACEHOLDERS[1]: rules.PLACEHOLDERS[1] + " \"Two\" & Co\\"})
    got = json.loads(con.execute("SELECT words FROM filing_words WHERE id = ?", (fid,)).fetchone()[0])
    check("a name holding a placeholder's words, quotes or a backslash is written as given",
          got == [(rules.PLACEHOLDERS[1] + " Holdings").upper(), (rules.PLACEHOLDERS[1] + " \"Two\" & Co\\").upper()], got)
    bad = []
    for names in ({"Someone Else": "Example"}, {rules.PLACEHOLDERS[0]: " "}, ["x"],
                  {rules.PLACEHOLDERS[0]: "Ex3ample"}):  # the markers fill_names uses on the way
        try:
            checklistbook.fill_names(con, names)
        except ValueError:
            bad.append(names)
    check("names for anything but the placeholders, empty ones or ones holding its markers are refused", len(bad) == 4, bad)
    # A company added in Setup gets the starter checklist whatever its code, even one with a list in the code
    sid = con.execute("INSERT INTO entities (code, name, uses_sql) VALUES (?, 'Example Again Sdn Bhd', 1)", (code + "X",)).lastrowid
    con.execute("UPDATE entities SET code = ? WHERE id = ?", (code + "-new", sid))
    checklistbook.seed_company(con, {"id": sid, "code": code, "uses_sql": 1}, starter=True)
    items = con.execute("SELECT code, system FROM checklist_items WHERE entity_id = ? ORDER BY id", (sid,)).fetchall()
    check("a company added with a code that has a list in the code still gets the starter checklist, its own to change",
          [r[0] for r in items] == [x[0] for x in rules.STARTER] and all(r[1] == 0 for r in items), items)
finally:
    con.rollback()
    con.close()

# ---------- 2. a company added in Setup ----------
STARTER = [x[0] for x in rules.STARTER]
new = j("post", "/api/setup/entities", json={"fields": {"code": "EXT", "name": "Example Trading Sdn Bhd"}, "reason": "test: new company"})
chk = j("get", f"/api/setup/checklist?entity={new['id']}")
check("a company added starts with the starter checklist, in order, worded as the code has it",
      [i["code"] for i in chk["items"]] == STARTER
      and [i["now"]["title"] for i in chk["items"]] == [x[2] for x in rules.STARTER], [i["code"] for i in chk["items"]])
check("its items are its own to change: nothing built in, each can be deleted, the list can still be replaced",
      all(i["can_delete"] and not i["system"] for i in chk["items"]) and chk["replaceable"] is True)
check("Setup no longer says it has no checklist", not any("no monthly checklist" in n for n in new["notes"]))
tok = q("SELECT token FROM audit_row WHERE tbl = 'entities' AND op = 'insert' AND row_key = ?", (str(new["id"]),))[0]["token"]
tables = {r["tbl"] for r in q("SELECT DISTINCT tbl FROM audit_row WHERE token = ?", (tok,))}
tx = q("SELECT reason FROM audit_tx WHERE id = (SELECT MAX(id) FROM audit_tx)")[0]
check("the checklist is added in the same audited change as the company, with its reason",
      {"entities", "checklist_items", "checklist_terms"} <= tables and tx["reason"] == "test: new company", (tables, tx))
noq = j("post", "/api/setup/entities", json={"fields": {"code": "EXN", "name": "Example Services Ltd", "uses_sql": False}})
chk_n = j("get", f"/api/setup/checklist?entity={noq['id']}")
check("a company not kept in SQL Account starts without the item asking for SQL vouchers",
      [i["code"] for i in chk_n["items"]] == [x for x in STARTER if x not in rules.STARTER_SQL_ONLY])
check("the starter checklist names no company", not any(re.search(r"\b(sdn|bhd|ltd|international)\b", f"{x[2]} {x[3]}", re.I)
                                                         for x in rules.STARTER))

# ---------- 3. months set up with it ----------
month = db.current_cycle()
j("post", "/api/months/open", json={"entity_id": new["id"], "month": month})
tasks = [r["code"] for r in q("SELECT code FROM tasks WHERE entity_id = ? AND month = ? AND code NOT LIKE 'joiner-%' "
                               "AND code NOT LIKE 'leaver-%' ORDER BY sort, id", (new["id"], month))]
check("a month set up for it gets the starter checklist", tasks == STARTER, tasks)
chk = j("get", f"/api/setup/checklist?entity={new['id']}")
r = call("post", "/api/setup/checklist", json={"action": "copy", "entity_id": new["id"], "copy_from": noq["id"],
                                                "from_month": chk["default_from"]})
check("once a month is set up with it, it can't be replaced by a copy", r.status_code == 400 and "already has a checklist" in
      r.get_json()["error"] and chk["replaceable"] is False, r.get_json())

# ---------- 4. replaced by a copy before any month is set up ----------
fresh = j("get", f"/api/setup/checklist?entity={noq['id']}")
pv = j("post", "/api/setup/checklist", json={"action": "copy", "entity_id": noq["id"], "copy_from": new["id"],
                                             "from_month": fresh["default_from"], "preview": True})
check("a copy can be previewed, leaving the starter checklist as it was",
      pv["preview"] is True and [i["code"] for i in j("get", f"/api/setup/checklist?entity={noq['id']}")["items"]]
      == [i["code"] for i in fresh["items"]])
j("post", "/api/setup/checklist", json={"action": "copy", "entity_id": noq["id"], "copy_from": new["id"],
                                        "from_month": fresh["default_from"], "reason": "test: as the other company"})
after = j("get", f"/api/setup/checklist?entity={noq['id']}")
check("the copy takes the starter checklist's place (the SQL vouchers item comes with it)",
      [i["code"] for i in after["items"]] == STARTER and "payroll-jv" not in [i["code"] for i in fresh["items"]],
      [i["code"] for i in after["items"]])

# ---------- 5. an unused company is deleted with its checklist ----------
gone = j("post", "/api/setup/entities", json={"fields": {"code": "EXD", "name": "Example Dormant Sdn Bhd"}})
check("another company added has its starter checklist", q("SELECT COUNT(*) AS n FROM checklist_items WHERE entity_id = ?",
                                                            (gone["id"],))[0]["n"] == len(STARTER))
j("delete", f"/api/setup/entities/{gone['id']}", json={"reason": "test: added by mistake"})
check("an unused company is deleted with its checklist, not refused by it",
      not q("SELECT 1 FROM entities WHERE id = ?", (gone["id"],))
      and not q("SELECT 1 FROM checklist_items WHERE entity_id = ?", (gone["id"],))
      and not q("SELECT 1 FROM checklist_terms WHERE item_id NOT IN (SELECT id FROM checklist_items)"))
with db.connect() as r:
    check("the trail checks out", audit.verify(r)["ok"])

# ---------- 6. more made-up setup to move ----------
ents = {e["code"]: e["id"] for e in j("get", "/api/meta")["entities"]}
EXH, EXT = ents["EXH"], ents["EXT"]
j("post", "/api/setup/payment_types", json={"fields": {"key": "water_bill", "label": "Water bill", "plural": "water bills", "direction": "out"}})
j("post", "/api/setup/doc_types", json={"fields": {"key": "tax_form", "label": "Tax form", "singular": "tax form", "plural": "tax forms"}})
old = j("post", "/api/setup/doc_types", json={"fields": {"key": "old_form", "label": "Old form"}})
j("post", f"/api/setup/doc_types/{old['id']}/stop", json={"reason": "test: not used any more"})
frm = j("get", "/api/setup/required")["default_from"]
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": None, "docs": ["invoice", "tax_form"], "from_month": frm})
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": EXT, "docs": ["tax_form"], "from_month": frm})
acme = j("post", "/api/setup/parties", json={"fields": {"name": "Acme Paper Trading", "kind": "supplier", "entity_id": EXH,
                                                        "sql_code": "400-A001", "tin": "C1234567890"}})
j("post", "/api/setup/parties", json={"fields": {"name": "Beta Stationery", "kind": "supplier", "entity_id": None}})
j("post", "/api/setup/parties", json={"fields": {"name": "Gamma Books Ltd", "kind": "customer", "entity_id": EXH, "match_words": "GAMMA, BOOKS"}})
group = next(code for code, _, t in partybook.SQL_GROUPS if t == "equity")
j("post", "/api/setup/gl_accounts", json={"fields": {"code": "300-000", "name": "Capital", "sql_type": group}, "entity_id": EXH})
j("post", "/api/setup/gl_accounts", json={"fields": {"code": "300-100", "name": "Share capital", "parent_code": "300-000", "sql_type": group},
                                          "entity_id": EXH})
j("post", "/api/setup/gl_accounts", json={"fields": {"code": "310-000", "name": "Bank", "special": "bank", "type": "asset"}, "entity_id": EXH})
j("post", "/api/setup/accounts", json={"fields": {"label": "FCA USD", "bank": "Example Bank", "number": "000-333", "currency": "USD",
                                                  "gl_code": "310-000"}, "entity_id": EXH})
j("post", "/api/setup/filing_words", json={"fields": {"label": "Acme invoices", "doc_kind": "invoice", "words": "ACME",
                                                      "checklist_code": "budget", "party_id": acme["id"]}})
guess = j("get", "/api/setup/guess_words")["rows"][0]
j("post", f"/api/setup/guess_words/{guess['id']}/stop", json={"reason": "test: not wanted"})
rem = j("get", "/api/setup/reminders")
j("post", "/api/setup/reminders", json={"action": "add", "key": "medical", "kind": "joiner", "short_name": "Medical check",
                                        "from_month": rem["default_from"],
                                        "fields": {"days": 14, "title": "Medical check for {name}", "detail": "Book it by {date}.", "docs": []}})
j("patch", "/api/setup/settings", json={"values": {"soon_days": 5, "organisation_name": "Example Group"}})
main_acct = q("SELECT id FROM accounts WHERE entity_id = ? AND label = 'Main'", (EXH,))[0]["id"]
staff = j("post", "/api/payees", json={"entity_id": EXH, "name": "Example Staff One", "category": "salary", "amount": 3000, "due_day": 25,
                                       "month_offset": 0, "bank_details": "Example Bank 1234 5678", "account_id": main_acct})
j("post", f"/api/payees/{staff['id']}/advances", json={"monthly_deduction": 100, "start_month": "2026-01", "end_month": "2026-03",
                                                       "note": "test advance"})
j("post", "/api/payees", json={"entity_id": EXH, "name": "Acme Paper Trading", "category": "water_bill", "party_id": acme["id"],
                               "match_words": "ACME PAPER"})
chk = j("get", f"/api/setup/checklist?entity={EXT}")
j("post", "/api/setup/checklist", json={"action": "add", "entity_id": EXT, "from_month": chk["default_from"],
                                        "fields": {"completion": "payments", "title": "Water bills paid", "due_offset": 1, "due_day": 15,
                                                   "rule": {"categories": ["water_bill"], "docs": ["tax_form"], "name": ["water bill", "water bills"]}}})


def export(query):
    r = call("get", "/api/setup/export?" + query)
    check(f"export {query}: a JSON file to save", r.status_code == 200 and r.mimetype == "application/json"
          and "attachment" in r.headers.get("Content-Disposition", ""), (r.status_code, r.data[:300]))
    return r.data, json.loads(r.data)


reads = len(q("SELECT 1 FROM audit_row WHERE tbl = 'read' AND row_key = 'setup export'"))
t_raw, template = export(f"what=template&entity={EXT}")
f_raw, full = export("what=full&payees=1")
n_raw, nopay = export("what=full")
check("each export is kept in the trail", len(q("SELECT 1 FROM audit_row WHERE tbl = 'read' AND row_key = 'setup export'")) == reads + 3)
check("an export says what it is and which records made it",
      all(d["format"] == "hrp-setup" and d["format_version"] == 1 and d["records_version"] == len(db.MIGRATIONS) for d in (template, full))
      and (template["what"], full["what"]) == ("template", "full"))
check("the template holds the rules only: no company, account, customer, supplier, person or the organisation's name",
      not any(k in template for k in ("entities", "accounts", "gl_accounts", "parties", "checklist", "payees", "advances"))
      and not any(s.encode() in t_raw for s in ("Example Holdings", "000-111", "C1234567890", "Example Staff", "Example Group"))
      and "organisation_name" not in template["settings"] and template["settings"]["soon_days"] == 5)
check("its starter checklist is the chosen company's, in force now",
      [x["code"] for x in template["starter_checklist"]] == STARTER + ["water-bills-paid"], [x["code"] for x in template["starter_checklist"]])
check("its filing words are those of its starter checklist, without the supplier",
      [(w["label"], w["checklist_code"], w["party"]) for w in template["filing_words"]]
      == [("Payroll journals", "payroll-jv", None), ("Acme invoices", "budget", None)], template["filing_words"])
check("its sets of required documents are those for every company",
      all(s["company"] is None for s in template["required_sets"]) and any(s["payment_type"] == "water_bill" for s in template["required_sets"]))
check("everything says it holds bank account numbers, and the recurring payments' personal data when ticked",
      any("account numbers" in h for h in full["holds"]) and any("personal data" in h for h in full["holds"])
      and not any("personal data" in h for h in nopay["holds"]) and "payees" not in nopay and "advances" not in nopay
      and b"Example Staff" not in n_raw and b"000-111" in n_raw)
check("ids never go into the file: references are codes, keys or refs",
      not re.search(rb'"(id|entity_id|account_id|party_id|payee_id|item_id|people_task_id)"', f_raw)
      and next(p for p in full["payees"] if p["name"] == "Acme Paper Trading")["party"] == "p1"
      and next(p for p in full["payees"] if p["name"] == "Example Staff One")["account"] == "a1"
      and full["advances"][0]["payee"] == next(p for p in full["payees"] if p["name"] == "Example Staff One")["ref"])
r = call("post", "/api/setup/import", json={"setup": template, "reason": "test: into records in use"})
check("records holding companies refuse an import, saying why", r.status_code == 409 and "new records" in r.get_json()["error"]
      and not j("get", "/api/setup/import")["empty"])

# ---------- 7. each imported into a new install of its own ----------


def norm(d, drop_items_of=()):
    """An export to compare: when it was made aside, and the payments rules as Setup keeps them (the code's own lists
    hold them in a shorter form)."""
    d = json.loads(json.dumps(d))
    d.pop("made")
    for x in d.get("starter_checklist", []):
        x["rule"] = monthly._norm_rule(x["rule"])
    d["checklist"] = [x for x in d.get("checklist", []) if x["company"] not in drop_items_of]
    for x in d["checklist"]:
        for t in x["terms"]:
            t["rule"] = monthly._norm_rule(t["rule"])
    return d


root = Path(__file__).resolve().parent.parent
for name, raw, d in (("template", t_raw, template), ("full", f_raw, full)):
    src, dst = tmp / f"setup-{name}.json", tmp / f"setup-{name}-again.json"
    src.write_bytes(raw)
    run = subprocess.run([sys.executable, "-m", "synthetic_tests.extras_test", "--import", str(src), str(dst)], cwd=root,
                         capture_output=True, text=True, encoding="utf-8")
    print("\n".join("  " + x for x in run.stdout.strip().splitlines()))
    check(f"the {name} goes into a new install of its own", run.returncode == 0 and dst.exists(), run.stderr[-2000:])
    again = json.loads(dst.read_text(encoding="utf-8"))
    no_list = [e["code"] for e in d.get("entities", []) if not any(x["company"] == e["code"] for x in d["checklist"])]
    a, b = norm(d), norm(again, drop_items_of=no_list)
    diff = [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
    check(f"the new install exports the {name} it was given: names, codes, rules, checklists, chart, settings"
          + (", customers and suppliers, recurring payments" if name == "full" else ""), not diff,
          {k: (a.get(k), b.get(k)) for k in diff[:2]})

# ---------- 8. a stopped cash book, as Setup reaches it, still moves ----------
# Setup can leave a company's cash book stopped while another account is in use: stop the other account, stop the cash
# book (nothing else is in use then), use the other one again (in USD, it doesn't take the cash book).
main_acct, fca = (q("SELECT id FROM accounts WHERE entity_id = ? AND label = ?", (EXH, x))[0]["id"] for x in ("Main", "FCA USD"))
for p in q("SELECT id FROM payees WHERE account_id = ? AND active = 1", (main_acct,)):
    j("post", f"/api/payees/{p['id']}/stop", json={"reason": "test: paid from elsewhere"})
for rid, act in ((fca, "stop"), (main_acct, "stop"), (fca, "use")):
    j("post", f"/api/setup/accounts/{rid}/{act}", json={"reason": "test: the cash book stopped"})
got = [(r["label"], r["active"], r["cash_book"]) for r in q("SELECT label, active, cash_book FROM accounts WHERE entity_id = ? ORDER BY id",
                                                             (EXH,))]
check("Setup reaches a stopped cash book with another account in use", got == [("Main", 0, 1), ("FCA USD", 1, 0)], got)
src = tmp / "setup-stopped-cash-book.json"
src.write_bytes(export("what=full&payees=1")[0])
run = subprocess.run([sys.executable, "-m", "synthetic_tests.extras_test", "--as-is", str(src)], cwd=root,
                     capture_output=True, text=True, encoding="utf-8")
print("\n".join("  " + x for x in run.stdout.strip().splitlines()))
check("its export goes into a new install of its own", run.returncode == 0 and "PASS [as is]" in run.stdout, run.stderr[-2000:])

# ---------- 9. what Setup reaches moves as it is ----------
# A company added in Setup with a code that has a list in the code has the starter checklist, its own (nothing built
# in); one from seed.json with such a code has that list, built in. A document type stopped once only a wording or a set
# of required documents that ended at a filed month asks for it. Setup refuses a title another item will have in use.
frozen_code, seeded_code = list(rules.CHECKLIST)[:2]
added = j("post", "/api/setup/entities", json={"fields": {"code": frozen_code, "name": "Example Added Sdn Bhd"}, "reason": "test"})
con = db.connect()
try:
    con.arm("seed", "test: a company from seed.json")
    db.load_seed(con, {"entities": [{"code": seeded_code, "name": "Example Seeded Sdn Bhd"}]})
    con.commit()
finally:
    con.disarm()
    con.close()
ents = {e["code"]: e["id"] for e in j("get", "/api/meta")["entities"]}
src_added, src_seeded = (j("get", f"/api/setup/checklist?entity={ents[x]}") for x in (frozen_code, seeded_code))
check("a company added with a code that has a list in the code has its own starter checklist; one from seed.json the list, built in",
      all(not i["system"] and i["can_delete"] for i in src_added["items"]) and src_added["replaceable"] is True
      and [i["code"] for i in src_seeded["items"]] == [x[0] for x in rules.CHECKLIST[seeded_code]]
      and all(i["system"] for i in src_seeded["items"]), (src_added["items"][:2], src_seeded["items"][:2]))

ef = j("post", "/api/setup/entities", json={"fields": {"code": "EXF", "name": "Example Filing Sdn Bhd"}, "reason": "test"})["id"]
j("post", "/api/setup/accounts", json={"fields": {"label": "Main", "bank": "Example Bank", "number": "000-444", "currency": "MYR"}, "entity_id": ef})
exdoc = j("post", "/api/setup/doc_types", json={"fields": {"key": "exdoc", "label": "Example form"}})
exset = j("post", "/api/setup/doc_types", json={"fields": {"key": "exset", "label": "Example set form"}})
M = j("get", f"/api/setup/checklist?entity={ef}")["default_from"]
N = db.shift_month(M, 1)
form = j("post", "/api/setup/checklist", json={"action": "add", "entity_id": ef, "from_month": M,
                                               "fields": {"title": "Example form signed", "completion": "hand", "due_day": 5,
                                                          "due_offset": 0, "docs": ["exdoc"]}})["item_id"]
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": ef, "docs": ["exset"], "from_month": M})
j("post", "/api/months/open", json={"entity_id": ef, "month": M, "reason": "test"})
j("post", "/api/months/close", json={"entity_id": ef, "month": M, "closed": True, "reason": "test: filed"})
j("post", "/api/setup/checklist", json={"action": "change", "entity_id": ef, "item_id": form, "from_month": N,
                                        "fields": {"title": "Example form signed", "due_day": 5, "due_offset": 0, "docs": []}})
j("post", "/api/setup/required", json={"payment_type": "water_bill", "entity_id": ef, "docs": [], "from_month": N})
for d in (exdoc, exset):
    j("post", f"/api/setup/doc_types/{d['id']}/stop", json={"reason": "test: retired after a filed month"})
check("Setup stops document types only a wording and a set that ended at a filed month asked for",
      q("SELECT key, active FROM doc_types WHERE key IN ('exdoc', 'exset') ORDER BY key") == [{"key": "exdoc", "active": 0},
                                                                                             {"key": "exset", "active": 0}]
      and q("SELECT to_month FROM checklist_terms WHERE item_id = ? AND docs LIKE '%exdoc%'", (form,)) == [{"to_month": N}]
      and q("SELECT to_month FROM required_sets WHERE entity_id = ? AND docs LIKE '%exset%'", (ef,)) == [{"to_month": N}])

# A title planned for later is taken from the month it is planned for back: an item can't take it earlier, by an add
# or a change; a title an item had only before the month asked for is free.
ALPHA, BRAVO, CHARLIE = "Example Alpha task", "Example Bravo task", "Example Charlie task"
hand = {"completion": "hand", "due_day": 5, "due_offset": 0, "docs": []}
alpha = j("post", "/api/setup/checklist", json={"action": "add", "entity_id": ef, "from_month": N, "fields": {**hand, "title": ALPHA}})["item_id"]
j("post", "/api/setup/checklist", json={"action": "change", "entity_id": ef, "item_id": alpha, "from_month": db.shift_month(N, 4),
                                        "fields": {**hand, "title": BRAVO}})
r = call("post", "/api/setup/checklist", json={"action": "add", "entity_id": ef, "from_month": db.shift_month(N, 1),
                                                "fields": {**hand, "title": BRAVO}})
says = f"Another item in use is called {BRAVO}. Give this one another title."
check("Setup refuses an item added earlier with a title another item takes later", r.status_code == 400
      and r.get_json()["error"] == says, (r.status_code, r.data[:300]))
charlie = j("post", "/api/setup/checklist", json={"action": "add", "entity_id": ef, "from_month": N, "fields": {**hand, "title": CHARLIE}})["item_id"]
r = call("post", "/api/setup/checklist", json={"action": "change", "entity_id": ef, "item_id": charlie, "from_month": db.shift_month(N, 1),
                                                "fields": {**hand, "title": BRAVO}})
check("Setup refuses changing an item to it earlier too, in the same words", r.status_code == 400 and r.get_json()["error"] == says,
      (r.status_code, r.data[:300]))
r = call("post", "/api/setup/checklist", json={"action": "add", "entity_id": ef, "from_month": db.shift_month(N, 4),
                                                "fields": {**hand, "title": ALPHA}})
check("a title another item had only before that month may be used", r.status_code == 200, r.data[:300])

src, out = tmp / "setup-as-setup-left-it.json", tmp / "setup-as-setup-left-it-held.json"
raw, data = export("what=full&payees=1")
src.write_bytes(raw)


def probe(path):
    run = subprocess.run([sys.executable, "-m", "synthetic_tests.extras_test", "--probe", str(path), str(out)], cwd=root,
                         capture_output=True, text=True, encoding="utf-8")
    check(f"a new install takes {path.name}", run.returncode == 0 and out.exists(), run.stderr[-2000:])
    return json.loads(out.read_text(encoding="utf-8"))


held = probe(src)
check("its export imports, in a preview and for real, with the document types stopped",
      held["preview"] == [200, None] and held["import"] == [200, None] and held["doc_types"]["exdoc"] == 0
      and held["doc_types"]["exset"] == 0 and held["trail_ok"], {k: held[k] for k in ("preview", "import")})
mine = held["companies"][frozen_code]
check("the company added in Setup keeps its own checklist: nothing built in, each item can be deleted, the list replaced",
      [x[0] for x in mine["items"]] == [i["code"] for i in src_added["items"]]
      and all(x[1] == 0 and x[2] for x in mine["items"]) and mine["replaceable"] is True, mine)
seeded = held["companies"][seeded_code]
check("the company from seed.json keeps its list built in",
      [x[0] for x in seeded["items"]] == [x[0] for x in rules.CHECKLIST[seeded_code]]
      and all(x[1] == 1 and not x[2] for x in seeded["items"]), seeded)
d = copy.deepcopy(data)
for x in d["checklist"]:
    x.pop("system")
src.write_text(json.dumps(d), encoding="utf-8")
held = probe(src)
check("an item the file doesn't say is built in imports as the company's own",
      held["import"] == [200, None] and all(x[1] == 0 for c in held["companies"].values() for x in c["items"]), held["import"])
d = copy.deepcopy(data)
for x in d["checklist"]:
    x["system"] = 1
src.write_text(json.dumps(d), encoding="utf-8")
held = probe(src)
check("a file can make built in only the items of a company's list in the code",
      held["import"] == [200, None] and all(x[1] == 0 for x in held["companies"][frozen_code]["items"]
                                            if x[0] not in {y[0] for y in rules.CHECKLIST[frozen_code]})
      and all(x[1] == 0 for x in held["companies"]["EXT"]["items"])
      and all(x[1] == 1 for x in held["companies"][seeded_code]["items"]), held["import"])

# ---------- 10. a copy replaces only an untouched starter checklist; titles are checked over the months each is in use ----------
# A copy replaces a checklist only while it is the starter list as given and no month is set up (section 4). A
# checklist with the company's own items, or a starter item reworded, is kept: as before Phase 7, the copy is refused
# when the company has items in force in the month it starts, and otherwise adds to them.
con = db.connect()
try:
    con.arm("seed", "test: companies from seed.json")
    db.load_seed(con, {"entities": [{"code": x, "name": f"Example {x} Sdn Bhd"} for x in ("EXQ", "EXR", "EXS", "EXK", "EXL")]})
    con.commit()
finally:
    con.disarm()
    con.close()
ents = {e["code"]: e["id"] for e in j("get", "/api/meta")["entities"]}
exq, exr, exs = ents["EXQ"], ents["EXR"], ents["EXS"]
P = j("get", f"/api/setup/checklist?entity={exs}")["default_from"]
P1, P2, P3, P4 = (db.shift_month(P, k) for k in (1, 2, 3, 4))


def save(entity_id, action, month, expect=200, **kw):
    r = call("post", "/api/setup/checklist", json={"action": action, "entity_id": entity_id, "from_month": month, **kw})
    assert expect is None or r.status_code == expect, (action, month, r.status_code, r.data[:300])
    return r


def titles(entity_id, month):
    with db.connect() as r:
        checklistbook.forget(r)
        return sorted(i["title"] for i in checklistbook.get(r).checklist({"id": entity_id}, month))


SRC = save(exs, "add", P, fields={**hand, "title": "Example Source task"}).get_json()["item_id"]
OWN = "Example Own task"
save(exq, "add", P2, fields={**hand, "title": OWN})
v = j("get", f"/api/setup/checklist?entity={exq}")
check("a company from seed.json with only its own item is not a starter checklist a copy may replace", v["replaceable"] is False, v)
save(exq, "copy", P, copy_from=exs)
check("a copy into it from before its own item starts adds to it: its own item stays",
      titles(exq, P) == ["Example Source task"] and titles(exq, P2) == sorted(["Example Source task", OWN]), titles(exq, P2))

ext2 = j("post", "/api/setup/entities", json={"fields": {"code": "EXU", "name": "Example Untouched Sdn Bhd"}, "reason": "test"})["id"]
ext3 = j("post", "/api/setup/entities", json={"fields": {"code": "EXV", "name": "Example Reworded Sdn Bhd"}, "reason": "test"})["id"]
ext4 = j("post", "/api/setup/entities", json={"fields": {"code": "EXW", "name": "Example Added To Sdn Bhd"}, "reason": "test"})["id"]
first = j("get", f"/api/setup/checklist?entity={ext3}")["items"][0]
save(ext3, "change", P, item_id=first["id"], fields={**first["now"], "title": "Example reworded task"})
save(ext4, "add", P, fields={**hand, "title": "Example Charlie own"})
views = {e: j("get", f"/api/setup/checklist?entity={e}") for e in (ext2, ext3, ext4)}
check("an untouched starter checklist may still be replaced; one reworded or added to may not",
      [views[e]["replaceable"] for e in (ext2, ext3, ext4)] == [True, False, False], [views[e]["replaceable"] for e in views])
for e in (ext3, ext4):
    r = save(e, "copy", P, expect=None, copy_from=exs)
    check(f"a copy over a starter checklist {'reworded' if e == ext3 else 'added to'} is refused, the list kept as it was",
          r.status_code == 400 and "already has a checklist" in r.get_json()["error"]
          and [i["code"] for i in j("get", f"/api/setup/checklist?entity={e}")["items"]] == [i["code"] for i in views[e]["items"]],
          r.get_json())
save(ext2, "copy", P, copy_from=exs)
check("a copy over the untouched starter checklist replaces it",
      [i["code"] for i in j("get", f"/api/setup/checklist?entity={ext2}")["items"]] == ["example-source-task"])

# A Xray from P, then Yankee from P4; B takes Xray from P4. A may change in the months before P4, and be used again,
# keeping Xray: it is Xray only until P4.
XRAY, YANKEE, ZULU = "Example Xray task", "Example Yankee task", "Example Zulu task"
a = save(exr, "add", P, fields={**hand, "title": XRAY}).get_json()["item_id"]
save(exr, "change", P4, item_id=a, fields={**hand, "title": YANKEE})
save(exr, "add", P4, fields={**hand, "title": XRAY})
r = save(exr, "change", P1, expect=None, item_id=a, fields={**hand, "title": XRAY, "due_day": 9})
check("an item may be changed, keeping its title, in the months before another item takes that title", r.status_code == 200, r.data[:300])
save(exr, "stop", P1, item_id=a, reason="test")
r = save(exr, "use", P2, expect=None, item_id=a, reason="test")
check("and used again then too", r.status_code == 200, r.data[:300])
save(exr, "add", P, fields={**hand, "title": ZULU})
r = save(exr, "change", P2, expect=None, item_id=a, fields={**hand, "title": ZULU})
check("a title in use by another item over the same months is still refused, in Setup's words",
      r.status_code == 400 and r.get_json()["error"] == f"Another item in use is called {ZULU}. Give this one another title.", r.data[:300])

# Use again puts the changes planned later in use too: each title is checked over its own months.
ALT, LATER = "Example Victor task", "Example Whiskey task"
v2 = save(exr, "add", P, fields={**hand, "title": ALT}).get_json()["item_id"]
save(exr, "change", P4, item_id=v2, fields={**hand, "title": LATER})
save(exr, "stop", P1, item_id=v2, reason="test")
save(exr, "add", P4, fields={**hand, "title": LATER})
r = save(exr, "use", P2, expect=None, item_id=v2, reason="test")
check("using an item again is refused when a change planned later would bring a title another item has then",
      r.status_code == 400 and r.get_json()["error"] == f"Another item in use is called {LATER}. Give this one another title."
      and titles(exr, P4).count(LATER) == 1, (r.data[:300], titles(exr, P4)))

# A copy that adds to a checklist: each copied title is checked against the company's other items in use.
KILO, LIMA = "Example Kilo task", "Example Lima task"
exk, target = ents["EXK"], ents["EXL"]  # from seed.json: no checklist
kilo = save(exk, "add", P, fields={**hand, "title": KILO}).get_json()["item_id"]
save(exk, "change", P1, item_id=kilo, fields={**hand, "title": LIMA})
save(target, "add", P3, fields={**hand, "title": LIMA})  # its own example-lima-task from P3
before = q("SELECT COUNT(*) AS n FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?)", (target,))
r = save(target, "copy", P1, expect=None, copy_from=exk)
check("a copy bringing a title another of the company's items has then is refused whole, in Setup's words",
      r.status_code == 400 and r.get_json()["error"] == f"Another item in use is called {LIMA}. Give this one another title."
      and q("SELECT COUNT(*) AS n FROM checklist_terms WHERE item_id IN (SELECT id FROM checklist_items WHERE entity_id = ?)",
            (target,)) == before, r.data[:300])
save(target, "add", P4, fields={**hand, "title": KILO})  # its own example-kilo-task from P4: the copy writes over it until then
r = save(target, "copy", P, expect=None, copy_from=exk)
check("a copy from a month where the titles don't meet goes ahead; the company's own item of the same code doesn't count",
      r.status_code == 200 and titles(target, P) == [KILO] and titles(target, P4) == sorted([KILO, LIMA]), (r.data[:300], titles(target, P4)))
with db.connect() as r:
    check("the trail checks out after the copies and title checks", audit.verify(r)["ok"])

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
