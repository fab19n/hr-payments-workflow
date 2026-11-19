# HR Payments redesign: motion and keyboard spec

Applies to every board in `design-v48/project`. The audit found: no transitions anywhere, motion only on the payment
dialog (with a close timer that doesn't match its animation), no Escape / focus trap / focus return on any dialog or
menu, no visible focus ring on buttons, links or tabs, and tabs without `aria-selected` or arrow keys.

## 0. Format rules that must not be broken

Read `design-snapshot/artifact-type/reference/format.md` first. In particular:

- Holes are dotted lookups only (`{{a.b}}`), never expressions. Compute in `renderVals()`.
- Inside an `<sc-for>`, a hole may only start with that loop's variable (or an enclosing loop's variable), never a
  top-level name. If an item needs a top-level value, put it on the item in `renderVals()`.
- Every `<sc-if>` / `<sc-for>` keeps its `hint-*` attribute. Close every element; quote every attribute.
- **No global keydown handlers** (no `document.addEventListener`, no `window.onkeydown`). Keyboard handling is
  `onKeyDown="{{fn}}"` on the element itself (the dialog, the menu, the tablist, the input). Calling `.focus()` on an
  element found with `document.getElementById` from `componentDidUpdate` is fine (the SQL board already does it).
- No code before `class Component extends DCLogic`. Helpers go inside the class or inside `renderVals()`.
- A shared component (Sidebar, Topbar, SetupNav, Icon) is mounted with `<dc-import>`; its own `<helmet>` should hold
  only fonts and `body{margin:0}` plus what it already has. Rules that style it on a page go in the page's helmet.
- Ids must be unique within a board. Prefix new ids with the board's short name (`co-`, `pay-`, `mp-`, …).
- Change only what this spec asks. Keep all copy, data, layout and behaviour otherwise as it is.

## 1. Motion tokens

| Token | Duration | Curve | Used for |
|---|---|---|---|
| `fast` | 120ms | `ease-out` | hover, press and focus colour; chevron turn |
| `base` | 180ms | enter `cubic-bezier(.22,1,.36,1)` | menus and popovers opening, disclosure content, tab panel swap, toasts leaving |
| `enter` | 240ms | `cubic-bezier(.22,1,.36,1)` | dialogs, sheets, toasts arriving, revealed results |
| `exit` | 180ms | `cubic-bezier(.4,0,1,1)` | dialogs and sheets leaving |
| `dim` | 200ms in / 150ms out | `ease-out` / `ease-in` | backdrop |
| `progress` | 320ms | `cubic-bezier(.2,0,0,1)` | progress bars and rings changing width or angle |
| `flash` | 900ms | `ease-out` | a row that just changed, or that a link landed on: brand tint `#EAF0FD` (dark `#1B2B4A`) fading to its own background |

Movement is small: rise 8px, menus scale from .96, dialogs translateY(12px) scale(.97). Nothing bounces, nothing
loops except spinners and skeletons.

## 2. The base helmet block (every page board)

Add this to the page's `<helmet><style>` (adapt the class list to the hover classes the board already has; keep the
board's existing hover rules). Dark boards use ring colour `#8DB0FA` instead of `#2450B8`.

```css
/* motion and focus base */
.hb,.hs,.hr,.hg,.mi,.dz,.nb,.nv,.sn,.pr{transition:background-color .12s ease-out,border-color .12s ease-out,color .12s ease-out,box-shadow .12s ease-out}
:where(button,a,summary,[tabindex]):focus-visible{outline:2px solid #2450B8;outline-offset:2px}
:where(input,select,textarea):focus-visible{outline:2px solid #2450B8;outline-offset:-1px}
.nv:focus-visible,.nb:focus-visible{outline-color:#8DB0FA}            /* the dark sidebar */
.fr:focus-visible{outline-offset:-2px}                               /* full-width rows and tabs inside overflow:hidden */
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes unfold{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
@keyframes menuIn{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:none}}
@keyframes flashA{from{background-color:#EAF0FD}}
@keyframes flashB{from{background-color:#EAF0FD}}
.rv{animation:rise .24s cubic-bezier(.22,1,.36,1) both}
.ex{animation:unfold .18s cubic-bezier(.22,1,.36,1) both}
.mn{transform-origin:top right;animation:menuIn .18s cubic-bezier(.22,1,.36,1) both}
.chev{display:inline-flex;transition:transform .18s cubic-bezier(.22,1,.36,1)}
.chev.on{transform:rotate(90deg)}
.bar{transition:width .32s cubic-bezier(.2,0,0,1),background-color .32s ease-out}
.fa{animation:flashA .9s ease-out}
.fb{animation:flashB .9s ease-out}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{animation-duration:1ms !important;animation-delay:0s !important;animation-iteration-count:1 !important;transition-duration:1ms !important;scroll-behavior:auto !important}}
```

