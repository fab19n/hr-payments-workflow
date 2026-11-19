"use strict";
/* ---------------- Payments › Monthly checklist (slice 2) ----------------
   The checklist part of the company month page of before slice 2, as its own page (view key checklist, address
   #/<CODE>/<YYYY-MM>/payments/checklist), built to design/canvas/MonthlyChecklist.dc.html: "18 of 27 done" with its bar, the filters
   All items, Not done, Done and Missing documents (the items whose documents are missing, which the Overview's Documents missing
   count on the Overview will open, from slice 1's Overview cards (core/next.js pillGo docs_missing); the filter is in the address), the items in sections by when they fall due (50 at a time), each with its tick, its document slots,
   what the records show, and "Tick anyway?" (core/events.js) when they don't; Mark month as filed and Reopen; the payroll workbook
   the Payroll check filed, with the earlier ones it replaced; reminders waiting for a later month; a month not set up. A filed month
   is read only until it is reopened here. */

const CL_TABS = [["all", "All items"], ["open", "Not done"], ["done", "Done"], ["missing", "Missing documents"]];
// A month's checklist is read whole (most hold 20 to 40 items); only a much longer one shows 50 at a time, with Show more.
const CL_STEP = 50;
// A reminder waiting for a later month (t.waiting) shows under All items only, and is never counted here.
const clIn = (t, k) => k === "all" || (!t.waiting && (k === "missing" ? t.missing.length > 0 : k === "open" ? !t.done : t.done));
const clTab = () => { const t = state.addr?.params?.tab; return CL_TABS.some(([k]) => k === t) ? t : "all"; };
function clState() {
  const key = `${state.entity}:${state.month}`;
  if (!state.cl || state.cl.key !== key) state.cl = { key, shown: CL_STEP, hist: [] };
  return state.cl;
}
const lastDayOf = m => new Date(+m.slice(0, 4), +m.slice(5, 7), 0).getDate();
// The sections, by when an item falls due: in the month (before paying), the 1st to the 15th of the next month (statutory and
// filing), the rest of the next month (books, bank and review), later; then the reminders from other months.
function clSection(t, month) {
  if (t.waiting) return "later";
  const nx = shiftMonth(month, 1);
  return t.due_date <= `${month}-${String(lastDayOf(month)).padStart(2, "0")}` ? "pay" : t.due_date <= `${nx}-15` ? "file"
    : t.due_date <= `${nx}-${String(lastDayOf(nx)).padStart(2, "0")}` ? "close" : "after";
}
function clSections(month) {
  const MN = monthName(month).split(" ")[0], nx = shiftMonth(month, 1), NX = MONTHS[+nx.slice(5, 7) - 1];
  return { pay: ["Before paying", `due in ${MN}`], file: ["Statutory and filing", `1 to 15 ${NX}`], close: ["Books, bank and review", `16 to ${lastDayOf(nx)} ${NX}`],
    after: ["Later", `counted in ${MN}`], later: ["Reminders from other months", "not counted here"] };
}
const CL_ORDER = ["pay", "file", "close", "after", "later"];
const atTime = iso => iso ? `${shortDate(iso)}${String(iso).length > 10 ? " " + String(iso).slice(11, 16) : ""}` : "";
// What a workbook check found, in words (no names, no figures).
function checkWords(c) {
  const fix = +c.to_fix || 0, chk = +c.to_check || 0, n = +c.notes || 0;
  return `${fix ? `${fix} thing${fix > 1 ? "s" : ""} to fix before paying` : "nothing to fix"}${chk ? `, ${chk} to check` : ""}${n ? `; ${n} note${n > 1 ? "s" : ""}` : ""}`;
}

