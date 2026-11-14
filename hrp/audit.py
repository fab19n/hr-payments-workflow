"""The audit trail: every change to the records, captured by SQLite triggers in the same save as the change.

How it fits together:
- Each audited table has generated AFTER INSERT/UPDATE/DELETE triggers that write the whole row, before and after, as
  JSON into audit_row. They fire for every write, whatever code makes it, so nothing can be left out by forgetting to log.
- Who, why and from where come from the app: a connection is "armed" (Connection.arm) with a token, which it puts in the
  one-row audit_context table; the triggers copy that token onto every row they write.
- At commit, the connection seals the transaction's rows into one audit_tx entry whose hash covers those rows and the
  previous entry's hash (a hash chain), so an entry changed afterwards no longer checks out. audit_row, audit_tx and the
  activity log refuse UPDATE and DELETE.
- Rows written with no token (another program editing records.db) stay unsealed and are reported as changes made
  outside this app until someone accepts them with a reason. Rows the app wrote without arming are sealed as
  unattributed app writes.
- audit-head.json, beside records.db, keeps the last entry's number and hash. A records.db that is behind it (restored
  from a backup, or entries removed) or whose entry at that number has another hash (the chain rebuilt) is recorded in
  the trail as an event, so the next save can't erase the finding.

What this does not stop: someone with the file and the skill can drop the triggers, rebuild a consistent chain and
rewrite the head file too. Printed check codes on audit packs and the copies in off-PC backups (later phases) are the
checks for that.

Update steps (db.MIGRATIONS) after 17: the triggers are refreshed after every step and after db.add_column, so a step
that adds a column and fills it is captured. A step that creates a table and fills it must call refresh(con) between
the two (else the rows are recorded as a baseline once the step ends). A step that drops a column or rebuilds a table
must call drop_triggers(con) first; a step must not DROP TABLE on records without deleting the rows first (so the trail
keeps them).
"""
import getpass
import hashlib
import json
import os
import re
import socket
import sqlite3
import uuid
from datetime import datetime

from .config import DATA_DIR

GENESIS = "0" * 64
HEAD_FILE = DATA_DIR / "audit-head.json"
CTX = "(SELECT token FROM audit_context WHERE only = 1)"
SKIP = ("audit_row", "audit_tx", "audit_context", "audit_sealed")  # the audit store itself
APPEND_ONLY = ("audit_row", "audit_tx", "activity", "audit_sealed", "ledger_lines")
# Tables whose rows belong to a company through a parent row (the rest have entity_id, or are entities themselves).
ENTITY_VIA = {
    "advances": "(SELECT entity_id FROM payees WHERE id = {X}.payee_id)",
    "statements": "(SELECT entity_id FROM accounts WHERE id = {X}.account_id)",
    "statement_lines": "(SELECT a.entity_id FROM statements s JOIN accounts a ON a.id = s.account_id WHERE s.id = {X}.statement_id)",
    "book_openings": "(SELECT entity_id FROM accounts WHERE id = {X}.account_id)",
}

STORE = """
CREATE TABLE IF NOT EXISTS audit_row (
  id INTEGER PRIMARY KEY,
  token TEXT,
  at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now', 'localtime')),
  tbl TEXT NOT NULL,
  row_key TEXT NOT NULL,
  op TEXT NOT NULL CHECK (op IN ('insert', 'update', 'delete', 'baseline', 'event')),
  entity_id INTEGER,
  before TEXT CHECK (before IS NULL OR json_valid(before)),
  after TEXT CHECK (after IS NULL OR json_valid(after))
);
CREATE TABLE IF NOT EXISTS audit_tx (
  id INTEGER PRIMARY KEY,
  token TEXT NOT NULL UNIQUE,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  machine TEXT,
  source TEXT NOT NULL CHECK (source IN ('user', 'auto', 'import', 'migration', 'seed', 'system', 'outside')),
  action TEXT NOT NULL,
  route TEXT,
  entity_id INTEGER,
  reason TEXT,
  summary TEXT,
  counts TEXT CHECK (counts IS NULL OR json_valid(counts)),
  null_rows TEXT CHECK (null_rows IS NULL OR json_valid(null_rows)),  -- ids of token-less rows this entry seals
  late INTEGER NOT NULL DEFAULT 0,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_context (only INTEGER PRIMARY KEY CHECK (only = 1), token TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_sealed (row_id INTEGER PRIMARY KEY, tx_id INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS audit_row_rec ON audit_row (tbl, row_key, id);
CREATE INDEX IF NOT EXISTS audit_row_token ON audit_row (token);
CREATE INDEX IF NOT EXISTS audit_row_entity ON audit_row (entity_id, id);
CREATE INDEX IF NOT EXISTS audit_row_null ON audit_row (id) WHERE token IS NULL;
CREATE INDEX IF NOT EXISTS audit_tx_at ON audit_tx (at);
"""

