"use strict";
/* ---------------- The States patterns and toasts (step 0c) ----------------
   Plain functions that return HTML strings (every input escaped) for the situations every page meets: nothing to show,
   loading, could not load, a refusal, many rows, and a page the company does not use. Plus the toast stack that toast()
   (core/base.js) draws. Wording and sizes: design/canvas/States.dc.html. Motion: design/motion-keyboard-spec.md section 6.
   emptyState (with its compact filter variant) and manyRows are ready for the list pages of the later slices. */

// A data attribute name the caller chose must really be one (data-something), or the button carries none.
const stAttr = (name, value) => /^data-[a-z0-9-]+$/.test(name || "") ? ` ${name}="${esc(value ?? "1")}"` : "";
const stPlate = (glyph, tone) => `<span class="state-plate ${esc(tone || "brand")}">${icon(glyph || "inbox")}</span>`;

// The card for a page or a list with nothing to show: why, and at most one clear next step.
// action: { label, attr: "data-open-month", value: "5", glyph: "plus", ghost: false }. tone: brand (default), ok, mute.
// compact: the small block a filter that matches nothing leaves in a list (muted search glyph, a ghost "Clear filter").
function emptyState({ glyph = "inbox", title = "", body = "", action = null, tone = "brand", compact = false } = {}) {
  const a = action && action.label ? `<div class="state-actions"><button type="button" class="${action.ghost || compact ? "ghost" : "btn"}"${stAttr(action.attr, action.value)}>${action.glyph ? icon(action.glyph) : ""}${esc(action.label)}</button></div>` : "";
  if (compact) return `<div class="state compact">${stPlate(glyph === "inbox" ? "search" : glyph, "mute")}<b>${esc(title)}</b>${body ? `<p>${esc(body)}</p>` : ""}${a}</div>`;
  return `<div class="state">${stPlate(glyph, tone)}<h2>${esc(title)}</h2>${body ? `<p>${esc(body)}</p>` : ""}${a}</div>`;
}

// Placeholder shapes while a page loads: the shimmer stops under reduced motion (base block in app.css). kind: list (default,
// rows of plate, two lines and a pill), stats (a 2 x 2 strip of figures), table (a heading row and rows).
function loadingSkeleton(rows = 3, { kind = "list", label } = {}) {
  const n = Math.max(1, Math.min(12, Math.floor(+rows) || 3)), w = [70, 60, 75, 55, 65], s = [45, 35, 40, 50, 30];
  const sk = (cls, width) => `<span class="sk ${cls}"${width ? ` style="width:${width}%"` : ""}></span>`;
  if (kind === "stats") {
    const card = i => `<div class="sk-stat">${sk("sk-s1", [50, 60, 45, 55][i % 4])}${sk("sk-s2", [70, 55, 65, 60][i % 4])}${sk("sk-s3", [40, 45, 50, 35][i % 4])}</div>`;
    return `<div class="skel-stats" role="group" aria-busy="true" aria-label="${esc(label || "Loading figures")}"><span class="sr-only">Loading</span>${[0, 1, 2, 3].map(card).join("")}</div>`;
  }
  if (kind === "table") {
    const row = i => `<div class="sk-trow">${sk("sk-t1", [38, 30, 44, 34][i % 4])}<span class="sk-gap"></span>${sk("sk-t1", [16, 18, 15, 17][i % 4])}</div>`;
    return `<div class="skel-table" role="group" aria-busy="true" aria-label="${esc(label || "Loading rows")}"><span class="sr-only">Loading</span><div class="sk-thead">${sk("sk-t0", 20)}<span class="sk-gap"></span>${sk("sk-t0", 14)}</div>${Array.from({ length: n }, (_, i) => row(i)).join("")}</div>`;
  }
  const row = i => `<div class="sk-row"><span class="sk sk-plate"></span><span class="sk-lines"><span class="sk" style="width:${w[i % w.length]}%"></span><span class="sk sk-sub" style="width:${s[i % s.length]}%"></span></span><span class="sk sk-pill"></span></div>`;
  return `<div class="skel" role="group" aria-busy="true" aria-label="${esc(label || "Loading payments")}"><span class="sr-only">Loading</span><span class="sk sk-title"></span>${Array.from({ length: n }, (_, i) => row(i)).join("")}</div>`;
}

