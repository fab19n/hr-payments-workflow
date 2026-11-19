# Brief: bringing the canvas up to stage 1

Paths below are relative to the repository root (they were in a scratchpad when this was written).
Canvas files: `design/canvas`. App code (read only): `C:\GitHub\hr-payments` at HEAD.

Stage 1 of the app added Books (trial balance, general ledger, profit and loss, balance sheet, customers and
suppliers, statutory payables), account lines kept from SQL with checks against SQL's reports, MyInvois e-Invoices,
printed invoices and notes, new Setup fields and a Statutory accounts section, books pages in the audit pack, a
"SQL books agree" checklist item, "Before tracking", and wording changes on existing screens. The canvas was drawn
before all this.

## Read first
1. The maps of the code, one per area: `design/notes/stage1-maps/map-books.md`, `map-statutory.md`, `map-parties.md`,
   `map-einvoice.md`, `map-sql-bank.md`, `map-pack-setup-overview.md`, and the gaps the critic found,
   `design/notes/stage1-maps/critic.md`. They give every screen, state and exact string, with code lines. Check the code when
   something matters.
2. **`design/samples-stage1.md`: the one shared sample data set.** Every board uses these figures exactly, so the trial
   balance, ledger, statements, statutory, customers and suppliers, SQL, Bank, Company and Overview boards agree.
3. `design/motion-keyboard-spec.md` (motion, focus, keyboard; section 0: format rules that fail silently) and
   `(the Design artifact type format reference, not copied: see design/README.md)`.
4. For the house look, the finished boards: `Sql.dc.html`, `Bank.dc.html`, `Company.dc.html`, `Setup.dc.html`
   (shared record dialog and list toolbar), `Foundations.dc.html`.

## Rules
- Real app wording where the app has it (from the maps and code). Sentence case, plain words.
- Accounting figures follow the app: report tables have no "RM"; balances read `x Dr` / `x Cr`; brackets for the
  other way round; `—` for unknown; blank for zero in movement columns; `0.00` for a nil balance.
- The Books page has no payroll month: its period is From / To dates, defaulting to the financial year to date.
- Nothing on the Books pages can be edited (they follow SQL for a company kept in SQL).
- Today is Wednesday 18 November 2026; October 2026 is the month being worked. AISB is kept in SQL; AI
  (Agrinexus International) is not.
- Where the code has a gap the maps flag (for example an error that comes back as raw JSON, or a section that should
  hide for a company not in SQL), draw the right behaviour and list it under `new_work` in your report.
- Keep motion, keyboard and accessibility rules (dialogs, menus, tabs, reduced motion, 4.5:1 text, 3:1 control
  borders, labels). Icons only from `Icon.dc.html` (a `books` glyph is being added).
- Keep everything that works. Write only your package's files. No helper or temp files anywhere (use `node -e`).
- Run `node design/tools/check_board.js <file>` on every file you touch until it prints OK.
- Report per file: what you did, what you skipped and why, the `$preview` height, `new_work`, the checker's last line.
