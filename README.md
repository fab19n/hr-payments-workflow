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
| `backups\` | Zip backups made from the Backup & log page |
| `seed.json` | Starting payees and accounts, read once on first start. An optional `"names"` gives the real names for the made-up related company and tenant in the built-in checklists (`rules.PLACEHOLDERS`), so they never sit in the program |

The app only listens on this PC (127.0.0.1) and makes no internet connections. Don't put `C:\HR-Records` inside OneDrive or
Google Drive.

## Backups

On **Backup & log**, type a password (at least 12 characters) twice and press **Make encrypted backup**. This writes
`HR-Records backup <date> (encrypted).zip` (AES-256) in the `backups\` folder, then opens it again and checks every file.
The password is typed each time; it is never saved or logged. **Backup on this PC only (not encrypted)** makes a plain zip.

**Backup folder (optional)** is where encrypted backups are also copied (saved in `settings.json` as `backup_dir`). Put it
inside your OneDrive folder, for example `C:\Users\<you>\OneDrive\HR-Backup`, and OneDrive uploads it. Only encrypted
backups are copied there; a plain backup stays on this PC. After you mark a month as filed, the app offers to make an
encrypted backup.

Only the contents of an encrypted backup are protected. The names of the files inside (the documents folder) can be seen
without the password, so avoid putting a person's name in a document's file name if the backup goes to OneDrive.

### Restore from an encrypted backup

1. Close HR Payments.
2. Open the zip with 7-Zip (Windows Explorer cannot open AES zips) and type the password. Without the password the backup
   cannot be opened.
3. Copy `records.db` and the `documents` folder from the zip into the records folder (`C:\HR-Records`), replacing what is
   there (keep a copy of the old folder first).
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
4. **Bank statements** – import each Maybank statement PDF. Lines are matched to payments automatically; explain the rest.
5. **SQL import** (AISB) – sign in to SQL Account yourself, export the PV / JV / Cash Book listing to Excel, and import it here.
   Each entry's doc no. is saved on the payment it records; estimated bills take SQL's actual amount. Entries in SQL but not
   in the tracker are listed so nothing is missed. Re-importing the same export is safe.
   A journal that moves the bank counts in the reconciliation once its lines (SQL's journal detail grid) are pasted on the SQL page
   and the bank account's GL code is set in Setup.
6. **Audit pack** – **Before you print** lists what the month still needs: bank statements not imported, lines to
   explain, payments not complete and what each lacks, checklist documents missing, checklist items not done, payments
   paid but not in SQL (AISB), and files that won't print (emails, Excel, password PDFs, missing files). Click a line to
   go where it is fixed; it shows **Ready to print** once clear. Build one PDF per entity and month and print it; a
   statement not imported is listed in it under "Not included". Then **Yes, mark month as filed**, or **Mark month as
   filed** at the top of the company's month page (it warns first if something is still open, or the pack isn't built or
   is out of date, for a month filed outside the app). A filed month shows **Filed** with **Reopen**, and its past-due,
   missing and similar counts no longer show on the Overview. A joiner or leaver reminder that falls in a filed month
   goes into the next month still open instead (or, when there is none, once the next month is set up); one already in
   a filed month stays there, unless the start date or last day is changed: then it moves on in the same way.

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
  for stop, use again and delete. Filed months never change.
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
- Tests on made-up data only, safe to keep in git: `.venv\Scripts\python -m synthetic_tests.audit_trail_test`,
  `.venv\Scripts\python -m synthetic_tests.trail_view_test`, `.venv\Scripts\python -m synthetic_tests.setup_test` and
  `.venv\Scripts\python -m synthetic_tests.types_test`, `synthetic_tests.checklist_test`, `synthetic_tests.parties_test`, `synthetic_tests.extras_test`, `synthetic_tests.restore_test` and `synthetic_tests.pack_check_test`. `synthetic_tests.masters_equivalence_test --golden <file>`
  compares this code's results with a snapshot taken on older code (`--write-golden <file>` on that code makes one).
  `synthetic_tests.checklist_equivalence_test --golden <file>` does the same for update 21.
