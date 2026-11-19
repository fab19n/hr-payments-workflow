"""The dialog shell (step 0c): the drawer as a modal dialog and the styled confirm that replaces the browser's own question box.
Made-up text only. The page script is run in Node against a small stand-in for the page (elements, focus, events, an inert
flag), so the test needs no browser and no server.

Checks: no browser confirm() is left in the page script; ask() answers true for the yes button and false for no, Escape,
the dim and the close button; focus starts on the safe button, stays inside on Tab and Shift+Tab, and returns to what
opened it; the dialog is labelled and modal; the page behind is inert while it is open; a second ask waits for the first;
mayLeave() and closeDrawer() are async, a clean drawer asks nothing, an edited one asks "Discard your changes?"; the drawer
is labelled by its heading, takes the focus, traps Tab, closes on Escape and on the dim, closes at the end of its animation
(or the safety timer) and at once for reduced motion.

Run: .venv\\Scripts\\python -m synthetic_tests.dialog_shell_test
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

from synthetic_tests.appsource import app_bundle, app_source

failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)
        if detail:
            print("     " + str(detail)[:600])


# ---------- 1. no browser confirm() is left ----------
left = [p.name for p in Path(__file__).resolve().parents[1].joinpath("static", "js").rglob("*.js")
        if re.search(r"(?<![\w.])confirm\(", p.read_text(encoding="utf-8"))]
check("no confirm( is left in static/js", not left, left)
src = app_source()
check("ask(), mayLeave() and closeDrawer() are async functions",
      "async function ask(" in src and "async function mayLeave(" in src and "async function closeDrawer(" in src)
check("the Discard question has its title and buttons",
      'title: "Discard your changes?"' in src and 'yes: "Discard"' in src and 'no: "Keep editing"' in src)

# ---------- 2. the page script in Node ----------
tmp = Path(tempfile.mkdtemp(prefix="hrp-dialog-shell-test-"))
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
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5)] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  set tabIndex(v) { this.attrs.tabindex = String(v); }
  appendChild(c) { if (c.parent) c.remove(); c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  get firstElementChild() { return this.children[0] || null; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === body; }
  contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = n => { for (const c of n.children) { if (matches(c, sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get textContent() { return (this.text || "") + this.children.map(c => c.textContent).join(""); }
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
    if (m[5] !== undefined) { top.text = (top.text || "") + m[5]; continue; }
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
const side = new Node("aside"); side.className = "side";
const content = new Node("div"); content.className = "content";
const drawer = new Node("aside"); drawer.id = "drawer"; drawer.className = "drawer"; drawer.hidden = true;
const toastEl = new Node("div"); toastEl.id = "toast"; toastEl.hidden = true;
for (const n of [side, content, drawer, toastEl]) body.appendChild(n);
let calm = true;
const document = {
  body, activeElement: body,
  querySelector: sel => body.querySelector(sel), querySelectorAll: sel => body.querySelectorAll(sel),
  createElement: tag => new Node(tag),
  addEventListener(type, fn, o) { addL(document, type, fn, o); }, removeEventListener(type, fn, o) { delL(document, type, fn, o); },
};
const fetch = () => new Promise(() => {});   // the page's first request never answers: nothing else runs
const ctx = vm.createContext({ document, fetch, console, setTimeout, clearTimeout, FormData: class {},
  localStorage: { getItem: () => null, setItem() {} }, window: { open() {}, print() {}, matchMedia: () => ({ matches: calm }) } });
const run = code => vm.runInContext(code, ctx);
vm.runInContext(fs.readFileSync(appPath, "utf8"), ctx);

const results = [], ok = (name, v, detail) => results.push([name, !!v, detail === undefined ? "" : String(detail)]);
const layers = () => body.children.filter(c => c.className.includes("dlg-layer"));
const key = (k, extra = {}) => dispatch(document.activeElement, { type: "keydown", key: k, ...extra });
const opener = new Node("button"); opener.id = "opener"; body.appendChild(opener);
const openFrom = () => { opener.focus(); dispatch(opener, { type: "click" }); };
const glyphOf = n => { const u = n && n.querySelector("use"); return u ? u.getAttribute("href") : ""; };
const dec = s => String(s).replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const main = new Node("main"); main.id = "main"; body.appendChild(main);

(async () => {
  // ---- ask(): looks, focus, answers ----
  openFrom();
  let p = run(`ask("First line\\n<b>Second</b> & more", { title: "Remove it?", yes: "Remove", no: "Keep", danger: true })`);
  await tick();
  let L = layers()[0], panel = L && L.querySelector(".cfm");
  ok("the confirm opens as one layer", layers().length === 1 && panel);
  ok("it is a modal dialog labelled by its title", panel.getAttribute("role") === "dialog" && panel.getAttribute("aria-modal") === "true"
     && L.querySelector("#" + panel.getAttribute("aria-labelledby")).textContent === "Remove it?", panel.getAttribute("aria-labelledby"));
  ok("it is described by its body", !!L.querySelector("#" + panel.getAttribute("aria-describedby")));
  const paras = L.querySelectorAll("p");
  ok("each line is its own paragraph, escaped", paras.length === 2 && paras[0].text === "First line", paras.length);
  ok("the markup was escaped, not injected", !L.querySelector("b") && L.innerHTML.includes("&lt;b&gt;Second&lt;/b&gt; &amp; more"), L.innerHTML.slice(0, 300));
  const noB = L.querySelector('[data-ask="no"]'), yesB = L.querySelector('[data-ask="yes"]'), xB = L.querySelector(".cfm-x");
  ok("the buttons carry the given words", noB.textContent === "Keep" && yesB.textContent === "Remove");
  ok("the destructive button has the danger style", yesB.classList.contains("danger-solid") && !noB.classList.contains("danger-solid"));
  ok("focus starts on the safe button", document.activeElement === noB);
  ok("the page behind is inert, the drawer too", side.inert && content.inert && drawer.inert);
  // Tab stays inside
  xB.focus(); key("Tab");
  ok("Tab from the last control goes to the first", document.activeElement === noB);
  key("Tab", { shiftKey: true });
  ok("Shift+Tab from the first goes to the last", document.activeElement === xB);
  opener.inert = false; document.activeElement = body; key("Tab");
  ok("Tab with the focus outside comes back inside", panel.contains(document.activeElement));
  yesB.click(); await tick();
  ok("the yes button answers true and the layer goes", (await p) === true && layers().length === 0);
  ok("the page is not inert any more and the focus is back on the opener", !side.inert && !content.inert && !drawer.inert && document.activeElement === opener);

  const answerBy = async (how, opts = "{}") => {
    openFrom(); const q = run(`ask("Sure?", ${opts})`); await tick();
    const l = layers()[0]; how(l); await tick(); return [await q, layers().length, document.activeElement === opener];
  };
  let r = await answerBy(l => l.querySelector('[data-ask="no"]').click());
  ok("the no button answers false", r[0] === false && r[1] === 0 && r[2], r);
  r = await answerBy(() => key("Escape"));
  ok("Escape answers false", r[0] === false && r[1] === 0 && r[2], r);
  r = await answerBy(l => dispatch(l.firstElementChild, { type: "click" }));
  ok("a click on the dim answers false", r[0] === false && r[1] === 0 && r[2], r);
  r = await answerBy(l => l.querySelector(".cfm-x").click());
  ok("the close button answers false", r[0] === false && r[1] === 0 && r[2], r);
  openFrom(); p = run(`ask("Still here?")`); await tick();
  dispatch(layers()[0].querySelector(".cfm"), { type: "click" }); await tick();
  ok("a click on the dialog itself answers nothing", layers().length === 1);
  key("Escape"); await tick(); await p;
  openFrom(); p = run(`ask("Go on?", { safe: "yes" })`); await tick();
  ok("safe: yes puts the focus on the yes button", document.activeElement.dataset.ask === "yes");
  ok("without a title the dialog is labelled by its text", !!layers()[0].querySelector("#" + layers()[0].querySelector(".cfm").getAttribute("aria-labelledby")));
  layers()[0].querySelector('[data-ask="yes"]').click(); await tick(); await p;

  // one at a time: the second waits for the first
  openFrom(); const a1 = run(`ask("One")`), a2 = run(`ask("Two")`); await tick();
  ok("a second ask waits for the first", layers().length === 1 && layers()[0].textContent.includes("One") && !layers()[0].textContent.includes("Two"));
  layers()[0].querySelector('[data-ask="yes"]').click(); await tick(); await tick();
  ok("and opens when the first is answered", layers().length === 1 && layers()[0].textContent.includes("Two") && (await a1) === true);
  layers()[0].querySelector('[data-ask="no"]').click(); await tick();
  ok("each gets its own answer", (await a2) === false && layers().length === 0);

  // animated: the layer stays until its animation ends (or the safety timer)
  calm = false;
  openFrom(); p = run(`ask("Slowly")`); await tick();
  L = layers()[0]; panel = L.querySelector(".cfm");
  ok("it comes in animated", panel.classList.contains("dr-in") && L.firstElementChild.classList.contains("dim-in"));
  L.querySelector('[data-ask="yes"]').click(); await tick();
  ok("it goes out animated and is still there until the animation ends", layers().length === 1 && panel.classList.contains("dr-out") && L.firstElementChild.classList.contains("dim-out"));
  dispatch(panel, { type: "animationend" }); await tick();
  ok("animationend finishes it", (await p) === true && layers().length === 0);
  openFrom(); p = run(`ask("Safety")`); await tick();
  layers()[0].querySelector('[data-ask="no"]').click();
  await sleep(480);
  ok("the safety timer finishes it when animationend never comes", (await p) === false && layers().length === 0 && document.activeElement === opener);
  calm = true;

  // ---- mayLeave / closeDrawer ----
  ok("mayLeave and closeDrawer return promises", typeof run("mayLeave()").then === "function" && typeof run("closeDrawer(true)").then === "function");
  run("var realAsk = ask; ask = async (...a) => { globalThis.__asked = (globalThis.__asked || 0) + 1; return realAsk(...a); }");
  run("globalThis.__asked = 0");
  ok("mayLeave resolves true with a clean drawer, without a dialog", (await run("mayLeave()")) === true && layers().length === 0 && run("globalThis.__asked") === 0);
  openFrom();
  drawer.innerHTML = `<div class="row"><h2>Edit a thing</h2><button id="closeDrawer">Close</button></div><input id="f1"><button id="save">Save</button>`;
  run("showDrawer()");
  ok("an open drawer with nothing typed still asks nothing", (await run("mayLeave()")) === true && layers().length === 0);
  run("state.drawerDirty = () => true");
  p = run("mayLeave()"); await tick();
  L = layers()[0];
  ok("an edited drawer opens the Discard dialog, naming what is open", L && L.querySelector("h2").text === "Discard your changes?" && L.textContent.includes("You have unsaved changes on \u201cEdit a thing\u201d. Closing now loses them."), L && L.textContent);
  ok("with Discard and Keep editing, the safe one focused", L.querySelector('[data-ask="yes"]').text === "Discard" && L.querySelector('[data-ask="no"]').text === "Keep editing"
     && document.activeElement.text === "Keep editing" && L.querySelector('[data-ask="yes"]').classList.contains("danger-solid"));
  ok("the Discard dialog has the board's plate (edit glyph, warn tone, not red), note and closing line", L.querySelector(".plate").classList.contains("warn") && !L.querySelector(".plate").classList.contains("bad")
     && glyphOf(L.querySelector(".plate")).endsWith("#i-edit") && L.querySelector(".cfm-note").text.startsWith("Escape, a click outside the dialog, Cancel, changing page or month")
     && dec(L.querySelector(".cfm-close").textContent).includes("Discarded changes can't be recovered.") && glyphOf(L.querySelector(".cfm-close")).endsWith("#i-alert"));
  const again = run("mayLeave()"); await tick();
  ok("two asks at once share one dialog", layers().length === 1);
  L.querySelector('[data-ask="no"]').click(); await tick();
  ok("Keep editing answers false to both", (await p) === false && (await again) === false);
  p = run("closeDrawer()"); await tick();
  key("Escape"); await tick();
  ok("Keep editing leaves the drawer open", (await p) === false && !drawer.hidden);
  ok("the drawer is still open after Keep editing", !drawer.hidden);
  p = run("closeDrawer()"); await tick();
  layers()[0].querySelector('[data-ask="yes"]').click(); await tick();
  ok("Discard changes closes it", (await p) === true && drawer.hidden && !run("state.drawerDirty"));
  ok("focus goes back to what opened it", document.activeElement === opener);

  // ---- the board's confirms: plate tone and glyph, list, note, closing line ----
  p = run(`ask("Two things are open:", { title: "Mark it as filed?", tone: "brand", glyph: "pack", list: [{ glyph: "alert", tone: "warn", text: "3 payments <b>not</b> complete" }], closing: "A filed month can be reopened later.", yes: "File anyway", no: "Go back" })`); await tick();
  L = layers()[0];
  ok("a brand plate with its own glyph, not red", L.querySelector(".plate").classList.contains("brand") && glyphOf(L.querySelector(".plate")).endsWith("#i-pack") && !L.querySelector('[data-ask="yes"]').classList.contains("danger-solid"));
  ok("a list of glyph lines, escaped", L.querySelector(".cfm-list").querySelectorAll("li").length === 1 && L.querySelector(".cfm-list").querySelector("li").classList.contains("warn") && dec(L.querySelector(".cfm-list").textContent).includes("3 payments <b>not</b> complete") && !L.innerHTML.includes("<b>not"));
  ok("a closing line given as text gets the undo glyph", glyphOf(L.querySelector(".cfm-close")).endsWith("#i-undo") && L.querySelector(".cfm-close").textContent.includes("reopened later"));
  ok("no note box when none is given", !L.querySelector(".cfm-note"));
  L.querySelector('[data-ask="no"]').click(); await tick(); await p;
  p = run(`ask("Sure?", { danger: true })`); await tick();
  ok("without a tone, danger still gives the red plate", layers()[0].querySelector(".plate").classList.contains("bad"));
  layers()[0].querySelector('[data-ask="no"]').click(); await tick(); await p;

  // ---- focus comes back to the right place after a save redraws the page ----
  const mkRow = () => { const r = new Node("tr"); r.setAttribute("data-payment", "7"); r.id = "pay-7"; body.appendChild(r); return r; };
  let row = mkRow();
  document.activeElement = body; dispatch(row, { type: "click" });   // a payment row is no control: the click is what names the opener
  drawer.innerHTML = `<div class="row"><h2>Pay it</h2><button id="closeDrawer">Close</button></div>`; run("showDrawer()");
  ok("a clicked row (no tabindex) is remembered as the opener, with a way to find it again", run("DLG.opener") === row && run("DLG.sel") === '[id="pay-7"]', run("DLG.sel"));
  row.remove(); const row2 = mkRow();   // the save drew the list again
  await run("closeDrawer(true)");
  ok("focus goes to the same row in the redrawn list", document.activeElement === row2, document.activeElement && document.activeElement.tagName);
  row2.remove();
  document.activeElement = body; dispatch(opener, { type: "click" }); opener.remove();
  drawer.innerHTML = `<div class="row"><h2>Pay it</h2></div>`; run("showDrawer()");
  await run("closeDrawer(true)");
  ok("when the opener is gone and cannot be found, focus goes to the page, not nowhere", document.activeElement === main && main.getAttribute("tabindex") === "-1");
  body.appendChild(opener);
  // the page is drawn after the drawer is closed: render() asks for the focus to be put back when it is done
  row = mkRow(); document.activeElement = body; dispatch(row, { type: "click" });
  drawer.innerHTML = `<div class="row"><h2>Pay it</h2></div>`; run("showDrawer()");
  await run("closeDrawer(true)");
  row.remove(); document.activeElement = body; const row3 = mkRow();   // a slow redraw replaced it after the focus went back
  run("dlgRestore()");
  ok("a redraw that comes after the close gets the focus put back on the row", document.activeElement === row3);
  row3.remove();

  // ---- the drawer as a dialog ----
  run("state.drawerDirty = null");
  openFrom(); drawer.innerHTML = `<div class="row"><h2>Another thing</h2><button id="a1">One</button></div><input id="f2"><button id="a2">Two</button><button id="a3" disabled>No</button>`;
  run("showDrawer()");
  const dim = body.querySelector(".dim");
  ok("the drawer is a modal dialog labelled by its heading", drawer.getAttribute("role") === "dialog" && drawer.getAttribute("aria-modal") === "true"
     && drawer.getAttribute("tabindex") === "-1" && drawer.getAttribute("aria-labelledby") === "drawerTitle" && drawer.querySelector("#drawerTitle").text === "Another thing");
  ok("the heading takes the focus", document.activeElement === drawer.querySelector("h2") && drawer.querySelector("h2").getAttribute("tabindex") === "-1");
  ok("a dim is added once and shown", dim && !dim.hidden && dim.getAttribute("aria-hidden") === "true" && body.querySelectorAll(".dim").length === 1);
  ok("the page behind is inert", side.inert && content.inert && !drawer.inert);
  drawer.querySelector("#a2").focus(); key("Tab");
  ok("Tab from the last control goes to the first", document.activeElement === drawer.querySelector("#a1"));
  key("Tab", { shiftKey: true });
  ok("Shift+Tab from the first goes to the last enabled one", document.activeElement === drawer.querySelector("#a2"));
  run("showDrawer()");
  ok("drawn again while open, the opener and the dim stay", body.querySelectorAll(".dim").length === 1 && run("DLG.opener") === opener);
  key("Escape"); await tick();
  ok("Escape closes it (nothing typed)", drawer.hidden && dim.hidden && !side.inert && !content.inert);
  ok("and the focus goes back to the opener", document.activeElement === opener);
  openFrom(); run("showDrawer()"); dispatch(body.querySelector(".dim"), { type: "click" }); await tick();
  ok("a click on the dim closes it", drawer.hidden);
  openFrom(); run("showDrawer()"); run("state.drawerDirty = () => true");
  p = null; dispatch(body.querySelector(".dim"), { type: "click" }); await tick();
  ok("a click on the dim goes through the discard check", layers().length === 1 && !drawer.hidden && layers()[0].textContent.includes("Discard your changes?"));
  ok("with a confirm on top the drawer is inert too", drawer.inert);
  key("Escape"); await tick();
  ok("Escape answers the confirm first and leaves the drawer", layers().length === 0 && !drawer.hidden && !drawer.inert);
  run("state.drawerDirty = null"); await run("closeDrawer()");

  // animated drawer
  calm = false;
  openFrom(); run("showDrawer()");
  ok("it comes in animated", drawer.classList.contains("dr-in") && dim.classList.contains("dim-in"));
  p = run("closeDrawer()"); await tick();
  ok("it goes out animated and is hidden only at the end", !drawer.hidden && drawer.classList.contains("dr-out") && dim.classList.contains("dim-out") && side.inert);
  dispatch(drawer, { type: "animationend" }); await tick();
  ok("animationend hides it", drawer.hidden && dim.hidden && !drawer.classList.contains("dr-out") && !side.inert && document.activeElement === opener);
  openFrom(); run("showDrawer()"); await run("closeDrawer()");
  await sleep(450);
  ok("the safety timer hides it when animationend never comes", drawer.hidden && !side.inert);
  openFrom(); run("showDrawer()"); await run("closeDrawer()"); run("showDrawer()"); await sleep(450);
  ok("drawn again while it was going out, it stays open", !drawer.hidden && !drawer.classList.contains("dr-out"));
  calm = true; await run("closeDrawer(true)");
  ok("reduced motion closes it at once", drawer.hidden && !side.inert);

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

# ---------- 3. the README lists this test ----------
readme = Path(__file__).resolve().parents[1].joinpath("README.md").read_text(encoding="utf-8")
check("the README lists this test", "dialog_shell_test" in readme)

print("\n%s" % ("all passed" if not failures else "%d failed: %s" % (len(failures), "; ".join(failures))))
raise SystemExit(1 if failures else 0)