// A page that could not load: the reason, and Try again (a button carrying data-retry; the click handler draws the page again)
// beside Copy details (the title and the reason, for whoever helps). Every load only reads, so it says nothing was changed.
function errorState({ title = "Couldn't load this page", body = "", retry = true, nothingChanged = true } = {}) {
  const text = [body, nothingChanged ? "Nothing was changed." : ""].filter(Boolean).join(" ");
  const b = (retry ? `<button type="button" class="btn" data-retry="${esc(retry === true ? "1" : retry)}">${icon("refresh")}Try again</button>` : "")
    + `<button type="button" class="ghost" data-copy-details="${esc(title + "\n" + text)}">Copy details</button>`;
  return `<div class="state bad" role="alert">${stPlate("alert", "bad")}<h2>${esc(title)}</h2>${text ? `<p>${esc(text)}</p>` : ""}<div class="state-actions">${b}</div></div>`;
}

// Copy details: the text goes to the clipboard, and a toast says so (or says it could not).
async function copyDetails(text) {
  try { await navigator.clipboard.writeText(String(text ?? "")); toast("Details copied"); }
  catch { toast("Couldn't copy. Select the text and copy it yourself.", true); }
}

// The page is open but the app has stopped: a fetch that never reached the server fails with a TypeError (the browser's
// "Failed to fetch"). Replaces the blank page and that wording with what to do.
const appStopped = e => !!e && (e.name === "TypeError" || e instanceof TypeError);
function stoppedState({ detail = "" } = {}) {
  const title = "HR Payments isn't running";
  return `<div class="state bad stopped" role="alert">${stPlate("laptop", "warn")}<div class="stopped-text"><h2>${esc(title)}</h2>`
    + `<p>The black window that runs it was closed, so this page can't reach your records. Nothing you typed since then was sent or saved.</p>`
    + `<ol><li>Double-click <b>Start HR Payments.bat</b>.</li><li>Keep the black window open while you work.</li><li>Come back here and press Try again.</li></ol>`
    + `<div class="state-actions"><button type="button" class="btn" data-retry="1" data-busy="Looking for it…">${icon("refresh")}Try again</button>`
    + `<button type="button" class="ghost" data-copy-details="${esc(title + (detail ? "\n" + detail : ""))}">Copy details</button>`
    + `<span class="state-note" role="status"></span></div></div></div>`;
}

// The server refused a save: its reason in words, in place (not a toast, which goes after a few seconds). A banner across the
// top of the form. field: { id, label, message } links to the field that caused it (Go to <label>) and, with markField(), marks it.
function refusedNote(reason, { title = "Nothing was saved", field = null } = {}) {
  const go = field && /^[\w-]+$/.test(field.id || "") ? `<a href="#${esc(field.id)}" class="ghost small refused-go" data-go-field="${esc(field.id)}">Go to ${esc(field.label || "the field")}</a>` : "";
  return `<div class="refused" role="alert">${icon("alert")}<div class="refused-text"><b>${esc(title)}</b><div class="refused-why">${esc(reason)}</div></div>${go}</div>`;
}
// Marks the field a refusal is about: red edge, aria-invalid, and its message under it (a 15px alert glyph). Clears the mark when
// message is empty. Returns the field.
function markField(id, message) {
  const el = document.getElementById(id);
  if (!el) return null;
  const eid = id + "-err", old = document.getElementById(eid);
  if (old) old.remove();
  if (!message) { el.removeAttribute?.("aria-invalid"); el.removeAttribute?.("aria-describedby"); return el; }
  el.setAttribute("aria-invalid", "true"); el.setAttribute("aria-describedby", eid);
  const m = document.createElement("span");
  m.id = eid; m.className = "field-err"; m.innerHTML = `${icon("alert")}${esc(message)}`;
  const at = el.parentNode && el.closest?.("label") ? el.closest("label") : el;
  if (at.parentNode?.insertBefore) at.parentNode.insertBefore(m, at.nextSibling); else el.parentNode?.appendChild(m);
  return el;
}

