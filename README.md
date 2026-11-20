# HR Payments

A personal tracker for a group of companies' monthly payroll, statutory and supplier payment cycle.
It keeps every supporting document with its payment, so the month can be printed and filed as one audit pack.

## Start it

Double-click **Start HR Payments.bat**. Your browser opens at http://127.0.0.1:8626. Keep the black window open while you work; close it to stop the app.

## Where your records are

Everything is stored in `C:\HR-Records`, not in this program folder:

| Folder / file | What it holds |
|---|---|
| `records.db` | Payments, checklist, bank statement lines, activity log |
| `documents\<AISB or AI>\<YYYY-MM>\` | Uploaded documents, one folder per payment. Files are made read-only and fingerprinted at upload. |
| `audit-packs\` | Generated audit pack PDFs |
| `exports\<company>\` | Auditor packages (zips) built on the Audit pack page |
| `company-assets\` | Each company's logo and signature, uploaded in Setup › Companies and printed on its invoices |
| `backups\` | Zip backups made from the Backup & log page |
| `seed.json` | Starting payees and accounts, read once on first start. An optional `"names"` gives the real names for the made-up related company and tenant in the built-in checklists (`rules.PLACEHOLDERS`), so they never sit in the program |

The app only listens on this PC (127.0.0.1) and contacts nothing on the internet itself. The MyInvois links on the e-Invoices
page, and the QR codes on printed invoices, point to the tax authority's MyInvois site (myinvois.hasil.gov.my): your
browser opens it only when you click a link or someone scans a code. Don't put `C:\HR-Records` inside OneDrive or
Google Drive.

## Backups

On **Backup & log**, type a password (at least 12 characters) twice and press **Make encrypted backup**. This writes
`HR-Records backup <date> (encrypted).zip` (AES-256) in the `backups\` folder, then opens it again and checks every file.
The password is typed each time; it is never saved or logged. **Backup on this PC only (not encrypted)** makes a plain zip.

**Backup folder (optional)** is where encrypted backups are also copied (saved in `settings.json` as `backup_dir`). Put it
inside your OneDrive folder, for example `C:\Users\<you>\OneDrive\HR-Backup`, and OneDrive uploads it. Only encrypted
backups are copied there; a plain backup stays on this PC. After you mark a month as filed, the app offers to make an
encrypted backup.

`settings.json` is kept in the program folder. When the `HRP_DATA_DIR` environment variable is set (the tests do this),
the settings are kept in that folder instead and the program folder's file is neither read nor written.

Only the contents of an encrypted backup are protected. The names of the files inside (the documents and
company-assets folders) can be seen without the password, so avoid putting a person's name in a document's file name if
the backup goes to OneDrive.

### Restore from an encrypted backup

1. Close HR Payments.
2. Open the zip with 7-Zip (Windows Explorer cannot open AES zips) and type the password. Without the password the backup
   cannot be opened.
3. Copy `records.db`, the `documents` folder and the `company-assets` folder (the logos and signatures printed on
   invoices) from the zip into the records folder (`C:\HR-Records`), replacing what is there (keep a copy of the old
   folder first).
4. Start HR Payments again.

## What to do next

The **Overview** opens with **Next up** and today's date: what is due or waiting, worked out from your records each time
the page is drawn (nothing is stored, so a row goes as soon as the records show it done). Most urgent first: by priority,
then overdue, due today, due soon, later. Each row has a due pill (red overdue, amber today or within 3 days, grey later)
and **Go**, which sets the company and month and opens the payment, the checklist items or payments the row names (marked
for a moment), the Bank statements page on the right account with only the lines to explain, or the SQL, Budget, Audit or
Backup page. On a "Pay ... by 6 Nov" row, **Go** opens the Budget page as at today, which is what the row adds up (not
the balance date you saved there; a note offers it). **Show all** lists the rest, for the Overview and for each company's
page apart; **Back up now** on the backup row backs up without leaving the page. A company's month page shows its own
three most urgent. Months still open from before are named in one line under the list; they only give the rows that cost
money or risk a penalty (payments not found, statutory payments past the legal deadline, part paid, lines to explain),
so with nothing due the card says so rather than "All caught up". A statutory payment not recorded as paid gets a row
from 3 days before its legal deadline. Once a pack is built, a row stays until you mark the month as filed (the Audit
page asks "Printed and filed?" whenever the pack is up to date). The counts on each company's card
(past due, part paid, documents missing, lines to explain, not in SQL) are buttons to what they count. A page drawn on a
new day (a click, or coming back to the tab) sets up the new payroll month and moves to it if it was on the one before.

## The monthly flow

1. **Recurring** – keep salaries, consultant fees, bills and statutory payments up to date. The current payroll month and the
   month before are set up from this list when the app opens; other months when you click **Set up this month**. Saving a
   change also updates the payments not due yet that you haven't changed by hand, from the current payroll month on;
   payments already due are left as they were, as they were most likely paid already.
2. **Budget** (by the 20th) – enter the bank balance and the date it was taken. The budget is the month's payments still to
   pay after that date, with the shortfall to request as funds; payments paid on or before it are already out of the
   balance and are listed under **Already paid**. A payment made in several transfers counts the ones after that date. An
   estimate whose bank lines so far add up to less (the fund requisition paid in tranches) is budgeted at the estimate
   until you confirm the amount in the payment. The Overview shows the same figure.
3. **AISB / AI** – work through the checklist; click a payment to enter the paid date, bank ref, SQL PV no. and upload its documents.
   Pick or drop several files at once; each is kept as its own document (several transfer slips for one payment, say).
   Replace asks first. Each **＋** on a checklist item uploads that document; a checklist document can also be removed
   (the file stays on this PC, out of the audit pack). Checklist items the records can show tick themselves and say why:
   the bank statements imported for every account (and, for the reconciliation, balancing with every line explained and
   the reconciliation filed), a PV in SQL for each salary, each fund receipt's OR and validated e-Invoices for the month
   that add up to what was received, KWSP / PERKESO / PCB paid or their
   acknowledgement filed on the payment, each overseas claim's e-Invoice, and an audit pack built since the last document
   was added. Ticking an item by hand while something is missing asks **Tick anyway?** first. A salary's start date or
   last day adds reminders to the checklist of the month each falls due in, or until that month is set up the latest
   one set up, where it shows without counting in that month or its audit pack (e-CP22, PERKESO and KWSP registration,
   stamping over RM 3,000; CP22A): reminders to check, not legal advice.
   **Payroll check** (Monthly work, before paying salaries) – upload the month's payroll workbook (.xlsx). It is read by
   its headings and checked: each Summary row against its person's payslip (and that every link points at that
   person's own pay row, not another person's sheet, a month of the table or another workbook), the Summary's sums and
   totals, each payslip's year-to-date box against its monthly table (and YTD formulas that will go wrong next month),
   the sheet's own check cells, money with more than 2 decimals, and EPF, SOCSO, EIS and SKBBK against the rates as at
   Nov 2026 (in `hrp/payrollcheck.py`, to check each year). PCB amounts themselves are not checked. The report starts
   with a headline (things to fix before paying, to check, notes), then the Summary and each person with the cells, and
   the month's amounts to pay per person and per authority; **Excel report** exports it. The workbook is filed as the
   month's payroll summary on the checklist; **Check again** with a corrected file keeps the earlier checks listed. IC
   numbers show only their last 4 characters. While the latest check has things to fix, Next up says so in one line.
4. **Bank statements** – import each Maybank statement PDF. Lines are matched to payments automatically; explain the rest.
5. **SQL import** (AISB) – sign in to SQL Account yourself, export the PV / JV / Cash Book listing to Excel, and import it here.
   Each entry's doc no. is saved on the payment it records; estimated bills take SQL's actual amount. Entries in SQL but not
   in the tracker are listed so nothing is missed. Re-importing the same export is safe.
   **Fetch from SQL exports** reads every listing exported from SQL Account in one click: in SQL, the arrow beside the print
   button › Export to Microsoft Excel Workbook, saved in `SQL Drive on SQL Connect › Download` (the browser then downloads
   it). The files are read by what they hold, not by their names, from your Downloads folder or the folder saved on the SQL
   page (`sql_exports_dir` in `settings.json`), and each document is shown once as new or already imported. A listing that
   doesn't add up to its own grand total, or belongs to another company, is left out with the reason; nothing in the folder is
   changed. It reads the Cash Book, Payment Voucher, Official Receipt, Journal Voucher, Customer Invoice, Sales Invoice,
   Customer Payment, Supplier Invoice and Supplier Payment listings, not their GST layouts (`hrp/sqlreport.py`,
   `hrp/sqlfetch.py`). A file whose company line names no company in Setup is held, with **Take it for** on the SQL page:
   clicking it confirms that printed company name as one of your companies, and Fetch then reads such files for it. The
   names confirmed are listed in **Setup › Companies**, each with when and by whom, and **Remove** (two clicks) holds
   such files again from the next Fetch. A company's files are never read for another company. A document in two listings is
   kept once, with what each says (the cash book's description and cheque no., the customer payment listing's name and
   code). The same click reads SQL's general-ledger reports exported for the same dates: the **GL Journal of
   Transaction** (the account lines of every voucher, receipt, journal and invoice), the **GL Ledger** (Local - Ledger -
   Detail, Level 1 or V2) and the **Trial Balance** (This Month vs This Year with Opening) (`hrp/sqlgl.py`). A report that
   doesn't add up to its own totals is left out whole, with the reason. The lines are kept per document with versions
   (`hrp/ledger.py`): a document exported again with other lines becomes its next version, one SQL no longer prints in the
   journal's period is marked so, and nothing is ever edited or deleted. Each entry on the SQL page shows its lines and
   whether they balance and agree with the listing, and **Checks against SQL's reports** lists where the ledger or trial
   balance differ from the lines (said to be possibly out of date when a journal fetched after the trial balance changed
   documents in its dates: export the Trial Balance again for the same dates and Fetch it). Documents in SQL's journal
   with no listing this app reads (credit and debit notes, contra entries, cash sales and the like) are listed apart and
   checked by their account lines and the trial balance; those whose listing exists but wasn't fetched are listed so you
   can fetch it. A journal that moves the bank counts in the reconciliation from its lines once the bank
   account's GL code is set in Setup (pasting its detail grid still works); a signed-off month this changes is named in the
   preview and the activity log, and stays signed off. Fetch also reads a copy of SQL's **MyInvois Transaction** screen
   (click its grid, Ctrl+A, Ctrl+C, paste it into a new Excel workbook with its headings and save it in the exports folder
   under any name; an older copy without headings is read too). It is the company's whose TIN (Setup › Companies) it
   holds (`hrp/myinvois.py`): each e-Invoice is kept by its UUID, a later copy updates its status (an e-Invoice
   cancelled) and one it leaves out is kept. The company's own e-Invoices and self-billed PVs fill in the e-Invoice of the
   SQL document with the same number, so the checklist sees them validated (or cancelled); those received are matched to
   supplier invoices and payment vouchers, and the valid ones not found in SQL's books are listed on the
   **Accounting › e-Invoices** page (`hrp/einvoicebook.py`), with the Issued, Received and Self-billed tabs for a month and
   their Excel.
   e-Invoice details can still come from copy and paste of SQL's invoice grid.

   **Printed invoices** (`hrp/invoicepdf.py`): each customer invoice, debit note and credit note, and each payment voucher
   with a self-billed e-Invoice, has a button in the Print column of the e-Invoices page that opens it as a PDF laid out as SQL Account prints it,
   from SQL's account lines (fetch the GL Journal of Transaction covering its date first), with the company's header,
   footer, bank details, logo and signature from **Setup › Companies** and, once MyInvois validated it, the QR code with
   its UUID and the time it was validated. **All of the month**, on the Issued tab (its invoices, debit
   and credit notes) or the Self-billed tab, downloads as one zip, with a note of any that couldn't be printed and why. Beside each PDF, its print note says what the
   print check found (a line cut short, no QR code yet). A document that can't be printed says why instead (no account lines yet, lines that disagree with the listing, a date that differs).
6. **Books and checks** – SQL Account stays the books: nothing here creates or changes an accounting entry for a company
   kept in SQL. The **Books** page shows the books mirrored from SQL's reports (`hrp/books.py`, `hrp/finstatements.py`,
   `hrp/receivables.py`): the **trial balance** (with opening balances, checked against SQL's own trial balance), the
   **general ledger** of one account or all, the **profit and loss** account and the **balance sheet** (with the
   previous financial year's end beside it), **customers and suppliers** (who owes what, with its ageing) and the
   **statutory payables** check (`hrp/statutory.py`: what each payroll month withheld for KWSP, PERKESO, EIS, PCB and
   the like against what was paid by the due date, from the statutory accounts confirmed in Setup). **Excel** downloads the
   report on screen for the same dates (`hrp/booksexcel.py`). The financial year starts in the month set for the
   company in **Setup › Companies** (keep it the same as in SQL Account). A statutory payable not paid by its due day, or
   paid short, is a row in **Next up**. Each month's checklist has **SQL books agree with SQL Account**, which ticks itself
   when every document of the month is in SQL's journal and its listings, each balances and agrees with its listing,
   and SQL's trial balance agrees with the books here. The bank reconciliation counts each payment from its bank
   lines and, at the month's end, checks its book closing against SQL's balance on the bank account's GL code.
   On **Bank and reconciliation** one statement line can be linked to several payments (a bulk transfer), with a
   running total; book entries where **No money moved** (a voucher and its reversal) are confirmed with a reason; and a
   month signed off (with an optional note, the note the app writes and a declared **Prepared by**) is **locked**: its
   lines, matches, book opening and its payments' bank fields can't change until it is reopened with a reason
   (**Reopen month**, logged). **Print the reconciliation statement** gives a PDF with the code
   `BR-yymm-<company>-<last 4 digits>`, a keyed check and a QR (`hrp/bankrecpdf.py`, `hrp/formcode.py`); the signed copy
   is filed on the month's bank reconciliation checklist item.
7. **Audit pack** – **Before you print** lists what the month still needs: bank statements not imported, lines to
   explain, payments not complete and what each lacks, checklist documents missing, checklist items not done, payments
   paid but not in SQL (AISB), and files that won't print (emails, Excel, password PDFs, missing files). Click a line to
   go where it is fixed; it shows **Ready to print** once clear. Build one PDF per entity and month and print it; a
   statement not imported is listed in it under "Not included". Then **Yes, mark month as filed**, or **Mark month as
   filed** at the top of the company's month page (it warns first if something is still open, or the pack isn't built or
   is out of date, for a month filed outside the app). A filed month shows **Filed** with **Reopen**, and its past-due,
   missing and similar counts no longer show on the Overview. A joiner or leaver reminder that falls in a filed month
   goes into the next month still open instead (or, when there is none, once the next month is set up); one already in
   a filed month stays there, unless the start date or last day is changed: then it moves on in the same way.
   The pack has three books pages after the bank reconciliation: the SQL books check, the statutory payables check and
   the trial balance against SQL (possibly out of date when a later journal was fetched, as on the Books page).
   **Auditor package** builds a zip in the `exports` folder with a fresh pack, the month report, the original files and
   a `Books` folder of Excel files: the month's trial balance, general ledger, profit and loss, balance sheet,
   customers and suppliers, and statutory payables check.

**Months before tracking.** Each company has a **First month tracked** in Setup › Companies. Months before it are never
set up on their own and nothing in them counts as overdue; SQL documents from them are kept in the books but listed
apart as **Before tracking**, and their bank reconciliation can be marked **Reconciled before tracking**. **Tidy up
months before this** removes what was set up there with nothing in it.

A payment is **Complete** only when it is paid and every required document is uploaded, or already shown by what is
imported here: a linked SQL PV, OR or JV (print it from SQL), an e-Invoice SQL shows as validated and no refund or
credit note takes back, or its line on an imported bank statement. A payment past due and not paid yet says why: **Not on
Oct statement** once that statement is imported without it; until then **Waiting for SQL record** (AISB) or **Waiting for
Oct statement**. Statutory payments not paid by the 15th of the next month show **Past legal deadline**, and those paid
after it a note.

## Developer notes

- Python 3.14 with a private environment in `.venv` (see `requirements.txt`).
- Tests (each uses a throwaway records folder): `.venv\Scripts\python -m tests.smoke_test samples` and `.venv\Scripts\python -m tests.sql_test`.
- `samples\` and all records are excluded from git.
- Audit trail (`hrp/audit.py`): SQLite triggers record every change to every table (the whole row before and after) in
  the same save, sealed per save into a hash chain with who (the Windows user), what and why. Check it with
  `.venv\Scripts\python -m hrp.trail status` (or `verify` for the whole trail); changes made to `records.db` with another
  program are accepted with `.venv\Scripts\python -m hrp.trail accept "why"`. An update step that drops a column or
  rebuilds a table calls `audit.drop_triggers(con)` first (see the module's notes).
  In the app: **Filing › Audit trail** lists every entry (filters, search, Excel export, **Check the audit trail**,
  and accepting changes made outside the app); payments and recurring payments have a **History** section, and budget
  lines a **History** button. Audit pack covers carry the trail's check code, and each backup zip a `manifest.json`.
  **Check this pack** under Recent packs on the Audit pack page (`hrp/packcheck.py`) says whether the file is still the
  one built and what changed since in what it reads, each change with its trail entry; a pack's entry records what
  built it (program version, the day, and the trail entry and check code on its cover).
- Setup (`hrp/masters.py`, `hrp/appsettings.py`): companies, bank accounts (one MYR cash book each), recurring payments
  with salary advances, and general settings, each added, changed, stopped or (only while unused) deleted, with a reason
  for stop, use again and delete. Filed months never change: a change of **Payroll month runs until** (the cutoff day)
  that would move an SQL document or a joiner or leaver reminder in or out of a filed month is refused, naming what
  would move (reopen the month first if it really must change).
  A company added in Setup starts with a starter monthly checklist (`rules.STARTER`), its own to change, or replaced
  by a copy of another company's until a month is set up.
  **Setup › Move setup** (`hrp/setupfile.py`) saves the setup as one file: a template (the rules and a starter
  checklist) or everything (the companies and what belongs to them; recurring payments only when ticked), and imports
  one into a new install, previewed first and all or nothing.
  A record deleted in Setup can be put back (`hrp/restore.py`): **Put it back** on the delete in the Audit trail, or
  under **Show deleted** in its Setup list; previewed first, with a reason, refused when its key is taken or its company
  is gone.
- Payment types, document types and required documents (`hrp/rulebook.py`, update 20): kept in the records and edited
  in **Setup › Payments and documents**; required documents change from a payroll month on, for every company or one.
  Code asks `rulebook.get(con)` rather than `rules.py` for them (`rules.py` keeps the seed values).
- Monthly checklist, joiner and leaver reminders and matching words (`hrp/checklistbook.py`, update 21; Setup logic in
  `hrp/monthly.py`): kept in the records and edited in **Setup › Monthly work** and **Matching words**; checklist and
  reminder changes apply from a payroll month on and never reach a filed month. Code asks `checklistbook.get(con)`.
- Customers and suppliers and each company's chart of accounts (`hrp/partybook.py`, updates 22 to 24): entered in Setup
  by hand or with **Paste a list**, which also reads a list printed from SQL Account to a text file (page by page, with
  sub-accounts placed under their parent account). The chart shows as a flat list or as a tree under SQL's account
  groups, each group and parent account opening and closing; a recurring payment can be linked to a supplier or customer, and SQL
  entries keep their code, payment method, cheque number, document key and currency, so a supplier's code matches its
  vouchers first.
- Tests on made-up data only, safe to keep in git, each run as `.venv\Scripts\python -m synthetic_tests.<name>`:
  addresses_test, audit_trail_test, bank_rec_guard_test, bank_rec_opening_test, bank_rec_page_test, bank_rec_print_test, bank_rec_test, before_tracking_test, books_excel_test, books_test, budget_recurring_test, checklist_equivalence_test, checklist_test, dialog_shell_test,
  einvoices_groups_test, einvoices_page_test, extras_test, fetch_checks_test, financial_year_test, gl_reports_test, invoice_notes_test, invoice_pdf_test,
  journal_bank_test, ledger_fetch_test, ledger_store_test, masters_equivalence_test, menu_test, meta_pages_test, myinvois_amount_test,
  myinvois_test, pack_check_test, parties_test, payment_dialog_test, payroll_check_test, receivables_test, recon_bank_lines_fixes_test, recon_bank_lines_test,
  recon_review_fixes_test, register_checklist_test, restore_test, seed_names_test, settings_isolation_test, setup_test, sql_books_item_test,
  sql_doc_labels_test, sql_exports_test, sql_page_test, sql_typed_ref_test, stage1_leftovers_test, stage1_settle_test, states_test, statements_test, statutory_test, topbar_test, trail_view_test and types_test.
  `synthetic_tests.masters_equivalence_test --golden <file>` also compares this code's results with a snapshot taken on
  older code (`--write-golden <file>` on that code makes one); `synthetic_tests.checklist_equivalence_test --golden
  <file>` does the same for update 21.
