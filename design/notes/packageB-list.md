# Package B: what package A left for the other boards (from the integration check, 17 Nov 2026)

Also apply scope/samples.md section 17 (edits the samples need on existing boards).

4. LIST FOR PACKAGE B (other boards; I did not edit them)
- MyInvois, InvoicePdf: Sidebar active "sql" → "einvoices". Topbar section "Monthly work"/"SQL import" → "Accounting"/"e-Invoices".
- BooksParties: Sidebar "books" → "parties", Topbar page "Customers and suppliers".
- BooksStatutory: Sidebar "books" → "statutory", Topbar page "Statutory payables".
- Recurring, setup mode: today it reads sidebar "setup" and Admin › Setup › Recurring payments. Its one home is now Payments › Recurring (the SetupNav note says "Opens Payments › Recurring"), so sbActive should stay "recurring" and the Topbar should read Payments/Recurring, or the setup mode should go.
- NewPayment: the Topbar reads Payments › Payments register. The review wants Payments › Add payment: pass section="Payments" and a page, or sub="Add payment".
- Main, DarkOverview: pass the Topbar company="none" when coMode is none, and companies="four" in the four-company view. Today the Topbar shows "All companies" with two companies while the Sidebar has none or four.
- The 19 boards with the in-page role="group" aria-label="Company" control: remove it, and pass the chosen company to Topbar and Sidebar as company (and kind) props. These are AuditPack, Bank, BankReview, Books, BooksLedger, BooksParties, BooksStatements, BooksStatutory, Budget, CommandPalette, DarkBank, Recurring, Setup, SetupChart, SetupChecklist, SetupParties, SetupStatutory, Sql, SqlBooks. Until then, the Budget "ai" view and similar views still show AISB in the bar and the menu.
- Every old board should switch to the new section names and explicit company/kind props. The old values only work through aliases.
- The Setup boards should pass SetupNav kind="here" for AI pages (this hides Matching words) and payroll="true" for AISB (this shows Payroll settings). Today they get the defaults: sql, and no Payroll settings.
- SetupChecklist: the Topbar page "Checklist and reminders" doesn't match the SetupNav entries "Monthly checklist" / "Joiner and leaver reminders". This is only cosmetic.
- SetupMatching: optional. Its Topbar page "SQL matching words" could become "Matching words". The Topbar's switch toast handles both names.