// One item. The markup of the month page before slice 2 is kept (tests and the change handler read data-task), with the lock note
// for an item done from the records, the payroll workbook's place, and the earlier files a document replaced.
function clItem(d, t, ro) {
  const C = clState(), up = !ro;
  // Each document still needed is its own upload button, so the file is filed as that type. Once one is filed, Add another files
  // the next one as the same type (a second approval, say). One SQL already shows needs no upload, but can still take one.
  const filed = new Set(t.documents.map(x => x.doc_type));
  const chips = t.required_docs.map(dt => t.missing.includes(dt)
    ? (up ? `<button class="chip need" data-task-upload="${t.id}" data-type="${dt}" title="${esc(t.not_counted[dt]?.hint || "Upload the " + docLabel(dt))}">＋ ${esc(docLabel(dt))}</button>`
      : `<span class="chip need" title="${esc(t.not_counted[dt]?.hint || "Not filed")}">· ${esc(docLabel(dt))}</span>`)
    : filed.has(dt) ? `<span class="chip have">✓ ${esc(docLabel(dt))}</span>` : evidenceChip(t.evidence[dt])).join("");
  const more = up ? t.required_docs.filter(dt => !t.missing.includes(dt))
    .map(dt => `<button class="ghost small" data-task-upload="${t.id}" data-type="${dt}">＋ ${filed.has(dt) ? "Add another" : "Upload"} ${esc(docLabel(dt))}</button>`).join("") : "";
  // The workbook the Payroll check filed is replaced by checking a corrected one there; it can still be taken off here.
  const payroll = pageAddr("payroll", d);
  const files = t.documents.map(x => `<span class="chip file">${icon("document")}<a href="/api/documents/${x.id}/file" target="_blank">${esc(docLabel(x.doc_type))}: ${esc(x.original_name)}</a>${x.from_check ? `<span class="chip-note">· Uploaded on HR › Payroll › Workbook check</span>` : ""}
        ${!up ? "" : x.from_check ? "" : `<button class="link" data-task-upload="${t.id}" data-type="${x.doc_type}" data-replaces="${x.id}" data-name="${esc(x.original_name)}">Replace</button>`}
        ${up ? `<button class="link" data-remove-doc="${x.id}" data-name="${esc(x.original_name)}">Remove</button>` : ""}</span>`).join("") +
    t.sql_docs.map(x => `<span class="chip have" title="From SQL">SQL ${esc(x.doc_no)} · ${money(x.amount)}${x.taken_back_by ? ` · e-Invoice cancelled by ${esc(x.taken_back_by)}`
      : x.einvoice_status ? " · e-Invoice " + esc(x.einvoice_status.split(",")[0].toLowerCase()) : ""}</span>`).join("");
  const links = t.required_docs.includes("payroll") || t.documents.some(x => x.from_check) ? `<a class="pg-link small" href="${payroll}">Open the workbook check${icon("arrow")}</a>` : "";
  const hist = t.documents.filter(x => x.earlier && x.earlier.length).map(x => {
    const open = C.hist.includes(x.id), n = x.earlier.length, what = x.doc_type === "payroll" ? "workbook" : "file";
    return `<div class="cl-hist"><button type="button" class="linkish cl-hist-b" data-cl-hist="${x.id}" aria-expanded="${open}"><span class="chev${open ? " on" : ""}">${icon("chevronRight")}</span>${open ? "Hide" : "Show"} the earlier ${what}${n > 1 ? "s" : ""} (${n} replaced)</button>
      ${open ? `<ul class="cl-hist-list">${x.earlier.map(h => `<li>${icon("history")}<span><s>${esc(h.name)}</s> · ${h.check ? `checked ${esc(atTime(h.check.checked_at))}: ${esc(checkWords(h.check))}. ` : `uploaded ${esc(atTime(h.uploaded_at))}. `}Replaced ${esc(atTime(h.replaced_at))}.</span></li>`).join("")}</ul>` : ""}</div>`;
  }).join("");
  // Done when ticked, or when the records show it (auto; its box can't be unticked then). The server words what they show or
  // still lack; a tick by hand that they don't bear out says so.
  const why = t.why ? `<div class="note ${t.auto ? "ok" : t.done_at ? "warn" : ""}">${t.done_at && !t.auto ? "Ticked by hand. " : ""}${esc(t.why)}</div>` : "";
  const lock = t.auto && !t.done_at && !ro ? `<div class="note lock">${icon("lock")}Done from the records, so it can't be unticked.</div>` : "";
  const waits = t.waiting ? `<div class="note">Part of the ${monthName(t.waiting)} checklist. Shown here until that month is set up; not counted in this month or its audit pack.</div>` : "";
  const box = ro ? `disabled title="${esc(d.label)} is filed: reopen it to change the checklist."` : t.auto && !t.done_at ? `disabled title="${esc(t.why)}"` : "";
  const byHand = t.done && t.done_at && !t.auto && t.why;
  const pill = t.flag ? flagPill(t.flag) : t.done ? (byHand ? `<span class="pill warn">Ticked by hand</span>` : `<span class="pill ok">Done</span>`)
    : t.waiting ? `<span class="pill grey">${esc(monthName(t.waiting))} checklist</span>` : `<span class="pill grey">To do</span>`;
  return `<div class="task ${t.done ? "done" : ""}${t.waiting ? " waits" : ""}" id="task-${t.id}">
      <input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""} ${box} id="cl-tk-${t.id}" aria-labelledby="cl-tt-${t.id}">
      <div><div class="t" id="cl-tt-${t.id}"><label for="cl-tk-${t.id}">${esc(t.title)}</label></div>${t.detail ? `<div class="d">${esc(t.detail)}</div>` : ""}${why}${lock}${waits}
        <div class="docs">${chips}${files}${more}${up ? `<button class="ghost small" data-task-upload="${t.id}" data-type="other">＋ Other document</button>` : ""}${links}</div>${hist}</div>
      <div class="num"><span class="muted">${shortDate(t.due_date)}</span><br>${pill}</div>
    </div>`;
}

