# Package K results

## Decisions
- KWSP payment name (from the app): hrp/rules.py names the payment 'KWSP payment', the tests' recurring payee is 'KWSP', and checklistbook SUBMIT uses 'KWSP'. 'KWSP (EPF)' is nowhere in hrp/ or static/app.js. So every payment row, recurring row, To pay item, register row, Budget line, bank-review payment and SQL-page payment reads 'KWSP' ('KWSP for October', 'Pay KWSP for October', 'KWSP · September'). 'EPF (KWSP)' stays only where the app uses the statutory kind word: statutory.KIND_WORDS and masters.py, that is Setup › Statutory accounts, Statutory payables, Next up rule 14, the audit pack statutory page, payslip and statutory deduction labels, and employer-number fields. The same rule applies to the other two payments: 'PERKESO' (not 'PERKESO (SOCSO & EIS)') and 'PCB' (not 'PCB (MTD)' or 'LHDN (PCB)'). The kinds keep 'SOCSO (PERKESO)', 'EIS (SIP)' and 'PCB (LHDN)'. The BooksStatutory note at line ~767 ('one of the two names should go') is dropped.
- Reminder titles: the SetupChecklist template is filled in with the preferred name wherever a reminder title is shown: 'e-CP22 for Daniel', 'CP22A for Kah Seng', 'Register Daniel with KWSP and PERKESO', 'Stamp the contract of Daniel'. Prose may stay descriptive. This includes Next up rows 12 and 13 on Main, DarkOverview and CommandPalette, because the app shows reminder titles with {name} on Next up. samples §14's 'no name' rule is reworded to 'no pay figure or other personal data', and the rule 16 HR rows (probation, permit) stay nameless. SetupGeneral's made-up '8 Sep joiner' is replaced (see the setup-types group).
- Daniel's joiner tasks all sit on AISB's November checklist: 'Register Daniel with KWSP and PERKESO' (due Tue 10 Nov, done 10 Nov), 'e-CP22 for Daniel' (due Thu 3 Dec) and 'Stamp the contract of Daniel' (due Thu 3 Dec). The stamp task follows from the SetupChecklist template because his basic of 3,500.00 is over 3,000. The brief's '1 of 28' is corrected: November's 28 already included the e-CP22, so with the registration and the stamp task November reads **1 of 30**. CP22A for Kah Seng still waits for December and is not counted.
- Company.dc.html stays as an unlinked source board. CommandPalette 'Switch company' links to CompanySwitcher.dc.html (the top-bar switcher). States 'Go to October' links to MonthlyChecklist.dc.html. Company.dc.html itself is not edited.
- Budget (AISB) follows the Payments register: the contractor was paid 6 Oct, Electricity 1,163.20 was paid 4 Nov, Telephone & internet 398.60 was paid 28 Oct (as the register has it), PCB was paid 14 Nov, PERKESO was paid 17 Nov, and KWSP and the consultant are unpaid. Stationery Mart 1,120.00 (paid 30 Oct) and the three AF-2611-003 claims (unpaid) are added as payments with no budget line. Rental received is dated 2 Oct. The balance is moved to the date the October fund requisition was signed: **Mon 19 Oct 2026, RM 56,790.35** (Maybank current's running balance after the 15 Oct line on the October statement). The 45,000.00 fund receipt then arrives 20 Oct. The figures are: still to pay 91,190.00 (lines) + 2,733.10 (payments with no line) = **RM 93,923.10**, and funds to request **RM 37,132.75**.
- Insurance renewal 2,498.60 stays only as an AISB budget line with no payment entered yet (link none). It is not a tracker payment, so BankReview's 'aIns' candidate and Sql's 'Insurance premium 2,310.00' (p5) are removed.
- AI's Budget is rebuilt from AI's own October payments: Salaries — staff 21,300.00 (paid 24 Oct), Farm supplies 6,750.00 (paid 19 Oct), KWSP 4,478.00, PERKESO 612.40 (paid 14 Nov), Electricity bill 1,420.00 (waiting for the Nov statement) and Consultant — farm audit 2,500.00 (due 30 Nov). AI's only account is Maybank FCA in USD, so **no RM balance is entered**. AI's Funds to request (October and September) shows the existing sentence 'Enter the bank balance to see funds to request', and the All companies total is AISB's alone (37,132.75). In the four-company variant it is AISB 37,132.75 + AIL 6,420.00 + AIP 9,880.00. September variant: AISB 31,200.00, AI not entered, AIL 5,980.00, AIP 9,100.00, recorded in samples as variant figures.
- AI's October KWSP is **RM 4,478.00** (employee 2,083.00, employer 2,395.00), worked out by the Third Schedule from AI's basics (Faizal 5,800: 638/696; Pei Shan 4,200: 462/546; Priya 4,600: 506/598; Jun Wei 3,900: 429/507; Rina, foreign worker, 2,400 at 2% + 2%: 48/48). It replaces 11,240.00 on every AI row. AI's Due and overdue reads '1 overdue, RM 4,478.00'.
- AISB October Electricity bill: paid Wed 4 Nov, RM 1,163.20, linked to PV2611-003 (version 2 changed in SQL to 1,136.20), with the paid date typed in because the November statement is not imported (stage 1 §23). It is no longer 'Waiting for Nov statement'. Rule 7's '1 voucher changed in SQL' already counts it. Payment's 'cancelled' state keeps CN2611-001 marked as an invented state-only document.
- The Telephone & internet register row (paid 28 Oct, 398.60, bank line not on the statement) is left as stage 1 §25 leaves it, because rule 7's '4 payments not recorded' depends on it. Budget follows the register. The gap is recorded in samples D19.
- Trial balance read times (stage 1 §21 wins). In 'differs' the journal is read 18/11/2026 10:42 and SQL's TB 18/11/2026 10:58 (SqlBooks' 10:58:41), so the TB holds JV2610-012 (Dr 900-010 / Cr 310-000 48.00) and the journal does not: 310-000 33,570.35 against 33,618.35, and 900-010 58.00 against 10.00. In 'stale' the TB is read 10:58 and the journal again at 11:05. There is no 17/11 09:10 read. AuditPackBooks D1/D2 become the 310-000 and 900-010 rows.
- Net salaries payable (420-000 Accruals) was confirmed for AISB on **Fri 13 Nov 2026**, before the 14 Nov audit pack. So stage 1's '4 statutory accounts added' at 18 Nov 10:50 and AuditPack's '74 to SQL's books or the statutory accounts' stand. SetupStatutory's history for that row says 13 Nov, and BooksStatutory's suggestions leave it out (toast '4 statutory accounts added.').
- Consultant names: the SQL name for 400-P004 stays 'Payroll advisor' (stage 1, Books, BooksParties). The payee and short name are 'Payroll Advisory PLT' everywhere. 'Robin Advisory' and 'Robin Advisory Sdn Bhd' go, and the bank boards read 'Consultant fee — Payroll Advisory PLT'.
- Payment types: SetupTypes is the single list (hrp/rules.py CATEGORIES and DOC_TYPES plus the canvas's added types). Every board uses its labels. Recurring maps Director → 'Director allowance', Office rental → 'Rental', Cloud hosting, Cleaning and Security → 'Other payment', Utility → 'Utility / telco', Consultant → 'Consultant fee', Money in → 'Money received'. Document types use the full DOC_TYPES labels. SetupRequired's types and docs tabs show exactly SetupTypes' rows.
- Customers and suppliers: SetupParties' 9-row list is the one list, and SetupChart's parties tab shows it. Recurring's Cleaning service party is 400-C003 (SetupParties' stopped 'Old cleaning contractor'). The water supplier is 400-W001. The office landlord's account is CIMB 8006447122 (Menara Holdings).
- AISB's September 2026 is Still open and only AI's September is filed (5 Oct). Setup refusal states that need a filed month use AI.
- Recurring counts follow the Recurring board: AISB 11, AI 4, 15 in all. The KWSP recurring history and the audit trail both read 11 Nov 2026 14:20, 11,180.00 → 11,240.00, 'October's contributions from the payroll summary'. The consultant fee started 1 Sep 2026 and is approved per payment (latest AF-2611-004, waiting).
- Approval forms: AIP has no approvers ('None yet'). That is the no-approvers example on Approvals, PrintApprovalForm and SetupApprovers. The SA advance series is app-wide like AF, so a new AI advance today is SA-2611-003.
- Overview 'Documents missing 2' (AISB October) means the 2 checklist items whose documents are missing: 'KWSP, PERKESO and PCB paid or acknowledgement filed' (KWSP acknowledgement) and 'Fund receipts: OR and validated e-Invoices add up' (e-Invoice). AuditPack already counts it this way. MonthlyChecklist gains a 'Missing documents 2' filter (#missing-documents), which the counter opens.
- The rollover banner counts the October Next up rows of the company it names. e-CP22 is November, so the banner reads 'AISB … 5 things left', and CommandPalette tags the e-CP22 item 'Nov 2026'.
- Notifications and activity: the October Maybank current statement had 14 lines, 8 matched, imported 3 Nov 09:40. The Maybank FCA October statement had 2 lines (5 Nov). The Office rental bank slip was uploaded 13 Nov 10:42. The bell shows 6 unread everywhere (Topbar default 6, or 7 with trail attention).
- Card and tab links land on the state they name. Each target reads a first-load hash, as PrintHrLists does: Approvals #from-overview #hr-requests #paid-without #to-print; ToPay #from-due #from-requests #kept-here; PaymentsRegister #without-approval; BooksParties #customers-overdue #suppliers-due; HrCalendar #coming-up; HrLeave #calendar #balances; HrStaffRecord #S0nn plus #claims or #pay; PayrollCheck #ai; AccountingKeptHere #purchases #journals #close; MonthlyChecklist #missing-documents. Sql and SqlBooks 'Open AI's Overview' becomes 'Open the Overview'.
- Forms use 'Discard your changes?' (the States pattern) everywhere except dialogs that discard a whole new item. Every 'added / Saved / deleted / put back' toast on the Setup boards offers Undo.
- List states: the new boards PayrollCheck and SetupHolidays gain their missing many-rows state. The pre-scope boards Setup, SetupCompanies, SetupParties, SetupChart, SetupMatching and SqlBooks are accepted exceptions, because review §3's rule covers new boards.
- Scope §10 bank reconciliation gap: a new board **PrintBankRec.dc.html** (printed statement in the standard layout, No money moved pairs, totals check, SQL GL check, Prepared by / Reviewed by with the sign-off note, code + keyed check + QR) is added. Bank and DarkBank get a Print action, BankReview gets a 'No money moved' group, and ApprovalUpload gets bank-reconciliation states.
- packageK-notes: KWSP name, Company.dc.html, Switch company and Daniel and e-CP22 are as above. Budget's contractor details become 'Field works, October'. AIL/AIP card figures and the opening year-to-date figures go into samples.md. The empty Funds/Bank sentences may wrap (kept). $preview heights: each group measures the boards it renders, and the rest stay estimates. Phone stays deferred. PrintHrLists examples and the plain AF-2611-003 print stay intended. Foundations' signature block splits Signature and Date as PrintApprovalForm does. Approvals gains a no-approvers state (AIP).
- Company names AISB / Agrinexus stay as samples D4.1 and stage 1 set them (the owner's own companies are the app's subject; the made-up-names rule applies to people, and every person name passed the git check). 'Exabytes' is replaced by a made-up bank text.
- Daniel's November pay stays at a full month (3,500.00): samples says the November workbook pays the full month as his offer letter agreed. September's EPF (5,320.00 / 5,860.00) stays as stage 1 has it, with a note that September's per-person split is not drawn.

## Samples changes
- §0 D13: add 'AISB November 2026: 1 of 30 (the 27 items, e-CP22 for Daniel, Stamp the contract of Daniel, and Register Daniel with KWSP and PERKESO done 10 Nov); CP22A for Kah Seng waits for December.' Also add the 'Missing documents 2' meaning: KWSP acknowledgement and the e-Invoice item.
- §0 D12: reword the needs-approval list in SetupTypes labels: 'Salary, Director allowance, Rental, Consultant fee, Other payment, Staff claim, Salary advance and Payroll run: yes. Statutory, Utility / telco and Money received: no.'
- §0 D16: rule 16 rows (probation, permit) are written without names. Joiner and leaver reminder rows show the template title with the preferred name ('e-CP22 for Daniel', 'CP22A for Kah Seng'), as the app shows reminder titles.
- §0 D19: replace the 'left for K' bullets with what K settled. AI KWSP 4,478.00. Budget follows the register, with the balance on 19 Oct. AI has no RM balance entered. Consultant payee Payroll Advisory PLT (SQL name 'Payroll advisor'). Insurance renewal is a budget line only. Telephone & internet's 28 Oct bank line is not on the statement (stage 1 §25, left because rule 7 depends on it). Overview September bank movement versus the September register (stage 1 §25, left). The KWSP double row stays an owner question.
- §0 new D20 'Names K settled': payments 'KWSP', 'PERKESO', 'PCB'; statutory kinds 'EPF (KWSP)', 'SOCSO (PERKESO)', 'EIS (SIP)', 'PCB (LHDN)'; reminder titles from the SetupChecklist template with the preferred name; Net salaries payable confirmed 13 Nov; AIP no approvers; SA series app-wide; Cleaning service 400-C003; water supplier 400-W001; landlord CIMB 8006447122; the read times for the TB differs and stale states.
- §2: AIP 'Approvers (Setup › HR)' becomes 'None yet (the no-approvers example)'.
- §5 Daniel: 'Joiner tasks on November's checklist: Register Daniel with KWSP and PERKESO (due Tue 10 Nov, done 10 Nov), e-CP22 for Daniel (due Thu 3 Dec), Stamp the contract of Daniel (due Thu 3 Dec, basic over RM 3,000).'
- §6: add 'November: the workbook pays Daniel's full month (3,500.00), as his offer letter agreed; the part-month rule applies to runs made in the app.' Add 'September per person is not drawn; its EPF 5,320.00 / 5,860.00 stays as stage 1.' Add the opening year-to-date table copied from PayrollOpeningYtd: Jan to Sep per person including Kavitha, the 26.00 placed on Aisha's employee EPF, November 61,800.00, December 63,300.00, gross Jan to Nov 643,332.50, YTD 706,632.50, Kah Seng 97,332.50.
- §9: Tue 1 Dec 'CP22A for Kah Seng'; Thu 3 Dec 'e-CP22 for Daniel' and 'Stamp the contract of Daniel'; add Tue 10 Nov 'Register Daniel with KWSP and PERKESO' (done, November checklist).
- §13 marker table: 'Electricity bill 1,163.20' (paid 4 Nov, PV2611-003), not 1,150.00. 'KWSP, PERKESO, PCB' names unchanged.
- §14: rows 3 and 4 read 'Pay KWSP for October', with AI's meta 'AI · To pay · RM 4,478.00 · legal deadline 15 Nov'. Row 12 title 'CP22A for Kah Seng'. Row 13 title 'e-CP22 for Daniel'. Intro: 'Rows carry no pay figure or other personal data; joiner and leaver reminders show the preferred name as the template does.'
- §15 To pay items: AI 'KWSP October 4,478.00 (overdue)'.
- §16: Due and overdue AI '1 overdue, RM 4,478.00'. Budget row AISB: 'Budget as at Mon 19 Oct (balance RM 56,790.35, Maybank current, statement) · Budgeted RM 115,190.00 (and USD 1,200.00) · Still to pay RM 93,923.10 · Funds to request RM 37,132.75'. AI: 'Lines 37,060.40; no RM balance entered (AI's only account is Maybank FCA, USD): Enter the bank balance to see funds to request'. All companies total RM 37,132.75. Add the four-company and September variant figures (Oct AIL 6,420.00, AIP 9,880.00; Sep AISB 31,200.00, AI not entered, AIL 5,980.00, AIP 9,100.00), marked as variant figures with no Budget view. Add the AIL/AIP checklist variants (Oct AIL 10 of 14, AIP 12 of 18; Sep AIL 12 of 12, AIP 15 of 15). Note 'Documents missing 2 = checklist items'.
- §18: replace the Budget line with 'AISB as at 19 Oct: lines not paid by 19 Oct 48,600.00 + 12,000.00 + 11,240.00 + 6,500.00 + 4,915.00 + 3,200.00 + 2,498.60 + 1,150.00 + 1,086.40 = 91,190.00; payments with no line, not paid by 19 Oct 398.60 + 1,120.00 + 486.50 + 408.00 + 320.00 = 2,733.10; 93,923.10 − 56,790.35 = 37,132.75'. Add 'AI KWSP 638 + 462 + 506 + 429 + 48 = 2,083; 696 + 546 + 598 + 507 + 48 = 2,395; 4,478.00'. Add 'November checklist 27 + 3 = 30, 1 done'.

