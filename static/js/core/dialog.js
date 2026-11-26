"use strict";
/* ---------------- Dialogs (step 0c) ----------------
   The drawer is a modal dialog: openers draw it and call showDrawer(); closeDrawer() (pages/company.js) calls hideDrawer().
   ask() is the styled confirm that replaces the browser's own question box. Motion and focus rules: design/motion-keyboard-spec.md
   section 3. Everything that touches the page is guarded, so the script also runs where there is no real DOM. */
// seq: goes up each time a dialog is shown or closed; asked: each time one is asked for that reads first (dialogDraw); closed: each time
// the dialog is closed (closeDrawer, pages/company.js).
const DLG = { opener: null, sel: "", want: null, click: null, timer: null, closing: false, wired: false, dim: null, asking: 0, n: 0, seq: 0, asked: 0, closed: 0 };
// A dialog that is read before it opens, or filled once it is open: draw(dlg) waits with dlg.read, and writes only while it is still the one
// wanted: none that reads has been asked for since (the one asked for last wins, whatever order the answers come in), and none has been shown
// or closed (one that needs no read, Close, or going to another page, which closes the dialog first). As pageDraw (core/page.js): read
// first, then show. A page drawn again behind the dialog does not end it.
function dialogDraw(draw) {
  const ask = ++DLG.asked, at = DLG.seq;
  return drawWhile(drawTicket(() => DLG.asked !== ask || DLG.seq !== at, false), draw);
}
// For what a dialog's own change does once the server has answered (close the dialog, write into it, open it again): says whether that
// dialog has not been closed since. Once it has, whatever dialog is on show is another one, and the answer leaves it alone (it is said in a
// message). Ask before the first await.
function dialogHere() {
  const at = DLG.closed;
  return () => DLG.closed === at;
}
const DLG_FOCUSABLE = 'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';

const dlgCalm = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
// Animated only where there is a real DOM and the system has not asked for less motion; otherwise open and close at once.
const dlgCanAnimate = () => typeof document.createElement === "function" && !dlgCalm();
const dlgSet = (el, name, value) => { if (el && el.setAttribute) el.setAttribute(name, value); };

// The drawer is open from the moment it is shown until its closing animation ends.
const dlgDrawerOpen = () => { const d = $("#drawer"); return !!d && !d.hidden; };
// Open and not on its way out (what a dirty check should look at).
const drawerShown = () => dlgDrawerOpen() && !DLG.closing;

// Tab and Shift+Tab stay inside box.
function dlgTrap(ev, box) {
  const f = [...(box.querySelectorAll ? box.querySelectorAll(DLG_FOCUSABLE) : [])].filter(x => !x.closest?.("[hidden]"));
  if (!f.length) { ev.preventDefault(); box.focus?.(); return; }
  const a = document.activeElement, first = f[0], last = f[f.length - 1];
  if (ev.shiftKey && (a === first || f.indexOf(a) < 0)) { ev.preventDefault(); last.focus(); }
  else if (!ev.shiftKey && (a === last || !box.contains(a))) { ev.preventDefault(); first.focus(); }
}

// The page behind a dialog cannot be reached by keyboard, pointer or screen reader; the drawer too while a confirm is on top.
function dlgInert() {
  const behind = dlgDrawerOpen() || DLG.asking > 0;
  for (const s of [".side", ".content"]) { const e = document.querySelector(s); if (e) e.inert = behind; }
  const d = $("#drawer"); if (d) d.inert = DLG.asking > 0;
}

// What had the focus when a dialog opened, or what was last clicked when a click gave nothing the focus.
// A payment row is not a control, so a click on it counts too. Buttons of a toast or a confirm are never what a dialog returns to.
function dlgOpener() { const a = document.activeElement; return a && a !== document.body ? a : DLG.click; }
if (document.addEventListener) document.addEventListener("click", ev => {
  const b = ev.target?.closest?.('button, a[href], [data-payment], [tabindex]:not([tabindex="-1"])') || null;
  DLG.click = b && b.closest?.(".toast-stack, .dlg-layer") ? DLG.click : b;
}, true);

