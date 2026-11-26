# Before the build: checks on the code and the design, and the build in stages (19 November 2026)

This note sits beside the build plan, `docs/design/2026-11-19-redesign-build-plan.md`, and does not replace it. The
plan still describes each slice: its boards, screens, server work and tests. This note does three things:
- it records what was checked before any code is written, and what was found;
- it lists the corrections the plan needs;
- it sets the order of the build as stages, each with an entry gate and an exit check.

Nothing in the app was changed by these checks.

---

## 1. What was checked

| Check | How | Model |
|---|---|---|
| The design's own tools | `node design/tools/check_imports.js design/canvas --strict` and `check_board.js` on all 92 boards | run directly |
| The plan's claims about the server, slices 0 to 10 and sections 4.1 to 5 | Read `hrp/` against every concrete claim, with file and line evidence | Sonnet |
| The stage 1 fixes (section 4.1) and the HR and payroll claims, slices 11 to 15 | Read `static/app.js` and `hrp/` | Sonnet |
| The front end for slice 0 | Read the structure of `app.js`, `app.css`, `index.html` and `theme.js` against the shell boards and the motion and keyboard spec | Sonnet |
| The plan against the scope, the boards, the sweep and the test names | Board coverage, scope section 10 and the Decided table, sweep-k, dependencies | Sonnet |
| Test baseline | Every file in `synthetic_tests/` and `tests/`, run from a scratch copy with `HRP_DATA_DIR` set | Haiku |

## 2. Verdict

**The design is complete and buildable, and the plan's shape is sound.** All 92 boards pass the checkers: 2,969
imports with 0 problems, and only the two known board-script warnings (Sql and SetupChecklist), which the plan already
lists as "not app behaviour". Every board belongs to exactly one slice or to the reference and deferred list
(79 + 13 = 92). Every scope item maps to a slice, to stage 2 or to the phone deferral. No slice depends on itself in a
loop.

**What the checks changed:**
- **One safety fix goes first.** It must be made before any slice's tests run (3.1 below).
- **Six local tests fail today** (3.4). All 36 committed synthetic tests passed at the start (38 now, with the two added in stage 0). The local failures must be sorted out
  before slice 0, or no slice can meet the plan's "existing tests pass" rule.
- **Slice 0 is bigger than the plan says.** Today the app has no addresses at all, so it is cut into six smaller
  steps (5, stage 1).
- **22 facts in the plan are out of date or incomplete** (section 4). None changes a slice's boards. A few change
  its server work.
- **Four owner questions were answered on 19 November** (section 6). Plan decisions 3 to 6 stay open for stages 4 to 6.

---

## 3. Findings

### 3.1 Safety: the settings file is shared with the real app (fix before any slice)

`hrp/config.py` always reads and writes `settings.json` in the program folder. `HRP_DATA_DIR` moves the records, but
not this file, which holds the records folder, the backup folder and the SQL exports folder. A test that saves a
setting (`save_settings`) therefore writes the live PC's `settings.json`. A Fetch test can also read the real SQL
exports folder that file names. The test baseline was run from a scratch copy of the program for this reason.

**Fix (stage 0, before slice 0):** when `HRP_DATA_DIR` is set, keep `settings.json` in that folder instead, or read a
separate `HRP_SETTINGS_FILE`. The real app's settings must never be touched by a test. Add a synthetic test that a
settings save under `HRP_DATA_DIR` leaves the program folder's file alone. This is one small change with one test.

### 3.2 The front end today (affects slice 0)

- **No addresses.** `app.js` keeps the page, company, month and tab only in memory (`state.view`, `state.entity`,
  `state.month`, `state.mark`, `state.books.tab` and so on). `render()` is an if/else chain. There is no `location.hash`
  and no history, so Back and Refresh lose your place today. The plan's addresses (`#/CODE/2026-10/page/state`) are new
  work, and every `go()` / `goTo()` call (about 32 uses of `state.view`) and the server's Next up `go` objects must be
  moved onto them.
