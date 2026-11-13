Scores run from 1 to 10. For effort, 10 means the least work. The total weights safety and audit completeness twice, because the owner's real records and a trustworthy trail come first.

| Design | Safety of real records | Audit completeness | Fit with code and screens | User value | Effort | Weighted total |
|---|---|---|---|---|---|---|
| Integrity | 8 | 9 | 7 | 8 | 5 | **54 (winner, used as the base)** |
| Incremental | 7 | 7 | 8 | 8 | 8 | 52 |
| Generic | 6 | 8 | 7 | 9 | 6 | 50 |

**Key claims checked against the code (read only)**

- **Confirmed:**
  - `.commit()` appears 27 times in app.py and 2 times in db.py (db.py:321, 324), 29 in all. Incremental's count is right; Generic's "about 50" is wrong.
  - There is no `INSERT OR REPLACE`.
  - `executescript` is used only at db.py:184, 237 and 315. `executemany` is used at app.py:459-460 (Tidy deletes).
  - `rules.` appears 53 times: app 10, auditpack 8, db 25, nextup 5, reports 5.
  - `nextup.py:170` indexes `LEGAL_DUE["statutory"]` directly. A row that can be deleted would turn this into a KeyError.
  - The "first account" rule appears at recon.py:53 and app.py:1339, and a third time in the browser at app.js:1405 (`accounts[0]`). None of the designs saw the third one.
  - GET connections are query_only (app.py:49-51). The server runs with `threaded=False` (app.py:1783).
  - `Backup created: ` is parsed at nextup.py:413.
  - The checklist is keyed by company code (db.py:172, 190, 410).
  - Pack files are named by company code (auditpack.py:162-163) and found by glob (db.py:1227-1228).
  - FK `ON DELETE SET NULL` is at db.py:97.
  - The code uses `rowcount` (app.py:566, 572, 1173, 1188-1196) and `lastrowid` widely. Neither is changed by AFTER triggers in SQLite, because both report only the top-level statement. Phase 0 must still test this.
- **Generic is the only design that caught a real bug.** `sync_payee` works out the old plan with `_due_in(con, old, month)`, which leads to `planned()`, which calls `advance_for()` and so reads the live `advances` table (db.py:597-600, 683). If an advance is written first and `sync_payee` runs afterwards, the old and new plans are equal and nothing changes. Incremental ("a save runs sync_payee") and Integrity ("same fan-out") would both silently do nothing.
- **All three designs share one false claim.** They say `samples/` holds real data committed to git. It is in .gitignore, and `git ls-files` and `git log --all -- samples tests` return nothing. Only 21 source files are tracked. `samples/` and `tests/` exist only on the PC.
- **Generic's claim that packs are "never overwritten" is false.** The pack name has minute resolution (`%Y%m%d-%H%M`, auditpack.py:163) and is written with `open(...,"wb")`. A second build in the same minute overwrites the first.
- **Integrity has a gap: lazy arming overrides only `execute`.** Tidy's `executemany` deletes (app.py:459-460) run before its `log` (app.py:461). Those deleted rows would get a NULL token and be flagged as "outside this app".
- **Generic's `create_function` context has two problems:**
  - Every write from DB Browser or the sqlite3 CLI fails, which blocks repair and recovery.
  - Its "snapshot required documents onto each payment" approach has to be recomputed on every category change: `PATCH /api/payments`, sync_payee's category change, and recon apply. The design never mentions this.
- **A migration hazard none of the designs named in full.** Old steps call live business functions, not only constants:
  - step 6, `take_line_total`;
  - step 7, `planned`;
  - step 8, `sync_reminders`, which reads `rules.PEOPLE_TASKS` (db.py:462, 519);
  - step 12, `refile_documents`;
  - step 13, `CHECKLIST["AISB"]`.

  If those functions read the new tables, an old database that upgrades through steps 6-13 would run them against empty tables.
- **app.js:69 also hard-codes the "after the 10th" rollover.** It duplicates db.py:393-396, so that setting must reach the browser through `/api/meta`.

# Setup and audit trail: combined design for hr-payments

**Base:** the Integrity design. It has database-level capture, a context row, an append-only log, a hash chain, a baseline, guard triggers and an honest feasibility review.

**Grafts from the other two:**
- From **Incremental**: the phasing, effective-dated required documents, the setup snapshot hash for packs, the stale-edit check, the before/after equivalence test, and reuse of the existing Recurring drawer.
- From **Generic**: one registry that drives the API, forms and history; the advances "old plan" fix; a rule snapshot on tasks at ensure_month; an `audit_packs` table; a `Sec-Fetch-Site` check on logged reads; and a self-check in the seed step.

All file:line references are to main at 61b5530. Nothing was run or edited.

---

## 1. Principles

1. **Keys are permanent; labels and parameters are editable.** Stored rows refer to text keys:
   - `payments.category` (db.py:48)
   - `tasks.code` and `tasks.required_docs` (db.py:40-41)
   - `documents.doc_type` (db.py:56)
   - `budget_lines.category` (db.py:98)
   - joiner and leaver task codes `{kind}-{key}-{payee_id}` (db.py:467, 519)

   No key ever changes. Keys that the code branches on carry `system = 1`.
2. **History keeps its meaning.** Two things are copied at the time of use, and filed months (`months.closed_at`) are never rewritten by a Setup change:
   - A task copies its template when the month is opened (db.py:410-413). It also gets the template's completion rule (new).
   - Required documents are effective-dated by month.
3. **Capture can't be skipped.** Generated SQLite triggers write every row change in the same transaction as the change. The app adds who, why and where on top. Missing context produces an *unattributed* row, never a missing one.
4. **Append-only, chained and anchored.** No UPDATE or DELETE ever runs on the audit store. A hash chain shows edits in place. Anchors outside the database (the head file, a check code printed on packs, a backup manifest) show a full rewrite.
5. **Migrations add, never rewrite.** New tables and columns are filled from today's values. `rules.py` is frozen as the release 1 defaults, and old steps behave exactly as today (see §5.4).
6. **Copy is plain sentence case**: "Stop using", "Why are you making this change?", "Used by 214 payments, so the key can't change."

---

## 2. Master record types

| Setup section | Table | Editable fields (**bold** = locked once used or always) | Replaces |
|---|---|---|---|
| Companies | `entities` + columns | **code** (locked once any month, payment or document exists: folders and packs, docstore.py:27, auditpack.py:162, db.py:1228), name, short_name, reg_no, tin, sst_no, employer_kwsp, employer_perkeso, employer_lhdn, sql_database, uses_sql, first_month, active, sort, notes | seed only (db.py:331); the first-month card on the Backup page (app.js:1520-1524, app.py:417-427); "Sdn Bhd" stripping (app.js:212) |
| Bank accounts | `accounts` + columns | label, bank, number, **currency** (locked once statements or payments exist), statement_format ('maybank'), gl_code, sql_payment_method, cash_book (exactly one per company), active, sort, notes | seed only (db.py:336); first-account rules at recon.py:53, app.py:1339, app.js:1405; the silent number fill (app.py:762-763) becomes audited |
| Recurring payments | `payees` (existing) + party_id, sql_code | existing fields (app.py:676-677) | Stays on the existing Recurring drawer (app.js:1404-1447). Gains server-side validation, delete when unused, and History |
| Salary advances | `advances` (existing) | payee, monthly_deduction, start_month, end_month, note | seed only (db.py:349-351). Saves through the payee fan-out with the old-plan fix (§6) |
| Customers and suppliers | `parties` (new) | kind (customer, supplier, related, statutory), name, short_name, **sql_code**, tin, brn, match_words, gl_code, active, notes | hard-coded counterparty names in rules.py:95-96, 120, 142-144 and sqlimport.py:507-509. **Staff are not parties**: they stay recurring payments, so personal data isn't copied into a second store |
| Chart of accounts | `gl_accounts` (new) | company, **code**, name, type, special (bank, debtor_control, creditor_control), parent_code, active, notes | the 3xx/4xx prefix guess (sqlimport.py:85-96). Reference data only; nothing posts to the GL |
| Payment types | `payment_types` (new) | **key**, label, plural, **direction** (locked when used), legal_due_offset, legal_due_day, guess_words, sql_hint_words, system, active, sort | CATEGORIES (rules.py:35-47), LEGAL_DUE (:72), nextup KINDS (nextup.py:24-25), `_guess_category` words (app.py:1298-1306), CATEGORY_HINTS (sqlimport.py:323-324) |
| Document types | `doc_types` (new) | **key**, label, singular, plural, pack_order, from_sql, system, active | DOC_TYPES, DOC_COUNTED, DOC_ORDER, SQL_ONLY (rules.py:6-33, 65). Upload validation (app.py:591) checks against active keys |
| Required documents | `required_docs` (new) | payment_type, doc_type, company (blank = all), **from_month**, to_month, sort | REQUIRED_DOCS and required_docs() (rules.py:51-64, 75-77), effective-dated |
| Monthly checklist | `checklist_items` (new) | company, **code**, month_offset, day, title, detail, docs, completion, rule (JSON: categories, direction, words, party_id, docs, on_item, paid, none, name), deadline, submit_group, system, active, sort | CHECKLIST (rules.py:85-126), TASK_PAYMENTS (:139-153), TASK_STATEMENTS/TASK_PACK (:156-158), nextup DEADLINES/SUBMIT/COVERED/STATEMENT_DUE/CLOSE_DUE (nextup.py:15-19) |
| Joiner and leaver reminders | `people_tasks` (new) | **key**, kind, days, salary_over, title, detail ({name}, {date}), docs, short_name, active, sort | PEOPLE_TASKS (rules.py:164-179), nextup PEOPLE (nextup.py:21-22) |
| Matching words | `match_words` (new) | purpose (overseas provider, SQL filing, bank charge word, own-transfer word), words, target_key, party_id, active | OVERSEAS_PROVIDERS (app.py:1295); TASK_RULES words (sqlimport.py:505-510), until phase 6 turns names into party links |
| General settings | `settings` (new, key → JSON) | organisation name, base currency, default due day, cycle rollover day, soon/ahead days, new recurring payment defaults, debtor/creditor code prefixes | index.html:13, budget.py:247, db.py:26/347, db.py:393-396 **and app.js:69**, nextup.py:9, app.js:1405, sqlimport.py:86-95 |

