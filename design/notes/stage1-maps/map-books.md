# Books and accounting reports: inventory, canvas coverage and proposal

**Scope.** I read the code at HEAD b698dc1 against baseline b7d7fa0, and changed no files. The whole Books page came after the baseline:
- hrp/books.py, hrp/finstatements.py and hrp/booksexcel.py are new files.
- hrp/ledger.py and hrp/sqlgl.py are new.
- The Books UI is new: static/app.js lines 1642-2036, plus the helpers at 1418-1504.
- **The canvas has no Books board, no "Accounting" sidebar group and no books icon.**

Note: hrp/statements.py is the Maybank bank-statement reader. The financial statements live in **hrp/finstatements.py**, so I covered that file instead.

---

## A. Inventory: what the user sees, with exact strings and code lines

### A0. How to reach the page, and the page-level rules
- **Sidebar.** `VIEWS` (app.js:126-129) adds a group `"Accounting"` holding one item, `"Books"` (view `books`). It sits between "Monthly work" and "Filing".
  - Icon `ICON.books` (app.js:136) is an open book: `M4 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4zM20 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6zM7 8h2M15 8h2M7 12h2M15 12h2`.
- **No payroll month.** `goTo` (app.js:365) leaves `state.month` unchanged when the view is books ("the Books page has no payroll month").
- **Next up deep link.** goTo (app.js:372-376) opens a tab with dates. The statutory rows in Next up (nextup.py:462) open `{view:"books", tab:"statutory", from:"<month>-01", to:<today>}`.
- **Other places that point to the page in words:**
  - sqlbooks.py:115: "Open it on the SQL page or Accounting › Books to see its lines."
  - sqlbooks.py:130: "See Accounting › Books › Trial balance, then fetch again what differs."
  - masters.py:240 mentions "Accounting › Books › Statutory".
- **State defaults** (app.js:122): `books: {tab:"tb", from:null, to:null, rollup:true, account:null, q:"", months:false, side:"customers", party:null}`.
  - The trial balance opens with **roll-up ticked**.
  - Switching company resets from, to, account, search and party. The tab, roll-up and months settings are kept (app.js:1653).
- **Load failure for the whole page** (app.js:315): `Couldn't load this page.` followed by the message.

### A1. Page shell (viewBooks, app.js:1650-1705)
- **No company yet:** `Add a company in Setup first.`
- The company picker comes first: one button per company, filled for the current one (`entityPicker`, app.js:319).
- **Heading:** h1 `Books · {code}`, for example `Books · AISB`.
- **Intro note, company kept in SQL:**
  > "The books worked out here: each account starts from the opening balance SQL printed (its trial balance or ledger, kept when they were fetched) and adds the account lines of SQL's GL Journal of Transaction. Profit and loss start again at the financial year start (1 January). Nothing on this page can be changed; it follows what is fetched from SQL."
- **Intro note, company not in SQL:**
  > "The books kept here for this company: each account starts from its opening balance entered here (or from nothing) and adds the account lines entered here. Profit and loss start again at the financial year start (1 January). Nothing on this page can be changed."
- **When the financial-year setting is empty**, the bracket reads `(January, as it isn't set in Setup › Companies)`.
- **Gap:** nothing in the app lets anyone enter an opening or account line "here". `put_openings` with source `here` exists, but no route calls it. A company not in SQL (AI) therefore always shows empty books.
- **Period row:**
  - `From` (date input `bkFrom`) and `To` (date input `bkTo`).
  - Button `Show`.
  - Ghost button `This financial year to date`, which clears both dates.
  - Link `Excel` (`#bkExcel`), titled `This report as an Excel file, for the dates and options shown`.
- **Tab control** (aria-label "Report"), six tabs: `Trial balance` | `General ledger` | `Profit and loss` | `Balance sheet` | `Customers and suppliers` | `Statutory`.
- **Loading:** `Loading…`. The Excel link is hidden while loading and after an error.
- **Errors** appear as a note in warning colour, using the server's sentence (app.py:2031-2053, 2111-2123):
  - `The from date isn't a date (use YYYY-MM-DD).` and the same for `to`.
  - `The from date is out of range: use a date from 1900 to 2999.`
  - `The From date is after the To date.`
  - `The as-at date isn't a date (use YYYY-MM-DD).` and `The as-at date is out of range: use a date from 1900 to 2999.`
  - `Columns are 'total' or 'month'.`
  - `Months are shown for up to 24 months at a time. Choose a shorter period.`
- **Default period** (`_books_period`, `books.default_to`):
  - To = the last day SQL's kept reports reach: the latest `period_to` of the trial balance, journal or GL ledger reads, never after today. It is today for a company not in SQL, or when nothing has been fetched.
  - From = the start of the financial year on or before To.
  - After each load the page writes the dates the server used back into the inputs (app.js:1746).
- **Excel link per tab** (app.js:1753-1767), all under `/api/export/books/…`:
  - `trial-balance.xlsx?…&rollup=`
  - `ledger.xlsx?…&account=`
  - `profit-and-loss.xlsx?…&columns=month|total`
  - `balance-sheet.xlsx?entity_id&as_at=`
  - `customers-and-suppliers.xlsx?…&side=`
  - `statutory-payables.xlsx?…`
  - The link is hidden on a single customer's or supplier's statement.
  - It is a plain link: an error comes back as a raw JSON page.
  - Each download is logged in the audit trail as `Opened books export` (app.py:2656 `@audited_read("books export")`, :70).

### A2. Trial balance tab (tbHtml 1788, paintTbRows 1805; server books.trial_balance 458, check_against_sql 580)

**Check-against-SQL banner** (`sqlCheckBanner` 1771-1784). It is shown only for a company kept in SQL. Four states:

1. **Agrees** (green): **`Checked against SQL's trial balance: agrees`**, then text such as `Agrees with SQL's trial balance as at 31/10/2026: all 22 accounts compared.` (books.py:721), plus any extra sentences.
2. **Not checked** (grey): **`Not checked against SQL's trial balance`**. The text is one of:
   - `No trial balance of SQL's is kept yet.`
   - `No trial balance of SQL's as at {dd/mm/yyyy} is kept, so this one can't be checked against SQL's. Fetch SQL's Trial Balance for the same dates.` (562)
   - `SQL's trial balance as at {d} was kept, but its stored file is missing or has changed since it was kept, so it can't be read again.` (576)
