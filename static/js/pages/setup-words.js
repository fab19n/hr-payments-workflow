"use strict";
/* ---- Matching words: the Move grip and Try a voucher description (design/canvas/SetupMatching.dc.html) ----
   A list the server calls ordered (spec.ordered: the payment type guesses and the filing words) tries its rules in order, and the first
   that matches wins. Its rows show their place in that order (every rule counted, stopped ones too: the Order column) and a Move grip.
   The grip is dragged, or pressed (click, Enter or Space) to pick the rule up, moved with Up and Down, and pressed again to drop it;
   Tab drops it too, as does moving to another control of the list's page that opens nothing over it (rankDropsTo); Escape puts it back.
   Only a drop sends anything: the whole new order, with the order the list showed, which the server saves as each rule's Order field, or
   refuses when another change came first. While one is being saved no other move starts. Nothing says it was saved before the server has
   said so; with no clear answer the list is read again.
   Try a voucher description (spec.tried: the payment type guesses) asks the server which rule matches the text typed, so it answers by
   the very matching that adds SQL vouchers: no rule is matched here. It answers for the saved order only.
   Not sortable and not cut into pages of 25: a place in the order means nothing in another order, and a rule is moved among them all. */
// list: the ordered list drawn last (below); saving: a new order is on its way to the server; press: a pointer down on a grip, and
// whether it has become a drag; quiet: the click a drag's release raises is not a pick up.
const RANK = { list: null, saving: false, press: null, quiet: false, timer: null };

// The ordered list setupList has just drawn. rows: as the page shows them; saved: their ids as the server keeps them; held: the rule
// picked up, from: the rows as they were then; answer: Try's last answer and the text it was for.
function rankNew(box, kind, spec, rows) {
  if (RANK.list?.kind === kind) rankLost(RANK.list);  // the same list drawn again takes a rule picked up with it
  rankDragOff();
  return RANK.list = { id: "setup-" + kind, kind, box, nameKey: spec.name_field, tried: !!spec.tried, rows, saved: rows.map(r => r.id), held: null, from: null, flash: null, answer: null, painting: false };
}
// Whether the list is still the one on show: not once another list or page was drawn, or asked for (what is on show then is the old one).
const rankOn = L => !!L && RANK.list === L && state.view === "setup" && state.setup.kind === L.kind && !L.box.page?.gone() && !!$("#setupList");
const rankSearching = L => !!listState(L.id).q.trim();
const rankOff = L => RANK.saving || rankSearching(L);  // no move starts
const rankShown = r => state.setup.stopped || r.status !== "stopped";
const rankPos = (L, id) => L.rows.findIndex(r => r.id === id) + 1;
const rankHelp = L => rankSearching(L) ? "Clear the search to change the order." : "To change the order, drag the move button, or press it, then Up or Down, and Space to drop.";
function rankSay(words) { const el = $("#rank-say"); if (el) el.textContent = words; }
// The rule Try's answer names, with its words found: only while the answer is for what is typed now and the order on show is the saved one.
function rankHit(L) {
  const a = L.answer;
  return a && L.held == null && !RANK.saving && a.text === (state.setup.probe || "") && a.r.rule_id != null ? { id: a.r.rule_id, words: a.r.words || [] } : null;
}