**Stays in code.** These are rules of SQL Account, the bank or the app, not master data. They are never editable:
- SQL doc-type sets (sqlimport.py:27-31), SQL_VOUCHERS (rules.py:68) and the DATAPACKET columns
- the Maybank parser and its regexes (statements.py:14-22; BANK_CHARGE/OWN_TRANSFER at 212-213 keep their regex shape, with only literal words drawn from `match_words` once the owner asks)
- matching thresholds, TOL/STATUS_WORDS, RECON_DETAIL, CHECKLIST_CHANGED
- ALLOWED_HOSTS, MIN_PASSWORD, PAY_FIELD_NAMES and the UI mirrors (RC_PILL, READY_HEADS, SQL_FIELD_LABELS)
- machine settings in settings.json (config.py:9-26), which are needed before the database opens

A `SYSTEM_KEYS` constant lists every key the code branches on. A startup assertion checks that each one exists:
- **Payment types:** salary, director, statutory, claim_overseas, receipt, other.
- **Document types:** all 15 current keys.
- **Checklist codes:** statement, recon, records, file, einv-selfbilled, kwsp, perkeso, epcb, einv-rental, payroll-jv, fund-received, budget.

---

## 3. DDL

### 3.1 Audit store (step 16)

```sql
CREATE TABLE IF NOT EXISTS audit_row (            -- written only by triggers and audit.event()
  id INTEGER PRIMARY KEY,
  token TEXT,                                     -- NULL = written without the app's context (outside tool, or a bug)
  at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now','localtime')),
  tbl TEXT NOT NULL,                              -- table name, or 'file' / 'pack' / 'backup' / 'export' / 'settings'
  row_key TEXT NOT NULL,                          -- id; key; 'entity_id|month' (months, budgets); 'account_id|month' (book_openings)
  op TEXT NOT NULL CHECK (op IN ('insert','update','delete','baseline','event')),
  entity_id INTEGER,
  before TEXT CHECK (before IS NULL OR json_valid(before)),
  after  TEXT CHECK (after  IS NULL OR json_valid(after))
);
CREATE TABLE IF NOT EXISTS audit_tx (             -- one per sealed transaction; inserted by Python at commit
  id INTEGER PRIMARY KEY,
  token TEXT NOT NULL UNIQUE,
  at TEXT NOT NULL, actor TEXT NOT NULL, machine TEXT,
  source TEXT NOT NULL CHECK (source IN ('user','auto','import','migration','seed','read','outside','system')),
  action TEXT NOT NULL,                           -- 'setup.payment_types.update', 'POST /api/payments', 'update 17'
  route TEXT, entity_id INTEGER, reason TEXT,
  summary TEXT,                                   -- this transaction's activity lines, joined
  counts TEXT CHECK (counts IS NULL OR json_valid(counts)),   -- {"payments":{"update":3},"tasks":{"delete":1}}
  null_rows_upto INTEGER,                         -- 'outside' seals only: covers NULL-token rows up to this audit_row.id
  late INTEGER NOT NULL DEFAULT 0,                -- sealed at start-up after a crash
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_context (only INTEGER PRIMARY KEY CHECK (only = 1), token TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_packs (          -- every pack built, so a printed copy can be verified
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), month TEXT NOT NULL,
  file_name TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL, built_at TEXT NOT NULL,
  tx_token TEXT NOT NULL, head_hash TEXT NOT NULL, setup_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_snapshots (hash TEXT PRIMARY KEY, at TEXT NOT NULL, json TEXT NOT NULL);
-- created inside the step, not in SCHEMA (SCHEMA runs before the steps, db.py:315):
CREATE INDEX IF NOT EXISTS audit_row_rec    ON audit_row(tbl, row_key, id);
CREATE INDEX IF NOT EXISTS audit_row_token  ON audit_row(token);
CREATE INDEX IF NOT EXISTS audit_row_entity ON audit_row(entity_id, id);
CREATE INDEX IF NOT EXISTS audit_row_null   ON audit_row(id) WHERE token IS NULL;
CREATE INDEX IF NOT EXISTS audit_tx_at      ON audit_tx(at);
-- append-only guards, on audit_row, audit_tx, audit_packs and activity:
CREATE TRIGGER IF NOT EXISTS audit_row_no_u BEFORE UPDATE ON audit_row BEGIN SELECT RAISE(ABORT,'The audit trail can''t be changed.'); END;
CREATE TRIGGER IF NOT EXISTS audit_row_no_d BEFORE DELETE ON audit_row BEGIN SELECT RAISE(ABORT,'The audit trail can''t be changed.'); END;
-- (same pair for audit_tx, audit_packs, activity; activity is insert-only today: db.py:118 is its only writer)
-- plus add_column(con, 'activity', 'token', 'TEXT')
```

`audit_row` and `audit_tx` are kept separate so the trail page can list and page transactions directly. `setup_snapshots` is keyed by content and is not covered by triggers.

### 3.2 Master tables (SCHEMA for fresh installs, and created in steps 18-21)

```sql
CREATE TABLE IF NOT EXISTS payment_types (
  key TEXT PRIMARY KEY, label TEXT NOT NULL, plural TEXT,
  direction TEXT NOT NULL DEFAULT 'out' CHECK (direction IN ('out','in')),
  legal_due_offset INTEGER, legal_due_day INTEGER CHECK (legal_due_day IS NULL OR legal_due_day BETWEEN 1 AND 31),
  guess_words TEXT, sql_hint_words TEXT,
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS doc_types (
  key TEXT PRIMARY KEY, label TEXT NOT NULL, singular TEXT, plural TEXT, pack_order INTEGER,
  from_sql INTEGER NOT NULL DEFAULT 0, system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  sort INTEGER NOT NULL DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS required_docs (
  id INTEGER PRIMARY KEY, payment_type TEXT NOT NULL REFERENCES payment_types(key),
  doc_type TEXT NOT NULL REFERENCES doc_types(key), entity_id INTEGER REFERENCES entities(id),  -- NULL = every company
  from_month TEXT NOT NULL DEFAULT '0000-00', to_month TEXT,                                     -- [from, to)
  sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS checklist_items (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), code TEXT NOT NULL,
  month_offset INTEGER NOT NULL, day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
  title TEXT NOT NULL, detail TEXT, docs TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(docs)),
  completion TEXT NOT NULL DEFAULT 'hand'
    CHECK (completion IN ('hand','payments','statements','statements_balanced','reconciled','pack')),
  rule TEXT CHECK (rule IS NULL OR json_valid(rule)),
  deadline INTEGER NOT NULL DEFAULT 0, submit_group TEXT,
  system INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0, notes TEXT,
  UNIQUE (entity_id, code));
CREATE TABLE IF NOT EXISTS people_tasks (
  key TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('joiner','leaver')), days INTEGER NOT NULL,
  salary_over REAL, title TEXT NOT NULL, detail TEXT NOT NULL, docs TEXT NOT NULL DEFAULT '[]', short_name TEXT,
  active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS match_words (
  id INTEGER PRIMARY KEY, purpose TEXT NOT NULL, words TEXT NOT NULL, target_key TEXT,
  party_id INTEGER REFERENCES parties(id), active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS parties (
  id INTEGER PRIMARY KEY, entity_id INTEGER REFERENCES entities(id),     -- NULL = both companies
  kind TEXT NOT NULL CHECK (kind IN ('customer','supplier','related','statutory')),
  name TEXT NOT NULL, short_name TEXT, sql_code TEXT, tin TEXT, brn TEXT, match_words TEXT, gl_code TEXT,
  active INTEGER NOT NULL DEFAULT 1, notes TEXT);
CREATE TABLE IF NOT EXISTS gl_accounts (
  id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL REFERENCES entities(id), code TEXT NOT NULL, name TEXT NOT NULL,
  type TEXT CHECK (type IN ('asset','liability','equity','income','expense')),
  special TEXT CHECK (special IS NULL OR special IN ('bank','debtor_control','creditor_control')),
  parent_code TEXT, active INTEGER NOT NULL DEFAULT 1, notes TEXT, UNIQUE (entity_id, code));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL CHECK (json_valid(value)));
```

**Columns added through `add_column`**, so no table is rebuilt:
- **entities:** short_name, reg_no, tin, sst_no, employer_kwsp, employer_perkeso, employer_lhdn, sql_database, active (default 1), sort (0), notes.
- **accounts:** statement_format (default 'maybank'), gl_code, sql_payment_method, cash_book (0), active (1), sort (0), notes.
- **payees:** party_id, sql_code.
- **tasks:** rule (TEXT, JSON), completion (TEXT).
- **sql_entries** (phase 6): code, payment_method, cheque_no, dockey, currency_code.

Indexes on added columns (`parties(entity_id, sql_code) WHERE sql_code IS NOT NULL`, `required_docs(payment_type, from_month)`) are created inside the steps.

### 3.3 Guard triggers: the backstop for references SQLite can't enforce

```sql
CREATE TRIGGER payment_types_key_fixed BEFORE UPDATE OF key ON payment_types WHEN NEW.key IS NOT OLD.key
BEGIN SELECT RAISE(ABORT,'A payment type''s key can''t be changed.'); END;
CREATE TRIGGER payment_types_system_kept BEFORE DELETE ON payment_types WHEN OLD.system = 1
BEGIN SELECT RAISE(ABORT,'The app itself uses this payment type, so it can''t be deleted.'); END;
CREATE TRIGGER payment_types_in_use BEFORE DELETE ON payment_types
WHEN EXISTS (SELECT 1 FROM payments WHERE category = OLD.key) OR EXISTS (SELECT 1 FROM payees WHERE category = OLD.key)
  OR EXISTS (SELECT 1 FROM budget_lines WHERE category = OLD.key) OR EXISTS (SELECT 1 FROM required_docs WHERE payment_type = OLD.key)
BEGIN SELECT RAISE(ABORT,'This payment type is in use. Stop using it instead.'); END;
-- doc_types: same three; in-use also checks documents.doc_type, required_docs.doc_type,
--   tasks.required_docs via json_each, checklist_items.docs via json_each, people_tasks.docs via json_each
-- checklist_items: code fixed; delete refused while any tasks row has (entity_id, code)
-- people_tasks: key fixed; delete refused while any tasks.code LIKE kind||'-'||key||'-%'
-- entities: code fixed once months/payments/documents/tasks exist; delete refused while any child row exists
-- payees: delete refused while payments, advances, budget_lines.payee_id (no FK, db.py:98) or joiner-/leaver- tasks reference it
```

