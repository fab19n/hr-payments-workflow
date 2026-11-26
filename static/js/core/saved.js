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
   would be hidden behind it); one with something typed in it, or another dialog opened meanwhile, is left alone (the payment dialog left open
   gets the message too, as it covers the page). The same when the record's
   dialog can't be opened again after a good reading. dialogSaved: what the dialog holds was saved by this change, so only what is typed from
   now on counts: true for all of it, or a function that says which inputs (by id). Returns whether it all worked. */
async function afterSaved(refresh, reopen, { dialogSaved = false } = {}) {
  if (dialogSaved && drawerShown() && state.drawerAt) {
    if (dialogSaved === true) watchDrawer();
    else { const now = drawerInputs(); for (const k in now) if (dialogSaved(k)) state.drawerAt[k] = now[k]; }
  }
  const at = DLG.seq, shown = drawerShown();
  const typed = () => Object.keys(unsavedEdits()).length > 0 || !!state.drawerDirty?.();
  const closeClean = () => { if (shown && DLG.seq === at && drawerShown() && !typed()) closeDrawer(true); };
  const said = () => toast(SAVED_NOT_READ, true, { ms: 0, action: { label: "Try again", fn: again } });
  const again = async () => {
    try { return (await refresh({ saved: true })) !== false; } catch (e) { said(); return false; }
  };
  let ok = false, thrown = false;
  try { ok = await refresh({ saved: true }); } catch (e) { thrown = true; }
  if (!thrown && ok !== false) {
    try { if (reopen && DLG.seq === at) await reopen(); return true; }
    catch (e) {
      toast(SAVED_NOT_REOPENED, true);
      closeClean();  // as after a failed reading: only a dialog nobody has typed in since, and still the one on show
      return false;
    }
  }
  closeClean();
  // said in a message when no page painted it, and when the payment dialog stays open over the page that did (something typed in it)
  if (thrown || Object.keys(unsavedEdits()).length) said();
  return false;
}

// The reading back of one part of a page (a bank review, the budget, a payroll check): that part, while still() says its page is the one on
// show; else the page now on show is drawn instead, which only reads too, and the part is never drawn over it. draw() throws when it can't read.
const savedPart = (still, draw) => opts => still() ? draw() : render(opts);