- Remove `outline: 0` / `outline:0` from inline styles of controls that can take focus, unless a parent shows the ring
  instead with `.fx:focus-within{outline:2px solid #2450B8;outline-offset:1px}` (add that rule when you use it).
- A chevron that changes between `chevronRight` and `chevronDown` becomes one `chevronRight` inside
  `<span class="{{x.chevCls}}">` where `chevCls` is `'chev'` or `'chev on'`.
- Content that appears when a row or section opens gets `class="ex"`. A new result card gets `class="rv"`.
- To replay a flash on a row each time it changes, alternate its class between `fa` and `fb` (a counter in state).
- Progress bars get `class="bar"` on the moving element (their width stays an inline style).

## 3. Dialogs (payment dialog, search, notifications, confirm dialogs, mobile sheets)

Markup:
- The panel has `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing at its heading, `tabindex="-1"` and
  `onKeyDown="{{dlgKey}}"`. The heading has an id and `tabindex="-1"`.
- The backdrop closes on click (keep it `aria-hidden="true"`).
- Every dialog has a visible close button with `aria-label`.

Motion (replace any older numbers):
```css
@keyframes dimIn{from{opacity:0}to{opacity:1}}
@keyframes dimOut{from{opacity:1}to{opacity:0}}
@keyframes popIn{from{opacity:0;transform:translateY(12px) scale(.97)}to{opacity:1;transform:none}}
@keyframes popOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(8px) scale(.98)}}
.dim-in{animation:dimIn .2s ease-out both}
.dim-out{animation:dimOut .15s ease-in both}
.dr-in{animation:popIn .24s cubic-bezier(.22,1,.36,1) both}
.dr-out{animation:popOut .18s cubic-bezier(.4,0,1,1) both}
```
Mobile sheets slide instead: `@keyframes sheetIn{from{transform:translateY(100%)}to{transform:none}}`,
`sheetOut` the reverse, `.sh-in{animation:sheetIn .24s cubic-bezier(.22,1,.36,1) both}`,
`.sh-out{animation:sheetOut .18s cubic-bezier(.4,0,1,1) both}`.

Closing is finished by the animation, not a guessed timer:
```js
closeDrawer() {
  if (!this.state.open || this.state.closing) return;
  const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (calm) return this.finishClose();
  this.setState({ closing: true, menu: null });
  clearTimeout(this._t);
  this._t = setTimeout(() => this.finishClose(), 400);   // only a safety net if animationend never arrives
}
finishClose() { clearTimeout(this._t); if (this.state.open) this.setState({ open: null, closing: false, menu: null }); }
```
and on the panel `onAnimationEnd="{{onPanelAnim}}"` with
`onPanelAnim: e => { if (this.state.closing && e.target === e.currentTarget) this.finishClose(); }`.

Focus:
- On open, remember the opener: `this._opener = document.activeElement` (inside the click handler, before setState).
- In `componentDidUpdate(prevProps, prev)`: when the dialog has just opened, focus its heading
  (`document.getElementById('<prefix>-title')?.focus({ preventScroll: true })`); when it has just closed, focus
  `this._opener` if it is still in the document (`this._opener && this._opener.isConnected`).
- `dlgKey`:
  - `Escape`: if a menu inside is open, close the menu and return focus to its button; otherwise close the dialog.
    Call `e.stopPropagation()`.
  - `Tab` / `Shift+Tab`: keep focus inside: find focusables in `e.currentTarget` with
    `querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')`;
    wrap from last to first and first to last with `preventDefault()`.
- Switching to another payment while the dialog is open (where the board allows it) cross-fades the body: alternate a
  class `swapA`/`swapB` (`@keyframes swapA{from{opacity:.0}}` and the same for `swapB`, 120ms ease-out).
- After closing a dialog in which something changed, flash the row that opened it (section 2, `fa`/`fb`).

## 4. Menus (the ⋯ more-actions menus, account menus)

- Button: `aria-haspopup="menu"`, `aria-expanded`, an id (`<prefix>-mb-<key>`), `onKeyDown` that opens the menu on
  `ArrowDown` / `Enter` / `Space` and focuses the first item.
- Menu: `role="menu"`, `class="mn"` (scale and fade from the corner it hangs from; use
  `transform-origin: top left` when it opens to the right), `onKeyDown="{{menuKey}}"`.
