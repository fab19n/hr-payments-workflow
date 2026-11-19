# Area: customers and suppliers (who owes what, ageing, statements) and the "SQL books agree" checklist item

Sources (read-only): `hrp/receivables.py` (409 lines, added in 0133981), `hrp/sqlbooks.py`, `hrp/checklistbook.py`, `hrp/rules.py`, `hrp/db.py` (task_status), `hrp/monthly.py`, `hrp/nextup.py`, `hrp/booksexcel.py`, `hrp/reports.py`, `hrp/auditpack.py`, routes in `hrp/app.py`, UI in `static/app.js`. Canvas: `design/canvas`.

Main finding: the canvas has **no Books page at all**. The whole Accounting › Books page, with its "Customers and suppliers" tab, was added after b7d7fa0 (at b7d7fa0, app.js has no `"books"` view and no `data-bk-tab`). No canvas board mentions ageing, receivables, "who owes", "SQL books" or `sql-books`.

---

## A. Inventory

### A1. Where it sits
- Sidebar section **"Accounting"** with one item, **"Books"** (`static/app.js:127`, `VIEWS`). It sits between "Monthly work" and "Filing".
- Books page shell (`viewBooks`, app.js:1650-1690). This shell probably belongs to another area; it is listed here only as context.
  - Company picker, then `<h1>Books · {code}</h1>`, then an intro note.
  - **From** and **To** date fields, a **Show** button, a "This financial year to date" button, and an **Excel** link. The Excel link is hidden on a single statement.
  - Report segmented control: Trial balance | General ledger | Profit and loss | Balance sheet | **Customers and suppliers** (`data-bk-tab="parties"`, app.js:1671) | Statutory.
- State (app.js:122): `books.side` defaults to `"customers"` and `books.party` to `null`.
  - Changing the tab clears `party` (1678).
  - The side toggle sets `side` and clears `party` (1685).
  - A code button sets `party` (1686). "All customers/suppliers" clears it (1687).
- Fetching (app.js:1719-1724):
  - The list comes from `GET /api/books/parties?entity=&from=&to=&side=` (app.py:2126, `receivables.balances`).
  - A statement comes from `GET /api/books/party?entity=&from=&to=&code=` (app.py:2140, `receivables.statement`).
  - The server writes `from` and `to` back into the date fields.
- Loading shows "Loading…". An error replaces the body with `<div class="note warn-text">{message}</div>`.
- Period rules (`_books_period`, app.py:2034):
  - With no To date, To is the last day SQL's reports kept reach (`books.default_to`), never after today. A company kept here uses today.
  - With no From date, From is the financial year start (Setup › Companies `fy_start`, January when it is not set).
  - Error messages:
    - "The from date isn't a date (use YYYY-MM-DD)." (also "The to date…")
    - "The from date is out of range: use a date from {Y0} to {Y1}."
    - "The From date is after the To date."

### A2. Customers and suppliers list (`partiesHtml`, app.js:1906-1937; server `receivables.balances`, receivables.py:282-366)

**Header row:** `<h2>{Customers|Suppliers}, {1 Oct 2026} to {31 Oct 2026}</h2>` (fmtDate gives "31 Oct 2026"), with a segmented control `aria-label="Customers or suppliers"` holding the buttons "Customers" and "Suppliers".

**Who is listed (rules):**
- Every code under a debtor or creditor control account. The side of a control account is decided in this order (`_side_of`, receivables.py:62):
  1. Chart special `debtor_control` means customers; `creditor_control` means suppliers.
  2. Otherwise, the kinds of Setup parties using it: only customers means customers, only suppliers means suppliers. Only related or statutory parties means *not listed*, so a KWSP code under 430-100 is never a "supplier".
  3. Otherwise, the chart type: asset means customers, liability means suppliers.
  4. Otherwise, the name contains DEBTOR/RECEIVABLE or CREDITOR/PAYABLE.
- A row is kept only if any of its figures is non-zero or its opening or closing is unknown.
- The control account's own balance comes first, as its own row.

**Banner** (`fsBanner`, app.js:1860):

| `d.ties` | Class | Title |
|---|---|---|
| `true` | `ok` | "Ties to the control accounts" |
| `false` | `warn` | "Doesn't tie to the control accounts" |
| `null` | `grey` | "Not fully checked" |

