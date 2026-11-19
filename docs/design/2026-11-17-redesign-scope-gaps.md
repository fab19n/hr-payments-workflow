# The redesign after the new scope: what changed and what is new

17 November 2026. This answers the question "what has changed, and what is new, for the new redesign?"

Sources:
- The approved scope, `docs/2026-11-16-hr-payments-accounting-scope.md`. Section 10's checklist is the yardstick.
- The code since the canvas was brought up to stage 1: `git log b698dc1..HEAD` and `git diff -w b698dc1..HEAD`.
- The design canvas: 52 boards, read with grep. No board was changed.

Boards use made-up names and figures only. Nothing here comes from the owner's payroll workbook.

---

## 1. What changed since 16 November

### In the code

Two commits add one page: **9bdf070** and **b2e0994**, the Payroll workbook check. Apart from line endings, nothing
else in the app changed. `git diff -w` shows real changes only in `hrp/payrollcheck.py` (new),
`hrp/app.py` (three routes), `hrp/nextup.py` (rule 15), `hrp/db.py` (migration 38), `hrp/auditread.py` (4 lines),
`static/app.js` (`viewPayroll`), `static/app.css` (6 lines) and `README.md`.

| What the user sees | Where in the code | What the boards lack |
|---|---|---|
| A **Payroll check** page under Monthly work. You upload the month's payroll Excel, and the page lists what is wrong under three labels: "Fix before paying", "Check" and "Note". | `static/app.js` VIEWS `["payroll", "Payroll check"]`, with the comment "The Payroll check sits under Monthly work until the redesign moves it to HR." | No board draws it. Sidebar's `active` enum has no `payroll`. |
| A headline such as "3 things to fix before paying, 2 to check; 4 notes", findings grouped as Summary, one group per payslip and "The whole workbook", an "Amounts to pay · as the Summary has them" table (KWSP, SOCSO, EIS, SKBBK, PCB), the earlier checks of the month, and an "Excel report". | `payrollcheck.headline`, `report_of`, `/api/payroll-check/export.xlsx` | Not drawn. |
| The workbook is filed on the month's checklist item "Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB" (code `payroll-calc`), with the note "Uploaded on the Payroll check page". A newer check replaces the older file. | `payrollcheck.save`, `hrp/rules.py:97` | Company.dc.html has no payroll item for AISB in October. Its "Payroll summary filed" item (line 818) is in AI's block (`co === 'AI' && mon === 0`). |
| IC numbers are masked except the last 4 characters, everywhere, the Excel report included. | `payrollcheck.mask` | This is the first masking rule in the app, and HR boards should follow it. |
| Rates "as at Nov 2026". The EIS exemption for a worker who first contributed at 57 or over, and the over-60 timing marked as common payroll practice. | `RATES` in `payrollcheck.py` (b2e0994) | Setup › HR › Payroll settings must show the same rows and dates. |
| **Next up rule 15**: "Oct AISB: the payroll check found 3 things to fix before paying". It is priority 1, opens the Payroll page, and carries no name or amount. | `hrp/nextup.py` lines 479-480, `_row(15, …, {"view": "payroll"}, "payroll")` | No Next up sample has it. |
| The audit trail shows "Payroll check" records, and opening the Excel report is logged as a read. | `auditread.py` TABLE_LABELS `payroll_checks`, `@audited_read("payroll check export")` | AuditTrail.dc.html has no payroll filter. |
| The error page "The records need update 38 for the payroll check. Restart the app." | `/api/payroll-check` | This is the existing "Couldn't load this page" kind, so no new pattern is needed. |

Unchanged but relevant: Next up rule 14 still reads "Check it on the Statutory tab." and opens
`{"view": "books", "tab": "statutory"}` (`nextup.py:462`). The new menu turns Statutory into its own page, so both the
wording and the target must change.

### In the scope (approved 16 November, owner's answers 17 November)

- **Five areas**: Overview, HR, Payments, Accounting and Admin, replacing Dashboard, Companies, Monthly work,
  Accounting, Filing and Setup.
- A **company switcher** in the top bar replaces the one-menu-item-per-company list. The Overview can show All
  companies, the Staff list can show All companies read only, and every other page works on one company. On screen,
  companies are labelled **Kept in SQL Account** or **Kept here**.
- **Four steps** (Request, Approve, Pay, Record and reconcile). Approval is a printed form with a reference code, a
  keyed check and a QR code, up to 3 approvers, and any one signature approves. An Approval marker appears on every
  payment, and there is a "Paid without approval on file" list. Approval never blocks paying.
- New Payments pages: **Approvals** and **To pay**. The company month page splits into the **Payments register** and
  the **Monthly checklist**. A printed **Month review** sheet is signed each month.
- **HR step 1**: staff records, leave, calendar and reminders, claims and salary advances. Advances move out of
  Recurring.
- **HR step 2**: payroll, run in the app for a company with "Runs payroll in this app" on (AISB today), with a parallel run and a switch-over. The Payroll check stays available to every company (owner, 17 Nov).
- Accounting gains **e-Invoices**, **Customers and suppliers** and **Statutory payables** as pages of their own, a
  locked month and reopen on the bank reconciliation, and "book this line" for Kept here companies. Sales, Purchases,
  Journals and Period close get placeholders.
- Admin gains **Setup › HR** (approvers, leave, public holidays, claim types, payroll settings) and **Users and
  access** (drawn now, built with logins).
- A **fifth phone screen**: photograph a signed approval form.
- **English only** on screens and on everything printed. Existing boards are moved, not redrawn, where nothing changes.

---

## 2. The new shape

### The menu

Two choices settled here, both left to the designer by scope section 2:
- Calendar and reminders becomes a tab of Staff, and Salary advances becomes a tab of "Claims and advances". With the
  menu fully open, AISB has 24 rows. Sidebar.dc.html's `min-height` is 1020px, and the logo, status card and user
  block also need room. The staff record already has a "Claims and advances" tab, which matches this choice.
- The user block (Aisha Rahman, Sign out) leaves the sidebar footer. The top bar already has the user menu.

Numbers in brackets are badges. The Payroll badge follows the existing rule in Sidebar.dc.html line 80: "ONE BADGE
RULE. A sidebar number is how many Next up rows belong to that area". Rule 15 is a Next up row, so Payroll shows 1.
Approvals and To pay are the only **count** badges, as scope section 2 asks. They are drawn neutral blue, and To pay
turns red when an item is overdue.

| AISB · Kept in SQL Account, runs payroll | AIL · Kept in SQL Account, no payroll run | AI · Kept here | Kevin Lim (Payments and Accounting only), on AISB |
|---|---|---|---|
| **OVERVIEW** Overview | Overview | Overview | Overview (no HR cards) |
| **HR** Staff (tab: Calendar and reminders) · Leave · Claims and advances · Payroll [1] | Staff · Leave · Claims and advances · Payroll (the Workbook check only) | Staff · Leave · Claims and advances · Payroll (the Workbook check only) | No HR group |
| **PAYMENTS** Approvals [3] · To pay [5] · Payments register · Monthly checklist · Budget [1] · Recurring | the same | the same | the same |
| **ACCOUNTING** Bank and reconciliation [1] · SQL import [1] · e-Invoices · Books · Customers and suppliers · Statutory payables [1] | the same | Bank and reconciliation · e-Invoices · Books · Customers and suppliers · Statutory payables, then a quiet "Kept here" sub-group: Sales · Purchases · Journals · Period close | the same as AISB |
| **ADMIN** Setup · Audit pack · Audit trail · Backup [1] · Users and access (Admin right only) | the same | the same | No Admin group (he has no Admin right) |
| 22 rows | 22 rows | 25 rows | 13 rows |

### The company switcher

- It sits in the top bar, left of the month switcher. The button reads "AISB · Kept in SQL Account ▾". The menu lists
  each company in use with its code, full name, label and Next up count. Stopped companies are not offered.
- "All companies" is offered only on the Overview, and read only on HR › Staff.
- When you switch, you stay on the same page if it exists for the new company. Otherwise you land on that company's
  Overview, with the toast "SQL import isn't used for AI (Kept here). Showing AI's Overview."
- With no company yet, the button reads "No company yet" and the menu holds "Add your first company". This moves
  from the Sidebar's `companies=none` box.
- The switcher replaces the in-page `role="group" aria-label="Company"` control. Grep finds that control on 19
  boards: AuditPack, Bank, BankReview, Books, BooksLedger, BooksParties, BooksStatements, BooksStatutory, Budget,
  CommandPalette, DarkBank, Recurring, Setup, SetupChart, SetupChecklist, SetupParties, SetupStatutory, Sql and
  SqlBooks.