// The table: the Move grip, the place in the order, the list's own columns with the name as the button that opens the rule, Used by and
// Status. cell, usedCell, statusCell and emptyRow are the shared list's (pages/setup.js setupList).
function rankTable(L, { cols, cell, text, usedCell, statusCell, emptyRow }) {
  const q = listState(L.id).q.trim(), shown = L.rows.filter(rankShown), list = q ? shown.filter(r => LT.match(text(r), q)) : shown;
  setCount(L.id, list.length, L.rows.length);
  const hit = rankHit(L), off = rankOff(L);
  const row = r => {
    const n = rankPos(L, r.id), held = L.held === r.id, found = hit?.id === r.id, name = r[L.nameKey] || "(no name)";
    const grip = `<button type="button" class="rank-grip" id="rank-grip-${+r.id}" data-grip="${+r.id}" aria-label="${esc(`Move ${name}, position ${n} of ${L.rows.length}`)}" aria-pressed="${held}" aria-describedby="rank-help"${off ? ` aria-disabled="true"` : ""}>${icon("grip")}</button>`;
    const td = c => c.key === "sort" ? `<td><span class="rank-n">${n}</span></td>`
      : c.key === L.nameKey ? `<td><button type="button" class="link st-name" data-setup-open="${+r.id}" aria-haspopup="dialog">${esc(name)}</button></td>`
      : c.key === "words" && L.tried ? `<td><div class="mt-words">${asList(r.words).map(w => `<span class="mt-word${found && hit.words.includes(w) ? " hit" : ""}" data-word="${esc(w)}">${esc(w)}</span>`).join("")}</div></td>`
      : cell(r, c);
    return `<tr class="st-row${r.status === "stopped" ? " stopped" : ""}${held ? " rank-held" : ""}${found ? " mt-hit" : ""}${L.flash === r.id ? " rank-flash" : ""}" data-setup-row="${+r.id}"><td class="rank-move">${grip}</td>${cols.map(td).join("")}${usedCell(r)}${statusCell(r)}</tr>`;
  };
  return `<table class="st-table rank-table"><thead><tr><th scope="col"><span class="sr-only">Move</span></th>${cols.map(c => `<th scope="col">${esc(c.label)}</th>`).join("")}<th class="num">Used by</th><th>Status</th></tr></thead><tbody>
      ${list.map(row).join("") || emptyRow(cols.length + 3, shown.length, L.rows.length)}
      </tbody></table>`;
}
// The note above the table, and the place a screen reader is told what a move did.
const rankNoteHtml = L => `<div class="note">Click a row to change it. The first rule that matches wins, so order matters. <span id="rank-help">${esc(rankHelp(L))}</span></div>
      <div class="sr-only" id="rank-say" role="status" aria-live="assertive"></div>`;

// The list is drawn again (a search, Show stopped): a search takes a rule picked up back to where it was, as the order can't change then.
function rankRedrawing(L) {
  if (L.held != null && rankSearching(L)) { L.rows = L.from; L.held = L.from = null; rankDragOff(); rankSay("Cancelled, back where it was."); tryPaint(); }
  const help = $("#rank-help");
  if (help) help.textContent = rankHelp(L);
}
// The grip or the rule's name that has the focus, as a way to find it again once the rows are drawn again; else null.
function rankSpot() {
  const d = document.activeElement?.dataset;
  return d?.grip ? `[data-grip="${+d.grip}"]` : d?.setupOpen ? `[data-setup-open="${+d.setupOpen}"]` : null;
}
// Runs draw, which reads the list of this kind again (an order refused or not answered, or its section drawn again while it was saved) and
// so replaces the grip or name that had the focus: it goes back to its twin, unless something else has the focus by then.
async function rankKeepFocus(kind, draw) {
  const on = rankSpot();
  const ok = await draw();
  if (on && focusLost() && state.view === "setup" && state.setup.kind === kind) $("#setupList")?.querySelector(on)?.focus?.({ preventScroll: true });
  return ok;
}
// Draws the rows again. focus: where the focus goes (a grip being moved keeps it); without one it stays on the same grip or name if it
// was on one, and is left alone anywhere else.
function rankRedraw(L, focus, still = true) {
  const was = rankSpot();
  L.painting = true;  // the grip that has the focus is replaced: that is not leaving it
  try {
    LIST_REDRAW[L.id]?.();
    const to = focus || was;
    if (to) $("#setupList")?.querySelector(to)?.focus?.({ preventScroll: still });
  } finally { L.painting = false; }
}
// The grips as they stand now (picked up, or off), without drawing the rows again: the focus may be on its way to another control.
function rankMarks(L) {
  if (!rankOn(L)) return;
  const off = rankOff(L);
  for (const b of $("#setupList").querySelectorAll("[data-grip]")) {
    const held = +b.dataset.grip === L.held;
    b.setAttribute("aria-pressed", String(held));
    if (off) b.setAttribute("aria-disabled", "true"); else b.removeAttribute("aria-disabled");
    b.closest("tr")?.classList.toggle("rank-held", held);
  }
}

