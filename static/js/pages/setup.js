"use strict";
/* ---------------- Setup ---------------- */
// Companies, bank accounts, recurring payments and general settings, kept in the records and changed here. The sections,
// their fields and list columns come from the server (/api/setup/types). A stopped record stays, for its history.
const setupSpec = () => state.setup.types?.kinds?.[state.setup.kind] || null;
const sectionLabel = spec => spec.single || !spec.plural ? spec.label : spec.plural.charAt(0).toUpperCase() + spec.plural.slice(1);
const NUM_TYPES = ["number", "money", "day"];

async function viewSetup(main) {
  const S = state.setup;
  if (!S.types) S.types = await api("/api/setup/types");
  const T = S.types;
  if (!T.kinds[S.kind]) S.kind = T.groups.flatMap(g => g[1]).find(k => T.kinds[k]) || null;
  renderNav();  // the breadcrumb names the section
  const sections = T.groups.map(([g, kinds]) => {
    const ks = kinds.filter(k => T.kinds[k]);
    return ks.length ? `<div class="setup-group">${esc(g)}</div>${ks.map(k => `<button type="button" data-setup-kind="${esc(k)}"${k === S.kind ? ` class="on" aria-current="page"` : ""}>${esc(sectionLabel(T.kinds[k]))}</button>`).join("")}` : "";
  }).join("");
  main.innerHTML = `<div class="setup-grid"><nav class="setup-nav card noprint" aria-label="Setup sections">${sections}</nav><div class="setup-main" id="setupMain"></div></div>`;
  const box = $("#setupMain"), spec = setupSpec();
  if (!spec) box.innerHTML = `<div class="card"><div class="note">Nothing to set up yet.</div></div>`;
  else if (spec.single) await setupSettings(box);
  else if (S.kind === "payees") await viewPayees(box);
  else if (S.kind === "required") await setupRequired(box);
  else if (S.kind === "checklist") await setupChecklist(box);
  else if (S.kind === "reminders") await setupReminders(box);
  else if (S.kind === "move") await setupMove(box);
  else if (spec.bespoke) box.innerHTML = `<div class="card"><h1>${esc(sectionLabel(spec))}</h1><div class="note">This section isn't ready in this version of the app.</div></div>`;
  else await setupList(box, S.kind);
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

// The list of one kind (companies, or one company's bank accounts), stopped ones shown when asked.
async function setupList(box, kind) {
  const S = state.setup, spec = S.types.kinds[kind], id = "setup-" + kind, e = ent();
  const cols = spec.columns || [], fieldOf = k => (spec.fields || []).find(f => f.key === k);
  const isNum = c => NUM_TYPES.includes(fieldOf(c.key)?.type);
  // Registered before the list's first listState, so a sort chosen earlier is kept.
  SORTS[id] ||= Object.fromEntries([...cols.map(c => [c.key, [isNum(c) ? "num" : "text", r => { const f = fieldOf(c.key);
      return f && ["select", "bool", "words", "company"].includes(f.type) ? fieldText(f, r[c.key]) : r[c.key]; }]]),
    ["used", ["num", r => r.used_total]], ["status", ["text", r => r.status]]]);
  if (spec.per_entity && !e) { box.innerHTML = `<div class="card"><h1>${esc(sectionLabel(spec))}</h1><div class="note">Add a company first.</div></div>`; return; }
  const { rows } = await api(`/api/setup/${kind}${spec.per_entity ? `?entity=${state.entity}` : ""}`);
  const stopped = r => r.status === "stopped", nStopped = rows.filter(stopped).length;
  const text = r => [...cols.map(c => fieldText(fieldOf(c.key), r[c.key])), usedText(r.used_by), stopped(r) ? "stopped" : "in use", +r.system ? "used by the app" : ""].join(" ");
  const cell = (r, c, i) => {
    const v = fieldText(fieldOf(c.key), r[c.key]);
    if (!i) return `<td><button class="link" data-setup-open="${r.id}">${esc(v || "(no name)")}</button></td>`;
    return `<td${isNum(c) ? ` class="num"` : ""}>${v ? esc(v) : "—"}</td>`;
  };
  const view = setupView(kind, spec), closed = S.closed[treeId(kind, spec)] ||= new Set();
  const table = () => view === "tree" ? treeTable() : flatTable();
  // The tree: the same columns, unsorted (accounts by code under their group and parent).
  const treeTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), q = listState(id).q.trim();
    const hit = q ? new Set(shown.filter(r => LT.match(text(r), q)).map(r => r.id)) : null;
    const rowHtml = (r, first) => `<tr class="tree-row${hit && !hit.has(r.id) ? " tree-context" : ""}"><td>${first}</td>${cols.slice(1).map((c, i) => cell(r, c, i + 1)).join("")}
        <td class="num" title="${esc(usedText(r.used_by) || "Not used yet")}">${+r.used_total || 0}</td>
        <td>${stopped(r) ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(r)}</td></tr>`;
    const [body, n] = setupTree(spec, shown, hit, closed, cols.length + 2, rowHtml);
    setCount(id, hit ? hit.size : n, rows.length);
    return `<table class="tree"><thead><tr>${cols.map(c => `<th${isNum(c) ? ` class="num"` : ""}>${esc(c.label)}</th>`).join("")}<th class="num">Used by</th><th>Status</th></tr></thead><tbody>
      ${body || `<tr><td colspan="${cols.length + 2}" class="empty">${!rows.length ? "None yet." : shown.length ? `No ${esc(spec.plural)} match.` : `Only stopped ${esc(spec.plural)}: tick Show stopped to see them.`}</td></tr>`}
      </tbody></table>`;
  };
  const flatTable = () => {
    const shown = S.stopped ? rows : rows.filter(r => !stopped(r)), list = listRows(id, shown, text);
    setCount(id, list.length, rows.length);
    return `<table><thead><tr>${cols.map(c => sortTh(id, c.key, esc(c.label), isNum(c) ? "num" : "")).join("")}${sortTh(id, "used", "Used by", "num")}${sortTh(id, "status", "Status")}</tr></thead><tbody>
      ${list.map(r => `<tr>${cols.map((c, i) => cell(r, c, i)).join("")}
        <td class="num" title="${esc(usedText(r.used_by) || "Not used yet")}">${+r.used_total || 0}</td>
        <td>${stopped(r) ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(r)}</td></tr>`).join("")
      || `<tr><td colspan="${cols.length + 2}" class="empty">${!rows.length ? "None yet." : shown.length ? `No ${esc(spec.plural)} match.` : `Only stopped ${esc(spec.plural)}: tick Show stopped to see them.`}</td></tr>`}
      </tbody></table>`;
  };
  box.innerHTML = `${spec.per_entity ? entityPicker() : ""}
    <div class="card"><div class="row spread"><h1>${esc(sectionLabel(spec))}${spec.per_entity ? ` · ${esc(e.code)}` : ""}</h1>
        <div class="row">${spec.paste ? `<button class="ghost" data-setup-paste="${esc(kind)}">Paste a list</button>` : ""}<button class="btn" data-setup-new="${esc(kind)}">Add ${esc(lowerFirst(spec.label))}</button></div></div>
      ${spec.help ? `<div class="note">${esc(spec.help)}</div>` : ""}
      <div class="note">Click a row to change it. Something already used can't be deleted: stop using it instead, and its history stays.</div>
      <div class="row">${listBar(id, spec.plural)}<label class="row tight"><input type="checkbox" data-setup-stopped ${S.stopped ? "checked" : ""}> Show stopped (${nStopped})</label>
        ${deletedToggle(kind)}
        ${spec.tree ? `<div class="seg" role="group" aria-label="Show the ${esc(spec.plural)} as">${[["flat", "Flat list"], ["tree", "Tree"]].map(([v, l]) =>
          `<button type="button" data-setup-view="${v}" aria-pressed="${view === v}">${l}</button>`).join("")}</div>` : ""}
        ${view === "tree" ? `<button type="button" class="ghost small" data-tree-all="open">Open all</button><button type="button" class="ghost small" data-tree-all="close">Close all</button>` : ""}</div>
      ${view === "tree" ? `<div class="note" id="treeSearchNote" hidden>While searching, everything found is shown open. Clear the search to open or close the groups.</div>` : ""}
      <div class="tbl-wrap" id="setupList">${table()}</div><div id="setupDeleted"></div></div>`;
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

