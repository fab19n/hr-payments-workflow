"""Matching words (slice 9c): the Move grip and "Try a voucher description", on made-up rules.

Part 1, the server: Try answers by the very matching that adds an SQL voucher as a payment (one function, checklistbook's
guess_match, and the same check of the payment type), names the rule by its place among all of them, and writes nothing; a reorder
saves the Order field of the rules whose place changes, in one change of the audit trail, as editing the field does (no reason
asked), refuses a list read before another change, changes nothing when asked for the order the rules are in, and is all or nothing.

Part 2, the page script, run in Node on a small tree-shaped stand-in for the page, every request answered by the real server: the
grips, places and Try box; moving by keyboard (pick up, Up, Down, Space, Tab, leaving, Escape) and by dragging; one request for a
drop and none while one is on its way; hidden stopped rules and a search; a refused move, one with no clear answer, one answered
after another page was opened, and a reading back that fails.

Run: .venv\\Scripts\\python -m synthetic_tests.matching_words_test
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-matching-words-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import app as server_app, checklistbook, config, db, masters  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_files  # noqa: E402
from synthetic_tests.flags import KEEP_GOING  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}]},
    {"code": "EXB", "name": "Example Beta Ltd", "uses_sql": False, "accounts": [{"label": "Current", "bank": "Example Bank", "number": "000-222"}]},
]}), encoding="utf-8")

passed, failed = [], []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {str(detail)[:900]}" if detail else ""))
        if not KEEP_GOING:
            sys.exit(1)
        failed.append(name)
        return
    passed.append(name)
    print(f"PASS {name}")


db.init()
client = app.test_client()
BASE, H = f"http://127.0.0.1:{config.SETTINGS['port']}", {"X-HRP": "1"}


def call(method, path, expect=200, **kw):
    r = getattr(client, method)(BASE + path, headers=H, **kw)
    assert r.status_code == expect, (method, path, r.status_code, r.data[:800])
    return r.get_json()


def q(sql, args=()):
    with sqlite3.connect(config.DB_PATH) as r:
        r.row_factory = sqlite3.Row
        return [dict(x) for x in r.execute(sql, args)]


EXA, EXB = [r["id"] for r in q("SELECT id FROM entities ORDER BY id")]


def rules(kind="guess_words"):
    return call("get", f"/api/setup/{kind}")["rows"]


def order(kind="guess_words"):
    return [r["id"] for r in rules(kind)]


def sorts(kind="guess_words"):
    return {r["id"]: r["sort"] for r in rules(kind)}


def last_tx():
    return q("SELECT COALESCE(MAX(id), 0) AS n FROM audit_tx")[0]["n"]


def tx_since(n):
    out = []
    for t in q("SELECT * FROM audit_tx WHERE id > ? ORDER BY id", (n,)):
        out.append({**t, "rows": q("SELECT * FROM audit_row WHERE token = ? OR id IN (SELECT row_id FROM audit_sealed WHERE tx_id = ?) ORDER BY id", (t["token"], t["id"]))})
    return out


def try_words(text, expect=200):
    return call("post", "/api/setup/guess_words/try", expect, json={"text": text})


def new_rule(label, words, payment_type="utility"):
    return call("post", "/api/setup/guess_words", json={"fields": {"label": label, "words": words, "payment_type": payment_type}})["id"]


# ---------- part 1: the server ----------
kinds = call("get", "/api/setup/types")["kinds"]
check("the server says which lists are ordered (payment type guesses and filing words, not salary words) and which is tried",
      sorted(k for k, v in kinds.items() if v.get("ordered")) == ["filing_words", "guess_words"] and [k for k, v in kinds.items() if v.get("tried")] == ["guess_words"])

LABEL = {r["key"]: r["label"] for r in call("get", "/api/setup/payment_types")["rows"]}
first = new_rule("Zebra stationery", ["ZEBRAWORD", "ZW PENS"], "utility")
second = new_rule("Zebra rent", ["ZEBRAWORD", "ZEBRA HALL"], "rental")
at = order().index(first) + 1
got = try_words("Payment for zebraword and zw pens, October")
check("Try names the first rule that matches, by its place among all the rules, with its words found and the payment type it gives",
      got == {"rule_id": first, "rule_name": "Zebra stationery", "position": at, "words": ["ZEBRAWORD", "ZW PENS"], "rule_type": "utility", "rule_type_label": LABEL["utility"],
              "payment_type": "utility", "label": LABEL["utility"]}, got)
call("post", f"/api/setup/guess_words/{first}/stop", json={"reason": "Not used for now"})
got = try_words("ZEBRAWORD")
check("a stopped rule is skipped, and the place still counts it", got["rule_id"] == second and got["position"] == at + 1 and got["payment_type"] == "rental", got)
call("post", f"/api/setup/guess_words/{first}/use", json={"reason": "Used again"})
got = try_words("nothing of the kind here")
check("no rule matches: the payment would be Other payment", got == {"rule_id": None, "payment_type": "other", "label": LABEL["other"]}, got)

# a rule whose payment type has been stopped since: adding the voucher would give Other payment, and Try says so
call("post", "/api/setup/payment_types", json={"fields": {"key": "tst_gone", "label": "Test stopped type", "direction": "out"}})
gone_rule = new_rule("Gone type", ["GONEWORD"], "tst_gone")
gone_type = next(r["id"] for r in call("get", "/api/setup/payment_types")["rows"] if r["key"] == "tst_gone")
call("post", f"/api/setup/payment_types/{gone_type}/stop", json={"reason": "No longer paid"})
got = try_words("a goneword voucher")
check("a rule whose payment type was stopped: Try names the rule and its type, and says the payment would be added as Other payment",
      got["rule_id"] == gone_rule and got["rule_type"] == "tst_gone" and got["rule_type_label"] == "Test stopped type" and got["payment_type"] == "other" and got["label"] == LABEL["other"], got)

# the same answer as adding the voucher: _payment_from_entry, which both ways of adding an SQL voucher go through
TEXTS = ["Payment for zebraword and zw pens", "ZEBRA HALL booking", "a goneword voucher", "KWSP contribution for October", "SALARY October 2026", "nothing of the kind here",
         "zebra hall then salary", ""]


def added_as(text):
    with app.test_request_context(BASE + "/x", method="POST", headers=H):
        con = server_app.con()
        s = {"id": 0, "entity_id": EXA, "direction": "out", "description": text, "payee": "Made Up Payee", "doc_no": "PV-9999", "amount": 12.5, "doc_date": "2026-10-05", "einvoice": None}
        pid = server_app._payment_from_entry(con, s)
        cat = con.execute("SELECT category FROM payments WHERE id = ?", (pid,)).fetchone()[0]
        con.rollback()
    return cat


real = [added_as(t) for t in TEXTS]
tried = [try_words(t)["payment_type"] for t in TEXTS]
check("for every description tried, Try's payment type is the one adding an SQL voucher with it gives (the made rules and the app's own, a stopped type, no match, nothing typed)",
      real == tried and len(set(real)) >= 4, list(zip(TEXTS, real, tried)))

seen = []
_match = checklistbook.Book.guess_match
checklistbook.Book.guess_match = lambda self, text: (seen.append(text), (0, ["SPY"]))[1]
try:
    spy_added, spy_tried = added_as("spy one"), try_words("spy two")
finally:
    checklistbook.Book.guess_match = _match
top = rules()[0]
check("there is one matching: adding a voucher and Try both ask checklistbook's guess_match",
      seen == ["spy one", "spy two", "spy two"] and spy_added == top["payment_type"] and spy_tried["words"] == ["SPY"], (seen, spy_added, spy_tried))

n0, rows0 = last_tx(), q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"]
try_words("ZEBRAWORD")
check("Try writes nothing: no entry in the audit trail, no row", last_tx() == n0 and q("SELECT COUNT(*) AS n FROM audit_row")[0]["n"] == rows0)
check("Try without a text is refused", try_words(None, 400)["error"] == "Type a voucher description." and try_words(7, 400)["error"] == "Type a voucher description.")

# --- the reorder ---
was = order()
moved = was[-1]
want = [moved] + was[:-1]
before = sorts()
n0 = last_tx()
r = call("post", "/api/setup/guess_words/order", json={"ids": want, "was": was, "moved": moved})
after = sorts()
check("a reorder saves the Order field of the rules in their new places, 1, 2, 3 and so on, and answers with the list as it is then",
      [x["id"] for x in r["rows"]] == want and order() == want and [after[i] for i in want] == list(range(1, len(want) + 1)), (before, after))
tx = tx_since(n0)
changed = [i for i in want if before[i] != after[i]]
check("it is one change in the audit trail, by the user, with no reason asked (as editing the Order field asks none)",
      len(tx) == 1 and tx[0]["source"] == "user" and not tx[0]["reason"] and tx[0]["action"] == "POST /api/setup/guess_words/order", tx and {k: tx[0][k] for k in ("source", "reason", "action")})


def row_shape(row):
    old, new = json.loads(row["before"] or "{}"), json.loads(row["after"] or "{}")
    return row["tbl"], row["op"], sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k))


trail_rows = [x for x in tx[0]["rows"] if x["tbl"] != "activity"] if tx else []  # the activity log's own lines are in the entry too
check("the trail has a row for each rule whose Order changed, and only those, each changing the Order alone",
      sorted(int(x["row_key"]) for x in trail_rows) == sorted(changed) and all(row_shape(x) == ("guess_words", "update", ["sort"]) for x in trail_rows),
      [row_shape(x) for x in trail_rows])
names = {x["id"]: x["label"] for x in rules()}
summary = tx[0]["summary"] if tx else ""
check("its words are the ones editing the Order field writes, one line a rule, the rule moved named first",
      summary.startswith(f"Changed payment type from sql vouchers {names[moved]}: order") and summary.count(": order") == len(changed), summary)
n0 = last_tx()
call("patch", f"/api/setup/guess_words/{moved}", json={"fields": {"sort": 0}})
edit = tx_since(n0)
check("...which is what editing the Order field in the rule's dialog leaves: the same kind of entry, row and words",
      len(edit) == 1 and edit[0]["source"] == "user" and not edit[0]["reason"] and [row_shape(x) for x in edit[0]["rows"] if x["tbl"] != "activity"] == [("guess_words", "update", ["sort"])]
      and edit[0]["summary"] == f"Changed payment type from sql vouchers {names[moved]}: order", edit and edit[0]["summary"])

now = order()
swapped = [now[1], now[0]] + now[2:]
n0 = last_tx()
call("post", "/api/setup/guess_words/order", json={"ids": swapped, "was": now, "moved": now[0]})
check("the real matching follows the new order at once", order() == swapped)
n0 = last_tx()
again = call("post", "/api/setup/guess_words/order", json={"ids": swapped, "was": now, "moved": now[0]})
check("the same drop sent twice changes nothing the second time and is no new entry", [x["id"] for x in again["rows"]] == swapped and order() == swapped and last_tx() == n0)
other = [swapped[2], swapped[0], swapped[1]] + swapped[3:]
stale = call("post", "/api/setup/guess_words/order", 409, json={"ids": other, "was": now, "moved": other[0]})
check("a move made from a list read before another change is refused, and nothing changes",
      stale["error"] == masters.ORDER_CHANGED and order() == swapped and last_tx() == n0, stale)
a, b = new_rule("Added since", ["ADDEDWORD"]), None
n0 = last_tx()
stale = call("post", "/api/setup/guess_words/order", 409, json={"ids": list(reversed(swapped)), "was": swapped})
check("...and so is one made before a rule was added (or deleted)", stale["error"] == masters.ORDER_CHANGED and order() == swapped + [a] and last_tx() == n0)
call("delete", f"/api/setup/guess_words/{a}", json={"reason": "Only for the test"})
now = order()
BAD = [{"ids": now, "was": None}, {"ids": "x", "was": now}, {"ids": now + [now[0]], "was": now + [now[0]]}, {"ids": [True] + now[1:], "was": now}, {"ids": now[1:], "was": now}, {}]
n0 = last_tx()
check("a body that isn't the whole new order and the order it was is refused", all(call("post", "/api/setup/guess_words/order", 400, json=x)["error"] for x in BAD) and order() == now and last_tx() == n0)
check("salary words, payment types and an unknown list have no order to change",
      all(call("post", f"/api/setup/{k}/order", 404, json={"ids": [], "was": []})["error"] for k in ("hint_words", "payment_types", "nothing_such")))

_update, calls_ = masters.update, []


def breaks(con, kind, rid, fields, quiet=False):
    calls_.append(rid)
    if len(calls_) == 2:
        raise masters.Refused("A test refusal on the second rule.")
    return _update(con, kind, rid, fields, quiet)


masters.update = breaks
try:
    kept, n0 = sorts(), last_tx()
    refused = call("post", "/api/setup/guess_words/order", 400, json={"ids": list(reversed(now)), "was": now})
finally:
    masters.update = _update
check("all or nothing: a refusal part of the way through leaves every rule's Order as it was, with no entry",
      len(calls_) == 2 and refused["error"] == "A test refusal on the second rule." and sorts() == kept and last_tx() == n0, (calls_, refused))

call("post", "/api/setup/entities", json={"fields": {"code": "EXC", "name": "Example Gamma Ltd", "uses_sql": 1}})  # a company added here has the starter checklist
code = call("get", "/api/meta")["checklist_codes"]
for name, word in (("Made filing one", "FILEONE"), ("Made filing two", "FILETWO"), ("Made filing three", "FILETHREE")):
    rid = call("post", "/api/setup/filing_words", json={"fields": {"label": name, "words": [word], "doc_kind": "invoice", "checklist_code": next(iter(code))}})["id"]
    call("patch", f"/api/setup/filing_words/{rid}", json={"fields": {"sort": 0}})  # a shared Order, as the app's own words can have
filing = rules("filing_words")
fids = [x["id"] for x in filing]
ties = len({x["sort"] for x in filing}) < len(filing)
want = fids[:1] + [fids[2], fids[1]] + fids[3:]
call("post", "/api/setup/filing_words/order", json={"ids": want, "was": fids, "moved": fids[2]})
check("filing words that shared an Order keep their order but for the move, and each then has its own place",
      ties and order("filing_words") == want and sorted(sorts("filing_words").values()) == list(range(1, len(want) + 1)), (ties, sorts("filing_words")))

# ---------- part 2: the page ----------
# some made rules to move, and a stopped one between them; more than 25 rules in all, so a list cut into pages would show
for r in rules():
    if r["label"] in ("Gone type",):
        call("delete", f"/api/setup/guess_words/{r['id']}", json={"reason": "Only for the server checks"})
hidden = new_rule("Hidden middle", ["HIDDENWORD"])
for n in range(1, 22):
    new_rule(f"Filler rule {n:02d}", [f"FILLER{n:02d}WORD"])
start = order()
a_, b_ = first, second
rest = [i for i in start if i not in (a_, b_, hidden)]
call("post", "/api/setup/guess_words/order", json={"ids": [a_, hidden, b_] + rest, "was": start})
call("post", f"/api/setup/guess_words/{hidden}/stop", json={"reason": "Stopped for the test"})
PAGE_ORDER = order()
assert PAGE_ORDER[:3] == [a_, hidden, b_] and len(PAGE_ORDER) > 25

PROBE = r"""
const fs = require("fs"), vm = require("vm"), readline = require("readline");
const [fxPath, ...files] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const unheard = [];
process.on("unhandledRejection", e => unheard.push(String(e && e.stack || e).slice(0, 300)));