- Items: `role="menuitem"`, `tabindex="-1"`, ids `<prefix>-mi-<key>-<n>`. `ArrowDown` / `ArrowUp` move (wrapping),
  `Home` / `End` jump, `Escape` closes and focuses the button, `Tab` closes the menu. Picking an item closes the menu
  and returns focus to the button.
- A click outside closes it: render, while open, a transparent catcher before the menu
  (`<div aria-hidden="true" onClick="{{closeMenu}}" style="position: fixed; inset: 0; z-index: <menu z-index - 1>"></div>`).
- Focus moves with `componentDidUpdate` (menu just opened: focus item 0) or directly in the key handler with
  `document.getElementById(...)`.
- Mobile action sheets follow the same keys and slide up (section 3).

## 5. Tabs, segmented controls and disclosure rows

- Tabs: container `role="tablist"` with `aria-label`; each tab `role="tab"`, `id`, `aria-selected="true|false"`,
  `aria-controls` the panel id, roving `tabindex` (`0` on the selected tab, `-1` on the others) and
  `onKeyDown="{{t.key}}"`: `ArrowRight` / `ArrowLeft` (wrap), `Home`, `End` select and focus the tab. The panel has
  `role="tabpanel"` and `aria-labelledby` the selected tab. Add `class="fr"` to tabs inside `overflow: hidden`.
  When the tab changes, the panel content gets `class="ex"` (or alternate `swapA`/`swapB`) so the change is seen.
- An underline tab indicator: keep it as a `border-bottom` and add `transition: border-color .12s ease-out, color .12s ease-out` to the tab style.
- Segmented controls (a row of buttons where one is chosen, e.g. company AISB / AI, filters): `role="group"` with
  `aria-label`, each button `aria-pressed="true|false"`. The chosen button's background and shadow change with the
  `fast` transition (add it to the button's inline style).
- Disclosure rows (audit trail entries, tree groups, collapsible lists): native `<button>` with `aria-expanded`, the
  chevron turns (section 2), the opened content gets `class="ex"`, full-width buttons in `overflow:hidden` get `fr`.
  Do not point `aria-controls` at an id that exists only while open.

## 6. Status, counts, toasts and loading

- Status pills that change (Missing → Complete, Open → Explained): give the pill a class that alternates `swapA`/`swapB`
  when its text changes (or a one-off `rv` on the new state) so the change is seen; when something becomes complete,
  one ring pulse: `@keyframes pulse{from{box-shadow:0 0 0 0 rgba(14,138,80,.45)}to{box-shadow:0 0 0 8px rgba(14,138,80,0)}}` 400ms, once.
- Progress bars and rings: `bar` class (rings: add `transition: background .32s` won't animate a conic-gradient, so
  leave rings as they are).
- Toasts (States board and any board that shows one): enter `rise` 240ms from the bottom, leave 180ms (`toastOut`:
  `to{opacity:0;transform:translateY(8px)}`), `role="status"` (errors `role="alert"`), stay 6s, pause while hovered or
  focused (show this as a rule in Foundations; the mock may show a static toast).
- Buttons that start work show a busy state: label changes, a 16px spinner replaces the icon, the width does not jump,
  `aria-busy="true"`, `disabled`. Spinner: `@keyframes spin{to{transform:rotate(360deg)}}`, 700ms linear infinite.
- Skeletons keep their shimmer (1.4s linear infinite) and stop under reduced motion (the base block does that).

## 7. Touch and size

- Mobile boards: every control at least 44px tall; desktop at least 32px.
- Focus rings must not be clipped: use `fr` (offset -2px) for controls flush with an `overflow:hidden` edge.

## 8. Foundations board additions

Add two sections to Foundations, in its visual style:
1. **Motion**: the token table from section 1 as cards (name, duration, curve, where) with a small live demo for
   each that plays on hover or on a "Play" button (respecting reduced motion), and one line on reduced motion:
   "Reduce motion in the system settings turns every movement into an instant change; nothing is lost."
2. **Focus and keyboard**: the focus ring (light and dark), and the keyboard map: Dialogs (Esc closes, Tab stays
   inside, focus returns to what opened it), Menus (↓ ↑ Home End, Esc), Tabs (← →, Home, End), Search (Ctrl K opens,
   ↑ ↓ moves, Enter opens, Esc closes), Lists (Enter opens a row), Toasts (stay 6s, pause on hover or focus). Use the
   two-tone icons from `Icon.dc.html` and plain text for key names in a `<kbd>`-styled span, not emoji.
   The board's `$preview` and its `h` in canvas.json may need to grow; report the new height.

## 9. What to report

For each board: what you changed (motion, focus, keyboard), anything in this spec you could not do and why, and the
result of `node <scratchpad>/check_board.js <file>`, which must print `OK`.
