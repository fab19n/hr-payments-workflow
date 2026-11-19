# Brief: design package J, the printed boards

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas: `design/canvas` (86 boards). Copy before this package: `(an earlier canvas version; see the artifact history)`.

**First read and follow `design/briefs/scopeC-brief.md` in full** (reading list, owner's rules, privacy, wording, links to
planned boards, accessibility, file ownership, checkers, report format) **and `design/briefs/scopeF-brief.md`** (HR and payroll
rules: payslip password, IC masking, Payroll figures right, statutory facts). This brief adds what is particular to
printouts.

## What package J draws
Five new boards, each a print preview of one or more A4 pages, as review section 3 boards 36 to 40 describe
(`docs/design/2026-11-17-redesign-scope-gaps.md`): PrintApprovalForm, PrintMonthReview, PrintPayslip,
PrintPayrollOutputs, PrintHrLists. Every state the review lists for each.

## Read also
1. Scope section 4 (how approval works: the form's code, keyed check and QR, up to 3 approvers, "Any one signature
   approves this form", Paid without approval on file, the Month review), section 6 (payslips, outputs, bank payment
   list, statutory files, journal summary), section 10 "Printed and downloaded", and section 1 (English only).
2. The print patterns already on the canvas: Foundations.dc.html "print" section (A4 sheet, code + keyed check + QR
   block, approver signature block, "declared, not verified", "Page x of y"), InvoicePdf.dc.html (pages drawn at mm
   positions, state chips, lead card), AuditPackBooks.dc.html (A4 print preview with a bookmark list).
3. The boards each printout must agree with: Approvals, ApprovalUpload, SetupApprovers, HrClaims, HrClaim, HrAdvances,
   Recurring, PaymentsRegister, MonthlyChecklist, Bank (reconciliation), PayrollRun, PayrollTotals, PayrollFiles,
   PayrollLeaver, PayrollParallel, HrStaffRecord, HrLeave, BooksStatutory. Codes (AF-…, MR-2610-AISB), keyed checks,
   signers, amounts, names and dates come from `design/samples.md` and must match those boards exactly.

## Print rules
- A printout is a page, not a screen: no Sidebar or Topbar on the page itself. The board around it may have a short lead
  card (file name, who printed it, the audit-trail entry) and a "State to show" chip group like InvoicePdf.
- A4 portrait, drawn to scale with real margins; text at print sizes (body about 9 to 10 pt); "Page x of y" on every
  page; a repeated header on page 2 and later. Black and grey on white; colour only where it carries meaning that also
  reads in black and white.
- English only. Company name, registration number and address as Setup › Companies holds them for the company.
- The approval form never prints a pay figure per person on page 1; per-person pay prints on page 2 only for a user with
  the Payroll figures right. The payslip masks the IC to the last 4 (it is emailed). The staff record PDF is the one
  place the full IC prints, marked "Confidential: personal data"; race and religion are left out unless chosen.
- Nothing is fixed to AISB: a company without approvers set prints nothing and says why; AI (one approver) shows the
  self-approved case where the review asks for it.
- The QR is a stand-in pattern, labelled as not scannable on the board.
