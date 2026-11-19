# Shared sample data for the new scope (packages A to K)

Every board drawn or redrawn for the new scope (HR, Payments, Accounting, Admin, the shell) takes its names, codes,
counts and badges from this file. It builds on `stage1/samples.md`: **every figure there stays** (books, SQL, bank,
statutory, MyInvois, audit pack). This file adds what the new scope needs and settles where the review
(`docs/design/2026-11-17-redesign-scope-gaps.md`, sections 4 and 7) disagreed with stage 1 or with the boards.

- Where this file and `stage1/samples.md` differ on a books figure, stage 1 wins (none should).
- Where this file and the review differ, this file wins. The Decisions list says why.
- Every person, company and number here is made up. Before using a new name, check
  `git -C C:\GitHub\hr-payments log --all -S'<surname>' --oneline` returns nothing and that the name is not in the
  app's code or tests.
- Format rules as stage 1: money `1,234.56`, no "RM" in report tables, `—` unknown. On screen a company is **Kept in
  SQL Account** or **Kept here**, never "stage 1/2".
- IC numbers are never written in full anywhere on a board: use the masked form `••••••-••-1234` (as
  `payrollcheck.mask` prints it). A passport reads `••••1307`.

---

## 0. Decisions

**D1. Workbook checks re-dated (review: 5 and 6 Nov).** A check is done before paying, so:
- October: "Example Payroll - OCT 2026.xlsx" checked **Wed 21 Oct 2026 10:12** ("3 things to fix before paying, 2 to
  check; 9 notes"), the corrected file "Example Payroll - OCT 2026 (corrected).xlsx" checked **Thu 22 Oct 09:40**
  ("Nothing to fix or check; 9 notes"). Salaries were paid Sat 24 Oct. October's latest check has nothing to fix, so
  October gives no rule 15 row.
- November: AISB's November 2026 was set up on **18 Nov 09:05** (by Aisha Rahman) to prepare November pay, and
  "Example Payroll - NOV 2026.xlsx" was checked **18 Nov 09:20**: "3 things to fix before paying, 2 to check; 10
  notes". This is the only rule 15 row on the default Overview: **"Nov AISB: the payroll check found 3 things to fix
  before paying"**. So the Payroll badge of 1 is true.
- Notes are counted as the code counts them: one "SKBBK is 0" note per payslip (no one has Lindung 24 Jam deducted)
  plus the always-present "PCB amounts themselves are not checked" note. October has 8 payslips (9 notes), November 9
  (10 notes). The review's "4 notes" and "1 note" can't come out of the code with these figures.

**D2. Menu cases and badges.** Section 15 gives each company's badge per menu item and the row counts. Badges follow
the existing ONE BADGE RULE (Sidebar.dc.html line 80): a menu item's number is how many Next up rows belong to it,
blue, and red with the alert glyph only when one of those rows is overdue. Approvals and To pay are the only **count**
badges (requests waiting for approval; items in To pay), blue, To pay red when an item in it is overdue. A Next up row
whose place is To pay (the "Pay KWSP" rows) is counted inside the To pay count, never added to it.
- **The Payroll badge is blue**, not red as the review said: rule 15 has no due date, so it is never overdue.

**D3. Company switcher list.** Section 3. The default canvas world has **two companies in use (AISB, AI)**; AIL and
AIP are the four-company variant used for the menu cases and the long switcher list. The stopped company shown "not
offered" is SetupCompanies' existing **OLD · Former Trading Sdn Bhd** (stopped 30 Jun 2025); TEST · Training company
(stopped 21 Jul 2026) is not offered either.

**D4. Contradictions settled (the existing boards win unless wrong).**
1. **AISB's name** is "AISB Sdn Bhd" (SetupCompanies, stage 1), not the review's "Agrinexus Sdn Bhd".
2. **AISB's holidays**: Wilayah Persekutuan Kuala Lumpur (the scope names it for the owner's company), rest day
   Sunday. The printed address in Petaling Jaya stays: holidays follow where the staff work, and Setup › HR › Public
   holidays says so in its hint ("The state where the staff work, not the printed address"). **AI's holidays: Sabah**,
   because Budget.dc.html already puts AI's office rental at "Lot 4, Kota Kinabalu". AI's staff work in Sabah, which
   gives the scope's "Sabah and Sarawak note" a real case.
3. **No foreign worker at AISB.** The October SOCSO and EIS totals already on the boards (205.00 / 717.60 and
   81.90 / 81.90) only fit eight Malaysian contributors: a foreign worker would add about 69.40 of employer SOCSO
   (employment injury, 1.25%). So all eight October staff are Malaysian and S008 is **Nur Izzati binti Kamal**. The
   foreign-worker case (passport, work permit expiring 10 Jan 2027) moves to **AI's Rina Santoso (A005)**. AI doesn't
   run payroll in the app, so no AI figure has to change.
4. **Per-person October pay is new and ties exactly.** The review's basics and nets did not give the boards' totals
   under the code's own EPF, SOCSO and EIS rules. Section 6 replaces them with figures that give gross 59,147.90, net
   48,600.00 and every statutory total to the sen, and that the Payroll check passes.
5. **Cleaning service is not an October payment.** Recurring.dc.html has it stopped on 12 Oct at RM 650.00. It is
   not in Company's October list or on the October bank statement. The "Paid more than approved" case is
   **Stationery Mart, PV2610-022, RM 1,120.00 paid 30 Oct (cheque 000214), approved RM 1,000.00** (already on
   BankReview and in SQL). The register must gain this row (section 17).
6. **SA-2611-001 (Hafiz's advance) is not paid yet.** A payment on 4 Nov from Maybank current would need an SQL
   voucher in the journal read to 17 Nov, and rule 7 would count 5 payments not recorded, not 4. It is approved
   (3 Nov) and in To pay, due Fri 20 Nov, before the first deduction on 24 Nov. **To pay is 6 for AISB, not 5.**
7. **The October salary run form is AF-2610-009** (printed 21 Oct, signed 22 Oct by Hassan Ismail), not AF-2611-005:
   a November form can't approve pay sent on 24 Oct. It exists on the step 2 boards only (PayrollRun, PrintApprovalForm
   salary-run state). In today's world October's salaries were approved once on the recurring set-up form AF-2610-001.
8. **Recurring "approval once" reads "Approved by Rajesh Kumar, 1 Oct 2026"** (AF-2610-001, salaries and director
   fee), not 3 Nov: 3 Nov is the advance's form, and a 3 Nov approval would leave October's salaries unapproved.
9. **Names changed** after the git and code check: Kevin Lim → **Marcus Teoh**; Lim Jia Hui → **Goh Jia Hui**;
   Kavitha Raman → **Kavitha Nair**; Muhammad Hafiz Rosli → **Mohd Hafiz bin Rosli**; Siti Khadijah Omar → **Nor
   Khadijah binti Omar**; Ahmad Faizal Yusof → **Mohd Faizal bin Yusof**. "Kevin" is in the app's tests, "Lim",
   "Raman", "Siti" and "Ahmad" are in its git history as people's names, and "Muhammad" is in a code docstring. Every
   name in this file passed the check on 17 Nov 2026.
