"use strict";
/* ---------------- The top bar (step 0e) ----------------
   Breadcrumb (Area › Page, from core/menu.js), the company switcher, the month switcher and the account menu, as
   design/canvas/Topbar.dc.html and CompanySwitcher.dc.html draw them. The month group is in index.html (its buttons are handled in
   core/events.js); the company switcher and the account menu are drawn here, into #tbCompany and #tbUser, and again whenever the
   page is drawn, so they follow the address (Back, Forward, a refresh).
   Menus follow design/motion-keyboard-spec.md section 4: the button has aria-haspopup="menu" and aria-expanded; ArrowDown or ArrowUp on
   it, or Enter or Space (a click), opens the menu and puts the focus in it (on the chosen company, else the first item); ArrowUp and
   ArrowDown move through the items and wrap, Home and End jump, Escape closes and puts the focus back on the button, Tab closes, a click
   anywhere else closes. Letters typed move to the item that starts with them.
   The company a click picks: the same page when that company uses it (the server's pages for the company, core/menu.js), else the
   company's Overview and the toast "Switched to <code>". All companies is offered on the Overview only.
   There is no sign-in yet: the account menu is for the one person who uses this PC (what stays here, the audit trail, the theme). */
const TB = { open: null, focus: null, html: { company: null, user: null }, ta: { s: "", t: 0 } };
const TB_SLOT = { company: "#tbCompany", user: "#tbUser" };

// The Next up rows of a company (those with no company count for every company), or of all companies: {n, over}.
function tbTally(key) {
  const rows = (state.menuNext?.items || []).filter(r => key === "all" || r.entity_id == null || r.entity_id === +key);
  return { n: rows.length, over: rows.filter(r => r.state === "overdue").length, known: !!state.menuNext };
}
const tbBadge = t => !t.known ? "" : `<span class="tb-badge${t.over ? " over" : ""}">${t.over ? icon("alert") : ""}<span aria-hidden="true">${t.n}</span></span>`;
const tbSay = t => t.known ? `, ${t.n} to do${t.over ? `, ${t.over} overdue` : ""}` : "";

// Which company the bar shows: All companies (the Overview), none yet, or the one on show.
function tbScope() {
  const live = (state.meta?.entities || []).filter(isActive);
  return { live, none: !live.length, all: state.view === "overview" && !!state.addr.all, e: ent() || null };
}

function tbCompanyHtml() {
  const { live, none, all, e } = tbScope(), open = TB.open === "company";
  const text = none ? "No company yet" : all ? "All companies" : e ? e.code : "Company";
  const kind = !none && !all && e ? keptLabel(e) : "";
  const label = none ? "No company yet, open the company menu" : (all ? "All companies" : e ? `${e.code} · ${kind}, ${e.name}` : "Company") + ", change company";
  let h = `<button type="button" id="tb-mb-company" class="tb-btn tb-co" aria-haspopup="menu" aria-expanded="${open}" aria-label="${esc(label)}" data-tb-toggle="company"><span class="tb-co-code">${esc(text)}</span>`
    + (kind ? `<span class="tb-dot" aria-hidden="true">·</span><span class="tb-kind">${esc(kind)}</span>` : "") + `${icon("chevronDown")}</button>`;
  if (!open) return h;
  h += `<button type="button" class="tb-away" tabindex="-1" aria-hidden="true" data-tb-away="1"></button><div role="menu" id="tb-menu-company" aria-label="Company" class="tb-menu mn">`;
  if (none) h += `<a href="#/admin/setup/entities" role="menuitem" id="tb-mi-company-0" tabindex="-1" class="tm tb-add" data-tb-add="1" data-ta="add">${icon("plus")}<span>Add your first company</span></a>`;
  else {
    const row = (key, code, name, kindText, on, i) => { const t = tbTally(key);
      return `<button type="button" role="menuitemradio" id="tb-mi-company-${i}" class="tm tb-row${on ? " on" : ""}" aria-checked="${on}" aria-label="${esc((key === "all" ? name : `${code}, ${name}, ${kindText}`) + tbSay(t))}" tabindex="-1" data-tb-pick="${key}" data-ta="${esc(key === "all" ? "all companies" : code)}">`
        + `<span class="tb-code">${esc(code)}</span><span class="tb-names"><span class="tb-name">${esc(name)}</span>${kindText ? `<span class="tb-kindline">${esc(kindText)}</span>` : ""}</span>${tbBadge(t)}<span class="tb-tick">${on ? icon("check") : ""}</span></button>`; };
    h += `<div class="tb-menu-head" aria-hidden="true"><span>Company</span><span>Next up</span></div>`;
    let i = 0;
    if (state.view === "overview" || all) h += row("all", "All", "All companies", "", all, i++) + `<div role="separator" class="tb-sep"></div>`;
    for (const x of live) h += row(x.id, x.code, x.name, keptLabel(x), !all && !!e && x.id === e.id, i++);
    h += `<div class="tb-menu-foot">Stopped companies are not offered.</div>`;
  }
  return h + `</div>`;
}