Banner body is `d.text` (receivables.py:352-360):
- "Every control account ties: the customers listed add up to their control accounts in the trial balance."
- "Not every control account ties to the trial balance: {control texts}"
- "Not every control account can be checked: {control texts}"

**Two notes under the banner** (app.js:1933-1934):
- "Each amount is what is owed: what the customer owes the company; a figure in brackets is the other way round. Invoiced is what the sales book added, received what the bank book took off, other everything else (credit notes, journals). The ageing is at 31 Oct 2026."
  - Suppliers variant: "what the company owes the supplier", "purchase book", "paid".
- FIFO_NOTE (receivables.py:41): "SQL's exports don't say which receipt or payment settled which invoice, so each receipt, payment, credit note or journal is taken to settle the oldest invoice still open first. SQL's exports carry no due dates either, so invoices are aged by their own date: current is within 30 days of it. An opening balance with no invoices kept behind it is aged as brought forward."

**One card per control account** (`card-in`):
- Heading `<h3>`: a code button (`data-bk-acct`, title "Open the ledger of {code}", opens the General ledger tab) followed by the name.
- Pill on the right:

| `ties` | Pill |
|---|---|
| `true` | `ok` "Ties to the trial balance" |
| `false` | `bad` "Doesn't tie" |
| `null` | `grey` "Can't be checked" |

- Table `table.fs.ar`. Columns:
  - Code, Name, Opening, Invoiced, {Received|Paid}, Other, Closing.
  - Then the ageing columns: Current, 31-60 days, 61-90 days, Over 90 days.
  - **Brought forward** appears only when some control account's brought-forward total is non-zero (app.js:1916-1917). Ageing columns have class `ar-age` (background `--bg`, app.css:372).
- **Row cells:**
  - Code: a button `linkish mono`, `data-bk-party`, title "Open the statement of {code}".
  - Name, for the control account's own row: muted "Held on the control account itself, not split by customer" (or "supplier") (receivables.py:312).
  - Name, for any other row: the name, plus a warn pill **"Not in Setup"** when the name did not come from Setup. Its title is "Not in Setup › Customers and suppliers: named from the chart of accounts" / "named as SQL printed it" / "named by nobody yet".
  - Row notes appear under the name as `.note`.
  - Opening: `fsAmt`. Negative shows as "(300.00)"; unknown shows as "—".
  - Invoiced: `rmCell`, blank when 0.
  - Received/Paid and Other: blank when 0, otherwise `fsAmt`.
  - Closing: **bold** `fsAmt`.
  - Ageing cells: `rmCell`, blank when 0.
  - A row in credit shows one spanned cell instead of the ageing cells: grey pill "In credit" plus muted "paid in advance or overpaid".
  - A row with no ageing shows a spanned muted "—".
- **Total row** (`fs-sub`): "Total".
  - Opening, Other and Closing use `fsAmt`. Invoiced and the ageing totals use `rmPlain`, so a zero total shows "0.00", where row cells leave zeros blank.
  - Rows in credit are left out of the ageing totals.
- **Trial balance row** (`fs-line`): "{code} in the trial balance".
  - TB opening, then "Moved {x}" spanning three columns, then TB closing.
  - In the ageing span: muted "In credit: {x}" when any row is in credit.
- Under the table, a note with the control account's text (receivables.py:328-348):
  - Ties: "{ctl} {name}: the customers add up to the control account in the trial balance, {opening} at the start and {closing} at the end."
  - Doesn't tie: "{ctl} {name}: the customers don't add up to the control account in the trial balance: the opening here is X, the trial balance's Y (a difference of Z); the period's movement here is …; the closing here is …." It then adds one of:
    - " A later opening kept for {codes} doesn't follow from the earlier one and the lines."
    - " The trial balance adds a code into the control account that isn't listed here; see the Trial balance tab with customers and suppliers added in."
  - Can't check: "{ctl} {name}: can't be checked against the trial balance, as no opening balance is kept for {codes}."
- Amounts from `_money` have no "RM" and use "1,234.56"; negatives look like "-200.00".

**Notes at the bottom** (`d.notes`):
- "Not in Setup › Customers and suppliers, so named from the chart or the name SQL printed: {codes}." (receivables.py:363)
- Coverage note (books.py:452): "The GL Journal of Transaction reads kept cover {spans}, not all of {period}: lines dated outside them are missing here. Fetch the journal for the whole period."

