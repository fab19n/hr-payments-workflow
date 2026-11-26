"use strict";
/* ---------------- "It was saved" (slice 9a's helper in Setup; shared since step 0g) ----------------
   A change was kept (the server said so). What comes after it (reading the records and drawing the page again, opening the record's dialog
   again) can fail, and the change stays, so that is never "nothing was changed". Every action that changes something and then reads back
   goes through afterSaved(), after the change's own try (so a refusal is still said as a refusal).
   refresh(opts) reads and draws: render is one. It returns false when it painted the words itself (render() paints them for opts.saved, with
   its own Try again) or throws when it can't read; anything else means it worked. reopen() then opens the record's dialog again, once, if no
   other dialog has been opened or closed meanwhile.
   When the reading back fails, a message says it was saved, with a Try again that only runs refresh again: it never reopens a record, never
   closes a dialog and never sends the change again, and a page that painted the words doesn't get a message as well. The dialog of the change
   is closed on a failure only if nothing has been typed in it since (an Add dialog left open would add the record twice, and the page's words
   would be hidden behind it); one with something typed in it, or another dialog opened meanwhile, is left alone, and then the message is said
   too, as that dialog covers the page. The same closing when the record's dialog can't be opened again after a good reading. Typed also
   means files waiting for their type in the payment dialog, or one picked to replace a document and not confirmed.
   here: which dialog is the change's own: dialogHere(), asked before the change was sent from that dialog. WITHOUT IT THE CHANGE HAS NO
   DIALOG (a change made on a page, an Undo in a message, a change that has already closed its dialog): none is closed or counted as saved,
   whatever is on show. With it, once the change's own dialog has been closed, a dialog on show is another one: it isn't touched and nothing
   is opened again.
   dialogSaved: what the dialog holds was saved by this change, so only what is typed from now on counts: true for all of it, or a function that
   says which inputs (by id). Returns whether it all worked. */
async function afterSaved(refresh, reopen, { dialogSaved = false, here = null } = {}) {
  const own = !!here && here();
  if (own && dialogSaved && drawerShown() && state.drawerAt) {
    if (dialogSaved === true) watchDrawer();
    else { const now = drawerInputs(); for (const k in now) if (dialogSaved(k)) state.drawerAt[k] = now[k]; }
  }
  const at = DLG.seq, asked = DLG.asked, shown = own && drawerShown();
  const typed = () => Object.keys(unsavedEdits()).length > 0 || !!state.drawerDirty?.() || !!state.pay?.pick || !!state.pay?.ask?.file;
  const closeClean = () => { if (shown && DLG.seq === at && drawerShown() && !typed()) closeDrawer(true); };
  const said = () => toast(SAVED_NOT_READ, true, { ms: 0, action: { label: "Try again", fn: again } });
  const again = async () => {
    try { return (await refresh({ saved: true })) !== false; } catch (e) { said(); return false; }
  };
  let ok = false, thrown = false;
  try { ok = await refresh({ saved: true }); } catch (e) { thrown = true; }
  if (!thrown && ok !== false) {
    try { if (reopen && (!here || own) && DLG.seq === at && DLG.asked === asked) await reopen(); return true; }  // nor over a dialog asked for meanwhile
    catch (e) {
      toast(SAVED_NOT_REOPENED, true);
      closeClean();  // as after a failed reading: only a dialog nobody has typed in since, and still the one on show
      return false;
    }
  }
  closeClean();
  // said in a message when no page painted it, and when a dialog stays open over the page that did (its words are behind the dialog)
  if (thrown || drawerShown()) said();
  return false;
}

// The reading back of a change whose result the caller then writes into the page (a link, a check's result): true only when that very
// reading is now the page on show, drawn whole. It is false when it failed, and when the page was asked for again while it was read.
async function readBackPage() {
  let n;
  const ok = await afterSaved(opts => { const drawing = render(opts); n = PAGE.n; return drawing; });  // render() takes its number at once
  return ok && n === PAGE.n && pageWhole();
}

// The reading back of one part of a page (a bank review, the budget, a payroll check): that part, while still() says its page is the one on
// show; else the page now on show is drawn instead, which only reads too, and the part is never drawn over it. draw() throws when it can't read.
// still must tell the company and month apart too, as pageHere() does (asked before the change is sent).
const savedPart = (still, draw) => opts => still() ? draw() : render(opts);
// The same for a part the page's own draw writes too (the bank's year and review, a payroll check, a Books report). Drawn directly it takes
// the place of the page's draw of that part, so only on a page drawn whole: over one still being read (another company's, or the same one
// asked for again) it would, if it failed, leave that page with nothing. A part of its own (the budget's lines, the SQL preview) needs only
// savedPart.
const savedPagePart = (still, draw) => savedPart(() => still() && pageWhole(), draw);
