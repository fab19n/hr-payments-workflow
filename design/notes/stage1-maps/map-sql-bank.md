# Inventory: SQL import and bank reconciliation changes since b7d7fa0

I only read files. Nothing was created, changed, run or imported, and I did not touch C:\HR-Records.

**Commits in this area:**
- 3818373: fetch from the folder, every document's account lines kept and checked
- 80b74fc: months before tracking set aside, financial year setting, small bank charges
- 1285cc2: the recon-review fixes
- c4aa5e4: no-listing documents, Deleted in SQL, fetch quick wins
- afe3a08: vouchers counted by their bank lines, matched either way, checked against SQL's bank account
- 3030d67: another company's file held until confirmed, edited vouchers re-fetched
- 2cdf9b6: printed company names in Setup, stale trial balance

The app.js diff without whitespace is about 945 lines (the raw diff looks bigger because line endings changed). The parts that matter here are app.js 992–1390, 1392–1640, 2112–2190, 2874–2905, 3171 and 4250–4360. The server parts are app.py 1242–1330, 1363–1490, 1646–1837, 1929–2024, 2294–2501, 2874–2890 and 3231–3252, plus hrp/recon.py, hrp/sqlfetch.py, hrp/ledger.py 600–860 and 1386–1755, hrp/sqlimport.py 780–914, and hrp/statements.py 228–470.

Abbreviations below: **JoT** = SQL's GL Journal of Transaction. **Cash book account** = the company's main bank account, the one the SQL cash book is reconciled against.

## A. What the user sees now, with exact strings

### A1. SQL import page, top card (app.js 1597–1612)

**Intro note:**
> "Fetch (or paste) each SQL listing for the month: **Cash Book**, **Receipt Voucher**, **Payment Voucher**, **Journal** and **Customer Invoice**. Payments and receipts are matched to this tracker; …overlap is fine."

The old text started "Paste each SQL listing…".

**New block "Fetch exported listings (one click)"**, with this note:
> "Reads every SQL listing saved in **{folder}**, whatever the files are called, and shows what is new and what is already imported. In SQL: open the listing, then the arrow beside the print button, **Export to Microsoft Excel Workbook**, and save it in **SQL Drive on SQL Connect › Download**. It reads the Cash Book, Payment Voucher, Official Receipt, Journal Voucher, Customer Invoice, Sales Invoice and Customer Payment listings (not their GST layouts). It also reads SQL's **GL Journal of Transaction** (the account lines of every document), **GL Ledger** (Local - Ledger - Detail, Level 1) and **Trial Balance** (This Month vs This Year with Opening): export them for the same dates as the listings, and the lines are kept and checked against SQL's own figures. It also reads a copy of SQL's **MyInvois Transaction** screen: click its grid, press **Ctrl+A** then **Ctrl+C**, paste it into a new Excel workbook with its headings and save it in the same folder under any name."

**Folder setting:**
- A collapsed "Use another folder" section with the field "Folder the exports are saved in (leave empty for your Downloads folder)". Its placeholder is the current folder.
- Button "Save folder", which posts to /api/settings/sql-exports-dir. Toast "Reading your Downloads folder" or "Folder saved".
- Errors (app.py 2874):
  - "Give the folder as text."
  - "Give the full path of the folder, starting with the drive letter, for example C: and then the folders."
  - "That folder can't be found. Check the path, or leave it empty to use your Downloads folder."

**Primary button "Fetch from SQL exports":**
- While working it reads "Reading the folder…" and is disabled.
- When done, the page scrolls to the preview.
- Errors:
  - "The folder {folder} can't be found. Choose the folder your SQL exports are saved in."
  - "The folder {folder} can't be read: {OS error}"
  - "The exported files couldn't be read. Copy and paste the listings instead, and report this."

**Paste form:** the heading is now "Copy and paste" (it was "Copy and paste (easiest)"). New errors:
- When a MyInvois copy is pasted: "This is a copy of SQL's MyInvois Transaction screen: paste it into Excel, save it in the exports folder and use Fetch from SQL exports."
- When an uploaded file is too large: "This file is too large to read ({x.x} MB; at most 25 MB). Export a shorter period from SQL Account."
- When a GL report is uploaded by hand: "This is SQL's {GL Journal of Transaction|GL Ledger|Trial Balance}: save it in the exports folder and use Fetch from SQL exports."

### A2. What the fetch found (`sqlFetchReview`, app.js 2112; `sqlfetch.gather` 199–338)

**First line**, one of:
- "**{n} listing(s) read** from {folder}: {n} document(s), **{n} new**, {n} already imported."
- "No new SQL listing was found in {folder}."

Then, when reports were read, " **{n} report(s) of SQL's general ledger read.**". MyInvois adds " **MyInvois e-Invoices: {n}**." (that is another area).

**One row per listing read:** "{file} · {title}, {d Mon} to {d Mon}", and on the right "{n} new, {n} already imported[, {n} also in another file]".

**One row per report read:** "{file} · GL Journal of Transaction|GL Ledger|Trial Balance, {span}", and on the right "{n} documents, {n} lines" for a JoT or "{n} accounts" otherwise. A trial balance shows "as at {d Mon}" when it has no From date.

**Files not used.** The heading is "**{n} files not used**". Each line reads "{file}: {reason}". Every status and its exact reason:

- **other_company:** "This {title} is for {CODE} ({name}), not {CODE}."
- **unknown_company with a printed name (NEW):**
  > "This {title} is from a company not in Setup: "{printed name}" matches no company's name or registration number in Setup, so nothing was taken from it. If it is {CODE}'s, click Take it for {CODE}; otherwise correct the company's name or registration number in Setup › Companies, then fetch again."
  - It has the button "**Take it for {CODE}**".
  - The first click changes the button text to `Click again: "{printed name}" is {CODE}`.
  - The second click posts to /api/sql/take-company, shows the toast `Exports printed for "{name}" are taken for {CODE} from now on. Fetching again…`, and fetches again.
  - On records without update 36 (the update that adds the printed-names table), the button is not offered and the sentence ends "…Correct the company's name or registration number in Setup › Companies, then fetch again."