The application runs the same checks first, through the registry's `used_by`, so it can show a friendly 409 with counts. The triggers are the backstop. Adding real FKs would mean rebuilding tables of real records, which isn't worth the risk.

---

## 4. Audit trail model

### 4.1 Capture: generated triggers
- **Generation.** `hrp/audit.py` holds `AUDITED`, a spec per table: row-key expression, entity expression and sensitive columns. `ensure_triggers(con)` reads `PRAGMA table_info` and generates `audit_<t>_i/_u/_d`. Each writes `json_object(...)` of the full row before and after, with `token = (SELECT token FROM audit_context WHERE only = 1)`.
  - The UPDATE trigger has `WHEN OLD.a IS NOT NEW.a OR ...`, so no-op updates write nothing. This matters for sync_payee, link_new and the SQL re-import fill-in at app.py:1173-1187.
- **Entity per row.**
  - Tables with an `entity_id` column use it.
  - statements and book_openings go through accounts. statement_lines goes through statements and accounts. advances goes through payees.
  - Global masters get NULL.
- **Tables covered.** Every business table and every new master table. `audit_*`, `setup_snapshots` and `activity` are excluded. Activity is protected by the guard triggers and linked by token instead.
- **When triggers are regenerated.** At the end of every `init()`, after the steps, and inside any step that adds a column to an audited table.
  - Each trigger's stored SQL in `sqlite_master` is compared with the generated SQL. Only triggers that differ are dropped and recreated, and that is recorded as an event.
  - Triggers that are missing or edited, when nothing in the code changed, raise an alert event.
- **`PRAGMA recursive_triggers = ON`** in `db.connect()`. A future `INSERT OR REPLACE` then still fires DELETE triggers. No other triggers exist today, so turning it on is safe.
- **What this catches that the current log misses.** All the not-logged writes in the code map:
  - the task note (app.py:478-479)
  - the budget header (budget.py:291-301)
  - link_new (budget.py:188)
  - the silent account-number fill (app.py:762-763)
  - rematch, auto_match, take_line_total and classify (app.py:1426-1431; statements.py:178-202, 242)
  - `_add_sql_ref`, `_after_unlink` and `_unlink_entry` (app.py:1224-1292, 1509)
  - the SQL row inserts and fills (app.py:1166-1187)
  - ensure_month's inserts (db.py:411-417)
  - every hard delete, with the full deleted row (db.py:532, 696; app.py:459-460, 573, 875, 1495; budget.py:284)
  - the upsert (recon.py:627-629)
  - the FK SET NULL (db.py:97), to be confirmed in phase 0

### 4.2 Context: who, why, from where
- **Connection.** `db.connect()` becomes `sqlite3.connect(DB_PATH, factory=HrpConnection)`, keeping `foreign_keys = ON`.
  - It holds `ctx = {token (uuid4 hex), actor, machine, source, action, route, entity_id, reason}`.
  - Actor and machine come from `getpass.getuser()` and `socket.gethostname()`, read once in `main()` (app.py:1776).
- **Arming is eager, not lazy.** This fixes Integrity's `executemany` gap. For every non-GET request, `con()` (app.py:45-52) runs `INSERT INTO audit_context ... ON CONFLICT DO UPDATE` straight away.
  - That opens the transaction, so every write in the request carries the token, whether it comes from execute, executemany or a cascade.
  - The cost is one tiny write per POST, including the auto-opens on page load (app.js:1873-1879). That is negligible.
  - `init()` arms each migration step (source `migration`, action `update <n>`) and the seed (source `seed`).
- **Source.**
  - `user` by default.
  - `auto` when the body has `auto: true` (app.py:382). No new header is needed.
  - `import` for `/api/statements` and `/api/sql/apply`.
  - Setup handlers set a readable action such as `setup.<kind>.<verb>`.
- **Reason.** A body field `reason`. The server requires it for:
  - delete, stop or restart of a master record
  - reopening a filed month (app.py:388-414)
  - removing a document (app.py:627-643)
  - accepting outside changes

  The prompt reads "Why are you making this change?".
- **Activity.** `db.log` is unchanged in its text, with all 52 call sites kept. It also writes `activity.token`. `nextup` still reads `Backup created: ` (nextup.py:413).

### 4.3 Sealing at commit
`HrpConnection.commit()` does the following:
1. It reads this token's `audit_row` and `activity` rows in id order. If there are none, it deletes the context row and commits.
2. Otherwise it builds canonical text: one compact `json.dumps([id, at, token, tbl, row_key, op, entity_id, before, after])` line per row, with the JSON text hashed **as stored**, plus the activity lines.
3. It reads `prev_hash` from the last `audit_tx`. The first one is `'0' * 64`.
4. It inserts an `audit_tx` row with `hash = sha256(prev_hash + "\n" + canonical + "\n" + canonical(tx row without hash))`.
5. It deletes the context row and commits.

`rollback()` drops everything with the change, so `/api/sql/preview` (app.py:1115) leaves nothing behind. The hash is computed in Python, because core SQLite has no sha256.

**Startup jobs, in `init()` after the steps:**
- **Late seal.** Rows with a token but no `audit_tx` (a crash, or an implicit commit by `executescript`) are sealed with `late = 1`.
- **Outside rows.** NULL-token rows raise the "Changes made outside this app" alert. "Accept and seal" needs a reason. It writes an `outside` tx with `null_rows_upto`, so the rows themselves are never updated.
- **Quick check** of the last 200 tx rows, then the head file is written.

### 4.4 Baseline (step 17)
One `baseline` row is written per existing row of every audited table, so the trail starts from the real records as they stand that day.
- The install tx also records the count and sha256 of the existing `activity` rows, so the old log is anchored as it stood.
- Existing activity rows stay as they are. They appear on the trail page as "Before the detailed audit trail".

### 4.5 Reads and events
- **POST events.** Backup (app.py:1664-1713), pack build (app.py:1527-1537), auditor export (app.py:1599-1611) and the backup-folder setting (app.py:1716-1743) call `audit.event(con, kind, key, detail)`. The detail holds the file name, sha256, size and head hash.
  - **Pack builds also insert `audit_packs`.** The pack name gains seconds (`%Y%m%d-%H%M%S`, auditpack.py:163), so a second build in the same minute no longer overwrites the first.
  - The `packs_of` glob pattern (db.py:1228) still matches.
- **GET downloads and exports** (app.py:617-624, 1559-1564, 1574-1596, 1616-1621) use `@audited_read(kind)`.
  - The event is written in `after_request`, only for 2xx responses, on a separate short connection with source `read`.
  - It is written **only when `Sec-Fetch-Site` is `same-origin` or `none`**. A cross-site `<img>` to 127.0.0.1 passes the Host check (app.py:30), and this stops it from filling the trail.
  - A test asserts that every GET route either has `@audited_read` or is on a "plain read" allowlist.
  - Page views are not logged (see the owner decision in §10).

### 4.6 Tamper evidence and its limits
- **Checks.** `audit.verify(full)` does four things:
  - recomputes the chain;
  - lists NULL-token rows;
  - compares the triggers with the generated SQL;
  - runs a **replay check**: the last after-image per `row_key` from baseline, inserts and updates must equal the live row. Phase 2 runs it on demand from the trail page.
- **Anchors outside the database:**
  - `PROGRAM_DIR/audit-head.json` holds `{last_tx, hash, at}` and is written atomically like `save_settings` (config.py:23-26). It must be added to .gitignore.
  - The audit pack footer prints "Audit trail entry N · check code xxxxxxxx".
  - Each backup zip gets a `manifest.json` with the head and the snapshot's sha256.
- **What this does not stop.** Someone with the file and skill can still drop the triggers and rebuild a consistent chain. That only goes unnoticed if the printed packs, the off-PC backups and the head file are all ignored. The trail page says this plainly, and says that "Made by" is the Windows user running the app, not a signed-in person.
- **Integrity failures warn, they don't block.** A red banner appears and an event is written.
- **Failure to install triggers at startup refuses to start**, with a plain message and the pre-update copy (db.py:300-305) as the way back. Both of these are owner decisions.

### 4.7 Personal data and volume
- **Sensitive columns are masked** until the reader clicks "Show": payees.bank_details, accounts.number, and amounts on salary/director rows. The Excel export warns before including them.
- **Retention** is forever. The trail is not in the auditor package by default, and it travels in the existing encrypted backups.
- **Volume.** Estimated at a few MB a year, plus 5-10 MB for a first year-long SQL import. Phase 0 measures it.
- **All new tests use a synthetic seed**, so they can live in git. The existing local tests use real data (.gitignore).

---

## 5. Constant-to-table migration

### 5.1 Steps
Steps are appended to `MIGRATIONS` (db.py:203-253). Each one is idempotent and runs after the existing `copy_before_update`.

| Step | Does | Effect on real records |
|---|---|---|
| 16 | Audit tables, indexes, guards, `activity.token` | none |
| 17 | `ensure_triggers`; baseline rows; install tx with the activity count and hash | none (copies only) |
| 18 | entities and accounts columns; `cash_book = 1` on the lowest-id account per company (matches recon.py:53 and app.py:1339 exactly); `statement_format = 'maybank'`; `settings` seeded with today's literals | behaviour unchanged |
| 19 | `payment_types`, `doc_types`, `required_docs` (all `from_month '0000-00'`, entity NULL) seeded from rules.py with `INSERT OR IGNORE`, then `UPDATE ... SET system = 1` for SYSTEM_KEYS | every status evaluates as today |
| 20 | `checklist_items` per entity **whose code is a key of `rules.CHECKLIST`** (same lookup as db.py:410); rule from TASK_PAYMENTS; completion from TASK_STATEMENTS/TASK_PACK; deadline and submit_group from nextup; `people_tasks`; `match_words` (overseas providers; TASK_RULES words, including the counterparty names, kept as words for now). Adds `tasks.rule` and `tasks.completion` and **fills them for existing tasks from today's constants by code** | new columns filled with today's meaning; no existing value changes |
| 21 (phase 6) | `parties`, `gl_accounts`, `payees.party_id` and `sql_code`, the sql_entries columns. Parties for the related company and the tenant are created from the words in code. The payee links are offered in Setup, one confirmation at a time, never automatic | none until you act |

