# HR, Payments and Accounting: scope for approval

Date: 16 November 2026, revised 17 November 2026 after review and the owner's answers. Status: **approved by the owner on 17 November 2026.** Nothing
here is built yet.

What happens to this document: the owner reads it, answers the open questions in section 11 and approves it. A
separate redesign session then draws every screen named here (design only, no logic). This project then builds to
that approved design.

All examples use made-up names and figures. Words that may be unfamiliar are explained in the glossary (section 12).

---

## 1. Why, and what is decided

### Why

Today hr-payments is a payments tracker with accounting reports on top. Staff exist only as people who get paid.
Payroll is done by hand in a monthly Excel workbook, with every statutory figure looked up on a government calculator
and typed in. Leave, birthdays, contract dates and staff claims live nowhere in the app. The owner wants one system
that covers the whole path: HR prepares the request, someone approves it, finance pays it, and accounting books and
reconciles it. Each step is recorded with who did it and when. At the owner's company one person may do all four
steps, but the app is built for a bigger company where four different people do them. The redesign has to draw this
new shape now, or it would draw a shell without HR and have to be redone.

### Decided (by the owner, 15, 16 and 17 November 2026)

| Topic | Decision |
|---|---|
| Shape of the app | Three areas, **HR**, **Payments** and **Accounting**, plus an **Overview** and an **Admin** area. |
| Companies | A **company switcher** at the top replaces the one-menu-item-per-company list. |
| Four steps | 1 Request, 2 Approve, 3 Pay, 4 Record and reconcile. Each step records who and when. |
| One payments register | Every outgoing payment, whatever started it, is in one register in Payments. |
| Claims and advances | Requests live in HR; their payment lives in Payments; each points to the other. |
| Bank statements | Move to Accounting, next to the bank reconciliation. |
| Approvals for now | A printed approval form with a reference code and a keyed check (text and QR). Up to 3 approvers set in Setup. Any one signature approves. Never blocks a payment. |
| Leave | Entered by HR for everyone. Staff self-service comes later, with logins. |
| HR step 1 | Staff records, leave, calendar and reminders, claims, salary advances. |
| HR step 2 | Payroll calculated inside the app, after a 2 to 3 month parallel run. |
| Out at first | Attendance and clock-in, recruitment, performance reviews. |
| Order of work | This scope, then the redesign, then HR step 1, then payroll, then stage 2. |
| Data | Every new area has easy **input** (typed, or pasted / imported from Excel), **view** (its page and Overview card) and **extract** (Excel export of every list, and the audit pack). |
| Stage 1 | SQL Account stays the books for the owner's company. Payments are matched to SQL's vouchers. |
| Stage 2 | For a company not in SQL, hr-payments is the books. "Add payment" creates the voucher. Full accounting practice, no SQL data. |
| Payroll companies (17 Nov) | Payroll runs in the app for the owner's main company only. Other companies keep paying salaries as recurring payments. |
| Claims (17 Nov) | Paid separately, once approved, never through payroll. |
| Public holidays (17 Nov) | The office is in Kuchai Lama: Wilayah Persekutuan Kuala Lumpur holidays, one location for the whole company (per office later, if ever needed). |
| HRDF (17 Nov) | With 8 employees registration is optional, not required. The company is probably not registered (no levy paid in the 2026 books). Setup keeps an HRDF setting, off by default, and warns when the Malaysian headcount reaches 10. |
| Leave policy (17 Nov) | Set in Setup › HR › Leave, pre-filled with the legal minimums. The owner only changes what the company gives above them. |
| Statutory rate dates (17 Nov) | EPF, SOCSO and EIS rates as used from October 2024: confirmed by the owner. Lindung 24 Jam from June 2026: the owner believed so, and PERKESO's FAQ confirms it. 60-and-over rates from the month after the 60th birthday: the owner's yes depended on it being an official rule; it is not published, so it stays common payroll practice, to check with KWSP and PERKESO. |
| Recurring bills (17 Nov) | Approved once, when the recurring payment is set up or its amount changes; no form each month. |
| Who is staff (17 Nov) | Directors on the payroll are staff records (they have EPF and PCB). Contract workers stay payees unless they are on the payroll. |
| Payslips (17 Nov) | Printed and signed as today, and also emailed to each person as a password-protected PDF. |
| Bank payment file (17 Nov) | Payroll produces Maybank's bulk payment file for the salary transfer, if the company uses Maybank bulk payment (to confirm when payroll is built). |
| Records kept (17 Nov) | A leaver's record is kept 7 years after they leave, then removed. |
| Unapproved items (17 Nov) | Shown only on Payments › Approvals; To pay lists only what is ready to pay. |
| Month review sheet (17 Nov) | Yes: one approver signs a printed Month review each month, with a checklist item that ticks once it is uploaded, while one person does every step. |
| Leave approval (17 Nov) | Recorded by HR only for now; a director's approval can come with logins later. |
| Users and access (17 Nov) | The redesign draws an **Admin › Users and access** page now: add a person, sign-in name, and six access rights (HR, Payroll figures, Payments, Accounting, Approver, Admin), plus how the menu looks for a user without HR access. It is built later, with hosting and logins; until then the app runs for one person as today. |
| Phone upload (17 Nov) | Yes: a fifth phone screen to photograph a signed approval form; the code is read from its QR and HR confirms which approver signed (question 14). |
| Language (17 Nov) | English only, on screens and on everything printed (payslips, approval forms, Month review). Wording can change later without a redesign. |
| Payroll check (17 Nov, redesign questions) | Every company has the payroll workbook check; using it is up to the company. A company whose pay has no statutory deductions does not use it. HR › Payroll shows the check for every company; the run shows only where Setup › Companies has "Runs payroll in this app" on. |
| Built for any company (17 Nov) | Nothing is fixed to the owner's company in the code: payroll, approvers and every HR setting are per-company settings, and the owner's company is simply the first to use them. |
| Net salaries payable (17 Nov) | Follow the account the company's books use (420-000 Accruals in the owner's SQL books), chosen per company in Setup › Statutory accounts. |
| Customers overdue (17 Nov) | Older than 30 days. Balances from before tracking are not counted as overdue; they are shown apart, labelled "Before tracking" (owner, 19 Nov). |
| Bank sign-off rule (19 Nov) | Owner: keep today's rule. A month is signed off only when the book closing equals the bank closing; sign-off with reconciling items listed is not allowed. |
| Per company (17 Nov) | Approvers, leave policy, public holidays and claim types are set per company. |
| Leave values (17 Nov) | The legal minimums are the entitlement. Anything above the legal days (leave recorded beyond them, or a Setup value set higher) shows a warning only and is never refused. Question 3 closed. |
| Payslip password (17 Nov) | Agreed by the owner: the person's IC number without dashes by default (passport number for a foreign worker); HR may set a personal password on the staff record instead, stored encrypted and resettable. The email names the rule, never the password. |
| Bank reconciliation statement (18 Nov) | A printed, signed reconciliation statement per bank account and month, in the standard layout, with Prepared by and Reviewed by; book entries where no money moved (such as a duplicated self-billed receipt and payment that cancel out) are listed as pairs with their reason, and the reason is kept with the sign-off so the auditor's copy needs nothing written by hand (section 8). |
| Joiner reminders (19 Nov) | One merged reminder "Register {name} with KWSP and PERKESO" due 7 days after the start date, and "Stamp the contract of {name}", replacing the app's separate KWSP (7 days) and PERKESO (30 days) registration reminders and "Stamp {name}'s appointment letter". An app change, built with HR step 1. |
| One Next up row per unpaid statutory payment (19 Nov) | When a statutory payment for the month is entered and still unpaid, Next up shows only its payment row ("Pay KWSP for October", marked overdue after the due date), not also the statutory check row. The check row (rule 14) shows only when there is no unpaid payment to point at, for example when the payment was made short or never entered. An app change (hrp/nextup.py). |
| Placements (17 Nov) | SQL import, e-Invoices and printed invoices go under Accounting, e-Invoices and invoices with a page of their own; each company's month page splits into the Payments register and the Monthly checklist. |
| Phone design deferred (18 Nov) | Owner: the phone design waits. The five phone boards are not built, and the fifth phone screen (photograph a signed approval form, row "Phone upload" above) waits with them. Today's narrow-screen layout stays. The upload is done on the computer, on Approvals. |

On screen, "stage 1" and "stage 2" are never shown. A stage 1 company is labelled **Kept in SQL Account**; a stage 2
company is labelled **Kept here**.

### Still open

No question is open. Question 3 was answered on 17 November 2026 with the redesign questions (see the table above):
the legal minimums are the entitlement, and anything above them is a warning only.

---

## 2. The new structure

### The side menu

| Area | Page | What it is for |
|---|---|---|
| **Overview** | Overview | What's next, pending items, and summary cards for Payments, Accounting and HR. |
| **HR** | Staff | The staff list and each person's record. |
| | Leave | Leave taken and booked, balances and the team calendar. |
| | Calendar and reminders | Birthdays, work anniversaries, probation, contract, passport and permit dates; joiner and leaver tasks. |
| | Claims | Staff expense claims with receipts. |
| | Salary advances | Advances given and how they are repaid from salary. |
| | Payroll (step 2) | The monthly salary run, payslips and statutory totals. |
| **Payments** | Approvals | Every approval form printed and uploaded, and what still waits for one: HR requests (claims, advances, salary runs) and supplier bills alike. Linked from every HR request. |
| | To pay | Approved items waiting to be paid. |
| | Payments register | Every outgoing payment of the month, with "Add payment". Money in (rent received, say) stays on the same page, counted apart, as today. Today's company month page. |
| | Monthly checklist | The month's checklist, documents and filing. |
| | Budget | Bank balance, what is still to pay, and funds to request. |
| | Recurring | Salaries, fees, bills and statutory payments that come every month. |
| **Accounting** | Bank and reconciliation | Bank statements imported, lines explained, reconciliation per account and month. |
| | SQL import | Kept in SQL Account companies only. Fetch from SQL exports, paste, SQL entries and their lines. |
| | e-Invoices | MyInvois e-Invoices: issued, self-billed, received; printed invoices and notes. |
| | Books | Trial balance, general ledger, profit and loss, balance sheet. |
| | Customers and suppliers | Who owes what, with ageing. |
| | Statutory payables | What each payroll month withheld against what was paid by the due date, and net salaries still unpaid. |
| | Sales | Kept here companies only (see section 8). |
| | Purchases | Kept here companies only. |
| | Journals | Kept here companies only. |
| | Period close | Kept here companies only. |
| **Admin** | Setup | Every master record and setting, including the new HR ones. |
| | Audit pack | Before you print, build, check, auditor package, mark filed. |
| | Audit trail | Every change, with filters, check and export. |
| | Backup | Encrypted backup and the backup log. |
| | Users and access | Who can sign in and what each person can see (designed now, built with logins later). |

