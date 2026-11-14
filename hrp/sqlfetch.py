"""One click for every SQL Account export waiting in a folder.

SQL Account on SQL Connect can only hand its data out as files the person exports (print button > Export to Microsoft
Excel Workbook, saved in SQL Drive > Download, which the browser downloads). Those files arrive with any name (1.xlsx),
so they are told apart by what they hold: every workbook in the folder is opened, the SQL listings among them are read,
and their documents are put together, each one once, marked new or already imported. SQL's general-ledger reports (the
GL Journal of Transaction, the GL Ledger and the Trial Balance, read by hrp/sqlgl.py) are taken in the same way and
handed back whole, for their account lines and their checks (hrp/ledger.py).

Nothing in the folder is moved, renamed or deleted. A file is left out the next time once it has been imported (its
fingerprint is among the company's stored SQL exports); a listing of another company is never taken.
"""
import csv
import hashlib
import io
import re
from datetime import datetime
from pathlib import Path

from . import sqlimport, sqlreport

EXTENSIONS = (".xlsx", ".xlsm")
MAX_BYTES = 10 * 1024 * 1024   # a listing is a few hundred KB; a larger workbook is something else
MAX_FILES = 500                # the newest ones, so a crowded Downloads folder stays quick


class FetchError(sqlimport.SqlImportError):
    pass


def default_folder():
    return str(Path.home() / "Downloads")


def folder_of(settings):
    """Where exports are looked for: the folder saved in settings.json, else the person's Downloads folder."""
    return (settings.get("sql_exports_dir") or "").strip() or default_folder()


