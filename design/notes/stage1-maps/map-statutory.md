# Statutory payables check and statutory accounts: inventory for the canvas update

Area: the statutory payables check (EPF, SOCSO, EIS, SKBBK, PCB) and statutory accounts in Setup and in Move setup. All of it arrived after b7d7fa0, in three commits: 7fa239d (check), 27aeab2 (employer's share on another kind's account) and c4aa5e4 (Setup moves).

I only read files. I did not run the app or tests and did not touch C:\HR-Records.

---

## A. Inventory: what the user sees, from the code

### A1. Where it appears
1. **Accounting › Books › Statutory tab.** This is the main screen.
   - Tab button: static/app.js:1672 `Statutory`, the 6th tab after Trial balance, General ledger, Profit and loss, Balance sheet, Customers and suppliers.
   - Nav entry: app.js:127 `["Accounting", [["books", "Books"]]]`.
2. **Next up, rule 14.** hrp/nextup.py:452-466. It appears on the Overview, on the company page and in the sidebar badges.
3. **Setup › Companies and banks › Statutory accounts.** A list and a drawer per company. hrp/masters.py:236-259; rendered by the generic setupList and openSetup at app.js:2676 and 2836.
4. **Setup › General › Move setup.** Export and import carry the statutory accounts. hrp/setupfile.py; UI at app.js:3173-3215.
5. **Excel files:**
   - The Books "Excel" link on the tab: app.js:1763 and hrp/booksexcel.py:284-317.
   - The auditor package `Books/` folder: hrp/reports.py:336-356.
6. **Audit pack PDF.** It has a page "Statutory payables check" (hrp/auditpack.py:567-645). "Check this pack" has a group "SQL's books and the statutory accounts (its books pages)" (hrp/packcheck.py:28 and 40).
7. **Audit trail and restore.** Records are called "Statutory account / statutory accounts" (hrp/auditread.py:28). A deleted one can be put back (hrp/restore.py:33-35, 335-337).

### A2. Books › Statutory tab (app.js:1962-2022; data from GET /api/statutory, hrp/app.py:2153-2167)

**Page shell (shared Books page, app.js:1650-1673)**
- Company picker, then the card heading `Books · AISB`, then the Books source note.
- `From` and `To` date inputs, `Show`, `This financial year to date`, and an `Excel` link (title: "This report as an Excel file, for the dates and options shown").
- The From and To days are cut to their months: payroll months.
- When both are empty, the range is this financial year to date (statutory.default_range). For AISB on 18 Nov 2026 with FY start January, that is January–November 2026.
- Unlike the other tabs, the Statutory tab never writes the months back into the inputs. The inputs stay empty while the heading names the months.
- While loading: `Loading…`.
- On error: a `note warn-text` with the message, for example `The records need update 29 for the statutory check. Restart the app.` (app.py:2166) or `The {from|to} month isn't a month. Months are written like 2026-10.`

**State 1: not configured (`d.configured` false, app.js:1976-1981)**
- Heading `Statutory payables`.
- Grey banner, bold `Nothing is checked yet`, then the summary.
- Three variants:

| Variant | Summary (statutory.py:445-446) | Extra text | Buttons |
|---|---|---|---|
| a. Suggestions found | `No statutory accounts are confirmed for this company yet, so nothing is checked.` | Appended to the summary: ` Confirm which accounts the salary vouchers credit with what is taken off the salaries, and which take the employer's share.` Then the note `Suggested from the chart of accounts by their names:` and a table: Kind · Payable account (mono code + name) · Employer's share account (mono code + name, or `—`) · Due day (number, right-aligned) | `Use these accounts` (primary) and `Set them up in Setup instead` (ghost) |
| b. No suggestion | Same summary and appended sentence | Note `The chart of accounts has no account whose name looks like an EPF, SOCSO, EIS, SKBBK or PCB payable. Add them in Setup.` | `Open Setup › Statutory accounts` |
| c. All stopped (`d.stopped`) | `All the statutory accounts confirmed for this company are stopped, so nothing is checked.` | No appended sentence. Note `The statutory accounts confirmed for this company are all stopped in Setup. Start one again there to have it checked.` | `Open Setup › Statutory accounts` |

- `Use these accounts` (statutoryUse, app.js:2015-2022) posts to /api/statutory/use-suggested (app.py:2170-2189). Each suggestion is added as Setup would add it, so each gets its own history.
  - Success toast: `${n} statutory account(s) added.` (for example `5 statutory accounts added.`), then the tab redraws.
  - Error toasts: `Choose a company.` · `There is no such company.` · `The chart of accounts suggests no statutory account that isn't added already.` · any Setup refusal (A7).
- Both Setup buttons set the Setup section to statutory_accounts and open Setup on the same company.