function clTabsHtml(d) {
  const counts = {};
  for (const [k] of CL_TABS) counts[k] = d.tasks.filter(t => !t.waiting && clIn(t, k)).length;
  return tabButtons(CL_TABS, clTab(), "data-cl-tab", "cl-tab", "clPanel", counts);
}
function clEmpty(d, tab) {
  return { missing: { glyph: "check", tone: "ok", title: "No documents missing", body: `Every item of ${d.label} that needs a document has it on file.` },
    open: { glyph: "check", tone: "ok", title: "Everything is done", body: `Every item of ${d.label} is ticked. Mark the month as filed when the audit pack is built.` },
    done: { glyph: "clock", tone: "mute", title: "Nothing is done yet", body: "Items tick themselves from the records, or you tick them by hand." },
    all: { glyph: "checklist", tone: "brand", title: "No checklist items this month", body: "The items come from Setup › Monthly checklist when the month is set up." } }[tab];
}
// The list: the filter, the sections (each counts its own items, done of all, before the filter), CL_STEP at a time.
function clPanelHtml(d) {
  const C = clState(), tab = clTab(), ro = !!d.closed_at, SEC = clSections(d.month);
  const rows = d.tasks.filter(t => clIn(t, tab)).map(t => ({ t, sec: clSection(t, d.month) }))
    .sort((a, b) => CL_ORDER.indexOf(a.sec) - CL_ORDER.indexOf(b.sec));
  if (!rows.length) return listEmpty(clEmpty(d, tab));
  const shown = rows.slice(0, C.shown), out = [];
  for (const key of CL_ORDER) {
    const mine = shown.filter(r => r.sec === key);
    if (!mine.length) continue;
    const all = d.tasks.filter(t => clSection(t, d.month) === key && !t.waiting), sub = SEC[key][1] + (all.length ? ` · ${all.filter(t => t.done).length} of ${all.length} done` : "");
    out.push(`<div class="cl-group" role="group" aria-labelledby="cl-sec-${key}"><div class="cl-sh"><h3 id="cl-sec-${key}">${esc(SEC[key][0])}</h3><span class="muted">${esc(sub)}</span></div>
      ${mine.map(r => clItem(d, r.t, ro)).join("")}</div>`);
  }
  const counted = rows.filter(r => !r.t.waiting).length, waiting = rows.length - counted;
  const many = rows.length > CL_STEP ? manyRows({ shown: shown.length, total: rows.length, step: CL_STEP, what: "items", attr: "data-cl-more" })
    .replace("</span>", `${waiting ? ` · ${waiting} reminder${waiting > 1 ? "s" : ""} from other months, not counted` : ""}</span>`) : "";
  return out.join("") + many;
}