- **unknown_company with no printed name:** "This {title} prints no company name, so whose it is can't be told and nothing was taken from it. Export it again from SQL Account with the company name on it." There is no button.
- **too_large (NEW):** "too large to read ({x.x} MB; at most 25 MB). Export a shorter period." This is only for a workbook that looks like an SQL export. Any other large workbook is just counted under "other".
- **unreadable**, one of:
  - "This file couldn't be opened. Close it if it is open in Excel, then fetch again."
  - Any refusal from sqlreport or sqlgl, shown verbatim. New ones include:
    - "This {title} shows its amounts in {USD}, not ringgit (MYR). This app reads SQL's reports in ringgit only: export it again with the amounts in MYR."
    - "This {title} says it has {n} documents, but {m} could be read, so nothing was taken from it. Copy and paste this listing instead."
    - "This {title} says its total is …, but the documents read add up to …, so nothing was taken from it. Copy and paste this listing instead."
    - The GST layout, chart-of-accounts and "not a listing this app reads yet" messages.
    - About 25 GL-report refusals ("…so nothing was taken from it. Export it again.", sqlgl.py 235–558).
  - "This {title} has no dates in it, so there is nothing to keep."

**Take it for errors** (sqlfetch 73–107):
- "Only a company kept in SQL Account can take SQL's exports."
- "This export prints no company name, so it can't be taken for a company."
- `"{name}" already matches {CODE} in Setup, so there is nothing to confirm.`
- `"{name}" was taken for {CODE} before. Check which company the export is from in SQL Account.`
- "The records need update 36 to take an export for a company. Restart the app."

**Last line:** "Left alone: {n} file(s) imported before; {n} copy/copies of a file read; 1 other workbook that isn't an SQL listing or report / {n} other workbooks that aren't SQL listings or reports."

### A3. Preview card (`renderSqlPreview`, app.js 2134–2190)

**When nothing is new:** heading "Nothing new to import", a "Close" button, then the fetch review.

**When only reports or MyInvois copies were read (NEW):**
- Heading "SQL's general-ledger reports", muted "No new listing entries".
- The fetch review, then the account-lines box.
- Buttons [**Keep account lines**] and [Cancel]. The first is disabled when the box says the import is refused.
- The label is built by `applyLabel` (1415): "Keep account lines", "Keep MyInvois e-Invoices", or "Keep account lines and keep MyInvois e-Invoices".

**Listing preview after a fetch:**
- A warning when new rows fall in a signed-off month:
  > "New entries fall in {August 2026}, whose bank reconciliation is signed off: its book figures may change. Nothing is un-signed: check that month (those months) again after importing."
- The fetch review, the account-lines box, then "Check each suggested payment, then import. The new documents are listed first."
- After a fetch the column-mapping form is hidden. After a paste or file upload it still shows, with "Check the columns were read correctly…".

**"Records this payment" column:**
- New pill for a row before the first tracked month: "Before tracking, kept with SQL's books" (grey).
- An already-imported row before tracking shows only "Already imported", with no receipt picker.
- The unchanged note under a new row whose number is already linked: "Changed in SQL? This number is already linked to {payment} at {RM x}."

**Import label:** "Import {n} entries ({m} linked)", plus " and keep account lines" and/or " and keep MyInvois e-Invoices".

**Account-lines box (`sqlLedgerBox`, 1508–1536, built from `ledger.preview`, ledger.py 1466–1552):**
- Bold title "Account lines".
- When refused: "This company's books aren't kept in SQL Account, so SQL's account lines and reports can't be kept for it."
- "{n} documents, {n} lines: **{n} new**, {n} changed, {n} unchanged[, {n} back in SQL], {n} no longer in SQL."
- One row per report: "{file} · {title}, {dd/mm/yyyy-dd/mm/yyyy | as at dd/mm/yyyy | no period printed}". On the right, "{n} documents, {n} lines" for a JoT or "Checked against the account lines on import." otherwise.
- A JoT with no printed period adds: "No period printed: documents deleted in SQL can't be told from this file."
- Documents SQL no longer has: "**No longer in SQL** (deleted or renumbered there; kept here, marked): {doc} ({d Mon}[, linked to {payment}][, moved {RM x} on the bank][ {pill: {Month} signed off}]); …"
- Journals that start counting: a warning box "**{n} journal(s) will count in the bank reconciliation** (lines on {310-000}):". Under it, one line per journal: "{doc}, {d Mon}: {RM x} into/out of the bank[ (counted as {RM y} until now)][, once its listing is imported][ {pill warn: {Month} signed off}]".
- "The book figures of {months} will change. Nothing is un-signed: check those months again after importing."

### A4. Result toasts after import (app.js 4262–4278)

**Reports or MyInvois only:**
> "Kept the account lines of {n} documents from {n} report(s) of SQL's[; {n} difference(s) from SQL's reports, listed under Checks against SQL's reports]"

plus the MyInvois part, plus the signed-off part.

**Listings:**
> "Imported {n} entries; {m} linked to payments[, {k} already imported][; {b} bank lines matched][. Kept the account lines …][. Kept {n} MyInvois e-Invoice(s) …][. Changed in SQL, listed once at the new figure: {docs}][. {n} linked voucher was/vouchers were changed in SQL: see Changed in SQL][. The bank reconciliation of signed-off {months} changed: it stays signed off; check it again]."

### A5. Entry lists on the SQL page (1529–1596)

**Account-lines pill (`linesPill`, 1423)** on rows in Not linked, Corrections, Linked, Ignored, Before tracking and Journals and invoices. Clicking it toggles an inline row. The states, in priority order:

| Pill | Tone | When |
|---|---|---|
| No lines | grey | Not a button. A JoT read covered the date and book, but SQL has no document. |
| No longer in SQL | bad | The document is gone from SQL. |
| Lines don't balance | bad | Debits and credits differ. |
| Lines ≠ amount | warn | The lines don't agree with the listing amount. |
| Changed in SQL (v{n}) | warn | Version above 1. |
| "{n} line(s)" | warn | An account isn't in the chart, or there are other warnings. |
| "{n} line(s)" | ok | Everything checks. |

**Inline lines row (`ledgerDocView`, 1450, from GET /api/ledger/doc):**
- Header: "{doc}[ · {book label}]", a pill "No longer in SQL" (bad) or "Replaced" (grey), and the note "Version {n}, {d Mon yyyy}, from SQL's GL Journal of Transaction|the journal lines pasted|the journal lines pasted before ({file}), read {yyyy-mm-dd hh:mm:ss}".
- Table: Account | Description | Debit | Credit.
- Each account shows "{code} {name}". Accounts unknown to the chart get the warn pill "Not in chart". Bank accounts get the grey pill "Bank" and their row is highlighted.
- A Total row.
- The checks below are warning sentences, or "The lines balance and agree with the listing.".
- A collapsed "Earlier versions ({n})" section.
- Check sentences (ledger.py 618–747):
  - "{doc} is no longer in SQL's Journal of Transaction: it was deleted or renumbered in SQL."
  - "Its lines don't balance: the debits add up to {x} and the credits to {y}."
  - "The lines on the bank account have debits/credits of {x} and move money in/out of {y} net, but the listing has {z} money in/out (checked on the bank account's lines)."
  - " SQL's lines match an earlier listing of this document." (appended to the line above when it applies)
  - "SQL's journal dates it {iso}, but the listing dates it {iso}."
  - "It is in the Bank Journal|… of SQL's journal, but the listing has it as a payment or receipt|a journal|an invoice."
  - "Enter the chart of accounts in Setup to check the account codes."
  - "Not in the chart of accounts: {codes}."
  - "Can't tell whether the lines agree with the listing: …" (three variants)
- These amounts have no "RM".
- Error when no lines are kept: "SQL's Journal of Transaction hasn't given the lines of this document yet." Another error: "The records need update 26 to show account lines. Restart the app."

**"Changed in SQL" card (NEW, 1542; `sqlimport.changed_linked`).** It sits above "SQL entries not linked…".
- Note: "These vouchers were edited in SQL after they were linked to a payment: the latest fetch gives another amount or date. The link stays on the earlier entry until you move it. Moving it keeps the earlier entry, marked as replaced."
- One item per voucher: "**{doc}** changed in SQL {from 1,163.20 to 1,136.20[, dated dd/mm/yyyy before, dd/mm/yyyy now]}."
- Then: "Linked to {payment} ({Month yyyy}), whose amount is {RM}."
- Followed by either "SQL's GL Journal of Transaction (version {n}) already has {RM}." or "SQL's GL Journal of Transaction kept here still has {RM}: fetch it again for the same dates so the account lines follow."
- A checkbox, shown only when the payment amount equals the old voucher amount: "Also change the payment's amount from {RM old} to {RM new}".
- Button "Move the link to the new amount". It has no confirm step.
- Toast: "{doc}: the link of {payment} moved to the amount SQL gives now, and the payment's amount changed with it|; the payment's amount is as it was[; n bank lines matched]".
- Errors:
  - "{doc} has no later entry from SQL to move its link to, or it changed since. Reload the SQL page."
  - "The payment's amount ({x}) isn't {doc}'s old amount ({y}), so it can't be changed with the link. Move the link alone, then change the payment's amount yourself if needed."
  - The update-36 restart message.
- The new entry is left out of "not linked" and "corrections" while it waits here.

**Rules for edited vouchers:**
- An edited voucher whose earlier entry is linked to nothing is replaced automatically at import. That earlier entry gets `status=superseded`.
- A voucher edited back to a figure it had before revives that earlier entry.
- A voucher listed on several rows, an ignored one, a journal and an invoice are never paired.

**"Replaced by a later version from SQL · {n}" (NEW, 1550, collapsed):**
- Note: "Earlier entries of vouchers edited in SQL. They are kept as they were read; the later entry is the one that counts."
- Table: Doc No | Date (with "now {d Mon}" when the date moved) | Description | Amount then | Amount now.

**"Before tracking ({n})" (NEW, 1589, collapsed, read-only, no actions):**
- Note: "These SQL entries are from months before {July 2026}, the first month tracked here. They are kept with SQL's books (their account lines and the checks against SQL's reports) but are not tracked as payments, so nothing asks you to link them."
- Table: Doc No | Date | Description (+ lines pill) | Amount.
- Rule (db.py 638): an entry counts as before tracking only when both its date month and the month its description names are before the first tracked month. A row dated 30 Jun with "RENTAL JUL 26" is tracked.
- "Create payments for all" skips these.

**"Linked to payments" and "Ignored":** both have lines pills now.
- Unlink toast now ends "…back under Before tracking" or "SQL entries not linked".
- Un-ignore toast: "{doc} is back under Journals and invoices|Before tracking|SQL entries not linked[. The bank reconciliation of signed-off {months} changed: it stays signed off; check it again]".
- Payment-removal toast adds "; {docs} back under Before tracking on the SQL page".

**"Journals and invoices" card (renamed from "Journals and customer invoices"):**
- Lines pill on each row.
- The Checklist item column shows the grey pill "Before tracking" for documents before tracking, with no link or create controls.
- Empty text: "Fetch SQL's Journal Voucher and Customer Invoice listings on this page to see them here."
- "Moves {RM} into/out of the bank, so it counts in the bank reconciliation." now also comes from fetched JoT lines.
- Linking a journal with no bank lines fails with: "{doc} has no lines on the bank account, so it moves no money and can't be linked to a payment. Fetch SQL's GL Journal of Transaction (or paste its lines), and set the bank account's GL code in Setup."
- The invoice print bar, Print buttons and the MyInvois column belong to other areas.