// "Showing 25 of 120 entries" and a "Show 25 more" button. The caller wires the button's data attribute (attr, default
// data-more, carrying value) and then draws slice(rows, shown + step). Nothing when there are no rows.
function manyRows({ shown = 0, total = 0, step = 25, what = "entries", attr = "data-more", value = "1" } = {}) {
  if (!(total > 0)) return "";
  const s = Math.min(Math.max(0, shown), total), more = Math.min(step, total - s);
  return `<div class="many noprint"><span role="status">Showing ${s} of ${total} ${esc(what)}</span>${more > 0 ? `<button type="button" class="ghost"${stAttr(attr, value)}>Show ${more} more</button>` : ""}</div>`;
}
const slice = (rows, shown) => rows.slice(0, Math.max(0, shown));

/* A page a company does not use. Switching company while on it lands on that company's Overview and says why in a toast;
   reaching it any other way (a link) shows the card. Add a page here when it depends on a company setting. */
const PAGE_RULES = {
  sql: { name: "SQL import", used: e => !!e.uses_sql,
    why: e => `${e.name} is Kept here, so there is nothing to import for it. Switch to a company that is Kept in SQL Account to import SQL listings.` }
};
// The page's name when the company doesn't use it, else null.
const unusedPage = (view = state.view, e = state.meta && ent()) => { const r = PAGE_RULES[view]; return r && e && !r.used(e) ? r.name : null; };
function switchedNote(name, e) {
  toast(`${name} isn't used for ${e.code} (Kept here). Showing ${e.code}'s Overview.`, false, { title: `Switched to ${e.code}`, glyph: "company", tone: "brand" });
}
// The card: what the page is, why this company has no use for it, and a way to a company that does.
function unusedCard(view = state.view, e = ent()) {
  const r = PAGE_RULES[view]; if (!r || !e) return "";
  const other = (state.meta?.entities || []).find(x => x.id !== e.id && isActive(x) && r.used(x));
  return emptyState({ glyph: "database", tone: "mute", title: `${r.name} isn't used for ${e.code}`, body: r.why(e),
    action: other ? { label: `Go to ${other.code}`, attr: "data-pick-entity", value: other.id, ghost: true } : null });
}

/* ---------------- Toasts ----------------
   toast(msg, bad, opts): opts { title, body, glyph, tone: ok | brand | bad, undo: fn, action: {label, fn, href}, ms, progress }.
   A stack in #toast (aria-live), at most 3 showing, an error stays until dismissed, the timer waits while the pointer is over a
   toast or focus is in it, Escape dismisses the focused one. Where the page has no real DOM (the test stand-ins) the one #toast
   element just carries the latest message. */