// One input for a field (FieldSpec from the server). lock: why it can't be changed; pre: the id prefix.
function fieldHtml(f, v, lock, pre) {
  const id = pre + f.key, val = v == null ? "" : String(v);
  const wide = f.wide || f.type === "textarea" ? ` style="grid-column:1/-1"` : "";
  const ro = lock ? " readonly" : "", req = f.required && !lock ? " required" : "";
  const len = f.max && ["text", "textarea", "code", "sqlcode"].includes(f.type) ? ` maxlength="${+f.max}"` : "";
  let input;
  if (f.type === "textarea") input = `<textarea id="${id}" rows="3"${ro}${req}${len}>${esc(val)}</textarea>`;
  // A company, or every company (the empty choice): the companies in use by code, and the one saved even if stopped.
  else if (f.type === "company") input = `<select id="${id}"${lock ? " disabled" : ""}><option value="">Every company</option>${companyChoices(val).map(x =>
    `<option value="${x.id}" ${String(x.id) === val ? "selected" : ""}>${esc(x.code)} · ${esc(x.name)}${isActive(x) ? "" : " (stopped)"}</option>`).join("")}</select>`;
  // A code as SQL Account has it: typed in capitals (data-upper).
  else if (f.type === "sqlcode") input = `<input id="${id}" type="text" class="mono" value="${esc(val)}" spellcheck="false" autocomplete="off" data-upper${ro}${req}${len}>`;
  // Words: typed with commas between them, saved as a list.
  else if (f.type === "words") input = `<input id="${id}" type="text" value="${esc(asList(v).join(", "))}" spellcheck="false" autocomplete="off"${ro}${req}>`;
  else if (f.type === "bool" || f.type === "select") {
    const sel = f.type === "bool" ? (val === "" ? "0" : String(+val ? 1 : 0)) : val;
    let opts = f.type === "bool" ? [[1, "Yes"], [0, "No"]] : fieldOptions(f);
    if (sel !== "" && !opts.some(o => optVal(o[0]) === sel)) {  // a value no longer offered (a type stopped since) stays as it is
      const was = fieldOptions(f, true).find(o => optVal(o[0]) === sel);
      const gone = f.options_from !== "categories" || !catActive(sel);  // a type in use but not offered here isn't stopped
      opts = [...opts, was ? [was[0], gone ? `${was[1]} (stopped)` : was[1]] : [sel, sel]];
    }
    // An optional choice has an empty one, unless the server's choices have it already (No legal deadline, say).
    const blank = f.type === "select" && !f.required && !opts.some(o => optVal(o[0]) === "") ? `<option value="">${f.options_from === "parties" ? "(none)" : "—"}</option>` : "";
    input = `<select id="${id}"${lock ? " disabled" : ""}>${blank}${opts.map(([k, l]) => `<option value="${esc(optVal(k))}" ${optVal(k) === sel ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  } else {
    const type = { number: "number", money: "number", day: "number", month: "month", date: "date" }[f.type] || "text";
    const extra = f.type === "money" ? ` step="0.01"` : f.type === "day" ? ` min="1" max="31" step="1"`
      : f.type === "number" ? ` step="any"${f.max != null ? ` max="${+f.max}"` : ""}` : f.type === "code" ? ` class="mono" spellcheck="false" autocomplete="off"` : "";
    input = `<input id="${id}" type="${type}" value="${esc(val)}"${extra}${ro}${req}${len}>`;
  }
  const hint = f.hint || (f.type === "words" ? "Separate the words with commas." : "");
  return `<label class="field${lock ? " locked" : ""}"${wide}><span>${esc(f.label)}</span>${input}${hint ? `<span class="note">${esc(hint)}</span>` : ""}${lock ? `<span class="note">${esc(lock)}</span>` : ""}</label>`;
}
// What an input holds, as the field's type: numbers, 0 or 1, null for an empty date, month or number, a list of words.
function fieldValue(f, el) {
  const v = el.value;
  if (f.type === "words") return splitWords(v);
  if (f.type === "bool") return +v ? 1 : 0;
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

// The reason asked before a stop, use again, delete or tidy up: its own form, so Enter in it doesn't save the record.
const whyForm = () => `<form id="setupWhy" class="row setup-why" hidden><label class="field"><span>Why are you making this change?</span><input id="su-reason" maxlength="500" autocomplete="off"></label>
  <button class="btn" type="submit" id="su-why-go"></button><button class="ghost" type="button" data-why-cancel="1">Cancel</button></form>`;
// Shows the reason box under the button clicked; run(reason) does the change once a reason is given.
function askWhy(btn, label, run) {
  const f = $("#setupWhy");
  if (!f) return;
  (btn.closest(".adv-row") || btn.closest(".row") || btn).after(f);
  $("#su-why-go").textContent = label; f.hidden = false; state.why = run; $("#su-reason").focus();
}
function hideWhy() {
  const f = $("#setupWhy");
  if (f) { f.hidden = true; $("#su-reason").value = ""; }
  state.why = null;
}
async function whySubmit() {
  const inp = $("#su-reason"), goBtn = $("#su-why-go"), reason = inp.value.trim();
  if (!reason) { toast("Say why you're making this change.", true); inp.focus(); return; }
  const run = state.why;
  if (!run) return hideWhy();
  goBtn.disabled = true;
  try { await run(reason); hideWhy(); } catch (e) { toast(e.message, true); } finally { if (goBtn.isConnected) goBtn.disabled = false; }
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

// The drawer of one company or bank account (id "new" to add one). keep: what was typed in it and not saved yet, when
// it is drawn again after a stop or use again; notes: what the server said about the save just made.
async function openSetup(kind, id, { force = false, keep = {}, notes = [] } = {}) {
  if (!force && !(await mayLeave())) return;
  const spec = state.setup.types?.kinds?.[kind];
  if (!spec) return;
  const isNew = id === "new", e = ent();
  if (spec.per_entity && !e) return toast("Add a company first.", true);
  const fresh = Object.fromEntries((spec.fields || []).filter(f => f.default !== undefined).map(f => [f.key, f.default]));
  // A new record's company field starts on the company being viewed (every company is chosen in it).
  for (const f of spec.fields || []) if (f.type === "company" && fresh[f.key] == null && e) fresh[f.key] = e.id;
  const r = isNew ? { record: fresh, used_by: [], locked: {}, can_delete: false, notes: [] } : await api(`/api/setup/${kind}/${id}`);
  const rec = r.record || {}, locked = r.locked || {}, fields = spec.fields || [];
  const stopped = !isNew && (rec.status === "stopped" || !isActive(rec));
  state.openPayment = null; state.why = null; state.setup.id = id;
  const name = isNew ? `New ${lowerFirst(spec.label)}` : rec[spec.name_field] || "(no name)";
  const allNotes = [...(r.notes || []), ...(notes || []).filter(n => !(r.notes || []).includes(n))];
  const tidy = kind === "entities" && !isNew && rec.first_month;
  $("#drawer").innerHTML = `
    <div class="ex-head"><div class="row spread"><div><div class="eyebrow">${esc(spec.label)}${spec.per_entity ? " · " + esc(e.code) : ""}</div><h2>${esc(name)}</h2></div><button class="ghost small" id="closeDrawer">Close</button></div>
      ${isNew ? "" : `<div class="row">${stopped ? `<span class="pill grey">Stopped</span>` : `<span class="pill ok">In use</span>`}${systemPill(rec)}</div>`}</div>
    ${spec.help ? `<div class="note">${esc(spec.help)}</div>` : ""}
    <form class="form setup-form" id="setupForm">${fields.map(f => fieldHtml(f, rec[f.key] ?? null, locked[f.key], "su-")).join("")}
      <div class="row" style="grid-column:1/-1"><button class="btn" type="submit">${isNew ? `Add ${esc(lowerFirst(spec.label))}` : "Save"}</button></div></form>
    ${allNotes.map(n => `<div class="note">${esc(n)}</div>`).join("")}
    ${isNew ? "" : `<div><h3>Where used</h3>${usedHtml(r.used_by)}</div>
    <div class="row">${stopped ? `<button class="ghost" type="button" data-setup-act="use">Use again</button>` : r.can_stop === false ? "" : `<button class="ghost" type="button" data-setup-act="stop">Stop using</button>`}
      ${r.can_delete && !+rec.system ? `<button class="btn danger small" type="button" data-setup-act="delete">Delete</button>` : ""}
      ${tidy ? `<button class="ghost" type="button" data-setup-act="tidy">Tidy up months before this</button>` : ""}</div>
    ${+rec.system ? `<div class="note">The app's own rules rely on this ${esc(lowerFirst(spec.label))}, so it can't be deleted.</div>` : ""}
    ${tidy ? `<div class="note">Tidy up removes, from the months before the first month tracked, the payments with no paid date, documents, SQL voucher or bank line, and the checklist items not ticked with no documents.</div>` : ""}
    ${kind === "entities" ? `<div id="suPrint"></div><div id="suNames"></div>` : ""}
    ${whyForm()}
    ${histSection(spec.table, id)}`}`;
  showDrawer();
  state.setup.drawer = { kind, id, locked, loaded: formValues(fields, "su-") };
  watchDrawer(keep);
  if (kind === "entities" && !isNew) { drawPrintSettings(id); drawSqlNames(id); }
}

// The company names SQL prints on its exports that the owner took for this company on the SQL page (Take it for), each
// with when and by whom, and a Remove that asks for a second click first.
async function drawSqlNames(id, got) {
  if (!$("#suNames")) return;
  const d = got || await api(`/api/setup/entities/${+id}/sql-names`);
  const box = $("#suNames");
  if (!box || String(state.setup.id) !== String(id)) return;
  const co = state.meta.entities.find(x => x.id === +id);
  const when = at => at ? `${at.slice(0, 10).split("-").reverse().join("/")}${at.length >= 16 ? ` at ${at.slice(11, 16)}` : ""}` : "—";
  box.innerHTML = `<h3>Printed company names</h3>
    <div class="note">Names SQL Account prints on its exports that match no company in Setup, confirmed as ${esc(co?.code || "this company")}'s with <b>Take it for ${esc(co?.code || "")}</b> on the SQL page. Fetch takes files printing them for this company.</div>
    ${!d.ready ? `<div class="note">The records need an update for this. Restart the app.</div>`
      : !d.names.length ? `<div class="muted">None confirmed.</div>`
      : `<div class="tbl-wrap"><table><thead><tr><th>Name as printed</th><th>Confirmed</th><th>By</th><th></th></tr></thead><tbody>${d.names.map(n => `<tr>
        <td>${esc(n.name)}</td><td>${esc(when(n.confirmed_at))}</td><td>${n.confirmed_by ? esc(n.confirmed_by) : `<span class="muted">Not recorded</span>`}</td>
        <td style="white-space:nowrap"><button class="ghost small" type="button" data-sql-name-remove="${+n.id}" data-sql-name="${esc(n.name)}">Remove</button></td></tr>`).join("")}</tbody></table></div>
        <div class="note" id="suNamesConfirm" hidden></div>`}`;
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
  box.innerHTML = `<h3>Printed invoices</h3>
    <div class="note">Customer invoices and self-billed e-Invoices are printed from SQL's documents with this header and footer: the name, registration no., TIN, address, phone, email and website above, the bank account on invoices, and the logo and signature here (PNG or JPEG, at most 2 MB).</div>
    <div class="grid2">${img("logo", "Logo")}${img("signature", "Signature")}</div>
    ${p.missing.length ? `<div class="note"><b>Print settings still missing</b> (invoices print without them):<ul>${p.missing.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>` : `<div class="note">Every print setting is filled in.</div>`}
    ${fontNote(p.fonts)}${tooLongNote(p.too_long)}`;
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

// Save: a new record is added; one already there sends only the fields changed.
async function setupSave() {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind], now = formValues(spec.fields || [], "su-");
  if (D.id === "new") {
    // Empty fields are left out, but a company field always goes: empty there means every company.
    const isCompany = k => (spec.fields || []).some(f => f.key === k && f.type === "company");
    const body = { fields: Object.fromEntries(Object.entries(now).filter(([k, v]) => v !== null && v !== "" || isCompany(k))) };
    if (spec.per_entity) body.entity_id = state.entity;
    const r = await api(`/api/setup/${D.kind}`, { json: body });
    toast(`${spec.label} added`);
    await afterSetupChange(D.kind); await render();
    return r.id == null ? closeDrawer(true) : openSetup(D.kind, r.id, { force: true });
  }
  const fields = {};
  for (const k in now) if (!(k in D.locked) && JSON.stringify(now[k]) !== JSON.stringify(D.loaded[k])) fields[k] = now[k];
  if (!Object.keys(fields).length) return toast("Nothing has changed.");
  const r = await api(`/api/setup/${D.kind}/${D.id}`, { method: "PATCH", json: { fields } });
  toast("Saved");
  await afterSetupChange(D.kind); await render();
  return openSetup(D.kind, D.id, { force: true, notes: r.notes });
}

// Stop using, Use again and Delete ask why first; Tidy up counts first, then asks.
async function setupAct(act, btn) {
  const D = state.setup.drawer;
  if (!D) return;
  const spec = state.setup.types.kinds[D.kind];
  if (act === "tidy") return tidyMonths(D.id, btn);
  const label = { stop: "Stop using it", use: "Use it again", delete: "Delete it" }[act];
  if (!label) return;
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
  });
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

