# Gap check: what the six maps missed (read-only; baseline b7d7fa0, HEAD b698dc1)

Method: git log --stat, then a whitespace-ignoring diff of static/app.js plus hrp/masters.py, audit.py, auditread.py, restore.py, rules.py, monthly.py, config.py and the new routes in hrp/app.py. Canvas folder is `design/canvas`. Line numbers are static/app.js at HEAD.

The six maps appear to cover almost all of the app.js diff. The gaps below are mostly server-defined strings and cross-cutting items that never show up as h2/h3/toast in app.js.

## 1. Removed or replaced since b7d7fa0 that the canvas still shows

All of these are stale on Sql.dc.html, Bank.dc.html and DarkBank.dc.html.

1. Sql.dc.html card **"Journals and customer invoices"**. HEAD renames it **"Journals and invoices"** (app.js 1617).
2. Sql.dc.html: the instruction note "Paste each SQL listing for the month in turn: Cash Book, Receipt Voucher, Payment Voucher, Journal and Customer Invoice…" is gone. The page now leads with:
   - **"Fetch exported listings (one click)"** (1599) with a `<details>` folder row (input `#sqlDir`, button "Save folder", see 1603).
   - The primary button **"Fetch from SQL exports"** (1604), which changes to "Reading the folder…" while it runs (4291).
   - "Copy and paste" (1606) is now the secondary route.
3. Sql.dc.html: the e-Invoices card note now adds "Where a copy of SQL's MyInvois Transaction screen was read, what MyInvois says is shown beside it." (1628).
4. Sql.dc.html: "Imported files" rows (1635) now append "· N lines". The old "Imported N entries; N linked" toast gained the ". Kept the account lines…", ". Kept N MyInvois e-Invoice(s)…" and "Changed in SQL, listed once at the new figure…" tails (4276).
5. Bank.dc.html and DarkBank.dc.html: the note "Paste only the bank's cash book listing for reconciliation: a voucher paid from petty cash or a card would count as a bank movement." is replaced (1089) by **"For the reconciliation, fetch only the bank's cash book listing: …"**.
6. Bank review notes now say "…on the SQL import page." or "Fetch SQL's GL Journal of Transaction…" (1079, 1085). The old "paste the cash book listing for that month" wording is gone.
7. The Overview pill **"Month not set up"** now shows only when not before the first month tracked (485). Before the first month tracked, the whole row is replaced by **"Before tracking"** (a grey pill, `BEFORE_PILL`, 349) plus only the pills that still apply (the `kept` list, 466-483). The canvas shows "Before the first month tracked" on MobileOverview.dc.html only. HEAD's string is "Before tracking", used on the Overview row, the company month h1, the Budget h1 and the "isn't set up yet" h2 (350, 573, 771, 855).
8. The Next up and Overview filing rule changed: `NO_DEADLINE` now includes `"books"` (3426), and the Setup checklist offers the "SQL books agree" completion only when the company is kept in SQL (3521).
9. The payment-removed and unlink toasts now route to "Before tracking" or "SQL entries not linked" (4231-4232, 4350-4355). The old toast "Payment removed; X back under SQL entries not linked" is stale on the canvas.

## 2. Added since b7d7fa0 that no map heading covers

### 2a. Setup > Companies form: new fields (hrp/masters.py, server-defined, so no app.js line)

Canvas SetupCompanies.dc.html has only "Financial year starts" and "First month tracked". None of the others are there.