**"Imported files":** each row is "{filename} · {n} entries, {m} linked · {n} lines".
- A fetch is named "SQL exports fetched {yyyymmdd-hhmm}.csv".
- A reports-only fetch is named "SQL reports fetched {yyyymmdd-hhmm}: {file}, {file}".

### A6. "Checks against SQL's reports" card (NEW, `sqlChecksCard` 1463–1506)

The card is hidden when nothing has been read and nothing is orphaned.

**Intro:**
> "The latest of SQL's GL Journal of Transaction, GL Ledger and Trial Balance fetched, checked against the account lines kept. Not checked: Period To Date and opening balances against the lines (SQL's trial balance moves earlier profit and loss into retained earnings on its From date), and anything after the dates the journals read cover."

**Section heading, per report:** "GL Journal of Transaction|GL Ledger|Trial Balance", with muted "{file} · {d Mon} to {d Mon}|as at {d Mon} · read {iso}".

**JoT section:**
- "{n} documents ({n} new, {n} changed, {n} unchanged[, {n} back in SQL], {n} no longer in SQL), {n} lines."
- The no-period note.
- "Moved by more than 180 days, so the number may have been used again in SQL: {docs}."
- One line per changed signed-off month: "The bank reconciliation of {Month}, signed off, changed: money in {RM} → {RM}, money out {RM} → {RM}. It stays signed off; check it again."

**Ledger and trial balance sections:**
- When there are warnings, a table: Account | What differs | SQL's figure | The lines | Difference. Otherwise the ok pill "No differences".
- Then the ok, "Not checked: …" and info sentences (ledger.py 912–1188). For example: "{n} accounts agree with the lines.", "No GL Journal of Transaction read covers …", "SQL's trial balance counts profit and loss from its From date (dd/mm/yyyy), so it moved a profit of {x} from earlier into retained earnings. No document carries that move."
- When a later JoT changed documents in the trial balance's dates, a grey banner:
  > "**Possibly out of date** A GL Journal of Transaction read after this trial balance changed documents in its dates, so these differences may only be the trial balance being old. Export SQL's Trial Balance again for the same dates ({d Mon} to {d Mon}) and Fetch it."

**"In SQL's journal but no listing fetched · {n}":**
- Note: "Fetch SQL's listing these are in on the SQL import page, so each can be matched to a payment."
- Table: Doc No | Date | Section | [Lines].
- The Section column shows the raw book code: "bank", "general", "sales" or "purchase".

**"No listing this app reads yet · {n}" (collapsed):**
- Note: "No listing this app reads yet: checked by their account lines and SQL's trial balance. These are in other sections of SQL's journal (cash sales, credit or debit notes, deposits, refunds, contra and the like), so nothing asks for their listing."
- Table: Doc No | Date | [Lines].

**"Listing entries missing from SQL's Journal of Transaction · {n}":**
- Note: "Dated inside a journal read, but not in it: deleted or renumbered in SQL. If SQL no longer has one, click Deleted in SQL: it is kept here, listed under Ignored, and left out of the checks (Un-ignore puts it back)."
- Table: Doc No | Date (+ pill "No longer in SQL") | Amount | action.
- The action is the button "**Deleted in SQL**" when nothing is linked; otherwise muted "Linked to a payment: unlink it first".
- Deleted in SQL has no confirm step.
- Toast: "{docs} marked as deleted in SQL; listed under Ignored[. The bank reconciliation of signed-off … check it again]".
- Errors:
  - "Choose the entries SQL no longer has."
  - "Those entries aren't all of one company's SQL listings."
  - "{doc} is listed on several rows: confirm all of its rows as deleted in SQL together (reload the SQL page and use its Deleted in SQL button)."
  - "{docs} can't be confirmed as deleted in SQL: only an entry SQL's GL Journal of Transaction no longer has, linked to no payment, can (unlink it first if it is linked)."

**Footer:** "{n} document(s) before the first month tracked has/have no listing or is/are missing from the journal; months before tracking aren't checked."

### A7. Setup › Companies drawer, "Printed company names" (NEW, app.js 2874–2905, app.py 3231–3252)

- Heading "Printed company names".
- Note: "Names SQL Account prints on its exports that match no company in Setup, confirmed as {CODE}'s with **Take it for {CODE}** on the SQL page. Fetch takes files printing them for this company."
- Table: Name as printed | Confirmed (dd/mm/yyyy at hh:mm) | By (or muted "Not recorded") | [Remove].
- Removing takes two clicks. The first changes the button to "Click again to remove" and shows the note: `Removing "{name}": files printing it are held again on the next Fetch, until Take it for is clicked again.`
- Toast after removal: `"{name}" removed. Files printing it are held again on the next Fetch, until Take it for is clicked again.`
- Empty state: "None confirmed." Old records: "The records need an update for this. Restart the app."

### A8. Bank statements, year view and month panel (app.js 1007–1149, recon.py)

**Book closing note (recon.py 295):** "Fetch SQL's cash book listing[ for {Month yyyy}]". It was "Paste SQL listing". The panel adds " on the SQL import page."

**Year card note (NEW, recon.py 574):**
> "{n} month(s) this year still count(s) some receipts or payments by their listing amount: fetch SQL's GL Journal of Transaction to count them by their bank lines."

**Status cell of a year row:** when the book figures changed under a sign-off, the "Reconciled" pill is followed by a red note:
> "{Book figures changed since sign-off: confirm again}: book closing {RM} at sign-off, {RM} now (in {RM} → {RM}, out {RM} → {RM})"

