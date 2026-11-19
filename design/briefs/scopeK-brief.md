# Brief: design package K, the final consistency sweep

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas: `design/canvas` (91 boards). Copy before this package: `(an earlier canvas version; see the artifact history)`.
App code (read only, never run, never read C:\HR-Records): `C:\GitHub\hr-payments`.

Packages A to J redrew the canvas for the owner's approved scope. K makes the whole canvas agree with itself before the
build starts: the same names, codes, figures, dates and wording everywhere, every scope screen present, every link
landing on a real state. It is a sweep, not a redesign: fix what disagrees, never restyle.

## Read first
1. `design/briefs/scopeC-brief.md` (rules for every board: owner's rules, privacy, wording, links, accessibility, checkers) and
   `design/briefs/scopeF-brief.md` (HR and payroll rules).
2. `design/samples.md`: the one shared sample data set. Where boards disagree, samples.md wins unless it is itself
   wrong; then fix samples.md first and say so.
3. `design/notes/design-leftovers.md`: every leftover the earlier packages handed to K.
4. `docs/design/2026-11-17-redesign-scope-gaps.md` (sections 2 to 4, 7) and the scope
   `docs\2026-11-16-hr-payments-accounting-scope.md` section 10 (the checklist of screens).

## Owner decisions that apply
- **Phone design is deferred.** Never edit MobileOverview, MobileCompany, MobilePayment, MobileNewPayment or
  MobileDesktopOnly; MobileApprovalPhoto is not drawn and links to it stay. Phone items in scope section 10 are out of
  this sweep (list them as deferred).
- Nothing is fixed to AISB; the Payroll check is for every company; approvers, leave policy, holidays and claim types
  are per company; leave above the legal days is a warning only; Customers overdue = older than 30 days; Net salaries
  payable = the company's own account (AISB 420-000 Accruals); payslip password = IC number without dashes or a
  personal one.
- The Overview cards follow the calmer design of 18 Nov (one headline, one note, company lines only for All companies,
  four per row; Bank merged; Funds to request; Dates coming up holds birthdays).

## Decisions K makes (state each in the report)
- **The KWSP payment's name:** use the app's own wording (grep `hrp/` and `static/app.js` for how the payment type,
  recurring row and Next up text name it) and use it on every board.
- **"e-CP22 for …":** use the SetupChecklist template form ("e-CP22 for {name}") wherever a reminder is shown.
- **Daniel's "Register Daniel with KWSP and PERKESO"** (done 10 Nov): it belongs on November's checklist (he joined
  3 Nov). Update samples.md and the boards (November then reads 1 of 28 done).
- **Company.dc.html** ("Payments register (source)") stays as a board for now, but no board may link to it any more:
  point every link at PaymentsRegister, MonthlyChecklist or DarkCompany as fits.
- Anything else in packageK-notes.md: decide, apply, and report. Only a question that changes the product (not the
  sample data) goes to the owner.

## Rules
- Keep every state, link, handler, keyboard path and motion working. Do not change layouts or styles except where a
  fix needs it. Made-up names only; check any new name with `git -C C:\GitHub\hr-payments log --all -S'<surname>'`.
- No helper or temp files anywhere (use `node -e`). Run `node design/tools/check_board.js <file>` on each file you touch until
  OK, and `node design/tools/check_imports.js design/canvas --strict` (must stay at 0 problems).