- **One file, one scope.** `app.js` is 4,722 lines of classic script with one shared `state`, about 15 document-level
  listeners and one delegated click handler (lines 4159 to 4580) that knows every page's ids. Setup alone is about
  1,300 lines. Splitting it is safe if the parts stay **classic scripts loaded in order** (no `type="module"`). Top-level
  constants that call into other files at load time (`LT`, `SORTS`) set the load order.
- **No dialog component.** Every form uses the one `#drawer`. "Discard your changes?" is the browser's `confirm()`.
  Escape closes the drawer, but there is no focus trap, no focus return, no `role="dialog"`, no reduced-motion rule and
  no arrow keys on tabs.
- **CSS.** The tokens are in `:root` (lines 2 to 9). The dark values are written out twice, under
  `prefers-color-scheme` and under `[data-theme=dark]`. The breakpoints (860, 700, 640, 520) are as the plan says. The
  fonts in `static/fonts/` are not linked yet. Roughly 70% of the page rules survive, restyled.
- **Every current page has a new home.** `overview`, `entity` (the register and the checklist, split in slice 2),
  `budget`, `payees` (Recurring, which holds the advances until slice 14), `payroll`, `bank`, `sql` (and its MyInvois
  part), `books` (and its parties and statutory tabs), `audit`, `trail`, `settings` (Backup) and `setup`.
- **Only three local tests look at the front end** (`smoke_test`, `b5_frontend_test`, `n5_next_ui_test`). A missed
  function after the split would show as a blank page, not a failed test.

### 3.3 Stage 1 fixes (plan section 4.1): all but one still to build

Only Bank's "Confirm again" exists (`app.js:1037`, route `/api/recon/confirm-book`). It still has to be checked against
the board's wording. The other 15 are not done. Evidence is in `app.js` at the lines below.

| Slice | Fix | Today |
|---|---|---|
| 5 | Supplier invoices labelled in the preview | `app.js:2160` labels every invoice "Customer invoice"; `sqlimport.py:440` puts PI, SD and SC under the same kind |
| 5 | "Deleted in SQL" pill under Ignored | Not shown (`app.js:1588`); the date is in the row data |
| 5 | Check-table sections in words | Raw `bank` / `general` (`app.js:1496`); `BOOK_NAMES` exists at 1651 |
| 5 | Import toast sentence | No unfinished sentence found in the code; compare the toasts at `app.js:4372-4386` with the Sql board |
| 6 | Print month defaults to the month worked | Newest month (`app.js:2084`) |
| 6 | MyInvois times "1 Oct 2026, 11:19" | Raw ISO text (`app.js:2053`, `2058`) |
| 6 | Print note beside each PDF button | Not shown (`app.js:2072`) |
| 7 | Grey "Can't be totalled" pill; no pill on an empty trial balance | Two states only; `books.py:516` needs a third (unknown) |
| 7 | Excel failure shown in place | Plain link to a raw JSON error (`app.js:1756`) |
| 7 | Statutory check ignores months the journal doesn't cover | Only months before tracking are greyed (`statutory.py:390`) |
| 7 | One date style on Books pages | Three styles in use |
| 9a | Printed invoices and company names hidden when not kept in SQL | Shown for every company (`app.js:2912`) |
| 9a | "Open Setup" opens that company's drawer | Opens the list (`app.js:4393`) |
| 9a | Move setup "Everything" sentence | Misses statutory accounts, print settings and printed company names (`app.js:3232`); the export has all three |

### 3.4 Tests today

**The committed suite is green; the local suite is not.** All 36 files in `synthetic_tests/` passed (38 after stage 0). 17 of the 23 local
files in `tests/` pass and **6 fail**, each on both runs (not flaky):

| Local test | Fails at | Error |
|---|---|---|
| `b1_payments_test` | line 29 | AssertionError |
| `b3_sql_months_test` | line 169 | AssertionError |
| `b5_frontend_test` | line 252 | AssertionError |
| `b6_auditpack_test` | line 98 | AssertionError |
| `n12_recon_test` | line 188 | AssertionError |
| `n4_next_api_test` | line 445 | AssertionError |

