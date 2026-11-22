"use strict";
/* ---------------- Setup ---------------- */
// Companies, bank accounts, charts, customers and suppliers, payment and document types, the monthly work, the matching words and the
// general settings, kept in the records and changed here (design/canvas/Setup*.dc.html). The sections, their fields and list columns
// come from the server (/api/setup/types). Every list has one toolbar (search, Show stopped, Show deleted) and one record dialog:
// the fields in groups, Where used, Stop using / Use again / Delete (each asks why) and its History; Show deleted lists what was
// deleted with Put it back. A stopped record stays, for its history.
const setupSpec = () => state.setup.types?.kinds?.[state.setup.kind] || null;
const sectionLabel = spec => spec.single || !spec.plural ? spec.label : spec.plural.charAt(0).toUpperCase() + spec.plural.slice(1);
const NUM_TYPES = ["number", "money", "day"];
// A section's one record as it reads in a sentence: bank account, customer or supplier, but GL account as it is.
const setupNoun = s => /^[A-Z][a-z]/.test(s) ? lowerFirst(s) : s;

// The Setup menu (design/canvas/SetupNav.dc.html): the server's groups (hrp/masters.py GROUPS), each with its sections. A group for
// companies Kept in SQL Account only (Matching words, T.sql_only) is left out for a company Kept here. A section the server does not
// have is left out too, so the HR group the server adds with slice 11 shows with no change here.
const SETUP_SQL_KINDS = ["guess_words", "hint_words", "filing_words"];  // used before the page has read the server's groups
// A section that lives on another page: its menu item is a link there (the server says so with link_note).
const SETUP_LINKS = { payees: "payments/recurring" };
function setupGroups(T = state.setup.types, e = ent()) {
  const here = !!e && !e.uses_sql, sqlOnly = T?.sql_only || [];
  return (T?.groups || []).filter(([label]) => !(here && sqlOnly.includes(label)))
    .map(([label, kinds]) => ({ label, kinds: kinds.filter(k => T.kinds[k]) })).filter(g => g.kinds.length);
}
const setupGroupOf = (kind, T = state.setup.types) => (T?.groups || []).find(([, ks]) => ks.includes(kind))?.[0] || "";
// A section for companies Kept in SQL Account only.
function setupNeedsSql(kind, T = state.setup.types) {
  const g = setupGroupOf(kind, T);
  return g ? (T.sql_only || []).includes(g) : SETUP_SQL_KINDS.includes(kind);
}
const setupLinkHref = kind => { const item = MENU_BY_PAGE[SETUP_LINKS[kind]]; return item ? menuHref(item) : "#/"; };

// The menu: groups with their headings, each section a button (a link when it lives on another page, with its note and the
// external mark). The one on show is aria-current.
function setupNavHtml(T, active, groups = setupGroups(T)) {
  const item = k => {
    const spec = T.kinds[k], label = sectionLabel(spec), glyph = icon(spec.glyph || "sliders");
    if (spec.link_note && SETUP_LINKS[k]) return `<a class="sn" href="${esc(setupLinkHref(k))}" data-setup-link="${esc(k)}" aria-describedby="sn-note-${esc(k)}">${glyph}<span class="sn-words"><span>${esc(label)}</span><span class="sn-note" id="sn-note-${esc(k)}">${esc(spec.link_note)}</span></span>${icon("external")}</a>`;
    return `<button type="button" class="sn${k === active ? " on" : ""}" data-setup-kind="${esc(k)}"${k === active ? ` aria-current="page"` : ""}>${glyph}<span class="sn-words"><span>${esc(label)}</span></span></button>`;
  };
  return `<nav class="setup-nav card noprint" aria-label="Setup sections">${groups.map((g, i) => `<div class="sn-group" role="group" aria-labelledby="sn-g-${i}"><span class="setup-group" id="sn-g-${i}">${esc(g.label)}</span>${g.kinds.map(item).join("")}</div>`).join("")}</nav>`;
}

// The head of a Setup page: the group, the section, its sentence, and its buttons (design/canvas/Setup.dc.html).
function setupHead(kind, spec, { title, intro, actions = "" } = {}) {
  const words = intro === undefined ? spec?.intro : intro;
  return `<div class="pg-head st-head"><div class="pg-words"><span class="eyebrow">${esc(setupGroupOf(kind))}</span><h1 id="pg-h1" tabindex="-1">${esc(title ?? sectionLabel(spec))}</h1>${words ? `<p class="note">${esc(words)}</p>` : ""}</div>${actions ? `<div class="row pg-actions">${actions}</div>` : ""}</div>`;
}

// A section for companies Kept in SQL Account only, reached by an old link or bookmark for a company Kept here: the page says it is
// not used (the menu has left it out). Switching company on it goes to the Overview with a toast instead (core/topbar.js).
function setupNotUsed(kind, e) {
  const T = state.setup.types, group = setupGroupOf(kind, T) || sectionLabel(T.kinds[kind]), other = (state.meta.entities || []).find(x => isActive(x) && x.uses_sql);
  return `${setupHead(kind, null, { title: group, intro: "Words that match SQL Account vouchers and documents. Used only for companies Kept in SQL Account." })}
    ${emptyState({ glyph: "database", tone: "mute", title: `${group} aren't used for ${e.code}`,
      body: `${e.name} is Kept here, so there are no SQL vouchers or documents to match. Switch to a company that is Kept in SQL Account to change its ${group.toLowerCase()}.`,
      action: other ? { label: `Go to ${other.code}`, attr: "data-pick-entity", value: other.id, ghost: true } : null })}
    <div class="note">This page is left out of ${esc(e.code)}'s Setup menu. An old link or bookmark opened it.</div>`;
}

// Opens one Setup record in its dialog by its address (#/admin/setup/<section>/<id>); "Open Setup" in a print note names the company it is about.
function goSetupRecord(kind, id) {
  if (id == null) return go("setup");
  return navigate({ view: "setup", entity: state.entity, month: state.month, sub: kind, id: String(id), params: {} }, { fresh: true });
}

async function viewSetup(main) {
  const S = state.setup;
  if (!S.types) S.types = await api("/api/setup/types");
  const T = S.types, e = ent(), groups = setupGroups(T, e);
  if (!T.kinds[S.kind] || SETUP_LINKS[S.kind]) S.kind = groups[0]?.kinds[0] || null;  // a link's old address (Recurring payments) has no page here
  if (S.kind !== "move" && S.move) S.move.justImported = false;
  const at = setupMoreAt(setupSpec());  // the rows Show 25 more showed stay shown only while the same list is drawn again
  if (S.moreAt !== at) { S.more = {}; S.moreAt = at; }
  renderNav();  // the breadcrumb names the section
  // The same section of the same company drawn again (a save, a stop, a delete, a put back) keeps what it showed in place until the new one is
  // read, so the page keeps its height and the window its place; another section or company starts empty, at the top, as it always did.
  const same = !!main.querySelector(".setup-nav") && S.drawnAt === at, keep = same ? $("#setupMain")?.innerHTML || "" : "";
  const sx = window.scrollX, sy = window.scrollY;
  const top = main.querySelector(".setup-nav")?.scrollTop || 0;  // the menu is drawn again with the page: it keeps where it was scrolled to
  main.innerHTML = `<div class="setup-grid">${setupNavHtml(T, S.kind, groups)}<div class="setup-main" id="setupMain">${keep}</div></div>`;
  const shown = main.querySelector(".setup-nav");
  if (shown) shown.scrollTop = top;  // at once, not when the section has been read
  const box = $("#setupMain"), spec = setupSpec();
  if (!spec) box.innerHTML = emptyState({ glyph: "sliders", title: "Nothing to set up yet." });
  else if (e && !e.uses_sql && setupNeedsSql(S.kind, T)) box.innerHTML = setupNotUsed(S.kind, e);
  else if (spec.single) await setupSettings(box);
  else if (S.kind === "required") await setupRequired(box);
  else if (S.kind === "checklist") await setupChecklist(box);
  else if (S.kind === "reminders") await setupReminders(box);
  else if (S.kind === "move") await setupMove(box);
  else if (spec.bespoke) box.innerHTML = `<div class="card"><h1>${esc(sectionLabel(spec))}</h1><div class="note">This section isn't ready in this version of the app.</div></div>`;
  else await setupList(box, S.kind);
  setupMenuScroll(main);  // last, once the section has its height
  if (same && (window.scrollX !== sx || window.scrollY !== sy)) window.scrollTo(sx, sy);  // the window where it was, if anything moved it
  S.drawnAt = at;
}

