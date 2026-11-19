"use strict";
/* ---------------- The side menu (step 0e) ----------------
   MENU is the one place the menu is defined: five areas, and in each the items in the order design/canvas/Sidebar.dc.html draws
   them. An item's page is the page key the server gives each company in /api/meta (entities[].pages, hrp/pages.py); its view is
   the page's key in ROUTES (core/router.js), where its address is. What a company sees is MENU and its pages: a company Kept
   in SQL Account has SQL import, one Kept here has the Kept here group (Sales, Purchases, Journals, Period close) instead.
   On the Overview of All companies the menu follows the first company in use that is Kept in SQL Account (else the first in
   use); with no company it is the same menu with no numbers. Calendar and reminders is a tab of Staff, Salary advances a tab of
   Claims and advances: neither is an item. Users and access comes with sign-in (slice 16).
   The number on an area is how many Next up rows belong to that area (row.area, hrp/nextup.py) for the company on show (All:
   every company), red with an alert mark when one of them is overdue. Overview carries the total. */
const MENU = [
  { key: "overview", label: "Overview", head: false, items: [{ page: "overview", view: "overview", label: "Overview", glyph: "overview" }] },
  { key: "hr", label: "HR", items: [
    { page: "hr/staff", view: "staff", label: "Staff", glyph: "staff" },
    { page: "hr/leave", view: "leave", label: "Leave", glyph: "leave" },
    { page: "hr/claims", view: "claims", label: "Claims and advances", glyph: "claim" },
    { page: "hr/payroll", view: "payroll", label: "Payroll", glyph: "payroll" }] },
  { key: "payments", label: "Payments", items: [
    { page: "payments/approvals", view: "approvals", label: "Approvals", glyph: "approval" },
    { page: "payments/to-pay", view: "topay", label: "To pay", glyph: "toPay" },
    { page: "payments/register", view: "entity", label: "Payments register", glyph: "payment" },
    { page: "payments/checklist", view: "checklist", label: "Monthly checklist", glyph: "checklist" },
    { page: "payments/budget", view: "budget", label: "Budget", glyph: "budget" },
    { page: "payments/recurring", view: "payees", label: "Recurring", glyph: "recurring" }] },
  { key: "accounting", label: "Accounting", items: [
    { page: "accounting/bank", view: "bank", label: "Bank and reconciliation", glyph: "bank" },
    { page: "accounting/sql", view: "sql", label: "SQL import", glyph: "database" },
    { page: "accounting/einvoices", view: "einvoices", label: "e-Invoices", glyph: "verified" },
    { page: "accounting/books", view: "books", label: "Books", glyph: "books" },
    { page: "accounting/parties", view: "parties", label: "Customers and suppliers", glyph: "users" },
    { page: "accounting/statutory", view: "statutory", label: "Statutory payables", glyph: "statutory" }],
    sub: { label: "Kept here", items: [
      { page: "accounting/sales", view: "sales", label: "Sales", glyph: "receipt" },
      { page: "accounting/purchases", view: "purchases", label: "Purchases", glyph: "inbox" },
      { page: "accounting/journals", view: "journals", label: "Journals", glyph: "sheet" },
      { page: "accounting/period-close", view: "close", label: "Period close", glyph: "lock" }] } },
  { key: "admin", label: "Admin", items: [
    { page: "admin/setup", view: "setup", label: "Setup", glyph: "sliders" },
    { page: "admin/audit-pack", view: "audit", label: "Audit pack", glyph: "pack" },
    { page: "admin/audit-trail", view: "trail", label: "Audit trail", glyph: "trail" },
    { page: "admin/backup", view: "settings", label: "Backup", glyph: "vault" }] },
];
const menuItems = g => [...g.items, ...(g.sub ? g.sub.items : [])];
const MENU_ALL = MENU.flatMap(menuItems);
const MENU_BY_PAGE = Object.fromEntries(MENU_ALL.map(i => [i.page, i]));
// The page on show lights its item (an item marked alias shares another's page and never lights).
const MENU_BY_VIEW = {};
for (const g of MENU) for (const i of menuItems(g)) if (!i.alias && !(i.view in MENU_BY_VIEW)) MENU_BY_VIEW[i.view] = { item: i, area: g };
const MENU_HERE = ["accounting/sales", "accounting/purchases", "accounting/journals", "accounting/period-close"];  // a server that gives no pages: the Kept here group is for companies kept here