function tbUserHtml() {
  const open = TB.open === "user", theme = (typeof window !== "undefined" && window.hrpTheme && window.hrpTheme.get()) || "auto";
  let h = `<button type="button" id="tb-mb-user" class="tb-btn tb-avatar" aria-haspopup="menu" aria-expanded="${open}" aria-label="Account menu" title="Account menu" data-tb-toggle="user">${icon("person")}</button>`;
  if (!open) return h;
  const trail = MENU_BY_PAGE["admin/audit-trail"], opt = ([k, label, glyph], i) => `<button type="button" id="tb-mi-user-${i + 1}" class="tm tb-seg-btn" tabindex="-1" data-theme-set="${k}" data-ta="${label.toLowerCase()}" aria-pressed="${theme === k}">${icon(glyph)}${label}</button>`;
  h += `<button type="button" class="tb-away" tabindex="-1" aria-hidden="true" data-tb-away="1"></button><div role="menu" id="tb-menu-user" aria-label="Account" class="tb-menu tb-menu-user mn">`
    + `<div class="tb-who"><b>This PC</b><span>Records stay on this PC. Nothing is sent anywhere.</span></div>`
    + `<a href="${esc(menuHref(trail))}" role="menuitem" id="tb-mi-user-0" tabindex="-1" class="tm" data-tb-go="admin/audit-trail" data-ta="audit trail">${icon("trail")}<span>Audit trail</span></a>`
    + `<div class="tb-theme"><span id="tb-theme-label" class="tb-theme-label">Theme</span><div role="group" aria-labelledby="tb-theme-label" class="seg">${[["auto", "Auto", "auto"], ["light", "Light", "sun"], ["dark", "Dark", "moon"]].map(opt).join("")}</div></div></div>`;
  return h;
}

// The month group and the heading, then the two menus; a menu is drawn again only when its HTML changed, so the focus stays where it is.
function renderTopbar() {
  if (!state.meta) return;
  const lbl = $("#monthLabel"), cur = $("#thisMonth"), crumb = $("#pageTitle");
  if (lbl) lbl.textContent = monthName(state.month);
  if (cur) { let now = false; try { now = state.month === currentCycle(); } catch { now = false; } cur.hidden = now; }
  if (crumb) { const h = menuCrumbHtml(); if (crumb._html !== h) { crumb.innerHTML = h; crumb._html = h; } }
  const html = { company: tbCompanyHtml(), user: tbUserHtml() };
  for (const name of ["company", "user"]) {
    const el = $(TB_SLOT[name]);
    if (!el || TB.html[name] === html[name]) continue;
    const a = document.activeElement, had = a && el.contains && el.contains(a) ? a.id : null;
    el.innerHTML = html[name]; TB.html[name] = html[name];
    if (had && !TB.focus) { const back = document.getElementById ? document.getElementById(had) : $("#" + had); back?.focus?.({ preventScroll: true }); }
  }
  if (TB.focus) { const f = TB.focus; TB.focus = null; tbFocus(f); }
}
function tbFocus(where) {
  const name = TB.open || where.slice(where.indexOf(":") + 1);  // a closed menu: the button it came from
  if (where === "button" || where.startsWith("button:")) { $(name === "user" ? "#tb-mb-user" : "#tb-mb-company")?.focus?.({ preventScroll: true }); return; }
  const box = $(TB.open === "user" ? "#tb-menu-user" : "#tb-menu-company"), items = box ? box.querySelectorAll(".tm") : [];
  const el = where === "last" ? items[items.length - 1] : where === "chosen" ? box?.querySelector('.tm[aria-checked="true"]') || items[0] : items[0];
  el?.focus?.({ preventScroll: true });
}
// Opens a menu (closing the other) and puts the focus in it, or closes the open one with the focus back on its button.
function tbSet(open, where) {
  const was = TB.open;
  TB.open = open;
  TB.focus = open ? where || "chosen" : where === "none" ? null : "button:" + was;
  if (open) menuNextEnsure();  // the to-do counts in the company menu
  renderTopbar();
}
function tbToggle(name, where) { TB.open === name ? tbSet(null) : tbSet(name, where); }
function tbClose(back) { if (TB.open) tbSet(null, back === false ? "none" : undefined); }

