# Brief: design packages C, D, E and H (Overview, Payments, Accounting, Admin)

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas files: `design/canvas`. Copy before these packages: `(an earlier canvas version; see the artifact history)`.
App code (read only, never run, never read C:\HR-Records): `C:\GitHub\hr-payments`.

The owner approved a new scope (`docs\2026-11-16-hr-payments-accounting-scope.md`). Package A
drew the new shell (Sidebar, Topbar with the company switcher, Icon with 80 glyphs, Foundations, DarkPalette, States,
SetupNav, ShellMenus, CompanySwitcher). Package B moved every board onto it. **Now the pages themselves change**, in
four packages that run at the same time, each split into groups of files: C Overview, D Payments, E Accounting,
H Admin.

## Read first
1. `docs/design/2026-11-17-redesign-scope-gaps.md`: your boards' rows in section 2 (existing boards),
   their entries in section 3 (new boards, with every state to draw), section 4 (shared changes, the decisions
   settled), section 7 (the owner's answers, which win over anything else).
2. The scope sections your boards cover (section 3 Overview; 4 the four steps and approvals; 7 Payments; 8
   Accounting; 9 privacy and access; 2 for Setup and placements; 5 and 6 only for the Setup › HR parts).
3. **`design/samples.md`**: every name, code, figure, count, badge and date. Boards must agree with it and with each
   other. Section 17 lists edits existing boards need. The stage 1 figures are in `design/samples-stage1.md`.
4. The shared patterns, so every board looks and behaves the same: `Foundations.dc.html` (company-kind chip, Overview
   card anatomy and states, the Approval marker's six readings, request / leave / staff pills, masked IC, Payroll check
   tones, print section, addresses), `States.dc.html` (empty, loading, could not load, many rows, refused, confirms,
   toasts with Undo), `DarkPalette.dc.html`. For the house look and the record dialog: `Setup.dc.html`, `Sql.dc.html`,
   `Bank.dc.html`, `Company.dc.html`.
5. `design/motion-keyboard-spec.md` (section 0: format rules that fail silently) and
   `(the Design artifact type format reference, not copied: see design/README.md)`.

## Rules
- **Shell:** every desktop board imports Sidebar and Topbar with explicit `active`, `company`, `kind` (Sidebar) and
  `section`, `page`, `company` (Topbar), following the company the board shows, and wires the top-bar switcher with
  `on-company` when the board can show more than one company. `node design/tools/check_imports.js design/canvas
  --strict` must report nothing for your files.
- **Owner's rules:** nothing is fixed to AISB (company differences are settings: Kept in SQL Account / Kept here,
  Runs payroll in this app); the Payroll check exists for every company; approvers, leave policy, holidays and claim
  types are per company; leave above the legal days is a warning only; Customers overdue = older than 30 days; Net
  salaries payable = the company's own account (AISB 420-000 Accruals); payslip password = IC number without dashes by
  default, or a personal one; approval never blocks a payment; unapproved items appear only on Approvals.
- **Privacy:** no pay figure, IC, bank account, address or leave type on the Overview; IC masked to the last 4
  everywhere except the HR staff record PDF.
- **Wording:** real app wording where the app has it, else the scope's; sentence case; plain English; never "stage";
  a company is "Kept in SQL Account" or "Kept here".
- **Every list** draws empty, loading, could not load and many rows; **every form** draws saving, refused with the
  reason, and Discard changes?; every toast that confirms a change offers Undo. Use the States patterns.
- **Links:** to existing boards, or to a planned board by its exact name from review section 3 (OverviewCards,
  HrStaff, HrStaffRecord, HrStaffForm, HrStaffExport, HrLeave, HrLeaveYear, HrCalendar, HrClaims, HrClaim, HrAdvances,
  PayrollCheck, PayrollRun, PayrollTotals, PayrollFiles, PayrollLeaver, PayrollParallel, PayrollOpeningYtd,
  PaymentsRegister, MonthlyChecklist, Approvals, ApprovalUpload, ToPay, BankBookLine, AccountingKeptHere,
  SetupApprovers, SetupLeave, SetupHolidays, SetupClaimTypes, SetupPayroll, UsersAccess, AuditPackHR,
  MobileApprovalPhoto, PrintApprovalForm, PrintMonthReview, PrintPayslip, PrintPayrollOutputs, PrintHrLists). Never
  invent another board name.
- Keep motion, keyboard and accessibility rules (dialogs: focus trap, Escape, focus return; menus; tabs with roving
  tabindex; reduced motion; 4.5:1 text, 3:1 control borders, light and dark; 32px targets; labels and errors tied to
  fields). Icons only from `Icon.dc.html`.
- Write only your group's files (and the new boards it names). Never edit Sidebar, Topbar, Icon, SetupNav,
  Foundations, DarkPalette, States, ShellMenus, CompanySwitcher, or another group's files: report what you need from
  them instead. Keep everything that works on the boards you edit.
- Made-up names only, from samples.md. No helper or temp files anywhere (use `node -e`).
- Run `node design/tools/check_board.js <file>` on every file you touch until it prints OK, and the strict import check.
- Report per file: what you did (per state), what you skipped and why, the `$preview` width and height, `new_work`
  (features with no app backend yet), anything you need from a shared board, and the checkers' last lines.