// The menu is a new element each time the page is drawn (it has its scroll back already): it scrolls itself (never the window, as
// scrollIntoView would) just far enough for the item on show to be in its frame, as when a deep address opens a lower section.
function setupMenuScroll(main) {
  const bar = main.querySelector(".setup-nav"), it = bar?.querySelector(".sn.on");
  if (!bar || !it) return;
  const at = it.getBoundingClientRect(), frame = bar.getBoundingClientRect();
  const a = at.top - frame.top - bar.clientTop + bar.scrollTop, b = a + at.height;  // the item's place in the menu's own content
  if (a < bar.scrollTop) bar.scrollTop = a;
  else if (b > bar.scrollTop + bar.clientHeight) bar.scrollTop = b - bar.clientHeight;
}

// The rows Show 25 more has shown (state.setup.more, per list) stay shown while the same list is drawn again (a save, a stop). They start
// again with another section or company (viewSetup, a section that is no list too), when the search changes, and on leaving Setup.
const setupMoreAt = spec => `${state.setup.kind}:${spec?.per_entity ? state.entity : ""}`;
const setupMoreReset = id => { (state.setup.more ||= {})[id] = SETUP_PAGE; };
// Another page is opened (core/router.js applyPlace): what Setup keeps only while it is on show is dropped.
function setupLeft() {
  const S = state.setup;
  S.more = {}; S.moreAt = null; S.drawnAt = null;
  if (S.move) S.move.justImported = false;
}

// A field's choices as [value, label] pairs: payment types in use only, unless all (to name a value already saved). The
// payment type a voucher's words give is a money-out one; checklist items are every company's, by code.
function fieldOptions(f, all) {
  if (f.options_from === "categories") {
    const dir = f.direction || (state.setup.kind === "guess_words" ? "out" : null);
    return Object.entries(state.meta.categories).filter(([k]) => all || catActive(k) && (!dir || catDir(k) === dir));
  }
  if (f.options_from === "checklist_codes") return Object.entries(state.meta.checklist_codes || {});
  // The company's own bank accounts (the company open in the drawer), by id: in use only, unless all.
  if (f.options_from === "entity_accounts") {
    const co = state.meta.entities.find(x => x.id === +state.setup.id);
    return (co?.accounts || []).filter(a => all || isActive(a)).map(a => [a.id, `${a.label}${a.bank ? ` · ${a.bank}` : ""}${a.number ? ` · ${a.number}` : ""}`]);
  }
  // Customers and suppliers, by id: in use only, unless all. In a per-company list, that company's and every company's.
  if (f.options_from === "parties") {
    const perEntity = !!state.setup.types?.kinds?.[state.setup.kind]?.per_entity;
    return (state.meta.parties || []).filter(pt => all || isActive(pt) && (!perEntity || pt.entity_id == null || pt.entity_id === state.entity))
      .map(pt => [pt.id, `${pt.name}${pt.sql_code ? ` · ${pt.sql_code}` : ""}${pt.entity_id == null ? "" : ` (${state.meta.entities.find(x => x.id === pt.entity_id)?.code ?? "?"})`}`]);
  }
  return f.options || [];
}
// The companies a "company" field offers, by code: those in use, and the one chosen even if stopped since.
const companyChoices = sel => state.meta.entities.filter(x => isActive(x) || String(x.id) === sel);
// A list kept as a list or as JSON text (documents, words): always a list.
function asList(v) {
  if (Array.isArray(v)) return v;
  if (typeof v !== "string" || !v.trim()) return [];
  try { const j = JSON.parse(v); if (Array.isArray(j)) return j; } catch { /* plain text: a comma list */ }
  return splitWords(v);
}
// Words typed with commas between them, as a list.
const splitWords = s => String(s ?? "").split(",").map(x => x.trim()).filter(Boolean);
// An option's value as the input holds it: none (null) is the empty choice.
const optVal = k => k == null ? "" : String(k);
// A value as it reads in a list: month names, Yes or No, an option's label.
function fieldText(f, v) {
  // A company field's empty value is a choice of its own: every company.
  if (f?.type === "company") return v == null || v === "" ? "Every company" : String(state.meta.entities.find(x => x.id === +v)?.code ?? v);
  if (v == null || v === "") return "";
  if (!f) return String(v);
  if (f.options_from === "parties") return String(partyById(v)?.name ?? v);
  if (f.type === "words") return asList(v).join(", ");
  if (f.type === "month") return /^\d{4}-\d{2}$/.test(v) ? monthName(v) : String(v);
  if (f.type === "date") return fmtDate(v);
  if (f.type === "bool") return +v ? "Yes" : "No";
  if (f.type === "money") return Number(v).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (f.type === "select") return String(fieldOptions(f, true).find(o => optVal(o[0]) === String(v))?.[1] ?? v);
  return String(v);
}

// A record the app's own rules rely on (a payment or document type it came with): it can't be deleted.
const systemPill = r => +r?.system ? ` <span class="pill" title="The app relies on it, so it can't be deleted">Used by the app</span>` : "";

// A list's view (Flat or Tree, for a kind that has a tree), kept in this browser.
function setupView(kind, spec) {
  if (!spec.tree) return "flat";
  if (!state.setup.view[kind]) { let v = null; try { v = localStorage.getItem("hrp-setup-view-" + kind); } catch {} state.setup.view[kind] = v === "tree" ? "tree" : "flat"; }
  return state.setup.view[kind];
}
const TREE_TYPES = [["asset", "Assets"], ["liability", "Liabilities"], ["equity", "Equity"], ["income", "Income"], ["expense", "Expenses"]];