**State 2: configured (app.js:1983-2011)**
- Row: `<h2>Statutory payables, {January 2026} to {November 2026}</h2>` and the ghost button `Statutory accounts in Setup`.
- Summary banner:
  - Class `warn` when there are problems; `grey` when `d.empty` (every tracked month is Nothing); else `ok`.
  - Bold text: `Statutory payables to look at` when there are problems, else `Statutory payables`. The span is `d.summary`.
  - Summary rules (statutory.py:505-526):
    - With problems: `{n} statutory payable(s) to look at: {first 4 texts joined by "; "}` plus `; and {n-4} more.`
    - All tracked months Nothing: `No statutory payables were taken off or paid in these months, so there was nothing to check.`
    - Otherwise: `All statutory payables cleared up to {Month YYYY}.` (the last month before the first that isn't Cleared or Nothing). If no month qualifies: `Nothing is cleared yet in these months.`
    - Then, if any month is Due: ` Next due by {15 Dec 2026}.`
- **Misposting banner** (27aeab2), only when `d.postings` is not empty: `banner warn`, bold `Employer's share on another account`.
  - One span per document: the doc no. as a button (SQL documents), then the rest of the text.
  - A grey `Before tracking` pill when the payroll month it pays is before the first month tracked.
  - Final span: `Correct it in SQL Account with a journal moving the amount to the right account, then fetch again.`
  - Text (statutory.py:498-501): `{doc} ({14 Oct 2026}) pays {EPF (KWSP)[ and SOCSO (PERKESO)]}, but puts RM {x} of employer's share on {code} {name}, the {Kind label} employer account, though it pays no {Kind label}. {Kind}'s employer share account is {code} {name}[; …]. The totals are right; each expense account is off by RM {x}.`
- Explanation note (fixed, app.js:2009): `Withheld is what the month's documents credit to the payable, with the corrections to it (a journal against the salary, shown as a correction, belongs to the month whose withholding it corrects). Paid is what the payments to the authority debit to it for that month (the month before their own first, else up to their own month), less any refund, with the employer's share they debit to its own account. The balance is the payable's, from the books, at the end of the due day.`

**One card per payable account (`card-in`, in Setup's order)**
- h3: `{label}` then muted `· {payable code mono} {payable name}`.
- Right-hand note: `Employer's share: {code mono} {name}` or `No employer's share account`, then ` · due by the {15th} of the next month`.
- Note: `Owed at {1 Jan 2026}: {X}` then `; {Y} of it paid since` (if any) then `, {Z} still owed` (if any) and a full stop.
  - X is `unknown` (no opening balance), `nil`, `{n} owed` or `{n} paid ahead` (owedRm, app.js:1969).
- Table columns (9): `Month` · `Withheld` · `Employer share` · `Paid` · `Difference` · `Balance at due date` · `Status` · `Payment voucher` · `Tracker payment`.
- Empty table: `No months in this period.`
- After the table: the account's notes, for example (statutory.py:399-401): `No opening balance of 430-100 is kept at 01/01/2026, so what was owed before then is unknown and its balances can't be shown. Fetch SQL's trial balance for that day.`

Cells per month row (app.js:1990-1999):
- **Row style:** muted when the month is before tracking or its status is Nothing.
- **Month:** `October 2026` with the note `Due {15 Nov 2026}` underneath.
- **Withheld:** `rmPlain` (e.g. `5,346.00`; zero shows `0.00`). Under it, the crediting documents comma-separated, a correction followed by muted `(correction)`.
- **Employer share:** `rmCell`, blank when zero.
- **Paid:** `rmPlain` (`0.00` when nothing was paid).
- **Difference:** blank when zero, else `+1,000.00` or `−5,346.00` (U+2212 minus).
- **Balance at due date:** `—` while the due day is today or later; else `nil`, `{n} owed` or `{n} paid ahead`.
- **Status pills:**

| Status | Pill tone | Notes |
|---|---|---|
| Cleared | ok | A second pill `Paid late` (warn) when `paid_late` |
| Due | warn | |
| Late | bad | |
| Short | bad | |
| Over | bad | |
| Nothing | grey | |
| Before tracking | grey | Reads `Before tracking · {status}` instead, title `Before the first month tracked: shown, never asked for` |

- **Status text** under the pill (statutory.py:404-420), with dates written `%d %b %Y` (zero-padded, e.g. `05 Nov 2026`):

| Status | Text |
|---|---|
| Cleared | `{L} for {October 2026} paid in full.` |
| Cleared, paid late | `{L} for {M} paid in full, the last of it on {17 Nov 2026}, after the due day {15 Nov 2026}.` |
| Due | `{L} for {M} is due by {15 Dec 2026}.` |
| Late | `{L} for {M} wasn't paid by {15 Nov 2026}.` |
| Short | `{L} for {M}: RM {x} less was paid than was taken off the salaries.` |
| Over | `{L} for {M}: RM {x} more was paid than was taken off the salaries.` |
| Nothing | `Nothing was taken off the salaries for {L} in {M}.` |

- **Payment voucher:** one line per payment, `{doc}` then muted `{14 Oct}`; `—` when none.
- **Doc numbers:**
  - For SQL documents, the doc no. is a link button (title `Show the lines of {doc}`). It opens the document's lines in a row under the month row; clicking again closes them (booksDoc, app.js:2025).
  - A document made here shows as plain mono text.
- **Tracker payment** (app.js:1985-1987):
  - No link: muted `Not linked` (SQL documents only).
  - Linked: a link with the amount (`RM 11,240.00`, title = the payment's description) that opens that payment on its company month, then muted `paid {14 Oct 2026}`.
  - Then a pill: `Agrees` (ok) when the tracker amount equals what the voucher pays to all statutory accounts; else `Voucher pays {1,086.40}` (warn, title `The voucher pays {x} to the statutory accounts`).
  - `—` when there is nothing.
- **Footer:** when the chart suggests accounts not yet added: `The chart also has {430-210, 430-220}, which look like statutory payables not checked. Add them in Setup if they are.`

### A3. Rules behind what is shown (hrp/statutory.py)

**Which accounts are checked**
- Only the active rows of `statutory_accounts` for the company (update 29). Nothing is checked until at least one is confirmed.

**Suggestions (suggest, :124-148)**
- A **payable** is suggested when:
  - its type is liability or untyped,
  - its name contains PAYABLE or ACCRU,
  - and its name has a kind word.
- An **employer's share** account is matched when:
  - its type is expense or untyped,
  - its name has the whole word EMPLOYER,
  - and its name has the same kind word.
- Kind words are tried in this order: SKBBK/LINDUNG → SIP/EIS → EPF/KWSP → SOCSO/PERKESO/SOCSCO → PCB/MTD/LHDN → HRDF/PSMB/"HRD CORP".
- Due day 15. The label comes from KIND_WORDS: `EPF (KWSP)`, `SOCSO (PERKESO)`, `EIS (SIP)`, `SKBBK (Lindung 24 Jam)`, `PCB (LHDN)`, `HRDF`, `Other statutory`.
- Codes that SQL's account lines name but the chart lacks are also considered (as untyped).

**What kind of document each one is (_kind_of_doc), judged by its lines on non-statutory accounts**
- All income or expense: a **correction**. It goes to the month of the last withholding (or its own month when that is older than the month before), and is marked `(correction)`.
- No income or expense line: **money**, meaning a payment, or a refund when it credits the payable.
- Otherwise: **usual** (credit = withheld, debit = paid).

**Withheld month**
- A salary credit counts in the payroll month its description names (db.filing_month), if that month is within 2 months before the document's own month; else in its own month.

**Payment allocation (_allocate)**
1. A payment goes first to the month before its own month, if that month owes exactly the payment.
2. Otherwise to any month owing exactly the payment.
3. Otherwise, if it equals everything owed, it is shared over all owing months.
4. Otherwise: month before first, then the oldest month owing, up to its own month.
5. Anything over what is owed is an overpayment of the month before.
6. A refund is taken back from the latest overpaid month.
- The opening balance counts as a "brought forward" month.

**Employer share and tracker**
- The employer share is the same documents' debit to the employer account, shared over the months the payment pays, in proportion.
- The tracker payment is the payment linked to the SQL voucher (sql_entries.payment_id). Its amount is compared with the voucher's total debits to every statutory payable and employer account. So one PERKESO voucher paying SOCSO, EIS and SKBBK together is compared as one amount.

**Status (:372-384)**
- `nothing`: nothing withheld and nothing paid.
- `over`: paid more than withheld.
- `cleared`: paid equals withheld; `paid_late` when the part paid by the due day was less than withheld.
- `due`: today is on or before the due day.
- `late`: due day passed and nothing paid.
- Otherwise `short`.
- The due date is the due day of the next month, capped at the month's last day.

**Before tracking and problems**
- Months before the company's first month tracked are grey, never problems, and never in Next up.
- Problems are late, short and over in tracked months.
- Next up (rule 14) takes only **late and short**, over the last 12 months to today.

**Misposting (misposted, :464-502)**
- A document is flagged when it debits a payable (it pays an authority) and also debits the employer account of a kind it pays nothing to.
- Documents are considered when dated from the first day of From to the last day of the month after To.

**Range**
- When From is after To, they are swapped.

### A4. Excel export (booksexcel.py:284-317; GET /api/export/books/statutory-payables.xlsx, app.py:2655-2680)
- Same months as the tab. File name: `{AISB} Statutory payables check to {30-11-2026}.xlsx` (the last day of the To month). Sheet `Statutory payables`.
- Header rows:
  - Row 1 (bold, 13 pt): `{AISB Sdn Bhd} ({AISB})`.
  - Row 2 (bold): `Statutory payables check, {January 2026}[ to {November 2026}] (payroll months)`.
  - Row 3: `Mirrored from SQL Account, read {18/11/2026}. Exported {18/11/2026 09:30}.`
    - For a company not kept in SQL: `Books kept in this app: this company's books are not kept in SQL Account.`
    - Nothing read yet: `Mirrored from SQL Account: nothing has been read from SQL yet.`
- Columns: `Month, Due, Withheld, Paid, Employer's share paid, Difference, Balance at month end, Balance at the due date, Status, What it says`.
  - **Balance at month end** appears only in Excel.
  - Payment voucher and Tracker payment are not in Excel.
- Account rows (bold): `EPF (KWSP) (430-100, employer 900-110)`.
- Status: `Cleared, paid late`; ` (before the first month tracked)` added for those months.
- After the rows: the account notes, the summary (bold), then the misposting texts, then `Balances are signed: a payable still owed shows in brackets. Amounts are in ringgit.`

### A5. Next up rule 14 (nextup.py:452-466)
- Text: `{AISB}: {status text} Check it on the Statutory tab.`
  - For example: `AISB: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026. Check it on the Statutory tab.`
- Due = the month's due date, so the pill reads `Overdue 15 Nov`. Priority P1. One row per account and month. Button `Go`.
- Go opens Books › Statutory on that company with From `{month}-01` and To today. app.js:372-377 keeps the Books page's own month apart from the payroll month.
- The row carries amount = withheld − paid (the employees' share only, e.g. 5,346.00, not the 11,240 voucher). nextRow does not display it.
- It sits alongside, and does not replace, the existing payment row `Pay KWSP (EPF) for October … Past legal deadline (15 Nov)`. The same overdue KWSP can therefore give two Next up rows: one for the tracker payment and one for the books check.

### A6. Audit pack, auditor package, pack check
- **Pack PDF:**
  - New pages "SQL books check", "Statutory payables check", "Trial balance against SQL".
  - The statutory page is titled `{head} - Statutory payables check`. It holds the summary for that payroll month, then lines like `- EPF (KWSP) (430-100): EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026.`, the account notes and that month's misposting texts.
  - Without update 29: `No statutory accounts are confirmed for this company yet, so nothing is checked.`
- **Auditor package zip:** `Books/` holds `{AISB} Statutory payables check to 31-10-2026.xlsx` for the pack month.
- **Check this pack:** the group heading is `SQL's books and the statutory accounts (its books pages)`; its summary count reads `to SQL's books or the statutory accounts`. Changes to statutory_accounts count there.
- These pages belong mostly to the audit pack area. I list them so the statutory content is not lost.

### A7. Setup › Statutory accounts (masters.py:236-257; generic UI)

**Navigation and list**
- Nav: group `Companies and banks`, 4th item `Statutory accounts` (GROUPS, masters.py:259). The list is per company.
- Heading: `Statutory accounts · AISB`, button `Add statutory account`.
- Help note (exact): `The payable accounts the salary vouchers credit with what is taken off the salaries (EPF, SOCSO, EIS, SKBBK, PCB), and the expense account each authority's voucher debits with the employer's share. Accounting › Books › Statutory checks that each month is paid in full by its due day. Nothing is checked until an account is added here; that page suggests them from the chart of accounts by their names.`
- Then the generic `Click a row to change it. Something already used can't be deleted: stop using it instead, and its history stays.`, a search box, `Show stopped (n)`, and the deleted toggle (statutory_accounts is in the per-company list at app.js:4050).
- Columns: `Name` (link) · `Kind` (option label) · `Payable account` · `Employer's share account` (`—` when empty) · `Due day` (numeric) · `Used by` · `Status`.
  - `Used by` is always 0 with the title `Not used yet`, because nothing uses a statutory account.
  - `Status` is the pill `In use` / `Stopped`.
- Empty states: `None yet.` · `No statutory accounts match.` · `Only stopped statutory accounts: tick Show stopped to see them.`
- With no company: `Add a company first.`
- Order: the `sort` field, then id.

**Drawer**
- Eyebrow `Statutory account · AISB`. Title: the Name, or `New statutory account`. Pill `In use` / `Stopped`. The help text repeats.
- Fields:

| Field | Type | Required | Hint |
|---|---|---|---|
| `Kind` | select: `EPF (KWSP)`, `SOCSO (PERKESO)`, `EIS (SIP)`, `SKBBK (Lindung 24 Jam)`, `PCB (LHDN)`, `HRDF`, `Other statutory` | yes | — |
| `Name` | wide text | yes | `As the check names it, e.g. EPF (KWSP).` |
| `Payable account` | sqlcode: mono, uppercased | yes | `The liability the salary vouchers credit, e.g. 420-1001 EPF PAYABLE.` |
| `Employer's share account` | sqlcode | no | `The expense the authority's voucher debits with the employer's share, e.g. 900-E001. Empty: none (PCB).` |
| `Due day of the next month` | day, 1–31 | no | `Contributions for a month are due by this day of the next month. Empty: the 15th.` |
| `Order` | number | no | `Lower comes first. Empty: after the others.` |
| `Notes` | wide textarea | no | — |

- Buttons: `Add statutory account` / `Save`. Section `Where used`, which always shows `Not used anywhere yet.`
- `Stop using` / `Use again`, then `Delete` (always offered, because usage is empty, masters.py:599). Each asks why (askWhy) and then toasts `Stopped. Its history stays.` / `In use again` / `Statutory account deleted`.
- Stopped note: `Stopped: the statutory payables check leaves this account out.`
- History section at the bottom (histSection).
- Refusals (masters.py:472-491, 768-775, 853-857):
  - `Payable account: the company's chart of accounts has no account {code}, and no account line or opening balance names it.`
  - The same with `Employer's share account: …`
  - `The payable account and the employer's share account are two different accounts.`
  - `The account {code} is already a statutory account of this kind for the company.`
  - `Choose the company whose books it is in.`
  - An emptied due day saves as 15. An emptied Order means after the others.
- Put back after delete (restore.py):
  - `Its company has been deleted since, so the statutory account can't be put back. Put the company back first.`
  - `Its company was put back as a new record (#{n}), so the statutory account can't follow it. Add it again there.`
  - Plus the same Setup refusals.

### A8. Move setup (c4aa5e4; setupfile.py)
- Export "Everything" now carries `statutory_accounts` (columns kind, label, payable_code, employer_code, due_day, active, sort, notes), listed after GL accounts. A template does not carry them.
- A row whose payable or employer account is not in the company's chart is **left out of the file**, and the file records why (setupfile.py:238-251): `Statutory account {EPF (KWSP)} of {AISB}: its account {430-210} isn't in the company's chart of accounts. Add it to the chart in Setup and export again, or add the statutory account again after importing.`
  - Nothing tells the user at export time: the export is a plain download link.
- Import preview:
  - The counts table gets a row `Statutory accounts | n`, after `GL accounts` (LISTS order, after `Printed company names` and `Bank accounts`).
  - Notes gain `Left out of the file when it was made: {text above}` (setupfile.py:980).
  - Each row is checked as Setup checks it. A refusal reads `Statutory account {label} of {company}: {Setup refusal}`.
  - Older records: `The file's statutory accounts can be imported once the records are updated.`
- Import blocked because the records already hold data: `These hold … {n} statutory accounts …`. HOLDING order: companies, bank accounts, recurring payments, salary advances, customers and suppliers, GL accounts, **statutory accounts**, checklist items, …
- The "Everything" description is unchanged (app.js:3184): `The template, plus the companies, their bank accounts with the account numbers, charts of accounts, customers and suppliers, and each company's checklist. Keep the file safe.` It does **not** mention statutory accounts.

### A9. Defects and wording gaps found (worth deciding before designing)
1. **Bug: doc link in the misposting banner.** The doc-no. button there calls booksDoc. That function does `t.closest("tr")` and then `row.children.length`, but a banner has no row. The result is an error toast with a JavaScript error message instead of the document's lines (app.js:2008 and 2025-2036).
2. **"Late" can be a false alarm.** The check reads only the books (SQL's GL journal). It shows `Late`, which also raises Next up rule 14, whenever the authority voucher isn't fetched from SQL yet. The tracker may already say paid. Nothing says how far the journal reaches.
3. **Wrong wording for a company kept here:**
   - The misposting fix line says `Correct it in SQL Account …`.
   - The missing-opening note says `Fetch SQL's trial balance for that day.`
   - Both should read differently for a company kept here, such as AI.
4. **Doubled "owed".** `Owed at 1 Jan 2026: 5,346.00 owed` reads "owed" twice (app.js:2002).
5. **"Start" versus "Use again".** The stopped-state note says `Start one again there`, but the Setup button is `Use again`.
6. **Move setup gaps.** The "Everything" description omits statutory accounts, and accounts left out are only reported at import, not at export.
7. **Two names for the same thing.** Labels say `EPF (KWSP)` while tracker payments say `KWSP (EPF)`.
8. **Zero-padded dates.** Status texts use zero-padded days (`05 Nov 2026`), while the rest of the UI uses `5 Nov 2026`.
9. **Empty date inputs.** On the Statutory tab, From and To stay empty while the heading names the months.

---

## B. Canvas coverage today

| Item | Board | State |
|---|---|---|
| Books page, Statutory tab | **none** | No Books board exists at all. The Sidebar board has no `Accounting › Books` group: its groups are Dashboard, Companies, Monthly work, Filing, Setup. Entirely missing. |
| Setup › Statutory accounts | SetupNav.dc.html | Already lists `statutory_accounts`, labelled `Statutory accounts`, with glyph `trail` (the same as Chart of accounts). It links to **SetupStatutory.dc.html, which does not exist**, so the link is broken. |
| Chart sample | SetupChart.dc.html:426-437 | Has `430-000 Statutory payables`, `430-100 KWSP payable`, `430-200 PERKESO payable`, `430-300 PCB payable`. No EIS or SKBBK payable and **no employer-share expense accounts**, so the suggestion and the employer column can't be shown from it. |
| Move setup | SetupMove.dc.html | The COUNTS list (line 211) has no `Statutory accounts`. The notes list has no `Left out of the file when it was made: …`. The blocked "holding" sentence (214-215) has no statutory accounts. The Everything text (78) matches the app, which also omits them. |
| Next up rule 14 | Main.dc.html todo (418-430), Company.dc.html next-up (803, 813), Sidebar badges | No rule-14 row anywhere. |
| Excel / pack pages | AuditPack.dc.html | No "Statutory payables check" page in the pack contents. The auditor package note (line 182) doesn't mention the Books Excel files. Mostly the audit pack area's job. |
| Empty, error and confirm states | States.dc.html | Nothing for the statutory tab: the not-configured variants, the update-29 error and the Use these accounts toast. |

**Sample conflicts in the canvas that touch this area:**
- **Company.dc.html, AISB October:**
  - KWSP 11,240.00 unpaid (Past legal deadline).
  - PERKESO (SOCSO & EIS) 1,086.40 paid 17 Nov, entered by hand, no SQL ref.
  - PCB 4,915.00 paid 14 Nov, no SQL ref.
- **Company.dc.html, AISB September:**
  - KWSP PV2610-005 and PCB PV2610-006 paid 14 Oct.
  - **No PERKESO row.**
- **Company.dc.html, AI October:**
  - KWSP 11,240.00 unpaid.
  - PERKESO 612.40 paid 14 Nov.
- **Main.dc.html** Next up names only AI's KWSP. The Company board's AISB Next up also has `Pay KWSP (EPF) for October`.
- **Sql.dc.html:645/754** has AISB `PV2610-019 · 28 Oct · KWSP October · 400-K001 · 11,180.00`, linked to `KWSP (EPF) · October 2026`.
  - This contradicts the Company board, where AISB's October KWSP is unpaid.
  - In the statutory logic it would pay October early: Cleared, or Short against 11,240.

---

## C. Proposal

### Sample data, reconciled with the existing boards
- **Companies:**
  - AISB: kept in SQL, first month tracked 2025-01, FY starts January.
  - AI (Agrinexus International): not kept in SQL, first month 2025-03.
- **Dates:** today Wed 18 Nov 2026, working month October 2026. The default range is January 2026 to November 2026.
- **Assumption:** SQL's GL Journal for AISB was fetched on 18 Nov up to 17 Nov. The October PCB and PERKESO vouchers are in SQL but **not yet linked** to their tracker payments, which matches the Company board where they show no SQL ref.
- **AISB chart** (to add to SetupChart.dc.html):

| Code | Name | Type | Change |
|---|---|---|---|
| 430-100 | KWSP payable | liability | existing |
| 430-200 | PERKESO payable | liability | existing; read as SOCSO |
| 430-210 | EIS (SIP) payable | liability | new |
| 430-220 | SKBBK payable (Lindung 24 Jam) | liability | new |
| 430-300 | PCB payable | liability | existing |
| 900-110 | KWSP - employer | expense | new |
| 900-120 | PERKESO - employer | expense | new |
| 900-130 | EIS (SIP) - employer | expense | new |

  All of these match the suggestion rules in A3.
- **Monthly figures, the same every month** (they add up to the Company board's amounts):
  - EPF: withheld **5,346.00** + employer **5,894.00** = **11,240.00** (the KWSP amount).
  - SOCSO: 172.50 + employer 603.70.
  - EIS: 77.80 + employer 77.80.
  - SKBBK: 154.60, no employer account.
  - PERKESO total: **1,086.40** (the PERKESO amount).
  - PCB: **4,915.00**, no employer account.
  - The split between SOCSO, EIS and SKBBK is illustrative; the owner should confirm it is plausible.
- **Salary voucher PV2610-014 (24 Oct):**
  - Dr 900-100 Salaries and wages 59,265.90.
  - Cr 310-000 Maybank current 48,600.00 (the canvas's net payroll).
  - Cr 430-100 5,346.00, 430-200 172.50, 430-210 77.80, 430-220 154.60, 430-300 4,915.00.
  - September: PV2609-012, with the same lines.
- **Authority vouchers:**

| Voucher | Date | Pays | Amount | Tracker |
|---|---|---|---|---|
| PV2610-005 | 14 Oct | KWSP for September | 11,240.00 | linked, `Agrees` |
| PV2610-006 | 14 Oct | PCB for September | 4,915.00 | linked, `Agrees` |
| PV2610-007 | 14 Oct | PERKESO for September | 1,086.40 | `Not linked` (the Company board's September list has no PERKESO payment, which this shows naturally) |
| PV2611-012 | 14 Nov | PCB for October | 4,915.00 | `Not linked` |
| PV2611-015 | 17 Nov | PERKESO for October | 1,086.40 | `Not linked` |
| — | — | KWSP for October | none | — |

- **Fix the Sql board's PV2610-019 "KWSP October 11,180.00".** Either re-describe it as a non-statutory voucher, or drop it. Otherwise it contradicts the unpaid October KWSP.
- **Add AISB's rule-14 row to Main's Next up**, and AISB's unpaid KWSP payment alongside AI's.

### New board 1: `BooksStatutory.dc.html` "Books · Statutory · AISB" (1440 wide)
This shares the Books page shell with whatever Books board the Books area adds: title, From/To/Show/This financial year to date/Excel, and the six tabs with Statutory pressed. It also needs a Sidebar `Accounting › Books` item.

States (a state switcher on the board):
1. **Default, AISB with a problem.**
   - Heading `Statutory payables, January 2026 to November 2026` and `Statutory accounts in Setup`.
   - Warn banner: `1 statutory payable to look at: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026.`
   - The explanation note.
   - Five account cards, each with rows January–November. September, October and November are the detailed rows; the earlier months are Cleared with `nil`.
   - EPF card: `Owed at 1 Jan 2026: 5,346.00 owed; 5,346.00 of it paid since.`
     - Sep: 5,346.00 / 5,894.00 / 5,346.00 / — / nil / Cleared; PV2610-005 14 Oct; `RM 11,240.00 paid 14 Oct 2026 [Agrees]`.
     - Oct: 5,346.00 (PV2610-014) / — / 0.00 / −5,346.00 / `5,346.00 owed` / **Late**, `EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026.`
     - Nov: muted, Nothing, balance `—`, `Due 15 Dec 2026`.
   - SOCSO card, Oct: 172.50 / 603.70 / 172.50 / — / `172.50 owed` / **Cleared + Paid late**, `SOCSO (PERKESO) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026.`; PV2611-015 17 Nov; `Not linked`.
   - EIS and SKBBK cards: the same pattern.
   - PCB card, Oct: Cleared; PV2611-012 14 Nov; `Not linked`.
   - The doc-lines expansion is shown open under one row, for example PV2610-005's lines.
2. **Misposting.** The same page with PV2610-005 putting the employer's 5,894.00 on 900-120 (the September EPF employer cell becomes blank). The banner `Employer's share on another account`: `PV2610-005 (14 Oct 2026) pays EPF (KWSP), but puts RM 5,894.00 of employer's share on 900-120 PERKESO - employer, the SOCSO (PERKESO) employer account, though it pays no SOCSO (PERKESO). EPF (KWSP)'s employer share account is 900-110 KWSP - employer. The totals are right; each expense account is off by RM 5,894.00.` plus `Correct it in SQL Account with a journal moving the amount to the right account, then fetch again.` The design should also decide where its doc link opens (finding A9.1).
3. **All clear.** For example with To = September 2026. Ok banner: `All statutory payables cleared up to September 2026.` Also a variant with a Due month: `… Next due by 15 Dec 2026.`
4. **Other statuses.** Show Short, Over, a `(correction)` credit, `Voucher pays 1,066.40` against a tracker of 1,086.40, and `Before tracking · Cleared` (From set to Nov 2024 for AISB).
5. **Not configured, with suggestions.** The suggestion table with the five rows above (due day 15 each), `Use these accounts` / `Set them up in Setup instead`, and the toast `5 statutory accounts added.`
6. **Not configured, no suggestion.** AI, whose chart has no such names, with the "no account whose name looks like…" note.
7. **All stopped.**
8. **AI configured but no books lines yet.** Grey banner `No statutory payables were taken off or paid in these months, so there was nothing to check.`, muted Nothing rows, and the opening-unknown note. Its wording for a company kept here is gap A9.3.
9. **Loading and error.** `Loading…`, and `The records need update 29 for the statutory check. Restart the app.`

### New board 2: `SetupStatutory.dc.html` "Setup · Statutory accounts" (the broken SetupNav link)
- Setup layout with SetupNav `active="statutory_accounts"`, company picker AISB, heading `Statutory accounts · AISB`, `Add statutory account`, the help text verbatim, list tools, `Show stopped (1)`.
- Rows:

| Name | Kind | Payable | Employer's share | Due day | Status |
|---|---|---|---|---|---|
| EPF (KWSP) | EPF (KWSP) | 430-100 | 900-110 | 15 | In use |
| SOCSO (PERKESO) | SOCSO (PERKESO) | 430-200 | 900-120 | 15 | In use |
| EIS (SIP) | EIS (SIP) | 430-210 | 900-130 | 15 | In use |
| SKBBK (Lindung 24 Jam) | SKBBK (Lindung 24 Jam) | 430-220 | — | 15 | In use |
| PCB (LHDN) | PCB (LHDN) | 430-300 | — | 15 | In use |
| HRDF | HRDF | 430-400 | — | 15 | Stopped (shown when ticked) |

  Used by is 0 on every row.
- States:
  - The drawer for a new account and an existing one, with every field and hint, and `Where used: Not used anywhere yet.`
  - `Stop using`, `Delete`, and the ask-why flow.
  - Each refusal message.
  - The stopped note.
  - Empty `None yet.`
  - AI with no company chart.
- Consider giving the SetupNav item its own glyph, since it shares `trail` with Chart of accounts.

### Changes to existing boards
- **SetupChart.dc.html:** add 430-210, 430-220, 900-110, 900-120, 900-130 (and 430-400 HRDF if the stopped row is used) under their groups. This makes the Statutory board's codes real.
- **SetupMove.dc.html:**
  - COUNTS: add `['Statutory accounts', 5]` after `GL accounts`; after `Companies` also add `Printed company names` (another area).
  - Add the note `Left out of the file when it was made: Statutory account HRDF of AISB: its account 430-400 isn't in the company's chart of accounts. Add it to the chart in Setup and export again, or add the statutory account again after importing.`
  - Holding sentence: add `5 statutory accounts` after GL accounts.
  - Flag A9.6: "Everything" should probably name statutory accounts, and the app should say at export time when one is left out.
- **Main.dc.html and Sidebar.dc.html:** add the rule-14 Next up row `AISB: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026. Check it on the Statutory tab.`, `Overdue 15 Nov`, verb `Go`, href BooksStatutory.dc.html. Count it in AISB's sidebar badge. Also add AISB's `Pay KWSP (EPF) for October` row to match the Company board.
- **Company.dc.html:**
  - AISB October Next up: add the rule-14 row (3-row limit, so it may sit under Show all).
  - Optionally add a September PERKESO payment. If none is added, the Statutory board shows PV2610-007 `Not linked`, as proposed.
- **Sql.dc.html:** re-describe or remove PV2610-019 `KWSP October 11,180.00` (conflict above).
- **States.dc.html:** add the statutory not-configured, error and toast states if the Books board doesn't carry them itself.
- **AuditPack.dc.html** (coordinate with that area):
  - The pack contents gain the three books pages, including `… - Statutory payables check`, for example the summary plus `- EPF (KWSP) (430-100): EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026.`
  - The auditor package mentions `Books/` Excel files, including `AISB Statutory payables check to 31-10-2026.xlsx`.
  - "Check this pack" adds the group `SQL's books and the statutory accounts (its books pages)`.

### Key code locations
- **static/app.js:** 127, 372-377, 1650-1767, 1962-2036, 2524, 2676-2745, 2836-2865, 2966-2985, 3173-3215, 4050.
- **hrp/statutory.py:** whole file.
- **hrp/app.py:** 2153-2189, 2655-2680, 3018-3053.
- **hrp/masters.py:** 236-259, 272, 472-491, 599, 768-775, 853-857.
- **hrp/setupfile.py:** 7, 76-97, 236-251, 640-653, 919, 979-980.
- **hrp/nextup.py:** 452-466.
- **hrp/booksexcel.py:** 50-67, 102-106, 284-317.
- **hrp/reports.py:** 336-356.
- **hrp/auditpack.py:** 567-645.
- **hrp/packcheck.py:** 24-40.
- **hrp/restore.py:** 33-35, 160-167, 335-337.
- **Canvas** (design/canvas):
  - SetupNav.dc.html:46
  - SetupChart.dc.html:416-437
  - SetupMove.dc.html:78, 211-215
  - Company.dc.html:727-813
  - Main.dc.html:418-430
  - Sql.dc.html:645, 754
  - Sidebar.dc.html:130-136
