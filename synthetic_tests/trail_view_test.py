"""The audit trail page's server side, on made-up records only: entries, filters and paging, an entry's changes, a
record's history, masking, logged reads, the full check with its replay, the Excel export, the check code on audit pack
covers and the manifest in backups.

Run: .venv\\Scripts\\python -m synthetic_tests.trail_view_test
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-trail-view-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import audit, auditread, config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "AISB", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-2222"}],
     "payees": [{"name": "Staff One", "category": "salary", "amount": 3000, "due_day": 26, "bank_details": "Example Bank 9876543210"}]},
    {"code": "AI", "name": "Example International Ltd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")
db.init()

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


client = app.test_client()
BASE = f"http://127.0.0.1:{config.SETTINGS['port']}"
H = {"X-HRP": "1"}


def call(method, path, expect=200, headers=None, **kw):
    r = getattr(client, method)(BASE + path, headers={**H, **(headers or {})}, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:300])
    return r


def j(method, path, expect=200, **kw):
    return call(method, path, expect, **kw).get_json()


# ---------- some work in the app ----------
j("post", "/api/months/open", json={"entity_id": 1, "month": "2026-10", "auto": True})
pid = j("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "Printer toner", "amount": 120})["id"]
j("patch", f"/api/payments/{pid}", json={"amount": 135.5, "notes": "Two boxes"})
for i in range(55):  # enough entries for a second page
    j("patch", f"/api/payments/{pid}", json={"notes": f"Note {i}"})
inj = j("post", "/api/payments", json={"entity_id": 2, "month": "2026-10", "description": "=HYPERLINK(\"http://x\")", "amount": 1})["id"]

# ---------- entries, filters, paging ----------
page = j("get", "/api/audit")
check("entries come newest first, 50 to a page, with more to come", len(page["entries"]) == 50 and page["more"]
      and page["entries"][0]["id"] > page["entries"][-1]["id"])
check("the browser gets the names of record types and sources from the server",
      page["labels"]["tables"]["payments"] == "Payment" and page["labels"]["sources"]["auto"] == "Automatic")
nxt = j("get", f"/api/audit?before_id={page['entries'][-1]['id']}")
check("the next page carries on below the last entry", nxt["entries"][0]["id"] < page["entries"][-1]["id"])
added = j("get", "/api/audit?q=added+toner")["entries"]  # every word must match
check("search finds the entry that added a payment by a word in it", any("Added payment: Printer toner" in e["headline"] for e in added),
      [e["headline"] for e in added])
check("filters by source", all(e["source"] == "auto" for e in j("get", "/api/audit?source=auto")["entries"]))
check("filters by company", all(e["company"] in ("AI", None) for e in j("get", "/api/audit?entity_id=2")["entries"])
      and any(e["company"] == "AI" for e in j("get", "/api/audit?entity_id=2")["entries"]))
check("filters by kind of record", j("get", "/api/audit?tbl=months")["entries"] and
      all("months" in e["counts"] for e in j("get", "/api/audit?tbl=months")["entries"]))
check("a bad filter is refused with a message", "source" in j("get", "/api/audit?source=hacker", 400)["error"])

# ---------- one entry, one record's history ----------
edit = next(e for e in j("get", "/api/audit?q=amount+toner&tbl=payments")["entries"] if "amount" in json.dumps(j("get", f"/api/audit/tx/{e['id']}")))
d = j("get", f"/api/audit/tx/{edit['id']}")
amount = next(f for ch in d["changes"] if ch["table"] == "payments" for f in ch["fields"] if f["name"] == "amount")
check("an entry shows each changed field before and after", (amount["label"], amount["before"], amount["after"]) == ("Amount", 120, 135.5), amount)
h = j("get", f"/api/audit/record/payments/{pid}")
check("a payment's history runs newest first, back to when it was added", h["changes"][0]["op"] == "update"
      and h["changes"][-1]["op"] == "insert" and len(h["changes"]) == 57, [c["op"] for c in h["changes"]][:3])
check("an unknown kind of record is refused", "record" in j("get", "/api/audit/record/sqlite_master/1", 404)["error"])
base = j("get", "/api/audit/record/payees/1")["changes"]
bank = next(f for f in base[-1]["fields"] if f["name"] == "bank_details")
check("bank details are masked unless asked for", bank["after"] == "••••3210", bank)
shown = next(f for f in j("get", "/api/audit/record/payees/1?show=1")["changes"][-1]["fields"] if f["name"] == "bank_details")
check("and shown with show=1", shown["after"] == "Example Bank 9876543210")

# ---------- logged reads ----------
n_reads = lambda: sqlite3.connect(config.DB_PATH).execute("SELECT COUNT(*) FROM audit_row WHERE tbl = 'read'").fetchone()[0]
before = n_reads()
call("get", "/api/export/month.xlsx?entity_id=1&month=2026-10", headers={"Sec-Fetch-Site": "same-origin"})
check("a download from the app itself is recorded as opened", n_reads() == before + 1)
call("get", "/api/export/month.xlsx?entity_id=1&month=2026-10", headers={"Sec-Fetch-Site": "cross-site"})
check("a download another website triggers is not recorded (it can't fill the trail)", n_reads() == before + 1)
gets = {r.rule: getattr(app.view_functions[r.endpoint], "audited_read", None) for r in app.url_map.iter_rules() if "GET" in r.methods}
files = {rule for rule in gets if rule.endswith("/file") or rule.endswith(".xlsx")}
check("every route that hands over a file records it", files and all(gets[r] for r in files), {r: gets[r] for r in files})

# ---------- the full check and its replay ----------
r = j("post", "/api/audit/check", json={})
check("the full check passes on records the app alone changed", r["ok"] and r["replay"]["count"] == 0 and r["replay"]["checked"] > 0, r)
raw = sqlite3.connect(config.DB_PATH)
raw.execute("DROP TRIGGER audit_payments_u")
raw.execute("UPDATE payments SET amount = 999 WHERE id = ?", (pid,))  # not recorded: the trigger is gone
raw.commit()
raw.close()
db.init()  # puts the trigger back (the window warns); the edit itself left no row
r = j("post", "/api/audit/check", json={})
check("the replay finds a record changed while its trigger was missing", not r["ok"] and any(
    p["table"] == "payments" and p["key"] == str(pid) and "Amount" in p["problem"] for p in r["replay"]["problems"]), r["replay"])
st = j("get", "/api/audit/status")
check("the status shows the last full check found problems", st["last_full_check"]["ok"] is False)
o = j("get", "/api/audit/outside")
check("a record that differs from the trail waits to be accepted like an outside change",
      o["total"] == 1 and o["changes"][0]["table"] == "payments" and any(f["name"] == "amount" and f["after"] == 999 for f in o["changes"][0]["fields"]), o)
h = j("get", f"/api/audit/record/payments/{pid}")["changes"][0]
check("and shows in the record's history, not accepted yet", h["source_label"].startswith("Outside this app") and h["op"] == "update", h)
r = j("post", "/api/audit/check", json={})
check("checking again doesn't record the same difference twice", j("get", "/api/audit/outside")["total"] == 1 and r["replay"]["count"] == 0)
check("a full check reads as words in the list", j("get", "/api/audit")["entries"][0]["headline"].startswith("Checked the audit trail"))

# ---------- accepting only what was shown ----------
raw = sqlite3.connect(config.DB_PATH)
raw.execute("UPDATE payees SET notes = 'second outside edit' WHERE id = 1")
raw.commit()
raw.close()
shown_upto = o["upto_id"]  # the page was opened before the second edit arrived
a = j("post", "/api/audit/accept-outside", json={"reason": "Checked the amount with the bank", "upto_id": shown_upto})
left = j("get", "/api/audit/outside")
check("Accept seals only up to the last change shown; one that arrived since still waits", a["accepted"] == 1 and left["total"] == 1
      and left["changes"][0]["table"] == "payees", (a, left["total"]))
j("post", "/api/audit/accept-outside", json={"reason": "Note added in DB Browser", "upto_id": left["upto_id"]})
acc = j("get", "/api/audit?tbl=payments&source=outside")["entries"]
check("an accepted outside change is found by the record-type filter", acc and acc[0]["reason"] == "Checked the amount with the bank", acc)
check("and by search", any(e["reason"] == "Checked the amount with the bank" for e in j("get", "/api/audit?q=999")["entries"]))

# ---------- many outside changes stay quick, and the index of them can't hide one ----------
import time  # noqa: E402
raw = sqlite3.connect(config.DB_PATH)
raw.executemany("UPDATE payments SET notes = ? WHERE id = ?", [(f"bulk {i}", pid) for i in range(3000)])
raw.commit()
raw.close()
o = j("get", "/api/audit/outside")
check("a large outside change is listed in part, with its true total", o["total"] == 3000 and len(o["changes"]) == auditread.OUTSIDE_SHOWN, (o["total"], len(o["changes"])))
while o["total"]:
    j("post", "/api/audit/accept-outside", json={"reason": "Bulk fix in a script", "upto_id": o["upto_id"]})
    o = j("get", "/api/audit/outside")
t0 = time.perf_counter()
j("get", "/api/audit/status?quick=1")
quick = time.perf_counter() - t0
check("the Overview's quick status stays quick after thousands of accepted changes", quick < 0.5, f"{quick:.2f} s")
raw = sqlite3.connect(config.DB_PATH)
raw.execute("UPDATE payees SET notes = 'hidden edit' WHERE id = 1")
hid = raw.execute("SELECT MAX(id) FROM audit_row").fetchone()[0]
raw.execute("INSERT INTO audit_sealed (row_id, tx_id) VALUES (?, 1)", (hid,))  # slipped into the index to hide it
raw.commit()
raw.close()
with db.connect() as c:
    v = audit.verify(c)
check("a row slipped into the index of accepted changes is reported by the check", any("index of accepted" in p for p in v["problems"]), v["problems"])

# ---------- Excel export ----------
from openpyxl import load_workbook  # noqa: E402
x = call("get", "/api/audit/export.xlsx?q=HYPERLINK", headers={"Sec-Fetch-Site": "same-origin"})
ws = load_workbook(io.BytesIO(x.data)).active
rows = list(ws.values)
check("the export has the columns and a row per field changed", list(rows[0]) == auditread.EXPORT_HEAD and len(rows) > 1)
cells = [c for row in ws.iter_rows(min_row=2) for c in row if isinstance(c.value, str) and c.value.startswith("=")]
check("a value that looks like a formula is kept as it is and stored as text", cells and all(c.data_type == "s" for c in cells),
      [(c.value, c.data_type) for c in cells])
check("empty cells stay empty (no stray apostrophes)", not any(c == "'" for row in rows for c in row))
j("post", "/api/payees", json={"entity_id": 1, "name": "Vendor\x0bTab", "category": "utility", "amount": 10, "due_day": 5})
x = call("get", "/api/audit/export.xlsx", headers={"Sec-Fetch-Site": "same-origin"})
check("a control character in a value doesn't break the export", x.status_code == 200 and load_workbook(io.BytesIO(x.data)).active.max_row > 1)
with db.connect() as c:
    _, cut = auditread.export_rows(c, {}, cap=3)
check("an export cut at its cap says so", cut is True)

# ---------- check code on an audit pack, manifest in a backup ----------
r = client.post(BASE + "/api/audit-pack", headers=H, json={"entity_id": 1, "month": "2026-10"})
if r.status_code == 200:
    from pypdf import PdfReader  # noqa: E402
    pack = next((tmp / "audit-packs" / "AISB").glob("*.pdf"))
    text = PdfReader(pack).pages[0].extract_text()
    check("an audit pack's cover carries the trail's check code", "check code" in text and "Audit trail entry" in text, text[:300])
else:
    print(f"SKIP pack cover: the pack could not be built here ({r.get_json().get('error')})")
z = Path(j("post", "/api/backup", json={})["file"])
with zipfile.ZipFile(z) as zf:
    man = json.loads(zf.read("manifest.json"))
    import hashlib  # noqa: E402
    sha = hashlib.sha256(zf.read("records.db")).hexdigest()
with sqlite3.connect(config.DB_PATH) as c:
    last_before_backup = c.execute("SELECT id, hash FROM audit_tx WHERE id = ?", (man["audit_trail"]["last_entry"],)).fetchone()
check("a backup holds a manifest naming the trail's last entry and the records' fingerprint",
      man["records_sha256"] == sha and last_before_backup and last_before_backup[1] == man["audit_trail"]["hash"], man)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
