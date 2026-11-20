"""The States patterns and the toast stack (step 0c): empty, loading, could not load, refused, many rows, the page a company
does not use, and toasts. Made-up text only. The page script is run in Node against a small stand-in for the page, so the test
needs no browser and no server.

Checks: every helper escapes its inputs and renders its wording; toast() keeps its old signature and the message is in
#toast; at most 3 toasts show and an error is the last to go; the timers (4s, 8s with Undo, none for an error) and pausing
while hovered; Escape and the close button dismiss; Undo calls its function; a page that fails to load shows "Couldn't load
this page" with Try again, which draws it again; a slow page shows a skeleton and a fast one never does; a Kept here
company navigating to the SQL import page lands on its Overview with the "Switched to" toast.

Run: .venv\\Scripts\\python -m synthetic_tests.states_test
"""
import json
import subprocess
import tempfile
from pathlib import Path

from synthetic_tests.appsource import app_bundle

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:600])


tmp = Path(tempfile.mkdtemp(prefix="hrp-states-test-"))
bundle = app_bundle(tmp / "app.js")

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const appPath = process.argv[2];

// ---- a small stand-in for the page ----
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tick = () => sleep(5);
const parseSel = sel => sel.split(",").map(s => s.trim()).filter(Boolean);
function matchOne(n, sel) {
  const m = /^([a-z0-9]*)((?:\[[^\]]+\]|\.[\w-]+|#[\w-]+)*)(?::not\((.*)\))?$/.exec(sel);
  if (!m) throw new Error("selector not supported: " + sel);
  if (m[1] && n.tagName !== m[1]) return false;
  for (const [, part] of m[2].matchAll(/(\[[^\]]+\]|\.[\w-]+|#[\w-]+)/g)) {
    if (part[0] === ".") { if (!n.classList.contains(part.slice(1))) return false; }
    else if (part[0] === "#") { if (n.id !== part.slice(1)) return false; }
    else {
      const [, k, v] = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(part);
      if (!n.hasAttribute(k) || (v !== undefined && n.getAttribute(k) !== v)) return false;
    }
  }
  if (m[3] && matchOne(n, m[3])) return false;
  return true;
}
const matches = (n, sel) => parseSel(sel).some(s => matchOne(n, s));
const listeners = new Map();   // target -> [{type, fn, capture}]
const addL = (t, type, fn, o) => { const l = listeners.get(t) || []; l.push({ type, fn, capture: o === true || !!(o && o.capture) }); listeners.set(t, l); };
const delL = (t, type, fn, o) => { const c = o === true || !!(o && o.capture); listeners.set(t, (listeners.get(t) || []).filter(x => !(x.type === type && x.fn === fn && x.capture === c))); };
class Node {
  constructor(tag) { this.tagName = tag; this.attrs = {}; this.children = []; this.parent = null; this.hidden = false; this.inert = false; this._html = ""; this.dataset = {}; }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; } set className(v) { this.attrs.class = v; }
  get classList() {
    const n = this, get = () => n.className.split(/\s+/).filter(Boolean);
    return { add: (...c) => { n.className = [...new Set([...get(), ...c])].join(" "); }, remove: (...c) => { n.className = get().filter(x => !c.includes(x)).join(" "); }, contains: c => get().includes(c) };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  set tabIndex(v) { this.attrs.tabindex = String(v); }
  appendChild(c) { if (c.parent) c.remove(); c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  get firstElementChild() { return this.children[0] || null; }
  get parentNode() { return this.parent; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === body; }
  contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = n => { for (const c of n.children) { if (matches(c, sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get textContent() { return (this.text || "") + this.children.map(c => c.textContent).join(""); } set textContent(v) { this.text = String(v); this.children = []; }
  get innerHTML() { return this._html; }
  set innerHTML(h) { this._html = h; this.children = []; parseInto(this, h); }
  focus() {
    for (let n = this; n; n = n.parent) if (n.inert) return;
    document.activeElement = this;
  }
  addEventListener(type, fn, o) { addL(this, type, fn, o); }
  removeEventListener(type, fn, o) { delL(this, type, fn, o); }
  click() { dispatch(this, { type: "click" }); }
}
function parseInto(root, html) {
  const stack = [root]; const tok = /<(\/?)([a-zA-Z0-9]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>|([^<]+)/g; let m;
  const VOID = new Set(["use", "input", "br", "img"]);
  while ((m = tok.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) { top.text = (top.text || "") + m[5].replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"); continue; }
    const [, close, tag, attrs, selfClose] = m;
    if (close) { stack.pop(); continue; }
    const n = new Node(tag.toLowerCase());
    for (const [, k, v] of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) {
      n.setAttribute(k, v === undefined ? "" : v);
      if (k === "hidden") n.hidden = true;
    }
    top.appendChild(n);
    if (!selfClose && !VOID.has(n.tagName)) stack.push(n);
  }
}
function dispatch(target, ev) {
  ev.target = target; ev.defaultPrevented = false; ev.stopped = false;
  ev.preventDefault = () => { ev.defaultPrevented = true; }; ev.stopPropagation = () => { ev.stopped = true; };
  const path = []; for (let n = target; n; n = n.parent) path.push(n);
  if (path[path.length - 1] === body) path.push(document);
  const call = (t, capture) => { for (const l of [...(listeners.get(t) || [])]) if (l.type === ev.type && (t === target || l.capture === capture)) { ev.currentTarget = t; l.fn(ev); } };
  for (const t of [...path].reverse()) { if (ev.stopped) return ev; if (t !== target) call(t, true); }   // capture, outermost first
  for (const t of path) { if (ev.stopped) return ev; call(t, false); }                                  // the target (all its listeners once), then bubbling
  return ev;
}

const body = new Node("body");
const main = new Node("main"); main.id = "main";
const nav = new Node("nav"); nav.id = "nav";
const monthLabel = new Node("span"); monthLabel.id = "monthLabel";
const side = new Node("aside"); side.className = "side";
const content = new Node("div"); content.className = "content";
const drawer = new Node("aside"); drawer.id = "drawer"; drawer.className = "drawer"; drawer.hidden = true;
const box = new Node("div"); box.id = "toast"; box.className = "toast-stack";
for (const n of [side, content, drawer, box, main, nav, monthLabel]) body.appendChild(n);
let calm = true;
const document = {
  body, activeElement: body,
  querySelector: sel => body.querySelector(sel), querySelectorAll: sel => body.querySelectorAll(sel),
  getElementById: id => body.querySelector("#" + id),
  createElement: tag => new Node(tag),
  addEventListener(type, fn, o) { addL(document, type, fn, o); }, removeEventListener(type, fn, o) { delL(document, type, fn, o); },
};
let fetchCalls = 0, fetchImpl = () => new Promise(() => {});   // the page's first request never answers: nothing else runs
const fetch = (...a) => { fetchCalls++; return fetchImpl(...a); };
const ctx = vm.createContext({ document, fetch, console, setTimeout, clearTimeout, FormData: class {},
  localStorage: { getItem: () => null, setItem() {} }, window: { open() {}, print() {}, matchMedia: () => ({ matches: calm }) } });
const run = code => vm.runInContext(code, ctx);
vm.runInContext(fs.readFileSync(appPath, "utf8"), ctx);
const results = [], ok = (name, v, detail) => results.push([name, !!v, detail === undefined ? "" : String(detail)]);
const toasts = () => box.children.filter(c => c.className.split(/\s+/).includes("toast"));
const texts = () => toasts().map(t => t.textContent);
const key = (k, extra = {}) => dispatch(document.activeElement, { type: "keydown", key: k, ...extra });

(async () => {
  // ---- helpers: wording and escaping ----
  const E = run(`emptyState({ glyph: "calendar", title: "Nothing <i>here</i>", body: 'Say "why" & more', action: { label: "Add <u>one</u>", attr: "data-add-thing", value: 'a"b' } })`);
  ok("emptyState shows the title, body and one button", E.includes("<h2>Nothing &lt;i&gt;here&lt;/i&gt;</h2>") && E.includes("Say &quot;why&quot; &amp; more") && E.includes(">Add &lt;u&gt;one&lt;/u&gt;</button>") && (E.match(/<button/g) || []).length === 1, E);
  ok("emptyState escapes the data value and keeps the caller's attribute", E.includes('data-add-thing="a&quot;b"') && !E.includes("<i>") && !E.includes("<u>"), E);
  const E2 = run(`emptyState({ title: "T", action: { label: "Go", attr: "onclick", value: "x" } })`);
  ok("a button attribute that is not data-something is dropped", !E2.includes("onclick") && E2.includes(">Go</button>"), E2);
  ok("emptyState without an action has no button and no body", !run(`emptyState({ title: "T" })`).includes("<button") && !run(`emptyState({ title: "T" })`).includes("<p>"));
  const S = run(`loadingSkeleton(2)`);
  ok("loadingSkeleton draws the rows it is asked for, marked busy", (S.match(/class="sk-row"/g) || []).length === 2 && S.includes('aria-busy="true"') && S.includes("Loading") && S.includes('class="sk '), S);
  const X = run(`errorState({ body: "The records <b>folder</b> can't be reached." })`);
  ok("errorState says Couldn't load this page, with the reason escaped", X.includes("Couldn&#39;t load this page") && X.includes("&lt;b&gt;folder&lt;/b&gt;") && X.includes('role="alert"'), X);
  ok("errorState has Try again carrying data-retry", X.includes('data-retry="1"') && X.includes("Try again") && !run(`errorState({ body: "x", retry: false })`).includes("data-retry"), X);
  const R = run(`refusedNote("Someone must keep the <b>Admin</b> right.")`);
  ok("refusedNote shows the reason in words, as an alert, escaped", R.includes('role="alert"') && R.includes("Nothing was saved") && R.includes("Someone must keep the &lt;b&gt;Admin&lt;/b&gt; right.") && !R.includes("<b>Admin"), R);
  ok("refusedNote takes another title", run(`refusedNote("r", { title: "It can't be put back" })`).includes("It can&#39;t be put back"));
  const M = run(`manyRows({ shown: 25, total: 120 })`);
  ok("manyRows says Showing 25 of 120 and offers Show 25 more", M.includes("Showing 25 of 120 entries") && M.includes("Show 25 more") && M.includes('data-more="1"') && M.includes('role="status"'), M);
  ok("the last step offers what is left", run(`manyRows({ shown: 100, total: 120 })`).includes("Show 20 more"));
  ok("with everything shown there is no button", !run(`manyRows({ shown: 120, total: 120 })`).includes("<button") && run(`manyRows({ shown: 120, total: 120 })`).includes("Showing 120 of 120"));
  ok("manyRows takes the caller's attribute and wording, and nothing for no rows", run(`manyRows({ shown: 10, total: 312, step: 10, what: "lines", attr: "data-more-lines", value: "trail" })`).includes('data-more-lines="trail"') && run(`manyRows({ total: 0 })`) === "");
  ok("slice gives the first rows", JSON.stringify(run(`slice([1, 2, 3, 4], 2)`)) === "[1,2]");

  // ---- toasts: the old call still works ----
  run(`toast("Saved it")`);
  ok("toast(msg) puts the message in #toast", box.textContent.includes("Saved it") && toasts().length === 1);
  ok("a plain toast is a status, an error an alert", toasts()[0].getAttribute("role") === "status");
  run(`toast("Could not save", true)`);
  ok("toast(msg, true) is an alert with the red edge", toasts()[1].getAttribute("role") === "alert" && toasts()[1].classList.contains("bad") && box.textContent.includes("Could not save"));
  ok("it has a close button with a name", !!toasts()[0].querySelector('button[aria-label="Dismiss"]'));
  ok("timers: 4 seconds, an error stays", run("TOASTS.list[0].ms") === 4000 && run("TOASTS.list[1].ms") === 0);
  run(`toast("Removed", false, { undo: () => {} })`);
  ok("with an Undo or an action: 8 seconds", run("TOASTS.list[2].ms") === 8000);
  // dismiss by the close button
  toasts()[0].querySelector('[data-toast-act="close"]').click();
  ok("the close button dismisses it", !texts().some(t => t.includes("Saved it")) && toasts().length === 2);
  // at most 3, errors last
  for (const m of ["one", "two", "three", "four"]) run(`toast("${m}")`);
  ok("at most 3 show", toasts().length === 3, texts());
  ok("the error is still there: the oldest ones that are not errors went first", texts().some(t => t.includes("Could not save")) && !texts().some(t => t.includes("Removed")) && texts().some(t => t.includes("four")), texts());
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  ok("all gone", toasts().length === 0);
  // Undo
  let undone = 0;
  run(`globalThis.__undo = () => { globalThis.__n = (globalThis.__n || 0) + 1; }; toast("Payment removed", false, { undo: __undo })`);
  const ub = toasts()[0].querySelector('[data-toast-act="undo"]');
  ok("an Undo button shows when asked", ub && ub.textContent === "Undo");
  ub.click();
  ok("Undo calls its function and dismisses the toast", run("globalThis.__n") === 1 && toasts().length === 0);
  run(`globalThis.__act = 0; toast("Filed", false, { action: { label: "Open it", fn: () => { globalThis.__act++; } } })`);
  toasts()[0].querySelector('[data-toast-act="action"]').click();
  ok("an action button calls its function", run("globalThis.__act") === 1 && toasts().length === 0);
  // title and body
  run(`toast("The body", false, { title: "The <title>" })`);
  ok("a title is bold and the message is the body, both escaped", toasts()[0].querySelector("b").text === "The <title>" && toasts()[0].innerHTML.includes("The &lt;title&gt;") && toasts()[0].textContent.includes("The body"));
  toasts()[0].querySelector('[data-toast-act="close"]').click();
  // progress
  run(`toast("Matching", false, { progress: 40 })`);
  ok("progress shows a bar", !!toasts()[0].querySelector('[role="progressbar"]') && toasts()[0].querySelector('[role="progressbar"]').getAttribute("aria-valuenow") === "40");
  toasts()[0].querySelector('[data-toast-act="close"]').click();
  // Escape
  run(`toast("Press escape")`);
  key("Escape", {});   // not inside a toast: nothing happens to it
  ok("Escape elsewhere leaves a toast", toasts().length === 1);
  const ev = dispatch(toasts()[0].querySelector(".toast-x"), { type: "keydown", key: "Escape" });
  ok("Escape on a toast dismisses it and goes no further", toasts().length === 0 && ev.defaultPrevented);
  // a toast that names an element to refocus (the company switch toast: the company button)
  { const cb = new Node("button"); cb.id = "tb-mb-company"; body.appendChild(cb);
    run(`toast("Switched", false, { refocus: "#tb-mb-company" })`);
    toasts()[0].querySelector(".toast-x").focus();
    dispatch(toasts()[0].querySelector(".toast-x"), { type: "keydown", key: "Escape" });
    ok("Escape on a toast that names an element puts the focus back on it", document.activeElement === cb, document.activeElement && document.activeElement.id);
    run(`toast("Switched again", false, { refocus: "not a selector" })`);
    ok("a refocus that is not an id selector is ignored", toasts().length === 1);
    toasts()[0].querySelector(".toast-x").click(); cb.remove(); }
  // timers
  run(`toast("Soon gone", false, { ms: 40 })`);
  await sleep(120);
  ok("it goes by itself when its time is up", toasts().length === 0);
  run(`toast("Held", false, { ms: 60 })`);
  dispatch(toasts()[0], { type: "mouseenter" });
  await sleep(150);
  ok("the timer waits while the pointer is over it", toasts().length === 1);
  dispatch(toasts()[0], { type: "mouseleave" });
  await sleep(150);
  ok("and runs again after", toasts().length === 0);
  run(`toast("Focused", false, { ms: 60 })`);
  dispatch(toasts()[0], { type: "focusin" });
  await sleep(150);
  ok("the timer waits while focus is inside it", toasts().length === 1);
  dispatch(toasts()[0], { type: "focusout" });
  await sleep(150);
  ok("and runs again after focus leaves", toasts().length === 0);
  run(`toast("An error", true, { ms: 40 })`);
  await sleep(120);
  ok("an error given a time still goes when asked", toasts().length === 0);
  run(`toast("Stays", true)`); await sleep(120);
  ok("an error without a time stays", toasts().length === 1);
  toasts()[0].querySelector('[data-toast-act="close"]').click();
  // animated leave
  calm = false;
  run(`toast("Slow out")`);
  const slow = toasts()[0];
  slow.querySelector('[data-toast-act="close"]').click();
  ok("with motion it leaves by playing toastOut first", slow.classList.contains("out") && slow.isConnected);
  dispatch(slow, { type: "animationend" });
  ok("and goes when the animation ends", !slow.isConnected);
  run(`toast("Safety")`); const sf = toasts()[0]; sf.querySelector('[data-toast-act="close"]').click();
  await sleep(480);
  ok("or at the safety timer", !sf.isConnected);
  calm = true;

  // ---- pages: failing, loading, not used ----
  run(`state.meta = { entities: [{ id: 1, code: "AA", name: "Alpha Co", active: 1, uses_sql: 1 }, { id: 2, code: "BB", name: "Beta Co", active: 1, uses_sql: 0 }], categories: {} }`);
  run(`state.month = "2026-01"; state.day = dayKey(); state.entity = 1;`);
  fetchImpl = () => Promise.reject(new Error("The records folder can't be reached."));
  run(`state.view = "overview"`); await run("render()");
  ok("a page that fails shows the Couldn't load card with the reason", main.innerHTML.includes("Couldn&#39;t load this page") && main.innerHTML.includes("The records folder can&#39;t be reached.") && main.innerHTML.includes('role="alert"'), main.innerHTML.slice(0, 300));
  await sleep(250);
  ok("a fast failure never flashed a skeleton", !main.innerHTML.includes("skel"));
  const before = fetchCalls;
  fetchImpl = () => Promise.reject(new Error("Still down."));
  const rb = main.querySelector("[data-retry]");
  dispatch(rb, { type: "click" });
  await sleep(50);
  ok("Try again draws the page again", fetchCalls > before && main.innerHTML.includes("Still down."), fetchCalls - before);
  // a slow page
  fetchImpl = () => new Promise((_, rej) => setTimeout(() => rej(new Error("Too slow.")), 400));
  run(`state.view = "budget"`);
  const pr = run("render()");
  await sleep(60);
  ok("a page that is quick to load shows no skeleton yet", !main.innerHTML.includes("skel"));
  ok("the old page is dimmed while the next one is asked for", main.classList.contains("loading"));
  await sleep(300);
  ok("a slow page shows the skeleton after 0.3 s", main.innerHTML.includes("skel") && main.innerHTML.includes('aria-busy="true"'), main.innerHTML.slice(0, 200));
  await pr;
  ok("and the failure replaces it", !main.innerHTML.includes("skel") && main.innerHTML.includes("Too slow."));
  ok("the dimming ends with the load", !main.classList.contains("loading"));
  ok("the failure card says nothing was changed and offers Copy details beside Try again", main.innerHTML.includes("Too slow. Nothing was changed.") && !!main.querySelector("[data-copy-details]") && main.querySelector("[data-copy-details]").text === "Copy details" && !!main.querySelector("[data-retry]"));
  // the app has stopped: a fetch that never reaches the server fails with a TypeError
  fetchImpl = () => Promise.reject(new TypeError("Failed to fetch"));
  run(`state.view = "budget"`); await run("render()");
  ok("a failed fetch shows the HR Payments isn't running card, with its three steps", main.innerHTML.includes("HR Payments isn&#39;t running") && main.innerHTML.includes("Start HR Payments.bat") && main.innerHTML.includes("<ol>") && main.innerHTML.includes('data-busy="Looking for it'), main.innerHTML.slice(0, 200));
  ok("and not the browser's own wording", !main.innerHTML.includes("Failed to fetch") || main.innerHTML.includes("data-copy-details"));
  const sb = main.querySelector("[data-retry]");
  fetchImpl = () => new Promise(() => {});
  dispatch(sb, { type: "click" }); await tick();
  ok("Try again shows its busy label while it looks", sb.disabled === true && sb.getAttribute("aria-busy") === "true" && sb.textContent.endsWith("Looking for it\u2026"), sb.textContent);
  fetchImpl = () => Promise.reject(new Error("x"));
  ok("stoppedState is a card with Try again and Copy details", run(`stoppedState()`).includes("data-retry") && run(`stoppedState()`).includes("Copy details"));
  // the other loading shapes
  ok("loadingSkeleton: a stat strip of four, labelled", (run(`loadingSkeleton(0, { kind: "stats" })`).match(/class="sk-stat"/g) || []).length === 4 && run(`loadingSkeleton(0, { kind: "stats" })`).includes('aria-label="Loading figures"'));
  ok("loadingSkeleton: table rows, labelled", (run(`loadingSkeleton(4, { kind: "table" })`).match(/class="sk-trow"/g) || []).length === 4 && run(`loadingSkeleton(4, { kind: "table" })`).includes('aria-label="Loading rows"'));
  ok("the list skeleton is busy and labelled, not a status", run(`loadingSkeleton(3)`).includes('aria-label="Loading payments"') && !run(`loadingSkeleton(3)`).includes('role="status"'));
  ok("the list skeleton's sub-lines are 45, 35 and 40 percent", ["45", "35", "40"].every(w => run(`loadingSkeleton(3)`).includes('sk-sub" style="width:' + w + "%")));

  // a page the company does not use
  fetchImpl = () => Promise.reject(new Error("x"));
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  run(`state.view = "sql"; state.entity = 1;`);
  await run("render()");
  ok("a company that uses SQL keeps the SQL import page", run("state.view") === "sql" && toasts().length === 0, run("state.view"));
  await run(`go("sql", 2)`);
  ok("a Kept here company asking for the SQL import page lands on its Overview", run("state.view") === "entity" && run("state.entity") === 2, run("state.view"));
  ok("the toast says Switched to BB", toasts().length === 1 && toasts()[0].querySelector("b").text === "Switched to BB", texts());
  ok("and why, in the board's words", toasts()[0].textContent.includes("SQL import isn't used for BB (Kept here). Showing BB's Overview."), texts());
  ok("it is a status, not an error", toasts()[0].getAttribute("role") === "status" && !toasts()[0].classList.contains("bad"));
  ok("the sidebar follows the page", /data-menu="payments\/register"[^>]*aria-current="page"/.test(nav.innerHTML));
  run(`state.view = "sql"; state.entity = 1;`); await run("render()");
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  run(`state.entity = 2;`); await run("render()");
  ok("switching to a Kept here company while on the SQL import page does the same", run("state.view") === "entity" && texts().some(t => t.includes("Switched to BB")));
  // reached by a link, with no company switch: the card
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  run(`state.view = "sql"; state.entity = 2;`); await run("render()");
  ok("a page reached by a link, not a company switch, shows the not-used card (no redirect, no toast)", run("state.view") === "sql" && main.innerHTML.includes("SQL import isn&#39;t used for BB") && toasts().length === 0, main.innerHTML.slice(0, 160));
  ok("the card says why and has a ghost way to a company that uses it", main.innerHTML.includes("Beta Co is kept here, so there is nothing to import from SQL Account.") && main.innerHTML.includes('data-pick-entity="1"') && main.innerHTML.includes("Go to AA"));
  ok("pages without a rule are never redirected", run(`unusedPage("budget", ent())`) === null && run(`unusedPage("sql", ent())`) === "SQL import");

  // ---- the compact empty block, the refusal banner, field marks ----
  const EC = run(`emptyState({ compact: true, title: "No match for <x>", body: "Check the spelling.", action: { label: "Clear filter", attr: "data-clear-filter" } })`);
  ok("the compact empty block: a muted search plate, a bold title, a ghost Clear filter", EC.includes('class="state compact"') && EC.includes("#i-search") && EC.includes("state-plate mute") && EC.includes("<b>No match for &lt;x&gt;</b>") && EC.includes('class="ghost" data-clear-filter="1"'), EC);
  const RF = run(`refusedNote("Someone must keep it.", { field: { id: "f-admin", label: "the Admin right" } })`);
  ok("a refusal can link to the field that caused it", RF.includes('href="#f-admin"') && RF.includes('data-go-field="f-admin"') && RF.includes("Go to the Admin right") && RF.includes("Nothing was saved"), RF);
  ok("no link without a field, and an odd id gets none", !run(`refusedNote("r")`).includes("data-go-field") && !run(`refusedNote("r", { field: { id: 'a"b' } })`).includes("data-go-field"));
  main.innerHTML = `<div><input id="f-admin"></div>`;
  const fld = run(`markField("f-admin", "Someone must keep the Admin right.")`);
  ok("markField marks the field invalid and gives it its message", fld.getAttribute("aria-invalid") === "true" && fld.getAttribute("aria-describedby") === "f-admin-err" && !!main.querySelector("#f-admin-err") && main.querySelector("#f-admin-err").textContent.includes("Someone must keep"));
  run(`markField("f-admin", "")`);
  ok("and clears the mark", !fld.hasAttribute("aria-invalid") && !main.querySelector("#f-admin-err"));
  const goB = new Node("a"); goB.setAttribute("data-go-field", "f-admin"); goB.setAttribute("href", "#f-admin"); main.appendChild(goB);
  dispatch(goB, { type: "click" }); await tick();
  ok("Go to the field puts the focus in it", document.activeElement && document.activeElement.id === "f-admin");

  // ---- toasts: tones, the Undo glyph, a way on under the text, focus after a button is pressed ----
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  run(`toast("Fine")`); run(`toast("Switched", false, { tone: "brand", glyph: "company" })`); run(`toast("Bad", true)`);
  ok("a toast is ok by default, brand when asked, and an error is bad", toasts()[0].classList.contains("ok") && toasts()[1].classList.contains("brand") && toasts()[2].classList.contains("bad") && !toasts()[2].classList.contains("ok"));
  for (const t of [...toasts()]) t.querySelector('[data-toast-act="close"]').click();
  run(`toast("Saved", false, { undo: () => {}, action: { label: "See it", fn: () => {}, href: "/x#y" } })`);
  const tt = toasts()[0];
  ok("Undo carries the undo glyph", tt.querySelector('[data-toast-act="undo"]').querySelector("use").getAttribute("href").endsWith("#i-undo"));
  ok("a way on with an address is a link inside the text, under the message", tt.querySelector(".toast-text").querySelector("a") && tt.querySelector(".toast-text").querySelector("a").getAttribute("href") === "/x#y");
  tt.querySelector('[data-toast-act="close"]').click();
  run(`toast("Away", false, { action: { label: "Away", href: "https://evil.example/" } })`);
  ok("an address off this app is never made a link", !toasts()[0].querySelector("a") && !!toasts()[0].querySelector("button.toast-act"));
  toasts()[0].querySelector('[data-toast-act="close"]').click();
  // focus after pressing a toast's own button goes back to the page, not to the removed button
  const pageBtn = new Node("button"); pageBtn.id = "pg"; body.appendChild(pageBtn);
  pageBtn.focus(); dispatch(pageBtn, { type: "click" });
  run(`toast("Undoable", false, { undo: () => {} })`);
  const ub2 = toasts()[0].querySelector('[data-toast-act="undo"]');
  ub2.focus(); dispatch(ub2, { type: "click" });
  ok("a pressed toast button is never remembered as where the focus returns", run("DLG.click") === pageBtn);
  ok("after Undo the focus is back on the page button, not on body or the removed toast button", document.activeElement === pageBtn, document.activeElement && document.activeElement.tagName);
  pageBtn.remove();

  console.log(JSON.stringify(results));
  process.exit(0);
})().catch(e => { console.log(JSON.stringify([["the probe ran to the end", false, String(e && e.stack || e)]])); process.exit(0); });
"""
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
out = subprocess.run(["node", str(probe), bundle], capture_output=True, text=True, encoding="utf-8", timeout=120)
try:
    results = json.loads(out.stdout.strip().splitlines()[-1])
except Exception:
    results = [["the probe printed its results", False, (out.stdout + out.stderr)[:800]]]
for name, ok_, detail in results:
    check(name, ok_, detail)

# ---------- the README lists this test ----------
readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "states_test" in readme)

print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
