"""Setup phase 7, part 4, on made-up records only: Check this pack.

A pack built records in its trail event what built it (the program's commit and files' fingerprint, Python, fpdf2 and
pypdf, the day its statuses were worked out on, and the Generated line, trail entry and check code printed on its
cover), beside its file, fingerprint and size. Check this pack then says whether the file is still the one built
(unchanged, changed, missing, or built before the trail recorded packs) and what changed since in what the pack reads,
for its company and month only, grouped and counted, with what it can't tell. Checking writes nothing.

Run: .venv\\Scripts\\python -m synthetic_tests.pack_check_test
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-pack-check-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

import hrp  # noqa: E402
from hrp import audit, auditpack, config, db  # noqa: E402
from hrp.app import app  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
assert hrp.config.DATA_DIR == Path(os.environ["HRP_DATA_DIR"])

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXH", "name": "Example Holdings Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111"}]},
    {"code": "EXI", "name": "Example International Ltd", "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")
db.init()

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


def a_pdf(text):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, text)
    return bytes(pdf.output())


def upload(pid, name, text):
    return j("post", "/api/upload", data={"file": (io.BytesIO(a_pdf(text)), name), "doc_type": "invoice", "payment_id": str(pid)},
             content_type="multipart/form-data")["id"]


def pack_check(**args):
    return j("get", "/api/audit-pack/check?" + "&".join(f"{k}={v}" for k, v in args.items()))


def group(r, key):
    return next((g for g in r["changes"]["groups"] if g["key"] == key), None)


# ---------- some made-up records ----------
for e in (1, 2):
    for m in ("2026-10", "2026-11"):
        j("post", "/api/months/open", json={"entity_id": e, "month": m, "auto": True})
pid = j("post", "/api/payments", json={"entity_id": 1, "month": "2026-10", "description": "Printer toner", "amount": 120})["id"]
did = upload(pid, "toner-invoice.pdf", "Invoice from Acme Paper Trading")
other_month = j("post", "/api/payments", json={"entity_id": 1, "month": "2026-11", "description": "Paper", "amount": 40})["id"]
other_company = j("post", "/api/payments", json={"entity_id": 2, "month": "2026-10", "description": "Pens", "amount": 15})["id"]

# ---------- a pack built records what built it ----------
r = call("post", "/api/audit-pack", json={"entity_id": 1, "month": "2026-10"})
check("a pack builds on made-up records", r.status_code == 200, r.data[:300])
name = r.get_json()["name"]
ev = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
d = json.loads(ev["after"])
tx = q("SELECT * FROM audit_tx WHERE token = ?", (ev["token"],))[0]
prev = q("SELECT * FROM audit_tx WHERE id = ?", (tx["id"] - 1,))[0]
check("the pack's event keeps the file, its fingerprint and size",
      d["company"] == "EXH" and d["month"] == "2026-10" and d["file"] == name and d["size"] > 0
      and d["sha256"] == audit.file_sha256(tmp / "audit-packs" / "EXH" / name), d)
prog = auditpack.program()
check("and what built it: the program's files' fingerprint and commit, Python, fpdf2 and pypdf",
      d["code_files"] and len(d["code_files"]) == 64 and "code_commit" in d and d["code_commit"] == prog["code_commit"]
      and d["fpdf2"] and d["pypdf"] and d["python"] and {k: d[k] for k in prog} == prog, d)
from pypdf import PdfReader  # noqa: E402
cover = PdfReader(tmp / "audit-packs" / "EXH" / name).pages[0].extract_text()
check("the day its statuses were worked out on, and the Generated line, trail entry and check code on its cover",
      d["today"] == date.today().isoformat() and re.fullmatch(r"\d\d \w{3} \d{4} \d\d:\d\d", d["generated"])
      and f"Generated {d['generated']}" in cover and d["trail_entry"] == prev["id"] == tx["id"] - 1
      and d["check_code"] == prev["hash"][:8] and f"Audit trail entry {d['trail_entry']}" in cover and d["check_code"] in cover,
      (d, cover[:300]))
check("the trail shows the new details in words", all(
    f["label"] != f["name"].capitalize() for f in j("get", f"/api/audit/tx/{tx['id']}")["changes"][-1]["fields"]
    if f["name"] in ("sha256", "code_files", "trail_entry", "generated", "today")))

# ---------- right after: nothing changed ----------
packs = j("get", "/api/audit-packs?entity=1&month=2026-10")
check("the month's packs name their trail row for Check this pack",
      len(packs) == 1 and packs[0]["name"] == name and packs[0]["event"] == ev["id"] and packs[0]["url"] and not packs[0]["missing"], packs)
tx_n = n_tx()
r1 = pack_check(event=ev["id"])
check("the file is the one built", r1["file"]["state"] == "unchanged" and r1["recorded"], r1["file"])
check("nothing it reads has changed since", r1["changes"]["total"] == 0 and r1["changes"]["groups"] == []
      and r1["changes"]["summary"].startswith("Nothing"), r1["changes"])
check("the same program built it, and what was printed is the recorded one",
      r1["pack"]["same_program"] is True and r1["pack"]["printed"]["trail_entry"] == d["trail_entry"]
      and not r1["pack"]["printed"]["worked_out"] and r1["pack"]["entry"] == tx["id"], r1["pack"])
check("it says it can't tell whether the PDF would come out differently",
      r1["cannot_tell"][0].startswith("Whether the PDF would come out differently") and not any("updated" in x for x in r1["cannot_tell"]))
check("its documents' files check out", r1["documents"] == {"checked": 1, "problems": []}, r1["documents"])
r1b = pack_check(entity=1, month="2026-10", file=name.replace(" ", "%20").replace("(", "%28").replace(")", "%29"))
check("found the same by company, month and file name", r1b == r1)
check("checking writes nothing to the trail", n_tx() == tx_n)

# ---------- changes after it ----------
j("patch", f"/api/payments/{pid}", json={"amount": 135.5, "notes": "Two boxes"})
upload(pid, "toner-receipt.pdf", "Receipt")
j("post", f"/api/documents/{did}/remove", json={})
j("patch", f"/api/payments/{other_month}", json={"amount": 41})     # another month: not the pack's
j("patch", f"/api/payments/{other_company}", json={"amount": 16})   # another company: not the pack's
j("patch", "/api/setup/settings", json={"values": {"soon_days": 7}, "reason": "test: a general setting"})
r2 = pack_check(event=ev["id"])
pays, docs = group(r2, "payments"), group(r2, "documents")
check("a payment changed since shows, with its fields before and after",
      pays and pays["count"] == 1 and pays["rows"][0]["op"] == "update"
      and {f["name"]: (f["before"], f["after"]) for f in pays["rows"][0]["fields"]}.get("amount") == (120, 135.5), pays)
check("documents added and removed since show", docs and docs["count"] == 2
      and [x["op"] for x in docs["rows"]] == ["insert", "update"], docs)
check("another month's and another company's payments don't",
      all(x["key"] == str(pid) for x in pays["rows"]))
check("a general setting changed shows", group(r2, "types") and group(r2, "types")["count"] >= 1, r2["changes"])
check("the summary counts them by kind", r2["changes"]["total"] == 3 + group(r2, "types")["count"]
      and "1 to payments" in r2["changes"]["summary"] and "2 to documents" in r2["changes"]["summary"], r2["changes"]["summary"])
row = pays["rows"][0]
entry = q("SELECT * FROM audit_tx WHERE id = ?", (row["entry"],))
check("each change names its trail entry, who made it and the entry's headline",
      entry and row["actor"] == entry[0]["actor"] and row["headline"] and row["source_label"] and not row["outside"], row)
check("the file is still the one built", r2["file"]["state"] == "unchanged")

# a change made outside the app
with sqlite3.connect(config.DB_PATH) as raw:
    raw.execute("UPDATE payments SET notes = 'Edited elsewhere' WHERE id = ?", (pid,))
r3 = pack_check(event=ev["id"])
out = [x for x in group(r3, "payments")["rows"] if x["outside"]]
check("a change made outside the app shows, marked as such, with a note on its date",
      len(out) == 1 and out[0]["source_label"] == "Outside this app, not accepted yet" and r3["changes"]["outside"] == 1
      and any("outside this app" in x for x in r3["cannot_tell"]), out)

# ---------- built again ----------
r = call("post", "/api/audit-pack", json={"entity_id": 1, "month": "2026-10"})
r4 = pack_check(event=ev["id"])
check("a later pack of the month shows under packs built since, and isn't counted as a change",
      r.status_code == 200 and r4["changes"]["packs_since"] == 1 and group(r4, "packs")["count"] == 1
      and r4["changes"]["total"] == r3["changes"]["total"] and "built 1 more time" in r4["changes"]["summary"], r4["changes"])
ev2 = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
check("the later pack has nothing changed since it", pack_check(event=ev2["id"])["changes"]["total"] == 0)

# ---------- the file altered, then gone ----------
f1 = tmp / "audit-packs" / "EXH" / name
os.chmod(f1, 0o666)
with open(f1, "ab") as f:
    f.write(b"\n% edited\n")
check("a file altered after it was built: changed", pack_check(event=ev["id"])["file"]["state"] == "changed")
f1.unlink()
r5 = pack_check(event=ev["id"])
check("a file deleted: missing, and the trail still has it", r5["file"]["state"] == "missing" and r5["pack"]["sha256"] == d["sha256"])
packs = j("get", "/api/audit-packs?entity=1&month=2026-10")
gone = next((p for p in packs if p["name"] == name), None)
check("the month's packs still list it, as missing, with no link", gone and gone["missing"] and gone["url"] is None
      and gone["event"] == ev["id"], packs)

# ---------- packs the trail didn't record ----------
old = tmp / "audit-packs" / "EXH" / "Audit pack EXH 2026-10 (20261001-0900).pdf"
shutil.copyfile(tmp / "audit-packs" / "EXH" / ev2["row_key"], old)
packs = j("get", "/api/audit-packs?entity=1&month=2026-10")
check("a pack file with no trail event is listed with no trail row", any(p["name"] == old.name and p["event"] is None for p in packs))
r6 = pack_check(entity=1, month="2026-10", file=old.name.replace(" ", "%20").replace("(", "%28").replace(")", "%29"))
check("checked by its file: built before the trail recorded packs, counted from its time on disk",
      r6["file"]["state"] == "not_recorded" and not r6["recorded"]
      and any("before the audit trail recorded packs" in x for x in r6["cannot_tell"]), r6["cannot_tell"])
with db.connect() as con:  # an event as packs were recorded before this phase: no details of what built it
    con.arm("user", "POST /api/audit-pack", entity_id=1)
    audit.event(con, "pack", "Audit pack EXH 2026-10 (20261002-0900).pdf",
                {"company": "EXH", "month": "2026-10", "file": "Audit pack EXH 2026-10 (20261002-0900).pdf", "sha256": "0" * 64, "size": 1},
                entity_id=1)
    con.commit()
ev3 = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
tx3 = q("SELECT * FROM audit_tx WHERE token = ?", (ev3["token"],))[0]
r7 = pack_check(event=ev3["id"])
check("a pack recorded before this phase: the trail entry on its cover is worked out, the program unknown",
      r7["pack"]["printed"]["worked_out"] and r7["pack"]["printed"]["trail_entry"] == tx3["id"] - 1
      and r7["pack"]["same_program"] is None and any("which version of the program" in x for x in r7["cannot_tell"])
      and r7["file"]["state"] == "missing", r7["pack"])

# ---------- the program updated since ----------
auditpack._PROGRAM["code_files"] = "f" * 64
try:
    r8 = pack_check(event=ev2["id"])
finally:
    auditpack._PROGRAM = None
    auditpack.program()
check("a pack built by another version of the program says a rebuild could differ",
      r8["pack"]["same_program"] is False and any("The program has been updated" in x for x in r8["cannot_tell"]), r8["cannot_tell"])

# ---------- refused ----------
check("a file name with a path is refused", call("get", "/api/audit-pack/check?entity=1&month=2026-10&file=..%2F..%2Frecords.db").status_code == 404)
check("an event that isn't a pack is refused", call("get", f"/api/audit-pack/check?event={pays['rows'][0]['id']}").status_code == 404)
check("an event that isn't a number is refused", call("get", "/api/audit-pack/check?event=abc").status_code == 404)
check("an event id too large for the records, or of digits that aren't 0-9, is refused the same",
      [call("get", f"/api/audit-pack/check?event={v}").status_code for v in ("99999999999999999999", "%C2%B2", "%D9%A3")] == [404] * 3)

# ---------- the auditor package records it too ----------
r = call("post", "/api/auditor-export", json={"entity_id": 1, "month": "2026-10"})
evp = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
dp = json.loads(evp["after"])
check("a pack built for the auditor package records what built it as well",
      r.status_code == 200 and dp["via"] == "auditor package" and dp["code_files"] == auditpack.program()["code_files"]
      and dp["trail_entry"] and dp["generated"] and pack_check(event=evp["id"])["file"]["state"] == "unchanged", dp)

# ---------- the auditor package's event names the pack it built, not the newest file on disk ----------
import zipfile  # noqa: E402
ahead = tmp / "audit-packs" / "EXH" / dp["file"]
later = ahead.stat().st_mtime + 3600  # as if copied from a PC whose clock ran ahead
os.utime(ahead, (later, later))
r = call("post", "/api/auditor-export", json={"entity_id": 1, "month": "2026-10"})
evq = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]
dq = json.loads(evq["after"])
with zipfile.ZipFile(config.EXPORTS_DIR / "EXH" / r.get_json()["name"]) as z:
    in_zip = [n for n in z.namelist() if n.startswith("Audit pack ")]
check("with an older pack's time on disk later, the package's event still names the pack it built",
      r.status_code == 200 and in_zip == [dq["file"]] and dq["file"] != dp["file"]
      and dq["sha256"] == audit.file_sha256(tmp / "audit-packs" / "EXH" / dq["file"]), (in_zip, dq["file"], dp["file"]))
packs = j("get", "/api/audit-packs?entity=1&month=2026-10")
by_name = {p["name"]: p["event"] for p in packs}
check("and the month's packs give each pack its own event",
      by_name.get(dp["file"]) == evp["id"] and by_name.get(dq["file"]) == evq["id"]
      and len([x for x in by_name.values() if x]) == len({x for x in by_name.values() if x}), packs)

# ---------- another month's payment paid in this month ----------
early = j("post", "/api/payments", json={"entity_id": 1, "month": "2026-11", "description": "Paper, paid early", "amount": 30,
                                         "paid_date": "2026-10-20"})["id"]
evs = {}
for m in ("2026-10", "2026-11"):
    assert call("post", "/api/audit-pack", json={"entity_id": 1, "month": m}).status_code == 200
    evs[m] = q("SELECT * FROM audit_row WHERE tbl = 'pack' AND op = 'event' ORDER BY id DESC LIMIT 1")[0]["id"]
upload(early, "paper-invoice.pdf", "Invoice from Example Stationers")
j("patch", f"/api/payments/{early}", json={"notes": "Ordered early"})
oct_, nov = pack_check(event=evs["2026-10"]), pack_check(event=evs["2026-11"])
check("a document and a note on another month's payment paid in this month aren't changes to this month's pack",
      oct_["changes"]["total"] == 0 and not group(oct_, "documents") and not group(oct_, "payments"), oct_["changes"])
check("but are to that payment's own month's pack",
      group(nov, "documents") and group(nov, "documents")["count"] == 1 and group(nov, "payments")
      and group(nov, "payments")["count"] == 1, nov["changes"])
j("patch", f"/api/payments/{early}", json={"amount": 32})
oct_ = pack_check(event=evs["2026-10"])
check("a change the bank reconciliation reads on it is",
      group(oct_, "payments") and group(oct_, "payments")["count"] == 1 and oct_["changes"]["total"] == 1, oct_["changes"])
j("patch", f"/api/payments/{early}", json={"sql_ref": "PV2610-001"})
oct_ = pack_check(event=evs["2026-10"])
check("and so is its SQL voucher number, which the pack's note on a payment paid with no bank line prints",
      group(oct_, "payments") and oct_["changes"]["total"] == 2, oct_["changes"])

# ---------- what built a pack never stops the app starting ----------
fake = Path(tempfile.mkdtemp(prefix="hrp-pack-check-git-"))
(fake / ".git").write_bytes(b"gitdir: wt\0\0\0\0")  # zero-filled after a crash
real_dir, real_git = auditpack.PROGRAM_DIR, auditpack._git_commit
auditpack.PROGRAM_DIR = fake
try:
    no_commit = auditpack._git_commit()
    auditpack._git_commit = lambda: 1 / 0
    prog_now = auditpack._program()
finally:
    auditpack.PROGRAM_DIR, auditpack._git_commit = real_dir, real_git
check("a damaged worktree .git file gives no commit instead of an error", no_commit is None)
check("and any failure finding the commit leaves it unknown, never stops a pack",
      prog_now["code_commit"] is None and prog_now["python"], prog_now)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