async function viewChecklist(main) {
  const [d, next] = await Promise.all([api(`/api/month?entity=${state.entity}&month=${state.month}`), loadNext(state.entity)]);
  state.data = d;
  const C = clState(), e = d.entity, ro = !!d.closed_at, tab = clTab();
  if (state.mark) C.shown = Math.max(C.shown, d.tasks.length);   // a link marks items: every item shows, so none it names is on a later page
  const links = `<div id="todoBox" class="pg-todo">${todoLinks(next)}</div><a class="pg-link" href="${pageAddr("entity", d)}">${icon("payment")}Payments register for ${esc(d.label)}</a>`;
  const actions = d.set_up && !ro ? `<button class="btn" data-close-month="1">${icon("pack")}Mark month as filed</button>` : "";
  const head = pageHead(d, { glyph: "checklist", title: "Monthly checklist", links, actions });
  const filed = ro ? `<div class="banner ok filed" role="status">${icon("verified")}<div><b>${esc(d.label)} was filed on ${shortDate(d.closed_at)}</b>
      <span>This month is marked as filed, so nothing in it counts as to do on the Overview. Payments, documents and the checklist are read-only until you reopen it.</span></div>
      <button class="ghost small noprint" data-reopen-month="1">Reopen</button></div>` : "";
  const setUp = d.set_up ? "" : notSetUp(e, d.month, 0);
  if (!d.set_up && !d.tasks.length) { main.innerHTML = head + setUp; return; }
  const counted = d.tasks.filter(t => !t.waiting), doneT = counted.filter(t => t.done).length, pct = counted.length ? Math.round(doneT / counted.length * 100) : 0;
  main.innerHTML = `${head}${filed}${setUp}
    <section class="card cl-card" aria-labelledby="cl-h">
      <div class="cl-top"><div class="cl-progress"><h2 id="cl-h">Checklist</h2>
          <div class="bar ok" role="progressbar" aria-label="Checklist items done" aria-valuemin="0" aria-valuemax="${counted.length}" aria-valuenow="${doneT}"><i style="width:${pct}%"></i></div>
          <b class="cl-count">${doneT} of ${counted.length} done</b></div>
        <div role="tablist" class="segtabs noprint" id="clTabs" aria-label="Show items">${clTabsHtml(d)}</div></div>
      <p class="reg-note">Items with a lock tick themselves from the records. The rest you tick by hand; ticking one the records don’t show asks first.</p>
      <div id="clPanel" role="tabpanel" tabindex="0" aria-labelledby="cl-tab-${tab}">${clPanelHtml(d)}</div>
    </section>`;
  // Opened from Before you print, Next up or a count to fix a checklist item: it is brought into view and marked for a moment.
  const { mark } = state;
  state.mark = null;
  flash(mark?.task ? d.tasks.filter(mark.task).map(t => $(`#task-${t.id}`)) : []);
}

function clPaint() {
  const d = state.data;
  if (!d || state.view !== "checklist" || !d.tasks) return;
  const tabs = $("#clTabs"), panel = $("#clPanel");
  if (tabs) tabs.innerHTML = clTabsHtml(d);
  if (panel) { panel.innerHTML = clPanelHtml(d); panel.setAttribute?.("aria-labelledby", `cl-tab-${clTab()}`); }
}
// A filter: written in the address in place of the one before; the marks a link brought are used up.
function clPick(k, focus) {
  if (!state.data || state.view !== "checklist") return;
  const p = { ...(state.addr.params || {}) };
  delete p.mark; delete p.task;
  if (k === "all") delete p.tab; else p.tab = k;
  state.addr.params = p;
  clState().shown = CL_STEP;
  syncAddr(); clPaint();
  if (focus) $(`#cl-tab-${clTab()}`)?.focus?.();
}
function clMore() {
  const d = state.data, C = clState(), rows = d.tasks.filter(t => clIn(t, clTab())), at = C.shown;
  C.shown += CL_STEP; clPaint();
  const first = rows.sort((a, b) => CL_ORDER.indexOf(clSection(a, d.month)) - CL_ORDER.indexOf(clSection(b, d.month)))[at];
  if (first) $(`#cl-tk-${first.id}`)?.focus?.();
}
function clHist(id) {
  const C = clState();
  C.hist = C.hist.includes(id) ? C.hist.filter(x => x !== id) : [...C.hist, id];
  clPaint();
  $(`[data-cl-hist="${id}"]`)?.focus?.();
}
