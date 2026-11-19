# The redesign: everything a build session needs

This folder holds the finished redesign of HR Payments, copied here on 19 November 2026 so another session can build
it. **Nothing in it is built into the app yet.** The app code (`hrp/`, `static/`) is unchanged by the design work,
except the bundled fonts in `static/fonts/` (not linked yet).

## Start here, in this order
1. **The build plan:** [`docs/design/2026-11-19-redesign-build-plan.md`](../docs/design/2026-11-19-redesign-build-plan.md).
   17 slices, from slice 0 (the new shell) to payroll and sign-in. Each slice names its boards, its screen work, its
   server work, what it depends on, and how it is checked. Section 4 lists every app behaviour the design changes;
   section 7 the decisions still open and the design leftovers to handle while building.
2. **The approved scope:** [`docs/2026-11-16-hr-payments-accounting-scope.md`](../docs/2026-11-16-hr-payments-accounting-scope.md).
   Its section 1 "Decided" table holds every owner decision, including those added 17 to 19 November.
3. **The design decisions:** [`docs/design/2026-11-19-design-sweep-k.md`](../docs/design/2026-11-19-design-sweep-k.md)
   (the final consistency sweep: 28 decisions and the owner's answers of 19 November) and
   [`docs/design/2026-11-17-redesign-scope-gaps.md`](../docs/design/2026-11-17-redesign-scope-gaps.md) (how every old
   board maps to the new menu, and every new board with its states).
4. **The boards themselves:** `design/canvas/`, read as the specification for each slice.

## What is in this folder
| Path | What it is |
|---|---|
| `canvas/` | The whole design: 92 boards (`*.dc.html`) and `canvas.json`, the layout and section titles. Identical to the published canvas, version 79. |
| `samples.md` | The one shared sample data set every board uses (companies, staff, payroll, leave, claims, approval forms, Next up rows, badges, card values), with the decisions behind it. |
| `samples-stage1.md` | The stage 1 sample data (books, SQL documents, trial balance, ledger, statutory) that `samples.md` builds on. |
| `motion-keyboard-spec.md` | Motion timings, focus, dialogs, menus, tabs, reduced motion and contrast rules the boards follow. |
| `tools/check_board.js` | Checks one board's format: `node design/tools/check_board.js design/canvas/Main.dc.html` prints OK or what is wrong. |
| `tools/check_imports.js` | Checks every board's imports of the shared parts: `node design/tools/check_imports.js design/canvas --strict` must report 0 problems. |
| `notes/design-leftovers.md` | Small things the design passes left open; the build plan's section 7.2 says what to do with each. |
| `notes/stage1-maps/` | Maps of the stage 1 code (screens, states, exact strings, code lines) made when the canvas was brought up to stage 1. |
| `notes/packageB-list.md` | How old board settings map to the new shell (history). |
| `briefs/` | The briefs each design package worked from (history; useful to see the rules the boards were drawn under). |

The fonts are in `static/fonts/`: Inter and Space Grotesk as variable `.woff2` files, `fonts.css` with the
`@font-face` rules, and both SIL Open Font License texts. Slice 0 links `/static/fonts/fonts.css` from `index.html`.

## Seeing the boards
- **Rendered:** the published canvas, https://claude.ai/artifact/FifhhSp76WmpJXqEpCeBJ9 (private to the owner). Its
  sections follow the new menu: Foundations and shared parts, Overview, Getting started, HR, Payroll, Payments,
  Accounting, Admin, Admin › Setup (three rows), Search and states, Printed, Phone, Dark mode.
- **As source:** a board is a Design Component. The `<x-dc>` template holds the markup with `{{name}}` holes,
  `<sc-for>` loops and `<sc-if>` blocks; `<dc-import name="Sidebar" …>` pulls in a shared part. The script
  (`class Component extends DCLogic`) holds the sample data and `renderVals()`, which works out every value the
  template shows. The `data-props` JSON lists the board's tweaks; `view` picks the state shown. The boards cannot
  render outside the canvas (they need its runtime), so read them as source and use the canvas to look.
- **Shared parts:** `Sidebar`, `Topbar`, `Icon` (80 two-tone glyphs), `SetupNav`. Reference boards: `Foundations`
  (tokens, components, the Overview card anatomy, the Approval marker, print rules), `DarkPalette`, `States` (empty,
  loading, error, many rows, refused, confirms, toasts with Undo), `ShellMenus` (the menu per company kind and access),
  `CompanySwitcher`, `OverviewCards` (every card in every state).

## Rules that carry over to the build
- **Real data stays out.** Never read or write `C:\HR-Records`. Every check runs against a temporary copy of the sample
  records with `HRP_DATA_DIR` set before `hrp` is imported.
- **Sample data is made up and stays in the design.** Do not copy the boards' names, figures or codes into the app,
  seed files or tests. New tests in `synthetic_tests/` use their own made-up data. Never take a person's name from the
  app's code or git history (one old placeholder name was a real person). The full IC numbers on the printed staff
  record use place code 00, which no real IC has.
- **Nothing is fixed to one company.** Every difference between companies is a setting (Kept in SQL Account / Kept
  here, Runs payroll in this app, approvers, leave policy, holidays, claim types).
- **On screen, never "stage 1" or "stage 2":** a company is "Kept in SQL Account" or "Kept here".
- **Phone design is deferred** by the owner. The five phone boards (`Mobile*.dc.html`) are the old design and are not
  built; today's narrow-screen layout stays.
- **Commits and pushes** only when the owner asks; one branch per slice.

## Keeping the design and the canvas in step
The published canvas is the master. If the build needs a design change, change the board on the canvas and copy the
changed `.dc.html` (and `canvas.json` if the layout moved) back into `design/canvas/`, so the repository copy never
drifts from what the owner sees.