function rankPickUp(L, id) {
  if (rankOff(L)) { if (RANK.saving) rankSay("The last move is still being saved."); return false; }
  L.held = id; L.from = L.rows.slice(); L.flash = null;
  rankSay(`Picked up. Position ${rankPos(L, id)} of ${L.rows.length}. Use Up and Down to move, Space to drop, Escape to cancel.`);
  rankMarks(L); tryPaint();
  return true;
}
// One place up or down among all the rules: a step can pass a stopped rule that is hidden.
function rankStep(L, dir) {
  const i = rankPos(L, L.held) - 1, j = i + dir, n = L.rows.length;
  if (j < 0 || j >= n) return rankSay(dir < 0 ? "Already first." : "Already last.");
  const rows = L.rows.slice(), passed = !rankShown(rows[j]);
  [rows[i], rows[j]] = [rows[j], rows[i]];
  L.rows = rows;
  rankRedraw(L, `[data-grip="${+L.held}"]`, false);
  rankSay(`Moved to position ${j + 1} of ${n}${passed ? ", past a stopped rule that is hidden" : ""}.`);
}
function rankCancel(L) {
  if (L.held == null) return;
  L.rows = L.from; L.held = L.from = null;
  rankRedraw(L);
  rankSay("Cancelled, back where it was.");
  tryPaint();
}
function rankDrop(L) {
  if (L.held == null) return;
  const id = L.held, ids = L.rows.map(r => r.id);
  L.held = L.from = null;
  if (ids.join() !== L.saved.join()) return rankSave(L, id, ids);
  rankSay(`Dropped at position ${ids.indexOf(id) + 1} of ${ids.length}, where it was.`);
  rankMarks(L); tryPaint();
}

// Saves the order a drop gives. One at a time. The change is on the page, not in a dialog (afterSaved, core/saved.js).
async function rankSave(L, moved, ids) {
  if (RANK.saving) return;
  const at = ids.indexOf(moved) + 1, of = ids.length, words = `Dropped at position ${at} of ${of}. Applies to SQL imports from now on.`;
  RANK.saving = true;
  rankSay("Saving the new order."); rankMarks(L); tryPaint();
  let r, failed;
  try { r = await api(`/api/setup/${L.kind}/order`, { json: { ids, was: L.saved, moved } }); }
  catch (e) { failed = e; }
  finally { RANK.saving = false; }
  rankMarks(RANK.list);  // also a list drawn while it was being saved
  if (failed) return rankNotSaved(L, failed);
  if (!rankOn(L)) toast(`The new order is saved. ${words}`);  // the list that would say so is no longer on show
  if (state.view !== "setup" || state.setup.kind !== L.kind) return;  // nothing on show holds this order: nothing to read back or draw again
  const readBack = savedPagePart(() => rankOn(L), async () => {
    L.rows = r.rows; L.saved = r.rows.map(x => x.id); L.flash = moved;
    rankRedraw(L);
    L.flash = null;  // it fades once: a later search doesn't light it again
    rankSay(words);
    tryRun();
  });
  return afterSaved(opts => rankKeepFocus(L.kind, () => readBack(opts)));
}
// Refused: nothing was changed. No clear answer: it isn't known whether it was saved. Either way the list, if it is still the one on show,
// is read again, so it shows the order the records have.
function rankNotSaved(L, e) {
  toast(e.unsure ? `The new order: ${changeError(e)}` : `The new order wasn't saved. ${e.message} Nothing was changed.`, true);
  const now = RANK.list;
  if (!rankOn(now) || now.kind !== L.kind) return;
  rankSay(e.unsure ? "It isn't known whether the new order was saved." : "The new order wasn't saved.");
  return rankKeepFocus(L.kind, () => render(e.unsure ? { unsure: true } : undefined));
}