**Row notes** (receivables.py:259-265):
- "No opening balance of {code} is kept: fetch SQL's trial balance (with a From date) or its GL ledger for the start of the period, or a period after one." (books.py:297)
- "A later opening kept for {code} says {x} at {dd/mm/yyyy}, but the opening and the lines come to {y}."

**Empty state** (app.js:1913-1915): the toggle, then a grey banner "Nothing listed" with text "No customer balance is kept for these dates." Below that, a note repeats "No customer balance is kept for these dates." and, for a company kept in SQL only, adds " Fetch SQL's GL Journal of Transaction and trial balance on the SQL import page." The banner and the note say the same sentence twice; the redesign should drop one.

**Figure rules:**
- Invoiced means sales or purchase book lines that add to what is owed.
- Received/paid means bank book lines, with a refund counting the other way.
- Other means everything else (credit notes, journals, contra), signed.
- Closing = opening + invoiced − received + other.
- Ageing at the To date, first in first out, by invoice date: current is up to 30 days, then 31-60, 61-90, and over 90. Brought forward means an opening with no invoices kept behind it, or a later opening's unexplained increase.
- A balance the other way round is "in credit" and is not aged.

### A3. One customer's or supplier's statement (`partyHtml`, app.js:1939-1960; `receivables.statement`, receivables.py:369-409)

- **Header:** `<h2>` with the mono code, the name, and a warn pill "Not in Setup" (no title here, unlike the list) unless the name came from Setup or the code is the control account itself. Button "All customers" or "All suppliers" (`data-bk-party-back`).
- **Note:** "Customer under {control button} {control name}. Owed by them at 31 Oct 2026: {owed}."
  - Supplier variant: "Supplier under …", "Owed to them".
  - `owed` is one of: "unknown", "{x} in credit (paid in advance or overpaid)", "nothing", or the amount.
- **Ledger table** `books-ledger`, columns Date, Doc No, Book, Description, Debit, Credit, Balance:
  - First row (`books-open`): "{1 Oct}" | Opening balance | `drCr`, for example "5,700.00 Dr".
  - Each line row:
    - Doc No: a button for SQL documents (`data-bk-doc`, title "Show the lines of {no}"); it toggles an inline `sql-lines-row` showing the document's account lines (`booksDoc`, 2025). Other documents show plain mono text.
    - Book: one of Bank, General, Sales, Purchase, Other.
    - Debit and Credit: blank when 0.
    - Balance: running, in Dr/Cr.
  - Last row: "Closing balance".
- **Section `<h3>Still open at 31 Oct 2026</h3>`:**
  - A row of grey pills, "Current: 4,500.00", "31-60 days: …", "61-90 days: …", "Over 90 days: …". "Brought forward: …" appears only when it is non-zero. No pills when in credit.
  - Then one of:
    - In credit: "In credit, so nothing is aged."
    - Items open: a table with Date, Doc No, Description, Invoice, Still open, Days, Age. Brought-forward items read "Brought forward at 01/01/2026, with no invoices kept behind it" or "Brought forward at {d}: the opening kept then is {x} more than the earlier opening and the lines since, with no invoices kept behind it".
    - Nothing open: "Nothing is open."
- **Notes:** the FIFO note, then:
  - "{B.why} The running balance starts from 0."
  - "A later opening kept for {code} says {x} after {dd/mm/yyyy}, but the opening and the lines come to {y}."
  - On the control account itself: "What 300-000 holds itself: an opening SQL printed for it that isn't split by customer, and anything posted to it directly."
- **Errors:** "Give the code of a customer or supplier." / "{code} isn't a customer's or supplier's code under a debtor or creditor control account."
- The Excel link is hidden on a statement (app.js:1757).

### A4. Excel export (app.py:2655-2697 `/api/export/books/customers-and-suppliers.xlsx?entity_id=&from=&to=&side=`; `booksexcel.parties`, booksexcel.py:239-279)
- `@audited_read("books export")` means the download writes an "opened" event into the audit trail.
- File name, for example **"AISB Customers to 31-10-2026.xlsx"**. With both sides: "… Customers and suppliers to …".
- Sheet title is "Customers".
- Rows 1-3:
  - Row 1: "{company name} ({code})", bold 13pt.
  - Row 2: "Customers, 01/10/2026 to 31/10/2026 (ageing at 31/10/2026)".
  - Row 3: "Mirrored from SQL Account, read dd/mm/yyyy. Exported dd/mm/yyyy HH:MM." Other source lines: "Books kept in this app: this company's books are not kept in SQL Account." / "Mirrored from SQL Account: nothing has been read from SQL yet."