### 5.2 Self-check inside each seed step
- **Comparison.** After seeding, the step reads the tables back through `masters` and compares them with `rules.py` (graft from Generic). A difference raises, so `user_version` isn't bumped (db.py:319-321).
- **SAVEPOINT.** Each new step runs inside one, so a failed seed leaves nothing half-written. `init()` has no try/except.

### 5.3 Readers switch to `hrp/masters.py`
- **What it exposes.** `masters.get(con)` is cached per connection and returns today's shapes: `.categories`, `.doc_types`, `.doc_order`, `.doc_counted`, `.required_docs(category, uses_sql, month, entity_id)`, `.checklist(entity_id)`, `.task_rule(task)`, `.people_tasks`, `.setting(key)`, `.legal_due(category)`.
  - `required_docs` keeps the fallback to `other` (rules.py:76) and the from_sql filter (rules.py:77).
  - Its callers (app.py:166, db.py:877, auditpack.py:112/184, reports.py:113) pass the payment's month and company.
- **Rewriting the references.** All 53 `rules.` references are rewritten, except that old migration steps keep `rules.` directly.
  - `ensure_month` (db.py:410) reads `checklist_items WHERE entity_id = ? AND active = 1` and copies the rule and completion into the task.
  - `task_status`/`_covers` (db.py:1007-1178) read `task["rule"]`.
  - nextup derives STATEMENT_DUE and CLOSE_DUE from the `statement` and `file` items, and LEGAL_DUE from the statutory row (nextup.py:19, 170).
- **`/api/meta`** (app.py:118-128) keeps its shape (`doc_types`, `categories`, `required`, `sql_only`). It adds inactive keys (flagged, so old rows still show a label) and the settings the browser mirrors: rollover day for app.js:69, new-payee defaults for app.js:1405, the organisation name for index.html:13, and the cash_book account.

### 5.4 The old-migration hazard (missed by all three designs)
Old steps call live functions: 6 (`take_line_total`), 7 (`planned`), 8 (`sync_reminders` and the checklist), 12 (`refile_documents`) and 13 (`CHECKLIST["AISB"]`).

- **Rule:** while `init()` runs with `user_version` below the seed step (19 or 20), `masters.get(con)` returns the frozen `rules.py` values, not the tables. `init` sets a flag on the connection for this.
- **Result:** an old database that upgrades through steps 6-13 behaves byte-for-byte as today. A fresh install runs those steps on empty tables, which is harmless.
- **`rules.py` is never edited again.** A comment at its top says so.

### 5.5 Equivalence test
On a synthetic seed, record payment status, task status, recon state, nextup rows and pack readiness before the steps run. Compare them after: they must be identical. The owner may run the same test on their own copy of records.db.

---

## 6. Edit, stop and delete rules