10. **The leaver's last day is 31 Aug 2026**, not 30 Sep: September and October both pay "8 people" on the boards, and
    Goh Jia Hui joined on 1 Sep in her place (August's 8 included Kavitha).
11. **Wei Ming's October claim** ("Oct 2026 Claims - Wei Ming", RM 486.50, due 14 Nov) is unpaid and **Past due**:
    approved on AF-2611-003 and in To pay since 13 Nov. Company's "Waiting for SQL record" (probably paid) and its
    file "Approval - claims October.eml" give way to this: a request's payment is paid only from To pay.
12. **To pay** lists unpaid items that are approved or need no approval. Statutory payments, utilities and money in
    need none. A payment flagged "Waiting for <month> statement" (probably paid by direct debit) is not in To pay.
    **Needs approval** defaults by payment type, in Setup › Payment types' labels: Salary, Director allowance,
    Rental, Consultant fee, Other payment, Staff claim, Salary advance and Payroll run: yes. Statutory, Utility /
    telco and Money received: no.
13. **Checklist counts.** The two new built-in items ("Approvals on file for every payment", "Month reviewed") join
    every month from **October 2026**, the first month approvals are kept. AISB October: **18 of 27** (both new items
    open). AI October: **15 of 22** (approvals item ticks itself, Month reviewed open). September stays AISB 23 of 25,
    AI 20 of 20 (filed).
    - **AISB November 2026: 1 of 30** (the 27 items, e-CP22 for Daniel, Stamp the contract of Daniel, and Register
      Daniel with KWSP and PERKESO done 10 Nov); CP22A for Kah Seng waits for December. The stamp task comes from the
      SetupChecklist template (his basic of 3,500.00 is over 3,000.00). It is a checklist item only, **not a Next up
      row**: AISB's 11 Next up rows and every badge stay as sections 14 and 15.
    - **"Documents missing 2"** (AISB October, Overview) counts the 2 checklist items whose documents are missing:
      "KWSP, PERKESO and PCB paid or acknowledgement filed" (the KWSP acknowledgement) and "Fund receipts: OR and
      validated e-Invoices add up" (the e-Invoice). The counter opens MonthlyChecklist's "Missing documents 2" filter
      (`#missing-documents`).
14. **HRDF.** AISB's "HRDF registered" is off and its HRD Corp employer no. is blank: the review's "HRD-0012345" with
    registration off contradicted itself. AISB has 9 Malaysians in employment on 18 Nov, so the 10-or-more warning
    shows only in a what-if.
15. **Overdue** means: a customer balance older than 30 days (owner, 17 Nov); a supplier invoice past its date (Setup
    holds no supplier terms, so it is due on its date). So the consultant's PI2610-013 is overdue on the Suppliers due
    card and past due in the register, the same story.
16. **Next up gains HR reminder rows** (scope 5.3: probation, contract or leaver, permit). The rule 16 rows
    (probation, permit) are written without names. Joiner and leaver reminder rows show the SetupChecklist template
    title with the preferred name ("e-CP22 for Daniel", "CP22A for Kah Seng"), as the app shows reminder titles. Rule
    16 is new_work (no rule number in the code yet; call it rule 16, HR reminders).
17. **AI has no claim types**: claim types need an expense account and AI has no chart of accounts (stage 1), so
    Setup › HR › Claim types for AI is "None yet". AISB's claim types use 900-800, 900-600 and three accounts AISB's
    chart must gain: 900-850 Staff welfare (already in SetupChart's paste sample), 900-860 Travelling and 900-870
    Entertainment (new).
18. **Rule 14 wording** follows the review: "…Check it on Statutory payables.", meta "AISB · Accounting › Statutory
    payables". All Next up metas use the new menu words (section 14).
19. **What package K settled** (these were left for K):
    - **AI's KWSP for October is RM 4,478.00** (employee 2,083.00, employer 2,395.00), worked out by the Third
      Schedule from AI's basics (section 5; arithmetic in section 18). It replaces 11,240.00 on every AI row. AI's
      other paid amounts are as recorded in the register (PERKESO 612.40 paid 14 Nov is the recorded amount, not
      derived from the basics, which would give about 517); only the KWSP is derived.
    - **Budget follows the Payments register.** The contractor was paid 6 Oct (PV2610-003); Electricity 1,163.20 paid
      4 Nov; Telephone & internet 398.60 paid 28 Oct; PCB paid 14 Nov; PERKESO paid 17 Nov; KWSP and the consultant
      unpaid. Stationery Mart 1,120.00 (paid 30 Oct) and the three AF-2611-003 claims (unpaid) are payments with no
      budget line. AISB's balance is on **Mon 19 Oct 2026, RM 56,790.35** (section 16).
    - **AI has no RM balance entered**: its only account is Maybank FCA (USD). AI's Funds to request shows "Enter the
      bank balance to see funds to request", so the old 11,200.00 against 11,310.00 mismatch is gone.
    - **Consultant**: the payee and short name are **Payroll Advisory PLT** everywhere; SQL's name for 400-P004 stays
      "Payroll advisor". "Robin Advisory" and "Robin Advisory Sdn Bhd" are gone; bank boards read "Consultant fee —
      Payroll Advisory PLT".
    - **Insurance renewal** 2,498.60 is an AISB budget line only, with no payment entered yet. It is not a tracker
      payment, so no bank review candidate or SQL payment carries it.
    - **Telephone & internet**'s 28 Oct bank line (398.60) is not on the October statement: left as stage 1 §25
      leaves it, because rule 7's "4 payments not recorded" depends on it.
    - The Overview's September bank movement against the September register: left as stage 1 §25 leaves it.
    - **The KWSP double row is settled (owner, 19 Nov 2026): one Next up row per unpaid statutory payment.** While a
      statutory payment for the month is entered and unpaid, Next up shows only its payment row, "Pay KWSP for
      October" (overdue after its due date, 15 Nov), and not rule 14's "AISB: EPF (KWSP) for October 2026 wasn't paid
      by 15 Nov 2026. Check it on Statutory payables." Rule 14 shows only when there is no unpaid payment to point at
      (paid short, or never entered). AISB's October KWSP is entered and unpaid, so section 14 drops row 2 (statepf)
      and every count from Next up follows (sections 3, 14, 15, 18). Statutory payables itself still finds October
      late, and the audit pack's statutory page is unchanged.

20. **Names and facts K settled** (every board uses these):
    - **Payments** are named as the app names them (`hrp/rules.py` "KWSP payment", the recurring payee "KWSP",
      checklist "KWSP"): **KWSP**, **PERKESO**, **PCB** ("KWSP for October", "Pay KWSP for October", "KWSP ·
      September"). Never "KWSP (EPF)", "PERKESO (SOCSO & EIS)", "PCB (MTD)" or "LHDN (PCB)" on a payment.
    - **Statutory kinds** keep the app's kind words (`statutory.KIND_WORDS`): **EPF (KWSP)**, **SOCSO (PERKESO)**,
      **EIS (SIP)**, **PCB (LHDN)**, on Setup › Statutory accounts, Statutory payables, Next up rule 14, the audit
      pack statutory page, payslip and statutory deduction labels, and employer-number fields.
    - **Reminder titles** are the SetupChecklist template filled with the preferred name wherever a reminder title is
      shown, Next up included: "e-CP22 for Daniel", "CP22A for Kah Seng", "Register Daniel with KWSP and PERKESO",
      "Stamp the contract of Daniel". Prose around them may stay descriptive.
    - **Net salaries payable** (420-000 Accruals) was confirmed for AISB on **Fri 13 Nov 2026**, before the 14 Nov
      audit pack; stage 1's "4 statutory accounts added" (18 Nov 10:50) stands, and Statutory payables' suggestions
      leave it out.
    - **AIP has no approvers** ("None yet"): the no-approvers example on Approvals, the approval form print and Setup ›
      HR › Approvers.
    - **SA series is app-wide**, like AF: a new AI advance today is **SA-2611-003**.
    - **Customers and suppliers**: Setup › Customers and suppliers' 9 rows are the one list. The cleaning service
      is **400-C003** (the stopped "Old cleaning contractor"); the water supplier is **400-W001**; the office
      landlord (Menara Holdings) is paid to **CIMB 8006447122**.
    - **Payment types**: Setup › Payment types is the single list (`hrp/rules.py` CATEGORIES and DOC_TYPES plus the
      canvas's added types). Recurring maps Director → "Director allowance", Office rental → "Rental", Cloud hosting,
      Cleaning and Security → "Other payment", Utility → "Utility / telco", Consultant → "Consultant fee", Money in →
      "Money received". Document types use the full DOC_TYPES labels.
    - **Recurring** rows: AISB 11, AI 4, 15 in all. KWSP's recurring history and the audit trail read "11 Nov 2026
      14:20, 11,180.00 → 11,240.00, October's contributions from the payroll summary". The consultant fee started
      1 Sep 2026 and is approved per payment (latest AF-2611-004, waiting).
    - **AISB October Electricity bill**: paid Wed 4 Nov, RM 1,163.20, linked to PV2611-003 (version 2 changed in SQL
      to 1,136.20; rule 7's "1 voucher changed in SQL" counts it), paid date typed in because the November statement
      is not imported (stage 1 §23). It is no longer "Waiting for Nov statement".
    - **Months**: AISB's September 2026 is Still open; only AI's September is filed (5 Oct). Setup refusals that need
      a filed month use AI.
    - **Rollover banner** counts the October Next up rows of the company it names: "AISB … 4 things left"; e-CP22
      is a November item (the command palette tags it "Nov 2026").
    - **Statements and notifications**: Maybank current's October statement had 14 lines, 8 matched, imported 3 Nov
      09:40; Maybank FCA's October statement had 2 lines (5 Nov). The Office rental bank slip was uploaded 13 Nov
      10:42. The bell shows 6 unread (7 with trail attention).
    - **Trial balance read times** (stage 1 §21). "Differs": journal read 18/11/2026 10:42, SQL's TB read 18/11/2026
      10:58 (10:58:41), so the TB holds JV2610-012 (Dr 900-010 / Cr 310-000 48.00) and the journal does not:
      310-000 33,570.35 (TB) against 33,618.35 (journal), 900-010 58.00 against 10.00. "Stale": TB read 10:58, journal
      read again at 11:05. There is no 17/11 09:10 read.

---

## 1. Today and months

| What | Value |
|---|---|
| Today | **Wednesday 18 November 2026** |
| Month worked (top bar label) | **October 2026** (not "October 2026 payroll") |
| Payroll month runs until | the **20th** (SetupGeneral): on 18 Nov the current cycle is October |
| AISB months | August 2026 Before first month (holds payments) · **September 2026 Still open** · **October 2026 Current** · **November 2026 set up 18 Nov 09:05** · December 2026 Not set up |
| AI months | September 2026 Filed 5 Oct · **October 2026 Current** · November 2026 **Not set up** |
| First month tracked | September 2026, both |
| First month with approvals | **October 2026** (approval forms and the two new checklist items start here) |
| SQL (AISB) | fetched 18 Nov 10:42; listings to 12 Nov; GL Journal of Transaction to **17 Nov**; trial balance as at 31 Oct |
| Bank statements | October imported for Maybank current, Maybank savings (AISB) and Maybank FCA (AI). November not imported. |
| Last backup | 11 Nov, 7 days ago |
| This week | Mon 16 Nov to Sun 22 Nov |

Weekdays used: Sat 3 Oct, Mon 5 Oct, Mon 12 Oct, Wed 14 Oct, Wed 21 Oct, Thu 22 Oct, Sat 24 Oct, Fri 30 Oct, Mon 2 Nov,
Tue 3 Nov, Wed 4 Nov, Thu 5 Nov, Fri 6 Nov, Sun 8 Nov, Mon 9 Nov, Wed 11 Nov, Thu 12 Nov, Fri 13 Nov, Sat 14 Nov, Sun
15 Nov, Mon 16 Nov, Tue 17 Nov, Fri 20 Nov, Mon 23 Nov, Tue 24 Nov, Wed 25 Nov, Fri 27 Nov, Mon 30 Nov, Tue 1 Dec, Thu
3 Dec, Mon 7 Dec, Thu 10 Dec, Fri 25 Dec, Thu 31 Dec, Sun 10 Jan 2027, Mon 11 Jan 2027.

---

## 2. Companies

| | AISB | AI | AIL (variant) | AIP (variant) |
|---|---|---|---|---|
| Full name | AISB Sdn Bhd | Agrinexus International | Agrinexus Logistics | Agrinexus Plantations |
| Kind label | **Kept in SQL Account** | **Kept here** | **Kept in SQL Account** | **Kept here** |
| Runs payroll in this app | **On** (the first company with it on) | Off | Off | Off |
| HR › Payroll shows | Workbook check, Run, Totals, Statutory files, Leaver, Parallel run, Opening YTD | Workbook check only | Workbook check only | Workbook check only |
| Payroll check used | Yes (October and November checks) | No check yet | No check yet | No check yet |
| Staff | 9 in employment + 1 left | 5 | not drawn | not drawn |
| Approvers (Setup › HR) | Hassan Ismail (from 1 Jan 2025), Tan Mei Ling (from 1 Jan 2025), Rajesh Kumar (from 1 Jul 2026). Former: Farid Osman, 1 Jan 2025 to 30 Jun 2026. List full (3). | **Hassan Ismail only**: self-approved case | Hassan Ismail, Tan Mei Ling | **None yet** (the no-approvers example) |
| Public holidays | **Wilayah Persekutuan Kuala Lumpur**, rest day Sunday | **Sabah**, rest day Sunday | WP Kuala Lumpur | not drawn |
| Work location of staff | Peninsular Malaysia | Sabah (the Labour Ordinance note shows) | — | — |
| Leave policy | "Same as the law" for every type | "Same as the law"; note "Sabah follows its own Labour Ordinance: check these minimums" | Same as the law | not drawn |
| Claim types | 6 (section 10) | **None yet** (no chart of accounts) | not drawn | not drawn |
| HRDF registered | Off; HRD Corp no. blank | Off | Off | Off |
| Payroll settings (Setup › HR) | Shown | Hidden | Hidden | Hidden |
| Net salaries payable (Setup › Statutory accounts) | **420-000 Accruals** (kind "Net salaries payable") | Not set up (no chart) | — | — |
| Other statutory kinds | EPF, SOCSO, EIS, PCB as stage 1. Lindung 24 Jam (SKBBK): Not set up. Zakat: Not set up. HRDF: Not registered. | none | — | — |
| e-Invoices | as stage 1 | "Submission method not decided yet" | — | — |

Everything else about AISB and AI (registration, TIN, employer numbers, bank accounts, chart) is stage 1 section 2.
Employer numbers stay on Setup › Companies; Payroll settings shows them read only.

**Public holidays, WP Kuala Lumpur 2026** (bundled list; "check with kabinet.gov.my or JTKSM" on the page):
- Locked by s.60D (5): Federal Territory Day Sun 1 Feb, Workers' Day Fri 1 May, Agong's birthday Mon 1 Jun, National
  Day Mon 31 Aug, Malaysia Day Wed 16 Sep.
- Two on one day: Federal Territory Day and Thaipusam both Sun 1 Feb → replacement days Mon 2 Feb and Tue 3 Feb.
- Replacement for a rest day: Deepavali Sun 8 Nov → **Mon 9 Nov**.
- Others ticked: New Year Thu 1 Jan, Chinese New Year Tue 17 and Wed 18 Feb, Christmas Fri 25 Dec, and the moon dates
  marked "may move" (Nuzul Al-Quran, Hari Raya Aidilfitri two days, Hari Raya Aidiladha, Awal Muharram, Maulidur
  Rasul, Wesak) with dates from the bundled list. One-off day: 20 Mar 2026. 2027: "not yet confirmed".
- November 2026 calendar shows Sun 8 Nov Deepavali and Mon 9 Nov replacement.

**Sabah 2026 (AI)**: the bundled Sabah list, with Pesta Kaamatan Sat 30 and Sun 31 May and Christmas Eve Thu 24 Dec
as the examples a Sabah list has and KL's doesn't.

---

## 3. Company switcher

Button: "AISB · Kept in SQL Account ▾". On the Overview, "All companies" is first; on HR › Staff, "All companies (read
only)"; elsewhere not offered.

| Code | Full name | Label | Next up | Offered |
|---|---|---|---|---|
| (All companies) | — | — | 14 | Overview only; Staff read only |
| AISB | AISB Sdn Bhd | Kept in SQL Account | **11** | Yes |
| AI | Agrinexus International | Kept here | **5** | Yes |
| AIL | Agrinexus Logistics | Kept in SQL Account | **2** | four-company variant |
| AIP | Agrinexus Plantations | Kept here | **2** | four-company variant |
| OLD | Former Trading Sdn Bhd | Kept here | — | **No: stopped 30 Jun 2025** |
| TEST | Training company | Kept here | — | No: stopped 21 Jul 2026 |

- All companies counts each "all companies" row once (Budget balance, Backup), so 11 + 5 − 2 = 14 in the two-company
  world, and still 14 with four companies.
- Switch toast: "SQL import isn't used for AI (Kept here). Showing AI's Overview." Second example: "Payroll settings
  aren't used for AI. Showing AI's Overview."
- No company yet: button "No company yet", menu item "Add your first company".
- Month menu, AISB: November 2026 (Set up), October 2026 (Current), September 2026 (Still open), August 2026 (Before
  first month). AI: November 2026 (Not set up), October 2026 (Current), September 2026 (Filed).

---

## 4. Users and rights

Six rights: HR, Payroll figures, Payments, Accounting, Approver, Admin. Before logins, the app runs on this PC and
"who" is declared.

| Person | Who | Rights | Staff record |
|---|---|---|---|
| **Aisha Rahman** | HR and Finance, at the keyboard | HR, Payroll figures, Payments, Accounting, Admin (**not** Approver) | AISB S001 |
| **Nurul Aina** | HR | **HR only** (no Payroll figures: payroll pages without pay amounts) | AISB S003 |
| **Marcus Teoh** | Outside accountant | **Payments, Accounting** (the no-HR, no-Admin case) | none |
| **Hassan Ismail** | Director | **Approver** (tied to Setup › HR › Approvers: AISB, AI, AIL) | none (not on payroll) |

- Top bar user menu for Aisha: "Access: HR, Payroll figures, Payments, Accounting, Admin", link "Users and access".
- Tan Mei Ling and Rajesh Kumar are approvers in Setup but have no user: they approve on paper.
- Last admin refused: removing Aisha Rahman's Admin right ("Someone must keep the Admin right").

---

## 5. Staff

Departments are free text. IC and passport numbers are masked. No race or religion is recorded for anyone (optional,
written consent; the record shows "Not recorded"). Staff records are personal data: nothing below goes on the
Overview except names on the On leave and Birthdays cards.

### AISB (9 in employment, 1 left)

| No. | Full name as on IC (preferred) | IC (masked) | Born | Gender | Position | Department | Type | Joined | Status |
|---|---|---|---|---|---|---|---|---|---|
| S001 | Aisha Rahman (Aisha) | ••••••-••-3418 | 27 Nov 1991 | F | HR and finance executive | Finance and HR | Permanent | 2 May 2019 | In employment |
| S002 | Ong Wei Ming (Wei Ming) | ••••••-••-5127 | 9 Mar 1993 | M | Sales executive | Sales | Permanent | 1 Jun 2021 | In employment |
| S003 | Nurul Aina binti Hashim (Aina) | ••••••-••-2046 | 15 Jun 1988 | F | HR and admin executive | Finance and HR | Permanent | 3 Oct 2016 | In employment |
| S004 | Mohd Hafiz bin Rosli (Hafiz) | ••••••-••-7391 | 22 Jul 1985 | M | Operations executive | Operations | Permanent | 4 Mar 2019 | In employment |
| S005 | Nor Khadijah binti Omar (Khadijah) | ••••••-••-6582 | 3 Feb 1990 | F | Customer service executive | Customer service | Permanent | 1 Feb 2020 | In employment (maternity leave) |
| S006 | Wong Kah Seng (Kah Seng) | ••••••-••-1035 | 12 Oct 1966 | M | IT support | IT | **Contract** (1 Jan 2024 to 31 Dec 2026) | 1 Jan 2024 | In employment; leaving 31 Dec (retiring) |
| S007 | Goh Jia Hui (Jia Hui) | ••••••-••-4720 | 30 Dec 1999 | F | Marketing executive | Marketing | Permanent | 1 Sep 2026 | **On probation** (ends 30 Nov) |
| S008 | Nur Izzati binti Kamal (Izzati) | ••••••-••-8264 | 21 Oct 2000 | F | Office assistant | Administration | Permanent | 15 Jan 2025 | In employment |
| S009 | Daniel Lee Chee Keong (Daniel) | ••••••-••-9153 | 14 May 2001 | M | Accounts assistant | Finance and HR | Permanent | **3 Nov 2026** | **On probation** (ends 2 Feb 2027); joiner |
| S010 | Kavitha Nair (Kavitha) | ••••••-••-3306 | 8 Aug 1996 | F | Marketing executive | Marketing | Permanent | 1 Jul 2023 | **Left** 31 Aug 2026, resigned; kept until 31 Dec 2033 |

All AISB staff: Malaysian citizens; work location Peninsular Malaysia; 5 working days a week, 8 hours a day; manual
work no; EPF rate group, SOCSO category and EIS cover worked out; Lindung 24 Jam: covered (none deducted yet, which is
what the Payroll check notes); HRDF counted: yes; paid by bank transfer.

| No. | Pay (basic from) | Fixed allowance | Bank (masked) | Reports to | Marital, PCB category, children | Payslip password | Work email |
|---|---|---|---|---|---|---|---|
| S001 | 8,600.00 from 1 Jan 2026 (was 8,200.00 from 1 Jan 2025) | Travelling 1,200.00 | Maybank ····2210 | Hassan Ismail | Single, 1 | IC number | aisha@aisb.example |
| S002 | 7,800.00 from 1 Jan 2026 | Travelling 3,000.00 | CIMB ····8841 | Tan Mei Ling | Single, 1 | **Own password, set 2 Nov 2026** (Reset) | weiming@aisb.example |
| S003 | 7,000.00 from 1 Jan 2026 | Travelling 800.00 | Maybank ····5532 | Hassan Ismail | Married, 3 (spouse working), 2 children under 18 | IC number | aina@aisb.example |
| S004 | 5,700.00 from 1 Jan 2026 | Travelling 2,600.00 | Public Bank ····0917 | Aisha Rahman | Married, 2 (spouse not working), 3 children under 18 | IC number | hafiz@aisb.example |
| S005 | 5,500.00 from 1 Jan 2026 | Travelling 600.00 | Maybank ····7764 | Aisha Rahman | Married, 3, 2 children under 18 | IC number | khadijah@aisb.example |
| S006 | 7,800.00 from 1 Jan 2024 | Travelling 600.00 | RHB ····3390 | Hassan Ismail | Married, 3, none | IC number | kahseng@aisb.example |
| S007 | 3,400.00 from 1 Sep 2026 | Travelling 600.00 | Maybank ····6128 | Tan Mei Ling | Single, 1 | IC number | jiahui@aisb.example |
| S008 | 2,800.00 from 15 Jan 2025 | Travelling 300.00 | Bank Islam ····4405 | Aisha Rahman | Single, 1 | IC number | izzati@aisb.example |
| S009 | 3,500.00 from 3 Nov 2026 | none | Maybank ····8073 | Aisha Rahman | Single, 1 | IC number | daniel@aisb.example |
| S010 | 3,200.00 (last) | none | Maybank ····1196 | — | Single, 1 | IC number | — |

- **Kah Seng turned 60 on 12 Oct 2026**: October is still paid at the under-60 rates; from **November 2026** EPF
  employee 0% and employer 4%, SOCSO second category (employer 1.25% only), no EIS. The record shows the worked-out
  categories with "check with KWSP and PERKESO" (payroll practice, not a published rule).
- Override sample (state only): Wei Ming chose a voluntary employee EPF of 13% from 1 Jan 2027, reason "Asked in
  writing, 12 Nov 2026" → "Overridden" pill.
- **Khadijah**: maternity eligibility confirmed by Aisha Rahman on 1 Oct 2026 (employed over 90 days in the 9 months
  before; 2 surviving children).
- **Kah Seng leaving**: last day 31 Dec 2026, reason "Retiring" → **CP22A** due by Tue 1 Dec 2026 (30 days before)
  and the tax-clearance hold on his final pay (step 2). His contract end 31 Dec is the same date.
- **Daniel**: joiner tasks on November's checklist: Register Daniel with KWSP and PERKESO (due Tue 10 Nov, done
  10 Nov), e-CP22 for Daniel (due Thu 3 Dec, 30 days after joining), Stamp the contract of Daniel (due Thu 3 Dec,
  basic over RM 3,000.00).
- **Kavitha**: advance balance at leaving RM 2,000.00; RM 1,600.00 taken from her August final pay (50% of RM 3,200.00
  wages) and **RM 400.00 to collect**, shown on her record. Moved company: none.
- Documents (S006 shown): IC copy, offer letter, contract (ends 31 Dec 2026, expiry flag), TP1 (2026). HR documents
  are stored under a code, not the person's name.
- Emergency contact (S003 shown): Amran Yahya, husband, 012-345 6789.
- Statutory numbers are masked to the last 4 (EPF ····5521 for S001, and so on).

### AI (5 in employment, Kept here, no payroll run)

AI pays its staff through the recurring row "Salaries — staff, 5 people, RM 21,300.00" (net, entered by hand). The row
lists its 5 staff, with dates read from the staff records.

| No. | Full name (preferred) | ID (masked) | Born | Gender | Position | Type | Joined | Notes |
|---|---|---|---|---|---|---|---|---|
| A001 | Mohd Faizal bin Yusof (Faizal) | ••••••-••-6611 | 4 Apr 1984 | M | Farm manager | Permanent | 1 Apr 2020 | Malaysian |
| A002 | Chong Pei Shan (Pei Shan) | ••••••-••-2958 | 19 Jan 1994 | F | Accounts assistant | Permanent | **1 Oct 2021** | 5 years in October |
| A003 | Priya Subramaniam (Priya) | ••••••-••-7744 | 2 Sep 1992 | F | Quality officer | Permanent | 16 Aug 2022 | Malaysian |
| A004 | Lee Jun Wei (Jun Wei) | ••••••-••-4019 | 25 Dec 1997 | M | Logistics coordinator | Permanent | 1 Mar 2023 | unpaid leave sample |
| A005 | Rina Santoso (Rina) | passport ••••1307, Indonesia | 6 Nov 1995 | F | Farm supervisor | Contract | 15 Jan 2025 | **Foreign worker**: work permit expires **Sun 10 Jan 2027**; Lindung 24 Jam always covered; EPF rate group not checked |

All AI staff work in Sabah. AI basics (Pay tab): Faizal 5,800.00, Pei Shan 4,200.00, Priya 4,600.00, Jun Wei 3,900.00,
Rina 2,400.00 (per-person net is not kept: AI doesn't run payroll).

**AI's October KWSP, RM 4,478.00** (Third Schedule on the basics; employee / employer): Faizal 638.00 / 696.00, Pei
Shan 462.00 / 546.00, Priya 506.00 / 598.00, Jun Wei 429.00 / 507.00, Rina (foreign worker, 2% + 2%) 48.00 / 48.00;
total 2,083.00 / 2,395.00.

**On 18 Nov (headcount):** AISB 9 in employment, 1 joiner this month (Daniel), 0 leavers; AI 5, 0, 0. All companies
14 in employment. HR › Staff filter Left shows Kavitha Nair only. 9 of AISB's 9 are Malaysian (the HRDF warning
needs 10: what-if only).

---

## 6. October payroll figures (AISB)

Ties to stage 1: gross (900-100) **59,147.90**, net **48,600.00** paid 24 Oct as "PAYROLL BULK 8 ITEMS" (ref BULK
241026, PV2610-014), EPF 5,346.00 / 5,894.00, SOCSO 205.00 / 717.60, EIS 81.90 / 81.90, PCB 4,915.00, zakat 0,
Lindung 24 Jam (SKBBK) 0. Payroll journal JV2610-007 credits 420-000 Accruals 48,600.00 (net salaries payable).

Wages for EPF, SOCSO and EIS are the basic salary (as `payrollcheck` reads them). Travelling allowance and overtime
are outside EPF and SOCSO wages.

| No. | Basic | Allowance | Overtime | Gross | EPF ee | SOCSO ee | EIS ee | PCB | **Net** | EPF er | SOCSO er | EIS er |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S001 Aisha | 8,600.00 | 1,200.00 | | 9,800.00 | 946.00 | 29.75 | 11.90 | 1,080.00 | **7,732.35** | 1,032.00 | 104.15 | 11.90 |
| S002 Wei Ming | 7,800.00 | 3,000.00 | | 10,800.00 | 858.00 | 29.75 | 11.90 | 1,180.00 | **8,720.35** | 936.00 | 104.15 | 11.90 |
| S003 Aina | 7,000.00 | 800.00 | | 7,800.00 | 770.00 | 29.75 | 11.90 | 700.00 | **6,288.35** | 840.00 | 104.15 | 11.90 |
| S004 Hafiz | 5,700.00 | 2,600.00 | | 8,300.00 | 627.00 | 28.25 | 11.30 | 560.00 | **7,073.45** | 684.00 | 98.90 | 11.30 |
| S005 Khadijah | 5,500.00 | 600.00 | | 6,100.00 | 605.00 | 27.25 | 10.90 | 340.00 | **5,116.85** | 660.00 | 95.40 | 10.90 |
| S006 Kah Seng | 7,800.00 | 600.00 | 847.90 | 9,247.90 | 858.00 | 29.75 | 11.90 | 1,000.00 | **7,348.25** | 936.00 | 104.15 | 11.90 |
| S007 Jia Hui | 3,400.00 | 600.00 | | 4,000.00 | 374.00 | 16.75 | 6.65 | 55.00 | **3,547.60** | 442.00 | 58.60 | 6.65 |
| S008 Izzati | 2,800.00 | 300.00 | | 3,100.00 | 308.00 | 13.75 | 5.45 | 0.00 | **2,772.80** | 364.00 | 48.10 | 5.45 |
| **Total** | **48,600.00** | **9,700.00** | **847.90** | **59,147.90** | **5,346.00** | **205.00** | **81.90** | **4,915.00** | **48,600.00** | **5,894.00** | **717.60** | **81.90** |

- EPF by the Third Schedule band rule (wages over RM 5,000: employer 12%; up to RM 5,000: 13%). SOCSO and EIS on the
  band midpoint with the RM 6,000 ceiling; Jia Hui's and Izzati's EIS (6.65, 5.45) and employer SOCSO (58.60, 48.10)
  are 5 sen or less from the exact share, which the check allows ("5 sen either way").
- Kah Seng's 847.90 is weekend overtime on the server move (contractual; he is above the RM 4,000 line).
- **Amounts to pay · as the Summary has them** (October, corrected check): KWSP 11,240.00 · SOCSO 922.60 · EIS
  163.80 · SKBBK 0.00 · PCB 4,915.00 · To pay (net) 48,600.00. PERKESO paid 17 Nov = 922.60 + 163.80 = 1,086.40.
- **Lindung 24 Jam the app works out** (parallel run difference; workbook has 0): 44.65 × 4 + 42.40 + 40.90 + 25.15 +
  20.65 = **307.70**.
- Short-match state (bank list): leaves out Jia Hui's **RM 3,547.60**, so the bank line of 48,600.00 against 45,052.40.
- The review's "RM 7,450.00 / 6,800.00 …" nets are replaced by the nets above.
- September: totals as stage 1 (59,121.90 gross, 48,600.00 net); not split per person. September per person is not
  drawn; its EPF 5,320.00 / 5,860.00 stays as stage 1 has it.
- **November (for the step 2 boards):** 9 people (Daniel from 3 Nov, basic 3,500.00: EPF 385.00 / 455.00, SOCSO 17.25
  / 60.40, EIS 6.90, SKBBK would be 25.90). Kah Seng at the 60-and-over rates: EPF 0.00 / 312.00, SOCSO 0.00 / 74.40,
  EIS none. Hafiz's first advance deduction RM 500.00 on 24 Nov.
- November: the workbook pays Daniel's full month (3,500.00), as his offer letter agreed; the part-month rule (the
  joining month prorated by calendar days) applies to runs made in the app.

**Opening year to date (HR › Payroll › Opening year to date, AISB 2026)**, as PayrollOpeningYtd imports it from
"Example Payroll - NOV 2026.xlsx". AISB switches over on Tue 1 Dec 2026; December 2026 is its first run paid from the
app. Gross, employee EPF and PCB; zakat 0.00 for everyone. January to September per person is the opening less
October (the table above) and November (November's pay; Kah Seng 8,400.00 gross, EPF 0.00, PCB 1,000.00).

| No. | Months | Gross Jan to Sep | EPF ee Jan to Sep | PCB Jan to Sep | Nov gross | **Gross Jan to Nov** | EPF ee Jan to Nov | PCB Jan to Nov | Dec gross | Dec EPF ee | Dec PCB | Gross, year to date |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S001 Aisha | Jan to Nov | 88,200.00 | 8,488.00 | 9,720.00 | 9,800.00 | **107,800.00** | 10,380.00 | 11,880.00 | 9,800.00 | 946.00 | 1,080.00 | 117,600.00 |
| S002 Wei Ming | Jan to Nov | 97,200.00 | 7,722.00 | 10,620.00 | 10,800.00 | **118,800.00** | 9,438.00 | 12,980.00 | 10,800.00 | 858.00 | 1,180.00 | 129,600.00 |
| S003 Aina | Jan to Nov | 70,200.00 | 6,930.00 | 6,300.00 | 7,800.00 | **85,800.00** | 8,470.00 | 7,700.00 | 7,800.00 | 770.00 | 700.00 | 93,600.00 |
| S004 Hafiz | Jan to Nov | 74,700.00 | 5,643.00 | 5,040.00 | 8,300.00 | **91,300.00** | 6,897.00 | 6,160.00 | 8,300.00 | 627.00 | 560.00 | 99,600.00 |
| S005 Khadijah | Jan to Nov | 54,900.00 | 5,445.00 | 3,060.00 | 6,100.00 | **67,100.00** | 6,655.00 | 3,740.00 | 6,100.00 | 605.00 | 340.00 | 73,200.00 |
| S006 Kah Seng | Jan to Nov | 79,684.60 | 7,722.00 | 9,000.00 | 8,400.00 | **97,332.50** | 8,580.00 | 11,000.00 | 9,900.00 (final pay) | 0.00 | 890.00 | 107,232.50 |
| S007 Jia Hui | Sep to Nov | 4,000.00 | 374.00 | 55.00 | 4,000.00 | **12,000.00** | 1,122.00 | 165.00 | 4,000.00 | 374.00 | 55.00 | 16,000.00 |
| S008 Izzati | Jan to Nov | 27,900.00 | 2,772.00 | 0.00 | 3,100.00 | **34,100.00** | 3,388.00 | 0.00 | 3,100.00 | 308.00 | 0.00 | 37,200.00 |
| S009 Daniel | Nov | — | — | — | 3,500.00 | **3,500.00** | 385.00 | 0.00 | 3,500.00 | 385.00 | 0.00 | 7,000.00 |
| S010 Kavitha | Jan to Aug | 25,600.00 | 2,816.00 | 120.00 | — | **25,600.00** | 2,816.00 | 120.00 | — | — | — | 25,600.00 |
| **Total** | | **522,384.60** | **47,912.00** | **43,915.00** | **61,800.00** | **643,332.50** | **58,131.00** | **53,745.00** | **63,300.00** | **4,873.00** | **4,805.00** | **706,632.50** |

- January to September ties to stage 1: gross 522,384.60 (SQL's 900-100 at 30 Sep), employee EPF 47,912.00. The
  **26.00** by which 47,912.00 falls short of the monthly rates is placed on **Aisha's employee EPF** (8,488.00 =
  9 × 946.00 − 26.00).
- Kavitha (left 31 Aug): January to August kept for her 2026 EA form; her September to November rows are zero.
- Kah Seng's January to September gross is 4,084.60 above nine months of 8,400.00 (79,684.60): overtime, outside EPF
  wages, not split by month.
- December is the example run from later: November's pay again, with Kah Seng's final pay as PayrollLeaver draws it
  (gross 9,900.00, EPF 0.00, PCB 890.00).
- Step 2 only: the October run approved on **AF-2610-009** (Hassan Ismail, 22 Oct), "Waiting for SQL record" then
  "Recorded" when Fetch finds **JV2610-007**.

---

## 7. Workbook checks (HR › Payroll › Workbook check)

| Checked | Company, month | File | Headline | Filed on |
|---|---|---|---|---|
| Wed 21 Oct 2026 10:12 | AISB, October 2026 | Example Payroll - OCT 2026.xlsx | **3 things to fix before paying, 2 to check; 9 notes** | October's "Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB"; replaced by the 22 Oct file |
| Thu 22 Oct 2026 09:40 | AISB, October 2026 | Example Payroll - OCT 2026 (corrected).xlsx | **Nothing to fix or check; 9 notes** | same item, current |
| Wed 18 Nov 2026 09:20 | AISB, November 2026 | Example Payroll - NOV 2026.xlsx | **3 things to fix before paying, 2 to check; 10 notes** | November's "Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB" |

Findings (use the code's own sentences for each kind):
- **21 Oct (October, first file).** Fix: `pay_row_sum` (Jia Hui's net pay cell is not pay less deductions),
  `summary_sum` (the Summary's KWSP column doesn't add up to its Total row), `unrounded` (the Summary's PCB total has
  more than 2 decimals). Check: `typed` (Hafiz's allowance typed on the Summary, not linked to his payslip),
  `summary_name` (the Summary says "Izzati", the payslip "Nur Izzati binti Kamal"). Notes: `skbbk_zero` × 8,
  `pcb_not_checked`. Kah Seng's payslip carries the line "Turns 60 this month: the under-60 rates still apply; the
  60-and-over rates start with November 2026's pay."
- **22 Oct (corrected).** Notes only: `skbbk_zero` × 8, `pcb_not_checked`.
- **18 Nov (November).** Fix: `eis` employee and `eis` employer on Kah Seng's payslip ("EIS isn't paid for a worker
  aged 60 or over."), `summary_sum` (Daniel's row is not in the Summary's Net total). Check: `sheet_month` on
  Daniel's payslip ("No month was found on this payslip."), `typed` (Daniel's KWSP typed on the Summary). Notes:
  `skbbk_zero` × 9, `pcb_not_checked`. Kah Seng's EPF (0.00 / 312.00) and SOCSO (0.00 / 74.40) are already at the
  60-and-over rates, so they pass.
- Audit trail line: "Payroll check for AISB November 2026: 3 things to fix before paying, 2 to check; 10 notes
  ('Example Payroll - NOV 2026.xlsx'), filed on Calculate payroll, KWSP, SOCSO, EIS, SKBBK and PCB". The Excel report
  opened at 09:25 is logged as a read ("payroll check export").
- AI, AIL, AIP: "No check yet" on the Workbook check tab.
- Refused-file and other states use the review's list (PayrollCheck, board 14) with these file names.

---

## 8. Leave

Entitlements are the **legal minimums** (Employment Act, Peninsular Malaysia): annual 8 / 12 / 16 days (under 2 years
/ 2 to 5 / 5 or more), sick 14 / 18 / 22, hospitalisation up to 60 (sick days inside it), maternity 98, paternity 7,
public holidays 11 or more. Anything above a person's legal days is a **warning, never refused**; so is a Setup value
above the law. No carry forward beyond what the law gives, no company extras, until the owner sets them. Unpaid,
compassionate, marriage, study and replacement leave: "Company policy: not set".

**Annual leave 2026 (AISB) at 18 Nov**

| Person | Service | Entitlement | Taken | Booked | Balance |
|---|---|---|---|---|---|
| Aisha | 7 years | 16 | 11 | 0 | 5 |
| Wei Ming | 5 years (2 to 5 at 1 Jan 2026) | 12 | 8.5 | 0 | 3.5 |
| Aina | 10 years | 16 | 14 (incl. 16 to 20 Nov) | 0 | 2 |
| Hafiz | 7 years | 16 | 10 | 1 (Fri 20 Nov) | 5 |
| Khadijah | 6 years | 16 | 6 | 0 | 10 (plus maternity) |
| Kah Seng | 2 years 10 months | 12 (leaving 31 Dec: 12 of 12 months) | 7 | 0 | 5 |
| Jia Hui | joined 1 Sep | **3** (8 × 4/12 = 2.67, rounds to 3) | 0 | **4** (Mon 7 to Thu 10 Dec) | **−1: warning** |
| Izzati | 1 year 10 months | 8 | 5 | 0 | 3 |
| Daniel | joined 3 Nov | 1 (8 × 2/12 = 1.33) | 0 | 0 | 1 |

**Leave entered (Taken and booked list)**
- Aina, annual leave, Mon 16 to Fri 20 Nov, 5 days. She is back **Mon 23 Nov** ("Aina is back on Mon 23 Nov", no
  type).
- Khadijah, maternity, **Mon 5 Oct 2026 to Sun 10 Jan 2027**, 98 days in a row; back Mon 11 Jan 2027.
- Hafiz, annual leave, **Fri 20 Nov**, 1 day, Booked. Clash state: the same day entered twice.
- Wei Ming, annual leave, **Wed 14 Oct, half day (morning)**.
- Jia Hui, annual leave, Mon 7 to Thu 10 Dec, 4 days, Booked: over-balance warning ("3 days this year by law").
- Kah Seng, sick leave, Mon 2 Nov, 1 day, certificate attached.
- Izzati, annual leave, Fri 13 Nov, **Cancelled** ("Work came up"), 1 day back to her balance.
- AI: Jun Wei, unpaid leave, Mon 9 and Tue 10 Nov, 2 days: note "Deduct it from the salary payment by hand".
- **On leave today (Wed 18 Nov):** Aina, Khadijah. **This week:** 3 (Hafiz on Fri 20 Nov). The Overview shows no type.
- Opening balances and year end (HrLeaveYear): imported from "Leave balances 2026.xlsx", 9 rows; carry-forward run
  for 2026 on the legal rule only.

---

## 9. Calendar dates

**AISB, from 18 Nov (Calendar and reminders list)**

| Date | What | Reminder |
|---|---|---|
| Fri 20 Nov | Hafiz on leave | — |
| Mon 23 Nov | Aina back | — |
| Fri 27 Nov | Aisha's birthday | Birthday (no year) |
| Mon 30 Nov | Jia Hui's probation ends | 30 and 7 days before; Next up |
| Tue 1 Dec | CP22A for Kah Seng (retiring 31 Dec) | Leaver task (December's checklist); Next up; starts the tax-clearance hold |
| Thu 3 Dec | e-CP22 for Daniel (joined 3 Nov) | Joiner task (November's checklist); Next up |
| Thu 3 Dec | Stamp the contract of Daniel (basic over RM 3,000.00) | Joiner task (November's checklist); not a Next up row |
| Mon 7 to Thu 10 Dec | Jia Hui on leave | — |
| Fri 25 Dec | Christmas (public holiday) | — |
| Wed 30 Dec | Jia Hui's birthday | Birthday |
| Thu 31 Dec | Kah Seng's contract ends and last day | 60 and 30 days before |
| Mon 11 Jan 2027 | Khadijah back from maternity leave | — |
| Tue 2 Feb 2027 | Daniel's probation ends | (outside the 60 days) |

Already done, so not in the list above: "Register Daniel with KWSP and PERKESO" (due Tue 10 Nov, done 10 Nov), on
November's checklist (section 0, D13).

**October 2026 (Birthdays and anniversaries, follows the month):** Aina **10 years** (Sat 3 Oct), Kah Seng birthday
(Mon 12 Oct), Izzati birthday (Wed 21 Oct). AI: Pei Shan **5 years** (Thu 1 Oct).
**November 2026:** AISB Aisha birthday (Fri 27 Nov); AI Rina birthday (Fri 6 Nov).

**Dates coming up (next 60 days from 18 Nov):** AISB: Jia Hui's probation 30 Nov, Kah Seng's contract 31 Dec. AI:
Rina's work permit **10 Jan 2027**.

A one-off reminder sample: "Renew the group insurance staff list", Tue 15 Dec, added by Aisha Rahman.

---

## 10. Claims

**AISB claim types** (Setup › HR › Claim types; per company)

| Type | Expense account | Monthly limit | Receipt |
|---|---|---|---|
| Mileage (RM 0.60 a km) | 900-860 Travelling (new) | — | Trip log |
| Parking and toll | 900-860 Travelling (new) | — | Required |
| Client meals | 900-870 Entertainment (new) | **RM 150.00** | Required |
| Phone | 900-600 Telephone and internet | RM 150.00 | Required |
| Stationery and materials | 900-800 Printing, postage and stationery | — | Required |
| Overseas travel | 900-860 Travelling (new) | — | Required; self-billed e-Invoice |

Staff welfare 900-850 is kept for a later type ("Team meals"). AI: none yet (no chart of accounts).

| Claim | Person | Lines | Total | Status |
|---|---|---|---|---|
| **CL-2610-004** "Oct 2026 Claims - Wei Ming" | Wei Ming | Parking and toll 12.00 (Tue 6 Oct); Client meals 186.50 (Wed 14 Oct, **over the RM 150.00 limit by 36.50**, flagged); Mileage 288.00 (Thu 22 Oct, 480 km) | **486.50** | Approved (AF-2611-003), in To pay, due Sat 14 Nov: **overdue** |
| CL-2610-005 | Aina | Mileage 144.00 (240 km); Parking and toll 64.00; Stationery and materials 200.00 | **408.00** | Approved (AF-2611-003), in To pay, due Fri 20 Nov |
| CL-2610-006 | Wei Ming | Parking and toll 120.00 | 120.00 | **Withdrawn**, "Entered twice" |
| CL-2610-007 | Jia Hui | Stationery and materials 320.00 (event materials) | **320.00** | Approved (AF-2611-003), in To pay, due Fri 20 Nov |
| CL-2611-001 | Kah Seng | Phone 145.00 (October bill) | **145.00** | Waiting for approval (AF-2611-005) |

- AF-2611-003's three claims: 486.50 + 408.00 + 320.00 = **1,214.50** ("Print approval form for 3 claims · RM
  1,214.50").
- Recorded (Kept in SQL Account): matched to SQL's voucher as today; none is paid yet, so none is recorded.
- State-only rows: "Paid, approval refused" (CL-2609-002, Wei Ming, RM 95.00, refused 2 Nov "Personal travel");
  overseas claim (Wei Ming, Singapore client visit, hotel SGD 180.00 = RM 612.00, needs a self-billed e-Invoice);
  director's own claim and self-approved (Hassan Ismail at AI, RM 640.00 mileage to the farm: AI has one approver,
  and its claim types must exist first); Kept here recorded (JV and PV) uses AI once it has a chart.

---

## 11. Advances

| Advance | Person | Amount, schedule | Form | Status on 18 Nov |
|---|---|---|---|---|
| **SA-2611-001** | Hafiz | RM 1,500.00 at RM 500.00 a month, Nov 2026 to Jan 2027 | AF-2611-001, Rajesh Kumar, 3 Nov | **Approved, in To pay, due Fri 20 Nov**; repaid 0.00, **left 1,500.00**; first deduction Tue 24 Nov |
| **SA-2611-002** | Daniel | RM 4,000.00 at RM 1,000.00 a month, Dec 2026 to Mar 2027 | AF-2611-005 | Waiting for approval; warning "More than one month's pay (RM 3,500.00)" |
| SA-2606-001 | Kavitha (left) | RM 2,400.00 at RM 400.00 a month from Jul 2026 | before approvals | Closed at leaving: 400.00 repaid in July, 1,600.00 from her August final pay, **RM 400.00 to collect** |

- Recurring's seed note "Staff advance approved 3 November" stays; its "left 1,000.00" becomes **1,500.00**.
- Over-50% warning (state only): Daniel's schedule changed to RM 2,000.00 a month (57% of RM 3,500.00).
- Kept here check against "Advances to staff": AI, state only, once AI has a chart.

---

## 12. Approval forms

One code series for the whole app, the company printed on each form. Approvers printed are the company's approvers on
the print date. "Any one signature approves this form."

| Code | Company | Requests | Total | Keyed check | Printed | Signed (date on form) | Uploaded | Result |
|---|---|---|---|---|---|---|---|---|
| AF-2610-001 | AISB | Recurring set-ups: Salaries — staff RM 48,600.00 a month (totals only); Director fee RM 12,000.00 a month (payee Hassan Ismail: his line struck, "Can't sign: payee") | 60,600.00 a month | H3T-9QWD | Thu 1 Oct | Rajesh Kumar, 1 Oct | Fri 2 Oct, paper scan, approver chosen by Aisha Rahman | Approved |
| AF-2610-002 | AI | Recurring set-up: Salaries — staff RM 21,300.00 a month | 21,300.00 | B7M-2KRN | Thu 1 Oct | Hassan Ismail, 1 Oct | Fri 2 Oct, digitally signed PDF | Approved |
| AF-2610-003 | AI | Farm supplies, Agro inputs INV-7781 | 6,750.00 | P5X-8LCA | Thu 15 Oct | Hassan Ismail, 16 Oct | Fri 16 Oct, digitally signed PDF | Approved (paid 19 Oct) |
| AF-2610-004 | AISB | Stationery Mart, quotation SQ-2210 | 1,000.00 | Z2R-6VNE | Mon 26 Oct | Tan Mei Ling, 27 Oct | Tue 27 Oct, paper scan | Approved; **paid 1,120.00** |
| AF-2610-009 | AISB | October salary run (**step 2 boards only**): page 1 totals, page 2 per person | 48,600.00 net | Q7L-3DXA | Wed 21 Oct | Hassan Ismail, 22 Oct | Thu 22 Oct | Approved |
| AF-2611-001 | AISB | SA-2611-001 Hafiz | 1,500.00 | C8W-3JTP | Mon 2 Nov | Rajesh Kumar, 3 Nov | Tue 3 Nov, digitally signed PDF (matched automatically) | Approved |
| AF-2611-002 | AISB | Recurring set-up: Office rental RM 6,500.00 a month (from October); Cloud hosting, annual plan USD 1,200.00 | 6,500.00 + USD 1,200.00 | M6D-4YQB | Wed 4 Nov | Hassan Ismail, **5 Nov** | **Fri 6 Nov**, paper scan, approver chosen by Aisha Rahman | Approved; office rental **approved after payment** |
| **AF-2611-003** | AISB | CL-2610-004, CL-2610-005, CL-2610-007 | **1,214.50** | **7KQ-M4XP** | Wed 11 Nov | **Tan Mei Ling, 12 Nov** | **Fri 13 Nov**, paper scan: "Approver chosen by Aisha Rahman from a paper scan" | Approved |
| **AF-2611-004** | AISB | Consultant fee, Payroll Advisory PLT, PA-1010 | **3,200.00** | T9F-5HRG | **Mon 16 Nov** | — | — | **Waiting**; also the phone-photo sample |
| **AF-2611-005** | AISB | CL-2611-001 Kah Seng; SA-2611-002 Daniel | 4,145.00 | W4N-7ZKC | Tue 17 Nov | — | — | **Waiting** |
| AF-2611-006 | AI | Consultant — farm audit (quarterly) | 2,500.00 | J2V-8PMS | Mon 16 Nov | Hassan Ismail, 17 Nov | Tue 17 Nov, digitally signed PDF | Approved |
| **MR-2610-AISB** | AISB | Month review, October 2026 | — | N5B-2RWH | Tue 17 Nov | — | — | **Waiting for upload** (checklist "Month reviewed" not ticked) |

- **Waiting for approval, AISB: 3** = CL-2611-001 and SA-2611-002 (HR) and the consultant fee (supplier bill). AI: 0.
- Upload sample "some match and some changed": on AF-2611-003, Aina's claim printed at RM 408.00 changed to RM 428.00
  after printing → that request is not approved by the form (state only; the review's "RM 486.50 printed, now
  RM 506.50" uses Wei Ming's claim the same way).
- Approver-is-payee: Director fee (Hassan Ismail). Same-name warning (state only): supplier "Rajesh Kumar & Co"
  against approver Rajesh Kumar. Signer not in the approvers list (state only): "Farid Osman" (stopped 30 Jun 2026).
- MR-2610-AISB covers: the register's October total (as the register shows it), the 2 paid without approval, the
  approvals per approver for October's payments (Rajesh Kumar 2: salaries, director fee; Tan Mei Ling 4: Stationery
  Mart on AF-2610-004, and Wei Ming's, Aina's and Jia Hui's claims on AF-2611-003; Hassan Ismail 2: office rental,
  cloud hosting; 8 in all, as the register's October payments show them), and the Maybank current reconciliation **not
  signed off** (5 lines to explain). AI: MR-2610-AI not printed yet.

---

## 13. Paid without approval on file, and the Approval marker

**AISB, October 2026**
- Still open (**2**):
  - Contractor — field works, RM 24,000.00, paid Tue 6 Oct, entered by Aisha Rahman: **Paid without approval on file**.
  - Stationery Mart, RM 1,120.00, paid Fri 30 Oct (PV2610-022): **Paid more than approved (RM 120.00)**, approved
    RM 1,000.00 on AF-2610-004.
- Approved after payment (**1**): Office rental RM 6,500.00, paid Fri 30 Oct, form dated 5 Nov, uploaded 6 Nov
  (AF-2611-002).
- Checklist "Approvals on file for every payment": not ticked ("2 without approval").

**AI:** none, so the Overview card is hidden for AI.

**Approval marker on AISB's October payments**

| Payment | Marker |
|---|---|
| Contractor — field works 24,000.00 | Paid without approval on file |
| Salaries — staff 48,600.00 | Approved by Rajesh Kumar, 1 Oct 2026 |
| Director fee 12,000.00 | Approved by Rajesh Kumar, 1 Oct 2026 |
| Office rental 6,500.00 | Approved by Hassan Ismail, 5 Nov 2026 (after payment) |
| Stationery Mart 1,120.00 | Paid more than approved (RM 120.00) |
| Consultant fee 3,200.00 | Waiting |
| Telephone & internet 398.60 (paid 28 Oct), Electricity bill 1,163.20 (paid 4 Nov, PV2611-003) | Not needed |
| Rental received 2,800.00 (money in) | Not needed |
| Oct 2026 Claims - Wei Ming 486.50 | Approved by Tan Mei Ling, 12 Nov 2026 |
| KWSP, PERKESO, PCB | Not needed |
| Cloud hosting USD 1,200.00 | Approved by Hassan Ismail, 5 Nov 2026 |
| (state only) | Paid, approval refused: CL-2609-002 |

---

## 14. Next up rows (default Overview, All companies, Aisha, Wed 18 Nov)

Most urgent first. "Place" is the menu item the row belongs to (its badge). Rows carry no pay figure or other personal
data; joiner and leaver reminders show the preferred name as the SetupChecklist template does (rule 16 rows stay
nameless).

| # | key | Co | Rule | Title | Meta | Due | Place | Verb |
|---|---|---|---|---|---|---|---|---|
| 1 | consultant | AISB | as today | Consultant fee not on the October statement | AISB · Payments register · RM 3,200.00 | **Overdue 31 Oct** | Payments register | Open payment |
| 3 | kwspaisb | AISB | as today | Pay KWSP for October | AISB · To pay · RM 11,240.00 · legal deadline 15 Nov | **Overdue 15 Nov** | To pay (in its count) | Open payment |
| 4 | kwsp | AI | as today | Pay KWSP for October | AI · To pay · RM 4,478.00 · legal deadline 15 Nov | **Overdue 15 Nov** | To pay (in its count) | Open payment |
| 5 | sqlbooks | AISB | 10 | Sep AISB: SQL books agree with SQL Account | AISB · Monthly checklist · September | **Overdue 15 Oct** | Monthly checklist | Show item |
| 6 | payroll | AISB | 15 | **Nov AISB: the payroll check found 3 things to fix before paying** | AISB · HR › Payroll | — (no due date) | Payroll | Go |
| 7 | explain | AISB | as today | Explain 5 bank lines on Maybank current | AISB · Accounting › Bank and reconciliation | Today 18 Nov | Bank and reconciliation | Explain 5 lines |
| 8 | balance | all | as today | Enter the bank balance for the November budget | Payments › Budget · all companies | Due 20 Nov | Budget | Enter balance |
| 9 | sql | AISB | 7 | Fetch SQL's Oct and Nov Payment Voucher listings on the SQL import page: 4 payments not recorded; 1 SQL entry not linked yet; 1 voucher changed in SQL (move the link on the SQL page) | AISB · Accounting › SQL import | Due 21 Nov | SQL import | Fetch from SQL exports |
| 10 | pack | AI | as today | Build and file the October audit pack | AI · Admin › Audit pack | Due 30 Nov | Audit pack | Open audit pack |
| 11 | probation | AISB | 16 (new) | A probation ends on 30 Nov: confirm or extend it | AISB · HR › Staff › Calendar and reminders | Due 30 Nov | Staff | Open reminder |
| 12 | cp22a | AISB | as ecp22 (leaver reminder) | CP22A for Kah Seng | AISB · Monthly checklist · Leaver reminder | Due 1 Dec | Monthly checklist | Open checklist |
| 13 | ecp22 | AISB | as today | e-CP22 for Daniel | AISB · Monthly checklist · Joiner reminder | Due 3 Dec | Monthly checklist | Open checklist |
| 14 | permit | AI | 16 (new) | A work permit expires on 10 Jan 2027 | AI · HR › Staff › Calendar and reminders | Due 10 Jan | Staff | Open reminder |
| 15 | backup | all | 13 | Last backup: 11 Nov, 7 days ago | Admin › Backup | — | Backup | Open backup |

- Rule numbers are the code's (`nextup.py`) where this file is sure of them; "as today" rows keep their code rule. 16 is new_work (HR date reminders from the staff record).
- With "trail = attention": row 0 "Review the changes made outside the app" (all, Audit trail, Needs attention).
- **No row 2 (owner, 19 Nov 2026; section 0, item 19).** One Next up row per unpaid statutory payment: AISB's
  October KWSP is entered and unpaid, so row 3 "Pay KWSP for October" (Overdue 15 Nov) is its only row, and rule 14's
  "AISB: EPF (KWSP) for October 2026 wasn't paid by 15 Nov 2026. Check it on Statutory payables." (key statepf) is not
  shown. Rule 14 shows only when there is no unpaid payment to point at (paid short, or never entered). The other row
  numbers stay as they were, because the boards use them as ids.
- **Per company:** AISB rows 1, 3, 5, 6, 7, 8, 9, 11, 12, 13, 15 = **11** (3 overdue). AI rows 4, 8, 10, 14, 15 =
  **5** (1 overdue). All companies **14** (4 overdue). AIL and AIP (variant): rows 8 and 15 only = **2** each.
- **Marcus Teoh (no HR, no Admin) on AISB:** rows 1, 3, 5, 7, 8, 9, 12, 13 = **8** (rows 6, 11 HR; 15 Admin).
- **Nurul Aina (HR only) on AISB:** rows 6 and 11 = **2**.
- The October rule 15 row does not exist (the 22 Oct check found nothing to fix).

---

## 15. Badges per menu item, and row counts

Blue = neutral; **red** = at least one overdue (with the alert glyph); count badges marked (count).

| Menu item | AISB (Aisha) | AI (Aisha) | AIL (Aisha) | AIP (Aisha) | AISB (Marcus Teoh) | AISB (Nurul Aina) |
|---|---|---|---|---|---|---|
| Overview | **11 red** | **5 red** | 2 | 2 | **8 red** | 2 |
| Staff | 1 | 1 | — | — | (hidden) | 1 |
| Leave | — | — | — | — | (hidden) | — |
| Claims and advances | — | — | — | — | (hidden) | — |
| Payroll | 1 | — | — | — | (hidden) | 1 |
| Approvals (count) | 3 | — | 1 | — | 3 | (hidden) |
| To pay (count) | **6 red** | **2 red** | 2 | 2 | **6 red** | (hidden) |
| Payments register | **1 red** | — | — | — | **1 red** | (hidden) |
| Monthly checklist | **3 red** | — | — | — | **3 red** | (hidden) |
| Budget | 1 | 1 | 1 | 1 | 1 | (hidden) |
| Recurring | — | — | — | — | — | (hidden) |
| Bank and reconciliation | 1 | — | — | — | 1 | (hidden) |
| SQL import | 1 | (hidden) | — | (hidden) | 1 | (hidden) |
| e-Invoices | — | — | — | — | — | (hidden) |
| Books | — | — | — | — | — | (hidden) |
| Customers and suppliers | — | — | — | — | — | (hidden) |
| Statutory payables | — | — | — | — | — | (hidden) |
| Sales, Purchases, Journals, Period close | (hidden) | — | (hidden) | — | (hidden) | (hidden) |
| Setup | — | — | — | — | (hidden) | (hidden) |
| Audit pack | — | 1 | — | — | (hidden) | (hidden) |
| Audit trail | — | — | — | — | (hidden) | (hidden) |
| Backup | 1 | 1 | 1 | 1 | (hidden) | (hidden) |
| Users and access | — | — | — | — | (hidden) | (hidden) |

- **To pay items.** AISB 6: KWSP October 11,240.00 (overdue 15 Nov), CL-2610-004 486.50 (overdue 14 Nov),
  CL-2610-005 408.00, CL-2610-007 320.00, SA-2611-001 1,500.00 (all due Fri 20 Nov), Cloud hosting USD 1,200.00 (due
  Wed 25 Nov). AI 2: KWSP October 4,478.00 (overdue), Consultant — farm audit 2,500.00 (due Mon 30 Nov). AIL 2 and
  AIP 2: not overdue (not drawn in detail). Groups on the To pay page (AISB): Overdue 2, This week 3, Later 1.
- **Approvals.** AISB 3 (2 HR requests, 1 supplier bill). AI 0. AIL 1 (not drawn). AIP 0.
- Screen-reader labels as today: "11 to do, 3 overdue"; counts read "3 waiting for approval", "6 to pay, 2 overdue".
- Overview's own badge counts that company's Next up rows the user can see; with All companies on the Overview the
  top of the list reads 14.
- **Statutory payables has no badge** in these samples: its only Next up row was rule 14, which does not show while
  "Pay KWSP for October" is entered and unpaid (section 14). That row counts inside To pay 6 (AISB) and 2 (AI). Were
  October's KWSP paid short or never entered, rule 14 would come back and Statutory payables would read 1 red.

**Rows per menu (items, not group headings)**

| Case | Groups and items | Rows |
|---|---|---|
| AISB · Kept in SQL Account, runs payroll (Aisha) | Overview 1 · HR 4 (Staff, Leave, Claims and advances, Payroll) · Payments 6 (Approvals, To pay, Payments register, Monthly checklist, Budget, Recurring) · Accounting 6 (Bank and reconciliation, SQL import, e-Invoices, Books, Customers and suppliers, Statutory payables) · Admin 5 (Setup, Audit pack, Audit trail, Backup, Users and access) | **22** |
| AIL · Kept in SQL Account, no payroll run (Aisha) | the same; Payroll holds the Workbook check only | **22** |
| AI · Kept here, no payroll run (Aisha) | Overview 1 · HR 4 · Payments 6 · Accounting 5 (no SQL import) + "Kept here" sub-group 4 (Sales, Purchases, Journals, Period close) · Admin 5 | **25** |
| AIP · Kept here (Aisha) | as AI | **25** |
| AISB for Marcus Teoh (Payments, Accounting) | Overview 1 · Payments 6 · Accounting 6; no HR, no Admin | **13** |
| AISB for Nurul Aina (HR only) | Overview 1 · HR 4 | **5** |
| Approver only (Hassan Ismail, later with logins) | Approvals | **1** |
| Menu fully open (comparison) | AISB's 22 with Calendar and reminders and Salary advances unfolded as their own items | **24** |

---

## 16. Overview card values (October 2026, Wed 18 Nov)

### Needs attention (follows the month)

| Counter | AISB | AI | All companies |
|---|---|---|---|
| Past due | **3** (KWSP, Consultant fee, Oct 2026 Claims - Wei Ming) | **1** (KWSP) | AISB 3 · AI 1 |
| Part paid | 0 (grey) | **1** (Produce export, USD 5,000.00 of 8,400.00 received) | AISB 0 · AI 1 |
| Documents missing | **2** | 0 (grey) | AISB 2 · AI 0 |
| Lines to explain | **5** (Maybank current) | 0 (grey) | AISB 5 · AI 0 |
| Not in SQL | **4** | not shown (Kept here) | AISB 4 |

### Payments cards

| Card | AISB | AI | All companies |
|---|---|---|---|
| Checklist | **18 of 27** | **15 of 22** | AISB 18 of 27 · AI 15 of 22 |
| Due and overdue (from today) | **2 overdue, RM 11,726.50**; **4 due in the next 7 days, RM 2,228.00 and USD 1,200.00** | **1 overdue, RM 4,478.00**; nothing due in the next 7 days | lines per company |
| Budget vs paid and Funds to request (as at the balance date, from Budget.dc.html) | Budget as at **Mon 19 Oct** (balance **RM 56,790.35**, Maybank current, statement) · Budgeted RM 115,190.00 (and USD 1,200.00) · Paid **RM 24,000.00** (lines paid by 19 Oct: the contractor, 6 Oct) · Still to pay **RM 93,923.10** · Funds to request **RM 37,132.75** | Lines **RM 37,060.40**; **no RM balance entered** (AI's only account is Maybank FCA, USD), so the budget is as at today: Paid RM 28,662.40 · Still to pay RM 8,398.00 · Funds to request: "Enter the bank balance to see funds to request" | AISB and AI lines; total funds to request **RM 37,132.75** (AISB's alone) |
| Paid without approval on file | **2** (RM 24,000.00; RM 1,120.00 paid, RM 120.00 above approval) | hidden (0) | AISB 2 |

- **Documents missing 2** (Needs attention) = the 2 checklist items with missing documents (section 0, D13).
- **AISB's budget** (Budget.dc.html): Rental received 2,800.00 is dated 2 Oct; the balance date is the day the October
  fund requisition was signed, **Mon 19 Oct 2026**, RM 56,790.35 being Maybank current's running balance after the
  15 Oct line on the October statement; the 45,000.00 fund receipt arrives 20 Oct. Lines still to pay 91,190.00 plus
  payments with no line 2,733.10 = 93,923.10 (section 18). Insurance renewal 2,498.60 is a line with no payment.
- **AI's budget lines** are AI's own October payments: Salaries — staff 21,300.00 (paid 24 Oct), Farm supplies
  6,750.00 (paid 19 Oct), KWSP 4,478.00 (unpaid, overdue), PERKESO 612.40 (paid 14 Nov), Electricity bill 1,420.00
  (waiting for the November statement), Consultant — farm audit 2,500.00 (due 30 Nov).
- **Variant figures** (four-company and September views of the Overview; no Budget view is drawn for them):
  - Funds to request, October: AISB 37,132.75 · AI not entered · AIL 6,420.00 · AIP 9,880.00; all companies RM
    53,432.75.
  - Funds to request, September: AISB 31,200.00 · AI not entered · AIL 5,980.00 · AIP 9,100.00; all companies RM
    46,280.00.
  - Checklist, October: AIL 10 of 14, AIP 12 of 18. September: AIL 12 of 12, AIP 15 of 15.

### Accounting cards

| Card | AISB | AI | All companies |
|---|---|---|---|
| Bank balance | Maybank current **RM 34,314.15** (statement, 31 Oct) · Maybank savings **RM 58,011.40** (31 Oct) | Maybank FCA **USD 17,480.00** (30 Oct) | one line per account, company chip |
| Money in and out (bank lines, October) | In **RM 55,984.20** (current 47,962.80, savings 8,021.40) · Out **RM 106,077.00** (current 106,067.00, savings 10.00) | In **USD 5,000.00** · Out USD 0.00 | per company |
| Profit or loss | October **loss RM 103,852.70** · year to date **loss RM 885,816.30** · "From SQL's books, journal to 17 Nov" | **No books yet** | AISB line · AI "No books yet" |
| Customers overdue (older than 30 days, as at 17 Nov) | **1 balance, RM 8,500.00** (brought forward on 300-000, not split by customer) | No balances | AISB line |
| Suppliers due (as at 17 Nov) | **Overdue RM 4,050.00** (2: PI2607-019 850.00 inside 400-000's brought forward; PI2610-013 3,200.00 Payroll advisor) · due in the next 14 days RM 0.00 | No balances | AISB line |

- The bank figures are the statement's (Bank.dc.html `cur:2026-10`: close 34,314.15, in 47,962.80, out 106,067.00);
  the book closing stays 33,618.35 (stage 1). AI's FCA: opening USD 12,480.00, two lines in (TT CR 3,000.00 on 28 Oct,
  2,000.00 on 30 Oct), closing USD 17,480.00 (new).
- Out-of-date examples (state only): "Statement runs to 12 Nov"; "SQL data runs to 12 Nov, fetch again"; "as at
  12 Nov, fetch again".

### HR cards (hidden from Marcus Teoh)

| Card | AISB | AI | All companies |
|---|---|---|---|
| On leave (today, no type) | **Aina, Khadijah**; 3 this week | No one on leave today; 0 this week | Aina (AISB), Khadijah (AISB); 3 this week |
| Birthdays and anniversaries (October) | Aina **10 years** (3 Oct) · Kah Seng birthday (12 Oct) · Izzati birthday (21 Oct) | Pei Shan **5 years** (1 Oct) | all four, company chips |
| Dates coming up (60 days) | Probation ends 30 Nov · Contract ends 31 Dec | Work permit expires 10 Jan | all three |
| Headcount (today) | **9** in employment · 1 joiner · 0 leavers | **5** · 0 · 0 | 14 · 1 · 0 |
| Requests waiting (now, HR only) | Waiting for approval **2** · Approved, waiting to pay **4** | Nothing waiting | AISB 2 / 4 |

Privacy: no pay, IC, bank, leave type or medical detail on any card; the payroll total appears only as "Salaries,
October" inside Payments amounts.

---

## 17. What this asks of existing boards (for packages B to K)

- **Company / PaymentsRegister (D):** add Stationery Mart (PV2610-022, 1,120.00, paid 30 Oct); Wei Ming's claim Past
  due and approved (AF-2611-003) instead of "Waiting for SQL record"; Approval markers as section 13; Office rental
  approved after payment.
- **Recurring (D):** advance note "left 1,500.00"; approval-once text "Approved by Rajesh Kumar, 1 Oct 2026"; AI
  salary row lists A001 to A005.
- **Main / DarkOverview / MobileOverview (C, I):** Next up as section 14; AISB November **set up** (the November view
  no longer reads "Month not set up" for AISB); checklist 18 of 27 and 15 of 22.
- **MobileCompany (I):** AI salaries 5 people, RM 21,300.00 (review).
- **SetupCompanies (H):** AISB "months set up" 3 → 4; "Runs payroll in this app" on for AISB only; HRDF off, no
  HRD Corp number.
- **SetupChart (E or H):** AISB gains 900-850 Staff welfare, 900-860 Travelling, 900-870 Entertainment.
- **SetupStatutory (E):** kind "Net salaries payable" = 420-000 Accruals for AISB.
- **Sidebar, Topbar (A):** keys, badges, counts and the switcher list from sections 3, 14 and 15.

---

## 18. Arithmetic checks (all hold)

- October pay: 48,600.00 basic + 9,700.00 allowances + 847.90 overtime = 59,147.90 gross. 59,147.90 − 5,346.00 −
  205.00 − 81.90 − 4,915.00 = 48,600.00 net. The 8 nets add up to 48,600.00.
- EPF: 946 + 858 + 770 + 627 + 605 + 858 + 374 + 308 = 5,346; 1,032 + 936 + 840 + 684 + 660 + 936 + 442 + 364 = 5,894.
- SOCSO: 29.75 × 4 + 28.25 + 27.25 + 16.75 + 13.75 = 205.00; 104.15 × 4 + 98.90 + 95.40 + 58.60 + 48.10 = 717.60.
- EIS: 11.90 × 4 + 11.30 + 10.90 + 6.65 + 5.45 = 81.90 (each side).
- PCB: 1,080 + 1,180 + 700 + 560 + 340 + 1,000 + 55 + 0 = 4,915.
- KWSP 5,346.00 + 5,894.00 = 11,240.00. PERKESO 205.00 + 717.60 + 81.90 + 81.90 = 1,086.40.
- AF-2611-003: 486.50 + 408.00 + 320.00 = 1,214.50. CL-2610-004: 12.00 + 186.50 + 288.00 = 486.50.
- AISB overdue in To pay: 11,240.00 + 486.50 = 11,726.50. Due in 7 days: 408.00 + 320.00 + 1,500.00 = 2,228.00.
- Budget AISB as at 19 Oct: lines not paid by 19 Oct 48,600.00 + 12,000.00 + 11,240.00 + 6,500.00 + 4,915.00 +
  3,200.00 + 2,498.60 + 1,150.00 + 1,086.40 = 91,190.00; payments with no line, not paid by 19 Oct 398.60 + 1,120.00 +
  486.50 + 408.00 + 320.00 = 2,733.10; 91,190.00 + 2,733.10 = 93,923.10; 93,923.10 − 56,790.35 = 37,132.75. Lines
  115,190.00 − 91,190.00 = 24,000.00 paid (the contractor).
- Budget AI: lines 21,300.00 + 6,750.00 + 4,478.00 + 612.40 + 1,420.00 + 2,500.00 = 37,060.40; paid 21,300.00 +
  6,750.00 + 612.40 = 28,662.40; still to pay 4,478.00 + 1,420.00 + 2,500.00 = 8,398.00; no RM balance entered, so no
  funds to request. All companies 37,132.75 (AISB alone); four companies 37,132.75 + 6,420.00 + 9,880.00 = 53,432.75.
- AI KWSP: employee 638 + 462 + 506 + 429 + 48 = 2,083; employer 696 + 546 + 598 + 507 + 48 = 2,395; 2,083.00 +
  2,395.00 = 4,478.00.
- November checklist (AISB): 27 + 3 = 30 items, 1 done (Register Daniel with KWSP and PERKESO).
- Opening year to date: 522,384.60 + 59,147.90 + 61,800.00 = 643,332.50; + 63,300.00 = 706,632.50. Employee EPF
  47,912.00 + 5,346.00 + 4,873.00 = 58,131.00. PCB 43,915.00 + 4,915.00 + 4,915.00 = 53,745.00.
- Money in AISB: 47,962.80 + 8,021.40 = 55,984.20; out 106,067.00 + 10.00 = 106,077.00.
- Suppliers overdue: 850.00 + 3,200.00 = 4,050.00.
- Next up: AISB 11 + AI 5 − 2 shared rows = 14. Leave: Khadijah 5 Oct to 10 Jan = 27 + 30 + 31 + 10 = 98 days.
- Kavitha: 2,400.00 − 400.00 − 1,600.00 = 400.00 to collect; 1,600.00 = 50% of 3,200.00.