// The chart of accounts as a tree: SQL's groups in the order it prints them, each with the accounts under no other
// account, each account with the ones under it (by code). An account without an SQL group goes under its type. A
// heading or an account with others under it opens and closes (closed: the keys closed, "g:CA" or "a:310-000"). A
// search shows the accounts it finds with the ones they sit under, all open. Returns [rows html, accounts in it].
function setupTree(spec, shown, hit, closed, ncol, rowHtml) {
  const up = v => String(v || "").toUpperCase();
  const byCode = new Map(shown.map(r => [up(r.code), r]));
  const parentOf = r => { const p = up(r.parent_code); return p && p !== up(r.code) && byCode.has(p) ? p : null; };
  const keep = new Set();
  for (const r of shown) {
    if (hit && !hit.has(r.id)) continue;
    for (let x = r, seen = new Set(); x && !seen.has(x.id); x = byCode.get(parentOf(x))) { seen.add(x.id); keep.add(x.id); }
  }
  const kids = new Map();
  const roots = [];
  for (const r of shown.filter(r => keep.has(r.id)).sort((a, b) => String(a.code).localeCompare(String(b.code), undefined, { numeric: true }))) {
    const p = parentOf(r);
    // an account whose parent chain loops back is shown at the top of its group
    let loops = false;
    for (let x = p, seen = new Set([up(r.code)]); x; x = parentOf(byCode.get(x))) { if (seen.has(x)) { loops = true; break; } seen.add(x); }
    if (p && !loops) { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(r); } else roots.push(r);
  }
  const groups = (spec.tree.groups || []).map(([code, name]) => ({ key: code, label: `${name} · ${code}` }))
    .concat(TREE_TYPES.map(([t, label]) => ({ key: "~" + t, label: `${label} · no SQL group` })), [{ key: "~", label: "No type or SQL group" }]);
  const groupOf = r => r.sql_type || "~" + (r.type || "");
  const size = r => 1 + (kids.get(up(r.code)) || []).reduce((n, k) => n + size(k), 0);
  // While searching everything found is shown open, and the arrows are only marks: opening or closing then would
  // change what shows after the search with nothing to see now.
  const searching = !!hit;
  let html = "";
  const walk = (list, depth, parent) => {
    for (const r of list) {
      const ch = kids.get(up(r.code)) || [], key = "a:" + up(r.code), open = searching || !closed.has(key);
      const tg = !ch.length ? `<span class="tree-tg" aria-hidden="true"></span>`
        : searching ? `<span class="tree-tg" aria-hidden="true">▾</span>`
        : `<button type="button" class="tree-tg" data-tree="${esc(key)}" aria-expanded="${open}" title="${open ? "Close" : "Open"} the ${ch.length} account${ch.length === 1 ? "" : "s"} under it"><span aria-hidden="true">${open ? "▾" : "▸"}</span><span class="sr-only">${open ? "Close" : "Open"} ${esc(r.code)}</span></button>`;
      const said = (parent ? `, under ${parent.code}` : "") + (hit && !hit.has(r.id) ? ", shown for an account found under it" : "");
      html += rowHtml(r, `<span class="tree-cell" style="--depth:${depth}">${tg}<button class="link" data-setup-open="${r.id}">${esc(r.code || "(no code)")}</button>${said ? `<span class="sr-only">${esc(said)}</span>` : ""}${ch.length && !open ? ` <span class="muted">+${size(r) - 1}</span>` : ""}</span>`);
      if (ch.length && open) walk(ch, depth + 1, r);
    }
  };
  for (const g of groups) {
    const list = roots.filter(r => groupOf(r) === g.key);
    if (!list.length) continue;
    const key = "g:" + g.key, open = searching || !closed.has(key), count = list.reduce((s, r) => s + size(r), 0);
    const head = searching ? `<span class="tree-head"><span aria-hidden="true">▾</span> ${esc(g.label)}</span>`
      : `<button type="button" class="tree-head" data-tree="${esc(key)}" aria-expanded="${open}"><span aria-hidden="true">${open ? "▾" : "▸"}</span> ${esc(g.label)}</button>`;
    html += `<tr class="tree-group"><th colspan="${ncol}" scope="rowgroup">${head} <span class="muted">${count} account${count === 1 ? "" : "s"}</span></th></tr>`;
    if (open) walk(list, 0, null);
  }
  return [html, keep.size];  // every account in the tree, open or closed
}

// Which tree a list is: a kind kept per company (the chart of accounts) has one for each company.
const treeId = (kind, spec) => spec?.per_entity ? `${kind}:${state.entity}` : kind;

// The keys a tree can close: every group heading and every account with others under it.
function treeKeys(rows) {
  const up = v => String(v || "").toUpperCase(), codes = new Set(rows.map(r => up(r.code)));
  const out = new Set(rows.map(r => "g:" + (r.sql_type || "~" + (r.type || ""))));
  for (const r of rows) if (r.parent_code && codes.has(up(r.parent_code))) out.add("a:" + up(r.parent_code));
  return out;
}

// The line under a record's name in a list (design/canvas/Setup*.dc.html): an account's last four digits, a company's switcher name,
// a type's plural, a customer's short name.
const SETUP_SUB = {
  accounts: r => { const last = String(r.number || "").replace(/\s/g, "").slice(-4); return last ? `···· ${last}` : "No account number yet"; },
  entities: r => r.short_name ? `Switcher: ${r.short_name}` : "",
  payment_types: r => r.plural ? `Several: ${r.plural}` : "",
  doc_types: r => r.plural ? `Several: ${r.plural}` : "",
  parties: r => r.short_name || "",
};
// A cell of a list as the board words it: a company's Books (Kept in SQL Account or Kept here), no first month as No limit, the way a
// payment type's money goes, its legal deadline, and Yes or nothing for a tick.
function setupCell(kind, f, r, key) {
  const v = r[key];
  if (key === "uses_sql") return +v ? "Kept in SQL Account" : "Kept here";
  if (key === "first_month") return v ? fieldText(f, v) : "No limit";
  if (key === "direction") return v === "in" ? "Money in" : "Money out";
  if (key === "legal_due_day") return v && r.legal_due_offset != null && r.legal_due_offset !== "" ? `Day ${v}, ${+r.legal_due_offset ? "the month after" : "the payroll month"}` : "";
  if (f?.type === "bool") return +v ? "Yes" : "";
  return fieldText(f, v);
}
const SETUP_TWINS = [["payment_types", "doc_types"], ["gl_accounts", "parties"]];  // two sections that share a tab strip, as the boards draw them
const SETUP_PAGE = 25;  // rows shown at a time

// The tab strip of a section that has a twin (Payment types and Document types; the chart of accounts and Customers and suppliers),
// with how many records each holds.
async function setupTabs(kind, per) {
  const pair = SETUP_TWINS.find(p => p.includes(kind));
  if (!pair) return "";
  const T = state.setup.types, counts = await Promise.all(pair.map(async k => {
    if (k === kind) return null;
    try { return (await api(`/api/setup/${k}${T.kinds[k].per_entity ? `?entity=${state.entity}` : ""}`)).rows.length; } catch { return null; }
  }));
  return { pair, counts };
}
const setupTabsHtml = (kind, tabs, own) => !tabs ? "" : `<div role="tablist" class="segtabs st-tabs noprint" aria-label="${esc(tabs.pair.map(k => sectionLabel(state.setup.types.kinds[k])).join(" and "))}">${tabs.pair.map((k, i) => {
  const spec = state.setup.types.kinds[k], n = k === kind ? own : tabs.counts[i];
  return `<button type="button" role="tab" class="segtab" data-setup-kind="${esc(k)}" aria-selected="${k === kind}" tabindex="${k === kind ? 0 : -1}">${icon(spec.glyph)}${esc(sectionLabel(spec))}${n == null ? "" : ` <span class="tab-n">${n}</span>`}</button>`;
}).join("")}</div>`;