// A way to find an opener again once the page is drawn again (a save redraws the list, so the element itself is gone): its id,
// else its first data attribute, else those of the payment row it sits in.
function dlgSel(el) {
  const one = x => {
    if (!x) return "";
    if (x.id) return `[id="${String(x.id).replace(/["\\]/g, "")}"]`;
    for (const k in x.dataset || {}) return `[data-${k.replace(/[A-Z]/g, c => "-" + c.toLowerCase())}="${String(x.dataset[k]).replace(/["\\]/g, "")}"]`;
    return "";
  };
  return one(el) || one(el?.closest?.("[data-payment]"));
}
// Focus returns to the opener, else to its twin in the redrawn page, else to a place that always exists: the open dialog, or the
// page itself (#main, made focusable). The page may still be drawing: render() calls dlgRestore() when it is done.
function dlgBack(el, sel) {
  const lost = !(el && el.isConnected);
  let to = lost ? (sel ? document.querySelector(sel) : null) : el;
  if (!to) { to = dlgDrawerOpen() ? $("#drawer") : $("#main"); if (to) dlgSet(to, "tabindex", "-1"); }
  to?.focus?.({ preventScroll: true });
  DLG.want = sel ? { sel, at: Date.now() } : null;
}
function dlgRestore() {
  const w = DLG.want; DLG.want = null;
  if (!w || Date.now() - w.at > 1500) return;
  const a = document.activeElement;
  if (a && a !== document.body && a.isConnected !== false && a !== $("#main")) return;   // focus is somewhere real: leave it
  document.querySelector(w.sel)?.focus?.({ preventScroll: true });
}

// The dim behind the drawer: one element for the page, made the first time it is needed. A click on it closes the drawer
// through the same check for unsaved edits.
function dlgDim() {
  if (DLG.dim || typeof document.createElement !== "function" || !document.body?.appendChild) return DLG.dim;
  const e = document.createElement("div");
  e.className = "dim"; e.hidden = true; dlgSet(e, "aria-hidden", "true");
  e.addEventListener("click", () => closeDrawer());
  document.body.appendChild(e);
  return DLG.dim = e;
}

function dlgWire(d) {
  if (DLG.wired) return;
  DLG.wired = true;
  d.addEventListener?.("keydown", ev => { if (ev.key === "Tab") dlgTrap(ev, d); });
  d.addEventListener?.("animationend", ev => { if (DLG.closing && ev.target === d) dlgFinish(); });
}

// Draws the drawer as a modal dialog (the opener has set its innerHTML): labelled by its first heading, the page behind it
// inert, focus on the heading. Drawn again while open (another payment, a redraw after a save), it keeps its opener and its
// place, and only takes the focus back if the redraw lost it. kind: "dialog" draws it as the centred payment dialog
// (pages/payment.js), "new" as the narrower New payment dialog, "setup" as Setup's record dialog (pages/setup.js); anything else as the side panel.
function showDrawer(kind) {
  const d = $("#drawer"); if (!d) return;
  DLG.seq++;
  dlgWire(d);
  const was = !d.hidden;
  clearTimeout(DLG.timer); DLG.closing = false;
  d.classList.remove("dr-out", "pay-dlg", "np-dlg", "st-dlg"); d.hidden = false;
  if (kind === "dialog" || kind === "new" || kind === "setup") d.classList.add("pay-dlg");
  if (kind === "new" || kind === "setup") d.classList.add("np-dlg");
  if (kind === "setup") d.classList.add("st-dlg");
  if (kind !== "dialog") d.classList.remove("pd-viewing");
  const dim = dlgDim();
  if (dim) { dim.classList.remove("dim-out"); dim.hidden = false; }
  if (!was) {
    DLG.opener = dlgOpener(); DLG.sel = dlgSel(DLG.opener); DLG.want = null;
    if (dlgCanAnimate()) { d.classList.add("dr-in"); dim?.classList.add("dim-in"); }
  }
  dlgSet(d, "role", "dialog"); dlgSet(d, "aria-modal", "true"); dlgSet(d, "tabindex", "-1");
  const h = d.querySelector ? d.querySelector("h1, h2, h3") : null;
  if (h) { h.id = "drawerTitle"; dlgSet(h, "tabindex", "-1"); dlgSet(d, "aria-labelledby", "drawerTitle"); }
  else d.removeAttribute?.("aria-labelledby");
  dlgInert();
  const a = document.activeElement;
  if (!was || !a || a === document.body || !d.contains?.(a)) (h || d).focus?.({ preventScroll: true });
}

// Closes it: out in 180 ms, hidden when the animation ends (animationend, with a 400 ms safety timer); at once for reduced motion.
function hideDrawer() {
  const d = $("#drawer"); if (!d || d.hidden || DLG.closing) return;
  if (!dlgCanAnimate()) return dlgFinish();
  DLG.closing = true;
  d.classList.remove("dr-in"); d.classList.add("dr-out");
  if (DLG.dim) { DLG.dim.classList.remove("dim-in"); DLG.dim.classList.add("dim-out"); }
  clearTimeout(DLG.timer); DLG.timer = setTimeout(dlgFinish, 400);
}
function dlgFinish() {
  clearTimeout(DLG.timer); DLG.closing = false;
  const d = $("#drawer"); if (!d) return;
  d.classList.remove("dr-in", "dr-out"); d.hidden = true;
  if (DLG.dim) { DLG.dim.classList.remove("dim-in", "dim-out"); DLG.dim.hidden = true; }
  dlgInert();
  const o = DLG.opener, sel = DLG.sel; DLG.opener = null; DLG.sel = "";
  if (!DLG.asking) dlgBack(o, sel);
}