All 23 local tests passed on 13 November. The six failing files were last edited between 5 and 13 November, and 22
commits have changed `hrp/` or `static/` since 13 November (stage 1, reconciliation, payroll check, statutory). They
are most likely out of date, not broken code, but that is **not verified**: their messages print real data, so they
are reported here only by line and error type. Plan rule 5 (existing tests pass before a merge) cannot hold until
they are sorted out, so this is stage 0 work.

**Sorted out in stage 0 (19 November).** Five were out of date, and the local test files were updated to the app's
deliberate changes (each traced to its commit): `b3` (one more checklist item, "SQL books agree"), `b5` (the removal
response gained a before-tracking list), `b6` (the audit pack gained three books pages), `n12` (a new count key and
the reworded fetch note), `n4` (the reworded rule 7 text). **One was a real app bug:** `b1`. Typing a voucher number
in a payment's SQL ref box made the SQL preview fail with a server error, because `sqlimport.payments_by_ref` did not
read the payment's month and dates that the before-tracking check (commit `80b74fc`) needs. Fixed in
`hrp/sqlimport.py`, with a committed test, `synthetic_tests/sql_typed_ref_test.py`, that fails on the old code.

**Still open:** every one of the 23 local tests copies `seed.json` from the real records folder into its own temporary
folder. That is a read of the real folder; it predates this work and was not changed. A later clean-up could make the
local tests use a made-up seed, as `synthetic_tests/` already do.

How the baseline was run: the project's `.venv` Python (the Python on PATH has none of the packages). Each file ran on
its own with a new temporary `HRP_DATA_DIR`, from a scratch copy of the program, with its own `settings.json` (see 3.1).
The copy must include `README.md`, `docs/` and `design/`, because `stage1_leftovers_test` reads `README.md`. About four
minutes in all.

---

## 4. Corrections to the build plan

All 22 corrections below were applied to the build plan on 19 November, after each was checked against the code. Where a
correction was wrong, the table now says so.

