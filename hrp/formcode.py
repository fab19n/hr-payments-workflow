"""The code, keyed check and QR printed on a form the app prints for a person to sign (the bank reconciliation
statement now; approval forms later).

- The code names the form: what it is, the month, the company and the account, e.g. BR-2610-ABC-0123 for a bank
  reconciliation statement (BR), October 2026, company ABC, the account whose number ends 0123. The company part is the
  company's own code from Setup, never a fixed one.
- The keyed check is worked out from the code and every figure printed on the form, with a key kept in the records
  (form_keys, update 41). A copy whose figures were changed no longer matches, and nobody can work out a matching check
  without the key. Two forms with the same figures give the same check.
- The key is made the first time a form is printed (key(con, make=True)), and that is written to the activity log. It
  is never copied into the audit trail (audit.SKIP) or a Move setup file (setupfile.export leaves it out; load never
  reads one: the file can't name the table).
- The QR holds the code and the check, as a PNG made by segno, for a phone to read.
"""
import base64
import hashlib
import hmac
import io
import re
import secrets

from . import db

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a check typed from paper reads back
KEY_TABLE = "form_keys"


class NoKey(LookupError):
    """No form has been printed yet, so there is no key to check against."""


def ready(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (KEY_TABLE,)).fetchone() is not None


def key(con, make=False):
    """The key the checks are worked out with (bytes). make: create it when there is none yet (the first form printed),
    writing that to the activity log; the caller commits. Without make, NoKey when there is none."""
    if not ready(con):
        raise NoKey("The records need update 41 for printed forms. Restart the app.")
    row = con.execute(f"SELECT secret FROM {KEY_TABLE} WHERE id = 1").fetchone()
    if row:
        return base64.b64decode(row["secret"])
    if not make:
        raise NoKey("No form has been printed here yet, so there is nothing to check against.")
    return _create(con)


def _create(con):
    """Makes the key, unless another print made it meanwhile (two first prints at once): then that one is used."""
    raw = secrets.token_bytes(32)
    # Two first prints at once: the one whose key went in first wins, and the other reads that key back.
    made = con.execute(f"INSERT OR IGNORE INTO {KEY_TABLE} (id, secret, created_at) VALUES (1, ?, ?)",
                       (base64.b64encode(raw).decode(), db.now())).rowcount
    if made == 1:
        db.log(con, "Made the key the printed forms' checks are worked out with (first form printed). It is kept in the "
                    "records only: not in the audit trail, backups' setup files or exports.")
    return base64.b64decode(con.execute(f"SELECT secret FROM {KEY_TABLE} WHERE id = 1").fetchone()["secret"])


def made_at(con):
    """When the key was made, or None."""
    if not ready(con):
        return None
    row = con.execute(f"SELECT created_at FROM {KEY_TABLE} WHERE id = 1").fetchone()
    return row["created_at"] if row else None


def account_digits(number, fallback):
    """The last 4 digits of an account number; fallback (the account's id, padded) when it holds fewer than 4 digits."""
    d = re.sub(r"\D", "", number or "")
    return d[-4:] if len(d) >= 4 else f"{int(fallback):04d}"[-4:]


def code(kind, month, company_code, account_number=None, account_id=0):
    """A form's code: kind (BR for a bank reconciliation statement), the month as yymm, the company's code and the last 4
    digits of the account number, e.g. BR-2610-ABC-0123."""
    comp = re.sub(r"[^A-Z0-9]", "", str(company_code or "").upper()) or "CO"
    return f"{kind}-{month[2:4]}{month[5:7]}-{comp}-{account_digits(account_number, account_id)}"


def _canon(figures):
    """The printed figures as one text: each a string, in order; a number as it prints with two decimals."""
    out = []
    for f in figures:
        if isinstance(f, bool) or f is None:
            out.append("" if f is None else str(f))
        elif isinstance(f, (int, float)):
            out.append(f"{round(float(f), 2):.2f}")
        else:
            out.append(str(f).strip())
    return "\x1f".join(out)


def check(con, form_code, figures, make=False):
    """The keyed check of a form: 7 letters and digits as XXX-XXXX, worked out from its code and figures with the key.
    make: create the key when there is none (printing a form)."""
    mac = hmac.new(key(con, make), (form_code + "\x1e" + _canon(figures)).encode("utf-8"), hashlib.sha256).digest()
    n = int.from_bytes(mac[:8], "big")
    chars = []
    for _ in range(7):
        n, r = divmod(n, len(ALPHABET))
        chars.append(ALPHABET[r])
    s = "".join(chars)
    return f"{s[:3]}-{s[3:]}"


def verify(con, form_code, figures, given):
    """True when the check typed or read from a form (given) is the one its code and figures give."""
    try:
        want = check(con, form_code, figures)
    except NoKey:
        return False
    norm = lambda s: re.sub(r"[^A-Z0-9]", "", str(s or "").upper())
    return hmac.compare_digest(norm(want), norm(given))


def qr_text(form_code, form_check):
    return f"{form_code}|{form_check}"


def qr_png(form_code, form_check, scale=6):
    """The QR of a form (its code and check) as PNG bytes."""
    import segno
    buf = io.BytesIO()
    segno.make(qr_text(form_code, form_check), error="m").save(buf, kind="png", scale=scale, border=1)
    return buf.getvalue()
