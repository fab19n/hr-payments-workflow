# Stage 1 inventory: Overview and Next up, sidebar, company month and checklist, audit pack books pages and pack check, Setup, README

This was a read-only pass. No files were changed. I compared the code at HEAD b698dc1 with b7d7fa0, ignoring whitespace (`git diff -w --ignore-cr-at-eol`). Canvas folder: `design/canvas`.

**Some stage 1 work is already on the canvas:**
- SetupNav already lists `statutory_accounts`, but it links to `SetupStatutory.dc.html`, which does not exist, and uses the glyph `trail`.
- SetupCompanies already has `fy_start`.
- Main and DarkOverview already show the grey "Before tracking" pill on a card that is not set up.
- SetupGeneral already mentions the SQL exports folder.

Everything else below is missing or wrong on the canvas.

---

## 1. Sidebar: the new "Accounting" group with Books

### A. Code
- `static/app.js:126-129` `VIEWS`. The sidebar order is now:
  - Dashboard (Overview)
  - Companies (one per company)
  - Monthly work: Budget, Bank statements, SQL import, Recurring
  - **Accounting: Books** (new)
  - Filing: Audit pack, Audit trail, Backup
  - Setup
- `app.js:136` adds a new icon `books`, an open book (path `M4 4h6a2 2 0 0 1 2 2v14…`).
- `app.js:309` routes `state.view === "books"` to `viewBooks`.
- `app.js:285` builds the breadcrumb from `VIEWS`, so the Books page reads **"Accounting › Books"**.
- `app.js:361-380` `goTo`:
  - A Next up row with `view: "books"` does not change the payroll month: `if (g.month && g.view !== "books") state.month = g.month`.
  - With `g.tab` it opens that Books tab with From and To set to the row's month through today. Statutory rows open `tab: "statutory"`.
- Books page (`app.js:1650`, owned by another area):
  - Title "Books · AISB", with the company picker, From/To, Show, "This financial year to date" and Excel.
  - Tabs: Trial balance, General ledger, Profit and loss, Balance sheet, Customers and suppliers, Statutory.

### B. Canvas (Sidebar.dc.html)
- The `groups` array has Dashboard, Companies, Monthly work, Filing and Setup. **There is no Accounting group and no Books item.**
- The `active` enum has no `books`.
- The link map `L` has no Books board.
- The badge list `todo` has no `books` area.
- Icon.dc.html has no `books` glyph.

### C. Proposal
- Sidebar:
  - Insert `{ label: 'Accounting', items: [item('books', 'Books', 'books')] }` between Monthly work and Filing.
  - Add `books` to the `active` enum and `L.books = 'Books.dc.html'` (the Books board belongs to the Books area).
  - Add a badge: `books: count(t => t.area === 'books')`. This keeps the one badge rule: the statutory Next up row (rule 14) has `go.view = books`.
  - With the sample below the badge is 1 and red: AISB KWSP is overdue. Also add that row to the `todo` list as `{ co: 'aisb', area: 'books', over: true }`, so the AISB badge goes up by one as well.