**SQL check at the top of the month panel and in the review (`rcSqlCheck`; recon.py 421–464).** It appears only for the cash book account of a company kept in SQL.
- When it agrees: the ok pill "Agrees with SQL's bank account {310-000}".
- When it differs: the bad pill "Check against SQL" followed by "Differs from SQL's bank account {code} by {RM}: the book closing here is {RM}, SQL's balance on dd/mm/yyyy is {RM}".
- When skipped, plain text "Not checked against SQL's bank account: " followed by one of:
  - "a month before tracking began here"
  - "set the bank account's GL code in Setup"
  - "there is no book closing yet"
  - "no opening balance of {code} is kept: fetch SQL's trial balance or GL ledger"
  - "SQL's GL Journal of Transaction kept doesn't cover dd/mm/yyyy to dd/mm/yyyy: fetch it for those dates"
  - "SQL's GL Journal of Transaction kept doesn't include the Bank Journal [or the General Journal] for {docs, up to 5}[ and {n} more]: fetch it again with all its sections"
  - "SQL's balance of {code} on dd/mm/yyyy can't be worked out"

**Panel and review listing note (recon.py 655–670):**
- "{n} receipt(s) or payment(s) this month is/are still counted by its/their listing amount: fetch SQL's GL Journal of Transaction to count them by their bank lines.[ {k} of them was/were pasted again after the journal was read (edited in SQL since), so the lines kept are out of date.]"
- Or: "Receipts and payments are counted by their listing amounts: set the bank account's GL code in Setup to count them by their lines on the bank account."
- Plus, for documents SQL no longer has: "{g} receipt(s) or payment(s) this month is/are no longer in SQL, so it is/they are counted by its/their listing amount for now: if SQL deleted it/them, click Deleted in SQL on the SQL import page (unlink its payment/their payments first) to leave it/them out. Fetching the journal again won't change this."

**Left-out notes:**
- The journals note now ends "Fetch SQL's GL Journal of Transaction to count a journal that moves the bank."
- NEW: "Not counted: {n} receipt or payment / receipts or payments whose lines in SQL don't touch this bank account (paid from another account)."
- The old note "Paste only the bank's cash book listing…" now reads: "For the reconciliation, fetch only the bank's cash book listing: a voucher paid from petty cash or a card would count as a bank movement."

**Banner for a month signed off before the change (`rcChanged`, 1026; recon.py 341–383):** a warn banner under the sign-off.
- Bold title "Book figures changed since sign-off: confirm again".
- Text: "SQL's receipts and payments now count by what each one posted to the bank account, not by its listing amount."
- Table: | At sign-off | Now, with rows Money in, Money out and Book closing.
- Button "Confirm again". It is disabled unless the new figures agree with the bank, and then shows "The new book closing differs from the bank by {RM ±x}: undo the sign-off and review the month." or "The book closing can't be worked out."
- Toast after confirming: "Sign-off confirmed again with the new book figures."
- Errors: "This month isn't marked as reconciled."; "Nothing to confirm: this month's book figures haven't changed since it was signed off."
- The pill stays "Reconciled". The month is judged by its sign-off figures until it is confirmed again.
- Only months signed off before update 32 qualify, from the first tracked month on, on the cash book account, and not yet re-confirmed.
- The checklist "reconciled" item then reads "{account}: book figures changed since sign-off: confirm again" or "…book figures changed since sign-off and now differ from the bank by {RM}: review the month again" (db.py 1515). The audit pack prints the old and new figures (auditpack.py 450).

**Book opening input:** now uses `LT.typedAmount` (app.js 175).
- Accepted: digits, well-formed thousands commas, at most 2 decimals, and a leading "-" or (brackets) for a negative.
- Refused, for example: "25abc", "1.2.3", "1,2345", "1.234".
- Page message: "Choose the month and type the balance as a number."
- Server messages: "Type the book balance as a number." and "Choose the month the account's books start from: between January 2015 and a year from now."

### A9. Statement review (app.js 1151–1389; recon.py 732–876; statements.py 128–470)

**Date tick:** "Bank date differs by {n} days: keep the voucher|payment date ({d Mon})". It now shows on a matched or explained line only while the line is not confirmed (`needs_date_tick`). Applying a confirmed line left as it is changes nothing, not even the payment's paid date.

**"Explained by" sort and search:** these now treat matched lines as explained, because rows carry `payment_id`.

**"Open payments" in the line dropdown:** a payment whose SQL voucher posted several bank lines (`bank_parts`) is offered when either:
- one of its open lines equals this line (a fee line can go to a receipt even though the money goes the other way), or
- nothing is linked yet and its net goes this line's way.

**New suggestion reasons:**
- "Same as what reached the bank (after the bank's charge), name matches: {payee}, same day as due"
- "Same as the bank line still open on {OR-…}, same day as due"

**The SQL check and listing note** from A8 are shown under the status pill.

**Matching rules (`_by_bank_lines`):** one of these is taken, never both, never a fee line on its own, and never a line named like another payment that is still to match:
- (a) named lines that add up to the net amount;
- (b) one-for-one: the largest line on a named line, plus a fee within 3 days whose wording matches the bank-charge pattern (BANK_CHARGE: SERVICE CHARGE, COMMISSION, TT CHARGES and so on) or that was marked "Bank charge", where the fee is less than 1/10 of the main line;
- (c) a named line plus a charge line that together equal one combined SQL bank line.

### A10. Counting rules that change the numbers

From the company's first tracked month (rule "lines"), a receipt or payment voucher with current JoT lines counts as the net of its lines on the bank GL code.
- A voucher with lines that don't touch that code is left out (other_bank).
- These still count at their listing amount: no lines yet, a listing newer than the lines, documents SQL no longer has (until confirmed), and months before tracking.
- A voucher listed on several rows for different payments counts each row at its listing amount, and the rest (the fee) goes on its first row.
- An entry confirmed Deleted in SQL is left out.
- Every import, Deleted in SQL and Un-ignore reports the signed-off months it moved. Nothing is ever un-signed.