/* The drag. boxes: the rows on show, in order, [{id, top, height}], the dragged one among them. It goes before the first other row whose
   middle is below the pointer, else after the last one. Rules not on show keep their places, and nothing changes while the order on show
   stays as it is. */
function rankDragOrder(rows, id, boxes, y) {
  const me = rows.find(r => r.id === id), others = boxes.filter(b => b.id !== id);
  if (!me || !others.length) return rows;
  const at = others.findIndex(b => y < b.top + b.height / 2), next = others.map(b => b.id);
  next.splice(at < 0 ? next.length : at, 0, id);
  if (next.join() === boxes.map(b => b.id).join()) return rows;
  const rest = rows.filter(r => r !== me), near = at < 0 ? others[others.length - 1] : others[at];
  rest.splice(rest.findIndex(r => r.id === near.id) + (at < 0 ? 1 : 0), 0, me);
  return rest;
}
function rankDragTo(L, id, y) {
  const boxes = [...$("#setupList").querySelectorAll("tr[data-setup-row]")].map(tr => {
    const b = tr.getBoundingClientRect();
    return { id: +tr.dataset.setupRow, top: b.top, height: b.height };
  });
  const rows = rankDragOrder(L.rows, id, boxes, y);
  if (rows === L.rows) return;
  L.rows = rows;
  rankRedraw(L, `[data-grip="${+id}"]`);
}
// The pointer is no longer pressing or dragging a grip.
function rankDragOff() {
  const was = RANK.press;
  RANK.press = null;
  if (was?.dragging) document.body?.classList?.remove("rank-dragging");
  return was;
}
function rankDragEnd(drop) {
  const P = rankDragOff();
  if (!P?.dragging) return;
  RANK.quiet = true; setTimeout(() => { RANK.quiet = false; }, 0);
  if (P.over || !rankOn(P.L)) return;  // over: Escape ended it before the button was let go
  return drop ? rankDrop(P.L) : rankCancel(P.L);
}
// A rule picked up that has been moved goes without having been dropped, and not by your own Escape or search: that is said.
const RANK_LOST = "The rule you were moving is back where it was: its new place wasn't saved.";
function rankLost(L) {
  if (L.held != null && L.rows.some((r, i) => r.id !== L.saved[i])) toast(RANK_LOST);
}
// Puts back a rule picked up or dragged on the list on show. False: there is none.
function rankPutBack() {
  const L = RANK.list;
  if (!L || L.held == null || !rankOn(L)) return false;
  // A drag ends here, but the button may still be down: the press is kept until it is let go, so the click that raises is kept back too.
  if (RANK.press?.dragging) { RANK.press.over = true; document.body?.classList?.remove("rank-dragging"); } else rankDragOff();
  rankCancel(L);
  return true;
}
// Escape while a rule is picked up or dragged puts it back, and does nothing else (core/listeners.js asks first).
function rankEscape(ev) {
  if (!rankPutBack()) return false;
  ev.preventDefault?.(); ev.stopPropagation?.();
  return true;
}
// A dialog is about to cover the list (showDrawer, core/dialog.js: a click on a row opens its rule with nothing else leaving the grip): a
// rule picked up goes back first, so it is never held behind the dialog, where Escape and the dialog's Save would meet it unseen.
function rankCovered() {
  const L = RANK.list;
  if (!rankOn(L)) return;
  rankLost(L);
  rankPutBack();
}
// A Setup section is drawn: a rule picked up on another section's list went when that list was left, so nothing says so later.
function rankSection(kind) {
  if (RANK.list && RANK.list.kind !== kind) RANK.list.held = null;
}
// Another page is opened (setupLeft, pages/setup.js): a rule picked up there is not saved, and what was typed in Try is dropped. A move
// already sent stays sent, and says what came of it in a message.
function rankLeft() {
  rankDragOff();
  clearTimeout(RANK.timer);
  RANK.list = null; state.setup.probe = "";
}