Approvals sits in Payments, not HR, because it also covers supplier bills, and because once logins exist finance
staff must see approvals for their own payments without having HR access. The pay detail on a salary-run form stays
visible only to people with HR or payroll access.

**Menu rules for the designer:**
- Payroll shows only for a company that runs payroll in the app (for now, the owner's main company only). SQL import shows only for a Kept in SQL Account
  company. Sales, Purchases, Journals and Period close show only for a Kept here company.
- Count badges: Approvals (waiting for approval), To pay (items due), and the existing badges.
- If the menu is too crowded on a laptop, Calendar and reminders may become a tab of Staff, and Salary advances a tab
  of Claims ("Claims and advances"). The designer decides; the pages' content does not change.
- Users and access shows only to a user with the Admin right. A user without HR access sees no HR section and no HR
  cards; one without Payroll figures sees payroll pages without pay amounts.
- Draw the menu for three cases: a Kept in SQL Account company without payroll, the same with payroll, and a Kept here
  company.

### The company switcher

- Sits in the top bar, next to the month switcher. Lists every company in use (stopped companies are not offered).
- The Overview can show **All companies** or one. Every other page works on the one company chosen. The Staff list
  may also show All companies, read only.
- Pages that only make sense for some companies are hidden for the others (see the menu rules above).
- Switching company keeps you on the same page where it exists for that company, otherwise opens its Overview.
- The page address remembers company, month and page, so Back and Refresh keep your place (already planned in the
  redesign build plan, slice 0).

### Where every existing page and feature goes (nothing is lost)

| Today | New place | Notes |
|---|---|---|
| Dashboard › Overview, with **Next up**, the months still open, and the audit-trail notice | Overview | Next up stays as the to-do list. The audit-trail notice ("The audit trail needs attention") stays at the very top of the Overview, above Next up. Cards are added (section 3). |
| Companies › one item per company (the month page) | Payments › Payments register and Monthly checklist, for the company chosen in the switcher | The counts on each company card (past due, part paid, documents missing, lines to explain, not in SQL) move to the Overview's **Needs attention** card (section 3). |
| Monthly work › Budget | Payments › Budget | Unchanged in what it does. |
| Monthly work › Bank statements | Accounting › Bank and reconciliation | Import, explain lines, reconciliation, sign-off, before tracking. |
| Monthly work › SQL import | Accounting › SQL import (Kept in SQL Account companies only) | Everything on today's SQL page stays here except the e-Invoices table: the Fetch button and its preview of what will be read; paste; SQL entries not linked; **Journals and invoices** (journals with the bank-move note, linked checklist item, link or create a payment); **Find an SQL entry** with search and sort; **Probably a correction** with Create all and Ignore all; **Replaced by a later version from SQL**; entries no longer in a journal read, with the **Deleted in SQL** button and the Ignored list; **Before tracking**; the **Imported files** list; the **Use another folder** export-folder setting; checks against SQL's reports. |
| Monthly work › Recurring | Payments › Recurring | Salary rows link to the staff record once HR exists. |
| Recurring › salary advances | HR › Salary advances | Repayment still comes off salary; the advance's payment is in the Payments register. |
| Joiner and leaver reminders on the checklist | HR › Calendar and reminders, and still on the month's checklist | Driven by the staff record's start date and last day instead of the recurring payment's. |
| Accounting › Books › Trial balance, General ledger, Profit and loss, Balance sheet | Accounting › Books | Same four tabs, same From / To bar, "financial year to date", Excel download, account drill-down from the trial balance to the ledger, and the document pop-up from a ledger line. |
| Books › Customers and suppliers | Accounting › Customers and suppliers | Own page, as the Overview card opens it. Both sides, list with ageing, one party's statement. |
| Books › Statutory | Accounting › Statutory payables | Own page, with "use this account", "open the payment" and "go to Setup". Also linked from HR › Payroll's per-authority totals. |
| SQL page › e-Invoices (MyInvois) | Accounting › e-Invoices | The MyInvois copy is still read by Fetch. |
| SQL page › printed invoices, debit and credit notes, self-billed, month zip | Accounting › e-Invoices (a Print column and "All of the month") | Same PDFs. Kept here companies print from their own documents. |
| Filing › Audit pack | Admin › Audit pack | Gains HR pages, the approval pages and the approver history (sections 4, 5). |
| Filing › Audit trail | Admin › Audit trail | HR records are captured like everything else. |
| Filing › Backup | Admin › Backup | Unchanged. |
| Setup › Companies and banks (companies, bank accounts, chart of accounts, statutory accounts) | Admin › Setup, same group | Companies keep their print settings; statutory employer numbers (EPF, SOCSO, LHDN employer no., HRDF) added for payroll, and an **HRDF registered** setting (yes or no, with the levy rate), off by default (section 6). |
| Setup › People and payments (recurring payments, customers and suppliers) | Admin › Setup, same group | Recurring is also reached from Payments. |
| Setup › Payments and documents (payment types, document types, required documents) | Admin › Setup, same group | New payment types: staff claim, salary advance (already exists as an advance), payroll run. |
| Setup › Monthly work (checklist, reminders) | Admin › Setup, same group | |
| Setup › Matching words | Admin › Setup, same group | Kept in SQL Account companies only. |
| Setup › General (settings, Move setup) | Admin › Setup, same group | Move setup gains the HR settings (not the staff themselves). |
| New Setup group **HR** | Admin › Setup › HR | Approvers (up to 3), leave types and company policy, public holidays and the company's state (Wilayah Persekutuan Kuala Lumpur for the owner's company), claim types and limits, payroll settings (step 2) including **Pay items**. |
| Payment dialog **Bank account** field (paid from / paid into) | Payments › payment dialog | New work already agreed (14 Nov). Moving a payment between accounts rechecks both reconciliations. For a Kept here company, see section 7: a posted voucher is never edited. |
| Kept new work from the redesign (search, notifications, Undo, badges, document viewer, backup extras, Overview extras, sign-in, first run) | Unchanged | Search and notifications must also cover HR records and requests, within access rights once logins exist. Listed in the section 10 checklist. |

---

## 3. The Overview

The Overview keeps today's top part: the audit-trail notice when there is one, today's date, **Next up** (most urgent
first, with **Go**), and the months still open from before. Below it, four rows of summary cards. Every card opens its
page for the same company and month. With **All companies** chosen, money cards show one line per company, each
marked Kept in SQL Account or Kept here.

### Needs attention

| Card | What it shows | A click opens |
|---|---|---|
| Needs attention | Five counters: **Past due**, **Part paid**, **Documents missing**, **Lines to explain**, **Not in SQL** (Kept in SQL Account companies only). With All companies, one line per company. A counter at zero is grey. | Past due and Part paid: Payments register, filtered. Documents missing: Monthly checklist, documents. Lines to explain: Accounting › Bank and reconciliation, lines to explain. Not in SQL: Accounting › SQL import. |

### Payments cards

| Card | What it shows | A click opens |
|---|---|---|
| Checklist | Items done out of total for the month, for example "14 of 22". | Payments › Monthly checklist |
| Due and overdue | Number and amount due in the next 7 days, and overdue. | Payments › To pay, filtered |
| Budget vs paid | Budgeted for the month, paid so far, still to pay, funds to request. | Payments › Budget |
| Paid without approval on file | Count of payments made with no approved form on file (including "Paid more than approved" and "Paid, approval refused"). Hidden when zero. | Payments › Approvals, filtered to these |

### Accounting cards

| Card | What it shows | A click opens |
|---|---|---|
| Bank balance | Per bank account: the balance at the latest statement line this month, and the statement's date. | Accounting › Bank and reconciliation, that account |
| Money in and out | This month's total in and total out, from the bank lines. | Same page, the month's lines |
| Profit or loss | This month and the financial year to date. Kept in SQL Account: from the books mirrored from SQL, with the date they run to. | Accounting › Books › Profit and loss |
| Customers overdue | Number and amount of customer balances past due. | Accounting › Customers and suppliers, customers, overdue |
| Suppliers due | Amount owed to suppliers due in the next 14 days, and overdue. | Accounting › Customers and suppliers, suppliers |

### HR cards

| Card | What it shows | A click opens |
|---|---|---|
| On leave | Names on leave today, and a count for this week. Leave **type is not shown** (a sick or maternity leave reads "On leave"). | HR › Leave, team calendar |
| Birthdays and anniversaries | This month's, by day: name and "birthday" or "5 years". **No age and no date of birth year.** | HR › Calendar and reminders |
| Dates coming up | Probation ends, contracts ending, passport and work permit expiries in the next 60 days. | HR › Calendar and reminders, filtered |
| Headcount | Staff in employment today, joiners and leavers this month. | HR › Staff |
| Requests waiting | Two counters for claims, advances and salary runs: **Waiting for approval** and **Approved, waiting to pay**. | Waiting for approval: Payments › Approvals, filtered to HR requests. Approved, waiting to pay: Payments › To pay, filtered. |

### How each card behaves

| Card | Follows the month switcher? | Empty | Out of date or not available |
|---|---|---|---|
| Needs attention | Yes | "Nothing needs attention" | |
| Checklist, Budget vs paid | Yes | "No checklist for this month yet" | |
| Due and overdue | No (from today) | "Nothing due" | |
| Paid without approval on file | Yes | Hidden | |
| Bank balance, Money in and out | Yes | "No statement imported for <month>" | "Statement runs to 12 Nov" |
| Profit or loss | Yes (plus year to date) | "No books yet" (Kept here company with nothing posted) | Kept in SQL Account: "SQL data runs to 12 Nov, fetch again" |
| Customers overdue, Suppliers due | No (as at today) | "No balances" | Kept in SQL Account: "as at 12 Nov, fetch again" |
| On leave, Headcount, Dates coming up | No (today) | "Add your staff to see this" | |
| Birthdays and anniversaries | Yes | "None this month" | |
| Requests waiting | No (now) | "Nothing waiting" | |

