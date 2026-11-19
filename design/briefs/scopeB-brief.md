# Brief: design package B, moving the boards into the new shell

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas files: `design/canvas`. A copy from before this package: `(an earlier canvas version; see the artifact history)`.
App code (read only, never run): `C:\GitHub\hr-payments`.

Package A redrew the shared shell (Sidebar, Topbar, Icon, SetupNav, Foundations, States). It kept every old setting
working through aliases so nothing broke. **Package B moves every other board onto the shell for real.** It is a
mechanical package: the pages' content, states and figures are redrawn later by packages C to K. Do not start that
work here.

## Read first
1. `design/notes/packageB-list.md` (what the integration check left for package B).
2. `docs/design/2026-11-17-redesign-scope-gaps.md`: section 2 (the board table: each board's new
   place; the "move" rows are this package; for "tweak", "rework" and "split" rows do only the moves below), section 4
   (label rule, Next up text), section 7 (owner's answers).
3. `design/samples.md` sections 2, 3 and 15 (companies, their kind, the switcher list, badges).
4. The shared components' data-props, so you pass valid values: `Sidebar.dc.html` (`active`, `kind`, `access`,
   `company`, `merged`, `theme`), `Topbar.dc.html` (`section`, `page`, `company`, `allowAll`, …), `SetupNav.dc.html`.
   Read their renderVals to see how each value renders. `design/motion-keyboard-spec.md` section 0 (format rules that
   fail silently) and `(the Design artifact type format reference, not copied: see design/README.md)`.

## What to do on each of your boards
1. **Sidebar import:** the new `active` key for the board's place (review section 4 lists them: register, budget,
   recurring, bank, sql, einvoices, books, parties, statutory, setup, pack, trail, backup, overview, …), plus explicit
   `company` and `kind` (AISB `sqlPayroll`, AI `here`, AIL `sql`, AIP `here`), following the board's own current
   company (use a `{{hole}}` when the board switches company). Never an old alias (`aisb`, `ai`, `ail`, `aip`).
2. **Topbar import:** `section` is one of Overview, HR, Payments, Accounting, Admin; `page` is the new page name
   (Payments register, Budget, Recurring, Bank and reconciliation, SQL import, e-Invoices, Books, Customers and
   suppliers, Statutory payables, Setup › …, Audit pack, Audit trail, Backup, Add payment …); `company` explicit
   (`all` only on the Overview, with `allowAll`).
3. **The in-page company control** (`role="group" aria-label="Company"`) goes: the top-bar switcher replaces it. The
   board keeps showing every company it showed: its `view` tweak (or a new `company` tweak if it had none) still
   selects the company, and the board passes that company to Sidebar and Topbar. Remove only the control and any
   heading space it took; keep the rest of the layout.
4. **Eyebrows and breadcrumbs** inside the page that name the old place ("Monthly work", "Filing", "Companies",
   "Dashboard") take the new area name. Do not retitle h1 headings that a later package reworks (MyInvois stays
   "SQL import · MyInvois e-Invoices" until package E) unless the review's "move" row says so.
5. **Label rule:** on screen only "Kept in SQL Account" or "Kept here". Fix "Not kept in SQL", "not kept in SQL",
   the short "Kept in SQL", "Books kept in this app" and similar, keeping the sentence natural.
6. **Next up rule 14 text** wherever it is quoted: "…Check it on Statutory payables." with the meta or link target
   "Accounting › Statutory payables" (BooksStatutory.dc.html).
7. **Setup boards:** pass SetupNav `kind` and `payroll` for the company shown (AISB: Kept in SQL Account, runs payroll;
   AI: Kept here, no payroll run), and fix the cosmetic page names in packageB-list.
8. **Phone boards** (no Sidebar or Topbar): only items 4, 5 and 6, plus the phone nav labels the review's rows name
   ("Companies" tab → "Payments"). The phone redesign itself is package I.

## Rules
- Write only your group's files. Never edit Sidebar, Topbar, Icon, SetupNav, Foundations, DarkPalette, States,
  ShellMenus or CompanySwitcher; if one of them can't express what a board needs, report it.
- Keep every state, link, handler, keyboard path and figure working. Change nothing else.
- Made-up names only; never take a name from the app's code or git history.
- No helper or temp files anywhere (use `node -e`).
- Run on every file you touch, until clean:
  `node design/tools/check_board.js <file>` (must print OK) and `node design/tools/check_imports.js design/canvas --strict`
  (no line may name your files).
- Report per file: what you changed (one line per item above), what you skipped and why, the `$preview` size if it
  changed, and the checkers' last lines.
