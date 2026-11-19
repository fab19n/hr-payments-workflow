"use strict";
/* ---------------- Go, and Next up ---------------- */
// Go: opens where something is done, for its company and month whichever are showing: the payment's drawer, a checklist
// item on the month page, the month page with what a count stands for marked, the Bank statements page on an account
// (only the lines to explain, for filter to_explain), or another page: the Budget page as at the day a row counts (as_at)
// when it has one. The page starts at the top; what is brought into view once it is drawn (a marked item, the
// statement) goes after that.
// The place goes in the address (core/router.js linkPlace and applyPlace hold what each of these keys does: the company and
// month, the payment to open as the id, and mark, pay, task, as_at, filter, account, tab, from and to as the filters).
function goTo(g) {
  const place = linkPlace(g);
  return place ? navigate(place, { link: true }) : Promise.resolve(false);
}

// What a count stands for on the month page: the checklist items and payments to mark (a row of Next up names its own,
// task_ids and payment_ids). A word that is none of these is a payment's (not_on_statement, past_legal...).
const MARKS = {
  overdue_tasks: { task: t => t.flag?.code === "overdue" },
  due_today_tasks: { task: t => t.flag?.code === "due_today" },
  part_paid: { pay: p => p.direction !== "in" && p.status === "part_paid" },
  "in-part_paid": { pay: p => p.direction === "in" && p.status === "part_paid" },
};
// A count of money received has in- in front of its word, so it marks the receipts alone.
const markFor = key => MARKS[key] || (key.startsWith("in-") ? { pay: p => p.direction === "in" && p.flag?.code === key.slice(3) }
  : { pay: p => p.direction !== "in" && p.flag?.code === key });

// Brings the first of these into view and marks them all for a moment.
function flash(els) {
  els = els.filter(Boolean);
  if (!els.length) return;
  for (const x of els) x.classList.add("focus");
  els[0].scrollIntoView?.({ block: "center" });
  setTimeout(() => els.forEach(x => x.classList.remove("focus")), 3000);
}