- The month button reads "October 2026", not "October 2026 payroll". Payroll is now an HR page, and only some companies run payroll in
  the app, so the word would mislead. "Payroll month runs until" stays as the setting's name in Setup › General.

### Every existing board, its new place and its action

Actions: **move** means a new place and a new menu key or breadcrumb, with the in-page company control removed and no
content change. **tweak** means small additions or states. **rework** means a substantial redraw. **split** means the
board becomes two. No board is kept untouched and none is retired: every board at least changes its menu key or
breadcrumb.

| # | Board (canvas title) | New place | Action | The change, in one line | What I saw |
|---|---|---|---|---|---|
| 1 | Foundations.dc.html (Foundations) | Shared | tweak | Company-switch rule rewritten (top bar, not an in-page control); new address examples; Kept in SQL Account / Kept here chip; Overview card anatomy and states; Approval marker and request pills; print section; icon count | "Company switch, one place everywhere: a segmented control (AISB, AI)…"; "Two-tone icons · 68 glyphs" |
| 2 | DarkPalette.dc.html | Shared | tweak | Dark tokens for the company chip, switcher menu, card states, count badges, Approval marker; the new States items in dark | Headings "Dark colours", "The States board in dark" |
| 3 | Icon.dc.html (Icon (shared)) | Shared | tweak | Add 12 glyphs (section 4) and update NAMES and the glyph enum | `const NAMES = ['overview','company','payment',…]`, 68 names, no `payroll` |
| 4 | Sidebar.dc.html (Sidebar (shared)) | Shared | rework | Five areas; `kind` (sql / sql-payroll / here) and `access` (full / no-hr / no-admin) props; new active keys; count badges; folded HR; user block removed | Groups "Dashboard / Companies / Monthly work / Accounting / Filing / Setup"; `active` [overview, aisb, ai, ail, aip, budget, bank, sql, recurring, books, pack, trail, backup, setup] |
| 5 | Topbar.dc.html (Top bar (shared)) | Shared | rework | Company switcher (`company` aisb / ai / all / none, `allowAll`); switch toast; breadcrumbs Overview / HR / Payments / Accounting / Admin; search placeholder with staff and requests; user menu with access rights and a "Users and access" link; month label without "payroll" | `<span aria-live="polite">{{label}} payroll</span>`; placeholder "Search payments, payees, SQL docs"; no company control |
| 6 | SetupNav.dc.html (Setup menu (shared)) | Admin › Setup menu | rework | Add a seventh group, HR (Approvers, Leave types and policy, Public holidays, Claim types, Payroll settings); hide Matching words for Kept here; hide Payroll settings where no payroll; Recurring note reads "Opens Payments › Recurring" | 6 groups / 16 entries; `['payees', 'Recurring payments', …, 'Opens the Recurring page']` |
| 7 | States.dc.html (Empty, error and confirm states) | Shared states | tweak | Add: page not used for this company; no access (later); company-switch toast; "Add your staff to see this"; many rows (desktop and phone); refused with the reason (form banner); confirms "Change an approved request?", Not approved, Withdraw, Mark as left; empties "Nothing waiting for approval", "Nothing to pay" | Sections "Empty and error pages", "Confirms", "Toasts"; no many-rows block |
| 8 | Main.dc.html (Overview) | Overview | rework | Keep the top part (audit-trail notice, date, Next up, older months); add the four card rows; retire the tiles and per-company cards; remove "Show tasks for" (the switcher is now the company filter); rule 15 row; Recent activity with HR and payroll-check events | View enum [default, caught-up, nothing-recent, error, first-run]; "Show tasks for" at lines 145 and 155 |
| 9 | DarkOverview.dc.html (Dark · Overview) | Overview (dark) | rework | Twin of the new Main: card rows, switcher, rule 15 row, payroll-check activity line; stale, failed and grey-zero card states in dark | Imports Topbar `section="Dashboard"` |
| 10 | CommandPalette.dc.html (Search (Ctrl K)) | Search | tweak | Staff and Requests result groups; Go to rows with their new areas; actions "Add leave", "New claim", "Print approval form", "Upload a signed form"; no-HR result state | View enum [recent, results, none]; `['Go to','bank','Bank statements','Monthly work']` |
| 11 | Notifications.dc.html | Notifications | tweak | Events "Approval form uploaded", "Form doesn't match", leave ending ("Aina is back on Mon 23 Nov", no type), permit expiring; HR events hidden without HR access | Events e0 to e6, none from HR |
| 12 | SignIn.dc.html (Sign in) | Getting started | tweak | Password hint reads "…in Admin › Users and access"; optional no-HR welcome | "ask the owner to set a new one for you in Setup" |
| 13 | FirstRun.dc.html (First run) | Getting started | tweak | Hint reads "Shown in the company switcher"; adds "Where are the books kept?" (Kept in SQL Account / Kept here) and "Runs payroll in this app"; next step "Add your staff or paste the Excel list" | View enum [start, …, added]; hint "Shown in the sidebar, for example AISB." |
| 14 | Company.dc.html (Company month · AISB) | Payments | split | Becomes PaymentsRegister and MonthlyChecklist (new boards 21 and 22); the file is kept as the source until both exist | View enum [october, sent-here, filed, loading, september, november, august]; h3 "Payments" and h3 "Checklist" on one page |
| 15 | DarkCompany.dc.html (Dark · Company month) | Payments › Payments register (dark) | rework | Becomes "Dark · Payments register": Approval column, Paid without approval tab, request links, Excel | Same view enum as Company |
| 16 | Payment.dc.html (Payment drawer) | Payments › payment dialog | rework | Approval marker with all six readings; Request and Approval form blocks under Linked records; claim receipts from the claim; viewer showing a claim receipt and a signed form; "Kept here (AI)" sample with the cancel-and-repost warning; locked month; same-name warning; account-move note | "Company not kept in SQL (AI)"; "Bank account it was paid from"; `viewer: null, vPage: 1, vZoom: '100'` |
| 17 | DarkPayment.dc.html (Dark · Payment drawer) | payment dialog (dark) | tweak | Approval marker (approved, paid without approval) and Request block in dark | Mirrors Payment, no view enum |
| 18 | NewPayment.dc.html (New payment) | Payments › Add payment | tweak | Subtitle "For one-off bills and money in, not coming from a request"; "Needs approval" tick; claim and advance types point to HR; Kept here money in opens a Sales receipt; page behind is the register | Subtitle "For ad hoc payments, claims and receipts in October 2026." |
| 19 | Budget.dc.html (Budget) | Payments › Budget | move | Eyebrow "Payments"; the in-page AISB / AI picker goes | View enum includes `ai`, `print`; eyebrow "Monthly work" |
| 20 | Recurring.dc.html (Recurring payments) | Payments › Recurring | rework | Advances block replaced by a pointer to HR › Claims and advances; salary rows list their staff, with dates read only from the staff record; approval once ("Approved by Rajesh Kumar, 3 Nov 2026"; "Amount changed: needs a new approval form"); AISB salary and statutory rows stopped at switch-over | `<h3 id="rc-adv-h">Salary advances</h3>`; seed `adv … left: '1,000.00'`; view enum includes `advances` |
| 21 | Bank.dc.html (Bank statements) | Accounting › Bank and reconciliation | tweak | Renamed; sign-off locks the month; "Undo sign-off" becomes "Reopen month" with a reason; locked, reopen and reopened states; AI as Kept here (no SQL check) | "Undo sign-off", comment "Sign-off, undo and before tracking run with no confirm step"; no lock or reopen on this board |
| 22 | DarkBank.dc.html (Dark · Bank statements) | Accounting (dark) | move | Renamed "Dark · Bank and reconciliation"; adds the locked pill | View enum identical to Bank |
| 23 | BankReview.dc.html (Bank statements · review) | Accounting › Bank and reconciliation › review | tweak | One line linked to several payments, with a running total ("Link 8 payments"); "Enter this in SQL Account" note on a bank charge; Kept here "Book this line"; locked review | Explain dialog: "Link to an existing payment" (one Link per row), "No documents needed (bank charge)" |
| 24 | Sql.dc.html (SQL import) | Accounting › SQL import (Kept in SQL Account only) | tweak | e-Invoices card and Print / zip controls move to e-Invoices; a `not-sql` view enum value with "Agrinexus International is kept here, so there is nothing to import from SQL Account"; JV2610-007 shown matching a payroll run (later) | `notSql: !isSql` block with no view value; the e-Invoices card and `aria-label="Print invoices"` sit in the `isSql` branch |
| 25 | SqlBooks.dc.html (SQL import · account lines and checks) | Accounting › SQL import | move | Breadcrumb and switcher only | View enum [lines, …, no-reads] |
| 26 | MyInvois.dc.html (SQL import · MyInvois e-Invoices) | Accounting › e-Invoices | rework | Retitled "e-Invoices"; takes the SQL page's e-Invoices card; Print column and "All of the month"; Issued / Received / Self-billed tabs; fetch panels replaced by a source line; Kept here state | h1 "SQL import · MyInvois e-Invoices"; filter all / received / self_billed |
| 27 | InvoicePdf.dc.html (Printed invoice) | Accounting › e-Invoices › printed document | move | Back link to e-Invoices; month zip refers to "All of the month"; same PDFs | `href="Sql.dc.html"` back link; "The layout is SQL's own and is not restyled." |
| 28 | Books.dc.html (Books · Trial balance) | Accounting › Books | tweak | Tabs go from 6 to 4 (Customers and suppliers and Statutory leave); h1 "Books"; AI shows "No books yet" | `const TABS = [… ['parties', …], ['statutory', …]]` at line 582 |
| 29 | BooksLedger.dc.html (Books · General ledger) | Accounting › Books | tweak | Tabs go from 6 to 4; h1 "Books" | TABS at line 597 |
| 30 | BooksStatements.dc.html (Books · Profit and loss, balance sheet) | Accounting › Books | tweak | Tabs go from 6 to 4; `pl-october` is the target of the Profit or loss card; empty reads "No books yet" for Kept here | TABS at line 722 |
| 31 | BooksParties.dc.html (Books · Customers and suppliers) | Accounting › Customers and suppliers | tweak | Own page (no tab strip), key `parties`; "Customers overdue" and "Suppliers due" filtered states; AI "No balances" | TABS at line 654; ageing columns Current, 31-60 days, … |
| 32 | BooksStatutory.dc.html (Books · Statutory payables) | Accounting › Statutory payables | rework | Own page, key `statutory`; Net salaries payable section; authorities EPF, SOCSO, EIS, Lindung 24 Jam (SKBBK), PCB, zakat, HRDF ("Not set up" / "Not registered"); "Use this account", "Open the payment", "Go to Setup"; arrival from HR › Payroll | ACCTS has only epf, socso, eis, pcb (lines 374-379); JV2610-007 credits 420-000 "Accruals" 48,600 |
| 33 | Setup.dc.html (Setup · Bank accounts) | Admin › Setup › Bank accounts | move | Breadcrumb "Admin › Setup"; switcher replaces `coSeg` / `coSelect` | `coSeg: c.perEntity && cos.length > 1 …` |
| 34 | SetupCompanies.dc.html (Setup · Companies) | Admin › Setup › Companies | tweak | HRD Corp employer no., "HRDF registered" with levy rate and a headcount warning, "Runs payroll in this app"; list reads Kept in SQL Account / Kept here; hints mention the switcher; print-settings note "Used by Accounting › e-Invoices" | `v.uses_sql ? 'Kept in SQL' : 'Not kept in SQL'`; employer_kwsp, employer_perkeso, employer_lhdn, no HRDF |
| 35 | SetupChart.dc.html (Setup · Chart of accounts) | Admin › Setup | move | Breadcrumb and switcher only; keeps codes 320-000 "Salary advances" and 900-850 "Staff welfare" for claim types | View enum [tree, …, putback] |
| 36 | SetupStatutory.dc.html (Setup · Statutory accounts) | Admin › Setup | tweak | Link reads "Accounting › Statutory payables"; adds kinds Net salaries payable and Zakat; label "Lindung 24 Jam (SKBBK)"; the due day stays here, as the one home | "Accounting › Books › Statutory checks that each month is paid in full"; field "Due day of the next month" |
| 37 | SetupParties.dc.html (Setup · Customers and suppliers) | Admin › Setup | move | Breadcrumb only; its paste pattern is reused by the staff import | View enum includes paste, paste-preview, pasted |
| 38 | SetupTypes.dc.html (Setup · Payment and document types) | Admin › Setup | tweak | App types Salary advance and Payroll run; "Staff claim" used by the app; document types "Approval form (signed)", "Month review (signed)", "Tax clearance letter (LHDN)"; "Payroll summary" used by the Payroll check | `p(7,'claim','Staff claim')` not a system type; `d(107,'payroll','Payroll summary', …)` |
| 39 | SetupRequired.dc.html (Setup · Required documents) | Admin › Setup | tweak | Rows for Staff claim, Salary advance, Payroll run; the Approval box is filled by an approved form on file; AI's PV box reads "posted here" | `director: { d: { approval: 1, slip: 1, pv: 1 } }` |
| 40 | SetupChecklist.dc.html (Setup · Monthly checklist) | Admin › Setup › Monthly work | tweak | Built-ins "Approvals on file for every payment" and "Month reviewed"; reminders driven by the staff record; CP22A / CP21 conditions; probation and work-pass templates handled by HR; HRMEMO ticks itself from the run's approval after switch-over; payroll-calc noted as the Payroll check's item | `HRMEMO: { … 'Payroll summary approved by a director' … done: 'hand' }`; `probation … days: 90`; `wpass … days: 60` |
| 41 | SetupMatching.dc.html (Setup · Matching words) | Admin › Setup (Kept in SQL Account only) | tweak | A not-SQL state for an old address | Tab enum [type, salary, filing] |
| 42 | SetupGeneral.dc.html (Setup · General settings) | Admin › Setup | move | Breadcrumb only; "Organisation name: Shown at the top of the sidebar." stays | where [pc, hosted] |
| 43 | SetupMove.dc.html (Setup · Move setup) | Admin › Setup | tweak | HR settings in Everything and counts; staff records never included; approver names are personal data (behind a checkbox); the form-key secret is never exported | COUNTS `[['General settings', 8], …, ['Recurring payments', 17]]` |
| 44 | AuditPack.dc.html (Audit pack) | Admin › Audit pack | tweak | Description and bookmarks gain HR and approval pages; "Include payslips" (off); Before you print gains paid without approval, forms not matching, Month review missing; "declared, not verified" | Topbar `section="Filing"`; line 79 "One PDF with an index page…" |
| 45 | AuditPackBooks.dc.html (Audit pack · books pages) | Admin › Audit pack | move | Bookmark list makes room for the HR pages that follow; "Statutory payables check" wording | View enum [aisb-done, aisb-open, differs, stale, ai] |
| 46 | AuditTrail.dc.html (Audit trail) | Admin › Audit trail | tweak | Record filters Staff, Leave, Claims, Salary advances, Payroll checks (later Payroll runs), Approvals, Users and access; a payroll-check entry and an export read; masking covers IC and pay; "declared, not verified"; a hosted state with signed-in, verified names; no match on an HR filter | `REC = { payment: 'Payments', … audit: 'Audit trail' }`; view enum [healthy, never, outside, problems, warnings, nomatch] |
| 47 | Backup.dc.html (Backup) | Admin › Backup | move | One hint updated (HR documents are stored under a code); not-encrypted state mentions staff records | "keep people's names out of document file names" |
| 48 | MobileOverview.dc.html (Mobile · Overview) | Phone › Overview | rework | Next up first, then the four card rows stacked; company switcher and month in the top bar; tabs Overview / Payments / More; rule 15 row; rule 14 meta "Accounting › Statutory payables" | View enum [normal, …, four-companies]; tiles "Checklist done", "Fully documented"…; nav Overview, Companies, Bank, Filing, More |
| 49 | MobileCompany.dc.html (Mobile · Company month) | Phone › Payments | tweak | Retitled "Mobile · Payments"; tabs "Payments register" / "Monthly checklist"; Approval marker pills; the two new checklist items; "Paid without approval" filter; AI salaries corrected to 5 people, RM 21,300.00 | Tabs mc-tab-pay / mc-tab-chk; line 332 "3 people · paid 24 Oct", RM 9,800.00 |
| 50 | MobilePayment.dc.html (Mobile · Payment) | Phone › Payment | tweak | Approval marker (six readings) with "Upload the signed form"; Request link to the claim; salary-run sample with totals only | payment enum includes `claim`, "Oct 2026 Claims - Wei Ming" |
| 51 | MobileNewPayment.dc.html (Mobile · New payment) | Phone › Add payment | tweak | "Needs approval" switch; claim and advance types point to HR; Kept here money in goes to Sales; refused-with-reason state | View enum [money-out, …, from-overview] |
| 52 | MobileDesktopOnly.dc.html (Mobile · Best done on a computer) | Phone › Best done on a computer | rework | Screen enum becomes every new page, grouped by area (Payroll included), each with one reason sentence; "On your phone you can" gains a fifth item; a named-record state ("Claim CL-2610-004") | screen enum [Bank statements, SQL import, Budget, Recurring, Audit pack, Audit trail, Backup, Setup, Search, Notifications] |