Every Accounting card for a Kept in SQL Account company shows the date SQL's data runs to. Any card that fails to load
shows "Could not load, try again" without hiding the others.

### What the Overview never shows (privacy)

- No salary, pay figure, payslip, IC number, passport number, bank account, address, tax or EPF number for any person.
- No reason for leave, no medical detail, no claim receipts.
- The payroll total appears only as one line inside Payments amounts (for example "Salaries, October"), never per person.
- Once logins exist, the HR cards show only to people with HR access; others see the other cards.

---

## 4. The four steps and approvals

### The steps

| Step | Who (in a bigger company) | Where in the app | What is recorded |
|---|---|---|---|
| 1 Request | HR (claims, advances, salary run) or accounting (supplier bills) | HR pages; for a bill, Payments › Add payment (Kept in SQL Account) or Accounting › Purchases (Kept here) | Who made it, when, the amount, the supporting files |
| 2 Approve | A director (one of up to 3 approvers) | Printed form, signed, uploaded on Payments › Approvals | Which approver signed (name as it was then), the date on the form, the upload date, the uploaded form |
| 3 Pay | Finance | Payments › To pay, then the payment dialog | Paid date, bank reference, bank account, who entered it |
| 4 Record and reconcile | Accounting | Accounting (Kept in SQL Account: SQL voucher linked; Kept here: voucher posted here) and the bank reconciliation | Voucher number, the matched bank line, who signed off the reconciliation |

**Requests in the two kinds of company:**
- A **supplier bill** for a Kept in SQL Account company is a payment record in the register with the Approval marker;
  until its due date it reads "not due yet". For a Kept here company it is a supplier invoice in Purchases (section 8).
- **Several items paid at once**: selecting several items in To pay and pressing **Pay** creates one payment per item,
  all with the same bank reference. The bank reconciliation can match one statement line (a bulk debit, say) to a
  group of payments.

### Segregation of duties (who did what)

- **Until logins exist**, the app cannot know who is at the keyboard. "Who" at each step is the name chosen or typed
  at that step. The audit pack labels it **declared, not verified**.
- **While one person holds every role**, these checks make up for it:
  - the approval form should be signed by an approver who is not the person who prepared and paid it; the app warns
    (never blocks) when the declared requester, payer and approver are the same name;
  - each month, one approver signs a printed **Month review** sheet covering the payments register total, the Paid
    without approval on file list, the approvals attributed to each approver, and the bank reconciliation. The signed
    sheet is uploaded like an approval form, and the checklist item "Month reviewed" ticks only when it is on file
    (proposed, open question 12).
- The audit pack shows, per month, which steps one name did alone.

### How approval works for now (no director login yet)

1. HR (or accounting, for a bill) picks one request or a batch (for example "all October claims") and presses
   **Print approval form**.
2. The form lists each request (who, what, amount, the request number), the total, a **reference code** and a
   **keyed check**: a short code worked out from the requests' details with a secret kept in the records, so a form
   whose details were changed after printing no longer matches. Both are printed as text and as a QR code.
3. The up to 3 approvers named in Setup are printed on every form, each with a signature line. **Any one signature
   approves it.**
4. The signed form is uploaded on **Payments › Approvals** (or on the request). The app reads the reference code from
   the PDF's text, or from the QR in a scan or phone photo, or the person uploading types it. It then checks the keyed
   check against the requests as they are now. The person uploading also types the **date written on the form**; the
   upload date is kept separately.
5. Who signed:
   - a **digitally signed PDF**: the signer's name is matched to the approvers automatically;
   - a **paper scan or photo**: the person uploading clicks which approver signed (one click). Wherever that approval
     shows, including the audit pack, it reads **"Approver chosen by <name> from a paper scan"**, and the approver sees
     it on their Month review sheet to confirm.
6. The approver's name is kept as it was on the day. Changing the approvers in Setup later does not change old
   approvals.
7. If a request on the form changed after printing (a different amount, say), the upload says so and that request is
   not approved by this form; a new form is printed for it.

**What the keyed check proves:** only that the requests' details have not changed since the form was printed. It does
not prove who signed: anyone with the records (or a backup) could work it out again. The signature, and the checks
above, cover who signed.

**Rules on approvals:**
- A request whose payee is one of the approvers (a director's own claim or advance) must be signed by a different
  approver. If only one approver is set up, it can only be "Self-approved", and it is listed in the audit pack.
- **Once approved, a request is locked.** Changing its amount, payee or lines sends it back to Draft, voids the
  approval (kept in the history) and needs a new form. A salary run is the exception: once approved or paid it is
  never reopened, and is corrected as section 6 says.
- The Approval marker compares what was paid with what was approved. If more was paid, it reads **"Paid more than
  approved (RM x)"**, and the difference goes on the Paid without approval on file list.
- The approver list's history (who was an approver, from when, until when) is a page in the audit pack. Creating or
  changing the secret behind the keyed check is recorded in the audit trail.

Approval **never blocks** a payment. A payment made without an approved form shows as **Paid without approval on
file** until the form is uploaded.

Later, once logins and access rights exist, approvers get their own login and approve with one click. The form stays
available as a fallback.

### Statuses

**A request** (claim, advance, salary run, supplier bill):

| Status | Meaning |
|---|---|
| Draft | Being prepared; can be changed or deleted. |
| Waiting for approval | On a printed form, not uploaded yet. |
| Approved | Signed form uploaded and matched. Shows who approved and when. Locked. |
| Not approved | The approver refused (marked with the reason). Nothing to pay. |
| Paid, approval refused | It was paid, then the approver refused it. Shown on the Overview card and in the audit pack until resolved by getting the money back, a credit, or a note from a director. |
| Withdrawn | Cancelled before payment, with a reason. Kept, never deleted. |
| Paid | Its payment in the register is paid (or **Part paid**). |
| Recorded | Its payment is booked. Kept in SQL Account: linked to an SQL voucher; for a salary run, "Waiting for SQL record" until Fetch finds the SQL journal whose totals match the run's journal summary (hr-payments posts nothing for a company kept in SQL). Kept here: voucher posted. |
| Done | Paid, recorded, reconciled and every document on file. |

A salary run has a few more steps of its own (section 6).

**A payment** in the register keeps today's statuses (not due yet, due, past due, part paid, paid, complete, past
legal deadline, waiting for SQL record, not on statement) and gains one marker: **Approval**, which reads *Not needed*,
*Waiting*, *Approved by <name>, <date>*, *Paid without approval on file*, *Paid more than approved (RM x)* or *Paid,
approval refused*.

### The "Paid without approval on file" list

- Every payment whose request needs approval, which is paid, and which has no approved form uploaded (or was paid
  above the approved amount, or was refused after payment).
- Shown on the Overview (a card, hidden when empty), on Payments › Approvals, and in the audit pack.
- The audit pack page has two parts: **Paid without approval on file** (still open: the payment, date paid, amount,
  who entered it) and **Approved after payment** (date paid, date signed on the form, upload date). A payment moves
  from the first to the second when its form is uploaded; the audit trail keeps both dates too.
- The checklist gains an item "Approvals on file for every payment" that ticks itself when the open list is empty for
  the month.

---

## 5. HR step 1 in detail

The staff record is the base. Salary, claims, advances, leave and reminders all hang off it. Today's recurring salary
payments become linked to a staff record (each salary row says whose it is), so nothing paid today is lost.

### 5.1 Staff record

| Group | Fields |
|---|---|
| Personal | Full name as on IC, preferred name, IC number (or passport number and country for non-citizens), date of birth, gender, nationality, citizenship status (citizen, permanent resident, foreign), race and religion (optional, see section 9), marital status, address, phone, personal email. |
| Job | Employer (which company), staff number, position, department, employment type (permanent, contract, part-time, intern), date joined, probation end date, confirmed date, contract end date (for contract staff), working days per week, normal hours per day, does manual work (yes or no, for the overtime rules), **work location** (Peninsular Malaysia or Labuan, Sabah, Sarawak), work state (if the company has more than one office), reporting to, work email, last day and reason for leaving (when they leave). |
| Pay | Basic salary per month and the date it applies from (a history, never overwritten), fixed allowances (for example transport), employer-paid insurance, bank name and account number, how they are paid (bank transfer, cheque). |
| Statutory numbers and categories | EPF (KWSP) number; SOCSO (PERKESO) number; income tax number (TIN); first-contribution date (when EPF, SOCSO and EIS were first paid for this person, ever). The **EPF rate group, SOCSO category and EIS cover are worked out** from date of birth, citizenship and the first-contribution date, and change automatically from the month after the month the person turns 60 (common payroll practice; *check with KWSP and PERKESO* which month the change starts, see section 6, Sources). HR can override them only with a reason (for example a voluntary higher EPF rate, or a foreign worker who chose 11%). **Lindung 24 Jam**: covered, or opted out from a date (Malaysians only; foreign workers are always covered). HRDF: counted or not (worked out from citizenship). |
| PCB details | Tax resident or not; tax category (1 single; 2 married, spouse not working; 3 married, spouse working, or divorced or widowed); spouse disabled; the person disabled; number of children by relief type (under 18, 18 and over studying, disabled); zakat paid through payroll (monthly amount); other reliefs declared on form TP1; benefits in kind and living accommodation declared on form TP2; earlier employer's pay and PCB this year (form TP3) for a mid-year joiner. |
| Documents | IC or passport copy, offer letter, contract, work permit, certificates, TP1, TP2 and TP3 forms, other. Each with an expiry date where it has one. Stored like today's payment documents: read-only, and cannot be changed unnoticed. |
| Emergency contact | Name, relationship, phone. |
| Notes | Free text, visible only to HR. |

Rules:
- A changed salary or rate starts from a date; past months are never rewritten.
- A person who leaves stays in the records (history and the yearly forms need them) and drops off current lists.
- No delete once the person has any pay, leave or claim; only "Left" with a last day, like "Stop using" in Setup today.
- A staff record belongs to one company. HR pages work on the company chosen in the switcher. A person who moves to
  another group company is "Left" in one and a new joiner in the other, with the two records linked.

| | How |
|---|---|
| Input | Type one person; or **Paste a list** / import the owner's existing Excel staff list (a preview shows each row read and what is missing, then all or nothing, as Setup does today). First run: "Add your staff or paste the Excel list". |
| View | HR › Staff: list with filters (in employment, left, department, type), and one page per person with tabs: Details, Pay, Leave, Claims and advances, Documents, History. |
| Extract | Excel of the staff list (with a choice of which columns, since IC and pay are sensitive); one person's record as a PDF. |