const TOASTS = { n: 0, list: [] };
function toastShow(msg, bad, opts) {
  opts = opts || {};
  const box = $("#toast");
  if (!box) return null;
  if (typeof document.createElement !== "function" || typeof box.appendChild !== "function") {
    box.textContent = msg; box.className = "toast" + (bad ? " bad" : ""); box.hidden = false;
    clearTimeout(toastShow.timer); toastShow.timer = setTimeout(() => box.hidden = true, bad ? 6000 : 2500);
    return null;
  }
  const t = { id: ++TOASTS.n, bad: !!bad, leaving: false, hover: false, focus: false, timer: null, safety: null,
    ms: opts.ms != null ? opts.ms : bad ? 0 : opts.undo || opts.action ? 8000 : 4000, el: document.createElement("div") };
  const el = t.el, title = opts.title ? esc(opts.title) : "", body = esc(opts.title ? (opts.body != null ? opts.body : msg) : msg);
  const tone = bad ? "bad" : ["ok", "brand", "bad"].includes(opts.tone) ? opts.tone : "ok";
  const glyph = opts.glyph || (bad ? "alert" : "check");
  // A way on under the text: a link when it has an address on this page or this app, else a button.
  const act = opts.action && opts.action.label ? opts.action : null;
  const href = act && /^(#|\/(?!\/))/.test(act.href || "") ? act.href : "";
  const actHtml = !act ? "" : href ? `<a class="toast-btn toast-act" href="${esc(href)}" data-toast-act="action">${esc(act.label)}</a>`
    : `<button type="button" class="toast-btn toast-act" data-toast-act="action">${esc(act.label)}</button>`;
  el.className = bad ? "toast bad" : "toast " + tone;
  el.setAttribute("role", bad ? "alert" : "status");
  el.innerHTML = `<span class="toast-glyph">${icon(glyph)}</span><div class="toast-text">${title ? `<b>${title}</b>` : ""}<div class="toast-body">${body}</div>`
    + `${opts.progress != null ? `<div class="toast-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${esc(opts.progress)}"><span style="width:${Math.max(0, Math.min(100, +opts.progress || 0))}%"></span></div>` : ""}${actHtml}</div>`
    + `${opts.undo ? `<button type="button" class="toast-btn" data-toast-act="undo">${icon("undo")}Undo</button>` : ""}`
    + `<button type="button" class="toast-x" data-toast-act="close" aria-label="Dismiss">${icon("close")}</button>`;
  const arm = () => { clearTimeout(t.timer); if (t.ms > 0 && !t.leaving && !t.hover && !t.focus) t.timer = setTimeout(() => toastDismiss(t), t.ms); };
  const call = fn => { try { const r = fn(); if (r && r.catch) r.catch(e => toast(e.message, true)); } catch (e) { toast(e.message, true); } };
  el.addEventListener("click", ev => {
    const b = ev.target?.closest?.("[data-toast-act]");
    if (!b) return;
    ev.stopPropagation();
    const what = b.dataset.toastAct;
    toastDismiss(t);
    if (what === "undo" && opts.undo) call(opts.undo);
    else if (what === "action" && act?.fn) call(act.fn);
  });
  el.addEventListener("keydown", ev => { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); toastDismiss(t); } });
  el.addEventListener("mouseenter", () => { t.hover = true; clearTimeout(t.timer); });
  el.addEventListener("mouseleave", () => { t.hover = false; arm(); });
  el.addEventListener("focusin", () => { t.focus = true; clearTimeout(t.timer); });
  el.addEventListener("focusout", () => { t.focus = false; arm(); });
  el.addEventListener("animationend", ev => { if (t.leaving && ev.target === el) toastGone(t); });
  box.appendChild(el);
  TOASTS.list.push(t);
  arm();
  for (let live = TOASTS.list.filter(x => !x.leaving); live.length > 3; live = TOASTS.list.filter(x => !x.leaving))
    toastDismiss(live.find(x => !x.bad) || live[0]);   // the oldest that is not an error goes first
  return { dismiss: () => toastDismiss(t), el };
}
function toastDismiss(t) {
  if (t.leaving) return;
  t.leaving = true; clearTimeout(t.timer);
  TOASTS.list = TOASTS.list.filter(x => x !== t);
  const hadFocus = !!t.el.contains?.(document.activeElement);
  if (!dlgCanAnimate()) return toastGone(t, hadFocus);
  t.el.classList.add("out");
  t.safety = setTimeout(() => toastGone(t), 400);   // animationend normally comes first
  if (hadFocus) toastRefocus(t);
}
function toastGone(t, hadFocus) {
  clearTimeout(t.safety); clearTimeout(t.timer);
  if (t.el.isConnected !== false) t.el.remove();
  if (hadFocus) toastRefocus(t);
}
// A dismissed toast had the focus: it goes to the next toast; else into the open dialog; else to what was last clicked on the
// page (never a button of a toast); else to the page.
function toastRefocus(t) {
  const out = x => !!x && x.isConnected !== false && !t.el.contains?.(x);
  const next = TOASTS.list[TOASTS.list.length - 1];
  const x = next && next.el.querySelector(".toast-x");
  const drawer = dlgDrawerOpen() ? $("#drawer") : null;
  const to = out(x) ? x : drawer || (out(DLG.click) ? DLG.click : $("#main"));
  if (to && to.focus) { if (to === $("#main")) dlgSet(to, "tabindex", "-1"); to.focus({ preventScroll: true }); }
}
