"""The page's start (static/js/main.js), on made-up records: the first reads of the page (the records' overview, the cycle's months, the place the
address names) can fail, and the page must then say so in its own place, with a Try again that starts again, instead of staying blank. The page
script is run in Node on a small stand-in for the page (no browser); the records overview that the page reads is the real server's own.

Checks: a records overview that can't be read (the server's 500, an answer that is not JSON, an answer with no companies in it, a network failure)
draws "HR Payments couldn't start" with the reason and a Try again, no "Nothing was changed" (nothing was being changed), and no loading dim left;
Try again starts again, reads the records again and the page starts (once); a Try again that fails again still says so; a start that fails after the
records were read (the cycle's months, the address's place) says the same; the address is listened to once, however often the app starts.

Run: .venv\\Scripts\\python -m synthetic_tests.start_test
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-start-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config, db  # noqa: E402
from hrp.app import app  # noqa: E402
from synthetic_tests.appsource import app_files  # noqa: E402
from synthetic_tests.flags import KEEP_GOING  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"
config.SETTINGS_FILE = tmp / "settings.json"  # never the program's own settings file

(tmp / "seed.json").write_text(json.dumps({"entities": [
    {"code": "EXA", "name": "Example Alpha Sdn Bhd", "accounts": [{"label": "Main", "bank": "Example Bank", "number": "000-111-4417"}]},
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
c = app.test_client()
META = c.get(f"http://127.0.0.1:{config.SETTINGS['port']}/api/meta", headers={"X-HRP": "1"}).get_json()
check("the records overview the page reads is the real server's: it lists the company", [e["code"] for e in META["entities"]] == ["EXA"])

PROBE = r"""
const fs = require("fs"), vm = require("vm");
const [fxPath, mainPath, ...files] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(fxPath, "utf8"));
const els = {}, listeners = {}, hashListeners = [];
const makeEl = id => { const set = new Set(); return ({ id, innerHTML: "", value: "", checked: false, hidden: false, textContent: "", className: "", dataset: {}, attrs: {},
  classList: { add: (...c) => c.forEach(x => set.add(x)), remove: (...c) => c.forEach(x => set.delete(x)), toggle() {}, contains: c => set.has(c) },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, removeAttribute(k) { delete this.attrs[k]; },
  focus() {}, querySelectorAll: () => [], querySelector: () => null, closest: () => null, contains: () => false, isConnected: true, addEventListener() {}, removeEventListener() {} }); };
const el = id => els[id] ||= makeEl(id);
const document = { activeElement: null, body: { classList: { add() {}, remove() {} } },
  querySelector: s => /^#[\w-]+$/.test(s) ? el(s.slice(1)) : null, querySelectorAll: () => [], getElementById: id => els[id] || null,
  addEventListener(t, f) { (listeners[t] ||= []).push(f); } };
// what each read of the records' overview does, in turn (the last one repeats): ok, a status, bad (not JSON), none (no companies), net (the app is not running)
let script = [], metaReads = 0;
async function fetch(path, init = {}) {
  if (path === "/api/meta") {
    metaReads++;
    const how = script.length > 1 ? script.shift() : script[0] || "ok";
    if (how === "net") throw new TypeError("Failed to fetch");
    if (how === "bad") return { ok: true, status: 200, json: async () => { throw new SyntaxError("not JSON"); } };
    if (how === "none") return { ok: true, status: 200, json: async () => ({}) };
    if (how === "500") return { ok: false, status: 500, json: async () => ({ error: "The server could not read the records." }) };
    return { ok: true, status: 200, json: async () => JSON.parse(JSON.stringify(FX.meta)) };
  }
  return { ok: true, status: 200, json: async () => ({}) };
}
const win = { matchMedia: () => ({ matches: true }), location: { hash: "", replace(v) { this.hash = v; } }, history: { state: null, replaceState() {} }, scrollX: 0, scrollY: 0, scrollTo() {},
  addEventListener(t, f) { if (t === "hashchange") hashListeners.push(f); }, print() {} };