### 5.2 Leave

**Leave types and the legal minimums** (Employment Act 1955). Since 1 January 2023 these minimums apply to every
employee in Peninsular Malaysia and Labuan, whatever their salary. Sabah and Sarawak follow their own Labour
Ordinances. Overtime and termination-benefit rules apply only to staff earning RM4,000 a month or less, or doing manual
work. The app's legal-minimum check uses the person's **work location**.

| Type | Minimum by law | Notes |
|---|---|---|
| Annual leave | 8 days (under 2 years' service), 12 days (2 to 5 years), 16 days (5 years or more) | Prorated in the year of joining, and by completed months in the year of leaving (half a day or more counts as 1 day). Untaken leave lapses 12 months after the year ends unless the company policy says otherwise. Paid out on leaving. May be lost if the person is absent without permission for more than 10% of working days. |
| Sick leave (no hospitalisation) | 14 days (under 2 years), 18 days (2 to 5 years), 22 days (5 years or more) | Needs a medical certificate. |
| Hospitalisation | Up to 60 days a year | Includes the sick days above, not on top of them. |
| Maternity | 98 days | 98 days in a row. Paid only if employed 90 days in the 9 months before the birth and with fewer than 5 surviving children (the app asks HR to confirm). |
| Paternity | 7 days | 7 days in a row per birth, up to 5 births, for married male staff with 12 months' service, given 30 days' notice (or as soon as possible). |
| Public holidays | At least 11 paid days a year, 5 of them fixed by law | Which days depends on the state. |
| Unpaid leave, compassionate, marriage, study, replacement leave | Company policy only | Set in Setup. |

Part-time staff (under 70% of normal hours) follow the Employment (Part-Time Employees) Regulations 2010. Interns are
flagged and get only the company's policy leave.

**Company policy** (Admin › Setup › HR › Leave): each leave type's days per year, if more generous than the law, by
years of service or by grade; whether it is paid; whether half days are allowed; how much may be carried forward to
next year and until when it must be used; whether a medical certificate is required; and the public holiday calendar.
This is all part of Setup (the owner's question, answered 17 November 2026): the app pre-fills the legal minimums
above, the owner changes only what the company gives above them, and any value can be changed at any time with the
date the change applies from (past years are not rewritten).

The app never lets a policy go below the legal minimum for an employee the Act covers; it warns if Setup tries to.

**What HR enters and what the app works out:**

| Typed by HR | Worked out |
|---|---|
| Leave: person, type, from, to, half day (morning or afternoon), reason, attached certificate | Working days counted (skipping rest days and the state's public holidays) |
| Opening balances when starting (imported from the owner's Excel list) | Entitlement for the year from service length and policy, prorated for joiners and leavers |
| Carry-forward decisions at year end (or automatic by policy) | Balance: entitlement + carried forward - taken - booked ahead |
| The company's state, and any company holidays | Public holidays for the year for that state |

**Leave statuses.** Leave is entered by HR as **Booked** (ahead) or **Taken**. There is no approval step for now
(open question 13). Cancelled leave stays in the list as **Cancelled**, with a reason, and its days go back to the
balance. Leave over the balance, or clashing with leave already entered for the same person, is warned about, not
refused.

Unpaid leave flows to payroll (step 2) as days to deduct.

**Public holidays by state**: a list per year per state, kept in Setup, pre-filled where possible and editable (some
holidays are announced late, and replacement days follow when a holiday falls on a rest day).

For the owner's company (office in Kuchai Lama, decided 17 November 2026) the list is **Wilayah Persekutuan Kuala
Lumpur**: the federal holidays plus Federal Territory Day (1 February). What the app pre-fills:
- The year's KL list from the Prime Minister's Department's official list (kabinet.gov.my). 2026 is bundled; 2027 is
  added only once checked against the official 2027 list (*not yet confirmed*: the official PDF could not be opened,
  and the 2027 dates seen so far are estimates).
- The 5 holidays the Employment Act fixes (s.60D) are locked: National Day (31 Aug), the Agong's birthday, Federal
  Territory Day (KL's stand-in for the Ruler's birthday, 1 Feb), Workers' Day (1 May) and Malaysia Day (16 Sep).
- Every other gazetted KL holiday is ticked by default; the owner may untick down to the legal minimum of 11.
- Moon-dependent dates (Nuzul Al-Quran, Aidilfitri, Aidiladha, Awal Muharram, Maulidur Rasul) are marked "may move"
  and editable, and the owner can add one-off days the government announces during the year (as 20 March 2026 was).
- Replacement days are worked out from the company's rest day (Sunday by default) and when two holidays fall on the
  same day, not copied from the civil-service list. A holiday on a rest day moves to the next working day
  (s.60D(1)(b)); with the employee's agreement another day may replace a holiday (s.60D(1A)).
- *Check with the Labour Department (JTKSM) or kabinet.gov.my*: the 2026 dates come from sites that copy the official
  list, which could not be opened directly. Sources: https://www.kabinet.gov.my/hari-kelepasan-am/ (official, could
  not be opened); JTKSM on 1 February 2026, reported by Sinar Harian:
  https://www.sinarharian.com.my/article/762326/berita/nasional/thaipusam-hari-wilayah-persekutuan-diwartakan-cuti-am-2026

**Team calendar**: a month view of who is off, by person, with public holidays marked. Leave type is shown here only to
HR access.

| | How |
|---|---|
| Input | Type leave one at a time; import opening balances from Excel; import public holidays as a list. |
| View | HR › Leave: Taken and booked list, Balances table (person by leave type), Team calendar. Each person's Leave tab. |
| Extract | Excel of leave taken (by dates), of balances at a date, and of the year's calendar; balances at year end in the audit pack's HR pages. |

### 5.3 Calendar and reminders

| Reminder | From | Shown |
|---|---|---|
| Birthday | Date of birth | Overview card, the calendar; no year or age shown |
| Work anniversary | Date joined | Overview card, the calendar (for example "3 years") |
| Probation ending | Probation end date | 30 days and 7 days before; Next up |
| Contract ending | Contract end date | 60 and 30 days before; Next up |
| Passport and work permit expiry | Document expiry dates | 90, 60 and 30 days before; Next up |
| Joiner tasks | Date joined | Today's reminders (e-CP22 within 30 days of joining, PERKESO and KWSP registration, stamping over RM 3,000), on the month's checklist as today |
| Leaver tasks | Last day | CP22A only when the person is retiring, has died, is leaving Malaysia, or had no PCB deducted; CP21 when leaving Malaysia for over 3 months. Both at least 30 days before the last day, and both start the tax-clearance hold (section 6). On the checklist as today. |

Joiner and leaver reminders keep today's rules (they go to the month they fall due in; a filed month passes them to
the next open month). They are only reminders, not legal advice, as today.

| | How |
|---|---|
| Input | Nothing new: they come from the staff record. HR can mark a reminder done or add a one-off reminder. |
| View | HR › Calendar and reminders (list and month view), Overview cards, Next up. |
| Extract | Excel of reminders for a date range. |

### 5.4 Claims

A staff claim is money a person spent for the company (travel, meals, parking, a purchase) and wants back.

Flow: HR enters the claim with its lines (date, claim type, description, amount, receipt file) -> it goes on an
approval form -> approved -> it appears in **Payments › To pay** -> paid separately -> booked.

- Claim types (Setup › HR) each carry an expense account (for the books), an optional monthly limit, and whether a
  receipt is required. A claim over its limit is flagged, not refused.
- An overseas claim keeps today's rule that its e-Invoice is required (self-billed).
- **Links**: the claim shows its approval form and its payment; the payment shows the claim and its receipts (so the
  payment's documents are complete from the claim's receipts).
- **Booking.** Kept in SQL Account: the payment is matched to SQL's voucher as today; nothing is posted in
  hr-payments. Kept here: when approved (or when paid, if paid first), the claim posts a journal voucher (JV series):
  claim expense accounts per line / Claims payable (staff). The payment then posts a payment voucher: Claims payable /
  Bank.
- **Paid separately** (decided 17 November 2026): each approved claim is paid on its own from To pay, never added to
  the payroll run.

| | How |
|---|---|
| Input | Typed, with receipts uploaded (several per line). |
| View | HR › Claims: by status and month; each person's Claims tab. |
| Extract | Excel of claims (lines, types, statuses); claims with their receipts in the audit pack under their payment. |

### 5.5 Salary advances

Already built (inside Recurring today). They move to **HR › Salary advances**, unchanged in what they do: an advance
amount, a monthly deduction, from a month to a month.

- The advance is a request (step 1), goes on an approval form (step 2) and is paid from **Payments › To pay**
  (step 3).
- **Booking (step 4).** Kept in SQL Account: the advance's payment is matched to SQL's voucher as today; nothing is
  posted in hr-payments. Kept here: paying it posts a payment voucher: Advances to staff (money the person owes the
  company, one line per person) / Bank. Each month's repayment through payroll reduces Advances to staff inside the
  payroll journal. The advance page's balance left must equal that person's Advances to staff balance in the books, and
  the audit pack checks this.
- Each month's repayment comes off salary: before payroll as today (the salary payment is lower); with payroll
  (step 2) as a deduction line on the payslip.
- A person who leaves with a balance left: it is deducted from the final pay (within the 50% limit below), and
  anything still left is kept as an amount to collect, shown on the person's record and in the audit pack.
- The page shows each advance's amount, repaid so far and balance left.
- **Employment Act limits.** The app warns, but does not block, when an advance is larger than the person's last
  month's wages, and when a month's total deductions (advances and other deductions, not counting EPF, SOCSO, EIS,
  Lindung 24 Jam, PCB or zakat) would exceed 50% of wages. Advances never carry interest.

| | How |
|---|---|
| Input | Typed (as today). |
| View | HR › Salary advances; each person's Claims and advances tab. |
| Extract | Excel of advances with balances. |

---

## 6. HR step 2: payroll

The legal rules below are **as at November 2026**. Each rate, table and date is kept in Setup with the date it applies
from, and must be checked each year and whenever the law changes. Exact formulas are confirmed against the current law
before building.

### What it calculates, and from what

| Calculated | From |
|---|---|
| Basic pay for the month | The salary on the staff record. Joiner or leaver part month: monthly pay x days employed / calendar days in the month (Employment Act s.18A). Unpaid leave deduction per day: monthly pay / 26 (s.60I). A company may set a more generous rule, never a less generous one. Rounded to the sen. *(Formulas to be confirmed against the current Act before building.)* |
| Pay items for the month | Basic, fixed allowances, overtime, bonus, commission, arrears, benefits in kind, pay in lieu of notice, leave paid out, and so on (see Pay items below) |
| EPF, employee and employer | EPF's contribution table (the Third Schedule), on the pay items that count for EPF, by the person's rate group |
| SOCSO, employee and employer | PERKESO's table by wage band and the person's category, on the pay items that count |
| EIS, employee and employer | PERKESO's EIS table by wage band, on the pay items that count |
| Lindung 24 Jam | Employee only, 0.75% from the June 2026 contribution month (1.00% from June 2028, 1.25% from June 2031, kept as dated rows), on wages up to RM6,000, at any age; goes in the PERKESO file. Uses the per-person flag (covered or opted out). *Check with PERKESO: the scheme is new and has already changed once; its banded amounts (Act A1788's Third Schedule) are not yet confirmed.* |
| PCB (monthly tax deduction) | LHDN's computerised method for the year (its specification kept per year): normal and additional pay handled separately; EPF relief capped (only EPF up to the RM4,000 relief counts); zakat deducted from PCB ringgit for ringgit; non-residents at a flat 30% with no reliefs; rounded as LHDN's specification says (5 sen; under RM10 not deducted). Uses this year's pay and PCB to date, the PCB details on the staff record, and TP1 / TP2 / TP3. *Check each year's specification.* |
| HRDF levy | Only when Setup's **HRDF registered** setting is on (off by default; the owner's company is probably not registered, decided 17 November 2026). Then 1% (10 or more Malaysian employees) or 0.5% (5 to 9, registered by choice) of each Malaysian employee's basic pay and fixed allowances; foreign staff excluded. A warning shows when the Malaysian headcount reaches 10 and the setting is still off. |
| Deductions | Advance repayments, unpaid leave, zakat, other deductions entered for the month |
| Net pay | Gross pay - employee deductions |
| Year to date | The opening year to date (if payroll started mid-year) plus every month kept, never typed |

### Pay items (Setup › HR › Payroll settings)

Each authority counts different things as wages. For example, EPF wages include bonus, commission, most allowances
and leave pay, but not overtime, travel allowance, gratuity, retirement benefits or pay in lieu of notice. Claims are paid
separately, never through payroll. So the run never works from "gross pay": it uses a **Pay items** list.

Each item (basic, fixed allowance, overtime, bonus, commission, arrears, benefit in kind, pay in lieu of
notice, leave paid out, and so on) has ticks: counts for **EPF**, **SOCSO and EIS**, **HRDF**, **PCB normal pay**,
**PCB additional pay**. The ticks come pre-filled from each authority's rules, with the date they apply from, and can
be checked by the owner.

### Contribution rates (as at Nov 2026, kept in Setup with the date they apply from)

| Scheme | Employee | Employer | Who |
|---|---|---|---|
| EPF | 11% | 13% on wages of RM5,000 or less, 12% above | Citizens and permanent residents under 60 |
| EPF | 0% | 4% | Citizens aged 60 and over |
| EPF | 5.5% | 6.5% on wages of RM5,000 or less, 6% above | Permanent residents aged 60 and over |
| EPF | 2% | 2% | Foreign workers, from October 2025 wages (domestic workers excluded) |
| SOCSO first category | 0.5% | 1.75% | Under 60, first joined before 55 |
| SOCSO second category (injury only) | 0% | 1.25% | 60 and over, and anyone first joining at 55 or over (foreign workers included) |
| EIS | 0.2% | 0.2% | Ages 18 to 60; not foreign workers; not anyone first joining at 57 or over |
| Lindung 24 Jam | 0.75% | 0% | From 1 June 2026, any age; Malaysians could opt out (window closed 31 August 2026, opting back in allowed any time), foreign workers stay covered |

SOCSO and EIS stop counting wages above RM6,000 a month. EPF, SOCSO and EIS rates as used from October 2024 were
confirmed by the owner on 17 November 2026.

**Confirmed by research (17 November 2026), and what is still to check:**
- EPF: under 60, 11% employee, 13% / 12% employer; citizens 60 and over 0% / 4%; permanent residents 60 and over
  5.5% / 6.5% or 6%; foreign workers 2% / 2% at every age from October 2025 wages. Up to RM20,000 the amounts come
  from the Third Schedule's band table. Contributions stop at 75.
- SOCSO: second category (injury only, 1.25% employer) from 60, and for anyone first joining at 55 or over.
- EIS: ages 18 to 60; ends at 60; a person aged 57 or over with no EIS contributions before 57 is exempt.
- Lindung 24 Jam: in force from the June 2026 contribution month, employee pays 100%, phased rates as above, RM6,000
  ceiling; voluntary for Malaysians (opt-out window 13 July to 31 August 2026), mandatory for foreign workers.
- HRDF: required from 10 Malaysian employees (1%); optional from 5 to 9 (0.5%).
- *Check with KWSP (03-8922 6000) and PERKESO (1-300-22-8000)*: whether the 60-and-over rates start in the birthday
  month or the month after. Neither publishes the month; the app uses the month after (common payroll practice), and
  the payroll workbook check does the same.
- *Check with PERKESO*: whether a worker aged 60 or over who stays covered still pays Lindung 24 Jam (the FAQ says "no
  age limit"), and how its banded amounts are rounded.
- *Check on HRD Corp's portal*: whether the company is registered (log in to e-TRiS with the company's MyCoID, look
  for HRD Corp's approval email, or ask helpdesk@hrdcorp.gov.my).

**Sources:**
- KWSP, mandatory contribution: https://www.kwsp.gov.my/en/employer/responsibilities/mandatory-contribution
- KWSP, Third Schedule from 1 October 2025: https://www.kwsp.gov.my/documents/d/guest/third_schedule_from_-1-october-2025
- KWSP, 60-and-over rate: https://www.kwsp.gov.my/en/w/new-minimum-statutory-rate-for-employees-above-age-60-takes-effect-1
- KWSP, non-citizen employees: https://www.kwsp.gov.my/en/employer/responsibilities/non-malaysian-citizen-employees
- PERKESO, contributions: https://www.perkeso.gov.my/en/our-services/employer-employee/contributions.html
- PERKESO, 2025 booklet: https://www.perkeso.gov.my/images/dokumen/risalah/2025-BOOKLET_PERKESO_BI.pdf
- PERKESO, LINDUNG 24 Jam FAQ (August 2026): https://www.perkeso.gov.my/images/lindung/lindung-24-jam/130826-FAQ%20_LINDUNG24Jam_EN_version.pdf
- PERKESO, LINDUNG 24 Jam FAQ v2.3 (Malay): https://www.perkeso.gov.my/images/lindung/lindung-24-jam/FAQ_LINDUNG24Jam_v_2.3%20.pdf
- HRD Corp, new employer registration FAQ: https://supportcentre.hrdcorp.gov.my/portal/en/kb/articles/frequently-ask-questions-new-employer-registration

**Rounding.** Pay lines are rounded to the sen. Contributions are never rounded by the app: EPF, SOCSO, EIS and Lindung
24 Jam are read from each authority's band table. Above EPF's table (wages over RM20,000) EPF is the percentage,
rounded up to the next ringgit. In a bonus month the employer EPF rate follows EPF's published rule on bonus, checked
in the parallel run.

### Overtime, minimum wage and pay date

- Overtime typed as hours is valued at 1.5 times (normal day), 2 times (rest day) and 3 times (public holiday) the
  hourly rate (ordinary rate of pay / normal hours per day), for staff the overtime rules cover (RM4,000 a month or
  less, or manual work). For others it is typed as an amount. Work on a rest day or public holiday is paid as the Act
  says (for example 2 extra days' pay for working a public holiday). The normal week is 45 hours.
- The run warns if basic pay is below the minimum wage in force (RM1,700 a month from 2025, kept with its date).
- The run warns if it is approved after the 7th day of the next month (pay is due by then, s.19).

Each month HR types only what changes: overtime, one-off allowances or bonuses, other deductions, and confirms unpaid
leave (which comes from Leave).

### Self-checks

Every run checks itself before it can be approved: totals agree across payslips, summary, per-authority totals and the
bank list; no deductions over 50% of wages (warning); no basic below minimum wage (warning); no recurring salary rows
still in use for the same people and month (refused, see Switching over below).

### Leaver's final pay

A leaver's last pay is a run line with these parts, each a pay item with its own ticks:

| Part | Notes |
|---|---|
| Part-month salary | By the s.18A rule above; prefilled. |
| Annual leave not taken | Paid at the ordinary rate of pay (monthly pay / 26 per day); days prefilled from Leave. |
| Notice pay, or pay in lieu of notice | Pay in lieu of notice is not EPF wages. |
| Termination benefits | For staff earning RM4,000 or less with 12 months' service: 10, 15 or 20 days' pay per year of service, by length of service (Employment (Termination and Lay-Off Benefits) Regulations 1980). |
| Tax on loss of job | Compensation for loss of job is tax-free up to RM20,000 per completed year of service (not when going to a related company). |
| Advance balance | Deducted, within the 50% limit (section 5.5). |

**Hold until tax clearance.** When a CP22A or CP21 reminder exists for the leaver, the final payment shows **Hold until
tax clearance** in Payments › To pay. The employer must hold back money owed until LHDN's clearance letter arrives or
90 days pass; paying in full first makes the employer liable for the person's tax. The hold is released when HR
uploads LHDN's letter, or after 90 days. (Approval never blocks; the hold is a warning on the item, recorded if paid
anyway.)

### Run states

| State | Meaning |
|---|---|
| Draft | Inputs being typed. |
| Checked | Calculated, and the self-checks pass. |
| Approved | Approval form uploaded and matched. Figures **frozen**. |
| Sent to pay | Net pay per person and each authority's total are in Payments › To pay. A run can be sent before its form is uploaded (approval never blocks); its figures are then frozen at this point and its payments read "Paid without approval on file" once paid. |
| Filed | The month's statutory files have been uploaded to the portals (marked by HR). |

Once approved (or sent to pay), a run's figures are frozen and stored. Recalculating an old run (after a table row was corrected, say)
is for comparison only and never changes a closed run, its payslips, its files or its journal. A mistake is put right
by an adjustment in the next run, or (Kept here) by reversing the run's journal and posting a replacement run, never by
editing. Each payroll month is locked once filed.

### Outputs

| Output | Notes |
|---|---|
| Payslip per person | Laid out like today's payslip (company header, person block, pay row, deductions, employer contributions, year-to-date box, "Approved by"), as a PDF. |
| Monthly summary | Like today's Summary sheet: one row per person, with the totals. |
| Per-authority totals | EPF (employee + employer), SOCSO, EIS, Lindung 24 Jam, PCB, zakat, HRDF. These become the statutory payments in Payments. |
| Bank payment list | Net pay per person with bank and account, for the bank's bulk payment upload (format to be confirmed). |
| Statutory files | Monthly files in each authority's upload format: EPF contribution (Form A data), PERKESO (SOCSO, EIS and Lindung 24 Jam), LHDN PCB file for e-PCB Plus (formerly CP39). |
| Yearly | EA form per person, and Form E with CP8D. Must be built before the first February after payroll goes live. |
| Joiner and leaver forms (later) | e-CP22, CP22A, CP21 data from the staff record. |

### Due dates (as at Nov 2026, kept in Setup with dates; check each year)

| What | Due |
|---|---|
| EPF, SOCSO, EIS, Lindung 24 Jam, PCB, HRDF levy | By the 15th of the following month |
| EA form to each person | By the last day of February |
| Form E with CP8D | By 31 March (LHDN's e-filing grace period may apply) |
| e-CP22 (new employee) | Within 30 days of joining (filed online through MyTax) |
| CP22A (leaver, when needed) | At least 30 days before the last day |
| CP21 (leaving Malaysia for over 3 months) | At least 30 days before leaving |

Statutory payables (section 8) compares what was paid with these dates.

### The salary run as a request, and how it is booked

The salary run is one request: it goes on an approval form (step 2). Once approved, each person's net pay and each
authority's total appear in **Payments › To pay** (step 3).

**Kept in SQL Account (step 4):** the app makes a payroll journal summary (account, debit, credit, in the same layout
as below) for the bookkeeper to enter in SQL. The run stays "Waiting for SQL record" until Fetch finds the SQL journal
whose totals match. hr-payments posts nothing for a company kept in SQL.

**Kept here (step 4):** the run posts once, when approved (or when sent to pay, if that comes first), as one journal voucher (JV series, numbered at posting),
dated the last day of the payroll month:

| Debit | Credit |
|---|---|
| Salaries and wages (gross, including allowances and overtime) | EPF payable (employee + employer) |
| Employer EPF expense | SOCSO payable (employee + employer) |
| Employer SOCSO expense | EIS payable (employee + employer) |
| Employer EIS expense | Lindung 24 Jam payable |
| HRDF levy expense | PCB payable |
| | Zakat payable |
| | HRDF payable |
| | Advances to staff (the repayment) |
| | Any other deduction, to its own account |
| | Net salaries payable |

Every payment that follows (net pay per person, each authority) posts Payable / Bank, never an expense. The Statutory
payables page includes Net salaries payable, with a check that each run's net pay has been paid in full. Parallel-run
months post nothing.

### Input, view and extract

| | How |
|---|---|
| Input | Each month's changes typed, or pasted from Excel. Opening year to date per person, imported once from the workbook (with a preview and errors, like the staff import). Pay items and rates in Setup. |
| View | HR › Payroll: the month's run (inputs, calculated table, checks, state), payslips, monthly summary, per-authority totals. |
| Extract | Excel of every output (summary, per-authority totals, bank list, year to date); payslip PDFs; statutory files; payroll pages in the audit pack. |

### How it replaces the hand-made workbook

Today one workbook per month has one sheet per person (the payslip), a Summary sheet, and an old hidden template.

| Typed by hand today | In the app |
|---|---|
| Basic salary, and prorated pay worked out in the cell | From the staff record; proration by the legal rule, rounded |
| SOCSO, EIS, Lindung 24 Jam, looked up on PERKESO's tables | Read from the tables |
| PCB, taken from LHDN's calculator each month | Calculated by LHDN's method |
| Employer EPF on some sheets (and the 13% rate typed for lower wages) | Read from the EPF table for everyone |
| Past months in each sheet's Jan to Dec table | Kept by the app from each month's run |
| Year-to-date figures | Opening year to date plus the months kept |
| Names on the Summary sheet | From the staff record |
| Transport allowance, insurance premium | Fixed items on the staff record |

**Weaknesses found in the workbook** (structure only, no personal data). Each becomes impossible in the app:

| Found | Why it matters | In the app |
|---|---|---|
| Year-to-date boxes built with hard-coded "x 7" multipliers and typed lists of past PCB | Wrong after month 7; PCB and the EA form depend on correct year to date | Year to date is always the opening figure plus the months kept |
| A self-check cell showing FALSE | A mismatch already present and unnoticed | Every run checks itself and cannot be approved if totals disagree |
| One person's Summary row taking EIS from **another person's** sheet | Wrong EIS paid and reported for both | Each figure belongs to one person; no cross-links possible |
| One row's basic pointing at the **August** row instead of the current month | Wrong month's pay used | The run uses the month being run |
| One row pulling EPF, SOCSO, EIS and Lindung 24 Jam from **a different workbook** | Breaks when that file moves or changes | Everything is in the one set of records |
| Prorated salary never rounded | Totals carry fractions of a sen, so the bank total and the authority totals do not match exactly | Pay lines rounded to the sen by one rule |
| EPF a formula on most sheets but typed on one | Easy to miss a rate change | One rule for everyone |
| A leaver kept as a row of zeros; some names typed | Summary can disagree with the payslips | Lists come from who was employed that month |

### Starting mid-year

If payroll goes live part way through a year, each person's pay, EPF, PCB and zakat for the earlier months are
imported as **opening year to date** (from the workbook's per-person Jan to Dec tables), so year-to-date PCB and the EA
form are right.

### The parallel run

For 2 to 3 months, the owner keeps doing the workbook as today **and** runs payroll in the app. For each person and
each figure the app shows its figure beside the one entered from the workbook (or from the government calculators),
and lists every difference. The app's payroll becomes the source only when a whole month agrees, or every difference
is explained and the owner signs it off.

Until then, payments keep coming from today's recurring salary rows.

### Switching over

From the month the owner signs off the switch, the company's recurring salary rows and statutory rows stop ("Stop
using", with that month as the last), and To pay takes salaries and statutory payments only from the approved run. The
app refuses to approve a run while recurring salary rows for the same people and month are still in use, so nothing is
paid twice.

### Trade-offs (as explained to the owner)

- Statutory tables and rates change, sometimes with little notice (EPF, SOCSO, EIS, Lindung 24 Jam, PCB schedules,
  minimum wage). Each change has to be added to the app from its date and tested against the government calculators.
- Statutory file formats change too, and the portals may refuse an old format.
- PCB by the computerised method has many cases (bonuses, arrears, prior employer, reliefs). The first version covers
  the cases the company has; others are flagged "check with the calculator".
- The app is not certified by LHDN. PCB follows LHDN's computerised-method specification for each year; each new
  specification is added with its date and the parallel run is repeated for one month. The parallel run and yearly
  checks against the calculators are the safeguard.

### Out of scope at first

Attendance and clock-in, overtime from time records (overtime is typed as an amount or hours), recruitment,
performance reviews, staff self-service, benefits-in-kind valuation (typed as an amount if any), multi-currency
salaries, foreign worker levy.

---

## 7. Payments section

| Page | What it does |
|---|---|
| **Approvals** | Every approval form, printed and uploaded; what still waits for one; the Paid without approval on file list; print form (single or batch), upload, and the Not approved and Withdrawn dialogs (with a reason). Excel export of all forms: who signed, date signed, upload date, requests covered. |
| **To pay** | Every approved item not yet paid, from any origin: claims, advances, salary run (net pay per person, totals per authority), supplier bills, and recurring payments now due. Grouped by due date, with total. Select several and **Pay**, or open one. Items on hold for tax clearance are marked. Excel export. *Proposal, not yet decided (open question 11):* a second tab "Waiting for approval" listing unapproved items, payable anyway and marked. |
| **Add payment** | Today's New payment, for anything not coming from a request (a one-off bill, money in). Can be marked as needing approval. For a Kept here company, money in from a customer opens a Sales receipt instead (section 8). |
| **Payments register** | Today's company month page: every outgoing payment of the month, its status, documents and approval marker, with money in counted apart as today; the payment dialog (with the **Bank account** field, already agreed); History. Each payment from a request links to it. Excel export. |
| **Monthly checklist** | Today's checklist and filing of the month, with the items that tick themselves, plus "Approvals on file" and (if agreed) "Month reviewed". Mark month as filed. |
| **Budget** | As today: bank balance and date, still to pay, funds to request, print and Excel. |
| **Recurring** | As today, without salary advances (now in HR). Salary rows show the linked staff record; with payroll they stop at the switch-over (section 6). |

**Kept in SQL Account and Kept here:**

| | Kept in SQL Account (stage 1) | Kept here (stage 2) |
|---|---|---|
| Pay | Enter paid date, bank reference, bank account | The same |
| Record | The SQL payment voucher is matched to the payment (Fetch or import); "Waiting for SQL record" until it is | Paying creates the payment voucher in hr-payments' own books, numbered at posting (PV series restarting each month), never edited after, cancelled vouchers keep their number |
| Reconcile | Bank statement lines matched to the payment (Accounting) | The same, against the voucher posted here |

**Changing a payment, Kept here.** Once the voucher is posted, changing the bank account, amount or date of a payment
cancels that voucher (it keeps its number, with a reversal) and posts a new one. The dialog says so before saving.
The voucher's posting date sets which month's series it takes. Payments in a locked month cannot be changed, and
posting into a locked month is refused.

**Paying without a request, Kept here.** Paying straight to an expense account against the bank is allowed only for an
Add payment that has no request behind it. A supplier bill or staff claim always goes through its payable (sections 5.4
and 8).

---

## 8. Accounting section

| Page | What it does | Which companies |
|---|---|---|
| **Bank and reconciliation** | Bank statements imported per account and month (moved here from Monthly work), lines matched or explained, the reconciliation statement, sign-off, before tracking. The statement is evidence checked against the books. Items only on the statement (bank charges, interest) are booked from it after checking: Kept in SQL Account by noting they must be entered in SQL; Kept here by posting a payment voucher (money out) or official receipt (money in) from the line, numbered at posting and linked to it. A signed-off reconciliation month is locked; reopening it is logged and needs the sign-off again. | Both |
| **SQL import** | Everything on today's SQL page except e-Invoices (see the section 2 table). | Kept in SQL Account only |
| **e-Invoices** | MyInvois e-Invoices (issued, self-billed, received), links to documents, unbooked received e-Invoices; printed invoices, debit and credit notes and self-billed vouchers, month zip. | Both (Kept here submission method still to decide) |
| **Books** | Four tabs: trial balance (Kept in SQL Account: checked against SQL's), general ledger, profit and loss, balance sheet. From / To bar and "financial year to date", Excel, trial balance account opens its ledger, ledger line opens the document. | Both |
| **Customers and suppliers** | Both sides; list with ageing; one party's statement; as-at date. | Both |
| **Statutory payables** | Withheld versus paid by the due date, per authority and payroll month; Net salaries payable with the check that each run's net pay is paid in full; "use this account", link to the payment, link to Setup. | Both |
| **Sales** | Customer invoices, debit notes, credit notes (mandatory original-invoice reference), receipts (OR series) knocked off to invoices. | Kept here |
| **Purchases** | Supplier invoices (PI series), debit and credit notes, payments (from Payments), knock-off. | Kept here |
| **Journals** | Journal vouchers, opening balances, reversals. | Kept here |
| **Period close** | Month locks, year-end close, numbering gap check. | Kept here |

Books, Customers and suppliers, and Statutory payables share the same From / To and "financial year to date" control
(Customers and suppliers uses its To date as the as-at date).

### Bank reconciliation statement and sign-off (decided 18 November 2026)

Today the reconciliation is printed only inside the audit pack and the month's Excel report, and the sign-off records a
date but no names. The redesign adds a printed **Bank reconciliation statement**, one per bank account and month,
printed from Bank and reconciliation. It applies to both kinds of company, and to Kept in SQL Account companies now.

**Layout (standard practice):**

```
Balance per bank statement at <last day>               X
Add: money in the books, not yet on the bank (each)   +
Less: payments in the books, not yet cleared (each)   −
Add / less: on the bank, not yet in the books (each)  ±
Adjusted bank balance                                  = Balance per books at <last day>
```

followed by:
- **Book entries where no money moved** (see below), each pair with its reason and net amount (nil);
- **Totals check:** money in and money out per the books, less the entries where no money moved, against the
  statement's total credits and total debits, so the debit and credit totals are shown to tally, not only the closing;
- for a Kept in SQL Account cash book: the check against SQL's balance on the bank's GL account (as today);
- **Prepared by** and **Reviewed by**: name, date and signature lines, and the sign-off note.

The form carries the same reference code, keyed check and QR as an approval form (section 4). The signed copy is
uploaded the same way and filed against the month; it is the detail behind the Month review sheet. If the
reconciliation changes after printing, the code no longer matches and the upload says so.

**Book entries where no money moved.** A receipt and a payment in the books that cancel out and never touched the
bank: for example a duplicated self-billed e-Invoice, where the PV was recorded twice and an OR was entered to refund
the duplicate, or a contra or reversal. In SQL Account these sit in the bank account, so SQL's bank reconciliation
clearing report lists them as uncleared, and the book debit and credit totals don't tally with the statement's even
when the closing balances agree. The app already spots such pairs on the SQL import page (a receipt and a payment for
the same amount on the same day, or a description saying reversal or contra). On the review screen:

- they show as a group **No money moved**, each pair together (the OR, the PV it cancels, the self-billed e-Invoice
  number when there is one) with its net, which must be nil;
- a reason is filled in for each pair, worded from the documents ("Duplicated self-billed e-Invoice SB…: PV… recorded
  twice, OR… refunds the duplicate; no money moved"), and can be edited;
- the person ticks each pair to confirm it. Sign-off is refused while a pair is unconfirmed, or while a pair's net is
  not nil (the remainder is then a difference to explain);
- a single entry with no partner is never explained away: it stays a reconciling item ("in the books, not on the
  bank") until it is corrected.

**The sign-off note.** On sign-off the app writes the note itself: each confirmed pair with its reason and amounts,
each line explained without documents, plus an optional free-text note. Sign-off needs the book closing to equal the bank closing, so no reconciling item is left on a signed statement. It
is kept with the sign-off as it stood (figures and reasons), shown on the screen, printed on the statement and in the
audit pack, so nothing has to be written by hand for the auditor. Undoing the sign-off keeps the old note in the
audit trail.

**What to do in SQL Account** (Kept in SQL Account; the statement says it in words): the pair stays in SQL's books.
The usual fix is to tick both the OR and the PV as cleared in the same month in SQL's bank reconciliation, since they
net to nil, so SQL's clearing report agrees; or to record future corrections like this as a contra or journal that
does not go through the bank account. A Kept here company never needs this: a duplicate is corrected by a credit note
or reversal on the payable, not through the bank (stage 2 rules).

**Supplier bills, Kept here.** A supplier bill's request is a Purchases supplier invoice (PI series), posted when
recorded: expense / Accounts payable. The approval covers that invoice. Paying it posts a payment voucher: Accounts
payable / Bank, knocked off to the invoice. So a bill approved but not yet paid at month end is in the books, and
supplier ageing and the Suppliers due card work.

**Money in, Kept here.** Money in from a customer is a Sales receipt (OR series) knocked off to invoices, so customer
ageing is right.

Stage 2 rules (decided 15 Nov): running numbers restart every month, one series per document type per company,
numbered at posting, never edited or reused; a cancelled document keeps its number; posted documents are corrected by a
credit note or reversal, never edited; the audit pack has a gap check. No Kept here page relies on SQL data.

Stage 2 is designed in detail later, on the new design. The redesign should reserve its menu places now.

---

## 9. Privacy and access

Staff records are **personal data** under Malaysia's Personal Data Protection Act 2010 (PDPA). **Sensitive personal
data** includes health (sick leave reasons, medical certificates) and religion. It needs the person's explicit consent
unless employment law requires it. Religion and race are optional, collected only with the person's written consent,
and left out of exports by default. Under the Act as amended in 2024, the company is a "data controller". In plain
terms, the company must:

- collect only what it needs for employment, pay and the law, and tell staff what is kept and why (a short notice,
  usually in the offer letter or handbook);
- keep it secure and let only the people who need it see it;
- keep it no longer than needed: at least 7 years after the year concerned for pay and tax records (Income Tax Act),
  and 6 years for Employment Act registers; after that it can be removed;
- let a person see and correct their own data on request;
- report a data breach to the Personal Data Protection Commissioner within 72 hours, and tell the people affected when
  it is likely to cause them significant harm (in force since June 2025).

What the app does about it:

| Now (before logins) | Later (with hosting and logins) |
|---|---|
| Runs only on this computer, as today | HR pages get their own access right; payroll and pay figures a tighter one |
| Backups are already encrypted; only encrypted backups go to OneDrive | Approvers log in to approve |
| The Overview never shows pay, IC, bank or medical details (section 3) | Staff see only their own leave and payslips (self-service) |
| The staff Excel export asks which columns, with IC, pay, religion and race off by default | Every view of a staff record is logged, not only changes |
| The audit trail already records every change, including HR records | Search and notifications respect access rights |
| Document file names inside a backup can be read without the password (as today): HR documents are stored under a code, not the person's name | Approvals and To pay visible to finance without HR access; salary-run detail only to HR and payroll |
| Audit pack HR pages hold only what an auditor needs (approvals, totals per authority, headcount), not payslips, unless chosen | Admin › Users and access sets each person's rights: HR, Payroll figures, Payments, Accounting, Approver, Admin |

The app helps; it does not make the company compliant on its own. The privacy notice and how long records are kept are
the company's decisions (section 11).

---

## 10. Order of work and what the redesign must design

### Order

1. The owner approves this scope.
2. **Redesign session**: designs the new shell and every screen below (design only). The existing canvas (52 boards)
   is reorganised into the new structure; existing boards are moved, not redrawn, where nothing changes.
3. This project **builds the shell and the moves** (the redesign build plan's slices, now under the new menu).
4. **HR step 1**: staff records, leave, calendar and reminders, claims, advances moved, approvals and To pay.
5. **HR step 2**: payroll, then the parallel run.
6. **Stage 2**: books kept in hr-payments.

### Screens and states the redesign must cover

Shell and Overview
- [ ] Side menu with Overview, HR, Payments, Accounting, Admin, drawn for three cases: Kept in SQL Account without
      payroll, Kept in SQL Account with payroll, Kept here; count badges
- [ ] Company switcher (one company, All companies on Overview, labels Kept in SQL Account / Kept here) and month
      switcher
- [ ] Overview with the audit-trail notice, Next up and the four card rows; All companies version (mixed company
      kinds); empty company; each card's empty, out-of-date and could-not-load states; the "Paid without approval on
      file" card shown and hidden; HR cards hidden for a user without HR access (later); the side menu for a user without HR access

Phone
- [ ] Overview: every card stacked, Next up first, company switcher and month in the top bar
- [ ] Company month; Payment (with the Approval marker and the link to its claim); New payment (with "needs approval")
- [ ] The "best done on a computer" page, used by every other screen (all HR, Approvals, To pay, Payroll and
      Accounting pages)
- [ ] Upload a photo of a signed approval form (agreed 17 November 2026): take the photo, code read from the QR,
      "which approver signed", code not readable (type it), reached from the Payment screen's Approval marker

HR
- [ ] Staff list (in employment, left, filters, All companies read only, empty state, first run "Add your staff or
      paste the Excel list") and Paste / import with preview and errors
- [ ] Staff record: Details, Pay (with salary history), Leave, Claims and advances, Documents (with expiries), History;
      add, edit, "Left" with last day; statutory categories worked out, with override and reason
- [ ] Staff Excel export with column choice
- [ ] Leave: taken and booked list (Booked, Taken, Cancelled), add leave (half day, certificate, over-balance and clash
      warnings), cancel with reason, balances table, team calendar month view, opening balances import, year-end
      carry-forward, maternity eligibility confirmation
- [ ] Calendar and reminders: list and month view, mark done, one-off reminder
- [ ] Claims: list by status, new claim with lines and receipts, over-limit flag, claim page with its approval and
      payment links
- [ ] Salary advances: list with balances, advance page, over-one-month and 50% warnings, balance left on leaving
- [ ] Payroll: month run (inputs to type, calculated table, checks, states Draft / Checked / Approved / Sent to pay /
      Filed), payslip PDF, monthly summary, per-authority totals, bank payment list, statutory files, leaver's final
      pay, parallel-run comparison with differences, sign-off, switch-over, run approved and sent to To pay, opening
      year to date import (preview and errors), Kept in SQL Account journal summary

Payments
- [ ] Approvals: print form (single and batch, mixed requests) and the printed form itself (code, keyed check, QR, 3
      approvers); upload with code read from text / QR / typed; date on the form; digital signer matched; signer not in
      the approvers list; paper scan "which approver signed"; form that no longer matches; form that matches some
      requests and not others; the same form uploaded twice; code not readable (type it); Not approved and Withdrawn
      dialogs with reason; same-name warning; approver is the payee; "Paid without approval on file" list; Excel export
- [ ] To pay (approved; tax-clearance hold; select several and Pay; empty; Excel; the proposed "Waiting for approval"
      tab only if agreed)
- [ ] Payments register and payment dialog with Bank account field, approval marker (all its readings) and request
      link; Kept here "this cancels voucher PV… and posts a new one" warning; locked month
- [ ] Add payment (with "needs approval"; Kept here money in opens a Sales receipt)
- [ ] Monthly checklist with the approvals item (and Month reviewed, if agreed)
- [ ] Budget, Recurring (salary rows linked to staff, advances removed, rows stopped at switch-over)

Accounting
- [ ] Bank and reconciliation (moved), with "book this statement line" for Kept here, one line matched to a group of
      payments, locked month and reopen
- [ ] Review screen's "No money moved" group: pairs with their documents, reason (filled in, editable), net nil or
      not, tick to confirm; sign-off refused while a pair is open; the sign-off note as written by the app, plus a free
      note; undo sign-off
- [ ] Bank reconciliation statement: print, upload the signed copy (code read, matched, "changed since printed")
- [ ] SQL import (Kept in SQL Account only): nothing waiting, preview of a fetch, changed in SQL, replaced by a later
      version, probably a correction, deleted in SQL and Ignored, before tracking, journals and invoices, find an SQL
      entry, imported files, folder setting, and the "this company is not kept in SQL" message
- [ ] e-Invoices page (split from SQL)
- [ ] Books: four tabs, date bar, Excel, account to ledger, document pop-up
- [ ] Customers and suppliers: two sides, list with ageing, one party's statement, as-at date
- [ ] Statutory payables: per authority, Net salaries payable, use-account action, link to payment, link to Setup
- [ ] Placeholders for Sales, Purchases, Journals, Period close (Kept here, detailed later)

Admin
- [ ] Setup with the new HR group: approvers (with their history), leave types and policy, public holidays by state,
      claim types, payroll settings (Pay items with their ticks, statutory tables and rates with dates, due dates,
      minimum wage, employer numbers, HRDF rate)
- [ ] Audit pack with HR pages, Paid without approval on file / Approved after payment, approver history, steps done
      by one name alone, "declared, not verified" labels
- [ ] Audit trail, Backup (moved)
- [ ] Users and access: list of people, add or edit a person, the six access rights, remove access; drawn now, built
      with logins later

Carried over, now with HR and approvals
- [ ] Search results including staff and requests
- [ ] Notifications: approval form uploaded, form not matching, leave ending, permit expiring
- [ ] Undo on toasts and sidebar badges for the new pages (To pay and Approvals counts)
- [ ] Document viewer beside the payment dialog, also for receipts and signed forms
- [ ] Overview extras (Funds to request, Recent activity, Needs attention tab, company filter)
- [ ] Sign-in set: sign in, session timed out, user menu, real names in the audit trail

Printed and downloaded
- [ ] All in English. Bank reconciliation statement (standard layout, No money moved pairs, totals check, Prepared by
      and Reviewed by, code and QR), approval form, payslip, Month review sheet, staff record PDF, leave and claim lists as printed, audit pack HR
      pages and Paid without approval page, bank payment list, statutory file preview, budget print (exists), payroll
      journal summary. Excel columns are listed by the build, not drawn.

Every list: empty, loading, error, many rows; every form: saving, refused with the reason, Discard changes?

### Out of scope

Attendance and clock-in, recruitment, performance reviews, staff self-service and director logins (until hosting with
logins), benefits-in-kind valuation, foreign worker levy, submitting files directly to EPF, PERKESO or LHDN portals
(the app makes the files; a person uploads them), writing anything back to SQL Account.

---

## 11. Open questions for the owner

1. **Recurring bills and approval.** Do recurring payments (rent, utilities, statutory payments) need an approval form
   each month, or is setting them up once enough? (Suggested: once, when set up or changed.) *Answered 17 November 2026:* once, when set up or its amount changes.
2. **Who is "staff".** Are contract workers (paid with only an employer SOCSO contribution, as in the old template) and
   directors kept as staff records, or only as payees? *Answered 17 November 2026:* directors on the payroll are staff records; contract workers stay payees unless on the payroll.
3. **Leave policy.** Does the company give more than the legal minimum for any leave type? Is unused annual leave
   carried forward, how much, and until when? *Partly answered, 17 November 2026:* the owner asked whether this is
   part of the setup. Yes: leave types, entitlements by years of service, carry-forward, half days and the public
   holiday calendar are all set in Setup › HR › Leave, pre-filled with the legal minimums and editable at any time with
   the date a change applies from (section 5.2). *Answered 17 November 2026:* the legal minimums stay the
   entitlement; leave beyond the legal days, or a value set above the law, shows a warning only and is never refused.
4. **State for public holidays.** *Answered 17 November 2026:* the office is in Kuchai Lama, so Wilayah Persekutuan
   Kuala Lumpur holidays apply, one location for the whole company (section 5.2).
5. **HRDF.** *Answered 17 November 2026:* the company has 8 employees and the owner is not sure it is registered; the
   2026 books show no HRDF levy paid. At 8 Malaysian employees registration is optional (required from 10). Setup
   keeps an HRDF setting, off by default, with a note to confirm on HRD Corp's portal, and a warning when the
   Malaysian headcount reaches 10 (section 6).
6. **Payroll for which companies.** *Answered 17 November 2026:* only the owner's main company for now, as a per-company setting ("Runs payroll in this app"), since the app is built for bigger companies too. The payroll workbook check is available to every company.
7. **Payslips.** Printed and signed as today, or also emailed to each person as a password-protected PDF? *Answered 17 November 2026:* printed and signed, and also emailed as a password-protected PDF.
8. **Bank payment list.** Which bank's bulk payment format should it produce (the company banks with Maybank today)? *Answered 17 November 2026:* Maybank's bulk payment file, if the company uses Maybank bulk payment (confirm when payroll is built).
9. **Claims paid with salary.** *Answered 17 November 2026:* paid separately, after approval (section 5.4).
10. **Records kept how long.** How many years after a person leaves should their record stay before it is removed?
    (Suggested: 7 years after the person leaves.) *Answered 17 November 2026:* 7 years after the person leaves.
11. **"Waiting for approval" in To pay.** Should To pay also show unapproved items in a second tab, payable anyway and
    marked? Or should they show only on Payments › Approvals? (Suggested: only on Approvals.) *Answered 17 November 2026:* only on Payments › Approvals.
12. **Month review sheet.** Should one approver sign a printed Month review each month (payments total, Paid without
    approval list, approvals attributed to each approver, bank reconciliation), with a checklist item that ticks only
    once it is uploaded? (Suggested: yes, while one person does every step.) *Answered 17 November 2026:* yes.
13. **Leave approval.** Is leave only recorded by HR for now, or should a director approve leave too? *Answered 17 November 2026:* recorded by HR only for now.
14. **Phone upload.** Is uploading a photo of a signed approval form from a phone wanted as a fifth phone screen, or is
    it done on the computer? *Answered 17 November 2026:* yes, as a fifth phone screen.

**Rate checks answered on 17 November 2026:**
- EPF, SOCSO and EIS rates applied from October 2024: *confirmed by the owner.*
- Lindung 24 Jam from June 2026: the owner believed so; *confirmed* by PERKESO's FAQ (in force from the June 2026
  contribution month). The 2026 books also show the first deduction labelled June 2026.
- 60-and-over rates from the month after the 60th birthday: the owner said yes if it is the official rule. Research
  found no official text giving the month, so it stays the app's rule as common payroll practice, marked *check with
  KWSP and PERKESO* (section 6).

---

## 12. Glossary

| Word | Meaning |
|---|---|
| Kept in SQL Account (stage 1) | A company whose books are kept in SQL Account; hr-payments only tracks and matches. |
| Kept here (stage 2) | A company whose books are kept in hr-payments itself. |
| Keyed check | A short code printed on an approval form that stops matching if the form's details are changed. |
| Voucher | A numbered accounting document: payment voucher (PV), official receipt (OR), journal voucher (JV), supplier invoice (PI). |
| Posting / numbered at posting | Writing a document into the books; it gets its running number at that moment. |
| Reconcile | Checking the books against the bank statement, line by line. |
| Ageing | How long each unpaid amount has been owed (for example 0-30, 31-60 days). |
| Knock-off | Linking a payment or receipt to the invoice it settles. |
| Payable | Money the company owes and has not paid yet. |
| Third Schedule | EPF's official table of contributions by wage band. |
| Form A | EPF's monthly contribution list. |
| e-PCB Plus (formerly CP39) | LHDN's system for the monthly PCB file. |
| TP1, TP2, TP3 | Staff forms for PCB: extra reliefs (TP1), benefits in kind (TP2), pay from an earlier employer this year (TP3). |
| EA form, Form E, CP8D | Yearly pay statement to each person (EA); the employer's yearly return (Form E) with its staff list (CP8D). |
| e-CP22, CP22A, CP21 | Notices to LHDN: a new employee; an employee leaving (in certain cases); an employee leaving Malaysia. |
| Proration | Paying part of a month's salary for part of a month. |
| Ordinary rate of pay | One day's pay as the Employment Act works it out (monthly pay / 26). |
| Parallel run | Running payroll in the app and in the workbook side by side to check the app. |
| Cannot be changed unnoticed | The app keeps a fingerprint of each stored document, so any change shows up. |