/* ---- the pipe to the real server ---- */
const waiting = new Map(); let askN = 0;
readline.createInterface({ input: process.stdin }).on("line", l => { const m = JSON.parse(l); const f = waiting.get(m.id); waiting.delete(m.id); f(m); });
const server = (method, path, body) => new Promise(res => { const id = ++askN; waiting.set(id, res); process.stdout.write("@@REQ " + JSON.stringify({ id, method, path, body }) + "\n"); });
// NET.delay[path]: ms before the answer; NET.fail[path]: "net" (never reaches the server), "lost" (the server does it, the answer is lost);
// NET.down: no read or write reaches it
const NET = { delay: {}, fail: {}, down: false, sent: [] };
async function fetch(path, init = {}) {
  const method = init.method || "GET", body = init.body ? JSON.parse(init.body) : null;
  NET.sent.push([method, path, body]);
  const how = NET.down ? "net" : NET.fail[path], ms = NET.delay[path];
  const wait = ms ? sleep(Array.isArray(ms) ? ms.shift() || 0 : ms) : null;
  if (how === "net") { await wait; throw new TypeError("Failed to fetch"); }
  const r = await server(method, path, body);
  await wait;
  if (how === "lost") throw new TypeError("Failed to fetch");
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
}

/* ---- the stand-in page: a tree built from the markup written into it ---- */
const unesc = s => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
function matchOne(n, sel) {
  const m = /^([a-z0-9]*)((?:\[[^\]]+\]|\.[\w-]+|#[\w-]+)*)(?::not\(([^)]*)\))?$/.exec(sel);
  if (!m) return false;
  if (m[1] && n.tagName.toLowerCase() !== m[1]) return false;
  for (const [, part] of m[2].matchAll(/(\[[^\]]+\]|\.[\w-]+|#[\w-]+)/g)) {
    if (part[0] === ".") { if (!n.classList.contains(part.slice(1))) return false; }
    else if (part[0] === "#") { if (n.id !== part.slice(1)) return false; }
    else { const x = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(part); if (!x || !n.hasAttribute(x[1]) || (x[2] !== undefined && n.getAttribute(x[1]) !== x[2])) return false; }
  }
  return !(m[3] && matchOne(n, m[3]));
}
function matches(n, sel) {
  return sel.split(",").some(s => {
    const parts = s.trim().split(/\s+/);
    if (!matchOne(n, parts[parts.length - 1])) return false;
    let at = n.parent;
    for (let i = parts.length - 2; i >= 0; i--) { while (at && !matchOne(at, parts[i])) at = at.parent; if (!at) return false; at = at.parent; }
    return true;
  });
}
const listeners = new Map();
const addL = (t, type, fn, o) => { const l = listeners.get(t) || []; l.push({ type, fn, capture: o === true || !!(o && o.capture) }); listeners.set(t, l); };
class Node {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.attrs = {}; this.children = []; this.parent = null; this._html = ""; this.text = ""; this.dataset = {}; this.style = {}; this.hidden = false; this.inert = false; this.scrollTop = 0; this.value = ""; this.checked = false; this.disabled = false; }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; } set className(v) { this.attrs.class = v; }
  get type() { return this.attrs.type || ""; }
  get classList() {
    const n = this, get = () => n.className.split(/\s+/).filter(Boolean);
    return { add: (...c) => { n.className = [...new Set([...get(), ...c])].join(" "); }, remove: (...c) => { n.className = get().filter(x => !c.includes(x)).join(" "); },
      contains: c => get().includes(c), toggle: (c, on) => { const want = on ?? !get().includes(c); want ? n.classList.add(c) : n.classList.remove(c); } };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { if (c.parent) c.remove(); c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(x => x !== this); this.parent = null; } }
  get firstChild() { return this.children[0] || (this.text ? this : null); }
  get firstElementChild() { return this.children[0] || null; }
  get parentNode() { return this.parent; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n === body; }
  contains(o) { for (let n = o; n; n = n.parent) if (n === this) return true; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (matches(n, sel)) return n; return null; }
  querySelectorAll(sel) { const out = []; const walk = n => { for (const c of n.children) { if (matches(c, sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  get textContent() { return unesc(this.text) + this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.children.forEach(c => { c.parent = null; }); this.children = []; this.text = String(v).replace(/&/g, "&amp;"); this._html = this.text; }
  get innerHTML() { return this._html; }
  set innerHTML(h) { this._html = String(h); this.children.forEach(c => { c.parent = null; }); this.children = []; this.text = ""; parseInto(this, this._html); }
  insertAdjacentHTML(where, h) { parseInto(this, h); this._html += h; }
  getBoundingClientRect() {
    if (this.tagName !== "TR" || !this.parent) return { top: 0, height: 600 };
    return { top: 200 + this.parent.children.indexOf(this) * 40, height: 40 };
  }
  focus() { for (let n = this; n; n = n.parent) if (n.inert) return; focused = this; }
  blur() {} scrollIntoView() {} setSelectionRange() {} after() {}
  addEventListener(type, fn, o) { addL(this, type, fn, o); } removeEventListener() {}
  click() { dispatch(this, { type: "click" }); }
}
function parseInto(root, html) {
  const stack = [root], tok = /<(\/?)([a-zA-Z0-9]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>|([^<]+)/g;
  const VOID = new Set(["use", "input", "br", "img"]);
  let m;
  while ((m = tok.exec(html))) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) { top.text += m[5]; continue; }
    const [, close, tag, attrs, selfClose] = m;
    if (close) { if (stack.length > 1) stack.pop(); continue; }
    const n = new Node(tag);
    for (const [, k, v] of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)) { n.setAttribute(k, v === undefined ? "" : unesc(v)); if (k === "value") n.value = unesc(v); if (k === "checked") n.checked = true; if (k === "hidden") n.hidden = true; }
    top.appendChild(n);
    if (!selfClose && !VOID.has(tag.toLowerCase())) stack.push(n);
  }
}
const body = new Node("body");
let focused = null;
const document = {
  body, hidden: false,
  get activeElement() { return focused && focused.isConnected ? focused : body; }, set activeElement(v) { focused = v; },
  querySelector: s => body.querySelector(s), querySelectorAll: s => body.querySelectorAll(s),
  getElementById: id => body.querySelector("#" + id), createElement: null,
  addEventListener(t, f, o) { addL(document, t, f, o); }, removeEventListener() {},
};
// as a browser: capture from the document down, then the target and up; stopPropagation ends it after the node it is on
function dispatch(target, ev) {
  ev.target = target; ev.defaultPrevented = false; let stopped = false;
  ev.preventDefault = () => { ev.defaultPrevented = true; }; ev.stopPropagation = () => { stopped = true; };
  const path = []; for (let n = target; n; n = n.parent) path.push(n);
  path.push(document);
  const results = [];
  const run = (t, capture) => { for (const l of [...(listeners.get(t) || [])]) if (l.type === ev.type && l.capture === capture) results.push(l.fn(ev)); };
  for (const t of [...path].reverse()) { if (stopped) break; run(t, true); }
  for (const t of path) { if (stopped) break; run(t, false); }
  ev.done = Promise.all(results);
  return ev;
}
for (const [id, tag] of [["nav", "nav"], ["pageTitle", "div"], ["monthLabel", "span"], ["main", "main"], ["drawer", "aside"], ["toast", "div"]]) { const n = new Node(tag); n.id = id; body.appendChild(n); }
body.querySelector("#drawer").hidden = true;

const win = { matchMedia: () => ({ matches: true }), scrollX: 0, scrollY: 0, scrollTo() {}, addEventListener() {}, print() {}, open() {} };
const sandbox = { document, fetch, FormData: class {}, console: { ...console, error() {} }, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, window: win, navigator: {} };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);

const $ = s => body.querySelector(s);
const out = {};
const tryit = async (name, fn) => { try { out[name] = await fn(); } catch (e) { out[name] = { error: String(e && e.stack || e).slice(0, 600) }; } };
const idle = async (ms = 30) => { for (let i = 0; i < 400; i++) { await sleep(ms); if (!waiting.size && !run(`RANK.saving`)) { await sleep(ms); if (!waiting.size) return; } } throw new Error("never idle"); };
const rowsOnShow = () => $("#setupList") ? $("#setupList").querySelectorAll("tr[data-setup-row]") : [];
const shown = () => rowsOnShow().map(tr => +tr.dataset.setupRow);
const grips = () => $("#setupList") ? $("#setupList").querySelectorAll("[data-grip]") : [];
const grip = id => $("#setupList").querySelector(`[data-grip="${id}"]`);
const places = () => rowsOnShow().map(tr => tr.querySelector(".rank-n").textContent);
const said = () => $("#rank-say") ? $("#rank-say").textContent : null;
const toasts = () => run(`__toasts.map(t => t.msg)`);
const posts = () => NET.sent.filter(x => /\/order$/.test(x[1])).map(x => x[2]);
const focusId = () => document.activeElement.id || "";
const click = async el => { if (el.tagName === "BUTTON") el.focus(); const ev = dispatch(el, { type: "click", button: 0 }); await sleep(0); return ev; };
const key = async (el, k) => { const ev = dispatch(el, { type: "keydown", key: k }); await sleep(0); return ev; };
const pointer = (el, type, y, buttons = 1, id = 1) => dispatch(el, { type, clientY: y, clientX: 10, button: 0, buttons, pointerId: id });
const midOf = i => 200 + i * 40 + 20;
const order = async () => (await server("GET", "/api/setup/guess_words", null)).body.rows.map(r => r.id);
const setOrder = async ids => server("POST", "/api/setup/guess_words/order", { ids, was: await order() });
async function open(kind = "guess_words", entity = FX.EXA) {
  Object.assign(NET, { delay: {}, fail: {}, down: false });
  await run(`closeDrawer(true)`);
  await run(`navigate({ view: "setup", entity: ${entity}, month: "2026-11", sub: ${JSON.stringify(kind)}, id: null, params: {} }, { fresh: true })`);
  await idle();
  run(`__toasts.length = 0`); NET.sent.length = 0; focused = null;
}
async function reset() { await setOrder(FX.ORDER); await open(); run(`state.setup.stopped = false; LIST_REDRAW["setup-guess_words"]()`); }
const type = async (text, wait = 400) => { const el = $("#mt-try"); el.value = text; el.focus(); dispatch(el, { type: "input" }); await sleep(wait); await idle(); };
const result = () => { const el = $("#mt-result"); return el ? { text: el.textContent, cls: el.className, role: el.getAttribute("role") } : null; };
const marked = () => ({ rows: rowsOnShow().filter(tr => tr.classList.contains("mt-hit")).map(tr => +tr.dataset.setupRow), words: ($("#setupList")?.querySelectorAll("[data-word]") || []).filter(w => w.classList.contains("hit")).map(w => w.textContent) });

(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));
  const meta = (await server("GET", "/api/meta", null)).body;
  run(`state.meta = ${JSON.stringify(meta)}; state.month = "2026-11"; state.day = dayKey(); state.entity = ${FX.EXA}; menuNextEnsure = () => {};
    globalThis.__toasts = []; { const was = toastShow; toastShow = (msg, bad, opts) => { __toasts.push({ msg, bad, opts }); return was(msg, bad, opts); }; }
    globalThis.__opened = []; { const was = openSetup; openSetup = (kind, id, o) => { __opened.push([kind, id]); return was(kind, id, o); }; }
    globalThis.__closed = 0; { const was = closeDrawer; closeDrawer = f => { __closed++; return was(f); }; }
    for (const v of ["Overview"]) globalThis["view" + v] = async main => { main.innerHTML = "<div id='ov'>Overview page</div>"; }; trailNotice = () => {};`);

  await tryit("drawn", async () => {
    await open();
    const head = $("#setupList").querySelectorAll("th").map(t => t.textContent);
    const g = grips()[2];
    return { ids: shown(), places: places(), head, sorters: $("#setupList").querySelectorAll("[data-sort]").length, more: $("#setupList").querySelectorAll("[data-setup-more]").length, grips: grips().length,
      label: g.getAttribute("aria-label"), pressed: g.getAttribute("aria-pressed"), by: g.getAttribute("aria-describedby"), off: g.getAttribute("aria-disabled"), tag: g.tagName,
      help: $("#rank-help").textContent, note: $("#setupMain").innerHTML.includes("The first rule that matches wins, so order matters."),
      live: [$("#rank-say").getAttribute("role"), $("#rank-say").getAttribute("aria-live"), !!$("#rank-say").closest("#setupList")],
      names: rowsOnShow().slice(0, 2).map(tr => tr.querySelector("[data-setup-open]").textContent), box: !!$("#mt-try"), boxValue: $("#mt-try").value, boxSaid: $("#mt-try").getAttribute("aria-describedby"),
      label2: $("#mt-try-l").textContent, note2: $("#mt-try-note").textContent, result: result(), words: rowsOnShow()[0].querySelectorAll("[data-word]").map(w => w.textContent) };
  });
  await tryit("others", async () => {
    const r = {};
    await open("filing_words"); r.filing = { grips: grips().length, rows: shown().length, box: !!$("#mt-try"), places: places().slice(0, 3) };
    await open("hint_words"); r.salary = { grips: grips().length, rows: shown().length, box: !!$("#mt-try"), sorters: $("#setupList").querySelectorAll("[data-sort]").length };
    await open("doc_types"); r.types = { grips: grips().length, sorters: $("#setupList").querySelectorAll("[data-sort]").length };
    return r;
  });

  await tryit("tryBox", async () => {
    const r = {};
    await reset();
    await type("Paid zebraword for the hall");
    r.match = result(); r.matched = marked(); r.sent = NET.sent.filter(x => /try$/.test(x[1])); r.addresses = NET.sent.map(x => x[1]).filter(p => /zebra/i.test(p));
    await type("hiddenword only"); r.stopped = result(); r.stoppedMarked = marked();
    await type("KUMPULAN of nothing at all qqq"); r.none = result();
    await type(""); r.empty = result(); NET.sent.length = 0; await sleep(300); r.emptySent = NET.sent.length;
    // keys typed quickly ask once, for the last text
    NET.sent.length = 0;
    for (const t of ["z", "ze", "zeb", "zebra hall"]) { $("#mt-try").value = t; dispatch($("#mt-try"), { type: "input" }); await sleep(30); }
    await sleep(400); await idle(); r.debounced = NET.sent.filter(x => /try$/.test(x[1])).map(x => x[2].text); r.hall = result();
    // an older, slower answer never replaces a newer one; while the newer is on its way the old one is dimmed, with no row marked
    NET.delay["/api/setup/guess_words/try"] = [600, 20];
    $("#mt-try").value = "zebraword"; dispatch($("#mt-try"), { type: "input" }); await sleep(320);
    $("#mt-try").value = "filler01word"; dispatch($("#mt-try"), { type: "input" }); r.stale = { result: result(), marked: marked() };
    await sleep(900); await idle(); r.latest = result(); r.latestMarked = marked(); NET.delay = {};
    // an older answer that comes after more was typed, before the newer text has been asked, is not shown
    NET.delay["/api/setup/guess_words/try"] = [120];
    $("#mt-try").value = "zebraword"; dispatch($("#mt-try"), { type: "input" }); await sleep(300);
    $("#mt-try").value = "filler02word"; dispatch($("#mt-try"), { type: "input" }); await sleep(130); r.between = result();
    await sleep(400); await idle(); NET.delay = {}; r.betweenAfter = result();
    // the same text tried again after the rules changed: the first answer, coming late, never replaces the newer one
    NET.delay["/api/setup/guess_words/try"] = [700, 20];
    $("#mt-try").value = "zebraword again"; dispatch($("#mt-try"), { type: "input" }); await sleep(320);
    await server("POST", `/api/setup/guess_words/${FX.ORDER[0]}/stop`, { reason: "For a moment" });
    run(`tryRun()`); await sleep(900); await idle(); NET.delay = {}; r.changed = result();
    await server("POST", `/api/setup/guess_words/${FX.ORDER[0]}/use`, { reason: "Used again" });
    $("#mt-try").value = "filler01word"; dispatch($("#mt-try"), { type: "input" }); await sleep(400); await idle();
    // the list drawn again (a save, a stop) tries the same text on it
    await run(`render()`); await idle(); r.redrawn = { value: $("#mt-try").value, result: result(), marked: marked() };
    // no clear answer: it says it couldn't be tried
    NET.fail["/api/setup/guess_words/try"] = "net"; await type("zebraword again"); r.broken = result(); r.brokenToasts = toasts(); NET.fail = {};
    // an answer that comes after another section was opened writes nothing and says nothing
    NET.delay["/api/setup/guess_words/try"] = 500;
    $("#mt-try").value = "zebraword late"; dispatch($("#mt-try"), { type: "input" }); await sleep(320);
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: "2026-11", sub: "hint_words", id: null, params: {} }, { fresh: true })`);
    run(`__toasts.length = 0`); const before = $("#main").innerHTML; await sleep(500); await idle();
    r.left = { same: $("#main").innerHTML === before, box: !!$("#mt-try"), toasts: toasts() }; NET.delay = {};
    await open(); r.back = $("#mt-try").value;
    await run(`navigate({ view: "overview", entity: "all", month: "2026-11", sub: null, id: null, params: {} }, { fresh: true })`); await idle();
    await open(); r.gone = $("#mt-try").value;
    return r;
  });

  await tryit("keys", async () => {
    const r = {};
    await reset();
    const [a, h, b, c] = FX.ORDER;
    const g = grip(a); g.focus();
    await key(g, "ArrowDown"); r.unpicked = { ids: shown().slice(0, 3), posts: posts().length };
    await click(grip(a)); r.picked = { pressed: grip(a).getAttribute("aria-pressed"), said: said(), held: grip(a).closest("tr").classList.contains("rank-held"), posts: posts().length };
    await key(grip(a), "ArrowUp"); r.first = said();
    const ev = await key(grip(a), "ArrowDown");   // past the stopped rule that is hidden
    r.passed = { said: said(), ids: shown().slice(0, 3), focus: focusId(), label: grip(a).getAttribute("aria-label"), pressed: grip(a).getAttribute("aria-pressed"), prevented: ev.defaultPrevented, places: places().slice(0, 3), posts: posts().length };
    await key(grip(a), "ArrowDown"); r.moved = { said: said(), ids: shown().slice(0, 3), posts: posts().length };
    await type("zebraword", 50); r.heldTry = { result: result(), marked: marked() };
    grip(a).focus();
    NET.delay["/api/setup/guess_words/order"] = 400;
    await click(grip(a)); await sleep(60);
    r.saving = { said: said(), off: grips().every(x => x.getAttribute("aria-disabled") === "true"), pressed: grip(a).getAttribute("aria-pressed"), posts: posts().length, result: result() };
    // nothing else can start while it is on its way: no second drop, no other pick up, no drag, no second request
    await click(grip(a)); await click(grip(c)); r.blockedSaid = said(); await key(grip(c), "ArrowDown");
    pointer(grip(b), "pointerdown", midOf(0)); pointer(grip(b), "pointermove", midOf(3)); pointer(grip(b), "pointerup", midOf(3), 0);
    await sleep(60); r.blocked = { posts: posts().length, pressed: grips().map(x => x.getAttribute("aria-pressed")).filter(x => x === "true").length, ids: shown().slice(0, 3) };
    grip(a).focus();
    await idle(); NET.delay = {};
    r.saved = { said: said(), posts: posts(), ids: shown().slice(0, 3), server: (await order()).slice(0, 4), focus: focusId(), off: grips().some(x => x.hasAttribute("aria-disabled")),
      flash: grip(a).closest("tr").classList.contains("rank-flash"), result: result(), marked: marked(), places: places().slice(0, 3), toasts: toasts() };
    // dropped where it was: nothing is sent
    NET.sent.length = 0;
    await click(grip(c)); await key(grip(c), "ArrowDown"); await key(grip(c), "ArrowUp"); await click(grip(c)); await idle();
    r.nowhere = { posts: posts().length, said: said(), pressed: grip(c).getAttribute("aria-pressed") };
    return { ...r, ids: { a, h, b, c } };
  });

  await tryit("escape", async () => {
    await reset();
    const [a] = FX.ORDER;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await key(grip(a), "ArrowDown");
    run(`__closed = 0`);
    const ev = await key(grip(a), "Escape"); await idle();
    const r = { ids: shown().slice(0, 3), said: said(), pressed: grip(a).getAttribute("aria-pressed"), posts: posts().length, closed: run(`__closed`), prevented: ev.defaultPrevented, focus: focusId(), grip: `rank-grip-${a}` };
    await key(grip(a), "Escape"); r.later = run(`__closed`);   // with nothing picked up, Escape does what it always did
    return r;
  });

  await tryit("leaving", async () => {
    const r = {};
    const [a, , b] = FX.ORDER;
    await reset();
    await click(grip(a)); await key(grip(a), "ArrowDown"); NET.sent.length = 0;
    dispatch(grip(a), { type: "focusout", relatedTarget: null }); await idle(); r.noTarget = { posts: posts().length, pressed: grip(a).getAttribute("aria-pressed") };
    const name = rowsOnShow()[0].querySelector("[data-setup-open]");
    dispatch(grip(a), { type: "focusout", relatedTarget: name }); name.focus(); await idle();
    r.blur = { posts: posts().length, server: (await order()).slice(0, 3), said: said(), focus: document.activeElement.dataset.setupOpen || "", was: name.dataset.setupOpen };
    await reset();
    await click(grip(a)); await key(grip(a), "ArrowDown"); NET.sent.length = 0;
    const tab = await key(grip(a), "Tab"); const kept = grip(a); await idle();
    r.tab = { posts: posts().length, server: (await order()).slice(0, 3), prevented: tab.defaultPrevented };
    // Tab drops without drawing the rows again at once: the focus is on its way to the next control
    await reset(); await click(grip(a)); await key(grip(a), "ArrowDown"); NET.delay["/api/setup/guess_words/order"] = 200;
    const before = grip(a); await key(before, "Tab"); r.tabNoRedraw = before.isConnected && grip(a) === before; await idle(); NET.delay = {};
    // another page opened while a rule is picked up: nothing is saved
    await reset(); await click(grip(a)); await key(grip(a), "ArrowDown"); NET.sent.length = 0;
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: "2026-11", sub: "doc_types", id: null, params: {} }, { fresh: true })`); await idle();
    r.left = { posts: posts().length, on: run(`rankOn(RANK.list)`) };
    await open(); r.back = { ids: shown().slice(0, 3), pressed: grips().filter(x => x.getAttribute("aria-pressed") === "true").length };
    return r;
  });

  await tryit("search", async () => {
    const r = {};
    const [a] = FX.ORDER;
    await reset();
    await click(grip(a)); await key(grip(a), "ArrowDown");
    const q = $("#setupMain").querySelector('[data-search="setup-guess_words"]');
    q.value = "zebra"; q.focus(); dispatch(q, { type: "input" }); await sleep(10);
    r.cancelled = { ids: shown(), said: said(), help: $("#rank-help").textContent, off: grips().every(x => x.getAttribute("aria-disabled") === "true"), pressed: grips().filter(x => x.getAttribute("aria-pressed") === "true").length, posts: posts().length,
      label: grips()[1].getAttribute("aria-label"), places: places() };
    await click(grips()[0]); r.noPick = { pressed: grips().filter(x => x.getAttribute("aria-pressed") === "true").length };
    pointer(grips()[0], "pointerdown", midOf(0)); pointer(grips()[0], "pointermove", midOf(1)); pointer(grips()[0], "pointerup", midOf(1), 0); await idle();
    r.noDrag = { posts: posts().length, ids: shown() };
    q.value = ""; dispatch(q, { type: "input" }); await sleep(10);
    r.cleared = { off: grips().some(x => x.hasAttribute("aria-disabled")), help: $("#rank-help").textContent };
    // with Show stopped on, a step is one row on show
    run(`state.setup.stopped = true; LIST_REDRAW["setup-guess_words"]()`);
    await click(grip(a)); await key(grip(a), "ArrowDown"); r.all = { ids: shown().slice(0, 3), said: said() };
    await key(grip(a), "Escape");
    const last = FX.ORDER[FX.ORDER.length - 1];
    await click(grip(last)); await key(grip(last), "ArrowDown"); r.last = said(); await key(grip(last), "Escape");
    return r;
  });

  await tryit("drag", async () => {
    const r = {};
    const [a, h, b, c, d] = FX.ORDER;
    await reset();
    // a press that moves under 5 pixels is no drag: the click after it picks up as it always does
    pointer(grip(a), "pointerdown", midOf(0)); pointer(grip(a), "pointermove", midOf(0) + 3); pointer(grip(a), "pointerup", midOf(0) + 3, 0);
    await click(grip(a)); r.press = { pressed: grip(a).getAttribute("aria-pressed"), posts: posts().length };
    await key(grip(a), "Escape");
    // dragged below the third row on show: the rows follow the pointer; nothing is sent until it is let go
    run(`__opened.length = 0`); NET.sent.length = 0;
    pointer(grip(a), "pointerdown", midOf(0));
    pointer(body, "pointermove", midOf(1) + 5); r.during1 = { ids: shown().slice(0, 3), posts: posts().length, cls: body.classList.contains("rank-dragging") };
    pointer(body, "pointermove", midOf(2) + 5); r.during2 = { ids: shown().slice(0, 3), posts: posts().length, places: places().slice(0, 3), pressed: grip(a).getAttribute("aria-pressed") };
    pointer(body, "pointerup", midOf(2) + 5, 0);
    const row = grip(a).closest("tr"); dispatch(grip(a), { type: "click", button: 0 }); dispatch(row.querySelector(".rank-n"), { type: "click", button: 0 });   // the click the release raises, wherever it lands
    await idle();
    r.dropped = { posts: posts(), server: (await order()).slice(0, 5), said: said(), opened: run(`__opened.slice()`), cls: body.classList.contains("rank-dragging"), pressed: grips().filter(x => x.getAttribute("aria-pressed") === "true").length };
    await sleep(20);
    await click(rowsOnShow()[1].querySelector(".rank-n")); await idle(); r.rowClick = run(`__opened.slice()`);   // a later click on a row still opens its rule
    await run(`closeDrawer(true)`); await idle();
    // dragged back up
    await reset();
    pointer(grip(c), "pointerdown", midOf(2)); pointer(body, "pointermove", midOf(0) - 5); pointer(body, "pointerup", midOf(0) - 5, 0); await idle();
    r.up = (await order()).slice(0, 4);
    // there and back again: nothing is sent
    await reset(); NET.sent.length = 0;
    pointer(grip(b), "pointerdown", midOf(1)); pointer(body, "pointermove", midOf(3) + 5); pointer(body, "pointermove", midOf(1) - 5); pointer(body, "pointermove", midOf(1)); pointer(body, "pointerup", midOf(1), 0); await idle();
    r.backAgain = { posts: posts().length, ids: shown().slice(0, 3) };
    // Escape during a drag puts it back, and the release after it does nothing
    await reset(); NET.sent.length = 0; run(`__closed = 0`);
    pointer(grip(a), "pointerdown", midOf(0)); pointer(body, "pointermove", midOf(2) + 5); await key(grip(a), "Escape"); pointer(body, "pointerup", midOf(2) + 5, 0); await idle();
    r.escaped = { posts: posts().length, ids: shown().slice(0, 3), closed: run(`__closed`), cls: body.classList.contains("rank-dragging") };
    // the pointer taken away (pointercancel), or let go where the page couldn't hear it: back where it was, nothing sent
    pointer(grip(a), "pointerdown", midOf(0)); pointer(body, "pointermove", midOf(2) + 5); pointer(body, "pointercancel", 0, 0); await idle();
    r.cancel = { posts: posts().length, ids: shown().slice(0, 3) };
    pointer(grip(a), "pointerdown", midOf(0)); pointer(body, "pointermove", midOf(2) + 5); pointer(body, "pointermove", midOf(3), 0); await idle();
    r.lost = { posts: posts().length, ids: shown().slice(0, 3), cls: body.classList.contains("rank-dragging") };
    // a second drag while the first is being saved doesn't start
    await reset(); NET.sent.length = 0; NET.delay["/api/setup/guess_words/order"] = 300;
    pointer(grip(a), "pointerdown", midOf(0)); pointer(body, "pointermove", midOf(2) + 5); pointer(body, "pointerup", midOf(2) + 5, 0); await sleep(30);
    pointer(grip(c), "pointerdown", midOf(2)); pointer(body, "pointermove", midOf(0) - 5); pointer(body, "pointerup", midOf(0) - 5, 0);
    await idle(); NET.delay = {};
    r.twice = { posts: posts().length, server: (await order()).slice(0, 4), shown: shown().slice(0, 3) };
    // the pure rule of where a drag puts a row: hidden rules keep their places while the order on show stays as it is
    const rows = JSON.stringify([1, 2, 3, 4].map(id => ({ id }))), boxes = JSON.stringify([{ id: 1, top: 0, height: 40 }, { id: 3, top: 40, height: 40 }, { id: 4, top: 80, height: 40 }]);
    r.pure = [[1, 10], [1, 65], [1, 500], [3, 50], [3, 5], [4, 5], [3, 500]].map(([id, y]) => run(`rankDragOrder(${rows}, ${id}, ${boxes}, ${y}).map(x => x.id).join()`));
    return { ...r, ids: { a, h, b, c, d } };
  });

  await tryit("refused", async () => {
    const r = {};
    const [a, , , c] = FX.ORDER;
    await reset();
    const other = FX.ORDER.slice(); other.splice(3, 1); other.unshift(c);
    await setOrder(other);   // another change comes first
    NET.sent.length = 0;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a)); await idle();
    r.stale = { posts: posts().length, toasts: toasts(), ids: shown().slice(0, 3), server: (await order()).slice(0, 4), read: NET.sent.filter(x => x[0] === "GET" && x[1] === "/api/setup/guess_words").length, off: grips().some(x => x.hasAttribute("aria-disabled")) };
    return { ...r, other: other.slice(0, 4) };
  });

  await tryit("unsure", async () => {
    const r = {};
    const [a] = FX.ORDER;
    const P = "/api/setup/guess_words/order";
    // the server saves it and the answer is lost: never said saved; the list read again shows what the records have
    await reset(); NET.fail[P] = "lost"; NET.sent.length = 0;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a)); await sleep(5); await idle(); NET.fail = {};
    r.lost = { toasts: toasts(), said: said(), ids: shown().slice(0, 3), server: (await order()).slice(0, 3), posts: posts().length, page: $("#main").innerHTML.includes("Applies to SQL imports"), off: grips().some(x => x.hasAttribute("aria-disabled")) };
    // it never reaches the server: not said saved, nor "nothing was changed"; the list shows the old order
    await reset(); NET.fail[P] = "net";
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a)); await idle(); NET.fail = {};
    r.never = { toasts: toasts(), ids: shown().slice(0, 3), server: (await order()).slice(0, 3) };
    // the app has stopped: the stopped page says it isn't known whether the change was saved, and nothing says "nothing was sent"
    await reset(); await click(grip(a)); await key(grip(a), "ArrowDown"); NET.down = true; await click(grip(a)); await idle();
    r.stopped = { page: $("#main").innerHTML, toasts: toasts() }; NET.down = false;
    return r;
  });

  await tryit("elsewhere", async () => {
    const r = {};
    const [a, , b] = FX.ORDER;
    const P = "/api/setup/guess_words/order";
    // answered after another section was opened: nothing of the old list is drawn over it, and a message says it was saved
    await reset(); NET.delay[P] = 300;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a));
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: "2026-11", sub: "doc_types", id: null, params: {} }, { fresh: true })`); await idle(); NET.delay = {};
    r.section = { kind: run(`state.setup.kind`), rank: $("#main").innerHTML.includes("rank-table"), types: $("#setupMain").innerHTML.includes('data-setup-new="doc_types"'), toasts: toasts(), server: (await order()).slice(0, 3) };
    // answered after another page was opened: the same
    await reset(); NET.delay[P] = 300;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a));
    await run(`navigate({ view: "overview", entity: "all", month: "2026-11", sub: null, id: null, params: {} }, { fresh: true })`); await idle(); NET.delay = {};
    r.page = { view: run(`state.view`), html: $("#main").innerHTML, toasts: toasts() };
    // the same, and the page now on show can't be read again: it says it was saved, never that nothing was changed
    await reset(); NET.delay[P] = 300;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a));
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: "2026-11", sub: "doc_types", id: null, params: {} }, { fresh: true })`); await sleep(60);
    NET.fail["/api/setup/doc_types"] = "net"; await idle(); NET.delay = {}; NET.fail = {};
    r.noRead = { page: $("#main").innerHTML, toasts: toasts(), posts: posts().length };
    // the same section asked for again while it is saved, and read before the save: it is read once more, and shows the saved order
    await reset(); NET.delay[P] = 300; NET.sent.length = 0;
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a));
    await run(`render()`); await sleep(40);
    r.mid = { off: grips().every(x => x.getAttribute("aria-disabled") === "true"), read: NET.sent.filter(x => x[0] === "GET" && x[1] === "/api/setup/guess_words").length };
    await idle(); NET.delay = {};
    r.again = { ids: shown().slice(0, 3), off: grips().some(x => x.hasAttribute("aria-disabled")), read: NET.sent.filter(x => x[0] === "GET" && x[1] === "/api/setup/guess_words").length };
    // refused after another section was opened: only a message, and the page on show isn't read again
    await reset(); NET.delay[P] = 300; const other = FX.ORDER.slice(0, -1); other.unshift(FX.ORDER[FX.ORDER.length - 1]);
    await setOrder(other);
    await click(grip(a)); await key(grip(a), "ArrowDown"); await click(grip(a));
    await run(`navigate({ view: "setup", entity: ${FX.EXA}, month: "2026-11", sub: "doc_types", id: null, params: {} }, { fresh: true })`); await sleep(40); NET.sent.length = 0;
    await idle(); NET.delay = {};
    r.refusedLeft = { toasts: toasts(), reads: NET.sent.filter(x => x[0] === "GET").length, types: $("#setupMain").innerHTML.includes('data-setup-new="doc_types"') };
    return r;
  });

  await setOrder(FX.ORDER);
  out.unheard = unheard;
  process.stdout.write("@@OUT " + JSON.stringify(out) + "\n");
  process.exit(0);
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""

fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps({"EXA": EXA, "EXB": EXB, "ORDER": PAGE_ORDER}), encoding="utf-8")
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
files = [str(f) for f in app_files() if not str(f).endswith("main.js")]
proc = subprocess.Popen([shutil.which("node"), str(probe), str(fx_path), *files], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
errors = []
reader = threading.Thread(target=lambda: errors.append(proc.stderr.read()), daemon=True)
reader.start()
watchdog = threading.Timer(300, proc.kill)
watchdog.start()
o = None
try:
    for line in proc.stdout:
        if line.startswith("@@REQ "):
            req = json.loads(line[6:])
            kw = {"headers": H}
            if req["body"] is not None:
                kw["json"] = req["body"]
            res = client.open(BASE + req["path"], method=req["method"], **kw)
            proc.stdin.write(json.dumps({"id": req["id"], "status": res.status_code, "body": res.get_json(silent=True) or {}}) + "\n")
            proc.stdin.flush()
        elif line.startswith("@@OUT "):
            o = json.loads(line[6:])
    proc.wait(timeout=30)
finally:
    watchdog.cancel()
    if proc.poll() is None:
        proc.kill()
reader.join(timeout=5)
check("the page script ran on the stand-in page, against the real server", o is not None, "".join(errors)[-1500:])


class Soft(dict):
    """A probe answer that may be missing: a key not there reads as an empty answer, so every check runs (and with HRP_KEEP_GOING is listed)."""
    def __missing__(self, k):
        return Soft()


def soften(v):
    if isinstance(v, dict):
        return Soft({k: soften(x) for k, x in v.items()})
    return [soften(x) for x in v] if isinstance(v, list) else v


o = soften(o)
for k in ("drawn", "others", "tryBox", "keys", "escape", "leaving", "search", "drag", "refused", "unsure", "elsewhere"):
    if o[k].get("error"):
        print(f"     {k}: {o[k]['error']}")

A, HID, B, C, D = PAGE_ORDER[:5]
VISIBLE = [i for i in PAGE_ORDER if i != HID]
N = len(PAGE_ORDER)
d = o["drawn"]
check("the payment type guesses are drawn in their order, all of them (no pages of 25, no sortable columns), each with a Move grip, the stopped one hidden",
      d["ids"] == VISIBLE and d["grips"] == len(VISIBLE) > 25 and d["sorters"] == 0 and d["more"] == 0, (d["ids"], d["grips"], d["sorters"], d["more"]))
check("the Order column shows each rule's place among all of them, stopped ones counted", d["places"] == [str(PAGE_ORDER.index(i) + 1) for i in VISIBLE], d["places"])
check("the columns are Move, then the list's own, with the name as the button that opens the rule",
      d["head"] == ["Move", "Order", "Name", "Payment type", "Words", "Used by", "Status"] and d["names"] == ["Zebra stationery", "Zebra rent"], (d["head"], d["names"]))
check("a grip is a button named with the rule and its place, not pressed, described by the helper line",
      d["tag"] == "BUTTON" and d["label"].endswith(f"position 4 of {N}") and d["label"].startswith("Move ") and d["pressed"] == "false" and d["by"] == "rank-help" and d["off"] is None, d)
check("the helper says the first match wins and how to move; a place for the screen reader is outside the rows",
      d["note"] is True and d["help"] == "To change the order, drag the move button, or press it, then Up or Down, and Space to drop." and d["live"] == ["status", "assertive", False], (d["help"], d["live"]))
check("Try a voucher description: an empty box (no sample text), described by its result, saying what to type and that money in is Money received",
      d["box"] is True and d["boxValue"] == "" and d["label2"] == "Try a voucher description" and "mt-result" in d["boxSaid"] and d["result"]["role"] == "status"
      and d["result"]["text"] == "Type a voucher description to see which rule matches it." and "always added as Money received" in d["note2"] and d["words"] == ["ZEBRAWORD", "ZW PENS"], d)
ot = o["others"]
check("filing words have grips and places and no Try box; salary words have neither and keep their sortable columns, as the other lists do",
      ot["filing"]["grips"] == ot["filing"]["rows"] > 0 and ot["filing"]["box"] is False and ot["filing"]["places"] == ["1", "2", "3"] and ot["salary"]["grips"] == 0 and ot["salary"]["box"] is False
      and ot["salary"]["sorters"] > 0 and ot["types"]["grips"] == 0 and ot["types"]["sorters"] > 0, ot)

t = o["tryBox"]
check("Try shows the server's answer: the rule by its place and name and the payment type it gives",
      t["match"]["text"] == f"Rule 1 (Zebra stationery) matches: the payment type is {LABEL['utility']}." and "ok" in t["match"]["cls"], t["match"])
check("the matching rule's row is marked, and in it the words found", t["matched"] == {"rows": [A], "words": ["ZEBRAWORD"]}, t["matched"])
check("the text goes to the server in the body of one request, never in an address",
      [(x[0], x[1], x[2]) for x in t["sent"]] == [("POST", "/api/setup/guess_words/try", {"text": "Paid zebraword for the hall"})] and t["addresses"] == [], t["sent"])
check("a stopped rule is skipped; a description no rule matches says it would be Other payment, with no row marked",
      t["stopped"]["text"] == f"No rule matches. The payment would be added as {LABEL['other']}, for you to set." and t["stoppedMarked"] == {"rows": [], "words": []} and t["none"]["text"] == t["stopped"]["text"] and "ok" not in t["none"]["cls"], t["stopped"])
check("an emptied box asks nothing and says what to type", t["empty"]["text"] == "Type a voucher description to see which rule matches it." and t["emptySent"] == 0, t["empty"])
check("keys typed quickly ask once, for the last text", t["debounced"] == ["zebra hall"] and "(Zebra rent)" in t["hall"]["text"], t["debounced"])
check("while a newer text is being tried the older answer is dimmed with no row marked, and an older answer that comes late never replaces the newer one",
      "stale" in t["stale"]["result"]["cls"] and t["stale"]["marked"] == {"rows": [], "words": []} and "(Filler rule 01)" in t["latest"]["text"] and "stale" not in t["latest"]["cls"]
      and t["latestMarked"]["words"] == ["FILLER01WORD"], (t["stale"], t["latest"]))
check("an older answer that comes after more was typed, before the newer text is asked, is not shown: the one on show stays, dimmed",
      "(Filler rule 01)" in t["between"]["text"] and "stale" in t["between"]["cls"] and "(Filler rule 02)" in t["betweenAfter"]["text"], (t["between"], t["betweenAfter"]))
check("a text tried again after the rules changed keeps the newer answer when the first one comes late", "(Zebra rent)" in t["changed"]["text"], t["changed"])
check("the list drawn again keeps what was typed and tries it again", t["redrawn"]["value"] == "filler01word" and "(Filler rule 01)" in t["redrawn"]["result"]["text"] and t["redrawn"]["marked"]["words"] == ["FILLER01WORD"], t["redrawn"])
check("an answer that never comes is said as not tried", t["broken"]["text"] == "The description couldn't be tried. The connection to HR Payments broke." and t["brokenToasts"] == [], t["broken"])
check("an answer that comes after another section was opened writes and says nothing", t["left"] == {"same": True, "box": False, "toasts": []}, t["left"])
check("what was typed is kept while Setup is on show, and dropped once another page is opened", t["back"] == "zebraword late" and t["gone"] == "", (t["back"], t["gone"]))

k = o["keys"]
check("Up and Down on a grip not picked up move nothing", k["unpicked"] == {"ids": [A, B, C], "posts": 0}, k["unpicked"])
check("pressing the grip picks the rule up, and says how to move it",
      k["picked"] == {"pressed": "true", "said": f"Picked up. Position 1 of {N}. Use Up and Down to move, Space to drop, Escape to cancel.", "held": True, "posts": 0}, k["picked"])
check("Up on the first rule says it is first already", k["first"] == "Already first.", k["first"])
check("a step past a stopped rule that is hidden says so; the rows and places follow, the focus stays on the grip, the page doesn't scroll, and nothing is sent yet",
      k["passed"] == {"said": f"Moved to position 2 of {N}, past a stopped rule that is hidden.", "ids": [A, B, C], "focus": f"rank-grip-{A}", "label": f"Move Zebra stationery, position 2 of {N}",
                      "pressed": "true", "prevented": True, "places": ["2", "3", "4"], "posts": 0}, k["passed"])
check("Down again moves it past the next one", k["moved"] == {"said": f"Moved to position 3 of {N}.", "ids": [B, A, C], "posts": 0}, k["moved"])
check("while a rule is picked up Try says the order isn't saved yet, and marks no row",
      k["heldTry"]["result"]["text"] == "The new order isn't saved yet. The description is tried again once it is." and k["heldTry"]["marked"] == {"rows": [], "words": []}, k["heldTry"])
check("a drop sends the whole new order once, with the order the list showed and the rule moved",
      k["saved"]["posts"] == [{"ids": [HID, B, A] + PAGE_ORDER[3:], "was": PAGE_ORDER, "moved": A}], k["saved"]["posts"])
check("until the server answers nothing says it was saved: Saving, every grip off",
      k["saving"]["said"] == "Saving the new order." and k["saving"]["off"] is True and k["saving"]["pressed"] == "false" and "isn't saved yet" in k["saving"]["result"]["text"], k["saving"])
check("while it is on its way no other move starts: a second drop, another grip, arrows and a drag send nothing and move nothing",
      k["blocked"] == {"posts": 1, "pressed": 0, "ids": [B, A, C]} and k["blockedSaid"] == "The last move is still being saved.", (k["blocked"], k["blockedSaid"]))
check("once saved: the records have the order, the screen reader is told where it dropped and that it applies from now on, the grip keeps the focus, and Try answers on the new order",
      k["saved"]["server"] == [HID, B, A, C] and k["saved"]["said"] == f"Dropped at position 3 of {N}. Applies to SQL imports from now on." and k["saved"]["focus"] == f"rank-grip-{A}" and k["saved"]["off"] is False
      and k["saved"]["flash"] is True and k["saved"]["places"] == ["2", "3", "4"] and "Rule 2 (Zebra rent)" in k["saved"]["result"]["text"] and k["saved"]["marked"]["rows"] == [B] and k["saved"]["toasts"] == [], k["saved"])
check("a rule dropped where it was sends nothing", k["nowhere"]["posts"] == 0 and k["nowhere"]["said"].endswith("where it was.") and k["nowhere"]["pressed"] == "false", k["nowhere"])
e = o["escape"]
check("Escape puts a picked-up rule back where it was, sends nothing and does nothing else; with nothing picked up it does what it did",
      e["ids"] == [A, B, C] and e["said"] == "Cancelled, back where it was." and e["pressed"] == "false" and e["posts"] == 0 and e["closed"] == 0 and e["prevented"] is True and e["focus"] == e["grip"] and e["later"] == 1, e)
lv = o["leaving"]
check("leaving the grip for another control drops it and keeps the focus there; a blur with nowhere to go doesn't",
      lv["noTarget"] == {"posts": 0, "pressed": "true"} and lv["blur"]["posts"] == 1 and lv["blur"]["server"] == [HID, A, B] and lv["blur"]["focus"] == lv["blur"]["was"] != "", lv)
check("Tab drops it, lets the focus move on, and doesn't draw the rows again under it",
      lv["tab"] == {"posts": 1, "server": [HID, A, B], "prevented": False} and lv["tabNoRedraw"] is True, (lv["tab"], lv["tabNoRedraw"]))
check("opening another page with a rule picked up saves nothing, and the list comes back as it was", lv["left"] == {"posts": 0, "on": False} and lv["back"] == {"ids": [A, B, C], "pressed": 0}, lv)
s = o["search"]
check("a search takes a picked-up rule back, turns the grips off and says why; the places stay each rule's own",
      s["cancelled"]["ids"] == [A, B] and s["cancelled"]["said"] == "Cancelled, back where it was." and s["cancelled"]["help"] == "Clear the search to change the order." and s["cancelled"]["off"] is True
      and s["cancelled"]["pressed"] == 0 and s["cancelled"]["posts"] == 0 and s["cancelled"]["places"] == ["1", "3"], s["cancelled"])
check("while searching, neither a press nor a drag moves anything", s["noPick"] == {"pressed": 0} and s["noDrag"] == {"posts": 0, "ids": [A, B]}, (s["noPick"], s["noDrag"]))
check("clearing the search turns the grips on again", s["cleared"]["off"] is False and s["cleared"]["help"].startswith("To change the order"), s["cleared"])
check("with Show stopped on, a step is one row; Down on the last says it is last already",
      s["all"] == {"ids": [HID, A, B], "said": f"Moved to position 2 of {N}."} and s["last"] == "Already last.", (s["all"], s["last"]))

g = o["drag"]
check("a press that barely moves is no drag: the click after it picks up", g["press"] == {"pressed": "true", "posts": 0}, g["press"])
check("dragging moves the rows with the pointer and sends nothing until it is let go",
      g["during1"] == {"ids": [B, A, C], "posts": 0, "cls": True} and g["during2"] == {"ids": [B, C, A], "posts": 0, "places": ["2", "3", "4"], "pressed": "true"}, (g["during1"], g["during2"]))
check("letting go saves the order shown, once; the click the release raises opens no rule and picks nothing up",
      g["dropped"]["posts"] == [{"ids": [HID, B, C, A] + PAGE_ORDER[4:], "was": PAGE_ORDER, "moved": A}] and g["dropped"]["server"] == [HID, B, C, A, D] and g["dropped"]["opened"] == []
      and g["dropped"]["cls"] is False and g["dropped"]["pressed"] == 0 and g["dropped"]["said"] == f"Dropped at position 4 of {N}. Applies to SQL imports from now on.", g["dropped"])
check("a later click on a row still opens its rule", len(g["rowClick"]) == 1 and g["rowClick"][0][0] == "guess_words", g["rowClick"])
check("a rule dragged up goes before the one it is above", g["up"] == [C, A, HID, B], g["up"])
check("dragged there and back, nothing is sent", g["backAgain"] == {"posts": 0, "ids": [A, B, C]}, g["backAgain"])
check("Escape during a drag puts it back and sends nothing, also when let go after", g["escaped"] == {"posts": 0, "ids": [A, B, C], "closed": 0, "cls": False}, g["escaped"])
check("a pointer taken away, or let go where the page couldn't hear it, puts it back and sends nothing",
      g["cancel"] == {"posts": 0, "ids": [A, B, C]} and g["lost"] == {"posts": 0, "ids": [A, B, C], "cls": False}, (g["cancel"], g["lost"]))
check("a second drag while the first is being saved doesn't start", g["twice"] == {"posts": 1, "server": [HID, B, C, A], "shown": [B, C, A]}, g["twice"])
check("where a drag goes: before the first other row whose middle is below the pointer, else after the last; hidden rules keep their places while the order on show stays as it is",
      g["pure"] == ["1,2,3,4", "2,3,1,4", "2,3,4,1", "1,2,3,4", "3,1,2,4", "4,1,2,3", "1,2,4,3"], g["pure"])

rf = o["refused"]
st = rf["stale"]
check("a refused move says it wasn't saved and that nothing was changed, and the list is read again with the order the records have",
      st["posts"] == 1 and st["toasts"] == [f"The new order wasn't saved. {masters.ORDER_CHANGED} Nothing was changed."] and st["ids"] == [rf["other"][0], A, B] and st["server"] == rf["other"] and st["read"] == 1 and st["off"] is False, st)
u = o["unsure"]
check("a move whose answer is lost says it isn't known whether it was saved (never saved, never nothing changed), and the list read again shows what the records have",
      u["lost"]["toasts"] == ["The new order: The connection to HR Payments broke. It isn't known whether it was saved: check before doing it again."] and u["lost"]["posts"] == 1
      and u["lost"]["server"] == [HID, A, B] and u["lost"]["ids"] == [A, B, C] and u["lost"]["page"] is False and u["lost"]["off"] is False, u["lost"])
check("...and one that never reached the server says the same, and shows the old order",
      u["never"]["toasts"] == u["lost"]["toasts"] and u["never"]["ids"] == [A, B, C] and u["never"]["server"] == [A, HID, B], u["never"])
check("with the app stopped, the stopped page says it isn't known whether the change was saved, not that nothing was sent",
      "isn't running" in u["stopped"]["page"].replace("&#39;", "'") and "known whether your last change was saved" in u["stopped"]["page"].replace("&#39;", "'")
      and "Nothing you typed since then" not in u["stopped"]["page"] and "Nothing was changed" not in " ".join(u["stopped"]["toasts"]), u["stopped"]["page"][:600])
el = o["elsewhere"]
check("answered after another section was opened: that section stays, nothing of the list is drawn over it, and a message says it was saved",
      el["section"] == {"kind": "doc_types", "rank": False, "types": True, "toasts": [f"The new order is saved. Dropped at position 2 of {N}. Applies to SQL imports from now on."], "server": [HID, A, B]}, el["section"])
check("...and so after another page was opened", el["page"]["view"] == "overview" and "Overview page" in el["page"]["html"] and "rank-table" not in el["page"]["html"]
      and len(el["page"]["toasts"]) == 1 and el["page"]["toasts"][0].startswith("The new order is saved."), el["page"])
nr = el["noRead"]
check("...and when the page now on show can't be read again after it, it says it was saved, never that nothing was changed",
      "It was saved, but this page could not reload. Try again." in nr["page"] and "Nothing was changed" not in nr["page"] + " ".join(nr["toasts"]) and nr["posts"] == 1, nr["page"][:500])
check("the same section drawn again while the order is being saved has its grips off, and is read once more after the save, so it shows what was saved",
      el["mid"] == {"off": True, "read": 1} and el["again"] == {"ids": [A, B, C], "off": False, "read": 2}, (el["mid"], el["again"]))
rl = el["refusedLeft"]
check("a refusal answered after another section was opened is only said: the page on show isn't read again", len(rl["toasts"]) == 1 and "Nothing was changed." in rl["toasts"][0] and rl["reads"] == 0 and rl["types"] is True, rl)
check("no failure went unheard", o["unheard"] == [], o["unheard"])

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
