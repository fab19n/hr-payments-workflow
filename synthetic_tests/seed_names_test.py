"""seed.json's names for the placeholders (rules.PLACEHOLDERS), on made-up records.

A new install from a seed.json whose companies have the per-code lists gets the names written in (checklistbook.
fill_names) and kept for this install (checklistbook.NAMES_KEY), not shown in General settings and not carried by a
setup file. Update 21's check reads the code's lists with those names, so running the updates again on these records
(as an older records.db being brought up to date does) reads back the same, every row kept. Without names nothing is
kept and the placeholders stay.
Run: .venv\\Scripts\\python -m synthetic_tests.seed_names_test
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-seed-names-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)
NO_NAMES = sys.argv[1:2] == ["--no-names"]  # the same install, from a seed.json without names

import hrp  # noqa: E402
from hrp import audit, checklistbook, config, db, rules  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

passed = []


def check(name, ok, detail=""):
    if not ok:
        raise AssertionError(f"{name}: {detail}")
    passed.append(name)
    print("PASS", name)


NAMES = {rules.PLACEHOLDERS[0]: "Example Sister Bhd", rules.PLACEHOLDERS[1]: "Example \"Tenant\" & Co"}
codes = list(rules.CHECKLIST)
seed = {"entities": [{"code": codes[0], "name": "Example One Sdn Bhd"}, {"code": codes[1], "name": "Example Sister Bhd"},
                     {"code": "EXN", "name": "Example Other Ltd"}]}
if not NO_NAMES:
    seed["names"] = NAMES
(tmp / "seed.json").write_text(json.dumps(seed), encoding="utf-8")
db.init()


def q(sql, args=()):
    con = db.connect()
    try:
        return [tuple(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def held():
    return " ".join(str(v) for t, c, _ in checklistbook.NAME_COLUMNS for (v,) in q(f"SELECT {c} FROM {t}"))


def tables():
    con = db.connect()
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'audit_%' "
                                           "AND name NOT IN ('activity', 'sqlite_sequence') ORDER BY name")]
        return {t: [tuple(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in names}
    finally:
        con.close()


con = db.connect()
kept = checklistbook.stored_names(con)
con.close()
if NO_NAMES:
    check("without names, nothing is kept and the placeholders stay",
          kept == {} and rules.PLACEHOLDERS[0] in held() and rules.PLACEHOLDERS[1].upper() in held())
else:
    check("the names are written in and kept for this install", kept == NAMES and not any(p.lower() in held().lower()
                                                                                         for p in rules.PLACEHOLDERS), kept)
    client = app.test_client()
    settings = client.get("/api/setup/settings").get_json()
    check("General settings doesn't show them", checklistbook.NAMES_KEY not in json.dumps(settings))
    exported = client.get("/api/setup/export?what=template").get_data(as_text=True)
    check("a setup file doesn't carry them", checklistbook.NAMES_KEY not in exported and "Example Sister" not in exported)
    check("read with them, the code's lists are what the install holds",
          checklistbook.named(checklistbook.FROZEN.checklist({"id": 2, "code": codes[1]}, "2026-01"), kept)[0]["title"]
          == q("SELECT title FROM checklist_terms t JOIN checklist_items i ON i.id = t.item_id WHERE i.entity_id = 2 "
               "ORDER BY t.sort LIMIT 1")[0][0])

# Running the updates again from before update 21 (an older records.db being brought up to date): update 21's check
# reads the same, and every row is kept.
before = tables()
con = sqlite3.connect(config.DB_PATH)
con.execute("PRAGMA user_version = 20")
con.commit()
con.close()
db.init()
after = tables()
check("the updates run again from update 21 without stopping", q("PRAGMA user_version")[0][0] == len(db.MIGRATIONS))
check("every row is kept", {t: r for t, r in after.items() if t != "app_settings"} == {t: r for t, r in before.items() if t != "app_settings"}
      and set(after["app_settings"]) >= set(before["app_settings"]))
con = db.connect()
check("the trail checks out", audit.verify(con)["ok"])
con.close()

# The same install from a seed.json without names, in a process of its own
if not NO_NAMES:
    import subprocess
    run = subprocess.run([sys.executable, "-m", "synthetic_tests.seed_names_test", "--no-names"], capture_output=True, text=True,
                         cwd=Path(__file__).resolve().parent.parent, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
    print("\n".join("  " + x for x in run.stdout.strip().splitlines()))
    check("and from a seed.json without names", run.returncode == 0, run.stderr[-2000:])

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
