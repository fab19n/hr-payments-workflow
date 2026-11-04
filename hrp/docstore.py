"""Stores uploaded documents on disk as read-only files, with a fingerprint (SHA-256) so later changes can be detected.

Layout:  documents/<ENTITY>/<YYYY-MM>/<folder>/<doc-type> - <original name>
"""
import hashlib
import os
import re
import stat
from pathlib import Path

from .config import DOCS_DIR
from .db import now

ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".ods", ".csv", ".docx", ".doc", ".txt", ".xml", ".eml", ".msg"}


def safe(name, limit=80):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:limit]
    return name.rstrip(" .") or "file"  # again after the cut: Windows drops a trailing space or dot from a folder name


def store(con, *, entity, month, folder, doc_type, filename, data, payment_id=None, task_id=None, statement_id=None, note=None):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError(f"{ext or 'This file type'} isn't accepted. Upload a PDF, image, Excel, Word or email file.")
    digest = hashlib.sha256(data).hexdigest()
    target_dir = DOCS_DIR / entity["code"] / month / safe(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    base = f"{doc_type} - {safe(Path(filename).stem, 60)}"
    target = target_dir / f"{base}{ext}"
    n = 2
    while target.exists():
        target = target_dir / f"{base} ({n}){ext}"
        n += 1
    target.write_bytes(data)
    os.chmod(target, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)  # read-only: evidence is never edited in place
    cur = con.execute(
        """INSERT INTO documents (payment_id, task_id, statement_id, entity_id, month, doc_type, original_name, stored_path,
           sha256, size, uploaded_at, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (payment_id, task_id, statement_id, entity["id"], month, doc_type, filename,
         str(target.relative_to(DOCS_DIR)), digest, len(data), now(), note))
    return cur.lastrowid


def path_of(doc):
    return DOCS_DIR / doc["stored_path"]


def verify(doc):
    """True when the file on disk still matches the fingerprint taken at upload."""
    p = path_of(doc)
    return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == doc["sha256"]