// The styled confirm, in place of the browser's: resolves true for yes and false for no, Escape, the dim and the close
// button. Focus starts on the safe button (no, unless safe is "yes"). Each line of message is a paragraph. One at a time:
// a second call waits for the first to be answered.
let askQueue = Promise.resolve();
// tone: brand | warn | bad colours the glyph plate (warn, or bad with danger, when not given); danger makes the yes button red.
// glyph: the plate's glyph (alert). list: [{ glyph, tone: warn | muted, text }] under the message. note: a grey box. closing: a
// last small line, "text" or { glyph, text }.
async function ask(message, { yes = "Yes", no = "No", title, danger = false, safe = "no", tone, glyph = "alert", list, note, closing } = {}) {
  const turn = askQueue.then(() => dlgAsk(String(message ?? ""), { yes, no, title, danger, safe, tone, glyph, list, note, closing }));
  askQueue = turn.catch(() => {});
  return turn;
}

function dlgAsk(message, o) {
  if (typeof document.createElement !== "function" || !document.body?.appendChild) return Promise.resolve(false);  // no page to ask on: not confirmed
  return new Promise(resolve => {
    const n = ++DLG.n, tid = "askTitle" + n, bid = "askBody" + n;
    const paras = message.split(/\r?\n/).filter(l => l.trim()).map(l => `<p>${esc(l)}</p>`).join("");
    const layer = document.createElement("div");
    const tone = ["brand", "warn", "bad"].includes(o.tone) ? o.tone : o.danger ? "bad" : "warn";
    const items = (o.list || []).map(i => `<li class="${esc(i.tone || "")}">${icon(i.glyph || "alert")}<span>${esc(i.text)}</span></li>`).join("");
    const cl = o.closing ? (typeof o.closing === "string" ? { glyph: "undo", text: o.closing } : o.closing) : null;
    layer.className = "dlg-layer";
    layer.innerHTML = `<div class="dim dim-in" aria-hidden="true"></div>
      <div class="cfm dr-in" role="dialog" aria-modal="true" aria-labelledby="${o.title ? tid : bid}"${o.title ? ` aria-describedby="${bid}"` : ""} tabindex="-1">
        <div class="cfm-head"><span class="plate ${tone}">${icon(o.glyph || "alert")}</span>
          <div class="cfm-text">${o.title ? `<h2 id="${tid}" tabindex="-1">${esc(o.title)}</h2>` : ""}<div class="cfm-body" id="${bid}">${paras}</div></div></div>
        ${items ? `<ul class="cfm-list">${items}</ul>` : ""}${o.note ? `<div class="cfm-note">${esc(o.note)}</div>` : ""}${cl ? `<div class="cfm-close">${icon(cl.glyph || "undo")}<span>${esc(cl.text)}</span></div>` : ""}
        <div class="cfm-actions"><button type="button" class="btn ghost" data-ask="no">${esc(o.no)}</button><button type="button" class="btn${o.danger ? " danger-solid" : ""}" data-ask="yes">${esc(o.yes)}</button></div>
        <button type="button" class="ghost small cfm-x" aria-label="Close" data-ask="no">${icon("close")}</button>
      </div>`;
    const opener = dlgOpener(), osel = dlgSel(opener);
    const dim = layer.firstElementChild, panel = layer.querySelector(".cfm");
    DLG.asking++;
    document.body.appendChild(layer);
    dlgInert();
    let done = false, finished = false, timer = null;
    const finish = answer => {
      if (finished) return;  // animationend and the safety timer can both come
      finished = true; clearTimeout(timer);
      layer.remove(); DLG.asking--; dlgInert();
      if (!DLG.asking) dlgBack(opener, osel);
      resolve(answer);
    };
    const answer = v => {
      if (done) return;
      done = true; document.removeEventListener("keydown", onKey, true);
      if (!dlgCanAnimate()) return finish(v);
      dim.classList.remove("dim-in"); dim.classList.add("dim-out"); panel.classList.remove("dr-in"); panel.classList.add("dr-out");
      panel.addEventListener("animationend", ev => { if (ev.target === panel) finish(v); });
      timer = setTimeout(() => finish(v), 400);
    };
    // On the document, in the capture phase, so Escape and Tab are caught wherever the focus has gone and nothing under the confirm hears them.
    const onKey = ev => {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); answer(false); }
      else if (ev.key === "Tab") dlgTrap(ev, panel);
    };
    document.addEventListener("keydown", onKey, true);
    layer.addEventListener("click", ev => {
      const b = ev.target.closest?.("[data-ask]");
      if (b) answer(b.dataset.ask === "yes");
      else if (ev.target === dim) answer(false);
    });
    layer.querySelector(`[data-ask="${o.safe === "yes" ? "yes" : "no"}"]`).focus({ preventScroll: true });
  });
}