3. **Differences** (warning): **`Checked against SQL's trial balance: differences`**.
   - Text: `{n} accounts differ from SQL's trial balance as at {d}; {agree} agree.` (702), followed by `SQL's trial balance was read on 18/11/2026 at 10:42; the latest GL Journal of Transaction for these dates on 18/11/2026 at 10:42.` (712, `_when`).
   - Table: `Account | What differs | SQL | Here | Difference`. Amounts show as `x Dr`/`x Cr` (`drCr`).
   - Row text (615):
     > "{code name}: {words} SQL's trial balance has {sql}, the books here {here} (a difference of {here-sql})."
   - `{words}` is one of:
     - `its balance at 31/10/2026:`
     - `its lines from 01/10/2026 to 31/10/2026:` (profit and loss, compared from SQL's From date)
     - `the movements from {from} to {to}:` (period, balance-sheet accounts, only when SQL's From date equals the From date)
     - `its balance at {d}, with its {n} customer or supplier code(s) ({codes}):` (a control account compared together with its customers' or suppliers' codes)
     - `its balance at {d}, counting profit and loss into it up to {SQL From} as SQL does from its From date:` (retained earnings)
4. **Possibly out of date** (grey; added in 3030d67, counts sharpened in 2cdf9b6): **`Checked against SQL's trial balance: possibly out of date`**.
   - Text: the differences text plus
     > "The journal was read after the trial balance, so these differences may be out of date rather than errors: export SQL's Trial Balance again for the same dates (01/10/2026 to 31/10/2026) and Fetch it." (books.py:715)
   - Table: `Account | May differ (re-export SQL's trial balance to check) | SQL then | Here | Difference`.
   - Rule: a GL Journal of Transaction from a **later fetch** (a higher import number; the same fetch doesn't count) did one of these to a document dated in the trial balance's dates: added it, replaced it, found it deleted, or **found again one marked deleted** (`back_batch_id`, books.py:749-762).

**Extra sentences that can follow any outcome:**
- `SQL's trial balance runs from {d or 'no From date'}, not {From}, so the period's movements aren't compared, only the balances.`
- `Not compared, as no opening balance is kept for them: {codes}.`

**Which SQL trial balance is used** (`_stored_tb`): one whose as-at day equals To, preferring the same From date, latest read first.

**Heading and openings line:**
- h2 `Trial balance, {1 October 2026} to {31 October 2026}`, with pill `Balances` (green) or `Doesn't balance` (red).
- Note, built from `d.openings`: `Openings from SQL's trial balance at 1 October 2026 (18 accounts); not on SQL's trial balance, so nothing at 1 October 2026 (3 accounts).`
  - Other words, from SOURCE_WORDS (books.py:30): `SQL's GL ledger`, `entered here`, `the books kept here from the start` (shown without a date), `inside its control account` (excluded from the count).

**Options:**
- Checkbox `Customers and suppliers added into their control accounts, as SQL prints them` (`bkRollup`, ticked by default).
- Search box, placeholder `Search accounts`. Count `{n} of {m} shown`. It matches code, name and rolled-in codes.

**Table** (`table.books-tb`):
- Columns: `Code | Name | Opening debit | Opening credit | Debit | Credit | [Year start] | Closing debit | Closing credit`.
- `Year start` appears only when some account has a year-start move inside the period. Its cells show `x Dr/Cr`.

**Row rules:**
- The code is a link (`Open the ledger of {code}`) that switches to the General ledger tab on that account.
- The line with no code (`Profit and loss carried at the year start (no retained earnings account in the chart)`) shows `—` for the code.
- The name gets a pill `Not in chart` when the name came only from what SQL printed, or there is none.
- Notes under the name: `With 300-T001, …` (rolled in) and `Sub-ledger of {control}` (when roll-up is off).
- An unknown opening or closing shows `—`. A zero shows blank (`rmCell`).
- The footer `Total` row is bold. When any opening or closing is unknown, the opening and closing totals show `—`.

**Empty rows:**
- `No account matches.` (search)
- `No opening balance or account line is kept for these dates yet. Fetch SQL's reports on the SQL import page.` (the second sentence only for a company in SQL)

**Notes under the table** (books.py:518-542), in order:
- Missing openings: `No opening balance is kept for {codes}, so their balances can't be shown and the totals can't be checked. Fetch SQL's trial balance (with a From date) or its GL ledger for the start of the period.`
- Otherwise, when unbalanced: `The trial balance doesn't balance: the openings come to {x} debit and {y} credit, the closings to {a} and {b}.`
- Opening jump: `{code}: a later opening kept for this account doesn't follow from the earlier one and the lines (a difference of {x}); its closing is the later opening's.`
- Untyped accounts: `Not typed in the chart of accounts, so taken as balance-sheet accounts (never started again at the year start): {codes}. Set their types in Setup.`
- Year start inside the period: `The period holds the start of the financial year (01/01/2026): profit and loss start again there, and what they held moves into retained earnings (the Year start column).`
- Year start not set: `The financial year start isn't set for this company (Setup › Companies), so it is taken as January.`
- `No opening is kept for {codes} before the year start, so what they moved into retained earnings there is not counted.`
- No retained earnings account: `The chart of accounts has no retained earnings account (SQL type RE, or an equity account named RETAINED), so what the year start moves from profit and loss is shown on a line of its own.`
- Coverage (books.py:452): `The GL Journal of Transaction reads kept cover 01/10/2026-12/11/2026, not all of 01/01/2026-12/11/2026: lines dated outside them are missing here. Fetch the journal for the whole period.` (or `no dates yet`)

**Server rules that change what is shown** (books.py docstring and `_Books`):
- **Where an opening comes from.** An account's opening is the latest one kept on or before the day: SQL's trial balance first, then its GL ledger. To that it adds the lines since.
- **Accounts left off a trial balance.** An account that a later SQL trial balance doesn't list had nothing on that date (`not_on_tb`).
- **Customer and supplier codes.** A customer's or supplier's code (for example 300-T001) has no opening of its own; it is counted from its control account's first opening. If its control isn't known, an unknown code goes under its family's `-0000` account.
- **Profit and loss at the year start.** Profit and loss restarts at the financial-year start, and the balance moves into retained earnings.
  - The retained earnings account is the chart account of SQL type RE, else an equity account named like RETAINED.
  - A profit and loss opening kept later in the year (SQL's trial balance with a From date mid-year) counts as the year so far.
- **Year end.** A period ending on the year end closes *before* that year's move.
- **Before-tracking documents.** Books never set aside documents from before the first month tracked. The full mirror is used. Only the Statutory tab greys those months.

### A3. General ledger tab (ledgerHtml 1818-1837; books.ledger_report 374)
**Account picker:**
- Field `Account (type to search)`, placeholder `All accounts`, with a datalist of `code name` covering every chart account and every code with lines or openings.
- Ghost button `All accounts` when one is picked.
- An unknown code typed in is ignored.

**Heading:** h2 `General ledger, {from} to {to}`.

**One card per account:**
- h3: mono code, then the name, plus `Not in chart` when it applies.
- `Sub-ledger of [control link]` on the right.
- Table `Date | Doc No | Book | Description | Debit | Credit | Balance`. Dates use `shortDate` ("5 Oct") **without the year**, even for other years.
- **First row:** `Opening balance · SQL's trial balance at 1 October 2026`, balance `89,218.35 Dr`.
- **Line rows:**
  - Book names: `Bank`, `General`, `Sales`, `Purchase`, `Other`.
  - A SQL document number is a link (`Show the lines of {doc}`) that opens the document inline (A4).
- **Year-start rows** are highlighted. They read `Year start: the year's profit and loss moved to retained earnings` (profit and loss accounts) or `Year start: the profit and loss of the year before carried in` (retained earnings).
- **Closing rows:** `Total for the period` (debit and credit totals), then `Closing balance` (balance only).

**Per-account notes:**
- `No opening balance of {code} is kept: fetch SQL's trial balance (with a From date) or its GL ledger for the start of the period, or a period after one. The running balance starts from 0.`
- `A later opening kept for {code} says {x} after {d}, but the opening and the lines come to {y} (a difference of {z}).`
- `A customer's or supplier's account: it rolls up into {ctl}, whose opening holds its balance before {d}; its own balance here is its lines from then.` (or `…; its own balance here is its lines.`)
- On a control account picked on its own: `The trial balance, with customers and suppliers added into their control accounts, shows 400-000 with 400-E012 added in: its ledger follows below, and together they close at {x}.`

**Page notes:**
- `{code} is not in the chart of accounts, and no line or opening is kept for it.`
- The coverage note.

**Empty:** `No line or opening balance is kept for {code|any account} in these dates.`

### A4. A document's lines inline (booksDoc 2025, ledgerDocView 1450, /api/ledger/doc app.py:2014)
- Clicking a document number inserts a row below; clicking it again closes it.
- **Header:** `{doc} · {book label}` with pill `No longer in SQL` (red) or `Replaced` (grey).
- **Source line:** `Version 2, 4 November 2026, from SQL's GL Journal of Transaction (GL Journal.xlsx), read 2026-11-18 10:42`. Other sources: `the journal lines pasted` and `the journal lines pasted before`.
- **Table:** `Account | Description | Debit | Credit`.
  - The bank's lines are tinted, with pill `Bank`.
  - A code unknown to the chart and to customers and suppliers gets `Not in chart`.
  - Then a `Total` row.
- **Checks:** warning lines (ledger.doc_checks), or `The lines balance and agree with the listing.`
- **Earlier versions:** collapsible `Earlier versions (n)`.
- **Errors (toast):**
  - `SQL's Journal of Transaction hasn't given the lines of this document yet.` (404)
  - `The records need update 26 to show account lines. Restart the app.`

### A5. Profit and loss tab (plHtml 1869; finstatements.profit_and_loss 295)
**Banner:**
- Green **`Reconciles to the trial balance`**, red **`Doesn't reconcile to the trial balance`**, or grey **`Not checked against the trial balance`**.
- The text joins these sentences:
  - `The net profit or loss after tax, -91,751.80, is the trial balance's profit and loss accounts' movement for 01/10/2026 to 31/10/2026.`
  - or `The net profit or loss after tax is {x}, but the trial balance's profit and loss accounts moved {y} (a difference of {z}).`
  - or `The check against the trial balance can't run: an opening balance is missing (see the notes).`
  - plus `The trial balance for these dates doesn't balance (see the Trial balance tab).`
  - or `The trial balance for these dates can't be fully checked: an opening balance at {d} is missing (see the Trial balance tab).`
  - with months shown: `The months add up to the total.` or `The months don't add up to the total for {codes}: a later opening kept inside the period doesn't follow from the lines before it.`

**Empty:** grey banner `Nothing to check` / `No income or expense account moved in these dates.`, then h2 and the same note.

**Heading and controls:**
- h2 `Profit and loss, {from} to {to}`, with checkbox `Months` (`bkMonths`).
- Note: `Income is shown as a credit above 0 and costs as a debit above 0; a figure in brackets is the other way round.`

**Table** (`table.fs`):
- Header: `Account`, then one column per month if Months is on (`Oct 2026`), the total column (`01/10/2026 to 31/10/2026`), and the comparative column (`01/10/2025 to 31/10/2025`) with sub-label `Comparative` in muted text.
- **Sections in SQL's order** (finstatements.py:37-49):
  - `Sales` (SL, with SA taken off) → `Total sales`
  - `Cost of sales` (CO) → `Total cost of sales`
  - **`Gross profit`**
  - `Other income` (OI, EO) → `Total other income`
  - `Expenses` (EP) → `Total expenses`
  - **`Net profit or loss before tax`**
  - `Taxation` (TX) → `Total taxation`
  - **`Net profit or loss after tax`**
  - `Appropriation` (AP) → `Total appropriation`, then **`Profit or loss after appropriation`** (only when there is an appropriation account)
  - `Not classified` with pill `Set their types in Setup` → `Total not classified (debit above 0)`
- Sections with no accounts are left out; the totals between them always show.
- **Account rows:** the code is a link to the ledger, then the name, `Not in chart` when it applies, and `With …` for rolled-in codes.
- **Sub-accounts** are indented 18px per level under their parent, followed by a `Total {parent name}` row. A parent with no amount of its own shows `0.00`.
- Negatives show as `(1,234.00)`. An unknown amount shows `—`.

**Comparative missing:** `No comparative column: {why}`, where `{why}` is:
- `The period runs across the start of a financial year, so there is no same period of one year before to compare it with.`
- `Nothing is kept for {d} to {d}, the same period a year before, so there is nothing to compare with.`
- `Not compared with {d} to {d}: {coverage note}`
- `No opening balance is kept for {codes} on {d}, so the same period a year before can't be worked out to compare with.`

**Notes:**
- Placed by type, for want of an SQL group: `{code name} is an {type} account but it has no SQL group, so it is shown under Other income|Expenses. Set its SQL group in Setup › Chart of accounts.` (or `…its SQL group is {name}, a balance sheet group…`)
- `Not typed in the chart of accounts, so not counted in the profit: {codes}. The trial balance takes them as balance sheet accounts. Set their types in Setup › Chart of accounts.`
- The appropriation note.
- `No opening balance is kept for {codes} at the start of a column's dates, so those amounts and the totals they are in can't be worked out. Fetch SQL's trial balance (with a From date) for the start of the period.`
- The financial-year-not-set note and the coverage note.

**Rule:** from a financial-year start, a profit and loss account opens at 0. The year-to-date view therefore works even when the only opening kept is SQL's trial balance from 1 Oct.

### A6. Balance sheet tab (bsHtml 1884; finstatements.balance_sheet 436)
- **Uses only To** (as at). The From field is ignored. Default: the last day SQL's reports reach.
- **Banner titles:**
  - **`Balances and reconciles to the trial balance`** (green)
  - **`Doesn't balance`** or **`Doesn't reconcile`** (warning)
  - **`Can't be totalled`** (grey)
- **Banner text pieces:**
  - `Balances: net assets and total equity are both {x}.`
  - `It doesn't balance: net assets come to {x} and total equity to {y}, a difference of {z}.`, followed by either
    `The accounts not classified ({codes}) hold {x} debit|credit between them and are left out of both sides: set their types in Setup › Chart of accounts and it will balance.`
    or `The trial balance as at that day doesn't balance either, or a balance is missing: see the Trial balance tab.`
  - `The balance sheet can't be totalled: an opening balance is missing (see the notes).`
  - `The profit or loss for the year to date, {x}, is the profit and loss account's net profit or loss after tax for {fy} to {d}.` (or the mismatch version, or `…can't be checked…: an opening balance is missing.`)
  - `The trial balance as at {d} doesn't balance: its closing balances come to {x} more debit than credit (see the Trial balance tab).`
  - or `Every account of the trial balance as at {d} is in it once.`
- **Empty:** grey `Nothing to check` / `No balance is kept at this day.`
- **Heading and note:**
  - h2 `Balance sheet at 31 October 2026`, with pill `Balances` or `Doesn't balance`, or no pill.
  - Note: `As at the To date above. The profit or loss for the year to date runs from 1 January 2026. Assets are shown as debits above 0, liabilities and equity as credits above 0; a figure in brackets is the other way round.`
- **Columns:** `At 31/10/2026`, plus comparative `At 31/12/2025`.
- **Sections** (finstatements.py:50-68):
  - `Non-current assets`, `Investments`, `Other assets`, `Current assets`, `Current liabilities`
  - **`Net current assets`**
  - `Non-current liabilities`, `Other liabilities`
  - **`Net assets`**
  - `Capital`, `Reserves`, `Retained earnings brought forward`, `Appropriation`
  - line `Profit or loss for the year to date`
  - **`Total equity`**
  - `Not classified`
- **Placement fallback by type:** assets go to Current assets, liabilities to Current liabilities, equity to Capital, each with a note saying why.
- **Comparative missing:**
  - `Nothing is kept for {d}, the end of the previous financial year, so there is nothing to compare with.`
  - `No opening balance is kept on or before {d}, the start of the previous financial year, so that year's profit, and so the balance sheet at {d}, can't be worked out to compare with. Fetch SQL's trial balance (with a From date) for {d}.`
  - `Not compared with {d}: that year's profit can't be worked out. {coverage}`
  - `No opening balance is kept for {codes} on or before {d}, the end of the previous financial year, so it can't be compared.`
- **Notes:**
  - Not classified: `…so left out of both net assets and equity: {codes}…`
  - Missing openings: `…Fetch SQL's trial balance (with a From date) for the start of the financial year.`
  - `The chart of accounts has no retained earnings account (SQL type RE), so the profit and loss carried at the year start is shown on a line of its own under Retained earnings brought forward.`
  - The financial-year and coverage notes.

### A7 and A8. Customers and suppliers tab, and one party's statement (partiesHtml 1906, partyHtml 1939; receivables.py)
These belong to Books, though the receivables area may also cover them in detail.

**Customers and suppliers list:**
- h2 `Customers|Suppliers, {from} to {to}`, with toggle `Customers` / `Suppliers`.
- **Banner:** `Ties to the control accounts`, `Doesn't tie to the control accounts`, `Not fully checked` or `Nothing listed`. Texts:
  - `Every control account ties: the customers listed add up to their control accounts in the trial balance.`
  - `No customer balance is kept for these dates.`
- **Notes:**
  - `Each amount is what is owed: what the customer owes the company; … Invoiced is what the sales book added, received what the bank book took off, other everything else (credit notes, journals). The ageing is at {d}.`
  - FIFO note: `SQL's exports don't say which receipt or payment settled which invoice, so each receipt, payment, credit note or journal is taken to settle the oldest invoice still open first. …`
- **Per control card:**
  - The h3 code links to the ledger.
  - Pill `Ties to the trial balance`, `Doesn't tie` or `Can't be checked`.
  - Columns: `Code | Name | Opening | Invoiced | Received|Paid | Other | Closing | Current | 31-60 days | 61-90 days | Over 90 days | [Brought forward]`.
  - A party in credit shows pill `In credit` with "paid in advance or overpaid".
  - A party missing from Setup shows pill `Not in Setup`.
  - Rows `Total` and `{code} in the trial balance` (`Moved x`).
  - Note `{ctl} {name}: the customers add up to the control account in the trial balance, {x} at the start and {y} at the end.`
- **Empty:** `No customer balance is kept for these dates. Fetch SQL's GL Journal of Transaction and trial balance on the SQL import page.`

**One party's statement:**
- h2 code and name, with button `All customers`.
- Note `Customer under {ctl link} {name}. Owed by them at {d}: {x|nothing|unknown|x in credit (paid in advance or overpaid)}.`
- A ledger-style table, then `Still open at {d}` with ageing pills and the table `Date | Doc No | Description | Invoice | Still open | Days | Age`.
- Otherwise `Nothing is open.` or `In credit, so nothing is aged.`

### A9. Statutory tab (statutoryHtml 1971; statutory.py)
Summary only; the statutory area may cover this in detail.

**Not set up:**
- h2 `Statutory payables` and grey banner `Nothing is checked yet`, with `No statutory accounts are confirmed for this company yet, so nothing is checked. Confirm which accounts …`.
- A suggestion table `Kind | Payable account | Employer's share account | Due day` with buttons `Use these accounts` and `Set them up in Setup instead`. The first gives toast `{n} statutory accounts added.`
- When all are stopped: `Open Setup › Statutory accounts`.

**Set up:**
- h2 `Statutory payables, January 2026 to November 2026` and button `Statutory accounts in Setup`.
- Banner `Statutory payables to look at` or `Statutory payables`. Summary such as `All statutory payables cleared up to September 2026. Next due by 15 Nov 2026.`
- Warning banner `Employer's share on another account`.
- **Per account:**
  - Owed line: `Owed at {d}: …`.
  - Table `Month | Withheld | Employer share | Paid | Difference | Balance at due date | Status | Payment voucher | Tracker payment`.
  - Status pills: `Cleared`, `Due`, `Late`, `Short`, `Over`, `Nothing`, plus `Paid late`.
  - Rows before the first month tracked are greyed: `Before tracking · Cleared`, titled "Before the first month tracked: shown, never asked for".
- **Period:** the months of From and To; when empty, this financial year to date (`statutory.default_range`).

### A10. Excel files (booksexcel.py; route app.py:2655-2692)
**Common layout:**
- **Title block:**
  - Row 1: `{Company name} ({CODE})`, bold, size 13.
  - Row 2: the heading.
  - Row 3: `Mirrored from SQL Account, read 18/11/2026. Exported 18/11/2026 10:42.` Alternatives: `Mirrored from SQL Account: nothing has been read from SQL yet.` and `Books kept in this app: this company's books are not kept in SQL Account.`
- **Headings and figures:** headings on row 5, frozen below, with column widths set. Amounts are numbers to 2 decimals, signed ones as `#,##0.00;(#,##0.00)`, dates as dd/mm/yyyy. Totals are written as figures, not formulas.
- **File names:** `{CODE} {words} to dd-mm-yyyy.xlsx`; the balance sheet uses `at`.
- **Unknown report:** `There is no such report.` (404).

| File | Sheet | Heading | Columns and extras |
|---|---|---|---|
| `AISB Trial balance to 31-10-2026.xlsx` | Trial balance | `Trial balance, 01/10/2026 to 31/10/2026 (customers and suppliers added into their control accounts)` | `Code, Name, Opening debit, Opening credit, Debit, Credit, [Year start (debit above 0)], Closing debit, Closing credit, [Added in]`. Then `Total`, then `Balances: the debits and credits are equal.` or `Doesn't balance (see the notes below).`, then `Checked against SQL's trial balance: {text}`, one row per difference, then notes |
| `AISB General ledger to …` / `AISB General ledger 310-000 to …` | General ledger | `General ledger, all accounts, …` or `General ledger of 310-000, …` | `Account, Date, Doc No, Book, Description, Debit, Credit, Balance (debit above 0)`. Per account: bold header, `Opening balance (SQL's trial balance at 01/10/2026)`, the lines, `Total for the period`, `Closing balance`, notes |
| `AISB Profit and loss to …` | Profit and loss | `Profit and loss, {from} to {to}` | `Code, Account, {column labels}[ (comparative)]`. Sign note, check text, `No comparative column: …`, notes |
| `AISB Balance sheet at 31-10-2026.xlsx` | Balance sheet | `Balance sheet at 31/10/2026 (profit or loss for the year from 01/01/2026)` | As the P&L, with the asset sign note |
| `AISB Customers to …` | Customers / Suppliers / Customers and suppliers | `Customers, … (ageing at {d})` | `Code, Name, Opening, Invoiced, Received|Paid, Other, Closing, 5 buckets, Note`. Totals and `In the trial balance` rows |
| `AISB Statutory payables check to 30-11-2026.xlsx` | Statutory payables | `Statutory payables check, January 2026 to November 2026 (payroll months)` | `Month, Due, Withheld, Paid, Employer's share paid, Difference, Balance at month end, Balance at the due date, Status, What it says`. Status may add ` (before the first month tracked)` |

### A11. Related screens outside the Books page (cross-references, because the stale trial-balance wording lives there too)
**SQL import page, card "Checks against SQL's reports"** (`sqlChecksCard` app.js:1463-1504):
- Intro: `The latest of SQL's GL Journal of Transaction, GL Ledger and Trial Balance fetched, checked against the account lines kept. Not checked: Period To Date and opening balances against the lines (SQL's trial balance moves earlier profit and loss into retained earnings on its From date), and anything after the dates the journals read cover.`
- Per report: header `Trial Balance · {file} · 1 Oct to 31 Oct · read …`. Then either a differences table (`Account | What differs | SQL's figure | The lines | Difference`) or pill `No differences`.
- **Stale banner** (1481), grey **`Possibly out of date`**:
  > "A GL Journal of Transaction read after this trial balance changed documents in its dates, so these differences may only be the trial balance being old. Export SQL's Trial Balance again for the same dates (1 Oct to 31 Oct) and Fetch it."
  - It sets `reads.trial_balance.stale` (app.py:2000-2002, `books.read_stale`).
- **Result lines from `_tb_checks`** (ledger.py:1040-1188):
  - `{n} accounts agree with the lines for the month.`
  - `{n} profit and loss accounts agree with the lines dated 01/10/2026-31/10/2026.`
  - From-date move: `SQL's trial balance counts profit and loss from its From date (01/10/2026), so it moved a loss of {x} from earlier into retained earnings. No document carries that move.`
  - `{n} balance-sheet accounts agree with SQL's ledger.`
  - Skips such as `Not checked: No GL Journal of Transaction read covers 01/10/2026-31/10/2026, so Month To Date can't be compared with the lines.`
  - When there is no From date: `At the start of the financial year (1 January) SQL moved a profit of {x} … so profit and loss Period To Date is not compared.`
- Openings not kept: `SQL's trial balance prints no From date, so its opening balances aren't kept.` (ledger.py:1274)
- Audit trail line (ledger.py:1712): `…; trial balance check: 2 differences; opening balances at 01/10/2026 kept for 21 accounts (1 changed, 0 removed from an earlier read)`.
- Fetch preview file note: `Checked against the account lines on import.`

**Setup › Companies** (masters.py:67-70):
- `First month tracked` (month), hint `Months before it are never set up on their own and nothing in them counts as overdue. Empty: no limit.`
- `Financial year starts in` (select January to December; blank option `—`), hint `Keep it the same as the company's setting in SQL Account: SQL's reports can't tell it. The trial balance check uses it, and later reports will too. Empty: January.`
- Opening refused for a company in SQL: `This company's books are kept in SQL Account: its opening balances come only from SQL's reports.`

**Monthly checklist item `SQL books agree with SQL Account`** (rules.py:174, sqlbooks.month_check):
- Done text: `Done: SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at 31 Oct 2026 agrees with the books here`.
- Failure texts include `Fetch SQL's Trial Balance up to at least 31 Oct 2026.` and the trial-balance differences text with ` See Accounting › Books › Trial balance, then fetch again what differs.`
- For a company not in SQL: `…tick it by hand.`

**Audit pack:** three books pages (auditpack.py:567-650): `SQL books check`, `Statutory payables check`, `Trial balance against SQL`. The last opens with `Possibly out of date: SQL's trial balance was read before a later GL Journal of Transaction.` or `Agrees with` / `Differs from SQL's trial balance.` / `Not checked.`

**Quirks the designers should know** (what the code does today):
1. An empty trial balance (company AI) shows the **green `Balances`** pill, because no accounts counts as balanced.
2. A trial balance with **missing openings** shows the **red `Doesn't balance`** pill. "Can't be totalled" would be closer.
3. Ledger and statement dates never show a year.
4. Date formats are mixed: headings say `31 October 2026`, server sentences `31/10/2026`, ledger rows `31 Oct`, file names `31-10-2026`.
5. The Excel link shows raw JSON when the export fails.
6. The financial-year hint says "later reports will too", but the P&L and balance sheet already use the setting.
7. For a company not in SQL, the intro promises "opening balance entered here", but nothing exists to enter one (stage 2).

---

## B. What the canvas covers today
Canvas folder: `design/canvas`

- **Books page (A1-A10): not on the canvas.** No board contains "Trial balance" (except the Sql intro), "General ledger", "Profit and loss", "Balance sheet", "Books ·" or "Checked against SQL's trial balance". Nothing draws the six Excel files.
- **Sidebar.dc.html** (groups at line ~129-136): the groups are Dashboard / Companies / Monthly work / Filing / Setup. The **Accounting group and Books item are missing**.
- **Icon.dc.html**: its 67 glyphs include no book glyph. Foundations.dc.html says "Two-tone icons · 67 glyphs".
- **CommandPalette.dc.html** and **MobileDesktopOnly.dc.html**: neither lists Books.
- **Foundations.dc.html "Dates and money"**: says "always RM first … Money out and money in sit in their own columns instead of a minus sign". Books reports show no RM, use `Dr/Cr` suffixes and brackets, and use `—` and blank for unknown and zero. There is no accounting-figures rule.
- **States.dc.html**: no Books loading, error or empty states.
- **SetupCompanies.dc.html** (lines 382-383, 496-502):
  - The financial-year and first-month fields exist, but the financial-year hint is shorter than the app's. The blank option reads `January (not set)`; the app shows `—`.
  - AISB `first_month: '2025-01'` conflicts with Bank.dc.html `FIRST: '2026-07'` (line 408).
- **SetupChart.dc.html** (sample accounts, lines 417-452):
  - **No retained earnings (RE) account.** The Books reports would show the "no retained earnings account" line and notes.
  - No Bank charges, Bank profit or 500-F001 accounts, though other boards use 900-010/900-700 and 500-F001.
  - 350-000 (no SQL group) and 999-000 (no type) already exist. They produce real Books notes, which is good.
- **Sql.dc.html:**
  - The READ list (line ~715) has only `GL Ledger.xlsx` (1 Oct to 12 Nov). There is **no GL Journal of Transaction or Trial Balance file**.
  - There is **no "Checks against SQL's reports" card**, so the stale wording `Possibly out of date` is missing. The from-date move and openings lines are also absent.
  - The journal-paste sample uses `900-010 Bank charges`, which is not in the chart.
  - OR2610-006 Fund received is **50,000.00**, but the Bank board's October book side money in is **47,800.00** (Bank.dc.html:387).
- **Company.dc.html**: no `SQL books agree with SQL Account` checklist item.
- **AuditPack.dc.html**: no books pages.
- Both of these are owned by other areas; I list them here because the stale trial-balance wording appears in them.

---

## C. Proposal

### C1. New canvas section "Accounting"
Add a `title1` note "Accounting" at y≈16820, and move Filing and everything below it down by about 2,700. Alternatively, put the row to the right of Monthly work. Boards are 1440 wide, matching the others.

### C2. Sample data
These are the agreed figures for AISB (kept in SQL, financial year from January), with today Wed 18 Nov 2026 and the month being worked October 2026. They reconcile with:
- Bank.dc.html book side: 310-000 is 89,218.35 at 30 Sep and **33,618.35 at 31 Oct**; 310-100 is 50,000.00 to **58,011.40**.
- Sql.dc.html document numbers and amounts (KWSP PV2610-019 11,180.00 on 28 Oct; Electricity PV2611-003 1,163.20 on 4 Nov; tenant 300-T001; supplier 400-E012).
- SetupChart.dc.html accounts.

**SQL reports kept** (fetched 18/11/2026 10:42):
- `Trial Balance.xlsx`, Trial Balance 01/10/2026–31/10/2026, **From date 1 Oct**. Its openings are kept at 1 Oct.
- `GL Journal.xlsx`, GL Journal of Transaction 01/10/2026–12/11/2026.
- `GL Ledger.xlsx`, 01/10/2026–12/11/2026 (already on the Sql board).

**Chart additions** (to SetupChart):
- `510-000 Retained earnings` (RE, equity)
- `650-000 Bank profit` (OI, income)
- `900-700 Bank charges` (EP)
- `500-F001 Funds from Agrinexus International` (CP, equity, parent 500-000)

**October documents:**

| Date | Doc | Lines |
|---|---|---|
| 1 Oct | IV2610-001 Rent October | Dr 300-T001 / Cr 600-000, 2,800.00 |
| 5 Oct | OR2610-001 Rent September | Dr 310-000 / Cr 300-T001, 2,800.00 |
| 5 Oct | PV2610-021 Office rental October | Dr 900-300 / Cr 310-000, 9,500.00 |
| 12 Oct | JV2610-001 Transfer to savings | Dr 310-100 / Cr 310-000, 8,000.00 |
| 15 Oct | PV2610-022 PERKESO September | Dr 430-200 / Cr 310-000, 1,240.00 |
| 15 Oct | PV2610-023 PCB September | Dr 430-300 / Cr 310-000, 2,150.00 |
| 20 Oct | OR2610-006 Fund received | Dr 310-000 / Cr 500-F001, **45,000.00** (the Sql board must change from 50,000.00, or the Bank board's October in from 47,800 to 52,800) |
| 20 Oct | PV2610-024 Directors fee Q3 | Dr 900-200 / Cr 310-000, 30,000.00 |
| 22 Oct | PV2610-025 Telephone and internet | Dr 900-600 / Cr 310-000, 306.00 |
| 28 Oct | PV2610-019 KWSP October | Dr 430-100 / Cr 310-000, 11,180.00 |
| 30 Oct | PV2610-026 Salary advance | Dr 320-000 / Cr 310-000, 2,000.00 |
| 31 Oct | JV2610-002 Salary October | Dr 900-100 53,594.00 / Cr 420-000 39,024.00, 430-100 11,180.00, 430-200 1,240.00, 430-300 2,150.00 |
| 31 Oct | PV2610-020 Salaries October (net) | Dr 420-000 / Cr 310-000, 39,024.00 |
| 31 Oct | PI-E2610 Electricity October | Dr 900-400 / Cr 400-E012, 1,163.20 |
| 31 Oct | CB2610-050 Profit paid | Dr 310-100 / Cr 650-000, 21.40 |
| 31 Oct | CB2610-051 Service charge | Dr 900-700 / Cr 310-100, 10.00 |

**Trial balance 1 Oct–31 Oct 2026, roll-up on.** Columns: opening Dr/Cr | debit | credit | closing Dr/Cr.

| Code | Name | Opening | Debit | Credit | Closing |
|---|---|---|---|---|---|
| 200-000 | Office equipment | 18,500.00 Dr | | | 18,500.00 Dr |
| 300-000 | Trade debtors, *With 300-T001* | 2,800.00 Dr | 2,800.00 | 2,800.00 | 2,800.00 Dr |
| 310-000 | Maybank current | 89,218.35 Dr | 47,800.00 | 103,400.00 | 33,618.35 Dr |
| 310-100 | Maybank savings | 50,000.00 Dr | 8,021.40 | 10.00 | 58,011.40 Dr |
| 320-000 | Salary advances | 1,500.00 Dr | 2,000.00 | | 3,500.00 Dr |
| 350-000 | Deposits paid | 6,000.00 Dr | | | 6,000.00 Dr |
| 400-000 | Trade creditors, *With 400-E012* | blank | | 1,163.20 | 1,163.20 Cr |
| 420-000 | Accruals | blank | 39,024.00 | 39,024.00 | blank |
| 430-100 | KWSP payable | 11,180.00 Cr | 11,180.00 | 11,180.00 | 11,180.00 Cr |
| 430-200 | PERKESO payable | 1,240.00 Cr | 1,240.00 | 1,240.00 | 1,240.00 Cr |
| 430-300 | PCB payable | 2,150.00 Cr | 2,150.00 | 2,150.00 | 2,150.00 Cr |
| 500-000 | Share capital | 100,000.00 Cr | | | 100,000.00 Cr |
| 500-F001 | Funds from Agrinexus International | 1,050,000.00 Cr | | 45,000.00 | 1,095,000.00 Cr |
| 510-000 | Retained earnings | 380,682.85 Dr | | | 380,682.85 Dr |
| 600-000 | Rental income | 25,200.00 Cr | | 2,800.00 | 28,000.00 Cr |
| 650-000 | Bank profit | blank | | 21.40 | 21.40 Cr |
| 900-100 | Salaries and wages | 482,346.00 Dr | 53,594.00 | | 535,940.00 Dr |
| 900-200 | Directors fee | 60,000.00 Dr | 30,000.00 | | 90,000.00 Dr |
| 900-300 | Office rental | 85,500.00 Dr | 9,500.00 | | 95,000.00 Dr |
| 900-400 | Utilities | 10,468.80 Dr | 1,163.20 | | 11,632.00 Dr |
| 900-600 | Telephone and internet | 2,754.00 Dr | 306.00 | | 3,060.00 Dr |
| 900-700 | Bank charges | blank | 10.00 | | 10.00 Dr |
| **Total** | | **1,189,770.00 / 1,189,770.00** | **208,788.60** | **208,788.60** | **1,238,754.60 / 1,238,754.60** |

- Openings line: `Openings from SQL's trial balance at 1 October 2026 (18 accounts); not on SQL's trial balance, so nothing at 1 October 2026 (3 accounts).`
- Check: `Agrees with SQL's trial balance as at 31/10/2026: all 22 accounts compared.`
- SQL's own trial balance prints retained earnings year-to-date as 996,551.65 Dr: 380,682.85 plus the Jan–Sep loss of 615,868.80 it moved on 1 Oct. The Sql board's checks card should then say: `SQL's trial balance counts profit and loss from its From date (01/10/2026), so it moved a loss of 615,868.80 from earlier into retained earnings. No document carries that move.`

**P&L 1–31 Oct:**
- Sales: Rental income 2,800.00. Gross profit 2,800.00.
- Other income: Bank profit 21.40.
- Expenses: 53,594.00 / 30,000.00 / 9,500.00 / 1,163.20 / 306.00 / 10.00, giving `Total expenses` 94,573.20.
- `Net profit or loss before tax` (91,751.80); `Net profit or loss after tax` (91,751.80).
- Check text: `…-91,751.80, is the trial balance's profit and loss accounts' movement for 01/10/2026 to 31/10/2026.`
- `No comparative column: Nothing is kept for 01/10/2025 to 31/10/2025, …`

**P&L for this financial year to date (1 Jan–31 Oct):**
- Totals: income 28,021.40, expenses 735,642.00, net (707,620.60).
- Grey banner (an opening at 01/01/2026 is missing).
- With Months on, Jan–Sep show `—` and October shows the figures.

**Balance sheet at 31 Oct 2026:**
- Non-current assets: 18,500.00.
- Current assets:
  - 300-000 2,800.00
  - 300-900 Cash and bank 0.00, with 310-000 33,618.35 and 310-100 58,011.40, `Total Cash and bank` 91,629.75
  - 320-000 3,500.00
  - 350-000 6,000.00, with note "…no SQL group, so it is shown under Current assets…"
  - Total current assets 103,929.75
- Current liabilities:
  - 400-000 1,163.20
  - 430-000 Statutory payables 0.00, with subs 11,180.00 / 1,240.00 / 2,150.00, `Total Statutory payables` 14,570.00
  - Total current liabilities 15,733.20
- Net current assets 88,196.55. **Net assets 106,696.55.**
- Capital: 500-000 100,000.00 with sub 500-F001 1,095,000.00, `Total Share capital` 1,195,000.00.
- Retained earnings brought forward (380,682.85). Profit or loss for the year to date (707,620.60). **Total equity 106,696.55.**
- Banner: `Balances and reconciles to the trial balance`.
- Coverage note (the journal covers only from 01/10/2026). Comparative missing (31/12/2025).

**Customers, 1–31 Oct:**
- 300-000: 300-T001 Tenant; opening 2,800.00, invoiced 2,800.00, received 2,800.00, closing 2,800.00; Current 2,800.00.
- Pill `Ties to the trial balance`.

**Suppliers, 1–31 Oct:** 400-E012 Electricity supplier, invoiced 1,163.20, closing 1,163.20, Current 1,163.20.

**Default view when the page opens** (no dates): 1 Jan 2026 to 12 Nov 2026.
- Every opening shows `—` and the totals show `—`, with pill `Doesn't balance`.
- Notes: the missing-openings sentence and the coverage note.
- Grey banner: `No trial balance of SQL's as at 12/11/2026 is kept, …`.
- November lines in the ledger: IV2611-001 1 Nov Rent November 2,800.00; PV2611-003 4 Nov Electricity October 1,163.20 (Dr 400-E012 / Cr 310-000).

**AI, Agrinexus International (not in SQL):**
- The other intro note. No banner.
- `No opening balance or account line is kept for these dates yet.`
- Pill `Balances` (quirk 1).
- P&L and balance sheet show `Nothing to check`.
- Excel source line: `Books kept in this app: …`.

### C3. Boards to add
1. **Books.dc.html, "Accounting · Books · Trial balance" (AISB).**
   - Shell: company picker, `Books · AISB`, intro, From/To, `Show`, `This financial year to date`, `Excel`, six tabs.
   - States, as one board with a state switcher like the others:
     - (a) the default view on opening
     - (b) 1–31 Oct agrees: the main sample above
     - (c) differences: SQL's 310-000 33,570.35 and 900-700 58.00, from a 48.00 charge entered in SQL after the fetch. Three rows: 310-000 balance, 310-000 movements −55,648.00 against −55,600.00, and 900-700 "its lines…" 58.00 against 10.00.
     - (d) the same differences, possibly out of date (the journal re-fetched 18/11/2026 at 11:05)
     - (e) roll-up off: 300-T001 and 400-E012 on their own rows with `Sub-ledger of …`
     - (f) search `KWSP`, with `1 of 22 shown`
     - (g) `Not in chart` (500-F001 before the chart is fixed), with the untyped note
     - (h) the year-start column, a hypothetical with a SQL trial balance from 01/12/2025
     - (i) AI empty
     - (j) loading and error (`The From date is after the To date.`)
2. **BooksLedger.dc.html, "Books · General ledger".**
   - 310-000 for 1–31 Oct, rows as in C2. Running balances: 92,018.35 → 82,518.35 → 74,518.35 → 73,278.35 → 71,128.35 → 116,128.35 → 86,128.35 → 85,822.35 → 74,642.35 → 72,642.35 → 33,618.35.
   - PV2611-003 expanded inline: Version 1, lines Dr 400-E012 / Cr 310-000 1,163.20 with the `Bank` pill, and "The lines balance and agree with the listing."
   - A control account 400-000 picked, with 400-E012 following and the "together they close at 1,163.20" note.
   - Missing-opening note (default view), all-accounts view, and the empty state.
3. **BooksPL.dc.html, "Books · Profit and loss".** Oct single column (reconciles); year to date grey; Months on (Jan–Sep `—`, Oct figures, total); comparative-missing note; empty; the Not classified pill state.
4. **BooksBS.dc.html, "Books · Balance sheet".** At 31 Oct, balancing; the Not classified imbalance using 999-000 Suspense 48.00 Dr ("…hold 48.00 debit … set their types … and it will balance."); the can't-be-totalled grey state; the no-retained-earnings line state.
5. **BooksParties.dc.html, "Books · Customers and suppliers"** with the statement drill-in. This may be shared with the receivables area.
6. **BooksStatutory.dc.html, "Books · Statutory payables"**, including the Before tracking grey rows: with first month July 2026, Jan–Jun are greyed. This may be shared with the statutory area.
7. **BooksExcel.dc.html, "Books · Excel files".** Sheet previews of the trial balance and the P&L: title block rows 1-3, frozen header row 5, bracket negatives, file names as in A10.

### C4. Existing boards to change
- **Sidebar:** add group `Accounting` with item `Books` (glyph `books`) between Monthly work and Filing, and support `active="books"`.
- **Icon and Foundations:** add a `books` glyph matching the app path (glyph count 68). Add an "Accounting figures" rule to Dates and money:
  - no RM in report tables; balances `x Dr`/`x Cr`; brackets for the other way round
  - `—` unknown; blank for zero in movement columns; `0.00` for a nil balance
  - one date style for report headings, sentences and ledger rows (with the year when it isn't the current one)
- **CommandPalette:** add Books and its six tabs as destinations. **MobileDesktopOnly:** add Books.
- **SetupCompanies:**
  - Financial-year hint, changed from the app's current text: "Keep it the same as the company's setting in SQL Account: SQL's reports can't tell it. The books' trial balance check, profit and loss and balance sheet use it. Empty: January." (the app says "…The trial balance check uses it, and later reports will too…")
  - Align AISB's first month tracked with Bank (2026-07) or the reverse.
- **SetupChart:** add the four accounts in C2. Keep 350-000 and 999-000 as they are.
- **Sql** (if this area is shared):
  - Add `GL Journal.xlsx` (GL Journal of Transaction, 1 Oct to 12 Nov, "37 documents, 52 lines") and `Trial Balance.xlsx` (Trial Balance, 1 Oct to 31 Oct, "22 accounts · Checked against the account lines on import.") to READ.
  - Add the "Checks against SQL's reports" card with the `Possibly out of date` banner and the from-date move line.
  - Fix OR2610-006 to 45,000.00 and the journal paste code 900-010 to 900-700.
- **Company and AuditPack** (other owners): add the `SQL books agree with SQL Account` item and the three books pages.
- **States:** add a Books loading and error example, and an "Excel couldn't be made" state.
  - Showing the error sentence there is **new work**: today the link goes to raw JSON.
  - Mark it on an orange "New work" note, as the canvas already does.