- Header: Code, Name, Opening, Invoiced, Received (or Paid / "Received or paid"), Other, Closing, Current, 31-60 days, 61-90 days, Over 90 days, Brought forward, Note. All five ageing columns always appear here, unlike the screen.
- For each control account:
  - A bold row "{code}" | "{name} (customers)".
  - The rows. The Note column holds "In credit (paid in advance or overpaid)" and the row notes.
  - A bold Total row, with "In credit: x" in Note.
  - A row "{code} | In the trial balance | opening | … | closing" with Note "Moved {x} in the period".
  - Then the control account's text.
- Then the overall text, and the notes "Each amount is what is owed; a figure in brackets is the other way round.", the FIFO note, and `d.notes`.
- The auditor package includes the month's version for both sides (`reports.books_workbooks`, reports.py:336-356).

### A5. The checklist item "SQL books agree with SQL Account" (code `sql-books`, update 30)

**Definition:**
- `rules.TASK_BOOKS = "sql-books"` (rules.py:210).
- Completion key `"books"`, labelled "SQL books agree with SQL Account (from SQL's journal and trial balance)" (checklistbook.py:31).
- First term (`books_term`, checklistbook.py:506):
  - Title **"SQL books agree with SQL Account"**.
  - Detail = `rules.BOOKS_DETAIL` (rules.py:84): "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least the month's last day. Done when every document of the month is in the journal and in SQL's listings, each one balances and agrees with its listing, and SQL's trial balance agrees with the books here."
  - **Due the 15th of the next month** (due_offset 1, due_day 15).
  - No documents, no deadline, not "submitted as".

**Who gets it** (`add_sql_books` / `install_sql_books`, checklistbook.py:550-586):
- Only companies kept in SQL that already have a checklist. In the canvas that is AISB only; AI never gets it.
- It starts from the month after the latest filed month (never before the first month tracked) and goes at the end of the checklist.
- The months already set up from then on get it.
- Activity log lines: "Checklist AISB: added SQL books agree with SQL Account, from October 2026" plus "Checklist AISB in …".

**How it is shown done** (`sqlbooks.month_check`, sqlbooks.py:62-133, called by `db.task_status`, db.py:1317):
- It is worked out live, never stored. The first failing check gives the sentence.
- Exact texts, where `{label}` is "October 2026", `{upto}` is "31 Oct 2026" and `{first}` is "1 Oct":
  1. Nothing fetched: "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least 31 Oct 2026."
  2. The journal does not cover the month: "Fetch SQL's GL Journal of Transaction for the whole of October 2026 (from 1 Oct to 31 Oct 2026): no journal fetched covers the whole month."
  3. Listing entries missing from the journal: "{n} document(s) of October 2026 in SQL's listings is/are missing from SQL's GL Journal of Transaction (A, B, C and N more): fetch the journal for October 2026 again, or check it/them in SQL."
  4. A journal document has no listing: "{n} document(s) of October 2026 in SQL's GL Journal of Transaction has/have no listing (…): fetch SQL's listing for October 2026 on the SQL import page."
  5. A document is unbalanced or disagrees with its listing: "{doc} doesn't balance or agree with its listing ({n} more documents of October 2026 too): {warning} Open it on the SQL page or Accounting › Books to see its lines."
  6. No trial balance: "Fetch SQL's Trial Balance up to at least 31 Oct 2026."
  7. The trial balance is later than the journals: "The nearest trial balance of SQL's kept is as at {d}, but the journals fetched stop before then: fetch SQL's Trial Balance as at 31 Oct 2026, or its GL Journal of Transaction up to {d}."
  8. The trial balance differs: "{n} accounts differ from SQL's trial balance as at 31/10/2026; {k} agree. … See Accounting › Books › Trial balance, then fetch again what differs." This may include "SQL's trial balance was read …" and the stale sentence "The journal was read after the trial balance, so these differences may be out of date…".
  9. Done: "Done: SQL's journal covers October 2026, its documents agree with the listings and SQL's trial balance as at 31 Oct 2026 agrees with the books here". It has no final full stop. It may add " (2 documents in sections with no listing this app reads were checked by their account lines and SQL's trial balance)".
- A company not kept in SQL that still has the item: "This company's books aren't kept in SQL Account, so nothing here can show this done: tick it by hand."
- A month before tracking: nothing is shown.