// The list of one section (companies, one company's bank accounts, types, words): the head, the toolbar, the table, and under it the
// records deleted when Show deleted is ticked.
async function setupList(box, kind) {
  const S = state.setup, spec = S.types.kinds[kind], id = "setup-" + kind, e = ent();
  const cols = spec.columns || [], fieldOf = k => (spec.fields || []).find(f => f.key === k);
  const isNum = c => NUM_TYPES.includes(fieldOf(c.key)?.type) && c.key !== "legal_due_day";  // a deadline reads as words
  const noun = setupNoun(spec.label), plural = spec.plural;
  const add = `<button type="button" class="btn" data-setup-new="${esc(kind)}" aria-haspopup="dialog">${icon("plus")}Add ${esc(noun)}</button>`;
  const paste = spec.paste ? `<button type="button" class="ghost" data-setup-paste="${esc(kind)}" aria-haspopup="dialog">${icon("clipboard")}Paste a list</button>` : "";
  // Registered before the list's first listState, so a sort chosen earlier is kept.
  SORTS[id] ||= Object.fromEntries([...cols.map(c => [c.key, [isNum(c) ? "num" : "text", r => setupCell(kind, fieldOf(c.key), r, c.key)]]),
    ["used", ["num", r => r.used_total]], ["status", ["text", r => r.status]]]);
  if (spec.per_entity && !e) {
    box.innerHTML = `${setupHead(kind, spec, { actions: `${paste.replace("<button", "<button disabled")}${add.replace("<button", "<button disabled")}` })}
      ${emptyState({ glyph: "company", title: "Add a company first.", body: `${sectionLabel(spec)} belong to a company. Once one is added, they are set up here.`,
        action: { label: "Go to Companies", attr: "data-setup-kind", value: "entities", glyph: "company" } })}`;
    return;
  }
  const [{ rows }, tabs] = await Promise.all([api(`/api/setup/${kind}${spec.per_entity ? `?entity=${state.entity}` : ""}`), setupTabs(kind, spec.per_entity)]);
  (S.more ||= {})[id] ??= SETUP_PAGE;  // the rows shown stay shown across a redraw (a save, a stop)
  const stopped = r => r.status === "stopped", nStopped = rows.filter(stopped).length;
  const text = r => [...cols.map(c => setupCell(kind, fieldOf(c.key), r, c.key)), SETUP_SUB[kind]?.(r) || "", usedText(r.used_by), stopped(r) ? "stopped" : "in use", +r.system ? "used by the app" : ""].join(" ");
  const sub = SETUP_SUB[kind] || (() => "");
  const cell = (r, c, i) => {
    const v = setupCell(kind, fieldOf(c.key), r, c.key);
    if (!i) return `<td><button type="button" class="link st-name" data-setup-open="${r.id}" aria-haspopup="dialog">${esc(v || "(no name)")}</button>${sub(r) ? `<div class="note st-sub">${esc(sub(r))}</div>` : ""}</td>`;
    return `<td${isNum(c) ? ` class="num"` : ""}>${v ? esc(v) : "—"}</td>`;
  };
  const usedCell = r => `<td class="st-used" title="${esc(usedText(r.used_by) || "Not used yet")}"><b>${+r.used_total || 0}</b><div class="note st-sub">${esc(usedText(r.used_by) || "Not used yet")}</div></td>`;
  const statusCell = r => `<td><div class="row tight">${stopped(r) ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(r)}</div></td>`;
  const view = setupView(kind, spec), closed = S.closed[treeId(kind, spec)] ||= new Set();
  const table = () => view === "tree" ? treeTable() : flatTable();
  // Nothing to show: none yet, only stopped ones, or the search finds none: what it means and the one thing to do.
  const emptyRow = (span, nShown, nRows) => `<tr><td colspan="${span}">${nRows === 0 ? emptyState({ compact: true, glyph: spec.glyph, title: "None yet.", action: { label: `Add ${noun}`, attr: "data-setup-new", value: kind, glyph: "plus", ghost: true } })
    : nShown === 0 ? emptyState({ compact: true, glyph: "eyeOff", title: `Only stopped ${plural}: tick Show stopped to see them.`, action: { label: "Show stopped", attr: "data-setup-show-stopped", value: kind } })
    : emptyState({ compact: true, glyph: "search", title: `No ${plural} match.`, action: { label: "Clear the search", attr: "data-setup-clear", value: kind } })}</td></tr>`;
  // The tree: the same columns, unsorted (accounts by code under their group and parent).
  const treeTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), q = listState(id).q.trim();
    const hit = q ? new Set(shown.filter(r => LT.match(text(r), q)).map(r => r.id)) : null;
    const rowHtml = (r, first) => `<tr class="tree-row${hit && !hit.has(r.id) ? " tree-context" : ""}"><td>${first}</td>${cols.slice(1).map((c, i) => cell(r, c, i + 1)).join("")}${usedCell(r)}${statusCell(r)}</tr>`;
    const [body, n] = setupTree(spec, shown, hit, closed, cols.length + 2, rowHtml);
    setCount(id, hit ? hit.size : n, rows.length);
    return `<table class="tree st-table"><thead><tr>${cols.map(c => `<th${isNum(c) ? ` class="num"` : ""}>${esc(c.label)}</th>`).join("")}<th class="num">Used by</th><th>Status</th></tr></thead><tbody>
      ${body || emptyRow(cols.length + 2, shown.length, rows.length)}
      </tbody></table>`;
  };
  const flatTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), list = listRows(id, shown, text), upto = S.more[id], part = list.slice(0, upto);
    setCount(id, list.length, rows.length);
    return `<table class="st-table"><thead><tr>${cols.map(c => sortTh(id, c.key, esc(c.label), isNum(c) ? "num" : "")).join("")}${sortTh(id, "used", "Used by", "num")}${sortTh(id, "status", "Status")}</tr></thead><tbody>
      ${part.map(r => `<tr class="st-row${stopped(r) ? " stopped" : ""}" data-setup-row="${r.id}">${cols.map((c, i) => cell(r, c, i)).join("")}${usedCell(r)}${statusCell(r)}</tr>`).join("")
      || emptyRow(cols.length + 2, shown.length, rows.length)}
      </tbody></table>${list.length > SETUP_PAGE ? manyRows({ shown: part.length, total: list.length, what: plural, attr: "data-setup-more", value: kind }) : ""}`;
  };
  box.innerHTML = `${setupHead(kind, spec, { title: spec.per_entity ? `${sectionLabel(spec)} · ${e.code}` : undefined, actions: `${paste}${add}` })}
    ${setupTabsHtml(kind, tabs, rows.length)}
    <section class="card st-list" aria-labelledby="st-list-h"><h2 id="st-list-h">${spec.per_entity ? `${esc(sectionLabel(spec))} of ${esc(e.code)}` : `All ${esc(plural)}`}</h2>
      <div class="row st-tools">${listBar(id, plural)}<label class="row tight"><input type="checkbox" data-setup-stopped ${S.stopped ? "checked" : ""}> Show stopped (${nStopped})</label>
        ${deletedToggle(kind)}
        ${spec.tree ? `<div class="seg" role="group" aria-label="Show the ${esc(plural)} as">${[["tree", "Tree"], ["flat", "Flat list"]].map(([v, l]) =>
          `<button type="button" data-setup-view="${v}" aria-pressed="${view === v}">${l}</button>`).join("")}</div>` : ""}
        ${view === "tree" ? `<button type="button" class="ghost small" data-tree-all="open">Open all</button><button type="button" class="ghost small" data-tree-all="close">Close all</button>` : ""}</div>
      <div class="note">Click a row to change it. Something already used can't be deleted: stop using it instead, and its history stays.</div>
      ${view === "tree" ? `<div class="note" id="treeSearchNote" hidden>While searching, everything found is shown open. Parent accounts stay as context. Clear the search to open or close the groups.</div>` : ""}
      <div class="tbl-wrap" id="setupList">${table()}</div></section>
    <div id="setupDeleted"></div>`;
  paintCount(id);
  drawDeleted(kind);
  // While a search is on, the tree's Open all / Close all are off and a note says why.
  const treeBar = () => {
    const on = !!listState(id).q.trim();
    document.querySelectorAll("[data-tree-all]").forEach(b => { b.disabled = on; });
    const note = $("#treeSearchNote");
    if (note) note.hidden = !on;
  };
  LIST_REDRAW[id] = () => { if (!$("#setupList")) return; $("#setupList").innerHTML = table(); paintCount(id); if (view === "tree") treeBar(); };
  if (view === "tree") treeBar();
  if (spec.tree) (S.treeKeys ||= {})[treeId(kind, spec)] = treeKeys(rows);  // what Close all closes
}