### A11. Code gaps the redesign should settle (found while reading)

1. **The explain drawer and the dropdown disagree.** The drawer's `LT.linkList` (app.js 150) still filters by direction and amount only. A receipt's fee line (money out) does not list the receipt unless "Also show money the other way…" is ticked, even though the dropdown offers it.
2. **Dead handler.** `data-sql-ignore-ids` (4331) has no button; `orphans().can_ignore` is unused.
3. **Raw section codes.** The "Section" column in the checks card prints "bank"/"general" instead of `BOOK_WORDS` ("the Bank Journal" and so on).
4. **Fetch intro leaves out two listings.** It omits the Supplier Invoice and Supplier Payment listings, which `sqlreport.READS` now reads.
5. **Deleted in SQL isn't visible under Ignored.** An entry confirmed Deleted in SQL looks like any ignored entry, except through its lines pill. The `deleted_in_sql` date is in the row data.

## B. What the existing boards cover, and what is missing or wrong

**Sql.dc.html** already has the fetch flow: folder, Use another folder, reading, found, nothing, error, status chips and legend, Fetch again. It was drawn ahead of some code.

Wrong or missing:
- **"Company not in Setup" row:**
  - It has an "Open Setup › Companies" action and old wording ("…which matches no company's … so it was left out. Correct…").
  - There is no **Take it for AISB** button, no second-click "Click again: … is AISB" state, and no toast followed by an automatic re-fetch.
- **File statuses:**
  - `too_large` is missing.
  - The other-currency reason is missing.
  - The legend lists 6 statuses; the code has 7.
- **Reports in the review:**
  - The GL Ledger row puts "1 report of SQL's general ledger read." into its meta. The code puts it in the header line.
  - No GL Journal of Transaction row ("{n} documents, {n} lines") and no Trial Balance row.
- **Missing from the preview:**
  - the Account lines box (counts, files, "No longer in SQL" list, journals that will count, signed-off warning);
  - the signed-off-months note;
  - the "Before tracking, kept with SQL's books" pill;
  - the "… and keep account lines" import label;
  - the reports-only preview with "Keep account lines".
- **Reads text:** it says "e-Invoice details still come from copy and paste below". The app now reads a MyInvois copy from the folder.
- **Import result:** it lacks the account-lines, changed, replaced and signed-off parts.
- **After import:** PV2611-003 (1,136.20 against the linked 1,163.20) lands in "not linked" with a "Changed in SQL?" note. Now it belongs in the **Changed in SQL** card.
- **Missing cards and pieces:**
  - lines pills;
  - the inline account-lines row;
  - Checks against SQL's reports;
  - Changed in SQL;
  - Replaced by a later version;
  - Before tracking;
  - Deleted in SQL and its toast;
  - "Journals and invoices" (the board still says "…customer invoices") with its new empty text and the "Before tracking" pill;
  - Imported files "· {n} lines".
- **Toasts:** the Unlink and Un-ignore destinations are missing.

**Bank.dc.html and DarkBank.dc.html** (same logic):
- The book note still says "Paste SQL listing" (and "…for {Month}"). It should be "Fetch SQL's cash book listing" plus " on the SQL import page.".
- The SQL note still says "Paste only the bank's cash book listing…".
- The journals left-out note already uses the new wording.
- Missing:
  - the SQL check (agrees, differs and skipped variants, including "a month before tracking began here" on the June 2026, May 2026 and December 2025 panels);
  - the year listing note and the month listing notes;
  - the `other_bank` note;
  - the changed-since-sign-off row note, banner, Confirm again (enabled or disabled with its reason) and toast.
- The opening check regex `/^-?\d+(\.\d+)?$/` after removing commas does not match `typedAmount`: brackets should be accepted, while malformed commas and a third decimal should be refused.

**BankReview.dc.html:**
- A matched row always shows the date tick when its dates differ (`tickOf` in doneRow). In the `after-apply` state, line 5 (Robin, 15 days, now confirmed) wrongly still shows "Bank date differs by 15 days…".
- "Open payments" uses the old direction-only rule.
- The new suggestion reasons are missing.
- The SQL check and listing note are missing under the status.
- There is no state showing a voucher matched by its bank lines (gross line plus fee, or net).

**SetupCompanies.dc.html:** the "Printed company names" section is missing (also the financial year start and print settings, which are other areas).

