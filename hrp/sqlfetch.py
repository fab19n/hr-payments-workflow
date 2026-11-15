"""One click for every SQL Account export waiting in a folder.

SQL Account on SQL Connect can only hand its data out as files the person exports (print button > Export to Microsoft
Excel Workbook, saved in SQL Drive > Download, which the browser downloads). Those files arrive with any name (1.xlsx),
so they are told apart by what they hold: every workbook in the folder is opened, the SQL listings among them are read,
and their documents are put together, each one once, marked new or already imported. SQL's general-ledger reports (the
GL Journal of Transaction, the GL Ledger and the Trial Balance, read by hrp/sqlgl.py) are taken in the same way and
handed back whole, for their account lines and their checks (hrp/ledger.py).

A copy of SQL's MyInvois Transaction grid, saved from Excel, is read too (hrp/myinvois.py): it is the company's whose
TIN it holds. Nothing in the folder is moved, renamed or deleted. A file is left out the next time once it has been imported (its
fingerprint is among the company's stored SQL exports); a listing of another company is never taken, and one whose
printed company matches no company in Setup only once the owner has said whose it is (Take it for, take_for).
"""
import csv
import hashlib
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from . import myinvois, sqlimport, sqlreport

EXTENSIONS = (".xlsx", ".xlsm")
MAX_BYTES = sqlreport.MAX_BYTES  # a larger workbook is not read (one from SQL is named as too large)
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


def names_ready(con):
    """Whether the records have update 36 (the company names the owner confirmed)."""
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sql_company_names'").fetchone())


def confirmed_names(con):
    """{printed company name, as a key: company id} for the names the owner said are one of the companies."""
    if not names_ready(con):
        return {}
    return {r["name_key"]: r["entity_id"] for r in con.execute("SELECT name_key, entity_id FROM sql_company_names")}


def take_for(con, entity_id, company):
    """Keeps a company name SQL printed on an export, that matches no company in Setup, as this company's, because the
    owner clicked Take it for on the fetch's list: the next fetch takes exports printed with it for this company (and
    for no other). Refused, with a sentence, for an empty name, a name that already matches a company, or one already
    taken for another company. Logged in the activity log; the audit trail keeps the row."""
    from .db import log, now
    if not names_ready(con):
        raise FetchError("The records need update 36 to take an export for a company. Restart the app.")
    ents = con.execute("SELECT * FROM entities").fetchall()
    me = next((e for e in ents if e["id"] == int(entity_id)), None)
    name = re.sub(r"\s+", " ", str(company or "")).strip()
    key = _key(name)
    if me is None or not me["uses_sql"]:
        raise FetchError("Only a company kept in SQL Account can take SQL's exports.")
    if not key:
        raise FetchError("This export prints no company name, so it can't be taken for a company.")
    own = owner(ents, name)
    if own is not None:
        raise FetchError(f"\"{name}\" already matches {own['code']} in Setup, so there is nothing to confirm.")
    had = confirmed_names(con).get(key)
    if had is not None:
        if had == me["id"]:
            return False
        other = next((e for e in ents if e["id"] == had), None)
        raise FetchError(f"\"{name}\" was taken for {other['code'] if other else 'another company'} before. "
                         "Check which company the export is from in SQL Account.")
    con.execute("INSERT INTO sql_company_names (entity_id, name_key, name, confirmed_at) VALUES (?, ?, ?, ?)",
                (me["id"], key, name, now()))
    log(con, f"Took SQL's exports printed for \"{name}\" as {me['code']}'s ({me['name']}): the company name matches none "
             "in Setup, and the owner confirmed it")
    return True


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


# The titles SQL Account prints on the listings and general-ledger reports this app reads.
SQL_TITLES = tuple(sqlreport.LISTINGS) + ("gl journal of transaction", "gl ledger", "trial balance")
PEEK = 256 * 1024  # how much of a large workbook's text is looked at to tell whether SQL Account wrote it