// One input for a field (FieldSpec from the server). lock: why it can't be changed; pre: the id prefix. Each has its hint and, for a
// field left empty that needs a value, a place for the message (id + "-err"); a ticked field is a checkbox.
function fieldHtml(f, v, lock, pre) {
  const id = pre + f.key, val = v == null ? "" : String(v);
  const wide = f.wide || f.type === "textarea" ? ` style="grid-column:1/-1"` : "";
  const ro = lock ? " readonly" : "", req = f.required && !lock ? " required" : "";
  const len = f.max && ["text", "textarea", "code", "sqlcode"].includes(f.type) ? ` maxlength="${+f.max}"` : "";
  const hint = f.hint || (f.type === "words" ? "Separate the words with commas." : "");
  const by = ` aria-describedby="${[`${id}-err`, hint ? `${id}-hint` : "", lock ? `${id}-lock` : ""].filter(Boolean).join(" ")}"`;
  const tags = `${f.required && !lock ? `<span class="req">Required</span>` : ""}${lock ? `<span class="req lock">${icon("lock")}Can't be changed</span>` : ""}`;
  const notes = `<span class="field-err" id="${id}-err" role="alert"></span>${hint ? `<span class="note" id="${id}-hint">${esc(hint)}</span>` : ""}${lock ? `<span class="note lock-why" id="${id}-lock">${icon("lock")}${esc(lock)}</span>` : ""}`;
  if (f.type === "bool") return `<label class="field check${lock ? " locked" : ""}"${wide}><span class="row tight"><input id="${id}" type="checkbox"${+val ? " checked" : ""}${lock ? " disabled" : ""}${by}>${esc(f.label)}${tags}</span>${notes}</label>`;
  let input;
  if (f.type === "textarea") input = `<textarea id="${id}" rows="3"${ro}${req}${len}${by}>${esc(val)}</textarea>`;
  // A company, or every company (the empty choice): the companies in use by code, and the one saved even if stopped.
  else if (f.type === "company") input = `<select id="${id}"${lock ? " disabled" : ""}${by}><option value="">Every company</option>${companyChoices(val).map(x =>
    `<option value="${x.id}" ${String(x.id) === val ? "selected" : ""}>${esc(x.code)} · ${esc(x.name)}${isActive(x) ? "" : " (stopped)"}</option>`).join("")}</select>`;
  // A code as SQL Account has it: typed in capitals (data-upper).
  else if (f.type === "sqlcode") input = `<input id="${id}" type="text" class="mono" value="${esc(val)}" spellcheck="false" autocomplete="off" data-upper${ro}${req}${len}${by}>`;
  // Words: typed with commas between them, saved as a list.
  else if (f.type === "words") input = `<input id="${id}" type="text" value="${esc(asList(v).join(", "))}" spellcheck="false" autocomplete="off"${ro}${req}${by}>`;
  else if (f.type === "select") {
    const sel = val;
    let opts = fieldOptions(f);
    if (sel !== "" && !opts.some(o => optVal(o[0]) === sel)) {  // a value no longer offered (a type stopped since) stays as it is
      const was = fieldOptions(f, true).find(o => optVal(o[0]) === sel);
      const gone = f.options_from !== "categories" || !catActive(sel);  // a type in use but not offered here isn't stopped
      opts = [...opts, was ? [was[0], gone ? `${was[1]} (stopped)` : was[1]] : [sel, sel]];
    }
    // An optional choice has an empty one, unless the server's choices have it already (No legal deadline, say).
    const blank = !f.required && !opts.some(o => optVal(o[0]) === "") ? `<option value="">${f.options_from === "parties" ? "(none)" : "—"}</option>` : "";
    input = `<select id="${id}"${lock ? " disabled" : ""}${by}>${blank}${opts.map(([k, l]) => `<option value="${esc(optVal(k))}" ${optVal(k) === sel ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  } else {
    const type = { number: "number", money: "number", day: "number", month: "month", date: "date" }[f.type] || "text";
    const extra = f.type === "money" ? ` step="0.01"` : f.type === "day" ? ` min="1" max="31" step="1"`
      : f.type === "number" ? ` step="any"${f.max != null ? ` max="${+f.max}"` : ""}` : f.type === "code" ? ` class="mono" spellcheck="false" autocomplete="off"` : f.upper ? ` data-upper` : "";
    input = `<input id="${id}" type="${type}" value="${esc(val)}"${extra}${ro}${req}${len}${by}>`;
  }
  return `<label class="field${lock ? " locked" : ""}"${wide}><span>${esc(f.label)}${tags}</span>${input}${notes}</label>`;
}
// What an input holds, as the field's type: numbers, 0 or 1, null for an empty date, month or number, a list of words.
function fieldValue(f, el) {
  const v = el.value;
  if (f.type === "words") return splitWords(v);
  if (f.type === "bool") return el.checked ? 1 : 0;
  if (NUM_TYPES.includes(f.type)) return v.trim() === "" ? null : Number(v);
  if (f.type === "month" || f.type === "date") return v || null;
  if (f.type === "company") return v === "" ? null : +v;
  if (f.type === "sqlcode") return v.trim().toUpperCase() || null;
  if (f.type === "select") { if (v === "") return null; const o = fieldOptions(f, true).find(x => optVal(x[0]) === v); return o ? o[0] : v; }
  return v.trim();
}
function formValues(fields, pre) {
  const out = {};
  for (const f of fields) { const el = document.getElementById(pre + f.key); if (el) out[f.key] = fieldValue(f, el); }
  return out;
}

// The reason asked before a stop, use again, delete, put back or import: a group with its own note, so Enter in it never saves the
// record around it (design/canvas/Setup.dc.html "In use"). askWhy opens it under the button clicked.
const whyForm = () => `<div id="setupWhy" class="st-why" role="group" aria-labelledby="su-why-l" hidden>
  <div class="st-why-note" id="su-why-note" hidden></div>
  <div class="field"><label id="su-why-l" for="su-reason">Why are you making this change? <span class="req why-req">Required</span></label>
    <input id="su-reason" maxlength="500" autocomplete="off" aria-required="true" aria-describedby="su-why-msg" placeholder="Kept in the audit trail with the change">
    <div id="su-why-msg" role="alert"></div></div>
  <div class="row st-why-go"><button class="ghost" type="button" data-why-cancel="1">Cancel</button><button class="btn" type="button" id="su-why-go" data-why-go="1"></button></div></div>`;
// The message under the reason box: it was left empty, or the server refused (the reason it gives, and that nothing was changed).
function setWhyMsg(msg, refused) {
  const m = $("#su-why-msg"), i = $("#su-reason");
  if (m) m.innerHTML = msg ? `<span class="field-err">${icon("alert")}<span>${esc(msg)}${refused ? ` ${esc(state.whyEnd || "Nothing was changed.")}` : ""}</span></span>` : "";
  if (i && i.setAttribute) { if (msg) i.setAttribute("aria-invalid", "true"); else i.removeAttribute("aria-invalid"); }
}
// Shows the reason box under the button clicked; run(reason) does the change once a reason is given. note: what the change does
// (the section's stop, use again or delete note), with its glyph; danger: the go button is red; end: said after a refusal.
function askWhy(btn, label, run, { note = "", glyph = "help", danger = false, end = "Nothing was changed." } = {}) {
  const f = $("#setupWhy");
  if (!f) return;
  (btn.closest(".adv-row") || btn.closest(".st-acts") || btn.closest(".row") || btn).after(f);
  const go = $("#su-why-go"), n = $("#su-why-note");
  go.textContent = label; go.className = danger ? "btn danger-solid" : "btn";
  if (n) { n.hidden = !note; n.innerHTML = note ? `${icon(glyph)}<span>${esc(note)}</span>` : ""; }
  setWhyMsg("");
  for (const b of document.querySelectorAll("[data-setup-act]")) b.setAttribute("aria-expanded", b === btn ? "true" : "false");
  f.hidden = false; state.why = run; state.whyEnd = end; $("#su-reason").focus();
}
function hideWhy() {
  const f = $("#setupWhy");
  if (f) { f.hidden = true; $("#su-reason").value = ""; setWhyMsg(""); }
  for (const b of document.querySelectorAll("[data-setup-act]")) b.setAttribute("aria-expanded", "false");
  state.why = null;
}
async function whySubmit() {
  if (state.whyBusy) return;  // Enter pressed twice: the change is made once
  const inp = $("#su-reason"), goBtn = $("#su-why-go"), reason = inp.value.trim();
  if (!reason) { setWhyMsg("Say why you're making this change."); inp.focus(); return; }
  const run = state.why;
  if (!run) return hideWhy();
  goBtn.disabled = true; goBtn.setAttribute("aria-busy", "true");
  state.whyBusy = true;
  try { await run(reason); hideWhy(); }
  catch (e) { if (appStopped(e)) toast(e.message, true); else { setWhyMsg(e.message, true); $("#su-reason")?.focus?.(); } }
  finally { state.whyBusy = false; if (goBtn.isConnected) { goBtn.disabled = false; goBtn.removeAttribute("aria-busy"); } }
}

// After a company, bank account, payment type, document type, matching words, customer or supplier, or GL account
// change: the page's copy of them is read again (the labels and pickers), and a company stopped or deleted while it was
// showing gives way to the first one in use.
async function afterSetupChange(kind) {
  if (!["entities", "accounts", "payment_types", "doc_types", "guess_words", "hint_words", "filing_words", "parties", "gl_accounts"].includes(kind)) return;
  state.meta = await api("/api/meta");
  const e = ent();
  if (!e || !isActive(e)) state.entity = firstEntityId();
  renderNav();
}

// The record dialog of one company, bank account, type, customer or supplier, account or word rule (id "new" to add one), as
// design/canvas/Setup.dc.html draws it: the fields in their groups, Where used, In use (Stop using, Use again, Delete: each asks why),
// the sections of a company's own, and History. keep: what was typed in it and not saved yet, when it is drawn again after a stop or
// use again; notes: what the server said about the save just made.
async function openSetup(kind, id, { force = false, keep = {}, notes = [] } = {}) {
  if (!force && !(await mayLeave())) return;
  const spec = state.setup.types?.kinds?.[kind];
  if (!spec) return;
  const isNew = id === "new", e = ent();
  if (spec.per_entity && !e) return toast("Add a company first.", true);
  const fresh = Object.fromEntries((spec.fields || []).filter(f => f.default !== undefined).map(f => [f.key, f.default]));
  // A new record's company field starts on the company being viewed (every company is chosen in it).
  for (const f of spec.fields || []) if (f.type === "company" && fresh[f.key] == null && e) fresh[f.key] = e.id;
  const r = isNew ? { record: fresh, used_by: [], used_total: 0, locked: {}, can_delete: false, notes: [] } : await api(`/api/setup/${kind}/${id}`);
  const rec = r.record || {}, locked = r.locked || {}, fields = spec.fields || [];
  const stopped = !isNew && (rec.status === "stopped" || !isActive(rec));
  state.openPayment = null; state.why = null; state.setup.id = id; syncAddr();
  const noun = setupNoun(spec.label), name = isNew ? `New ${noun}` : rec[spec.name_field] || "(no name)";
  const allNotes = [...new Set([...(stopped && spec.stop_note ? [spec.stop_note] : []), ...(r.notes || []), ...(notes || [])])];  // the server's stopped note is the section's: said once
  const tidy = kind === "entities" && !isNew && rec.first_month;
  const groups = (spec.field_groups || [["Details", fields.map(f => f.key)]]).map(([label, keys]) => [label, keys.map(k => fields.find(f => f.key === k)).filter(Boolean)]);
  const placed = new Set(groups.flatMap(g => g[1].map(f => f.key))), rest = fields.filter(f => !placed.has(f.key));
  if (rest.length) groups.splice(Math.max(0, groups.length - 1), 0, ["More", rest]);
  const pills = isNew ? "" : `${stopped ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(rec)}`;
  const actNote = isNew ? "" : +rec.system ? (r.can_stop === false ? `The app relies on this ${noun}, so it can't be stopped or deleted.` : `The app's own rules rely on this ${noun}, so it can't be deleted. It can be stopped.`)
    : r.used_total ? `Delete is offered only for a ${noun} not used anywhere yet. Stop using it instead: its history stays.` : `Not used anywhere yet, so it can still be deleted.`;
  const acts = isNew ? "" : `${stopped ? `<button type="button" class="ghost" data-setup-act="use" aria-expanded="false">${icon("eye")}Use again</button>`
      : r.can_stop === false ? "" : `<button type="button" class="ghost" data-setup-act="stop" aria-expanded="false">${icon("eyeOff")}Stop using</button>`}
    ${r.can_delete && !+rec.system ? `<button type="button" class="btn danger" data-setup-act="delete" aria-expanded="false">${icon("trash")}Delete</button>` : ""}
    ${tidy ? `<button type="button" class="ghost" data-setup-act="tidy">${icon("clock")}Tidy up months before this</button>` : ""}`;
  // Printed invoices and Printed company names belong to a company Kept in SQL Account: its invoices are printed from SQL's documents.
  const printed = kind === "entities" && !isNew && !!+rec.uses_sql;
  // A company switched to Kept here keeps the names confirmed while it was Kept in SQL Account: only they are listed, so they can be removed.
  const keptNames = kind === "entities" && !isNew && !+rec.uses_sql ? await api(`/api/setup/entities/${+id}/sql-names`).catch(() => null) : null;
  const hereNames = !!keptNames?.names?.length;
  $("#drawer").innerHTML = `<form class="np st-form" id="setupForm" novalidate aria-describedby="su-sub">
    <div class="pd-head"><span class="plate brand">${icon(spec.glyph || "sliders")}</span>
      <div class="pd-words"><span class="eyebrow">${esc(spec.label)}${spec.per_entity ? ` · ${esc(e.code)}` : ""}</span>
        <div class="row tight"><h2 id="drawerTitle" tabindex="-1">${esc(name)}</h2>${pills}</div>
        <span id="su-sub" class="pd-sub">${isNew ? "Fill in what you know; the rest can be added later. Nothing is kept until you add it." : "Changes are kept in the audit trail."}</span></div>
      <button type="button" class="ghost small pd-x" id="closeDrawer" aria-label="Close">${icon("close")}</button></div>
    <div class="np-body st-body">
      <div id="su-refused" tabindex="-1"></div><div id="su-summary"></div>
      ${allNotes.length ? `<div class="pd-movenote st-notes">${icon("help")}<div>${allNotes.map(n => `<div>${esc(n)}</div>`).join("")}</div></div>` : ""}
      ${groups.map(([label, fs]) => `<fieldset class="st-group"><legend>${esc(label)}</legend><div class="form setup-form">${fs.map(f => fieldHtml(f, rec[f.key] ?? null, locked[f.key], "su-")).join("")}</div></fieldset>`).join("")}
      ${isNew ? "" : `<section class="st-sec" aria-labelledby="su-used-h"><h3 id="su-used-h">Where used</h3>${r.used_total ? usedHtml(r.used_by) : `<div class="note">Not used anywhere yet.</div>`}</section>
      <section class="st-sec" aria-labelledby="su-use-h"><h3 id="su-use-h">In use</h3>
        <div class="row st-acts">${acts}</div>
        <div class="note" id="su-act-note">${esc(actNote)}</div>
        ${tidy ? `<div class="note">Tidy up removes, from the months before the first month tracked, the payments with no paid date, documents, SQL voucher or bank line, and the checklist items not ticked with no documents.</div>` : ""}
        ${whyForm()}</section>
      ${printed ? `<div id="suPrint"></div><div id="suNames"></div>` : hereNames ? `<div id="suNames"></div>` : ""}
      ${histSection(spec.table, id)}`}
    </div>
    <div class="pd-foot"><span id="su-foot" class="pd-foot-note ro">${isNew ? "It is added as in use." : "Saved changes are kept in the audit trail."}</span>
      <div class="pd-foot-acts"><button type="button" class="ghost" id="su-cancel" data-su-close="1">${isNew ? "Cancel" : "Close"}</button>
        <button type="submit" class="btn" id="su-save" aria-describedby="su-foot">${isNew ? icon("plus") : ""}${isNew ? `Add ${esc(noun)}` : "Save"}</button></div></div>
  </form>`;
  showDrawer("setup");
  state.setup.drawer = { kind, id, locked, used: r.used_by || [], keptHere: hereNames, loaded: formValues(fields, "su-") };
  watchDrawer(keep);
  suFoot();
  if (printed) { drawPrintSettings(id); drawSqlNames(id); }
  else if (hereNames) drawSqlNames(id, keptNames);
}
// The note beside Save: Unsaved changes while something is typed, else what Save does.
function suFoot() {
  const n = $("#su-foot"), D = state.setup.drawer;
  if (!n || !D) return;
  const dirty = !!state.drawerDirty?.();
  n.className = "pd-foot-note" + (dirty ? "" : " ro");
  n.textContent = dirty ? "Unsaved changes" : D.id === "new" ? "It is added as in use." : "Saved changes are kept in the audit trail.";
}

// The company names SQL prints on its exports that the owner took for this company on the SQL page (Take it for), each
// with when and by whom, and a Remove that asks for a second click first.
async function drawSqlNames(id, got) {
  if (!$("#suNames")) return;
  const d = got || await api(`/api/setup/entities/${+id}/sql-names`);
  const box = $("#suNames");
  if (!box || String(state.setup.id) !== String(id)) return;
  const co = state.meta.entities.find(x => x.id === +id);
  const here = !!state.setup.drawer?.keptHere;  // the company is Kept here now: the names can only be removed
  if (here && d.ready && !d.names.length) { box.innerHTML = ""; return; }
  const when = at => at ? `${at.slice(0, 10).split("-").reverse().join("/")}${at.length >= 16 ? ` at ${at.slice(11, 16)}` : ""}` : "—";
  box.innerHTML = `<section class="st-sec" aria-labelledby="su-pn-h"><h3 id="su-pn-h">Printed company names</h3>
    ${here ? `<div class="note">These names were confirmed while this company was Kept in SQL Account. While they stay, no other company can take them; remove any you don't want.</div>`
      : `<div class="note">Names SQL Account prints on its exports that match no company in Setup, confirmed as ${esc(co?.code || "this company")}'s with <b>Take it for ${esc(co?.code || "")}</b> on <a href="${esc(menuHref(MENU_BY_PAGE["accounting/sql"]))}" data-menu="accounting/sql">Accounting › SQL import</a>. Fetch takes files printing them for this company.</div>`}
    ${!d.ready ? `<div class="note">The records need an update for this. Restart the app.</div>`
      : !d.names.length ? `<div class="muted">None confirmed.</div>`
      : `<div class="tbl-wrap"><table><thead><tr><th>Name as printed</th><th>Confirmed</th><th>By</th><th></th></tr></thead><tbody>${d.names.map(n => `<tr>
        <td>${esc(n.name)}</td><td>${esc(when(n.confirmed_at))}</td><td>${n.confirmed_by ? esc(n.confirmed_by) : `<span class="muted">Not recorded</span>`}</td>
        <td style="white-space:nowrap"><button class="ghost small" type="button" data-sql-name-remove="${+n.id}" data-sql-name="${esc(n.name)}">Remove</button></td></tr>`).join("")}</tbody></table></div>
        <div class="note" id="suNamesConfirm" hidden></div>`}</section>`;
}
async function removeSqlName(btn) {
  const id = state.setup.drawer?.id;
  if (!id || id === "new") return;
  const note = $("#suNamesConfirm");
  if (btn.dataset.confirm !== "1") {
    document.querySelectorAll("[data-sql-name-remove]").forEach(b => { b.dataset.confirm = ""; b.textContent = "Remove"; });
    btn.dataset.confirm = "1";
    btn.textContent = "Click again to remove";
    if (note) { note.textContent = `Removing "${btn.dataset.sqlName}": files printing it are held again on the next Fetch, until Take it for is clicked again.`; note.hidden = false; }
    return;
  }
  let r;
  try { r = await api(`/api/setup/entities/${+id}/sql-names/${+btn.dataset.sqlNameRemove}`, { method: "DELETE", json: {} }); }
  catch (e) { btn.dataset.confirm = ""; btn.textContent = "Remove"; if (note) note.hidden = true; throw e; }
  toast(`"${r.removed}" removed. Files printing it are held again on the next Fetch, until Take it for is clicked again.`);
  return drawSqlNames(id, { ready: true, ...r });
}

// A company's printed invoices: its logo and signature (uploaded here, PNG or JPEG) and the settings they still lack.
async function drawPrintSettings(id, got) {
  if (!$("#suPrint")) return;
  const p = got || await api(`/api/setup/entities/${id}/print`);
  const box = $("#suPrint");
  if (!box || String(state.setup.id) !== String(id)) return;
  const img = (which, label) => `<div class="field"><span>${label}</span>
    ${p[which] ? `<img src="/api/setup/entities/${+id}/image/${which}?v=${esc(p[which].slice(0, 12))}" alt="${label}" style="max-height:70px;max-width:220px;object-fit:contain;border:1px solid var(--line);border-radius:4px;background:#fff;padding:4px">` : `<span class="muted">None uploaded</span>`}
    <div class="row"><input type="file" id="suImg-${which}" accept=".png,.jpg,.jpeg,image/png,image/jpeg"><button class="ghost small" type="button" data-inv-img-up="${which}">Upload</button>
      ${p[which] ? `<button class="ghost small" type="button" data-inv-img-remove="${which}">Remove</button>` : ""}</div></div>`;
  const bankGap = (p.missing || []).some(m => /Setup › Bank accounts/.test(m));
  box.innerHTML = `<section class="st-sec" id="su-print" aria-labelledby="su-pi-h"><h3 id="su-pi-h">Printed invoices</h3>
    <div class="note">Customer invoices and self-billed e-Invoices are printed from SQL's documents with this header and footer: the name, registration no., TIN, address, phone, email and website above, the bank account on invoices, and the logo and signature here (PNG or JPEG, at most 2 MB). Used by <a href="${esc(menuHref(MENU_BY_PAGE["accounting/einvoices"]))}" data-menu="accounting/einvoices">Accounting › e-Invoices</a>.</div>
    <div class="grid2">${img("logo", "Logo")}${img("signature", "Signature")}</div>
    ${p.missing.length ? `<div class="note"><b>Print settings still missing</b> (invoices print without them):<ul>${p.missing.map(m => `<li>${esc(m)}</li>`).join("")}</ul>${bankGap ? `<button type="button" class="ghost small" data-setup-kind="accounts" data-setup-entity="${+id}">Open Setup › Bank accounts</button>` : ""}</div>` : `<div class="note">${icon("check")} Every print setting is filled in.</div>`}
    ${fontNote(p.fonts)}${tooLongNote(p.too_long)}</section>`;
}
// Uploads (or removes) the logo or signature of the company open in the drawer.
async function printImage(which, remove) {
  const id = state.setup.drawer?.id;
  if (!id || id === "new") return;
  const name = which === "logo" ? "Logo" : "Signature";
  let r;
  if (remove) r = await api(`/api/setup/entities/${+id}/image/${which}`, { method: "DELETE", json: {} });
  else {
    const f = $(`#suImg-${which}`)?.files?.[0];
    if (!f) return toast("Choose an image first.", true);
    const form = new FormData(); form.append("file", f); form.append("entity_id", id);
    r = await api(`/api/setup/entities/${+id}/image/${which}`, { form });
  }
  toast(remove ? `${name} taken off the invoices` : `${name} uploaded`);
  return drawPrintSettings(id, r);
}