**Counts:** keep 0, move 10, tweak 29, rework 12, split 1, retire 0 (52).

Canvas sections become: Foundations & shared, Overview, HR, Payroll, Payments, Accounting, Admin, Search alerts and
states, Getting started and sign-in, Phone, Dark mode, Printed. Retitle 'Bank statements' to 'Bank and
reconciliation', 'SQL import · MyInvois e-Invoices' to 'e-Invoices', 'Books · Customers and suppliers' to 'Customers
and suppliers', 'Books · Statutory payables' to 'Statutory payables', 'Company month · AISB' to 'Payments register
(source)', and 'Mobile · Company month' to 'Mobile · Payments'. The phone note ("Phone scope: only Overview, Company
month, payment and new payment…") becomes five screens.

---

## 3. New boards (40)

Two rules apply to every list board below: it draws empty, loading, could not load and many rows. Every form draws
saving, refused with the reason, and Discard changes?. The patterns live on States; each board only shows its own
wording. Wherever a toast confirms a change, it offers Undo. Sizes: S is up to 5 states, M is 6 to 12, L is 13 or more.

### Shell and Overview (3)

1. **ShellMenus.dc.html**: "Side menu · three company kinds and access" (M). Five Sidebars side by side: AIL (Kept in
   SQL Account, no payroll run: Payroll shows the Workbook check only), AISB (with payroll, Payroll [1]), AI (Kept here, with the "Kept here" sub-group), AISB for
   Kevin Lim (no HR, no Admin), and the menu fully open for comparison. States: each kind; no-hr; no-admin; active on
   an HR, a Payments and an Accounting page; Approvals and To pay badges, normal and overdue.