**On the month page** (app.js:540-547):
- Note `t.why`, class `ok` when auto. When ticked by hand and not done, the class is `warn` and the note is prefixed "Ticked by hand. ".
- The checkbox is disabled while auto-done, with title = why.
- The pill is the flag ("Overdue", "Due today") or "Done".
- Ticking by hand while not done asks `confirm("{why}.\n\nTick anyway?")` (app.js:4436). **Small bug:** sqlbooks sentences already end in ".", so the dialog shows "…31 Oct 2026..". The redesign's confirm should not add a second full stop.

**Next up** (nextup.py:436-450, rule 10):
- One row: "Oct AISB: SQL books agree with SQL Account", or "Finish 2 Oct AISB checklist items: …".
- It opens the month page on the item.
- It is not a deadline row (monthly.py:257 forces deadline 0 for "books").

**Setup › Monthly checklist:**
- The "Done when" option is offered only for a company kept in SQL that does not already have the item (app.js:3519-3521).
- There is no Deadline checkbox (`NO_DEADLINE`, app.js:3426).
- Once added, the option is locked: "Fixed once the item is added."
- Server refusal: "AI's books aren't kept in SQL Account, so SQL's books can't show this item done." (monthly.py:432)

**Audit pack** (auditpack.py:567-655), for the audit-pack owner:
- A page "{head} - SQL books check". It shows "Done." / "Not done." / "Not checked here.", then the why without "Done: ", then the fixed paragraph "Whether SQL Account's books for the month agree with the mirror kept here: … SQL Account stays the books; nothing here changes them."
- The pages "Statutory payables check" and "Trial balance against SQL" follow it.

---

## B. Canvas coverage today