// Fields left empty that the record needs, said at the top of the dialog and on each field (the server checks the rest and says so in place).
function suCheck(fields, now, locked) {
  const gone = v => v == null || v === "" || (Array.isArray(v) && !v.length);
  const bad = fields.filter(f => f.required && !(f.key in locked) && gone(now[f.key]));
  for (const f of fields) {
    const el = document.getElementById("su-" + f.key), slot = document.getElementById("su-" + f.key + "-err"), on = bad.includes(f);
    if (slot) slot.innerHTML = on ? `${icon("alert")}This can't be empty.` : "";
    if (el && el.setAttribute) { if (on) el.setAttribute("aria-invalid", "true"); else el.removeAttribute("aria-invalid"); }
  }
  const box = $("#su-summary");
  if (box) box.innerHTML = bad.length ? `<div class="refused" role="alert">${icon("alert")}<div class="refused-text"><b>${bad.length === 1 ? "1 field needs a fix." : `${bad.length} fields need a fix.`}</b><div class="refused-why">${esc(bad.map(f => f.label).join(", "))}.</div></div></div>` : "";
  if (bad.length) document.getElementById("su-" + bad[0].key)?.focus?.();
  return !bad.length;
}
// A refusal in the dialog's own place (not a toast, which goes after a few seconds): what the server said, and that nothing was saved.
function suRefused(message) {
  const box = $("#su-refused");
  if (!box) return toast(message, true);
  box.innerHTML = refusedNote(message, { title: "Nothing was saved" });
  box.focus?.({ preventScroll: true });
}