def _key(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def owner(entities, company):
    """The company a listing's company line names (SQL prints "NAME SDN BHD (new reg no (old reg no))"): the one whose
    registration number is in the line, else the one with the longest name in it, else None."""
    line = _key(company)
    best = None
    for e in entities:
        reg, name = _key(e["reg_no"] if "reg_no" in e.keys() else ""), _key(e["name"])
        if len(reg) >= 6 and reg in line:
            return e
        if len(name) >= 4 and name in line and (best is None or len(name) > len(_key(best["name"]))):
            best = e
    return best


def _files(folder):
    p = Path(folder)
    if not p.is_dir():
        raise FetchError(f"The folder {folder} can't be found. Choose the folder your SQL exports are saved in.")
    try:
        found = [(f, f.stat()) for f in p.iterdir() if f.suffix.lower() in EXTENSIONS and not f.name.startswith("~$") and f.is_file()]
    except OSError as ex:
        raise FetchError(f"The folder {folder} can't be read: {ex}")
    found.sort(key=lambda x: (-x[1].st_mtime, x[0].name.lower()))  # newest first: its wording wins for a document in two files
    return found[:MAX_FILES]


def gather(con, entity_id, folder):
    """Every SQL listing and general-ledger report in the folder for this company, put together.

    Returns {folder, files, other, entries, new, already, csv, sources, gl}:
      files    what was found, newest first: {name, saved, status, reason, title, period, entries, new, already, repeated};
               a general-ledger report has report (its kind) and docs and lines (a journal) or accounts instead of entries
               status: read | imported_before | copy | other_company | unknown_company | unreadable
      other    how many workbooks are not SQL listings or reports (left alone)
      entries, new, already   the documents in the listings read, each counted once
      csv      those documents as one table (sqlimport reads it like a pasted listing), new ones first; None when there are none
      sources  [(name, data, month)] of the listings read, to keep with the import
      gl       [{name, sha, data, saved, kind, rep, month}] of the general-ledger reports read ('journal', 'gl_ledger' or
               'trial_balance', rep as hrp/sqlgl.py reads it), month the file's latest date as YYYY-MM
    """
    ents = con.execute("SELECT * FROM entities").fetchall()
    me = next(e for e in ents if e["id"] == int(entity_id))
    sql_users = [e for e in ents if e["uses_sql"] and ("active" not in e.keys() or e["active"])]
    imported = {r[0] for r in con.execute("SELECT sha256 FROM documents WHERE entity_id = ? AND doc_type = 'sqlexport'", (me["id"],))}

    files, sources, entries, seen, by_sha, other, gl = [], [], [], {}, {}, 0, []
    for path, st in _files(folder):
        info = {"name": path.name, "saved": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), "status": "read", "reason": ""}
        if st.st_size > MAX_BYTES:
            other += 1
            continue
        try:
            data = path.read_bytes()
        except OSError:
            files.append({**info, "status": "unreadable", "reason": "This file couldn't be opened. Close it if it is open in Excel, then fetch again."})
            continue
        sha = hashlib.sha256(data).hexdigest()
        if sha in imported:
            files.append({**info, "status": "imported_before", "reason": "Imported before."})
            continue
        if sha in by_sha:
            files.append({**info, "status": "copy", "reason": f"A copy of {by_sha[sha]}."})
            continue
        try:
            got = sqlreport.read(data)
        except sqlreport.ReportError as ex:  # refused whole and not kept, so the next fetch reads it again
            files.append({**info, "status": "unreadable", "reason": str(ex)})
            continue
        if got is None:
            other += 1
            continue
        kind, rep = got
        by_sha[sha] = path.name
        info.update(title=rep["title"], period=rep["period"], company=rep["company"])
        own = owner(ents, rep["company"])
        if own is not None and own["id"] != me["id"]:
            files.append({**info, "status": "other_company", "reason": f"This {rep['title']} is for {own['code']} ({own['name']}), not {me['code']}."})
            continue
        if own is None and not (len(sql_users) == 1 and sql_users[0]["id"] == me["id"]):
            files.append({**info, "status": "unknown_company",
                          "reason": f"This {rep['title']} is for \"{rep['company']}\", which matches no company's name or registration number in Setup, "
                                    "so it was left out. Correct the company's name or registration number in Setup › Companies, then fetch again."})
            continue
        if kind != "listing":
            month = _latest(kind, rep)
            if not month:
                files.append({**info, "status": "unreadable", "reason": f"This {rep['title']} has no dates in it, so there is nothing to keep."})
                continue
            info["report"] = kind
            if kind == "journal":
                info.update(docs=len(rep["docs"]), lines=sum(len(d["lines"]) for d in rep["docs"]), period_source=rep.get("period_source"))
            else:
                info.update(accounts=len(rep["accounts"]))
            files.append(info)
            gl.append({"name": path.name, "sha": sha, "data": data, "saved": info["saved"], "kind": kind, "rep": rep, "month": month})
            continue
        new = already = repeated = 0
        for e in rep["entries"]:
            key = (e["doc_no"].upper(), e["date"], round(abs(e["amount"]), 2))
            if key in seen:  # in a listing read already: that one is kept, with whatever only this one says
                repeated += 1
                for field in ("description", "payee", "code", "cheque_no"):
                    seen[key][field] = seen[key][field] or e[field]
                continue
            exists = bool(con.execute("SELECT 1 FROM sql_entries WHERE entity_id = ? AND doc_no = ? AND doc_date = ? AND amount = ?",
                                      (me["id"], e["doc_no"], e["date"], round(abs(e["amount"]), 2))).fetchone())
            new, already = new + (not exists), already + exists
            seen[key] = {**e, "exists": exists}
            entries.append(seen[key])
        files.append({**info, "entries": len(rep["entries"]), "new": new, "already": already, "repeated": repeated})
        if rep["entries"]:
            sources.append((path.name, data, max(e["date"] for e in rep["entries"])[:7]))

    entries.sort(key=lambda e: (e["exists"], e["date"], e["doc_no"]))  # what is new comes first
    table = None
    if entries:
        out = io.StringIO()
        clean = lambda v: re.sub(r"[\t\r\n]+", " ", v) if isinstance(v, str) else v  # a tab would make it read as pasted text
        csv.writer(out, lineterminator="\n").writerows([clean(v) for v in row] for row in sqlimport.listing_rows(entries))
        table = out.getvalue().encode("utf-8")
    return {"folder": str(Path(folder)), "files": files, "other": other, "entries": len(entries),
            "new": sum(1 for e in entries if not e["exists"]), "already": sum(1 for e in entries if e["exists"]),
            "csv": table, "sources": sources, "gl": gl}


def _latest(kind, rep):
    """The month (YYYY-MM) of a general-ledger report's latest date: the end of its period (a trial balance's as-at
    date), else its latest line. None when it has no date at all."""
    period = rep.get("period") or [None, None]
    dates = [str(period[1])] if period[1] else []
    if kind == "journal":
        dates += [d["date"] for d in rep["docs"] if d.get("date")]
    elif kind == "gl_ledger":
        dates += [r["date"] for a in rep["accounts"] for r in a["rows"] + a["virtual"] if r.get("date")]
    return max(dates)[:7] if dates else None
