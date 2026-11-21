"use strict";
// Add a payment (the New payment dialog) is drawn by pages/payment.js.

// Drag-and-drop files onto a document box in the payment dialog: each file is added as that type, never replacing one;
// files dropped anywhere else in the dialog wait for their type to be chosen. Files dropped anywhere else would make the
// browser leave the app to show them, so that is stopped; a file box (on the Bank statements and SQL import pages) still
// takes its file.
const dragsFiles = ev => ev.dataTransfer?.types?.includes("Files") && !ev.target.closest?.("input[type=file]");
document.addEventListener("dragover", ev => { if (!dragsFiles(ev)) return; ev.preventDefault(); ev.target.closest?.("[data-slot]")?.classList.add("drag"); });
document.addEventListener("dragleave", ev => ev.target.closest?.("[data-slot]")?.classList.remove("drag"));
// Where a file dropped in the wrong place can go, on the page showing.
function dropHint() {
  if (state.openPayment && !$("#drawer").hidden) return "Drop the file onto the payment, or onto one of its document boxes.";
  if (state.view === "bank") return "Drop the statement PDF on the Choose file button under Statement PDF.";
  if (state.view === "sql") return "Drop the SQL export on the file box under Choose an exported file.";
  if (state.view === "payroll") return "Drop the payroll workbook on the Choose file button above Check the workbook.";
  if (state.view === "entity") return "Open the payment and drop the file on a document box. A checklist item's documents go on the Monthly checklist page.";
  if (state.view === "checklist") return "Use the + buttons on an item to file its documents.";
  return "Open a payment on the company's page and drop the file on a document box.";
}
document.addEventListener("drop", async ev => {
  if (!dragsFiles(ev)) return;
  ev.preventDefault();
  const s = ev.target.closest?.("[data-slot]"), inDlg = state.openPayment && state.pay && ev.target.closest?.("#drawer");
  if (!inDlg) return toast(dropHint());
  s?.classList.remove("drag");
  if (state.data?.closed_at) return toast(`${state.data.label} is filed, so its payments are read only. Reopen it on the Monthly checklist to add a file.`);
  const files = [...ev.dataTransfer.files];
  try {
    if (s) await pdUpload(files.map(file => ({ file, type: s.dataset.slot })));
    else pdAskTypes(payOf(state.openPayment), files);
  } catch (e) { toast(e.message, true); }
});
// Tabs (design/motion-keyboard-spec.md section 5): on a tab of the Payments register or the Monthly checklist, the arrow keys
// (wrapping), Home and End pick the tab and move the focus to it.
document.addEventListener("keydown", ev => {
  const t = ev.target, ds = t?.dataset || {}, kind = "regTab" in ds ? "regTab" : "clTab" in ds ? "clTab" : null;
  if (!kind || t.getAttribute?.("role") !== "tab" || !["ArrowRight", "ArrowLeft", "Home", "End"].includes(ev.key)) return;
  ev.preventDefault();
  const list = [...(t.parentNode?.querySelectorAll?.('[role="tab"]') || [])], i = list.indexOf(t), last = list.length - 1;
  if (i < 0) return;
  const to = ev.key === "ArrowRight" ? (i === last ? 0 : i + 1) : ev.key === "ArrowLeft" ? (i === 0 ? last : i - 1) : ev.key === "Home" ? 0 : last;
  (kind === "regTab" ? regPick : clPick)(list[to].dataset[kind], true);
});
// The register's search: each key narrows the list (the box keeps the focus); Escape empties it first.
document.addEventListener("input", ev => { if (ev.target.id === "regQ") regSearch(ev.target.value); });
// Escape closes the drawer (asking first if something typed would be lost); in the reason box it closes only that.
document.addEventListener("keydown", async ev => {
  if (ev.key !== "Escape" || DLG.asking) return;  // a confirm on top takes the Escape itself
  if (ev.target.id === "regQ" && ev.target.value) { ev.target.value = ""; return regSearch(""); }
  if (ev.target.closest?.("#setupWhy")) return hideWhy();
  if (payEscape()) return;   // in the payment dialog: an open menu, a question, the files waiting for their type, the viewer first
  await closeDrawer();
});
// The record dialog of Setup: the note beside Save follows what is typed; Enter in the reason box makes the change it asks for and never
// saves the record around it; the arrow keys, Home and End move between the rows of a list and between the tabs of a pair of sections.
document.addEventListener("input", ev => { if (ev.target.closest?.("#setupForm")) suFoot(); });
document.addEventListener("change", ev => { if (ev.target.closest?.("#setupForm")) suFoot(); });
document.addEventListener("keydown", ev => {
  if (ev.key === "Enter" && ev.target.id === "su-reason") { ev.preventDefault(); whySubmit().catch(e => toast(e.message, true)); return; }
  const t = ev.target, ds = t?.dataset || {};
  if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End"].includes(ev.key)) return;
  if ("setupOpen" in ds && t.closest?.("#setupList")) {
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") return;
    const list = [...document.querySelectorAll("#setupList [data-setup-open]")], i = list.indexOf(t), to = ev.key === "Home" ? 0 : ev.key === "End" ? list.length - 1 : i + (ev.key === "ArrowDown" ? 1 : -1);
    if (i < 0 || to < 0 || to >= list.length) return;
    ev.preventDefault(); list[to].focus({ preventScroll: false }); return;
  }
  if ("setupKind" in ds && t.getAttribute?.("role") === "tab") {
    if (ev.key === "ArrowUp" || ev.key === "ArrowDown") return;
    const list = [...(t.parentNode?.querySelectorAll?.('[role="tab"]') || [])], i = list.indexOf(t), last = list.length - 1;
    if (i < 0) return;
    ev.preventDefault();
    const to = ev.key === "ArrowRight" ? (i === last ? 0 : i + 1) : ev.key === "ArrowLeft" ? (i === 0 ? last : i - 1) : ev.key === "Home" ? 0 : last;
    list[to].click();
  }
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
  if (ev.target.id === "rc-stopped") return rcPick("stopped", ev.target.checked);  // Payments › Recurring: Show stopped
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
    await render(); syncAddr();
  } catch (e) { toast(e.message, true); }
});

