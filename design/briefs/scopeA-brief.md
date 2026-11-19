# Brief: design package A, the new shell and shared boards

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas files: `design/canvas` (52 boards). App code (read only, never run): `C:\GitHub\hr-payments`.
A copy of every board before this package: `(an earlier canvas version; see the artifact history)`.

The owner approved a new scope for the app (`docs\2026-11-16-hr-payments-accounting-scope.md`):
five areas, Overview, HR, Payments, Accounting and Admin; a company switcher in the top bar instead of one menu item per
company; approvals; HR; payroll. The review `docs/design/2026-11-17-redesign-scope-gaps.md` maps what
every board must become. Package A redraws the **shared shell** that every other board imports. Later packages (B moves
the other boards, C to K draw the pages) build on it, so it must be right and it must not break today's boards.

## Read first
1. The review: section 2 (the menu table, the company switcher, rows 1 to 7 of the board table), section 3 boards 1 to
   3, section 4 (shared changes, icons, decisions settled), section 7 (the owner's answers). Where the review and the
   owner's answers differ, the answers win: **the Payroll check shows for every company** (HR › Payroll with the
   Workbook check tab for all; the run tabs only where "Runs payroll in this app" is on); **nothing is fixed to AISB**:
   every difference between companies is a setting (Kept in SQL Account / Kept here; Runs payroll in this app).
2. The scope: section 2 (side menu, menu rules, company switcher, where every page goes), 3 (Overview, for the card
   anatomy only), 9 (privacy and access).
3. **`design/samples.md`: the shared sample data for every new board.** Use its names, codes, counts and badges
   exactly.
4. `design/motion-keyboard-spec.md` (section 0 lists format rules that fail silently) and
   `(the Design artifact type format reference, not copied: see design/README.md)`.
5. The boards you edit, in full, and for the house look `Foundations.dc.html`, `Sql.dc.html`, `Company.dc.html`.

## Rules
- **Nothing that works today may break.** Every board imports Sidebar, Topbar, Icon or SetupNav with attribute values
  that are valid today. Keep every existing prop and every existing enum option working: map an old value to its new
  place (for example Sidebar `active="aisb"`, `"ai"`, `"ail"`, `"aip"` → Payments register; `active="sql"` stays SQL
  import; Topbar `section="Dashboard"` reads as Overview, `"Monthly work"` as Payments, `"Filing"` and `"Setup"` as
  Admin). Package B will change the other boards' attributes later; you do not edit them.
- After your edits, `node design/tools/check_imports.js design/canvas` must report **no problems other than these
  5, which exist today**: SetupChart's four `Icon tone="danger"` and SetupMatching's `SetupNav active="matching"`.
  (You may fix those two in Icon or SetupNav by accepting `danger` as an alias of `bad` and `matching` as the Matching
  words entry.)
- Real app wording where the app has it; otherwise the scope's wording. Sentence case, plain words, English only.
  On screen, never "stage 1/2": a company is **Kept in SQL Account** or **Kept here**.
- Made-up names only, from samples.md. Never take a person's name from the app's code or git history.
- Keep motion, keyboard and accessibility rules: menus with role menu / menuitem and arrow keys, Escape and focus
  return, roving tabindex where tabs exist, reduced motion, 4.5:1 text and 3:1 control borders in light and dark,
  32px targets, labels. Icons only from `Icon.dc.html`.
- Write only your package's files (and new boards it names). No helper or temp files anywhere (use `node -e`).
- Run `node design/tools/check_board.js <file>` on every file you touch until it prints OK, and `check_imports.js` as above.
- Report per file: what you did, what you skipped and why, the `$preview` width and height, `new_work` (features with
  no app backend yet), and the checkers' last lines.