## Owner questions
- Joiner reminders: the app makes separate 'KWSP registration for {name}' (7 days) and 'PERKESO registration for {name}' (30 days) reminders, uses "Stamp {name}'s appointment letter", and titles the LHDN ones 'e-CP22 to LHDN for {name}' and 'CP22A to LHDN for {name}'. The canvas's Setup › Joiner and leaver reminders merges the two registrations into one 7-day 'Register {name} with KWSP and PERKESO', says 'Stamp the contract of {name}' and drops 'to LHDN'. K kept the canvas form, as the brief asks. Should the build keep the app's split and wording, or change the app to the merged form?
- The October KWSP gives two Next up rows for one unpaid payment, as the code does today: rule 14 'EPF (KWSP) for October 2026 wasn't paid…' (Statutory payables) and 'Pay KWSP for October' (To pay). Keep both rows, or show one?

## Dropped
- Phone boards (fig-overview, wording, coverage and links-states 'deferred' entries): deferred by the owner on 18 Nov. Not edited and listed for the phone package. MobileApprovalPhoto links stay as planned-name links.
- coverage 'Status of the remaining packageK-notes items': not a gap. Only the $preview heights stay open, and each group measures the boards it renders.
- fig-overview 'Telephone & internet paid 28 Oct 398.60': not changed in the register. Stage 1 §25 leaves it on purpose because rule 7's '4 payments not recorded' (Next up row 9, Not in SQL 4, the Sql board) depends on it. Budget is aligned to the register and samples D19 records the gap.
- fig-overview 'September bank movement cannot hold the September payments': a stage 1 §25 known conflict (September is before the journal kept here). Recorded in samples D19 only.
- fig-accounting 'statutory accounts 5 vs 4' fix as proposed (77 changes, stage 1 recount): replaced by the smaller decision that Net salaries payable was confirmed 13 Nov, before the pack, so AuditPack and stage 1 counts stand.
- fig-accounting 'September EPF 5,320.00 / 5,860.00' explanation: no per-person change gives exactly 26.00 / 34.00 under the Third Schedule, so samples records that September's split is not drawn and the stage 1 figures stay.
- fig-hr 'Daniel paid a full month': kept, with a samples note that the November workbook pays the full month. Prorating would change PayrollCheck, Totals and OpeningYtd figures for no product reason.
- Brief's 'November then reads 1 of 28': arithmetic corrected. November's 28 already included e-CP22, and adding the registration and stamp tasks makes 1 of 30.
- links-states 'list states missing' on Setup, SetupCompanies, SetupParties, SetupChart, SetupMatching and SqlBooks: accepted exceptions (pre-scope boards, review §3's rule covers new boards). PayrollCheck and SetupHolidays are fixed.
- names-codes 'company names AISB / Agrinexus are real': kept per samples D4.1 and stage 1 (the owner's own companies are the app's subject). Person names all passed. Only 'Exabytes' is replaced.
- fig-overview 'Budget Insurance renewal 2,498.60 in no register': resolved as a budget line with no payment entered. BankReview aIns and Sql p5 are removed rather than adding a payment, which would change To pay and Approvals counts.
- fig-admin 'rename 400-P004 to Payroll Advisory PLT': not renamed. The SQL name stays 'Payroll advisor' (stage 1, Books) and Payroll Advisory PLT becomes the short name.
- Company.dc.html's own old wording (KWSP (EPF), e-CP22 for the joiner…, payee 'Payroll advisor'): not edited. The board is kept as an unlinked source per the brief.
- Duplicates merged: AI KWSP (3 reports), KWSP name (4), e-CP22 titles (4), Daniel's registration (5), Approvals no-approvers (2), Company.dc.html links (2), AIL/AIP figures (3), consultant name (2), SetupMatching parties (2), electricity amount (2).

## Groups

### samples (15 fixes)
Group "samples": done. The only file edited is design/samples.md. There is no samples.md in design-motion\project. PayrollOpeningYtd.dc.html was only read.

Checkers:
- `check_imports.js design-motion/project --strict`: 2953 imports checked, 0 problems.
- `check_board.js` does not apply to samples.md, because it is a Markdown file and not a board. Run on it, the checker gives "FAIL: no <x-dc>". No board was touched.

Per fix:
1. **All samples_changes, opening YTD table (partly): applied.** Every group in the list was changed, plus the extra cells the note named in items 9, 10, 13 and 14. The opening YTD table is in §6, copied from PayrollOpeningYtd's per-person Jan to Nov figures:
   - Columns: Jan to Sep, Nov, Jan to Nov, Dec, and year to date, for gross, employee EPF and PCB.
   - Jan to Sep is worked out as opening less October (§6) less November. Kah Seng's November is 8,400.00 gross, EPF 0, PCB 1,000.00, taken from PrintPayslip.
   - Totals tie: Jan to Sep 522,384.60 / 47,912.00 / 43,915.00; Nov 61,800.00; Jan to Nov 643,332.50 / 58,131.00 / 53,745.00; Dec 63,300.00 / 4,873.00 / 4,805.00; YTD 706,632.50. Kah Seng is 97,332.50 Jan to Nov.
   - The 26.00 sits on Aisha's employee EPF (8,488.00 = 9 × 946.00 − 26.00).
   - Kah Seng's Jan to Sep gross is 4,084.60 above nine months of 8,400.00. I describe it as overtime, outside EPF wages, not split by month.
2. **D13 (confirmed): applied.** Added "AISB November 2026: 1 of 30" and that CP22A waits for December. Also states that the stamp task is a checklist item only and not a Next up row, so the 12 rows and the badges stay. Added the meaning of "Documents missing 2" (the KWSP acknowledgement and the e-Invoice item) and the #missing-documents filter.
3. **D12 (confirmed): applied.** Needs-approval list now uses SetupTypes labels.
4. **D16 (confirmed): applied.** Rule 16 rows (probation, permit) stay nameless. Joiner and leaver rows use the template title with the preferred name.
5. **D19 (confirmed): applied.** The "left for K" bullets are replaced with what K settled. Also added:
   - The AI 11,200 vs 11,310 mismatch is gone because AI has no RM balance.
   - AI's paid amounts are as recorded (PERKESO 612.40, not derived); only the KWSP is derived.
6. **New D20 (confirmed): applied.** It holds the listed names and facts:
   - payment names KWSP, PERKESO and PCB, and the statutory kinds;
   - reminder titles;
   - Net salaries payable confirmed 13 Nov;
   - AIP no approvers;
   - SA series app-wide (SA-2611-003);
   - 400-C003, 400-W001 and the landlord's CIMB 8006447122;
   - TB read times for the "differs" and "stale" states.

   I also added these plan decisions as sample facts so other groups find them in one place: payment type mapping, recurring counts and the KWSP history line, Electricity paid 4 Nov on PV2611-003, AISB September still open, the rollover banner "5 things left", and statement and notification counts.
7. **§2 (confirmed): applied.** AIP approvers now read "None yet (the no-approvers example)".
8. **§5 Daniel (confirmed): applied.** Added his three joiner tasks with their dates. Also added AI's per-person KWSP table under AI's basics in §5.
9. **§6 (confirmed): applied.** Added that the November workbook pays Daniel's full month and the part-month rule applies to app runs. Added that September per person is not drawn and its EPF 5,320.00 / 5,860.00 stays. Added the YTD table (see 1).
10. **§9 (partly): applied as the note says.** Added the Thu 3 Dec "Stamp the contract of Daniel" row, marked not a Next up row. "Register Daniel with KWSP and PERKESO (done 10 Nov)" is a note under the table, not a dated row. The CP22A and e-CP22 rows now name their checklist month.
11. **§13 (partly): applied, including the note.** The marker row now reads Telephone & internet 398.60 (paid 28 Oct) and Electricity bill 1,163.20 (paid 4 Nov, PV2611-003).
12. **§14 (confirmed): applied.**
    - The intro is reworded.
    - Row 4's amount is RM 4,478.00.
    - Row 12 reads "CP22A for Kah Seng" and row 13 "e-CP22 for Daniel".
    - Counts are unchanged.
13. **§15 (confirmed): applied.** AI's To pay KWSP is 4,478.00.
14. **§16 (partly): applied, including the note.**
    - AI Due and overdue: 1 overdue, RM 4,478.00.
    - AISB Budget is as at Mon 19 Oct: balance 56,790.35, Budgeted 115,190.00 (and USD 1,200.00), Paid RM 24,000.00 (lines paid by 19 Oct, the contractor only), Still to pay 93,923.10, Funds to request 37,132.75.
    - AI lines total 37,060.40 with no RM balance. Its budget is therefore as at today: Paid 28,662.40, Still to pay 8,398.00, and the "Enter the bank balance to see funds to request" sentence. These two figures are worked out from the plan's paid dates.
    - All companies total is 37,132.75. The old 48,140.00 total and the "as at 10 Nov" wording are gone.
    - Added notes for "Documents missing 2", AISB's budget dates (Rental received 2 Oct, fund receipt 20 Oct) and AI's budget lines.
    - Added variant figures, marked as having no Budget view:
      - Funds to request, Oct: AIL 6,420.00, AIP 9,880.00; four-company total 53,432.75.
      - Funds to request, Sep: AISB 31,200.00, AI not entered, AIL 5,980.00, AIP 9,100.00; total 46,280.00.
      - Checklist: Oct AIL 10 of 14, AIP 12 of 18; Sep AIL 12 of 12, AIP 15 of 15.
    - I dropped the old "Paid 68,263.20 today" figure. It does not tie to the new register-based budget (lines paid by today would be 98,251.40).
15. **§18 (partly): applied, including the note.**
    - AISB budget arithmetic as given (91,190.00 + 2,733.10 = 93,923.10; less 56,790.35 = 37,132.75; 24,000.00 paid).
    - AI lines 37,060.40, paid 28,662.40, still to pay 8,398.00, no funds to request, and the four-company total 53,432.75. The old AI "11,200" line is gone.
    - AI KWSP 2,083 + 2,395 = 4,478.
    - November checklist 27 + 3 = 30, 1 done.
    - Opening YTD ties for gross, EPF and PCB.

Nothing was skipped. No new person names were added. Menara Holdings and CIMB 8006447122 are already on the Company, Payment and PaymentsRegister boards.

### overview (3 fixes)
Group "overview": all three fixes are applied, including the four gaps in the "partly" notes. I touched only Main.dc.html, DarkOverview.dc.html and OverviewCards.dc.html in design/canvas. samples.md already had these figures (D19, D20, sections 14 to 16 and 18), so it needed no change.

**Main.dc.html: APPLIED, all four gaps closed**
- **Funds to request:** F oct is aisb 37132.75, ai null, ail 6420, aip 9880. F sep is aisb 31200, ai null, ail 5980, aip 9100.
  - AI (null) returns `{ empty: 'Enter the bank balance to see funds to request', short: 'Balance not entered', asZero: true }`.
- **Gap 1 (B and src text):** AISB's bit now reads "AISB: still to pay RM 93,923.10, less RM 56,790.35 in the bank on 19 Oct." The AI bit and the September AI figure are gone.
  - The October src reads "From the Budget as at 19 Oct".
  - Decision: the September src drops its date ("From the Budget: …"). Samples gives no September balance date, and the old "10 Oct" broke the new rule that the balance date is the day the fund requisition was signed.
- **Gap 2 (`agree`):** I chose asZero on AI's "not entered", so All companies totals the companies that have a balance.
  - Two companies: head "RM 37,133", note "to cover what's still to pay", lines "AISB RM 37,132.75; AI Balance not entered". So the total is AISB's alone, as samples says.
  - Four companies: head "RM 53,433", with lines for each company (53,432.75 as in samples).
  - September: head "RM 31,200".
- **AI KWSP:** the 'kwsp' Next up meta reads "AI · To pay · RM 4,478.00 · legal deadline 15 Nov", and its href is ToPay.dc.html#kept-here. The AI line on Due and overdue reads "RM 4,478.00 overdue", with the matching bit.
- **Next up rows 12 and 13:** they read "CP22A for Kah Seng" and "e-CP22 for Daniel". ecp22 has oct:false. nextDue reads "3 Dec · e-CP22 for Daniel".
- **Rollover banner:** novCos moved up, and octLeft counts only the October rows of the companies whose November is set up.
  - All companies: "AISB's November is set up … 5 things left".
  - AISB alone: "November has started", 5 things.
  - AI alone: no banner.
- **Gap 4 (November checklist):** I removed the "0 ticked" novSet branch and made the figure data: `D.nov = { aisb: [1, 30] }`.
  - AISB November: "1 of 30", note "29 still to do".
  - All companies: "1 of 30" with note "AISB · 29 still to do", and AI's line reads "No checklist yet".
- **Activity rows:**
  - "uploaded Bank slip to Office rental · AISB · 13 Nov 10:42" moved down to the 13 Nov slot.
  - "imported the October statement, 14 lines, 8 matched · AISB · Maybank current · 3 Nov 09:40" moved to the end, so the list stays newest first.
  - With the 6-row cap, Aisha's All companies view no longer shows the statement row.
- **Card hrefs:**
  - Paid without approval → Approvals.dc.html#from-overview
  - Requests waiting → Approvals.dc.html#hr-requests
  - Due and overdue → ToPay.dc.html#from-due
  - Customers overdue → BooksParties.dc.html#customers-overdue
  - Suppliers due → BooksParties.dc.html#suppliers-due
  - Dates coming up → HrCalendar.dc.html#coming-up
  - On leave → HrLeave.dc.html#calendar
  - Documents missing counter → MonthlyChecklist.dc.html#missing-documents
- **Gap 3:** the Dates `where` now reads ", HR, Staff, Calendar and reminders, filtered".

**DarkOverview.dc.html: APPLIED.** It has exactly the same edits as Main. A diff of the two script blocks shows only `DARK = false/true`.

**OverviewCards.dc.html: APPLIED**
- The same card fixes as Main: F, B and src, AI asZero, AI due line at RM 4,478.00, the November checklist data, every card href and the Documents missing hash.
- Dates `where` reads ", HR, Staff, Calendar and reminders, filtered". The legend row reads "Open calendar: HR › Staff › Calendar and reminders, filtered. Merges Birthdays and anniversaries".
- The Checklist empty example was already `{ cos: ['ai'], m: 'nov' }`. It still draws "No checklist for this month yet", so I left it.
- The Funds empty example (AI, August) is unchanged.
- The card has no Next up rows and no activity, so those fixes don't apply here.

**Not done:**
- **$preview heights:** not measured, because I did not render the boards. The values stay as they were: Main and DarkOverview 1440×2300, OverviewCards 1600×5200. They are still estimates. No layout changed: the rows and cards are the same, and only text changed.
- **Hash targets:** the hrefs only land on their states once the Approvals, ToPay, BooksParties, HrCalendar, HrLeave and MonthlyChecklist groups add their first-load hash handlers. Until then each link opens the board's default state.

**Checks:**
- `check_board.js`: OK on all three files.
- `check_imports.js --strict`: "2956 imports checked, 0 problems".
- I also ran each board's script in node with a stub runtime to check the logic: All companies, AI alone, four companies, September, November, and AISB in November. The figures above are what it printed. No helper files were written.

### shell-notify (5 fixes)
Group "shell-notify": all five fixes are applied. Every file I touched passes check_board.js, and check_imports.js --strict reports "2956 imports checked, 0 problems". I touched no other file.

Files (folder design/canvas):

1. **Notifications.dc.html: applied.**
   - The October statement event (e1) now reads 'AISB · Maybank current · 14 lines, 8 matched.' and is dated '3 Nov, 09:40'.
   - The AI FCA event (in the many-rows list) now reads 'AI · Maybank FCA · 2 lines matched.' (5 Nov).
   - The Office rental slip event (e2) is dated '13 Nov, 10:42'.
   - I dropped 'Bank slip uploaded to Cloud hosting' (1 Nov). Repointing it at Office rental would have repeated e2.
   - The list is re-sorted newest first: e0, ec, ed (Today 08:00), ea (17 Nov), eb (13 Nov 14:10, mismatch view only), e2, e3, e4, e5, e6.
   - e1 is pulled out as its own row and is always drawn. In the default view it is last. In the many-rows view it comes after the 9 Nov to 4 Nov events and before the other 3 Nov ones.
   - Unread at default is still 6 (e2, e1, ec, ed, ea, e3), or 7 with trail attention. The read-state, filter and right-gating logic is unchanged.

2. **Topbar.dc.html: applied.**
   - The default unreadN is now 6, plus 1 with trail attention. It was 3.
   - The comment now says the default matches Notifications. Boards that pass the live count are unaffected.

3. **CommandPalette.dc.html: applied, including the minor extras.**
   - 'Switch company' now links to CompanySwitcher.dc.html.
   - Both payment rows now read 'KWSP'. The AI row reads 'RM 4,478.00 · due 15 Nov'.
   - The e-CP22 item is now 'e-CP22 for Daniel', tagged 'Nov 2026'. With the default "this month" scope (October) it is now filtered out; it shows under "all months".
   - 'Approval.pdf · Uploaded to Consultant fee' is now 'AF-2611-003 signed (paper scan).pdf · Uploaded to Oct 2026 Claims - Wei Ming'. Because of this, the 'wei ming' query in the results and no-hr views also finds this document row.
   - 'bank-slip-office-rental.pdf' is now 'Bank slip Office rental.pdf'.
   - 'IBG DR WEB HOSTING · EXABYTES' is now 'IBG DR WEB HOSTING · 291026', a bank reference with no company name, following PrintMonthReview's 'IBG DR 271026' style.
   - **Needs aligning:** no replacement bank text is set anywhere yet. Bank.dc.html, BankReview.dc.html ('IBG DR WEB HOSTING | EXABYTES', 'Web hosting · Exabytes') and DarkBank.dc.html still say Exabytes. Whichever group fixes those should use the same text, or this palette row needs to change to match.

4. **States.dc.html: applied.**
   - The rollover banner's 'Go to October' now links to MonthlyChecklist.dc.html. No Company.dc.html links are left in my five files.
   - Skipped: the banner text 'October is still open: 3 things left.' is unchanged. The banner names no company, and the plan's '5 things left' rule only applies to a banner that names AISB. If the owner wants States to show the AISB example, it should read 'AISB … 5 things left'.

5. **Sidebar.dc.html: applied.**
   - The kept-here links are now purchases → AccountingKeptHere.dc.html#purchases, journals → #journals and close → #close. Sales stays plain.
   - The row 13 comment is now 'e-CP22 for Daniel'. I also changed the row 12 comment to 'CP22A for Kah Seng' to follow the reminder-title decision.
   - Rule 14's 'EPF (KWSP)' comment is unchanged, as decided.
   - **Dependency:** AccountingKeptHere.dc.html has no location.hash handling yet (0 matches), so these links only land on their tab once that board reads the first-load hash. That change belongs to another group.

Checker results:
- check_board.js printed OK for Notifications, Topbar, CommandPalette, States and Sidebar.
- check_imports.js --strict: 2956 imports checked, 0 problems.

### budget (1 fixes)
Group "budget": the one fix to Budget.dc.html (verdict "partly") is APPLIED, together with all seven of the note's additions. I edited only design/canvas\Budget.dc.html.

**Data changes (applied):**
- **AISB payments now follow the register:**
  - Contractor: due and paid 2026-10-06.
  - Electricity: 1,163.20, paid 11-04.
  - 'Telephone & internet': 398.60, due and paid 10-28. It replaces 'Internet and phone' 420.
  - 'KWSP': 11,240, unpaid, due 11-15, legal.
  - 'PCB': 4,915, paid 11-14.
  - Consultant fee: 3,200, unpaid.
  - 'PERKESO': 1,086.40, paid 11-17.
  - Cloud hosting: USD 1,200, unpaid.
  - Rental received: due and paid 10-02.
  - Added: Stationery Mart 1,120 (paid 10-30) and the three claims for Wei Ming 486.50 (due 11-14), Aina 408.00 and Jia Hui 320.00 (both due 11-20), all unpaid.
  - p10 Insurance is removed, so line l8 has link null.
- **AISB lines:** l4 is 'KWSP', l6 is 'PCB', and l2's details read 'Field works, October'.
- **AISB balance:** default is '56,790.35' on 2026-10-19. The 'covered' state now uses 100,000.00, which leaves 6,076.90 over.
- **AI rebuilt from its register:**
  - Salaries — staff 21,300 (paid 10-24).
  - Farm supplies 6,750 (due 10-20, paid 10-19).
  - KWSP 4,478 (due 11-15, legal).
  - PERKESO 612.40 (paid 11-14).
  - Electricity bill 1,420 (due 11-07, unpaid).
  - Consultant — farm audit 2,500 (due 11-30).
  - Its lines m1 to m6 match these. Its default is useToday true with bal '' and date ''.
  - 'Produce export' (USD money in) is left out, as the note allows.

**Note items (all applied):**
- **(1) Balance not entered:** when useToday is on, the funds card reads "Enter the bank balance to see funds to request".
  - It has a neutral style and no figure, and the Print fund request button is hidden.
  - doFund only shows its toast when there is a shortfall.
  - Budget vs paid drops the Funds to request line. Its subtitle now reads "The same figures as the Overview card".
  - The print sheet reads "Funds to request: not worked out, bank balance not entered".
  - This also fixes AISB's 'as-at-today' state.
- **(2) Bank labels per company:**
  - The Bank balance label and balNote now come from each company's data instead of the hard-coded 'Maybank current'.
  - AI's label: "AI's only account is Maybank FCA (USD), so no RM balance is entered". AI's balNote: "AI's only account is Maybank FCA (USD)".
  - When no date is saved, balNote reads 'No balance saved yet' instead of 'as at another date'.
- **(3) Dates:** p6 is due 10-06, and p13 is due and paid 10-02.
- **(4) Covered state:** the balance is now 100,000.00.
- **(5) l9 history:** it now reads 'By hand', Aisha Rahman, 4 Nov 10:05, "Linked to PV2611-003; the paid date was typed in because the November statement is not imported yet". After: 'Electricity bill · PV2611-003 · paid 4 Nov'.
- **(6) Telephone & internet:** Budget uses 398.60. PaymentsRegister.dc.html still shows 420 on that row, and it also still has Rental received on OR2611-001 (3 Nov) and AI KWSP at 11,240. Those belong to the register group and were not touched.
- **(7) Produce export:** left out, as above.

**One extra change I made:** Budget vs paid's "Paid against the budget" now counts only line payments paid on or before the balance date. This makes it agree with samples §16 (Paid RM 24,000.00 as at 19 Oct; AI RM 28,662.40), and its footnote says so. The per-line "Paid · against budget" column and the table totals still show every line's paid status to date (RM table: paid 98,264.60, Over by RM 13.20). That is unchanged.

**Totals (checked by running renderVals in node -e):**

| View | Balance / date | Still to pay | Funds | Paid | Other |
|---|---|---|---|---|---|
| AISB stored and print | 56,790.35 on 19 Oct | 93,923.10 (14 payments) | Shortfall 37,132.75 | 24,000.00 (1 payment) | + money in 2,800.00; budgeted 115,190.00 (and USD 1,200.00); 5 payments under "Paid but not in the budget" |
| AISB covered | 100,000.00 | 93,923.10 | Covered, 6,076.90 left over | 24,000.00 | |
| AISB as-at-today | Not entered (saved balance 19 Oct) | 18,153.10 | No funds figure | 99,783.20 | |
| AI | Not entered, as at 18 Nov | 8,398.00 | "Enter the bank balance to see funds to request" | 28,662.40 | lines 37,060.40, no unlinked lines |

These agree with samples §16 and §18.

Every state is kept: covered, as-at-today, no-date, errors, print, history, history-empty, confirm-delete, not-set-up, month-empty, loading, load-error, many and ai.

**Checks:** `check_board.js Budget.dc.html` prints OK. `check_imports.js --strict` prints "2956 imports checked, 0 problems".

The $preview stays at 1440x3450 as an estimate, because I did not render the board.

### register (6 fixes)
Group "register": all six fixes are applied. check_board prints OK on all six files, and check_imports --strict reports "2956 imports checked, 0 problems". I edited only the six files named. Canvas: design/canvas

1. PaymentsRegister.dc.html: APPLIED
- **AISB October Electricity bill:**
  - Now paid 4 Nov, RM 1,163.20, linked to PV2611-003 (sql row 4 Nov 1,163.20), sub "TNB", paidNote "Entered by hand".
  - No bank line. bankNote: "The paid date is typed in because the November statement isn't imported yet."
  - The "Waiting for Nov statement" flag and est/Planned figure are removed.
  - New optional `r.sqlNote` field, shown before the Unlink sentence in the SQL box: "PV2611-003 changed in SQL from 1,163.20 to 1,136.20 (version 2). Move the link on the SQL page to follow it."
  - History: 12 Nov 16:04 SQL voucher linked (amount 1,150.00 → 1,163.20); 6 Nov 09:14 paid date entered; 6 Nov 09:12 bill uploaded. Origin: planned from Recurring, estimate RM 1,150.00.
- **Needs attention:** the counts are computed, so there was no static text to recount. With no bank line and no bank slip, the payment now reads "Paid · 1 doc missing" (Bank slip), so it counts under Needs attention. Not in SQL for AISB stays at 4 (Director fee, Telephone, PERKESO, PCB), which matches rule 7.
- **Payment names:** KWSP (EPF) / PERKESO (SOCSO & EIS) / PCB (MTD) → KWSP / PERKESO / PCB on the October, November, September and AI rows. AI's KWSP is now 4478. The Statutory (KWSP / PERKESO / LHDN) type label and AI's own Electricity flag are kept.
- **November consultant fee:** the 'print' reading now uses `a.hint` / `a.sub`, with defaults "Needs approval and is not on a form yet…" / "Not on a form yet". The row's hint says Payroll Advisory PLT's November invoice hasn't come in and a form is printed on Approvals once it has. "On To print on Approvals" is gone.
- **Links:** Open Period close → AccountingKeptHere.dc.html#close. "Print an approval form on Approvals" → Approvals.dc.html#to-print.
- **First-load hash:** the constructor now reads a hash when view is the default 'october'. It accepts #without-approval and every other view name.

2. DarkCompany.dc.html: APPLIED, identical to PaymentsRegister. The same data block, sqlNote hook, print reading, links and hash read; the dark styles and dark-href are unchanged.

3. NewPayment.dc.html: APPLIED
- **AISB underlay:** Electricity is paid 4 Nov, 1,163.20, docs Invoice / PV2611-003 / Bank slip needed, "Paid · 1 doc missing". KWSP, PERKESO and PCB are renamed.
- **AI underlay:** KWSP is 4,478. The "PV2610-001 / PV2610-002 / OR2610-001 / PV2611-001 posted here" boxes are removed, because AI has no books (as in PaymentsRegister's default AI view).
- **Type list:** now SetupTypes' live rows in its order: Salary, Director allowance, Consultant fee, Statutory, Utility / telco, Rental, Staff claim, Salary advance, Payroll run, Staff claim - overseas, Inter-company transfer, Money received, Other payment, Water bill, Insurance premium. Water bill and Insurance premium need approval by default, as SetupTypes sets every type except statutory, utility and receipt. Training fee is stopped, so it is left out.
- **Payroll run routing:** Payroll run is routed to HR, like claims and advances. It shows the error "The payroll run is made on HR › Payroll, not here." and an HR note with the link "Go to Payroll" (PayrollRun.dc.html) and the payroll glyph.
- **Topbar:** page="Payments register" sub="Add payment".

4. Payment.dc.html: APPLIED
- **'paid' sample:** RM 1,163.20, planned 1,163.20, PV2611-003, no bank line, so the "on the Nov bank statement" text is gone. It shows a new warn line in the SQL box (`sqlChOn` / `sqlChText`): "PV2611-003 changed in SQL from 1,163.20 to 1,136.20 (version 2). Move the link on the SQL import page to follow it."
- **History:** "Paid date entered" 6 Nov 09:14 with its reason; the SQL link shows amount RM 1,150.00 → RM 1,163.20; origin is estimate RM 1,150.00. Two optional hooks were added for this: `S0.sqlCh` and `S0.paidWhy`.
- **'cancelled' state:** now carries the note "State only: CN2611-001 is a made-up credit note for this reading… on no other board."
- **'kepthere' state:** the voucher, its paidCh and the Purchases note all now read AI-PV2610-001.
- **KWSP names:** no-op (the file has no KWSP strings).

5. DarkPayment.dc.html: APPLIED, the same as Payment. The new warn line uses the dark warn colour #F2B35B. KWSP names were a no-op here too.

6. ToPay.dc.html: APPLIED
- **KWSP items:** both now read "KWSP for October", note "From the recurring payment KWSP". The AI item is 4,478.00; AISB stays 11,240.00.
- **from-requests banner:** title "From Approvals' Approved tab: approved requests waiting to pay"; body otherwise unchanged ("…stay on Approvals").
- **First-load hash:** the constructor reads #from-due, #from-requests and #kept-here when view is 'list'.
- **Checked unchanged:** the due banner (2 overdue, RM 11,726.50; 4 due, RM 2,228.00 and USD 1,200.00), the requests total (RM 2,714.50) and kept-here-pay's selection of ai-kwsp all still agree.

Not changed, flagged:
- **Old voucher number in ToPay:** line ~419, in the AI paid toast example, still says "payment voucher PV2611-001", with no AI- prefix. AI-PV2611-001 is already PERKESO's voucher in the register's books view, so this should probably read AI-PV2611-002 / AI-PV2611-00n. I left it because it was not in this group's fix list.
- **#close anchor:** AccountingKeptHere needs to read the #close hash; that is assigned to another group.

$preview sizes are unchanged: PaymentsRegister and DarkCompany 1440x2460, NewPayment 1440x1700, Payment 1440x1480, ToPay 1440x1500. No new names or helper files were introduced; all edits were made in place.

### approvals-checklist (6 fixes)
Group "approvals-checklist": results for each fix. Five of the six fixes were already in the files when I started. They were modified around 23:59 to 00:06, which looks like an earlier pass of this group. I checked each one line by line against the fix and made only the one edit still missing (PrintHrLists).

1. Approvals.dc.html: APPLIED (already present, checked; no edit needed).
   - The `no-approvers` view is in the enum and opens on AIP in the To print tab.
   - It shows the PrintApprovalForm refusal wording ("AIP has no approvers yet … can’t be printed until a company has an approver").
   - The per-row Print buttons and the bulk Print button are disabled, with aria-describedby pointing at `ap-noappr`.
   - It has an "Add an approver" link to SetupApprovers.dc.html.
   - The constructor reads the first-load hash for #from-overview, #hr-requests, #paid-without and #to-print (plus #no-approvers), as PrintHrLists does.
   - The Approved tab links to ToPay.dc.html#from-requests ("Pay the approved requests on To pay").

2. MonthlyChecklist.dc.html: APPLIED (already present, checked; no edit needed). The two extra points in the fix's note are also handled.
   - November now has:
     - "Register Daniel with KWSP and PERKESO": due 10 Nov, done 10 Nov, with its acknowledgement file.
     - "e-CP22 for Daniel": due 3 Dec.
     - "Stamp the contract of Daniel": due 3 Dec.
     - "CP22A for Kah Seng": waits for December, not counted.
   - November reads 1 of 30. The comment and the item text now say November was set up 18 Nov 09:05 and the registration "came in ticked", so nothing claims "nothing ticked" any more.
   - The reminder titles use the template form in October and November.
   - There is a "Missing documents" filter (view and hash #missing-documents). It shows the items flagged docMiss: "KWSP, PERKESO and PCB paid or acknowledgement filed" and the e-Invoice item. The checklist now reads the view hashes.
   - Wording changes:
     - "Uploaded on HR › Payroll › Workbook check" and "Open the workbook check" are in place.
     - AI now reads "AI's workbook hasn't been checked yet".
     - The approvals links go to Approvals.dc.html#paid-without and PaymentsRegister.dc.html#without-approval.
     - The button reads "Print the Month review", or "Print the Month review again" once the review is on file.

3. PrintMonthReview.dc.html: APPLIED (already present, checked; no edit needed).
   - The payment lines read 'KWSP', 'PERKESO' and 'PCB' for AISB (lines 374 to 376) and for AI (453 and 454).
   - The AI KWSP line is 4,478.00. AISB stays at 11,240.00.
   - A link to PrintBankRec.dc.html ("Bank reconciliation statement") is in the related-pages list (line 518).
   - Note: PrintBankRec.dc.html does not exist yet in the canvas. The plan assigns it to another group, so this link only lands once that board is added. The strict import check still reports 0 problems.

4. Foundations.dc.html: APPLIED (already present, checked; no edit needed).
   - The print sample's approver block has a separate Signature line and a Date line.
   - The one-approver hint and the legend give "The approver’s signature approves this form." as PrintApprovalForm does.
   - The marker sample reads "Electricity bill 1,163.20".
   - $preview height: NOT MEASURED. The browser pane opens files outside the project only as static snapshots and never finished loading the board, so it could not be rendered. $preview stays at the estimate of 1440×13340. The change only adds one short Date line to the sample.

5. AuditPackHR.dc.html: APPLIED (already present, checked; no edit needed).
   - Approved now lists CL-2610-005 (Aina, 408.00) and CL-2610-007 (Jia Hui, 320.00) under AF-2611-003: Tan Mei Ling, 12 Nov, uploaded 13 Nov, not paid yet.
   - That gives Approved: 8, or Approved: 9 in none-open. This agrees with "Rajesh Kumar 2 · Tan Mei Ling 4 · Hassan Ismail 2: 8 approvals" and with the none-open "3 · 5 · 2: 10 approvals".
   - The none-open state cites the sheet reprinted on 18 Nov 2026: check F4H-9KXT, none open, Rajesh Kumar 3, Tan Mei Ling 5, Hassan Ismail 2.
   - The payment lines read "KWSP: 11,240.00", "PERKESO: 1,086.40" and "PCB: 4,915.00". The payslip deduction label keeps "EPF (KWSP)".

6. PrintHrLists.dc.html: APPLIED (edited this run).
   - Line 325, Coming up: the title changed from "CP22A for Kah Seng (retiring 31 Dec)" to "CP22A for Kah Seng".
   - The retiring date moved to the reminder column: "Leaver task (retiring 31 Dec); starts the tax-clearance hold". The date column still reads Tue 1 Dec 2026.

Other checks:
- Across the six files, none of these strings remain: "KWSP (EPF)", "PERKESO (SOCSO", "PCB (MTD)", "LHDN (PCB)", "joiner starting", "Robin Advisory", "Company.dc.html", "0 of 28", "1 of 28", or the Foundations "1,150.00".
- "Month review sheet" is left in PrintMonthReview's own title, page subtitle and descriptions. Foundations' section headings still say "Payroll check tones" and "the Payroll check". Neither is a target of this group's fixes, so I did not edit them.

Checkers (last lines):
- `node check_board.js` printed OK for each of Approvals, MonthlyChecklist, PrintMonthReview, Foundations, AuditPackHR and PrintHrLists.
- `node check_imports.js design/canvas --strict`: "2958 imports checked, 0 problems".

File changed this run: design/canvas\PrintHrLists.dc.html

### books (6 fixes)
Group "books": all 6 fixes are applied, 5 in full and 1 mostly. Every file I touched prints OK with check_board. The strict import check reports "2956 imports checked, 0 problems". Sql.dc.html also prints two warnings from the reports-only view ("keepLines(Escape) / undo(Escape) threw when called out of context"). Its pre-package copy in design-v74 gives the same two, so they were already there. I edited no other files.

Folder: design/canvas

1. **Books.dc.html: applied.**
   - "differ" now reads TB 18/11/2026 at 10:58 and journal at 10:42.
   - "stale" now reads TB at 10:58 and journal at 11:05.
   - "Opening balances in Journals" now links to AccountingKeptHere.dc.html#journals.
   - **Depends on another group:** AccountingKeptHere has no hash reading yet. The link only lands on Journals once that board's #journals change goes in.

2. **SqlBooks.dc.html: applied (the note's "partly").**
   - The read times were already right (10:58:41 for differs; the stale journal at 11:05:20), so I left them.
   - The PV2610-005 payment name 'KWSP (EPF)' is now 'KWSP'.
   - The button "Open AI's Overview" now reads "Open the Overview".
   - The line-548 comment is unchanged.

3. **AuditPackBooks.dc.html: applied, with one extra row.**
   - "differs": TB 18/11/2026 at 10:58, journal 18/11/2026 at 10:42. The 17/11 09:10 read is gone.
   - "stale": TB 18/11/2026 at 10:58, journal 18/11/2026 at 11:05 (it was 12/11 16:04 and 10:42).
   - The old D1/D2 lines (900-400 and 400-000, the 27.00 electricity story) are replaced with the JV2610-012 story.
   - **Beyond the plan:** "differs" now has three lines, not two:
     - 310-000 balance: SQL 33,570.35, here 33,618.35, difference 48.00.
     - 310-000 movements 01/10 to 31/10: SQL -55,648.00, here -55,600.00, difference 48.00.
     - 900-010 lines: SQL 58.00, here 10.00, difference -48.00.

     I added the movements line because hrp/books.py and the Books board both print one when the From dates match, and the -55,648.00 / -55,600.00 figures come from stage 1 §21. The count line "2 accounts differ… 29 agree" is unchanged.
   - "stale" now has its own lines S1–S3 with the sides flipped, matching how Books models stale (the books here hold JV2610-012; SQL's TB does not).
   - The explanation boxes for "differs" and "stale" now tell the 48.00 / JV2610-012 story. "Sample figures; not in the shared data set" now reads "A state-only variant of the shared sample data".

4. **Sql.dc.html: applied.**
   - PAYS p5 'Insurance premium 2,310.00' is removed; nothing else in the file used it.
   - p3 'Water bill' 80.00 is now 84.30.
   - The PV2610-005 payment name 'KWSP (EPF)' is now 'KWSP'.
   - "Open AI's Overview" now reads "Open the Overview".
   - Not changed: the line-76 design note, which describes the top bar's toast, and the line-1038 comment.
   - **Depends on another group:** BankReview's 'aIns' candidate is not my file and still has to be removed.

5. **InvoicePdf.dc.html: applied, with the note's extra date.**
   - The invented IV2611-014 is dated 18 Nov. Its note now reads "after the journal kept ends (17 Nov)".
   - All three "covering 20/11/2026" are now 18/11/2026.
   - The date-mismatch reason now reads "dated 17/11/2026, not this invoice's date (18/11/2026)"; it said 19/11 and 20/11.
   - No future dates are left in the file.

6. **BooksStatutory.dc.html: applied except one detail.**
   - Tracker names: 'KWSP (EPF), September' and both 'KWSP (EPF), October' now read 'KWSP, …'. Both 'PERKESO (SOCSO & EIS), October' now read 'PERKESO, October', following the plan's PERKESO rule. 'PCB (MTD), October' now reads 'PCB, October'.
   - The kind labels (EPF (KWSP) and the others) stay.
   - The "one of the two names should go" note is dropped.
   - 'net' is removed from the suggestions, so "Use these accounts" now adds 4.
   - The use-one state now adds EPF (KWSP). Its toast reads "EPF (KWSP) added" / "430-100 KWSP payable is now checked as EPF (KWSP), due by the 15th." and Undo covers ['epf'].
   - Because Net salaries payable is already confirmed, the not-configured banner title is now "Not all checked yet". With nothing added yet, its text reads "Only Net salaries payable (420-000 Accruals) is confirmed for this company so far, so the other statutory payables are not checked yet."
   - Wording changes that follow from dropping 'net':
     - The suggestions note now says suggestions come from the chart of accounts by their names only.
     - The hidden table caption no longer mentions the payroll journal.
     - The line-779 design note now says Net salaries payable isn't suggested because 420-000 was confirmed on 13 Nov 2026.
     - The code comment above the suggestions list now says the same.
   - The line-762 note is kept; it is only about the drawn check, not the suggestions.
   - **Skipped:** the trailing period on the toast title. The title already reads "4 statutory accounts added", and toast titles are written without one. The screen-reader announcement adds the period, so it says "4 statutory accounts added."

KWSP decision as used here: payment and tracker names read 'KWSP', 'PERKESO' and 'PCB', as the app's rules.py and the tests name them. The kind words 'EPF (KWSP)', 'SOCSO (PERKESO)', 'EIS (SIP)' and 'PCB (LHDN)' stay on BooksStatutory and on the AuditPackBooks statutory page.

### bankrec (5 fixes)
## Group "bankrec": report

All five fixes are in. The checkers are clean: `check_board.js` prints OK for Bank, DarkBank, BankReview, ApprovalUpload and PrintBankRec, and `check_imports.js --strict` reports "2969 imports checked, 0 problems". The project is at `design/canvas`.

### Per fix

**1. Bank.dc.html: applied**
- An earlier run of this group had already made every edit; I checked it and it holds.
- "Consultant fee — Payroll Advisory PLT" replaces Robin Advisory.
- The bank line now reads "IBG DR WEB HOSTING · 291026".
- A "Print the reconciliation statement" action sits under each month's Reconciliation statement heading. It opens `PrintBankRec.dc.html#current`, `#savings` or `#fca`, following the account. For months other than October 2026 the aria-label says it opens the October 2026 example.
- "Discard your changes?" was already the dialog text, so that part needed no change.
- CommandPalette's EXABYTES is gone too: no board in the canvas has Exabytes any more, so the flag to that group is no longer needed.

**2. DarkBank.dc.html: applied**
- Same edits as Bank, already in place and checked.

**3. BankReview.dc.html: applied, partly in a different way than the note asked (decision below)**
- `aRobin` is now "Consultant fee — Payroll Advisory PLT". Its internal id is renamed to `aConsult`, and its suggestion reads "name close: Payroll Advisory PLT".
- `aKwsp` is now "KWSP · September".
- The `aIns` payment is removed.
- Line 12 now reads "IBG DR WEB HOSTING | 291026". The `st.desc` override that the fix missed is changed too: "Web hosting · Exabytes" becomes "Web hosting".
- **Decision on the sample pair:** I used the existing CB2610-041 / CB2610-044 pair (48.00, both on 310-000, 31 Oct). I did not invent a self-billed OR/PV pair, for three reasons:
  - The pair is already in stage 1 §21.
  - stage 1 says the book totals (47,848.00 / 103,448.00) already include it, so it is a real "book entry where no money moved" in the data.
  - The scope also covers "a contra or reversal".
- The pair is book-side only, so the 5 lines to explain and the 695.80 difference are unchanged. The pair's description text still names the duplicated self-billed e-Invoice case as an example.
- **New "No money moved" group:** it sits between the matched lines and the bottom bar. It shows:
  - each pair with its documents table, and a "Net nil" or "Net RM x, not nil" pill;
  - an editable reason, filled in from the documents. Ticking with an empty reason is refused, with an error tied to the field;
  - a "Confirmed: no money moved" tick. It is off while the pair isn't nil or the month is locked, and the toast offers Undo;
  - for Kept in SQL Account, what to do in SQL.
- **Sign-off:**
  - It is refused with "1 pair under No money moved to confirm" or "…isn't nil (RM 3.00 left)".
  - A new optional "Note for the sign-off" field sits before signing.
  - Once signed, the app-written note shows: pairs with reason and amounts, lines explained without documents, and reconciling items. The free note shows beside it.
  - Undo sign-off stays (toast Undo and Reopen month). The signed savings and AI states now show their notes too.
- **New states:**
  - `pair-confirmed`: real data, pair ticked, toast with Undo.
  - `pair-not-nil`: what-if, CB2610-044 keyed as 45.00. Book closing becomes 33,615.35 and the difference 698.80.
  - `pair-ready`: what-if, every line explained and SQL agreeing at 34,314.15. Only the pair is left.
  - `pair-signed`: what-if, signed 18 Nov. The free note reads "The 8 Oct service charge is booked in SQL by JV2610-012."
  - The what-ifs say so in the board-sample strip.
- `$preview` height goes from 1800 to 2200 (an estimate; the boards couldn't be rendered here).

**4. ApprovalUpload.dc.html: applied**
- **Code scheme:** BR-yymm-company-last 4 digits of the account. The sample is BR-2610-AISB-0932 (Maybank savings, signed off 3 Nov), check H6P-4QZC, Reviewed by any AISB approver.
- **New states:**
  - `bank-rec`: code read from the QR, statement matches, Tan Mei Ling chosen, dated 18 Nov.
  - `bank-rec-matched`: on file, toast with Undo, link to Bank and reconciliation.
  - `bank-rec-changed`: the month was reopened after printing, with the same reason as Bank's reopen states. Nothing is kept, and the action reads "Print the statement again" (PrintBankRec#savings).
  - All three are labelled what-if ("as if printed today at 10:20").
- A statement matches whole or not at all.
- **Text updated:**
  - the lead paragraph and the drop zone;
  - the first table header ("Figure");
  - the who-signed legend ("…signed as Reviewed by?") and its note;
  - the date heading;
  - the match texts and the no-match title;
  - the reprint link, the foot note, the done text, marker and link;
  - the discard text, the thumbnail (Prepared by / Reviewed by blocks) and the undo text.
- The view enum and the forms table have the new entries.

**5. PrintBankRec.dc.html: applied (new board)**
- Imports Sidebar (active bank) and Topbar (Accounting › Bank and reconciliation › Reconciliation statement) with company, kind and on-company. It reads `#current`, `#savings` or `#fca` on first load.
- **Two A4 pages:**
  - Page 1: header with code, check and QR; the standard layout (balance per statement, add, less, add or less, adjusted bank balance against balance per books); No money moved; totals check.
  - Page 2: SQL GL check, sign-off note, then Prepared by and Reviewed by with separate Signature and Date lines.
- **States** (default changed as the note suggested):
  - `savings` (default): signed off 3 Nov, nil difference, note printed. No SQL check, because only Maybank current is SQL's cash book (310-000) in Bank's data; the board says so.
  - `current`: not signed off. 34,314.15 less PV2610-022 1,120.00 and PV2609-020 3,200.00 brought forward, plus the 6 bank-only lines net 3,624.20, gives 33,618.35, equal to books. The CB pair shows as not confirmed. Totals 47,848.00 / 103,448.00 less 48 / 48 tally to 47,962.80 / 106,067.00. Agrees with SQL 310-000.
  - `fca`: AI Maybank FCA, USD, Kept here, 12,480.00 to 17,480.00, not signed off, no SQL check, Reviewed by Hassan Ismail.
- **canvas.json:**
  - registered at x 7600, y 70370, 1440 × 3300 (estimate), with an `order` entry after PrintMonthReview;
  - BankReview h set to 2200;
  - the "Printed" note `nPr` moved from x 7600 to 9120 (my board would have covered it), with the bank reconciliation statement added to its text and `tPr` maxW raised to 9640.

### Not done, or for others
- **samples.md not edited** (the task said touch no other file). Lines to add:
  - BR code scheme and checks: BR-2610-AISB-0932 / H6P-4QZC, BR-2610-AISB-4417 / W3K-8TNB, BR-2610-AI-1186 / D9R-2LXF;
  - No money moved example = CB2610-041 / CB2610-044, with the reason text;
  - what-ifs: reversal keyed as 45.00; the BR upload by Tan Mei Ling on 18 Nov;
  - Prepared by = whoever signs off in the app (Aisha Rahman, savings, 3 Nov).
- **Other groups' boards:**
  - Approvals doesn't list bank reconciliation statements (Waiting for upload, Upload signed statement).
  - AuditPack doesn't show the signed statement and its note.
- **Product question for the owner:** the scope says a month can be signed off with reconciling items left, but Bank and BankReview keep the app's rule that sign-off needs book closing = bank closing. So `pair-signed` uses a what-if where SQL agrees with the bank.
- `$preview` heights are estimates. The browser pane only shows local files as static snapshots, so the boards couldn't be measured.


### recurring-trail (6 fixes)
Group "recurring-trail" is done. I applied all six fixes, five of them in full. In AuditTrail I made one numbering choice that leaves one cross-board item (see AuditTrail (a)). Checkers: check_board.js prints OK on all six files. `check_imports.js design/canvas --strict` reports "2969 imports checked, 0 problems". I did not edit samples.md or any other file.

Files (all in design/canvas):
Recurring.dc.html, AuditTrail.dc.html, AuditPack.dc.html, Backup.dc.html, SetupCompanies.dc.html, SetupMove.dc.html

## Recurring.dc.html (partly): applied, with the note's three additions
- **Types** now use the SetupTypes labels in the data, filter chips, select, eyebrow and every logic list:
  - Salary, Director allowance, Statutory (KWSP / PERKESO / LHDN), Utility / telco, Consultant fee, Money received.
  - Office rental is Rental.
  - Cloud hosting, Cleaning service and Security guard are Other payment.
  - A new row and the Money out switch default to Other payment. Needs-approval follows samples D4.12.
- **Payment names:**
  - KWSP, PERKESO and PCB on both companies' rows.
  - The switch-over banner reads "KWSP, PERKESO and PCB".
  - The Saved result now reads "September: KWSP, due 15 October (already due…)". It used to say "month filed", but AISB's September is still open.
- **AI KWSP** is 4478.
- **KWSP history:** "11 Nov 2026, 14:20 · 11,180.00 → 11,240.00 · October’s contributions from the payroll summary".
- **Consultant fee:**
  - Party "Payroll Advisory PLT", start 2026-09-01, In Oct, 2 payments, so it can no longer be deleted.
  - Its history step is Added 28 Aug 2026.
  - Approval is `{ k: 'wait', per: true, form: 'AF-2611-004' }`. The panel says "Approved per payment… The latest, AF-2611-004 for October (RM 3,200.00), is waiting", with the link "Open form AF-2611-004 on Approvals". "Not employed in Oct" is gone.
- **Office rental** bank is "CIMB 8006447122 (Menara Holdings)".
- **Parties:** Water bill is 400-W001 and Cleaning service is 400-C003. The supplier picker list was updated to match, including Payroll Advisory PLT.
- **Side effects of these fixes:**
  - The "delete" state now uses Cloud hosting (sel 13, canDelete, nothing uses it), because the consultant is now in use. Its note now reads "Its first payment is due Wed 25 Nov" instead of "waits in To pay".
  - Entry numbers now follow the trail's numbering: Water bill deleted 4748, Security guard 4388, Electricity put back from entry 4596, and a new delete is 4831 (was 1185, 1020, 1050, 1232).
  - The baseline "As it stood" date is now 6 Jan 2025, 08:02, like the Setup boards' seed. It was 1 Oct 2026, which came after the 12 Sep deletion.

## AuditTrail.dc.html (partly): applied
- **4741:** now a Changed entry on "Bank account Maybank savings, 5141 2300 0932 (AISB)", field Name "Savings account" → "Maybank savings".
- **4786:** record "Recurring payment · KWSP (AISB)", field Usual amount 11,180.00 → 11,240.00, with the samples reason.
- **4719** reads "Recurring payment · Office rental (AISB)".
- **Deleted and put-back records:**
  - The Seri Stationery entries (4760 and 4815) and Klang Courier (4806) are gone.
  - Added 4748: Water bill removed 3 Nov 14:20. It can be put back "with the same number".
  - Added under Show older:
    - 4388: Security guard removed 12 Sep 11:02. Put back is refused because the USD collections account is stopped. This replaces the old petty refused flow.
    - 4596 / 4601: Electricity bill removed 8 Oct 17:30, then put back 9 Oct 09:12. These keep the "Put back in entry" example.
- **Outside-change samples** that used "Payee" now use "Recurring payment" (the app's label for payees): Office rental bank details and the Cleaning service payee name.
- **4777 replaced:** Donation is removed in a new entry 4612 on 12 Oct 15:40 (SetupTypes' date, why "Donations go under Other payment", no AISB tag), and it can be put back.
- **The put-back flow** now uses the record's own label and says "with the same number" when no new number is given.
- **New entries:** 4827 is AISB November 2026 set up at 09:05, under a new "Months" record filter option. 4828 is the AISB logo uploaded at 09:15. The payroll check is renumbered to 4829 and its read to 4830, and LAST is 4830. No other board refers to 4827 or 4828.
- **(a), left for another file:** SetupTypes says Donation was deleted "in entry 1121". The number 1121 can't sit between 4388 (12 Sep) and 4719 (27 Oct), so the trail uses 4612. SetupTypes' entry 1121 should read 4612; that is a setup-types edit.
- **Wider numbering problem (unchanged):** the Setup boards use 1xxx entry numbers that also contradict the trail's 4xxx numbers and each other. Examples: SetupCompanies 1061 on 2 Sep and 1231, Setup 1184 on 3 Nov, SetupTypes 1121 on 12 Oct against Setup 1102 on 14 Oct.

## AuditPack.dc.html (confirmed): applied
- **AISB:** the 2 missing-document items, plus 7 not done with MonthlyChecklist's titles: Bank reconciliation balanced and filed; Approvals on file for every payment; Customer balances older than 30 days followed up; Month reviewed; Fixed asset register updated; Insurance and licence renewals checked; Audit pack built since the last document was added. The summary reads "7 checklist items not done" (8 when SQL books are open).
- **AI:** MonthlyChecklist AI's 7 open items with its titles. "KWSP and PERKESO paid or acknowledgement filed" has no missing-document flag on AI's checklist, so it is listed as not done. The others are Bank reconciliation; Export receipts matched to invoices; Supplier statements checked against the books; Month reviewed; Insurance and licence renewals checked; Audit pack built since the last document was added. The summary reads "7 checklist items not done" with no missing-documents pill.
- **Names:** "KWSP for October", "PERKESO", "PCB". The statutory rows keep EPF (KWSP) and PCB (LHDN), and the 4 rows / 74 changes are unchanged.
- **Electricity bill** detail now reads "Paid 4 Nov (date typed in): not on a statement until November is imported", from the plan's decision. I did this beyond the fix text.
- **$preview** height 1760 → 1910. This is an estimate, not measured.

## Backup.dc.html (confirmed): applied
- The 16 Oct backup now reads "After AI’s September 2026 was filed (5 Oct)".
- Documents are 74 → 450 in the check label and in both results. 450 = 214 + 140 + 96 from SetupCompanies.
- The logo upload at 18 Nov 09:15 already existed.

## SetupCompanies.dc.html (confirmed): applied
- **Counts:**
  - AISB: recurring 11, checklist items 90.
  - AI: recurring 4, months set up 2, checklist items 42.
- **History:** the AISB logo change (18 Nov 2026, 09:15, Logo — → aisb-logo.png) is added at the top.
- **Undo:** every confirming toast now offers a working Undo: added, Saved, deleted, put back, In use again, "Removed 3 payments and 8 checklist items", logo or signature uploaded or taken off, printed name removed. It is the SetupTypes pattern (`toast(text, extra, undoFn)`). The state-only views (saved, tidied, print-no-logo, print-ready, names-removed, put-back-done) get an undo through a new `viewUndo`. Stopped keeps `undoStop`.

## SetupMove.dc.html (confirmed): applied
- **File counts:**
  - Payment types 15 and document types 18 (SetupTypes, live only).
  - Starter checklist 7 (SetupChecklist's sample starter).
  - Reminders 7 (SetupChecklist, the deleted wpass not counted).
  - Payment type guesses 5, salary words 2, SQL filing words 4 (SetupMatching, in use).
  - Bank accounts 5, customers and suppliers 9, recurring 15.
- **This install holds:** 5 bank accounts, 15 recurring payments, 9 customers and suppliers, 12 months set up, 201 payments, 450 documents. The last three are SetupCompanies' Used by sums over AISB, AI and OLD.
- **Leftover:** the text still says "2 companies", and 5 bank accounts leaves out OLD's 1, but the month, payment and document totals include the stopped OLD company. If those should cover only the two companies in use, they would be 6, 160 and 354. "Checklist items 48" was left unchanged.

## Other things for the plan
- Recurring's AISB Electricity row still shows "Add to Oct" (`month: 'add'`). That disagrees with the decision that October's Electricity was paid 4 Nov. I left it because it is the board's only "Add to" example.
- Setup.dc.html and SetupCompanies use Maybank savings 5141 2300 0932, but Bank, DarkBank and BankReview use 5141 2345 0932.
- Setup.dc.html's Maybank savings history has only "As it stood". It needs the 2 Nov name change that trail entry 4741 now records.
- SetupParties still has short_name 'Robin Advisory' for 400-P004. That file belongs to another group.

### setup-types (6 fixes)
Group "setup-types": all 6 fixes applied. Files are in design/canvas. No other file was touched.

**1. SetupTypes.dc.html: applied.** An earlier interrupted run had already made these edits. I checked them against samples and they are correct, so nothing new was needed.
- Approval forms per type:
  - Staff claim: 2 (AF-2611-003, AF-2611-005)
  - Consultant fee: 2 (AF-2611-004, AF-2611-006)
  - Salary: 2 (AF-2610-001, AF-2610-002)
  - Director allowance: 1 (AF-2610-001)
  - Rental: 1 (AF-2611-002)
  - Other payment: 3 (AF-2610-003, AF-2610-004, AF-2611-002)
  - Salary advance: 2
  - Payroll run: none yet (AF-2610-009 exists only on the step 2 boards)
- Payroll check workbooks: 3.
- Recurring counts come from Recurring's 15 rows after renaming: Salary 2, Director allowance 1, Statutory 5, Rental 1, Other payment 2 (Cloud hosting, Cleaning), Utility / telco 2, Consultant fee 1, Money received 1.
  - Water bill shows 0 recurring on purpose: Recurring's Water bill row is deleted and its type is Utility.
- Paths now read "HR › Payroll › Workbook check" and "HR › Claims and advances".

**2. SetupRequired.dc.html: applied** (also by the earlier run, verified). The types and docs tabs draw exactly SetupTypes' rows:
- the 16 payment types and 19 document types, with the same names, keys, Used by, stopped and deleted rows;
- Used by figures are summed and their titles say what they count;
- the September refusal uses AI.

**3. SetupMatching.dc.html: applied.**
- **Type names:** rule targets now use SetupTypes' names (Statutory (KWSP / PERKESO / LHDN), Director allowance, Utility / telco, Consultant fee). The type list is SetupTypes' money-out types in use, matching the app's `_word_check`. The default target is Utility / telco, and "added as Other" now reads "Other payment".
- **Transport rule:** the deleted rule now targets Other payment. Its old reason (Travel deleted) became false, and no real app refusal fits, so it can now be put back (`can: true`). The refused put-back example still shows on the SQL documents tab (dl4).
- **Party list:** the options are SetupParties' 8 in-use parties. The stopped 400-C003 is left out, and 400-W001 is not added because it is not in SetupParties. AGRI-001, TAN-014, SUP-022 and "Agrinexus Sdn Bhd" are gone.
- **Rule f1:** now "Tenant invoices", party 300-T001.
- **Undo:** a new `undoTo()` gives Undo on the Saved, added, deleted, put back and "in use again" toasts.

**4. SetupGeneral.dc.html: applied.**
- The recurring-type options are the app's money-out types, as keys with SetupTypes labels; the default is `utility`.
- The day refusal now names AI's filed September: "the checklist item Update MBB bank records of AI, due 8 Oct 2026, would move from September 2026 to October 2026". A comment notes that the app's refusal really names SQL documents and joiner or leaver reminders, and AI has none near the day.
- The links now read "Change it on SQL import" and "Open SQL import".

**5. SetupChecklist.dc.html: applied.**
- **AISB:** the 27 in-use items are MonthlyChecklist's, with the same titles, due days and order (Payroll approved on the 24th, approvals on the 20th, Month reviewed on the 30th). The stopped OLDRPT and the deleted COUR and OVSEAS are kept but hidden.
- **AI:** shows its own 22 items by default (`aiMode` `own`).
  - Starter and empty stay as what-if states; the starter is now 6 items, without PV.
  - Copy now copies AISB's 25 non-SQL items, and its preview, toast and the "(N items)" option are computed.
- **First month:** a change can start from September 2026 for AISB items and from October 2026 for AI items and reminders. The refusal reads "AI's September 2026 is filed, and filed months never change. Choose October 2026 or later." The month inputs' `min` follows this, and a preview counts AISB's 3 open months or AI's 1.
- **History and By month lines:**
  - Items are in force from Sep 2026 (Oct 2026 for the two new items), with an earlier term of Jan to Aug 2026.
  - A stopped item shows "Stopped" from its month.
  - The history lines match.
- **Used by:** 3 for items, 2 for the new items; AI items 2 and 1; OLDRPT 0. Reminders: e-CP22 2, Register 2, Stamp 2 (Jia Hui and Daniel).
- **Labels:** TYPES and DOCS use SetupTypes labels, and the REMS documents were updated.
- **Overseas item:** OVSEAS's "type deleted since" problem was false, so it is removed.
- **Notes and paths:**
  - The Month review note now says it is printed from Payments › Approvals or the Monthly checklist.
  - The other notes now read "HR › Payroll › Workbook check", "HR › Payroll › Run" and "HR › Staff › Calendar and reminders".
- **Views:**
  - The delete view now uses OLDRPT, because LEAVE is used in 3 months and can no longer be deleted.
  - The saving and refused views use day 25.
  - The discard view appends " by a director".
- **Preview height:** `$preview` is now 1440×2900, an estimate (not measured), because the list grew from 11 to 27 rows.
- Templates are unchanged.

**6. FirstRun.dc.html: applied.**
- "Discard changes?" now reads "Discard your changes?".
- The setup-2026-11-14.json counts are taken from the Setup boards as they stood on 14 Nov. The app's export (hrp/setupfile.py) includes stopped rows and leaves out deleted ones:

| Count | Value | Rows behind it |
|---|---|---|
| Companies | 4 | AISB, AI, and the stopped OLD and TEST |
| Bank accounts | 5 | Maybank current, Maybank savings, the stopped USD collections, Public Bank current (added 9 Nov), Maybank FCA |
| Payment types | 15 | SetupTypes' 16, less Insurance premium (added 16 Nov) |
| Document types | 18 | SetupTypes' 19, less Tax form (added 17 Nov) |
| Checklist items | 50 | AISB 28 (27 in use plus the stopped OLDRPT) and AI 22 |

- The imported message now reads "AISB and AI and their setup are ready, with the 2 stopped companies kept as stopped."

**Needs another group (not edited):**
- **SetupMove.dc.html** shows 13 payment types, 16 document types, 4 bank accounts, 2 companies and 48 checklist items on 18 Nov. By the same export rule it should read 16, 19, 5, 4 and 50, so FirstRun and SetupMove now differ by exactly the 14–18 Nov changes plus that correction.
- **SetupTypes' "checklist items" and "checklist rules" counts** were not recounted, because they were outside this fix. With AI's own 22 items, Bank statement, Bank reconciliation, Payroll summary and Month review are each used by 2 checklist items, not 1. Statutory's "checklist rules" is now 2, not 3 (AISB's and AI's statutory items).
- **Recurring.dc.html** still uses the old type names (Bill, Director, Money in, and so on); its renaming belongs to another group.

**Checkers:** check_board printed OK on all 6 files. SetupChecklist still shows one warning that was already there before this change (o.toggle called with no dialog open). check_imports --strict: 2969 imports checked, 0 problems.

### setup-masters (6 fixes)
All 6 fixes in the setup-masters group are applied. One extra suggestion in a reviewer note was not followed, because the app works differently (see the SetupParties item). The checkers are clean. When this run started, Setup.dc.html and SetupChart.dc.html already held their fixes from an interrupted earlier run. I checked those edits against the fixes, the samples and Recurring, and found nothing to change.

Files are in design/canvas\

1. **Setup.dc.html: applied** (by the earlier run; checked).
   - Maybank current shows "recurring payments 11" (Recurring's 11 AISB rows, none on another account). The delete refusal text follows from the same list. Maybank FCA (AI) shows 4.
   - The other AISB accounts show no recurring payments.
   - The added, Saved, deleted, put back and In use again toasts offer Undo. The "saved" state now shows the saved change, and its Undo restores the account. The "put-back-done" state also offers Undo.

2. **SetupChart.dc.html: applied** (by the earlier run; checked).
   - The parties tab mirrors SetupParties: 9 AISB rows plus AI's Plantation supplies, with the same used lists. Payroll advisor's short name is Payroll Advisory PLT.
   - Deleted rows are now Sri Cahaya Printing (can be put back) and Old tenant (300-T001, refused). Old courier, Pacific Courier, Old landlord and 400-C002 are gone.
   - 420-000 Accruals is used by "1 statutory account (Net salaries payable)" and "1 SQL account line (JV2610-007)", so Delete is not offered.

3. **SetupParties.dc.html: applied.**
   - 400-P004 keeps the name "Payroll advisor" with the short name "Payroll Advisory PLT" (was Robin Advisory).
   - Used-by lists now match Recurring:

     | Party | Recurring payments | Other uses |
     |---|---|---|
     | Payroll advisor | 1 | 10 SQL entries |
     | KWSP | 1 (was 3) | 22 SQL entries, 1 filing rule |
     | Tenant 300-T001 | 1 (Rental received) | 5 SQL entries |
     | Old cleaning contractor 400-C003 | 1 | 8 SQL entries |
     | Plantation supplies (AI) | none | none, so it is no longer locked and shows "Not used yet" |

   - **Not followed:** the note's extra idea of separate used lists per company for the every-company rows. In hrp/masters.py, the used-by count for parties is `SELECT COUNT(*) FROM payees WHERE party_id = ?`, which counts every company. So a shared record shows the same counts in AISB and AI, as the app does. KWSP is 1, not the note's 2, because AI's KWSP recurring row has no party set (Recurring offers no parties for AI).
   - Added, Saved, deleted, put back, In use again and pasted-list toasts offer Undo. The "saved" and "pasted" states do too.

4. **SetupStatutory.dc.html: applied.**
   - Net salaries payable (420-000) has its own history entry: Added 13 Nov 2026, 10:05. That is before entry 1204 (13 Nov 11:24/11:30) and the 14 Nov audit pack.
   - The four statutory accounts keep Added 18 Nov 2026, 10:50.
   - The source comment now gives the 13 Nov confirmation.
   - All toasts offer Undo, as on the other boards, including the "saved" and "put-back-done" states.

5. **SetupApprovers.dc.html: applied.**
   - AIP now has no approvers. Tan Mei Ling (id 31) and the AIP-only approver note are removed.
   - The "none-yet" state opens on AIP in the four-company list. It reads "No approvers yet for AIP" and the shell shows four companies.
   - Other states are unchanged. With the four-company tweak, AIP shows the same empty state.

6. **SetupHolidays.dc.html: applied.**
   - Added the "many" state, following the Recurring and States pattern. The panel scrolls (max 560px), the header row stays at the top, and the scroll area can take focus.
   - A bar reads "Showing 25 of 40 public holidays in 2026", with a "Show 25 more" button that becomes "All 40 shown", and a note that 40 is a stress-case count.
   - Arrow-key row navigation follows the drawn rows. `$preview` is unchanged.

**Checks:** check_board.js prints OK for all 6 files. `check_imports.js --strict` reports "2958 imports checked, 0 problems". I also loaded each board's script with a stub and drew every State option (and each companies option) with no errors, and tried the new Undo paths, AIP none-yet and Holidays many.

**For another group:** Recurring.dc.html still uses 400-C002 for the cleaning service and 400-W004 for the water bill. The samples say 400-C003 and 400-W001.

### hr-staff (6 fixes)
Group "hr-staff": all 6 fixes are applied. The checkers are clean. Each of the 6 files gives "OK" from check_board.js, and `check_imports.js --strict` reports "2956 imports checked, 0 problems". I edited only the six files below, in design/canvas. samples.md already had the plan's wording, so I did not touch it.

**1. HrCalendar.dc.html: applied**
- **Reminder titles:**
  - The row and task titles now read "e-CP22 for Daniel" and "CP22A for Kah Seng".
  - Each of those rows gained a detail line that quotes its title: "On Next up as “e-CP22 for Daniel”." and "On Next up as “CP22A for Kah Seng”."
- **Daniel's tasks:** "Register Daniel with KWSP and PERKESO" now says "On the November checklist" and stays Done. e-CP22 and "Stamp the contract of Daniel" stay on the November checklist.
- **Carried state:** it now uses "Stamp the contract of Daniel" as the example. The story is that November 2026 is filed with the stamp task still open, so the task moves to the December checklist.
  - Pill: "1 task carried on from November 2026".
  - Task line: "On the December checklist, carried on from November 2026".
  - The note text is rewritten to match.
- **Hash on first load:** the default list state now reads `#coming-up` and every other view name, using the same pattern as PrintHrLists.
- **Wording:**
  - "Discard changes?" is now "Discard your changes?" (the label and the code comment).
  - The comment at the old line 526 now says "Setup › Joiner and leaver reminders".
- **Extra fix, not in the list:** the header line "Most urgent reminders also show on the Overview's Next up, without names." became false once reminder titles carry names. It now reads "...Next up: joiner and leaver tasks by their title, probation and permit dates with no name."

**2. HrStaffRecord.dc.html: applied**
- **S009 history** now reads: "Joined. Joiner tasks: Register Daniel with KWSP and PERKESO by Tue 10 Nov, e-CP22 for Daniel and Stamp the contract of Daniel by Thu 3 Dec (November checklist)."
- **Probation banner** now reads: "Register Daniel with KWSP and PERKESO: done on the November checklist. Also on the November checklist: e-CP22 for Daniel and Stamp the contract of Daniel, by Thu 3 Dec 2026."
- **Calendar tab titles** are now the template form: "CP22A for Kah Seng" and "e-CP22 for Daniel". The bracketed details ("retiring 31 Dec", "joined 3 Nov") moved into the reminder note line.
- **Hash on first load (details view only):**
  - It reads a person id, `#S0nn` or `#A0nn`, plus an optional tab, joined by `-` or `/`. Examples: `#S009`, `#S002-claims`, `#S007-pay`.
  - It also accepts the tab names calendar, documents, history and advances.
  - Unknown ids are ignored and the default person (S006) stays.
  - Links from other boards should use this form, for example `HrStaffRecord.dc.html#S002-claims`.
- **Wording:** "Setup › HR › Leave" is now "Setup › HR › Leave types and policy", and "Discard changes?" is now "Discard your changes?".

**3. HrStaffForm.dc.html: applied**
- "Setup › Checklist" is now "Setup › Joiner and leaver reminders" (the field hint and the comment).
- "Setup › HR › Leave types." is now "Setup › HR › Leave types and policy."
- "Discard changes?" is now "Discard your changes?".
- The e-CP22 title was already right and is unchanged.

**4. HrStaff.dc.html: applied**
- Each row now links to `HrStaffRecord.dc.html#<staff no>` through a new `recHref` field in the row data.
- The stand-in rows in the "many" state use numbers that are not in the record's data, so they land on the default record (S006).
- "Discard changes?" is now "Discard your changes?".

**5. HrLeave.dc.html: applied**
- The default list state now reads `#calendar` and `#balances` on first load.
- "Discard changes?" is now "Discard your changes?".

**6. HrLeaveYear.dc.html: applied**
- "Balances on HR › Leave" now links to `HrLeave.dc.html#balances`.
- Both remaining "Discard changes?" labels are now "Discard your changes?".
- The plain "HR › Leave" links (the back link and the link in the footnote about entering leave) are left bare, because they are not about balances.

Nothing was skipped. No layouts or styles changed, and every state, handler and keyboard path is kept.

### hr-claims-payroll (6 fixes)
Group hr-claims-payroll. Board folder: design/canvas. Five of the six fixes were already in the files from the earlier interrupted run, so I only checked those. This run edited one file, PrintPayslip.dc.html.

**1. HrClaim.dc.html: applied (already in the file).** Line 725 builds `whoHref: 'HrStaffRecord.dc.html#' + c.who.no + '-claims'` from the claim's own person, with no fixed S002. The director claim has no link. HrStaffRecord now reads `#S0nn-claims` on first load (line 719, the hr-staff group's reader), and it knows S001 to S010 and A001 to A005.

**2. HrAdvances.dc.html: applied (already in the file); one part skipped as the note says.** The list row (line 667) and the Person panel (line 896) link `HrStaffRecord.dc.html#<no>-claims`. The no-person fallback at line 792 stays a plain link. The code at line 947 is unchanged: 'SA-2611-003' in the today world, and 'SA-2612-002' only in AI's 'kh' world. In the today world AI cannot add an advance (cantNew), so it never gets a code there.

**3. PayrollCheck.dc.html: applied (already in the file).**
- The constructor reads `location.hash` on first load in the PrintHrLists way. It accepts #ai, #ai-not-filed, #earlier, #many-rows and every other view name in VIEWS(), and ignores unknown names.
- The 'many-rows' view is in the options. It shows 25 of 120 payslips with 'Show 25 more', and the Excel report holds every one.

**4. PayrollLeaver.dc.html: applied (already in the file).** Line 117 links `PayrollCheck.dc.html#ai`, and line 331 reads 'Discard your changes?'.

**5. PayrollFiles.dc.html: applied (already in the file).** Line 570 reads 'The CP22A for Kah Seng (retiring on 31 Dec) … and the e-CP22 for Daniel (started on 3 Nov) …'. Lines 311 and 459 read 'Discard your changes?'. No 'Discard changes?' is left in any of the six files.

**6. PrintPayslip.dc.html: applied (edited this run).**
- Line 107 already linked `PayrollCheck.dc.html#ai`.
- **November parallel payslips** ('advance' and 'sixty' views, NOV_PAR printed Tue 24 Nov 2026):
  - Both lead cards gain a fact: 'Printed — Tue 24 Nov 2026: the example run from later. On Wed 18 Nov November's run isn't started yet'.
  - Both lead texts now say they are 'the example run from later; on Wed 18 Nov it isn't started yet'.
  - The October 'parallel' view, printed Wed 18 Nov, is October's run, so it was left as is.
- **Staff record links** now name the person and tab:
  - 'Staff record, Pay tab' goes to `HrStaffRecord.dc.html#' + p.no + '-pay'`.
  - Three other lead links go to the person's record: 'His staff record', 'Payslip password on the staff record' and 'Work email on the staff record'. The password and work email sit on the Details tab, which is the default.
  - The 'Payslip password on the staff record' link in the email preview now uses a new value, `{{mailPwHref}}` (`'HrStaffRecord.dc.html#' + mp.no`), so it opens the record of the person whose email is shown.

**Checkers:** check_board.js prints OK for all six files. `check_imports.js design/canvas --strict` prints "2958 imports checked, 0 problems". No other file was touched.

### payroll-run (6 fixes)
Group "payroll-run": all 6 fixes are applied. check_board.js reports OK on all 6 files, and check_imports.js --strict reports 2956 imports checked, 0 problems. No other files were touched.

Files are in design/canvas\

1. PayrollParallel.dc.html: APPLIED.
   - 'KWSP (EPF)' became 'KWSP' (4 places), 'PERKESO (SOCSO & EIS)' became 'PERKESO' (2 as &amp; in the HTML sentences, 2 in the script) and 'PCB (MTD)' became 'PCB' (5 places). These are the sentences at l.143 and l.156, the recurring rows at l.698-699, the saving rows at l.719-721 and the refusal text at l.727.
   - No statutory deduction labels used these strings, so none were touched. The column heads were already KWSP / PCB.
   - 'Open AI's Workbook check' now links PayrollCheck.dc.html#ai. It only lands on AI once the PayrollCheck group adds a first-load hash reader.
   - Both 'Discard changes?' prompts (l.298, l.384) now read 'Discard your changes?'.
   - The plain 'Open the Workbook check' links are unchanged.

2. PayrollRun.dc.html: APPLIED.
   - Totals row 'KWSP (EPF)' became 'KWSP'.
   - The pay-list names became 'KWSP for October', 'PERKESO for October' and 'PCB for October'.
   - Name links in the input table now use href="{{r.href}}", and inRows gains href: 'HrStaffRecord.dc.html#' + p.no.
   - The note's second spot, the 'Open her staff record' check link for Jia Hui, is here in PayrollRun (around l.780), not in PayrollTotals. It now links HrStaffRecord.dc.html#S007.
   - Left as is, outside the fix: the authority totals row 'LHDN · PCB'. It is an "authority · item" label like 'HRD Corp · HRDF levy', not a payment name.
   - Left as is: the 'Discard changes' button label (l.208), which is a button rather than the prompt. The dialog title already reads 'Discard your changes?'.

3. PayrollTotals.dc.html: APPLIED.
   - The 'her staff record' link (Izzati) now goes to HrStaffRecord.dc.html#S008.
   - PayrollTotals has no 'Open her staff record' script action; that spot was fixed in PayrollRun.
   - The bank-list row names (l.222-223) are plain text, not links, so nothing changed there.

4. SetupPayroll.dc.html: APPLIED. 'Discard changes?' became 'Discard your changes?'. The 'EPF (KWSP)' / 'SOCSO (PERKESO)' / 'EIS (SIP)' wording at l.805 stays, because those are kind words.

5. SetupLeave.dc.html: APPLIED. 'Discard changes?' became 'Discard your changes?'.

6. UsersAccess.dc.html: APPLIED.
   - The staff record link now uses href="{{r.staffHref}}".
   - The row builder gains staffHref: 'HrStaffRecord.dc.html#' + staff number, falling back to plain HrStaffRecord.dc.html. So Aisha's link goes to #S001, Nurul Aina's to #S003, and every other linked person gets their own S0nn.

Waiting on other groups: the #S0nn links in fixes 2, 3 and 6 only land on the person once HrStaffRecord gains its hash reader in its own group, and #ai needs the same in PayrollCheck.

### accounting-links (4 fixes)
Group "accounting-links": all 4 fixes are applied. Checkers are clean: check_board.js gives OK on all 4 files, and check_imports.js --strict reports 2956 imports checked, 0 problems.

1. AccountingKeptHere.dc.html: **applied.** The constructor now reads the first-load hash the PrintHrLists way. It accepts #sales, #purchases, #journals and #close, and only replaces the default 'sales' view. An explicit view prop still wins, and componentDidUpdate is unchanged. The Sidebar part of the note needed no edit: Sidebar.dc.html line 182 already links purchases, journals and close to #purchases, #journals and #close. Sales links to the bare file, which lands on Sales anyway. Sidebar is not my file and was not touched.

2. BooksParties.dc.html: **applied.** The constructor reads location.hash on first load and only replaces the default 'customers' view. It accepts only the state names in the view enum, apart from 'customers' itself. initial() only builds state (the timer starts elsewhere), so starting a state from the hash is safe. The Overview card part of the note needed no edit: OverviewCards.dc.html lines 499/505 and Main.dc.html lines 721/727 already link to BooksParties.dc.html#customers-overdue and #suppliers-due. Neither file was touched.

3. BooksLedger.dc.html: **applied.** The 'Opening balances in Journals' link on line 118 now goes to AccountingKeptHere.dc.html#journals.

4. BooksStatements.dc.html: **applied.** The 'Opening balances in Journals' link on line 117 now goes to AccountingKeptHere.dc.html#journals.

Outside my group, other boards still link to bare AccountingKeptHere.dc.html, which lands on Sales:
- Payment.dc.html line 565 and DarkPayment.dc.html line 567: 'Open on Purchases'. This one lands on the wrong page and should get #purchases.
- BooksParties.dc.html line 121 'Sales and Purchases', MyInvois.dc.html line 99 'Open Sales', NewPayment.dc.html line 205 'Open a Sales receipt' and CommandPalette.dc.html line 241 'Sales'. These all mean Sales, so they are fine as they are.

Files edited (all in design/canvas):
- AccountingKeptHere.dc.html
- BooksParties.dc.html
- BooksLedger.dc.html
- BooksStatements.dc.html

## Integrate
Package K final pass on the design-motion project: done. Every board passes check_board (OK), the strict import check finds 0 problems, there are no broken links, the ten spot-checked figures agree across boards, and no temp files were left today.

**What I fixed in this pass**
- **"Discard your changes?" wording.** Two reason dialogs still used another heading. Neither throws away a whole new item, so the plan's rule applies to them.
  - HrClaim.dc.html line 411: "Discard the reason you typed?" now reads "Discard your changes?".
  - HrAdvances.dc.html line 739: the withdraw `askText` now reads "Discard your changes?". "Discard this new advance?" stays, because that dialog discards a whole new item.
- **Comments in Bank.dc.html and DarkBank.dc.html.** The comment describing the Reopen month discard dialog said "Discard changes?". It now says "Discard your changes?", which is what the dialog already shows.
- **SetupGeneral.dc.html rollover banner.** It said "October is still open: 9 things left." It now says "5 things left". Main and DarkOverview work this out from Next up as 5 (AISB alone, and All companies).
- **canvas.json heights.** Three boards had a new `$preview` height that canvas.json did not have yet: AuditPack 1910, SetupChecklist 2900 and SetupRequired 1960.
  - Because SetupChecklist is now taller, I moved every board and note at y ≥ 61150 down by 1140. That covers the Search/alerts/states row, the Printed row, Phone, Dark mode and their titles and notes, and keeps the 640 gap between rows.
  - After the change: 92 boards are on the canvas, every board's size matches its `$preview`, and nothing overlaps.

**Checker results**
- check_board.js on all 92 boards (93 files counting canvas.json): every board ends OK. Two boards print warnings before their OK. Both come from calling handlers with no context, and they were there before this pass.
  - SetupChecklist.dc.html:
    - `[{"view":"reminders-many"}] o.toggle(Escape) threw when called out of context: Cannot read properties of undefined (reading 'Bank statement')`
    - `[{"view":"reminders-loading"}] o.toggle(Escape) threw when called out of context: Cannot read properties of undefined (reading 'Bank statement')`
  - Sql.dc.html:
    - `[{"view":"reports-only"}] keepLines(Escape) threw when called out of context: Cannot read properties of undefined (reading 'no')`
    - `[{"view":"reports-only"}] undo(Escape) threw when called out of context: Cannot read properties of null (reading 'prev')`
- The five boards I edited (HrClaim, HrAdvances, SetupGeneral, Bank, DarkBank) were re-checked and are OK.
- `check_imports.js --strict`: "2969 imports checked, 0 problems".

**Do the plan's decisions hold everywhere (grep plus renderVals)?** Yes, on every board except Company.dc.html and the phone boards, which were not edited.
- **KWSP / PERKESO / PCB.**
  - "KWSP (EPF)", "PERKESO (SOCSO & EIS)", "PCB (MTD)" and "LHDN (PCB)" appear only on Company.dc.html and the phone boards.
  - "EPF (KWSP)" appears only where the statutory kind is meant: Setup › Statutory accounts, Statutory payables, Next up rule 14, the audit pack, payslip and deduction labels, and employer-number fields.
  - Payment rows read "KWSP" or "KWSP for October".
  - The "one of the two names" note is gone.
- **Reminder titles.** "e-CP22 for Daniel", "CP22A for Kah Seng", "Register Daniel with KWSP and PERKESO" and "Stamp the contract of Daniel" are used on every board that shows them, including Next up rows 12 and 13 on Main, DarkOverview, CommandPalette and Sidebar.
  - The rule 16 rows have no names.
  - "8 Sep joiner" is gone.
  - Exception: Topbar.dc.html lines 286–287 still say "CP22A for the leaver" and "e-CP22 for the joiner". These are code comments only and are not shown; I left them.
- **Daniel and November.** MonthlyChecklist (November) shows "1 of 30 done" with the filter counts 30, 29, 1 and 0. The Overview in November shows "1 of 30". "1 of 28" and "0 of 28" are nowhere.
- **Company.dc.html.** No board links to it; the only matches were "DarkCompany.dc.html". CommandPalette "Switch company" opens CompanySwitcher.dc.html, and States "Go to October" opens MonthlyChecklist.dc.html.
- **Budget (AISB):**
  - Balance RM 56,790.35 on 19 Oct; still to pay 93,923.10 across 14 payments; funds to request 37,132.75.
  - Electricity 1,163.20, paid 4 Nov.
  - The contractor details read "Field works, October".
  - Insurance renewal is a budget line only. The "aIns" candidate and "2,310.00" are gone (2,310 matches only the 52,310.40 in Bank's July figures).
- **Budget (AI):** no RM balance ("AI's only account is Maybank FCA (USD)"). Still to pay 8,398.00 = KWSP 4,478 + Electricity 1,420 + Consultant 2,500.
- **Funds to request on the Overview.**
  - AI shows "Enter the bank balance to see funds to request" in October and September.
  - The four-company variant reads AISB 37,132.75, AIL 6,420.00 and AIP 9,880.00 in October, and 31,200.00, 5,980.00 and 9,100.00 in September.
- **AI's KWSP of 4,478.00** is used on every AI row: Budget, PaymentsRegister, DarkCompany, NewPayment, Recurring, ToPay, CommandPalette, PrintMonthReview and the Overview ("RM 4,478.00 overdue"). 11,240.00 appears only on AISB rows.
- **Trial balance read times.**
  - "Differs": the journal is read at 10:42 and the trial balance at 10:58 (10:58:41 on SqlBooks). AuditPackBooks D1/D2/D3 show 310-000 33,570.35 against 33,618.35, and 900-010 58.00 against 10.00.
  - "Stale": the journal is read again at 11:05.
  - There is no 17/11 09:10 read.
- **Net salaries payable (420-000)** is confirmed 13 Nov 2026 on SetupStatutory and BooksStatutory.
- **Consultant.** "Payroll Advisory PLT" is the payee name on 20 boards. "Payroll advisor" appears only as SQL's account name. "Robin Advisory" is gone.
- **Payment types.** Recurring uses the labels from `hrp/rules.py` (Director allowance, Rental, Other payment, Utility / telco, Consultant fee, Money received, Statutory (KWSP / PERKESO / LHDN)).
- **Parties and bank details.** 400-C003, 400-W001 and CIMB 8006447122 are present.
- **Recurring counts.** AISB 11 and AI 4, 15 in all (SetupMove says 15).
- **Other facts:**
  - The KWSP recurring history reads 11 Nov 2026 14:20, 11,180.00 → 11,240.00.
  - The consultant fee starts 2026-09-01 and AF-2611-004 is waiting.
  - AIP shows "None yet" on Approvals, PrintApprovalForm and SetupApprovers.
  - SA-2611-003 is present.
  - AISB's September is still open and AI's September was filed 5 Oct.
- **Documents missing 2.** It opens `MonthlyChecklist.dc.html#missing-documents`, and the "Missing documents" filter there shows 2 and is selected.
- **Rollover banner.** Main and DarkOverview read "AISB's November is set up … 5 things".
- **Statements and notifications.**
  - Maybank current: 14 lines, 8 matched, imported 3 Nov 09:40.
  - Maybank FCA: 2 lines, 5 Nov.
  - The Office rental bank slip was uploaded 13 Nov 10:42.
  - The bell shows 6 unread, or 7 with trail attention (renderVals on Notifications).
- **Remaining checks:**
  - Every hash target in the plan has a first-load hash reader.
  - "Open AI's Overview" is gone.
  - The Setup toasts offer Undo, including the paste toast in SetupParties.
  - PayrollCheck has `many-rows` and SetupHolidays has `many`.
  - PrintBankRec exists. Bank and DarkBank print it per account (`#current`, `#savings`, `#fca`). BankReview has the "No money moved" pair states. ApprovalUpload has `bank-rec`, `bank-rec-matched` and `bank-rec-changed`.
  - The Foundations signature block is split into Signature and Date.
  - Approvals has a `no-approvers` state.
  - "Exabytes" is gone; the statement reads "WEB HOSTING".
  - samples.md holds section 0 items 19 and 20, the variant figures, Daniel's full November month and the September EPF note.

**Links**
- Every `*.dc.html` named on a board or in canvas.json exists, except MobileApprovalPhoto.dc.html. That one is linked from DarkPayment, Payment, PrintApprovalForm, PrintBankRec and PrintMonthReview, which is allowed.
- No board links to Company.dc.html.
- Every `#hash` link lands on a target that reads it, including the ones built in code (HrStaffRecord `#S0nn-claims` and `#S0nn-pay`, PrintBankRec `#current`/`#savings`/`#fca`, BooksLedger `#<code>`, PrintApprovalForm, PrintHrLists, PrintMonthReview `#ai`, PrintPayrollOutputs).

**Figures spot-checked with renderVals.** All ten agree.
1. **37,132.75 funds to request:** Budget, Main, DarkOverview, OverviewCards.
2. **93,923.10 still to pay:** Budget, Main, DarkOverview, OverviewCards.
3. **56,790.35 balance on 19 Oct:** Budget, the Overview tooltip, BankReview's 15 Oct running balance.
4. **4,478.00 AI KWSP:** Overview (Main and DarkOverview), ToPay, PaymentsRegister, DarkCompany, Budget, Recurring, CommandPalette, PrintMonthReview.
5. **11,240.00 AISB KWSP:** ToPay, PaymentsRegister, Budget, Recurring, BooksStatutory, AuditTrail, AuditPackHR, PrintMonthReview, CommandPalette.
6. **1,163.20 Electricity / PV2611-003:** PaymentsRegister, Budget, Sql, SqlBooks, Notifications, CommandPalette, PrintMonthReview, AuditTrail.
7. **11,726.50 overdue** (KWSP 11,240 + Wei Ming 486.50), plus 2,228.00 and USD 1,200 due within 7 days: ToPay sums, Main, DarkOverview, OverviewCards.
8. **25,120.00 paid without approval** (24,000 + 1,120): Main and DarkOverview, which agree with Approvals, AuditPack and PrintMonthReview on Stationery Mart's 1,120.00 / 120.00.
9. **Bank balance 92,325.55** = 34,314.15 + 58,011.40, with in 55,984 and out 106,077: Main and DarkOverview work it out, it matches Foundations, and it follows Bank's October statement data.
   - The PrintBankRec arithmetic is right: 34,314.15 − 4,320.00 + 3,624.20 = 33,618.35, and the 695.80 difference matches PrintMonthReview.
   - USD 17,480.00 for AI matches on PrintBankRec, PrintMonthReview and the Overview.
10. **Checklist 18 of 27 / 15 of 22:** MonthlyChecklist (All 27 / Done 18), Main, DarkOverview, PaymentsRegister, DarkCompany, PrintMonthReview.

**Boards whose `$preview` size changed (against design-v74)**
- AuditPack: 1440×1760 → 1440×1910
- BankReview: 1440×1800 → 1440×2200
- PrintBankRec (new board): 1440×3300
- SetupChecklist: 1440×1700 → 1440×2900
- SetupRequired: 1440×1760 → 1440×1960

All of these were made by the earlier K fixes. In this pass I only brought canvas.json into line with them and moved the lower rows down by 1140, as described above.

**Still open, and why**
- **Phone design is deferred** by the owner. MobileOverview, MobileCompany, MobilePayment, MobileNewPayment and MobileDesktopOnly are byte-identical to v74, and still carry "KWSP (EPF)", "e-CP22 for the joiner" and links to Company.dc.html. Company.dc.html is also unchanged, as planned. MobileApprovalPhoto is not drawn yet.
- **The KWSP double row** (rule 14 and "Pay KWSP" both on Next up) is still an owner question. It changes the product, not the sample data, so I did not decide it.
- **States.dc.html and DarkPalette.dc.html** keep a generic "November payroll has started … 3 things left" banner. These are pattern samples that name no company, so I left them.
- **Topbar.dc.html** row comments (lines 286–287) still say "the leaver" and "the joiner". They are comments only and not shown.
- **Estimated heights.** Main, DarkOverview, OverviewCards and Foundations still use estimated `$preview` heights, because I cannot render the boards here. Only the boards each group measured have measured heights.
- **Kept as intended:**
  - PrintHrLists draws only S006's and S010's staff record and the October lists.
  - AF-2611-003 prints plain.
  - The empty Funds and Bank sentences may wrap to two lines.
  - Telephone & internet's 28 Oct bank line is left as stage 1 §25 leaves it.
  - The pre-scope Setup and SqlBooks boards have no many-rows state; review §3's rule covers only new boards.

**Temp files:** nothing to delete. The only non-board files changed since 18 Nov are the allowed `scope\samples.md` and `scope*\*.md` files. The older helper files in the scratchpad root (patch_sql*.py, bank_*.js and others, all dated 14–15 Nov) were not left today, so I left them.

Folder: design/canvas

Files changed in this pass (all in that folder):
- HrClaim.dc.html
- HrAdvances.dc.html
- SetupGeneral.dc.html
- Bank.dc.html
- DarkBank.dc.html
- canvas.json
## Owner answer, 19 Nov
- Joiner reminders: MERGE. The build changes the app to one reminder "Register {name} with KWSP and PERKESO" (7 days) and "Stamp the contract of {name}", as the canvas draws them. The canvas needs no change.
- Still open: the KWSP double Next up row.
- KWSP double row: ONE ROW. Next up keeps the payment row ("Pay KWSP for October", overdue after 15 Nov) and drops the rule 14 statutory row while that payment is unpaid; rule 14 shows only when there is no unpaid payment to point at. App change in hrp/nextup.py; canvas updated in v77.