// Whose pages the menu shows: the company on show, or on the Overview of All companies the first in use that is Kept in SQL Account.
function menuScope() {
  const live = (state.meta?.entities || []).filter(isActive), all = state.view === "overview" && !!state.addr.all;
  return { all, e: all ? live.find(x => x.uses_sql) || live[0] || null : ent() || null };
}
function menuVisible(e) {
  if (e && Array.isArray(e.pages)) return new Set(e.pages);
  const here = !!e && !e.uses_sql;
  return new Set(MENU_ALL.map(i => i.page).filter(p => here ? p !== "accounting/sql" : !MENU_HERE.includes(p)));
}

// Where an item goes: its page for the company on show, or on the Overview of All companies (or for a page the company does not
// use) the first company in use that does. null when there is no company to give an address.
function menuPlace(item) {
  const R = ROUTES[item.view];
  if (!R) return null;
  let id = null;
  if (R.company === "one") {
    const rule = PAGE_RULES[item.view], cur = ent();
    id = state.entity ?? firstEntityId();
    if (rule && !(cur && rule.used(cur))) { const o = state.meta.entities.find(x => isActive(x) && rule.used(x)); if (o) id = o.id; }
    if (id == null) return null;  // no company yet: a company's page has no address
  }
  return goPlace(item.view, id);
}
function menuHref(item) {
  const a = addrOf(menuPlace(item));
  return a ? (item.alias ? a.replace(/\/register(?=[\/?]|$)/, "/" + item.alias) : a) : "#/";
}
// A click on an item: its address is written and the page drawn, as go() does. A modified click or a middle click is the browser's own (a new tab).
function menuGo(page) {
  const item = MENU_BY_PAGE[page], place = item && (menuPlace(item) || (ROUTES[item.view]?.company === "one" ? homePlace() : null));  // no company yet: the Overview, where its href (#/) points
  return place ? navigate(place, { fresh: true }) : Promise.resolve(false);
}

// The Next up rows of every company, kept for the numbers: loaded with the Overview's card (core/next.js) or here, at most once a minute.
function menuNextEnsure(force) {
  const M = state.menuNext;
  if (menuNextEnsure.busy || (M && !force && Date.now() - M.at < 60000)) return;
  menuNextEnsure.busy = true;
  loadNext(null).then(res => { state.menuNext = { items: res.error ? M?.items || [] : res.items, at: Date.now() }; renderNav(); }).finally(() => { menuNextEnsure.busy = false; });
}
// {area: {n, over}} and pages: {page key: {n, over}} for the company on show (All: every company); Next up rows with no company (the
// backup) count for every company. overview: all of them. A row counts on its menu item (row.page) and on that item's area (row.area);
// the area's number is drawn only while the area is folded, so a number is never counted twice on screen.
function menuCounts() {
  const { all } = menuScope(), out = { overview: { n: 0, over: 0 }, pages: {} };
  for (const g of MENU) out[g.key] = { n: 0, over: 0 };
  const add = (c, r) => { c.n++; if (r.state === "overdue") c.over++; };
  for (const r of state.menuNext?.items || []) {
    if (!out[r.area] || r.area === "overview" || !(all || r.entity_id == null || r.entity_id === state.entity)) continue;
    add(out[r.area], r); add(out.overview, r);
    if (r.page && MENU_BY_PAGE[r.page] && r.page !== "overview") add(out.pages[r.page] || (out.pages[r.page] = { n: 0, over: 0 }), r);
  }
  return out;
}
const menuBadge = c => !c || !c.n ? "" : `<span class="nbadge${c.over ? " over" : ""}">${c.over ? icon("alert") : ""}<span aria-hidden="true">${c.n}</span><span class="sr-only">, ${c.n} to do${c.over ? `, ${c.over} overdue` : ""}</span></span>`;