// A count pill on the Overview goes to what it counts, for its company and the month on show: the Payments register on its tab
// (Not in SQL; Needs attention for part paid) with the payments marked, the Monthly checklist with the items marked or on its Missing
// documents filter (docs_missing: checklist items whose documents are missing), the Bank page's lines to explain, or the Audit pack.
function pillGo(kind, entity) {
  const g = { entity_id: entity, month: state.month };
  if (kind === "paid_missing") return goTo({ ...g, view: "audit" });
  if (kind === "unmatched_lines") return goTo({ ...g, view: "bank", filter: "to_explain" });
  if (kind === "not_in_sql") return goTo({ ...g, view: "entity", tab: "nosql" });
  if (kind === "docs_missing") return goTo({ ...g, view: "checklist", tab: "missing" });
  if (MARKS[kind]?.task) return goTo({ ...g, view: "checklist", filter: kind });
  if (kind === "part_paid" || kind === "in-part_paid") return goTo({ ...g, view: "entity", filter: kind, tab: "attention" });
  return goTo({ ...g, view: "entity", filter: kind });
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dayLabel = iso => { const [y, m, d] = iso.split("-").map(Number); return `${WEEKDAYS[new Date(y, m - 1, d).getDay()]} ${d} ${MONTHS[m - 1]}`; };
// The list is for one company (its id) or both. A list that can't be read says so, and the page still shows.
const loadNext = scope => api(`/api/next${scope ? `?entity_id=${scope}` : ""}`).catch(e => ({ error: e.message }));
const nextScope = () => state.view === "entity" || state.view === "checklist" ? state.entity : null;
const DUE_WORD = { overdue: "Overdue", today: "Today", soon: "Due", later: "Due" };
const DUE_TONE = { overdue: "bad", today: "warn", soon: "warn", later: "grey" };
const dueTag = r => r.due ? `<span class="pill ${DUE_TONE[r.state]}">${DUE_WORD[r.state]} ${shortDate(r.due)}</span>` : "";
// The company is named after a sentence that doesn't name it already.
const forCompany = r => r.entity && !new RegExp(`\\b${r.entity}\\b`).test(r.text) ? ` <span class="muted">· ${esc(r.entity)}</span>` : "";

function nextRow(r) {
  return `<div class="next-row"><div>${esc(r.text)}${forCompany(r)}</div><div class="next-due">${dueTag(r)}</div>
    <div class="row next-act">${r.rule === 13 ? `<button class="btn small" data-next-backup="1">Open backup</button>` : ""}
    <button class="ghost small" data-next-go="${esc(r.key)}" aria-label="Go: ${esc(r.text)}">Go</button></div></div>`;
}

// The Next up card: 7 rows (3 on a company's page) and Show all, the older months still open as one muted line. Those
// months are not read for the list, so with any open it says nothing is due in the recent ones, never All caught up.
function nextCard(res, scope) {
  if (res.error) return `<div class="card noprint"><h2>Next up</h2><div class="note">Couldn't work out what to do next: ${esc(res.error)}</div></div>`;
  state.next = new Map(res.items.map(r => [r.key, r]));
  if (!scope) state.menuNext = { items: res.items, at: Date.now() };  // the side menu's numbers count these rows (core/menu.js)
  const limit = scope ? 3 : 7, many = !scope && state.meta.entities.length > 1;
  const all = state.nextAll[scope || 0];  // Show all is kept for each list: the Overview's and each company's
  const rows = (all ? res.items : res.items.slice(0, limit)).map(nextRow).join("");
  const more = res.items.length > limit ? `<div><button class="link" data-next-all="1">${all ? "Show fewer" : `Show all ${res.items.length}`}</button></div>` : "";
  const older = res.older_open_months.map(o => `<button class="link" data-older="${o.entity_id} ${o.month}">${esc(o.label)}${many
    ? ` (${esc(state.meta.entities.find(e => e.id === o.entity_id)?.code)})` : ""}</button>`).join(", ");
  return `<div class="card noprint"><h2>Next up <span class="muted">· ${esc(dayLabel(res.today))}</span></h2>
    ${res.items.length ? `<div class="next-list">${rows}</div>${more}`
      : `<div class="banner ok"><b>${older ? "Nothing due in the recent months" : "All caught up"}</b>${res.next_due ? `<span>Next due ${shortDate(res.next_due.due)} · ${esc(res.next_due.text)}</span>` : ""}</div>`}
    ${older ? `<div class="note">Older months still open: ${older}</div>` : ""}</div>`;
}

// The Payments register and the Monthly checklist have no Next up card (slice 2): a link to the company's to-dos on the Overview
// stands for it, with how many there are and how many are overdue, and the company's older months still open as one muted line.
function todoLinks(res) {
  const e = ent();
  if (!e) return "";
  const href = esc(addrOf({ view: "overview", entity: e.id, month: state.month }) || "#/"), code = esc(e.code);
  if (res.error) return `<a class="pg-link" href="${href}">${icon("sparkflag")}To-dos for ${code} on the Overview</a>`;
  const n = res.items.length, over = res.items.filter(r => r.state === "overdue").length;
  const older = (res.older_open_months || []).map(o => `<button class="link" data-older="${o.entity_id} ${o.month}">${esc(o.label)}</button>`).join(", ");
  return `<a class="pg-link" href="${href}" id="todoLink">${icon("sparkflag")}${n ? `${n} to-do${n === 1 ? "" : "s"} for ${code} on the Overview${over ? `, ${over} overdue` : ""}`
    : `Nothing to do for ${code} on the Overview`}</a>${older ? `<div class="note">Older months still open: ${older}</div>` : ""}`;
}

// Reads the list again and redraws the card alone (after a backup, or when the tab comes back into view), or on the register and
// the checklist the to-dos link. With keepOnError, a list that can't be read leaves it as it was.
async function refreshNext(keepOnError) {
  if (!["overview", "entity", "checklist"].includes(state.view)) return;
  const scope = nextScope(), res = await loadNext(scope);
  if (scope !== nextScope() || (keepOnError && res.error)) return;
  const box = $("#nextUp"), todo = $("#todoBox");
  if (box && !scope) { box.innerHTML = nextCard(res, scope); renderNav(); }
  else if (todo && scope) todo.innerHTML = todoLinks(res);
}

