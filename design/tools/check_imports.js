// Checks every <dc-import name="X" attr="value"> across the boards against X.dc.html's data-props:
// an enum attribute must use one of its options; an attribute X doesn't declare is reported.
// Values that hold a {{hole}} are skipped (computed at run time). Usage: node check_imports.js <project dir>
const fs = require('fs'), path = require('path');
const dir = process.argv[2];
const files = fs.readdirSync(dir).filter(f => f.endsWith('.dc.html'));
const props = {};
for (const f of files) {
  const t = fs.readFileSync(path.join(dir, f), 'utf8');
  const m = t.match(/data-props='([^']*)'/);
  if (m) { try { props[f.replace('.dc.html', '')] = JSON.parse(m[1]); } catch (e) { console.log('BAD data-props', f, e.message); } }
}
let bad = 0, seen = 0;
for (const f of files) {
  const t = fs.readFileSync(path.join(dir, f), 'utf8');
  for (const m of t.matchAll(/<dc-import\b([^>]*)>/g)) {
    const attrs = {}; for (const a of m[1].matchAll(/([\w-]+)="([^"]*)"/g)) attrs[a[1]] = a[2];
    const name = attrs.name; if (!name) continue; seen++;
    const p = props[name]; if (!p) { console.log(`${f}: imports ${name}, which has no board`); bad++; continue; }
    if (process.argv[3] === '--strict') {
      // After package B no board may rely on the old values that package A only kept as aliases.
      const OLD_ACTIVE = ['aisb', 'ai', 'ail', 'aip'], OLD_SECTION = ['Dashboard', 'Companies', 'Monthly work', 'Filing', 'Setup'];
      if (name === 'Sidebar' && OLD_ACTIVE.includes(attrs.active)) { console.log(`${f}: Sidebar active="${attrs.active}" is an old alias`); bad++; }
      if (name === 'Topbar' && OLD_SECTION.includes(attrs.section)) { console.log(`${f}: Topbar section="${attrs.section}" is an old alias`); bad++; }
      if ((name === 'Sidebar' || name === 'Topbar') && !('company' in attrs)) { console.log(`${f}: ${name} import has no company`); bad++; }
      if (name === 'Sidebar' && !('kind' in attrs)) { console.log(`${f}: Sidebar import has no kind`); bad++; }
    }
    for (const [k, v] of Object.entries(attrs)) {
      if (['name', 'class', 'style', 'id', 'hint-size', 'aria-hidden', 'role'].includes(k) || k.startsWith('hint-') || k.startsWith('aria-') || k.startsWith('data-')) continue;
      if (v.includes('{{')) continue;
      const d = p[k] || p[k.replace(/-(\w)/g, (_, c) => c.toUpperCase())];
      if (!d) { console.log(`${f}: ${name} has no prop "${k}" (value "${v}")`); bad++; continue; }
      if (d.editor === 'enum' && Array.isArray(d.options) && !d.options.includes(v)) { console.log(`${f}: ${name} ${k}="${v}" is not one of [${d.options.join(', ')}]`); bad++; }
    }
  }
}
console.log(`${seen} imports checked, ${bad} problems`);