- Icon: add a glyph `books` (the open book, as in the app's `ICON.books`).
- Topbar: the Books board passes `section="Accounting" page="Books"`.
- CommandPalette:
  - Add `['Go to', 'books', 'Books', 'Accounting', '', '', 'Books.dc.html', '', '']`.
  - Add a Setup record row, e.g. `KWSP (EPF)`, "Statutory accounts", AISB.
- Mobile: Books is not one of the 4 phone screens. Point it at MobileDesktopOnly if it is added to `moreLinks`.

---

## 2. Overview cards and Next up

### A. Code

**Before tracking** (`app.js:348-353`, `456-513`, server `hrp/app.py:392-445`):
- `beforeTracking(e, month)` is `e.first_month && month < e.first_month`.
- The pill is `BEFORE_PILL` = `<span class="pill grey">Before tracking</span>`. It was renamed from "Before the first month tracked".
- **Card not set up** (no payments and no tasks):
  - Heading: `"{Month YYYY} isn't set up yet"`, plus BEFORE_PILL when before tracking.
  - Note: `"It already holds N payment(s), shown below. "` (when it holds any), then `"Setting it up adds {CODE}'s checklist and recurring payments for the month."`, then, when before tracking, `" It is before the first month tracked in this app ({Month YYYY})."`
  - Button: "Set up this month".
- **Card for a before-tracking month that holds payments** (`app.js:466-485`), new:
  - The flags become `[BEFORE_PILL, …kept]`, where `kept` is only the payment-flag pills and the `"{n} bank lines not explained"` pill.
  - Checklist counts, part paid, documents missing and "not in SQL" pills are dropped.
  - "Nothing overdue" and "Filed …" still appear when nothing is kept.
  - **"Month not set up" is no longer added** for a before-tracking month (`!x.set_up && !x.before_first`).
- Server, new: for a before-tracking month, `unmatched_lines` counts only unmatched lines on statements that are **not signed off** (`app.py:419-426`).

**Next up** (`hrp/nextup.py`; drawn by `nextRow` and `nextCard`, `app.js:424-445`, which did not change). Rows are `{rule 1-14, text, due, state, priority, amount, go}`.

- **New rule 14, statutory** (`nextup.py:452-466`):
  - One row per statutory account and month that is **late** or **short**, for tracked months from 12 months before today. Nothing appears until statutory accounts are confirmed in Setup.
  - Priority P1, due = the due day.
  - `amount = -difference` in MYR (not drawn by `nextRow`).
  - Go: `{view: "books", tab: "statutory", from: "{month}-01", to: today}`.
  - Text is `"{CODE}: {text} Check it on the Statutory tab."`, where `{text}` comes from `statutory._text`:
    - late: `"{label} for {Month YYYY} wasn't paid by {DD Mon YYYY}."`
    - short: `"{label} for {Month YYYY}: RM x less was paid than was taken off the salaries."`
  - The dates use `%d %b %Y`, so they are zero-padded, e.g. "05 Dec 2026".
- **Rule 7, SQL. The wording changed** (`nextup.py:328-370`):
  - With unrecorded payments: `"Fetch SQL's {Oct[ and Nov]} {Payment Voucher[ and Official Receipt]} listing[s] on the SQL import page: {what} not recorded"`, then optionally `"; N SQL entries not linked yet"` and `"; N voucher(s) changed in SQL (move the link on the SQL page)"`.
  - Only loose entries: `"Link or ignore N SQL entr(y|ies) not linked yet"`, with `"; check N voucher(s) changed in SQL (move the link on the SQL page)"` when some changed.
  - Only changed vouchers: `"Check N voucher(s) changed in SQL (move the link on the SQL page)"`.
  - SQL entries from months before tracking are never counted.
- **Rule 10, checklist.** It now also carries the new "SQL books agree with SQL Account" item, which has no deadline:
  - One item: `"{Mon} {CODE}: {title}"`.
  - Several: `"Finish N {Mon} {CODE} checklist items: A and B"`, or `"… A and N more"` when a title contains " and " or a comma.
  - Go opens the company month with the item marked.
- The Waiting-for-SQL hint on a payment changed to: `"… Fetch SQL's latest listings on the SQL import page to record it."` (db.py).

### B. Canvas (Main.dc.html, DarkOverview, MobileOverview)
- The card's August `st='before'` state matches the not-set-up card. **Missing:**
  - The before-tracking card that holds payments: the grey pill plus only the payment and bank-line pills, no "Month not set up".
- The `todo` list has no:
  - rule 14 statutory row
  - rule 10 row for SQL books
- The `sql` row reads "Record 4 paid payments in SQL Account". The code now says "Fetch SQL's Oct Payment Voucher listing on the SQL import page: 4 … not recorded".
- AISB's checklist counts don't include the new SQL books item: `tasks:[17,24]` should be `[17,25]`, and September `[23,24]` should be `[24,25]` with the item done.

### C. Proposal (Main, then copy to DarkOverview and MobileOverview)
- Add to `todo`:
  - `{ id:'statkwsp', co:'aisb', area:'books', over:true, tone:'bad', glyph:'vault', title:"AISB: KWSP (EPF) for October 2026 wasn't paid by 15 Nov 2026. Check it on the Statutory tab.", meta:'AISB · Books › Statutory · RM 11,240.00', due:'Overdue 15 Nov', href:'Books.dc.html', verb:'Open Statutory' }`
  - `{ id:'sqlbooks', co:'aisb', area:'company', over:true, tone:'bad', glyph:'checklist', title:'Oct AISB: SQL books agree with SQL Account', meta:'AISB · Checklist', due:'Overdue 15 Nov', href:'Company.dc.html', verb:'Show item' }`
  - Change the sql row's title to the rule 7 wording.
- In August (`off<=-2`), give AISB a card that holds payments: `[Before tracking] [2 bank lines not explained]`, stats 0/0 checklist, no "Month not set up". Leave AI as the not-set-up card with the pill.
- The code shows **two rows for one unpaid KWSP**: the payment's "Past legal deadline" row and the statutory row. Show both, since that is what the code does, and flag it as a design question.

---

## 3. Company month page and checklist

### A. Code
- Header (`app.js:573`): `"{Name} · {Month YYYY}"`, plus BEFORE_PILL when `d.before_first`. The not-set-up card above it carries the same pill.
- **New built-in checklist item "SQL books agree with SQL Account"**:
  - code `sql-books`, completion `books`
  - due on the 15th of the next month, no documents, no deadline
  - only for a company kept in SQL (`rules.py:84,174,177,210`; `checklistbook.py:504-585`)
- Update 30 adds the item to each SQL company with a checklist, from the earliest month not filed. It is never added to a filed month or before the first month tracked.
- `rules.BOOKS_DETAIL` (shown as the item's detail): "Fetch SQL's GL Journal of Transaction and Trial Balance up to at least the month's last day. Done when every document of the month is in the journal and in SQL's listings, each one balances and agrees with its listing, and SQL's trial balance agrees with the books here."
- Status comes from `sqlbooks.month_check` (`hrp/sqlbooks.py:68`) through `db.task_status` (`db.py:1316`). It is worked out each time, never stored as a tick.
  - When done, the item is ticked and its box disabled. Note `.ok`: `"Done: SQL's journal covers {Month YYYY}, its documents agree with the listings and SQL's trial balance as at {D Mon YYYY} agrees with the books here"`, with optional `" (N document(s) in sections with no listing this app reads was/were checked by its/their account lines and SQL's trial balance)"`. There is no closing period.
  - When not done, the note is the first failing check, in this order:
    1. `"Fetch SQL's GL Journal of Transaction and Trial Balance up to at least {D Mon YYYY}."`
    2. `"Fetch SQL's GL Journal of Transaction for the whole of {Month YYYY} (from {D Mon} to {D Mon YYYY}): no journal fetched covers the whole month."`
    3. `"N document(s) of {Month} in SQL's listings is/are missing from SQL's GL Journal of Transaction (A, B, C and N more): fetch the journal for {Month} again, or check it/them in SQL."`
    4. `"N document(s) … has/have no listing (…): fetch SQL's listing for {Month} on the SQL import page."`
    5. `"{DOCNO} doesn't balance or agree with its listing ( N more document(s) of {Month} too): {reason} Open it on the SQL page or Accounting › Books to see its lines."`
    6. `"Fetch SQL's Trial Balance up to at least {D Mon YYYY}."`
    7. `"The nearest trial balance of SQL's kept is as at {X}, but the journals fetched stop before then: fetch SQL's Trial Balance as at {Y}, or its GL Journal of Transaction up to {X}."`
    8. `"{N accounts differ …} See Accounting › Books › Trial balance, then fetch again what differs."`
  - A company not kept in SQL: `"This company's books aren't kept in SQL Account, so nothing here can show this done: tick it by hand."`
  - Before tracking: no note.
- Toast after removing a payment (`app.js:4227-4232`): vouchers from months before tracking go back `"; X back under Before tracking on the SQL page"`. Unlinking an SQL entry says `"…back under Before tracking"`.

### B. Canvas (Company.dc.html, DarkCompany, MobileCompany)
- AISB October and September `tasks` have no SQL books item.
- There is no before-tracking month state. The `view` enum is october, sent-here, filed, loading, september, november.
- Next up has no statutory or SQL-books rows.
- The claims payment hint still says "Paste the latest SQL listing to record it." It should read "Fetch SQL's latest listings on the SQL import page to record it."

### C. Proposal
- AISB October, add after `recon`:
  - `{ k:'sqlbooks', title:'SQL books agree with SQL Account', detail: BOOKS_DETAIL, due:'2026-11-15', bad:true, auto:true, why:"Fetch SQL's Trial Balance up to at least 31 Oct 2026.", noOther:false }`
  - It has no document slots. Its box is enabled for a manual tick, and a manual tick shows "Ticked by hand. …" in a warn note.
- AISB September: the same item, done and auto, why `"Done: SQL's journal covers September 2026, its documents agree with the listings and SQL's trial balance as at 30 Sep 2026 agrees with the books here"`.
- AI: no item, since AI is not kept in SQL.
- AISB Next up: add the statutory row and the SQL books row from section 2.
- Add a view `august` (before tracking): header "AISB · August 2026 [Before tracking]" with the not-set-up card ("August 2026 isn't set up yet [Before tracking]", "It already holds 3 payments, shown below. … It is before the first month tracked in this app (September 2026).") and the payments table below it.

---

## 4. Audit pack: books pages, Before you print, auditor package, Check this pack

### A. Code
- **PDF order** (`hrp/auditpack.py:236-246`):
  1. Index
  2. Bank reconciliation
  3. **SQL books check**, **Statutory payables check**, **Trial balance against SQL**: one A4 page each, each with a PDF bookmark (`BOOKS_PAGES`, `auditpack.py:567`)
  4. The documents
- Page heads: `"{company name} - {Month YYYY} - {page title}"`, Helvetica B 15 for the heading and 9 pt for the body (`_books_pages`, `auditpack.py:622`). Content comes from `books_checks` (`auditpack.py:570`).
- **SQL books check**: `"Done."`, `"Not done."` or `"Not checked here."`.
  - Done text: month_check without "Done: ", capitalised, with a full stop.
  - Not checked: `"{Month} is before the first month tracked in this app, so SQL's books are not checked for it."`, or the not-in-SQL sentence.
  - Then always: "Whether SQL Account's books for the month agree with the mirror kept here: SQL's journal covers the month, its documents agree with the listings, and SQL's trial balance agrees with the books here. SQL Account stays the books; nothing here changes them."
- **Statutory payables check**: the summary, then `"- {label} ({payable}): {month text}"`, then the notes and mispostings.
  - Summary: `"N statutory payable(s) to look at: …"`, `"All statutory payables cleared up to {Month}."` with an optional `" Next due by …"`, or `"No statutory accounts are confirmed for this company yet, so nothing is checked."`
  - Month texts: `"… paid in full."`, `"… paid in full, the last of it on {DD Mon YYYY}, after the due day {DD Mon YYYY}."`, `"… is due by …"`, `"… more was paid …"`, `"Nothing was taken off the salaries for …"`
  - Missing opening note: `"No opening balance of X is kept at dd/mm/yyyy … Fetch SQL's trial balance for that day."`
- **Trial balance against SQL**: the first line is one of:
  - `"Agrees with SQL's trial balance."`
  - `"Differs from SQL's trial balance."`
  - `"Not checked."`
  - `"Possibly out of date: SQL's trial balance was read before a later GL Journal of Transaction."`
  
  Then `"Compared with SQL's trial balance {file}, {D Mon YYYY} to {D Mon YYYY}."` (or `", as at …"`), then the result text (`"N accounts differ from SQL's trial balance as at dd/mm/yyyy; M agree. …"` or `"Agrees … as at dd/mm/yyyy: all N accounts compared."`), then `"- {code name}: … SQL's trial balance has …, the books here … (a difference of …)."`
  - No TB kept: `"No trial balance of SQL's as at {D Mon YYYY} or later is kept, so the books here can't be checked against SQL's. Fetch SQL's Trial Balance as at {D Mon YYYY}."`
  - Not in SQL: `"This company's books are kept here, not in SQL, so there is no SQL trial balance to check against."`
- If the reconciliation was signed off and the book figures changed since, the Bank reconciliation page adds: `"{text}. Signed off with in …, out …, closing …; counting SQL's receipts and payments by their lines on the bank account it is now in …, out …, closing …."` and, when it no longer agrees, `" The new book closing doesn't agree with the bank, so the month needs reviewing again."` (`auditpack.py:450-456`)
- **Before you print**: no new code, but the SQL books item takes part as a "checklist item not done" row: title "SQL books agree with SQL Account", detail `"{why}, due 15 Nov"` (`auditpack.py:363`).
- **Auditor package** (`hrp/reports.py:336-378`):
  - The zip now has a `Books/` folder of Excel files (booksexcel): `"AISB Trial balance to 31-10-2026.xlsx"`, `"AISB General ledger to 31-10-2026.xlsx"`, `"AISB Profit and loss to 31-10-2026.xlsx"`, `"AISB Balance sheet at 31-10-2026.xlsx"`, `"AISB Customers and suppliers to 31-10-2026.xlsx"`, `"AISB Statutory payables check to 31-10-2026.xlsx"`.
  - Each is listed on the Files sheet with Belongs "Books", Type "Excel report".
  - The UI text did not change: confirm `app.js:4374`, result `app.js:4380` "Auditor package built (N files…)". N now includes the 6 Books files.
- **Check this pack** (`hrp/packcheck.py`):
  - New group `books`, placed between "SQL vouchers…" and "The month (set up, filed)". Label: **"SQL's books and the statutory accounts (its books pages)"**. In the summary it counts as "N to SQL's books or the statutory accounts".
  - It covers changes to ledger_batches, ledger_docs and ledger_openings (dated up to the end of the month after) and to gl_accounts and statutory_accounts (any date).
  - Rows are drawn by `changeHtml`: `"Added · Ledger document · PV2610-014"`, `"Changed · Statutory account · KWSP (EPF)"`, `"Added · Ledger read · #57"`.
  - New "can't tell" line (`packcheck.py:339`): "For its books pages, SQL's documents, openings and reports dated after the month that follows it are not listed: they reach those pages only when no trial balance of SQL's as at the month's end was kept."

### B. Canvas (AuditPack.dc.html)
- The pack check `LABEL` holds only payments, documents and packs. There is no books group and the new can't-tell line is missing.
- The auditor confirm text "In the zip: a fresh audit pack, the Excel month report with a Files sheet, and the original files." has no Books folder.
- Before you print has no SQL books row.
- No board shows the contents of the PDF.

### C. Proposal
- AuditPack:
  - Add `books: "SQL's books and the statutory accounts (its books pages)"` to `LABEL`.
  - Add an AISB check state with 2 books rows after build: `"Added · Ledger document · PV2611-004"` (a KWSP voucher fetched later) and `"Changed · Statutory account · KWSP (EPF)"`. Summary: "… 2 to SQL's books or the statutory accounts."
  - Add the new can't-tell line.
  - Auditor confirm: add "a Books folder of Excel files (trial balance, general ledger, profit and loss, balance sheet, customers and suppliers, statutory payables check)". Raise `D.files` by 6.
  - For AISB, add a Before you print row: `{ kind:'task_open', title:'SQL books agree with SQL Account', detail:"Fetch SQL's Trial Balance up to at least 31 Oct 2026, due 15 Nov" }`.
- **New board `AuditPackBooks.dc.html`, "Audit pack · books pages"**: a print preview of the 3 A4 pages plus the PDF bookmark list. Place it at x 6080, y 17080 and move note n3 to x 7600.
  - States (prop `view`):
    - `aisb-open` (default), for AISB Sdn Bhd, October 2026:
      - Page 1: "Not done." / "Fetch SQL's Trial Balance up to at least 31 Oct 2026." / the standing paragraph.
      - Page 2: "1 statutory payable to look at: KWSP (EPF) for October 2026 wasn't paid by 15 Nov 2026." then:
        - "- KWSP (EPF) (430-100): KWSP (EPF) for October 2026 wasn't paid by 15 Nov 2026."
        - "- PERKESO (SOCSO & EIS) (430-200): PERKESO (SOCSO & EIS) for October 2026 paid in full, the last of it on 17 Nov 2026, after the due day 15 Nov 2026."
        - "- PCB (MTD) (430-300): PCB (MTD) for October 2026 paid in full."
      - Page 3: "Not checked." / "No trial balance of SQL's as at 31 Oct 2026 or later is kept, … Fetch SQL's Trial Balance as at 31 Oct 2026."
    - `aisb-done`: September. "Done.", "All statutory payables cleared up to September 2026. Next due by …", and "Agrees with SQL's trial balance." / "Compared with SQL's trial balance AISB TB Sep 2026.xlsx, 1 Jan 2026 to 30 Sep 2026." / "Agrees with SQL's trial balance as at 30/09/2026: all 48 accounts compared."
    - `differs`
    - `stale` ("Possibly out of date…")
    - `ai`: "Not checked here." with the not-in-SQL sentence, "No statutory accounts are confirmed…", and "Not checked." with the books-kept-here sentence.

---

## 5. Setup

### 5.1 Companies: financial year, old registration no., print settings, printed company names
**A. Code**
- Field order (`hrp/masters.py:59-86`): Code, Name, Short name, Kept in SQL Account, First month tracked, **Financial year starts in**, Registration no., **Old registration no.**, Tax ID (TIN), SST no., KWSP/PERKESO/LHDN employer nos., SQL Account database, **Address** (textarea), **Phone**, **Email**, **Website**, **Bank account on invoices**, **Under the signature**, Notes.
- Hints:
  - fy_start: select January…December, empty option "—". Hint: "Keep it the same as the company's setting in SQL Account: SQL's reports can't tell it. The trial balance check uses it, and later reports will too. Empty: January."
  - reg_no: "As printed on invoices, e.g. 202401012345."
  - old_reg_no: "Printed in brackets after the registration no., e.g. 1234567-X. Empty: none."
  - address: "Printed in the invoice header, as one line. Several lines are joined with commas."
  - phone and email: "Printed in the invoice header."
  - website: "Printed in the invoice header, e.g. www.example.com."
  - invoice_account_id: options "{label} · {bank} · {number}" (only accounts in use). Hint: "Printed under All payments to be made to. Its bank, account number, bank address and transfer code come from Setup › Bank accounts."
  - sign_label: "Empty: For and the company's name, as SQL Account prints it."
- Refusals:
  - "Bank account on invoices: add the company first, then its bank accounts, then choose one."
  - "Bank account on invoices: choose one of this company's bank accounts."
  - "Bank account on invoices: that account is stopped. Choose one in use, or use it again first."
- Below "Where used", "Tidy up…" and its note, the drawer of an existing company has two new blocks (`app.js:2863-2869`):
  - **"Printed invoices"** (`app.js:2909-2923`):
    - Note: "Customer invoices and self-billed e-Invoices are printed from SQL's documents with this header and footer: the name, registration no., TIN, address, phone, email and website above, the bank account on invoices, and the logo and signature here (PNG or JPEG, at most 2 MB)."
    - Two fields, "Logo" and "Signature". Each shows the image (max 70 px high) or "None uploaded", a file input, **Upload**, and **Remove** when there is an image.
    - Then either "**Print settings still missing** (invoices print without them):" with a list, or "Every print setting is filled in."
    - Then optional "**Fonts:**" and "**Too long to print in full:**" lists.
    - Missing items (`invoicepdf.py:365`):
      - "No address: add it as Address in Setup › Companies › {CODE}."
      - "No phone, email or website: add them in Setup › Companies › {CODE}."
      - "No registration no.: …"
      - "No tax ID (TIN): …"
      - "No logo/signature: upload it under Printed invoices in Setup › Companies › {CODE}."
      - "The {logo} file changed or is missing since it was uploaded, …"
      - "No bank account chosen for All payments to be made to: choose one as Bank account on invoices in Setup › Companies › {CODE}."
      - "The bank account chosen for invoices ({label}) is stopped."
      - "The bank account {label} has no bank address or bank transfer (SWIFT) code: add it in Setup › Bank accounts."
    - Toasts: "Logo uploaded", "Signature uploaded", "Logo taken off the invoices", "Choose an image first."
    - Upload errors: "{Logo}: upload a PNG or JPEG image.", "…: the file is empty.", "…: the image is larger than 2 MB. Save it smaller and upload it again.", "…: the file isn't a PNG image.", "…: the image can't be read. Save it again as PNG or JPEG.", "…: the image is too large (W x H pixels). Save it smaller."
  - **"Printed company names"** (`app.js:2874-2906`):
    - Note: "Names SQL Account prints on its exports that match no company in Setup, confirmed as {CODE}'s with **Take it for {CODE}** on the SQL page. Fetch takes files printing them for this company."
    - Table columns: "Name as printed", "Confirmed" (dd/mm/yyyy at HH:MM), "By" ("Not recorded" when empty), and a Remove button.
    - Remove needs two clicks. The first click shows "Click again to remove" and the note `Removing "{name}": files printing it are held again on the next Fetch, until Take it for is clicked again.` The toast: `"{name}" removed. Files printing it are held again on the next Fetch, until Take it for is clicked again.`
    - Empty: "None confirmed." Not ready: "The records need an update for this. Restart the app."
  - Both blocks show for AI too, even though AI is not kept in SQL.

**B. Canvas (SetupCompanies.dc.html)**
- It has fy_start. Its empty option reads "January (not set)" (code: "—"), and the hint is shorter.
- No old_reg_no: reg_no samples hold "201901023456 (1331234-K)".
- The reg_no hint differs from the code.
- None of the print fields are shown.
- The Printed invoices and Printed company names blocks are missing.
- Used-by has no "statutory accounts".
- first_month samples are 2025-01 / 2025-03, which conflicts with Main's "September 2026".

**C. Proposal**
- Add a group "Printed invoices", with fields address, phone, email, website, invoice_account_id, sign_label plus the logo/signature block.
- Split reg_no "201901023456" from old_reg_no "1331234-K" and use the code's hints.
- AISB sample:
  - Address: "Lot 12, Jalan Teknologi 3/1, Kota Damansara, 47810 Petaling Jaya, Selangor"
  - Phone: 03-6150 2200
  - Bank account on invoices: "Maybank current · Maybank · 5141 2300 4417"
  - Logo uploaded, signature not uploaded
  - Missing list: "No signature: upload it under Printed invoices in Setup › Companies › AISB." and "The bank account Maybank current has no bank address or bank transfer (SWIFT) code: add it in Setup › Bank accounts."
- Printed company names for AISB: "AISB SDN BHD (HQ)", confirmed 12/11/2026 at 16:02 by Aisha Rahman. Match the SQL board's Take it for sample.
- New states: `print`, `image-error`, `names`, `names-remove` (click again), `names-empty`, `bank-refused`.
- Set first_month to 2026-09 for AISB and AI, matching Main.

### 5.2 Bank accounts (Setup.dc.html), and customers and suppliers (SetupParties.dc.html)
**A. Code**
- Bank accounts gain "Bank address" (wide; hint "Printed on invoices when this account is the one to pay into.") and "Bank transfer (SWIFT) code" (max 11; hint "Printed on invoices, e.g. EXMBMYKL."). Used-by adds "company's invoices".
- Customers and suppliers gain:
  - Address line 1–4. Line 1 hint: "Printed on its invoices. Filled from SQL's list when pasted with Address1 to Address4."
  - Attention: "Printed as Attn on its invoices."
  - Phone
  - Terms: max 40, "Its credit term as SQL prints it, e.g. 30 Days."

**B. Canvas**: neither board has these fields.

**C. Proposal**
- Add the fields to both boards.
- Maybank current: Used by 1 "company's invoices". Bank address and SWIFT are left empty, which is what makes the missing item in 5.1 appear.

### 5.3 Statutory accounts (new section, new board)
**A. Code**
- `masters.py:236-257`, kind `statutory_accounts`, per company. Group "Companies and banks", after Chart of accounts.
- List heading "Statutory accounts · AISB". Button "Add statutory account".
- Help: "The payable accounts the salary vouchers credit with what is taken off the salaries (EPF, SOCSO, EIS, SKBBK, PCB), and the expense account each authority's voucher debits with the employer's share. Accounting › Books › Statutory checks that each month is paid in full by its due day. Nothing is checked until an account is added here; that page suggests them from the chart of accounts by their names."
- Columns: Name, Kind, Payable account, Employer's share account, Due day, Used by, Status.
- Fields:
  - Kind: EPF (KWSP), SOCSO (PERKESO), EIS (SIP), SKBBK (Lindung 24 Jam), PCB (LHDN), HRDF, Other statutory
  - Name: "As the check names it, e.g. EPF (KWSP)."
  - Payable account: sqlcode, "The liability the salary vouchers credit, e.g. 420-1001 EPF PAYABLE."
  - Employer's share account: "… e.g. 900-E001. Empty: none (PCB)."
  - Due day of the next month: "… Empty: the 15th."
  - Order, Notes
- Stopped note: "Stopped: the statutory payables check leaves this account out."
- Always deletable (it has no uses). Show deleted / Put back works (`restore.py`).
- Refusals:
  - "Payable account: the company's chart of accounts has no account {code}, and no account line or opening balance names it."
  - "Employer's share account: …" (same wording)
  - "The payable account and the employer's share account are two different accounts."
  - "The account {code} is already a statutory account of this kind for the company."
  - "Choose the company whose books it is in."
- Empty list: "None yet."

**B. Canvas**: SetupNav links to `SetupStatutory.dc.html`, which doesn't exist. SetupNav uses glyph `trail`.

**C. Proposal**
- **New board `SetupStatutory.dc.html`, "Setup · Statutory accounts"**, using the SetupCompanies/SetupChart pattern. Place it at x 7600, y 19760 and move note n5 to x 9120.
- States: list, empty (AI, "None yet." plus help), new, errors (each refusal), edit, stop/stopped, delete, deleted/put-back, history.
- AISB sample:

  | Name | Kind | Payable account | Employer's share account | Due day |
  |---|---|---|---|---|
  | KWSP (EPF) | EPF (KWSP) | 430-100 | 900-110 | 15 |
  | PERKESO (SOCSO & EIS) | SOCSO (PERKESO) | 430-200 | 900-120 | 15 |
  | PCB (MTD) | PCB (LHDN) | 430-300 | — | 15 |

- Add 900-110 "KWSP employer's share" and 900-120 "PERKESO employer's share" to SetupChart's sample.
- In SetupNav, change the glyph to `vault`, which matches the statutory payments.

### 5.4 Monthly checklist (SetupChecklist.dc.html)
**A. Code**
- New completion option "SQL books agree with SQL Account (from SQL's journal and trial balance)" (`checklistbook.py:31`).
- It is offered only when the company is kept in SQL (`app.js:3519-3521`). A save for AI is refused with "AI's books aren't kept in SQL Account, so SQL's books can't show this item done."
- It has no deadline: the Deadline / Submitted as fields are hidden (`NO_DEADLINE`, `app.js:3426`).
- The item `sql-books` is a system item (`system=1`).

**B. Canvas**: `COMPL` doesn't have `books`, `ITEMS` doesn't have the item, and the select has no option.

**C. Proposal**
- Add `books` to `COMPL` and the `<select>`, hidden for AI.
- Add an item: `SQLBOOKS: { code:'sql-books', title:'SQL books agree with SQL Account', detail: BOOKS_DETAIL, off:1, day:15, docs:[], done:'books', built:true, noDl:true, used:2 }`. The `used:2` stands for September and October.
- Add an `edit-books` state.

### 5.5 General settings (SetupGeneral.dc.html)
**A. Code**
- New hint: "Until this day of a month you are still closing the month before (the 10th: October's payroll is worked on until 10 November). Change it rarely: joiner and leaver reminders and SQL documents dated near the day are placed by it. A change that would move one in or out of a month already filed is refused, so filed months never change."
- New refusal, 409 (`app.py:3004-3010`, `db.cycle_day_moves_filed`): "Payroll month runs until: months already filed would change, so nothing was saved. With the new day {item}; {item}; {item}; and N more. Reopen those months first if it really must change."
  - Items look like "SQL document PV… of AISB, dated 7 Oct 2026, would move from September 2026 to October 2026" or "the reminder {title} of AI, due 8 Oct 2026, would move from …".

**B. Canvas**: the short hint only; no refused state.

**C. Proposal**
- Add a `day-refused` state: change 10 to 5. Message: "…With the new day the reminder Register Nurul with KWSP and PERKESO of AI, due 8 Oct 2026, would move from September 2026 to October 2026. Reopen those months first if it really must change." AI September is filed on Main.

### 5.6 Move setup (SetupMove.dc.html)
**A. Code**
- A full export now also carries:
  - statutory accounts
  - print settings
  - the bank account on invoices, by name and number
  - logo and signature images in base64, with fingerprints
  - printed company names, with when and by whom
- Import preview count rows, new: **"Printed company names"** (after Companies) and **"Statutory accounts"** (after GL accounts).
- Notes:
  - "The file holds: Bank account numbers, and the companies' registration, tax and employer numbers."
  - "The file holds: The companies' signature images, as printed on their invoices."
  - "Left out of the file when it was made: {sentence}", for example "Statutory account PCB (MTD) of AISB: its account 430-300 isn't in the company's chart of accounts. Add it to the chart in Setup and export again, or add the statutory account again after importing.", or "Printed company name … of AISB: AISB is no longer kept in SQL Account…", or "The logo of AISB: its file changed or is gone since it was uploaded, … Upload it again in Setup › Companies after importing."
- New refusals, prefixed "Company AISB: …":
  - "Logo: the image isn't the one exported (its fingerprint doesn't match). Export the setup again."
  - "Bank account on invoices: the file has no bank account Maybank current (5141 2300 4417) for this company."
  - "Printed company name X of AISB: it already matches company AI, so there is nothing to confirm."
- The import is refused while records hold "statutory accounts".
- The UI "Everything" note did not change (`app.js:3184`), so it doesn't mention any of these.

**B. Canvas**: COUNTS, notes and refusals are missing these.

**C. Proposal**
- COUNTS: add ['Printed company names', 1] and ['Statutory accounts', 3].
- Add the holds notes and one left_out note.
- Add the image-fingerprint refusal to `refused`.
- Propose the Everything copy: "…charts of accounts, statutory accounts, customers and suppliers, each company's checklist, and what its printed invoices need (address, bank details, logo and signature) and the printed company names confirmed."

---

## 6. README (stage 1 as described)
README now describes:
- The `exports\` and `company-assets\` folders, which are backed up and restored with the records.
- That MyInvois links and invoice QR codes point to myinvois.hasil.gov.my.
- Step 5, **Fetch from SQL exports**, covering:
  - the listings
  - the GL Journal of Transaction, GL Ledger and Trial Balance
  - account lines kept as versions
  - "Checks against SQL's reports"
  - Take it for, and the names listed in Setup › Companies with Remove
  - MyInvois copies
  - **Printed invoices**: PDFs and month zips
- New step 6, **Books and checks**:
  - "SQL Account stays the books"
  - the Books page: trial balance, general ledger, P&L, balance sheet, customers and suppliers, statutory payables, Excel
  - financial year from Setup › Companies
  - statutory rows in Next up
  - the self-ticking checklist item "SQL books agree with SQL Account"
  - the month-end bank closing checked against SQL's GL balance
- Step 7, Audit pack: "three books pages after the bank reconciliation", and the auditor package's `Books` folder.
- A new paragraph, **Months before tracking**: "Before tracking" on the SQL page, "Reconciled before tracking", Tidy up.
- The rollover-day refusal under Setup.
- The longer test list.

---

## 7. Proposal summary
- **New boards:**
  - `SetupStatutory.dc.html`, "Setup · Statutory accounts" (5.3)
  - `AuditPackBooks.dc.html`, "Audit pack · books pages" (4)
  - Add both to canvas.json `boards` and `order`. Add a section title "Accounting" for the Books boards from the Books area.
- **Boards to change:**
  - Sidebar and Icon (section 1)
  - Main, DarkOverview, MobileOverview (section 2)
  - Company, DarkCompany, MobileCompany (section 3)
  - AuditPack (section 4)
  - SetupCompanies, Setup, SetupParties, SetupChecklist, SetupGeneral, SetupMove, SetupNav, SetupChart (section 5)
  - CommandPalette and Topbar usage (section 1)
- **Canvas samples to reconcile:**
  - First month tracked: Main says September 2026; SetupCompanies says 2025-01 / 2025-03; SetupChecklist `FIRST` is 2026-10. AI's September is "Filed 5 Oct" on Main, but Company says "Months set up: October" for AI.
  - Name: AISB is "AISB" on Main, "AISB Sdn Bhd" in Setup. The pack pages print the name.
  - SQL fetch date: Company says "SQL entries imported up to 12 Nov". With that date all three AISB statutory accounts would read "late". To get only KWSP late, the SQL area's sample needs a GL Journal fetched to 17 Nov holding PCB (14 Nov) and PERKESO (17 Nov) vouchers. Coordinate with the SQL area.

## 8. Things found in the code, not the canvas (flag only)
1. **Double full stop in Before you print** (`auditpack.py:363`): the detail reads "Fetch SQL's Trial Balance up to at least 31 Oct 2026., due 15 Nov", because the books why already ends in ".".
2. Pack check and trail rows for ledger reads and opening balances are named "#<id>". `auditread.NAME_FIELDS` (`auditread.py:83`) has no `file_name` or `account_code`.
3. The audit pack page description (`app.js:2424`) doesn't mention the bank reconciliation or the three books pages. The auditor confirm (`app.js:4374`) doesn't mention the Books folder.
4. The Move setup "Everything" note (`app.js:3184`) is out of date (5.6).
5. `reports.books_workbooks` makes Books Excel files for a company not kept in SQL as well (`ledger.ready` is global), so AI's auditor package likely gets Books files with little in them.
6. Next up shows two rows for one unpaid KWSP: "Past legal deadline" and rule 14.
7. Statutory dates are zero-padded ("05 Dec 2026"), unlike the rest of the app ("5 Dec 2026").
8. Printed invoices and Printed company names are shown for a company not kept in SQL (AI).