// The place a company is picked for: All companies (the Overview), the same page where the company uses it, else its Overview.
// gone: the name of the page it does not use, for the toast.
function tbPlace(key) {
  if (key === "all") return { place: { ...homePlace(), month: state.month }, gone: null, e: null };
  const e = state.meta.entities.find(x => x.id === +key), v = state.view, hit = MENU_BY_VIEW[v];
  if (!e) return null;
  // Setup's Matching words are for companies Kept in SQL Account: from them, a company Kept here lands on its Overview with the toast.
  if (v === "setup" && !e.uses_sql && setupNeedsSql(state.setup.kind)) return { place: { view: "overview", entity: e.id, month: state.month, sub: null, id: null, params: {} }, gone: setupGroupOf(state.setup.kind) || "Matching words", view: v, e, plural: true };
  if (hit && !menuVisible(e).has(hit.item.page)) return { place: { view: "overview", entity: e.id, month: state.month, sub: null, id: null, params: {} }, gone: PAGE_RULES[v]?.name || hit.item.label, view: v, e };
  const p = placeFromState();
  p.entity = e.id; p.id = null;
  p.params = v === "books" ? { tab: p.params.tab } : v === "parties" && p.params.tab ? { tab: p.params.tab } : {};  // the old company's dates, account and filters stay behind
  return { place: p, gone: null, e };
}
async function tbPick(key) {
  tbClose(true);
  const scope = tbScope();
  if (key === "all" ? scope.all : !scope.all && scope.e && scope.e.id === +key) return;
  const r = tbPlace(key);
  if (!r) return;
  if (await navigate(r.place, { fresh: true }) && r.gone) switchedNote(r.gone, r.e, r.plural ?? PAGE_RULES[r.view]?.plural);
}
// No company yet: Setup > Companies, with its add form open.
async function tbAddCompany() {
  tbClose(false);
  state.setup.kind = "entities";
  if (await go("setup")) await openSetup("entities", "new");
}

document.addEventListener("keydown", ev => {
  const t = ev.target, k = ev.key;
  if (!t || !t.closest) return;
  const btn = t.closest("[data-tb-toggle]");
  if (btn && (k === "ArrowDown" || k === "ArrowUp")) {  // on the button: open and move in; with the menu already open, move in
    ev.preventDefault();
    const name = btn.getAttribute("data-tb-toggle");
    if (TB.open === name) tbFocus(k === "ArrowUp" ? "last" : "chosen"); else tbSet(name, k === "ArrowUp" ? "last" : "chosen");
    return;
  }
  const box = t.closest(".tb-menu");
  if (!box) return;
  const items = Array.from(box.querySelectorAll(".tm")), n = items.length, i = items.indexOf(t.closest(".tm"));
  let to = -1;
  if (k === "ArrowDown") to = (i + 1) % n;
  else if (k === "ArrowUp") to = (i - 1 + n) % n;
  else if (k === "Home") to = 0;
  else if (k === "End") to = n - 1;
  else if (k === "Escape") { ev.preventDefault(); ev.stopPropagation(); tbClose(true); return; }
  else if (k === "Tab") { tbClose(false); return; }
  else if (k === " " && i >= 0 && String(items[i].tagName).toLowerCase() === "a") { ev.preventDefault(); items[i].click(); return; }  // a link: Space picks it, as Enter does
  else if (k && k.length === 1 && k !== " " && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {  // type-ahead: letters typed within 0.6 s make a prefix
    const now = Date.now(), s = (now - TB.ta.t < 600 ? TB.ta.s : "") + k.toLowerCase(), word = el => String(el.getAttribute("data-ta") || el.textContent || "").trim().toLowerCase();
    TB.ta = { s, t: now };
    to = items.findIndex(el => word(el) === s);  // a code typed in full wins (a short code typed in full beats a longer one that starts with it)
    for (let j = 1; to < 0 && j <= n; j++) { const at = (i + j + n) % n; if (word(items[at]).startsWith(s)) to = at; }
    if (to < 0) return;
  } else return;
  ev.preventDefault();
  if (n && items[to]) items[to].focus();
});