const sandbox = { document, fetch, FormData: class {}, console, setTimeout, clearTimeout, URLSearchParams, CSS: { escape: s => s },
  localStorage: { getItem: () => null, setItem() {} }, window: win, navigator: {}, __el: el };
const ctx = vm.createContext(sandbox);
const run = code => vm.runInContext(code, ctx);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = {};
const tryit = async (name, fn) => { try { out[name] = await fn(); } catch (e) { out[name] = { error: String(e && e.stack || e).slice(0, 400) }; } };
(async () => {
  run(files.map(f => fs.readFileSync(f, "utf8")).join("\n"));   // every script of the page but main.js, which starts it
  run(`globalThis.__boots = 0; globalThis.__realRouterBoot = routerBoot; renderNav = () => {}; routerBoot = async () => { __boots++; $("#main").innerHTML = "<div>Overview</div>"; };`);
  run(fs.readFileSync(mainPath, "utf8"));                          // starts the page: it reads the records (script, below, says how that goes)
  const main = el("main");
  const click = async dataset => { const b = { dataset, tagName: "BUTTON", id: "", className: "", getAttribute: () => null }; b.closest = () => b;
    const ev = { type: "click", target: b, button: 0, preventDefault() {}, stopPropagation() {} }; for (const f of listeners.click || []) await f(ev); };
  const shown = () => ({ html: main.innerHTML, loading: main.classList.contains("loading"), boots: run(`__boots`), reads: metaReads });
  const restart = async how => { script = how; metaReads = 0; main.innerHTML = ""; main.classList.add("loading"); run(`__boots = 0`); await run(`start()`); await sleep(20); };
  await sleep(30);   // the first start, with the records read as the script says (ok, nothing set yet): the page started
  out.first = shown();

  // the first read fails, in each of the ways it can: the page says so, with a Try again; Try again starts again and the page starts, once
  for (const how of ["500", "bad", "none", "net"]) await tryit("fail-" + how, async () => {
    const r = {};
    await restart([how]);
    r.failed = shown();
    script = ["ok"]; metaReads = 0;
    await click({ retry: "start" }); await sleep(30);
    r.retried = shown();
    return r;
  });
  // a Try again that fails again says so again; the next works
  await tryit("twice", async () => {
    const r = {};
    await restart(["500"]);
    metaReads = 0; await click({ retry: "start" }); await sleep(30); r.again = shown();
    script = ["ok"]; metaReads = 0; await click({ retry: "start" }); await sleep(30); r.ok = shown();
    return r;
  });
  // the records are read, and what comes after fails: the cycle's months (they are asked for one by one; the page says so on its own), the address's place
  await tryit("later", async () => {
    const r = {};
    run(`globalThis.__openCycleMonths = openCycleMonths; openCycleMonths = async () => { throw new Error("months"); }`);
    await restart(["ok"]); r.months = shown();
    run(`openCycleMonths = __openCycleMonths`);
    run(`globalThis.__stubBoot = routerBoot; routerBoot = async () => { throw new Error("place"); }`);
    await restart(["ok"]); r.place = shown();
    run(`routerBoot = __stubBoot`);
    metaReads = 0; await click({ retry: "start" }); await sleep(30); r.retried = shown();
    return r;
  });
  // the error page is the one Try again draws with the old click handler too (a page that fails to draw): "start" is only for a failed start
  await tryit("plainRetry", async () => {
    run(`globalThis.__renders = 0; __boots = 0; globalThis.__realRender = render; render = async () => { __renders++; }`);
    await click({ retry: "1" });
    const r = { renders: run(`__renders`), boots: run(`__boots`) };
    run(`render = __realRender`);
    return r;
  });
  // the address is listened to once, however often the app starts (the real routerBoot, the place it names stubbed)
  await tryit("hashOnce", async () => {
    run(`globalThis.__applied = 0; applyPlace = async () => { __applied++; }; routerBoot = __realRouterBoot`);
    const route = run(`onHashChange`);
    for (let i = 0; i < 3; i++) await run(`routerBoot()`);
    return { listeners: hashListeners.filter(f => f === route).length, applied: run(`__applied`) };
  });
  process.stdout.write(JSON.stringify(out));
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
"""

fx_path = tmp / "fixtures.json"
fx_path.write_text(json.dumps({"meta": META}), encoding="utf-8")
probe = tmp / "probe.js"
probe.write_text(PROBE, encoding="utf-8")
files = [str(f) for f in app_files() if not str(f).endswith("main.js")]
main_js = [str(f) for f in app_files() if str(f).endswith("main.js")]
check("the page lists main.js, which starts it, last", len(main_js) == 1 and str(app_files()[-1]) == main_js[0], main_js)
res = subprocess.run([shutil.which("node"), str(probe), str(fx_path), main_js[0], *files], capture_output=True, text=True, encoding="utf-8", timeout=120)
o = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None
check("the page's script ran on the stand-in page, against the server's own records overview", o is not None, res.stderr[-1500:])


class Soft(dict):
    """A probe answer that may be missing: a key not there reads as an empty answer, so every check runs (and with HRP_KEEP_GOING is listed)."""
    def __missing__(self, k):
        return Soft()


def soften(v):
    if isinstance(v, dict):
        return Soft({k: soften(x) for k, x in v.items()})
    return [soften(x) for x in v] if isinstance(v, list) else v


o = soften(o)
STARTED = "<div>Overview</div>"
check("the first start, when the records can be read, starts the page: the overview is drawn, once, with no error", o["first"]["html"] == STARTED and o["first"]["boots"] == 1 and o["first"]["reads"] == 1, o["first"])


def says(s):
    """What the page shows when it could not start: the title, the reason, a Try again that starts again; nothing about changes, no dim left."""
    h = s["html"]
    return ("HR Payments couldn&#39;t start" in h and "The records couldn&#39;t be read just now." in h and 'data-retry="start"' in h and "Try again</button>" in h
            and "Nothing was changed" not in h and s["loading"] is False and s["boots"] == 0)


WAYS = {"500": "the server's 500", "bad": "an answer that is not JSON", "none": "an answer with no companies in it", "net": "a network failure (the app is not running)"}
for how, what in WAYS.items():
    f = o["fail-" + how]
    check(f"the first read of the records failing ({what}) draws \"HR Payments couldn't start\" with the reason and a Try again, and no loading dim is left", says(f["failed"]) and f["failed"]["reads"] == 1, f["failed"])
    check(f"...Try again ({what}) reads the records again and starts the page, once", f["retried"] == {"html": STARTED, "loading": False, "boots": 1, "reads": 1}, f["retried"])
check("a Try again that fails again says so again, and the next one that works starts the page",
      says(o["twice"]["again"]) and o["twice"]["again"]["reads"] == 1 and o["twice"]["ok"] == {"html": STARTED, "loading": False, "boots": 1, "reads": 1}, o["twice"])
check("a start that fails after the records were read (the cycle's months, the address's place) says the same, and Try again starts it", says(o["later"]["months"]) and says(o["later"]["place"])
      and o["later"]["retried"] == {"html": STARTED, "loading": False, "boots": 1, "reads": 1}, o["later"])
check("Try again on a page that failed to draw still only draws the page again (it doesn't start the app again)", o["plainRetry"] == {"renders": 1, "boots": 0}, o["plainRetry"])
check("the address is listened to once, however often the app starts", o["hashOnce"] == {"listeners": 1, "applied": 3}, o["hashOnce"])

if failed:
    print(f"\n{len(failed)} failed, {len(passed)} passed")
    sys.exit(1)
print(f"\n{len(passed)} checks passed")