// Save: a new record is added; one already there sends only the fields changed.
async function setupSave() {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind], fields = spec.fields || [], now = formValues(fields, "su-");
  const box = $("#su-refused"); if (box) box.innerHTML = "";
  if (!suCheck(fields, now, D.id === "new" ? {} : D.locked)) return;
  if (D.id === "new") {
    // Empty fields are left out, but a company field always goes: empty there means every company.
    const isCompany = k => fields.some(f => f.key === k && f.type === "company");
    const body = { fields: Object.fromEntries(Object.entries(now).filter(([k, v]) => v !== null && v !== "" || isCompany(k))) };
    if (spec.per_entity) body.entity_id = state.entity;
    let r;
    try { r = await api(`/api/setup/${D.kind}`, { json: body }); } catch (e) { if (appStopped(e)) throw e; return suRefused(e.message); }
    toast(`${spec.label} added`);
    await afterSetupChange(D.kind); await render();
    return r.id == null ? closeDrawer(true) : openSetup(D.kind, r.id, { force: true });
  }
  const changed = {};
  for (const k in now) if (!(k in D.locked) && JSON.stringify(now[k]) !== JSON.stringify(D.loaded[k])) changed[k] = now[k];
  if (!Object.keys(changed).length) {
    const n = $("#su-foot"); if (n) { n.className = "pd-foot-note ro"; n.textContent = "Nothing has changed."; }
    return toast("Nothing has changed.");
  }
  let r;
  try { r = await api(`/api/setup/${D.kind}/${D.id}`, { method: "PATCH", json: { fields: changed } }); } catch (e) { if (appStopped(e)) throw e; return suRefused(e.message); }
  toast("Saved");
  await afterSetupChange(D.kind); await render();
  return openSetup(D.kind, D.id, { force: true, notes: r.notes });
}

