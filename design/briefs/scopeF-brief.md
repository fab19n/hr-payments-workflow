# Brief: design packages F (HR step 1) and G (Payroll)

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas: `design/canvas` (69 boards). Copy before these packages: `(an earlier canvas version; see the artifact history)`.

**First read and follow `design/briefs/scopeC-brief.md` in full**: its reading list, rules, shell rules, owner's rules, privacy,
wording, list and form states, links (the planned board names), accessibility, file ownership, checkers and report
format all apply here. This brief adds what is particular to HR and payroll.

## Also read
1. The scope, `docs\2026-11-16-hr-payments-accounting-scope.md`: section 5 (HR step 1, all of
   5.1 to 5.5) for package F; section 6 (payroll, all of it) for package G; section 9 (privacy and access) for both;
   section 4 for how requests go to Approvals and To pay.
2. The review `docs/design/2026-11-17-redesign-scope-gaps.md` section 3: boards 4 to 13 (HR) and 14
   to 20 (Payroll), with every state to draw; section 4 decisions settled.
3. `design/samples.md` sections 4 to 13 (users, staff, October payroll, workbook checks, leave, calendar, claims,
   advances, approval forms). Every person, date, code and figure comes from there.
4. The boards these link to and must agree with: `Approvals.dc.html`, `ToPay.dc.html`, `PaymentsRegister.dc.html`,
   `MonthlyChecklist.dc.html`, `Recurring.dc.html`, `BooksStatutory.dc.html`, `SetupLeave.dc.html`,
   `SetupHolidays.dc.html`, `SetupClaimTypes.dc.html`, `SetupApprovers.dc.html`, `SetupPayroll.dc.html`,
   `OverviewCards.dc.html` (the HR cards open your pages, filtered).
5. For package G: the app's Payroll check, which exists today. `hrp\payrollcheck.py` (report
   shape, severities, headline wording, refusals, RATES, masking), the `/api/payroll-check` routes in
   `hrp\app.py`, `viewPayroll` in `static\app.js`, Next up rule 15 in `hrp\nextup.py`, and
   `synthetic_tests\payroll_check_test.py` for wording. Read only. Never read the owner's real payroll workbook or
   anything under C:\HR-Records.

## HR and payroll rules
- **Menu:** Sidebar `active` is `staff` (Staff list and record), `calendar` (Calendar and reminders, a tab of Staff),
  `leave`, `claims` (Claims tab of "Claims and advances"), `advances` (Advances tab), `payroll`. Topbar section `HR`.
  HR › Staff can show All companies read only (Topbar `allowAll` read-only); other HR pages are per company.
- **Every company** has HR (staff, leave, calendar, claims, advances) and the Payroll page with its **Workbook check**
  tab. The payroll **run** tabs (run, outputs, files, leaver, parallel run, opening year to date) show only where
  "Runs payroll in this app" is on (AISB in the samples). For a company without it, HR › Payroll holds only the
  Workbook check tab, and a short line says the run is turned on in Setup › Companies. Nothing is fixed to AISB.
- **Requests:** a claim, an advance or a salary run is a request. It goes to Payments › Approvals for its signed form
  and to Payments › To pay once approved; approval never blocks paying. Show both links on the request.
- **Privacy:** pay figures show only to a user with the Payroll figures right (Nurul Aina has HR without it: draw that
  state on the boards that show pay); IC masked to the last 4 everywhere, except the HR staff record PDF (package J);
  leave type never shown outside HR; no medical detail anywhere.
- **Statutory facts:** follow scope section 6 and `payrollcheck.RATES` exactly, with their dates. Where the scope
  marks something as common payroll practice ("check with KWSP and PERKESO"), show that flag.
- **Leave:** the legal minimums are the entitlement; above the legal days is a warning only, never refused.
- **Payslip password:** the person's IC number without dashes by default (passport number for a foreign worker), or a
  personal one set by HR on the staff record; the email names the rule, never the password.