_WHO = None


def who():
    """(Windows user, PC name) the app runs as: what 'Made by' records until there is a sign-in."""
    global _WHO
    if _WHO is None:
        try:
            user = getpass.getuser()
        except Exception:
            user = "unknown"
        _WHO = (user, socket.gethostname())
    return _WHO


def stamp():
    return datetime.now().isoformat(timespec="milliseconds")


def present(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'audit_context'").fetchone() is not None


def started(con):
    """Capture is on (update 17 has run): the capture triggers exist. Not "a baseline exists", as a records.db that was
    empty when the trail started has none."""
    return present(con) and con.execute(
        r"SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit\_%\_i' ESCAPE '\'").fetchone() is not None


# ---------- the connection ----------

class Connection(sqlite3.Connection):
    """A records.db connection that attributes and seals what it writes. db.connect() returns one."""

    ctx = None          # who, why and from where for the transaction in progress; None until arm()
    _mark = 0           # highest audit_row id when this connection last started or committed (see _seal_unattributed)
    _audit = False      # the audit store exists in this records.db (cached once true)
    _head = None        # the head entry to write to HEAD_FILE once the commit succeeds
    _head_noted = False  # a disagreement with the head file was already recorded on this connection

    def audited(self):
        if not self._audit:
            self._audit = present(self)
        return self._audit

    def mark(self):
        if self.audited():
            self._mark = self.execute("SELECT COALESCE(MAX(id), 0) FROM audit_row").fetchone()[0]

    def arm(self, source, action, route=None, entity_id=None, reason=None):
        """Says who is changing the records, how and why, for every row written until the next commit (and, with the
        same details under a new token, after it). What was already written under an earlier arm keeps that one: it is
        sealed first. Does nothing before the audit store exists (old update steps)."""
        if not self.audited():
            self.ctx = None
            return
        if self.in_transaction:
            seal(self)
        user, machine = who()
        self.ctx = {"source": source, "action": action, "route": route, "entity_id": entity_id,
                    "reason": reason, "actor": user, "machine": machine}
        self._put_token()

    def _put_token(self):
        self.ctx["token"] = uuid.uuid4().hex
        self.execute("INSERT INTO audit_context (only, token) VALUES (1, ?) ON CONFLICT (only) DO UPDATE SET token = excluded.token",
                     (self.ctx["token"],))

    def _after_commit(self):
        if self._head:
            write_head(self._head)
            self._head = None
        self.mark()
        if self.ctx:  # later writes on this connection keep the same who and why, as a new entry
            self._put_token()

    def commit(self):
        if self.audited():
            seal(self)
        super().commit()
        self._after_commit()

    def executescript(self, script):
        # executescript commits whatever is pending before it runs, outside commit(): seal first, so the context row is
        # never committed (a committed one would lend the app's token to another program's edits).
        if self.audited() and self.in_transaction:
            seal(self)
        cur = super().executescript(script)
        self._after_commit()
        return cur

    def __exit__(self, kind, value, tb):
        # `with con:` commits in C, past commit(); route it through commit()/rollback() so the seal still happens.
        if kind is None:
            self.commit()
        else:
            self.rollback()
        # The block is over: drop the fresh context commit()/rollback() put in, or the still-open connection would hold
        # records.db's write lock and every other writer would wait for it.
        self.disarm()
        return False

    def disarm(self):
        """Stops attributing writes; call right after commit (it drops the fresh, still empty transaction)."""
        self.ctx = None
        if self.in_transaction:
            super().rollback()

    def rollback(self):
        super().rollback()
        self._head = None
        if self.ctx and self.audited():
            self._put_token()


# ---------- capture: generated triggers ----------

def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _lit(text):
    return "'" + text.replace("'", "''") + "'"


def _slug(table):
    """A trigger-name-safe form of a table name (the app's own names are already safe and stay as they are)."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", table)
    return s if s == table else f"{s}_{hashlib.sha1(table.encode('utf-8')).hexdigest()[:6]}"


def _columns(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({_q(table)})")]


def _key_columns(con, table):
    pk = sorted((r[5], r[1]) for r in con.execute(f"PRAGMA table_info({_q(table)})") if r[5])
    return [name for _, name in pk]


def audited_tables(con):
    return [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
            if r[0] not in SKIP]


def _exprs(con, table, X):
    """SQL for a row of table X ("NEW", "OLD" or an alias): its key, its company and its whole row as JSON."""
    cols = _columns(con, table)
    keys = _key_columns(con, table)
    if len(keys) == 1:
        key = f"CAST({X}.{_q(keys[0])} AS TEXT)"
    elif not keys:
        key = f"CAST({X}.rowid AS TEXT)"
    else:
        key = " || '|' || ".join(f"COALESCE(CAST({X}.{_q(k)} AS TEXT), '')" for k in keys)
    if table == "entities":
        ent = f"{X}.id"
    elif "entity_id" in cols:
        ent = f"{X}.entity_id"
    else:
        ent = ENTITY_VIA.get(table, "NULL").format(X=X)
    obj = "json_object(" + ", ".join(f"{_lit(c)}, {X}.{_q(c)}" for c in cols) + ")"
    return key, ent, obj


def _row_sql(table, op, key, ent, before, after):
    return (f"INSERT INTO audit_row (token, tbl, row_key, op, entity_id, before, after) "
            f"VALUES ({CTX}, {_lit(table)}, {key}, '{op}', {ent}, {before}, {after});")


def triggers(con):
    """name -> CREATE TRIGGER statement, for every audited table as its columns are now."""
    out = {}
    for t in audited_tables(con):
        s, on = _slug(t), _q(t)
        nkey, nent, nobj = _exprs(con, t, "NEW")
        okey, oent, oobj = _exprs(con, t, "OLD")
        out[f"audit_{s}_i"] = (f"CREATE TRIGGER audit_{s}_i AFTER INSERT ON {on} BEGIN "
                               + _row_sql(t, "insert", nkey, nent, "NULL", nobj) + " END")
        if t in APPEND_ONLY:
            continue
        changed = " OR ".join(f"OLD.{_q(c)} IS NOT NEW.{_q(c)}" for c in _columns(con, t))
        out[f"audit_{s}_u"] = (f"CREATE TRIGGER audit_{s}_u AFTER UPDATE ON {on} WHEN {changed} BEGIN "
                               + _row_sql(t, "update", nkey, nent, oobj, nobj) + " END")
        out[f"audit_{s}_d"] = (f"CREATE TRIGGER audit_{s}_d AFTER DELETE ON {on} BEGIN "
                               + _row_sql(t, "delete", okey, oent, oobj, "NULL") + " END")
    for t in APPEND_ONLY:
        if not _exists(con, t):  # a table a later update step creates (audit_sealed, ledger_lines) gets its guard then
            continue
        if t == "ledger_lines":
            msg = "Account lines can''t be changed: a change in SQL is kept as a new version."
        else:
            msg = ("The activity log" if t == "activity" else "The audit trail") + " can''t be changed."
        for op, word in (("u", "UPDATE"), ("d", "DELETE")):
            out[f"audit_guard_{t}_{op}"] = (f"CREATE TRIGGER audit_guard_{t}_{op} BEFORE {word} ON {_q(t)} "
                                            f"BEGIN SELECT RAISE(ABORT, '{msg}'); END")
    return out


def _exists(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None


def _have(con):
    return {r[0]: r[1] for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'audit\\_%' ESCAPE '\\'")}


def ensure_triggers(con):
    """Creates or recreates every audit trigger that is missing or differs from what the tables need now (a column
    added by an update step changes them). Returns the names it changed."""
    want, have = triggers(con), _have(con)
    changed = []
    for name in sorted(set(have) - set(want)):
        con.execute(f"DROP TRIGGER {_q(name)}")
        changed.append(name)
    for name, sql in want.items():
        if have.get(name) != sql:
            con.execute(f"DROP TRIGGER IF EXISTS {_q(name)}")
            con.execute(sql)
            changed.append(name)
    return changed


def _baseline(con, table):
    key, ent, obj = _exprs(con, table, "X")
    con.execute(f"INSERT INTO audit_row (token, tbl, row_key, op, entity_id, before, after) "
                f"SELECT {CTX}, {_lit(table)}, {key}, 'baseline', {ent}, NULL, {obj} FROM {_q(table)} AS X ORDER BY X.rowid")


def refresh(con):
    """Brings the triggers up to date with the tables after an update step changed them (db.init calls it after every
    step, db.add_column after every column added). A table that had no triggers yet and already holds rows gets a
    baseline of them. Records what changed as an event. Nothing happens before the trail has started."""
    if not started(con):
        return []
    new_tables = [t for t in audited_tables(con) if f"audit_{_slug(t)}_i" not in _have(con)]
    changed = ensure_triggers(con)
    baselined = []
    for t in new_tables:
        if t not in APPEND_ONLY or t == "activity":
            if con.execute(f"SELECT 1 FROM {_q(t)} LIMIT 1").fetchone() and not con.execute(
                    "SELECT 1 FROM audit_row WHERE tbl = ? LIMIT 1", (t,)).fetchone():
                _baseline(con, t)
                baselined.append(t)
    if changed:
        event(con, "audit", "triggers", {"updated": changed, "baselined": baselined, "why": "update step"})
    return changed


def drop_triggers(con):
    """Removes every audit trigger. SQLite refuses ALTER TABLE ... DROP COLUMN on a column a trigger names, and a table
    rebuild (CREATE new, copy, DROP, RENAME) on a table other triggers name, so an update step doing either calls this
    first; db.init refreshes them after the step, and start-up puts them back in any case."""
    for name in list(_have(con)):
        con.execute(f"DROP TRIGGER {_q(name)}")


# ---------- update steps (db.MIGRATIONS 16 and 17) ----------

def install(con):
    """Step 16: the audit store. Nothing in the records changes."""
    for stmt in STORE.split(";"):
        if stmt.strip():
            con.execute(stmt)


def sealed_index(con):
    """Step 18: an index of the token-less rows each entry seals (audit_tx.null_rows stays the record that is hashed),
    so finding the changes made outside the app stays quick however many have been accepted."""
    con.execute("CREATE TABLE IF NOT EXISTS audit_sealed (row_id INTEGER PRIMARY KEY, tx_id INTEGER NOT NULL)")
    con.execute("""INSERT OR IGNORE INTO audit_sealed (row_id, tx_id)
                   SELECT j.value, t.id FROM audit_tx t, json_each(t.null_rows) j WHERE t.null_rows IS NOT NULL""")
    ensure_triggers(con)  # its append-only guard


def start(con):
    """Step 17: triggers on every table, and one baseline row per row as the records stand, so the trail starts
    from the real records on the day it was turned on. The activity log so far is part of the baseline."""
    con.arm("migration", "Audit trail started")
    already = started(con)
    changed = ensure_triggers(con)
    if already:  # the step ran before (a records.db whose update count was set back): the trail has its start
        if changed:
            event(con, "audit", "triggers", {"updated": changed, "why": "update 17 run again"})
        return
    for t in audited_tables(con):
        _baseline(con, t)


# ---------- sealing ----------

def _canon_row(r):
    return json.dumps([r["id"], r["at"], r["token"], r["tbl"], r["row_key"], r["op"], r["entity_id"], r["before"], r["after"]],
                      ensure_ascii=False, separators=(",", ":"))


TX_FIELDS = ("token", "at", "actor", "machine", "source", "action", "route", "entity_id", "reason", "summary", "counts",
             "null_rows", "late", "prev_hash")


def _canon_tx(tx):
    return json.dumps([tx[f] for f in TX_FIELDS], ensure_ascii=False, separators=(",", ":"))


def entry_hash(prev_hash, rows, tx):
    text = prev_hash + "\n" + "\n".join(_canon_row(r) for r in rows) + "\n" + _canon_tx(tx)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(rows):
    lines = [json.loads(r["after"])["what"] for r in rows if r["tbl"] == "activity" and r["op"] == "insert"]
    counts = {}
    for r in rows:
        counts.setdefault(r["tbl"], {}).setdefault(r["op"], 0)
        counts[r["tbl"]][r["op"]] += 1
    return ("\n".join(lines) or None), json.dumps(counts, separators=(",", ":"))


def _last(con):
    r = con.execute("SELECT id, hash FROM audit_tx ORDER BY id DESC LIMIT 1").fetchone()
    return (r[0], r[1]) if r else (0, GENESIS)


UNCOVERED_LISTS = """token IS NULL AND NOT EXISTS (SELECT 1 FROM audit_tx t, json_each(t.null_rows) j
                                         WHERE t.null_rows IS NOT NULL AND j.value = audit_row.id)"""
UNCOVERED_INDEXED = "token IS NULL AND NOT EXISTS (SELECT 1 FROM audit_sealed s WHERE s.row_id = audit_row.id)"


def uncovered(con):
    """SQL for token-less rows nobody has sealed: through audit_sealed (update 18 on), else the id lists in audit_tx."""
    return UNCOVERED_INDEXED if _exists(con, "audit_sealed") else UNCOVERED_LISTS


def _add_tx(con, rows, meta, token=None, null_ids=None, late=0):
    last_id, prev = _last(con)
    summary, counts = _summary(rows)
    user, machine = who()
    if meta.get("entity_id") is None:  # a request that didn't name its company (an edit by id): the one its rows belong to
        ents = {r["entity_id"] for r in rows if r["entity_id"] is not None}
        meta = {**meta, "entity_id": ents.pop() if len(ents) == 1 else None}
    tx = {"token": token or uuid.uuid4().hex, "at": stamp(), "actor": meta.get("actor") or user,
          "machine": meta.get("machine") or machine, "source": meta["source"], "action": meta["action"],
          "route": meta.get("route"), "entity_id": meta.get("entity_id"), "reason": meta.get("reason"),
          "summary": summary, "counts": counts, "late": late, "prev_hash": prev,
          "null_rows": json.dumps(null_ids, separators=(",", ":")) if null_ids is not None else None}
    tx["hash"] = entry_hash(prev, rows, tx)
    con.execute(f"INSERT INTO audit_tx ({', '.join(TX_FIELDS)}, hash) VALUES ({', '.join('?' * (len(TX_FIELDS) + 1))})",
                [tx[f] for f in TX_FIELDS] + [tx["hash"]])
    if null_ids and _exists(con, "audit_sealed"):
        con.executemany("INSERT INTO audit_sealed (row_id, tx_id) VALUES (?, ?)", [(i, last_id + 1) for i in null_ids])
    con._head = {"last_tx": last_id + 1, "hash": tx["hash"], "at": tx["at"]}
    return tx


def _rows(con, where, args):
    con_rf, con.row_factory = con.row_factory, sqlite3.Row
    try:
        return con.execute(f"SELECT * FROM audit_row WHERE {where} ORDER BY id", args).fetchall()
    finally:
        con.row_factory = con_rf


def seal(con):
    """Turns what this transaction wrote into one audit_tx entry (called by Connection.commit, and by arm before a
    new context replaces one that already has rows)."""
    tok = con.execute("SELECT token FROM audit_context WHERE only = 1").fetchone()
    if tok:
        rows = _rows(con, "token = ?", (tok[0],))
        if rows:
            _note_head(con)
            rows = _rows(con, "token = ?", (tok[0],))
            meta = con.ctx if con.ctx and con.ctx.get("token") == tok[0] else {"source": "system", "action": "Unattributed app write"}
            _add_tx(con, rows, meta, token=tok[0])
        con.execute("DELETE FROM audit_context")
    _seal_unattributed(con)


def _seal_unattributed(con):
    """Rows written by this connection without a token (code that never armed it): sealed as the app's own, so they are
    never mistaken for a change made outside the app. Only rows above the mark taken when this connection started or
    last committed are taken, and only when this connection has written something."""
    if not con.in_transaction:
        return
    rows = _rows(con, f"id > ? AND {uncovered(con)}", (con._mark,))
    if rows:
        _add_tx(con, rows, {"source": "system", "action": "Unattributed app write"}, null_ids=[r["id"] for r in rows])


def event(con, kind, key, detail, entity_id=None):
    """Something done that is not a change to a table, such as an audit pack built, a backup made or a file exported:
    one row in the trail, sealed with the request's other changes."""
    con.execute(f"INSERT INTO audit_row (token, tbl, row_key, op, entity_id, after) VALUES ({CTX}, ?, ?, 'event', ?, ?)",
                (kind, str(key), entity_id, json.dumps(detail, ensure_ascii=False, separators=(",", ":"))))


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- the head file ----------

def write_head(head):
    tmp = HEAD_FILE.with_name(HEAD_FILE.name + ".tmp")
    try:
        tmp.write_text(json.dumps(head), encoding="utf-8")
        os.replace(tmp, HEAD_FILE)
    except OSError:
        pass  # the head file is a check from outside records.db; failing to write it never stops a save


def read_head():
    try:
        h = json.loads(HEAD_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = (isinstance(h, dict) and isinstance(h.get("last_tx"), int) and isinstance(h.get("hash"), str)
          and re.fullmatch(r"[0-9a-f]{64}", h["hash"]))
    return h if ok else None


def head_problem(con):
    """How records.db disagrees with the head file: None, or {"kind": "behind" | "rewritten", ...}. Behind: the file
    has fewer entries than were recorded (a backup restored, or entries removed). Rewritten: the entry the head file
    names has another hash (the chain was rebuilt)."""
    head = read_head()
    if not head:
        return None
    last_id, _ = _last(con)
    if head["last_tx"] > last_id:
        return {"kind": "behind", "head_last_tx": head["last_tx"], "head_hash": head["hash"], "head_at": head.get("at"),
                "records_last_tx": last_id}
    r = con.execute("SELECT hash FROM audit_tx WHERE id = ?", (head["last_tx"],)).fetchone()
    if r and r[0] != head["hash"]:
        return {"kind": "rewritten", "head_last_tx": head["last_tx"], "head_hash": head["hash"], "head_at": head.get("at"),
                "records_hash": r[0]}
    return None


def _note_head(con):
    """Records a disagreement with the head file as an event in the entry being sealed, once per connection, before
    the new entry moves the head on (which would otherwise erase the finding)."""
    if con._head_noted:
        return
    p = head_problem(con)
    if p:
        event(con, "audit", "head", p)
        con._head_noted = True


# ---------- start-up and checks ----------

def startup(con):
    """Run by db.init after the update steps. In this order: a context row left committed by an unexpected stop is
    cleared; a disagreement with the head file is recorded (before anything could be re-sealed over it); triggers that
    are missing or changed are put back and recorded; entries left unsealed are sealed, marked late. Returns status()
    plus what this start found."""
    if not present(con):
        return None
    stale = con.execute("SELECT token FROM audit_context WHERE only = 1").fetchone()
    stale = stale[0] if stale else None
    if stale:
        con.execute("DELETE FROM audit_context")
        con.commit()
    con.arm("system", "Audit capture checked")
    problem = head_problem(con)
    if problem:
        event(con, "audit", "head", problem)
        con._head_noted = True
    repaired = ensure_triggers(con)
    from . import ledger
    if ledger.ensure_guard(con):  # outside the trail's own triggers, so put back here (and checked by verify)
        repaired = repaired + ["ledger_guard_here"]
    if repaired:
        event(con, "audit", "triggers", {"updated": repaired, "why": "missing or changed at start-up"})
    late = 0
    for (tok,) in con.execute("""SELECT DISTINCT r.token FROM audit_row r WHERE r.token IS NOT NULL
                                 AND r.token IS NOT (SELECT token FROM audit_context WHERE only = 1)
                                 AND NOT EXISTS (SELECT 1 FROM audit_tx t WHERE t.token = r.token) ORDER BY r.token""").fetchall():
        action = ("Sealed after an unexpected stop; may include changes made outside this app" if tok == stale
                  else "Sealed after an unexpected stop")
        _add_tx(con, _rows(con, "token = ?", (tok,)), {"source": "system", "action": action}, token=tok, late=1)
        late += 1
    con.commit()
    con.disarm()
    return {**status(con), "head": problem, "triggers_repaired": repaired, "late_sealed": late}


def outside_rows(con):
    """Rows written by another program (no token) that nobody has accepted yet."""
    return con.execute(f"SELECT COUNT(*) FROM audit_row WHERE {uncovered(con)}").fetchone()[0]


def accept_outside(con, reason, upto=None):
    """Seals the changes made outside this app into the chain, with the reason given; with upto, only those up to that
    row (the last one the person was shown), so a change that arrived since, or wasn't on screen, is never accepted
    unseen. The rows themselves never change."""
    rows = _rows(con, uncovered(con) + (" AND id <= ?" if upto is not None else ""), (upto,) if upto is not None else ())
    if rows:
        _add_tx(con, rows, {"source": "outside", "action": "Accepted changes made outside this app", "reason": reason},
                null_ids=[r["id"] for r in rows])
    return len(rows)


def status(con):
    last_id, last_hash = _last(con)
    p = head_problem(con)
    return {"entries": last_id, "outside": outside_rows(con), "head_behind": bool(p and p["kind"] == "behind"),
            "head_rewritten": bool(p and p["kind"] == "rewritten"), "check_code": last_hash[:8] if last_id else None}


def verify(con, last=None):
    """Recomputes the hash chain (every entry, or the last n), checks the triggers and the head file. Returns
    {"ok", "checked", "problems": [...], "outside", "check_code"}."""
    problems = []
    rf, con.row_factory = con.row_factory, sqlite3.Row
    try:
        txs = con.execute("SELECT * FROM audit_tx ORDER BY id").fetchall()
        start_i = max(0, len(txs) - last) if last else 0
        prev = txs[start_i - 1]["hash"] if start_i else GENESIS
        for t in txs[start_i:]:
            if t["prev_hash"] != prev:
                problems.append(f"Entry {t['id']} does not follow entry {t['id'] - 1}.")
            if t["null_rows"] is not None:
                rows = con.execute("""SELECT * FROM audit_row WHERE token IS NULL AND id IN (SELECT value FROM json_each(?))
                                      ORDER BY id""", (t["null_rows"],)).fetchall()
            else:
                rows = con.execute("SELECT * FROM audit_row WHERE token = ? ORDER BY id", (t["token"],)).fetchall()
            if entry_hash(t["prev_hash"], rows, t) != t["hash"]:
                problems.append(f"Entry {t['id']} ({t['at'][:16].replace('T', ' ')}, {t['action']}) has been changed since it was saved.")
            prev = t["hash"]
        unsealed = con.execute("""SELECT COUNT(DISTINCT token) FROM audit_row r WHERE token IS NOT NULL
                                  AND token IS NOT (SELECT token FROM audit_context WHERE only = 1)
                                  AND NOT EXISTS (SELECT 1 FROM audit_tx t WHERE t.token = r.token)""").fetchone()[0]
        if unsealed:
            problems.append(f"{unsealed} saved change{'s are' if unsealed > 1 else ' is'} not sealed into the trail.")
    finally:
        con.row_factory = rf
    want, have = triggers(con), _have(con)
    if any(have.get(n) != s for n, s in want.items()):
        problems.append("The audit triggers have been changed or removed.")
    from . import ledger
    if ledger.guard_missing(con):
        problems.append("The check that refuses entries made here for a company kept in SQL has been changed or removed.")
    if _exists(con, "audit_sealed"):
        odd = con.execute("""SELECT COUNT(*) FROM (
                               SELECT j.value AS row_id, t.id AS tx_id FROM audit_tx t, json_each(t.null_rows) j WHERE t.null_rows IS NOT NULL
                               EXCEPT SELECT row_id, tx_id FROM audit_sealed
                               UNION ALL
                               SELECT row_id, tx_id FROM audit_sealed
                               EXCEPT SELECT j.value, t.id FROM audit_tx t, json_each(t.null_rows) j WHERE t.null_rows IS NOT NULL)""").fetchone()[0]
        if odd:
            problems.append("The index of accepted outside changes doesn't match the entries that accepted them.")
    st = status(con)
    if st["head_behind"]:
        problems.append("records.db is older than the last entry recorded outside it (expected after restoring a backup).")
    if st["head_rewritten"]:
        problems.append("The last entry recorded outside records.db has a different fingerprint in records.db: "
                        "the trail may have been rebuilt.")
    return {"ok": not problems, "checked": len(txs) - start_i, "problems": problems, "outside": st["outside"],
            "check_code": st["check_code"]}