// Folded groups are kept in this browser (a convenience: it draws open when it can't be read).
function menuFolded() {
  if (!state.menuFold) { try { state.menuFold = JSON.parse(localStorage.getItem("hrp-menu-fold") || "{}") || {}; } catch { state.menuFold = {}; } }
  return state.menuFold;
}
// Draws the menu into the nav. The same HTML is not written again, and when it is, the focus goes back to the item that had it (a keyboard
// user is not thrown out when the numbers arrive or a page changes).
function menuPaint(nav) {
  const html = menuHtml();
  if (nav._menuHtml === html) return;
  const a = typeof document !== "undefined" ? document.activeElement : null, on = a && nav.contains && nav.contains(a) && a.closest ? a.closest("[data-menu],[data-menu-fold]") : null;
  const sel = on ? (on.getAttribute("data-menu") != null ? `[data-menu="${on.getAttribute("data-menu")}"]` : `[data-menu-fold="${on.getAttribute("data-menu-fold")}"]`) : null;
  nav.innerHTML = html; nav._menuHtml = html;
  if (sel) nav.querySelector(sel)?.focus?.({ preventScroll: true });
}
function menuFoldToggle(key) {
  const F = menuFolded();
  F[key] = !F[key];
  try { localStorage.setItem("hrp-menu-fold", JSON.stringify(F)); } catch { /* not kept */ }
  renderNav();
  $(`[data-menu-fold="${key}"]`)?.focus?.();
}

// The menu as HTML: groups with their headings (Overview has none), items as links with their address, the page on show marked
// aria-current, a number on each item that has Next up rows (the area's number shows on its heading only while the area is folded).
function menuHtml() {
  const { e } = menuScope(), vis = menuVisible(e), counts = menuCounts(), cur = MENU_BY_VIEW[state.view], fold = menuFolded(), out = [];
  const link = i => `<a class="nv${cur && cur.item === i ? " on" : ""}" href="${esc(menuHref(i))}" data-menu="${esc(i.page)}"${cur && cur.item === i ? ` aria-current="page"` : ""}>${icon(i.glyph)}<span>${esc(i.label)}</span>${menuBadge(i.page === "overview" ? counts.overview : counts.pages[i.page])}</a>`;
  for (const g of MENU) {
    const items = g.items.filter(i => vis.has(i.page)), sub = g.sub ? g.sub.items.filter(i => vis.has(i.page)) : [];
    if (!items.length && !sub.length) continue;
    if (g.head === false) { out.push(`<div class="nav-group" role="group" aria-label="${esc(g.label)}"><div class="nav-list">${items.map(link).join("")}</div></div>`); continue; }
    const shut = !!fold[g.key] && !(cur && cur.area === g);  // the group that holds the page on show stays open
    out.push(`<div class="nav-group" role="group" aria-label="${esc(g.label)}"><button type="button" class="nav-head" data-menu-fold="${g.key}" aria-expanded="${!shut}"><span>${esc(g.label)}</span>${shut ? menuBadge(counts[g.key]) : ""}<span class="nav-chev" aria-hidden="true">${icon("chevronRight")}</span></button>`
      + `<div class="nav-list"${shut ? " hidden" : ""}>${items.map(link).join("")}${sub.length ? `<div class="nav-sub" role="group" aria-label="${esc(g.sub.label)}"><span class="nav-sub-label" aria-hidden="true">${esc(g.sub.label)}</span>${sub.map(link).join("")}</div>` : ""}</div></div>`);
  }
  return out.join("");
}

// The heading above the page: area, then page (Setup also names its section). The parts, then the text ("Area › Page") and the HTML
// the top bar draws: the area in the quiet tone, a chevron, the page in bold and aria-current (Setup's section is the bold one).
function menuCrumbParts() {
  if (state.view === "setup") return ["Admin", "Setup", ...(setupSpec() ? [sectionLabel(setupSpec())] : [])];
  const c = MENU_BY_VIEW[state.view];
  return !c ? [] : c.area.head === false ? [c.item.label] : [c.area.label, c.item.label];
}
const menuCrumb = () => menuCrumbParts().join(" › ");
function menuCrumbHtml() {
  const parts = menuCrumbParts(), last = parts.length - 1;
  return parts.map((t, i) => (i ? icon("chevronRight") : "") + `<span class="${i === last ? "crumb-page" : i === 0 ? "crumb-area" : "crumb-page sub"}"${i === last ? ` aria-current="page"` : ""}>${esc(t)}</span>`).join("");
}