| Need | Board today | Missing or wrong |
|---|---|---|
| Accounting › Books › Customers and suppliers (list, toggle, ties, ageing, in credit, Not in Setup, TB row, notes, empty, error) | **None** | Everything. No Books board exists. |
| Statement of one customer or supplier, open items aged | **None** | Everything. |
| Sidebar "Accounting › Books" | Sidebar.dc.html:130-136 has Dashboard / Companies / Monthly work / Filing / Setup | The **Accounting** group with **Books** is missing. It goes between Monthly work and Filing. |
| SQL books item on the month checklist | Company.dc.html AISB October tasks (737-749) and September (766-770). Same in DarkCompany and MobileCompany (311-317, 325-326). | No `sql-books` item. Checklist counts and tiles are therefore one short for AISB. AI correctly has none. |
| "Done when: SQL books agree…" | SetupChecklist.dc.html:259 select and :485 `COMPL` | The `books` option is missing. The AISB item list has no "SQL books agree with SQL Account" row. The not-offered-for-AI rule and the refusal are not shown. |
| Next up row | Main.dc.html:418-426, Company next-up (803-809) | No SQL books row. This is optional but now real. |
| Audit pack books pages | AuditPack.dc.html | No books check pages (for the audit-pack area). |
| Excel export | None | The Customers xlsx (and the auditor package's both-sides xlsx) is not shown anywhere. |
| Chart, control accounts | SetupChart.dc.html: 300-000 Trade debtors `debtor_control`, 400-000 Trade creditors `creditor_control` | Fine. These are the control accounts to use. |
| Parties | SetupParties.dc.html: 300-T001 Tenant (customer, GL 300-000); 400-E012 Electricity supplier, 400-R001 Office landlord, 400-P004 Payroll advisor, 400-C002 Old courier (stopped), 400-A001 Agrinexus International (related), 400-K001 KWSP (statutory, 430-100) | No other customers. It needs the extra sample customers below. |

The existing samples are inconsistent with each other, so note this before building:
- Company board: Tenant 300-T001, IV-2610-031, 31 Oct, 2,800, paid by OR 2610-07 on 3 Nov, e-Invoice cancelled by CN-2611-002.
- Sql board: "Office rental October, Unit 3A", IV2610-014, 1 Oct, 1,800; OR2611-002 on 5 Nov with "Code 500-R001".
- The document-number formats differ (`IV-2610-031` / `OR 2610-07` against `IV2610-014` / `OR2610-006`). I kept both as they are and used the SQL style (no dash or space) for new numbers.

---

## C. Proposal

### C1. New board: `BooksParties.dc.html`, "Books · Customers and suppliers" (1440 wide)
It reuses the Books shell: title "Books · AISB", the period bar with From 1 Oct 2026 and To 31 Oct 2026, Show, "This financial year to date", Excel, and the six report tabs with **Customers and suppliers** selected. If another area adds a Books shell board, take the header from it. Use a state enum like the other boards.

**State 1, "customers" (default): AISB, Customers, 1 Oct 2026 to 31 Oct 2026. Ties.**
- Banner `ok` "Ties to the control accounts", with "Every control account ties: the customers listed add up to their control accounts in the trial balance."
- Card **300-000 Trade debtors**, pill "Ties to the trial balance":

| Code | Name | Opening | Invoiced | Received | Other | Closing | Current | 31-60 | 61-90 | Over 90 | Brought fwd |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 300-000 | *Held on the control account itself, not split by customer* | 350.00 | | | | **350.00** | | | | | 350.00 |
| 300-A001 | AGRINEXUS INTERNATIONAL [Not in Setup: "named as SQL printed it"] | 5,700.00 | 4,500.00 | 1,200.00 | | **9,000.00** | 4,500.00 | 4,500.00 | | | |
| 300-G001 | Greenfield Agro Sdn Bhd | 2,000.00 | | | (500.00) | **1,500.00** | | | | 1,500.00 | |
| 300-P002 | Pantai Kitchen Sdn Bhd | 0.00 | 1,200.00 | 1,500.00 | | **(300.00)** | spanned: [In credit] *paid in advance or overpaid* |
| 300-T001 | Tenant (Block A) | 2,800.00 | 2,800.00 | 2,800.00 | | **2,800.00** | 2,800.00 | | | | |
| 300-U001 | Office tenant (Unit 3A) | 0.00 | 1,800.00 | | | **1,800.00** | 1,800.00 | | | | |
| **Total** | | 10,850.00 | 10,300.00 | 5,500.00 | (500.00) | 15,150.00 | 9,100.00 | 4,500.00 | 0.00 | 1,500.00 | 350.00 |
| 300-000 in the trial balance | | 10,850.00 | Moved 4,300.00 (spans 3) | | | 15,150.00 | *In credit: 300.00* (spans the ageing columns) |

- Note under the table: "300-000 Trade debtors: the customers add up to the control account in the trial balance, 10,850.00 at the start and 15,150.00 at the end."
- Bottom note: "Not in Setup › Customers and suppliers, so named from the chart or the name SQL printed: 300-A001."
- Arithmetic check: 10,850 + 10,300 − 5,500 − 500 = 15,150. The ageing totals, 15,450, equal the closing plus the 300 in credit.
- The documents behind it:
  - 300-A001: IV2609-015 (3 Sep, 4,500, cancelled by the existing CN2609-002), IV2609-028 (25 Sep, 1,200), IV2609-022 (30 Sep, 4,500), OR2610-008 (15 Oct, 1,200), IV2610-033 (31 Oct, 4,500).
  - 300-T001: OR2610-003 (5 Oct, 2,800, September rent) and the existing IV-2610-031 (31 Oct, 2,800).
  - 300-U001: the existing IV2610-014 (1 Oct, 1,800). OR2611-002 on 5 Nov falls after the To date.
  - 300-G001: IV2606-011 (15 Jun, 3,000, part-paid 1,000 in August) and CN2610-003 (20 Oct, 500).
  - 300-P002: IV2610-020 (12 Oct, 1,200) and OR2610-010 (14 Oct, 1,500).

**State 2, "suppliers": the toggle on Suppliers. Doesn't tie.**
- Banner `warn` "Doesn't tie to the control accounts", with "Not every control account ties to the trial balance: 400-000 Trade creditors: the suppliers don't add up to the control account in the trial balance: the period's movement here is 1,252.60, the trial balance's 1,452.60 (a difference of -200.00); the closing here is 4,750.00, the trial balance's 4,950.00 (a difference of -200.00). The trial balance adds a code into the control account that isn't listed here; see the Trial balance tab with customers and suppliers added in."
- Card **400-000 Trade creditors**, pill "Doesn't tie". Columns: Code, Name, Opening, Invoiced, Paid, Other, Closing, plus the four ageing columns (no Brought forward column):

| Code | Name | Opening | Invoiced | Paid | Other | Closing | Current | 31-60 | 61-90 | Over 90 |
|---|---|---|---|---|---|---|---|---|---|---|
| 400-E012 | Electricity supplier | 1,097.40 | 1,150.00 | 1,097.40 | | 1,150.00 | 1,150.00 | | | |
| 400-P004 | Payroll advisor | 2,400.00 | 1,200.00 | | | 3,600.00 | 1,200.00 | 1,200.00 | 1,200.00 | |
| 400-R001 | Office landlord | 0.00 | 6,500.00 | 6,500.00 | | 0.00 | | | | |
| **Total** | | 3,497.40 | 8,850.00 | 7,597.40 | 0.00 | 4,750.00 | 2,350.00 | 1,200.00 | 1,200.00 | 0.00 |
| 400-000 in the trial balance | | 3,497.40 | Moved 1,452.60 | | | 4,950.00 | |

- The documents behind it reuse the canvas: PV2610-002 (4 Oct, 1,097.40, September TNB bill) and PV2610-021 (30 Oct, 6,500, rent). New: PI2609-024 (25 Sep), PI2610-001 (1 Oct), PI2610-018 (26 Oct, 1,150), Payroll advisor PI2608-030 (31 Aug), PI2609-031 (30 Sep), PI2610-035 (30 Oct).
- KWSP 400-K001 is correctly absent (statutory, under 430-100).

**State 3, "statement": click 300-A001.**
- `<h2>` "300-A001 AGRINEXUS INTERNATIONAL [Not in Setup]", with the button "All customers".
- Note: "Customer under **300-000** Trade debtors. Owed by them at 31 Oct 2026: 9,000.00."
- Ledger:

| Date | Doc No | Book | Description | Debit | Credit | Balance |
|---|---|---|---|---|---|---|
| 1 Oct | | | Opening balance | | | 5,700.00 Dr |
| 15 Oct | OR2610-008 | Bank | Recharge received | | 1,200.00 | 4,500.00 Dr |
| 31 Oct | IV2610-033 | Sales | Management fee October | 4,500.00 | | 9,000.00 Dr |
| 31 Oct | | | Closing balance | | | 9,000.00 Dr |

- One doc row is expanded inline to show its account lines: Dr 300-A001 4,500.00 / Cr 500-xxx Management fee income 4,500.00.
- "Still open at 31 Oct 2026" with the pills Current 4,500.00, 31-60 days 4,500.00, 61-90 days 0.00, Over 90 days 0.00.
- Open items:
  - 30 Sep, IV2609-022, Management fee September, 4,500.00, 4,500.00, 31, "31-60 days".
  - 31 Oct, IV2610-033, Management fee October, 4,500.00, 4,500.00, 0, "Current".
- The FIFO note last.

**State 4, "in-credit statement": 300-P002.**
- "Owed by them at 31 Oct 2026: 300.00 in credit (paid in advance or overpaid)."
- No pills, and "In credit, so nothing is aged."

**State 5, "control-account statement": 300-000 itself.**
- No "Not in Setup" pill.
- Note: "What 300-000 holds itself: an opening SQL printed for it that isn't split by customer, and anything posted to it directly."
- One open item: "Brought forward at 01/01/2026, with no invoices kept behind it", 350.00, Days 304, Age "Brought forward".

**State 6, "can't check":** the customers state with 300-U001's opening shown as "—".
- The row note "No opening balance of 300-U001 is kept: fetch SQL's trial balance (with a From date) or its GL ledger for the start of the period, or a period after one."
- The ageing span shows "—". The card pill is grey "Can't be checked".
- Banner grey "Not fully checked": "Not every control account can be checked: 300-000 Trade debtors: can't be checked against the trial balance, as no opening balance is kept for 300-U001."
- Add the coverage note: "The GL Journal of Transaction reads kept cover 1 Jan 2026 to 30 Sep 2026, not all of 1 Oct 2026 to 31 Oct 2026: …". Check `books._dates`' exact format before drawing it.

**State 7, "AI empty":** Books · AI (books kept here, nothing entered).
- Banner grey "Nothing listed", "No customer balance is kept for these dates."
- No SQL hint. Show one sentence, not the current duplicate.

**State 8, "error":** "The From date is after the To date." Also an invalid code: "300-Z999 isn't a customer's or supplier's code under a debtor or creditor control account."

**Excel inset:** a small preview of "AISB Customers to 31-10-2026.xlsx", for example as a tooltip on the Excel link or a side card.
- The title rows "AISB Sdn Bhd (AISB)" / "Customers, 01/10/2026 to 31/10/2026 (ageing at 31/10/2026)" / "Mirrored from SQL Account, read 14/11/2026. Exported 18/11/2026 09:30."
- The 13 columns, including all five ageing columns.
- Note that the download is recorded in the audit trail ("books export").
- The Excel link is hidden in states 3-5.

### C2. Changes to existing boards
1. **Sidebar.dc.html:** add the group `{ label: 'Accounting', items: [item('books', 'Books', <ledger/book glyph>)] }` between "Monthly work" and "Filing", and link it to the new board(s). Mirror the change wherever the sidebar is copied: Dark boards, CommandPalette, and the Topbar breadcrumbs if they list sections.
2. **Company.dc.html, DarkCompany.dc.html (AISB only):**
   - October tasks: add before 'pack' `{ k: 'books', title: 'SQL books agree with SQL Account', detail: <BOOKS_DETAIL>, due: '2026-11-15', auto: true (box locked while records decide), bad: true, why: "Fetch SQL's Trial Balance up to at least 31 Oct 2026.", lacking: same, noOther?: false }`.
     - It shows the "Overdue 15 Nov" flag and has no document chips.
     - Ticking by hand opens the confirm "Fetch SQL's Trial Balance up to at least 31 Oct 2026.\n\nTick anyway?" with a single full stop. After that the note reads "Ticked by hand. Fetch SQL's …" in warn.
   - September tasks: add `{ k: 'books', …, due: '2026-10-15', auto: true, done0: true, why: "Done: SQL's journal covers September 2026, its documents agree with the listings and SQL's trial balance as at 30 Sep 2026 agrees with the books here" }`. The box stays checked and disabled, with the Done pill.
   - Raise AISB's "Checklist done" totals by one.
   - Optional next-up row `{ g: 'checklist', tone: 'bad', text: 'Oct AISB: SQL books agree with SQL Account', meta: 'Checklist · October', due: '2026-11-15', verb: 'Show item', task: 'books' }`.
   - AI's checklists stay unchanged (AI is not kept in SQL).
3. **MobileCompany.dc.html:** AISB October chk gets `{ k: 'h', title: 'SQL books agree with SQL Account', locked: true, due: ['Overdue 15 Nov','bad'], detail: "Fetch SQL's Trial Balance up to at least 31 Oct 2026." }`. It renders as "Waits for records". September gets it locked and done ("From records").
4. **SetupChecklist.dc.html:**
   - Add `books: "SQL books agree with SQL Account (from SQL's journal and trial balance)"` to `COMPL` and to the "Done when" select. Hide the option for AI and once AISB has the item.
   - Add the AISB item `SQLBOOKS: { title: 'SQL books agree with SQL Account', detail: BOOKS_DETAIL, off: 1, day: 15, docs: [], done: 'books' }`. It has no Deadline option, and its "Done when" is locked with "Fixed once the item is added."
   - Add a states-only refusal toast: "AI's books aren't kept in SQL Account, so SQL's books can't show this item done."
5. **Main.dc.html / DarkOverview / MobileOverview (optional):** add a Next up row `{ co: 'aisb', area: 'company', over: true, tone: 'bad', glyph: 'checklist', title: 'Oct AISB: SQL books agree with SQL Account', meta: 'AISB · Checklist', due: 'Overdue 15 Nov', exact: 'Due Sunday 15 November 2026', href: 'Company.dc.html', verb: 'Show item' }`.
6. **SetupParties.dc.html:** add the AISB customers with control 300-000: 300-U001 "Office tenant (Unit 3A)", 300-G001 "Greenfield Agro Sdn Bhd", 300-P002 "Pantai Kitchen Sdn Bhd". Leave 300-A001 out on purpose so the "Not in Setup" state stays true.
7. **AuditPack.dc.html (hand to the audit-pack area):**
   - The index row "SQL books agree with SQL Account — Not done".
   - The page "AISB … - SQL books check": "Not done." / "Fetch SQL's Trial Balance up to at least 31 Oct 2026." / the fixed paragraph.
   - The auditor package's file list includes "AISB Customers and suppliers to 31-10-2026.xlsx".
8. **CommandPalette.dc.html (optional):** results for "Books › Customers and suppliers" and "Statement · 300-A001 AGRINEXUS INTERNATIONAL".
9. **Consistency fix to decide before building:** use one document-number format across boards (SQL style `IV2610-031`, `OR2610-007`), and give the Unit 3A receipt a 300-code, not "Code 500-R001".
