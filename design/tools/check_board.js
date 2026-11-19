// Checks one .dc.html board without rendering it: tags close and nest, sc-if/sc-for keep their hints, holes are
// plain lookups, every top-level hole and loop field resolves in renderVals() for each value of every enum tweak,
// handlers run without throwing, no global key listeners, no code before the class. Prints OK or the problems.
// Usage: node check_board.js <file.dc.html>
const fs = require('fs');
const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');
const problems = [];
const say = m => problems.push(m);
const warnings = [];
const warn = m => warnings.push(m);

const a = src.indexOf('<x-dc>'), b = src.indexOf('</x-dc>');
if (a < 0 || b < 0) { console.log('FAIL: no <x-dc>'); process.exit(1); }
const tpl = src.slice(a, b);
if (!src.includes('<script src="./support.js"></script>')) say('the support.js head line is missing or changed');

// 1. tags
const VOID = new Set(['input', 'link', 'meta', 'br', 'img', 'hr', 'path', 'circle', 'rect', 'ellipse', 'line', 'polyline', 'polygon']);
const stack = [];
const re = /<(\/?)([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
let m;
const lineOf = i => tpl.slice(0, i).split('\n').length;
while ((m = re.exec(tpl))) {
  const [, close, rawName, attrs] = m, name = rawName.toLowerCase();
  if (VOID.has(name) || attrs.trim().endsWith('/')) {
    if (name === 'dc-import') say(`line ${lineOf(m.index)}: dc-import must not self-close`);
    continue;
  }
  if (close) {
    const top = stack.pop();
    if (!top || top[0] !== name) { say(`line ${lineOf(m.index)}: </${name}> closes ${top ? '<' + top[0] + '> from line ' + top[1] : 'nothing'}`); if (top) stack.push(top); }
  } else {
    stack.push([name, lineOf(m.index)]);
    if ((name === 'sc-if' || name === 'sc-for') && !/hint-placeholder-(val|count)=/.test(attrs)) say(`line ${lineOf(m.index)}: <${name}> has no hint attribute`);
    const unq = attrs.match(/\s[\w:-]+=(?!["'])\S+/);
    if (unq) say(`line ${lineOf(m.index)}: unquoted attribute ${unq[0].trim()}`);
  }
}
if (stack.length !== 1 || stack[0][0] !== 'x-dc') say('left open: ' + stack.filter(s => s[0] !== 'x-dc').map(s => `<${s[0]}> line ${s[1]}`).join(', '));

// 2. holes
const holes = [...tpl.matchAll(/\{\{\s*([^}]*?)\s*\}\}/g)].map(x => x[1]);
for (const h of holes) if (!/^(\$index|true|false|-?\d+(\.\d+)?|'[^']*'|[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)*)$/.test(h)) say(`hole is not a plain lookup: {{${h}}}`);

// loops, in document order, each with the loops that enclose it (by index)
const loops = [];
const lre = /<sc-for\s[^>]*list="\{\{\s*([^}]+?)\s*\}\}"[^>]*as="(\w+)"[^>]*>|<\/sc-for>/g;
const open = [];
while ((m = lre.exec(tpl))) {
  if (m[0].startsWith('</')) { open.pop(); continue; }
  loops.push({ list: m[1], v: m[2], parents: open.slice(), end: m.index + m[0].length });
  open.push(loops.length - 1);
}
// the loops enclosing a position (indices, outermost first)
const scopeAt = i => { const st = []; let mm, n = -1; const r2 = /<sc-for\s[^>]*>|<\/sc-for>/g;
  while ((mm = r2.exec(tpl)) && mm.index + mm[0].length <= i) { if (mm[0].startsWith('</')) st.pop(); else { n++; st.push(n); } } return st; };
// the sc-if blocks enclosing a position: their value paths (outermost first)
const ifs = [];
{ const st = []; let mm; const r3 = /<sc-if\s[^>]*value="\{\{\s*([^}]+?)\s*\}\}"[^>]*>|<\/sc-if>/g;
  while ((mm = r3.exec(tpl))) { if (mm[0].startsWith('</')) { const o = st.pop(); if (o) o.close = mm.index; } else { const o = { path: mm[1], open: mm.index + mm[0].length }; ifs.push(o); st.push(o); } } }
const ifsAt = i => ifs.filter(o => o.open <= i && (o.close === undefined || i < o.close)).map(o => o.path);
const holeAt = [...tpl.matchAll(/\{\{\s*([^}]*?)\s*\}\}/g)].map(x => ({ h: x[1], at: x.index, scope: scopeAt(x.index), conds: ifsAt(x.index) }));
for (const { h, scope } of holeAt) {
  const vars = scope.map(i => loops[i].v), first = h.split('.')[0];
  if (vars.length && !vars.includes(first) && !/^(\$index|true|false|-?\d)/.test(h) && !h.startsWith("'")) say(`hole {{${h}}} inside a loop (${vars.join(' > ')}) reads a name outside it`);
}

// 3. script
const sa = src.indexOf('data-dc-script');
if (sa < 0) { say('no data-dc-script'); }
const js = sa < 0 ? '' : src.slice(src.indexOf('>', sa) + 1, src.indexOf('</script>', sa));
if (/addEventListener\(\s*['"]key|onkeydown\s*=|document\.onkey|window\.onkey/.test(js)) say('global key listener in the script');
if (js.trim() && !/^\s*class Component extends DCLogic/.test(js)) say('code before class Component extends DCLogic');
let props = {};
try {
  const dp = src.match(/data-props='([^']*)'/);
  if (dp) props = JSON.parse(dp[1].replace(/&amp;/g, '&').replace(/&#39;/g, "'"));
} catch (e) { say('data-props is not valid JSON: ' + e.message); }

// stubs for the browser
const el = () => ({ focus() {}, scrollIntoView() {}, isConnected: true, querySelectorAll: () => [], contains: () => true, getBoundingClientRect: () => ({}) });
global.document = { getElementById: () => el(), activeElement: el(), querySelector: () => el(), querySelectorAll: () => [] };
global.window = { matchMedia: () => ({ matches: false }), requestAnimationFrame: f => setTimeout(f, 0) };
global.requestAnimationFrame = global.window.requestAnimationFrame;
const timers = [];
const realSet = setTimeout;
global.setTimeout = (f, ms) => { timers.push(f); return timers.length; };
global.clearTimeout = () => {};
let Component;
try {
  Component = new Function('DCLogic', js + '\nreturn Component;')(class DCLogic {
    constructor(p) { this.props = p || {}; this.state = {}; }
    setState(x, cb) { const prev = { ...this.state }; Object.assign(this.state, typeof x === 'function' ? x(this.state, this.props) : x); if (this.componentDidUpdate) { try { this.componentDidUpdate(this.props, prev); } catch (e) { say('componentDidUpdate threw: ' + e.message); } } if (cb) cb(); }
    forceUpdate() {}
  });
} catch (e) { say('script does not compile: ' + e.message); }

// a path's values, where loop variables come from the enclosing loops' items
const resolve = (r, path, items, scope) => {
  const parts = path.split('.');
  const own = scope.slice().reverse().find(i => loops[i].v === parts[0]);
  let vals = own !== undefined ? items[own] : [r[parts[0]]];
  for (const p of parts.slice(1)) vals = vals.flatMap(v => (v == null ? [] : [v[p]]));
  return vals;
};
const check = (r, tag) => {
  const items = [];
  loops.forEach((L, i) => {
    const lists = resolve(r, L.list, items, L.parents).filter(x => x !== undefined && x !== null);
    const parentsEmpty = L.parents.length && L.parents.some(pi => !items[pi].length);
    if (!lists.length && !parentsEmpty) say(`[${tag}] sc-for list {{${L.list}}} is undefined`);
    if (lists.some(x => !Array.isArray(x))) say(`[${tag}] sc-for list {{${L.list}}} is not an array`);
    items[i] = lists.filter(Array.isArray).flat();
  });
  const missing = new Set();
  for (const { h, scope, conds } of holeAt) {
    if (/^(\$index|true|false|-?\d|')/.test(h)) continue;
    if (conds.some(c => !c.includes('.') && c in r && !r[c])) continue;  // inside an sc-if that is off in this state
    const parts = h.split('.'), own = scope.slice().reverse().find(i => loops[i].v === parts[0]);
    if (own !== undefined) {
      const its = items[own];
      if (!its.length || !parts[1]) continue;
      if (!its.some(it => it && typeof it === 'object' && parts[1] in it)) missing.add(h);
    } else if (!(parts[0] in r)) missing.add(h);
    else if (parts.length > 1 && r[parts[0]] !== null && resolve(r, h, items, []).every(v => v === undefined)) missing.add(h);  // null: shown only when set
  }
  for (const h of missing) say(`[${tag}] {{${h}}} is not returned`);
  return items;
};

const variants = [{}];
for (const [k, v] of Object.entries(props)) if (v && v.editor === 'enum' && Array.isArray(v.options)) {
  const base = variants.slice();
  for (const o of v.options) for (const b of base) variants.push({ ...b, [k]: o });
  if (variants.length > 40) break;
}
const ev = { target: { value: '', checked: true, files: [] }, currentTarget: el(), key: 'Escape', shiftKey: false, preventDefault() {}, stopPropagation() {} };
if (Component) for (const extra of variants.slice(0, 40)) {
  const p = {};
  for (const [k, v] of Object.entries(props)) if (v && 'default' in v) p[k] = v.default;
  Object.assign(p, extra);
  const tag = Object.keys(extra).length ? JSON.stringify(extra) : 'defaults';
  let c, r;
  try { c = new Component(p); if (!c.state) c.state = {}; r = c.renderVals(); } catch (e) { say(`[${tag}] renderVals threw: ${e.message}`); continue; }
  const items = check(r, tag);
  // run every handler once (top level and on loop items), each on a fresh component
  const fns = Object.entries(r).filter(([, v]) => typeof v === 'function').map(([k]) => ({ k }));
  items.forEach((its, li) => { for (const it of its.slice(0, 3)) if (it && typeof it === 'object') for (const [k, f] of Object.entries(it)) if (typeof f === 'function') fns.push({ k: loops[li].v + '.' + k, li, name: k }); });
  const seen = new Set();
  for (const f of fns) {
    if (seen.has(f.k + (f.li ?? ''))) continue; seen.add(f.k + (f.li ?? ''));
    for (const key of ['Escape', 'ArrowDown', 'Tab', 'Enter']) {
      try {
        const c2 = new Component(p); if (!c2.state) c2.state = {};
        const r2 = c2.renderVals();
        let fn;
        if (f.li !== undefined) { const it2 = check(r2, tag + ' (rerun)'); const it = (it2[f.li] || []).find(o => o && typeof o[f.name] === 'function'); fn = it && it[f.name]; }
        else fn = r2[f.k];
        if (fn) fn({ ...ev, key });
        c2.renderVals();
        while (timers.length) { const t = timers.shift(); try { t(); } catch (e) { warn(`[${tag}] a timer from ${f.k} threw: ${e.message}`); } }
        c2.renderVals();
      } catch (e) { warn(`[${tag}] ${f.k}(${key}) threw when called out of context: ${e.message}`); }
      if (!/key|Key/.test(f.k)) break;
    }
  }
}
const uniq = [...new Set(problems)], wu = [...new Set(warnings)];
if (wu.length) console.log(['WARN (handlers called with no context; fix only if the control can be used in that state)', ...wu.slice(0, 12)].join(String.fromCharCode(10)));
console.log(uniq.length ? 'FAIL\n' + uniq.slice(0, 60).join('\n') + (uniq.length > 60 ? `\n… ${uniq.length - 60} more` : '') : 'OK');
process.exit(uniq.length ? 1 : 0);
