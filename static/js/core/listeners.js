"use strict";
function addPaymentDrawer() {
  if (!mayLeave()) return;
  state.openPayment = null; state.drawerDirty = null;
  const e = ent(), acct = defaultAccount(e)?.id;
  $("#drawer").innerHTML = `
    <div class="row spread"><h2>Add a payment</h2><button class="ghost small" id="closeDrawer">Close</button></div>
    <div class="note">For ad hoc payments, claims and receipts in ${monthName(state.month)}.</div>
    <form class="form" id="addForm" style="grid-template-columns:1fr 1fr">
      <label class="field" style="grid-column:1/-1"><span>Description</span><input id="ap-desc" required placeholder="e.g. Oct 2026 Claims - Soon"></label>
      <label class="field"><span>Type</span><select id="ap-cat">${typeOptions(oneOffType(), "out")}</select></label>
      <label class="field"><span>Money</span><select id="ap-dir"><option value="out">Paid out</option><option value="in">Received</option></select></label>
      <label class="field"><span>Amount</span><input id="ap-amt" type="number" step="0.01"></label>
      <label class="field"><span>Due date</span><input id="ap-due" type="date"></label>
      <label class="field" style="grid-column:1/-1"><span>Account</span><select id="ap-acct">${pickAccounts(e).map(a => acctOption(a, acct)).join("")}</select></label>
      <div class="row"><button class="btn" type="submit">Add payment</button></div>
    </form>`;
  $("#drawer").hidden = false;
  pairTypeDir($("#ap-cat"), $("#ap-dir"), { keep: oneOffType() });  // Received offers the types of money received; Paid out, the one-off default again
}