def _from_sql(path):
    """Whether a workbook looks like one SQL Account exported, read cheaply without unpacking it whole: its workbook part
    has the attribute SQL Account writes (WindowWidth, which Excel spells windowWidth), or the start of its text names a
    report title this app reads."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "xl/workbook.xml" in names and z.getinfo("xl/workbook.xml").file_size <= PEEK:
                if b"WindowWidth=" in z.read("xl/workbook.xml"):
                    return True
            if "xl/sharedStrings.xml" in names:
                with z.open("xl/sharedStrings.xml") as f:
                    text = f.read(PEEK).decode("utf-8", "ignore").lower()
                return any(t in text for t in SQL_TITLES)
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return False
    return False


def gather(con, entity_id, folder):
    """Every SQL listing and general-ledger report in the folder for this company, put together.

    Returns {folder, files, other, entries, new, already, csv, sources, gl}:
      files    what was found, newest first: {name, saved, status, reason, title, period, entries, new, already, repeated};
               a general-ledger report has report (its kind) and docs and lines (a journal) or accounts instead of entries
               status: read | imported_before | copy | other_company | unknown_company | unreadable | too_large
               an unknown_company file whose printed company can be confirmed has take_for (this company's code)
      other    how many workbooks are not SQL listings or reports (left alone)
      entries, new, already   the documents in the listings read, each counted once
      csv      those documents as one table (sqlimport reads it like a pasted listing), new ones first; None when there are none
      sources  [(name, data, month)] of the listings read, to keep with the import
      gl       [{name, sha, data, saved, kind, rep, month}] of the general-ledger reports read ('journal', 'gl_ledger' or
               'trial_balance', rep as hrp/sqlgl.py reads it), month the file's latest date as YYYY-MM
      myinvois [{name, sha, data, saved, rep, month}] of the copies of SQL's MyInvois Transaction grid read (rep as
               hrp/myinvois.py reads it); in files each has report 'myinvois' and what keeping it would do (new,
               changed, unchanged, older, and how many were issued, self-billed and received)
    """
    ents = con.execute("SELECT * FROM entities").fetchall()
    me = next(e for e in ents if e["id"] == int(entity_id))
    confirmed = confirmed_names(con)
    can_confirm = names_ready(con) and bool(me["uses_sql"])
    imported = {r[0] for r in con.execute("SELECT sha256 FROM documents WHERE entity_id = ? AND doc_type = 'sqlexport'", (me["id"],))}

    files, sources, entries, seen, by_sha, other, gl, mi = [], [], [], {}, {}, 0, [], []
    for path, st in _files(folder):
        info = {"name": path.name, "saved": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), "status": "read", "reason": ""}
        if st.st_size > MAX_BYTES:
            # An SQL report too large to read is named, so it isn't missed without a word; any other large workbook (a
            # budget saved in Downloads) is left alone, as one that is no listing.
            if _from_sql(path):
                files.append({**info, "status": "too_large", "reason": f"too large to read ({st.st_size / 1024 / 1024:.1f} MB; "
                                                                         f"at most {MAX_BYTES // (1024 * 1024)} MB). Export a shorter period."})
            else:
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
        if kind == "myinvois":
            # A copy of the MyInvois grid names no company: it is the one whose TIN is the supplier's or buyer's in it.
            # A company without its TIN in Setup can't be told, so the copy is never taken on a guess.
            own = myinvois.owner(ents, rep)
            if own is not None and own["id"] != me["id"]:
                files.append({**info, "status": "other_company", "reason": f"This MyInvois copy is for {own['code']} ({own['name']}), not {me['code']}."})
            elif own is None:
                files.append({**info, "status": "unknown_company",
                              "reason": f"This MyInvois copy has no e-Invoice whose supplier or buyer TIN is {me['code']}'s"
                                        + ("" if (me["tin"] if "tin" in me.keys() else None) else " (its TIN isn't in Setup yet)")
                                        + ", so it was left out. Enter the company's TIN in Setup › Companies, then fetch again."})
            elif not myinvois.ready(con):
                files.append({**info, "status": "unreadable", "reason": "The records need update 33 to keep MyInvois copies. Restart the app, then fetch again."})
            else:
                info.update(report="myinvois", **myinvois.compare(con, me["id"], rep, info["saved"]))
                files.append(info)
                mi.append({"name": path.name, "sha": sha, "data": data, "saved": info["saved"], "rep": rep,
                           "month": (rep["period"] or [None, info["saved"][:10]])[1][:7]})
            continue
        own = owner(ents, rep["company"])
        if own is None and _key(rep["company"]) in confirmed:  # a printed name the owner said is this company's (Take it for)
            own = next((e for e in ents if e["id"] == confirmed[_key(rep["company"])]), None)
        if own is not None and own["id"] != me["id"]:
            files.append({**info, "status": "other_company", "reason": f"This {rep['title']} is for {own['code']} ({own['name']}), not {me['code']}."})
            continue
        if own is None:
            # Never taken on a guess, even when only one company is kept in SQL: nothing from it is read until the owner
            # says whose it is (Take it for ..., which keeps the printed name with that company for later fetches).
            if not _key(rep["company"]):
                files.append({**info, "status": "unknown_company",
                              "reason": f"This {rep['title']} prints no company name, so whose it is can't be told and nothing "
                                        "was taken from it. Export it again from SQL Account with the company name on it."})
            else:
                files.append({**info, "status": "unknown_company", "take_for": me["code"] if can_confirm else None,
                              "reason": f"This {rep['title']} is from a company not in Setup: \"{rep['company']}\" matches no "
                                        "company's name or registration number in Setup, so nothing was taken from it. "
                                        + (f"If it is {me['code']}'s, click Take it for {me['code']}; otherwise correct the "
                                           "company's name or registration number in Setup › Companies, then fetch again."
                                           if can_confirm else "Correct the company's name or registration number in Setup › "
                                                               "Companies, then fetch again.")})
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
            "csv": table, "sources": sources, "gl": gl, "myinvois": mi}


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