// Stop using, Use again and Delete ask why first, with what the change does; Tidy up counts first, then asks. A refusal (the cash
// book account, a record used since the dialog was drawn) comes back under the reason box, with nothing changed.
async function setupAct(act, btn) {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind];
  if (act === "tidy") return tidyMonths(D.id, btn);
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
  if (btn.getAttribute("aria-expanded") === "true" && $("#setupWhy") && !$("#setupWhy").hidden) return hideWhy();  // the button again closes its box
  // An account a company prints on its invoices: stopping it is allowed, and the company's print settings then say so.
  const onInvoices = act === "stop" && (D.used || []).some(([w, n]) => /invoices/.test(w) && +n);
  const note = { stop: (spec.stop_note || "") + (onInvoices ? " Its company prints it under All payments to be made to. Once it is stopped, the print settings say that the bank account chosen for invoices is stopped." : ""),
    use: spec.use_note || "", delete: spec.delete_note || "" }[act];
  return askWhy(btn, label, async reason => {
    if (act === "delete") {
      await api(`/api/setup/${D.kind}/${D.id}`, { method: "DELETE", json: { reason } });
      closeDrawer(true); toast(`${spec.label} deleted`);
      await afterSetupChange(D.kind); return render();
    }
    await api(`/api/setup/${D.kind}/${D.id}/${act}`, { json: { reason } });
    toast(act === "stop" ? "Stopped. Its history stays." : "In use again");
    const keep = drawerEdits();
    await afterSetupChange(D.kind); await render();
    return openSetup(D.kind, D.id, { force: true, keep });
  }, { note, glyph: { stop: "eyeOff", use: "eye", delete: "trash" }[act], danger: act === "delete" });
}

// Tidy up before a company's first month tracked: the first click counts what would go, the second asks why.
async function tidyMonths(eid, btn) {
  const e = state.meta.entities.find(x => x.id === +eid);
  if (btn.dataset.armed !== "1") {
    const n = await api(`/api/months/tidy?entity=${eid}`), before = n.before ? monthName(n.before) : "the first month tracked";
    if (!n.payments && !n.tasks) return toast(`Nothing to tidy up before ${before}.`);
    btn.dataset.armed = "1"; btn.textContent = `Click again to remove ${n.payments} payments and ${n.tasks} checklist items before ${before}`; return;
  }
  return askWhy(btn, "Remove them", async reason => {
    const r = await api("/api/months/tidy", { json: { entity_id: +eid, reason } });
    toast(`Removed ${r.payments} payments and ${r.tasks} checklist items from ${e?.code || "the company"}`);
    const keep = drawerEdits();
    await render(); return openSetup("entities", eid, { force: true, keep });
  });
}

