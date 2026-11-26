"use strict";
/* ---------------- Accounting › Books ---------------- */
// The books worked out here from the openings SQL printed and the account lines kept: the trial balance (checked against
// SQL's own) and the general ledger. Read-only: nothing on this page changes the records.
const rmPlain = n => n == null ? "—" : (n / 100).toLocaleString("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const rmCell = n => n ? rmPlain(n) : "";
const drCr = n => n == null ? "—" : n === 0 ? "0.00" : `${rmPlain(Math.abs(n))} ${n > 0 ? "Dr" : "Cr"}`;
const BOOK_NAMES = { bank: "Bank", general: "General", sales: "Sales", purchase: "Purchase", other: "Other" };

async function viewBooks(main) {
  const e = ent(), B = state.books;
  if (!e) { main.innerHTML = `<div class="card"><div class="note">Add a company in Setup first.</div></div>`; return; }
  if (B.entity !== state.entity) Object.assign(B, { entity: state.entity, from: null, to: null, account: null, q: "", party: null });
  main.innerHTML = `${entityPicker()}
    <div class="card" id="booksView"><h1>Books · ${esc(e.code)}</h1>
      <div class="note">${e.uses_sql
        ? "The books worked out here: each account starts from the opening balance SQL printed (its trial balance or ledger, kept when they were fetched) and adds the account lines of SQL's GL Journal of Transaction."
        : "The books kept here for this company: each account starts from its opening balance entered here (or from nothing) and adds the account lines entered here."} Profit and loss start again at the financial year start${e.fy_start ? ` (1 ${esc(monthName("2000-" + String(e.fy_start).padStart(2, "0")).split(" ")[0])})` : " (January, as it isn't set in Setup › Companies)"}. Nothing on this page can be changed${e.uses_sql ? "; it follows what is fetched from SQL" : ""}.</div>
      <div class="row" style="align-items:flex-end">
        <label class="field"><span>From</span><input type="date" id="bkFrom" value="${esc(B.from || "")}"></label>
        <label class="field"><span>To</span><input type="date" id="bkTo" value="${esc(B.to || "")}"></label>
        <button class="btn" type="button" data-bk-show="1">Show</button>
        <button class="ghost small" type="button" data-bk-year="1">This financial year to date</button>
        <a class="ghost small" id="bkExcel" hidden title="This report as an Excel file, for the dates and options shown">Excel</a>
      </div>
      <div class="row"><div class="seg" role="group" aria-label="Report">
        <button type="button" data-bk-tab="tb" aria-pressed="${B.tab === "tb"}">Trial balance</button>
        <button type="button" data-bk-tab="ledger" aria-pressed="${B.tab === "ledger"}">General ledger</button>
        <button type="button" data-bk-tab="pl" aria-pressed="${B.tab === "pl"}">Profit and loss</button>
        <button type="button" data-bk-tab="bs" aria-pressed="${B.tab === "bs"}">Balance sheet</button>
        <button type="button" data-bk-tab="parties" aria-pressed="${B.tab === "parties"}">Customers and suppliers</button>
        <button type="button" data-bk-tab="statutory" aria-pressed="${B.tab === "statutory"}">Statutory</button></div></div>
      <div id="booksBody"><div class="note">Loading…</div></div></div>`;
  const view = $("#booksView");
  view.addEventListener("click", ev => {
    const t = ev.target.closest("button"); if (!t) return;
    const ds = t.dataset;
    if (ds.bkTab) { B.tab = ds.bkTab; B.party = null; syncAddr(); view.querySelectorAll("[data-bk-tab]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.bkTab === B.tab))); return drawBooks(); }
    if (ds.bkShow) { B.from = $("#bkFrom").value || null; B.to = $("#bkTo").value || null; syncAddr(); return drawBooks(); }
    if (ds.bkYear) { B.from = B.to = null; syncAddr(); return drawBooks(); }
    if (ds.bkAcct) { B.tab = "ledger"; B.account = ds.bkAcct; syncAddr(); view.querySelectorAll("[data-bk-tab]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.bkTab === "ledger"))); return drawBooks(); }
    if (ds.bkAll) { B.account = null; return drawBooks(); }
    if (ds.bkDoc) return booksDoc(t);
    if (ds.bkSide) { B.side = ds.bkSide; B.party = null; syncAddr(); return drawBooks(); }
    if (ds.bkParty) { B.party = ds.bkParty; return drawBooks(); }
    if (ds.bkPartyBack) { B.party = null; return drawBooks(); }
    if (ds.stUse) return statutoryUse(t);
    if (ds.stPay) { const [id, month] = ds.stPay.split(" "); return goTo({ view: "entity", entity_id: state.entity, month, payment_id: +id }); }
    if (ds.stSetup) { state.setup.kind = "statutory_accounts"; return go("setup"); }
  });
  view.addEventListener("input", ev => {
    if (ev.target.id === "bkSearch") { B.q = ev.target.value; paintTbRows(); }
  });
  view.addEventListener("change", ev => {
    const t = ev.target;
    if (t.id === "bkRollup") { B.rollup = t.checked; return drawBooks(); }
    if (t.id === "bkMonths") { B.months = t.checked; return drawBooks(); }
    if (t.id === "bkAcct") {
      const v = t.value.trim().toUpperCase(), code = v.split(/\s+/)[0];
      if (!v) { B.account = null; return drawBooks(); }
      if ((B.choices || []).some(c => c.code === code)) { B.account = code; return drawBooks(); }
    }
  });
  await drawBooks();
}

const booksQuery = () => { const B = state.books; return `entity=${state.entity}${B.from ? `&from=${B.from}` : ""}${B.to ? `&to=${B.to}` : ""}`; };

// The report on show in the frame viewBooks wrote: a part of its own (core/page.js), so of two tabs or dates picked quickly only the last
// one's answer is used. saved: it reads back a change that was kept, so a failure is said that way, in the report's place.
function drawBooks({ saved = false } = {}) { return pageDraw("books", page => booksDraw(page, saved || page.saved)); }
async function booksDraw(page, saved) {
  const B = state.books, body = $("#booksBody");
  if (!body) return;
  body.innerHTML = `<div class="note">Loading…</div>`;
  booksExcelLink(true);
  try {
    if (B.tab === "statutory") {
      const d = await page.read(api(`/api/statutory?${booksQuery()}`));
      if (!$("#booksBody")) return;
      body.innerHTML = statutoryHtml(d);
    } else if (B.tab === "parties") {
      const d = await page.read(B.party ? api(`/api/books/party?${booksQuery()}&code=${encodeURIComponent(B.party)}`)
        : api(`/api/books/parties?${booksQuery()}&side=${B.side}`));
      if (!$("#booksBody")) return;
      B.from = d.from; B.to = d.to;
      body.innerHTML = B.party ? partyHtml(d) : partiesHtml(d);
    } else if (B.tab === "pl") {
      const d = await page.read(api(`/api/books/profit-and-loss?${booksQuery()}&columns=${B.months ? "month" : "total"}`));
      if (!$("#booksBody")) return;
      B.from = d.from; B.to = d.to;
      body.innerHTML = plHtml(d);
    } else if (B.tab === "bs") {
      const d = await page.read(api(`/api/books/balance-sheet?entity=${state.entity}${B.to ? `&as_at=${B.to}` : ""}`));
      if (!$("#booksBody")) return;
      B.to = d.as_at;
      body.innerHTML = bsHtml(d);
    } else if (B.tab === "tb") {
      const d = await page.read(api(`/api/books/trial-balance?${booksQuery()}&rollup=${B.rollup ? 1 : 0}`));
      if (!$("#booksBody")) return;
      B.from = d.from; B.to = d.to; B.tb = d;
      body.innerHTML = tbHtml(d); paintTbRows();
    } else {
      const d = await page.read(api(`/api/books/ledger?${booksQuery()}${B.account ? `&account=${encodeURIComponent(B.account)}` : ""}`));
      if (!$("#booksBody")) return;
      B.from = d.from; B.to = d.to; B.choices = d.choices;
      body.innerHTML = ledgerHtml(d);
    }
    $("#bkFrom").value = B.from || ""; $("#bkTo").value = B.to || "";
    booksExcelLink();
  } catch (e) {
    page.check();
    body.innerHTML = saved ? errorState({ body: SAVED_NOT_READ, retry: "saved", nothingChanged: false }) : `<div class="note warn-text">${esc(e.message)}</div>`;
    booksExcelLink(true);
    return !saved;  // false: the words that it was saved are on the page (core/saved.js)
  }
}

// The Excel button: the report shown, for the dates and options on the screen (none for one customer's or supplier's
// statement).
function booksExcelLink(off) {
  const a = $("#bkExcel"), B = state.books;
  if (!a) return;
  const q = `entity_id=${state.entity}${B.from ? `&from=${B.from}` : ""}${B.to ? `&to=${B.to}` : ""}`;
  const href = off || B.party ? null : {
    tb: `trial-balance.xlsx?${q}&rollup=${B.rollup ? 1 : 0}`,
    ledger: `ledger.xlsx?${q}${B.account ? `&account=${encodeURIComponent(B.account)}` : ""}`,
    pl: `profit-and-loss.xlsx?${q}&columns=${B.months ? "month" : "total"}`,
    bs: `balance-sheet.xlsx?entity_id=${state.entity}${B.to ? `&as_at=${B.to}` : ""}`,
    parties: `customers-and-suppliers.xlsx?${q}&side=${B.side}`,
    statutory: `statutory-payables.xlsx?${q}`,
  }[B.tab];
  a.hidden = !href;
  if (href) a.href = `/api/export/books/${href}`; else a.removeAttribute("href");
}

// The banner of the check against SQL's own trial balance: green when it agrees, the differences when not, grey when
// it couldn't run (and why).
function sqlCheckBanner(ch) {
  if (!ch) return "";
  if (ch.outcome === "ok") return `<div class="banner ok"><b>Checked against SQL's trial balance: agrees</b><span>${esc(ch.text)}</span></div>`;
  if (ch.outcome === "skipped") return `<div class="banner grey"><b>Not checked against SQL's trial balance</b><span>${esc(ch.text)}</span></div>`;
  // A trial balance read before a later journal: its differences may be out of date, so they aren't shown as errors.
  if (ch.stale) return `<div class="banner grey"><b>Checked against SQL's trial balance: possibly out of date</b><span>${esc(ch.text)}</span>
    <div class="tbl-wrap"><table><thead><tr><th>Account</th><th>May differ (re-export SQL's trial balance to check)</th><th class="num">SQL then</th><th class="num">Here</th><th class="num">Difference</th></tr></thead><tbody>
    ${ch.differences.map(x => `<tr><td class="mono">${esc(x.code)}</td><td>${esc(x.text)}</td><td class="num">${drCr(x.sql_sen)}</td><td class="num">${drCr(x.here_sen)}</td><td class="num">${drCr(x.diff_sen)}</td></tr>`).join("")}
    </tbody></table></div></div>`;
  return `<div class="banner warn"><b>Checked against SQL's trial balance: differences</b><span>${esc(ch.text)}</span>
    <div class="tbl-wrap"><table><thead><tr><th>Account</th><th>What differs</th><th class="num">SQL</th><th class="num">Here</th><th class="num">Difference</th></tr></thead><tbody>
    ${ch.differences.map(x => `<tr><td class="mono">${esc(x.code)}</td><td>${esc(x.text)}</td><td class="num">${drCr(x.sql_sen)}</td><td class="num">${drCr(x.here_sen)}</td><td class="num">${drCr(x.diff_sen)}</td></tr>`).join("")}
    </tbody></table></div></div>`;
}

const acctName = r => r.code == null ? esc(r.name) : `${esc(r.name || "")}${r.name_from === "printed" ? ` <span class="pill warn">Not in chart</span>` : !r.name ? ` <span class="pill warn">Not in chart</span>` : ""}${r.rolled?.length ? `<div class="note">With ${esc(r.rolled.join(", "))}</div>` : ""}${r.control ? `<div class="note">Sub-ledger of ${esc(r.control)}</div>` : ""}`;

function tbHtml(d) {
  const resets = d.accounts.some(r => r.reset_sen);
  const starts = d.openings.map(o => o.as_of ? `${esc(o.words)} at ${esc(fmtDate(o.as_of))} (${plural(o.accounts, "account")})` : `${esc(o.words)} (${plural(o.accounts, "account")})`).join("; ");
  return `${sqlCheckBanner(ent()?.uses_sql ? d.check : null)}
    <div class="row spread"><h2>Trial balance, ${esc(fmtDate(d.from))} to ${esc(fmtDate(d.to))}</h2>
      ${d.balanced ? `<span class="pill ok">Balances</span>` : `<span class="pill bad">Doesn't balance</span>`}</div>
    ${starts ? `<div class="note">Openings from ${starts}.</div>` : ""}
    <div class="row"><label class="row tight"><input type="checkbox" id="bkRollup" ${d.rollup ? "checked" : ""}> Customers and suppliers added into their control accounts, as SQL prints them</label>
      ${listBarBooks()}</div>
    <div class="tbl-wrap"><table class="books-tb"><thead><tr><th>Code</th><th>Name</th><th class="num">Opening debit</th><th class="num">Opening credit</th><th class="num">Debit</th><th class="num">Credit</th>${resets ? `<th class="num">Year start</th>` : ""}<th class="num">Closing debit</th><th class="num">Closing credit</th></tr></thead>
    <tbody id="bkRows"></tbody>
    <tfoot><tr class="sql-lines-total"><td colspan="2">Total</td><td class="num">${rmPlain(d.totals.opening_dr_sen)}</td><td class="num">${rmPlain(d.totals.opening_cr_sen)}</td><td class="num">${rmPlain(d.totals.dr_sen)}</td><td class="num">${rmPlain(d.totals.cr_sen)}</td>${resets ? `<td class="num">${drCr(d.totals.reset_sen)}</td>` : ""}<td class="num">${rmPlain(d.totals.closing_dr_sen)}</td><td class="num">${rmPlain(d.totals.closing_cr_sen)}</td></tr></tfoot></table></div>
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

const listBarBooks = () => `<input type="search" id="bkSearch" value="${esc(state.books.q)}" placeholder="Search accounts" aria-label="Search accounts"><span class="muted" id="bkCount" aria-live="polite"></span>`;

function paintTbRows() {
  const d = state.books.tb, tb = $("#bkRows");
  if (!d || !tb) return;
  const resets = d.accounts.some(r => r.reset_sen);
  const rows = d.accounts.filter(r => LT.match(`${r.code || ""} ${r.name || ""} ${(r.rolled || []).join(" ")}`, state.books.q));
  tb.innerHTML = rows.map(r => `<tr><td class="mono">${r.code == null ? "—" : `<button type="button" class="linkish mono" data-bk-acct="${esc(r.code)}" title="Open the ledger of ${esc(r.code)}">${esc(r.code)}</button>`}</td>
    <td>${acctName(r)}</td><td class="num">${r.opening_sen == null ? "—" : rmCell(r.opening_dr_sen)}</td><td class="num">${r.opening_sen == null ? "—" : rmCell(r.opening_cr_sen)}</td>
    <td class="num">${rmCell(r.dr_sen)}</td><td class="num">${rmCell(r.cr_sen)}</td>${resets ? `<td class="num">${r.reset_sen ? drCr(r.reset_sen) : ""}</td>` : ""}
    <td class="num">${r.closing_sen == null ? "—" : rmCell(r.closing_dr_sen)}</td><td class="num">${r.closing_sen == null ? "—" : rmCell(r.closing_cr_sen)}</td></tr>`).join("")
    || `<tr><td colspan="${resets ? 9 : 8}" class="empty">${d.accounts.length ? "No account matches." : `No opening balance or account line is kept for these dates yet.${ent()?.uses_sql ? " Fetch SQL's reports on the SQL import page." : ""}`}</td></tr>`;
  const c = $("#bkCount"); if (c) c.textContent = `${rows.length} of ${d.accounts.length} shown`;
}

function ledgerHtml(d) {
  const B = state.books;
  const pick = `<div class="row" style="align-items:flex-end"><label class="field" style="min-width:280px"><span>Account (type to search)</span>
      <input id="bkAcct" list="bkChoices" value="${esc(B.account || "")}" placeholder="All accounts" autocomplete="off"></label>
      <datalist id="bkChoices">${(d.choices || []).map(c => `<option value="${esc(c.code)}">${esc(c.code)} ${esc(c.name || "")}</option>`).join("")}</datalist>
      ${B.account ? `<button class="ghost small" type="button" data-bk-all="1">All accounts</button>` : ""}</div>`;
  const acct = a => `<div class="card-in"><div class="row spread"><h3><span class="mono">${esc(a.code)}</span> ${esc(a.name || "")}${a.name_from === "printed" || !a.name ? ` <span class="pill warn">Not in chart</span>` : ""}</h3>
      ${a.control ? `<span class="note">Sub-ledger of <button type="button" class="linkish mono" data-bk-acct="${esc(a.control)}">${esc(a.control)}</button></span>` : ""}</div>
    <div class="tbl-wrap"><table class="books-ledger"><thead><tr><th>Date</th><th>Doc No</th><th>Book</th><th>Description</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead><tbody>
      <tr class="books-open"><td>${esc(shortDate(d.from))}</td><td></td><td></td><td>Opening balance${a.opening_words ? ` <span class="muted">· ${esc(a.opening_words)}${a.opening_as_of ? ` at ${esc(fmtDate(a.opening_as_of))}` : ""}</span>` : ""}</td><td></td><td></td><td class="num">${drCr(a.opening_sen)}</td></tr>
      ${a.rows.map(r => r.kind === "year_start" ? `<tr class="books-reset"><td>${esc(shortDate(r.date))}</td><td></td><td></td><td>${esc(r.description)}</td><td class="num">${rmCell(r.dr_sen)}</td><td class="num">${rmCell(r.cr_sen)}</td><td class="num">${drCr(r.balance_sen)}</td></tr>`
        : `<tr><td>${esc(shortDate(r.date))}</td><td>${r.origin === "sql" ? `<button type="button" class="linkish mono" data-bk-doc="${esc(r.doc_no)}" title="Show the lines of ${esc(r.doc_no)}">${esc(r.doc_no)}</button>` : `<span class="mono">${esc(r.doc_no)}</span>`}</td><td>${esc(BOOK_NAMES[r.book] || r.book || "")}</td>
          <td>${esc(r.description || "")}</td><td class="num">${rmCell(r.dr_sen)}</td><td class="num">${rmCell(r.cr_sen)}</td><td class="num">${drCr(r.balance_sen)}</td></tr>`).join("")}
      <tr class="sql-lines-total"><td colspan="4">Total for the period</td><td class="num">${rmPlain(a.dr_sen)}</td><td class="num">${rmPlain(a.cr_sen)}</td><td></td></tr>
      <tr class="books-open"><td>${esc(shortDate(d.to))}</td><td></td><td></td><td>Closing balance</td><td></td><td></td><td class="num">${drCr(a.closing_sen)}</td></tr>
    </tbody></table></div>${a.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}</div>`;
  return `${pick}<h2>General ledger, ${esc(fmtDate(d.from))} to ${esc(fmtDate(d.to))}</h2>
    ${d.accounts.map(acct).join("") || `<div class="note">No line or opening balance is kept for ${B.account ? esc(B.account) : "any account"} in these dates.</div>`}
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

// The financial statements (hrp/finstatements.py): the profit and loss account and the balance sheet, laid out as SQL
// prints them, from the trial balance with customers and suppliers added into their control accounts. Each section's
// amounts are shown its usual way round (income, liabilities and equity as credits); negatives are in brackets. An
// account's code opens its ledger, as on the trial balance. Read-only.
const fsAmt = n => n == null ? "—" : n < 0 ? `(${rmPlain(-n)})` : rmPlain(n);
const fsCells = (amounts, cols) => amounts.map((n, i) => `<td class="num${cols[i].role === "comparative" ? " fs-comp" : cols[i].role === "total" && cols.length > 1 && cols.some(c => c.role === "month") ? " fs-sum" : ""}">${fsAmt(n)}</td>`).join("");

function fsTable(d) {
  const cols = d.columns, n = cols.length;
  const head = `<tr><th>Account</th>${cols.map(c => `<th class="num${c.role === "comparative" ? " fs-comp" : ""}">${esc(c.label)}${c.role === "comparative" ? `<div class="note">Comparative</div>` : ""}</th>`).join("")}</tr>`;
  const row = r => r.kind === "group_total"
    ? `<tr class="fs-group"><td style="padding-left:${12 + r.depth * 18}px">${esc(r.name)}</td>${fsCells(r.amounts, cols)}</tr>`
    : `<tr><td style="padding-left:${12 + r.depth * 18}px">${r.code == null ? esc(r.name || "") : `<button type="button" class="linkish mono" data-bk-acct="${esc(r.code)}" title="Open the ledger of ${esc(r.code)}">${esc(r.code)}</button> ${esc(r.name || "")}`}${r.in_chart === false ? ` <span class="pill warn">Not in chart</span>` : ""}${r.rolled?.length ? `<div class="note">With ${esc(r.rolled.join(", "))}</div>` : ""}</td>${fsCells(r.amounts, cols)}</tr>`;
  const block = b => b.kind === "section"
    ? `<tr class="fs-head"><th colspan="${n + 1}">${esc(b.title)}${b.key === "not_classified" ? ` <span class="pill warn">Set their types in Setup</span>` : ""}</th></tr>
       ${b.rows.map(row).join("")}
       <tr class="fs-sub"><td>${esc(b.total_label)}</td>${fsCells(b.total, cols)}</tr>`
    : `<tr class="${b.kind === "total" ? "fs-total" : "fs-line"}"><td>${esc(b.label)}</td>${fsCells(b.amounts, cols)}</tr>`;
  return `<div class="tbl-wrap"><table class="fs"><thead>${head}</thead><tbody>${d.blocks.map(block).join("")}</tbody></table></div>`;
}

function fsBanner(good, title, text) {
  return `<div class="banner ${good === true ? "ok" : good === false ? "warn" : "grey"}"><b>${esc(title)}</b><span>${esc(text)}</span></div>`;
}

// A statement is empty when no account is listed in it (the totals between the sections are always there, all 0).
function fsEmpty(d) {
  return !d.blocks.some(b => b.kind === "section" || (b.kind === "line" && b.amounts.some(a => a !== 0)));
}

function plHtml(d) {
  const ch = d.check;
  if (fsEmpty(d)) return `${fsBanner(null, "Nothing to check", "No income or expense account moved in these dates.")}
    <h2>Profit and loss, ${esc(fmtDate(d.from))} to ${esc(fmtDate(d.to))}</h2>
    <div class="note">No income or expense account moved in these dates.</div>
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
  return `${fsBanner(ch.reconciles, ch.reconciles === true ? "Reconciles to the trial balance" : ch.reconciles === false ? "Doesn't reconcile to the trial balance" : "Not checked against the trial balance", ch.text)}
    <div class="row spread"><h2>Profit and loss, ${esc(fmtDate(d.from))} to ${esc(fmtDate(d.to))}</h2>
      <label class="row tight"><input type="checkbox" id="bkMonths" ${d.columns_mode === "month" ? "checked" : ""}> Months</label></div>
    <div class="note">Income is shown as a credit above 0 and costs as a debit above 0; a figure in brackets is the other way round.</div>
    ${fsTable(d)}
    ${d.comparative.shown ? "" : d.comparative.why ? `<div class="note">No comparative column: ${esc(d.comparative.why)}</div>` : ""}
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

function bsHtml(d) {
  const ch = d.check;
  if (fsEmpty(d)) return `${fsBanner(null, "Nothing to check", "No balance is kept at this day.")}
    <h2>Balance sheet at ${esc(fmtDate(d.as_at))}</h2>
    <div class="note">No balance is kept at this day.</div>
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
  const good = ch.balances === true && ch.reconciles === true ? true : ch.balances === false || ch.reconciles === false ? false : null;
  return `${fsBanner(good, good === true ? "Balances and reconciles to the trial balance" : ch.balances === false ? "Doesn't balance" : good === false ? "Doesn't reconcile" : "Can't be totalled", ch.text)}
    <div class="row spread"><h2>Balance sheet at ${esc(fmtDate(d.as_at))}</h2>
      ${d.balanced === true ? `<span class="pill ok">Balances</span>` : d.balanced === false ? `<span class="pill bad">Doesn't balance</span>` : ""}</div>
    <div class="note">As at the To date above. The profit or loss for the year to date runs from ${esc(fmtDate(d.fy_from))}. Assets are shown as debits above 0, liabilities and equity as credits above 0; a figure in brackets is the other way round.</div>
    ${fsTable(d)}
    ${d.comparative.shown ? "" : d.comparative.why ? `<div class="note">No comparative column: ${esc(d.comparative.why)}</div>` : ""}
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

// Customers and suppliers (hrp/receivables.py): who owes what, per debtor or creditor control account, with the ageing
// at the To date, the totals checked against the control account in the trial balance. Every amount is what is owed (a
// customer owes the company, the company owes a supplier); a figure in brackets is the other way round. A code opens the
// customer's or supplier's statement; a doc no. there opens its lines. Read-only.
const AR_AGE = ["current", "d31_60", "d61_90", "over_90"];

function partiesHtml(d) {
  const B = state.books, sup = B.side === "suppliers";
  const who = sup ? "supplier" : "customer";
  const toggle = `<div class="row spread"><h2>${sup ? "Suppliers" : "Customers"}, ${esc(fmtDate(d.from))} to ${esc(fmtDate(d.to))}</h2>
    <div class="seg" role="group" aria-label="Customers or suppliers">
      <button type="button" data-bk-side="customers" aria-pressed="${!sup}">Customers</button>
      <button type="button" data-bk-side="suppliers" aria-pressed="${sup}">Suppliers</button></div></div>`;
  if (!d.controls.length) return `${toggle}${fsBanner(null, "Nothing listed", d.text)}
    <div class="note">No ${who} balance is kept for these dates.${ent()?.uses_sql ? " Fetch SQL's GL Journal of Transaction and trial balance on the SQL import page." : ""}</div>
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
  const bf = d.controls.some(c => c.totals.ageing.brought_forward);
  const ages = AR_AGE.concat(bf ? ["brought_forward"] : []);
  const words = Object.fromEntries(d.buckets.map(b => [b.key, b.words]));
  const head = `<tr><th>Code</th><th>Name</th><th class="num">Opening</th><th class="num">Invoiced</th><th class="num">${sup ? "Paid" : "Received"}</th><th class="num">Other</th><th class="num">Closing</th>${ages.map(k => `<th class="num ar-age">${esc(words[k])}</th>`).join("")}</tr>`;
  const ageCells = r => r.credit ? `<td colspan="${ages.length}" class="ar-age"><span class="pill grey">In credit</span> <span class="muted">paid in advance or overpaid</span></td>`
    : r.ageing ? ages.map(k => `<td class="num ar-age">${rmCell(r.ageing[k])}</td>`).join("") : `<td colspan="${ages.length}" class="ar-age muted">—</td>`;
  const row = r => `<tr><td><button type="button" class="linkish mono" data-bk-party="${esc(r.code)}" title="Open the statement of ${esc(r.code)}">${esc(r.code)}</button></td>
    <td>${r.own ? `<span class="muted">${esc(r.name_words || "")}</span>` : esc(r.name || "")}${!r.own && r.name_from !== "party" ? ` <span class="pill warn" title="Not in Setup › Customers and suppliers: named ${r.name_from === "chart" ? "from the chart of accounts" : r.name_from === "printed" ? "as SQL printed it" : "by nobody yet"}">Not in Setup</span>` : ""}${r.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}</td>
    <td class="num">${fsAmt(r.opening_sen)}</td><td class="num">${rmCell(r.invoiced_sen)}</td><td class="num">${r.received_sen ? fsAmt(r.received_sen) : ""}</td><td class="num">${r.other_sen ? fsAmt(r.other_sen) : ""}</td>
    <td class="num"><b>${fsAmt(r.closing_sen)}</b></td>${ageCells(r)}</tr>`;
  const ctl = c => `<div class="card-in"><div class="row spread"><h3><button type="button" class="linkish mono" data-bk-acct="${esc(c.code)}" title="Open the ledger of ${esc(c.code)}">${esc(c.code)}</button> ${esc(c.name || "")}</h3>
      ${c.ties === true ? `<span class="pill ok">Ties to the trial balance</span>` : c.ties === false ? `<span class="pill bad">Doesn't tie</span>` : `<span class="pill grey">Can't be checked</span>`}</div>
    <div class="tbl-wrap"><table class="fs ar"><thead>${head}</thead><tbody>${c.rows.map(row).join("")}
      <tr class="fs-sub"><td colspan="2">Total</td><td class="num">${fsAmt(c.totals.opening_sen)}</td><td class="num">${rmPlain(c.totals.invoiced_sen)}</td><td class="num">${fsAmt(c.totals.received_sen)}</td><td class="num">${fsAmt(c.totals.other_sen)}</td><td class="num">${fsAmt(c.totals.closing_sen)}</td>${ages.map(k => `<td class="num ar-age">${rmPlain(c.totals.ageing[k])}</td>`).join("")}</tr>
      <tr class="fs-line"><td colspan="2">${esc(c.code)} in the trial balance</td><td class="num">${fsAmt(c.tb.opening_sen)}</td><td class="num" colspan="3">${esc(`Moved ${fsAmt(c.tb.moved_sen)}`)}</td><td class="num">${fsAmt(c.tb.closing_sen)}</td><td colspan="${ages.length}" class="ar-age">${c.totals.in_credit_sen ? `<span class="muted">In credit: ${esc(fsAmt(c.totals.in_credit_sen))}</span>` : ""}</td></tr>
    </tbody></table></div><div class="note">${esc(c.text)}</div></div>`;
  return `${toggle}${fsBanner(d.ties, d.ties === true ? "Ties to the control accounts" : d.ties === false ? "Doesn't tie to the control accounts" : "Not fully checked", d.text)}
    <div class="note">Each amount is what is owed: ${sup ? "what the company owes the supplier" : "what the customer owes the company"}; a figure in brackets is the other way round. Invoiced is what the ${sup ? "purchase" : "sales"} book added, ${sup ? "paid" : "received"} what the bank book took off, other everything else (credit notes, journals). The ageing is at ${esc(fmtDate(d.to))}.</div>
    <div class="note">${esc(d.ageing_note)}</div>
    ${d.controls.map(ctl).join("")}
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

function partyHtml(d) {
  const sup = d.side === "suppliers";
  const words = Object.fromEntries(d.buckets.map(b => [b.key, b.words]));
  const doc = r => r.doc_no == null ? "" : r.origin === "sql" ? `<button type="button" class="linkish mono" data-bk-doc="${esc(r.doc_no)}" title="Show the lines of ${esc(r.doc_no)}">${esc(r.doc_no)}</button>` : `<span class="mono">${esc(r.doc_no)}</span>`;
  const owed = d.owed_sen == null ? "unknown" : d.credit ? `${rmPlain(Math.abs(d.owed_sen))} in credit (paid in advance or overpaid)` : d.owed_sen === 0 ? "nothing" : rmPlain(d.owed_sen);
  const ageRow = d.ageing && !d.credit ? Object.keys(d.ageing).filter(k => k !== "brought_forward" || d.ageing[k]).map(k => `<span class="pill grey">${esc(words[k])}: ${esc(rmPlain(d.ageing[k]))}</span>`).join(" ") : "";
  return `<div class="row spread"><h2><span class="mono">${esc(d.code)}</span> ${esc(d.name || "")}${d.name_from !== "party" && d.code !== d.control ? ` <span class="pill warn">Not in Setup</span>` : ""}</h2>
      <button class="ghost small" type="button" data-bk-party-back="1">All ${sup ? "suppliers" : "customers"}</button></div>
    <div class="note">${sup ? "Supplier" : "Customer"} under <button type="button" class="linkish mono" data-bk-acct="${esc(d.control)}" title="Open the ledger of ${esc(d.control)}">${esc(d.control)}</button> ${esc(d.control_name || "")}. ${sup ? "Owed to them" : "Owed by them"} at ${esc(fmtDate(d.to))}: ${esc(owed)}.</div>
    <div class="tbl-wrap"><table class="books-ledger"><thead><tr><th>Date</th><th>Doc No</th><th>Book</th><th>Description</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead><tbody>
      <tr class="books-open"><td>${esc(shortDate(d.from))}</td><td></td><td></td><td>Opening balance</td><td></td><td></td><td class="num">${drCr(d.opening_sen)}</td></tr>
      ${d.rows.map(r => `<tr><td>${esc(shortDate(r.date))}</td><td>${doc(r)}</td><td>${esc(BOOK_NAMES[r.book] || r.book || "")}</td><td>${esc(r.description || "")}</td><td class="num">${rmCell(r.dr_sen)}</td><td class="num">${rmCell(r.cr_sen)}</td><td class="num">${drCr(r.balance_sen)}</td></tr>`).join("")}
      <tr class="books-open"><td>${esc(shortDate(d.to))}</td><td></td><td></td><td>Closing balance</td><td></td><td></td><td class="num">${drCr(d.closing_sen)}</td></tr>
    </tbody></table></div>
    <h3>Still open at ${esc(fmtDate(d.to))}</h3>
    ${ageRow ? `<div class="row">${ageRow}</div>` : ""}
    ${d.credit ? `<div class="note">In credit, so nothing is aged.</div>` : d.open_items.length ? `<div class="tbl-wrap"><table class="books-ledger"><thead><tr><th>Date</th><th>Doc No</th><th>Description</th><th class="num">Invoice</th><th class="num">Still open</th><th class="num">Days</th><th>Age</th></tr></thead><tbody>
      ${d.open_items.map(i => `<tr><td>${esc(shortDate(i.date))}</td><td>${doc(i)}</td><td>${esc(i.description || "")}</td><td class="num">${rmPlain(i.amount_sen)}</td><td class="num">${rmPlain(i.open_sen)}</td><td class="num">${i.days == null ? "" : esc(i.days)}</td><td>${esc(i.bucket_words)}</td></tr>`).join("")}
    </tbody></table></div>` : `<div class="note">Nothing is open.</div>`}
    <div class="note">${esc(d.ageing_note)}</div>
    ${d.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}`;
}

// The statutory payables check (hrp/statutory.py): for each statutory account confirmed in Setup, the payroll months of
// the period (the months of From and To; this financial year to date when they are empty) with what was taken off the
// salaries, the employer's share and what was paid for it, and whether it was paid in full by the due day. Months
// before the company's first month tracked are grey: shown, never asked for. Read-only, except Use these accounts, which
// adds the accounts the chart suggests as Setup would.
const ST_PILL = { cleared: "ok", due: "warn", late: "bad", short: "bad", over: "bad", nothing: "grey" };
const ST_WORDS = { cleared: "Cleared", due: "Due", late: "Late", short: "Short", over: "Over", nothing: "Nothing" };
const owedRm = n => n == null ? "—" : n === 0 ? "nil" : n < 0 ? `${rmPlain(-n)} owed` : `${rmPlain(n)} paid ahead`;

function statutoryHtml(d) {
  const sug = d.suggestion || [];
  const sugTable = sug.length ? `<div class="tbl-wrap"><table><thead><tr><th>Kind</th><th>Payable account</th><th>Employer's share account</th><th class="num">Due day</th></tr></thead><tbody>
    ${sug.map(x => `<tr><td>${esc(x.label)}</td><td><span class="mono">${esc(x.payable_code)}</span> ${esc(x.payable_name || "")}</td>
      <td>${x.employer_code ? `<span class="mono">${esc(x.employer_code)}</span> ${esc(x.employer_name || "")}` : "—"}</td><td class="num">${esc(x.due_day)}</td></tr>`).join("")}</tbody></table></div>` : "";
  if (!d.configured) {
    return `<h2>Statutory payables</h2><div class="banner grey"><b>Nothing is checked yet</b><span>${esc(d.summary)}${d.stopped ? "" : " Confirm which accounts the salary vouchers credit with what is taken off the salaries, and which take the employer's share."}</span></div>
      ${d.stopped ? `<div class="note">The statutory accounts confirmed for this company are all stopped in Setup. Start one again there to have it checked.</div><div class="row"><button class="ghost small" type="button" data-st-setup="1">Open Setup › Statutory accounts</button></div>`
        : sug.length ? `<div class="note">Suggested from the chart of accounts by their names:</div>${sugTable}
        <div class="row"><button class="btn" type="button" data-st-use="1">Use these accounts</button><button class="ghost small" type="button" data-st-setup="1">Set them up in Setup instead</button></div>`
        : `<div class="note">The chart of accounts has no account whose name looks like an EPF, SOCSO, EIS, SKBBK or PCB payable. Add them in Setup.</div><div class="row"><button class="ghost small" type="button" data-st-setup="1">Open Setup › Statutory accounts</button></div>`}`;
  }
  const bad = d.problems.length > 0;
  const doc = x => x.origin === "sql" ? `<button type="button" class="linkish mono" data-bk-doc="${esc(x.doc_no)}" title="Show the lines of ${esc(x.doc_no)}">${esc(x.doc_no)}</button>` : `<span class="mono">${esc(x.doc_no)}</span>`;
  const tracker = x => !x.tracker ? (x.origin === "sql" ? `<span class="muted">Not linked</span>` : "")
    : `<button type="button" class="linkish" data-st-pay="${esc(x.tracker.id)} ${esc(x.tracker.month)}" title="${esc(x.tracker.description || "")}">${esc(money(x.tracker.amount_sen == null ? null : x.tracker.amount_sen / 100))}</button>${x.tracker.paid_date ? ` <span class="muted">paid ${esc(fmtDate(x.tracker.paid_date))}</span>` : ""}
      ${x.tracker.matches ? `<span class="pill ok">Agrees</span>` : `<span class="pill warn" title="The voucher pays ${esc(rmPlain(x.tracker.expected_sen))} to the statutory accounts">Voucher pays ${esc(rmPlain(x.tracker.expected_sen))}</span>`}`;
  const pill = m => m.before_tracking ? `<span class="pill grey" title="Before the first month tracked: shown, never asked for">Before tracking · ${esc(ST_WORDS[m.status] || m.status)}</span>`
    : `<span class="pill ${ST_PILL[m.status] || "grey"}">${esc(ST_WORDS[m.status] || m.status)}</span>${m.paid_late ? ` <span class="pill warn">Paid late</span>` : ""}`;
  const row = m => {
    const pays = m.payments.length ? m.payments.map(x => `<div>${doc(x)} <span class="muted">${esc(shortDate(x.date))}</span></div>`).join("") : "—";
    const trk = m.payments.map(tracker).filter(Boolean).map(h => `<div>${h}</div>`).join("") || "—";
    return `<tr class="${m.before_tracking || m.status === "nothing" ? "muted" : ""}"><td>${esc(m.label)}<div class="note">Due ${esc(fmtDate(m.due))}</div></td>
      <td class="num">${rmPlain(m.withheld_sen)}${m.credits.length ? `<div class="note">${m.credits.map(x => doc(x) + (x.correction ? ` <span class="muted">(correction)</span>` : "")).join(", ")}</div>` : ""}</td>
      <td class="num">${rmCell(m.employer_sen)}</td><td class="num">${rmPlain(m.paid_sen)}</td>
      <td class="num">${m.difference_sen ? (m.difference_sen > 0 ? "+" : "−") + rmPlain(Math.abs(m.difference_sen)) : ""}</td>
      <td class="num">${owedRm(m.balance_due_sen)}</td>
      <td>${pill(m)}<div class="note">${esc(m.text)}</div></td><td>${pays}</td><td>${trk}</td></tr>`;
  };
  const acct = a => `<div class="card-in"><div class="row spread"><h3>${esc(a.label)} <span class="muted">· <span class="mono">${esc(a.payable_code)}</span> ${esc(a.payable_name || "")}</span></h3>
      <span class="note">${a.employer_code ? `Employer's share: <span class="mono">${esc(a.employer_code)}</span> ${esc(a.employer_name || "")}` : "No employer's share account"} · due by the ${esc(ordinal(a.due_day))} of the next month</span></div>
    <div class="note">Owed at ${esc(fmtDate(a.opening_day))}: ${a.opening_sen == null ? "unknown" : esc(owedRm(a.opening_sen))}${a.brought_forward.paid_sen ? `; ${esc(rmPlain(a.brought_forward.paid_sen))} of it paid since` : ""}${a.brought_forward.still_owed_sen ? `, ${esc(rmPlain(a.brought_forward.still_owed_sen))} still owed` : ""}.</div>
    <div class="tbl-wrap"><table><thead><tr><th>Month</th><th class="num">Withheld</th><th class="num">Employer share</th><th class="num">Paid</th><th class="num">Difference</th><th class="num">Balance at due date</th><th>Status</th><th>Payment voucher</th><th>Tracker payment</th></tr></thead>
    <tbody>${a.months.map(row).join("") || `<tr><td colspan="9" class="empty">No months in this period.</td></tr>`}</tbody></table></div>
    ${a.notes.map(n => `<div class="note">${esc(n)}</div>`).join("")}</div>`;
  return `<div class="row spread"><h2>Statutory payables, ${esc(monthName(d.from))} to ${esc(monthName(d.to))}</h2><button class="ghost small" type="button" data-st-setup="1">Statutory accounts in Setup</button></div>
    <div class="banner ${bad ? "warn" : d.empty ? "grey" : "ok"}"><b>${bad ? "Statutory payables to look at" : "Statutory payables"}</b><span>${esc(d.summary)}</span></div>
    ${(d.postings || []).length ? `<div class="banner warn"><b>Employer's share on another account</b>${d.postings.map(p => `<span>${doc(p)} ${esc(p.text.slice(p.doc_no.length))}${p.before_tracking ? ` <span class="pill grey">Before tracking</span>` : ""}</span>`).join("")}<span>Correct it in SQL Account with a journal moving the amount to the right account, then fetch again.</span></div>` : ""}
    <div class="note">Withheld is what the month's documents credit to the payable, with the corrections to it (a journal against the salary, shown as a correction, belongs to the month whose withholding it corrects). Paid is what the payments to the authority debit to it for that month (the month before their own first, else up to their own month), less any refund, with the employer's share they debit to its own account. The balance is the payable's, from the books, at the end of the due day.</div>
    ${d.accounts.map(acct).join("")}
    ${sug.length ? `<div class="note">The chart also has ${esc(sug.map(x => x.payable_code).join(", "))}, which look like statutory payables not checked. Add them in Setup if they are.</div>` : ""}`;
}

// Use these accounts: the accounts suggested from the chart are added as Setup would add them, then the check is drawn.
async function statutoryUse(t) {
  t.disabled = true;
  const here = pageHere();
  try {
    const r = await api("/api/statutory/use-suggested", { json: { entity_id: state.entity } });
    toast(`${plural(r.added, "statutory account")} added.`);
  } catch (e) { toast(changeError(e), true); t.disabled = false; return; }
  await afterSaved(savedPagePart(here, () => drawBooks({ saved: true })));
}

// A doc no. in the ledger opens that document's lines below its row, as on the SQL page; clicking it again closes them.
function booksDoc(t) {
  const row = t.closest("tr"), next = row?.nextElementSibling, no = t.dataset.bkDoc;
  if (next?.classList.contains("sql-lines-row") && next.dataset.doc === no) { next.remove(); return; }
  if (next?.classList.contains("sql-lines-row")) next.remove();
  return pageDraw(null, async page => {
    try {
      const v = await page.read(api(`/api/ledger/doc?entity=${state.entity}&doc_no=${encodeURIComponent(no)}`));
      const tr = document.createElement("tr");
      tr.className = "sql-lines-row"; tr.dataset.doc = no;
      tr.innerHTML = `<td colspan="${row.children.length}">${ledgerDocView(v)}</td>`;
      row.after(tr);
    } catch (e) { page.check(); toast(e.message, true); }
  });
}

// Which of the print settings are too long to print in full (their end is cut off), with where to shorten them.
const tooLongNote = rows => rows && rows.length ? `<div class="note"><b>Too long to print in full:</b><ul>${rows.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>` : "";
// Which of SQL's fonts this computer lacks and what invoices print instead (nothing when all are found).
const fontNote = fonts => fonts && fonts.length ? `<div class="note"><b>Fonts:</b><ul>${fonts.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>` : "";

function einvPill(x) {
  if (!x.einvoice && !x.einvoice_status) return `<span class="muted">—</span>`;
  const ok = (x.einvoice_status || "").startsWith("Validated") && !x.taken_back_by;
  const pill = `<span class="pill ${ok ? "ok" : "warn"}">${x.taken_back_by ? `Cancelled by ${esc(x.taken_back_by)}` : esc(x.einvoice_status || "Has UUID")}</span>`;
  return x.einvoice_link ? `${pill} <a href="${esc(x.einvoice_link)}" target="_blank" rel="noopener noreferrer">MyInvois ↗</a>` : pill;
}