/* ---- Try a voucher description ---- */
const tryHtml = () => `<section class="card mt-try" aria-labelledby="mt-try-l">
      <label class="field" for="mt-try"><span id="mt-try-l">${icon("search")}Try a voucher description</span>
        <input id="mt-try" type="text" value="${esc(state.setup.probe || "")}" autocomplete="off" spellcheck="false" aria-describedby="mt-result mt-try-note"></label>
      <div id="mt-result" class="mt-result" role="status"></div>
      <div class="note" id="mt-try-note">For a voucher that pays money out. One that brings money in is always added as ${esc(state.meta.categories?.receipt || "Money received")}, whatever its words.</div></section>`;
// The server's answer in words: [glyph, tone, sentence].
function tryWords(r) {
  if (r.error) return ["alert", "none", `The description couldn't be tried. ${r.error}`];
  if (r.rule_id == null) return ["help", "none", `No rule matches. The payment would be added as ${r.label}, for you to set.`];
  if (r.payment_type !== r.rule_type) return ["alert", "none", `Rule ${r.position} (${r.rule_name}) matches, but its payment type, ${r.rule_type_label}, isn't offered for money out, so the payment would be added as ${r.label}, for you to set.`];
  return ["check", "ok", `Rule ${r.position} (${r.rule_name}) matches: the payment type is ${r.label}.`];
}
// The result under the box, and the matching row and words marked in the list.
function tryPaint() {
  const L = RANK.list, el = $("#mt-result");
  if (!L || !L.tried || !el) return;
  const text = state.setup.probe || "";
  let [glyph, tone, words] = ["help", "none", ""];
  if (!text.trim()) words = "Type a voucher description to see which rule matches it.";
  else if (L.held != null || RANK.saving) words = "The new order isn't saved yet. The description is tried again once it is.";
  else if (!L.answer) words = "Trying it…";
  else [glyph, tone, words] = tryWords(L.answer.r);
  const stale = !!text.trim() && !!L.answer && L.answer.text !== text;  // dimmed until the answer for what is typed now comes
  el.className = `mt-result ${tone}${stale ? " stale" : ""}`;
  const html = `${icon(glyph)}<span>${esc(words)}</span>`;
  if (el.said !== html) { el.said = html; el.innerHTML = html; }  // told again only when it changes
  const hit = rankHit(L);
  for (const tr of $("#setupList")?.querySelectorAll("tr[data-setup-row]") || []) {
    const on = hit?.id === +tr.dataset.setupRow;
    tr.classList.toggle("mt-hit", on);
    for (const w of tr.querySelectorAll("[data-word]")) w.classList.toggle("hit", on && hit.words.includes(w.dataset.word));
  }
}
// Asks the server about the text typed. Only the latest answer counts, for the text and the list still on show (a draw of its own).
function tryRun() {
  const L = RANK.list;
  clearTimeout(RANK.timer);
  if (!rankOn(L) || !L.tried) return;
  const text = state.setup.probe || "";
  if (!text.trim() || RANK.saving) {
    pageDrop("try");
    if (!text.trim()) L.answer = null;
    return tryPaint();
  }
  tryPaint();
  return pageDraw("try", async page => {
    let r;
    try { r = await page.read(api(`/api/setup/${L.kind}/try`, { json: { text } })); }
    catch (e) { page.check(); r = { error: errorWords(e) }; }
    if (!rankOn(L) || (state.setup.probe || "") !== text) return;
    L.answer = { text, r };
    tryPaint();
  });
}