// Drag-and-drop files onto a document box in the payment drawer: each file is added, never replacing one. Files dropped
// anywhere else would make the browser leave the app to show them, so that is stopped; a file box (on the Bank
// statements and SQL import pages) still takes its file.
const dragsFiles = ev => ev.dataTransfer?.types?.includes("Files") && !ev.target.closest?.("input[type=file]");
document.addEventListener("dragover", ev => { if (!dragsFiles(ev)) return; ev.preventDefault(); ev.target.closest?.("[data-slot]")?.classList.add("drag"); });
document.addEventListener("dragleave", ev => ev.target.closest?.("[data-slot]")?.classList.remove("drag"));
// Where a file dropped in the wrong place can go, on the page showing.
function dropHint() {
  if (state.openPayment && !$("#drawer").hidden) return "Drop the file onto one of the document boxes.";
  if (state.view === "bank") return "Drop the statement PDF on the Choose file button under Statement PDF.";
  if (state.view === "sql") return "Drop the SQL export on the Choose file button under SQL export.";
  if (state.view === "payroll") return "Drop the payroll workbook on the Choose file button above Check the workbook.";
  if (state.view === "entity") return "Open the payment and drop the file on a document box, or use the + buttons on the checklist.";
  return "Open a payment on the company's page and drop the file on a document box.";
}
document.addEventListener("drop", async ev => {
  if (!dragsFiles(ev)) return;
  ev.preventDefault();
  const s = ev.target.closest?.("[data-slot]");
  if (!s || !state.openPayment) return toast(dropHint());
  s.classList.remove("drag");
  try { await uploadFiles([...ev.dataTransfer.files], { payment_id: state.openPayment, doc_type: s.dataset.slot }); } catch (e) { toast(e.message, true); }
});
// Escape closes the drawer (asking first if something typed would be lost); in the reason box it closes only that.
document.addEventListener("keydown", ev => {
  if (ev.key !== "Escape") return;
  if (ev.target.closest?.("#setupWhy")) return hideWhy();
  closeDrawer();
});
document.addEventListener("input", ev => {
  const id = ev.target.dataset?.search;
  if (id) { listState(id).q = ev.target.value; LIST_REDRAW[id]?.(); }
});
document.addEventListener("input", ev => { if (ev.target.id === "sqlPaste") state.sqlPaste[state.entity] = ev.target.value; });
document.addEventListener("input", ev => { if (ev.target.id === "trailReason") state.trail.reason = ev.target.value; });  // kept across redraws
// The SQL box holds one listing: pasting replaces what is in it, so a listing left there can't run into the next one.
document.addEventListener("paste", ev => {
  const text = ev.target.id === "sqlPaste" && ev.clipboardData?.getData("text");
  if (!text) return;
  ev.preventDefault(); ev.target.value = text; state.sqlPaste[state.entity] = text;
});
// Keeps the SQL page's lists open across a refresh (after Unlink); toggle doesn't bubble, so it is caught on the way down.
document.addEventListener("toggle", ev => { const k = ev.target.dataset?.sqlOpen; if (k) state.sqlOpen[k] = ev.target.open; }, true);
document.addEventListener("toggle", async ev => {
  const d = ev.target, k = d.dataset?.hist;
  if (!k || !d.open || d.dataset.loaded) return;
  const [tbl, key] = k.split(":"), body = d.querySelector(".hist-body");
  body.innerHTML = `<div class="note">Loading…</div>`;
  try { body.innerHTML = historyHtml(await api(`/api/audit/record/${tbl}/${key}`)); d.dataset.loaded = "1"; }
  catch (e) { body.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}, true);
document.addEventListener("change", ev => {
  const k = ev.target.dataset?.tf;
  if (k) {
    const v = ev.target.value;
    if (ev.target.type === "date" && v && !(v >= "2000-01-01" && v <= "2999-12-31")) return;  // a year still being typed
    state.trail.f[k] = v; return refreshTrailList();
  }
  if (ev.target.id === "trailShow") return trailShow(ev.target.checked);
  if (ev.target.matches?.("[data-setup-stopped]")) { state.setup.stopped = ev.target.checked; return LIST_REDRAW["setup-" + state.setup.kind]?.(); }
  if (ev.target.matches?.("[data-setup-deleted]")) { state.setup.deleted = ev.target.checked; return drawDeleted(ev.target.dataset.setupDeleted); }
  if (ev.target.id === "cl-from" && ev.target.closest?.("#chkForm")) return chkMonth();
  if (ev.target.id === "rm-from" && ev.target.closest?.("#remForm")) return remMonth();
  if (ev.target.closest?.("#chkForm, #remForm")) return setupPaint();
});
// A preview shown is of what was typed then: a change typed after it (other than the reason) takes it away.
document.addEventListener("input", ev => {
  if (!ev.target.closest?.("#chkForm, #chkCopyForm, #remForm") || /-reason$/.test(ev.target.id)) return;
  for (const el of document.querySelectorAll("#drawer [data-preview-out]")) el.innerHTML = "";
});
// Paste a list: a change to the text, who it is for or what they are takes the preview away (and Save with it); a
// column picked in the preview reads it again instead (the change listener).
document.addEventListener("input", ev => {
  if (!["ps-text", "ps-scope", "ps-kind"].includes(ev.target.id) || !state.setup.paste) return;
  Object.assign(state.setup.paste, { preview: null, previewFor: null, shown: null }); paintPaste();
});
// A code as SQL Account has it is typed in capitals; the cursor stays where it was.
document.addEventListener("input", ev => {
  const t = ev.target;
  if (!t.matches?.("input[data-upper]") || t.value === t.value.toUpperCase()) return;
  const a = t.selectionStart, b = t.selectionEnd;
  t.value = t.value.toUpperCase();
  try { t.setSelectionRange(a, b); } catch { /* not a text input */ }
});

// The current cycle and the month before are set up on their own; other months when you ask.
async function openCycleMonths() {
  try {
    for (const e of state.meta.entities.filter(isActive)) for (const m of [shiftMonth(currentCycle(), -1), currentCycle()])
      await api("/api/months/open", { json: { entity_id: e.id, month: m, auto: true } });
    return true;
  } catch (e) { toast(e.message, true); return false; }
}

// A day after the one the page last set up the cycle's months on, whichever way it is drawn again (a click, or the tab
// coming back): the new cycle's months are set up, and a page still on the cycle it was drawn in moves to the new one,
// unless a payment is open. state.day moves on only once the months are set up, so a failure is tried again.
async function newDay() {
  const [y, m, d] = state.day.split("-").map(Number);
  if (state.month === currentCycle(new Date(y, m - 1, d)) && !state.openPayment) state.month = currentCycle();
  if (await openCycleMonths()) state.day = dayKey();
  renderNav();
}

// A tab left open overnight: when it comes back into view on another day the page is drawn again (what fell due is
// flagged, and render sets up the new cycle); on the same day only the Next up list is read again.
document.addEventListener("visibilitychange", async () => {
  if (document.hidden || !state.meta) return;
  try {
    if (dayKey() === state.day) return await refreshNext(true);
    await render();
  } catch (e) { toast(e.message, true); }
});