2. **CompanySwitcher.dc.html**: "Company and month switcher" (S). States: closed; open (no All companies); open on
   Overview (All companies first); No company yet with "Add your first company"; switch to a company without this page
   (toast, then its Overview); the month menu open with Current, Still open and Not set up, labelled "October 2026";
   dark. Keyboard: arrows, Escape, focus return.
3. **OverviewCards.dc.html**: "Overview cards · every state" (M). The 15 cards of scope section 3. Each is shown
   normal, empty (with the scope's own sentence, for example "Nothing needs attention", "No statement imported for
   October", "No books yet", "Add your staff to see this", "None this month", "Nothing waiting"), out of date
   ("Statement runs to 12 Nov", "SQL data runs to 12 Nov, fetch again") and "Could not load, try again". Also: the
   All-companies lines with company chips, grey zero counters, "Paid without approval on file" hidden at zero, a legend
   for which cards follow the month, and the privacy rule.

### HR (10)

4. **HrStaff.dc.html**: "HR · Staff" (L). The list (preferred name, staff no., position, department, type, date
   joined, status; no pay; IC masked to the last 4). Filters for In employment, Left and All. Add a person, Paste a
   list, Import Excel, Excel. States: list of 9; left; filtered; All companies (read only, company column); first run
   "Add your staff or paste the Excel list"; no match; paste, unread, columns, preview with what is missing, errors
   (all or nothing), file chosen, pasted with Undo; loading; error; many rows.
5. **HrStaffRecord.dc.html**: "HR · Staff record" (L). Tabs: Details, Pay, Leave, Calendar and reminders, Claims and
   advances, Documents, History. States: details; foreign worker (passport, permit); statutory categories worked out
   (Kah Seng turned 60, new rates from Nov 2026, "check with KWSP and PERKESO"); override dialog and overridden pill;
   pay with salary history; change salary from a date; leave; claims and advances; documents with an expiry flag and
   upload; history; left (kept until 2033); left with an amount to collect; moved company; loading; error.
6. **HrStaffForm.dc.html**: "HR · Add or edit a person, Left" (M). States: new; filled; errors; saving; saved with
   Undo; editing; discard; Left dialog (last day, reason); CP22A or CP21 from the reason, which starts the
   tax-clearance hold; warning about an advance balance; delete refused ("mark her as left instead"); delete allowed;
   move to the other company.
7. **HrStaffExport.dc.html**: "HR · Staff Excel export" (S). Column choice, with IC, pay, religion and race off and
   marked "Sensitive". States: default; sensitive on (PDPA note); none chosen (refused); downloading; done ("recorded
   in the audit trail").
8. **HrLeave.dc.html**: "HR · Leave" (L). Tabs: Taken and booked, Balances, Team calendar. States: list; add; half
   day; certificate; over-balance warning; clash warning; errors; saving; saved with Undo; cancel with reason;
   cancelled; maternity eligibility confirm; not eligible (unpaid); balances; balances at a date; calendar for
   November 2026 with KL holidays; calendar without the type (later, no HR access); intern or part-time; Sabah and
   Sarawak note; AI unpaid-leave note ("Deduct it from the salary payment by hand"); empty; loading; error; many rows.
9. **HrLeaveYear.dc.html**: "HR · Leave opening balances and year end" (M). States: paste; preview; errors; imported;
   carry-forward run; override with reason; done. Entitlements are the legal minimums (owner, 17 Nov).
10. **HrCalendar.dc.html**: "HR · Calendar and reminders (a Staff tab)" (M). List and month views. States: list from
    18 Nov; month; coming up (next 60 days, opened from the Overview card); mark done with Undo; done shown; one-off
    reminder (with saving, errors and discard); joiner task on the checklist; reminder carried on from a filed month;
    empty; loading; error; many rows.
11. **HrClaims.dc.html**: "HR · Claims and advances, Claims tab" (M). Status tabs from Draft to Withdrawn. States:
    list; one status; select several then "Print approval form for 3 claims · RM 1,214.50"; over-limit row; "Paid,
    approval refused" row; empty; loading; error; many rows.
12. **HrClaim.dc.html**: "HR · New claim and claim page" (L). States: new; lines with receipts; over limit; receipt
    missing; overseas (self-billed e-Invoice); errors; saving; draft saved with Undo; waiting (AF-2611-003); approved
    (locked); warning on editing an approved claim; paid; recorded (SQL voucher matched); recorded Kept here (JV and
    PV); not approved; withdraw; withdrawn; director's own claim; discard.
13. **HrAdvances.dc.html**: "HR · Claims and advances, Advances tab" (M). States: list; new (with saving and discard);
    warning for more than one month's pay; warning for over 50%; errors; draft; waiting; approved; paid; advance page
    with schedule; leaver balance; Kept here check against "Advances to staff"; withdrawn; empty; loading; error; many
    rows.

### Payroll (7)

14. **PayrollCheck.dc.html**: "HR › Payroll · Workbook check" (L). Today's Payroll check page in the new shell.
    Until payroll runs in the app it is the only tab of HR › Payroll. After switch-over it stays read only for past
    months. Content follows `viewPayroll` and its wording exactly (section 1). States: no check yet; findings ("3
    things to fix before paying, 2 to check; 4 notes", with a SKBBK-is-0 note and the PCB-not-checked note); nothing
    found; only checks; amounts to pay; an earlier version shown; checking; refused files (PDF, no Summary, no payslips,
    over 20 MB, unreadable), each with "nothing was kept"; no file chosen; wrong month; not filed (month not set up);
    "records need update 38"; Excel report; drop hint; loading; could not load; without Payroll figures (later). It shows for every company
    (owner, 17 Nov): a company whose pay has no statutory deductions simply does not use it. For a company that does
    not run payroll in the app, HR › Payroll holds only this tab.
15. **PayrollRun.dc.html**: "HR › Payroll · October run" (L). The stepper Draft, Checked, Approved, Sent to pay,
    Filed, plus "Waiting for SQL record" and "Recorded" for Kept in SQL Account. States: draft; paste preview; checked;
    checks failing; refused while recurring rows are in use; approved (AF-2611-005); sent to To pay; paid without
    approval; filed; waiting for SQL record and recorded (JV2610-007); recalculate for comparison; late approval;
    no staff; without Payroll figures; loading; error; saving; discard; many rows.
16. **PayrollTotals.dc.html**: "HR › Payroll · Summary, authorities, bank list" (M). States: summary; authorities
    (KWSP October overdue since 15 Nov); HRDF off with the headcount warning; bank list; person missing bank details
    (refused); Excel; empty; loading; error.
17. **PayrollFiles.dc.html**: "HR › Payroll · Statutory files" (M). EPF, PERKESO (SOCSO, EIS, Lindung 24 Jam) and
    LHDN e-PCB Plus. States: ready; preview; one marked uploaded; all filed (month locked); format out of date; yearly
    forms not yet available; empty; loading; error.
18. **PayrollLeaver.dc.html**: "HR › Payroll · Leaver's final pay" (M). States: leaver line; hold until tax clearance;
    hold released by letter or after 90 days; advance balance over 50%; paid anyway.
19. **PayrollParallel.dc.html**: "HR › Payroll · Parallel run and switch-over" (L). The workbook figures come from the
    month's latest Workbook check (its Summary rows), so nothing is retyped; PCB can be typed from LHDN's calculator.
    States: no workbook checked ("Check the workbook first"); differences, including Lindung 24 Jam, which the app
    works out while the workbook has 0; all agree; explained; signed off (declared name, saving, refused); switch-over
    dialog listing the rows to stop; switched over; approval refused while recurring rows are in use.
20. **PayrollOpeningYtd.dc.html**: "HR › Payroll · Opening year to date" (S). States: start; preview; errors;
    imported; year-to-date view; refused file.

### Payments (5)

21. **PaymentsRegister.dc.html**: "Payments register" (M). Split from Company. Columns Payment, Type, Paid /
    received, Amount, Documents, Status and Approval. Tabs All, Not paid, Needs attention, Paid without approval,
    Not in SQL (Kept in SQL Account only), Complete. Search, bulk bar, "Add a payment", Excel. The company Next up
    panel is dropped: Next up lives on the Overview, and the register shows a link "3 to-dos for AISB on the Overview".
    An AISB salary row shows "The payroll check found 3 things to fix", linking to HR › Payroll. States: October AISB
    with every approval reading; paid-without-approval tab; AI Kept here (PV posted here); filed; locked (Kept here
    only); sent here; not set up; empty; loading; could not load; many rows.
22. **MonthlyChecklist.dc.html**: "Monthly checklist" (M). Split from Company. "18 of 25", ticks, slots, "Tick
    anyway?", Mark month as filed, Reopen. New items: "Approvals on file for every payment" and "Month reviewed". For
    AISB, the item "Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB" holds the workbook filed by the Payroll check,
    with the note "Uploaded on the Payroll check page" and a link. States: open; approvals item not ticked (2 without
    approval); ticked; month review printed and waiting; on file; payroll workbook filed with "replaced" history;
    filed; not set up; loading; could not load; many rows.
23. **Approvals.dc.html**: "Approvals" (L). Tabs: To print, Waiting for approval, Approved, Not approved and
    Withdrawn, Paid without approval on file (with Approved after payment). States: to print with a mixed selection;
    print dialog, single and batch; waiting; approved; Not approved dialog; Withdrawn dialog; both with Undo on the
    toast; paid without approval list; approved after payment; same-name warning; approver is the payee; self-approved;
    filtered from the Overview card; filtered to HR requests (from the Requests waiting card); empty "Nothing waiting
    for approval"; loading; could not load; many rows; Excel.
24. **ApprovalUpload.dc.html**: "Approvals · upload a signed form" (L). States: code read from PDF text; read from
    QR; not readable, so typed; wrong code; date on the form; digital signer matched; signer not in the approvers list;
    paper scan, which approver signed; all match (approved, toast with Undo); some match and some changed (RM 486.50
    printed, now RM 506.50); no longer matches; uploaded twice; saving; refused with the reason.
25. **ToPay.dc.html**: "To pay" (M). Approved items only, grouped as overdue, this week and later. States: list;
    select several and Pay (one paid date, bank reference and account; one payment per item); paid with Undo;
    tax-clearance hold; filtered from Due and overdue; filtered from Requests waiting (approved, waiting to pay); Kept
    here "Paying posts a payment voucher"; link "Waiting for approval: 3, on Approvals"; empty "Nothing to pay";
    loading; could not load; many rows; Excel.

### Accounting (2)

26. **BankBookLine.dc.html**: "Bank and reconciliation · book a statement line" (M), for Kept here only. States: money
    out (PV preview); money in (OR preview); posting; posted ("Booked · PV2610-009"); refused in a locked month; refused
    with no counter account; discard.
27. **AccountingKeptHere.dc.html**: "Sales, Purchases, Journals, Period close · placeholders" (S). One view per page,
    each with a short "what will be here" panel, plus "Sales is for companies kept here. AISB is kept in SQL Account"
    for an old address.

### Admin (7)

28. **SetupApprovers.dc.html**: "Setup › HR · Approvers" (M). States: list of 3; history; one only (AI, self-approved);
    none yet; full; new; errors; edit; discard; stop; stopped; no form key yet; change-key confirm; key changed. Saving
    is drawn too.
29. **SetupLeave.dc.html**: "Setup › HR · Leave types and policy" (L). Pre-filled with the legal minimums, which stay the entitlement (owner, 17 Nov). States: list
    ("Same as the law"); a value set above the law shows a warning, never refused; edit by years of service; below the minimum (refused); new company type; change from a date;
    carry forward; history; discard; saved; loading; error.
30. **SetupHolidays.dc.html**: "Setup › HR · Public holidays" (M). WP Kuala Lumpur, rest day Sunday. States: 2026;
    2027 unconfirmed; untick below 11 (refused); locked s.60D row; replacement day; two on one day; one-off day;
    moving date; paste import; change state; saving; discard; loading; error.
31. **SetupClaimTypes.dc.html**: "Setup › HR · Claim types" (S). States: list; none yet; new; errors (no expense
    account); edit (saving, discard); stop; history; put back.
32. **SetupPayroll.dc.html**: "Setup › HR · Payroll settings" (L), shown only for a company that runs payroll. Tabs:
    Pay items, Rates and tables, Due dates, Minimum wage, Pay rules, Employer numbers. The Rates tab matches
    `payrollcheck.RATES`. Due dates lists the yearly forms and shows the monthly due days read only, with a link to
    Statutory accounts, which is their one home. Employer numbers is a read-only summary linking to Companies. States:
    pay items; edit a pay item; rates; new dated row; overlap refused; a "check with" flag; due dates; minimum wage; a
    less generous pay rule refused; HRDF off; headcount warning; discard; saved; loading; error.
33. **UsersAccess.dc.html**: "Users and access" (L). A banner "Drawn now, built with hosting and logins". Four people
    with six rights; the Approver right ties to Setup › HR › Approvers; "Set a new password" on a person. States: list;
    add; errors; edit (saving); discard; remove confirm; removed with Undo; last admin refused; menu preview without HR;
    menu preview without Payroll figures; PC-only banner; only the owner; loading; error.
34. **AuditPackHR.dc.html**: "Audit pack · HR and approval pages" (M). Beside AuditPackBooks. Pages: approvals of the
    month; paid without approval (still open, approved after payment); approver history; steps one name did alone; HR
    summary (headcount, totals per authority, leave balances at year end, advances, amounts to collect); Month review on
    file. States: AISB; AI ("Payroll isn't run in the app for AI"); none open; one name did every step; with payslips;
    before HR (no staff).

### Phone (1)

35. **MobileApprovalPhoto.dc.html**: "Mobile · Upload a signed approval form" (M). Reached from a payment's Approval
    marker. The same screen takes the Month review sheet. States: camera; reading; code read and matched; which approver
    signed (Save off until chosen); date missing; code not readable, so typed; no longer matches; matches some; already
    on file; approver is the payee (greyed); only one approver (self-approved); same-name warning; salary-run form
    (totals only); uploading, failed and retry; saved (back on the payment, Undo); discard.

### Printed (5)

36. **PrintApprovalForm.dc.html**: "Printed approval form" (M). A4, English. The code AF-…, the keyed check and the
    QR, the requests table, up to 3 approver blocks, "Any one signature approves this form." States: single; batch of
    October claims; mixed (claim, advance, supplier bill); salary run (page 1 totals, page 2 per person, printed only by
    a user with Payroll figures); recurring set-up; approver is the payee (line struck, "Can't sign: payee"); one
    approver; two pages; no approvers set (nothing prints).
37. **PrintMonthReview.dc.html**: "Printed Month review sheet" (M). States: AISB October with 2 paid without approval;
    none; AI; reconciliation not signed off; uploaded (checklist ticks).
38. **PrintPayslip.dc.html**: "Payslip" (M). A4, IC masked to the last 4 (it is emailed), "Approved by". States:
    staff; with advance repayment; with overtime and unpaid leave; leaver's final pay; 60 and over; parallel-run
    watermark; not approved yet; emailed and email failed.
39. **PrintPayrollOutputs.dc.html**: "Payroll printouts" (M). The bank payment list, the monthly summary and the
    Kept in SQL Account payroll journal summary, as printed. States: each sheet; journal waiting and matched; "Maybank
    bulk format to be confirmed".
40. **PrintHrLists.dc.html**: "Printed staff record, leave and claim lists" (M). The staff record PDF shows the full
    IC (HR's own file, marked "Confidential: personal data"); race and religion are left out unless chosen. States:
    staff record; leaver record; leave list for October; balances at 31 Dec; claim list for October; empty period.

**New boards per area:** Shell and Overview 3, HR 10, Payroll 7, Payments 5, Accounting 2, Admin 7, Phone 1, Printed
5. That makes 40. With the 52 existing boards, the canvas will hold 92.

Duplicates merged here: ApprovalForm and PrintApprovalForm; MonthReview and PrintMonthReview; PayrollPayslip and
PrintPayslip; HrPrints and PrintHrLists; AuditPackHR and AuditPackHr. PayrollJournal is split: its states go on
PayrollRun and its printed sheet goes on PrintPayrollOutputs. The new SetupPayroll comes from two proposals and keeps
the employer numbers on Companies.

---

## 4. Shared changes

### Sidebar, top bar, Foundations, States

- **Sidebar**: the five areas above, with props `kind`, `access` and `merged`. New active keys: overview, staff,
  leave, claims, payroll, approvals, topay, register, checklist, budget, recurring, bank, sql, einvoices, books,
  parties, statutory, sales, purchases, journals, close, setup, pack, trail, backup, users. Map the old keys:
  aisb, ai and `{{sideKey}}` become register; sql on MyInvois and InvoicePdf becomes einvoices; books on BooksParties
  becomes parties and on BooksStatutory becomes statutory. The sample Next up line `{ co: 'aisb', area: 'books' }`
  (rule 14) moves to area statutory.
- **Top bar**: the company switcher, the month label "October 2026", breadcrumb sections (Dashboard becomes
  Overview; Companies becomes Payments › Payments register; Monthly work becomes Payments or Accounting; Filing and
  Setup become Admin), the search placeholder "Search payments, staff, requests, SQL docs", and a user menu showing
  "Access: HR, Payroll figures, Payments, Accounting, Admin".
- **Every board that imports them** changes its active key and breadcrumb, as in the table. The in-page company
  control goes from the 19 boards listed.
- **Foundations**:
  - addresses: `#/all/2026-10/overview`, `#/AISB/2026-10/payments/register`, `#/AISB/hr/staff/S003`,
    `#/admin/setup/hr/approvers`;
  - the company-kind chip;
  - Overview card anatomy and its four states;
  - the Overview privacy rule;
  - the Approval marker with six readings: Not needed (grey), Waiting (amber), Approved (green), Paid without approval
    on file, Paid more than approved and Paid, approval refused (red);
  - request pills: Draft, Waiting for approval, Approved, Not approved, Paid, approval refused, Withdrawn, Paid, Part
    paid, Recorded, Done;
  - leave pills: Booked, Taken, Cancelled;
  - staff pills: In employment, On probation, Left;
  - the Overridden and Sensitive markers and the masked IC style;
  - Payroll check tones: Fix before paying (red), Check (amber), Note (grey), Nothing found (green);
  - a print section: A4 sheet, code + keyed check + QR block, approver signature block, "declared, not verified",
    "Page x of y";
  - the phone tab bar and phone switcher sheet.
- **States**: the additions listed on board 7. "Page not used for this company" uses two examples, SQL import for AI
  and Payroll for AI.
- **Label rule on every board**: only "Kept in SQL Account" or "Kept here". Fix "Not kept in SQL" (SetupCompanies),
  "AI, not kept in SQL", "Books kept in this app", and the short "Kept in SQL".
- **Next up text** wherever rule 14 is quoted (Main, DarkOverview, Company, DarkCompany, MobileOverview,
  MobileCompany): "…Check it on Statutory payables.", with the meta "AISB · Accounting › Statutory payables".

### Icons: 12 new glyphs (68 becomes 80)

| Glyph | Used for |
|---|---|
| staff (ID card) | HR › Staff (`users` stays Customers and suppliers) |
| leave (sun lounger) | Leave, and Setup › HR › Leave |
| reminder (calendar with a bell) | Calendar and reminders, the Dates coming up card (`calendar` stays the month switcher and holidays) |
| birthday (cake) | Birthdays and anniversaries card |
| claim (receipt with a person) | Claims and advances, Setup › HR › Claim types |
| advance (coins with an arrow) | the Advances tab |
| payroll (from app.js `ICON.payroll`, "M4 3h16v18H4zM4 9h16M4 15h16M10 3v18M14 12l1.5 1.5L18 11") | Payroll, Setup › HR › Payroll settings |
| approval (pen on a form) | Approvals, Setup › HR › Approvers, the Approval marker |
| toPay (wallet with an out arrow) | To pay |
| statutory (government building) | Statutory payables and the KWSP / PERKESO rows; `vault` is left for Backup |
| access (shield with a person) | Users and access |
| qr | approval-form code and phone reading |

Existing glyphs are reused for: e-Invoices `verified`, Sales `receipt`, Purchases `inbox`, Journals `sheet`, Period
close `lock`, Payments register `payment`, and Budget and Recurring as today.

### Decisions settled in this review

| Question | Decision | Why, in a line |
|---|---|---|
| Badge on Payroll | Yes: 1, red, from rule 15 | The existing "ONE BADGE RULE" (Sidebar line 80) counts Next up rows per area, and rule 15 is one. |
| Next up "Show tasks for" filter | Removed; the top-bar switcher is the company filter | The scope keeps a company filter as an Overview extra; the switcher does that job, and two controls would disagree. |
| Menu fold | Folded (Staff tab; Claims and advances) | It keeps the menu to 22 to 24 rows; the scope leaves this to the designer. |
| Month label | "October 2026", not "October 2026 payroll" | Payroll is now an HR page; only some companies run payroll in the app. |
| Where the Payroll check lives | HR › Payroll › Workbook check tab, every company (owner, 17 Nov) | The code comment says the redesign moves it to HR. |
| Parallel-run source | The month's latest Workbook check | It already reads every Summary row, so nothing is retyped. |
| Lindung 24 Jam in October | Existing figures stay; the check shows "SKBBK is 0" and the parallel run shows it as a difference | Seven boards keep agreeing, and the sample shows the check doing its job. |
| Due dates | Monthly due days stay on Setup › Statutory accounts (`due_day` in the app); Payroll settings shows the yearly forms | One home, already in the app. |
| Employer numbers and HRDF registered | On Setup › Companies; Payroll settings shows them read only | Scope section 2 puts them on Companies. |
| Payroll settings for AI | Hidden | AI does not run payroll in the app. |
| Staff document kinds | A fixed list on the staff record | It keeps HR files out of payment document types. |
| Departments | Free text, offering past values | The scope names no Setup list. |
| Approver right | Tied to the Setup › HR › Approvers list | One list, no drift. |
| Company Next up panel on the register | Dropped | The Overview with one company chosen shows the same rows. |
| Locked month | The filed month stays read only for every company; period-close lock is for Kept here only; on the bank sign-off, a change in SQL still shows "Confirm again" | It matches today's filing and the drawn app fix. |
| SQL import per-row PDF | Moves to the e-Invoices Print column | Printing then has one home. |
| e-Invoices for AI | Shown: its own documents print; "Submission method not decided yet" | It reserves the place. |
| Required documents "Approval" box | Filled by an approved form on file | No double upload. |
| Recurring bill with varying amount | A new form only when the set-up amount changes | Answer 1 says "set up or its amount changes". |
| "Needs approval" default | Per payment tick, defaulting from a per-type setting in Setup › Payment types | Supplier bills need it, statutory payments do not. |
| HRMEMO checklist item | Ticked by hand until switch-over; then it ticks itself from the run's approval form | Nothing is lost before payroll runs. |
| Probation and work-pass templates | Read only, "From the staff record, see Calendar and reminders" | Scope 5.3 drives them from the record. |
| Phone tab bar | Overview / Payments / More | HR and Accounting tabs would only open "best done on a computer". |
| Phone "Paid without approval" card | Opens Mobile · Payments filtered; each payment's marker leads to the photo upload | That is the scope's route to the fifth screen. |
| Payslip IC | Masked to the last 4 | It is emailed; the payroll check sets the masking rule. |
| Salary-run form | Totals on page 1, per person on page 2 | The signing director approves pay; on screen only Payroll figures users see page 2. |
| Parallel-run sign-off | In the app, declared name and date, with a printable comparison | Logins come later; this is the same pattern as other steps. |
| Five rival rosters, approvers and codes | One shared set, below | The boards must agree. |
| AI salaries | 5 people, RM 21,300.00 (Company.dc.html line 798); MobileCompany's "3 people", RM 9,800.00 is corrected | The desktop board is the reference. |

**Corrections to the earlier area notes:**
- "Payroll summary filed" is AI's item, not AISB's.
- KWSP October (RM 11,240.00) is **unpaid** on every board; PV2611-018 appears only in BooksStatutory's all-clear
  variant.
- Sql's e-Invoices card and Print controls sit in the `isSql` branch, not the not-SQL block.
- Bank has no lock or reopen; AuditPack's "Reopen" is the audit-pack filing, which is unrelated.
- Rule 15's `"payroll"` is the row key; its target is `{"view": "payroll"}`.

### Shared sample data (all made up)

**Dates**: today is Wednesday 18 November 2026; October 2026 is the month worked; September is still open.

**Companies**:
- AISB = Agrinexus Sdn Bhd, Kept in SQL Account, runs payroll, WP Kuala Lumpur holidays, rest day Sunday, HRDF
  registered off, HRD Corp employer no. HRD-0012345.
- AI = Agrinexus International, Kept here, 5 staff on a recurring salary row (RM 21,300.00), no payroll.
- AIL = Agrinexus Logistics (Kept in SQL Account, no payroll) and AIP = Agrinexus Plantations (Kept here), for the
  menu cases only.

**Users**:

| Person | Role | Rights |
|---|---|---|
| Aisha Rahman | HR and Finance, at the keyboard | HR, Payroll figures, Payments, Accounting, Admin (not Approver) |
| Nurul Aina | HR | HR only (no Payroll figures) |
| Kevin Lim | Finance | Payments, Accounting (the no-HR case) |
| Hassan Ismail | Director | Approver |

**Approvers**:
- AISB: Hassan Ismail, Tan Mei Ling and Rajesh Kumar, all directors and none on the payroll. Hassan and Tan Mei Ling
  from 1 Jan 2025, Rajesh Kumar from 1 Jul 2026. Former approver: Farid Osman, 1 Jan 2025 to 30 Jun 2026.
- AI: Hassan Ismail only, which gives the self-approved case.
- Approver is the payee: the Director fee (RM 12,000.00) is paid to Hassan Ismail.

**AISB staff on the October payroll (8)**:

| No. | Name (preferred) | Job | Joined | Basic | Oct net pay | Used for |
|---|---|---|---|---|---|---|
| S001 | Aisha Rahman | HR and finance executive | 2 May 2019 | 8,600 | 7,450.00 | the user; all four steps by one name |
| S002 | Ong Wei Ming (Wei Ming) | Sales executive | 1 Jun 2021 | 7,800 | 6,800.00 | claim CL-2610-004; half day 14 Oct |
| S003 | Nurul Aina Hashim (Aina) | Admin executive | 3 Oct 2016 | 7,000 | 6,100.00 | 10 years in October; annual leave 16 to 20 Nov |
| S004 | Muhammad Hafiz Rosli (Hafiz) | Operations executive | 4 Mar 2019 | 6,500 | 5,650.00 | advance SA-2611-001; leave Fri 20 Nov |
| S005 | Siti Khadijah Omar (Khadijah) | Customer service | 1 Feb 2020 | 5,000 | 4,400.00 | maternity 5 Oct 2026 to 10 Jan 2027 |
| S006 | Wong Kah Seng (Kah Seng) | IT support, contract | 1 Jan 2024 | 10,500 | 9,200.00 | turned 60 on 12 Oct (new rates from Nov); contract ends 31 Dec; retiring, so a CP22A and the tax-clearance hold state |
| S007 | Lim Jia Hui (Jia Hui) | Marketing executive | 1 Sep 2026 | 4,800 | 4,000.00 | probation ends 30 Nov; over-balance leave warning |
| S008 | Rina Santoso (Rina) | Production assistant, foreign worker | 15 Jan 2025 | 5,600 | 5,000.00 | work permit expires 10 Jan 2027; birthday 21 Oct |

- Joiner S009 Daniel Lee Chee Keong, from 3 Nov 2026, basic RM 3,500. His e-CP22 is due 3 Dec, matching Main's
  "e-CP22 for the joiner starting 3 Nov". He asks for an advance of RM 4,000, more than one month's pay.
- Leaver S010 Kavitha Raman, last day 30 Sep 2026, resigned, kept until Sep 2033. Her advance balance was RM 2,000:
  RM 1,600 was deducted from final pay and RM 400 is to collect.
- On 18 Nov: 9 in employment, 1 joiner, 0 leavers; 8 Malaysian, so the HRDF warning shows only in a what-if of 10.
- AI staff: Ahmad Faizal Yusof, Chong Pei Shan, Priya Subramaniam, Lee Jun Wei, Nur Izzati Kamal.

**October payroll (ties to the existing boards)**:
- Gross RM 59,147.90. Net pay RM 48,600.00, paid 24 Oct as "PAYROLL BULK 8 ITEMS" (ref BULK 241026). The 8 net
  amounts above add up to it. The short-match state leaves out Jia Hui's RM 4,000.00.
- Employee deductions: EPF 5,346.00, SOCSO 205.00, EIS 81.90, PCB 4,915.00, zakat 0, Lindung 24 Jam 0 (the check
  notes it).
- Employer: EPF 5,894.00, SOCSO 717.60, EIS 81.90.
- KWSP October RM 11,240.00 (5,346.00 + 5,894.00) was due 15 Nov and is **unpaid and overdue**. Statutory payables
  shows 5,346.00 withheld and unpaid.
- PERKESO RM 1,086.40 was paid 17 Nov (FPX 1711093). PCB RM 4,915.00.
- SQL journal JV2610-007 (Dr 900-100 59,147.90; Cr 420-000 48,600.00 …) is the run's journal; PV2610-014 paid the
  net pay.
- Workbook check: "Example Payroll - OCT 2026.xlsx", checked 5 Nov 10:12, "3 things to fix before paying, 2 to
  check; 4 notes". The corrected file, checked 6 Nov 09:40, gives "Nothing to fix or check; 1 note". Next up shows
  "Oct AISB: the payroll check found 3 things to fix before paying".

**Leave and dates on 18 Nov**:
- On leave today: Aina and Khadijah, 3 this week (Hafiz Fri 20 Nov).
- October birthdays and anniversaries: Aina 10 years (3 Oct), Kah Seng birthday (12 Oct), Rina birthday (21 Oct).
- Dates coming up: Jia Hui's probation 30 Nov, Daniel's e-CP22 3 Dec, Kah Seng's contract 31 Dec, Rina's permit
  10 Jan.

**Claims, advances and forms**:

| Item | Detail | Status |
|---|---|---|
| CL-2610-004, Wei Ming | parking 12.00 (6 Oct), client lunch 186.50 (14 Oct), mileage 288.00 (22 Oct) = RM 486.50 (the existing "Oct 2026 Claims - Wei Ming", due 14 Nov) | approved, in To pay, overdue |
| CL-2610-005, Aina | RM 408.00 | approved, in To pay |
| CL-2610-006 | RM 120.00 | withdrawn, "Entered twice" |
| CL-2610-007, Jia Hui | RM 320.00 | approved, in To pay |
| CL-2611-001, Kah Seng | RM 145.00 | waiting for approval |
| AF-2611-003 | the 3 October claims, RM 1,214.50; keyed check 7KQ-M4XP; printed 11 Nov; signed 12 Nov by Tan Mei Ling; uploaded 13 Nov from a paper scan ("Approver chosen by Aisha Rahman from a paper scan") | approved |
| SA-2611-001, Hafiz | RM 1,500.00 at RM 500 a month, Nov 2026 to Jan 2027, on AF-2611-001 (Rajesh Kumar, 3 Nov), paid 4 Nov; first deduction 24 Nov, so RM 1,500.00 left on 18 Nov (Recurring's seed "left 1,000.00" changes) | paid |
| SA-2611-002, Daniel | RM 4,000.00 | waiting for approval |
| AF-2611-004, Consultant fee | Payroll Advisory PLT, RM 3,200.00, printed 16 Nov | waiting; also the phone-photo sample |
| AF-2611-005 | the October salary run (step 2 boards) | approved |
| MR-2610-AISB | Month review | waiting for upload |

**Paid without approval on file (AISB, October)**:
- Contractor — field works, RM 24,000.00, paid 6 Oct.
- Cleaning service, approved RM 800.00, paid RM 880.00 ("Paid more than approved (RM 80.00)").
- Approved after payment: Office rental RM 6,500.00, paid 30 Oct, form dated 5 Nov, uploaded 6 Nov.
- AI has none, so the card is hidden for AI.

**Badges (AISB)**: Approvals 3 (2 HR requests and 1 supplier bill), To pay 5 (KWSP overdue, three claims, Cloud
hosting USD 1,200.00 due 25 Nov), Payroll 1.

---

## 5. Design packages and order

Each package runs as the stage 1 run did: build, review, verify (on a cheaper model), fix. The board counts include
the new boards.

| # | Package | Boards | Can run in parallel with |
|---|---|---|---|
| A | **Shell and shared**: Sidebar, Topbar, Icon, Foundations, DarkPalette, States, SetupNav, plus ShellMenus and CompanySwitcher. The shared sample data is fixed here first. | 9 (2 new) | Nothing. It goes first. |
| B | **Moves**: active keys, breadcrumbs, the in-page company control off 19 boards, retitles, canvas sections and notes. Mostly mechanical; it can be scripted and then checked. | about 30 touched, 0 new | Nothing. It goes right after A. |
| C | **Overview and carried-over shell**: Main, DarkOverview, OverviewCards, CommandPalette, Notifications, SignIn, FirstRun | 7 (1 new) | D, E, H |
| D | **Payments**: Company split into PaymentsRegister and MonthlyChecklist, DarkCompany, Payment, DarkPayment, NewPayment, Recurring, Approvals, ApprovalUpload, ToPay, SetupTypes, SetupRequired, SetupChecklist | 15 (5 new) | C, E, H |
| E | **Accounting**: Bank, BankReview, DarkBank, Sql, MyInvois, InvoicePdf, Books, BooksLedger, BooksStatements, BooksParties, BooksStatutory, SetupStatutory, BankBookLine, AccountingKeptHere | 14 (2 new) | C, D, H |
| F | **HR step 1**: the 10 HR boards | 10 new | G (once D has fixed the Approval marker) |
| G | **Payroll**: the 7 payroll boards | 7 new | F |
| H | **Admin**: SetupApprovers, SetupLeave, SetupHolidays, SetupClaimTypes, SetupPayroll, UsersAccess, AuditPackHR, SetupCompanies, SetupMatching, SetupMove, AuditPack, AuditTrail | 12 (7 new) | C, D, E |
| I | **Phone**: MobileOverview, MobileCompany, MobilePayment, MobileNewPayment, MobileDesktopOnly, MobileApprovalPhoto | 6 (1 new) | After C and D |
| J | **Printed**: PrintApprovalForm, PrintMonthReview, PrintPayslip, PrintPayrollOutputs, PrintHrLists | 5 new | After D and G |
| K | **Consistency sweep**: sample figures, names and codes agree across all 92 boards; no "stage" wording; every scope section 10 box ticked | all | Last |

Order: A, then B, then C, D, E and H together, then F and G together, then I and J, then K. Rough size: 40 new boards
and about 45 existing boards edited.

---

## 6. What the build plan (`review/2026-11-14-redesign-build-plan.md`) must change

- **Slice 0 (Foundations and shell)** grows to cover:
  - the five-area sidebar with company kinds and access;
  - the company switcher, which replaces the per-company items and the 19 in-page controls;
  - addresses carrying company, month and page;
  - the 12 new glyphs;
  - the menu places reserved for HR, Approvals, To pay and the Kept here placeholders, showing "coming soon" until
    built.
  
  Its board list adds ShellMenus and CompanySwitcher.
- **The Payroll check moves now**: a small slice, or part of slice 0. `viewPayroll` moves from Monthly work to HR ›
  Payroll (every company) with no change to what it does, following PayrollCheck.dc.html.
- **Slice 1 is re-cut** into:
  - 1a Overview: four card rows, Needs attention, privacy rule. HR cards show "Add your staff to see this" until HR
    exists.
  - 1b Payments register, Monthly checklist, payment dialog and Add payment, with the phone screens.
- **Slice 2** becomes **Accounting › Bank and reconciliation**. It adds the month lock and logged reopen, and one line
  matched to several payments (server work). Book this line comes with stage 2.
- **Slice 3** splits into **SQL import** and **e-Invoices**. The e-Invoices card, Print column and month zip move to
  their own page.
- **Slice 4** becomes **Payments › Budget and Recurring**. Salary advances stay on Recurring until the HR claims and
  advances slice moves them.
- **Slice 5** becomes **Admin › Audit pack, Audit trail, Backup**. The HR and approval pages come with their HR
  slices.
- **Slice 6** becomes **Admin › Setup**: the 15 sections now. The Setup › HR group comes with the HR slices.
- **Slice 7** becomes **Accounting › Books** with 4 tabs, plus Customers and suppliers and Statutory payables as
  pages of their own. Server work: rule 14's text and target (`nextup.py:462`), and the authority list gaining SKBBK
  (Lindung 24 Jam), Net salaries payable, zakat and HRDF.
- **New slices**, after slices 0 to 7, in this order:
  1. **Approvals and To pay**: requests, approval forms with code, keyed check and QR, upload matching, the Approval
     marker, the "Paid without approval on file" list, Month review, the two checklist items and the phone photo
     screen. Server work: requests, forms and the key secret.
  2. **HR staff**: staff records, import, export, Calendar and reminders (joiner and leaver reminders re-driven from
     the record), Setup › HR approvers and holidays.
  3. **HR leave**: leave, balances, calendar, Setup › HR leave.
  4. **HR claims and advances**: claim types, advances moved out of Recurring, payments through To pay.
  5. **Payroll (HR step 2)**: Setup › HR payroll settings, run, outputs, parallel run, switch-over.
  6. **Users and access**: with sign-in and hosting, last.
- **New features table**:
  - badges add the Approvals and To pay counts;
  - search adds staff and requests;
  - notifications add HR and approval events;
  - Undo covers the new pages;
  - the document viewer also shows receipts and signed forms;
  - Recent activity adds HR and payroll-check events without private detail.
- **Section 3b, app fixes**: add rule 14's wording and target, and the Statutory payables authority list.
- **Section 5, open decisions**: the KWSP two-rows question stays open. "Sign-in timing" is now tied to Users and
  access.

---

## 7. The owner’s answers (17 November 2026)

1. **Payroll check for any company.** It is a feature every company has; using it is up to the company and the
   user. A company whose pay has no statutory deductions does not use it. So HR › Payroll shows for every company:
   the Workbook check tab always, and the run, outputs and parallel-run tabs only where Setup › Companies has
   **Runs payroll in this app** on. No company code is hard-wired: AISB is simply the first company with it on.
2. **Payslip password: agreed** (the owner said yes on 17 Nov). See below.
3. **Leave.** The legal minimums are the entitlement and stay as they are. Anything above the legal days is a
   **warning only**, never refused: leave recorded beyond a person’s legal days, and a Setup value set above the
   law. No company extras and no carry-forward beyond what the law gives, until the owner sets them.
4. **Net salaries payable.** Follow what the company’s books use: for AISB, SQL’s **420-000 Accruals**. It is a
   per-company choice in Setup › Statutory accounts (kind "Net salaries payable"), not fixed in the code, because
   the app is built for bigger companies too.
5. **Customers overdue** means older than 30 days.
6. **Per company.** Approvers, leave policy, public holidays and claim types are set per company (AI has one
   approver, which gives the self-approved case).
7. **"Soon" was a real name.** It came from an old placeholder in the app’s first commit ("e.g. Oct 2026 Claims -
   Soon", removed later; today’s code no longer has it). It was on five boards (Company, DarkCompany, NewPayment,
   MobilePayment, MobileNewPayment) and is replaced with the made-up **Ong Wei Ming (Wei Ming)**, published as version
   64. No other board text comes only from the app’s history. The old placeholder is still in the git history
   (and on GitHub if that history is pushed).

### Payslip password (agreed)

- **Default: the person’s IC number without dashes** (passport number for a foreign worker). The app already holds it,
  nobody has to send a password, and it is what most Malaysian payroll systems do.
- **Own password, optional:** HR can set a personal payslip password on the staff record when someone asks; it is
  stored encrypted, never shown again, and can be reset.
- The email says which rule applies ("Open it with your IC number, without dashes") but never contains the password.
  The PDF uses AES-256 encryption. The password appears in no list, export or audit entry, and IC numbers stay masked
  on screen as the Payroll check does today.
- The trade-off: anyone who knows a person’s IC number can open their payslip. The personal password is the answer
  for anyone who minds. The boards draw both: the staff record’s "Payslip password" row (IC number, or own password
  set on a date, with Reset) and the payslip email preview.
