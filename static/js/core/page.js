"use strict";
/* ---------------- Page draws (step 0g) ----------------
   No page paints over a newer page. render() (core/shell.js) numbers every page as it is asked for (pageTurn), and whatever
   waits for the server before it draws a page, or a part of one, runs as a draw:

     async function viewThing(main) { return pageDraw("main", page => thingDraw(page, main)); }
     async function thingDraw(page, main) {
       const d = await page.read(api("/api/thing"));
       main.innerHTML = ...;                     // state, markup and messages only after page.read
     }

   page.read(promise) hands back the answer, or throws the failure, only while the draw is still wanted: no newer page has
   been asked for, and no later draw of the same part has started. Otherwise the draw ends at that line: nothing after it runs,
   so it writes no markup, no state and no message, and its caller (render(), a click handler) gets no error to show.
   Inside a draw:
     - every wait for the server is page.read, never a bare await; after awaiting another draw, call page.check() before
       writing anything;
     - a catch round a page.read starts with page.check(), or it takes the end of an overtaken draw for a failure (better: turn
       the failure into a value before the read, page.read(api(...).catch(e => ({ error: e.message }))));
     - what must happen whatever page is on show (a change sent to the server and what follows from it, a busy flag cleared)
       never waits behind page.read.
   An overtaken page is never drawn again by itself: the newer draw is the page.
   part: the name of what the draw writes into. Two draws of one part can race on one page (two tabs clicked quickly), so only
   the last one started counts, and draws of other parts are left alone. "main" is a whole page. null: only the page counts.
   A dialog that is read before it opens has the same rule, by the dialogs asked for, opened and closed (dialogDraw, core/dialog.js), and what a
   change made in a dialog does once the server answers asks first whether that dialog is still there (dialogHere). What is read back after a
   change goes through afterSaved (core/saved.js). While the page is being read, what is still on show can be clicked: what would then draw
   a part the page's own draw writes too (unless it paints its own failure there, as a Books report does), or write a change's result into
   the page, does so only while pageWhole(). What is picked there (a filter, a tick, a date) is not lost: the pick is kept, and the page's
   draw reads again for it before it writes (pages/trail.js, pages/budget.js). What waits for a page to follow something up (a link's
   record) waits with pageSettled, as the page can be asked for again while it is read. */
const PAGE = { n: 0, drawn: 0, saved: false, latest: null, parts: Object.create(null) };  // latest: the reading of the page asked for last (render)
// A new page is asked for (render() only): every draw asked for before is overtaken.
const pageTurn = () => ++PAGE.n;
// Whether the page asked for last has been drawn whole (render() sets PAGE.drawn). It hasn't while it is being read, even when it is the
// same company's and month's as the one before, whose content may still be on show; nor when it failed and shows why.
const pageWhole = () => PAGE.drawn === PAGE.n;
// Resolves once the page asked for last has been drawn, or says why it couldn't be. One asked for again while it is waited for (a late
// change's reading back, say, which ends the draw waited for before it has drawn) is waited for too. It stops once wanted() says no.
async function pageSettled(wanted = () => true) {
  let n;
  do { n = PAGE.n; await PAGE.latest; } while (n !== PAGE.n && wanted());
}
// Starts a page's draw (render() only). saved: it reads back a change that was kept, which the draws started by this call know of (a page
// that words its own failed read says it was saved, or lets the failure through to render()). A draw asked for later knows nothing of it.
function drawnAs(saved, start) {
  PAGE.saved = saved;
  try { return start(); } finally { PAGE.saved = false; }
}
// The draws of one part that are still reading are no longer wanted, though no new page was asked for.
function pageDrop(part) { return PAGE.parts[part] = (PAGE.parts[part] || 0) + 1; }

class Overtaken extends Error { constructor() { super("This page was left."); this.name = "Overtaken"; } }

// What a draw is handed: gone() says it is no longer wanted, check() ends it then, read() waits and checks. saved: the page is
// the reading back of a change that was kept (a page that says its own read failures lets them through to render() then).
function drawTicket(gone, saved) {
  const check = () => { if (gone()) throw new Overtaken(); };
  return { gone, check, saved, async read(promise) { let v; try { v = await promise; } catch (e) { check(); throw e; } check(); return v; } };
}
async function drawWhile(page, draw) {
  try { return await draw(page); }
  catch (e) {
    // A draw nobody waits for says nothing, whatever it met. A failure marked ofDraw is not its own: it is the failure of a draw that
    // was still wanted, which this one handed over to (the bank's year to the review it opens: one part, so the later draw makes the
    // earlier one count as overtaken), and it goes to whoever waits.
    if (page.gone() && !e?.ofDraw) return undefined;
    if (e && typeof e === "object") e.ofDraw = true;
    throw e;
  }
}
// Runs draw(page). The ticket is taken now, before anything is awaited. Resolves with what draw returns, or with nothing when
// the draw was overtaken.
function pageDraw(part, draw) {
  const n = PAGE.n, k = part ? pageDrop(part) : 0;
  return drawWhile(drawTicket(() => n !== PAGE.n || !!part && k !== PAGE.parts[part], PAGE.saved), draw);
}

// For an action that writes its result on the page once the server has answered: says whether the same page (company, month) is
// still the one on show. Ask before the first await. (The result of a change that was kept is still said, in a message.)
function pageHere() {
  const at = () => `${state.view}:${state.entity}:${state.month}`, was = at();
  return () => at() === was;
}
