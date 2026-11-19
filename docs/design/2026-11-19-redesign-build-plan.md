# HR Payments: building the redesign (plan of 19 November 2026)

This plan replaces `review/2026-11-14-redesign-build-plan.md`. That plan covered 52 boards in slices 0 to 7. The
design has since grown to the approved HR, Payments and Accounting scope, so the slices are re-cut here.

---

## 1. What this plan builds, and from what

**The design.** The redesign is finished as a Design canvas: **92 boards**, published as **version 79** at
https://claude.ai/artifact/FifhhSp76WmpJXqEpCeBJ9 (private to the owner). Every board and the layout
(`canvas.json`) are copied into this repository under `design/canvas/`; start with `design/README.md`. None of it is
in the app yet.

**Words used in this plan.**
- A **board** is one design file (`Name.dc.html`). Each board draws one page or part, in several **states** (empty,
  loading, an error, a filled form, and so on).
- A **slice** is one piece of the build, made on its own branch, reviewed and merged before the next depends on it.
- A **route** is an address the server answers (the `@app.get` / `@app.post` lines in `hrp/app.py`, 128 today).
- A **migration** is a numbered update to the records file that runs once (`MIGRATIONS` in `hrp/db.py`, at update 38
  today).
- An **address** is the part of the page link after `#`, for example `#/AISB/2026-10/payments/register`.

**Sources.**
- The approved scope, `docs/2026-11-16-hr-payments-accounting-scope.md`: section 1 (the Decided table, with the rows
  added 17 to 19 November), section 2 (menu and placements) and section 10 (order, screens, out of scope).
- The gap review, `docs/design/2026-11-17-redesign-scope-gaps.md`: sections 2 to 4, 6 and 7.
- The final design sweep, `docs/design/2026-11-19-design-sweep-k.md` (28 decisions, the owner's answers of 19 November,
  what is still open) and the leftovers list `design/notes/design-leftovers.md`.
- The app as it is: `static/app.js` (the `VIEWS` menu list and the `view…` page functions), the modules in `hrp/`, the
  local test files in `tests/` (gitignored, they hold real data) and the committed made-up-data suite in
  `synthetic_tests/` (38 test files).

**What it builds, in the owner's order.**
1. **The redesign build** (slices 0 to 10): the new five-area shell, every existing page moved to its new place and
   restyled, the stage 1 app fixes drawn on the boards, and the new features the owner kept.
2. **HR step 1** (slices 11 to 14): approvals and To pay, staff records, leave, claims and advances.
3. **Payroll** (slice 15): payroll run in the app, its outputs, the parallel run and the switch-over.
4. **Users and access** (slice 16): sign-in and access rights, with hosting. It is built when the owner decides
   hosting (section 7, decision 5), whenever that falls.

Stage 2 (books kept in hr-payments) comes after payroll, with its own design. It does not wait for slice 16 or for
the hosting decision.

**What is deferred.**
- **Phone design** (owner, 18 November). The five phone boards are not built and the fifth phone screen
  (MobileApprovalPhoto) was never drawn. Today's phone behaviour stays: the app's narrow-screen layout in `app.css`.
  See the ground rules for new pages.
- **Stage 2 pages.** Book a statement line (BankBookLine), and real Sales, Purchases, Journals and Period close pages.
  This plan builds only their placeholders.
- **Stage 2 states on boards built now.** Some boards built in this plan also draw what a Kept here company sees once
  it posts its own vouchers (a payment voucher "posted here", a journal voucher on a claim, and so on). Those states
  wait for stage 2. Each slice lists them under "Waits for stage 2", with what the app shows in their place.
- **Out of scope** as the scope says: attendance, recruitment, performance reviews, staff self-service, director
  logins before slice 16, benefits-in-kind valuation, foreign worker levy, sending files to government portals, and
  writing anything back to SQL Account.

---

## 2. Ground rules

Kept from the old plan:
- **Same server, new face.** Each slice rebuilds screens in `static/` (`app.js`, `app.css`, `index.html`). The routes
  and `hrp/` modules stay as they are, except where a slice lists server work.
- **Nothing breaks between slices.** Pages not rebuilt yet keep working inside the new shell, at their new menu place.
  Every slice leaves month-end work possible.
- **Real data stays out.** Every check runs on a temporary copy: `HRP_DATA_DIR` is set to a temp folder before `hrp`
  is imported. Nothing reads or writes `C:\HR-Records`. `tests/` and `samples/` stay local (they are gitignored
  because they hold real data); test failures are reported by line number and error type only.
- **Offline first.** The app works with no internet. The fonts are bundled in `static/fonts/` (decision 1 in section 7).

New:
- **Company differences are settings.** Nothing is fixed to AISB or any company code. Payroll, approvers, leave
  policy, public holidays, claim types and statutory accounts are per-company settings; the owner's main company is
  simply the first to use them. A grep for company codes in `hrp/` and `static/` is part of every review. One exception: `rules.CHECKLIST` (keyed
  "AISB" and "AI", `hrp/rules.py`) is the documented fallback for records from before update 21 and for tests. It stays
  a fallback only: no new code may read it.
- **The canvas is the spec; its sample data is not real data.** Build to the boards' layout, wording and states. Never
  copy the boards' names, figures or codes into the app, seed files or commits. Test data is made up, and every new
  person name is checked against the app's git history first (the "Soon" rule).
- **Phone is deferred.** No phone layouts are built. Today's narrow-screen behaviour (the `@media` rules in `app.css`
  at 860, 700, 640 and 520 pixels wide) is carried into the new shell, and new pages must still not break at phone
  width (no sideways scroll of the page). Where a new page cannot work at that width (a wide payroll table, say), it
  shows a short note in the wording of MobileDesktopOnly.dc.html ("best done on a computer"), not a phone design.
  Every slice from 4 on says whether it needs the note ("Phone note" in its block).
- **Tests use made-up data and are committed.** New tests go in `synthetic_tests/`, with made-up data, so they reach
  the slice branch for review. The local files in `tests/` are gitignored because they hold real data: they are still
  run before each merge (on a temporary copy), and are updated locally where a slice changes what they check, but no
  new test is written there.