| Field | Hint (exact) |
|---|---|
| Financial year starts in (select, January to December) | "Keep it the same as the company's setting in SQL Account: SQL's reports can't tell it. The trial balance check uses it, and later reports will too. Empty: January." (masters.py:68) |
| Registration no. | hint "As printed on invoices, e.g. 202401012345." |
| Old registration no. | "Printed in brackets after the registration no., e.g. 1234567-X. Empty: none." |
| Address (textarea) | "Printed in the invoice header, as one line. Several lines are joined with commas." |
| Phone, Email | "Printed in the invoice header." |
| Website | "Printed in the invoice header, e.g. www.example.com." |
| Bank account on invoices (select from this company's bank accounts) | "Printed under All payments to be made to. Its bank, account number, bank address and transfer code come from Setup › Bank accounts." |
| Under the signature | "Empty: For and the company's name, as SQL Account prints it." |

Refusals:
- On a new company: "Bank account on invoices: add the company first, then its bank accounts, then choose one."
- "Bank account on invoices: choose one of this company's bank accounts."
- "Bank account on invoices: that account is stopped. Choose one in use, or use it again first."

Two more sections appear on an existing company's page (2863-2869):
- **"Printed invoices"** (2918) with Upload and Remove buttons for the logo and signature image (2916-2917, accepts .png/.jpg; toasts "Choose an image first." and "<name> uploaded" or "<name> taken off the invoices", 2933-2937).
- **"Printed company names"** (2881): table of confirmed names with Remove buttons, a click-again confirm on Remove (2894-2903), and the toast "\"X\" removed. Files printing it are held again on the next Fetch, until Take it for is clicked again." Its columns are the name, `when()` formatted dd/mm/yyyy "at hh:mm", and "Not recorded" in the confirmed-by cell (2886).

The einvoice and pack-setup maps may cover these two; I list them because the field list and the confirm pattern appear nowhere on the canvas.

### 2b. Setup > Bank accounts: two new fields

Neither is on the canvas.
- **Bank address**: "Printed on invoices when this account is the one to pay into."
- **Bank transfer (SWIFT) code**: "Printed on invoices, e.g. EXMBMYKL." (max 11 characters).

### 2c. Setup > Customers and suppliers: seven new fields

Not on the canvas (grep for "Address line 1", "Attention" and "Terms" found nothing in the boards).
- Address line 1 to 4: "Printed on its invoices. Filled from SQL's list when pasted with Address1 to Address4."
- Attention: "Printed as Attn on its invoices."
- Phone.
- Terms: "Its credit term as SQL prints it, e.g. 30 Days."

### 2d. Setup > Statutory accounts (kind `statutory_accounts`)

The statutory map covers the screen. The Setup-side strings below are server-defined; I checked only the first two against the canvas.
- A new group entry under "Companies and banks".
- Plural/help text beginning "The payable accounts the salary vouchers credit…".
- List columns: Name, Kind, Payable account, Employer's share account, Due day.
- Kind options: "EPF (KWSP)", "SOCSO (PERKESO)", "EIS (SIP)", "SKBBK (Lindung 24 Jam)", "PCB (LHDN)", "HRDF", "Other statutory".
- Field hints: "As the check names it, e.g. EPF (KWSP)." / "The liability the salary vouchers credit, e.g. 420-1001 EPF PAYABLE." / "…e.g. 900-E001. Empty: none (PCB)." / "Due day of the next month: Contributions for a month are due by this day of the next month. Empty: the 15th." / "Order: Lower comes first. Empty: after the others."
- Stopped note: "Stopped: the statutory payables check leaves this account out."
- Refusals:
  - "Payable account: the company's chart of accounts has no account X, and no account line or opening balance names it."
  - "The payable account and the employer's share account are two different accounts."
  - "The account X is already a statutory account of this kind for the company."
  - "Choose the company whose books it is in."
- Delete is always allowed (the check only reads it).
- It is restorable from the audit trail (restore.py).
- Usage lists on other records now include "statutory account", "SQL account line" (a chart account) and "company's invoices" (a bank account used as the invoice account).

### 2e. Setup > Checklist: "SQL books agree" item

Not on the canvas (grep for "SQL books agree" and "sql-books" found nothing).
- Starter item `sql-books`, due (1, 15), title **"SQL books agree with SQL Account"**.
- Detail text (rules.py `BOOKS_DETAIL`): "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least the month's last day. Done when every document of the month is in the journal and in SQL's listings, each one balances and agrees with its listing, and SQL's trial balance agrees with the books here."
- A company not kept in SQL has it left out of the starter items.
- Saving the completion for such a company refuses: "<code>'s books aren't kept in SQL Account, so SQL's books can't show this item done." (monthly.py).
- The checklist view returns `uses_sql`.
- The item has a deadline of 0 (Next up shows it through rule 10).

### 2f. Setup > General: SQL exports folder

The route `POST /api/settings/sql-exports-dir` and config `sql_exports_dir` (empty means the Downloads folder) are new. The visible parts are the folder `<details>` on the SQL page (1599-1604) and the toasts "Reading your Downloads folder" and "Folder saved" (4312). Sql.dc.html and SetupGeneral.dc.html mention "Downloads" only generically. Check that both show the editable folder row and the two toasts.

### 2g. Audit trail screen (AuditTrail.dc.html)

New row and field labels (auditread.py):
- Table labels: "Statutory account(s)", "Ledger read(s)", "Ledger document(s)", "Account line(s)", "Opening balance(s)", "MyInvois e-Invoice(s)".
- Field labels: "Book figures by bank lines confirmed", "Financial year starts in", "Payable account", "Employer's share account", "Kind".
- `fy_start` is a new field name on companies.

Append-only guard messages (audit.py):
- "Account lines can't be changed: a change in SQL is kept as a new version."
- "The activity log can't be changed." and "The audit trail can't be changed." (reworded to one shared template).

**Audit-check problem line (new):** "The check that refuses entries made here for a company kept in SQL has been changed or removed." This shows in the audit trail's check result when `ledger.guard_missing` is true. Canvas AuditTrail.dc.html has no such problem state.

### 2h. "Kept in SQL" write refusals (user-visible errors everywhere entries can be made)

hrp/ledger.py:23 and 1228 block entries made here for a company kept in SQL.
- "This company's books are kept in SQL Account: its entries come only from SQL."
- "This company's books are kept in SQL Account: its opening balances come only from SQL's reports."
- These are database-trigger errors that can surface as an error toast on Payment, Bank opening and Setup. The canvas shows no such error state (grep for "refuses entries" and "Account lines can" returned nothing).

### 2i. Bank reconciliation additions

These may belong to the sql-bank map; confirm they were listed.
- **book_changed banner** (`rcChanged`, 1026-1036): banner "warn rc-changed" showing `ch.text`, then "SQL's receipts and payments now count by what each one posted to the bank account, not by its listing amount." A table with columns "At sign-off" / "Now" and rows Money in / Money out / Book closing. A **"Confirm again"** button (disabled when `!can_reconfirm`, with `reconfirm_why` beside it). The success toast is "Sign-off confirmed again with the new book figures." (4251). The route is `POST /api/recon/confirm-book`.
- **Year-list row note** (1129): `book_changed.text`, then "book closing X at sign-off, Y now (in A → B…)", styled bad-text.
- **rcSqlCheck** (1039-1043): `ok` pill with the text, a "Check against SQL" `bad` pill plus text, or plain text.
- Notes: "Not counted: N receipt(s) or payment(s) whose lines in SQL don't touch this bank account (paid from another account)." (1087); `listing_note` (1088, 1141, 1302).
- The date-difference tick now uses `needs_date_tick` (1193) and candidate matching by `open_lines` (1216-1218), so rules for which candidate payments are offered changed.
- A banner on the import preview (2173): "New entries fall in <months>, whose bank reconciliation is signed off: its book figures may change. Nothing is un-signed: check that month…".
- Toast tail (3171, 4270): ". The bank reconciliation of signed-off <months> changed: it stays signed off; check it again".

### 2j. Other unlisted app.js strings

- **Click-again confirm** on "Take it for <code>" (4297): the button turns into `Click again: "<name>" is <CODE>`. Success toast (4299): `Exports printed for "<name>" are taken for <CODE> from now on. Fetching again…`. This click-again pattern (an in-place button label change) is a new component for States.dc.html.
- "Changed in SQL" card (1542-1548) with a button **"Move the link to the new amount"** and a "follow the new amount" checkbox (`data-sql-follow`), plus the toast "<doc>: the link of <payment> moved to the amount SQL gives now, and the payment's amount changed with it" or "; the payment's amount is as it was" (4306).
- "Replaced by a later version from SQL · N" `<details>` (1550).
- "Before tracking (N)" `<details>` on the SQL page (1589).
- "Nothing new to import" card with a Close button (2137); "No new listing entries" header (2166); the import header "SQL's general-ledger reports" or "MyInvois e-Invoices" (2166); the apply button label via `applyLabel(p)`.
- Ignore and delete toasts: "1 entry ignored; it is listed under Ignored" / "N entries ignored; …"; "<docs> marked as deleted in SQL; listed under Ignored" (4333, 4337); un-ignore toast (4355). The sql-bank map lists "Deleted in SQL", but check these three toasts.
- Document pill that opens the lines (`button.pill.pill-btn`, title "Show the account lines", 1430), with an inline expanded row `.sql-lines-row` (4280-4289). This inline-expansion pattern has no board.
- The unused-files list "N file(s) not used" with reasons and a **"Take it…"** button (2130).
- The e-Invoice row link built from the Long ID, `https://myinvois.hasil.gov.my/<uuid>/share/<long_id>` (2055). Month-first dates were fixed in myinvois.py.
- Invoice print bar: the "Print settings:" missing list with a "Open Setup › Companies" button (2086); the month picker `data-inv-month` and `/api/invoices/month.zip` (4418). The einvoice map should have it; verify the month ZIP is listed.
- Typed-amount parsing (`LT.typedAmount`, 175-180) now accepts commas and bracket negatives, for the Book opening field (4502). The error toast was reworded to the same "Choose the month and type the balance as a number." but with a stricter check.
- Accounting group in the sidebar and the Books icon (127, 136) were noted by the books map; also the Next up deep-link to the Statutory tab (372-377).

## 3. Candidate boards to add or change (for part C)

Beyond what the maps propose:
- **SetupCompanies.dc.html**: add the invoice header block (registration/old registration, address, phone, email, website, bank account on invoices, under the signature), the Printed invoices block (logo and signature upload), and the Printed company names table with the click-again Remove. Add the SWIFT and bank address fields to SetupAccounts if that board exists. Check that SetupParties.dc.html gets the address, Attention, Phone and Terms fields.
- **SetupNav.dc.html** already lists `statutory_accounts` but links to a missing `SetupStatutory.dc.html` (noted by the pack-setup map). Add that board with the columns, kind options and hints listed in 2d.
- **SetupChecklist.dc.html**: add the "SQL books agree with SQL Account" starter item and its SQL-only rule.
- **AuditTrail.dc.html**: add the new table and field labels, and a failed-check state carrying the guard problem text.
- **States.dc.html**: add the click-again button state, the inline account-lines expansion row, the "Before tracking" pill (grey), and the kept-in-SQL refusal toast.
- **Sql.dc.html** (rename and rebuild per section 1): Fetch card with the folder row, "Changed in SQL", "Replaced by a later version", "Before tracking", the "Nothing new to import" preview, and the signed-off warning on the preview.
- **BankReview.dc.html and Bank.dc.html**: add the book_changed banner with its At sign-off / Now table and "Confirm again", the sql_check pill, and the reworded notes.
- **Main.dc.html, DarkOverview.dc.html and MobileOverview.dc.html**: change "Month not set up" to follow the before-tracking rule, with kept pills.

Sample-data note: use today Wednesday 18 Nov 2026 and month October 2026 for the statutory due dates (October contributions are due Sun 15 Nov, so show them as overdue). For AISB use SQL-kept data; for AI (no SQL) show the refusals and the left-out checklist item, which only apply to AISB.

Not verified: I did not open each canvas board in full. Presence or absence is by grep for the exact strings quoted above.