| # | Plan says | The code shows | Change in the plan | Slice |
|---|---|---|---|---|
| 1 | 123 routes | 128 | Say 128 | 1. Words |
| 2 | `/api/meta` gives each company's kind | The field exists as `entities.uses_sql` (0 or 1) | "Adds `kind`, worked out from `uses_sql`; no migration" | 0 |
| 3 | Next up rows carry their area | No area today; the nearest is `go.view` | New field on every row (`nextup.py` `_row`) | 0 |
| 4 | One Next up row per unpaid statutory payment touches `_statutory` and `_to_pay` | Rule 5 (`_to_pay`) already lists unpaid statutory payments; rule 14 comes from `statutory.next_up` (`statutory.py:529`), which returns late and short only | Name `statutory.next_up` too; the change is a de-duplication between rules 5 and 14 | 1 |
| 5 | Sign-off locks the month (as if new) | Today a changed line **removes** the sign-off (`recon.line_changed`, `recon.py:886`) | The lock replaces clear-on-change; list the tests that rely on the clearing and update them | 4 |
| 6 | Sign-off keeps a free note and Prepared by | `statements.reconciled_note` exists; `sign_off` sets it to empty; no Prepared by | Confirms the migration | 4 |
| 7 | Statutory kinds gain Net salaries payable and Zakat | `KIND_WORDS` has epf, socso, eis, skbbk, pcb, hrdf, other; the table has a `CHECK` on kind (`statutory.py:66`) | State that SKBBK and HRDF already exist; the migration **rebuilds the table** (SQLite cannot change a CHECK) | 7 |
| 8 | Customers overdue at 30 days: slice 1 changes the ageing | Ageing already has buckets (current ≤30, 31-60, 61-90, over 90, brought forward) | A sum of the 31-and-over buckets, small; decide whether brought-forward balances count (owner question 2) | 1 |
| 9 | Budget rules (4.3) | Payments up to the balance date: **already done** (`budget.py:75-94`). No-balance: **not handled** (a blank balance counts as 0 and reads "balance covers the budget"). The balance is also kept in the browser (`localStorage`). No bank label exists | Rewrite slice 8's server work: the no-balance state, the balance read only from the stored budget, and a new bank label from the company's account | 8 |
| 10 | Stage 1 fixes "may already be fixed" | Only "Confirm again" is | Use 3.3 as the list | 4-9a |
| 11 | Joiner reminders: change `rules.py` and `checklistbook.py` wording | The reminders live in the records (`people_tasks`, `people_task_terms`), seeded from `rules.PEOPLE_TASKS`; short names in `checklistbook.PEOPLE_NAMES` | The migration rewrites the stored tasks, terms and short names, and the Move setup `reminders` section; the merged reminder gets a new key with a 7-day term | 12 |
| 12 | {name} is the preferred name from the staff record | Today {name} is `short_name()`: the bracketed part of the payee name | Add a preferred-name field to the staff record, falling back to `short_name()` for payees | 12 |
| 13 | `cryptography` already in `requirements.txt` | True, but only pypdf uses it (encrypted bank PDFs); nothing imports it directly | Note that slice 15's payslip key is its first direct use | 15 |
| 14 | Company-code grep in every review | `rules.CHECKLIST` is keyed "AISB" and "AI" (`rules.py:92`, `125`): the documented fallback for records from before update 21 and for tests | Exempt `rules.CHECKLIST` from the grep. Keep it a fallback only: no new code may read it | all |
| 15 | Can run side by side: 13 beside 14 | Both add migrations | "Agree migration numbers before opening both" | 13, 14 |
| 16 | Slices that change `nextup.py`: 1, 7, 11, 12, 13, 15 | Slice 0 changes it too (area field). Slice 13 has no Next up work in its block | Add 0; for 13, add the work or drop it from the list | 0, 13 |
| 17 | Every new list has a many-rows state | The sweep accepted that six pre-scope boards (Setup, SetupCompanies, SetupParties, SetupChart, SetupMatching, SqlBooks) draw none | Name the exception, or build those states without a board | 9a, 5 |
| 18 | Needs-approval default (4.3) | The sweep (D12) names Salary, Director allowance, Rental, Consultant fee, Other payment, Staff claim, Salary advance, Payroll run. The plan adds Staff claim - overseas service, Inter-company transfer and "any type a company added" | Owner question 3 | 11 |
| 19 | Decision 1 (fonts) under "still open" | Decided and bundled | Move it to Closed | 7.1 |
| 20 | Routes and modules not named | `/api/open-payments`, `/api/export`, `/api/overview`, `/api/integrity`, `/api/statement-suggestions`, `/api/statement-lines`, `/api/audit/*`, `/api/auditor-export`, `/api/settings`, `/api/upload`, `/api/tasks`; modules such as `docstore`, `trail`, `finstatements`, `sqlgl`, `ledger`, `partybook` | A "stays as it is" list, so each slice knows what its page calls | all |
| 21 | Tests cited | All exist. Two local tests are never cited: `n8_payslips_test` (payslips and Next up: slice 15) and `n11_ui_extras_test` (list search: slice 10). Corrected 19 Nov: the first version also tied `n8_payslips_test` to slice 10, which the test does not cover | Add them to those slices' "Checked by" | 10, 15 |
| 22 | Phone deferral (18 November) | Recorded in the sweep and leftovers only; the scope's Decided table still says "Yes, fifth phone screen" | Add the deferral to the scope's Decided table | scope |

---

## 5. The build in stages

Each stage ends with a click-through by the owner. Each slice keeps its own branch and review, as the plan says. With
one reviewer, two slices are open at a time at most. "∥" means the two can be open together. Each pair was checked
against the plan's rules: no two migrations at once, no two `nextup.py` changes at once, no slice before its
dependencies, and 5 and 6 never together.