- **Every new list has an Excel export** (the scope's Decided "Data" row): each slice that adds a list adds its
  Excel button, and its "Checked by" covers it.
- **English only**, on screens and on everything printed.
- **Branches and commits.** One branch per slice, named like the phase branches so far (for example
  `slice-0-shell`, `slice-11-approvals`). Nothing is committed or pushed unless the owner asks.
- **One migration chain.** Migrations are numbered in merge order. Only one open branch adds migrations at a time, or
  the later one renumbers before it merges.

**A slice is done when:**
1. every state on its boards can be reached in the app, with the boards' wording, except those listed under the
   slice's "Waits for stage 2" (they show what that list says) and those a later slice finishes;
2. every address a board links to (a tab or a filter, such as Approvals' "Paid without approval") opens that state,
   or, while the target's slice is not merged, its interim landing as named in the slice;
3. keyboard, focus and reduced-motion rules hold (Escape, focus trap and return, arrow keys, visible focus rings);
4. light and dark both pass contrast (4.5:1 for text, 3:1 for control borders);
5. the existing tests pass (`synthetic_tests/` and the local `tests/`), and new tests in `synthetic_tests/` cover
   every server change;
6. no company code is fixed in the code, and no canvas sample data is in the app;
7. every new list has its Excel export, and the page passes the phone-width check (no sideways scroll, or the note);
8. the owner has clicked through it on sample data and approved the merge.

**Synthetic tests run in every slice.** The whole `synthetic_tests/` suite runs before every merge. Each slice's
"Checked by" names the ones closest to its work. `seed_names_test` checks seed.json's placeholder names; it runs
wherever seeds or checklist names change (0, 9a, 12). It does not check sample person names against the app's
history: that stays a review step (the "Soon" rule above).

---

## 3. The slices

### 3.1 The order at a glance

| # | Slice | Phase | Boards | Size | Needs first |
|---|---|---|---|---|---|
| 0 | Shell and foundations, Payroll check moved | Redesign | 5 | L | nothing |
| 1 | Overview | Redesign | 2 | M | 0, 8 (Funds to request uses its Budget rules) |
| 2 | Payments register and Monthly checklist | Redesign | 3 | M | 0 |
| 3 | Payment dialog and Add payment | Redesign | 3 | M | 2 |
| 4 | Bank and reconciliation | Redesign | 4 | L | 3 |
| 5 | SQL import | Redesign | 2 | M | 0 |
| 6 | e-Invoices | Redesign | 2 | M | 5 |
| 7 | Books, Customers and suppliers, Statutory payables | Redesign | 6 | L | 5 |
| 8 | Budget and Recurring | Redesign | 2 | M | 0 |
| 9 | Admin: Setup (9a), Audit pack, Audit trail, Backup (9b) | Redesign | 16 | L | 0 (9a and 7 in either order) |
| 10 | Search, notifications and Undo | Redesign | 2 | L | 9a, 9b |
| 11 | Approvals and To pay | HR step 1 | 7 | L | all of 0 to 10 |
| 12 | HR staff | HR step 1 | 7 | L | 11 |
| 13 | HR leave | HR step 1 | 3 | L | 12 |
| 14 | HR claims and advances | HR step 1 | 4 | L | 11, 12 |
| 15 | Payroll (15a run, 15b outputs, 15c parallel run and switch-over) | Payroll | 9 | L × 3 | 12, 13, 14 |
| 16 | Users and access, sign-in, hosting | When hosting is decided | 2 | L | all before it, and the hosting decision |

Sizes: **S** is a page or two with little server work; **M** is a few pages or one real server change; **L** is
many pages or new tables and rules.

79 boards are built in slices. The other 13 are reference or deferred boards (3.2). That makes 92.

**Boards on more than one slice.** Each board belongs to the slice that first builds its page. Some of its states
need server work from a later slice (the Approval marker on the payment dialog, say). The later slice finishes those
states and lists them under "Finishes on earlier boards". Since slice 11 needs all of 0 to 10, every HR and payroll
slice can finish states on any redesign board.

**Interim landings.** A card, link or menu item whose target page is built by a later slice opens the named interim
landing until that slice is merged, then its real address. The slice that builds the target switches the link.

### 3.2 Reference and deferred boards (13)

| Board | Kind | Used by |
|---|---|---|
| Foundations.dc.html | Reference | Slice 0 (tokens, glyphs, components, card anatomy, pills, print block, addresses) and every slice after |
| DarkPalette.dc.html | Reference | Slice 0 (dark tokens) and every slice's dark check |
| States.dc.html | Reference | Slice 0 (empty, loading, error, many rows, refused, confirms, toasts) and every slice after |
| ShellMenus.dc.html | Reference | Slice 0 (menu for the three company kinds); slice 16 (menus by access) |
| CompanySwitcher.dc.html | Reference | Slice 0 |
| OverviewCards.dc.html | Reference | Slice 1, and the HR and Approvals slices that fill their cards |
| Company.dc.html | Reference: the source of the split | Slice 2. No board links to it; it can leave the canvas once slice 2 is merged |
| MobileDesktopOnly.dc.html | Deferred (phone); its wording is used for the "best done on a computer" note | Any slice that needs the note |
| MobileOverview.dc.html | Deferred (phone) | None |
| MobileCompany.dc.html | Deferred (phone) | None |
| MobilePayment.dc.html | Deferred (phone) | None |
| MobileNewPayment.dc.html | Deferred (phone) | None |
| BankBookLine.dc.html | Deferred to stage 2 (book a statement line, Kept here only) | None |

### 3.3 Each slice

**Stage 0: ready to build** (before slice 0). Three jobs, all done before any slice opens.
1. **The settings fix.** `hrp/config.py` always reads and writes `settings.json` in the program folder, so a test that
   saves a setting under `HRP_DATA_DIR` would change the live app's file. Keep `settings.json` in the `HRP_DATA_DIR`
   folder when that is set, or read a separate `HRP_SETTINGS_FILE`. One synthetic test: a settings save under
   `HRP_DATA_DIR` leaves the program folder's file alone.
2. **The six failing local tests sorted.** Six files in `tests/` fail today (`b1_payments_test`, `b3_sql_months_test`,
   `b5_frontend_test`, `b6_auditpack_test`, `n12_recon_test`, `n4_next_api_test`), each at one line with an
   AssertionError. For each: if the app changed on purpose, update the test locally; if the app broke, fix the app and
   add a synthetic test. Report by line and error type only. Rule 5 of "A slice is done when" cannot hold until this is
   done.
3. **The corrections folded into this plan** (from `docs/design/2026-11-19-build-check-and-stages.md`).

Exit: both suites pass (38 synthetic, 23 local), and the settings test proves a save stays in the temporary folder.

---

**Slice 0 · Shell and foundations, Payroll check moved** (L, branch `slice-0-shell`)

- **Boards:** Sidebar.dc.html, Topbar.dc.html, Icon.dc.html, PayrollCheck.dc.html, AccountingKeptHere.dc.html.
  Reference: Foundations, DarkPalette, States, ShellMenus, CompanySwitcher.
- **Screens.**
  - Colour tokens for light and dark, the existing Auto / Light / Dark switch restyled, fonts, the two-tone icons as
    one SVG sprite (80 glyphs: the 68 drawn before plus 12 new: staff, leave, reminder, birthday, claim, advance,
    payroll, approval, toPay, statutory, access, qr).
  - Components: buttons, pills (with the company-kind chip "Kept in SQL Account" / "Kept here"), fields, tables, cards,
    tabs, menus, toasts, skeletons, busy buttons, motion and reduced motion.
  - The dialog shell: focus trap, Escape, focus return, close at the end of the animation, "Discard your changes?".
  - The States patterns: empty, loading, could not load, many rows, refused with the reason, page not used for this
    company, the company-switch toast.
  - The five-area side menu (Overview, HR, Payments, Accounting, Admin) for the three company kinds, as ShellMenus draws
    it: Calendar and reminders as a tab of Staff, "Claims and advances" as one item, no user block in the sidebar.
  - The top bar: company switcher (All companies on the Overview only; stopped companies not offered; "No company yet"
    with "Add your first company"), month switcher reading "October 2026", breadcrumbs, user menu for the one person
    who uses the app today.
  - Addresses carry company, month, page and an optional state, so Back and Refresh keep your place and card links land
    on a filter.
  - Pages not rebuilt yet open at their new place. Pages not built yet (Staff, Leave, Claims and advances, Approvals,
    To pay) show a short "Coming soon" page. Sales, Purchases, Journals and Period close show the AccountingKeptHere
    placeholders, for Kept here companies only, until stage 2.
  - Menu items that are parts of other pages today open there until their own slice: **e-Invoices** opens the
    MyInvois e-Invoices part of today's SQL import page (slice 6 makes it a page; for a Kept here company, "Coming
    soon"); **Customers and suppliers** opens today's Books page on its parties tab, and **Statutory payables** on its
    statutory tab (slice 7 makes both pages).
  - **Narrow screens.** The new sidebar, top bar and switchers keep today's narrow-screen behaviour (the `app.css`
    rules at 860, 700, 640 and 520 pixels), restyled. No phone design is added.
  - **Payroll check moved:** `viewPayroll` moves from Monthly work to HR › Payroll › Workbook check, for every
    company, with no change to what it does. It follows PayrollCheck.dc.html's wording, including "The records need
    update 38" and the IC masking.
  - Sidebar badges by the existing one-badge rule (a number is how many Next up rows belong to that area).
  - `app.js` is split into one plain module per page (no build step).
- **Server work.** `/api/meta` gives each company's kind and which pages it uses: the kind is worked out from
  `entities.uses_sql` (0 or 1), so no migration. Next up rows carry a new `area` field on every row (`_row` in
  `hrp/nextup.py`; today the nearest thing is `go.view`), so badges and new addresses can be worked out; rule 15's
  target opens HR › Payroll. No migration.
- **Steps.** One branch, cut into six steps, each reviewed before the next. Today the app has no addresses at all
  (`app.js` keeps the page, company and month in memory), so the router is new work.

  | Step | What | Visible change | Check |
  |---|---|---|---|
  | 0a | Split `app.js` into classic scripts: `static/js/core/` (util, api, state, ui, router, events), `static/js/pages/` (one per page), `main.js` last. No `type="module"` | None | The local front end tests, every page opens with no console error, a click through of today's app |
  | 0b | Tokens (light and dark in one place), fonts linked, the 80 glyph sprite, buttons, pills, fields, reduced motion | The new look on the old layout | Contrast in both themes |
  | 0c | The dialog shell (focus trap, Escape, focus return, `role="dialog"`, a styled "Discard your changes?" replacing `confirm()`) and the States patterns | Dialogs and empty, loading and error states | Keyboard only walk |
  | 0d | Addresses `#/CODE/YYYY-MM/page/state`: a hash router replacing `render()`'s chain; `go()` and `goTo()` write the address | Back and Refresh keep your place | New synthetic test: every old page key opens its address |
  | 0e | The shell: five area menu, top bar, company and month switchers, breadcrumbs, badges; `/api/meta` kind and pages; Next up area; Coming soon pages, Kept here placeholders, interim landings | The new menu | Tests for the interim landings, the company switch toast and the Kept here menu; phone width (375 px) |
  | 0f | Payroll check moves to HR › Payroll › Workbook check; rule 15's target follows | One page moves | `payroll_check_test` unchanged |
- **Depends on:** stage 0 (above). Nothing else runs while it is open.
- **Phone note:** none. The shell is checked at phone width (375 pixels): menu, switchers and every existing page
  usable with no sideways scroll of the page.
- **Checked by:** local `smoke_test`, `b5_frontend_test`, `n5_next_ui_test` updated for the new shell. Synthetic:
  `payroll_check_test` (the check unchanged at its new place), `checklist_test`, `seed_names_test`. New synthetic
  tests: every old page key opens its new address; the interim landings of e-Invoices, Customers and suppliers and
  Statutory payables; switching to a company without the page lands on its Overview with the toast; the menu for a
  Kept here company. Click-through: a normal month's work inside the new shell, then again at phone width.

**Step 0a done (19 November).** `static/app.js` is now 22 plain scripts under `static/js/` (`core/`: base, shell, next, events, listeners; `pages/`: one per page, with Setup in four parts; `main.js` last), loaded in order by `index.html`. They are contiguous slices of the old file, so joined they are byte for byte the old `app.js` (checked), and nothing was reordered. The names say where the code is today; the finer split into util, api, state, ui and router comes with 0c to 0e, as those parts are rewritten. Tests that read the page script as text use `synthetic_tests/appsource.py` (`app_source`, `app_files`, `app_bundle`), which reads the list from the `<script>` tags in `index.html`. New files under `static/js/` must be added to that list, in load order.

**Step 0b done (19 November).** The new look on the old layout. `static/app.css` is rewritten on the design's tokens: every colour is declared once with `light-dark()`, so the dark values are no longer written twice (Chrome or Edge 123 or later, Firefox 120 or later; Auto follows Windows and the Theme button still forces Light or Dark through `color-scheme`). Inter and Space Grotesk are linked from `static/fonts/fonts.css`. The 80 glyphs are one sprite, `static/icons.svg`, drawn by `icon()` in `core/base.js` (`<use href="/static/icons.svg#i-name">`; the stroke is the text colour, the tint is `--glyph-tint`). Buttons, fields, pills, chips, the navy sidebar, focus rings, the motion tokens and the reduced-motion rule follow the boards. Not done in 0b because they need markup or script: the three-option Theme control (0e), the toast's exit animation and alert glyph, the busy field, and the plus glyph on the missing-document chip. Known and left: the Backup page's long folder path pushes the page sideways at phone width (as before; fix with the phone-width check in 0e).

**Step 0c done (19 November).** `core/dialog.js`: the side panel is now a modal dialog (`role="dialog"`, the page behind inert, focus to its heading and back to the opener, Tab kept inside, Escape and the dim close it through the unsaved-edits check, closing finishes with its animation). `ask(message, options)` is the styled confirm and replaces every browser `confirm()`; `mayLeave()`, `closeDrawer()`, `go()` and `goTo()` are now async, so callers await them. `core/states.js`: `emptyState`, `loadingSkeleton`, `errorState`, `stoppedState`, `refusedNote`, `manyRows`, `unusedCard`, and the toast stack (three at most, errors stay, pause on hover or focus, Undo and action buttons ready for slice 10). A page the company does not use (SQL import for a Kept here company) lands on that company's page with the "Switched to" toast. Harness tests stub `ask` instead of `confirm`. Not wired yet because no page needs them: `manyRows` and the compact empty state in a list.

**Step 0d done (19 November).** `core/router.js` holds the one route table. Every page has its final address: `#/<CODE|all>/<YYYY-MM>/<area>/<page>` for month pages (register, budget, recurring, bank, SQL import, payroll workbook, audit pack, overview), `#/<CODE>/accounting/books?tab=…` and `#/admin/audit-trail`, `#/admin/backup`, `#/admin/setup[/<kind>[/<id>]]` without a month. Filters ride in the query (`mark`, `pay`, `task`, `as_at`, `filter`, `account`, `tab`, `from`, `to`; never names or amounts). `go()`, `goTo()`, the month buttons and the company pick write the address; Back, Forward, Refresh and a pasted link apply it; Back with unsaved edits asks first and "Keep editing" restores the address without a new history entry. A bad address or a page the company does not use opens the Overview with a toast. Known and left for 0e or later: Setup uses one shape (`admin/setup/<kind>`, with `entities` for Companies) where the design also draws `#/AISB/admin/setup/hr/approvers`; the register answers `payments/checklist` as an alias until slice 2; Customers and suppliers, Statutory payables and e-Invoices are still tabs of Books or the SQL page until slices 6 and 7; staff addresses (`hr/staff/S003`) arrive with slice 12. Small items left: a stopped company's address still opens; a rollover seen through a plain redraw leaves the old month in the address until the next navigation; a Books address without a tab keeps the last Books dates.

**Step 0e: known departures from the boards, left on purpose (20 November).** The menu, top bar and company switcher are built; these differ from the boards and are handled later. (1) Approvals and To pay count badges (requests waiting; items to pay, red when overdue) come with slice 11, which builds the pages that hold the counts; Staff's number from probation and permit reminders comes with the reminders rule. Until then an item shows a number only for the Next up rows that name it (`row.page`), and an area heading shows its number only while folded, as the board does. (2) The sidebar status card shows the verified glyph and "Records stay on this PC"; its second line (last encrypted backup, audit trail intact) and the red "The audit trail needs attention" state arrive in a later slice, when the backup and trail status are on the front end's data. (3) The sidebar brand sub line is the organisation name setting, empty until one is set. (4) A Kept in SQL Account company that reaches Sales, Purchases, Journals or Period close by address sees the States "page not used" card, not the longer AccountingKeptHere old-address card (three links, two buttons); the long card is slice 7 work with the real Kept here pages. (5) The account button shows a person glyph, not initials, and its menu has no name, access line, Users and access or Sign out: there is one local person until sign-in (slice 16). The Theme control is a three-option group inside the account menu, not the board's separate button with a menu; move it when the notifications bell and search arrive (slice 10) or change the board. (6) The month label is a plain label with Previous, Next and Current; the board's month menu (per-month status tags) needs per-month status from the server and comes in a later slice.

**Step 0f done (20 November). Slice 0 is complete.** The Payroll check is HR › Payroll with its Workbook check tab (`#/<CODE>/<YYYY-MM>/hr/payroll/workbook`), for every company, doing what it did before. The page follows PayrollCheck.dc.html: the Payroll heading and its sentence, the one Workbook check tab (the run tabs come with slice 15), the headline banner, the Next up sentence while the latest check has things to fix, the filter chips of What the check found with Show everything, a refused workbook explained in place ("… wasn't checked", "Nothing was kept"), the busy Check button, the closing note with the audit trail link, and no company control on the page (the top bar's switcher drives it). Next up rule 15 opens it through the router. Not drawn yet because the setting does not exist: the note that the run tabs need "Runs payroll in this app" and the link to Setup › HR › Payroll settings (slice 15).

---

**Slice 1 · Overview** (M, `slice-1-overview`)

- **Boards:** Main.dc.html, DarkOverview.dc.html. Reference: OverviewCards.dc.html.
- **Screens.** The top part stays: audit-trail notice, date, Next up with Go, older open months, the rollover
  banner. Below it, 13 cards in four rows, in the calmer design of 18 November (one headline, one note, company lines
  only with All companies, four per row). The card rules are in section 4.4. Every card has its empty, out-of-date
  and could-not-load state. The tiles, the per-company cards and "Show tasks for" go (the switcher is the company
  filter). Recent activity (a kept feature).
  - Cards whose pages are not built yet: HR cards read "Add your staff to see this"; Requests waiting reads "Nothing
    waiting"; Paid without approval stays hidden.
  - **Interim landings** (each switched by the slice named):

    | Link | Until then it opens | Real target from |
    |---|---|---|
    | Due and overdue | Payments register, Not paid tab (slice 2 merges first); before that, today's company month page | To pay, slice 11 |
    | Needs attention: Past due, Part paid, Not in SQL | Today's company month page, unfiltered | Register tabs, slice 2 |
    | Needs attention: Documents missing; Checklist card | Today's company month page, at its checklist | Monthly checklist and its Missing documents filter, slice 2 |
    | Needs attention: Lines to explain; Bank card | Today's Bank statements page at that month | Bank and reconciliation, slice 4 |
    | Profit or loss | Today's Books page, profit and loss tab | Books › Profit and loss, slice 7 |
    | Customers overdue, Suppliers due | Today's Books page, parties tab | Customers and suppliers `#customers-overdue` / `#suppliers-due`, slice 7 |
    | HR cards, Requests waiting | No link while empty | Slices 11 to 13 |

    Slices 2 and 4 are likely merged before slice 1 (section 6.2); then only the later rows apply.
- **Server work.** One small route per card, so one failing card never hides the others. The 19 November rule: one
  Next up row per unpaid statutory payment (`hrp/nextup.py`, section 4.2): rule 5 (`_to_pay`) already lists unpaid
  statutory payments, and rule 14 comes from `statutory.next_up`, which returns late and short only, so the change is
  a de-duplication between the two. The rollover banner counts the rows of the company it names. **Customers overdue
  at 30 days:** this slice owns the change to `hrp/receivables.py`. The ageing already has buckets (current up to 30
  days, 31 to 60, 61 to 90, over 90, brought forward); the card is the sum of the 31 and over buckets, a small
  change. **Balances from before tracking** (the brought forward bucket) do not count as overdue: the card shows them
  apart, labelled "Before tracking" (owner, 19 November). Slice 7's Customers overdue view reuses this and does not
  change it.
- **Depends on:** 0 and 8 (Funds to request uses slice 8's Budget rules: the no-balance sentence, payments counted up
  to the balance date, the company's own bank label).
- **Phone note:** none; cards stack at narrow widths.
- **Checked by:** local `n4_next_api_test`, `n5_next_ui_test`. Synthetic: `receivables_test`, `statutory_test`. New
  synthetic tests: each card's figures on made-up data; the one-row rule (unpaid gives only "Pay KWSP for October";
  short-paid or not entered gives the rule 14 row); Customers overdue counts only balances older than 30 days inside the tracked period, with brought forward
  balances shown apart as "Before tracking"; each card's link opens its target or interim landing. Click-through: All companies, one company, a company with nothing
  yet.

---

**Slice 2 · Payments register and Monthly checklist** (M, `slice-2-register`)

- **Boards:** PaymentsRegister.dc.html, DarkCompany.dc.html, MonthlyChecklist.dc.html. Reference: Company.dc.html.
- **Screens.** Today's company month page splits in two.
  - Register: columns Payment, Type, Paid / received, Amount, Documents, Status; tabs All, Not paid, Needs attention,
    Not in SQL (Kept in SQL Account only), Complete; search, bulk bar, "Add a payment", Excel; money in counted apart;
    the link "3 to-dos for AISB on the Overview" in place of the company Next up panel; a salary row's link "The payroll
    check found 3 things to fix"; a filed month read only.
  - Checklist: "18 of 27", ticks, slots, "Tick anyway?", Mark month as filed, Reopen, the Missing documents filter,
    the payroll workbook item with "Uploaded on HR › Payroll › Workbook check" and its replaced history, not set up.
- **Server work.** Little: the register's Excel (from the existing month export if it covers it).
- **Depends on:** 0. It switches the Overview's register and checklist links from their interim landings.
- **Checked by:** local `b1_payments_test`, `n1_status_test`, `n2_checklist_test`, `n3_closing_test`. Synthetic:
  `checklist_test`, `checklist_equivalence_test`, `stage1_settle_test`; a new one for the Missing documents filter.
  Click-through.

**Slice 2 done (20 November).** The company month page is two pages. **Payments › Payments register** (view key `entity`, `#/<CODE>/<YYYY-MM>/payments/register`, `pages/company.js`): the head with the company's kind and the month's state, the link "N to-dos for CODE on the Overview, M overdue" (with the older months still open) in place of the company's Next up card, the link to the checklist, Excel (the existing month report, `/api/export/month.xlsx`, whose Payments sheet holds every column), Add a payment; the figures that pick a tab (payments out counted apart from money in, which has its own figure); the tabs All, Not paid, Needs attention, Not in SQL (Kept in SQL Account only), Complete, in the address as `?tab=`, with the keyboard rules; the search (never in the address); columns Payment, Type, Paid / received, Amount, Documents, Status, grouped by due date with money out and money in added up apart, sorting, 25 at a time; the bulk bar (a paid date only on payments not paid yet, one bank slip to all; refused ones stay picked); a salary row's payroll check link; a filed month read only (no Add, no picking, the payment read only). **Payments › Monthly checklist** (view key `checklist`, `#/<CODE>/<YYYY-MM>/payments/checklist`, `pages/checklist.js`): "N of M done" with its bar, the filters All items, Not done, Done and Missing documents (`?tab=missing`, items whose documents are missing; slice 1's Overview card will open it through `pillGo("docs_missing")`), sections by due date, ticks, document slots, Tick anyway?, Mark month as filed, Reopen, the payroll workbook item ("Uploaded on HR › Payroll › Workbook check", its replaced history), reminders from other months, not set up; 50 items at a time. `/api/month` adds the latest payroll check (counts only) and, per checklist document, whether the Payroll check filed it and the earlier files it replaced. Next up rows and the Overview's counts about checklist items land on the checklist (marked), the rest on the register's tab; an old `register?task=` address opens the checklist. Departures: the Approval column and Paid without approval tab wait for slice 11, the payment dialog and document viewer for slice 3, Print the Month review for slice 11, the Period close lock and "once it has books" notes for stage 2, the status "why?" popovers (title tooltips stay); kept although the boards drop them: the older months still open line and Remove on the check's workbook (Replace goes through the check); the state pill says "Before tracking" as the rest of the app does. **Not now:** the filed-month lock is screen-only (the server guard comes with slice 4's month lock); a reminder from an open month shown in a filed month is locked with it; the Overview's payment figures count payments out only while the register's tabs include money in.

---

**Slice 3 · Payment dialog and Add payment** (M, `slice-3-payment`)

- **Boards:** Payment.dc.html, DarkPayment.dc.html, NewPayment.dc.html.
- **Screens.** The centred payment dialog: documents (several files per type, drop on a row), Pay to, the one-way
  estimate tick, part paid, status words, the **Bank account** field (paid from / paid into), the document viewer
  beside the dialog with Download, the note when the linked voucher changed in SQL, the paid date typed in, a locked
  month. Add payment: "For one-off bills and money in, not coming from a request", types in Setup's order, the
  register behind it.
- **Server work.** Most of it exists; check each against the app first and build only what is left.
  - The payment save already takes `account_id` (`PAY_FIELDS` in `hrp/app.py`, checked by `own_account()`). Left:
    when `account_id` changes, recheck the reconciliation of both the old and the new account for that month.
  - `/api/documents/<id>/file` already serves a file inline, or as a download with `?download=1`. Left: check the
    file type before serving it inline (PDF and images inline; anything else only as a download).
- **Waits for stage 2** (Kept here posting its own vouchers):
  - The "cancels voucher … and posts a new one" warning, the "posted here" voucher box and the "Payment voucher
    (posted here)" label on Payment and DarkPayment. In their place the payment shows the record reference field, as
    for any payment with no SQL voucher, and saving asks nothing.
  - NewPayment's "open a Sales receipt instead" for a Kept here company's money in from a customer. In its place Add
    payment keeps today's Money received type for every company.
- **Depends on:** 2.
- **Phone note:** none for the dialog (full width at narrow widths, as today); the document viewer beside it opens
  in place of the dialog below 860 pixels.
- **Checked by:** local `b1_payments_test`, `b2_undo_links_test`, `n12_recon_test`. Synthetic: `types_test`,
  `recon_bank_lines_test`, `stage1_settle_test`. New synthetic tests: moving a payment's account rechecks both; the
  viewer refuses an unknown file type inline. Click-through.

---

**Slice 4 · Bank and reconciliation** (L, `slice-4-bankrec`)

- **Boards:** Bank.dc.html, DarkBank.dc.html, BankReview.dc.html, PrintBankRec.dc.html.
- **Screens.** The page moves to Accounting and is renamed. Import card, year table, month panel, Book opening.
  The review with Apply, Confirm all matched and Explain; **one statement line linked to several payments** with a
  running total ("Link 8 payments"); the "Enter this in SQL Account" note on a bank-only line; the **No money moved**
  group (pairs with their documents, Net nil pill, reason filled in and editable, tick to confirm). Sign-off with an
  optional note, and the note the app writes. **Sign-off locks the month**; "Reopen month" with a reason replaces
  "Undo sign-off". **The printed reconciliation statement** per account and month (PrintBankRec: standard layout, No
  money moved, totals check, SQL check, Prepared by and Reviewed by, code, keyed check and QR).
- **Server work.**
  - A link table so one statement line can carry several payments (migration; today a line holds one payment).
  - Pair finding reused from the SQL import page; pair confirmation with its reason (migration).
  - The sign-off keeps its note as it stood, the free note and the declared Prepared by name (migration). The free
    note column exists (`statements.reconciled_note`); `recon.sign_off` sets it to empty today, and there is no
    Prepared by yet.
  - The lock: a signed-off month refuses changes to its lines and to its payments' bank fields. **It replaces
    today's clear on change:** `recon.line_changed` removes the sign-off when a line changes. Find every caller
    (`hrp/app.py`) and update the tests that rely on the clearing (local `n12_recon_test` at least). Reopening is
    logged with the reason, needs a new sign-off, and keeps the old note in the audit trail.
  - The sign-off rule is today's: the book closing must equal the bank closing (owner, 19 November; section 7.1). A
    reconciling items section is not needed for sign-off.
  - **Reopen replaces Undo sign-off.** Today's `/api/recon/undo-sign-off` route (`recon.undo_sign_off`) becomes the
    reopen route, which takes a reason; the old route is retired, not kept beside it. The "Undo sign-off" button
    (`data-rc-undo` in `app.js`) goes. The local `n12_recon_test` and `b2_undo_links_test` are updated to the reopen
    route.
  - A small form-code module (code, keyed check, QR) for the statement. The **keyed check** is a short code worked
    out from the printed figures with a secret kept in the records, so a changed statement no longer matches. The
    statement's code is `BR-yymm-<company code>-<last 4 digits of the account number>`, as PrintBankRec draws it.
    Slice 11 reuses the module for approval forms.
  - **The secret** is created on first use (the first statement printed), and its creation is written to the audit
    trail. It is never in a Move setup file: `hrp/setupfile.py` leaves it out of `export`, and `load` never reads
    one. A test checks both. Slice 11 adds the Setup › HR › Approvers screen that shows when it was made and can
    replace it.
  - The statement PDF, and the audit pack's reconciliation page showing the signed statement and its note.
  - Until slice 11 brings code reading, the signed statement is filed as an ordinary document on the month's bank
    reconciliation checklist item.
- **Waits for stage 2:** booking a bank-only line for a Kept here company (BankBookLine). In its place the line stays
  a line to explain, as today.
- **Depends on:** 3 (decision 2 is closed, so nothing else waits).
- **Phone note:** needed on the review (BankReview: statement lines beside payments) and on the statement print
  preview. The year table and month panel keep the narrow layout.
- **Checked by:** local `n12_recon_test`, `b2_undo_links_test`, `n10_backup_match_test`. Synthetic:
  `recon_bank_lines_test`, `recon_bank_lines_fixes_test`, `recon_review_fixes_test`, `journal_bank_test`. New
  synthetic tests: one line to several payments; sign-off refused while a pair is unconfirmed or not nil; reopen
  needs a reason and is logged; the old undo route is gone; the keyed check changes when a figure changes; the secret
  is created once, logged, and never in a setup file. Click-through: reconcile a month, print the statement.

---

**Slice 5 · SQL import** (M, `slice-5-sql`)

- **Boards:** Sql.dc.html, SqlBooks.dc.html.
- **Screens.** Kept in SQL Account companies only. Everything on today's SQL page except e-Invoices: Fetch and its
  preview, paste, entries not linked, Journals and invoices, Find an SQL entry, Probably a correction, Replaced by a
  later version, Deleted in SQL and Ignored, Before tracking, Imported files, Use another folder, the checks against
  SQL's reports, account lines. The "this company is kept here" message at an old address. Drag and drop on the file
  box (a kept feature).
- **Server work.** The SQL fixes in section 4.1 only.
- **Depends on:** 0. Sql's payroll-run journal match ("Matches the October payroll run") is finished by slice 15.
- **Phone note:** needed on the check tables and the account lines; the rest keeps the narrow layout.
- **Checked by:** local `sql_test`, `sql_multi_test`, `sql_paste_test`, `b3_sql_months_test`. Synthetic:
  `sql_exports_test`, `sql_books_item_test`, `fetch_checks_test`, `ledger_fetch_test`, `before_tracking_test`.
  Click-through: a fetch.

---

**Slice 6 · e-Invoices** (M, `slice-6-einvoices`)

- **Boards:** MyInvois.dc.html, InvoicePdf.dc.html.
- **Screens.** Its own Accounting page, for both company kinds. Issued, Received and Self-billed tabs, links to
  documents, unbooked received e-Invoices. A Print column (invoices, debit and credit notes, self-billed vouchers),
  "All of the month" zip, and each document's print note beside its PDF button. The MyInvois copy is still read by
  Fetch, shown as a source line. A Kept here company prints its own documents and reads "Submission method not decided
  yet". The printed documents keep SQL's layout.
- **Server work.** None new. The existing invoice check route finally gets its screen.
- **Depends on:** 5 (both take code out of today's SQL page, so they never run at the same time). It switches the
  e-Invoices menu item from its interim landing.
- **Phone note:** none; the tabs' lists keep the narrow layout.
- **Checked by:** synthetic `myinvois_test`, `myinvois_amount_test`, `invoice_pdf_test`, `invoice_notes_test`.
  Click-through: print one invoice and the month zip.

---

**Slice 7 · Books, Customers and suppliers, Statutory payables** (L, `slice-7-books`)

- **Boards:** Books.dc.html, BooksLedger.dc.html, BooksStatements.dc.html, BooksParties.dc.html,
  BooksStatutory.dc.html, SetupStatutory.dc.html.
- **Screens.**
  - Books with four tabs (trial balance checked against SQL, general ledger, profit and loss, balance sheet), the From /
    To bar and "financial year to date", Excel, account to ledger, the document pop-up, "No books yet" for Kept here.
  - Customers and suppliers as its own page: both sides, ageing, one party's statement, as-at date, the Customers
    overdue and Suppliers due views.
  - Statutory payables as its own page: per authority and payroll month (EPF, SOCSO, EIS, Lindung 24 Jam (SKBBK), PCB,
    zakat, HRDF with "Not set up" or "Not registered"); Net salaries payable with its paid-in-full check; Use this
    account, Open the payment, Go to Setup.
  - Setup › Statutory accounts with the new kinds, built into whichever Setup shell is merged at the time: inside
    today's Setup page if slice 9a is not merged yet (9a then moves it into the new Setup menu), or straight into the
    new Setup menu if it is.
- **Server work.** Statutory kinds gain **Net salaries payable** and **Zakat**. `statutory.KIND_WORDS` has EPF, SOCSO,
  EIS, SKBBK, PCB, HRDF and Other today, so SKBBK and HRDF already exist. The statutory accounts table has a `CHECK`
  on kind (`statutory.py`), which SQLite cannot change, so the migration **rebuilds the table**. Net salaries payable follows the account each company chooses
  (420-000 Accruals in the owner's SQL books). Rule 14's wording and target (section 4.2). The Books fixes in 4.1.
- **Depends on:** 5 (Books reads what the SQL import keeps). The 30-day Customers overdue rule comes from slice 1;
  if slice 7 merges first, it shows today's ageing until slice 1 lands. Balances from before tracking show apart as
  "Before tracking", not as overdue. It switches the Customers and suppliers and
  Statutory payables menu items and the Overview's Profit or loss, Customers overdue and Suppliers due links from
  their interim landings.
- **Phone note:** needed on the trial balance, general ledger and statutory tables; the party lists keep the narrow
  layout.
- **Checked by:** local `n9_reports_test`. Synthetic: `statutory_test`, `receivables_test`, `books_test`,
  `books_excel_test`, `gl_reports_test`, `parties_test`, `statements_test`, `financial_year_test`. New synthetic
  tests: the two new kinds, the paid-in-full check, rule 14's text and target, the Customers overdue view following
  slice 1's rule. Click-through.

---

**Slice 8 · Budget and Recurring** (M, `slice-8-budget`)

- **Boards:** Budget.dc.html, Recurring.dc.html.
- **Screens.** Budget under Payments: stored budget, editable lines, set-up, Print, Excel, each company's own bank
  label, "Enter the bank balance to see funds to request" when no balance is entered. Recurring under Payments: the
  full form, types with Setup's labels, Add to month. Salary advances stay on Recurring until slice 14.
- **Server work.** The Budget rules in section 4.3, checked against `hrp/budget.py`. Payments counted up to the balance
  date is already done (`line_left`, `payment_left`). Left: the no balance state (today a blank balance counts as 0
  and reads "None (balance covers the budget)"), the balance read only from the stored budget (the page also keeps it
  in the browser's `localStorage` today), and a new bank label taken from the company's own account (none exists).
- **Depends on:** 0. Slice 1 waits for it (Funds to request).
- **Phone note:** needed on the budget table and its print; Recurring keeps the narrow layout.
- **Checked by:** local `b4_budget_test`, `n6_budget_test`, `n7_money_in_test`. No synthetic test covers Budget
  today; new synthetic tests: the no-balance sentence and hidden fund-request print, the balance read only from the
  stored budget, the company's own bank label, and payments counted up to the balance date (done in the code, but no synthetic
  test covers it). Click-through: a budget print.

**Slice 8 done (20 November).** **Payments › Budget** (`pages/budget.js`) follows Budget.dc.html: the head (Payments, "Budget for <month>", the company and its bank, the payroll month it covers, Excel, Print budget), the bank balance card (the bank named from the company's own account, the date and balance boxes saving on the stored budget when you leave them or press Enter, with Saved, the "Enter the date this balance was taken" and "As at today … Use <date>" notes), the figures (balance, still to pay, funds to request, already paid, other currencies), Budget vs paid, Budget lines (edited in place, Select all, Delete selected, Add line per currency, the not-linked note, History, 25 at a time), Paid but not in the budget, Budget against paid, Already paid (in the balance) folded on a button, the estimate help card, the not-set-up banner with Set up budget and its read-only list, the month-not-set-up card, and a print preview (the budget, or the fund request while there is a shortfall). **Server (section 4.3):** `budget.balance_of` and `budget.funds_to_request`: the balance is read only from the stored budget (a month with none has no balance) and the funds to request are `None` while no ringgit balance is entered, never worked out from a blank as 0, and `None` too when the page is at another date than the balance's own (`budget.balance_for`: a Next up link as at today never sets the balance of another day against what is left today; the page, its print and the Excel say "the balance is for <date>; open the budget as at that date to see funds to request"); `/api/budget` gives `balance`, `funds_to_request`, `bank` (`budget.bank_account`: the company's cash book account when in ringgit, else its first ringgit account in use, with its other-currency accounts) and `today`; `sums.<cur>.paid_by` (paid against the budget by the balance date, by the rule `line_left` uses: bank lines dated by then for a payment paid in parts). `bank` names a stopped ringgit account as stopped. The page shows "Enter the bank balance to see funds to request", hides the fund request print and prints "not worked out, bank balance not entered"; the fund request print lists only what is still to pay, so its total is the Still to pay figure. `localStorage` is gone from `budget.js`, and the Overview no longer sends `as_at_<id>` (the server takes the date kept with the budget; the parameter stays for tests). A balance a browser kept before slice 8 goes across to the stored budget once (`core/legacy.js`, with its date as kept, never today in its place) and leaves the browser; a month not set up keeps it until its budget is. A balance saved with no date leaves the date empty until one is entered; Saved shows only once the server took the save; Enter saves once. Each currency's table shows 25 lines at a time on its own; Select all and Delete selected take the lines shown only; the payment picker shows each payment's amount. The worked-out list moved to `budget.worked_out`; `/api/export/budget.xlsx` now exports a month with no stored budget too (the worked-out list), and both sheets carry the bank account, "Not entered" and the funds to request. **Payments › Recurring** (`pages/recurring.js`) follows Recurring.dc.html: the head with Excel (new `/api/export/recurring.xlsx`, every field, types in Setup's words) and Add recurring payment, the search and count, Show stopped, Show deleted, the type filter (Setup's labels, with counts), the table (25 at a time, empty and no-match states), Add to <month> on a row not in the month (a stopped one too, under its Stopped pill: nothing else can add its last payment), and the form in the board's order with its own checks (Required, hints, fields marked in red). Salary advances stay in the form until slice 14. The "best done on a computer" note (`desktopNote`, `core/states.js`) shows at narrow widths above the budget tables; Recurring keeps the narrow layout; no sideways page scroll at 375 px (checked). New synthetic test `budget_recurring_test`. **Departures:** the balance box is off until the budget is set up (the stored budget is the one place it is kept), where the board lets it be typed before set-up; the recurring form stays in the side panel (dialog) rather than the board's panel beside the list, keeping its unsaved-edits guard; Budget against paid keeps today's SVG chart, without the board's sort buttons and links; Start date and Last day stay on salary rows (the staff records come with slice 12); the Approval column and section (slice 11), Staff on this row (slice 12), the advance pointer to HR (slice 14), the payroll switch-over notes (slice 15) and money in on the Already paid card are not built; the print's "Prepared … by <name>" has no name until sign-in (slice 16); Add to <month> stays on a stopped row, where the board leaves it off (kept: nothing may be lost). Local `n9_reports_test` was updated for the new export but needs `samples/` in its folder to run.

---

**Slice 9 · Admin** (L, reviewed and merged in two halves)

- **9a Setup** (`slice-9a-setup`). **Boards:** Setup.dc.html, SetupNav.dc.html, SetupCompanies.dc.html,
  SetupChart.dc.html, SetupParties.dc.html, SetupTypes.dc.html, SetupRequired.dc.html, SetupChecklist.dc.html,
  SetupMatching.dc.html, SetupGeneral.dc.html, SetupMove.dc.html, FirstRun.dc.html.
  - **Screens.** The Setup menu (the HR group appears with slice 11), the shared list toolbar and record dialog (Where
    used, Stop / Use again / Delete with a reason), Show deleted and Put back, Paste a list, Move setup. Matching words
    hidden for a Kept here company. Company labels "Kept in SQL Account" / "Kept here". First run: the welcome page
    for an empty install, using the existing setup-file import, with "Where are the books kept?".
  - **Server work.** The Setup fixes in 4.1. First run needs no new route.
  - **Waits for stage 2:** SetupRequired's "posted here" payment-voucher box for a Kept here company. In its place the
    payment voucher is required only where the company's rules say so today, with no "posted here" choice.
  - **Phone note:** none; Setup keeps today's narrow layout (the 520-pixel form rules).
  - **Checked by:** synthetic `setup_test`, `types_test`, `parties_test`, `masters_equivalence_test`,
    `stage1_leftovers_test`, `seed_names_test`; new ones for each Setup fix in 4.1.
- **9b Filing** (`slice-9b-filing`). **Boards:** AuditPack.dc.html, AuditPackBooks.dc.html, AuditTrail.dc.html,
  Backup.dc.html.
  - **Screens.** Audit pack: Before you print, build with progress, Check this pack, Auditor package, Excel, filed and
    reopen, the books pages. Audit trail: filters (adding Payroll checks and Months), history, the needs-attention
    state. Backup with the documents check and the backup extras.
  - **Server work.** The new trail filters; backup extras read backup events from the trail.
  - **Phone note:** none for Audit trail and Backup; the audit pack's Before you print and build steps show it.
  - **Checked by:** synthetic `trail_view_test`, `audit_trail_test`, `pack_check_test`, `restore_test`; new ones for
    the trail filters and backup extras.
- **Depends on:** 0. 9a and slice 7 can merge in either order (Setup › Statutory accounts goes into whichever Setup
  shell is there). 9a before 11 (Setup › HR goes into its menu).
- **Checked by (both halves):** local `b0_migrations_test`, `b6_auditpack_test`, `n10_backup_match_test`,
  `smoke_test`. Click-through.

---

**Slice 10 · Search, notifications and Undo** (L, `slice-10-search`)

- **Boards:** CommandPalette.dc.html, Notifications.dc.html.
- **Screens.** Search with Ctrl K (recent, grouped results, nothing found; Go to rows with the new areas; "Switch
  company" opens the switcher). The notifications bell with read state, kept apart from Next up. Undo on the toasts of
  every rebuilt page.
- **Server work.** A search route over payments, SQL entries, bank lines, documents, checklist items and Setup
  records. An events table and a read marker (migration). Undo: a short-lived undo record per action, written to the
  audit trail as its own entry; today's SQL link undo stays (sign-off has no undo since slice 4: it is reopened with a
  reason). Each later slice adds its own records to search and its own events to notifications.
- **Depends on:** 9a and 9b, so Undo covers the Setup pages in one go.
- **Phone note:** none; search and the bell open full width at narrow widths.
- **Checked by:** local `n11_ui_extras_test` (updated if it touches the list search). New synthetic tests for
  search per record kind, read state, an undo written and reversed, an undo that has expired; `audit_trail_test` for
  the undo entries. Click-through.

---

**Slice 11 · Approvals and To pay** (L, `slice-11-approvals`)

- **Boards:** Approvals.dc.html, ApprovalUpload.dc.html, ToPay.dc.html, PrintApprovalForm.dc.html,
  PrintMonthReview.dc.html, SetupApprovers.dc.html, AuditPackHR.dc.html (its approval pages; its HR pages are finished
  by slices 12 to 15).
- **Why approvers are here.** The gap review put Setup › HR › Approvers with HR staff. A form cannot print without
  approvers, and the keyed-check secret is shown and replaced on that board, so it moves to this slice. (The secret
  itself is created by slice 4.)
- **Screens.** Approvals with its tabs (To print, Waiting for approval, Approved, Not approved and Withdrawn, Paid
  without approval on file with Approved after payment), print dialog single and batch, Not approved and Withdrawn
  dialogs, the no-approvers state. Upload a signed form with all its cases. To pay grouped as overdue, this week and
  later, select several and Pay. The printed approval form and Month review sheet. Setup › HR › Approvers with their
  history and the form key. Excel exports of Approvals (every form: who signed, date signed, upload date, requests
  covered) and To pay. AuditPackHR's "Steps done by one name alone" page: per month, each request whose declared
  requester, payer and approver were the same name.
- **Finishes on earlier boards.** The Approval marker's six readings, the Request and Approval form blocks and the
  same-name warning on Payment and DarkPayment. The Approval column and Paid without approval tab on PaymentsRegister
  and DarkCompany. The two checklist items on MonthlyChecklist and SetupChecklist. "Needs approval" on NewPayment. The
  approval line on Recurring. The per-type default and the new document types on SetupTypes. The Approval box on
  SetupRequired. The form secret and approver names in SetupMove. Before you print and "declared, not verified" on
  AuditPack. The Paid without approval and Requests waiting cards on Main. The Approvals and To pay count badges on
  Sidebar. The signed reconciliation statement upload (ApprovalUpload's bank-rec states) for slice 4. The Approvals
  record filter on AuditTrail.
- **Server work.** The rules are in section 4.5.
  - New tables (migration): approvers per company with dated history; forms and their items; uploads; request status
    on payments; the needs-approval setting per type (default for every type in use, section 4.3) and per payment;
    the **declared names** at each step: who requested, who entered or paid the payment, and who chose the approver
    from a paper scan.
  - **Reading the code back.** From a PDF's text with `pypdf` (already in `requirements.txt`). From the QR in a scan
    or photo with an offline QR-reading library, not yet chosen (section 7, decision 6); `segno`, already there,
    only makes QR codes. A typed code is always the fallback, and is the only way until decision 6 is made.
  - **Digitally signed PDFs.** The signer's name is read from the PDF's signature field with `pypdf` and matched to
    the company's approvers. A PDF with no readable signer is handled like a paper scan (choose the approver).
- **Waits for stage 2:** paying a Kept here company's item on ToPay posts its payment voucher, and the paid toast
  names it. In its place the app shows the state ToPay already draws for a company with no chart of accounts: paying
  records the payment, with nothing posted.
- **Depends on:** all of 0 to 10 (it finishes states on Main, Recurring, Payment, the register, Setup and AuditPack,
  and uses slice 4's form-code module and slice 10's search and events).
- **Phone note:** needed on the print dialog and the upload matching screen. The Approvals and To pay lists keep the
  narrow layout.
- **Checked by:** new synthetic tests: the keyed check changes when an amount, payee or line changes; every upload
  case; a typed code, a PDF-text code and a signed PDF's signer; lock and void on change; every marker reading; the
  Paid without approval list; one payment per item when paying several; an approver's name stays as it was after
  Setup changes; the same declared name warns and appears on the one-name-alone page; the Approvals and To pay
  exports. Synthetic `types_test` and `setup_test` for the needs-approval defaults. Click-through: print a form, sign
  it on paper, scan it, upload it.

---

**Slice 12 · HR staff** (L, `slice-12-staff`)

- **Boards:** HrStaff.dc.html, HrStaffRecord.dc.html, HrStaffForm.dc.html, HrStaffExport.dc.html, HrCalendar.dc.html,
  SetupHolidays.dc.html, PrintHrLists.dc.html (the staff record PDF; its leave and claim lists come with 13 and 14).
- **Screens.** The staff list (In employment, Left, All; All companies read only; first run "Add your staff or paste
  the Excel list"), paste and Excel import with a preview, all or nothing. The staff record with its tabs, add and
  edit, Left with last day and reason, move to another company. Staff Excel export with a column choice. Calendar and
  reminders as a Staff tab (list, month view, mark done, one-off reminder). Setup › HR › Public holidays.
- **Finishes on earlier boards.** Salary rows on Recurring linked to their staff record. SetupChecklist's reminders
  driven by the staff record (probation and work-pass templates read only). The Dates coming up and Headcount cards.
  Next up rule 16 (probation and permit dates, with no name). Staff in search, permit expiry in notifications. The Staff
  filter and IC and pay masking on AuditTrail. The HR summary page of AuditPackHR. HR settings in SetupMove (staff
  records never). FirstRun's next step.
- **Server work.** Section 4.6. New tables (migration): staff records, pay history, staff documents, reminders,
  holidays per company. The merged joiner reminders (section 4.2): the reminders live in the records (`people_tasks`,
  `people_task_terms`), seeded from `rules.PEOPLE_TASKS`, with short names in `checklistbook.PEOPLE_NAMES`, so the
  migration rewrites the stored tasks, terms and short names and the Move setup `reminders` section; the merged
  reminder gets a new key with a 7 day term.
  - **Preferred name** (owner, 19 November: yes). A preferred name field on the staff record, used as {name} in
    reminders. Today {name} is `db.short_name()`, the bracketed part of the payee name; that stays the fallback for
    payees and for staff records with no preferred name.
  - **Moving from payees to staff records.** A company's joiner and leaver reminders keep coming from its recurring
    salary rows until that company has at least one staff record. From then on they come from staff records, and a
    salary row linked to a staff record no longer makes its own. Existing open reminders are not lost or doubled at
    the change.
  - **Who is staff** (scope Decided row, 17 November): directors on the payroll are staff records (they have EPF and
    PCB); contract workers stay payees unless they are on the payroll. The import and the "Add staff" form follow
    this, and a payee is never turned into a staff record without HR choosing it.
- **Depends on:** 11 (Setup › HR group, requests), and through it 0 to 10.
- **Phone note:** none for the staff list and record (narrow layout); needed on the import preview, the export column
  choice and the calendar's month view.
- **Checked by:** new synthetic tests: the worked-out categories change the month after the 60th birthday; an
  override needs a reason; IC masked to the last 4; the import is all or nothing; a director on the payroll imports
  as staff and a contract worker not on the payroll does not; the export leaves sensitive columns off; merged
  reminder dates; reminders from salary rows for a company with no staff records, and from staff records once it has
  one, with none lost or doubled; holidays below 11 refused; replacement days. a preferred name is used in a reminder and the bracketed payee name is the fallback; `seed_names_test` and
  `checklist_test` for the reminder wording. Click-through with made-up staff.

---

**Slice 13 · HR leave** (L, `slice-13-leave`)

- **Boards:** HrLeave.dc.html, HrLeaveYear.dc.html, SetupLeave.dc.html.
- **Screens.** Taken and booked (Booked, Taken, Cancelled), add leave (half day, certificate, warnings), cancel with a
  reason, maternity eligibility, Balances (also at a date), Team calendar with the public holidays. Opening balances
  and year end. Setup › HR › Leave types and policy.
- **Finishes on earlier boards.** The On leave card (no leave type). "Back on Monday" notifications. The Leave tab on
  HrStaffRecord. The leave lists on PrintHrLists. The Leave filter on AuditTrail.
- **Server work.** Section 4.7. New tables (migration): leave, policy per company with dated values, opening balances.
- **Depends on:** 12. Can run beside 14, with migration numbers agreed before both open.
- **Phone note:** needed on the team calendar and Balances at a date; the leave list keeps the narrow layout.
- **Checked by:** new synthetic tests: working days skip rest days and holidays; entitlement by service and work
  location; proration; leave above the legal days warns and is never refused; a policy below the legal minimum is
  refused; the Excel export of each leave list. Click-through.

---

**Slice 14 · HR claims and advances** (L, `slice-14-claims`)

- **Boards:** HrClaims.dc.html, HrClaim.dc.html, HrAdvances.dc.html, SetupClaimTypes.dc.html.
- **Screens.** Claims and advances with the Claims and Advances tabs, a new claim with lines and receipts, the claim
  page with its approval and payment links, the advance page with its schedule. Setup › HR › Claim types.
- **Finishes on earlier boards.** Recurring's advances block becomes a pointer to HR. NewPayment sends Staff claim and
  Salary advance to HR. The payment dialog shows the claim and its receipts, and the viewer shows receipts. The claim
  list on PrintHrLists. The Claims and advances tab on HrStaffRecord. Advances and amounts to collect on AuditPackHR.
  HR requests on the Requests waiting card and the Approvals filter. The Claims and Salary advances record filters on
  AuditTrail.
- **Screens, exports.** Excel export of the Claims list and the Advances list.
- **Server work.** Section 4.8.
  - New tables (migration): claim types per company (expense account, optional monthly limit, receipt required,
    stopped); claims (staff record, company, status, the request it belongs to, the payment it became); claim lines
    (date, claim type, amount, note); receipts (stored as documents, linked to their claim line and, once paid, to
    the payment); the app-wide **SA series** for advances (one counter for all companies, like AF); on each advance,
    its staff record, SA number and the **amount to collect** left after a leaver's last deduction.
  - Routes: claim types (list, add, change, stop), claims (list, add, change, withdraw, send for approval), claim
    lines and receipts (add, remove), advances under HR (list, add, change, end), the Claims and Advances Excel
    exports. Today's `/api/payees/<pid>/advances` and `/api/advances/<id>` routes are retired once the HR routes
    replace them.
  - **Moving existing advances.** The migration keeps every advance row as it is and adds its staff record where the
    payee has one (matched by the link slice 12 makes between a salary row and its staff record). An advance whose
    payee has no staff record yet stays on its payee, works as today, and is shown on HR with "No staff record yet:
    add one to move this advance". It moves when HR links that payee to a staff record. Deductions, months and
    balances never change in the move.
- **Waits for stage 2:** HrClaim's "Recorded" journal voucher for a Kept here company, and HrAdvances' Kept here
  booking (a payment voucher to Advances to staff). In their place both show the state the boards draw for a Kept
  here company with no chart of accounts: nothing is posted, the claim or advance is paid and recorded as a payment.
- **Depends on:** 11, 12. Can run beside 13, with migration numbers agreed before both open.
- **Phone note:** needed on a new claim with its lines and receipts; the Claims and Advances lists keep the narrow
  layout.
- **Checked by:** new synthetic tests: a claim over its limit is flagged, not refused; receipts become the payment's
  documents; a director's own claim cannot be approved by that director; SA numbers run app-wide; every existing
  advance survives the move with its balance, both with and without a staff record; the Claims and Advances exports.
  Click-through: a claim from entry to paid.

---

**Slice 15 · Payroll** (L in three parts, `slice-15a-run`, `slice-15b-outputs`, `slice-15c-parallel`)

- **Boards:** 15a PayrollRun.dc.html, SetupPayroll.dc.html; 15b PayrollTotals.dc.html, PayrollFiles.dc.html,
  PrintPayslip.dc.html, PrintPayrollOutputs.dc.html; 15c PayrollLeaver.dc.html, PayrollParallel.dc.html,
  PayrollOpeningYtd.dc.html.
- **Screens.** HR › Payroll gains the Run, Summary, Statutory files, Parallel run and Opening year to date tabs, only
  for a company with "Runs payroll in this app" on. The Workbook check tab stays for every company, read only for past
  months after the switch-over. Setup › HR › Payroll settings. Payslip, bank payment list, monthly summary and journal
  summary as printed.
- **Finishes on earlier boards.** "Runs payroll in this app", "HRDF registered" with its levy rate and headcount
  warning, and the HRD Corp employer number on SetupCompanies. The Payroll run type and the "Tax clearance letter
  (LHDN)" document type on SetupTypes. The salary-approval checklist item ticking itself from the run's form after the
  switch-over on SetupChecklist. Rows stopped at the switch-over on Recurring. The tax-clearance hold on ToPay.
  NewPayment sends Payroll run to HR. Salary-run forms (totals on page 1, people on page 2) on Approvals and
  PrintApprovalForm. "Include payslips" and the payroll pages on AuditPack. The link from per-authority totals to
  Statutory payables (BooksStatutory). FirstRun's "Runs payroll in this app" choice. On Sql, the payroll run's
  journal match ("Matches the October payroll run", "Open the payroll run"), and the run's "Waiting for SQL record"
  state on Payment and DarkPayment. A Payroll runs record filter on AuditTrail: the board does not draw one, so it is
  built in the style of the other filters (section 7.2).
- **Server work.** Section 4.9.
  - New company columns (migration): Runs payroll in this app, HRDF registered, HRDF levy rate, HRD Corp employer
    number, the other employer numbers the files need.
  - New tables (migration): pay items per company with their ticks; **payroll rates by date** (EPF, SOCSO, EIS,
    Lindung 24 Jam, PCB tables and minimum wage, each with the date it applies from); pay rules; yearly form due
    dates; runs (company, month, status, declared names, dates); run lines per person with **frozen figures** (every
    amount stored once approved, never recalculated in place); the opening year-to-date figures per person.
  - **Where dated rates live, and payrollcheck.py.** Today the Workbook check's rates are a fixed `RATES` table in
    `hrp/payrollcheck.py`. The dated rates go in the new table, filled at the migration from `RATES` with today's
    start dates. `payrollcheck.py` then reads the same table for the month it checks, so the Workbook check and the
    run can never use different rates. `payroll_check_test` must still pass unchanged after the switch.
  - **Payslip password key.** Personal payslip passwords are stored encrypted with a key kept like the form secret:
    in the records, made on first use, its creation logged, never in a Move setup file, an export or an audit entry.
    Backups carry it so a restore can still open payslips. `cryptography` is in `requirements.txt` already, but only `pypdf` uses it today (encrypted bank PDFs) and nothing
    imports it directly, so this key is its first direct use.
  - **Email sending** of payslips waits for decision 3 (section 7). Until then payslips are made as password-protected
    PDFs for download and the email states are not offered.
  - Routes: payroll settings, pay items and rates (list, add from a date), runs (start, recalculate a draft, check,
    approve, send to pay, file), payslips and output files, the parallel-run comparison and its sign-off, the
    switch-over, the opening year-to-date import with its preview.
- **Waits for stage 2:** a Kept here company's run posting its own journal. In its place the run stops at "Sent to
  pay" and "Filed", with the journal summary printed for the books.
- **Decisions first:** section 7, decisions 3 and 4 (how payslips are emailed; Maybank bulk payment), and the checks
  listed there.
- **Depends on:** 12, 13 (unpaid leave), 14 (advance repayments).
- **Phone note:** needed on the run, Summary, Statutory files, Parallel run and Opening year to date tabs; the
  payslip PDF is unaffected.
- **Checked by:** every figure tested against the government calculators and the payroll workbook check; then the
  parallel run for 2 to 3 months before the switch-over. Local `n8_payslips_test` (updated for the new payslips).
  Synthetic: `payroll_check_test` (unchanged on the dated
  rates), `statutory_test` (per-authority totals become statutory payments), new synthetic tests for each rate table
  by date, frozen figures, the payslip password never shown or exported, and the opening year-to-date import.

---

**Slice 16 · Users and access, sign-in, hosting** (L, `slice-16-access`)

- **Boards:** UsersAccess.dc.html, SignIn.dc.html.
- **Screens.** The people list with six rights (HR, Payroll figures, Payments, Accounting, Approver, Admin), add,
  edit, remove, last admin refused, menu previews; sign in, session timed out, user menu with sign out.
- **Finishes on earlier boards.** The menus by access on ShellMenus and Sidebar; HR cards hidden without HR access;
  pay amounts hidden without Payroll figures; search and notifications within access; real, verified names on
  AuditTrail, with its Users and access record filter; the Approver right tied to the approvers list; every view of
  a staff record logged.
- **Server work.** User accounts, password hashing, sessions and timeout, rights on every route, the signed-in name on
  every audit entry.
- **When.** Built when the owner decides hosting (section 7, decision 5). Stage 2 does not wait for it: if hosting is
  still open when payroll is switched over, stage 2 starts first and slice 16 follows whenever hosting is decided.
- **Depends on:** everything before it, and the hosting decision.
- **Phone note:** none for sign-in, which works at phone width; needed on Users and access's rights table.
- **Checked by:** new synthetic tests per right on every route; click-through as each of the four sample kinds of
  user.

### 3.4 Stays as it is

Routes and modules the slices do not name, which the pages keep calling as they are: `/api/open-payments`,
`/api/export`, `/api/overview`, `/api/integrity`, `/api/statement-suggestions`, `/api/statement-lines`, `/api/audit/*`,
`/api/auditor-export`, `/api/settings`, `/api/upload`, `/api/tasks`; and the modules `docstore`, `trail`,
`finstatements`, `sqlgl`, `ledger` and `partybook`. A slice that moves a page keeps its calls to these, and changes
one only where its "Server work" says so.

**Local tests no slice cited.** `n8_payslips_test` is added to slice 15 and `n11_ui_extras_test` to slice 10. All the
other tests named in this plan exist.

---

## 4. App changes the design asks for

These are behaviours the boards draw that the app does not do today. Restyling is not listed. Each goes with its
slice and gets a test.

### 4.1 Stage 1 app fixes (old plan section 3b)

Checked against the code on 19 November: only "Confirm again" exists; the rest are still to build. Lines are in
`static/app.js` unless named.

- **Slice 4, Bank:** "Confirm again" when book figures change after sign-off. Done in the app (line 1037, route
  `/api/recon/confirm-book`); only compare it with the board's state and wording.
- **Slice 5, SQL import:** supplier invoices labelled as such in the preview; a "Deleted in SQL" pill under Ignored;
  check-table sections in words; the unfinished import toast's sentence completed (no unfinished sentence was found in
  the code: compare the toasts at lines 4372 to 4386 with the Sql board). Today: every invoice is labelled "Customer
  invoice" (line 2160; `sqlimport.py` puts PI, SD and SC under the same kind); Deleted in SQL not shown (1588; the date
  is in the row data); raw `bank` / `general` sections (1496; `BOOK_NAMES` at 1651).
- **Slice 6, e-Invoices:** the print month defaults to the month being worked; MyInvois times as "1 Oct 2026, 11:19";
  each document's print note beside its PDF button. Today: the newest month (2084), raw ISO times (2053, 2058), no
  print note (2072).
- **Slice 7, Books:** a grey "Can't be totalled" pill on the trial balance when an opening is missing (it shows
  "Doesn't balance" today); no pill on an empty trial balance (a third, unknown, state in `books.py`, which has two today); an Excel failure shown in place, not as a raw error
  page; the statutory check does not judge months the kept journal doesn't cover (only months before tracking are greyed,
  `statutory.py`); one date style on Books pages (three in use).
- **Slice 9, Setup:** Printed invoices and Printed company names hidden for a company not kept in SQL (shown for every
  company today, line 2912); "Open Setup" from a print note opens that company's drawer (opens the list, 4393); the Move
  setup "Everything" sentence names statutory accounts, print settings and printed company names (line 3232 misses
  them; the export has all three).

### 4.2 The owner's decisions of 19 November

| Change | Slice | Where |
|---|---|---|
| **Joiner reminders merged.** One reminder "Register {name} with KWSP and PERKESO", due 7 days after the start date, replaces the separate KWSP (7 days) and PERKESO (30 days) registration reminders. "Stamp the contract of {name}" replaces "Stamp {name}'s appointment letter". The LHDN titles drop "to LHDN": "e-CP22 for {name}", "CP22A for {name}". {name} is the preferred name from the staff record (owner, 19 November: a preferred name field is added; the bracketed payee name, `db.short_name()`, is the fallback). A migration merges open, unticked registration items; ticked ones stay in history as they were. | 12 | The reminders live in the records (`people_tasks`, `people_task_terms`), seeded from `rules.PEOPLE_TASKS`, with short names in `checklistbook.PEOPLE_NAMES`: the migration rewrites those and the Move setup `reminders` section |
| **One Next up row per unpaid statutory payment.** While a statutory payment for the month is entered and unpaid, Next up shows only its payment row ("Pay KWSP for October", overdue after the due date). The rule 14 check row shows only when there is no unpaid payment to point at (paid short, or never entered). | 1 | `hrp/nextup.py` (`_statutory` rule 14, `_to_pay` rule 5) and `statutory.next_up` (`hrp/statutory.py`): rule 5 already lists unpaid statutory payments, so the change is a de-duplication |
| **Rule 14 wording and target.** "…Check it on Statutory payables." (not "on the Statutory tab"), opening the Statutory payables page, with the meta "Accounting › Statutory payables". | 7 | `hrp/nextup.py` line 462 |

### 4.3 Design-sweep decisions that change app behaviour

Of the sweep's 28 decisions, these change what the app does. The others only settle the boards' sample data, and the
build ignores them.

| Decision | Change | Slice |
|---|---|---|
| Payment names | None: the boards now follow the app ("KWSP", "PERKESO", "PCB" for payments; "EPF (KWSP)" and the other kind words for statutory kinds). | — |
| Reminder titles | Next up shows joiner and leaver reminders by their title with the preferred name ("e-CP22 for Daniel"). The new HR date rows (probation, permit) carry no name. | 12 |
| Documents missing | The Overview counter counts **checklist items** whose documents are missing; the checklist gets a "Missing documents" filter it opens. | 1, 2 |
| Rollover banner | Counts only the open month's Next up rows of the company it names. | 1 |
| Card and tab links | Every card and cross-page link opens the named tab or filter, through the address. | 0, then each slice |
| Discard and Undo | "Discard your changes?" on every form, except a dialog that discards a whole new item. Every Setup toast that confirms a change offers Undo. | 0, 10 |
| Many rows | Every new list has a many-rows state ("Showing 25 of 120", "Show 25 more"). Exception: six boards drawn before the scope (Setup, SetupCompanies, SetupParties, SetupChart, SetupMatching, SqlBooks) draw none; the sweep accepted that, so slices 9a and 5 build those states from the States patterns, without a board. | each slice |
| Budget with no balance | With no ringgit balance entered, Funds to request reads "Enter the bank balance to see funds to request", the fund-request print is hidden, and the print says "not worked out, bank balance not entered". Paid against the budget counts payments up to the balance date (already done in `hrp/budget.py`). Not done: the no balance state (a blank balance counts as 0 today), the balance read only from the stored budget (the browser keeps a copy today), and the bank label from the company's own account. | 8 |
| Paid date typed in | A payment can be paid with a typed date while the statement isn't imported, noted "Entered by hand"; the payment shows when its linked voucher changed in SQL, with "Move the link on the SQL import page to follow it". | 3 |
| Payment types | Setup's payment types are the one list on every page. The "Needs approval" default is set per type, following SetupTypes: no for Statutory, Utility / telco and Money received; yes for every other type, including Salary, Director allowance, Rental, Consultant fee, Other payment, Staff claim, Staff claim - overseas service, Inter-company transfer, Salary advance, Payroll run, and any type a company added. Slice 11's migration sets this default on every type in use. Owner-confirmed on 19 November: the Yes for Staff claim - overseas service, Inter-company transfer and any type a company added (the design sweep, D12, named only the others). | 11 |
| No approvers | A company with no approvers cannot print a form; Approvals says so and links to Setup. Form (AF) and advance (SA) numbers run app-wide, not per company. | 11, 14 |
| Bank reconciliation statement | The printed statement, the No money moved pairs, and the bank-rec upload states. | 4, 11 |
| Signature block | Every printed form has separate Signature and Date lines; with one approver it reads "The approver's signature approves this form." | 4, 11 |

### 4.4 Overview card rules (slice 1)

The 18 November design: one headline, one note, company lines only with All companies, four cards per row. With All
companies, money cards show one line per company marked Kept in SQL Account or Kept here. Every Accounting card for a
Kept in SQL Account company shows the date SQL's data runs to. A card that fails shows "Could not load, try again"
without hiding the others.

| Card | Shows | Follows the month? | Empty | Out of date | Opens |
|---|---|---|---|---|---|
| Needs attention | Past due, Part paid, Documents missing, Lines to explain, Not in SQL (Kept in SQL Account only); grey at zero | Yes | "Nothing needs attention" | | Each counter its own list |
| Checklist | Items done of total, "18 of 27" | Yes | "No checklist for this month yet" | | Monthly checklist |
| Due and overdue | Number and amount due in the next 7 days, and overdue | No, from today | "Nothing due" | | To pay, filtered (the register's Not paid tab until slice 11) |
| Funds to request | Still to pay less the bank balance on the Budget's balance date | Yes | "Enter the bank balance to see funds to request" | | Budget |
| Paid without approval on file | Count, including Paid more than approved and Paid, approval refused | Yes | Hidden | | Approvals, filtered (slice 11) |
| Bank | Balance per account at the latest statement line, with its date; the month's money in and out | Yes | "No statement imported for <month>" | "Statement runs to 12 Nov" | Bank and reconciliation |
| Profit or loss | This month and the financial year to date | Yes, plus year to date | "No books yet" (Kept here); "Nothing fetched from SQL yet" | "SQL data runs to 12 Nov, fetch again" | Books › Profit and loss |
| Customers overdue | Number and amount of customer balances **older than 30 days** inside the tracked period; balances brought forward from before tracking are not counted and show apart as "Before tracking" | No, as at today | "No balances" | "as at 12 Nov, fetch again" | Customers and suppliers, customers overdue |
| Suppliers due | Owed to suppliers, due in the next 14 days and overdue | No, as at today | "No balances" | "as at 12 Nov, fetch again" | Customers and suppliers, suppliers due |
| On leave | Names on leave today and a count for the week; never the leave type | No | "Add your staff to see this" | | Leave, team calendar (slice 13) |
| Dates coming up | Probation ends, contract ends, passport and permit expiries in 60 days, counted with no name; this month's birthdays and anniversaries, day and month only | No | "Add your staff to see this" | | Staff › Calendar and reminders, filtered (slice 12) |
| Headcount | In employment today; joiners and leavers this month | No | "Add your staff to see this" | | Staff (slice 12) |
| Requests waiting | Waiting for approval; approved, waiting to pay | No, now | "Nothing waiting" | | Approvals (slice 11; HR requests from slice 14) |

**Never on the Overview:** a salary or pay figure, payslip, IC or passport number, bank account, address, tax or EPF
number, a reason or type of leave, a medical detail, a claim receipt or one person's claim, an age or year of birth.
The payroll total shows only as one Payments line ("Salaries, October").

### 4.5 Approvals and To pay rules (slice 11)

- **Requests.** For now a request is a payment that needs approval (a supplier bill, a recurring set-up or amount
  change). Claims, advances and salary runs join the same model in slices 14 and 15. Statuses: Draft, Waiting for
  approval, Approved, Not approved, Paid, approval refused, Withdrawn, Paid, Recorded, Done.
- **Forms.** Code AF-yymm-nnn, a keyed check and a QR. Up to 3 approvers per company, printed with signature lines;
  any one signature approves. Single, batch and mixed forms. An approver who is the payee is struck through ("Can't
  sign: payee"); with one approver it is "Self-approved" and listed in the audit pack.
- **Upload.** The code is read from the PDF's text, from the QR in a scan or photo, or typed. The date on the form is
  typed; the upload date is kept apart. A digitally signed PDF's signer is matched to the approvers. A paper scan asks
  which approver signed, and shows "Approver chosen by <name> from a paper scan". Cases: some requests changed, no
  longer matches, uploaded twice, signer not an approver.
- **Locks.** Once approved, a request is locked. Changing its amount, payee or lines sends it back to Draft and voids
  the approval (kept in history). Not approved and Withdrawn need a reason.
- **The Approval marker** on every payment: Not needed, Waiting, Approved by <name> <date>, Paid without approval on
  file, Paid more than approved (RM x), Paid, approval refused. Approval never blocks a payment.
- **Paid without approval on file** list, and Approved after payment with both dates; the checklist item "Approvals on
  file for every payment" ticks itself when the month's list is empty.
- **Month review.** MR-yymm-company, printed, signed by one approver, uploaded the same way; "Month reviewed" ticks
  when it is on file.
- **Declared names.** Until sign-in (slice 16) the app cannot know who is at the keyboard, so "who" at each step is
  the name chosen or typed there: the requester, who entered or paid the payment, and who chose the approver from a
  paper scan. Each is stored with its step and labelled "declared, not verified" in the audit pack.
- **Warnings, never blocks:** the same declared name as requester, payer and approver. AuditPackHR's "Steps done by
  one name alone" page lists, per month, every request where they were the same name.
- **Approvers.** Kept per company with dated history; an old approval keeps the name as it was. Creating or changing
  the secret is logged; it is never in a Move setup file. Approver names in Move setup sit behind a checkbox.
- **Recurring.** Approved once, when set up or when its amount changes ("Amount changed: needs a new approval form"),
  or per payment where the row says so.
- **To pay.** Approved and not-needed items, not yet paid, grouped as overdue, this week and later, with Excel.
  Selecting several and pressing Pay makes one payment per item, all with the same bank reference; slice 4's
  one-line-to-many link matches them to the bulk bank line. Unapproved items show only on Approvals.

### 4.6 HR staff rules (slice 12)

- **Who is staff** (17 November): directors on the payroll are staff records (they have EPF and PCB). Contract workers
  stay payees unless they are on the payroll.
- **From payees to staff records:** joiner and leaver reminders come from recurring salary rows until a company has
  staff records, then from the records (slice 12 block).
- **The record:** personal (including a **preferred name**, used in reminders, with the bracketed payee name as the
  fallback), job, pay (salary history from a date, never overwritten), statutory numbers, PCB details,
  documents with expiry dates (stored under a code, not the person's name), emergency contact, notes.
- **Worked out:** EPF rate group, SOCSO category and EIS cover from date of birth, citizenship and first-contribution
  date, changing from the month after the 60th birthday (common practice, marked "check with KWSP and PERKESO").
  Override only with a reason. Lindung 24 Jam covered or opted out from a date.
- **Payslip password:** the IC number without dashes by default (passport number for a foreign worker), or a personal
  password set by HR, stored encrypted, never shown again, resettable. It appears in no list, export or audit entry.
- **Privacy:** IC masked to the last 4 everywhere on screen; race and religion optional and out of exports by default;
  the Excel export asks for columns with sensitive ones off, and is logged as a read; the staff record PDF shows the
  full IC and is marked "Confidential: personal data".
- **Leaving:** "Left" with last day and reason; no delete once the person has pay, leave or claims; CP22A or CP21
  reminders from the reason, which start the tax-clearance hold (shown in To pay with slice 15). Kept 7 years after
  leaving, then listed for removal with a confirm. A move to another company makes a leaver and a joiner, linked.
- **Reminders** from the record: birthday and anniversary (no year), probation 30 and 7 days before, contract 60 and
  30, passport and permit 90, 60 and 30; joiner and leaver tasks on the month's checklist as today, now from the start
  date and last day; mark done; one-off reminders.
- **Public holidays** per company: state and rest day; 2026 Wilayah Persekutuan Kuala Lumpur bundled (2027 only once
  checked against the official list); the five holidays fixed by law locked; untick down to 11, never fewer; moving
  dates marked; one-off days; replacement days worked out from the rest day.

### 4.7 HR leave rules (slice 13)

- Working days skip rest days and the company's public holidays. Entitlement is the legal minimum by years of
  service, using the person's work location (Peninsular Malaysia and Labuan, or Sabah and Sarawak with a note).
  Prorated for joiners and leavers.
- Leave above the legal days, or a policy value set above the law, shows a warning only, never refused. A policy below
  the legal minimum is refused. Over-balance and clashing leave are warned about, never refused.
- Cancelled leave stays with its reason; its days go back to the balance. Maternity asks HR to confirm eligibility.
- Opening balances import, year-end carry-forward, balances at a date, Excel of every list. Unpaid leave days are kept
  for payroll; a company without payroll in the app gets the note to deduct them by hand.

### 4.8 HR claims and advances rules (slice 14)

- Claim types per company: expense account, optional monthly limit, receipt required. Over the limit is flagged, not
  refused. An overseas claim needs its self-billed e-Invoice, as today.
- A claim goes on an approval form, then to To pay, and is paid on its own, never through payroll. Its receipts become
  its payment's documents; the claim and the payment link to each other.
- A director's own claim or advance needs a different approver.
- Advances: amount, monthly deduction, from and to month, as today, now under HR with an SA number. Warnings, never
  blocks, when an advance is over one month's pay or a month's deductions pass 50% of wages. A leaver's balance is
  deducted within that limit and the rest kept as an amount to collect.
- Bookings for a Kept here company (journal and payment vouchers) wait for stage 2.
- Existing advances keep their payee and gain a staff record where one exists; the rest move when HR links the payee
  (slice 14 block). Claims and Advances each have an Excel export.

### 4.9 Payroll rules (slice 15)

- **Settings per company:** "Runs payroll in this app", HRDF registered (off by default, with a warning at 10
  Malaysian staff), employer numbers. Pay items with their ticks (EPF, SOCSO and EIS, HRDF, PCB normal, PCB
  additional). Rates and tables with the date they apply from, matching the Workbook check's rates. Minimum wage.
  Pay rules (a less generous rule is refused). Yearly form due dates; the monthly due days stay on Statutory accounts.
- **The run:** Draft, Checked, Approved, Sent to pay, Filed, plus "Waiting for SQL record" and "Recorded" for Kept in
  SQL Account. Self-checks before approval. Refused while recurring salary rows are in use for the same people and
  month. Warned when approved after the 7th. Figures frozen once approved or sent to pay; recalculating an old run is
  for comparison only.
- **Outputs:** payslip PDF (IC masked, "Approved by", password as in 4.6, emailed with the rule named and never the
  password; each send or failure in the audit trail); monthly summary; per-authority totals that become the statutory
  payments; bank payment list; EPF, PERKESO and e-PCB Plus files; the journal summary that Fetch matches for a Kept in
  SQL Account company. EA forms and Form E before the first February after go-live.
- **Leaver's final pay** with "Hold until tax clearance" until LHDN's letter is uploaded or 90 days pass.
- **Parallel run:** the app's figures beside the month's latest Workbook check, every difference listed, signed off
  with a declared name. **Switch-over** stops the company's recurring salary and statutory rows from the signed-off
  month.
- **Opening year to date** imported once, with a preview.

---

## 5. New features kept from the design

These are not on screen today. The owner chose to keep them. Each is built inside the slice named. Some already
have part of their server support; the column says only what is left, to be checked against the app first.

| Feature | Server work left | Size | Slice |
|---|---|---|---|
| Document viewer beside the payment dialog, and Download; later also claim receipts and signed forms | The file route already serves inline, or as a download with `?download=1`; left: check the file type before serving inline | S | 3; receipts 14, signed forms 11 |
| Bank account field in the payment dialog | The save already takes `account_id` (checked by `own_account()`); left: recheck both accounts' reconciliation when it changes | S | 3 |
| Drag and drop on the SQL file box | None | S | 5 |
| Sidebar badges: Next up rows per area, plus the Approvals and To pay counts (blue; To pay red when overdue) | Next up rows carry their area; one cheap counts route | S | 0; counts 11 |
| Overview extras: Funds to request (now a card), Recent activity (HR and payroll-check events with no private detail), Needs attention, the switcher as company filter | Activity is read from the audit trail (`/api/activity` exists) | M | 1 |
| Backup extras: recent backups, password strength meter, Restoring card, "am I backed up" | Backup events read from the trail | S | 9b |
| First run, with "Where are the books kept?"; "Add your staff" as next step | None (setup-file import exists) | S | 9a; next step 12 |
| Undo on toasts, every rebuilt page and every Setup toast | A short-lived undo record per action, in the audit trail as its own entry | M | 10, then each slice |
| Search (Ctrl K), with staff and requests, and the actions Add leave, New claim, Print approval form, Upload a signed form | A search route; later slices add their records | M | 10; staff 12, requests 11, leave 13, claims 14 |
| Notifications bell with read state: approval form uploaded, form doesn't match, leave ending, permit expiring | An events table and a read marker | M | 10; events 11 to 13 |
| Sign in, session timeout, user menu, real names in the audit trail | Accounts, password hashing, sessions, `who` on every entry | L | 16 |
| Phone photo of a signed form (the fifth phone screen) | | | Deferred with the phone design |

---

## 6. Order and rough effort

### 6.1 Phases

| Phase | Slices | Sizes | What the owner gets |
|---|---|---|---|
| Redesign build | 0 to 10 | 5 L, 6 M | The whole app in its new shape, the stage 1 fixes, the kept features |
| HR step 1 | 11 to 14 | 4 L | Approvals on paper, To pay, staff, leave, claims and advances |
| Payroll | 15a to 15c | 3 L, then 2 to 3 months of parallel run | Payroll in the app, then the switch-over |
| Users and access | 16 | 1 L | Sign-in and access rights, with hosting; built when hosting is decided, and stage 2 does not wait for it |

Payroll is the largest and riskiest part: its figures must agree with the government calculators month after month
before the switch-over.

### 6.2 What can run side by side

**Never side by side:**
- Anything with slice 0: every other slice builds on it.
- Two slices that both add migrations, unless their numbers are agreed first (one chain in `hrp/db.py`).
- Two slices that both change `hrp/nextup.py`: 0, 1, 7, 11, 12, 15 (and 13, if it adds Next up work; its block has none today).
- Slices 5 and 6: both take code out of today's SQL page.
- Slice 11 with any HR slice: they all build on its request model.
- Slice 1 beside or before slice 8: Funds to request needs 8's Budget rules.
- Slice 11 while any of slices 0 to 10 is still open.

**Side by side, after slice 0:**
- 8 (Budget and Recurring) beside 2 then 3 (register, then dialog); then 1 (Overview) once 8 is merged.
- 2 then 3 beside 5 then 6 (SQL import, then e-Invoices).
- 4 (Bank) beside 9a (Setup), once 3 is merged.
- 7 (Books) after 5, beside 9a or 9b; 7 and 9a in either order.
- 13 (leave) beside 14 (claims and advances), after 12.
- Stage 2, after payroll, beside or before 16 (16 waits for hosting).

With one reviewer, two slices open at a time is the practical limit.

### 6.3 Where the owner clicks through

Every slice ends with a click-through on sample data. These are the larger walk-throughs:

| After | The walk |
|---|---|
| Slice 0 | A normal month's work inside the new shell: nothing lost, every page at its new place |
| Slices 1 to 4 | Month-end in the new face: Overview, register, checklist, a payment, reconciliation and its printed statement |
| Slices 5 to 10 | The whole redesign: SQL fetch, e-Invoices, Books, Budget, Setup, audit pack, search, Undo; light and dark; keyboard only |
| Slice 11 | A paper round trip: print a form, sign it, scan it, upload it, pay from To pay, print the Month review |
| Slice 14 | HR step 1: add a joiner, record leave, a claim from entry to paid, an advance |
| Slice 15 | Each parallel-run month's comparison and sign-off, then the switch-over |
| Slice 16 | Sign in as each kind of user, with hosting |

---

## 7. Open decisions and known design leftovers

### 7.1 Decisions still open for the owner

Decisions 1 and 2 are closed (below); the numbers stay as they are.

3. **How payslips are emailed** (slice 15b). The boards draw emailed and failed payslips "with the mail server's
   reason". Which mail account sends them, and where is it set? Nothing in the sources decides this.
4. **Maybank bulk payment** (slice 15b). The scope says to confirm, when payroll is built, that the company uses
   Maybank's bulk payment file.
5. **Hosting** (slice 16). Where the app is hosted, and when. Sign-in is built with it. Stage 2 does not wait for
   this decision.
6. **Reading QR codes from scans and photos** (slice 11). Already approved by the owner on 16 November: add a
   QR-reading library when HR is built (for example zxing-cpp). Still to confirm in slice 11: which one, checked for
   offline use on Windows and its licence (some ship a native file, a DLL, with the app); `segno`, already there, only
   makes QR codes. A typed code is the fallback either way. Signers of digitally signed PDFs are read with `pypdf`,
   already there, with no new library.

**Closed since the old plan:**
- **Decision 1, fonts** (slice 0): decided 19 November, bundled. Inter and Space Grotesk (variable, SIL Open Font
  License) are in `static/fonts/` with `fonts.css` and the two licences. Slice 0 links `/static/fonts/fonts.css` from
  `index.html`.
- **Decision 2, sign-off with items left** (slice 4): owner, 19 November: **no**. Keep today's rule, the book closing
  must equal the bank closing. The boards already keep it. Slice 4 does not wait on it.
- KWSP on Next up (one row, 19 November); the tenant sample figure (sample data only);
sign-in timing (with hosting, slice 16).

**Checks, not decisions, before payroll goes live:** whether the 60-and-over rates start in the birthday month or the
month after (KWSP, PERKESO); Lindung 24 Jam's banded amounts and rounding (PERKESO); whether the company is registered
with HRD Corp; the official 2027 Kuala Lumpur holidays.

### 7.2 Design leftovers to handle during the build

From the final sweep and `packageK-notes.md`. None needs the canvas redrawn before the build starts.

| Leftover | What the build does | Slice |
|---|---|---|
| Phone boards still carry old wording ("KWSP (EPF)", "e-CP22 for the joiner") and links to Company.dc.html | Nothing: phone is deferred | — |
| MobileApprovalPhoto is linked from five boards but not drawn | Those links show no phone action; on the computer the upload is on Approvals | 11 |
| Approvals does not list printed reconciliation statements waiting for their signed copy | List them on Approvals' Waiting tab, since their upload uses the same screen | 11 |
| AuditPack does not show the signed statement and its sign-off note | Show both on the pack's reconciliation page, as the scope says | 4 |
| Payment and DarkPayment "Open on Purchases" lands on Sales | Link it to the Purchases placeholder | 3 |
| ToPay's Kept here paid toast names "PV2611-001" without the company prefix | Stage 2 wording; ignore now | — |
| States and DarkPalette show a generic "November payroll has started … 3 things left" banner | Use the Overview's wording ("November has started", the named company's count), with no "payroll" | 1 |
| SetupMove's counts ("2 companies"; totals that include the stopped company) and FirstRun's counts disagree | Counts come from the app's setup file (`hrp/setupfile.py`: stopped rows in, deleted rows out) | 9a |
| Requests waiting opens Approvals only; "approved, to pay" is in its note | Build as drawn | 1 |
| The empty Funds to request and Bank sentences wrap to two lines | Allowed | 1 |
| PrintHrLists draws only two people's records and October's lists | The build prints any person and any period | 12 to 14 |
| AF-2611-003's over-limit line prints plain (the limit was set after printing) | Intended: a form prints its requests as they were at printing | 11 |
| Audit entry numbers on the Setup boards (1xxx) disagree with the trail's (4xxx); two Maybank savings numbers; Recurring's "Add to Oct" on a paid bill; the Telephone & internet bank line | Sample data only; the app shows real numbers | — |
| Two boards print warnings from their checker (Sql reports-only, SetupChecklist reminders) | Board scripts only; not app behaviour | — |
| `$preview` heights of Main, DarkOverview, OverviewCards and Foundations are estimates | Canvas layout only | — |
| Company.dc.html kept as an unlinked source | Retire it from the canvas once slice 2 is merged | 2 |
| AuditTrail draws record filters for Approvals, Claims, Salary advances and Users and access, but none for payroll runs | Each slice adds its filter (11, 14, 16); slice 15 adds a Payroll runs filter in the same style | 11, 14, 15, 16 |
| Stage 2 states drawn on boards built now (Kept here vouchers on Payment, NewPayment, ToPay, HrClaim, HrAdvances, SetupRequired, payroll runs) | Each slice's "Waits for stage 2" list says what the app shows instead | 3, 9a, 11, 14, 15 |
