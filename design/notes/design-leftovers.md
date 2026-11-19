# Left for package K (consistency sweep), from packages C, D, E, H (18 Nov 2026)

- KWSP payment name: "EPF (KWSP)" (BooksStatutory, Next up rule 14, as hrp/nextup.py words it) vs "KWSP (EPF)" (PaymentsRegister, ToPay, Next up row 3). Pick one (owner or K).
- Company.dc.html is kept as "Payments register (source)": decide whether to retire it once nothing links to it.
- CommandPalette "Switch company" action still opens Company.dc.html; better wired to the top-bar switcher.
- Budget.dc.html line ~537 describes the contractor as "Field works, phase 2" (budget wording only).
- Main/DarkOverview: AIL and AIP card figures are not in scope/samples.md (four-company view).
- Full per-group reports: scopeC/result-full.md.
- (from F/G) Daniel's "Register Daniel with KWSP and PERKESO" (done, due 10 Nov): HrCalendar says it is on a checklist, but MonthlyChecklist lists it in neither month. He joined 3 Nov, so it belongs on November's checklist (November then shows 1 of 28, not 0 of 28). Decide in samples.md, then fix HrCalendar and MonthlyChecklist.
- (from F/G) "e-CP22 for the joiner starting 3 Nov" (Main, MonthlyChecklist, HrCalendar) vs the SetupChecklist template "e-CP22 for {name}".
- (from F/G) Figures added beyond samples.md, to check: PayrollOpeningYtd November and December per person and totals (gross Jan-Nov 643,332.50; Dec 63,300.00; YTD 706,632.50). October is the example run; AISB switches over on Tue 1 Dec 2026.
- (Overview cards, v73) Empty sentences on Funds to request ("Enter the bank balance to see funds to request") and Bank ("No statement imported for November 2026") wrap to two lines in the card; allowed for now, shorten if wanted.
- (Overview cards, v73) Requests waiting opens Approvals only; "approved, to pay" is in its note, To pay is reached from Due and overdue.
- (Overview cards, v73) $preview heights of Main, DarkOverview, OverviewCards, Foundations are estimates: measure when the boards are rendered.
- (owner, 18 Nov) Phone design deferred: K must not redraw phone boards; links to MobileApprovalPhoto stay as planned-name links.
- (J, v74) PrintHrLists draws only S006's and S010's staff record and only October lists; Print links for other people or months land on those examples (aria-labels say so).
- (J, v74) Foundations print sample has one "Signature and date" line; PrintApprovalForm splits Signature and Date, and with one approver prints "The approver's signature approves this form." Align.
- (J, v74) Approvals has no state for a company with no approvers (PrintApprovalForm's refusal wording can be reused).
- (J, v74) The AF-2611-003 over-limit line prints plain (limit set after printing); HrClaim/HrClaims/PrintHrLists still flag it on screen. Intended.