| Action | Rule |
|---|---|
| Add | Validated server-side from the registry spec with `_body()` (app.py:251-253). The key is a slug typed or generated once, unique and then locked. This closes save_payee's gaps (category, due_day 1-31, month_offset 0/1 and ISO dates are unchecked today; a bad value gives a 500 at db.py:365-367) |
| Edit | Labels and parameters are free. Locked fields are refused on the server with a one-line reason. The drawer sends the id of the last `audit_row` it saw for the record; if a newer one exists, the reply is "This record was changed since you opened it." |
| Fan-out edits | Recurring payment, advance, required documents, checklist "also apply to open months", reminder rules. The **preview** runs in a SAVEPOINT that is then rolled back, the same pattern as app.py:1094-1115. The result shows on the existing changes/kept card (app.js:1371-1374). Filed months, ticked tasks and payments with anything recorded are never touched (db.py:624-629, 654-659, 691-694) |
| Advances (Generic's fix) | Inside the transaction: compute `was = {m: _due_in(con, payee, m)}` for each open month **before** writing the advance; write it; then call `sync_payee(con, old, new, was_plans=was)`. sync_payee gains an optional `was_plans` argument. Without it, was == want and nothing updates |
| Required documents | A save asks "From which month?". The default is the earliest month not yet filed, with the hint "Months before this keep their current rules." The save sets `to_month` on the current rows and inserts new ones. It reports how many open payments become complete or incomplete |
| Checklist template | Affects months opened later. "Also update months already open (not filed)" updates the un-ticked tasks with that code (title, detail, docs, due date, rule), like `_checklist_from_data` (db.py:169-177), with a preview |
| Reminder rules | Deactivating a rule: `sync_reminders` must build `codes` from **all** rules (db.py:519) and `want` from active rules only, so un-ticked reminders with nothing filed are removed and ticked or held ones stay (db.py:524-533) |
| Stop using (deactivate) | Allowed for any non-system record. A reason is required. The record is hidden from pickers, new months and matching, stays on old rows tagged "no longer used", and can be used again. The `other` type and system checklist items can't be stopped |
| Delete | Only when non-system and every `used_by` count is 0. The guard triggers back this up. A reason is required. Otherwise the reply is 409 with counts: "Used by 12 payments and 3 budget lines. Stop using it instead." The full row stays in `audit_row.before`. **Setup never cascades a delete** |
| Rename | Allowed. Payments keep their stored descriptions (db.py:48). Labels on old months follow the new name. Printed packs are files with a hash in `audit_packs`, and the trail shows when the name changed |
| Restore (phase 7) | "Put it back" re-inserts a deleted record's `before` JSON with the same id or key, if free. Audited |

---

## 7. API

Blueprint `hrp/setup.py` and `hrp/audit_api.py`. Both keep the Host allow-list, `X-HRP: 1` and the CSP (app.py:24-42), and use `_body()`, `entity()`, `own_account()` and `err()`. Every write rolls back on error, as `_recon_do` does (app.py:935-947).

| Method and path | Purpose |
|---|---|
| GET `/api/setup/types` | Registry: fields, labels, list columns, locks, sensitive fields, form kind |
| GET `/api/setup/<kind>?entity=&inactive=1&q=` | List with usage counts |
| GET `/api/setup/<kind>/<id>` | Record, `used_by` counts, locked fields and why |
| POST `/api/setup/<kind>` | Create |
| PATCH `/api/setup/<kind>/<id>` | Edit. Body `{fields, reason?, seen}`. Returns `changes`/`kept` for fan-out kinds |
| POST `/api/setup/<kind>/<id>/preview` | Fan-out dry run (rolled back) |
| POST `/api/setup/<kind>/<id>/stop` and `/use` | Deactivate or reactivate. Body `{reason}` |
| DELETE `/api/setup/<kind>/<id>` | Delete when unused. Body `{reason}`. 409 with counts otherwise |
| POST `/api/setup/required-docs` | `{payment_type, entity_id?, docs[], from_month, reason?}` |
| POST `/api/setup/checklist/<id>/apply-open` | Apply to open months (preview first) |
| POST `/api/payees/<id>/advances`, PATCH/DELETE `/api/advances/<id>`, DELETE `/api/payees/<id>` | Advances with the old-plan fix; payee delete when unused |
| GET `/api/audit?from&to&entity&tbl&op&source&q&before_id&limit=50` | Transactions, newest first, keyset paging |
| GET `/api/audit/tx/<token>` | One transaction: context, activity lines, field diffs. Labels come from PAY_FIELD_NAMES (app.py:487), db.CHANGED (db.py:633) and the registry; ids resolve to today's names |
| GET `/api/audit/record/<tbl>/<key>` | One record's history, including child rows (advances, required-doc rows) |
| GET `/api/audit/status` | Alerts: chain, outside rows, triggers, head file |
| POST `/api/audit/verify` | Full chain and replay check. Writes its result as an event |
| POST `/api/audit/accept-outside` | Seal NULL-token rows. Body `{reason}` |
| GET `/api/audit/export.xlsx?<filters>` | Excel export (openpyxl), `@audited_read`, warns about sensitive columns |
| GET `/api/activity` | Unchanged (app.py:1746-1749) |
| GET `/api/setup/export`, POST `/api/setup/import` (phase 7) | setup.json for a new install, so the app can run for another company with an empty records.db |

---

## 8. Setup UI (vanilla JS in static/app.js)

- **Navigation** (`VIEWS`, app.js:77-78):
  - Add a group `["Setup", [["setup", "Setup"], ["trail", "Audit trail"]]]`. The key `audit` is taken by Audit pack.
  - Rename "Backup & log" to "Backup".
  - Add an `ICON` for each new key (app.js:79-90) and a branch in `render()` (app.js:234-247).
  - Setup is **one view** holding `state.setup = {kind, id}`, like `state.recon`, with a section list. The breadcrumb reads "Setup › Payment types", which needs a small change in renderNav.
- **Section list, grouped:**
  - Companies and banks: Companies, Bank accounts, Chart of accounts
  - People and parties: Recurring payments, Salary advances, Customers and suppliers
  - Payments and documents: Payment types, Document types, Required documents, Matching words
  - Monthly work: Monthly checklist, Joiner and leaver reminders
  - General settings
- **Each list** reuses `listBar`/`sortTh`/`SORTS` (app.js:132-177) and `entityPicker()`. It has search, a "Show stopped" toggle, a "Used by" count and a pill: In use, Stopped, or Used by the app.
- **Each record** opens in the shared `#drawer` (index.html:31), drawn by one generic `editRecord(kind, row)` from `/api/setup/types`. The unsaved-changes guard comes from `closeDrawer` (app.js:503-510).
  - **Details tab:** the form; locked fields read-only with their reason ("Folders and audit packs are named by this code, so it can't change."); "Where used"; Save, Stop using or Use again, and Delete (shown only when unused). Stop and Delete ask "Why are you making this change?".
  - **History tab:** when, who, source and reason, then one line per field: "Label: Rental → Office rental". Sensitive values are masked until the reader clicks "Show". A deleted record offers "Put it back" (phase 7).
- **Recurring payments** keep the existing `editPayee` drawer (app.js:1404). It gains a History tab, Delete (when unused) and an advances grid. The "Recurring" entry in Monthly work stays as a shortcut.
- **Required documents and the checklist** add the "From which month?" box or the "Also update months already open" option, plus the preview card.
- **After any company or account change**, refresh `state.meta` as app.js:1708 does.
- **Audit trail page:**
  - An alerts banner.
  - Filters: date range, company, record type, action (added, changed, removed, read or export, sealed), made by (you, automatic, import, update, outside this app), and text search.
  - One row per transaction: when, who, source, headline (the activity line or "3 changes to payments"). Expanding a row shows the field diffs, with links to each record.
  - "Show older", "Export to Excel" and "Check the audit trail", which reports "All N entries check out. Check code xxxxxxxx."
  - A "Before the detailed audit trail" section for the old activity rows.
  - A plain note that "Made by" is the Windows user running the app.
- **History links** in the payment drawer, the bank-line panel and the budget line.

---

## 9. Phased delivery (each phase ships on its own)

| Phase | Ships | Effort |
|---|---|---|
| 0. Spike | On a scratch database in a temp folder, confirm: the FK SET NULL fires the child UPDATE trigger; the upsert fires the UPDATE trigger; `rowcount`/`lastrowid` are unchanged with triggers present; `executescript` inside a step; the timing of a 5,000-row SQL import with and without triggers. No real records are touched | S (1-2 days) |
| 1. Audit capture | Steps 16-17, `HrpConnection` (eager arming, seal, late and outside handling), trigger generator, guards, baseline, `recursive_triggers`, head file. Events plus `audit_packs` for pack, backup and export, with seconds in the pack name. Synthetic tests: no NULL tokens after every route, rollback leaves nothing, no-op updates write nothing, no `.commit()` bypasses the connection class | M (5-6 days) |
| 2. Audit trail page | `/api/audit*`, transaction view, filters, Excel export, `@audited_read` with the Sec-Fetch-Site check and the route-coverage test, verify and replay, check code on the pack footer, backup manifest. History links on payments, payees and budget lines | M (4-5 days) |
| 3. Setup framework, companies, accounts, recurring, advances, settings | Step 18. Registry, generic API and drawer, usage counts and locks, stop and delete. cash_book replaces three first-account rules. First month and Tidy move to Companies. Payee delete, validation and the advances grid with the old-plan fix. Settings served through `/api/meta`, including app.js:69 and app.js:1405 | L (7-8 days) |
| 4. Payment types, document types, required documents | Step 19 with self-check. `masters.py` with the pre-seed fallback. The `rules.` readers switched. Effective-dated required documents. `setup_snapshots` hash written on each pack build. Equivalence test | L (6-8 days) |
| 5. Checklist, reminders, matching words | Step 20 (templates, `tasks.rule` filled). ensure_month no longer depends on the company code. nextup derives its dates and flags. Apply-to-open-months. The reminder `codes`/`want` split. Match-words editor | L (6-9 days) |
| 6. Customers, suppliers, chart of accounts | Step 21. The SQL import keeps CODE, PAYMENTMETHODDESC, CHEQUENUMBER, DOCKEY and CURRENCYCODE (sqlimport.py:73-140). Matching by sql_code before words. "Create or match from codes found in this import" in the preview (app.py:1058-1117). TASK_RULES and the fund-received rule point to parties. Chart of accounts entered by hand or pasted (`read_rows`, sqlimport.py:40-70) | L (8-12 days); **blocked on real SQL Account exports** |
| 7. Extras | Put back a deleted master, rebuild a pack as built from the trail, setup.json export and import with a generic starter template | M (4-5 days) |

Phases 1 and 2 come first, so every Setup change is audited from its first day. Phases 3, 4 and 5 don't depend on 6.

---

## 10. Risks
1. **Trigger behaviour still needs confirming.** FK actions and upserts firing triggers, and rowcount staying unchanged. Phase 0 covers this.
2. **Fail-closed startup.** If the trigger install fails, the app won't open on payroll day. The pre-update copy and a clear message are the way back, and the owner chooses the policy.
3. **Effective-dating mistakes could change past months' status.** Mitigated by the equivalence test and a test that every caller of `required_docs` passes the month.
4. **Old migrations.** They must use the frozen defaults (§5.4). A test upgrades a synthetic version-0 database through every step and compares the result with today's code.
5. **Personal data is held twice**, in the records and in an immutable log. Mitigated by the same encrypted backups, masking and the export warning. PDPA correction is handled as a new entry, never an erasure.
6. **The actor is the Windows user.** Any local process able to send `X-HRP: 1` looks the same (app.py:27-33).
7. **Browser mirrors drifting.** Anything that moves to tables must reach app.js through `/api/meta`, never be copied into JS. This covers app.js:69, 212 and 1405.
8. **Volume and speed on large imports.** Expected to be small; measured in phase 0.

## 11. Decisions only the owner can make
1. **Who uses the app.** Is the Windows user enough for "Made by", or should a named-user picker (not real authentication) be added for an accountant or auditor on the same PC?
2. **Deletes.** Is "delete only if never used, otherwise stop using it" right for every master? Which actions must ask "why"? The proposal is delete, stop, reopening a filed month, removing a document, and accepting outside changes.
3. **Rule changes and months.** Should required-document and checklist changes apply from a chosen month (recommended), or also to every open month automatically? Do the two companies need different required documents for the same type?
4. **Integrity problems at startup.** Warn with a red banner (recommended) or refuse to open? And should a failure to install the triggers refuse to start?
5. **Reads.** Log only exports, downloads, packs and backups (recommended), or page views too?
6. **Check code on packs.** Is it fine to print "Audit trail entry N · check code" on every audit pack footer?
7. **Retention and PDPA.** Keep the trail forever? What period does the accountant require? Are corrections added as new entries rather than erasing old values?
8. **Customers and suppliers.** A separate list linked to recurring payments (recommended), with staff kept out of Setup?
9. **SQL Account exports.** Can you export Maintain Account (chart of accounts), Maintain Customer, Maintain Supplier and a PV listing with creditor codes? Does each company have its own SQL database?
10. **Company codes.** Is it fine that a code is locked once records exist? Names can change freely.
11. **Bank wording.** Should the bank-charge and own-transfer words be editable now, or wait until a second bank is supported?
12. **A starter template.** Should the app ship a generic starter checklist, so it can be used by a company other than these two?

---

## 12. Real company data hard-coded in tracked source (to move into records)

None of these are copied here. Tracked source holds no staff names, IC numbers, salaries or bank account numbers; those come from seed.json in the records folder (db.py:322-352). `samples/` and `tests/` are gitignored and were never committed (`git ls-files` and `git log --all` show nothing), which corrects all three designs.

- **The two company codes**, used as dictionary keys: rules.py:86 and :119, read by db.py:190 and db.py:410. They move to `checklist_items.entity_id`.
- **The sister company's full legal name**:
  - checklist wording at rules.py:95-96 and :120;
  - a comment at rules.py:135;
  - TASK_PAYMENTS words and name at rules.py:142-144;
  - SQL filing words at sqlimport.py:507-508.

  It moves to a `parties` row of kind related, plus the checklist wording.
- **The office tenant's trading name** at sqlimport.py:509. It moves to a `parties` customer and `match_words`.
- **The group brand line** at index.html:13. It moves to `settings.organisation_name`.
- **Named local utility, telco and copier suppliers** in checklist wording at rules.py:90 and in category guess words at app.py:1303. They move to `payment_types.guess_words` and the checklist wording.
- **Overseas software vendors** at app.py:1295 and in wording at rules.py:59 and :113. These are public vendors, not personal data. They move to `match_words`.
- **The bank and account product names** (main bank, Labuan current account, FCA, Islamic SME account) at statements.py:1-7 and rules.py:122-123. They move to the `accounts` labels and checklist wording; the parser stays in code.
- **Comment-only traces**, which need cleaning rather than moving:
  - A real-looking fund-requisition transfer pattern at db.py:222.
  - Transfer amounts at statements.py:132-133, 189 and 251.
  - SQL document numbers and the invoice numbering pattern at sqlimport.py:86 and 347-348, and db.py:731, 737, 814 and 847.
  - Name stems at statements.py:124.
  - A name word said to appear in two consultants' names at statements.py:287, which may be a fragment of a real personal name.

  These should be replaced with neutral examples.
---

## 13. Owner decisions (12 Nov 2026)

1. **Made by** is the Windows user and PC name for now. When the app moves to a hosted setup, a login system fills the same `actor` field, so the trail's shape doesn't change.
2. **Deletes:** a master record can be deleted only while unused; otherwise it is stopped ("Stop using"). Every delete and stop asks why.
3. **Rule changes** (required documents, checklist) apply from a month the user chooses, defaulting to the earliest month not yet filed. Filed months never change.
4. **Build order:** Phase 0 (trial on a scratch database) and Phase 1 (audit capture) first.

### Changes to the design made while building Phase 1
- The activity log is captured by an insert trigger like every other table, instead of a new `activity.token` column. Old migration steps call `db.log` before any new column could exist, and the trigger makes the log append-only automatically.
- **Unattributed writes are sealed, not lost.** If code writes through a connection that was never given a context, `commit()` seals those rows as "unattributed app write". Only rows written by another program show as "Changes made outside this app".
- Audit packs keep their minute-stamped name. A second build in the same minute takes a seconds stamp instead of overwriting, as the auditor package already does (reports.py:362-364).

### Phase 0 and 1 status (12 Nov 2026)
- **Phase 0 (trial on a scratch database):** 28/28 checks. FK `ON DELETE SET NULL` and upserts fire the triggers; `rowcount` and `lastrowid` are unchanged; 5,000 statement lines imported and all updated take 172 ms instead of 11 ms and add about 6 MB (full rows before and after).
- **Phase 1 (audit capture) built:** `hrp/audit.py`, update steps 16 and 17, request attribution in `app.con()`, events for audit packs (both routes), auditor packages, backups and the backup-folder setting, `GET /api/audit/status`, `POST /api/audit/accept-outside`, and `python -m hrp.trail`.
- **Independent review:** 22 findings, 13 confirmed by a skeptic and fixed (9 after merging duplicates): re-arming could orphan rows; triggers stale within later update steps (now refreshed after every step and every `add_column`); `executescript` and `with con:` bypassing the seal; the head file's hash never compared, and a restore or rebuilt chain silently rebased (now recorded as an event before the head moves); triggers repaired silently at start-up (now warned); no way to accept outside changes; identifier escaping in generated triggers; no event for the auditor package's pack; same-minute backups overwriting each other.
- **Tests:** `synthetic_tests/audit_trail_test.py` 38/38. The local `tests/` suite: 19 pass; 8 were adjusted for the trail (audit tables excluded from "nothing changed" counts, `drop_triggers` before simulated column drops, the activity guard lifted where a test back-dates a line, the update count, and n10's same-minute backup now kept as two files). 4 fail exactly as they do on the code before this change (b3_sql_months, n7_money_in, sql_multi, sql_paste).

### Phase 2 status (12 Nov 2026)
- **Built:** `hrp/auditread.py` (entries with filters and keyset paging, an entry's changes field by field, a record's history, outside changes, the replay check, the Excel export); routes `GET /api/audit`, `/api/audit/tx/<id>`, `/api/audit/record/<tbl>/<key>`, `/api/audit/outside`, `/api/audit/export.xlsx`, `POST /api/audit/check`; logged reads (`@audited_read` on every file download, written only for `Sec-Fetch-Site` same-origin or none); the check code on audit pack covers; `manifest.json` in backup zips; the Audit trail page under Filing; History in the payment and recurring-payment drawers and on budget lines; a notice on the Overview when the trail needs attention. Update 18 adds `audit_sealed`, an index of accepted outside rows (the hashed record stays `audit_tx.null_rows`; the full check proves the two agree).
- **Owner-visible decisions taken by default:** reads logged are downloads and exports only (no page views); bank details, account numbers and budget-line details are masked in trail views and exports until "Show" is ticked; a record that differs from the trail at a full check is recorded as a change made outside the app, to be accepted with a reason.
- **Independent review:** 19 findings, 16 confirmed and fixed (12 after merging), plus 3 from the browser walkthrough: Accept could seal changes not shown (now only up to the last one listed); filters slow or blind to accepted outside rows (index pinned, id-list join ordered); quadratic outside count (update 18); replay differences unaccepted and later absorbed (now recorded as outside changes); export broken by control characters, stray apostrophes, silent 5,000-entry cap; raw route as a check's headline; the page rebuilt on every filter change (now only the list); double-append, stuck loading, errors on leaving mid-check; entries without a company (taken from their rows); activity-line noise in an entry; budget-line details unmasked.
- **Tests:** `synthetic_tests/trail_view_test.py` 36/36, `audit_trail_test.py` 38/38. Local `tests/`: 19 pass (n5 and n9 adjusted: the Overview's extra status request; "GETs change nothing" now excludes the audit store, which records downloads by design); the same 4 fail as before this work. Browser check on made-up records: Overview notice, trail page, entry detail, full check, accept with reason, payment and budget-line history, filters keeping focus, the 17 → 18 update.

### Phase 3 status (12 Nov 2026)
- **Built:** Setup (sidebar › Setup) with Companies, Bank accounts, Recurring payments and General settings. `hrp/masters.py` holds the registry (field specs, checks, usage counts, locks, add, change, stop, use again, delete); `hrp/appsettings.py` the general settings (organisation name, payroll cutoff day, new recurring payment defaults, Next up's soon/ahead days, backup reminder days), cached and served in `/api/meta`. Update 19 adds the company and bank-account columns and `app_settings` (organisation name kept as it was), and makes each company's first account its cash book. Recurring payments: every field checked on the server, defaults from settings, stop / use again / delete with a reason, usage, and salary advances added, changed and removed with the fan-out fix (`db.plans` taken before the change, `sync_payee(..., was_plans=...)`). A payee's history includes its advances. "Backup & log" is now "Backup"; first month and Tidy moved to the company drawer (Tidy asks why).
- **Rules taken:** deleting only while unused, else stop, with a reason (owner decision). Locked once used: a company's code (folders and packs), its SQL Account flag (once a month is filed), an account's currency (once it has payments or statements), the cash book (once a month is filed). The cash book is one MYR account per company. An account recurring payments use can't be stopped. A stopped company leaves the sidebar, Overview and Next up; a stopped account stops asking for statements. Filed months never change: recurring payment changes skip them and say so; Tidy never touches them.
- **Known limit:** changing the payroll cutoff day is retroactive for where joiner and leaver reminders and SQL documents dated near the change are filed, filed months included. The setting says so; a proper fix needs effective-dated settings (later).
- **Independent review:** 19 findings, 14 confirmed and fixed (12 after merging): filed months changed by advances, stop and use (and by any save when a month was filed early); Tidy deleting from filed months; the cash book change moving past months' SQL listing (now locked once a month is filed); stopped accounts re-attributing past no-account payments; two cash books, or a USD one; stopping an account recurring payments use; receipts as a default type; an empty account crashing the save; new companies defaulting to "not in SQL"; the page left on the old cycle after the cutoff day changed; the organisation name that couldn't be cleared. Plus, found while building: `with db.connect()` holding the write lock (now released), and "trail started" misread on a records.db that was empty when the trail began.
- **Tests:** `synthetic_tests/setup_test.py` 52/52, `trail_view_test.py` 36/36, `audit_trail_test.py` 38/38. Local `tests/`: 19 pass (b3's Tidy call now sends a reason); the same 4 fail as before this work. Browser check on made-up records: companies (edit, stop with a reason, use again), general settings (name, cutoff day), bank accounts, recurring payments (salary advance 3,000 → 2,750 with the card and history), new-company defaults; no console errors.

### Phase 4 status (12 Nov 2026)
- **Built:** payment types, document types and required documents kept in the records instead of `rules.py`. `hrp/rulebook.py` reads them (cached per connection, frozen to `rules.py` below update 20) and answers what the code used to look up: labels, money in or out, legal deadlines, plurals for Next up, document labels and pack order, and the documents a payment needs for its month and company. Update 20 (`rulebook.install`) creates `payment_types`, `doc_types` and `required_sets`, seeds them from `rules.py` (recorded in the trail as added), and checks every answer against `rules.py` before it is kept. Setup gains **Payments and documents**: Payment types, Document types and Required documents. Required documents are set from a payroll month on (owner decision), for every company or one company (its own set wins; it can follow every company's again); the months before keep their sets and filed months never change. The pickers offer only the types going the chosen way (money in or out).
- **Equivalence proof:** `synthetic_tests/masters_equivalence_test.py` builds the same made-up records on the code before this phase (the golden snapshot) and on this code, stopped at update 19 and run to update 20: statuses, flags, Next up, audit pack contents, reports and refusals are identical (40/40).
- **Rules taken:** the types and documents the code relies on can't be deleted and have their keys locked; salary, director, statutory, receipt and other can't be stopped; of the seeded document types only claim form and payslip can be stopped (the monthly checklist asks for the rest). A document type can't be stopped while a set reaching an open month requires it. A payment type's legal deadline is locked once a filed month has payments of that type; the type new recurring payments start on (General settings) can't be stopped or deleted. Payments made from bank lines and SQL vouchers keep only a type in use going their way (else Money received or Other payment). A payment added by hand keeps the money in / out it is posted with, as before, and takes its type's when none is sent; changing its type to one going the other way is refused.
- **Known limits:** the monthly checklist, its payment rules and the joiner and leaver reminders are still in `rules.py` (Setup says so); the words that guess a voucher's type stay in code. Legal deadlines are not dated: changing one is refused once filed months used it, rather than dated like required documents.
- **Independent review:** 19 findings, 13 confirmed and fixed (9 after merging): stopping a document type an open month still needed through a set that had ended; checklist documents (approval, portal, payroll summary) stoppable; legal deadline edits re-judging filed months; payments from bank lines and SQL vouchers taking stopped, unknown or wrong-way types; a manual payment's type changed to one going the other way; the default recurring type stoppable (and then shown as its raw key); the Required documents month picker refusing open months before the current cycle; Add a payment switching back to Paid out on the recurring default instead of a claim. Found while building: internal document types (statement, reconciliation, SQL listing) offered as required documents.
- **Tests:** `synthetic_tests/types_test.py` 40/40, `masters_equivalence_test.py` 40/40 against the golden snapshot, `setup_test.py` 52/52, `trail_view_test.py` 36/36, `audit_trail_test.py` 38/38 (the new tables excluded from "changes no record"; every seeded row must be in the trail). Local `tests/`: 19 pass; the same 4 fail as before this work. Browser check on made-up records: Required documents (Approval for Salary from December: November unchanged, December needs it), internal types not offered, pickers by direction, a new money-in type kept, Add a payment's default type; no console errors.

### Phase 5 status (12 Nov 2026)
- **Built:** the monthly checklist, the joiner and leaver reminders and the matching words kept in the records instead of code (update 21, `hrp/checklistbook.py`, frozen to the old constants below 21). Each company's checklist is a set of items (a code that never changes and how the item is shown done: by hand, by the month's payments, by the bank statements, by reconciliation, by the audit pack) with dated wordings: due date, title, detail, documents, whether Next up shows it as a deadline and under what name it is submitted, and for a payments item which payments and documents show it done. A month set up gets the items in force for it; an item is judged by the wording in force for its own month, so filed months keep their rules. Reminders are dated by the month of the person's start date or last day. Setup gains **Monthly work** (Monthly checklist, per company, with Copy from another company; Joiner and leaver reminders) and **Matching words** (payment type guesses for SQL vouchers, salary words for SQL matching, SQL documents filed on the checklist). Every change is previewed first, applies from a chosen month (default the earliest month not filed), keeps changes planned for later months, brings the months already set up into line (un-ticked items only) and is refused if it would touch a filed month. Next up reads its deadlines, the combined Submit row, reminder names and the statement and closing due dates from the checklist; `/api/meta` gives the reminders and checklist codes. `hrp/monthly.py` holds the Setup logic.
- **Equivalence proof:** `synthetic_tests/checklist_equivalence_test.py` compares the code before this phase (golden snapshot) with this code at update 20 and after update 21, including months opened after the update, reminder moves from payee saves, Next up, SQL filing, salary-word matching and type guesses: 81/81 identical. The Phase 4 proof still passes (40/40).
- **Rules taken:** words aren't dated (they act on SQL imports from then on; nothing filed is filed again). The app's own checklist items and reminders can't be deleted (stop them instead); the statement, balanced records, reconciliation and audit pack items are built in, one each per company. Codes of new items come from their title. Approval, acknowledgement and payroll summary can be stopped again once no checklist or reminder in force asks for them. A checklist item due after the cycle's rollover day stays in its month (from update 21; only reminders wait for a later month). A submit row shows the statutory legal deadline only for KWSP, PERKESO and e-PCB.
- **Known limits:** a fresh company added in Setup starts with no checklist (copy one or add items). Bank wording (charges, own transfers) stays in code. A reminder waiting for a later month may still sit in the latest month set up even when it is filed, as before.
- **Independent review:** 18 findings, 17 confirmed and fixed (16 after merging): a change from a month deleting later planned changes; the drawer editing the latest wording instead of the one in force at the chosen month, and its Stop / Use again buttons; stop, use and delete accepted without a reason; the app's reminders deletable; use or change refused before an item's first month; no size limits on a rule's names; an emptied Order crashing a word rule's save; stopped items still blocking a document type's stop; History not showing an item's or reminder's changes; the trail's 'kind' label; the waiting rule changed below update 21; a company's own submitted item shown with the statutory legal deadline; built-in items doubled in Next up as deadlines; the page's limits differing from the server's; the word lists' help never shown.
- **Tests:** `synthetic_tests/checklist_test.py` 63/63, `checklist_equivalence_test.py` 81/81, `masters_equivalence_test.py` 40/40, `types_test.py` 40/40, `setup_test.py` 52/52, `trail_view_test.py` 36/36, `audit_trail_test.py` 38/38 (the new tables listed as update 21's own). Local `tests/`: 19 pass (Next up keeps its old constant names as aliases); the same 4 fail as before this work. Browser check on made-up records upgraded from update 20: the checklist list, a change previewed and saved from December (November keeps its wording), a stop planned for January shown as "Stops from Jan 2027" with Stop / Use again following the chosen month, edits kept when the month changes, reminders and words sections; no console errors.
### Phase 6 status (12 Nov 2026)
- **Owner decisions:** build now and enter the lists later, by hand or by pasting a text export from SQL Account (the chart of accounts can't be exported from SQL as XML); a recurring payment that isn't a salary or director's fee may be linked to a supplier or customer, by choice only. The sample cash book export carries no customer or supplier code (CODE), so matching by code takes effect only for listings that carry one.
- **Built:** update 22 (`hrp/partybook.py`): customers and suppliers (`parties`, for one company or every company, with SQL code, TIN, BRN and control account) and each company's chart of accounts (`gl_accounts`, with type, special account and parent), both in Setup with **Paste a list**: tab, `|` tables, `;`, comma, fixed-width text and SQL Account grid copies, columns guessed from headings or shown for choosing, previewed, added or updated by code, never stopped or deleted, empty cells never clearing a field, one activity line per paste. A recurring payment can be linked to a supplier or customer. SQL imports keep an entry's code, payment method, cheque number, document key and currency when the listing has them; a voucher carrying the code of the supplier or customer a payment's recurring payment is linked to counts as naming that payment; an SQL filing rule can name a customer or supplier, whose code files a document before any words. `/api/meta` gives the parties.
- **Rules taken:** an SQL code is unique among the parties a company sees; an every-company party may have one only while the companies share one SQL Account database (and a company can't then take a different database); the SQL code is locked once SQL entries carry it, the scope once anything uses the party, a GL code once anything refers to it; a party's kind can't change against the recurring payments linked to it, and a paste never changes it. Bank statement matching is unchanged (bank lines carry no codes).
- **Equivalence:** both earlier proofs still pass with update 22 (40/40, 81/81); they now compare table rows by the columns that existed before the remaining updates and check added columns are empty, and the Phase 5 proof leaves out the five column pickers update 22 adds to the SQL page.
- **Independent review:** 19 findings, 15 confirmed and fixed (12 after merging): deleting a company with only parties or GL accounts crashing; chart pastes refusing SQL Account's plural type names and unreadable optional values failing whole rows; a child account before its parent refused; an every-company code left ambiguous when companies take separate databases; a paste turning a customer into a supplier; a comma inside a name saved into the wrong fields; a stray quote or very long line crashing the reader; a party-named filing rule not taking precedence over words; the paste preview hiding the server's message and allowing Save; stale previews after changing scope, kind or columns.
- **Tests:** `synthetic_tests/parties_test.py` 72/72 (51 at first; printed reports and update 23 added 13 Nov); `checklist_test` 63/63, `types_test` 40/40, `setup_test` 52/52, `trail_view_test` 36/36, `audit_trail_test` 38/38, both equivalence proofs. Local `tests/`: 19 pass; the same 4 fail as before this work. Browser check on made-up records upgraded from update 21: customers and suppliers list, a pasted list previewed and saved, the supplier picker on a recurring payment (hidden for a salary), the link shown in the list, a paste the page can't read refused with its message; no console errors.
- **Printed lists (13 Nov 2026):** the owner's chart of accounts export is a report printed to a text file, not a list: a page header and the heading row on every page, each page shifted a few places, group headings with SQL's type, sub-accounts printed further in, totals at the end. Paste a list now reads such a report page by page (each cell goes under its own page's heading), leaves out page headers, group headings and totals, and gives a Parent column from the indent. SQL Account's short type codes (FA, IV, OA, CA, CL, OL, LT, CP, RV, RE, AP, SL, SA, OI, EO, CO, EP, TX) and special codes (BA, CH, DC, CC, AD, DP, BS, OS, CS) are known. The chart now keeps cash, accumulated depreciation, deposit / prepayment and the three stock accounts as special types: **update 23** remakes `gl_accounts` with the wider check where update 22 made it narrower, keeping every row and id; it drops only that table's own capture triggers, so the refresh after the step puts them back and start-up finds none missing. Checked on the real export (layout only): 5 pages, 157 accounts, 13 sub-accounts, no row with a problem. An independent review of the reader (12 findings, 7 confirmed, 5 distinct, all fixed): figures with thousands commas made a printed listing read as a comma list; a lined-up list with one odd line was taken for a report and lost the line; a paste starting mid-page lost the accounts above its first heading row; a figure right-aligned under a shorter heading joined the name; a page header without its page break cut a sub-account from its parent.
- **Tree view (13 Nov 2026):** the chart of accounts shows as a flat list or a tree (the choice kept in the browser). **Update 24** gives each account SQL Account's account group (`gl_accounts.sql_type`: its A/C Type FA, IV, OA, CA, CL, OL, CP, RV, RE, LT, SL, SA, CO, OI, EO, EP, TX, AP), taken from a pasted chart's type column; the type follows the group, and a different type is refused while a group is set. The tree has SQL's groups as headings in SQL's order (accounts without a group under their type), each account under its parent account; every heading and parent opens and closes, with Open all and Close all; a search shows the accounts found with the ones they sit under.
- **Still to do:** check the paste reader against SQL Account's Maintain Customer and Supplier lists (layout only).

### Phase 7 status (13 Nov 2026)
- **Owner decisions (13 Nov 2026):** a pack rebuild is a "what changed since this pack was built" report and a file fingerprint check, and each pack build records what built it; a deleted Setup record can be put back; real names leave tracked seeds and wording, and every company added gets a generic starter checklist; Setup exports as a generic template or in full, imported only into a new install.
- **Part 1, names and the starter checklist:** the sister company's legal name, the office tenant's trading name, the group brand line, the named utility and telco suppliers and the comment-only traces (a fund requisition, transfer amounts, doc numbers, name stems, a consultant's name word) are gone from tracked files (checked against the values at the commit before, read into memory and never printed). The frozen per-code lists in `rules.CHECKLIST` and the filing words keep their structure with made-up names of the same length (Northwind International, Contoso Cafe), so older records and the equivalence proofs behave as before. The utility guess words are generic (electric, water, internet, broadband, telco, telephone). The page's sidebar line starts empty and update 19 no longer writes a brand: the organisation name is typed in Setup. Old git history keeps the names (accepted).
- **New install seeds:** update 21 seeds SQL filing words only for the codes a company's checklist has or the starter checklist brings (`checklistbook._filing_codes`), so a new install gets only the payroll journals rule; a company from seed.json with a code of `rules.CHECKLIST` gets that code's rules (`checklistbook.seed_filing`). Update 13 no longer indexes `rules.CHECKLIST` by a company code (`db.SELFBILLED_DUE`).
- **Starter checklist:** `rules.STARTER` (the first company's list without the related company's fund and the tenant's rent, worded for any company; same codes, so payments, statements and the audit pack show items done as before). `masters.create` gives a company added in Setup that list in the same audited change (or its code's list in `rules.CHECKLIST`), not built in, so every item can be changed, stopped or deleted; a company not in SQL Account gets it without the SQL vouchers item. Until a month is set up with it, "Copy from another company" replaces it (`monthly._replaceable`). Deleting an unused company now removes its own checklist and required-document sets in the same change (it failed with a foreign-key error before).
- **Equivalence:** both proofs pass against their goldens (43/43 and 83/83) with a documented allowance by key: each old name is read from the golden at a known place (the fund-received title, the October utility and consultant payments, two vouchers' descriptions) and masked as its new made-up name is; the guess inputs that named real suppliers are compared by the type guessed only, and the first company's budget item's detail not at all.
- **Tests:** new `synthetic_tests/extras_test.py` (21 checks: a new install's seeded words and settings, the starter checklist on a company added, its months, copying over it, deleting a company with it).
- **Local tests:** three of the local tests on real records (status, checklist, Next up) look for the old wording and words of the first two companies' frozen checklists, which a records folder made from seed.json still gets; they pass with only those seed values put back (in memory, for the check). They need the made-up wording, or the real names typed into that records folder's Setup.
- **Part 2, Setup export and import (decision 4):** **Setup › General › Move setup** saves `setup.json` (`hrp/setupfile.py`; `GET /api/setup/export?what=template|full&payees=0|1`, logged as an opened file): format `hrp-setup`, version 1, `records_version` = the records' update number. A template holds the rules only (general settings without the organisation name, payment and document types, the sets of required documents for every company, a starter checklist with no company: the chosen company's items in force now, else the one new companies get, the reminders, the matching words; filing words only for the starter checklist's items, without a customer or supplier). Everything adds the companies, bank accounts (with their numbers, and the file says so), charts of accounts, customers and suppliers, each company's checklist with its dated wordings, and the company sets; recurring payments and salary advances only when ticked, with a personal-data warning. No ids: companies by code, types and reminders by key, GL accounts by company and code, bank accounts, customers and suppliers and recurring payments by a ref local to the file.
- **Import:** `POST /api/setup/import` through `_setup_call` (a preview makes it and undoes it), shown in the trail as source import with its reason. Refused unless the records hold no company data (companies, accounts, recurring payments, customers and suppliers, GL accounts, checklist items, months, checklist items in months, payments, documents, statements, SQL imports, budgets), for an unknown format, a newer version or a newer records version, an unknown list or field. Types merge by key onto the update steps' rows through `masters.update`/`create` (the code keeps its system flags and locks); the sets of required documents and the word lists in the file replace the seeded ones; reminders merge by key, their wordings replaced. Every row goes through Setup's own checks (`masters._checked`, `_unique_code`, `_gl_check` with parents first, `_party_check`, `_word_check`, `payee_check`, `advance_check`, `monthly._term_fields`/`_people_fields`, `appsettings.check`), dated wordings and sets must not overlap, and whether a record is in use is set last; any refusal or SQLite integrity error undoes the whole import. Settings are reloaded after every call, so a preview leaves no trace in them.
- **Starter checklist kept:** a file's starter checklist is stored in `app_settings` under the hidden key `starter_checklist` (`checklistbook.STARTER_KEY`; General settings doesn't show it), so no update step was needed; `checklistbook.seed_company` reads it before `rules.STARTER` for a company added later, and a company imported without a checklist of its own starts with it.
- **Tests:** `synthetic_tests/extras_test.py` now 37 checks, plus 15 and 19 in two fresh installs it starts (`--import`): template and everything exported from made-up records, each imported into a new install whose own export must match (rules compared as Setup keeps them), refusals (records in use, newer version or form, a key or company twice, bad references, a late refusal) leaving nothing, the preview leaving nothing, the trail entry. Checked in a browser on made-up records too.
- **Limits:** the template keeps the update steps' types and reminders the file doesn't name (merge, not replace). A full import gives a company without a checklist in the file the starter checklist, so its re-export differs there. The UI offers import only while the records hold no company.
- **Part 3, put back a deleted Setup record (decision 2):** `hrp/restore.py`. **Put it back** is offered on a delete in the Audit trail (an entry's change, a record's History) and under **Show deleted** in each Setup list (the generic lists, Monthly checklist, Joiner and leaver reminders, Recurring payments). It opens a drawer with a preview (`POST /api/setup/restore/<audit_row id>` with `preview`, through `_setup_call`, so nothing is kept), then asks why. `GET /api/setup/restore?kind=&entity=` lists a section's deletes made in this app (entries of source user, auto or import) and not put back, each with why it can't be put back now, if it can't.
- **How:** a put back is chosen by the trail row of the delete, never by the key (ids are reused). The before image goes back in with the columns the table has now; the same id when free, else a new one (the rows deleted with it follow it). Children come back from the same entry: a payment type's sets of required documents, a checklist item's and a reminder's wordings, and a company's own checklist and sets (deleted with it since Part 1); a company's checklist item deleted with the company is put back only with the company. An event (`restore`, in the same entry) names the delete's entry and row: History shows "Put back from entry N" (with a link to the history under the other number when it came back with a new one), the delete shows "Put back in entry N", and a second put back of the same delete is refused.
- **Refused, with a plain reason (409):** a code or key taken now (Setup's own checks: `_unique_code`, `_party_check`, `_gl_check`, `payee_check`), its company, parent account, payment type, document type, checklist item, customer or supplier or bank account gone, another checklist item in use with its title, a delete made outside the app (even once accepted), a record below the update that made its table. An `IntegrityError` in any Setup change is now a refusal, not a 500.
- **Invariants kept:** a cash book put back after another account took over comes back as not the cash book, with a note (an MYR account put back into a company with no cash book becomes it); a recurring payment fans out like one added (`db.sync_payee(c, None, new)` and `sync_reminders`); a checklist item is brought into its company's open months (`monthly._bring_into_line`) and a reminder to the people it reaches, and `_keep_filed` refuses any change to a filed month; the rulebook and checklist caches are forgotten. Sets of required documents naming a company, payment type or document type gone since are left out, with a note.
- **Delete of a company with its own checklist:** the 500 the map found (no count of `checklist_items` and company `required_sets` in `USES["entities"]`) was already gone with Part 1, which deletes a company's own checklist and sets with it while no month uses them. Part 3 keeps that (refusing would make every company added in Setup undeletable, as each now gets a starter checklist) and puts them back with the company.
- **Tests:** new `synthetic_tests/restore_test.py`, 46 checks: each kind put back (payment type with its sets, document type, guess words, customer or supplier, company with its checklist and sets, GL account, bank account, checklist item, reminder, recurring payment), id taken (new id, history linked), key or code taken, company or payment type gone, children, the cash book note, payee and reminder fan-out, a filed month untouched, previews leaving nothing, a reason asked, a second put back refused, an outside delete refused, the trail checking out and replay clean. All synthetic tests and both equivalence proofs pass (43/43, 83/83); the local tests are as after Part 2 (the three named above still fail, with or without Part 3, plus the four known).
- **Limits:** salary advances, required-document sets on their own and General settings are not put back (an advance comes back by adding it again). Show deleted lists at most the newest 200 per section. A record deleted before the trail started, or by an update step, can't be put back.
- **Part 4, Check this pack (decision 1):** `hrp/packcheck.py`, `GET /api/audit-pack/check` (by the pack's trail row, `?event=`, or by `?entity=&month=&file=`). It reads only: no entry is written. **Check this pack** on each pack under Recent packs opens a drawer with the result; each change opens its trail entry in place.
- **What a pack records now:** the pack event (`app._pack_event`, for **Build audit pack PDF** and the auditor package) keeps company, month, file, SHA-256 and size as before, plus `auditpack.build`'s `built`: `code_commit` (read from `.git`'s files, None without it; never fails), `code_files` (SHA-256 of the program's `hrp/*.py`, taken when the app starts, so it also tells apart changes not committed), `python`, `fpdf2`, `pypdf`, `today` (the day the statuses were worked out on), `generated` (the line printed on the cover, to the minute; build now takes the time once for it) and the `trail_entry` and `check_code` printed. The event's own `audit_row` id is the cut-off for an exact rebuild later. No schema change.
- **The file:** unchanged, changed (fingerprint differs), missing (the trail still has it, and Recent packs still lists it with **File missing**) or not recorded (a pack file with no event: built before the trail recorded packs).
- **What changed since:** the trail's rows after the pack's row, not those of its own entry, for its company and month: payments of the month or paid in it, their documents and those of the month's checklist items and statements (not SQL listing copies or the pack item's), checklist items (not the pack item), statements and their lines, SQL entries linked to its payments or items, the month row, required sets and checklist wordings whose months reach it and checklist items, payment types, document types and general settings, the company and its accounts, and later packs of the month (counted apart). Shown with `describe_row` and `headline`, grouped and counted (50 listed per group), outside and late rows marked. Its documents' files now are checked against their upload fingerprints.
- **Said plainly:** whether the PDF would come out differently is not known; a program or library update since (by `code_files`, else the commit) or a pack recorded before this part means a rebuild could differ; statuses were worked out on the day built; indirect changes (recurring payments, SQL entries not linked, book openings) are not listed; a change found by the trail check is dated when found. For a pack recorded before this part, the trail entry and check code on its cover are worked out (the entry before its own); for a file with no event the cut-off is the last row before the file's time on disk.
- **Tests:** new `synthetic_tests/pack_check_test.py`, 34 checks: the new event fields and their match with the cover's text, nothing changed right after, a payment and documents changed after (another month's and company's not), a general setting, a change made outside the app, a later pack, the file altered (changed) and deleted (missing, still listed), a pack file with no event, an old-style event, another program version, refused names and events, the auditor package. All earlier synthetic tests and both equivalence proofs still pass; the local tests are as after part 1 (19 pass, the 4 known failures plus the three of part 1).
- **Not done:** the exact rebuild itself (a scratch database folded from the trail up to the pack's row, built by the recorded commit) and a code-independent digest of the inputs; a re-check of the documents as the pack used them (only their files now are checked).
- **Review (two rounds, each finding reproduced on made-up records, then fixed and re-checked):** a company added in Setup (or imported without a checklist) gets the starter checklist whatever its code; the per-code lists are only for update 21 and seed.json, and a full setup file carries each item's built-in flag (kept only for a code in that company's frozen list). The import refuses impossible dates (`masters.is_day`, also for the payee form), a malformed header, settings of the wrong shape, two items in use with one title, active recurring payments on a stopped account and stopped document types still asked for by a wording or set with no end; `_setup_call` undoes any failure before the settings are reloaded. Setup's own title check now looks at later months too, so it refuses what the import refuses.
- **Put back, ids reused:** a record whose company, bank account or customer or supplier was deleted after it is refused even when another record has taken that id since (`restore._same`, iterative, its chain read once per list); when the parent came back under a new id the reason says so. A recurring payment put back onto a stopped account, and a wording or set asking for a document type stopped since (reaching an open month), are refused or left out with a note.
- **Check this pack:** the auditor package records the pack it built (not the newest file by time); an event id must be ASCII digits; another month's payment paid in the month counts only for the fields the reconciliation prints (with the SQL voucher number and month); finding the commit can never stop the app starting.
- **seed.json names:** the frozen lists hold made-up names for the related company and the tenant (`rules.PLACEHOLDERS`). A seed.json may give the real ones (`"names": {"Northwind International": "...", "Contoso Cafe": "..."}`); `checklistbook.fill_names` writes them in as given and in capitals in the matching words, in two passes so a name holding a placeholder's words stays as given. Without them a new install from an old seed.json gets the placeholder words, which never match: a reinstall should use Move setup › Everything or a seed.json with names. Two of the three local tests above pass again with the names; the checklist one also looks for other wording made generic and needs updating.
- **Copy from another company:** replaces a company's list only while it is still the untouched starter list it was given and no month is set up; any other list is copied onto as before (refused where items are in use in the start month), keeping the company's own items. Titles are checked over the months each item will be in use, for a change, Use again and a copy alike.
- **Tests now:** extras 72, restore 82, pack_check 43; the proofs 43/43 and 83/83; the local suite fails only the four known tests and the three above.