### Stage 0: Ready to build (before slice 0)
- **Work:**
  - The settings-file fix (3.1) with its test.
  - Sort out the six failing local tests (3.4). For each, decide whether the app changed on purpose (then update the
    test, locally) or broke (then fix the app, with a synthetic test). Report by line and error type only.
  - Fold the corrections in section 4 into the build plan.
- **Owner:** nothing outstanding. Question 1 is answered (keep today's sign-off rule).
- **Exit:** both suites pass (38 synthetic, 23 local), and a test proves that settings saves stay in the temp folder.
  This is the baseline slice 0a is measured against.

### Stage 1: The new shell (slice 0, cut into six steps)
One branch, `slice-0-shell`. Each step is reviewed before the next. Nothing else is open during this stage.

| Step | What | Visible change | Check |
|---|---|---|---|
| 0a | Split `app.js` into classic scripts: `static/js/core/` (util, api, state, ui, router, events), `static/js/pages/` (one per page), `main.js` last | None | The local front-end tests, a check that every page opens with no console error, and a click-through of today's app |
| 0b | Tokens (light and dark in one place), fonts linked, the 80-glyph sprite, buttons, pills, fields, reduced motion | The new look on the old layout | Contrast in both themes |
| 0c | The dialog shell (focus trap, Escape, focus return, `role="dialog"`, a styled "Discard your changes?" replacing `confirm()`) and the States patterns | Dialogs and empty, loading and error states | Keyboard-only walk |
| 0d | Addresses: `#/CODE/YYYY-MM/page/state`, a hash router replacing `render()`'s chain; `go()` / `goTo()` write the address | Back and Refresh keep your place | New synthetic test: every old page key opens its address |
| 0e | The shell: five-area menu, top bar, company and month switchers, breadcrumbs, badges; `/api/meta` kind and pages; Next up area; Coming soon pages, Kept here placeholders, interim landings | The new menu | Tests for the interim landings, the company-switch toast and the Kept here menu; phone width (375 px) |
| 0f | Payroll check moves to HR › Payroll › Workbook check; rule 15's target follows | One page moves | `payroll_check_test` unchanged |

**Exit:** a normal month's work done inside the new shell, then again at phone width.

### Stage 2: Month-end in the new face (slices 2, 8, 3, 5, 4, 6)
| Wave | Open together | Why this pairing |
|---|---|---|
| 2.1 | **2** Register and checklist ∥ **8** Budget and Recurring | Both need only 0. Neither adds a migration |
| 2.2 | **3** Payment dialog ∥ **5** SQL import | 3 needs 2; 5 needs 0. No migrations |
| 2.3 | **4** Bank and reconciliation ∥ **6** e-Invoices | 4 needs 3; 6 needs 5. Only 4 adds migrations |

**Exit:** month-end in the new face: register, checklist, a payment, a reconciliation and its printed statement, a SQL
fetch, an e-Invoice print, a budget print.

### Stage 3: Overview, Books and Admin (slices 1, 9a, 7, 9b, 10)
| Wave | Open together | Why this pairing |
|---|---|---|
| 3.1 | **1** Overview ∥ **9a** Setup | 1 needs 8 (done). 2 and 4 are merged, so only the Books links still use interim landings. 9a adds no migration |
| 3.1b | **0g** Shell loading fix ∥ **9c** Setup follow-ups (added 26 November) | Both fix what wave 3.1 left (see below). 0g owns `core/` and the pages outside Setup; 9c owns the Setup pages, First run and one argument in `core/topbar.js`. Neither adds a migration. Done before 3.2 so slices 7 and 9b build on the fixed page loader |
| 3.2 | **7** Books, parties, statutory ∥ **9b** Audit pack, trail, backup | 7 adds a migration and changes `nextup.py`, so it is kept apart from 1. 9b adds none |
| 3.3 | **10** Search, notifications, Undo | Needs 9a and 9b. It adds the events migration |

**Exit:** the whole redesign walk: light and dark, keyboard only, every card and its link.

#### Wave 3.1b, slice 0g: Shell loading fix (its own change, owner 26 November)
The known limits (a), (b), (c) and (e) to (h) in slice 9a's plan note. They are shared-code problems, so they are fixed
once in the shell, not inside a slice (round 8 of 9a showed that a page loader changed from inside a slice did harm).
1. **No page paints over a newer page.** Every page draw gets a render number from `render()` and checks it before it
   writes anything (markup, state, toasts). A draw that a newer one overtook writes nothing. Setup's own `viewSetup.n`
   is the model; after 0g Setup uses the shared number.
2. **No page is left on "Loading".** `render()`'s 300 ms skeleton no longer replaces a shell a page has already
   written, so Bank, Books, Customers and suppliers and Statutory payables fill the body they drew, whatever the
   read's time. Checked with every read delayed 300 ms, 900 ms and 1.5 s, on arrival, on a company switch and on a
   month change.
3. **"It was saved" after a kept write whose re-read fails.** Setup's `afterSaved` becomes a shared helper in `core/`,
   used by the payment dialog and register, the company page, Recurring payments, the SQL import page, Bank, Budget,
   the audit pack, the audit trail's accept and the click handlers in `core/events.js`. Its Try again only reads again;
   it never sends the write again. "Nothing was changed" is said only when the server refused the write.
4. **Start and api leftovers:** a 200 reply that is not JSON is an error, not `{}` (e); the month arrows do nothing,
   with no raw toast, while the start has failed (f); a network failure at start shows the stopped page's text (g);
   focus stays on Try again after a failed retry (h).
- **Tests:** a synthetic test that delays reads and opens pages out of order (A slow, B fast, A returns: B stays), a
  test per write-then-reread flow (kept write, failing re-read: "saved", no second write), and the slice tests as they
  are. Live click-through with slow reads.

#### Wave 3.1b, slice 9c: Setup follow-ups (owner answers of 26 November)
1. **Company switcher shows full names**, as CompanySwitcher.dc.html and Topbar.dc.html draw: `x.name` in place of
   `companyShortName(x)` in `tbCompanyHtml` (`core/topbar.js`); Setup's "Switcher:" line goes (`SETUP_SUB.entities`);
   `topbar_test` back to full names. The Short name field stays, for other uses.
2. **Matching words: the Move grip and "Try a voucher description"**, as SetupMatching.dc.html draws: drag (and
   keyboard: arrow keys on the grip) to reorder, saved as the Order field; a box to type a voucher description that
   shows which rule matches it and what it gives.
3. **First run's import reason:** the reason box is filled with "Started this install from <file name>." (editable),
   so the audit trail says what the screen showed. An emptied box gets the same sentence.
4. **Required documents matrix** (owner, 26 November: yes), as SetupRequired.dc.html draws, in place of today's table
   and side drawer: payment types down the side, document types across; click any boxes, each changed box marked
   "Changed, not saved yet", one Save applies every changed type from the payroll month picked (never a filed
   month), with Discard and the "Discard your changes?" prompt on leaving; For: every company or one company, a type
   one company has changed marked so, with "Follow all companies again"; Earlier sets per type; box sources (from
   SQL, from an approved form, posted here; for a company Kept here, SQL Account's own documents greyed as today).
   Under 700 pixels the grid scrolls sideways with the type names held in place. Approval boxes show the marker only:
   Approvals arrive with slice 11. The server's rules (`/api/setup/required`) stay as they are; a save of several
   types is one write with one reason, all or nothing, shown in the audit trail per type.
5. The Setup-only known limits of 9a's plan note: (j) `typed()` also counts a half-typed reason, (k) the checklist and
   reminders Add dialogs get a saved marker, (l) an Add dialog during a slow POST.
- Already as the owner wants, no change: the import preview counts the starter checklists (`setupfile._Import.more`).

### Stage 4: HR step 1 (slices 11, 12, then 13 ∥ 14)
- **Entry:** stages 1 to 3 merged. The needs-approval defaults are answered. QR reading was approved by the owner on
  16 November (plan decision 6): slice 11 picks the library (offline on Windows, licence checked) as a build check,
  not an owner question. A typed code is the fallback.
- **Order:** 11 Approvals and To pay, then 12 Staff (preferred name on the staff record, answered), then 13 Leave ∥ 14
  Claims and advances (migration numbers agreed first).
- **Exit:** a paper round trip (print a form, sign it, scan it, upload it, pay from To pay), then a joiner, leave, a
  claim from entry to paid, and an advance.

### Stage 5: Payroll (slices 15a, 15b, 15c, then the parallel run)
- **Entry:** the payroll checks in plan 7.1 (age-60 timing, Lindung 24 Jam bands, HRD Corp registration, 2027
  holidays). Plan decisions 3 (payslip email) and 4 (Maybank bulk file) are **on hold** (owner, 26 November): 15b
  does not wait for them. It builds payslips to print and download as PDF, and shows **Email payslips** and **Maybank
  bulk file** as Coming soon placeholders in their places on the boards. Each is built when the owner decides.
- **Exit:** two to three months of parallel run signed off, then the switch-over.

### Stage 6: Users and access (slice 16)
- **Entry:** the hosting decision (plan decision 5), **on hold** until the owner is ready (26 November). Nothing
  before stage 6 waits for it, and stage 2 of the books does not either.

---

## 6. Owner questions, and when each is needed

**Answered 19 November (owner):**
1. **Sign-off with items left: No.** Keep today's rule: the book closing must equal the bank closing. Plan decision 2
   is closed. The printed statement does not need a reconciling-items section for sign-off.
2. **Customers overdue: balances from before tracking do not count, and they should show as something else.** The
   Overview card counts only balances older than 30 days that are inside the tracked period. Brought-forward balances
   are shown apart, labelled "Before tracking" (not as overdue, not hidden).
3. **Needs-approval default: Yes** for Staff claim - overseas service, Inter-company transfer and any type a company
   adds.
4. **Preferred name on the staff record: Yes.** Used in reminders; the bracketed payee name is the fallback.

**Answered 26 November (owner):**
5. **Company switcher: follow the design** (full names). Slice 9c.
6. **Import preview counts the starter checklists: Yes.** Already built that way in 9a; no change.
7. **Matching words grip and "Try a voucher description": now.** Slice 9c.
8. **Required documents matrix: Yes**, in place of the table and drawer. Slice 9c.
9. **First run's default import reason: as suggested** ("Started this install from <file name>.", shown in the box).
   Slice 9c.
10. **Payslip email and Maybank bulk file: on hold**, with Coming soon placeholders in 15b.
11. **QR library:** already approved on 16 November; only the pick of the library is left, in slice 11.
12. **Hosting: on hold** until the owner is ready.
13. **Shell loading problems: plan the fix.** Slice 0g, wave 3.1b.

The table below is kept as asked.

| # | Question | Needed before |
|---|---|---|
| 1 | Bank sign-off with reconciling items left: keep today's rule (book closing must equal bank closing) or allow sign-off with the items listed on the statement? (plan decision 2) | Slice 4 (stage 2, wave 2.3) |
| 2 | Customers overdue: do balances brought forward from before tracking count as overdue? | Slice 1 (stage 3) |
| 3 | Needs-approval default: also Yes for Staff claim - overseas service, Inter-company transfer and any type a company adds? | Slice 11 (stage 4) |
| 4 | A "preferred name" field on the staff record, used in reminders, with the bracketed payee name as fallback? | Slice 12 (stage 4) |
| 5 | Plan decisions 3 to 6 as listed there: payslip email, Maybank bulk file, hosting, QR library | Stages 4 to 6 (26 November: 3, 4 and 5 on hold; 6 approved, library picked in slice 11) |