**Canvas inconsistencies to settle:**
- The AISB first month is '2025-01' on SetupCompanies but FIRST '2026-07' on Bank (Bank's July 2026 is assumed below).
- Voucher numbering differs: PV-0912/OR-1030 on the bank boards, PV2610-021 on Sql.

## C. Proposal

### New board: `SqlBooks.dc.html`, "SQL import · account lines and checks"

Size 1440×3200, at x 6680, y 12900, right of note n2. Widen title t2 to maxW 8200. It is the lower half of the SQL page for AISB and uses the Sql board's samples.

**States:**

1. **`lines`:** the lists with pills.
   - PV2610-019 KWSP "2 lines" (ok).
   - CB2610-041 Bank charges "2 lines" (warn, because 900-011 is not in the chart).
   - OR2610-006 Fund received "Lines ≠ amount", with the check "The lines on the bank account have debits of 49,950.00 and move money in of 49,950.00 net, but the listing has 50,000.00 money in (checked on the bank account's lines)."
   - PV2611-008 7 Nov 250.00 "No longer in SQL".
   - PV2609-027 "No lines".
2. **`lines-open`:** PV2611-003 expanded.
   - Header: "Version 2, 4 Nov 2026, from SQL's GL Journal of Transaction (GL Journal Oct-Nov.xlsx), read 2026-11-18 10:42:13".
   - Lines: 900-120 Electricity, Dr 1,136.20; 310-000 Maybank current [Bank], Cr 1,136.20; Total 1,136.20 / 1,136.20.
   - Check: "The lines balance and agree with the listing."
   - "Earlier versions (1)" open: version 1, read 2026-11-12 16:04:10 from GL Journal Nov.xlsx, at 1,163.20 / 1,163.20.
3. **`checks`:**
   - **JoT section:** GL Journal Oct-Nov.xlsx · 1 Oct to 12 Nov. "214 documents (9 new, 2 changed, 202 unchanged, 1 no longer in SQL), 642 lines."
   - **Ledger section:** GL Ledger.xlsx shows "No differences" and "48 accounts agree with the lines."
   - **Trial balance section:** Trial Balance Nov.xlsx · 1 Jan to 12 Nov, with one warning row: "900-010 Bank charges: the trial balance's Month To Date nets 85.00, the lines dated 01/11/2026-12/11/2026 84.00." (SQL 85.00 | lines 84.00 | -1.00).
   - **No listing fetched:** JV2611-006 · 10 Nov · general (the October JV listing doesn't cover it).
   - **No listing this app reads yet · 2:** CS2610-001 14 Oct, CN2610-002 28 Oct.
   - **Missing from the journal · 1:** PV2611-008 · 7 Nov [No longer in SQL] 250.00 [Deleted in SQL].
   - **Footer:** "3 documents before the first month tracked…".
4. **`checks-stale`:** the trial balance warnings with the grey "Possibly out of date" banner.
5. **`deleted`:**
   - Toast: "PV2611-008 marked as deleted in SQL; listed under Ignored".
   - The row is now under Ignored with its pill.
   - Variant: the row is linked, showing "Linked to a payment: unlink it first".
6. **`changed`:**
   - The Changed in SQL card for PV2611-003: "changed in SQL from 1,163.20 to 1,136.20."; "Linked to Electricity bill (October 2026), whose amount is RM 1,163.20. SQL's GL Journal of Transaction (version 2) already has RM 1,136.20."
   - The checkbox "Also change the payment's amount from RM 1,163.20 to RM 1,136.20".
   - Variant `changed-stale-lines`: "…kept here still has RM 1,163.20: fetch it again…".
7. **`moved`:** toast "PV2611-003: the link of Electricity bill moved to the amount SQL gives now, and the payment's amount changed with it". The Replaced card then holds PV2611-003 (1,163.20 → 1,136.20).
8. **`replaced`:** PV2611-009 · 6 Nov · Courier charges October · then 168.50 · now 186.50. It was auto-replaced; the import toast includes "Changed in SQL, listed once at the new figure: PV2611-009".
9. **`before-tracking`:**
   - Before tracking (2): OR2606-004 3 Jun Rental received June +1,800.00 [3 lines]; PV2606-018 30 Jun Office rental June 6,500.00 [2 lines].
   - In Journals and invoices, JV2606-002 shows the "Before tracking" pill.
10. **`no-reads`:** the card is hidden and the pills are absent.

### Changes to `Sql.dc.html`

- **Read files list:** add "GL Journal Oct-Nov.xlsx · GL Journal of Transaction, 1 Oct to 12 Nov | 214 documents, 642 lines" and "Trial Balance Nov.xlsx · Trial Balance, 1 Jan to 12 Nov | 52 accounts". Move "3 reports of SQL's general ledger read." into the header line.
- **Unused files:**
  - New row "PV Listing Nov (2).xlsx": the unknown_company reason with the printed name `"AISB (M) SDN BHD (1331234-K)"`. That name escapes both the name and registration-number matching for "AISB Sdn Bhd" / "201901023456 (1331234-K)". The row has [Take it for AISB].
  - Keep ZZ Trading with the new wording. It also gets the button, and the owner must not click it.
  - Add "GL Journal 2026.xlsx: too large to read (31.4 MB; at most 25 MB). Export a shorter period."
  - Add "PV Listing USD.xlsx" with the currency reason.
- **States to add:**
  - `take-confirm`: the second-click label.
  - `taken`: the toast plus the re-fetched review with that file now read.
  - `found` gets the Account lines box: "214 documents, 642 lines: 9 new, 2 changed, 202 unchanged, 1 no longer in SQL."; the files; "No longer in SQL … PV2611-008 (7 Nov, moved RM 250.00 on the bank)."; and "1 journal will count in the bank reconciliation (lines on 310-000): JV2611-004, 8 Nov: RM 5,001.00 out of the bank". That matches the board's own JV lines 320-000 5,000 + 900-010 1 against 310-000 5,001. The import label becomes "Import 9 entries (7 linked) and keep account lines".
  - `reports-only`.
  - `found-signed-off`: new PV2608-031 29 Aug gives "New entries fall in August 2026, whose bank reconciliation is signed off…".
  - The preview row for OR2606-004 shows "Before tracking, kept with SQL's books".
- **Text fixes:**
  - Rename the card to "Journals and invoices" and use the new empty text.
  - Imported files: "SQL exports fetched 20261118-1042.csv · 9 entries, 7 linked · 642 lines".
  - Fix the reads text (MyInvois copy; the supplier listings, see A11.4).
  - Import result text as in A4.

### Changes to `Bank.dc.html` (mirror them in `DarkBank.dc.html`)

All figures reconcile with the board's existing ST and MOV data.

- **October (default):**
  - Pill "Agrees with SQL's bank account 310-000". SQL's balance on 31/10/2026 equals the book closing RM 33,618.35.
  - Add the note "Not counted: 1 receipt or payment whose lines in SQL don't touch this bank account (paid from another account)." This is PV-1029, paid from petty cash; it is left out, so no figure changes.
  - Use the new SQL note wording.
- **`october-sql-differs`:**
  - Story: the 8 Oct SERVICE CHARGE was booked in SQL as JV2610-012 (Dr 900-010 48.00, Cr 310-000 48.00) and its listing hasn't been fetched yet.
  - Pill "Check against SQL", then "Differs from SQL's bank account 310-000 by RM 48.00: the book closing here is RM 33,618.35, SQL's balance on 31/10/2026 is RM 33,570.35".
- **`october-listing`:**
  - The JoT kept covers 1 Jan to 24 Oct only, so PV-1031 and PV-1033 (30 Oct) have no lines.
  - Panel: "2 receipts or payments this month are still counted by their listing amount: fetch SQL's GL Journal of Transaction to count them by their bank lines."
  - Year card: "1 month this year still counts some receipts or payments by their listing amount: fetch…".
  - Check: "Not checked against SQL's bank account: SQL's GL Journal of Transaction kept doesn't cover 01/01/2026 to 31/10/2026: fetch it for those dates".
  - The figures don't change.
- **`august-changed` (can confirm again):**
  - Story: OR-0814 (Klinik Sehat · invoice 1019, 20,000.00) is on two rows of SQL's Cash Book listing (20,000.00 in, and its bank charge 36.25 out), both linked to the receipt. Counted by its lines it is one net item, +19,963.75.
  - Table: Money in RM 38,500.00 → RM 38,463.75; Money out RM 43,939.60 → RM 43,903.35; Book closing RM 96,000.00 → RM 96,000.00.
  - "Confirm again" is enabled.
  - Year row note: "Book figures changed since sign-off: confirm again: book closing RM 96,000.00 at sign-off, RM 96,000.00 now (in RM 38,500.00 → RM 38,463.75, out RM 43,939.60 → RM 43,903.35)".
  - Then the `reconfirmed` toast.
- **`august-changed-differs` (cannot confirm again):**
  - Story: PV-0827 was edited in SQL after the sign-off from 1,000.00 to 1,200.00, and its JoT lines now count 1,200.00.
  - Figures: out RM 43,939.60 → RM 44,139.60; closing RM 96,000.00 → RM 95,800.00.
  - The button is disabled with "The new book closing differs from the bank by RM 200.00: undo the sign-off and review the month."
  - This state-only variant moves the later book closings: September RM 89,018.35, October RM 33,418.35.
- **November book note:** "Fetch SQL's cash book listing".
- **Before-tracking panels:** the June 2026, May 2026 and December 2025 panels get the skip text "…a month before tracking began here".
- **Opening field:** follows the `typedAmount` rule.

### Changes to `BankReview.dc.html`

- **Date tick:** show it on a done row only while it is unconfirmed. This fixes `after-apply` line 5.
- **Open payments:** use the open-lines rule.
- **SQL check and listing note:** add both under the status pill.
- **New data set "September 2026", Maybank current.** It reconciles with Bank ST cur:2026-09: open 92,418.35? No: opening 96,000.00, in 12,000.00, out 15,581.65, closing 92,418.35, 9 lines.

| # | Date | Line | Amount | Balance | Explained by |
|---|---|---|---|---|---|
| 1 | 2 Sep | IBG CR RENTAL TENANT | +2,800.00 | 98,800.00 | OR-0902 Rental received |
| 2 | 5 Sep | IBG DR OFFICE RENTAL | −6,500.00 | 92,300.00 | PV-0905 |
| 3 | 12 Sep | IBG DR TNB ELECTRICITY | −1,290.00 | 91,010.00 | PV-0911 |
| 4 | 15 Sep | PERKESO AUG CONTRIBUTION | −755.40 | 90,254.60 | PV-0914 |
| 5 | 18 Sep | TT CR KLINIK SEHAT INV 1031 | +9,200.00 | 99,454.60 | OR-0918 Klinik Sehat · invoice 1031 |
| 6 | 18 Sep | INWARD TT CHG | −36.25 | 99,418.35 | the same OR-0918 |
| 7 | 26 Sep | DUITNOW TRF FIELD WAGES | −2,500.00 | 96,918.35 | PV-0922 Field wages · September 7,000 |
| 8 | 26 Sep | DUITNOW TRF FIELD WAGES | −2,500.00 | 94,418.35 | PV-0922 |
| 9 | 26 Sep | DUITNOW TRF FIELD WAGES | −2,000.00 | 92,418.35 | PV-0922 |

- OR-0918's lines in SQL: Dr 310-000 9,200.00 / Cr Klinik Sehat 9,200.00 / Dr 900-010 Bank charges 36.25 / Cr 310-000 36.25.
- The book side counts the receipt as net +9,163.75. Sep MOV becomes [11,963.75, 18,745.40], including the uncleared PV-0912 3,200. Book closing stays RM 89,218.35 and only that internal pair changes. September's SQL check agrees.
- **State `september`:** everything confirmed; line 6 is explained by the receipt.
- **State `september-fee-open`:** line 6 is still open. "INWARD TT CHG" does not match the bank-charge pattern, so auto-match left it.
  - Suggested: "Klinik Sehat · invoice 1031 · +RM 9,200.00 (September 2026) · Same as the bank line still open on OR-0918, same day as due · already linked RM 9,200.00".
  - The drawer should show the same suggestion (see A11.1).
- **Reason catalogue line:** the net variant "Same as what reached the bank (after the bank's charge), name matches: Klinik Sehat, same day as due".

### Changes to `SetupCompanies.dc.html`

- State `printed-names`, in the AISB drawer: "AISB (M) SDN BHD (1331234-K) | 18/11/2026 at 10:44 | Aisha Rahman | Remove".
- State `printed-names-remove`: "Click again to remove" with the note, then the removal toast.
- An empty state: "None confirmed.".

### States and Notifications boards (optional)

- Add the fetch error strings (A1).
- Add the second-click patterns (Take it for, Remove).
- Add a notification "Bank reconciliation of August 2026 changed: confirm again".