// Whether the focus going from the held rule's grip to `to` drops the rule: only to another control of the list's own page that leaves
// the list on show and uncovered. Not to a place that only takes the focus of a click (#main, a heading: no control), nor to what is off
// the list's page (the side menu, the top bar, a message: opening another page never saves a move), nor to a button that opens a dialog
// over the list (a rule's name, Add: the rule goes back as the dialog arrives, rankCovered, and that is said). Nor to nowhere (null).
const RANK_CONTROL = 'button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])';
const rankDropsTo = (L, to) => !!to && L.box.contains(to) && to.closest(RANK_CONTROL) === to && to.getAttribute("aria-haspopup") !== "dialog";

// The page's own listeners.
document.addEventListener("click", ev => { if (RANK.quiet && ev.target?.closest?.("#setupList")) { ev.preventDefault(); ev.stopPropagation(); } }, true);
document.addEventListener("click", async ev => {
  const b = ev.target?.closest?.("[data-grip]");
  if (!b || RANK.quiet) return;
  const L = RANK.list, id = +b.dataset.grip;
  if (!rankOn(L)) return;
  try { await (L.held == null ? rankPickUp(L, id) : rankDrop(L)); }  // with a rule picked up, a press drops it
  catch (e) { toast(e.message, true); }
});
document.addEventListener("keydown", ev => {
  const L = RANK.list;
  if (!L || L.held == null || +ev.target?.dataset?.grip !== L.held || !rankOn(L)) return;
  if (ev.key === "ArrowUp" || ev.key === "ArrowDown") { ev.preventDefault(); rankStep(L, ev.key === "ArrowUp" ? -1 : 1); }
  else if (ev.key === "Tab") Promise.resolve(rankDrop(L)).catch(e => toast(e.message, true));
});
document.addEventListener("focusout", ev => {
  const L = RANK.list;
  if (!L || L.held == null || L.painting || RANK.press?.dragging || +ev.target?.dataset?.grip !== L.held || !rankOn(L) || !rankDropsTo(L, ev.relatedTarget)) return;
  Promise.resolve(rankDrop(L)).catch(e => toast(e.message, true));
});
document.addEventListener("pointerdown", ev => {
  const b = ev.target?.closest?.("[data-grip]"), L = RANK.list;
  if (!b || ev.button || RANK.press?.dragging || !rankOn(L) || rankOff(L)) return;
  RANK.press = { L, id: +b.dataset.grip, y: ev.clientY, pointer: ev.pointerId, dragging: false };
});
document.addEventListener("pointermove", ev => {
  const P = RANK.press;
  if (!P || ev.pointerId !== P.pointer) return;
  if (!rankOn(P.L)) return void rankDragOff();
  if (!ev.buttons) return void rankDragEnd(false);  // let go where the page couldn't hear it: nothing is saved
  if (P.over) return;
  if (!P.dragging) {
    if (Math.abs(ev.clientY - P.y) < 5) return;
    if (P.L.held !== P.id && (P.L.held != null || !rankPickUp(P.L, P.id))) return void rankDragOff();  // not while another move is on
    P.dragging = true;
    document.body?.classList?.add("rank-dragging");
  }
  if (P.L.held !== P.id) {  // dropped or put back by a key while the button is still down: the drag is over
    P.over = true; document.body?.classList?.remove("rank-dragging");
    return;
  }
  ev.preventDefault?.();
  rankDragTo(P.L, P.id, ev.clientY);
});
document.addEventListener("pointerup", ev => {
  if (RANK.press && ev.pointerId === RANK.press.pointer) Promise.resolve(rankDragEnd(true)).catch(e => toast(e.message, true));
});
document.addEventListener("pointercancel", ev => { if (RANK.press && ev.pointerId === RANK.press.pointer) rankDragEnd(false); });
document.addEventListener("input", ev => {
  if (ev.target?.id !== "mt-try") return;
  state.setup.probe = ev.target.value;
  clearTimeout(RANK.timer);
  tryPaint();
  RANK.timer = setTimeout(() => Promise.resolve(tryRun()).catch(e => toast(e.message, true)), 250);
});
